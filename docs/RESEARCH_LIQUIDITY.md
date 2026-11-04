# Thanh khoản chứng quyền — nghiên cứu thực nghiệm

*Cập nhật: 04/11/2026 · dữ liệu tới phiên 03/11/2026 · phiên bản phương pháp 1.1.0*

Tài liệu này trả lời một câu hỏi cụ thể: **thanh khoản của chứng quyền (CW) Việt Nam ảnh hưởng
như thế nào tới khả năng giao dịch và lợi nhuận kỳ vọng** — và vì vậy hệ thống phải dùng nó ra sao.
Mọi con số dưới đây sinh ra từ chính pipeline trong repo (`research/liquidity_build.py`,
`research/liquidity_study.py`, `python -m cwintel.build`), không có số ngoại lai.

---

## 0. Tóm tắt

| Câu hỏi | Kết quả | Hệ quả |
|---|---|---|
| Thanh khoản có dự báo lợi nhuận 20 phiên? | **Có, nhưng chỉ ở cấp độ vũ trụ**: nhóm ADV20 thấp nhất −18,3%/20 phiên, nhóm cao nhất −3,9%; tương quan hạng +0,164 | Dùng làm trọng số điểm + cổng chặn rủi ro, **không** dùng như tín hiệu mua |
| Thanh khoản có dự báo khả năng thoát hàng? | **Có, rất rõ**: ADV < 5 triệu VND/phiên có 14–18% lệnh phải bán trễ hạn, trung bình trễ 1,6–2,2 phiên; ADV ≥ 100 triệu chỉ 8,0% và 0,91 phiên | Cổng ADV + độ phủ + cảnh báo DTL |
| Bao nhiêu CW thực sự khó giao dịch? | **74/348** CW trong snapshot có ADV20 < 5 triệu VND/phiên; **201/348** cần > 5 phiên để thoát 50 triệu VND ở mức 20% ADV | Cảnh báo hiển thị trên từng mã và trang Thanh khoản |
| Biên độ giá có phải chuyện thanh khoản? | **Mạnh nhất trong các biến**: nhóm biên độ high-low rộng nhất −25,6% và 27,3% lệnh kẹt thoát, so với −3,8%/4,6% ở nhóm hẹp | Đưa biên độ vào điểm thanh khoản và cổng MUA MẠNH/MUA |
| Lọc thanh khoản có làm chiến lược top-5 tốt hơn? | **Không** (ADV cao hơn còn tệ hơn nhẹ); chỉ khi kết hợp IV ≤ HV **và** biên độ ≤ 10% mới dương, nhưng mẫu chỉ 33 lệnh | Không hứa hẹn alpha; nêu rõ trong báo cáo và trên UI |
| Độ phủ phiên có phải thước đo tốt? | **Không, nếu tính thô**: 85/335 CW có <50% phiên giao dịch trong 60 phiên, nhưng **77 trong số đó vẫn giao dịch ≥50% trong 20 phiên gần nhất**; chỉ **22/335** thực sự thưa ở hiện tại | Đo độ phủ *từ ngày niêm yết*, cửa sổ 20 phiên, **tính lại tại as-of** |

---

## 1. Vì sao thanh khoản CW khác cổ phiếu

Một cổ phiếu thanh khoản kém thì khó mua bán. Một CW thanh khoản kém thì **không có giá để tin**:
giá khớp cuối phiên có thể chỉ là một lệnh 100 CW của tổ chức tạo lập thị trường, trong khi bạn muốn
mua 50 triệu VND. Các đặc điểm thị trường dưới đây là nguyên nhân gốc, không phải chi tiết kỹ thuật:

- **Bước giá 10 VND cho mọi mức giá**, giá sàn 10 VND, lô khớp tối thiểu 100 CW. Với CW giá 30–80 VND,
  một bước giá đã là 12–33% — biên độ high-low bị "làm tròn" lên, và phần lớn mức giá không giao dịch được.
- **Nghĩa vụ tạo lập thị trường có điều kiện**: khi chỉ có lệnh một chiều, không có lệnh, hoặc chênh lệch
  mua-bán vượt 5%, tổ chức phát hành phải vào lệnh trong 5 phút, khối lượng tối thiểu 100 CW, chênh lệch
  không quá 5%, lệnh tồn tại tối thiểu 1 phút. **Miễn trừ** khi giá lý thuyết ≤ 10 VND, cổ phiếu cơ sở bị
  tạm ngừng, hoặc hết hàng trong tài khoản tạo lập.
