# Data rights and source scope

## Current Yuanta snapshot

The project owner states that the Yuanta endpoint below is legally authorized and complete for the intended use, and has requested public deployment of its response:

```text
https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW
```

The automated publisher is intentionally narrow: it fetches only the EW current price-board response, preserves its raw fields, publishes one latest snapshot, and overwrites it on the next successful fetch. It does not archive or reconstruct individual warrant daily OHLCV. The agent has not independently reviewed the signed approval or Yuanta's original terms and cannot reach the host from the sandbox. Publication is based on the owner's express representation/request; review the provider's current original terms if the approved scope or endpoint changes.

## No other source data in the publishing path

The current GitHub Pages workflow does not call Vnstock, Vietstock, HNX, VBMA, KBS, or VCI and does not use their old artifacts. Legacy analysis code remains in the repository but is not run by the Yuanta snapshot workflow. Do not restore old cache/history files without separate authorization for those sources and outputs.

## Data limitations

- The API response is a current board snapshot, not a daily candle history.
- `fetchedAt` records when the GitHub runner fetched it; it is not represented as the exchange's as-of timestamp.
- Numeric values and original field names remain as returned. No currency/unit scaling or calculated values are added.
- The public JSON is replace-in-place; historical snapshots are not retained by this workflow.
