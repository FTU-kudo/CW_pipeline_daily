# Yuanta EW snapshot architecture

```text
Yuanta YS Radar current board endpoint (stock_type=EW)
              │ scripts/yuanta_client.py
              │   browser headers + landing-page warm-up + Chrome TLS (curl_cffi)
              │   WAF JS interstitial (jsKey) followed like a browser
              │   retry/backoff, diagnosable errors with full body
              │ one API call per run, weekdays
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

docs/data/yuanta_snapshot.json
              │ scripts/backfill_yuanta_history.py
              ▼
cwintel/yuanta_history.py
  - resolve_session(): a bar is complete only if captured after 15:10 ICT
  - bars_from_rows(): untraded warrant → close = null (RefP is never a close)
  - upsert_bars(): idempotent; provisional bars cannot overwrite closed ones
              │
              ├──► data/cw_history/YYYY-MM.csv    (committed: accumulated daily store)
              ├──► docs/data/yuanta_sessions.json (series + coverage + per-ticker gaps)
              └──► docs/data/yuanta_analytics.json
                     cwintel/yuanta_analytics.py
                       - liquidity tiers from the snapshot's own quantiles
                       - grouping by underlying
                       - untraded / recovered warrant monitor
                       - session-over-session comparison (only with ≥ 2 sessions)
              │
              │
              └──► cwintel/yuanta_intraday.py (uses confirmed field semantics)
                     - intraday_moves(): (High-Low)/RefP, close location in [Low, High]
                     - price_band_profile(): CeilingP/FloorP read as-is, never ±7%
                     - last_trade_profile(): LastMVol/TotalVol
                     - ref_continuity(): today's RefP vs yesterday's close in the store
              │
              └──► cwintel.yuanta_history.to_cwintel_ohlcv()
                     Ticker/time/open/high/low/close/volume for the legacy CW Analytics app
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

## Daily OHLCV history: what is real and what is not

A snapshot taken after the close carries the session's own bar (`OpenP`, `HighestP`,
`LowestP`, `LastMP`, `TotalVol`). Bars are appended to `data/cw_history/`, so a genuine daily
OHLCV series accumulates **from the first workflow run onwards**. There is no backfill: the
endpoint carries no past data, missing sessions are listed in `coverage.missingSessions`, and
nothing is interpolated.

Untraded warrants get `close = null`, because the source only offers `RefP` — the *previous*
session's reference price, not a traded price. Using it as a close would manufacture
zero-return days that never happened.

The legacy CW Analytics dashboard (`docs/legacy.html`) still cannot be built: `cwintel`
requires contract terms (strike, conversion ratio, maturity), underlying prices and a risk-free
curve to produce intrinsic value, premium, Greeks, IV and recommendations. The EW endpoint has
none of those fields, and `scripts/check_cw_analytics_bridge.py` reports exactly what is
missing (exit code 2) rather than inventing terms to fill the gap.

## Explicitly unsupported in this generation

No model prices, Greeks, IV, recommendations, technical signals, backtests, underlying-stock
history. The board renders only what the snapshot says, and the history view renders only bars
that were actually captured.

## Workflows

- `.github/workflows/cw_pipeline.yml`: scheduled/manual fetch and publish of the Yuanta snapshot; no secrets are passed.
- `.github/workflows/cw_tests.yml` (if present): offline tests only; never makes a provider request.
- GitHub Pages must serve `main:/docs`; pushes of a changed JSON snapshot trigger its Pages deployment.

## Legacy code

`pipeline.py`, `vnstock_config.py`, `cwintel/` and the old analysis UI are not used by the scheduled Yuanta workflow. They remain only as dormant code and must not be presented as current Yuanta-backed results. Their sources/permissions are separate from the current snapshot authorization.