- **Không bán khống, không ký quỹ** với CW; nhà đầu tư nước ngoài không bị giới hạn tỷ lệ sở hữu.
- **Thanh toán khi đáo hạn** theo giá bình quân 5 phiên của cổ phiếu cơ sở trước ngày đáo hạn; ngày giao
  dịch cuối cùng là 2 ngày trước đáo hạn.
- **Kênh phân phối sơ cấp**: phần lớn CW nằm trong tay nhà đầu tư mua đợt phát hành và **ít sang tay**;
  tỷ lệ quay vòng (turnover) trung vị chỉ ~1,7%/phiên.

Hệ quả đo lường: (a) khối lượng bao gồm cả giao dịch của tổ chức tạo lập → ADV là **cận trên** của độ sâu
thực; (b) không có dữ liệu bid/ask → phải dùng biên độ high-low làm proxy chênh lệch mua-bán; (c) phiên
không khớp lệnh là **thông tin**, không phải dữ liệu thiếu.

---

## 2. Dữ liệu

| Hạng mục | Giá trị |
|---|---|
| Nguồn | Vietstock (điều khoản CW) + vnstock VCI/KBS (OHLCV) + HNX/VBMA (lãi suất) |
| Chuỗi OHLCV | 158.353 dòng · 1.315 CW · 937 phiên · 02/02/2023 → 03/11/2026 |
| CW đang lưu hành | 335 (master), 348 vào snapshot (có giao dịch trong 14 phiên) |
| CW đáo hạn | 980 |
| Cổ phiếu cơ sở | 22 mã, 18 tổ chức phát hành |

Không có dữ liệu sổ lệnh, không có giao dịch nội bộ của tổ chức tạo lập, không có khối ngoại theo CW.

---

## 3. Đo lường

Toàn bộ chỉ tiêu tính trên **lịch giao dịch đầy đủ** của thị trường: phiên CW không khớp lệnh được tính
là 0 VND. Đây là khác biệt quan trọng so với thống kê thông thường — bỏ qua phiên trắng sẽ thổi phồng
thanh khoản 1,5–4,6 lần (tỷ lệ ADV20 / trung vị giá trị trên các phiên có giao dịch: p50 = 1,49, p90 = 4,64).

| Chỉ tiêu | Công thức | Ý nghĩa |
|---|---|---|
| `adv5`, `adv20`, `adv60` | Σ giá trị giao dịch N phiên ÷ N | Độ sâu (VND/phiên) |
| `coverage20`, `coverage60` | Số phiên có khớp lệnh ÷ số phiên trong cửa sổ | Tần suất giao dịch |
| `coverage_listing` | Số phiên có khớp lệnh ÷ min(20, số phiên kể từ ngày giao dịch đầu tiên) | Không phạt CW mới niêm yết |
| `zero20` | Số phiên không khớp lệnh trong 20 phiên | Rủi ro kẹt hàng |
| `amihud20` | median(\|r₁\| / giá trị giao dịch) × 10⁹ | % giá dịch chuyển trên 1 tỷ VND giao dịch |
| `range20` | median((high − low)/close) × 100 | Proxy chênh lệch mua-bán / chi phí khớp lệnh |
| `turnover20` | KL bình quân ÷ lượng CW lưu hành × 100 | Mức sang tay |
| `dtl_50m` | 50 triệu ÷ (20% × ADV20) | Số phiên cần để thoát vị thế tham chiếu |
| `impact_50m_pct` | 0,10 × σ × √(50 triệu/ADV20) × 100 | Tác động giá ước tính (mô hình căn bậc hai) |

**Tính lại tại ngày as-of** (`liquidity.rebase_to_asof`): `slice_asof` lấy dòng cuối của mỗi CW, nên nếu CW
ngừng khớp lệnh 10 phiên thì ADV20 sẽ đóng băng ở lần giao dịch cuối và trông tốt hơn thực tế. Hàm này
tính lại trên 20 phiên gần nhất *tính tới as-of*, coi các phiên trắng sau đó là 0. Ví dụ một CW giao dịch
100 triệu/phiên rồi im lặng 10 phiên sẽ có ADV20 = 50 triệu, độ phủ 50%, DTL gấp đôi.

