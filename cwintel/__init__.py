"""CW Intelligence — Professional Covered Warrant Analytics.

Package này là tầng phân tích định lượng thuần offline cho thị trường chứng quyền
Việt Nam. Nó chỉ đọc cache parquet do `pipeline.py` tạo ra, không gọi mạng, nên có
thể chạy lại bất cứ lúc nào và kết quả tái lập được.

Quy ước đơn vị (dùng xuyên suốt package):
    * Giá CW / giá cổ phiếu cơ sở : VND (cache lưu nghìn VND, được nhân 1_000 khi nạp)
    * Giá thực hiện (strike)       : VND
    * ratio (tỷ lệ chuyển đổi n)   : số CW cần để nhận 1 cổ phiếu (CW price = option / n)
    * T                            : năm, ACT/365, đo từ ngày as-of tới ngày đáo hạn
    * r, sigma, IV                 : thập phân/năm (0.05 = 5%)
    * Delta                        : cổ phiếu quy đổi **trên 1 CW** = N(d1)/n
    * Theta                        : VND / CW / ngày lịch
    * Vega                         : VND / CW / 1 điểm vol (1%)
    * Gamma                        : cổ phiếu / VND
"""

__version__ = "1.0.0"
METHODOLOGY_VERSION = "1.1.0"

from . import config  # noqa: F401,E402
