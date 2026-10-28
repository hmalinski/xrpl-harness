"""Rule pack. Each rule takes one transaction dict and returns a list of Findings.

Rules do not depend on ledger state, so a finding never changes with the account's
on-ledger situation. Most rules are hard `error`s (the transaction is malformed and
rippled would reject it); a few are advisory `warn`s (a valid-but-risky pattern).
A rule should never raise; the engine isolates failures, but keep rules total anyway.

Flag/constant values are from the XRPL docs and the relevant XLS specs (Payment,
XLS-56 Batch). XRP amount grammar follows rippled's integer-drops convention.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Tuple

# --- Payment flags ---
TF_PARTIAL_PAYMENT = 0x00020000  # Payment: tfPartialPayment

# --- Batch (XLS-56) flags ---
TF_INNER_BATCH_TXN = 0x40000000  # marks an (unsigned) inner transaction of a Batch
BATCH_MODE_FLAGS = {
    "tfAllOrNothing": 0x00010000,
    "tfOnlyOne": 0x00020000,
    "tfUntilFailure": 0x00040000,
    "tfIndependent": 0x00080000,
}

# A Fee above this (1 XRP) is almost always a mistake (normal fees are ~10-15 drops).
MAX_SANE_FEE_DROPS = 1_000_000

# Canonical integer-drops string: ASCII digits, no sign, no leading zeros, no decimal/exponent.
_DROPS_RE = re.compile(r"0|[1-9][0-9]*")
_DIGITS_RE = re.compile(r"[0-9]+")

# Fields whose string form is XRP drops (and whose object form is an IOU/MPT amount).
_XRP_AMOUNT_FIELDS = ("Amount", "SendMax", "DeliverMin", "DeliverMax", "TakerGets", "TakerPays", "Amount2")

Severity = str  # "error" | "warn" | "info"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    message: str


Rule = Callable[[dict], List[Finding]]
RULES: List[Tuple[str, Rule]] = []


def rule(rule_id: str):
    def deco(fn: Rule) -> Rule:
        RULES.append((rule_id, fn))
        return fn
    return deco


def _flags(tx: dict) -> int:
    """Flags as an int. rippled accepts a decimal string too (e.g. "131072")."""
    f = tx.get("Flags", 0)
    if isinstance(f, bool):
        return 0
    if isinstance(f, int):
        return f
    if isinstance(f, str) and f.isascii() and f.isdigit():
        try:
            return int(f)
        except ValueError:
            return 0
    return 0


def _is_canonical_drops(v: str) -> bool:
    return bool(_DROPS_RE.fullmatch(v))


# ---------------------------------------------------------------- amount format

@rule("xrp-amount-format")
def _xrp_amount_format(tx: dict) -> List[Finding]:
    out: List[Finding] = []
    for field in _XRP_AMOUNT_FIELDS:
        if field not in tx:
            continue
        v = tx[field]
        if isinstance(v, dict):
            cur = v.get("currency")
            if isinstance(cur, str) and cur.upper() == "XRP":
                out.append(Finding("xrp-amount-format", "error",
                    f"{field} is an amount object with currency XRP. XRP must be a string of integer "
                    "drops, never an object."))
            continue  # otherwise a legitimate IOU/MPT amount object
        if isinstance(v, bool) or isinstance(v, (int, float)):
            out.append(Finding("xrp-amount-format", "error",
                f"{field} is a bare number ({v!r}). An XRP amount is a STRING of integer drops "
                f'(e.g. "1000000"); xrpl.js and xrpl-py reject a number here. IOU/MPT amounts are objects.'))
        elif isinstance(v, str):
            if v.startswith("-"):
                out.append(Finding("xrp-amount-format", "error",
                    f"{field} = {v!r} is negative; an XRP amount cannot be negative."))
            elif not _is_canonical_drops(v):
                out.append(Finding("xrp-amount-format", "error",
                    f"{field} = {v!r} is not canonical integer drops. Use ASCII digits with no decimal "
                    'point, exponent, sign, or leading zeros (e.g. "1000000").'))
        else:
            out.append(Finding("xrp-amount-format", "error",
                f"{field} = {v!r} has an unsupported type; expected an integer-drops string or an "
                "IOU/MPT amount object."))
    return out


# ---------------------------------------------------------------- partial payment

@rule("payment-partial-xrp-direct")
def _payment_partial_xrp_direct(tx: dict) -> List[Finding]:
    if tx.get("TransactionType") != "Payment" or not (_flags(tx) & TF_PARTIAL_PAYMENT):
        return []
    amount, send_max = tx.get("Amount"), tx.get("SendMax")
    xrp_direct = isinstance(amount, str) and (send_max is None or isinstance(send_max, str))
    if xrp_direct:
        return [Finding("payment-partial-xrp-direct", "error",
            "tfPartialPayment is set on an XRP-to-XRP Payment. rippled rejects this outright "
            "(temBAD_SEND_XRP_PARTIAL); partial payment only applies when a non-XRP asset is involved.")]
    return []


@rule("delivermin-without-partial")
def _delivermin_without_partial(tx: dict) -> List[Finding]:
    if tx.get("TransactionType") != "Payment":
        return []
    if "DeliverMin" in tx and not (_flags(tx) & TF_PARTIAL_PAYMENT):
        return [Finding("delivermin-without-partial", "error",
            "DeliverMin is set without tfPartialPayment. rippled rejects this (temBAD_AMOUNT); "
            "DeliverMin only applies to a partial payment.")]
    return []


@rule("partial-payment-no-delivermin")
def _partial_payment_no_delivermin(tx: dict) -> List[Finding]:
    # Advisory (valid, but risky): a partial payment with no DeliverMin floor.
    if tx.get("TransactionType") != "Payment" or not (_flags(tx) & TF_PARTIAL_PAYMENT) or "DeliverMin" in tx:
        return []
    amount, send_max = tx.get("Amount"), tx.get("SendMax")
    if isinstance(amount, str) and (send_max is None or isinstance(send_max, str)):
        return []  # XRP-direct is already a hard error above
    return [Finding("partial-payment-no-delivermin", "warn",
        "tfPartialPayment is set with no DeliverMin, so there is no floor on what is delivered for the "
        "SendMax you pay. Set DeliverMin to bound the downside. (Separately, the recipient must read "
        "delivered_amount, not Amount, to avoid the partial-payment accounting exploit.)")]


# ---------------------------------------------------------------- sequence / ticket

@rule("sequence-and-ticket")
def _sequence_and_ticket(tx: dict) -> List[Finding]:
    if tx.get("TicketSequence") is None or "Sequence" not in tx:
        return []
    seq = tx["Sequence"]
    is_zero = seq == "0" or (isinstance(seq, int) and not isinstance(seq, bool) and seq == 0)
    if not is_zero:
        return [Finding("sequence-and-ticket", "error",
            "A non-zero Sequence is set together with TicketSequence. A ticketed transaction must have "
            "Sequence = 0 (temSEQ_AND_TICKET).")]
    return []


# ---------------------------------------------------------------- fee

@rule("fee-format")
def _fee_format(tx: dict) -> List[Finding]:
    if "Fee" not in tx:
        return []
    fee = tx["Fee"]
    if isinstance(fee, str) and _DIGITS_RE.fullmatch(fee):
        return []
    return [Finding("fee-format", "error",
        f"Fee = {fee!r} must be a string of integer drops (e.g. \"12\").")]


@rule("high-fee")
def _high_fee(tx: dict) -> List[Finding]:
    fee = tx.get("Fee")
    if not (isinstance(fee, str) and _DIGITS_RE.fullmatch(fee)):
        return []  # malformed Fee is handled by fee-format
    if int(fee) > MAX_SANE_FEE_DROPS:
        return [Finding("high-fee", "warn",
            f"Fee is {fee} drops (> 1 XRP). Usually a fat-finger (normal fees are ~10-15 drops). "
            "A few transactions legitimately pay more (e.g. AccountDelete / AMMCreate pay the owner "
            "reserve); verify the intended fee.")]
    return []


# ---------------------------------------------------------------- batch structure

@rule("batch-structure")
def _batch_structure(tx: dict) -> List[Finding]:
    if tx.get("TransactionType") != "Batch":
        return []
    out: List[Finding] = []
    flags = _flags(tx)
    set_modes = [name for name, bit in BATCH_MODE_FLAGS.items() if flags & bit]
    if len(set_modes) != 1:
        out.append(Finding("batch-structure", "error",
            f"A Batch must set exactly one mode flag ({', '.join(BATCH_MODE_FLAGS)}); "
            f"found {set_modes or 'none'}."))
    raw = tx.get("RawTransactions")
    if not isinstance(raw, list):
        if raw is not None:
            out.append(Finding("batch-structure", "error",
                'RawTransactions must be an array of {"RawTransaction": {...}} objects.'))
        return out
    if len(raw) < 2:
        out.append(Finding("batch-structure", "error",
            f"A Batch needs at least 2 inner transactions (has {len(raw)}); fewer is temARRAY_EMPTY."))
    if len(raw) > 8:
        out.append(Finding("batch-structure", "error",
            f"A Batch allows at most 8 inner transactions (has {len(raw)}); more is temARRAY_TOO_LARGE."))
    for i, entry in enumerate(raw):
        inner = entry.get("RawTransaction") if isinstance(entry, dict) else None
        if not isinstance(inner, dict):
            out.append(Finding("batch-structure", "error",
                f'RawTransactions[{i}] must be an object of the form {{"RawTransaction": {{...}}}}.'))
            continue
        if inner.get("TransactionType") == "Batch":
            out.append(Finding("batch-structure", "error",
                f"RawTransactions[{i}] is itself a Batch; nested Batch is not allowed."))
        if inner.get("Fee") not in ("0", None):
            out.append(Finding("batch-structure", "error",
                f"RawTransactions[{i}] inner Fee must be \"0\" (temBAD_FEE); found {inner.get('Fee')!r}."))
        if not (_flags(inner) & TF_INNER_BATCH_TXN):
            out.append(Finding("batch-structure", "error",
                f"RawTransactions[{i}] must set the tfInnerBatchTxn flag (0x40000000)."))
        if inner.get("TxnSignature") not in (None, "") or inner.get("SigningPubKey") not in (None, ""):
            out.append(Finding("batch-structure", "error",
                f"RawTransactions[{i}] inner transactions must be unsigned (empty SigningPubKey, no "
                "TxnSignature)."))
    return out
