# 🎯 CW Pipeline Daily

Pipeline tự động scrape & tổng hợp dữ liệu Chứng quyền (CW) Việt Nam.

## Luồng xử lý

```
Bước 1  →  Scrape thông tin CW từ Vietstock (2301 → nay)
Bước 2  →  Tải OHLCV lịch sử từ vnstock / KBS
Bước 3  →  Lọc CW có ngày GD cuối cùng ≥ 02/01/2024, sort theo ngày → Ticker
Bước 4  →  Xuất Excel 3 sheet vào /output
```

## Output Excel

| Sheet | Nội dung |
|---|---|
| `OHLCV` | Dữ liệu giá lịch sử, sort theo ngày → Ticker |
| `CW_Info_Active` | Thông tin CW còn giao dịch đến hôm nay |
| `CW_Info_Expired` | Thông tin CW đã đáo hạn nhưng có GD từ 2024 |

## Cách chạy

### Chạy thủ công trên GitHub Actions

1. Vào tab **Actions** → chọn workflow **CW Pipeline – YSVN**
2. Nhấn **Run workflow** → **Run workflow**
3. Sau ~2 tiếng, vào run đó → mục **Artifacts** → tải file Excel về

Hoặc file Excel cũng được commit thẳng vào thư mục `/output` trong repo.

### Tự động hàng đêm

Bỏ comment phần `schedule:` trong `.github/workflows/cw_pipeline.yml`.

## GitHub Secret cần thiết

| Secret | Mô tả |
|---|---|
| `VNSTOCK_API` | API key của tài khoản vnstock |

Thêm tại: **Settings → Secrets and variables → Actions → New repository secret**

## Cấu trúc repo

```
├── pipeline.py                        # Script chính
├── requirements.txt
├── output/                            # File Excel được lưu tại đây
│   └── CW_Pipeline_YYYYMMDD.xlsx
└── .github/
    └── workflows/
        └── cw_pipeline.yml            # GitHub Actions workflow
```
