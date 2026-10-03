"""Rewrite import specifiers after a batch of `git mv` operations (ADR-0040).

A restructure is mostly a question of paths: every file that used to import
`../api.ts` has to import the new location, and a missed one is a compile error
at best and a silently wrong module at worst. Doing that by hand across ~100
files is exactly the kind of tedious pass that gets half-done.

Usage:  python tools/rewrite_imports.py <mapping.json>

The mapping is `{"old/src/path.ts": "new/src/path.ts"}`; every occurrence of the
old path is rewritten to a specifier relative to the importing file's NEW
location, keeping the explicit extension the project uses everywhere (ADR-0005).

The mapping is bidirectional-aware: `vi.mock("...")` paths are rewritten too,
because they are strings and do not follow the module they name. That is the
single most common way a Vue/Vite-style restructure silently breaks its suite.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

# A quoted specifier preceded by `from`, a bare `import`, or a `vi.*` call.
# Comments are NOT excluded here on purpose — the script is deliberately simple,
# and a stale example path inside a doc comment is a small price for a rewrite
# that can be reviewed as one mechanical diff. Reviewers see the whole file.
SPECIFIER = re.compile(
    r"""(?P<prefix>"""
    r"""\bfrom\s+|\bimport\s+|\bimport\s*\(\s*|\bimportActual\s*\(\s*"""
    r"""|\bvi\.(?:mock|doMock)\s*\(\s*"""
    # `vi.importActual` is special: a long generic argument makes Prettier wrap
    # it, so the literal can sit several lines below the call —
    #   vi.importActual<typeof import("../api.ts")>(
    #     "../api.ts",
    #   )
    # — with `<…>` between the name and the parenthesis. Matching "everything up
    # to the first quote" is what covers both the wrapped and plain forms.
    r"""|\bvi\.importActual\b[^"']*"""
    r""")"""
    r"""(?P<quote>["'])(?P<path>[^"']+)(?P=quote)""",
)


def to_specifier(target: pathlib.PurePosixPath, importer: pathlib.PurePosixPath) -> str:
    """Relative specifier from the importer's directory to `target`."""
    target_parts = list(target.with_suffix("").parts)
    importer_parts = list(importer.with_suffix("").parts)[:-1]
    common = 0
    while (
        common < len(target_parts)
        and common < len(importer_parts)
        and target_parts[common] == importer_parts[common]
    ):
        common += 1
    up = [".."] * (len(importer_parts) - common)
    down = target_parts[common:]
    joined = "/".join(up + down) or "."
    prefix = "" if joined.startswith(".") else "./"
    # The extension is re-attached because `tsconfig.app.json` sets
    # `allowImportingTsExtensions` and every import in the project carries it.
    return f"{prefix}{joined}{target.suffix}"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    mapping: dict[str, str] = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    moved = {pathlib.PurePosixPath(old): pathlib.PurePosixPath(new) for old, new in mapping.items()}

    changed_files: list[str] = []
    for file in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx")):
        rel = file.relative_to(SRC).as_posix()
        if rel in mapping:
            continue
        text = file.read_text(encoding="utf-8")
        importer_new = moved.get(pathlib.PurePosixPath(rel), pathlib.PurePosixPath(rel))

        def replace(match: re.Match[str]) -> str:
            raw = match.group("path")
            if not raw.startswith("."):
                return match.group(0)
            # Resolve the literal against the importer's OLD location.
            old_importer = pathlib.PurePosixPath(rel)
            parts = list(old_importer.with_suffix("").parts)[:-1]
            for segment in raw.split("/"):
                if segment in ("", "."):
                    continue
                if segment == "..":
                    if not parts:
                        # A specifier that climbs above `src/` (a comment
                        # example, typically). Leave it alone rather than
                        # resolve it to a path that does not exist.
                        return match.group(0)
                    parts.pop()
                else:
                    parts.append(segment)
            resolved = pathlib.PurePosixPath("/".join(parts))
            if resolved not in moved:
                return match.group(0)
            specifier = to_specifier(moved[resolved], importer_new)
            return f"{match.group('prefix')}{match.group('quote')}{specifier}{match.group('quote')}"

        updated = SPECIFIER.sub(replace, text)
        if updated != text:
            file.write_text(updated, encoding="utf-8", newline="")
            changed_files.append(rel)

    for name in changed_files:
        print(f"rewrote {name}")
    print(f"{len(changed_files)} file(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())