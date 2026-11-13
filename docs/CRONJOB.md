# Chạy phân tích hằng ngày bằng cronjob.org

Trang này giải thích cách nối **cronjob.org** (hoặc bất kỳ scheduler ngoài nào: cron của
server, Google Cloud Scheduler, n8n…) vào workflow `daily_analysis.yml` để mỗi ngày nhận
báo cáo chứng quyền.

## Trước tiên: vì sao danh sách Workflows chỉ có 3 mục

GitHub chỉ liệt kê những workflow **thực sự tồn tại** trong `.github/workflows/`:

| Workflow | Nguồn |
|---|---|
| `CW Yuanta EW snapshot — publish` | `cw_pipeline.yml` — lấy snapshot, phân tích, ghi lịch sử, publish Pages |
| `CW Pipeline — offline tests` | `cw_tests.yml` — chạy test khi push/PR |
| `pages-build-deployment` | GitHub Pages **tự sinh**, không nằm trong repo |

Không có workflow nào bị ẩn hay bị xoá. Sau khi thêm `daily_analysis.yml`, mục thứ tư
`CW Yuanta — daily analysis` sẽ xuất hiện — nhưng chỉ khi file đó đã nằm trên nhánh mặc định
(`main`). Trên nhánh PR, GitHub vẫn hiển thị workflow nhưng nút "Run workflow" của
`workflow_dispatch` chỉ dùng được từ nhánh mặc định.

## Hai kiểu lịch, chọn một

### A. Lịch nội bộ GitHub (không cần cronjob.org)

Đã cấu hình sẵn trong `daily_analysis.yml`:

```yaml
schedule:
  - cron: "10 11 * * 1-5"    # 18:10 ICT, sau workflow publish 17:30 ICT
```

Đây là cách đơn giản nhất. Nhược điểm: GitHub có thể trễ vài phút tới vài chục phút khi tải
cao, và **tự tắt lịch sau 60 ngày không có commit** trên repo.

### B. cronjob.org gọi vào GitHub (chủ động, không bị tự tắt)

cronjob.org không chạy được Python, nên nó **gọi API GitHub** để kích hoạt workflow. Workflow
mới là nơi thực thi.

**Bước 1 — tạo token GitHub có quyền chạy workflow**

- Fine-grained token: repository `FTU-kudo/CW_pipeline_daily`, quyền **Actions: Read and write**.
- Hoặc classic token với scope `workflow` (hoặc `repo`).

Không cần quyền gì khác: workflow này chỉ đọc repo và chạy phân tích.

**Bước 2 — tạo job trên cronjob.org**

- **URL**: `https://api.github.com/repos/FTU-kudo/CW_pipeline_daily/actions/workflows/daily_analysis.yml/dispatches`
- **Method**: `POST`
- **Schedule**: `10 18 * * 1-5` (18:10 giờ Việt Nam, thứ Hai–thứ Sáu)
- **Headers**:
  ```
  Authorization: Bearer <TOKEN>
  Accept: application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28
  Content-Type: application/json
  ```
- **Body**:
  ```json
  {"ref": "main", "inputs": {"notify": "summary", "max_age_hours": "36"}}
  ```

GitHub trả **204 No Content** khi nhận thành công. Đó là "đã xếp hàng", **không** phải "đã
phân tích xong" — muốn xem kết quả thì mở trang Actions, hoặc dùng API kiểm tra lần chạy.

**Bước 3 — (tuỳ chọn) kiểm tra kết quả bằng API**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://api.github.com/repos/FTU-kudo/CW_pipeline_daily/actions/workflows/daily_analysis.yml/runs?per_page=1" \
  | python -c "import json,sys; r=json.load(sys.stdin)['workflow_runs'][0]; \
print(r['status'], r['conclusion'], r['html_url'])"
```

`conclusion` là `failure` khi báo cáo phát hiện **dữ liệu cũ hơn ngưỡng** (exit code 3) — đó
là tín hiệu có chủ đích, không phải lỗi hạ tầng: nó nghĩa là workflow publish đã không cập
nhật snapshot.

## `notify` chọn gì

| Giá trị | Kết quả |
|---|---|
| `summary` (mặc định) | Báo cáo gọn: tổng quan, top 10 thanh khoản, trong phiên, trần–sàn, liên tục, lịch sử |
| `full` | Như trên, kèm bảng chi tiết mã không giao dịch |
| `json` | Toàn bộ dữ liệu máy đọc được, để đẩy sang nơi khác |

Báo cáo luôn được ghi vào **Summary** của lần chạy (mở trang Actions là đọc được) và upload
làm artifact 30 ngày.

## Chạy tại máy, không cần GitHub

Cùng một script, chạy trực tiếp:

```bash
python -m pip install -r requirements-core.txt

# Báo cáo gọn ra màn hình (đọc từ dữ liệu đã publish trong repo)
python scripts/daily_analysis_report.py --summary

# Đầy đủ, ghi ra file
python scripts/daily_analysis_report.py --out report/cw-$(date +%F).md

# Dạng JSON cho hệ thống khác
python scripts/daily_analysis_report.py --format json

# Lấy dữ liệu mới rồi mới phân tích (cần mạng tới Yuanta)
python scripts/fetch_yuanta_snapshot.py \
  && python scripts/analyze_yuanta_warrants.py --offline docs/data/yuanta_snapshot.json \
  && python scripts/backfill_yuanta_history.py --offline \
  && python scripts/daily_analysis_report.py --summary
```

Cron trên Linux:

```cron
10 18 * * 1-5 cd /duong/dan/CW_pipeline_daily && \
  /usr/bin/python3 scripts/daily_analysis_report.py --summary \
  >> /var/log/cw-daily.log 2>&1
```

## Vì sao workflow phân tích không tự lấy dữ liệu

Tách đôi như vậy là có chủ đích:

- **`publish` lấy dữ liệu** — một request duy nhất tới Yuanta, có thử lại, có kiểm tra chất
  lượng, và ghi lịch sử. Đây là nơi duy nhất chạm mạng.
- **`daily analysis` đọc dữ liệu đã publish** — không mạng, không thể thất bại vì WAF, không
  tạo ra bar giả. Nếu nó chạy lúc 18:10 sau khi publish lúc 17:30, dữ liệu đã sẵn sàng.

Nếu cho workflow phân tích tự gọi API, một lần WAF chặn sẽ làm cả hai cùng đỏ, và tệ hơn: nó
có thể ghi một snapshot rỗng vào lịch sử. Tách ra thì lần chạy phân tích hoặc phản ánh dữ
liệu thật, hoặc báo "dữ liệu cũ" — cả hai đều là thông tin đúng.

## Những gì báo cáo KHÔNG có

Định giá, Greeks, IV, điểm số, khuyến nghị, backtest. Endpoint `stock_type=EW` của Yuanta
không có strike, hạn mức, ngày đáo hạn, giá cổ phiếu cơ sở hay chuỗi quá khứ, nên không thể
tính các chỉ tiêu đó. Chi tiết: `scripts/check_cw_analytics_bridge.py`.