Tham chiếu phương pháp: Amihud (2002) cho price impact; quy ước thực hành tham gia 10–25% ADV và
days-to-liquidate = vị thế ÷ (tỷ lệ tham gia × ADV); mô hình tác động căn bậc hai η·σ·√(Q/ADV) với η ≈ 0,1.

---

## 4. Thiết kế nghiên cứu

`research/liquidity_study.py` dựng một nghiên cứu sự kiện không chồng lấn:

- **Mốc tín hiệu**: 43 ngày, cách nhau 20 phiên, từ 01/06/2023 tới 14/10/2026.
- **Điều kiện vào**: CW có ≥ 20 phiên lịch sử, còn ≥ 30 ngày tới đáo hạn, giá > 0.
- **Vào lệnh**: phiên giao dịch đầu tiên trong vòng 10 ngày sau mốc (mô phỏng độ trễ thực tế).
- **Nắm giữ**: 20 phiên; nếu CW không có giá ở phiên thoát dự kiến, bán ở phiên kế tiếp có giá (**stale exit**)
  và ghi nhận số phiên trễ.
- **Đo**: lợi nhuận gộp, MAE/MFE, tỷ lệ lệnh phải bán trễ, độ trễ trung bình.
- **7.134 quan sát**; chia quintile theo từng chỉ tiêu tại ngày tín hiệu; cổng ADV; tương tác DTE × thanh khoản;
  tương quan hạng trong mặt cắt.

Đây là nghiên cứu **mô tả**, không phải chiến lược: không trừ chi phí, không mô hình hoá stop-loss, và mọi
nhóm tuân theo cùng một lịch tín hiệu. Phần D dưới đây mới là kiểm định trong backtest có phí.

---

## 5. Kết quả A — mặt cắt hiện tại

Tại phiên 03/11/2026, snapshot gồm **348 CW** đang giao dịch (335 CW theo điều khoản hợp đồng):

| Chỉ tiêu | P10 | P25 | Trung vị | P75 | P90 | TB |
|---|---|---|---|---|---|---|
| ADV20 (triệu VND/phiên) | 2,05 | 7,06 | **35,16** | 149,61 | 338,44 | 128,33 |
| Độ phủ giao dịch (%) | 58,5 | 90,0 | **100,0** | 100,0 | 100,0 | 89,8 |
| Amihud20 (%/1 tỷ VND) | 0,16 | 0,41 | 2,05 | 12,05 | 51,65 | 44,98 |
| Biên độ high-low 20P (%) | 0,0 | 5,0 | 10,0 | 18,2 | 32,3 | 13,5 |
| Turnover20 (%) | 0,10 | 0,39 | 1,69 | 3,52 | 5,87 | 2,39 |
| DTL 50 triệu (phiên) | 0,7 | 1,7 | 7,1 | 35,4 | 122,2 | 201,4 |
| Tác động giá 50 triệu (%) | 0,32 | 0,60 | 1,46 | 3,66 | 7,54 | 3,47 |

Phân bố rất lệch: trung bình DTL 201 phiên trong khi trung vị 7,1 phiên — một nhóm nhỏ CW gần như không
thể thoát ở quy mô 50 triệu VND kéo đuôi phân bố. Vì vậy mọi so sánh nên dùng trung vị.

**Phân bố theo độ sâu** — thanh khoản tập trung cực đoan:

| Nhóm ADV20 | Số CW | % vũ trụ | % tổng giá trị giao dịch | Độ phủ trung vị |
|---|---|---|---|---|
| Dưới 10 triệu | 108 | 31,0% | **1,3%** | 85% |
| 10 – 50 triệu | 93 | 26,7% | 6,3% | 100% |
| 50 – 200 triệu | 80 | 23,0% | 19,8% | 100% |
| 200 – 500 triệu | 47 | 13,5% | 35,8% | 100% |
| Trên 500 triệu | 20 | 5,7% | **36,8%** | 100% |

