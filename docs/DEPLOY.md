# Hướng dẫn cài đặt & triển khai

## 1. Yêu cầu

- Python 3.11+
- ~2 GB RAM trống, ~1 GB đĩa cho cache + artifact
- Không cần database, không cần server

Thư viện (`requirements.txt`): pandas, numpy, pyarrow, openpyxl, requests, beautifulsoup4, pytz, playwright (chỉ pipeline gốc), pytest.

## 2. Cài đặt cục bộ

```powershell
git clone https://github.com/FTU-kudo/CW_pipeline_daily.git
cd CW_pipeline_daily
# Windows PowerShell: inspect an existing Vnstock 6 environment before using it
if (Test-Path "$HOME\.venv_6x\Scripts\python.exe") {
    & "$HOME\.venv_6x\Scripts\python.exe" -m pip show vnstock vnstock-oapi
} else {
    py -m venv "$HOME\.venv_6x"
}
```

Nếu môi trường đã tồn tại, kiểm tra kết quả trước khi cài; dừng nếu đang chứa thế hệ khác. Chỉ khi môi trường mới hoặc đã là thế hệ 6 mới chạy:

```powershell
& "$HOME\.venv_6x\Scripts\python.exe" -m pip install -r requirements.txt
```

## 3. Cập nhật dữ liệu

### 3.1 Chỉ dựng lại artifact phân tích (dùng cache có sẵn)

```bash
python -m cwintel.build                      # ~250 s, ghi docs/data/
python -m cwintel.build --no-backtest        # bỏ backtest, nhanh hơn ~90 s
python -m cwintel.build --asof 2026-10-31    # dựng đúng một phiên
python -m cwintel.build --out /tmp/cwdata    # đích khác
```

### 3.2 Cập nhật dữ liệu gốc từ nguồn

```bash
# Chọn nguồn sau khi có tài khoản/khóa ở nguồn đó; không dùng tên VCI/KBS cũ.
$env:VNSTOCK_SOURCE = "<nguồn-bạn-chọn>"
& "$HOME\.venv_6x\Scripts\python.exe" pipeline.py
```

Pipeline gốc mất 1–2 giờ (playwright). Sau đó chạy `python -m cwintel.build` để cập nhật dashboard mới.

> **Không commit khóa.** Khóa tài khoản Vnstock và khóa nguồn là hai loại riêng.
> Lưu khóa nguồn bằng `vnstock keys set <nguồn>` trong Terminal của bạn; không đưa vào mã hay Git.
> Cấu hình nguồn duy nhất nằm ở `vnstock_config.py` / `VNSTOCK_SOURCE`.

## 4. Chạy dashboard cục bộ

```bash
python -m http.server 8000 --directory docs
# http://localhost:8000
```

Bắt buộc dùng web server: `fetch('data/*.json')` bị chặn bởi CORS khi mở `file://`.

## 5. GitHub Pages

1. Repo → **Settings → Pages**
2. Source: **Deploy from a branch** → Branch `main`, folder `/docs`
3. Truy cập `https://<user>.github.io/CW_pipeline_daily/`

Dashboard cũ vẫn ở `/legacy.html`, dữ liệu cũ ở `/data.json`.

## 6. GitHub Actions

### 6.1 Workflow gốc — `cw_pipeline.yml`

Chạy pipeline scrape/tải (hiện schedule đang comment). Có thể bật:

```yaml
on:
  schedule:
    - cron: "0 9 * * 1-5"     # 16:00 ICT, T2–T6
```

Generation 6 cần biến Actions `VNSTOCK_SOURCE` sau khi bạn chọn nguồn và khóa tài khoản Vnstock trong secret `VNSTOCK_API` (được ánh xạ sang `VNSTOCK_API_KEY`). Cấu hình khóa API của chính nguồn phải theo hướng dẫn nguồn đã chọn; chưa chọn nguồn thì không chạy workflow.

### 6.2 Workflow CW Intelligence — `cw_intelligence.yml`

- Chạy `pytest -q` (chặn merge nếu test fail)
- Chạy `python -m cwintel.build`
- Commit `docs/data/**` nếu có thay đổi
- Upload artifact JSON (dự phòng)
- Trigger: push lên `main`, `workflow_dispatch`, schedule 10:30 UTC (17:30 ICT)

Không cần secret nào (chỉ đọc cache đã commit).

### 6.3 Bảo mật

- `permissions: contents: write` chỉ trong workflow commit dữ liệu.
- Không in token ra log.
- Không dùng `pull_request_target` cho workflow có quyền ghi.
- Dữ liệu người dùng (watchlist/danh mục) chỉ nằm trong `localStorage`.

## 7. Kiểm tra sau triển khai

```bash
pytest -q                                    # phải xanh
python -c "import json;m=json.load(open('docs/data/meta.json'));print(m['asof'],m['buildSeconds'],m['universe'])"
```

Checklist thủ công trên dashboard:

- [ ] Tổng quan hiển thị đúng phiên dữ liệu (không phải hôm nay nếu chưa cập nhật)
- [ ] Screener lọc 2 điều kiện AND/OR, xuất CSV
- [ ] Heatmap đổi màu/kích thước/nhóm, nhấp mở chi tiết
- [ ] Chi tiết CW: nến + RSI + MACD + kịch bản + so sánh cùng cơ sở
- [ ] Khuyến nghị: mở card, xem lý do, kế hoạch hoặc "Chưa đủ dữ liệu"
- [ ] Backtest: đường vốn, độ nhạy, bảng lệnh, caveats
- [ ] Watchlist/danh mục lưu sau khi tải lại trang
- [ ] Chất lượng dữ liệu: 16 kiểm tra, 0 lỗi

## 8. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Trang trắng, "Không tải được dữ liệu" | Mở bằng `file://` hoặc thiếu `docs/data` | Chạy web server; chạy `python -m cwintel.build` |
| `ModuleNotFoundError: cwintel` | Chạy ngoài thư mục repo | `cd` vào repo hoặc `PYTHONPATH=.` |
| Build lỗi `KeyError` ở quality | Thiếu tệp cache | Chạy `pipeline.py` để tạo `output/cache` |
| Dashboard báo dữ liệu cũ | `dataAgeDays > 3` | Chạy lại pipeline + build |
| Biểu đồ trống | Thiếu series cho mã đó (CW đáo hạn lâu) | Bình thường — UI báo "không có chuỗi giá" |
| `ImportError: numpy has no erf` | numpy ≥ 2.4 | Đã xử lý bằng `math.erfc` (`cwintel/bs.py`) |

## 9. Chi phí

| Thành phần | Chi phí |
|---|---|
| GitHub Actions (public repo) | 0 |
| GitHub Pages (public repo) | 0 |
| Lưu trữ artifact 13–24 MB | 0 (trong repo) |
| Nguồn dữ liệu | Vietstock/vnstock theo gói của người dùng |

Tổng: **0 đồng** cho hạ tầng, miễn là repo public và dung lượng artifact trong giới hạn Pages (1 GB khuyến nghị).
