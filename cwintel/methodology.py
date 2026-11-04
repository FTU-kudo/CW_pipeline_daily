"""Nội dung phương pháp luận xuất ra docs/data/methodology.json (và hiển thị trên UI)."""

from __future__ import annotations

from . import METHODOLOGY_VERSION, config


def methodology_payload() -> dict:
    return {
        "version": METHODOLOGY_VERSION,
        "currency_units": {
            "price": "VND cho 1 chứng quyền",
            "underlying": "VND cho 1 cổ phiếu",
            "value": "VND (giá CW × khối lượng)",
            "ratio": "số CW cần để nhận 1 cổ phiếu (n:1)",
            "T": "năm, ACT/365",
        },
        "conventions": [
            {"id": "strike", "title": "Giá thực hiện & tỷ lệ chuyển đổi",
             "formula": "K = K_điều_chỉnh nếu có, ngược lại K_gốc; n = ratio_điều_chỉnh nếu có",
             "note": "CW Việt Nam điều chỉnh strike/ratio khi có cổ tức, thưởng. Dùng strike gốc "
                     "sẽ làm break-even lệch trung vị ~811 VND (xem docs/AUDIT.md)."},
            {"id": "value", "title": "Giá trị 1 CW",
             "formula": "C = S·N(d1) − K·e^(−rT)·N(d2);  P_CW = C / n",
             "note": "Quyền châu Âu, thanh toán tiền mặt, không trừ cổ tức (đã nằm trong K, n)."},
            {"id": "d1d2", "title": "d1, d2",
             "formula": "d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T);  d2 = d1 − σ√T"},
            {"id": "delta", "title": "Delta",
             "formula": "Δ_CW = N(d1) / n",
             "note": "Đơn vị: cổ phiếu quy đổi trên 1 CW. 'Δ tuỳ chọn' hiển thị trên UI là N(d1) "
                     "(delta của quyền trên 1 cổ phiếu) để so sánh moneyness."},
            {"id": "gamma", "title": "Gamma",
             "formula": "Γ_CW = φ(d1) / (S·σ·√T·n)"},
            {"id": "vega", "title": "Vega",
             "formula": "V_CW = S·φ(d1)·√T / 100 / n",
             "note": "VND/CW cho 1 điểm biến động (1%)."},
            {"id": "theta", "title": "Theta",
             "formula": "Θ_CW = [−S·φ(d1)·σ/(2√T) − r·K·e^(−rT)·N(d2)] / 365 / n",
             "note": "VND/CW/ngày lịch; thường âm với vị thế mua."},
            {"id": "intrinsic", "title": "Giá trị nội tại & thời gian",
             "formula": "IV_CW = max(S − K, 0)/n;  TV = P_CW − IV_CW"},
            {"id": "premium", "title": "Premium hoà vốn",
             "formula": "Premium = (BE/S − 1)·100;  BE = K + P_CW·n",
             "note": "Đây là premium chuẩn so sánh được giữa các mức moneyness. "
                     "'Premium thời gian' = TV/S chỉ là phần giá trị thời gian, KHÔNG so sánh "
                     "được giữa ITM và OTM."},
            {"id": "gearing", "title": "Đòn bẩy",
             "formula": "Gearing_gộp = S / (P_CW·n);  Gearing_hiệu_dụng = N(d1)·S/(P_CW·n)",
             "note": "Gearing hiệu dụng = gearing gộp × delta tuỳ chọn; là mức thay đổi giá CW "
                     "khi underlying thay đổi 1%."},
            {"id": "iv", "title": "Implied volatility",
             "formula": "Giải BS ngược từ P_CW thị trường (bisection + Newton)",
             "note": "Chỉ nhận IV khi giá CW > giá trị nội tại và ≤ S/n; gắn cờ chất lượng thấp "
                     "khi giá CW ≤ 30 VND, T < 7 ngày hoặc IV > 300%."},
            {"id": "smile", "title": "Đường cong biến động (smile) cùng underlying",
             "formula": "IV ≈ a + b·z với z = ln(K/S)/√T (OLS theo nhóm cùng underlying)",
             "note": "Nếu R² < 0,15 thì dùng kernel Gaussian theo z. 'IV residual' = IV thực / IV "
                     "trên đường cong − 1. Giá trị hợp lý (fair value smile) = BS với IV trên "
                     "đường cong. Đây là thước đo đắt/rẻ TƯƠNG ĐỐI trong cùng cổ phiếu cơ sở."},
            {"id": "hv", "title": "Historical volatility",
             "formula": "σ_HV = stdev(ln(P_t/P_{t−1}), 252 phiên) × √252 (ddof=1)"},
            {"id": "rsi", "title": "RSI(14)",
             "formula": "Wilder: RSI = 100 − 100/(1 + EMA_α(gain)/EMA_α(loss)), α = 1/14"},
            {"id": "macd", "title": "MACD(12,26,9)",
             "formula": "MACD = EMA12 − EMA26; Signal = EMA9(MACD); Histogram = MACD − Signal"},
            {"id": "atr", "title": "ATR(14)",
             "formula": "TR = max(H−L, |H−C_{t−1}|, |L−C_{t−1}|); ATR = Wilder EMA của TR"},
        ],
        "scoring": {
            "range": "0–100, là điểm TƯƠNG ĐỐI trong vũ trụ CW hiện tại (xếp hạng percentile), "
                     "không phải xác suất sinh lời.",
            "weights": config.SCORE_WEIGHTS,
            "labels": config.SCORE_LABELS_VI,
            "components": {
                "underlying_momentum": "40% percentile return 21 phiên + 20% return 63 phiên + "
                                       "20% vị thế so với MA20/MA50 + 15% vùng RSI + 5% khoảng "
                                       "cách đỉnh 60 phiên",
                "valuation": "30% percentile premium hoà vốn (thấp tốt) + 30% percentile IV "
                             "residual so với smile + 15% percentile IV/HV + 10% percentile "
                             "upside so với fair value smile + 5% IV rank + 10% vùng delta",
                "liquidity": "35% percentile log(ADV20) + 20% percentile Amihud (thấp tốt) + "
                             "20% độ phủ giao dịch từ khi niêm yết + 15% dải tác động giá ước "
                             "tính cho vị thế 50 triệu + 10% xu hướng ADV5/ADV20",
                "risk_reward": "30% theta %/ngày + 25% khoảng cách tới break-even + 25% thời gian "
                               "đáo hạn + 10% vùng biến động + 10% mức gearing hiệu dụng",
                "technical": "30% vùng RSI + 20% MACD dương + 10% MACD tăng + 20% trên MA20 + "
                             "10% trên MA50 + 10% breakout 20 phiên (giảm độ tin cậy nếu < 30 phiên)",
                "time_to_maturity": "Ưu tiên 45–180 ngày; giảm mạnh dưới 30 ngày và trên 270 ngày",
            },
            "confidence": "Mỗi thành phần có confidence = tỷ lệ trọng số có dữ liệu. Điểm tổng "
                          "chuẩn hoá lại theo trọng số khả dụng, nên CW thiếu dữ liệu không bị "
                          "điểm 0 oan.",
            "data_quality": "0–1, tổng hợp: điều khoản hợp lệ, nguồn sigma, độ mới giá, số phiên, "
                            "độ dài lịch sử underlying, có IV, tỷ lệ phiên giao dịch.",
        },
        "recommendation": {
            "thresholds": [{"min": th, "label": lb, "label_vi": config.REC_LABELS_VI[lb]}
                           for th, lb in config.REC_THRESHOLDS],
            "gates": config.GATES,
            "note": "Điểm cao không đủ để nâng hạng nếu vi phạm cổng thanh khoản (ADV20, độ phủ, "
                    "biên độ high-low) / chất lượng dữ liệu / thời gian đáo hạn / IV quá cao so với HV. "
                    "Cổng thanh khoản phản ánh khả năng thoát vị thế, không phải kỳ vọng lợi nhuận — "
                    "xem docs/RESEARCH_LIQUIDITY.md.",
            "no_data": "Khi data_quality < 0,45 hệ thống trả 'CHƯA ĐỦ DỮ LIỆU' thay vì một "
                       "khuyến nghị hành động.",
        },
        "trading_plan": {
            "entry": "Quanh giá hiện tại ± 0,5 ATR(14), làm tròn bước giá 10 VND",
            "stop_loss": "Giá − 2 ATR(14)",
            "take_profit": "Mô phỏng BS khi underlying +5% / +10% sau 10 / 20 phiên (sigma = HV "
                           "hiện tại, T đã trừ thời gian nắm giữ); backtest dùng TP = 2R",
            "holding": "min(60, ngày tới đáo hạn − 15), tối thiểu 5 phiên",
            "note": "Đây là kịch bản mô phỏng có quy tắc, không phải dự báo giá.",
        },
        "backtest": {
            "method": "Walk-forward, tín hiệu tại t, vào lệnh tại close phiên kế tiếp, "
                      "nắm giữ 20 phiên, tái cân bằng mỗi 20 phiên, top-5 điểm cao nhất, "
                      "giới hạn 40% vốn mỗi issuer.",
            "costs": config.BACKTEST,
            "benchmarks": ["EW toàn bộ CW đủ điều kiện", "Chọn ngẫu nhiên 5 CW (trung bình 10 seed)",
                           "EW rổ 22 cổ phiếu cơ sở"],
            "biases": ["Không survivorship: universe gồm cả CW đã đáo hạn",
                       "Không look-ahead: mọi đặc trưng dùng dữ liệu ≤ t, vào lệnh t+1",
                       "Hạn chế: điều khoản CW lấy từ snapshot hiện tại; không mô phỏng "
                       "giới hạn khối lượng"],
        },
        "data_quality_rules": [
            "Không hiển thị dữ liệu cũ như realtime: mọi bảng có cột 'phiên' và cảnh báo nếu "
            "quá 4 ngày.",
            "Không nội suy giá CW; CW không giao dịch quá 7 ngày bị loại khỏi snapshot.",
            "Giá trị mô phỏng (scenario, portfolio, backtest) luôn được ghi nhãn riêng.",
        ],
        "limitations": [
            "Không có dữ liệu bid/ask thật → spread phải giả định.",
            "Không có lịch sử lợi suất TPCP dài → r dùng hằng số hiện tại trong backtest.",
            "Không có dữ liệu khối lượng nước ngoài / room / tự doanh.",
            "Điểm số là tương đối theo vũ trụ hiện tại; khi thị trường xấu, điểm cao vẫn có thể "
            "đi kèm kỳ vọng âm (xem kết quả backtest).",
            "Không phải khuyến nghị đầu tư; không đảm bảo lợi nhuận.",
        ],
        "sources": [
            "Vietstock (finance.vietstock.vn) — điều khoản CW",
            "vnstock — OHLCV (VCI/KBS)",
            "HNX / VBMA — đường cong lợi suất TPCP",
        ],
    }
