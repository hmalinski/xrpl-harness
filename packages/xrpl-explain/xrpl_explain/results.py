"""Map an XRPL transaction result code to a plain-language explanation.

A curated set of common and lending/MPT-relevant codes, with a prefix fallback so any
unrecognized but well-formed code still gets the right category (tes/tec/tem/tef/ter/tel).
"""
from __future__ import annotations

import re
from typing import Tuple

# code -> (category, explanation)
_CODES = {
    "tesSUCCESS": ("success", "The transaction succeeded; if this is a validated result, its changes are in the ledger."),
    # tem*: malformed, rejected before processing, no fee charged.
    "temBAD_SEND_XRP_PARTIAL": ("malformed", "tfPartialPayment was set on an XRP-to-XRP payment, which is not allowed."),
    "temBAD_AMOUNT": ("malformed", "An amount field is invalid (e.g. DeliverMin without tfPartialPayment, a non-positive amount, or mismatched assets)."),
    "temSEQ_AND_TICKET": ("malformed", "The transaction set both a non-zero Sequence and a TicketSequence; a ticketed transaction needs Sequence 0."),
    "temREDUNDANT": ("malformed", "The transaction would do nothing (e.g. sending to yourself)."),
    "temDISABLED": ("malformed", "The transaction uses a feature whose amendment is not enabled."),
    # tec*: failed but included; fee charged; only bookkeeping/cleanup state changes.
    "tecUNFUNDED_PAYMENT": ("failed, fee charged", "The sender did not have enough XRP to make the payment."),
    "tecUNFUNDED_OFFER": ("failed, fee charged", "The account did not have the funds it offered."),
    "tecPATH_PARTIAL": ("failed, fee charged", "Could not deliver the full Amount along available paths. Use tfPartialPayment with a DeliverMin to allow partial delivery."),
    "tecPATH_DRY": ("failed, fee charged", "No path/liquidity could deliver the amount (also returned for some vault arithmetic overflows, and for a plain payment to an account with no usable trust line)."),
    "tecNO_LINE": ("failed, fee charged", "A required trust line is missing or unsuitable — e.g. an OfferCreate under RequireAuth, Clawback, CheckCash, an NFT offer, or a vault withdrawal to a destination."),
    "tecNO_AUTH": ("failed, fee charged", "Not authorized to hold this asset; the issuer requires authorization (a trust line's lsfRequireAuth, or an MPToken's RequireAuth)."),
    "tecNO_PERMISSION": ("failed, fee charged", "The account lacks permission for this action (e.g. not a member of the required permissioned domain, or not the issuer)."),
    "tecINSUFFICIENT_RESERVE": ("failed, fee charged", "The account would drop below its reserve requirement."),
    "tecINSUF_RESERVE_LINE": ("failed, fee charged", "Not enough reserve to add another trust line."),
    "tecINSUF_RESERVE_OFFER": ("failed, fee charged", "Not enough reserve to add another offer."),
    "tecDIR_FULL": ("failed, fee charged", "A ledger directory (owner directory or an order-book page) is full."),
    "tecEXPIRED": ("failed, fee charged", "A time condition had already passed — e.g. an object's/offer's Expiration or CancelAfter, or a loan payment made after it was due."),
    "tecKILLED": ("failed, fee charged", "An offer was killed: a tfFillOrKill offer could not be fully filled, or a tfImmediateOrCancel offer traded nothing."),
    "tecFROZEN": ("failed, fee charged", "The trust line or asset is frozen."),
    "tecLOCKED": ("failed, fee charged", "The MPT/vault balance is locked by the issuer."),
    "tecINVARIANT_FAILED": ("failed, fee charged", "A ledger invariant check failed and the transaction's effect was not applied — a protocol-level safety net caught an inconsistency."),
    "tecOBJECT_NOT_FOUND": ("failed, fee charged", "A referenced ledger object does not exist."),
    "tecINSUFFICIENT_FUNDS": ("failed, fee charged", "Insufficient funds for this operation (e.g. a vault/loan amount)."),
    "tecLIMIT_EXCEEDED": ("failed, fee charged", "An amount exceeds a configured limit (e.g. a vault AssetsMaximum or a loan/broker cap)."),
    # tef*: failed, cannot be applied, not included, no fee.
    "tefPAST_SEQ": ("failed", "The sequence number is below the account's current sequence (already used, or skipped by ticket creation)."),
    "tefMAX_LEDGER": ("failed", "The transaction's LastLedgerSequence has passed; it can no longer be included."),
    "tefBAD_AUTH": ("failed", "The signing key is not authorized for this account."),
    # ter*: retryable.
    "terPRE_SEQ": ("retry", "The sequence number is higher than the account's current sequence; it may apply after earlier transactions."),
    "terQUEUED": ("retry", "The transaction was queued for a future ledger."),
}

_PREFIX = {
    "tes": ("success", "Succeeded (provisional unless this is a validated result)."),
    "tec": ("failed, fee charged", "Failed to achieve its purpose but was included in a ledger and charged the fee; state changes are limited to bookkeeping and cleanup (e.g. removing unfunded offers) — read the metadata."),
    "tem": ("malformed", "Malformed and rejected before processing; not included in any ledger and no fee charged. Fix the transaction."),
    "tef": ("failed", "Failed and cannot be applied (e.g. bad sequence or signature); not included; no fee charged."),
    "ter": ("retry", "Not applied yet but might succeed later (e.g. a future sequence number)."),
    "tel": ("local error", "Rejected locally by this server (e.g. fee too low here); may succeed on another server."),
}

_CODE_SHAPE = re.compile(r"(tes|tec|tem|tef|ter|tel)[A-Z][A-Za-z0-9_]*")


def explain_result(code) -> Tuple[str, str]:
    if not code or not isinstance(code, str):
        return ("unknown", "No result code present.")
    if code in _CODES:
        return _CODES[code]
    if _CODE_SHAPE.fullmatch(code):
        cat, base = _PREFIX[code[:3]]
        return (cat, f"{code}: {base}")
    return ("unknown", f"{code!r}: unrecognized result code.")
