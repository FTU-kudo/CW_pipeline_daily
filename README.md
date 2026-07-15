# 🎯 CW Pipeline Daily

Pipeline tự động scrape & tổng hợp dữ liệu Chứng quyền (CW) Việt Nam. Trải nghiệm phiên bản HTML dễ sử dụng ngay **[tại đây](https://ftu-kudo.github.io/CW_pipeline_daily/)**.

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

1. Vào tab **Actions** → chọn workflow **CW Pipeline Daily**
2. Nhấn **Run workflow** → **Run workflow**
3. Sau ~2 tiếng, vào run đó → mục **Artifacts** → tải file Excel về

Hoặc file Excel cũng được commit thẳng vào thư mục `/output` trong repo.

## GitHub Secret cần thiết

| Secret | Mô tả |
|---|---|
| `VNSTOCK_API` | API key của tài khoản vnstock |

Thêm tại: **Settings → Secrets and variables → Actions → New repository secret**

## Cấu trúc repo

## Cấu trúc repo

```
├── .github/
│   └── workflows/
│       └── cw_pipeline.yml       # GitHub Actions workflow
├── docs/
│   ├── data.json
│   └── index.html
├── output/
│   ├── cache/                    # Thư mục chứa các file parquet lưu tạm
│   │   ├── ohlcv.parquet
│   │   ├── underlying.parquet
│   │   └── vietstock.parquet
│   ├── .gitkeep
│   └── cw_master.xlsx            # File Excel tổng hợp
├── README.md                     # Tài liệu hướng dẫn
├── pipeline.py                   # Script thực thi chính
└── requirements.txt              # Danh sách thư viện Python cần thiết
```
