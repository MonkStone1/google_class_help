"""Repair a relative import that no longer resolves, by naming its target from `src/`.

A batch move produces two kinds of damage: a path that points at the OLD
location of a module that has since moved, and a path written by a previous
partial rewrite. Both have the same shape — the literal starts with `.`, the
file it names does not exist, and a file with the same SUFFIX does exist under
`src/` — so both are repaired by the same rule.

Deliberately conservative: nothing is rewritten unless the current literal does
not resolve AND a file with the same name exists somewhere in `src/`. A typo and
a moved file look alike, and guessing wrong would turn a compile error into a
wrong import.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "frontend" / "src").resolve()

# Any quoted literal that starts with `.`. The safety net is not the pattern but
# the two checks below: the current path must not resolve, and a module with
# that name must exist in `src/`. A CSS class (".donate-qr") fails both and is
# therefore never touched — which is why this can afford to be greedy enough to
# catch the `vi.importActual("…")` argument on its own line, where the generic
# bracket sits between the call and the string.
SPECIFIER = re.compile(r'(?P<quote>["\'])(?P<path>\.[^"\']+)(?P=quote)')


def existing() -> set[str]:
    return {
        path.relative_to(SRC).as_posix()
        for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx"))
    }


def main() -> int:
    targets = {
        path.name: path
        for path in SRC.rglob("*")
        if path.is_file()
    }
    # A name is ambiguous (`index.ts` exists in a dozen slices), so only unique
    # ones may be used to repair a broken import. Guessing between them would
    # turn a compile error into a wrong import, which is worse.
    unique = {
        name: path
        for name, path in targets.items()
        if sum(1 for other in SRC.rglob(name)) == 1
    }
    fixed = 0
    all_modules = [
        path
        for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx"))
        if path.is_file()
    ]

    for path in list(SRC.rglob("*.ts")) + list(SRC.rglob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        changed = False

        def fix(match: re.Match[str]) -> str:
            nonlocal changed
            literal = match.group("path")
            resolved = (path.parent / literal).resolve()
            if resolved.exists():
                # It resolves: either correct, or an import of a CSS/asset that
                # only the bundler understands. Either way, leave it alone.
                return match.group(0)
            candidate = unique.get(pathlib.PurePosixPath(literal).name)
            if candidate is None:
                # `index.ts` exists in a dozen slices, so the FILE NAME is
                # ambiguous. The tail of the path is not: `shared/i18n/index.ts`
                # names exactly one module in the tree, and that is the shape a
                # half-rewritten import has.
                tail = literal.lstrip("./").replace("\\", "/")
                matches = [
                    path
                    for path in all_modules
                    if path.as_posix().endswith("/" + tail)
                    or path.as_posix() == tail
                ]
                if len(matches) != 1:
                    return match.group(0)
                candidate = matches[0]
            import os

            replacement = os.path.relpath(candidate, path.parent).replace(os.sep, "/")
            if not replacement.startswith("."):
                replacement = "./" + replacement
            changed = True
            return (
                f'{match.group("quote")}'
                f'{replacement}{match.group("quote")}'
            )

        updated = SPECIFIER.sub(fix, text)
        if changed and updated != text:
            path.write_text(updated, encoding="utf-8", newline="")
            fixed += 1
    print(f"{fixed} file(s) repaired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())