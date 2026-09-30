"""Fail if a tracked text file contains NUL bytes or is not valid UTF-8.

Why this exists
---------------
``README.md`` shipped to GitHub for several commits with a 40-byte UTF-16LE
fragment ("# google-class-help") appended to its end — 20 NUL bytes inside an
otherwise valid UTF-8 file. Windows PowerShell 5.1's ``>>`` and ``Add-Content``
default to UTF-16LE, and an append never writes a BOM, so the corruption is
invisible in an editor (NUL is a legal U+0000 code point) but makes GitHub
treat the file as unrenderable and display it as plain text.

The check is cheap and runs in CI on every push/PR so the same class of
corruption cannot land again. It only inspects files Git tracks as text
(``git check-attr text``); declared binaries are skipped.

Usage (from the project root)::

    .venv\\Scripts\\python.exe tools\\check_text_encoding.py

Exits 0 when every tracked text file is clean, 1 with a report otherwise.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NUL = b"\x00"
BATCH_SIZE = 100


def _git(*args: str) -> bytes:
    """Run a git command in the repository root and return raw stdout."""
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    ).stdout


def _attr_batch(paths: list[Path]) -> dict[str, str]:
    """Return ``{path: text-attribute}`` for one batch of files.

    ``check-attr -z`` emits a flat stream of ``<path>\\0<attr>\\0<value>\\0``
    triples when the paths are passed as arguments, which is unambiguous.
    """
    out = _git(
        "check-attr",
        "-z",
        "text",
        "--",
        *[p.as_posix() for p in paths],
    )
    fields = out.split(b"\x00")
    # A trailing NUL terminates the last triple, so drop the empty tail.
    if fields and fields[-1] == b"":
        fields.pop()

    verdicts: dict[str, str] = {}
    for i in range(0, len(fields) - 2, 3):
        path = fields[i].decode("utf-8", "surrogateescape")
        value = fields[i + 2].decode("ascii", "replace")
        verdicts[path] = value
    return verdicts


def _looks_binary(data: bytes) -> bool:
    """Git's own heuristic: a NUL in the first 8000 bytes means binary.

    Reusing it keeps the check from flagging legitimate binaries (.png, .ico,
    .lnk) while still catching the failure mode we care about: a UTF-8 text
    file with a stray NUL-padded fragment appended at the very end.
    """
    return NUL in data[:8000]


def tracked_files() -> list[Path]:
    """Return tracked text files that Git does not treat as binary."""
    raw = _git("ls-files", "-z")
    candidates = [
        Path(p.decode("utf-8", "surrogateescape")) for p in raw.split(b"\x00") if p
    ]
    existing = [p for p in candidates if (REPO_ROOT / p).is_file()]
    if not existing:
        return []

    # Batched because Windows caps the command line; the output format is
    # positional, so the batches can be merged freely.
    verdicts: dict[str, str] = {}
    for start in range(0, len(existing), BATCH_SIZE):
        verdicts.update(_attr_batch(existing[start : start + BATCH_SIZE]))

    text_files: list[Path] = []
    for path in existing:
        value = verdicts.get(path.as_posix())
        if value == "unset":
            # Explicitly declared binary (-text / binary attribute).
            continue
        if value == "set":
            text_files.append(path)
            continue
        # "auto" or "unspecified": let the NUL sniff decide.
        if not _looks_binary((REPO_ROOT / path).read_bytes()):
            text_files.append(path)
    return text_files


def check(paths: list[Path]) -> list[str]:
    """Return a report line for every file that is not clean UTF-8 text."""
    problems: list[str] = []
    for path in paths:
        data = (REPO_ROOT / path).read_bytes()
        if NUL in data:
            offset = data.index(NUL)
            count = data.count(NUL)
            problems.append(
                f"{path.as_posix()}: {count} NUL byte(s), first at offset {offset}"
            )
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            problems.append(
                f"{path.as_posix()}: not valid UTF-8 ({exc.reason} at byte {exc.start})"
            )
    return problems


def main() -> int:
    paths = tracked_files()
    if not paths:
        print("No tracked text files to check.")
        return 0

    problems = check(paths)
    if problems:
        print("Tracked text files are corrupted:", file=sys.stderr)
        for line in problems:
            print(f"  {line}", file=sys.stderr)
        print(
            "\nHint: a PowerShell 5.1 `>>` / `Add-Content` / `Set-Content` append writes\n"
            "UTF-16LE by default. Re-save the file as UTF-8 (LF) or use\n"
            "`Out-File -Append -Encoding utf8NoBOM`.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(paths)} tracked text file(s) are NUL-free valid UTF-8.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
