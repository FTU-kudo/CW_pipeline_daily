# Phương pháp phân tích CW

Tài liệu này mô tả phép tính của phần mềm, không kèm snapshot thị trường hoặc kết quả thực nghiệm lấy từ dữ liệu nhà cung cấp. Các đầu vào phải được người dùng thu thập và sử dụng đúng quyền. Không phải khuyến nghị đầu tư.

## 1. Quy ước đầu vào

- Giá CW, giá cổ phiếu cơ sở, strike `K`: đồng Việt Nam (VND).
- `n`: số chứng quyền cần để nhận một cổ phiếu; giá CW lý thuyết bằng giá quyền chọn chia `n`.
- `T`: thời gian tới đáo hạn theo ACT/365; `r`, `sigma`, IV là số thập phân theo năm.
- Dữ liệu OHLCV được chuẩn hóa theo ticker/ngày; nguồn, schema, đơn vị và timezone phải được xác minh ở adapter nguồn trước khi phân tích.
- Tham số mặc định trong `cwintel/config.py` là cấu hình phần mềm, không phải số liệu thị trường hay cam kết hiệu quả.

## 2. Black–Scholes

Với quyền chọn kiểu châu Âu, không cổ tức:

```text
d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
d2 = d1 − σ√T
C  = S·N(d1) − K·e^(−rT)·N(d2)
P  = K·e^(−rT)·N(−d2) − S·N(−d1)
CW theoretical value = option value / n
```

Greeks được tính theo các công thức giải tích, điều chỉnh tỷ lệ chuyển đổi và đơn vị hiển thị. Giá CW thị trường có thể nằm ngoài miền giá trị mà bộ giải IV chấp nhận; trường hợp đó cần trả trạng thái không hợp lệ/thiếu IV thay vì ép ra một con số.

Đây là mô hình đơn giản hóa: không tự xử lý sự kiện doanh nghiệp trong tương lai, rủi ro thanh khoản, chênh lệch mua-bán, khả năng thực thi hay rủi ro nhà phát hành. Không coi giá lý thuyết là giá giao dịch.

## 3. Biến động và chỉ báo

- Biến động lịch sử có thể được ước lượng từ log-return giá đóng cửa, annualize theo số phiên giao dịch quy định trong cấu hình.
- IV được giải ngược từ giá CW quan sát được bằng nghiệm số; cần kiểm tra giới hạn arbitrage, bước giá, tỷ lệ chuyển đổi và quy ước đơn vị trước khi diễn giải.
- RSI, MACD, moving averages, ATR và các đặc trưng chuỗi thời gian được tính cục bộ từ OHLCV đầu vào. Thay đổi provider/schema phải qua test tương thích.
- Không công bố percentile, xếp hạng, chỉ báo theo mã, số liệu backtest hay thống kê rút ra từ dữ liệu nguồn nếu quyền của nguồn/sở giao dịch chưa cho phép.

## 4. Scoring và backtest

Scoring chia tín hiệu thành các nhóm động lượng, định giá, thanh khoản, rủi ro/lợi nhuận, kỹ thuật và thời gian tới đáo hạn. Trọng số, cổng chất lượng và cách xử lý thiếu dữ liệu nằm trong `cwintel/config.py` và các module tương ứng; đây là tham số phân tích, không bảo đảm xác suất thành công.

Backtest phải dùng thông tin có sẵn tại thời điểm ra quyết định, mô phỏng thời điểm vào lệnh ở phiên sau và công khai giả định phí/khớp lệnh khi quyền dữ liệu cho phép công bố kết quả. Kết quả lịch sử không bảo đảm kết quả tương lai. Repo hiện không phát hành bảng kết quả hiệu suất dựa trên dữ liệu nguồn.

## 5. Lợi suất phi rủi ro

Mô hình cần xác định rõ tenor, ngày quan sát, đơn vị, lãi suất hiệu dụng/ghép liên tục và phương thức nội suy. Tài liệu Vnstock G6 có route bond-yield, nhưng chưa xác nhận tương đương với chuỗi HNX spot-rate/continuous-compounding đang được pipeline cũ dùng. Không thay nguồn lãi suất trước khi so sánh hợp đồng dữ liệu và quyền sử dụng.

## 6. Nguồn và quyền dữ liệu

Vnstock G6 yêu cầu chỉ rõ nguồn, không có nguồn mặc định. Tài liệu route hiện hành liệt kê hỗ trợ theo từng API; không suy ra rằng tên adapter cũ (`VCI`, `KBS`) còn được hỗ trợ hoặc rằng route của nguồn mới tương đương.

Điều khoản dữ liệu độc lập với giấy phép phần mềm. Phần CW Intelligence cũ vẫn bị khóa ở chế độ private theo `cwintel/rights.py`; luồng công khai hiện tại chỉ là snapshot Yuanta riêng biệt, không chạy các phép tính trong tài liệu này. Xem [Data rights](DATA_RIGHTS.md).
