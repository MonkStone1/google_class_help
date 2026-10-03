"""Cut a contiguous line range out of a file (ADR-0040 stage 2).

The plan moves whole blocks rather than rewriting them by hand: `filters.ts`
gave up its URL half to `shared/lib/url.ts`, and a 100-line deletion done by hand
is a diff nobody reads. The file is rewritten in place, and the removed block is
kept next to it so a wrong range is one command to undo.

Usage: python tools/cut_lines.py <file> <first> <last> [--undo]
"""

from __future__ import annotations

import pathlib
import shutil
import sys

BACKUP_SUFFIX = ".cutbak"


def main() -> int:
    if len(sys.argv) not in (4, 5):
        print(__doc__, file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    backup = path.with_suffix(path.suffix + BACKUP_SUFFIX)

    if len(sys.argv) == 5 and sys.argv[4] == "--undo":
        if not backup.exists():
            print(f"nothing to undo: {backup} does not exist", file=sys.stderr)
            return 1
        shutil.copyfile(backup, path)
        backup.unlink()
        print(f"restored {path}")
        return 0

    first, last = int(sys.argv[2]), int(sys.argv[3])
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not (1 <= first <= last <= len(lines)):
        print(f"range {first}-{last} is outside 1-{len(lines)}", file=sys.stderr)
        return 1
    shutil.copyfile(path, backup)
    removed = lines[first - 1 : last]
    kept = lines[: first - 1] + lines[last:]
    path.write_text("".join(kept), encoding="utf-8", newline="")
    print(
        f"cut {len(removed)} lines ({first}-{last}); "
        f"{len(kept)} remain; backup at {backup.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())