"""Restore moved files from HEAD, so a botched re-root can be undone.

A file that was moved AND re-rooted cannot be recovered with `git checkout` on
its new path — git does not know that path yet. This reads the blob at the OLD
path out of HEAD and writes it to the NEW one, which is the exact inverse of the
move and leaves only the import rewriting to redo.

Usage: python tools/restore_moved.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

MOVES = {
    "components/Badges.tsx": "entities/assignment/ui/Badges.tsx",
    "components/SubjectCards.tsx": "entities/course/ui/SubjectCards.tsx",
    "components/TicketMessage.tsx": "entities/feedback/ui/TicketMessage.tsx",
    "components/TicketMessage.test.tsx": "entities/feedback/ui/TicketMessage.test.tsx",
    "components/AttachmentList.tsx": "entities/feedback/ui/AttachmentList.tsx",
    "components/Skeletons.tsx": "shared/ui/Skeletons.tsx",
    "components/StatCard.tsx": "shared/ui/StatCard.tsx",
    "components/CollapsibleCard.tsx": "shared/ui/CollapsibleCard.tsx",
    "components/CollapsibleCard.test.tsx": "shared/ui/CollapsibleCard.test.tsx",
    "components/ConfirmDialog.tsx": "shared/ui/ConfirmDialog.tsx",
    "components/ConfirmDialog.test.tsx": "shared/ui/ConfirmDialog.test.tsx",
    "components/ErrorBoundary.tsx": "shared/ui/ErrorBoundary.tsx",
}


def main() -> int:
    for old, new in MOVES.items():
        blob = subprocess.run(
            ["git", "show", f"HEAD:frontend/src/{old}"],
            cwd=ROOT,
            capture_output=True,
        )
        if blob.returncode != 0:
            print(f"missing at HEAD: {old}", file=sys.stderr)
            return 1
        target = SRC / new
        target.write_bytes(blob.stdout)
        print(f"{old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())