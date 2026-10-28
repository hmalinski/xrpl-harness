# xrpl-harness

Open-source developer tooling for the XRP Ledger, built around one idea: **independently checking that value and intent are preserved** — before you send a transaction, within it, across a sequence, and across a bridge.

It's a monorepo so the tools share one core (standalone-node driver, typed state/metadata decoder, invariant engine, ddmin reducer). All MIT-licensed.

## Packages

| Package | What it does | Status |
|---|---|---|
| [`xrpl-lint`](packages/xrpl-lint) | Static linter for XRPL transactions — catches footguns before you sign/submit (no node needed). | **v0.0.1** |
| [`xrpl-explain`](packages/xrpl-explain) | Explain a tx result + a typed before/after state diff (type-agnostic; MPT/Vault/Loan included). | **v0.0.1** |
| `xrpl-fuzz` | Stateful invariant fuzzer — random tx sequences vs user-defined invariants, shrunk to a minimal repro. | planned |
| `xrpl-harness-core` | Shared node driver, decoder, invariant engine, ddmin (extracted from the Nullsum harness). | planned |

Related: [Nullsum](https://github.com/hmalinski/nullsum) — the single-chain conservation-invariant harness this line grew out of.

## License
MIT.
