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

# old path under components/ -> new path. Only files that are NOT yet committed
# belong here: anything already in a previous commit is safe, and `git show` will
# fail for it because `components/Badges.tsx` no longer exists in HEAD.
MOVES = {
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
    "components/Sidebar.tsx": "widgets/sidebar/Sidebar.tsx",
    "components/AdminSidebar.tsx": "widgets/sidebar/AdminSidebar.tsx",
    "components/SidebarNav.tsx": "widgets/sidebar/SidebarNav.tsx",
    "components/Sidebars.test.tsx": "widgets/sidebar/Sidebars.test.tsx",
    "components/TopBar.tsx": "widgets/topbar/TopBar.tsx",
    "components/TopBar.test.tsx": "widgets/topbar/TopBar.test.tsx",
    "components/SearchResults.tsx": "widgets/topbar/SearchResults.tsx",
    "components/Markdown.tsx": "widgets/markdown/Markdown.tsx",
    "components/Markdown.test.tsx": "widgets/markdown/Markdown.test.tsx",
    "components/MarkdownField.tsx": "widgets/markdown/MarkdownField.tsx",
    "components/MarkdownField.test.tsx": "widgets/markdown/MarkdownField.test.tsx",
    "components/Landing.tsx": "widgets/landing/Landing.tsx",
    "components/Landing.test.tsx": "widgets/landing/Landing.test.tsx",
    "components/SignIn.tsx": "widgets/landing/SignIn.tsx",
    "components/NotificationCenter.tsx": "features/notifications/NotificationCenter.tsx",
    "components/DonateCards.tsx": "features/donate/DonateCards.tsx",
    "components/DonateCards.test.tsx": "features/donate/DonateCards.test.tsx",
    "components/AssignmentModal.tsx": "features/assignment-modal/AssignmentModal.tsx",
    "components/AssignmentCard.tsx": "entities/assignment/ui/AssignmentCard.tsx",
    "components/BootSplash.tsx": "app/boot/BootSplash.tsx",
    "components/Toaster.tsx": "app/toaster/Toaster.tsx",
    "components/Toaster.test.tsx": "app/toaster/Toaster.test.tsx",
    "components/SyncToaster.tsx": "app/toaster/SyncToaster.tsx",
    "components/SyncToaster.test.tsx": "app/toaster/SyncToaster.test.tsx",
    "components/RequireAdmin.tsx": "app/router/RequireAdmin.tsx",
    "components/RequireAdmin.test.tsx": "app/router/RequireAdmin.test.tsx",
    "components/RequireSuperAdmin.tsx": "app/router/RequireSuperAdmin.tsx",
    "components/RequireSuperAdmin.test.tsx": "app/router/RequireSuperAdmin.test.tsx",
    "components/TeacherCourse.tsx": "pages/subject/ui/TeacherCourse.tsx",
}


def main() -> int:
    missing = 0
    for old, new in MOVES.items():
        blob = subprocess.run(
            ["git", "show", f"HEAD:frontend/src/{old}"],
            cwd=ROOT,
            capture_output=True,
        )
        if blob.returncode != 0:
            # Already committed under its new path in an earlier stage: nothing
            # to restore, and restoring would be wrong.
            print(f"already committed: {new}")
            missing += 1
            continue
        target = SRC / new
        target.write_bytes(blob.stdout)
        print(f"{old} -> {new}")
    print(f"{len(MOVES) - missing} restored, {missing} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())