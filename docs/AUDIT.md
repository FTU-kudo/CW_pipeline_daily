# AUDIT KỸ THUẬT — CW Pipeline Daily

> Thời điểm audit: 2026-11-04 (ICT). Audit trên commit `3a9a304`, dữ liệu cache ngày 03/11/2026.
> Mọi con số dưới đây được tính trực tiếp từ `output/cache/*.parquet` và `docs/data.json` trong repo,
> không phải ước lượng. Mã kiểm chứng nằm trong `docs/audit/` (script chạy lại được, không cần mạng).

---

## 1. Kiến trúc hiện tại

```
GitHub Actions (cw_pipeline.yml, schedule ĐANG BỊ COMMENT)
        │
        ▼
pipeline.py
  step1_vietstock()      scrape finance.vietstock.vn → output/cache/vietstock.parquet
  step2_ohlcv()          vnstock (VCI → KBS fallback)  → output/cache/ohlcv.parquet
  step3_filter()         lọc ticker có phiên ≥ FILTER_DATE, sort ngày → ticker
  step4_excel()          output/cw_master.xlsx (OHLCV / CW_Info_Active / CW_Info_Expired)
  step5_export_json()    docs/data.json (cw_list + ohlcv + BS/Greeks)  ← dashboard đọc file này
        │
        ▼
docs/index.html  — SPA tĩnh (Chart.js CDN, không build step), GitHub Pages
```

Thành phần phụ:

| File | Vai trò thực tế |
|---|---|
| `bs_calculator.py` (33 KB) | **Dead code** — không được import ở bất kỳ đâu (`grep -n "bs_calculator" pipeline.py` → 0 kết quả). Chứa logic lãi suất HNX/vnbond phức tạp nhưng pipeline dùng bản riêng trong `pipeline.py`. |
| `check_cw_groups.py` | Script chẩn đoán ad-hoc, hardcode mốc `2026-08-15`. |
| `patch_ohlcv.py` | Script vá dữ liệu ad-hoc, hardcode `START_DATE=2026-08-15`. |
| `output/cache/hnx_bond_yields.csv` | 57 phiên lợi suất TPCP (2026-08 → 2026-11-03), cột `10Y` = 4.441% (03/11). |

Nguồn dữ liệu: Vietstock (metadata CW), vnstock/VCI/KBS (OHLCV CW + cổ phiếu cơ sở), HNX/VBMA
(lãi suất phi rủi ro 10Y). Không có API key nào bị commit; `VNSTOCK_API` lấy từ GitHub Secrets — **đạt**.

---

## 2. Chất lượng dữ liệu (phát hiện quan trọng nhất)

### 2.1. Trùng lặp 31,4% do khoá dedupe là *chuỗi ngày thô*

`output/cache/ohlcv.parquet`: **273.488 dòng** nhưng chỉ có **187.552 cặp (ticker, ngày) duy nhất**
→ **85.936 dòng trùng (31,4%)**.

Nguyên nhân: cùng một phiên được lưu ở 2 định dạng chuỗi — `14/03/2023` và `2023-03-14 07:00:00`
(timezone +07 đã bị "trôi" vào chuỗi). Dedupe hiện tại dùng `drop_duplicates(subset=["time","Ticker"])`
trên **chuỗi thô**, nên hai định dạng không bao giờ trùng nhau.

Kiểm chứng hai định dạng là **cùng một dữ liệu** (không phải nguồn khác):

| Chỉ số | Giá trị |
|---|---|
| Số cặp (ticker, ngày) xuất hiện ở cả 2 định dạng | 115.135 |
| Tương quan mức giá close giữa 2 định dạng | **0,99999** |
| Tỷ lệ giá trị giống tuyệt đối | **96,8%** |
| Chênh lệch tương đối p99 | 3,9% (snapshot lệch, thường là dữ liệu intraday) |

### 2.2. Parse ngày `dayfirst=True` làm mất 100% dòng ISO → dữ liệu công bố thiếu 25,7%

