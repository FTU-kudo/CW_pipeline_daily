# CW Intelligence — Nền tảng phân tích chứng quyền Việt Nam

Nền tảng phân tích covered warrant (chứng quyền): chuẩn hoá dữ liệu do người dùng được quyền truy cập, định giá Black–Scholes, screener, chấm điểm giải thích được và backtest walk-forward. Mã phân tích chạy offline trên dữ liệu cục bộ; chưa có nguồn được chọn hoặc chấp thuận phân phối lại.

**Giao diện:** `docs/index.html` (mã UI tĩnh; không kèm dữ liệu thị trường). **Dữ liệu và dashboard build:** `output/private-data/` (bị Git bỏ qua, chạy riêng trên máy).

> ⚠️ Công cụ phân tích/giáo dục, không phải khuyến nghị đầu tư. Việc dùng thư viện Vnstock không cấp quyền phân phối dữ liệu của nhà cung cấp/sở giao dịch. Xem [`docs/DATA_RIGHTS.md`](docs/DATA_RIGHTS.md).

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
| Thanh khoản | ADV20/độ phủ/Amihud/biên độ theo TCPH và cổ phiếu cơ sở, danh sách cảnh báo, máy tính days-to-liquidate, công cụ phân tích và kiểm tra rủi ro |
| Công cụ | Watchlist, danh mục mô phỏng (P/L, tỷ trọng, DTE), cảnh báo theo quy tắc (client-side) |
| Giao diện | **Song ngữ Việt/Anh** (VI · EN · VI+EN, đổi ngay, nhớ lựa chọn), **sáng/tối/theo hệ thống**, chart có legend + crosshair + tooltip nhiều series, bảng dính header |
| Dữ liệu | Kiểm tra chất lượng 16 hạng mục, metadata nguồn, phát hiện dữ liệu cũ, không che giấu cảnh báo |

---

## 2. Kiến trúc

```
Nguồn                    Ingestion              Chuẩn hoá & kiểm tra        Quant                 Phát hành
─────────────────────────────────────────────────────────────────────────────────────────────────────────
Nguồn được người dùng chọn ─┐
Metadata / lãi suất có quyền ─┴→ output/private-data/cache/* → cwintel/data.py → cwintel/panels.py → output/private-data/dashboard/*.json
                                                       (dedupe & kiểm tra)   cwintel/bs.py      (local-only)
                                                                             quality/scoring/
                                                                             recommend/backtest
```

Chi tiết: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

| Thư mục | Vai trò |
|---|---|
| `pipeline.py` | Nạp/chuẩn hóa dữ liệu đã được cấp quyền; cache, Excel và JSON mặc định nằm trong `output/private-data/` |
| `cwintel/` | Phân tích offline; build mặc định vào `output/private-data/dashboard/`; có guard cấm đường dẫn `docs/` khi thiếu giấy phép |
| `docs/` | Mã giao diện và phương pháp công khai; không chứa snapshot dữ liệu thị trường |
| `docs/DATA_RIGHTS.md` | Phân biệt giấy phép thư viện và quyền dữ liệu; checklist xác nhận quyền tái phân phối |
| `tests/` | Bộ kiểm thử định lượng, UI và cổng quyền xuất bản |

---

## 3. Chạy nhanh

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pandas, numpy, pyarrow, openpyxl, requests, bs4, pytz, pytest

# 1) Kiểm thử
pytest -q

# 2) Dựng artifact riêng trên máy (đầu vào cần có quyền sử dụng)
python -m cwintel.build

