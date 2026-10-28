# xrpl-explain

Explain an XRP Ledger transaction result: a **typed before/after state diff** and a
**plain-language explanation of the result code**. It decodes the affected ledger objects
from a transaction's metadata — **MPT, Vault and Loan included** (type-agnostic, no
special-casing), which xrpl-py's balance helpers skip — and computes a signed delta for
amount/counter fields. (Fields a transaction *adds* have no prior value in the metadata, so
added-only changes aren't reconstructable from meta alone.)

Pure-Python, no node needed: it works on the `meta` that a single `tx` response, one
`account_tx` entry, or a `simulate` result already contains (text metadata, not `binary`
mode). A standalone-replay / `simulate` front-end is planned.

## Use

```bash
pip install -e .
xrpl-explain tx.json            # a tx response JSON (with meta)
cat tx.json | xrpl-explain
```

As a library:

```python
from xrpl_explain import explain, render
exp = explain(tx)                 # tx includes "meta" (or "metaData")
print(exp.result, exp.category)   # e.g. "tesSUCCESS" "success"
for c in exp.diff.of_type("MPToken"):
    print(c.account, c.fields)    # per-holder MPT balance deltas
print(render(exp))
```

## What it gives you

- **Result explanation** — a curated map of common and lending/MPT codes
  (`tecINVARIANT_FAILED`, `tecNO_AUTH`, `tecNO_LINE`, `temBAD_SEND_XRP_PARTIAL`, …) plus a
  prefix fallback so any code still gets the right category (tes/tec/tem/tef/ter/tel).
- **State diff** — for each created/modified/deleted object: the entry type, the owning
  account, and each changed field with a signed delta for amount-like values (XRP drops,
  IOU `value`, `MPTAmount`, `OutstandingAmount`, …).

## License
MIT.
