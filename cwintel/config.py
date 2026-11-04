"""Cấu hình trung tâm: đường dẫn, tham số mô hình, trọng số scoring, ngưỡng khuyến nghị.

Tất cả tham số ở đây đều là **giả định phương pháp luận** (có thể cấu hình qua biến
môi trường / file JSON truyền vào), không phải số liệu thị trường.
"""

from __future__ import annotations

import os
from pathlib import Path

# ──────────────────────────────────────────────────────────────────
# ĐƯỜNG DẪN
# ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent

CACHE_DIR = ROOT / "output" / "cache"
VIETSTOCK_CACHE = CACHE_DIR / "vietstock.parquet"
OHLCV_CACHE = CACHE_DIR / "ohlcv.parquet"
UNDERLYING_CACHE = CACHE_DIR / "underlying.parquet"
IV_CACHE = CACHE_DIR / "iv_history.parquet"
BOND_CACHE = CACHE_DIR / "hnx_bond_yields.csv"
REC_HISTORY_CACHE = CACHE_DIR / "rec_history.parquet"
PANEL_CACHE = CACHE_DIR / "feature_panel.parquet"

DOCS_DIR = ROOT / "docs"
DATA_DIR = DOCS_DIR / "data"
SERIES_DIR = DATA_DIR / "series"

# Lịch sử khuyến nghị (walk-forward) chỉ cần đủ dài để đánh giá, không cần toàn bộ 2023.
BACKTEST_START = os.environ.get("CWINTEL_BACKTEST_START", "2023-06-01")

# ──────────────────────────────────────────────────────────────────
# THAM SỐ ĐỊNH GIÁ
# ──────────────────────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR = 252
DAYS_PER_YEAR = 365.0

# Fallback cuối cùng khi không có cache lợi suất. Giá trị này CHỈ được dùng khi
# thiếu dữ liệu và luôn được ghi kèm `risk_free_source` trong metadata.
DEFAULT_RISK_FREE = 0.0444

# Sigma dùng cho định giá khi không đủ dữ liệu lịch sử underlying.
# Không dùng để "làm đẹp" dữ liệu: mọi CW dùng fallback đều bị đánh dấu data_quality.
SIGMA_FALLBACK = 0.30
MIN_HV_SESSIONS = 60          # tối thiểu số phiên để tính HV có ý nghĩa
HV_WINDOW = 252

# Ngưỡng moneyness (so với strike điều chỉnh). |S/K - 1| <= 2% → ATM.
ATM_BAND = 0.02

# ──────────────────────────────────────────────────────────────────
# TRỌNG SỐ SCORING (tổng = 1.0)
# ──────────────────────────────────────────────────────────────────
SCORE_WEIGHTS = {
    "underlying_momentum": 0.25,
    "valuation": 0.20,
    "liquidity": 0.15,
    "risk_reward": 0.20,
    "technical": 0.10,
    "time_to_maturity": 0.10,
}

SCORE_LABELS_VI = {
    "underlying_momentum": "Động lượng cổ phiếu cơ sở",
    "valuation": "Định giá CW",
    "liquidity": "Thanh khoản",
    "risk_reward": "Rủi ro / Lợi nhuận",
    "technical": "Tín hiệu kỹ thuật",
    "time_to_maturity": "Thời gian đáo hạn",
}

# ──────────────────────────────────────────────────────────────────
# NGƯỠNG KHUYẾN NGHỊ (khởi tạo — được kiểm chứng lại bằng backtest)
# ──────────────────────────────────────────────────────────────────
REC_THRESHOLDS = [
    (80, "STRONG_BUY"),
    (65, "BUY"),
    (45, "HOLD"),
    (30, "AVOID"),
    (0, "HIGH_RISK"),
]

REC_LABELS_VI = {
    "STRONG_BUY": "MUA MẠNH",
    "BUY": "MUA",
    "HOLD": "THEO DÕI",
    "AVOID": "TRÁNH",
    "HIGH_RISK": "RỦI RO CAO",
    "NO_DATA": "CHƯA ĐỦ DỮ LIỆU",
}

