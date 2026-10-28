"""Command-line entry point for xrpl-lint.

Exit codes: 0 = no error-severity findings, 1 = at least one error finding,
2 = could not read or parse the input (distinct from "lint errors found").
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .linter import lint, has_errors, LintInputError

_SEV_RANK = {"error": 0, "warn": 1, "info": 2}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="xrpl-lint",
        description="Static linter for XRPL transactions (catch footguns before you sign/submit).",
    )
    p.add_argument("file", nargs="?", help="JSON file with a transaction or a list of them; omit to read stdin.")
    a = p.parse_args(argv)

    try:
        if a.file:
            with open(a.file, encoding="utf-8-sig") as fh:  # utf-8-sig tolerates a BOM
                raw = fh.read()
        else:
            raw = sys.stdin.read()
    except OSError as e:
        print(f"xrpl-lint: cannot read input: {e}", file=sys.stderr)
        return 2

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:  # huge ints raise ValueError, not JSONDecodeError
        print(f"xrpl-lint: invalid JSON: {e}", file=sys.stderr)
        return 2

    try:
        results = lint(data)
    except LintInputError as e:
        print(f"xrpl-lint: {e}", file=sys.stderr)
        return 2

    if not results:
        print("xrpl-lint: no issues found.")
        return 0

    for i, f in sorted(results, key=lambda r: (r[0], _SEV_RANK.get(r[1].severity, 9))):
        print(f"[{f.severity.upper()}] tx#{i} {f.rule_id}: {f.message}")
    return 1 if has_errors(results) else 0


if __name__ == "__main__":
    sys.exit(main())
