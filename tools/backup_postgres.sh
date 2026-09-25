#!/bin/sh
# PostgreSQL backup / restore helper for the hosted deployment
# (migration stage 10, §57; DDoS plan §26).
#
# The database is the authoritative store of users, sessions, encrypted OAuth
# grants and the Classroom cache, so it is the only thing that must be backed
# up. Secrets are NOT in the dump: .env (Fernet key, Google web client secret,
# tunnel token) is backed up separately and encrypted.
#
# Usage (from the repository root, on the VPS):
#
#   ./tools/backup_postgres.sh dump          # write backups/<date>.dump
#   ./tools/backup_postgres.sh restore FILE  # restore a dump (STOPS the app)
#   ./tools/backup_postgres.sh list          # show local dumps
#
# Environment (optional): BACKUP_DIR, POSTGRES_USER, POSTGRES_DB.
#
# Recommended cron (daily 03:30 UTC):
#   30 3 * * * cd /opt/google_class_help && ./tools/backup_postgres.sh dump >> logs/backup.log 2>&1
#
# Keep a few rolling dumps ON the VPS for fast recovery, and periodically copy
# one encrypted dump to another machine. Never commit dumps to Git.

set -eu

BACKUP_DIR="${BACKUP_DIR:-backups}"
PG_USER="${POSTGRES_USER:-google_class_help}"
PG_DB="${POSTGRES_DB:-google_class_help}"
KEEP="${BACKUP_KEEP:-7}"

compose() {
	# docker compose reads .env for ${POSTGRES_PASSWORD} interpolation.
	docker compose "$@"
}

cmd_dump() {
	mkdir -p "$BACKUP_DIR"
	stamp="$(date +%F-%H%M)"
	target="${BACKUP_DIR}/googleclasshelp-${stamp}.dump"
	echo "==> pg_dump (custom format) -> ${target}"
	compose exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" --format=custom >"$target"
	echo "==> done ($(wc -c <"$target") bytes)"
	# Rolling retention: keep the newest $KEEP dumps.
	ls -1t "${BACKUP_DIR}"/googleclasshelp-*.dump 2>/dev/null | tail -n +"$((KEEP + 1))" | while read -r old; do
		echo "==> pruning ${old}"
		rm -f "$old"
	done
	echo "==> remember: keep an encrypted copy OFF this VPS (scp the file, store the passphrase elsewhere)"
	echo "    restore secrets too: .env (Fernet key, GOOGLE_CLIENT_SECRET, CLOUDFLARE_TUNNEL_TOKEN)"
}

cmd_restore() {
	file="${1:?usage: $0 restore <dump file>}"
	[ -f "$file" ] || { echo "no such dump: $file" >&2; exit 1; }
	echo "==> stopping web + worker so nothing writes during restore"
	compose stop web worker
	echo "==> pg_restore --clean --if-exists from ${file}"
	compose exec -T postgres pg_restore -U "$PG_USER" -d "$PG_DB" --clean --if-exists <"$file"
	echo "==> applying migrations (dump is data-only history, schema may lag)"
	compose run --rm web alembic -c /app/alembic.ini upgrade head
	echo "==> starting web + worker"
	compose start web worker
	echo "==> verify: curl -fsS https://<domain>/api/ready"
}

cmd_list() {
	ls -1t "${BACKUP_DIR}"/googleclasshelp-*.dump 2>/dev/null || echo "no dumps in ${BACKUP_DIR}"
}

case "${1:-}" in
dump) cmd_dump ;;
restore) shift; cmd_restore "$@" ;;
list) cmd_list ;;
*)
	echo "usage: $0 {dump|restore <file>|list}" >&2
	exit 2
	;;
esac