REC_COLORS = {
    "STRONG_BUY": "#0f9d58",
    "BUY": "#4caf50",
    "HOLD": "#c9a227",
    "AVOID": "#ef6c00",
    "HIGH_RISK": "#d32f2f",
    "NO_DATA": "#78909c",
}

# Cổng chặn chất lượng: điểm cao không đủ để nâng hạng nếu vi phạm các điều kiện này.
GATES = {
    "STRONG_BUY": {
        "min_score": 80,
        "min_liquidity": 60,
        "min_data_quality": 0.80,
        "min_days_to_maturity": 21,
        "min_median_value_vnd": 50_000_000,
        "max_iv_vs_hv_pct": 40,
        "min_sessions": 15,
    },
    "BUY": {
        "min_score": 65,
        "min_liquidity": 40,
        "min_data_quality": 0.65,
        "min_days_to_maturity": 14,
        "min_median_value_vnd": 10_000_000,
        "max_iv_vs_hv_pct": 60,
        "min_sessions": 10,
    },
}

# Cổng định giá: bằng chứng backtest (docs/BACKTEST.md) cho thấy mua CW khi IV cao
# hơn nhiều so với biến động lịch sử có kỳ vọng âm. Vì vậy MUA/MUA MẠNH yêu cầu
# IV không vượt quá ngưỡng này so với HV. Đây là giả định phương pháp luận có thể cấu hình.
# Dưới ngưỡng này, hệ thống không đưa ra khuyến nghị hành động.
MIN_DATA_QUALITY_FOR_REC = 0.45

# ──────────────────────────────────────────────────────────────────
# THANH KHOẢN
# ──────────────────────────────────────────────────────────────────
LIQUIDITY_WINDOW = 20            # phiên
VALUE_UNIT = 1_000               # giá (nghìn VND) × KL × 1.000 = VND
HIGH_LIQUIDITY_VALUE_VND = 300_000_000   # ≥ 300 triệu/phiên (median 20 phiên) → "cao"
MEDIUM_LIQUIDITY_VALUE_VND = 50_000_000  # ≥ 50 triệu/phiên → "trung bình"

# ──────────────────────────────────────────────────────────────────
# BACKTEST (giả định chi phí — công bố rõ trong báo cáo)
# ──────────────────────────────────────────────────────────────────
BACKTEST = {
    "rebalance_freq": "every N sessions",
    "spacing": 20,                 # tái cân bằng mỗi 20 phiên (không chồng lấn với holding)
    "holding_days": 20,            # phiên nắm giữ
    "top_n": 5,
    "min_days_to_maturity": 30,
    "min_median_value_vnd": 10_000_000,   # sàn thanh khoản tối thiểu
    "max_weight_per_issuer": 0.40,
    "commission_per_side": 0.0015,  # 0,15% — mức phổ biến của CTCK VN
    "slippage_per_side": 0.0030,    # 0,30% — CW biến động mạnh, khớp lệnh thị trường
    "half_spread": 0.0050,          # 0,50% — không có dữ liệu bid/ask → giả định
    "cost_sensitivity": [0.005, 0.010, 0.020],  # tổng chi phí/chiều để kiểm tra độ nhạy
}
BACKTEST["cost_per_side"] = (
    BACKTEST["commission_per_side"] + BACKTEST["slippage_per_side"] + BACKTEST["half_spread"]
)

# ──────────────────────────────────────────────────────────────────
# CẢNH BÁO (alert rules mặc định, người dùng có thể sửa trên UI)
# ──────────────────────────────────────────────────────────────────
ALERT_DEFAULTS = {
    "score_above": 75,
    "score_drop_below": 45,
    "dte_below": 30,
    "rsi_overbought": 75,
    "rsi_oversold": 30,
    "volume_spike_x": 3.0,
    "price_breakout_days": 20,
}

# ──────────────────────────────────────────────────────────────────
# NGƯỠNG HIỂN THỊ
# ──────────────────────────────────────────────────────────────────
STALE_DATA_DAYS_WARNING = 4      # dữ liệu cũ hơn 4 ngày lịch → cảnh báo "không phải realtime"
MIN_SESSIONS_FOR_TECH = 30       # dưới ngưỡng này RSI/MACD không đáng tin
