#!/usr/bin/env python3
"""Sinh báo cáo Markdown từ snapshot + phân tích đã có — dùng cho chạy tay, cronjob.org, CI.

Tại sao cần script riêng
------------------------
Workflow trên GitHub Actions tự dựng được báo cáo trong log. Nhưng khi chạy từ **cronjob.org**
(hoặc bất kỳ scheduler ngoài nào), người dùng chỉ nhận được HTTP status và body trả về của
job — nên job đó phải *tự* trả về báo cáo. Script này biến dữ liệu đã có trong repo thành
một báo cáo Markdown/JSON, không gọi mạng:

    python scripts/daily_analysis_report.py                     # in Markdown
    python scripts/daily_analysis_report.py --format json        # in JSON
    python scripts/daily_analysis_report.py --out report.md      # ghi file + vẫn in
    python scripts/daily_analysis_report.py --summary            # gọn cho log cronjob.org

Đầu vào là sản phẩm của pipeline, nên script chạy được ngay cả khi mạng có sự cố:
``docs/data/yuanta_snapshot.json``, ``docs/data/yuanta_board_analysis.json``,
``docs/data/yuanta_analytics.json``, ``docs/data/yuanta_sessions.json``.

Mã thoát: 0 = có dữ liệu và báo cáo hợp lệ, 1 = thiếu snapshot (chưa chạy pipeline lần nào),
3 = dữ liệu cũ hơn ngưỡng ``--max-age-hours`` (dùng để cronjob.org báo động).

Không có nội dung nào ở đây là khuyến nghị đầu tư hay dự báo. Mọi con số đều đọc từ dữ liệu
nguồn; chỗ nào nguồn không có thì báo cáo nói thẳng là không có.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs" / "data"

DEFAULT_SNAPSHOT = DATA / "yuanta_snapshot.json"
DEFAULT_BOARD = DATA / "yuanta_board_analysis.json"
DEFAULT_ANALYTICS = DATA / "yuanta_analytics.json"
DEFAULT_SESSIONS = DATA / "yuanta_sessions.json"

#: Ngưỡng cảnh báo dữ liệu cũ (giờ). Cron chạy hằng ngày nên 36h là quá một phiên.
DEFAULT_MAX_AGE_HOURS = 36.0


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _vnd(value, digits: int = 0) -> str:
    """Định dạng VND theo kiểu Việt Nam; '—' khi không có số."""
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    text = f"{number:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _pct(value, digits: int = 2) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(number):
        return "—"
    return f"{number:.{digits}f}%".replace(".", ",")


def _first_session_date(snapshot: dict) -> str | None:
    stamp = snapshot.get("fetchedAt")
    if not stamp:
        return None
    return str(stamp)[:10]


def build_report(*, snapshot_path: Path = DEFAULT_SNAPSHOT,
                 board_path: Path = DEFAULT_BOARD,
                 analytics_path: Path = DEFAULT_ANALYTICS,
                 sessions_path: Path = DEFAULT_SESSIONS,
                 max_age_hours: float | None = DEFAULT_MAX_AGE_HOURS,
                 now: datetime | None = None) -> tuple[dict, int]:
    """Trả ``(report, exit_code)``. Không gọi mạng, không ghi gì ngoài ``report``."""
    now = now or datetime.now(timezone.utc)
    snapshot = _load(snapshot_path)
    board = _load(board_path)
    analytics = _load(analytics_path)
    sessions = _load(sessions_path)

    if not snapshot or not isinstance(snapshot.get("rows"), list):
        return ({
            "ok": False,
            "reason": (
                f"Không có snapshot dùng được ở {snapshot_path}. Chạy "
                "scripts/fetch_yuanta_snapshot.py trước (hoặc để workflow publish chạy)."
            ),
            "generatedAt": now.isoformat(timespec="seconds"),
        }, 1)

    fetched_raw = snapshot.get("fetchedAt")
    fetched = None
    if fetched_raw:
        try:
            fetched = datetime.fromisoformat(str(fetched_raw).replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
        except ValueError:
            fetched = None

    age_hours = None
    is_stale = False
    if fetched is not None:
        age_hours = round((now - fetched).total_seconds() / 3600, 1)
        if max_age_hours is not None:
            is_stale = age_hours > max_age_hours

    rows = snapshot["rows"]
    traded = [r for r in rows
              if (r.get("TotalVol") or 0) > 0 and (r.get("LastMP") or 0) > 0]

    report: dict = {
        "ok": True,
        "generatedAt": now.isoformat(timespec="seconds"),
        "session": _first_session_date(snapshot),
        "fetchedAt": fetched_raw,
        "ageHours": age_hours,
        "staleData": is_stale,
        "maxAgeHours": max_age_hours,
        "counts": {
            "rows": len(rows),
            "traded": len(traded),
            "untraded": len(rows) - len(traded),
            "untradedPct": round((len(rows) - len(traded)) / len(rows) * 100, 2) if rows else None,
        },
        "hasBoardAnalysis": board is not None,
        "hasAnalytics": analytics is not None,
        "hasSessions": sessions is not None,
    }

    if board:
        report["summary"] = board.get("summary", {})
        report["quality"] = board.get("quality", {})
        report["movers"] = {
            key: (board.get("movers", {}).get(key) or [])[:5]
            for key in ("gainers", "losers")
        }
        report["byUnderlying"] = (board.get("byUnderlying") or [])[:8]

    if analytics:
        liq = analytics.get("liquidity", {})
        report["scoring"] = analytics.get("scoring", {})
        report["liquidity"] = {
            "top": (liq.get("ranking") or [])[:10],
            "thresholds": liq.get("thresholds"),
            "tiers": liq.get("tiers"),
            "concentration": liq.get("concentration"),
        }
        report["stale"] = analytics.get("stale", {})
        report["intraday"] = analytics.get("intraday", {})
        report["priceBand"] = analytics.get("priceBand", {})
        report["lastTrade"] = analytics.get("lastTrade", {})
        report["refContinuity"] = analytics.get("refContinuity", {})
        report["historyCoverage"] = analytics.get("historyCoverage")
        report["sessionsComparison"] = analytics.get("sessions")
        report["caveats"] = analytics.get("caveats", [])

    if sessions:
        report["historyTickers"] = len(sessions.get("tickers") or {})

    exit_code = 3 if is_stale else 0
    return report, exit_code


# ──────────────────────────────────────────────────────────────────
# RENDER
# ──────────────────────────────────────────────────────────────────
def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(cells) + " |" for cells in rows]
    return out


def render_markdown(report: dict, *, compact: bool = False) -> str:
    """Báo cáo Markdown. ``compact`` bỏ các bảng phụ (dùng cho log cronjob.org)."""
    if not report.get("ok"):
        return f"# Báo cáo CW Yuanta — KHÔNG CÓ DỮ LIỆU\n\n{report.get('reason')}\n"

    session = report.get("session") or "không rõ phiên"
    counts = report.get("counts", {})
    lines: list[str] = [f"# Báo cáo chứng quyền Yuanta — phiên {session}", ""]

    if report.get("staleData"):
        lines += [f"> ⚠️ **Dữ liệu cũ**: lấy lúc {report.get('fetchedAt')} "
                  f"({_vnd(report.get('ageHours'), 1)} giờ trước, ngưỡng "
                  f"{_vnd(report.get('maxAgeHours'), 0)} giờ). Kiểm tra lại workflow publish.", ""]

    lines += [
        f"- Snapshot: `{report.get('fetchedAt')}`",
        f"- Số mã: **{counts.get('rows', 0)}** · có khớp lệnh: **{counts.get('traded', 0)}** · "
        f"không giao dịch: **{counts.get('untraded', 0)}** ({_pct(counts.get('untradedPct'), 1)})",
        f"- Có phân tích board: {'có' if report.get('hasBoardAnalysis') else 'KHÔNG'} · "
        f"phân tích mở rộng: {'có' if report.get('hasAnalytics') else 'KHÔNG'} · "
        f"chuỗi lịch sử: {'có' if report.get('hasSessions') else 'KHÔNG'}",
        "",
    ]

    summary = report.get("summary") or {}
    if summary:
        lines += ["## Tổng quan phiên", ""]
        lines += _table(
            ["Chỉ tiêu", "Giá trị"],
            [
                ["Tổng giá trị giao dịch", f"{_vnd(summary.get('totalValueVND'))} VND"],
                ["Tổng khối lượng", f"{_vnd(summary.get('totalVolume'))} CW"],
                ["Giá trị trung vị / mã", f"{_vnd(summary.get('medianValueVND'))} VND"],
                ["Số cổ phiếu cơ sở", str(summary.get("underlyings", "—"))],
                ["Tăng / Giảm / Đứng", f"{summary.get('gainers', '—')} / "
                                       f"{summary.get('losers', '—')} / "
                                       f"{summary.get('unchanged', '—')}"],
                ["Biến động trung vị", _pct(summary.get("medianChangePct"))],
                ["Spread trung vị", f"{_pct(summary.get('medianSpreadPct'))} "
                                    f"({_vnd(summary.get('medianSpreadTicks'), 1)} bước giá)"],
                ["Top 10 tỷ trọng giá trị", _pct(summary.get("top10ValueSharePct"), 1)],
            ],
        )
        lines.append("")

    liq = report.get("liquidity") or {}
    top = liq.get("top") or []
    if top:
        lines += ["## Xếp hạng thanh khoản (top 10)", ""]
        lines += _table(
            ["#", "Mã", "Cơ sở", "Giá", "%Ngày", "Giá trị (VND)", "Tỷ trọng", "Nhóm"],
            [[str(r.get("rank", i + 1)), str(r.get("t")), str(r.get("u") or "—"),
              _vnd(r.get("price")), _pct(r.get("chgPct")),
              _vnd(r.get("valueVND")), _pct(r.get("valueSharePct")), str(r.get("tier"))]
             for i, r in enumerate(top)],
        )
        conc = liq.get("concentration") or {}
        if conc:
            lines += ["", f"Tập trung: top 1 = {_pct(conc.get('top1ValueSharePct'), 2)} · "
                          f"top 10 = {_pct(conc.get('top10ValueSharePct'), 2)} · "
                          f"HHI = {_vnd(conc.get('hhi'), 4)}"]
        thresholds = liq.get("thresholds") or []
        if thresholds:
            lines += ["", "Ngưỡng chia nhóm (phân vị của chính phiên này): " + " · ".join(
                f"{t.get('quantile')} = {_vnd(t.get('valueVND'))} VND" for t in thresholds)]
        lines.append("")

    scoring = report.get("scoring") or {}
    if scoring.get("ranking"):
        dist = scoring.get("distribution") or {}
        lines += ["## Xếp hạng CW theo ngày (điểm 0–100)", "",
                  f"- Đã chấm **{_vnd(scoring.get('scored'))}** mã có khớp lệnh "
                  f"({_vnd(scoring.get('unscored'))} mã không giao dịch không được chấm)",
                  f"- Trung vị {_vnd(dist.get('median'), 1)} · p25–p75 = "
                  f"{_vnd(dist.get('p25'), 1)}–{_vnd(dist.get('p75'), 1)}"]
        weights = scoring.get("weights") or {}
        if weights:
            labels = {"liquidity": "thanh khoản", "cost": "chi phí", "priceQuality": "chất lượng giá",
                      "consistency": "độ ổn định"}
            lines.append("- Trọng số: " + " · ".join(
                f"{labels.get(k, k)} {round(v * 100)}%" for k, v in weights.items()))
        lines += ["", *_table(
            ["#", "Mã", "Cơ sở", "Điểm", "Giá", "%Ngày", "Giá trị (VND)", "Thanh khoản", "Chi phí"],
            [[str(r.get("rank")), str(r.get("t")), str(r.get("u") or "—"),
              _vnd(r.get("score"), 1), _vnd(r.get("price")), _pct(r.get("chgPct")),
              _vnd(r.get("valueVND")), _vnd((r.get("parts") or {}).get("liquidity")),
              _vnd((r.get("parts") or {}).get("cost"))]
             for r in (scoring.get("ranking") or [])[:10]])]
        valuation = scoring.get("valuation") or {}
        if valuation.get("available") is False:
            lines += ["", f"- **Không có Black–Scholes/IV/Greeks**: thiếu "
                          f"{', '.join(valuation.get('blockedBy') or [])}. "
                          f"{valuation.get('reason', '')}"]
        lines.append("")

    intraday = report.get("intraday") or {}
    if intraday.get("available"):
        s = intraday.get("summary") or {}
        lines += ["## Trong phiên", "",
                  f"- Biên độ trung vị: **{_pct(s.get('medianRangePct'))}** "
                  f"(≈ {_vnd(s.get('medianRangeTicks'), 1)} bước giá)",
                  f"- Đứng giá cả phiên: **{_vnd(s.get('countFlatSession'))}** mã",
                  f"- Đóng cửa nửa trên / nửa dưới: **{_vnd(s.get('countCloseInUpperHalf'))}** / "
                  f"**{_vnd(s.get('countCloseInLowerHalf'))}** mã", ""]

    band = report.get("priceBand") or {}
    if band.get("available"):
        s = band.get("summary") or {}
        lines += ["## Trần – sàn", "",
                  f"- Chạm trần: **{_vnd(s.get('countAtCeiling'))}** mã "
                  f"{', '.join(s.get('atCeiling') or []) or ''}".rstrip(),
                  f"- Chạm sàn: **{_vnd(s.get('countAtFloor'))}** mã "
                  f"{', '.join(s.get('atFloor') or []) or ''}".rstrip(),
                  f"- Dải trần–sàn trung vị: {_vnd(s.get('medianBandPct'), 1)}% "
                  "(đọc từ nguồn, không phải ±7%)", ""]

    last = report.get("lastTrade") or {}
    if last.get("available"):
        s = last.get("summary") or {}
        lines += ["## Chất lượng giá đóng cửa", "",
                  f"- `LastMVol/TotalVol` trung vị: **{_pct(s.get('medianLastSharePct'), 1)}**",
                  f"- Đóng cửa bằng đúng một lệnh: **{_vnd(s.get('countSingleTradeClose'))}**/"
                  f"{_vnd(s.get('countTraded'))} mã ({_pct(s.get('singleTradeSharePct'), 1)})", ""]

    cont = report.get("refContinuity") or {}
    lines += ["## Kiểm tra tính liên tục", ""]
    if cont.get("available"):
        s = cont.get("summary") or {}
        lines.append(f"- So `RefP` với close phiên {cont.get('prevSession')}: "
                     f"**{s.get('linked', 0)}/{s.get('checked', 0)}** khớp "
                     f"({_pct(s.get('linkedPct'), 1)}) · lệch > {_vnd(s.get('tolerancePct'), 0)}%: "
                     f"{s.get('mismatch', 0)} · thiếu phiên: {s.get('missingSession', 0)}")
        lines.append(f"- Kết luận: **{s.get('verdict', '—')}**")
    else:
        lines.append(f"- {cont.get('reason') or 'Chưa đủ phiên để đối chiếu.'}")
    lines.append("")

    stale = report.get("stale") or {}
    if stale.get("count"):
        lines += ["## Mã không giao dịch", "",
                  f"- **{_vnd(stale.get('count'))}** mã ({_pct(stale.get('sharePct'), 1)})"]
        if not compact:
            rows = [[str(r.get("t")), str(r.get("u") or "—"), _vnd(r.get("refPrice")),
                     str(r.get("sessionsIdle") if r.get("sessionsIdle") is not None else "—")]
                    for r in (stale.get("rows") or [])[:10]]
            if rows:
                lines += [""] + _table(["Mã", "Cơ sở", "RefP", "Phiên im lặng"], rows)
        if stale.get("recoveredCount"):
            lines += ["", f"- Vừa hồi phục sau ≥ {stale.get('thresholdSessions')} phiên im lặng: "
                          f"**{stale.get('recoveredCount')}** mã"]
        lines.append("")

    cov = report.get("historyCoverage") or {}
    lines += ["## Lịch sử", ""]
    if cov.get("sessions"):
        lines.append(f"- {cov.get('sessions')} phiên ({cov.get('first')} → {cov.get('last')}), "
                     f"{cov.get('tickers')} mã, {cov.get('rows')} dòng, "
                     f"{_pct(cov.get('tradedSharePct'), 1)} dòng có khớp lệnh")
        missing = cov.get("missingSessions") or []
        lines.append(f"- Phiên thiếu: {len(missing)}"
                     + (f" ({', '.join(missing[:8])})" if missing else " — không nội suy"))
    else:
        lines.append("- Chưa có chuỗi lịch sử.")
    lines.append("")

    lines += ["## Không có trong báo cáo này", "",
              "Định giá, Greeks, IV, điểm số, khuyến nghị, backtest. Endpoint Yuanta EW không "
              "có strike, hạn mức, ngày đáo hạn, giá cổ phiếu cơ sở hay chuỗi quá khứ, nên "
              "không thể tính các chỉ tiêu đó. Báo cáo chỉ mô tả phiên đã xảy ra.", ""]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--analytics", type=Path, default=DEFAULT_ANALYTICS)
    parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--out", type=Path, default=None, help="ghi báo cáo ra file")
    parser.add_argument("--summary", action="store_true",
                        help="bản gọn (bỏ bảng phụ) — hợp với log cronjob.org")
    parser.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS,
                        help=f"cảnh báo khi dữ liệu cũ hơn ngưỡng (mặc định "
                             f"{DEFAULT_MAX_AGE_HOURS:g} giờ; 0 = tắt)")
    args = parser.parse_args(argv)

    report, code = build_report(
        snapshot_path=args.snapshot, board_path=args.board,
        analytics_path=args.analytics, sessions_path=args.sessions,
        max_age_hours=args.max_age_hours if args.max_age_hours else None,
    )

    if args.format == "json":
        text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    else:
        text = render_markdown(report, compact=args.summary)

    sys.stdout.write(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"\nĐã ghi: {args.out}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
