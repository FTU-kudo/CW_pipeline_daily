# Yuanta EW snapshot architecture

```text
Yuanta YS Radar current board endpoint (stock_type=EW)
              │ scripts/yuanta_client.py — browser headers, retry, diagnosable errors
              │ exactly one server-side request per run, weekdays
              ▼
scripts/fetch_yuanta_snapshot.py
  - validate success/response/StockCode/Exchange/SymbolType
  - preserve raw row fields and values; no unit conversion
              │ atomic write
              ▼
docs/data/yuanta_snapshot.json ─────────────────┐
              │                                 │ re-read offline (no second request)
              ▼                                 ▼
docs/index.html                     scripts/analyze_yuanta_warrants.py
  filterable board + raw JSON          └─► cwintel/yuanta_board.py
  + derived columns read from the          - clean_board(): typed, derived columns
    analysis JSON                          - quality_checks(): 10 integrity checks
                                           - summarize / top_movers / by_underlying
                                           - spread_profile (bid–ask cost proxy)
                                          │
                        ┌─────────────────┴──────────────────┐
                        ▼                                    ▼
docs/data/yuanta_board_analysis.json          yuanta_covered_warrants.csv
(committed; Pages serves it)                  (workflow artifact only, never committed)
```

`cwintel/yuanta_board.py` never fetches: it is pure pandas, so results are reproducible from
a saved payload and tests run offline (`tests/fixtures/yuanta_ew_sample.json`).

## Units are evidenced, not assumed

The payload satisfies `TotalVal ≈ TotalVol × AvgP` across the snapshot (sample row:
`2,775,000 / 17,700 = 156.78`, matching `AvgP`). That identity is what justifies reading
prices as VND/CW and `TotalVal` as VND. `quality_checks` re-tests the identity on every run;
rows beyond 0.5% are flagged, never silently rewritten. Fields whose meaning is not
documented in the payload (`FRoom`, `DeemP`/`DeemVol`, `SymbolAdminStatusCode`) are carried
through untouched and are not interpreted.

## Explicitly unsupported in this generation

The supplied endpoint does not provide daily historical OHLCV per individual covered warrant. The new Pages app is therefore a current-board view only. It does not expose charts, model prices, Greeks, recommendations, technical signals, backtests, underlying-stock history, or derived historical data. Old snapshots are overwritten rather than accumulated.

## Workflows

- `.github/workflows/cw_pipeline.yml`: scheduled/manual fetch and publish of the Yuanta snapshot; no secrets are passed.
- `.github/workflows/cw_tests.yml` (if present): offline tests only; never makes a provider request.
- GitHub Pages must serve `main:/docs`; pushes of a changed JSON snapshot trigger its Pages deployment.

## Legacy code

`pipeline.py`, `vnstock_config.py`, `cwintel/` and the old analysis UI are not used by the scheduled Yuanta workflow. They remain only as dormant code and must not be presented as current Yuanta-backed results. Their sources/permissions are separate from the current snapshot authorization.
