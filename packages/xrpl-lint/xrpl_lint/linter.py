"""Linter engine: run the rule pack over one transaction or a list of them.

Also lints the inner transactions of a Batch (one level deep; a nested Batch is
reported by the `batch-structure` rule rather than descended into).
"""
from __future__ import annotations

from typing import List, Tuple, Union

from .rules import RULES, Finding


class LintInputError(ValueError):
    """Raised when the input is not a transaction object or a list of them."""


def lint_tx(tx: dict) -> List[Finding]:
    """Run every rule against a single transaction dict."""
    if not isinstance(tx, dict):
        raise LintInputError("a transaction must be a JSON object")
    findings: List[Finding] = []
    for rule_id, fn in RULES:
        try:
            findings.extend(fn(tx))
        except Exception as e:  # never silently swallow: surface it instead of implying "clean"
            findings.append(Finding("internal-error", "warn",
                f"rule {rule_id!r} failed on this input ({type(e).__name__}); its result is unknown."))
    return findings


def _unwrap(tx):
    """Accept common wrappers around a tx: {"tx_json": {...}} and {"result": {"tx_json": {...}}}."""
    if isinstance(tx, dict):
        if isinstance(tx.get("tx_json"), dict):
            return tx["tx_json"]
        res = tx.get("result")
        if isinstance(res, dict) and isinstance(res.get("tx_json"), dict):
            return res["tx_json"]
    return tx


def lint(txs: Union[dict, list]) -> List[Tuple[int, Finding]]:
    """Lint a transaction dict or a list of them. Returns (index, finding) pairs.

    Raises LintInputError if the top-level input is neither an object nor a list.
    """
    if isinstance(txs, dict):
        txs = [txs]
    elif not isinstance(txs, list):
        raise LintInputError("input must be a transaction object or a list of transaction objects")

    results: List[Tuple[int, Finding]] = []
    for i, raw_tx in enumerate(txs):
        tx = _unwrap(raw_tx)
        if not isinstance(tx, dict):
            results.append((i, Finding("not-an-object", "error",
                "entry is not a JSON object; expected a transaction.")))
            continue
        for f in lint_tx(tx):
            results.append((i, f))
        # Lint Batch inner transactions one level deep.
        if tx.get("TransactionType") == "Batch" and isinstance(tx.get("RawTransactions"), list):
            for j, entry in enumerate(tx["RawTransactions"]):
                inner = entry.get("RawTransaction") if isinstance(entry, dict) else None
                if isinstance(inner, dict) and inner.get("TransactionType") != "Batch":
                    for f in lint_tx(inner):
                        results.append((i, Finding(f.rule_id, f.severity,
                            f"[RawTransactions[{j}]] {f.message}")))
    return results


def has_errors(results: List[Tuple[int, Finding]]) -> bool:
    return any(f.severity == "error" for _, f in results)
