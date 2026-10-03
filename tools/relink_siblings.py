"""Point a moved file at its neighbour when BOTH moved in the same batch.

The import re-rooting runs per file and resolves paths against the OLD
directory, so a file that imported a sibling out of `components/` ends up
pointing at `components/<sibling>` after the sibling moved too. Listing those
pairs explicitly is honest: each one is a decision about where a component
lives now, not a pattern to guess.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"

# (file, old literal, new literal)
PAIRS = [
    # app/router: the files moved out of components/, so every `../x` they
    # carried needs one more level.
    ("app/router/RequireAdmin.test.tsx", '"../shared/', '"../../shared/'),
    ("app/router/RequireAdmin.test.tsx", '"../entities/', '"../../entities/'),
    ("app/router/RequireAdmin.test.tsx", '"../features/', '"../../features/'),
    ("app/router/RequireAdmin.tsx", '"../entities/', '"../../entities/'),
    ("app/router/RequireSuperAdmin.test.tsx", '"../shared/', '"../../shared/'),
    ("app/router/RequireSuperAdmin.test.tsx", '"../entities/', '"../../entities/'),
    ("app/router/RequireSuperAdmin.test.tsx", '"../features/', '"../../features/'),
    ("app/router/RequireSuperAdmin.tsx", '"../entities/', '"../../entities/'),
    ("app/router/RequireAdmin.test.tsx", "../../shared/settings/SettingsProvider.tsx", "../../shared/settings/index.ts"),
    ("app/router/RequireSuperAdmin.test.tsx", "../../shared/settings/SettingsProvider.tsx", "../../shared/settings/index.ts"),
    ("app/router/RequireAdmin.test.tsx", "../../components/RequireAdmin.tsx", "./RequireAdmin.tsx"),
    ("app/router/RequireSuperAdmin.test.tsx", "../../components/RequireSuperAdmin.tsx", "./RequireSuperAdmin.tsx"),
    ("app/router/RequireAdmin.test.tsx", "../shared/settings/SettingsProvider.tsx", "../../shared/settings/index.ts"),
    ("app/router/RequireSuperAdmin.test.tsx", "../shared/settings/SettingsProvider.tsx", "../../shared/settings/index.ts"),
    ("app/toaster/SyncToaster.test.tsx", "../../components/SyncToaster.tsx", "./SyncToaster.tsx"),
    ("app/toaster/Toaster.test.tsx", "../../components/Toaster.tsx", "./Toaster.tsx"),
    ("features/donate/DonateCards.test.tsx", "../../components/DonateCards.tsx", "./DonateCards.tsx"),
    ("features/notifications/NotificationCenter.tsx", "../../components/TopBar.tsx", "../../widgets/topbar/index.ts"),
    ("pages/subject/ui/TeacherCourse.tsx", "../../../components/AssignmentCard.tsx", "../../../entities/assignment/index.ts"),
    ("widgets/landing/Landing.test.tsx", "../../components/Landing.tsx", "./Landing.tsx"),
    ("widgets/markdown/Markdown.test.tsx", "../../components/Markdown.tsx", "./Markdown.tsx"),
    ("widgets/markdown/MarkdownField.test.tsx", "../../components/MarkdownField.tsx", "./MarkdownField.tsx"),
    ("widgets/sidebar/Sidebar.tsx", "../../components/SidebarNav.tsx", "./SidebarNav.tsx"),
    ("widgets/sidebar/AdminSidebar.tsx", "../../components/SidebarNav.tsx", "./SidebarNav.tsx"),
    ("widgets/sidebar/Sidebars.test.tsx", "../../components/Sidebar.tsx", "./Sidebar.tsx"),
    ("widgets/sidebar/Sidebars.test.tsx", "../../components/AdminSidebar.tsx", "./AdminSidebar.tsx"),
    ("widgets/topbar/TopBar.tsx", "../../components/SearchResults.tsx", "./SearchResults.tsx"),
    ("widgets/topbar/TopBar.tsx", "../../components/NotificationCenter.tsx", "../../features/notifications/index.ts"),
    ("widgets/landing/Landing.tsx", "../../lib/signInChallenge.ts", "./useSignInChallenge.ts"),
    ("app/router/RequireAdmin.tsx", "../../components/RequireAdmin.tsx", "./RequireAdmin.tsx"),
]


def main() -> int:
    for name, old, new in PAIRS:
        path = SRC / name
        text = path.read_text(encoding="utf-8")
        if old not in text:
            print(f"skip (not found): {name}: {old}", file=sys.stderr)
            continue
        path.write_text(text.replace(old, new), encoding="utf-8", newline="")
        print(f"{name}: {old} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())