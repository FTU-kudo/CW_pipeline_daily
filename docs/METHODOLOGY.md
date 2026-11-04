# Phương pháp định lượng — CW Intelligence 1.0.0

Tài liệu này giải thích **chính xác** hệ thống tính gì, công thức nào, đơn vị nào, giả định nào và chỗ nào có thể sai. Mọi con số trên dashboard đều truy vết được về đây.

---

## 1. Quy ước thị trường Việt Nam

| Khái niệm | Quy ước |
|---|---|
| Loại quyền | Châu Âu, thanh toán tiền mặt khi đáo hạn |
| Tỷ lệ chuyển đổi | *n*:1 — cần *n* CW để nhận 1 cổ phiếu |
| Đơn vị giá CW | VND / 1 CW |
| Đơn vị giá cổ phiếu | VND / 1 cổ phiếu |
| Điều khoản | Dùng **strike & ratio đã điều chỉnh** (`terms_adjusted`) khi có cổ tức/thưởng |
| Cổ tức | Không trừ thêm trong mô hình (đã nằm trong K, n điều chỉnh) |
| Lãi suất | Lợi suất TPCP 10Y tại ngày dữ liệu (HNX/VBMA); fallback 4,44% |
| Thời gian | ACT/365, T = DTE/365 |

### 1.1 Vì sao phải dùng strike điều chỉnh

Dùng strike gốc làm break-even lệch **trung vị 811 VND** trên dữ liệu lịch sử (xem `AUDIT.md`). Sau khi dùng strike/tỷ lệ điều chỉnh, sai số trung vị còn **0,4 VND** khi đối chiếu với break-even do Vietstock công bố (474 CW kiểm tra). Đây là kiểm chứng thực nghiệm rằng quy ước tính là đúng.

---

## 2. Công thức

### 2.1 Giá trị CW

```
d1 = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
d2 = d1 − σ·√T
C  = S·N(d1) − K·e^(−rT)·N(d2)
P_CW = max(C, intrinsic) / n
intrinsic = max(S − K, 0)/n
time value = P_CW − intrinsic
```

### 2.2 Greeks (đơn vị / 1 CW)

| Greek | Công thức | Đơn vị |
|---|---|---|
| Delta | N(d1)/n | số cổ phiếu quy đổi / CW |
| Gamma | φ(d1) / (S·σ·√T·n) | 1/VND |
| Vega | S·φ(d1)·√T / 100 / n | VND/CW cho 1 điểm σ (1%) |
| Theta | [−S·φ(d1)·σ/(2√T) − r·K·e^(−rT)·N(d2)] / 365 / n | VND/CW/ngày lịch |
| Rho | K·T·e^(−rT)·N(d2) / 100 / n | VND/CW cho 1% lãi suất |

**Delta tuỳ chọn** (hiển thị trên UI) = N(d1), tức delta của quyền trên 1 cổ phiếu — dùng để so sánh moneyness; **delta CW** = N(d1)/n là số cổ phiếu thực nhận khi giá CW thay đổi 1 VND.

### 2.3 Định giá tương đối

```
Premium hoà vốn = (K + P_CW·n)/S − 1          [%]
Breakeven       = K + P_CW·n                   [VND]
Gearing gộp     = S / (P_CW·n)
Gearing hiệu dụng = gearing gộp × N(d1)
```

**IV residual** — so IV của CW với *đường cong biến động của các CW cùng cổ phiếu cơ sở*:

```
z    = ln(K/S) / √T
IV_smile = a + b·z      (hồi quy tuyến tính theo nhóm cùng underlying)
IV_resid = IV / IV_smile − 1
```

Nếu R² < 0,15 hoặc <5 quan sát → dùng kernel Gaussian theo moneyness (băng thông IQR); nếu <3 quan sát → trung vị nhóm. Lý do: CW deep OTM luôn có IV cao hơn ATM, so trung vị thô sẽ sai.

`FV_smile` = BS với `IV_smile` (giá trị CW nếu giao dịch đúng đường cong nhóm). `FV_HV` = BS với biến động lịch sử. **Không dùng FV_HV làm tín hiệu mua** (xem §5).

### 2.4 Biến động lịch sử

```
σ_HV = std(log returns, N phiên) × √252     (ddof = 1)
Ưu tiên: HV252 → HV60 → HV20 → fallback 0,35
```

### 2.5 IV suy ra

