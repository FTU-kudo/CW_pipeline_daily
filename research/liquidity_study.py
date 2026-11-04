"""Nghiên cứu thực nghiệm: thanh khoản ảnh hưởng thế nào tới lợi nhuận & khả năng thoát vị thế.

Xuất:
  /tmp/liq_obs.parquet  — quan sát (ngày tín hiệu × CW)
  /tmp/liq_study.json   — bảng tổng hợp cho báo cáo
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from cwintel import config

SPACING = 20
HOLD = 20
TOL = 7
START = "2023-06-01"


def forward_stats(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.sort_values(["ticker", "date"]).reset_index(drop=True)
    cal = np.array(sorted(panel["date"].unique()), dtype="datetime64[ns]")
    cal_pos = {d: i for i, d in enumerate(cal)}
    series = {}
    for t, g in panel.groupby("ticker", sort=False):
        series[t] = (g["date"].to_numpy("datetime64[ns]"), g["close"].to_numpy(float),
                     g["adv20"].to_numpy(float), g["coverage20"].to_numpy(float))
    return series, cal, cal_pos


def build_obs(panel: pd.DataFrame) -> pd.DataFrame:
    series, cal, cal_pos = forward_stats(panel)
    dates = [pd.Timestamp(d) for d in cal if pd.Timestamp(d) >= pd.Timestamp(START)]
    reb = dates[::SPACING]
    rows = []
    for t in reb:
        t64 = np.datetime64(t)
        ti = cal_pos[t64]
        snap = panel[(panel["date"] <= t) & (panel["date"] >= t - pd.Timedelta(days=TOL))]
        snap = snap.sort_values("date").groupby("ticker").tail(1)
        snap = snap[(snap["close"] > 0) & (snap["adv20"].notna())]
        for r in snap.itertuples(index=False):
            arr = series.get(r.ticker)
            if arr is None:
                continue
            d, c, adv, cov = arr
            pos = int(np.searchsorted(d, t64, side="right"))
            if pos >= len(d):
                continue
            entry_date = pd.Timestamp(d[pos])
            if (entry_date - t).days > 10:            # không giao dịch trong 10 ngày → không vào được
                continue
            entry = c[pos]
            if not np.isfinite(entry) or entry <= 0:
                continue
            # thoát: phiên thứ HOLD trên lịch chung sau t
            target_i = min(ti + HOLD, len(cal) - 1)
            target = pd.Timestamp(cal[target_i])
            j = int(np.searchsorted(d, np.datetime64(target), side="right") - 1)
            if j < pos:
                continue
            exit_date = pd.Timestamp(d[j])
            exit_lag = int(np.searchsorted(cal, np.datetime64(exit_date), side="right") - 1)
            exit_lag = target_i - exit_lag
            ret = c[j] / entry - 1.0
            # MAE/MFE trong 20 phiên (theo giá đóng cửa có giao dịch)
            path = c[pos:j + 1]
            mae = float(np.min(path) / entry - 1.0) if len(path) else np.nan
            mfe = float(np.max(path) / entry - 1.0) if len(path) else np.nan
            rows.append({
                "date": t, "ticker": r.ticker, "underlying": r.underlying, "issuer": r.issuer,
                "close": entry, "adv20": r.adv20, "adv60": r.adv60,
                "coverage20": r.coverage20, "coverage60": r.coverage60,
                "amihud20": r.amihud20, "turnover20": r.turnover20, "range20": r.range20,
                "zero20": r.zero20, "value_cv20": r.value_cv20,
                "dte": (pd.Timestamp(r.maturity) - t).days,
                "listed": r.listed_volume, "outstanding": r.outstanding_volume,
                "fwd_ret": ret, "mfe": mfe, "mae": mae,
                "exit_lag": exit_lag, "stale_exit": bool(exit_lag > 3),
                "days_to_liquidate_50m": 50e6 / max(r.adv20 * 0.2, 1),
                "days_to_liquidate_200m": 200e6 / max(r.adv20 * 0.2, 1),
            })
    return pd.DataFrame(rows)


def qcut_table(df: pd.DataFrame, col: str, q: int = 5, target: str = "fwd_ret") -> list[dict]:
    d = df.dropna(subset=[col, target]).copy()
    if d.empty:
        return []
    d["bucket"] = pd.qcut(d[col], q, labels=False, duplicates="drop")
    out = []
    for b, g in d.groupby("bucket"):
        out.append({
            "bucket": int(b),
            "range": [float(g[col].min()), float(g[col].max())],
            "n": int(len(g)),
            "avg": round(float(g[target].mean()) * 100, 2),
            "median": round(float(g[target].median()) * 100, 2),
            "win": round(float((g[target] > 0).mean()) * 100, 1),
            "stale_exit": round(float(g["stale_exit"].mean()) * 100, 1),
            "mae": round(float(g["mae"].mean()) * 100, 2),
        })
    return out


def main() -> None:
    panel = pd.read_parquet("/tmp/liq_panel.parquet")
    obs = build_obs(panel)
    obs.to_parquet("/tmp/liq_obs.parquet", index=False)
    print("obs", len(obs), "dates", obs.date.nunique())

    out: dict = {"n_obs": int(len(obs)), "period": [str(obs.date.min().date()), str(obs.date.max().date())],
                 "n_dates": int(obs.date.nunique())}
    out["describe"] = {c: {k: float(v) for k, v in obs[c].describe().items()}
                       for c in ["adv20", "coverage20", "amihud20", "turnover20", "range20",
                                 "fwd_ret", "mae", "exit_lag"]}
    out["overall"] = {
        "avg_ret": round(float(obs.fwd_ret.mean()) * 100, 2),
        "median_ret": round(float(obs.fwd_ret.median()) * 100, 2),
        "win": round(float((obs.fwd_ret > 0).mean()) * 100, 1),
        "stale_exit": round(float(obs.stale_exit.mean()) * 100, 1),
    }

    for col in ["adv20", "coverage20", "amihud20", "turnover20", "range20", "zero20",
                "value_cv20", "days_to_liquidate_50m"]:
        out[col] = qcut_table(obs, col)

    # tương quan hạng trong từng mặt cắt (loại bỏ ảnh hưởng thời gian)
    corr = {}
    for col in ["adv20", "coverage20", "amihud20", "turnover20", "range20", "zero20"]:
        vals = []
        for _, g in obs.dropna(subset=[col, "fwd_ret"]).groupby("date"):
            if len(g) < 10:
                continue
            vals.append(g[col].rank().corr(g["fwd_ret"].rank()))
        corr[col] = round(float(np.nanmean(vals)), 3) if vals else None
    out["rank_corr"] = corr

    # ngưỡng thanh khoản: % quan sát đạt + lợi nhuận
    gates = []
    for thr in [5e6, 10e6, 20e6, 50e6, 100e6, 200e6, 500e6]:
        d = obs[obs.adv20 >= thr]
        gates.append({"adv": thr, "share": round(len(d) / len(obs) * 100, 1),
                      "avg": round(float(d.fwd_ret.mean()) * 100, 2),
                      "median": round(float(d.fwd_ret.median()) * 100, 2),
                      "win": round(float((d.fwd_ret > 0).mean()) * 100, 1),
                      "stale": round(float(d.stale_exit.mean()) * 100, 1)})
    out["adv_gates"] = gates

    cov_gates = []
    for thr in [30, 50, 70, 90, 100]:
        d = obs[obs.coverage20 >= thr]
        cov_gates.append({"coverage": thr, "share": round(len(d) / len(obs) * 100, 1),
                          "avg": round(float(d.fwd_ret.mean()) * 100, 2),
                          "win": round(float((d.fwd_ret > 0).mean()) * 100, 1),
                          "stale": round(float(d.stale_exit.mean()) * 100, 1)})
    out["coverage_gates"] = cov_gates

    # khả năng thoát: xác suất không giao dịch quanh ngày thoát
    exit_risk = []
    for lo, hi in [(0, 1e6), (1e6, 5e6), (5e6, 20e6), (20e6, 100e6), (100e6, np.inf)]:
        d = obs[(obs.adv20 >= lo) & (obs.adv20 < hi)]
        exit_risk.append({"bucket": f"{lo/1e6:.0f}–{hi/1e6:.0f}" if np.isfinite(hi) else f"{lo/1e6:.0f}+",
                          "n": int(len(d)),
                          "stale_exit": round(float(d.stale_exit.mean()) * 100, 1),
                          "avg_exit_lag": round(float(d.exit_lag.mean()), 2),
                          "mae": round(float(d.mae.mean()) * 100, 2)})
    out["exit_risk"] = exit_risk

    # tương tác với DTE
    dte_bins = [0, 60, 120, 240, 9999]
    obs["dte_bin"] = pd.cut(obs["dte"], dte_bins, right=False)
    inter = []
    for (b, liq), g in obs.groupby(["dte_bin", pd.qcut(obs["adv20"], 3, labels=["thấp", "vừa", "cao"], duplicates="drop")]):
        inter.append({"dte": str(b), "liq": str(liq), "n": int(len(g)),
                      "avg": round(float(g.fwd_ret.mean()) * 100, 2),
                      "win": round(float((g.fwd_ret > 0).mean()) * 100, 1)})
    out["dte_liq"] = inter

    with open("/tmp/liq_study.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ["overall", "adv_gates", "coverage_gates", "exit_risk", "rank_corr"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
