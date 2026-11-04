# CW Intelligence — Nền tảng phân tích chứng quyền Việt Nam

Nền tảng phân tích **covered warrant (chứng quyền)** cho thị trường Việt Nam: dữ liệu chuẩn hoá hằng ngày, định giá Black–Scholes, screener đa điều kiện, bảng nhiệt, chấm điểm 0–100 có thể giải thích, kế hoạch giao dịch mô phỏng và backtest walk-forward — tất cả chạy trên dữ liệu thật, không có số liệu demo.

**Dashboard:** `docs/index.html` (GitHub Pages) · **Dashboard cũ:** `docs/legacy.html`

> ⚠️ Công cụ phân tích & giáo dục. Không phải khuyến nghị đầu tư. Dữ liệu là snapshot cuối phiên, **không phải realtime**.

---

## 1. Năng lực chính

| Nhóm | Chức năng |
|---|---|
| Tổng quan | Số CW active/đáo hạn, độ rộng tăng–giảm, giá trị & khối lượng, ITM/ATM/OTM, top tăng/giảm/thanh khoản, phân bố theo TCPH và cổ phiếu cơ sở |
| Heatmap | Treemap theo mã / cổ phiếu cơ sở / TCPH / moneyness; tô màu theo %thay đổi, CW Score, premium, IV, IV−HV, DTE, giá trị; nhấp để mở chi tiết |
| Screener | 35+ trường số & định tính, logic AND/OR, 8 bộ lọc mẫu, lưu bộ lọc, chọn cột, sắp xếp, xuất CSV/Excel |
| Chi tiết CW | Nến + KL + MA20/50, RSI, MACD, giá cổ phiếu cơ sở; bảng định giá; Greeks; lịch sử premium/IV; **phân tích kịch bản**; **thanh khoản & máy tính thoát vị thế**; so sánh cùng cơ sở |
| Khuyến nghị | CW Score 0–100 với 6 thành phần có trọng số, cổng chất lượng, yếu tố +/−, cảnh báo rủi ro, điều kiện vô hiệu hoá, kế hoạch giao dịch (entry/stop/TP/holding) |
| Backtest | Walk-forward, không nhìn trước, có chi phí bid-ask/phí/trượt giá, xử lý đáo hạn, benchmark, độ nhạy (holding, ngưỡng điểm, chi phí, bộ lọc), báo cáo cả kết quả xấu |
| Thanh khoản | ADV20/độ phủ/Amihud/biên độ theo TCPH và cổ phiếu cơ sở, danh sách cảnh báo, máy tính days-to-liquidate, bằng chứng thực nghiệm từ backtest |
| Công cụ | Watchlist, danh mục mô phỏng (P/L, tỷ trọng, DTE), cảnh báo theo quy tắc (client-side) |
| Giao diện | **Song ngữ Việt/Anh** (VI · EN · VI+EN, đổi ngay, nhớ lựa chọn), **sáng/tối/theo hệ thống**, chart có legend + crosshair + tooltip nhiều series, bảng dính header |
| Dữ liệu | Kiểm tra chất lượng 16 hạng mục, metadata nguồn, phát hiện dữ liệu cũ, không che giấu cảnh báo |

---

## 2. Kiến trúc

```
Nguồn                    Ingestion              Chuẩn hoá & kiểm tra        Quant                 Phát hành
─────────────────────────────────────────────────────────────────────────────────────────────────────────
Vietstock (điều khoản) ─┐
vnstock VCI/KBS (OHLCV)─┤→ output/cache/*.parquet → cwintel/data.py      → cwintel/panels.py  → docs/data/*.json
HNX/VBMA (lãi suất)     ┘        (dedupe ngày)      cwintel/dates.py         cwintel/bs.py        13 MB tĩnh
                                                    cwintel/quality.py       cwintel/scoring.py   (GitHub Pages)
                                                                             cwintel/recommend.py
                                                                             cwintel/backtest.py
```

Chi tiết: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

| Thư mục | Vai trò |
|---|---|
| `pipeline.py` | Pipeline gốc: scrape Vietstock + tải OHLCV, xuất Excel & `docs/data.json` (giữ nguyên để tương thích) |
| `cwintel/` | Thư viện phân tích mới: chuẩn hoá, Black–Scholes, chỉ báo, panel, scoring, recommendation, backtest, build JSON |
| `docs/data/` | Artifact tĩnh cho dashboard (meta/market/screener/recommendations/underlyings/liquidity/backtest/quality/methodology + series) |
| `docs/assets/` | SPA không phụ thuộc thư viện ngoài (vanilla JS + canvas) |
| `tests/` | 71 kiểm thử pytest (BS, Greeks, IV, chỉ báo, thanh khoản, scoring, backtest, artifact) |

---

