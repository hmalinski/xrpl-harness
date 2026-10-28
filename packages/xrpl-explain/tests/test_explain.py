import pytest

from xrpl_explain import explain, render, decode_meta, explain_result

META = {
    "TransactionResult": "tesSUCCESS",
    "AffectedNodes": [
        {"ModifiedNode": {"LedgerEntryType": "AccountRoot", "LedgerIndex": "AAA",
                          "FinalFields": {"Account": "rSender", "Balance": "999999988", "Sequence": 6},
                          "PreviousFields": {"Balance": "1000000000", "Sequence": 5}}},
        {"ModifiedNode": {"LedgerEntryType": "MPToken", "LedgerIndex": "BBB",
                          "FinalFields": {"Account": "rHolder", "MPTokenIssuanceID": "ABC", "MPTAmount": "150"},
                          "PreviousFields": {"MPTAmount": "100"}}},
        {"ModifiedNode": {"LedgerEntryType": "MPTokenIssuance", "LedgerIndex": "CCC",
                          "FinalFields": {"Issuer": "rIssuer", "OutstandingAmount": "150"},
                          "PreviousFields": {"OutstandingAmount": "100"}}},
        {"CreatedNode": {"LedgerEntryType": "MPToken", "LedgerIndex": "DDD",
                         "NewFields": {"Account": "rNewHolder", "MPTokenIssuanceID": "ABC", "MPTAmount": "0"}}},
    ],
}
TX = {"TransactionType": "Payment", "hash": "H", "meta": META}


def _field(change, name):
    return next(f for f in change.fields if f.name == name)


# ---------------------------------------------------------------- basics

def test_result_decoded():
    exp = explain(TX)
    assert exp.result == "tesSUCCESS" and exp.category == "success"


def test_account_balance_delta_is_the_fee():
    ar = decode_meta(META).of_type("AccountRoot")[0]
    assert _field(ar, "Balance").delta == "-12"


def test_mpt_holder_and_issuance_deltas():
    diff = decode_meta(META)
    holder = [c for c in diff.of_type("MPToken") if c.action == "modified"][0]
    assert holder.account == "rHolder" and _field(holder, "MPTAmount").delta == "50"
    assert _field(diff.of_type("MPTokenIssuance")[0], "OutstandingAmount").delta == "50"


def test_created_object_detected():
    created = [c for c in decode_meta(META).of_type("MPToken") if c.action == "created"]
    assert created and created[0].account == "rNewHolder"


def test_render_is_readable():
    out = render(explain(TX))
    assert "tesSUCCESS" in out and "MPToken" in out and "delta 50" in out


def test_int_counter_gets_delta():
    ar = decode_meta(META).of_type("AccountRoot")[0]
    assert _field(ar, "Sequence").delta == "1"


# ---------------------------------------------------------------- deleted nodes (the big fix)

def test_deleted_node_uses_previous_fields():
    meta = {"AffectedNodes": [{"DeletedNode": {
        "LedgerEntryType": "Offer",
        "FinalFields": {"Account": "rX", "TakerGets": "0",
                        "TakerPays": {"currency": "USD", "issuer": "rI", "value": "0"}},
        "PreviousFields": {"TakerGets": "5000000",
                           "TakerPays": {"currency": "USD", "issuer": "rI", "value": "3.012"}}}}]}
    offer = decode_meta(meta).of_type("Offer")[0]
    assert offer.action == "deleted"
    assert _field(offer, "TakerGets").delta == "-5000000"
    assert _field(offer, "TakerPays").delta == "-3.012"


def test_iou_value_delta():
    meta = {"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "RippleState", "LedgerIndex": "X",
            "FinalFields": {"Balance": {"currency": "USD", "issuer": "rI", "value": "30"}},
            "PreviousFields": {"Balance": {"currency": "USD", "issuer": "rI", "value": "10"}}}}]}
    assert _field(decode_meta(meta).of_type("RippleState")[0], "Balance").delta == "20"


# ---------------------------------------------------------------- added-field / dropped-node handling

def test_added_only_modified_node_is_kept():
    meta = {"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "DirectoryNode",
            "FinalFields": {"Owner": "rA"}, "PreviousFields": {}}}]}
    assert decode_meta(meta).of_type("DirectoryNode")  # kept, not silently dropped


def test_changed_field_with_added_sibling():
    meta = {"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "AccountRoot",
            "FinalFields": {"Account": "rA", "Domain": "ABCD", "Balance": "5"},
            "PreviousFields": {"Balance": "10"}}}]}
    ar = decode_meta(meta).of_type("AccountRoot")[0]
    assert _field(ar, "Balance").delta == "-5"
    assert "Domain" not in {f.name for f in ar.fields}  # added field not reconstructable


# ---------------------------------------------------------------- no bogus deltas

def test_hex_identifier_field_gets_no_delta():
    meta = {"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "AccountRoot",
            "FinalFields": {"Account": "rA", "Domain": "3133"}, "PreviousFields": {"Domain": "3132"}}}]}
    ar = decode_meta(meta).of_type("AccountRoot")[0]
    assert _field(ar, "Domain").delta is None


@pytest.mark.parametrize("vals", [("NaN", "5"), ("1e999999999", "0"), ("Infinity", "Infinity"), ("x", "5")])
def test_nonfinite_or_bad_amount_no_crash_no_delta(vals):
    before, after = vals
    meta = {"AffectedNodes": [{"ModifiedNode": {"LedgerEntryType": "AccountRoot",
            "FinalFields": {"Balance": after}, "PreviousFields": {"Balance": before}}}]}
    ar = decode_meta(meta).of_type("AccountRoot")[0]
    assert _field(ar, "Balance").delta is None  # and no exception


# ---------------------------------------------------------------- robustness

@pytest.mark.parametrize("meta", [
    None, 5, {"AffectedNodes": 5}, {"AffectedNodes": [1, "x", None]},
    {"AffectedNodes": [{"CreatedNode": "x"}]},
    {"AffectedNodes": [{"CreatedNode": {"NewFields": ["a"]}}]},
    {"AffectedNodes": [{"ModifiedNode": {"PreviousFields": "oops", "FinalFields": 3}}]},
    {"AffectedNodes": [{"DeletedNode": {"FinalFields": "x"}}]},
])
def test_malformed_meta_never_crashes(meta):
    assert isinstance(decode_meta(meta).changes, list)


@pytest.mark.parametrize("bad", [None, [], "x", 5])
def test_explain_tolerates_non_dict(bad):
    exp = explain(bad)
    assert exp.category == "unknown" and exp.diff.changes == []


# ---------------------------------------------------------------- result codes

def test_result_code_curated_and_prefix_fallback():
    assert explain_result("tecINVARIANT_FAILED")[0] == "failed, fee charged"
    assert explain_result("tecSOMETHING_NEW")[0] == "failed, fee charged"
    assert explain_result("temWHATEVER")[0] == "malformed"
    assert explain_result("tesSUCCESS")[0] == "success"
    assert explain_result(None)[0] == "unknown"


def test_tecpledged_is_not_presented_as_a_real_code():
    cat, msg = explain_result("tecPLEDGED")
    assert cat == "failed, fee charged" and "CollateralLock" not in msg


@pytest.mark.parametrize("code", ["temporary", "TEC_FOO", "tesSUCCESS ", "zzzFOO", "tec"])
def test_malformed_result_codes_are_unknown(code):
    assert explain_result(code)[0] == "unknown"
