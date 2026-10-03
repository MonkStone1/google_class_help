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
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "frontend" / "src").resolve()

SPECIFIER = re.compile(r'(?P<quote>["\'])(?P<path>\.[^"\']+)(?P=quote)')


def reroot(old_dir: str, new_path: str) -> bool:
    path = SRC / new_path
    text = path.read_text(encoding="utf-8")
    # How many `../` reach `src/` from the file's NEW home — counted against
    # `SRC` itself, because `SRC` is absolute and its own parts would otherwise
    # be added to the prefix (which is how this produced 11 `../`).
    depth = len(path.parent.relative_to(SRC).parts)
    # `src/entities/user/model/x.ts` is three levels below `src/`, so three `..`;
    # a file directly in `src/` needs `./` rather than nothing.
    prefix = "../" * depth if depth else "./"

    def fix(match: re.Match[str]) -> str:
        old = pathlib.PurePosixPath(match.group("path"))
        target = ((SRC / old_dir) / old).resolve()
        try:
            relative = target.relative_to(SRC).as_posix()
        except ValueError:
            return match.group(0)
        return f'{match.group("quote")}{prefix}{relative}{match.group("quote")}'

    updated = SPECIFIER.sub(fix, text)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="")
        return True
    return False


def main() -> int:
    args = sys.argv[1:]
    if len(args) % 2 != 0:
        print(__doc__, file=sys.stderr)
        return 2
    changed = sum(reroot(args[i], args[i + 1]) for i in range(0, len(args), 2))
    print(f"{changed} file(s) re-rooted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())