Bisection trên [1e-4, 5,0], sai số 1e-7, tối đa 200 vòng; Newton khởi tạo. Kiểm tra arbitrage: giá < intrinsic − 1 VND → không có IV; giá ≥ S/n → không hợp lệ. Chấp nhận dung sai 1 VND cho bước giá và làm tròn nghìn VND.

Kiểm chứng: round-trip IV trên 3 tỷ lệ và 5 mức moneyness, sai số < 1e-5 (xem `tests/test_bs.py`).

---

## 3. CW Score (0–100)

### 3.1 Công thức tổng

```
Score = Σ (w_i · s_i · c_i) / Σ (w_i · c_i)
```

- `s_i` ∈ [0, 100]: điểm thành phần
- `c_i` ∈ [0, 1]: **độ tin cậy** — tỷ lệ trọng số của các tiêu chí con thực sự có dữ liệu (và, với thành phần kỹ thuật, bị nhân thêm `min(sessions/30, 1)`)
- `w_i`: trọng số dưới đây

CW thiếu dữ liệu vì thế **không bị điểm 0 oan** — chỉ giảm độ tin cậy và bị cổng chất lượng xử lý.

### 3.2 Trọng số và cách đo

| Thành phần | w | Chi tiết |
|---|---|---|
| `underlying_momentum` | 25% | 40% percentile return 21 phiên + 20% percentile return 63 phiên + 20% trend (trên MA20/MA50) + 15% dải RSI cơ sở + 5% khoảng cách đỉnh 60 phiên. **Percentile tính trên các underlying duy nhất**, không theo số CW. |
| `valuation` | 20% | 30% percentile premium trong cùng cơ sở + 30% percentile IV residual trong cùng cơ sở + 15% percentile IV−HV + 10% percentile FV smile upside + 5% IV rank + 10% dải delta (ưu tiên 0,30–0,70; phạt <0,15 hoặc >0,85). |
| `liquidity` | 15% | 50% percentile log(GT TB 20 phiên) + 25% % phiên có giao dịch + 25% percentile tăng tốc khối lượng. |
| `risk_reward` | 20% | 30% dải theta/ngày + 25% dải khoảng cách hoà vốn + 25% dải DTE + 10% dải biến động (ưu tiên vùng 40–65 percentile) + 10% dải gearing hiệu dụng. |
| `technical` | 10% | 30% dải RSI CW + 20% MACD histogram + 10% độ dốc MACD + 20% trên MA20 + 10% trên MA50 + 10% breakout 20 phiên. |
| `time_to_maturity` | 10% | Dải DTE: 45–180 ngày = 100; 180–270 = 80; 30–45 = 70; 270–365 = 55; 21–30 = 40; 14–21 = 20; <14 = 5; >365 = 35. |

Tất cả percentile dùng mid-rank (`method="average", pct=True`), NaN giữ NaN.

### 3.3 Chất lượng dữ liệu (DQ, 0–1)

```
DQ = 0,25·terms_valid + 0,15·σ có nguồn thật + 0,15·(tuổi giá ≤ 3 phiên)
   + 0,15·min(sessions/60,1) + 0,10·min(u_sessions/120,1)
   + 0,10·(IV có) + 0,10·tỷ lệ phiên có giao dịch
```

DQ < 0,45 → **NO_DATA**, không khuyến nghị hành động.

---

## 4. Ngưỡng & cổng chất lượng

| Ngưỡng điểm | Nhãn |
|---|---|
| 80–100 | MUA MẠNH (STRONG_BUY) |
| 65–79 | MUA (BUY) |
| 45–64 | THEO DÕI (HOLD) |
| 30–44 | TRÁNH (AVOID) |
| 0–29 | RỦI RO CAO (HIGH_RISK) |

Ngưỡng được áp **tăng dần** (lỗi cũ áp giảm dần khiến toàn bộ 331 mã thành HIGH_RISK — đã có test hồi quy).

### 4.1 Cổng bắt buộc

| Cổng | MUA MẠNH | MUA |
|---|---|---|
| Điểm thanh khoản tối thiểu | 60 | 40 |
| DQ tối thiểu | 0,80 | 0,65 |
| DTE tối thiểu | 21 ngày | 14 ngày |
| GT giao dịch TB 20 phiên | 50 triệu | 10 triệu |
| IV − HV tối đa | +40% | +60% |
| Số phiên lịch sử tối thiểu | 15 | 10 |

