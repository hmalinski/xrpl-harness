"""CLI: explain an XRPL transaction result (with its meta)."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .explain import explain, render


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="xrpl-explain",
        description="Explain an XRPL transaction result and its ledger state changes.",
    )
    p.add_argument("file", nargs="?", help="JSON file with a transaction result incl. its meta; omit for stdin.")
    a = p.parse_args(argv)

    try:
        if a.file:
            with open(a.file, encoding="utf-8-sig") as fh:
                raw = fh.read()
        else:
            raw = sys.stdin.read()
    except (OSError, UnicodeError) as e:
        print(f"xrpl-explain: cannot read input: {e}", file=sys.stderr)
        return 2
    try:
        tx = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"xrpl-explain: invalid JSON: {e}", file=sys.stderr)
        return 2

    if isinstance(tx, dict) and isinstance(tx.get("result"), dict):
        tx = tx["result"]  # unwrap a JSON-RPC `tx` response
    if not isinstance(tx, dict):
        print("xrpl-explain: expected a transaction object", file=sys.stderr)
        return 2

    print(render(explain(tx)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