Top-1 CW chiếm 5,0% tổng giá trị phiên, top-5 chiếm 18,4%, top-10 chiếm 29,2%. Nói cách khác: **một phần ba
số CW chỉ chiếm 1,3% thanh khoản**, và 20 mã chiếm hơn một phần ba giá trị.

**Số CW vướng ngưỡng cảnh báo** (trên 348 mã):

| Ngưỡng | Số CW | % |
|---|---|---|
| ADV20 < 5 triệu VND/phiên | 74 | 21,3% |
| Độ phủ giao dịch < 50% | 24 | 6,9% |
| Cần > 5 phiên để thoát 50 triệu VND | 201 | 57,8% |
| Amihud20 > 3 (%/tỷ) | 151 | 43,4% |
| Biên độ high-low > 12% | 143 | 41,1% |

Tương quan hạng trong mặt cắt: ADV20 **nghịch** với premium hoà vốn (−0,259) và với IV−HV (−0,266) — CW thanh
khoản cao thường là CW được định giá "bình thường" hơn; CW kém thanh khoản thường đi kèm premium và IV cao.
Biên độ high-low nghịch với DTE (−0,392) — CW gần đáo hạn dao động mạnh hơn tính theo %.

---

## 6. Kết quả B — thanh khoản và lợi nhuận 20 phiên

Lợi nhuận trung bình toàn mẫu: **−10,52%** (trung vị −13,89%, 29,5% lệnh có lãi, 9,4% phải bán trễ).
Bối cảnh: đây là giai đoạn CW Việt Nam giảm giá hệ thống do theta và premium cao — **mọi** nhóm đều âm.

### 6.1 ADV20 (quintile)

| Nhóm | ADV20 (VND/phiên) | n | TB 20 phiên | Trung vị | % lãi | MAE TB | % bán trễ |
|---|---|---|---|---|---|---|---|
| Q1 | 0,07 – 24,9 triệu | 1.375 | −18,26% | −21,66% | 22,8% | −36,5% | 14,1% |
| Q2 | 25,0 – 81,9 triệu | 1.374 | −11,75% | −18,18% | 29,1% | −33,2% | 10,2% |
| Q3 | 81,9 – 198 triệu | 1.375 | −10,16% | −15,71% | 30,5% | −32,0% | 8,9% |
| Q4 | 198 – 481 triệu | 1.374 | −8,60% | −11,24% | 32,5% | −28,1% | 7,8% |
| Q5 | 482 triệu – 6,04 tỷ | 1.375 | −3,85% | −7,27% | 38,3% | −24,0% | 8,0% |

Đơn điệu gần như hoàn hảo: chênh lệch Q5−Q1 = **14,4 điểm %** lợi nhuận và 14,4 điểm % tỷ lệ lãi.
Tương quan hạng trong mặt cắt: **+0,164**.

### 6.2 Amihud20 (tác động giá)

| Nhóm | Amihud | n | TB | % lãi | Bán trễ |
|---|---|---|---|---|---|
| Q1 (ít tác động) | 0 – 0,10 | 1.360 | −2,79% | 37,9% | 8,4% |
| Q2 | 0,10 – 0,29 | 1.359 | −9,12% | 31,6% | 7,1% |
| Q3 | 0,29 – 0,85 | 1.359 | −7,97% | 32,7% | 7,9% |
| Q4 | 0,85 – 3,37 | 1.359 | −14,23% | 28,3% | 10,9% |
| Q5 (tác động lớn) | 3,38 – 2.640 | 1.359 | −17,82% | 23,3% | 14,9% |

Tương quan hạng **−0,189**. Nhóm Q1 tốt hơn hẳn, nhưng Q2–Q3 không đơn điệu — Amihud nhiễu với CW
giá rất thấp vì mẫu số (giá trị giao dịch) nhỏ.

### 6.3 Biên độ high-low (chi phí khớp lệnh) — tín hiệu mạnh nhất

| Nhóm | range20 | n | TB | Trung vị | % lãi | Bán trễ |
|---|---|---|---|---|---|---|
| Q1 | 0 – 4,6% | 1.372 | −3,76% | −8,11% | 37,9% | 4,6% |
| Q2 | 4,6 – 7,2% | 1.372 | −4,42% | −8,48% | 36,7% | 4,3% |
| Q3 | 7,2 – 10,5% | 1.372 | −5,33% | −11,40% | 32,7% | 4,3% |
| Q4 | 10,5 – 16,4% | 1.372 | −13,33% | −19,23% | 26,7% | 8,6% |
| Q5 | 16,4 – 247% | 1.372 | −25,60% | −36,81% | 19,4% | 27,3% |