Vi phạm → hạ xuống một bậc **và ghi lý do** vào `rec_reason` (ví dụ "Hạ từ MUA MẠNH do lịch sử giao dịch quá ngắn"). Nếu vi phạm tiếp cổng của bậc dưới, hạ tiếp. Không bao giờ tự động nâng hạng.

Cổng IV được thêm sau khi nghiên cứu bộ lọc (xem §6.4): chỉ CW có IV ≤ HV mới có kỳ vọng dương mỗi lệnh.

### 4.2 Kế hoạch giao dịch

```
ATR  = ATR(14)                              (nếu thiếu: giá × std(ret1, 20 phiên))
Vùng vào lệnh = [giá − 0,5·ATR, giá + 0,25·ATR]
Stop-loss     = max(giá − 2·ATR, 10 VND)
Take-profit   = BS(S·1,05, T − 10/365, σ) và BS(S·1,10, T − 20/365, σ)
Giữ dự kiến   = clamp(DTE − 15, 5, 60) phiên
R:R           = (TP1 − giá) / (giá − stop)
```

Điều kiện: cần giá, ATR (hoặc ret_std20), DTE ≥ 21, đủ điều khoản. Nếu thiếu → `{available: false, reason}` và UI hiển thị **"Chưa đủ dữ liệu"**. Không bịa giá mục tiêu.

---

## 5. Những gì hệ thống **không** làm

1. **Không dùng BS@HV làm tín hiệu mua.** Trên dữ liệu Việt Nam, gần như toàn bộ CW giao dịch trên giá trị BS theo HV (chênh lệch dương hệ thống). Một chiến lược "mua khi giá < FV_HV" sẽ mua gần như toàn bộ thị trường và thua lỗ.
2. **Không coi giá trị lý thuyết là giá có thể giao dịch.** Chênh lệch phản ánh IV, thanh khoản, cung cầu và rủi ro TCPH.
3. **Không dự báo giá.** Kịch bản là phép tính "nếu cơ sở thay đổi X%, σ = Y, giữ Z phiên thì giá CW *lý thuyết* là bao nhiêu" — không phải mục tiêu.
4. **Không tạo khuyến nghị khi thiếu dữ liệu.** DQ thấp → NO_DATA; thiếu ATR → không có kế hoạch.
5. **Không giấu kết quả xấu.** Xem §6.

---

## 6. Backtest

### 6.1 Thiết kế

- **Walk-forward**: chấm điểm tại ngày T bằng dữ liệu ≤ T, vào lệnh tại **giá đóng cửa phiên kế tiếp** T+1.
- Tái cấu trúc mỗi 20 phiên, nắm giữ 20 phiên (không chồng lấn).
- Vũ trụ: CW còn giao dịch, DTE ≥ 30, GT TB 20 phiên ≥ 10 triệu, DQ ≥ 0,60, ≥20 phiên lịch sử.
- Chọn top-5 theo Score, trần 40% mỗi TCPH.
- **Chi phí**: 0,50% nửa chênh lệch bid-ask + 0,15% phí + 0,30% trượt giá = **0,95%/chiều**.
- **Stop/TP**: stop = −2 ATR, TP = +2R, kiểm tra trong từng phiên bằng high/low.
- **Đáo hạn**: nếu CW hết hạn trong thời gian nắm giữ → thoát tại giá trị nội tại (có thể = 0).
- **Không survivorship bias**: vũ trụ tại mỗi ngày chỉ gồm CW đã niêm yết và còn giao dịch tại ngày đó, kể cả mã sau này đáo hạn vô giá trị.
- Benchmark: toàn vũ trụ EW, ngẫu nhiên, cổ phiếu cơ sở EW.

### 6.2 Kết quả (06/2023 → 11/2026)

| Chiến lược | Tổng LN | CAGR | Vol | Sharpe | MDD | % kỳ dương |
|---|---|---|---|---|---|---|
| Top-5 Score | −91,1% | −50,8% | 67,5% | −0,75 | −92,4% | 41,9% |
| Toàn vũ trụ EW | −95,0% | −58,5% | 43,0% | −1,85 | −94,9% | 30,2% |
| Ngẫu nhiên | −96,4% | −62,3% | 52,5% | −1,61 | −96,3% | — |
| Cổ phiếu cơ sở EW | +44,9% | — | — | 0,44 | −20,3% | — |

Chi tiết lệnh: 215 lệnh, win 47,4%, TB −2,96%/lệnh, trung vị −7,2%, PF 0,78, stop 46,0%, TP 44,2%, giữ TB 7,3 phiên.

