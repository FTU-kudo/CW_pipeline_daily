"""Dựng khung dữ liệu thanh khoản (nghiên cứu) từ cache parquet.

Kết quả: /tmp/liq_panel.parquet — 1 dòng/(ticker, phiên), có metric cửa sổ trượt
tính trên **lịch giao dịch đầy đủ** (phiên không giao dịch = volume 0, không phải NaN).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from cwintel.data import load_market_data

CAL_COLS = ["adv20", "adv60", "coverage20", "coverage60", "amihud20", "turnover20",
            "range20", "zero20", "value_cv20"]


def build_liquidity_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    m = load_market_data()
    oh = m.ohlcv.copy()
    oh["value"] = oh["close"] * oh["volume"]
    master = m.master.set_index("ticker")
    cal = pd.DatetimeIndex(sorted(oh["date"].unique()))

    frames = []
    for ticker, g in oh.groupby("ticker", sort=False):
        g = g.sort_values("date").set_index("date")
        full = pd.date_range(g.index.min(), g.index.max(), freq="B")
        full = cal[(cal >= g.index.min()) & (cal <= g.index.max())]
        if len(full) == 0:
            continue
        r = pd.DataFrame(index=full)
        r["close"] = g["close"].reindex(full)
        r["value"] = g["value"].reindex(full).fillna(0.0)
        r["volume"] = g["volume"].reindex(full).fillna(0.0)
        r["high"] = g["high"].reindex(full)
        r["low"] = g["low"].reindex(full)
        r["traded"] = r["value"] > 0
        ret = r["close"].pct_change()
        r["ret1"] = ret

        r["coverage20"] = r["traded"].rolling(20, min_periods=5).mean() * 100
        r["coverage60"] = r["traded"].rolling(60, min_periods=20).mean() * 100
        r["adv20"] = r["value"].rolling(20, min_periods=5).sum() / 20.0
        r["adv60"] = r["value"].rolling(60, min_periods=20).sum() / 60.0
        r["zero20"] = (~r["traded"]).rolling(20, min_periods=5).sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            am = (ret.abs() / r["value"].replace(0, np.nan)) * 1e9
            r["amihud20"] = am.rolling(20, min_periods=5).median()
        rng = ((r["high"] - r["low"]) / r["close"].replace(0, np.nan))
        r["range20"] = rng.rolling(20, min_periods=5).median() * 100
        out = master.loc[ticker, "outstanding_volume"] if ticker in master.index else np.nan
        r["turnover20"] = (r["volume"].rolling(20, min_periods=5).mean() / out * 100
                           if np.isfinite(out) and out > 0 else np.nan)
        r["value_cv20"] = (r["value"].rolling(20, min_periods=5).std()
                           / r["value"].rolling(20, min_periods=5).mean().replace(0, np.nan))

        r["ticker"] = ticker
        r = r.reset_index().rename(columns={"index": "date"})
        frames.append(r[["ticker", "date", "close", "value", "volume", "ret1"] + CAL_COLS])

    panel = pd.concat(frames, ignore_index=True)
    meta = m.master[["ticker", "underlying", "issuer", "issuer_name", "K", "ratio", "maturity",
                     "listed_volume", "outstanding_volume", "is_active", "first_trade", "last_trade"]]
    panel = panel.merge(meta, on="ticker", how="left", suffixes=("", "_m"))
    return panel, m.underlying


if __name__ == "__main__":
    panel, und = build_liquidity_panel()
    panel.to_parquet("/tmp/liq_panel.parquet", index=False)
    und.to_parquet("/tmp/liq_und.parquet", index=False)
    print("rows", len(panel), "tickers", panel.ticker.nunique(),
          "dates", panel.date.min().date(), panel.date.max().date())
    print(panel[CAL_COLS].describe().round(3).T[["count", "mean", "50%", "max"]])
