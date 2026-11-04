"""Kiểm tra chất lượng dữ liệu — chạy mỗi lần build, xuất docs/data/quality.json."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, lifecycle
from .data import MarketData


def _check(cid: str, title: str, status: str, value=None, detail: str = "",
           severity: str = "info") -> dict:
    return {"id": cid, "title": title, "status": status, "value": value,
            "detail": detail, "severity": severity}


def run_quality_checks(market: MarketData, panel: pd.DataFrame,
                       snap: pd.DataFrame, life: dict | None = None) -> dict:
    checks: list[dict] = []
    asof = market.asof
    oh = market.ohlcv
    diag = market.diagnostics.get("ohlcv", {})
    master = market.master

    # 1. Trùng lặp & định dạng ngày
    dup = diag.get("duplicates_removed", 0)
    fmt = diag.get("src_fmt_counts", {})
    checks.append(_check(
        "ohlcv_duplicates",
        "Trùng lặp bản ghi OHLCV (cùng ticker + ngày, khác định dạng chuỗi)",
        "warn" if dup else "ok",
        {"removed": dup, "rowsIn": diag.get("rows_in"), "rowsOut": diag.get("rows_out"),
         "byFormat": fmt},
        "Hai định dạng ngày (dd/mm/yyyy và ISO+07:00) từng được lưu song song cho cùng "
        "một phiên. Tầng phân tích chuẩn hoá ngày và dedupe theo (ticker, ngày), giữ bản "
        "ghi có khối lượng lớn hơn. Dữ liệu gốc không bị sửa.",
        severity="medium"))

    # 2. Ngày không parse được
    unparsed = diag.get("unparsed_dates", 0)
    checks.append(_check(
        "date_parse", "Ngày không đọc được", "warn" if unparsed else "ok",
        {"count": unparsed},
        "Số dòng có ngày không parse được (bị loại khỏi phân tích).",
        severity="high" if unparsed > 100 else "low"))

    # 3. Giá nằm ngoài [low, high]
    if {"close", "high", "low"}.issubset(oh.columns):
        bad = int(((oh["close"] > oh["high"] + 1e-9) | (oh["close"] < oh["low"] - 1e-9)).sum())
        checks.append(_check(
            "ohlc_consistency", "OHLC bất khả thi (close ngoài [low, high])",
            "warn" if bad else "ok", {"count": bad, "rows": int(len(oh))},
            "Thường do nguồn trả giá điều chỉnh khác nhau giữa các trường.", severity="low"))

    # 4. Điều khoản thiếu
    missing_terms = int((~master["terms_valid"]).sum())
    checks.append(_check(
        "terms_missing", "CW thiếu strike / tỷ lệ chuyển đổi hợp lệ",
        "error" if missing_terms else "ok", {"count": missing_terms},
        "Không thể định giá Black‑Scholes khi thiếu điều khoản.", severity="high"))

    # 5. Điều khoản điều chỉnh & đối chiếu break-even với Vietstock
    adj = master[master["terms_adjusted"] & master["be_vs"].notna() & master["price_vs"].notna()]
    if len(adj):
        be_calc = adj["K"] + adj["price_vs"] * adj["ratio"]
        err = (be_calc - adj["be_vs"]).abs()
        within = float((err <= 1.0).mean() * 100)
        checks.append(_check(
            "adjusted_terms", "Đối chiếu break-even với Vietstock (dùng strike/ratio điều chỉnh)",
            "ok" if within >= 70 else "warn",
            {"n": int(len(adj)), "within1VndPct": round(within, 1),
             "medianAbsErrVnd": round(float(err.median()), 1)},
            "Break-even tính lại = K(điều chỉnh) + giá CW × tỷ lệ điều chỉnh. Tỷ lệ khớp cao "
            "xác nhận quy ước tính là đúng.", severity="medium"))

    # 6. Moneyness so với Vietstock
    if "moneyness_vs" in master.columns:
        cmp = master[master["moneyness_vs"].isin(["ITM", "ATM", "OTM"])
                     & master["underlying_vs"].notna() & master["K"].notna()]
        if len(cmp):
            calc = np.where(cmp["underlying_vs"] > cmp["K"] * (1 + config.ATM_BAND), "ITM",
                            np.where(cmp["underlying_vs"] < cmp["K"] * (1 - config.ATM_BAND),
                                     "OTM", "ATM"))
            mismatch = int((calc != cmp["moneyness_vs"].values).sum())
            checks.append(_check(
                "moneyness_vs", "Moneyness tự tính khác Vietstock",
                "warn" if mismatch else "ok",
                {"n": int(len(cmp)), "mismatch": mismatch,
                 "mismatchPct": round(mismatch / len(cmp) * 100, 1)},
                "Vietstock đánh dấu ITM cả khi S < K (có thể do quy ước khác). Hệ thống dùng "
                "định nghĩa riêng: |S/K − 1| ≤ 2% là ATM, ngược lại ITM/OTM.",
                severity="low"))

    # 7. Dữ liệu cũ
    if "staleness_days" in snap.columns and len(snap):
        stale = int((pd.to_numeric(snap["staleness_days"], errors="coerce") > 3).sum())
        checks.append(_check(
            "stale_series", "CW có giá cũ hơn 3 ngày so với phiên chuẩn",
            "warn" if stale else "ok",
            {"count": stale, "asof": asof.strftime("%Y-%m-%d")},
            "CW không giao dịch trong vài phiên (thanh khoản thấp). Không được hiển thị như "
            "giá realtime.", severity="medium"))

    # 8. Thiếu giá cho CW active
    active = master[master["is_active"]]
    missing_price = sorted(set(active["ticker"]) - set(oh["ticker"]))
    checks.append(_check(
        "missing_prices", "CW đang giao dịch nhưng không có dữ liệu giá",
        "error" if missing_price else "ok",
        {"count": len(missing_price), "sample": missing_price[:10]},
        "Không thể phân tích các mã này.", severity="high"))

    # 9. Dao động giá bất thường
    if not panel.empty:
        jumps = int((pd.to_numeric(panel["ret1"], errors="coerce").abs() > 0.5).sum())
        checks.append(_check(
            "price_jumps", "Biến động ngày > 50% (nghi ngờ dữ liệu)",
            "warn" if jumps else "ok",
            {"count": jumps, "rows": int(len(panel))},
            "CW biến động mạnh là bình thường, nhưng >50%/ngày cần kiểm tra thủ công.",
            severity="low"))

    # 10. Chất lượng IV
    if "iv_quality" in panel.columns:
        counts = panel["iv_quality"].value_counts().to_dict()
        checks.append(_check(
            "iv_quality", "Độ tin cậy của IV suy ra từ giá",
            "ok", {"ok": int(counts.get("ok", 0)), "low": int(counts.get("low", 0)),
                   "na": int(counts.get("na", 0))},
            "IV bị đánh dấu 'low' khi giá CW ≤ 30 VND (làm tròn bước giá), còn < 7 ngày đáo "
            "hạn hoặc IV > 300% — không dùng các giá trị này trong scoring.",
            severity="low"))

    # 11. Lịch sử IV
    iv_obs = int(panel["iv"].notna().sum()) if "iv" in panel else 0
    checks.append(_check(
        "iv_history", "Số quan sát IV lịch sử (backfill từ giá CW)",
        "ok" if iv_obs > 10000 else "warn", {"count": iv_obs},
        "IV Rank cần ≥ 20 quan sát; cache iv_history.parquet của pipeline chỉ có ~70 phiên "
        "nên hệ thống tự backfill từ chuỗi giá CW + underlying.", severity="low"))

    # 12. Điểm & khuyến nghị
    scored = int(snap["score"].notna().sum()) if "score" in snap else 0
    checks.append(_check(
        "scoring_coverage", "CW active được chấm điểm",
        "ok" if scored >= 0 else "warn",
        {"scored": scored, "total": int(len(snap))},
        "Điểm cần dữ liệu giá, underlying và điều khoản.", severity="low"))

    # 13. Underlying
    und_last = market.underlying["date"].max() if not market.underlying.empty else None
    checks.append(_check(
        "underlying_freshness", "Độ mới dữ liệu cổ phiếu cơ sở",
        "ok" if und_last is not None and (asof - und_last).days <= 4 else "warn",
        {"lastDate": und_last.strftime("%Y-%m-%d") if und_last is not None else None,
         "underlyings": int(market.underlying["ticker"].nunique())},
        "Thiếu dữ liệu underlying sẽ làm HV và momentum sai.", severity="high"))

    # 14. Vòng đời: phân loại & tổng vũ trụ
    lc = (life or {}).get("counts") if life else None
    ident = (life or {}).get("identity") if life else None
    if lc:
        checks.append(_check(
            "universe_history", "Vũ trụ dữ liệu có bao gồm CW đã đáo hạn",
            "ok", {"expired": lc["expired"], "listed": lc["listed"], "traded": lc["traded"],
                   "notTraded": lc["notTraded"], "pending": lc["pending"],
                   "matured": lc["matured"], "delistedEarly": lc["delistedEarly"]},
            "Panel giữ cả CW đã đáo hạn để backtest không bị survivorship bias. "
            "Screener tách rõ: còn hiệu lực / đã đáo hạn / ngừng giao dịch sớm / chờ niêm yết.",
            severity="info"))
        checks.append(_check(
            "universe_identity", "Tổng vũ trụ khớp tổng các trạng thái vòng đời",
            "ok" if ident and ident.get("ok") else "error",
            {"total": lc["total"], "sumStates": ident["sumStates"] if ident else None,
             "gap": ident["gap"] if ident else None},
            "Mỗi CW phải thuộc đúng một trạng thái: còn hiệu lực, chờ niêm yết, đã đáo hạn, "
            "ngừng giao dịch sớm hoặc thiếu ngày đáo hạn. Lệch nghĩa là có mã bị đếm trùng/bỏ sót.",
            severity="high"))
    else:
        expired = int((~master["is_active"]).sum())
        checks.append(_check(
            "universe_history", "Vũ trụ dữ liệu có bao gồm CW đã đáo hạn",
            "ok", {"expired": expired, "active": int(master["is_active"].sum())},
            "Panel giữ cả CW đã đáo hạn để backtest không bị survivorship bias.",
            severity="info"))

    # 15. Lợi suất phi rủi ro
    checks.append(_check(
        "risk_free", "Nguồn lãi suất phi rủi ro",
        "ok" if market.risk_free_source != "default_constant" else "warn",
        {"value": round(market.risk_free, 5), "source": market.risk_free_source,
         "date": market.risk_free_date.strftime("%Y-%m-%d") if market.risk_free_date else None},
        "Dùng spot rate 10Y (lãi kép liên tục) từ đường cong HNX — khớp quy ước e^(−rT).",
        severity="medium"))

    # 16. Thanh khoản vũ trụ (thông tin cho người dùng, không phải lỗi dữ liệu)
    if "adv20" in snap.columns:
        adv = pd.to_numeric(snap["adv20"], errors="coerce")
        thin = float((adv < 5e6).mean()) * 100 if len(adv) else float("nan")
        cov = pd.to_numeric(snap.get("coverage_listing", snap.get("coverage20")),
                            errors="coerce")
        low_cov = float((cov < 50).mean()) * 100 if len(cov) else float("nan")
        checks.append(_check(
            "liquidity_depth", "Độ sâu thanh khoản vũ trụ",
            "ok" if thin < 25 else "warn",
            {"medianAdv20": round(float(adv.median()), 0) if adv.notna().any() else None,
             "advBelow5mPct": round(thin, 1), "coverageBelow50Pct": round(low_cov, 1)},
            "Tỷ lệ CW có ADV20 < 5 triệu VND/phiên. Thanh khoản thấp là đặc điểm thị trường, "
            "không phải lỗi dữ liệu — nhưng làm giảm khả năng thoát vị thế (xem RESEARCH_LIQUIDITY.md).",
            severity="low"))

    # 17. Snapshot chỉ chứa CW còn hiệu lực, DTE không âm
    if len(snap):
        if "lifecycle_state" in snap.columns:
            bad_state = int((snap["lifecycle_state"] != "listed").sum())
        else:
            bad_state = 0
        mats = pd.to_datetime(snap["maturity"], errors="coerce") if "maturity" in snap else pd.Series(dtype="datetime64[ns]")
        matured_in_snap = int((mats <= asof).sum())
        dte = pd.to_numeric(snap.get("days_to_maturity"), errors="coerce")
        neg_dte = int((dte < 0).sum())
        bad = bad_state + matured_in_snap + neg_dte
        checks.append(_check(
            "snapshot_lifecycle", "Snapshot chỉ chứa CW còn hiệu lực (không lẫn mã đã đáo hạn)",
            "error" if bad else "ok",
            {"rows": int(len(snap)), "maturedInSnapshot": matured_in_snap,
             "negativeDte": neg_dte, "badState": bad_state,
             "minDte": int(dte.min()) if dte.notna().any() else None},
            "CW đã đáo hạn phải nằm trong danh sách đã đáo hạn của screener, không được chấm "
            "điểm/khuyến nghị. DTE luôn tính lại tại phiên dữ liệu nên không thể âm.",
            severity="high"))

        # 18. Khuyến nghị chỉ dành cho CW còn hiệu lực
        recs = snap.get("recommendation")
        if recs is not None and "maturity" in snap.columns:
            bad_rec = int(((mats <= asof) & recs.notna() & (recs != "NO_DATA")).sum())
            checks.append(_check(
                "recs_listed_only", "Khuyến nghị chỉ phát hành cho CW còn hiệu lực",
                "error" if bad_rec else "ok", {"violations": bad_rec},
                "Mã đã đáo hạn không thể giao dịch được nữa nên không được khuyến nghị.",
                severity="high"))

    # 19. Sự kiện vòng đời (niêm yết mới / vừa đáo hạn / sắp đáo hạn)
    if life:
        up = life.get("upcoming") or {}
        checks.append(_check(
            "lifecycle_events", "Phát hiện niêm yết mới & đáo hạn theo phiên",
            "ok",
            {"recentSessions": life.get("recentSessions"),
             "recentSince": life.get("recentSince"),
             "newListings": (life.get("newListings") or {}).get("count"),
             "recentMaturities": (life.get("recentMaturities") or {}).get("count"),
             "upcoming30": (up.get("d30") or {}).get("count"),
             "upcoming60": (up.get("d60") or {}).get("count"),
             "upcoming90": (up.get("d90") or {}).get("count"),
             "earlyDelistings": (life.get("earlyDelistings") or {}).get("count")},
            "CW liên tục niêm yết và đáo hạn: mỗi lần build đều so sánh ngày giao dịch đầu tiên "
            "và ngày đáo hạn với cửa sổ phiên gần nhất, nên mã mới/ mã hết hạn được nhận diện "
            "ngay trong phiên, không phụ thuộc việc có ai mở dashboard hay không.",
            severity="info"))

    counts = {"ok": 0, "warn": 0, "error": 0}
    for c in checks:
        counts[c["status"]] = counts.get(c["status"], 0) + 1

    headline = []
    for c in checks:
        if c["status"] == "error":
            headline.append(f"LỖI: {c['title']}")
        elif c["status"] == "warn" and c["severity"] in ("high", "medium"):
            headline.append(f"Cảnh báo: {c['title']}")

    return {
        "asof": asof.strftime("%Y-%m-%d"),
        "summary": {**counts, "total": len(checks)},
        "headline": headline,
        "checks": checks,
    }
