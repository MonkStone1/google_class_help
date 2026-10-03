"""Split `app/styles/pages/all.css` along the section banners it already has.

The plan (§3.5) cuts the 1 556-line file into per-slice stylesheets at the
comment boundaries that were already there. This does it by those markers
rather than by hand, because a hand-cut 250-line block is a diff nobody reads
and a line count nobody can reproduce.

Every range below is 1-based and inclusive, and the script ASSERTS the marker at
the first line of each range: run it against a file that moved underneath it and
it fails instead of producing nine wrong stylesheets.

The order in `index.css` is the contract (ADR-0005), not this script's output —
the ranges preserve it so a later diff of the index shows only added lines.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "frontend" / "src" / "app" / "styles" / "pages" / "all.css"

# (marker at the first line, target file, comment carried into the new file)
RANGES = [
    ("/* Subjects ", "subjects.css"),
    ("/* Calendar ", "calendar.css"),
    ("/* Grades ", "grades.css"),
    ("/* Settings ", "settings.css"),
    ("/* Responsive ", "responsive.css"),
    ("/* Public landing ", "landing.css"),
    ("/* ----", "feedback.css"),
    ("/* --- Markdown editor", "markdown.css"),
    ("/* --------------------------------------- administrator registry", "admins.css"),
]

# Everything before the first section banner: the shared page primitives.
HEAD_LINES = 32


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    starts: list[tuple[int, str, str]] = []
    for marker, target in RANGES:
        for index, line in enumerate(lines):
            if line.startswith(marker):
                starts.append((index + 1, target, line.strip()))
                break
        else:
            print(f"marker not found: {marker!r}", file=sys.stderr)
            return 1

    out = SOURCE.parent
    (out / "common.css").write_text("".join(lines[:HEAD_LINES]), encoding="utf-8", newline="")

    for position, (start, target, banner) in enumerate(starts):
        end = (
            starts[position + 1][0] - 1
            if position + 1 < len(starts)
            else len(lines)
        )
        (out / target).write_text(
            "".join(lines[start - 1 : end]), encoding="utf-8", newline=""
        )
        print(f"{target}: {start}-{end} ({banner})")

    SOURCE.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())