Tương quan hạng **−0,266** — mạnh hơn cả ADV và Amihud. Nhưng phải đọc cẩn thận: biên độ rộng vừa phản
ánh **chi phí giao dịch**, vừa phản ánh **biến động** (CW biến động mạnh thì lỗ nhiều hơn khi thị trường
đi ngang/giảm). Vì vậy nó được dùng như cổng *thực thi* (khó khớp giá tốt), không phải dự báo hướng.

### 6.4 Turnover, độ phủ, số phiên trắng

| Chỉ tiêu | Quan hệ với lợi nhuận | Diễn giải |
|---|---|---|
| `turnover20` | Không đơn điệu: −6,2% (Q1) → −13,4% (Q3) → −12,0% (Q5), hạng −0,048 | Sang tay cao = đầu cơ ngắn hạn, không phải thanh khoản tốt |
| `coverage20` | Gần như không phân biệt được (−10,5% ở mọi nhóm) | Phần lớn CW trong mẫu đã giao dịch đủ dày; biến này đo *lịch sử giao dịch* nhiều hơn *thanh khoản hiện tại* |
| `zero20` | Như trên | Nhóm có nhiều phiên trắng bị loại khỏi mẫu do yêu cầu ≥20 phiên |

**Bài học phương pháp — kiểm chứng bằng số:** trong 335 CW đang lưu hành, nếu đếm phiên trắng trên cửa sổ
60 phiên thì 85 mã (25,4%) "kém thanh khoản"; nhưng 77 trong số 85 mã đó lại giao dịch ≥50% số phiên trong
20 phiên gần nhất — chúng chỉ thưa trong quá khứ (thường ngay sau khi niêm yết). Khi tính đúng cách
(từ ngày niêm yết, cửa sổ 20 phiên, tại as-of), chỉ **22/335 mã (6,6%)** thực sự thưa, và 22 mã này đều đã
niêm yết trung vị 95 phiên — tức là **CW cũ nhưng bị bỏ rơi**, đúng nhóm rủi ro nhất. Cửa sổ dài thô
thổi phồng "kém thanh khoản" lên gần 4 lần. Đó là lý do có `coverage_listing` + `rebase_to_asof`,
và vì sao cảnh báo độ phủ phải đi kèm điều kiện `sessions_listed ≥ 20`.

### 6.5 Tương tác với thời gian còn lại (DTE)

| DTE | Thanh khoản thấp | Vừa | Cao | Chênh lệch cao−thấp |
|---|---|---|---|---|
| 0–60 ngày | −29,44% (n=626) | −27,31% (n=505) | −17,78% (n=535) | +11,7 điểm % |
| 60–120 ngày | −16,58% (n=614) | −7,27% (n=652) | −2,97% (n=639) | +13,6 điểm % |
| 120–240 ngày | −9,72% (n=783) | −4,43% (n=864) | −2,92% (n=870) | +6,8 điểm % |
| >240 ngày | −5,46% (n=355) | −1,24% (n=357) | −0,49% (n=334) | +5,0 điểm % |

Thanh khoản **không** chỉ là proxy của DTE: trong *mọi* nhóm DTE, nhóm thanh khoản cao đều tốt hơn 5–14 điểm %.
Ngược lại, CW gần đáo hạn và kém thanh khoản là ô xấu nhất (−29,4%).

### 6.6 Cổng ADV

| Ngưỡng ADV20 | % quan sát còn lại | TB 20 phiên | % lãi | % bán trễ |
|---|---|---|---|---|
| ≥ 5 triệu | 93,8% | −10,13% | 30,1% | 9,0% |
| ≥ 10 triệu | 89,2% | −9,84% | 30,5% | 8,7% |
| ≥ 20 triệu | 82,1% | −9,11% | 31,3% | 8,4% |
| ≥ 50 triệu | 68,4% | −7,94% | 32,4% | 8,2% |
| ≥ 100 triệu | 55,1% | −7,73% | 33,1% | 8,0% |
| ≥ 200 triệu | 39,3% | −6,18% | 34,6% | 7,7% |
| ≥ 500 triệu | 19,1% | −3,49% | 37,7% | 7,9% |

