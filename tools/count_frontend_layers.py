"""Frontend structure inventory (ADR-0040, plan stage 0, step 6).

Prints file/line counts per layer so the numbers in PLAN.md and
FRONTEND_STRUCTURE.md can be re-taken with one command instead of being
re-counted by hand. Pure stdlib, no test framework: it is a developer aid,
not a guardrail (the guards live in frontend/src/test/structure.test.ts).
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend" / "src"
LAYERS = ("app", "pages", "widgets", "features", "entities", "shared")


def count_files(path: pathlib.Path, suffix: str) -> tuple[int, int]:
    files = [p for p in path.rglob(f"*{suffix}") if p.is_file()]
    return len(files), sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)


def count_layer(path: pathlib.Path) -> tuple[int, int]:
    """Every source file of a layer, `.ts` and `.tsx` counted together."""
    files = [
        p
        for p in path.rglob("*")
        if p.suffix in {".ts", ".tsx"} and p.is_file()
    ]
    return len(files), sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)


def main() -> int:
    if not SRC.is_dir():
        print(f"not found: {SRC}", file=sys.stderr)
        return 1

    source = [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"} and p.is_file()]
    source = [p for p in source if not p.name.endswith(".test.ts")
              and not p.name.endswith(".test.tsx")
              and p.name != "api-schema.d.ts"]
    tests = [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"}
             and p.is_file() and (p.name.endswith(".test.ts") or p.name.endswith(".test.tsx"))]
    css = [p for p in SRC.rglob("*.css") if p.is_file()]

    print(f"{'layer':<12}{'files':>7}{'lines':>9}")
    print("-" * 28)
    print(f"{'(source)':<12}{len(source):>7}{sum(len(p.read_text(encoding='utf-8').splitlines()) for p in source):>9}")
    for layer in LAYERS:
        path = SRC / layer
        if not path.is_dir():
            continue
        n, lines = count_layer(path)
        print(f"{layer:<12}{n:>7}{lines:>9}")
    tn, tl = 0, 0
    for path in SRC.rglob("*"):
        if not path.is_file() or path.suffix not in {".ts", ".tsx"}:
            continue
        name = path.name
        if name.endswith(".test.ts") or name.endswith(".test.tsx"):
            tn += 1
            tl += len(path.read_text(encoding="utf-8").splitlines())
    print(f"{'(tests)':<12}{tn:>7}{tl:>9}")
    cn, cl = count_files(SRC, ".css")
    print(f"{'(css)':<12}{cn:>7}{cl:>9}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())