`step2`, `step3_filter`, `step5` đều dùng `pd.to_datetime(..., dayfirst=True)`.
Với chuỗi `2023-03-14 07:00:00`, pandas suy luận format từ phần tử đầu và trả **NaT** cho toàn bộ
nhóm ISO (đo được: **134.178/273.488 = 49,1% NaT**), sau đó bị `dropna` loại bỏ.

Hệ quả trên dữ liệu đã công bố: `docs/data.json` chỉ có **139.310 điểm OHLCV / 1.315 ticker**,
trong khi cache có **187.552 phiên-ticker** → **thiếu 48.242 phiên (25,7%)**.
Ví dụ `CACB2301`: cache 197 dòng, dashboard chỉ có 99 điểm (mất 98 phiên).

Hệ quả phân tích: mọi chỉ số dựa trên chuỗi (return 5D/21D, HV, RSI, MACD, backtest) hiện đang
được tính trên chuỗi **bị đứt gãy** — sai lệch không thể phát hiện bằng mắt trên UI.

### 2.3. Các bất thường khác

| Kiểm tra | Kết quả |
|---|---|
| OHLC bất khả thi (`close` ngoài `[low, high]`) | 47 dòng / 273.488 (0,017%) |
| Giá ≤ 0 hoặc volume ≤ 0 | 0 |
| Trùng `ma_cw` trong vietstock | 0 |
| Trùng (ticker, ngày) trong underlying cache | 0 (underlying chỉ có 1 định dạng) |
| Thiếu `gia_th_dieu_chinh` / `tlcd_dieu_chinh` | 841/1.315 (64%) — bình thường, CW không bị điều chỉnh |
| Underlying | 22 mã × 1.001 phiên (2022-10-27 → 2026-11-03) — đủ dài cho MA200/HV252 |
| `iv_history.parquet` | chỉ 70 phiên (2026-07-22 → 2026-11-03) → **IV Rank chưa có ý nghĩa thống kê** |

---

## 3. Kiểm tra logic Black‑Scholes

### 3.1. Công thức: đúng cho quyền châu Âu, nhưng **sai đơn vị Greeks**

`black_scholes_option()` (pipeline.py:27) tính đúng `d1/d2`, `C = S·N(d1) − K·e^{−rT}·N(d2)`, và quy
đổi `bs_price = C/1000/ratio` (nghìn VND/CW) — khớp quy ước CW Việt Nam (tỷ lệ chuyển đổi
`n:1`, giá CW = giá quyền / n).

Nhưng:

| Field | Công thức hiện tại | Vấn đề |
|---|---|---|
| `delta` | `N(d1)` | **Delta của 1 cổ phiếu, không phải của 1 CW.** Delta/CW phải là `N(d1)/ratio`. UI hiển thị nhầm. |
| `gamma` | `φ(d1)/(Sσ√T)/ratio` | Đúng đơn vị/CW. |
| `vega` | `Sφ(d1)√T/100/ratio` | Đúng (VND/CW cho 1 điểm vol). |
| `theta` | `(...)/365` — **không chia ratio** | **Sai đơn vị**: theta tính trên 1 cổ phiếu trong khi gamma/vega tính trên 1 CW. |
| `rho` | không có | Thiếu. |
| `breakeven` | `(K + P_cw·ratio)/1000` | Trả về **nghìn VND** trong khi `underlying_price` là **VND** → UI trộn đơn vị. |
| `premium` | `(P_cw·ratio − max(S−K,0))/S` | Chỉ là *time value / S*, **không so sánh được giữa ITM và OTM**. Premium chuẩn phải là `(BE/S − 1)`. |

### 3.2. Không dùng giá thực hiện / tỷ lệ chuyển đổi **đã điều chỉnh**

57/335 CW đang giao dịch có `gia_th_dieu_chinh` + `tlcd_dieu_chinh` (điều chỉnh cổ tức/thưởng),
nhưng `step5` chỉ dùng `gia_thuc_hien` và `ty_le_chuyen_doi`.

Kiểm chứng bằng chính dữ liệu Vietstock (cột `hoa_von` = break-even do Vietstock tính):