Sàng càng mạnh càng tốt về lợi nhuận trung bình, nhưng **đánh đổi vũ trụ**: ngưỡng 500 triệu chỉ còn 19%
CW, và lợi ích biên giảm dần sau 100 triệu.

---

## 7. Kết quả C — rủi ro thoát vị thế

Đây là phần quan trọng nhất và ít được nói tới. Với mỗi lệnh, nghiên cứu ghi nhận lệnh có bán được đúng
phiên thoát dự kiến hay không:

| Nhóm ADV20 | n | % phải bán trễ | Độ trễ TB (phiên) | MAE TB |
|---|---|---|---|---|
| 0 – 1 triệu | 97 | 7,2%¹ | 1,09 | −30,1% |
| 1 – 5 triệu | 343 | **17,8%** | **2,22** | −34,7% |
| 5 – 20 triệu | 838 | 13,2% | 1,58 | −32,8% |
| 20 – 100 triệu | 1.922 | 9,4% | 1,13 | −33,3% |
| > 100 triệu | 3.934 | 8,0% | 0,91 | −27,7% |

¹ Nhóm 0–1 triệu chỉ có 97 quan sát và bị lọc bởi yêu cầu ≥20 phiên — không nên đọc là "an toàn hơn nhóm 1–5 triệu".
Xu hướng chung từ 1 triệu trở lên là đơn điệu: **thanh khoản càng thấp, khả năng kẹt hàng càng cao và mức lỗ
khi kẹt càng sâu** (MAE là mức giảm tệ nhất trong thời gian nắm giữ).

Điểm thực tế: một lệnh bán trễ 2 phiên trong thị trường CW giảm 10%/20 phiên không phải chuyện nhỏ —
nó biến một kế hoạch "thoát đúng hạn" thành khoản lỗ thêm vài điểm % và có thể đẩy DTE xuống dưới ngưỡng an toàn.

---

## 8. Kết quả D — kiểm định trong backtest top-5 (có phí)

Chạy walk-forward trên đúng panel của hệ thống (43 kỳ, tái cấu trúc 20 phiên, top-5 theo CW Score,
chi phí 0,95%/chiều):

**a) Toàn vũ trụ đủ điều kiện** (không chỉ top-5), lợi nhuận 20 phiên đã trừ phí:

| Nhóm ADV20 | n | TB 20 phiên | Trung vị | % lãi |
|---|---|---|---|---|
| Q1 (7,3 – 65,2 triệu) | 978 | −10,85% | −20,45% | 28,8% |
| Q2 (65,2 – 147,0 triệu) | 977 | −9,52% | −16,13% | 30,0% |
| Q3 (147,0 – 290,2 triệu) | 977 | −6,17% | −11,36% | 33,9% |
| Q4 (290,2 – 625,3 triệu) | 977 | −6,71% | −11,24% | 34,5% |
| Q5 (625,3 triệu – 6,04 tỷ) | 977 | **−2,00%** | −5,60% | 41,9% |

| Ngưỡng ADV20 | % quan sát còn lại | TB 20 phiên | % lãi |
|---|---|---|---|
| ≥ 10 triệu | 99,8% | −7,06% | 33,8% |
| ≥ 50 triệu | 85,5% | −6,19% | 34,9% |
| ≥ 200 triệu | 51,5% | −4,91% | 37,1% |
| ≥ 500 triệu | 25,5% | −2,58% | 40,7% |

Lưu ý: do prefilter của backtest yêu cầu giá trị giao dịch trung vị ≥ 10 triệu, Q1 ở đây bắt đầu từ 7,3 triệu
chứ không phải 0 — nhóm CW hoàn toàn không giao dịch đã bị loại trước khi vào backtest.

**b) Chiến lược top-5 với bộ lọc thanh khoản** (so với dòng cơ sở):

