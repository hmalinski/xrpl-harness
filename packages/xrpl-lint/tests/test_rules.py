import pytest

from xrpl_lint import lint, lint_tx, has_errors, LintInputError

TF_PARTIAL = 0x00020000
TF_INNER = 0x40000000
TF_ALL_OR_NOTHING = 0x00010000

IOU = {"currency": "USD", "issuer": "rIssuer", "value": "10"}
MPT = {"mpt_issuance_id": "00000000ABCDEF", "value": "10"}


def ids(results):
    return {f.rule_id for _, f in results}


def err_ids(results):
    return {f.rule_id for _, f in results if f.severity == "error"}


# ---------------------------------------------------------------- clean cases

def test_clean_payment_passes():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": "1000000", "Fee": "12", "Sequence": 5}
    assert lint(tx) == []


def test_iou_and_mpt_amounts_pass():
    for amt in (IOU, MPT):
        tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB", "Amount": amt}
        assert "xrp-amount-format" not in ids(lint(tx))


# ---------------------------------------------------------------- xrp-amount-format

@pytest.mark.parametrize("amount", [1000000, 1.5, True, "1.5", "-1", "--1", "0010", "１", "10²", "1e6", "+10", ["1"]])
def test_bad_xrp_amounts_flagged(amount):
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB", "Amount": amount}
    assert "xrp-amount-format" in err_ids(lint(tx))


@pytest.mark.parametrize("amount", ["0", "1", "1000000"])
def test_good_xrp_amounts_pass(amount):
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB", "Amount": amount}
    assert "xrp-amount-format" not in ids(lint(tx))


def test_xrp_as_object_flagged():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": {"currency": "XRP", "value": "1"}}
    assert "xrp-amount-format" in err_ids(lint(tx))


def test_other_amount_fields_checked():
    for field in ("DeliverMax", "TakerGets", "TakerPays", "Amount2"):
        tx = {"TransactionType": "X", field: 5}
        assert "xrp-amount-format" in err_ids(lint(tx)), field


# ---------------------------------------------------------------- partial payment

def test_xrp_direct_partial_is_error():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": "1000000", "Flags": TF_PARTIAL}
    assert "payment-partial-xrp-direct" in err_ids(lint(tx))


def test_cross_currency_partial_without_delivermin_is_warn_not_error():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": IOU, "Flags": TF_PARTIAL}
    r = lint(tx)
    assert "partial-payment-no-delivermin" in ids(r)
    assert "payment-partial-xrp-direct" not in ids(r)
    assert not has_errors(r)


def test_cross_currency_partial_with_delivermin_ok():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": IOU, "DeliverMin": IOU, "Flags": TF_PARTIAL}
    assert "partial-payment-no-delivermin" not in ids(lint(tx))


def test_delivermin_without_partial_flag_is_error():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": IOU, "DeliverMin": IOU}
    assert "delivermin-without-partial" in err_ids(lint(tx))


def test_string_flags_are_parsed():
    tx = {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
          "Amount": "1000000", "Flags": str(TF_PARTIAL)}
    assert "payment-partial-xrp-direct" in err_ids(lint(tx))


# ---------------------------------------------------------------- sequence / ticket

def test_sequence_and_ticket_nonzero_is_error():
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "Sequence": 7, "TicketSequence": 10}
    assert "sequence-and-ticket" in err_ids(lint(tx))


@pytest.mark.parametrize("seq", [0, "0"])
def test_ticket_with_zero_sequence_ok(seq):
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "Sequence": seq, "TicketSequence": 10}
    assert "sequence-and-ticket" not in ids(lint(tx))


def test_ticket_without_sequence_ok():
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "TicketSequence": 10}
    assert "sequence-and-ticket" not in ids(lint(tx))


# ---------------------------------------------------------------- fee

def test_high_fee_warns():
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "Fee": "5000000"}
    r = lint(tx)
    assert "high-fee" in ids(r) and not has_errors(r)


@pytest.mark.parametrize("fee", ["1.5", "-5", 12, True, "1_000", float("inf")])
def test_malformed_fee_is_error(fee):
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "Fee": fee}
    assert "fee-format" in err_ids(lint(tx))


# ---------------------------------------------------------------- batch

def _inner(dest, amount="1", **extra):
    base = {"TransactionType": "Payment", "Account": "rA", "Destination": dest,
            "Amount": amount, "Flags": TF_INNER, "Fee": "0", "SigningPubKey": ""}
    base.update(extra)
    return {"RawTransaction": base}


def test_valid_batch_passes():
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [_inner("rB"), _inner("rC")]}
    assert lint(tx) == []


def test_batch_needs_a_mode_flag():
    tx = {"TransactionType": "Batch", "Account": "rA",
          "RawTransactions": [_inner("rB"), _inner("rC")]}
    assert "batch-structure" in err_ids(lint(tx))


def test_batch_too_few_inners():
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [_inner("rB")]}
    assert "batch-structure" in err_ids(lint(tx))


def test_batch_nested_is_error():
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [_inner("rB"),
                              {"RawTransaction": {"TransactionType": "Batch", "Flags": TF_INNER, "Fee": "0",
                                                  "SigningPubKey": ""}}]}
    assert "batch-structure" in err_ids(lint(tx))


def test_batch_inner_fee_must_be_zero():
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [_inner("rB", Fee="10"), _inner("rC")]}
    assert "batch-structure" in err_ids(lint(tx))


def test_batch_inner_missing_inner_flag():
    inner = {"RawTransaction": {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
                                "Amount": "1", "Fee": "0", "SigningPubKey": ""}}
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [inner, _inner("rC")]}
    assert "batch-structure" in err_ids(lint(tx))


def test_batch_inner_transactions_are_linted():
    bad_inner = {"RawTransaction": {"TransactionType": "Payment", "Account": "rA", "Destination": "rB",
                                    "Amount": 1, "Flags": TF_INNER, "Fee": "0", "SigningPubKey": ""}}
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING,
          "RawTransactions": [bad_inner, _inner("rC")]}
    msgs = [f.message for _, f in lint(tx) if f.rule_id == "xrp-amount-format"]
    assert any("RawTransactions[0]" in m for m in msgs)


def test_batch_raw_transactions_not_a_list():
    tx = {"TransactionType": "Batch", "Account": "rA", "Flags": TF_ALL_OR_NOTHING, "RawTransactions": 5}
    assert "batch-structure" in err_ids(lint(tx))  # and does not crash


# ---------------------------------------------------------------- robustness

@pytest.mark.parametrize("bad", [None, 42, True, "abc"])
def test_scalar_input_raises(bad):
    with pytest.raises(LintInputError):
        lint(bad)


def test_non_dict_list_entry_reported():
    results = lint([{"TransactionType": "Payment", "Amount": "1"}, "junk", None])
    assert any(f.rule_id == "not-an-object" for _, f in results)
    assert has_errors(results)


def test_wrapper_tx_json_unwrapped():
    wrapped = {"result": {"tx_json": {"TransactionType": "Payment", "Account": "rA", "Amount": 1}}}
    assert "xrp-amount-format" in err_ids(lint(wrapped))


def test_lint_tx_rejects_non_dict():
    with pytest.raises(LintInputError):
        lint_tx(None)


def test_fee_overflow_does_not_crash():
    tx = {"TransactionType": "Payment", "Account": "rA", "Amount": "1", "Fee": float("inf")}
    r = lint(tx)  # must not raise
    assert "fee-format" in err_ids(r)
    assert not any(f.rule_id == "internal-error" for _, f in r)
