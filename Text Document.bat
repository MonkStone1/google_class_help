cd D:\Documents\google_class_help
docker compose --env-file .env.local -f compose.local.yml up -d postgres
docker compose --env-file .env.local -f compose.local.yml up -d web worker