| Bộ lọc | Số lệnh | TB/lệnh | % lãi | Profit factor | Tổng |
|---|---|---|---|---|---|
| Cơ sở: top-5 theo CW Score | 215 | −2,44% | 47,9% | 0,81 | −84,5% |
| ADV20 ≥ 50 triệu | 214 | −2,88% | 46,7% | 0,78 | −87,6% |
| ADV20 ≥ 200 triệu | 207 | −3,91% | 45,4% | 0,71 | −92,1% |
| ADV20 ≥ 500 triệu | 204 | −4,79% | 43,6% | 0,64 | −94,6% |
| Độ phủ ≥ 80% | 215 | −2,46% | 47,9% | 0,81 | −84,6% |
| Amihud ≤ trung vị vũ trụ | 213 | −3,05% | 46,0% | 0,76 | −87,8% |
| Biên độ ≤ 10% | 215 | −3,01% | 45,1% | 0,71 | −82,3% |
| IV ≤ HV | 56 | −0,13% | 57,1% | 0,99 | −86,5% |
| IV ≤ HV **và** ADV ≥ 200 triệu | 48 | +0,04% | 58,3% | 1,00 | −70,0% |
| IV ≤ HV **và** Amihud ≤ trung vị | 46 | +0,28% | 58,7% | 1,02 | −67,9% |
| IV ≤ HV **và** biên độ ≤ 10% | **33** | **+4,72%** | **66,7%** | **1,65** | **+43,5%** |

**Đọc kết quả này cho đúng:**

1. Ở cấp vũ trụ, thanh khoản **có** quan hệ đơn điệu với lợi nhuận (Q5 −2,0% so với Q1 −10,9%).
2. Nhưng khi đã chọn top-5 theo điểm, **thêm bộ lọc thanh khoản không cải thiện** — thậm chí ADV càng cao càng
   tệ nhẹ (ADV ≥ 500 triệu: −4,79%/lệnh so với cơ sở −2,44%). Nguyên nhân hợp lý: top-5 theo score đã nghiêng
   về CW thanh khoản, phần còn lại bị lọc bớt là nhóm có biến động cao hơn — mà biến động cao là thứ duy nhất
   có thể tạo lợi nhuận trong thị trường giảm hệ thống.
3. Dòng "IV ≤ HV và biên độ ≤ 10%" dương mạnh (+4,72%/lệnh, PF 1,65, tổng +43,5%) **nhưng chỉ 33 lệnh** —
   đủ để đề xuất hướng nghiên cứu, **không** đủ để tuyên bố một chiến lược. Nó cũng cho thấy tín hiệu nằm ở
   *biên độ* (chi phí + biến động), không phải ở ADV.
4. Vì vậy sản phẩm dùng thanh khoản làm **cổng rủi ro**, không dùng làm bộ lọc tăng lợi nhuận, và ghi rõ điều
   này trên trang Thanh khoản lẫn Backtest.

---

## 9. Diễn giải

1. **Thanh khoản dự báo khả năng thoát hàng, không dự báo hướng giá.** Ở cấp vũ trụ, ADV cao đi kèm lỗ ít hơn
   (Q5 −3,9% so với Q1 −18,3%), nhưng khi đã chọn top-5 theo điểm thì thêm bộ lọc ADV **không** cải thiện
   lợi nhuận mỗi lệnh. Đây là khác biệt giữa "yếu tố phân biệt trung bình" và "alpha sau khi đã chọn".
2. **Biên độ high-low là biến mạnh nhất trong dữ liệu** (−0,266 tương quan hạng), nhưng bản chất kép
   (chi phí + biến động) khiến nó phù hợp làm **cổng chặn**, không phải tín hiệu mua.
3. **Độ phủ phiên dễ bị hiểu sai.** Đếm phiên trắng chỉ có nghĩa khi so với tuổi niêm yết và khi tính lại
   tại ngày as-of; nếu không sẽ vừa oan cho CW mới, vừa bỏ sót CW cũ đã ngừng giao dịch.
4. **Thanh khoản là điều kiện cần để luận điểm đầu tư có thể thực thi.** Một CW có score 87 nhưng ADV 2 triệu
   VND/phiên thì "điểm" chỉ đúng trên giấy: 50 triệu VND cần 125 phiên ở mức 20% ADV.
