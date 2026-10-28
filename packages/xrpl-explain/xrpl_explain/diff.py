"""Decode a transaction's metadata (AffectedNodes) into a typed before/after state diff.

Type-agnostic: it works unchanged on every affected ledger object (AccountRoot,
RippleState, MPToken, Vault, Loan, ...). A signed delta is computed only for an
allowlist of amount/counter fields, so numeric-looking identifiers (hashes, Domain
hex, ...) never get a meaningless delta.

Metadata limits this cannot escape: a field that is *added* by a transaction has no
prior value in `PreviousFields`, so an addition-only change cannot be reconstructed
from metadata alone (the object is still reported, just without that field's delta).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, DecimalException, localcontext
from typing import Any, List, Optional

_ABSENT = object()  # distinguishes "field not present" from "present but null/non-numeric"

# Fields worth a signed delta. Everything else shows before -> after with no delta.
_DELTA_FIELDS = frozenset({
    # XRP drops / IOU / MPT amounts
    "Balance", "Amount", "Amount2", "SendMax", "DeliverMin", "DeliverMax",
    "TakerGets", "TakerPays", "MPTAmount", "OutstandingAmount", "LockedAmount",
    "ConfidentialOutstandingAmount",
    # vault / loan / amm
    "AssetsTotal", "AssetsAvailable", "AssetsMaximum", "SharesTotal",
    "LPTokenBalance", "PrincipalOutstanding", "PrincipalRequested", "CoverAvailable",
    # integer counters people want next to the fee
    "OwnerCount", "Sequence", "TicketCount", "MintedNFTokens", "BurnedNFTokens",
})


@dataclass
class FieldChange:
    name: str
    before: Any
    after: Any
    delta: Optional[str] = None  # signed decimal string, only for _DELTA_FIELDS


@dataclass
class ObjectChange:
    entry_type: str
    action: str  # "created" | "modified" | "deleted"
    ledger_index: Optional[str]
    account: Optional[str]
    fields: List[FieldChange] = field(default_factory=list)


@dataclass
class StateDiff:
    changes: List[ObjectChange] = field(default_factory=list)

    def of_type(self, entry_type: str) -> List[ObjectChange]:
        return [c for c in self.changes if c.entry_type == entry_type]


def _num(v: Any) -> Optional[Decimal]:
    """A finite Decimal for an XRP drops string, an int, or an IOU/MPT amount object; else None."""
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, int):
            return Decimal(v)
        if isinstance(v, str):
            d = Decimal(v)
        elif isinstance(v, dict) and "value" in v:
            d = Decimal(str(v["value"]))
        else:
            return None
        return d if d.is_finite() else None
    except (DecimalException, ValueError, TypeError):
        return None


def _delta(before: Any, after: Any) -> Optional[str]:
    b = Decimal(0) if before is _ABSENT else _num(before)
    a = Decimal(0) if after is _ABSENT else _num(after)
    if b is None or a is None:  # a present value that is not numeric -> cannot compute
        return None
    try:
        with localcontext() as ctx:
            ctx.prec = 200  # IOU exponents span -96..+80; avoid silent rounding
            return format(a - b, "f")
    except DecimalException:
        return None


def _d(x: Any) -> dict:
    return x if isinstance(x, dict) else {}


def _owner(fields: dict) -> Optional[str]:
    # Owner before Account: for pseudo-account objects (Vault, LoanBroker) Account is
    # the pseudo-account and Owner is the real owner.
    for k in ("Owner", "Account", "Borrower", "Issuer"):
        v = fields.get(k)
        if isinstance(v, str):
            return v
    return None


def _field_change(name: str, before: Any, after: Any) -> FieldChange:
    delta = _delta(before, after) if name in _DELTA_FIELDS else None
    return FieldChange(
        name,
        None if before is _ABSENT else before,
        None if after is _ABSENT else after,
        delta,
    )


def decode_meta(meta: Any) -> StateDiff:
    diff = StateDiff()
    if not isinstance(meta, dict):
        return diff
    nodes = meta.get("AffectedNodes")
    if not isinstance(nodes, list):
        return diff
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if "CreatedNode" in node:
            n = node["CreatedNode"]
            if not isinstance(n, dict):
                continue
            nf = _d(n.get("NewFields"))
            changes = [_field_change(k, _ABSENT, v) for k, v in nf.items()]
            diff.changes.append(ObjectChange(n.get("LedgerEntryType", "?"), "created",
                                             n.get("LedgerIndex"), _owner(nf), changes))
        elif "ModifiedNode" in node:
            n = node["ModifiedNode"]
            if not isinstance(n, dict):
                continue
            ff, pf = _d(n.get("FinalFields")), _d(n.get("PreviousFields"))
            # PreviousFields holds prior values for CHANGED fields only; added fields
            # (present in FinalFields, absent from PreviousFields) are not reconstructable.
            changes = [_field_change(k, pf[k], ff.get(k, _ABSENT)) for k in pf]
            diff.changes.append(ObjectChange(n.get("LedgerEntryType", "?"), "modified",
                                             n.get("LedgerIndex"), _owner(ff), changes))
        elif "DeletedNode" in node:
            n = node["DeletedNode"]
            if not isinstance(n, dict):
                continue
            ff, pf = _d(n.get("FinalFields")), _d(n.get("PreviousFields"))
            keys = list(ff.keys()) + [k for k in pf if k not in ff]
            # True pre-transaction value is PreviousFields[k] when the field changed in
            # this tx, else FinalFields[k]; the object is then deleted (after absent).
            changes = [_field_change(k, pf.get(k, ff.get(k)), _ABSENT) for k in keys]
            diff.changes.append(ObjectChange(n.get("LedgerEntryType", "?"), "deleted",
                                             n.get("LedgerIndex"), _owner(ff), changes))
    return diff