### 6.3 Độ nhạy

| Thay đổi | Kết quả |
|---|---|
| Giữ 5 / 10 / 20 phiên | −74,8% / −83,0% / −87,8% tổng |
| Ngưỡng điểm 45 / 65 / 80 | −87,8% / −87,5% / −43,8% |
| Chi phí 0,5% / 1% / 2% mỗi chiều | TB/lệnh −2,06% / −3,06% / −5,06% |

### 6.4 Bộ lọc — phát hiện quan trọng

| Bộ lọc | n | TB/lệnh | Win | PF | Tổng |
|---|---|---|---|---|---|
| Baseline (top-5 Score) | 215 | −2,96% | 47,4% | 0,78 | −87,8% |
| **IV ≤ HV** | 56 | **+0,27%** | **58,9%** | **1,02** | −86,0% |
| **IV ≤ HV và cơ sở trên MA50** | 44 | **+1,17%** | **61,4%** | **1,09** | −61,7% |
| IV residual ≤ 0 | 69 | −4,46% | 45,1% | 0,70 | −93,8% |
| Cơ sở trên MA50 | 171 | −3,61% | 47,6% | 0,73 | −86,9% |
| Điểm ≥ 80 | 127 | −0,63% | 52,8% | 0,95 | −33,7% |

Kết luận: **điểm cao một mình không đủ**; điều kiện "không trả giá biến động cao hơn biến động thực tế" mới tạo kỳ vọng dương. Vì vậy cổng IV−HV ≤ 40% được đưa vào MUA/MUA MẠNH.

### 6.5 Kiểm định tính đơn điệu của thang điểm

Lợi nhuận 20 phiên tới theo nhóm điểm (toàn bộ CW, không chỉ top-5):

| Nhóm | n | TB | Trung vị | Win |
|---|---|---|---|---|
| 80–100 | 223 | −2,0% | −9,3% | 40,8% |
| 65–79 | 1.924 | −1,0% | −7,3% | 39,5% |
| 45–64 | 2.624 | −10,7% | −16,7% | 29,8% |
| 30–44 | 115 | −34,7% | −32,9% | 15,7% |

Đơn điệu nhưng **yếu** — chênh lệch giữa nhóm cao và trung bình nhỏ. Đây là lý do xếp hạng được trình bày như **thang tương đối trong vũ trụ hiện tại**, không phải xác suất sinh lời.

---

## 7. Giới hạn & rủi ro mô hình

1. **Không có bid/ask thật** — chi phí là giả định; CW mỏng có thể trượt giá > 2%.
2. **Bước giá 10 VND** — CW giá < 100 VND có sai số IV rất lớn; hệ thống cảnh báo khi giá ≤ 50.
3. **IV từ giá cuối phiên** — có thể lệch nếu phiên cuối thanh khoản thấp.
4. **Không mô hình hoá sự kiện doanh nghiệp tương lai** (cổ tức, thưởng) làm thay đổi K, n.
5. **Rủi ro tổ chức phát hành** không định lượng được từ dữ liệu giá; chỉ cảnh báo khi tập trung > 35% GT giao dịch.
6. **Backtest quá khứ 2023–2026** — thị trường CW Việt Nam còn non, chỉ 18 TCPH; kết quả nhạy với giai đoạn.
7. **Không over-fit**: chỉ một bộ trọng số được công bố; các bảng độ nhạy cho thấy kết quả không phụ thuộc tinh chỉnh nhỏ, và bộ lọc IV được chọn vì có cơ sở kinh tế (không mua biến động đắt) chứ không phải tối ưu tham số.

---

## 8. Kiểm thử

`pytest -q` — 60+ test, gồm:

- BS: parity, tỷ lệ, đáo hạn, arbitrage bounds, Greeks vs sai phân hữu hạn, IV round-trip (scalar + vector).
- Chỉ báo: SMA/EMA/RSI/MACD/ATR/HV, percentile, parse ngày & số kiểu VN.
- Scoring: ngưỡng tăng dần, cổng hạ hạng, DQ, percentile theo underlying duy nhất, universe tối thiểu không crash.
- Backtest: `rows_asof` không dùng tương lai, dung sai, entry sau tín hiệu, trần TCPH, metrics, MFE/MAE.
- Artifact: schema JSON, không có lý do rỗng, không STRONG_BUY trên CW ngắn hạn/không thanh khoản, series khớp manifest, backtest báo lỗi trung thực.
