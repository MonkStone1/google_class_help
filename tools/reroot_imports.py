"""Re-root the imports of a file that moved to a different depth.

`rewrite_imports.py` rewrites the IMPORTERS of a moved file; this one rewrites
the file itself, whose own `../shared/...` paths were written for its old depth.
Both are needed for a move, and forgetting the second leaves a file that
compiles nowhere while its importers resolved fine.

The old directory matters: `../../shared/x` written in `src/components/` names
`src/shared/x`, and resolving it from the file's NEW home (`src/entities/user/`)
would land somewhere else entirely. So each file is restored and re-rooted
together, never one without the other.

Usage: python tools/reroot_imports.py <old-dir> <new-path> [<old-dir> <new-path> ...]
       python tools/reroot_imports.py --all <old-dir>
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "frontend" / "src").resolve()

# A module specifier, not any quoted string. The guard matters: `.donate-qr` in
# `querySelector(".donate-qr")` is a CSS class, and rewriting it into a path is
# how this script once produced `querySelector("../../components/.donate-qr")`
# and eleven failing tests that blamed the restructure.
#
# `head` is captured and re-emitted: without it the `from` / `import(` in front
# of the literal is swallowed too, and the result does not parse.
SPECIFIER = re.compile(
    r'(?P<head>(?:from|import\(|importActual\(|vi\.mock\(|vi\.importActual\()\s*)'
    r'(?P<quote>["\'])(?P<path>\.[^"\']+)(?P=quote)'
)


def reroot(old_dir: str, new_path: str) -> bool:
    import os

    path = SRC / new_path
    text = path.read_text(encoding="utf-8")

    def fix(match: re.Match[str]) -> str:
        old = pathlib.PurePosixPath(match.group("path"))
        # Resolve against the file's OLD directory, then ask for the path back
        # from its NEW one. Doing it with `os.path.relpath` rather than counting
        # `../` by hand is what keeps this correct on a Windows drive letter,
        # where `SRC` is `D:\...` and a hand-rolled prefix silently doubles up.
        target = ((SRC / old_dir) / old).resolve()
        try:
            new = os.path.relpath(target, path.parent)
        except ValueError:
            return match.group(0)
        return (
            f'{match.group("head")}{match.group("quote")}'
            f'{new.replace(os.sep, "/")}{match.group("quote")}'
        )

    updated_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        # A quoted `…/…` inside a comment is prose, not an import: this script
        # once rewrote a line of documentation and left a file that would not
        # parse. Comments are left exactly as they are.
        stripped = line.lstrip()
        if stripped.startswith(("//", "*", "/*")) or '"' not in line and "'" not in line:
            updated_lines.append(line)
            continue
        updated_lines.append(SPECIFIER.sub(fix, line))

    updated = "".join(updated_lines)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="")
        return True
    return False


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--all":
        # Every file that was moved OUT of one directory and now lives deeper.
        # The old directory is the only thing the script cannot infer, so it is
        # the one thing it is told.
        old_dir = args[1]
        targets = [
            path.relative_to(SRC).as_posix()
            for path in sorted(SRC.rglob("*.ts")) + sorted(SRC.rglob("*.tsx"))
            if path.relative_to(SRC).parts[0] in {"widgets", "features", "app", "entities"}
        ]
        changed = sum(reroot(old_dir, target) for target in targets)
        print(f"{changed} file(s) re-rooted")
        return 0
    if len(args) % 2 != 0:
        print(__doc__, file=sys.stderr)
        return 2
    changed = sum(reroot(args[i], args[i + 1]) for i in range(0, len(args), 2))
    print(f"{changed} file(s) re-rooted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())