## 3. Chạy nhanh

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pandas, numpy, pyarrow, openpyxl, requests, bs4, pytz, pytest

# 1) Kiểm thử
pytest -q

# 2) Dựng lại toàn bộ artifact (~3–4 phút với cache sẵn trong output/cache)
python -m cwintel.build

# 3) Xem dashboard (bắt buộc dùng web server — fetch JSON không chạy với file://)
python -m http.server 8000 --directory docs
# mở http://localhost:8000
```

`python -m cwintel.build --help`:

| Cờ | Ý nghĩa |
|---|---|
| `--asof YYYY-MM-DD` | Dựng snapshot tại một phiên cụ thể |
| `--no-backtest` | Bỏ backtest (nhanh hơn ~40 s) |
| `--out DIR` | Thư mục đích (mặc định `docs/data`) |

---

## 4. Mô hình định lượng (tóm tắt)

**Định giá** — quyền châu Âu, thanh toán tiền mặt, tỷ lệ chuyển đổi *n*:1, dùng strike/tỷ lệ **đã điều chỉnh**:

```
C = [S·N(d1) − K·e^(−rT)·N(d2)] / n
Delta/CW = N(d1)/n ; Vega/CW = S·φ(d1)·√T/100/n ; Theta/CW = ∂C/∂t/365/n
Premium hoà vốn = (K + P_CW·n)/S − 1
```

**CW Score (0–100)** — trung bình có trọng số của 6 thành phần, mỗi thành phần có *độ tin cậy* theo lượng dữ liệu thực có:

| Thành phần | Trọng số | Đo lường chính |
|---|---|---|
| Động lượng cổ phiếu cơ sở | 25% | percentile return 21/63 phiên (trên các underlying duy nhất), trend MA20/50, RSI |
| Định giá | 20% | percentile premium & IV residual **trong cùng cơ sở**, IV/HV, IV rank, dải delta |
| Thanh khoản | 15% | ADV20 trên lịch đầy đủ, Amihud (tác động giá), độ phủ từ khi niêm yết, tác động giá ước tính, xu hướng ADV5/ADV20 |
| Rủi ro/lợi nhuận | 20% | theta/ngày, khoảng cách hoà vốn, DTE, biến động, gearing hiệu dụng |
| Kỹ thuật | 10% | RSI, MACD, MA20/50, breakout (giảm độ tin cậy nếu <30 phiên) |
| Thời gian | 10% | DTE, ưu tiên 45–180 ngày |

**Cổng chất lượng** (không bao giờ MUA MẠNH khi vi phạm): điểm thanh khoản, DQ, DTE, **ADV20 ≥ 100 triệu/phiên**, **độ phủ giao dịch ≥ 80%**, **biên độ high-low ≤ 12%**, **IV−HV ≤ 40%**, **≥15 phiên lịch sử**.

Chi tiết công thức, giả định và giới hạn: [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) · từ điển dữ liệu: [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md)

---

## 5. Kết quả backtest (công bố trung thực)

Giai đoạn 06/2023 → 11/2026, tái cấu trúc 20 phiên, top-5 theo Score, chi phí 0,95%/chiều:

| Chiến lược | Tổng LN | CAGR | Sharpe | MDD |
|---|---|---|---|---|
| Top-5 theo CW Score | −84,5% | −42,1% | −0,53 | −86,7% |
| Toàn vũ trụ CW (EW) | −95,0% | −58,5% | −1,85 | −94,9% |
| Ngẫu nhiên | −96,4% | −62,3% | −1,61 | −96,3% |
| Cổ phiếu cơ sở (EW) | +44,9% | — | 0,44 | −20,3% |

Kết luận không tô hồng: **mua CW nắm giữ ngắn hạn có kỳ vọng âm** trên dữ liệu Việt Nam (theta + IV cao + chênh lệch mua-bán). Bộ lọc **IV ≤ HV** giúp giảm lỗ mạnh (−2,44% → −0,13%/lệnh, win 57,1%) nhưng chưa dương; kết hợp IV ≤ HV **và** cơ sở trên MA50 đạt +0,66%/lệnh (44 lệnh, PF 1,05) nhưng tổng vẫn âm. Đây là lý do cổng IV được đưa vào điều kiện MUA/MUA MẠNH, và vì sao dashboard luôn hiển thị giới hạn mô hình thay vì "tín hiệu thắng".

**Thanh khoản** được nghiên cứu riêng trong [`docs/RESEARCH_LIQUIDITY.md`](docs/RESEARCH_LIQUIDITY.md): trên 7.134 quan sát 20 phiên, nhóm ADV20 thấp nhất lỗ −18,3% và 14,1% lệnh không thoát được đúng hạn, nhóm cao nhất −3,9% và 8,0%; nhưng thêm bộ lọc ADV vào top-5 **không** tạo alpha. Vì vậy thanh khoản là **cổng rủi ro thực thi**, không phải tín hiệu mua — và điều này được ghi rõ trên dashboard.

---

## 5.1 Song ngữ & giao diện

Dashboard chạy được ở ba chế độ ngôn ngữ — **VI** (mặc định), **EN**, **VI+EN** hiển thị song song — chuyển bằng công tắc trên topbar, lưu ở `localStorage`. Bản dịch nằm trong `docs/assets/i18n.js` (~600 nhãn + ~40 mẫu câu động cho nội dung do engine sinh), không cần backend, không thêm request mạng, không phát sinh artifact mới. Số liệu, ngày tháng và đơn vị đổi theo locale (`vi-VN` ↔ `en-US`). Giao diện có ba chế độ **Sáng / Tối / Theo hệ thống**, chart tự vẽ lại khi đổi theme hay đổi kích thước cửa sổ. Cơ chế chi tiết: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#31-song-ngữ-việt-anh-docsassetsi18njs).

Kiểm thử: `python -m pytest tests -q` (80 test) + kiểm thử DOM chạy 12 route ở cả VI/EN/VI+EN và dark/light, yêu cầu 0 lỗi console và không còn chuỗi chưa dịch ở chế độ EN.

## 6. Triển khai

Xem [`docs/DEPLOY.md`](docs/DEPLOY.md). Tóm tắt:

- **GitHub Pages**: phục vụ thư mục `docs/` (Settings → Pages → Deploy from branch → `/docs`).
- **GitHub Actions**: workflow `CW Pipeline Daily` chạy pipeline gốc; workflow `CW Intelligence` chạy `pytest` + `python -m cwintel.build` và commit `docs/data/`.
- **Không cần backend/database.** Không có API key trong repo; dữ liệu công khai, tổng hợp.
- Nếu mở dashboard bằng `file://`, trình duyệt chặn `fetch` JSON → luôn dùng web server tĩnh.