| Cách tính break-even | Trung vị sai lệch so với Vietstock | % khớp ±1 VND |
|---|---|---|
| Dùng K, ratio gốc (hiện tại) | **811 VND** | 37,6% |
| Dùng K, ratio điều chỉnh | **0,4 VND** | **75,1%** |

Ví dụ `CACB2304`: K gốc 23.000, K điều chỉnh 19.323; ratio gốc 3, điều chỉnh 2,5204.
Break-even đúng 25.675 VND; code hiện tại cho 30.560 VND (sai 19%).
→ Toàn bộ premium, moneyness, intrinsic, BS value của nhóm CW này đang sai.

### 3.3. Moneyness: tin cột `trang_thai_cw` của Vietstock là không an toàn

So sánh `trang_thai_cw` với moneyness tự tính từ K điều chỉnh: **145/1.315 dòng (11%)** lệch.
Vietstock đánh dấu ITM cho cả những CW có `S < 0,98·K` (ví dụ `CHDB2605`: S=26.800, K=27.800 → OTM,
Vietstock ghi ITM). Thiếu chuẩn công bố → phải tự định nghĩa và ghi rõ ngưỡng.

### 3.4. Các lỗi nhỏ khác trong BS

* `bs_price` làm tròn 3 chữ số ở đơn vị **nghìn VND** ⇒ độ phân giải 1 VND. 49/335 CW active có
  `bs_price_call = 0`, không phân biệt được "giá trị < 1 VND" với "không tính được".
* `T` âm với CW đã đáo hạn → hàm trả 0 im lặng (không có cờ trạng thái).
* `sigma` fallback **0,25 cứng** khi thiếu dữ liệu underlying, nhưng vẫn xuất ra như sigma thật.
* IV solver bracket `[0,5%; 500%]`; khi giá CW > upper bound (giá quyền > S/n) trả `None` mà không
  nói lý do; thị trường CW VN thường xuyên có giá > intrinsic do underlying close cũ → cần trạng thái rõ ràng.
* Không có cảnh báo khi IV suy ra từ phiên không khớp (CW đứng giá, underlying chạy).

---

## 4. Logic Active / Expired — **có lỗi nghiêm trọng, âm thầm**

`step5`:

```python
status = "active" if row["_last_gd_dt"] >= today_ts else "expired"
```

`today_ts` là **ngày hôm nay**, không phải phiên giao dịch gần nhất. Hệ quả:

* Chạy pipeline **thứ Bảy/Chủ nhật** → `last_gd = thứ Sáu < hôm nay` → **toàn bộ 335 CW bị gán `expired`**.
* Chạy **trước 09:00 thứ Hai** → dữ liệu phiên cuối vẫn là thứ Sáu → toàn bộ expired.
* Cùng logic dùng ở `step1` để chọn mã refresh giá ⇒ hôm đó không refresh giá active nào.

Dashboard không có cảnh báo, chỉ hiển thị "0 CW active" → người dùng tưởng thị trường trống.

Ngoài ra: `FILTER_DATE = 2023-01-01` trong code nhưng README ghi "≥ 02/01/2024" (doc drift);
CW hết hạn không được cập nhật OHLCV (chấp nhận được, nhưng cần ghi rõ).

---

## 5. Hiệu năng pipeline

| Bước | Chi phí | Ghi chú |
|---|---|---|
| step1 template | 25 underlying × 4 năm × 50 = **5.000 mã** kiểm tra mỗi lần chạy | 10 worker, không TTL cache |
| step1 discovery | probe prefix ngoài template, ngân sách 15 phút | |
| step2 OHLCV | **1,2 s/ticker tuần tự**, `MAX_WORKERS` không dùng cho OHLCV | 335 active ≈ 7 phút; full load 5.000 mã ≈ 100 phút |
| step5 | fetch underlying full + HNX + BS cho 1.315 CW | vài phút, phần lớn là network |
| Workflow timeout | 180 phút | sát trần khi full load |
| **Tests** | **không có** | |
| **Schedule** | **đang bị comment** | không có cập nhật tự động |

