"""Top-level: explain a transaction's result and its ledger state changes."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from .diff import decode_meta, StateDiff
from .results import explain_result


@dataclass
class Explanation:
    result: Optional[str]
    category: str
    explanation: str
    diff: StateDiff


def _meta(tx: dict) -> dict:
    for k in ("meta", "metaData"):
        m = tx.get(k)
        if isinstance(m, dict):
            return m
    return {}


def explain(tx) -> Explanation:
    """Explain a transaction result that carries its `meta` (and optionally an
    `engine_result`). Returns the decoded result explanation and a typed state diff.
    Tolerates non-dict input (returns an 'unknown' explanation with no changes)."""
    if not isinstance(tx, dict):
        tx = {}
    meta = _meta(tx)
    code = meta.get("TransactionResult") or tx.get("engine_result")
    category, explanation = explain_result(code)
    return Explanation(code, category, explanation, decode_meta(meta))


def _nonzero(delta: Optional[str]) -> bool:
    if delta is None:
        return False
    try:
        return Decimal(delta) != 0
    except InvalidOperation:
        return False


def render(exp: Explanation) -> str:
    lines = [f"Result: {exp.result or '?'} ({exp.category})", f"  {exp.explanation}", ""]
    if not exp.diff.changes:
        lines.append("No ledger state changes decoded (no metadata, or nothing was applied).")
        return "\n".join(lines)
    lines.append("State changes:")
    for c in exp.diff.changes:
        who = f" [{c.account}]" if c.account else ""
        lines.append(f"  {c.action.upper()} {c.entry_type}{who}")
        for fc in c.fields:
            if _nonzero(fc.delta):
                lines.append(f"    {fc.name}: {fc.before} -> {fc.after}  (delta {fc.delta})")
            elif fc.before != fc.after:
                lines.append(f"    {fc.name}: {fc.before} -> {fc.after}")
    return "\n".join(lines)
