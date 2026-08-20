# Nhật ký Cập nhật & Bảo trì (HANDOFF)
**Ngày tạo:** 19/08/2026 (Cập nhật lúc 18:43 ICT)
**Dự án:** Covered Warrant Analytics Pipeline (`CW_pipeline_daily`)
**Thực hiện bởi:** VNAI (Google Antigravity Agent)

---

## 1. Khắc phục lỗi Timeout 3 tiếng trên GitHub Actions (Từ 17/08/2026)
- **Vấn đề:** Các phiên chạy GitHub Actions bị treo liên tục quá giới hạn 3 tiếng. Nguyên nhân cốt lõi là do API của nguồn VCI (thông qua thư viện `vnstock`) bị sập/chặn request, khiến lệnh gọi mạng bị treo vĩnh viễn không phản hồi.
- **Giải pháp đã triển khai:**
  - **Áp dụng Hard-cap Timeout:** Sử dụng `concurrent.futures.ThreadPoolExecutor(timeout=25)` ở tất cả các hàm gọi API ra bên ngoài (đặc biệt là bước tải OHLCV và giá tài sản cơ sở). Đảm bảo pipeline không bao giờ bị kẹt quá 25s cho một lệnh gọi.
  - **Cơ chế Cầu dao tự động (Circuit Breaker):** Thiết lập logic thông minh đếm số lần timeout. Nếu VCI bị treo liên tiếp 6 lần (`CIRCUIT_OPEN_AFTER = 6`), hệ thống sẽ "gạt cầu dao", bỏ qua hoàn toàn VCI trong các lần gọi tiếp theo và chuyển hướng toàn bộ request sang nguồn dự phòng là `KBS` để đảm bảo thời gian chạy Github Actions được tối ưu nhất (giảm từ 3h xuống còn ~5 phút).

## 2. Khắc phục lỗi "Mất tích 6 mã CW mới niêm yết" (Trên bảng điện hiển thị 322 thay vì 328)
- **Vấn đề:** 6 mã CW mới lên sàn (giao dịch từ 14/08) bị biến mất khỏi bảng điện (dashboard). Dù đã giao dịch 3 ngày nhưng trên bảng điện vẫn không thấy tăm hơi.
- **Nguyên nhân cốt lõi:**
  - Nguồn VCI cập nhật (index) các mã CW mới rất chậm. Khi pipeline gọi API VCI cho 6 mã này, VCI không báo lỗi nhưng trả về bảng dữ liệu rỗng (không có dòng nào).
  - Khối mã cũ mặc định coi "Dữ liệu rỗng từ VCI" = "Mã này chưa có dữ liệu", sau đó bỏ qua và xóa hoàn toàn 6 mã này khỏi danh sách hợp lệ, bất chấp việc nguồn `KBS` có khả năng cung cấp đầy đủ dữ liệu lịch sử.
- **Giải pháp đã triển khai:**
  - **Dự phòng dữ liệu (Fallback to KBS):** Cập nhật hàm `fetch_one`, bổ sung luồng xử lý: Nếu VCI trả về DataFrame rỗng, script sẽ lập tức gọi sang KBS để lấy dữ liệu. Nhờ vậy, 6 mã mới đã lấy lại được chuỗi dữ liệu giao dịch 3 ngày vừa qua.
  - **Bảo hiểm dữ liệu giá (Zero-OHLCV Fallback):** Thêm tính năng "ép" các mã siêu mới (chưa có bất kỳ lịch sử giao dịch nào từ cả VCI lẫn KBS) vẫn phải xuất hiện trên bảng điện. Thay vì bị lọc bỏ ở `step3_filter`, chúng sẽ được giữ lại, và mức giá tham chiếu của chúng (`price_cw`) sẽ được gán bằng cột giá cập nhật live (`gia_hien_tai`) đã được lấy từ Step 1, đảm bảo mô hình định giá Black-Scholes tiếp tục hoạt động mượt mà thay vì báo lỗi chia cho 0.

## 3. Quản lý Git & Triển khai liên tục (CI/CD)
- **Vấn đề:** Ban đầu Agent không thể tự động Git Push qua chế độ chạy nền do thiếu môi trường xác thực (Git Credential Manager) của hệ điều hành.
- **Giải pháp:** Tận dụng phiên đăng nhập (login session) và lưu cấu hình credential thông qua lệnh Terminal thủ công từ người dùng, Agent đã đồng bộ thành công khoá xác thực.
- **Kết quả:** Đã tự động hóa thành công toàn bộ quá trình Commit, Rebase và Push (`git pull --rebase` & `git push`) trực tiếp các bản vá lên repository `https://github.com/FTU-kudo/CW_pipeline_daily` cho cả 2 luồng fix bug lớn nêu trên.

---

## 4. Tối ưu hoá Rate Limit, khôi phục dữ liệu CW 2023 & Sửa luồng GitHub Actions
*Thời gian thực hiện: 20/08/2026 (Hoàn tất lúc 00:30 ICT)*

