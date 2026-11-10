# Cài đặt và chạy cục bộ

## 1. Môi trường

Vnstock được cài từ kho riêng của Vnstock, không phải PyPI-only. Dùng một virtualenv riêng, Python 3.10+; không cài generation 6 vào môi trường đang chứa generation 5.

```bash
python3 -m venv ~/.venv_6x
source ~/.venv_6x/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` ghim `vnstock==6.0.0` và `vnstock-oapi==0.1.0` cùng `--extra-index-url https://vnstocks.com/api/packages`. Nếu cần cài riêng, dùng đúng feed này theo [tài liệu cài đặt Vnstock](https://vnstocks.com/docs/vnstock/v6/cai-dat).

## 2. Quyền dữ liệu — bắt buộc trước khi tải

Chưa có nguồn Vnstock nào được chọn trong repo. Không đặt `VNSTOCK_SOURCE`, không chạy pipeline tải dữ liệu và không sử dụng khóa của người khác. Chọn nguồn sau khi tự kiểm tra điều khoản; với Open API của công ty chứng khoán, tài liệu Vnstock nói quyền nghiên cứu cá nhân không mặc nhiên cho phép chia sẻ bảng giá hay dữ liệu gốc/chuẩn hóa/phái sinh ra công chúng.

GitHub Actions hiện chỉ chạy test offline. Pipeline không còn chạy theo lịch hoặc commit cache/artifact. Dữ liệu tải về, cache, workbook và JSON mặc định ở `output/private-data/`, thư mục bị Git bỏ qua.

Chi tiết về yêu cầu chấp thuận bằng văn bản và schema record: [`DATA_RIGHTS.md`](DATA_RIGHTS.md).

## 3. Chạy pipeline riêng

Sau khi tự chọn nguồn, có tài khoản/quyền hợp lệ và cấu hình khóa trên chính máy của bạn theo tài liệu nguồn:

```bash
export VNSTOCK_SOURCE="<nguồn-bạn-đã-chọn>"
python pipeline.py
python -m cwintel.build
python scripts/serve_private_dashboard.py --port 8000
```

Mở `http://127.0.0.1:8000`. Server chỉ bind loopback, UI lấy JSON từ `output/private-data/dashboard/` và không đưa dữ liệu ra ngoài máy.

Các đường dẫn có thể đổi bằng `CW_DATA_DIR` và `CW_CACHE_DIR`. Mặc định là `output/private-data/` và `output/private-data/cache/`.

## 4. Kiểm thử

```bash
python -m pip install -r requirements-core.txt
pytest -q
```

Test suite không truy cập nhà cung cấp. `python -m cwintel.build --out docs/data` bị chặn trừ khi có `VNSTOCK_SOURCE` và record chấp thuận hiện hành, trùng nguồn trong `output/legal/data-redistribution-authorization.json` (hoặc `CW_DATA_RIGHTS_MANIFEST`).

```bash
python scripts/check_publication_rights.py --source <nguồn>
```

Script chỉ kiểm tra trường bắt buộc, nguồn và hạn hiệu lực; đây không phải ý kiến pháp lý hay xác minh hợp đồng. Chỉ người đã đọc văn bản gốc và kiểm tra chấp thuận của cả provider lẫn sở giao dịch mới được ghi nhận quyền đó. Không commit khóa, OTP, hợp đồng mật hoặc dữ liệu thị trường.

## 5. Về lịch sử phiên bản được liên kết

Trang lịch sử ghi mục `06-11-2026`, sau ngày hiện tại của phiên làm việc (04-11-2026). Đây là mục tương lai tại thời điểm rà soát; không ghim `vnstock_quant==1.0.0rc1` từ mục đó. Nó cũng không phải drop-in replacement cho mô hình định giá CW của dự án. Đánh giá package/tier và hợp đồng đầu vào-đầu ra riêng trước khi tích hợp.
