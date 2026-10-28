# xrpl-lint

Static linter for XRP Ledger transactions. It reads a transaction (or a list of them) as JSON and flags known footguns **before you sign or submit** — no node, no network.

Rules never depend on ledger state — they are decidable from the transaction alone. Most are hard **errors** (the transaction is malformed and rippled would reject it); a couple are advisory **warnings** (a valid-but-risky pattern, like a fee over 1 XRP). It also lints the inner transactions of a `Batch`.

## Install / use

```bash
pip install -e .            # from this directory
xrpl-lint tx.json           # lint a file
cat tx.json | xrpl-lint     # or stdin
```

Exit code is non-zero when any `error`-severity finding is present (CI-friendly).

As a library:

```python
from xrpl_lint import lint
for i, f in lint(tx_or_list):
    print(i, f.severity, f.rule_id, f.message)
```

## Rules (v0.0.1)

| Rule | Severity | Catches |
|---|---|---|
| `xrp-amount-format` | error | An XRP amount that is not canonical integer drops — a number, decimal, sign, leading zero, non-ASCII digits, or XRP written as an amount object. Checks `Amount`, `SendMax`, `DeliverMin`, `DeliverMax`, `TakerGets`, `TakerPays`, `Amount2`. |
| `payment-partial-xrp-direct` | error | `tfPartialPayment` on an XRP→XRP Payment (`temBAD_SEND_XRP_PARTIAL`). |
| `delivermin-without-partial` | error | `DeliverMin` set without `tfPartialPayment` (`temBAD_AMOUNT`). |
| `partial-payment-no-delivermin` | warn | A cross-currency partial payment with no `DeliverMin` floor. The recipient must also read `delivered_amount`, not `Amount`. |
| `sequence-and-ticket` | error | A non-zero `Sequence` together with `TicketSequence` (`temSEQ_AND_TICKET`). |
| `fee-format` | error | `Fee` that is not a string of integer drops. |
| `high-fee` | warn | `Fee` over 1 XRP — usually a fat-finger (advisory; some txns legitimately pay more). |
| `batch-structure` | error | A `Batch` that breaks XLS-56: not exactly one mode flag, fewer than 2 or more than 8 inner txns, a nested `Batch`, an inner `Fee` ≠ `"0"`, a missing `tfInnerBatchTxn` flag, or a signed inner. |

`Batch` inner transactions are also run through the rules above; those findings are tagged `[RawTransactions[i]]`.

More rules are added as a focused rule pack, not a kitchen sink. Contributions welcome.

## License
MIT.
