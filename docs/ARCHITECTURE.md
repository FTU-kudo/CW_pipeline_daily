# Yuanta EW snapshot architecture

```text
Yuanta YS Radar current board endpoint (stock_type=EW)
              │ one server-side request, weekdays
              ▼
scripts/fetch_yuanta_snapshot.py
  - validate success/response/StockCode/Exchange/SymbolType
  - preserve raw row fields and values; no unit conversion
              │ atomic write
              ▼
docs/data/yuanta_snapshot.json
              │ Pages serves the latest snapshot
              ▼
docs/index.html (filterable board + raw JSON per symbol)
```

## Explicitly unsupported in this generation

The supplied endpoint does not provide daily historical OHLCV per individual covered warrant. The new Pages app is therefore a current-board view only. It does not expose charts, model prices, Greeks, recommendations, technical signals, backtests, underlying-stock history, or derived historical data. Old snapshots are overwritten rather than accumulated.

## Workflows

- `.github/workflows/cw_pipeline.yml`: scheduled/manual fetch and publish of the Yuanta snapshot; no secrets are passed.
- `.github/workflows/cw_tests.yml` (if present): offline tests only; never makes a provider request.
- GitHub Pages must serve `main:/docs`; pushes of a changed JSON snapshot trigger its Pages deployment.

## Legacy code

`pipeline.py`, `vnstock_config.py`, `cwintel/` and the old analysis UI are not used by the scheduled Yuanta workflow. They remain only as dormant code and must not be presented as current Yuanta-backed results. Their sources/permissions are separate from the current snapshot authorization.