- **Xử lý giới hạn tần suất API (Rate Limit 429):**
  - **Vấn đề:** Phiên bản cũ chạy quá nhanh khiến API của Vietstock/VCI khóa IP hoặc phản hồi lỗi 429 ("too many requests" đối với tài khoản Community giới hạn 60 request/phút), dẫn tới việc GitHub Actions chờ vô hạn vì bị kẹt trong vòng lặp thử lại.
  - **Vấn đề:** Phiên bản cũ chạy quá nhanh khiến API của Vietstock/VCI khóa IP hoặc phản hồi lỗi 429 ("too many requests" đối với tài khoản Community giới hạn 60 request/min), dẫn tới việc GitHub Actions chờ vô hạn vì bị kẹt trong vòng lặp thử lại.
  - **Giải pháp:** Chỉnh sửa độ trễ `REQUEST_DELAY = 1.2` (duy trì 50 request/phút) để đảm bảo luôn ở dưới ngưỡng 60 req/min. Cải tiến logic đọc trực tiếp số giây phạt chờ từ message lỗi để sleep chuẩn xác thay vì đoán bừa. Bổ sung script thủ công `patch_ohlcv.py` chuyên tải bù hàng chục ngàn dòng lịch sử cho toàn bộ các mã CW từ trước tới nay.

- **Khôi phục toàn bộ CW từ đầu năm 2023:**
  - **Vấn đề:** Ban đầu người dùng yêu cầu lấy tất cả chứng quyền (hơn 1.000 mã), đặc biệt là nhóm CW năm 2023 (bắt đầu bằng `CACB2301`, v.v.), nhưng trên bảng điện vẫn không thấy.
  - **Giải pháp:** Kiểm tra thì phát hiện hàm `step3_filter` bị kẹp điều kiện cứng `FILTER_DATE = date(2024, 1, 2)`, vô tình lọc bỏ toàn bộ mã 2023 khỏi báo cáo cuối cùng dù kho lưu trữ OHLCV đã có đầy đủ. Đã đổi thành `date(2023, 1, 1)` và biến `OHLCV_START_DATE = "2023-01-01"` để tương thích hoàn toàn.

- **Sửa lỗi Workflow "Unstaged Changes" (Exit Code 128):**
  - **Vấn đề:** Khi Github Action cố gắng kéo code từ trên mạng về qua lệnh `git pull --rebase`, nó vướng phải các file dữ liệu mà pipeline vừa ghi ra (`data.json`, `cw_master.xlsx`) nên báo lỗi unstaged và từ chối đồng bộ.
  - **Giải pháp:** Thêm cờ `--autostash` thành `git pull --rebase --autostash` ở cả 2 bước commit trong file `.github/workflows/cw_pipeline.yml`. Cờ này có tác dụng cất các file bị sửa dở sang một bên tạm thời, tải toàn bộ thay đổi mới từ repository, sau đó tự động trả lại các file bị dở dang. Workflow đã hết lỗi và đồng bộ mượt mà.

---

## 5. Sửa lỗi Circuit Breaker gây hiệu ứng Domino (20/08/2026)
*Thời gian thực hiện: 20/08/2026 (Hoàn tất lúc 23:55 ICT)*

**Triệu chứng:** Pipeline chạy THÀNH CÔNG (exit 0, 19 phút) nhưng **không có phiên GD nào được cập nhật** vào ngày 20/08/2026. Log báo `Ket qua: OK=0 | NO_NEW=1207 | FAIL=2`. Dashboard vẫn hiển thị dữ liệu cũ đến 19/08/2026.

- **Nguyên nhân cốt lõi — Hiệu ứng Domino (Domino Circuit Breaker):**
  - 2 CW đầu tiên (`CACB2301`, `CACB2302`) bị timeout liên tiếp trên cả VCI lẫn KBS, khiến cả 2 circuit breaker đồng thời bật trạng thái OPEN.
  - Khi cả 2 circuit OPEN, hàm `fetch_one` trả về `pd.DataFrame()` (rỗng) thay vì `None`. Điều này bị vòng lặp đếm vào `n_empty` (NO_NEW) chứ không phải `failed`.
  - Hậu quả: 1207 CW còn lại **đều bị skip hoàn toàn trong im lặng**. Pipeline không phát hiện đây là lỗi nghiêm trọng, tiếp tục lưu cache cũ, và in ra kết quả thành công giả.

- **4 Fix đã triển khai trong `pipeline.py`:**
  1. **Fix #1 — Sửa return type khi cả 2 circuit OPEN:** Thay `return pd.DataFrame()` bằng `return None` → vòng lặp nhận diện đây là lỗi thực sự (FAIL), không phải NO_NEW. Đồng thời tách logic: nếu VCI open nhưng KBS vẫn ổn → thử KBS bình thường trước khi báo FAIL.
  2. **Fix #2 — Tách ngưỡng VCI và KBS:** `VCI_CIRCUIT_OPEN_AFTER = 6` (giữ nguyên) vs `KBS_CIRCUIT_OPEN_AFTER = 12` (tăng gấp đôi). Ngưỡng KBS cao hơn vì KBS là nguồn fallback — cần kiên nhẫn hơn trước khi từ bỏ.
  3. **Fix #3 — Soft Circuit Reset:** Thêm biến `_consecutive_ok` đếm số CW thành công liên tiếp. Sau 10 lần thành công liên tiếp, reset cả 2 circuit về trạng thái đóng để tránh hiệu ứng "oan hồn" (circuit bật do 2 CW đầu nhưng giữ trạng thái mãi mãi dù API đã phục hồi). Đồng thời reset `_kbs_circuit` khi bắt đầu vòng lặp fetch mới.
  4. **Fix #4 — NO_NEW Storm Guard:** Thêm cảnh báo và early-exit không lưu cache khi `n_ok == 0` và `n_empty > 70%` tổng CW cần fetch. Hành vi này bảo toàn cache cũ và force retry ở lần chạy tiếp theo thay vì ghi đè cache bằng kết quả rỗng.
