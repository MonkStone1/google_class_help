"""Move named imports between modules after a context was relocated (ADR-0040).

When a React context moves from `app/providers/DataProvider.tsx` into the layer
that owns it (`entities/user`, `features/sync`), every consumer has to import the
HOOK from the new place and keep importing the PROVIDER from the old one. Doing
that by hand across thirty files is exactly the pass that gets half-done, and a
half-done import rewrite shows up as a runtime failure in a test that mocks the
provider.

This rewrites one import statement per named symbol it finds in `FROM` and
leaves every other import alone.

Usage: python tools/split_imports.py <file> <from> <symbol=target> ...
"""

from __future__ import annotations

import pathlib
import re
import sys

IMPORT = re.compile(r"import\s+(type\s+)?\{([^}]*)\}\s+from\s+(\"[^\"]+\")\s*;", re.S)


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    path = pathlib.Path(sys.argv[1])
    source_module = sys.argv[2]
    routing = dict(arg.split("=", 1) for arg in sys.argv[3:])

    text = path.read_text(encoding="utf-8")

    def split(match: re.Match[str]) -> str:
        is_type, body, module = match.group(1) or "", match.group(2), match.group(3)
        if module != f'"{source_module}"':
            return match.group(0)
        # Two buckets: symbols that stay with the provider, and symbols that move
        # to the layer that now owns them.
        staying: list[str] = []
        moved: list[str] = []
        for raw in body.split(","):
            name = raw.strip()
            if not name:
                continue
            symbol = name.split(" as ")[0].strip()
            target = routing.get(symbol)
            if target is None:
                staying.append(f"  {name},")
                continue
            keyword = "import type" if is_type else "import"
            alias = f" as {name.split(' as ')[1].strip()}" if " as " in name else ""
            moved.append(f'{keyword} {{ {symbol}{alias} }} from "{target}";')
        parts = moved + (
            [f'import {{\n{"".join(staying)}\n}} from {module};'] if staying else []
        )
        return "\n".join(parts)

    updated = IMPORT.sub(split, text)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="")
        print(f"rewrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())