Lãng phí: `bs_calculator.py` kéo theo `playwright` + `vnbond` + `curl_cffi` trong requirements
nhưng không được dùng; workflow cài dependency bằng tay thay vì `requirements.txt`
→ **drift** giữa 2 nơi (workflow thiếu `curl_cffi`, `vnbond`).

---

## 6. Các điểm cần refactor (và phương án đã triển khai)

| # | Vấn đề | Mức độ | Phương án |
|---|---|---|---|
| 1 | Dedupe theo chuỗi ngày thô, 2 định dạng ngày | **Cao** | Chuẩn hoá ngày tập trung (`cwintel/dates.py`), dedupe theo `(ticker, date)`; sửa `pipeline.py` dùng cùng hàm. |
| 2 | Mất 25,7% dữ liệu khi parse | **Cao** | Parse đa định dạng, không dùng `dayfirst` mù; backfill đủ 187.552 phiên. |
| 3 | Bỏ qua K/ratio điều chỉnh | **Cao** | Dùng `gia_th_dieu_chinh`/`tlcd_dieu_chinh` khi có; validate với `hoa_von` của Vietstock. |
| 4 | `status` sai vào cuối tuần | **Cao** | Xác định phiên chuẩn từ cache + ngày đáo hạn; không dùng "hôm nay". |
| 5 | Greeks sai đơn vị (delta, theta) | Trung bình | Module `cwintel/bs.py` là nguồn duy nhất, đơn vị VND/CW, có test. |
| 6 | `premium`, `breakeven` không so sánh được | Trung bình | Định nghĩa lại: premium hòa vốn, break-even (VND), ghi rõ công thức. |
| 7 | IV Rank trên 70 phiên | Trung bình | Backfill IV history từ chính chuỗi giá CW + underlying (vector hoá). |
| 8 | Không có tầng phân tích/khuyến nghị | — | Package `cwintel/` + artifact JSON mới cho dashboard. |
| 9 | Không có test | **Cao** | `tests/` pytest cho BS, Greeks, IV, indicators, scoring, backtest, transform. |
| 10 | Dead code, script ad-hoc hardcode ngày | Thấp | Giữ nguyên file (không xoá) nhưng đánh dấu `legacy/`; không dùng trong luồng chính. |
| 11 | `.gitignore` là UTF‑16 (git không đọc được pattern) | Thấp | Ghi lại UTF‑8 + giữ nội dung. |
| 12 | Schedule tắt | Trung bình | Bật lại cron 09:00 UTC (T2–T6) + workflow rebuild analytics riêng. |

---

## 7. Nguyên tắc triển khai (không phá pipeline)

* `pipeline.py` vẫn là **ingestion + Excel + data.json cũ**; các sửa đổi chỉ ở tầng chuẩn hoá
  (ngày, K/ratio điều chỉnh, đơn vị) và có test offline.
* Tầng phân tích mới (`cwintel/`) **chỉ đọc cache**, không gọi API ⇒ chạy lại offline bất cứ lúc nào,
  kể cả khi Vietstock/vnstock lỗi.
* Dashboard mới đọc artifact mới (`docs/data/*.json`); dashboard cũ được giữ tại `docs/legacy.html`.
* Mọi thứ chưa đủ dữ liệu hiển thị "Chưa đủ dữ liệu" — không nội suy, không hardcode giá.
* Số liệu mô phỏng (scenario, portfolio, backtest) được ghi nhãn rõ và tách khỏi số liệu thị trường thật.


## Ghi chú chuyển đổi Vnstock thế hệ 6

Mã nạp OHLCV đang được chuyển sang `Market().equity(...).ohlcv(...)` với cấu hình nguồn tập trung tại `vnstock_config.py`. Nguồn Open API chưa được chọn; không chạy ingest hay xuất bản mới cho tới khi có quyền nguồn và được kiểm tra điều khoản công bố. Vnstock thế hệ 6 hiện chưa có tuyến `bond_yield` tương đương được xác nhận; mã dùng các lớp dự phòng HNX/Trading Economics vốn đã tồn tại. Đây là ghi chú kế hoạch, chưa phải kết quả đối chiếu dữ liệu thế hệ 6.