---

## 7. Giới hạn đã biết

- Không có dữ liệu bid/ask thật; chi phí giao dịch là giả định (0,50% nửa chênh lệch + 0,15% phí + 0,30% trượt giá mỗi chiều).
- IV suy ra từ giá cuối phiên, chịu ảnh hưởng bước giá 10 VND (đặc biệt CW giá < 100 VND).
- Không mô phỏng cổ tức/thưởng phát sinh **sau** ngày dữ liệu; điều khoản đã điều chỉnh chỉ phản ánh lịch sử.
- Thanh khoản CW Việt Nam mỏng và phân tán: 31% số CW chỉ chiếm 1,3% giá trị giao dịch; ADV20 tính trên lịch đầy đủ (phiên trắng = 0) và **tính lại tại ngày as-of**, nhưng vẫn bao gồm giao dịch của tổ chức tạo lập thị trường. Không có dữ liệu bid/ask.
- Dashboard không đặt lệnh, không kết nối tài khoản, không gửi dữ liệu ra ngoài.
- Cảnh báo chạy phía trình duyệt; Telegram/email cần backend riêng.

---

## 8. Cấu trúc repo (rút gọn)

```
.
├── pipeline.py                 # pipeline gốc (Vietstock + vnstock → Excel, docs/data.json)
├── bs_calculator.py            # CLI Black–Scholes độc lập
├── cwintel/                    # thư viện phân tích (xem ARCHITECTURE.md)
├── docs/
│   ├── index.html              # SPA mới
│   ├── legacy.html             # dashboard cũ (giữ nguyên)
│   ├── assets/                 # core.js + pages/*.js + app.css
│   ├── data/                   # artifact JSON (sinh tự động, KHÔNG sửa tay)
│   ├── AUDIT.md                # kiểm toán dữ liệu & lỗi hệ thống cũ
│   ├── ARCHITECTURE.md  DATA_DICTIONARY.md  METHODOLOGY.md  DEPLOY.md
│   ├── RESEARCH_LIQUIDITY.md  # nghiên cứu thanh khoản (số liệu thực nghiệm)
├── output/cache/               # parquet cache (nguồn cho cwintel)
├── tests/                      # pytest
└── .github/workflows/          # pipeline gốc + CW Intelligence
```

---

## 9. Ghi công & giấy phép

Dữ liệu: Vietstock (điều khoản CW), vnstock/VCI/KBS (OHLCV), HNX/VBMA (đường cong lợi suất). Mã nguồn theo giấy phép trong [`LICENSE`](LICENSE).

**Miễn trừ:** chứng quyền có thể mất toàn bộ giá trị khi đáo hạn OTM. Hiệu suất quá khứ không đảm bảo tương lai. Nhà đầu tư tự chịu trách nhiệm với quyết định của mình.