# 3) Xem dashboard riêng; server chỉ bind loopback và lấy JSON từ output/private-data/
python scripts/serve_private_dashboard.py --port 8000
# mở http://127.0.0.1:8000
```

`python -m cwintel.build --help`:

| Cờ | Ý nghĩa |
|---|---|
| `--asof YYYY-MM-DD` | Dựng snapshot tại một phiên cụ thể |
| `--no-backtest` | Bỏ backtest (nhanh hơn ~40 s) |
| `--out DIR` | Thư mục đích (mặc định `output/private-data/dashboard`; `docs/` bị khóa nếu chưa có hồ sơ chấp thuận hợp lệ) |

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

## 5. Kết quả dữ liệu

Không có giá trị backtest, snapshot, khuyến nghị hay chuỗi OHLCV nào được phát hành trong repo khi chưa có quyền phân phối lại bằng văn bản. Bộ dữ liệu riêng được dùng để phân tích cục bộ; kết quả công khai chỉ được bổ sung sau khi được cấp quyền và review lại.

## 5.1 Song ngữ & giao diện

Dashboard chạy được ở ba chế độ ngôn ngữ — **VI** (mặc định), **EN**, **VI+EN** hiển thị song song — chuyển bằng công tắc trên topbar, lưu ở `localStorage`. Bản dịch nằm trong `docs/assets/i18n.js` (~600 nhãn + ~40 mẫu câu động cho nội dung do engine sinh), không cần backend, không thêm request mạng, không phát sinh artifact mới. Số liệu, ngày tháng và đơn vị đổi theo locale (`vi-VN` ↔ `en-US`). Giao diện có ba chế độ **Sáng / Tối / Theo hệ thống**, chart tự vẽ lại khi đổi theme hay đổi kích thước cửa sổ. Cơ chế chi tiết: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#31-song-ngữ-việt-anh-docsassetsi18njs).

Kiểm thử: `python -m pytest tests -q` (**162 test**) + bộ kiểm thử đồng hồ `node tests/js/clock.test.mjs` (**94 kiểm tra**, gồm lịch lễ, múi giờ và WCAG); bộ JS cũng được gọi từ pytest khi có Node. Kiểm thử DOM chạy 12 route ở cả VI/EN/VI+EN và dark/light, yêu cầu 0 lỗi console và không còn chuỗi chưa dịch ở chế độ EN.

## 6. Triển khai

Xem [`docs/DEPLOY.md`](docs/DEPLOY.md). Tóm tắt:

- **GitHub Pages**: chỉ có thể phục vụ mã UI/phương pháp trong `docs/`; dữ liệu thị trường đã gỡ khỏi cây hiện tại. UI thông báo khi chưa có bộ dữ liệu được cấp quyền.
- **GitHub Actions**: chỉ chạy test offline, không nhận provider key, không nạp dữ liệu, không commit cache/artifact và không deploy market-data JSON.
- **Dữ liệu và khóa**: lưu riêng trên máy người dùng; không đưa khóa, OTP, cache, workbook hay dữ liệu phái sinh vào Git.
- Nếu có văn bản cho phép phân phối công khai, cần review lại các điều khoản gốc và quy trình phát hành; xem [`docs/DATA_RIGHTS.md`](docs/DATA_RIGHTS.md).

---

## 7. Giới hạn đã biết

- Không có dữ liệu bid/ask thật; chi phí giao dịch là giả định (0,50% nửa chênh lệch + 0,15% phí + 0,30% trượt giá mỗi chiều).
- IV suy ra từ giá cuối phiên, chịu ảnh hưởng bước giá 10 VND (đặc biệt CW giá < 100 VND).
- Không mô phỏng cổ tức/thưởng phát sinh **sau** ngày dữ liệu; điều khoản đã điều chỉnh chỉ phản ánh lịch sử.
- Không phát hành thống kê thanh khoản hoặc hiệu quả chiến lược rút ra từ dữ liệu nguồn nếu chưa có quyền; kiểm tra các hạn chế của bộ dữ liệu riêng trước khi diễn giải.
- Dashboard không đặt lệnh, không kết nối tài khoản, không gửi dữ liệu ra ngoài.
- Cảnh báo chạy phía trình duyệt; Telegram/email cần backend riêng.

---

## 8. Cấu trúc repo (rút gọn)

```
.
├── pipeline.py                 # ingestion cục bộ → output/private-data/
├── bs_calculator.py            # CLI Black–Scholes độc lập
├── cwintel/                    # thư viện phân tích (xem ARCHITECTURE.md)
├── docs/
│   ├── index.html              # UI tĩnh; không kèm dữ liệu thị trường
│   ├── assets/                 # core.js + pages/*.js + app.css
│   ├── DATA_RIGHTS.md          # quyền dữ liệu và cổng xuất bản
│   ├── AUDIT.md                # trạng thái migration, không còn snapshot
│   └── ARCHITECTURE/DEPLOY/METHODOLOGY.md
├── output/private-data/       # dữ liệu/cache/artifact cục bộ (gitignored)
├── scripts/                    # rights checker + server cục bộ
├── tests/                      # pytest offline
└── .github/workflows/          # kiểm thử offline, không ingestion/publish
```

---

## 9. Ghi công & giấy phép

Nguồn dữ liệu chưa được cấu hình trong repo; người dùng cần chọn nguồn có quyền và tuân thủ điều khoản gốc. Mã nguồn theo giấy phép trong [`LICENSE`](LICENSE), không bao gồm quyền dữ liệu. Xem [`docs/DATA_RIGHTS.md`](docs/DATA_RIGHTS.md).

**Miễn trừ:** chứng quyền có thể mất toàn bộ giá trị khi đáo hạn OTM. Hiệu suất quá khứ không đảm bảo tương lai. Nhà đầu tư tự chịu trách nhiệm với quyết định của mình.