5. **Không có bằng chứng rằng lọc thanh khoản tạo alpha dương.** Trung thực mà nói, nó làm giảm mức lỗ kỳ vọng
   và giảm xác suất kẹt hàng — hai mục tiêu đủ để đưa vào sản phẩm, nhưng không đủ để quảng cáo.

---

## 10. Đã thay đổi gì trong sản phẩm

| Hạng mục | Trước | Sau |
|---|---|---|
| Điểm thanh khoản (15% CW Score) | 50% log giá trị TB + 25% tỷ lệ phiên + 25% tăng tốc KL | 35% log ADV20 + 20% Amihud + 20% độ phủ từ niêm yết + 15% tác động giá 50 triệu + 10% xu hướng |
| Cổng MUA MẠNH | liquidity ≥ 60, GT TB ≥ 50 triệu | thêm **ADV20 ≥ 100 triệu**, **độ phủ ≥ 80%**, **biên độ ≤ 12%** |
| Cổng MUA | liquidity ≥ 40, GT TB ≥ 10 triệu | thêm **ADV20 ≥ 20 triệu**, **độ phủ ≥ 50%**, **biên độ ≤ 20%** |
| Cảnh báo từng mã | 1 dòng "thanh khoản thấp" | 6 loại cụ thể: ADV, độ phủ/phiên trắng, DTL > 5 phiên, Amihud, biên độ, thanh khoản suy giảm |
| Screener | GT TB 20 phiên | thêm ADV20, độ phủ, Amihud, biên độ, DTL, nhóm thanh khoản + 2 preset ("Thanh khoản tốt", "Dễ thoát hàng") |
| Trang mới | — | **Thanh khoản**: phân bố, theo TCPH/cơ sở, danh sách cảnh báo, máy tính thoát vị thế, bằng chứng backtest |
| Tab chi tiết CW | — | tab **Thanh khoản**: ADV/độ phủ theo thời gian, DTL, tác động giá, so sánh cùng cơ sở |
| Artifact | — | `docs/data/liquidity.json` + khối `liquidity` trong `backtest.json` |
| Phương pháp | v1.0.0 | v1.1.0 (đổi trọng số + cổng; score cũ không so sánh trực tiếp được) |

---

## 11. Giới hạn

1. **Không có bid/ask**: biên độ high-low là proxy thô, bao gồm cả biến động trong phiên.
2. **Khối lượng gồm giao dịch tạo lập**: ADV là cận trên của độ sâu thực; một phần "thanh khoản" chỉ là
   tổ chức phát hành đảo vị thế.
3. **Mẫu thời gian ngắn và một chu kỳ thị trường**: 43 mốc tín hiệu không chồng lấn, 2023–2026, thị trường CW
   trong xu hướng giảm hệ thống. Các quintile có thể đảo chiều trong chu kỳ khác.
4. **Không mô hình hoá cung cầu tổ chức phát hành**: khi tổ chức ngừng tạo lập (miễn trừ), thanh khoản có thể
   biến mất trong vài phiên mà ADV20 chưa phản ánh.
5. **DTL là kịch bản, không phải bảo đảm**: giả định tham gia đều 20% ADV, không có tin tức, không có làn sóng bán.
6. **Tác động giá dùng căn bậc hai với η = 0,10** (chuẩn thực hành cho cổ phiếu); CW có thể nhạy hơn do mất cân
   bằng cung cầu và bước giá 10 VND.
7. **Không có dữ liệu CW huỷ niêm yết sớm** đầy đủ — nhóm này thường là nhóm thanh khoản tệ nhất, nên thiên lệch
   survivorship có thể làm kết quả *lạc quan hơn* thực tế.

---

## 12. Tái lập

```bash
# 1) Panel thanh khoản (23,6 s) → /tmp/liq_panel.parquet
PYTHONPATH=. python research/liquidity_build.py

# 2) Nghiên cứu sự kiện 20 phiên (1,7 s) → /tmp/liq_study.json
PYTHONPATH=. python research/liquidity_study.py

# 3) Pipeline đầy đủ → docs/data/liquidity.json + khối liquidity trong backtest.json
PYTHONPATH=. python -m cwintel.build
```

Mọi bảng trong tài liệu này lấy từ hai tệp JSON trên. Số liệu backtest ở §8 lấy từ `docs/data/backtest.json`
(khối `liquidity` và `filter_sensitivity`).
