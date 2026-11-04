/* ============================================================
   CW Intelligence — song ngữ Việt/Anh + giao diện sáng/tối
   ------------------------------------------------------------
   Chiến lược dịch (không cần backend, không cần build step):

   1. STRINGS      — từ điển chính xác cho nhãn, tiêu đề, nút, cột…
                     (khoá = chuỗi tiếng Việt đã render, giá trị = tiếng Anh).
   2. TEMPLATES    — câu có số liệu do engine sinh ra; mỗi mẫu là một regex
                     bắt phần số rồi ghép lại thành câu tiếng Anh đúng trật tự.
   3. PHRASES      — dự phòng cho chuỗi ngắn chưa có trong từ điển: thay cụm
                     từ theo thứ tự dài→ngắn, chỉ áp dụng cho chuỗi ≤ 60 ký tự.

   Chế độ: 'vi' (mặc định) · 'en' · 'both' (hiển thị song song, EN in nghiêng).
   Không dùng CDN, không gọi mạng: mọi thứ nằm trong file này.
   ============================================================ */

const KEY_LANG = 'cwintel:lang';
const KEY_THEME = 'cwintel:theme';

let lang = (() => {
  try {
    const saved = localStorage.getItem(KEY_LANG);
    return saved === 'en' || saved === 'both' ? saved : 'vi';
  } catch { return 'vi'; }
})();

export const LANG_LABELS = { vi: 'VI', en: 'EN', both: 'VI+EN' };

/* ---------------------------------------------------------------
   1. TỪ ĐIỂN NHÃN GIAO DIỆN  (vi → en)
   --------------------------------------------------------------- */
export const STRINGS = {


  /* ---------- khung ứng dụng (nav, footer, boot) ---------- */
  "Thị trường": "Market",
  "Phân tích": "Analysis",
  "Hệ thống": "System",
  "Danh mục": "Portfolio",
  "Dashboard cũ": "Legacy dashboard",
  "Đang tải dữ liệu thị trường…": "Loading market data…",
  "Không phải khuyến nghị đầu tư. Dữ liệu có thể chậm 1 phiên.": "Not investment advice. Data may lag one session.",
  "Không có dữ liệu": "No data",
  "Không": "No",
  "Có": "Yes",
  "Tìm CW, cổ phiếu cơ sở, tổ chức phát hành…  ( / )": "Search warrants, underlyings, issuers…  ( / )",
  "Đổi giao diện sáng/tối": "Switch light/dark theme",
  "Menu": "Menu",
  "Covered Warrant Analytics": "Covered Warrant Analytics",
  "Dữ liệu: Vietstock, vnstock (VCI/KBS), HNX · Xây dựng trên repo": "Data: Vietstock, vnstock (VCI/KBS), HNX · Built on repo",
  "Vietstock — điều khoản CW (strike, tỷ lệ chuyển đổi, ngày đáo hạn)": "Vietstock — warrant terms (strike, conversion ratio, maturity date)",
  "vnstock (VCI/KBS) — OHLCV chứng quyền và cổ phiếu cơ sở": "vnstock (VCI/KBS) — warrant and underlying OHLCV",
  "HNX / VBMA — đường cong lợi suất TPCP (lãi suất phi rủi ro)": "HNX / VBMA — government bond yield curve (risk-free rate)",
  "Vietstock (finance.vietstock.vn) — điều khoản CW": "Vietstock (finance.vietstock.vn) — warrant terms",
  "HNX / VBMA — đường cong lợi suất TPCP": "HNX / VBMA — government bond yield curve",
  "VND (giá CW × khối lượng)": "VND (warrant price × quantity)",
  "VND/CW/ngày lịch; thường âm với vị thế mua.": "VND per warrant per calendar day; usually negative for a long position.",
  "K = K_điều_chỉnh nếu có, ngược lại K_gốc; n = ratio_điều_chỉnh nếu có": "K = adjusted strike if available, otherwise raw strike; n = adjusted ratio if available",
  "Quyền châu Âu, thanh toán tiền mặt, không trừ cổ phiếu cơ sở (đã nằm trong K, n).": "European exercise, cash settled, no dividend subtraction (already embedded in K and n).",
  "Đây là premium chuẩn so sánh được giữa các mức moneyness. 'Premium thời gian' = TV/S chỉ là phần giá trị thời gian, KHÔNG so sánh được giữa ITM và OTM.": "This is the standard premium comparable across moneyness levels. 'Time premium' = TV/S only measures the time-value share and is NOT comparable between ITM and OTM warrants.",
  "Giải BS ngược từ P_CW thị trường (bisection + Newton)": "Invert Black-Scholes from the market warrant price (bisection + Newton)",
  "IV ≈ a + b·z với z = ln(K/S)/√T (OLS theo nhóm cùng underlying)": "IV ≈ a + b·z with z = ln(K/S)/√T (OLS within each underlying group)",
  "Percentile premium hoà vốn, IV residual so đường cong cùng cơ sở, IV/HV, IV rank, dải delta": "Break-even premium percentile, IV residual vs the same-underlying curve, IV/HV, IV rank, delta band",
  "Theta/ngày, khoảng cách hoà vốn, thời gian đáo hạn, biến động, gearing hiệu dụng": "Theta/day, distance to break-even, time to maturity, volatility, effective gearing",
  "Score = Σ(w_i × s_i × c_i) / Σ(w_i × c_i) — c_i là độ tin cậy dữ liệu của thành phần.": "Score = Σ(w_i × s_i × c_i) / Σ(w_i × c_i) — c_i is the data confidence of each component.",
  "Không có dữ liệu bid/ask thật → spread phải giả định.": "No real bid/ask data → the spread must be assumed.",
  "Không có lịch sử lợi suất TPCP dài → r dùng hằng số hiện tại trong backtest.": "No long government-bond history → the backtest uses the current constant risk-free rate.",
  "Không có dữ liệu khối lượng nước ngoài / room / tự doanh.": "No foreign flow / room / proprietary trading data.",
  "Không phải khuyến nghị đầu tư; không đảm bảo lợi nhuận.": "Not investment advice; no return is guaranteed.",
  "Không có API key trong repo; workflow dùng GitHub Secrets khi cần.": "No API keys in the repository; the workflow uses GitHub Secrets when needed.",
  "mọi phép biến đổi nằm trong": "every transformation lives in",
  ", có test; build ghi lại metadata phiên bản và thời điểm sinh. Không có số liệu nào được nhập tay.": ", with tests; the build records version metadata and generation time. No figure is entered by hand.",
  "GitHub Actions chạy hằng ngày → ingestion (Vietstock/vnstock) → validation & chuẩn hoá → panel đặc trưng → quant (BS/Greeks/IV) → scoring → recommendation → xuất JSON tĩnh vào": "GitHub Actions runs daily → ingestion (Vietstock/vnstock) → validation & normalisation → feature panels → quant (BS/Greeks/IV) → scoring → recommendation → static JSON written to",
  "dashboard chỉ đọc JSON tĩnh, nên không thể đặt lệnh hay gửi Telegram trực tiếp. Cảnh báo chạy trên trình duyệt; muốn gửi Telegram/email cần thêm workflow định kỳ gọi bot API.": "the dashboard only reads static JSON, so it cannot place orders or send Telegram messages directly. Alerts run in the browser; Telegram/email delivery needs an extra scheduled workflow calling a bot API.",
  "CW Intelligence là công cụ phân tích và giáo dục, không phải công ty chứng khoán, không đưa ra lời khuyên đầu tư cá nhân hoá. Chứng quyền có thể mất toàn bộ giá trị khi đáo hạn OTM. Nhà đầu tư tự chịu trách nhiệm với quyết định của mình.": "CW Intelligence is an analytics and educational tool, not a securities firm, and does not provide personalised investment advice. A warrant can lose its entire value if it expires OTM. Investors are responsible for their own decisions.",

  /* ---------- nhà phát hành ---------- */
  "ACBS (Chứng khoán ACB)": "ACBS (ACB Securities)",
  "HSC (Chứng khoán TP.HCM)": "HSC (Hochiminh City Securities)",
  "Shinhan Securities Việt Nam": "Shinhan Securities Vietnam",
  "KAFI (Chứng khoán KAFI)": "KAFI (KAFI Securities)",
  "MBS (Chứng khoán MB)": "MBS (MB Securities)",
  "KIS Việt Nam": "KIS Vietnam",
  "TCBS (Chứng khoán Kỹ Thương)": "TCBS (Techcom Securities)",
  "PHS (Chứng khoán Phú Hưng)": "PHS (Phu Hung Securities)",
  "KB Securities Việt Nam": "KB Securities Vietnam",

  /* ---------- tổng quan ---------- */
  "Tổng quan thị trường chứng quyền": "Covered warrant market overview",
  "⇩ Xuất tổng quan (CSV)": "⇩ Export overview (CSV)",
  "Mở Screener →": "Open screener →",
  "CW đã đáo hạn hoặc ngừng giao dịch được tách khỏi snapshot nên không được chấm điểm hay khuyến nghị; mã không khớp lệnh trong 14 phiên cũng không vào snapshot.": "Matured or delisted warrants are kept out of the snapshot, so they are never scored or recommended; tickers without a trade in 14 sessions are excluded as well.",
  "Premium hoà vốn = (K + giá CW × tỷ lệ)/S − 1. Điểm CW là thang tương đối trong vũ trụ hiện tại.": "Break-even premium = (K + warrant price × ratio)/S − 1. The CW score is a relative scale within the current universe.",
  "Tăng / Giảm": "Up / Down",
  "tổng giá trị các CW có giao dịch": "total value of warrants actually traded",
  "Khối lượng/phiên": "Volume/session",
  "tổng khối lượng khớp lệnh": "total matched volume",
  "theo strike đã điều chỉnh": "by adjusted strike",
  "Thanh khoản cao": "Deep liquidity",
  "Tín hiệu tích cực": "Positive signals",
  "Premium hoà vốn TB": "Avg break-even premium",
  "IV trung vị / HV": "Median IV / HV",
  "IV cao hơn HV ⇒ CW đắt so với biến động thực tế": "IV above HV ⇒ warrants look rich vs realised volatility",
  "Độ rộng thị trường — số CW tăng/giảm": "Market breadth — warrants up vs down",
  "Tăng giá": "Advancing",
  "Giảm giá": "Declining",
  "Tổng giá trị giao dịch CW theo phiên": "Total warrant traded value by session",
  "Phân bố điểm CW (active)": "Warrant score distribution (active)",
  "Phân bố premium hoà vốn (%)": "Break-even premium distribution (%)",
  "Top CW nổi bật": "Notable warrants",
  "Tăng mạnh nhất": "Top gainers",
  "Giảm mạnh nhất": "Top losers",
  "Thanh khoản cải thiện": "Liquidity improving",
  "Biến động bất thường": "Unusual volatility",
  "Phân bố theo tổ chức phát hành": "Distribution by issuer",
  "Tăng": "Up",
  "Giảm": "Down",
  "CW tốt nhất": "Best warrant",
  "Ghi chú dữ liệu": "Data notes",
  "Dữ liệu là": "Data are",
  "thang tương đối": "a relative scale",
  "trong vũ trụ hiện tại.": "within the current universe.",

  /* ---------- heatmap ---------- */
  "Heatmap thị trường": "Market heatmap",
  "Diện tích = quy mô giao dịch · Màu = chỉ số đang chọn · Nhấp vào ô để mở phân tích chi tiết": "Area = traded size · Colour = selected metric · Click a tile to open the full analysis",
  "⇩ Ảnh chụp nhanh (CSV)": "⇩ Snapshot (CSV)",
  "Màu theo": "Colour by",
  "Premium hoà vốn (%)": "Break-even premium (%)",
  "Số ngày còn lại": "Days to maturity",
  "Kích thước theo": "Size by",
  "Khối lượng phiên": "Session volume",
  "Giá trị lưu hành (ước tính)": "Outstanding value (est.)",
  "Đều nhau": "Uniform",
  "Không nhóm": "No grouping",
  "Theo khuyến nghị": "By recommendation",
  "Tất cả khuyến nghị": "All recommendations",

  /* ---------- screener ---------- */
  "Tìm kiếm": "Search",
  "Số CW:": "Warrants:",
  "Tăng / Giảm:": "Up / Down:",
  "Nhóm:": "Group:",
  "Bộ lọc chứng quyền": "Warrant screener",
  "Kết hợp nhiều điều kiện số/ định tính với logic AND/OR. Mọi giá trị tính từ dữ liệu cuối phiên, không realtime.": "Combine numeric and qualitative conditions with AND/OR logic. Every value is computed from end-of-session data, never realtime.",
  "Cột hiển thị": "Visible columns",
  "⟳ Áp dụng ngay": "⟳ Apply now",
  "Điều kiện lọc": "Filter conditions",
  "Chưa có điều kiện. Chọn bộ lọc mẫu hoặc thêm điều kiện.": "No conditions yet. Pick a preset filter or add one.",
  "+ Thêm điều kiện": "+ Add condition",
  "Xoá hết": "Clear all",
  "Bộ lọc mẫu": "Preset filters",
  "Định giá hấp dẫn": "Attractive valuation",
  "Động lượng mạnh": "Strong momentum",
  "Sắp đáo hạn (rủi ro)": "Near maturity (risk)",
  "CW đắt (tránh)": "Expensive warrants (avoid)",
  "Dễ thoát hàng": "Easy to exit",
  "MUA/MUA MẠNH + DQ cao": "BUY/STRONG BUY + high data quality",
  "Bộ lọc đã lưu": "Saved filters",
  "Chưa lưu bộ lọc nào.": "No saved filters yet.",
  "Lưu": "Save",
  "Bao gồm CW đã đáo hạn": "Include matured warrants",
  "Lưu ý: bộ lọc chạy trên": "Note: filters run over",
  "toàn bộ": "the full set of",
  "CW trong snapshot, không chỉ các mã hiển thị.": "warrants in the snapshot, not only the visible rows.",
  "Không có điều kiện": "No conditions",
  "Phủ TK": "Cov.",
  "Khuyến nghị định lượng": "Quantitative recommendations",
  "Điểm thanh khoản tối thiểu": "Minimum liquidity score",
  "Chất lượng dữ liệu tối thiểu": "Minimum data quality",
  "Số ngày tới đáo hạn tối thiểu": "Minimum days to maturity",
  "IV vượt HV tối đa (%)": "Max IV above HV (%)",
  "Số phiên lịch sử tối thiểu": "Minimum history sessions",
  "Danh sách khuyến nghị": "Recommendation list",
  "Điểm cao → thấp": "Score high → low",
  "Thời gian còn lại": "Time left",
  "Premium thấp": "Low premium",
  "Lịch sử khuyến nghị — kiểm chứng walk-forward": "Recommendation history — walk-forward check",
  "Xem backtest đầy đủ →": "See the full backtest →",
  "Ngày tín hiệu": "Signal date",
  "Cổng chất lượng — không bao giờ MUA MẠNH khi vi phạm": "Quality gates — never STRONG BUY when breached",
  "Điểm cao vẫn bị hạ hạng nếu không đạt các điều kiện dưới đây. Đây là lý do nhiều CW có điểm khá nhưng chỉ ở mức THEO DÕI.": "A high score is still downgraded when the conditions below are not met. This is why many decent-scoring warrants only reach WATCH.",
  "Nhấp vào dòng để mở trang phân tích chi tiết. Điểm và khuyến nghị là thang tương đối trong vũ trụ CW hiện tại — xem tab Phương pháp.": "Click a row to open the full analysis. Scores and recommendations are a relative scale within the current warrant universe — see the methodology tab.",
  "Không có kết quả phù hợp": "No matching results",


  /* ---------- watchlist / danh mục / cảnh báo ---------- */
  "+ Thêm từ Screener": "+ Add from screener",
  "Watchlist đang trống.": "Watchlist is empty.",
  "Nhấn ★ trên bảng screener hoặc trang chi tiết để thêm mã.": "Click ★ in the screener or on a detail page to add a ticker.",
  "Mở Screener": "Open screener",
  "Danh mục mô phỏng": "Simulated portfolio",
  "Mô phỏng vị thế —": "Position simulation —",
  "kết nối tài khoản, không đặt lệnh. Dữ liệu giá là snapshot cuối phiên, không phải giá khớp thực tế.": "no account connection, no orders. Prices are end-of-session snapshots, not executed fills.",
  "⇩ Xuất CSV": "⇩ Export CSV",
  "Thêm vị thế (giả lập)": "Add position (simulated)",
  "Giá mua (VND/CW)": "Purchase price (VND/CW)",
  "Số lượng CW": "Warrant quantity",
  "Ngày mua": "Purchase date",
  "+ Thêm vị thế": "+ Add position",
  "Chưa có vị thế nào. Thêm vị thế để xem P/L và phân bổ.": "No positions yet. Add one to see P/L and allocation.",
  "Quy tắc cảnh báo chạy": "Alert rules run",
  "trên trình duyệt": "in the browser",
  "khi bạn mở trang (không có server nền). Lưu cục bộ theo thiết bị.": "when you open the page (there is no background server). Stored locally per device.",
  "🔔 Bật thông báo trình duyệt": "🔔 Enable browser notifications",
  "đây là cảnh báo phía client, chỉ chạy khi tab đang mở. Gửi Telegram/email cần backend (GitHub Actions + bot) — xem hướng dẫn ở trang Phương pháp. Hệ thống không gửi dữ liệu của bạn đi đâu cả.": "these are client-side alerts that only run while the tab is open. Telegram/email delivery needs a backend (GitHub Actions + bot) — see the methodology page. Nothing is sent anywhere.",
  "Thêm quy tắc cảnh báo": "Add alert rule",
  "Loại": "Type",
  "Điểm CW ≥": "CW score ≥",
  "Điểm CW ≤": "CW score ≤",
  "Khuyến nghị thay đổi": "Recommendation changes",
  "Giá CW ≥": "Warrant price ≥",
  "Giá CW ≤": "Warrant price ≤",
  "Còn ≤ ngày tới đáo hạn": "Days to maturity ≤",
  "Premium hoà vốn ≥": "Break-even premium ≥",
  "Mã CW (trống = toàn bộ)": "Warrant (blank = all)",
  "điểm": "points",
  "+ Thêm cảnh báo": "+ Add alert",
  "Chưa có quy tắc nào.": "No rules yet.",
  "Kết quả quét": "Scan results",
  "⟳ Quét ngay": "⟳ Scan now",
  "Chưa quét lần nào trong phiên bản này.": "No scan has run in this session yet.",
  "Danh sách theo dõi được lưu trên trình duyệt của bạn (localStorage). Không đồng bộ giữa các thiết bị.": "The watchlist is stored in your browser (localStorage). It does not sync across devices.",

  /* ---------- thanh khoản ---------- */
  "Độ sâu, độ phủ phiên, tác động giá và rủi ro thoát vị thế · số liệu phiên": "Depth, session coverage, price impact and exit risk · end-of-session data",
  "⇩ Xuất toàn bộ": "⇩ Export everything",
  "CW thanh khoản rất thấp": "Very thin warrants",
  "proxy chênh lệch mua-bán": "bid-ask spread proxy",
  "Tập trung giá trị": "Value concentration",
  "Độ phủ phiên trung vị": "Median session coverage",
  "% vũ trụ": "% of universe",
  "% tổng ADV": "% of total ADV",
  "Cảnh báo thanh khoản": "Liquidity alerts",
  "Phủ từ niêm yết": "Coverage since listing",
  "Phiên trắng": "No-trade sessions",
  "Amihud (%/tỷ)": "Amihud (%/bn)",
  "Biên độ HL": "High-low range",
  "Máy tính thoát vị thế": "Position exit calculator",
  "Vị thế (triệu VND)": "Position (VND m)",
  "Số phiên cần để thoát": "Sessions needed to exit",
  "Tác động giá ước tính": "Estimated price impact",
  "tác động tăng theo căn bậc hai của khối lượng": "impact grows with the square root of quantity",
  "Vị thế nhỏ so với thanh khoản: có thể thoát trong phiên.": "The position is small relative to liquidity: it can be exited within a session.",
  "Bằng chứng thực nghiệm": "Empirical evidence",
  "đến": "to",
  "% quan sát còn lại": "% of observations remaining",
  "Tương quan hạng trong mặt cắt hiện tại (không phải dự báo):": "Rank correlation in the current cross-section (not a forecast):",
  "Cặp biến": "Variable pair",
  "Đọc đúng con số:": "Reading the numbers correctly:",
  "lợi nhuận trung bình của": "average return of",
  "mọi": "every",
  "không tạo ra alpha dương": "does not create positive alpha",
  "; nó làm giảm mức lỗ kỳ vọng và đặc biệt giảm rủi ro không thoát được vị thế. Xem thêm trang Backtest và tài liệu RESEARCH_LIQUIDITY.md.": "; it reduces the expected loss and especially the risk of being unable to exit. See the backtest page and RESEARCH_LIQUIDITY.md.",
  "Cách đo và giới hạn": "Measurement & limits",
  "định nghĩa dùng xuyên suốt hệ thống": "definitions used across the system",
  "Chỉ tiêu": "Metric",
  "Định nghĩa": "Definition",
  "Dùng để": "Used for",
  "Độ sâu thị trường": "Market depth",
  "Rủi ro không thoát được hàng": "Inability-to-exit risk",
  "Tác động giá": "Price impact",
  "Biên độ high-low": "High-low range",
  "Proxy chênh lệch mua-bán / trượt giá": "Bid-ask spread / slippage proxy",
  "Mức độ sang tay": "Turnover intensity",
  "Số phiên cần để thoát hàng": "Sessions needed to exit",
  "Tác động ước tính": "Estimated impact",
  "Chi phí trượt giá": "Slippage cost",
  "Quy định thị trường ảnh hưởng trực tiếp:": "Market rules that matter directly:",
  "ADV20 trung vị": "Median ADV20",
  "ADV20 ≥ 50 triệu": "ADV20 ≥ VND 50m",
  "ADV20 ≥ 200 triệu": "ADV20 ≥ VND 200m",
  "ADV20 ≥ 500 triệu": "ADV20 ≥ VND 500m",
  "Độ phủ giao dịch ≥ 80% (từ niêm yết)": "Trading coverage ≥ 80% (since listing)",
  "Amihud20 ≤ trung vị vũ trụ": "Amihud20 ≤ universe median",
  "Biên độ high-low ≤ 10%": "High-low range ≤ 10%",
  "IV ≤ HV và ADV ≥ 200 triệu": "IV ≤ HV and ADV ≥ VND 200m",
  "IV ≤ HV và biên độ ≤ 10%": "IV ≤ HV and range ≤ 10%",
  "IV ≤ HV và Amihud ≤ trung vị": "IV ≤ HV and Amihud ≤ median",

  /* ---------- backtest: ghi chú dài ---------- */
  "Kết quả được báo cáo trung thực, kể cả khi xấu.": "Results are reported honestly, even when poor.",
  "thua lỗ": "a loss",
  "trong giai đoạn kiểm định — nguyên nhân chính là cấu trúc giảm giá của CW Việt Nam (theta + IV cao). Điều này không bị che giấu; các bộ lọc có kỳ vọng dương được trình bày trong bảng độ nhạy bên dưới.": "over the test window — driven mainly by the structurally negative drift of Vietnamese warrants (theta plus high IV). This is not hidden; the filters with positive expectancy are shown in the sensitivity table below.",
  "Đây là kiểm định tính đơn điệu của thang điểm: nhóm điểm cao phải có lợi nhuận kỳ vọng tốt hơn. Chênh lệch hiện còn yếu.": "This checks score monotonicity: higher score buckets should carry better expected returns. The spread is still weak.",
  "Giả định, giới hạn và chống thiên lệch": "Assumptions, limits and bias controls",
  "Vào lệnh tại giá đóng cửa phiên kế tiếp sau ngày tín hiệu; không mô phỏng khớp lệnh trong phiên.": "Entry at the close of the session after the signal date; no intraday fill simulation.",
  "Stop-loss/TP mô phỏng trên dữ liệu ngày; khi giá mở cửa gap qua ngưỡng, giả định khớp tại giá mở cửa.": "Stop-loss/take-profit use daily data; when the open gaps through a level, the fill is assumed at the open.",
  "Điều khoản CW (strike/ratio điều chỉnh) lấy từ snapshot hiện tại — có thể lệch nếu có điều chỉnh cổ phiếu trong quá khứ.": "Warrant terms (adjusted strike/ratio) come from the current snapshot — they can differ if corporate actions happened in the past.",
  "(mua khi IV không cao hơn biến động lịch sử) là biến thể duy nhất có kỳ vọng dương trên mỗi lệnh trong giai đoạn này, tuy tổng lợi nhuận vẫn âm do chi phí và đuôi rủi ro. Đây là lý do cổng": "(buy only when IV is not above historical volatility) is the only variant with positive expectancy per trade in this window, although total P&L stays negative because of costs and tail risk. This is why the gate",
  "được đưa vào điều kiện MUA/MUA MẠNH.": "is part of the BUY/STRONG BUY conditions.",
  "phải danh sách khuyến nghị hiện tại.": "rather than the current recommendation list.",
  "Mỗi dòng là một khuyến nghị trong quá khứ: giá vào lệnh (phiên kế tiếp), điểm, hạng, lợi nhuận sau đó, MFE/MAE và việc chạm stop/take-profit. Bảng này để đánh giá mô hình,": "Each row is a past recommendation: entry price (next session), score, rank, subsequent P&L, MFE/MAE and whether stop/take-profit was hit. This table evaluates the model,",

  /* ---------- linh tinh ---------- */
  "Hướng dẫn": "Guide",
  "Ghi chú": "Notes",
  "Lưu ý": "Note",
  "Xem thêm": "See also",
  "Tổng quan thị trường": "Market overview",


  /* ---------- bổ sung: nhãn còn sót sau kiểm thử ---------- */
  "Thanh khoản tốt": "Good liquidity",
  "Thanh khoản còn tốt": "Still liquid",
  "Giá trị giao dịch TB 20P": "Avg traded value (20 sessions)",
  "Giá trị giao dịch TB": "Avg traded value",
  "Giá trị giao dịch/phiên": "Traded value/session",
  "% thay đổi (1 phiên)": "% change (1 session)",
  "% thay đổi (5 phiên)": "% change (5 sessions)",
  "Màu xanh = diễn biến tích cực/điểm cao/rẻ hơn; đỏ = tiêu cực/điểm thấp": "Green = positive move / high score / cheaper; red = negative / low score",
  "Lọc CW có GT ≥ 5 triệu/phiên": "Only warrants traded ≥ VND 5m/session",
  "Chỉ mã có GT ≥ 1 triệu/phiên": "Only tickers traded ≥ VND 1m/session",
  "Nguồn: Vietstock (điều khoản) · vnstock VCI/KBS (OHLCV) · HNX/VBMA (lãi suất)": "Sources: Vietstock (terms) · vnstock VCI/KBS (OHLCV) · HNX/VBMA (rates)",
  "Dữ liệu là snapshot cuối phiên": "Data are an end-of-session snapshot",
  "không phải realtime. Các mã không giao dịch trong phiên được giữ giá cuối cùng.": "not realtime. Tickers with no trades keep their last price.",
  "Cấu trúc thị trường": "Market structure",
  "Điểm CW trung bình": "Average CW score",
  "Số CW tăng / giảm": "Warrants up / down",
  "Tổng giá trị giao dịch": "Total traded value",
  "Giá trị giao dịch bình quân 20 phiên": "20-session average traded value",
  "Độ phủ giao dịch 20 phiên": "20-session trading coverage",
  "Chỉ số thanh khoản": "Liquidity metrics",
  "Cảnh báo theo mã": "Per-ticker alerts",
  "Bảng xếp hạng": "Ranking",
  "Xếp hạng theo điểm": "Ranked by score",
  "Bộ lọc nâng cao": "Advanced filters",
  "Tải lại dữ liệu": "Reload data",
  "Xem chi tiết": "View details",
  "Sao chép": "Copy",
  "Đã sao chép": "Copied",
  "Đang tải…": "Loading…",
  "Sẵn sàng.": "Ready.",
  "Không tải được dữ liệu": "Could not load data",


  "HV 1 năm": "1-year HV",
  "RSI(14) cơ sở": "Underlying RSI(14)",
  "Cổng chất lượng": "Quality gate",
  "Trạng thái": "Status",
  "Không có": "None",
  "Chiến lược top-5 theo CW Score": "Top-5 by CW Score strategy",
  "Đường vốn — 4 chiến lược (base 100)": "Equity curves — 4 strategies (base 100)",
  "Giá CW — nến ngày, MA20/MA50, khối lượng": "Warrant price — daily candles, MA20/MA50, volume",
  "Cổ phiếu cơ sở — giá đóng cửa & MA50": "Underlying — close & MA50",
  "Kiểm tra tự động trên toàn bộ chuỗi dữ liệu tại phiên": "Automated checks across the whole data chain at the data session",
  "— công thức, trọng số, cổng chất lượng và giới hạn của mô hình.": "— formulas, weights, quality gates and model limits.",
  "VND cho 1 chứng quyền": "VND per warrant",
  "VND cho 1 cổ phiếu": "VND per share",
  "số CW cần để nhận 1 cổ phiếu (n:1)": "warrants needed per share (n:1)",
  "năm, ACT/365": "years, ACT/365",
  "Mỗi dòng là một khuyến nghị trong quá khứ — dùng để đánh giá mô hình, không phải danh sách hiện tại.": "Each row is a past recommendation — used to evaluate the model, not the current list.",
  "Mỗi khuyến nghị là kết quả của CW Score (0–100) + cổng chất lượng.": "Each recommendation combines the CW Score (0–100) with the quality gates.",


  /* ---------- quality.json ---------- */
  "Biến động ngày > 50% (nghi ngờ dữ liệu)": "Daily move > 50% (data suspect)",
  "CW có giá cũ hơn 3 ngày so với phiên chuẩn": "Warrants whose last price is more than 3 days older than the data session",
  "Cảnh báo: CW có giá cũ hơn 3 ngày so với phiên chuẩn": "Warning: warrants with prices more than 3 days older than the data session",
  "Không thể định giá Black‑Scholes khi thiếu điều khoản.": "Black-Scholes cannot price a warrant without its terms.",
  "Số dòng có ngày không parse được (bị loại khỏi phân tích).": "Rows whose dates could not be parsed (excluded from the analysis).",
  "Thường do nguồn trả giá điều chỉnh khác nhau giữa các trường.": "Usually caused by the source returning differently adjusted prices across fields.",
  "Đối chiếu break-even với Vietstock (dùng strike/ratio điều chỉnh)": "Cross-check break-even against Vietstock (using adjusted strike/ratio)",
  "Trùng lặp bản ghi OHLCV (cùng ticker + ngày, khác định dạng chuỗi)": "Duplicate OHLCV records (same ticker + date, different string formats)",
  "Cảnh báo: Trùng lặp bản ghi OHLCV (cùng ticker + ngày, khác định dạng chuỗi)": "Warning: duplicate OHLCV records (same ticker + date, different string formats)",
  "Panel giữ cả CW đã đáo hạn để backtest không bị survivorship bias.": "The panel keeps matured warrants so the backtest is free of survivorship bias.",
  "CW biến động mạnh là bình thường, nhưng >50%/ngày cần kiểm tra thủ công.": "Big warrant moves are normal, but >50% in a day needs a manual check.",
  "Dùng spot rate 10Y (lãi kép liên tục) từ đường cong HNX — khớp quy ước e^(−rT).": "Uses the 10Y spot rate (continuous compounding) from the HNX curve — consistent with the e^(−rT) convention.",
  "CW không giao dịch trong vài phiên (thanh khoản thấp). Không được hiển thị như giá realtime.": "The warrant has not traded for several sessions (thin liquidity). It must not be shown as a realtime price.",
  "Break-even tính lại = K(điều chỉnh) + giá CW × tỷ lệ điều chỉnh. Tỷ lệ khớp cao xác nhận quy ước tính là đúng.": "Recomputed break-even = adjusted K + warrant price × adjusted ratio. A high match rate confirms the convention is right.",
  "Vietstock đánh dấu ITM cả khi S < K (có thể do quy ước khác). Hệ thống dùng định nghĩa riêng: |S/K − 1| ≤ 2% là ATM, ngược lại ITM/OTM.": "Vietstock flags ITM even when S < K (a different convention). This system uses its own definition: |S/K − 1| ≤ 2% is ATM, otherwise ITM/OTM.",
  "IV Rank cần ≥ 20 quan sát; cache iv_history.parquet của pipeline chỉ có ~70 phiên nên hệ thống tự backfill từ chuỗi giá CW + underlying.": "IV Rank needs ≥ 20 observations; the pipeline's iv_history cache only covers ~70 sessions, so the system backfills from warrant and underlying prices.",
  "IV bị đánh dấu 'low' khi giá CW ≤ 30 VND (làm tròn bước giá), còn < 7 ngày đáo hạn hoặc IV > 300% — không dùng các giá trị này trong scoring.": "IV is flagged 'low' when the warrant price ≤ 30 VND (tick rounding), under 7 days to maturity, or IV > 300% — those values are excluded from scoring.",
  "Hai định dạng ngày (dd/mm/yyyy và ISO+07:00) từng được lưu song song cho cùng một phiên. Tầng phân tích chuẩn hoá ngày và dedupe theo (ticker, ngày), giữ bản ghi có khối lượng lớn hơn. Dữ liệu gốc không bị sửa.": "Two date formats (dd/mm/yyyy and ISO+07:00) were once stored for the same session. The analytics layer normalises dates and dedupes by (ticker, date), keeping the record with the larger volume. Raw data is untouched.",

  /* ---------- methodology.json ---------- */
  "Định giá CW": "Warrant valuation",
  "Động lượng cổ phiếu cơ sở": "Underlying momentum",
  "Rủi ro / Lợi nhuận": "Risk / Reward",
  "Tín hiệu kỹ thuật": "Technical signals",
  "Thời gian đáo hạn": "Time to maturity",
  "Giá trị 1 CW": "Value of 1 warrant",
  "Giá − 2 ATR(14)": "Price − 2 ATR(14)",
  "EW rổ 22 cổ phiếu cơ sở": "EW basket of 22 underlyings",
  "EW toàn bộ CW đủ điều kiện": "EW of all eligible warrants",
  "Chọn ngẫu nhiên 5 CW (trung bình 10 seed)": "Random 5 warrants (average of 10 seeds)",
  "VND/CW cho 1 điểm biến động (1%).": "VND/warrant per 1 volatility point (1%).",
  "Không survivorship: universe gồm cả CW đã đáo hạn": "No survivorship: the universe includes matured warrants",
  "Quanh giá hiện tại ± 0,5 ATR(14), làm tròn bước giá 10 VND": "Around the current price ± 0.5 ATR(14), rounded to a 10 VND tick",
  "Đây là kịch bản mô phỏng có quy tắc, không phải dự báo giá.": "This is a rules-based simulated scenario, not a price forecast.",
  "Ưu tiên 45–180 ngày; giảm mạnh dưới 30 ngày và trên 270 ngày": "Prefers 45–180 days; heavily penalises under 30 and over 270 days",
  "Không look-ahead: mọi đặc trưng dùng dữ liệu ≤ t, vào lệnh t+1": "No look-ahead: every feature uses data ≤ t, entry at t+1",
  "Giá trị mô phỏng (scenario, portfolio, backtest) luôn được ghi nhãn riêng.": "Simulated values (scenario, portfolio, backtest) are always labelled as such.",
  "Không nội suy giá CW; CW không giao dịch quá 7 ngày bị loại khỏi snapshot.": "No interpolation of warrant prices; warrants without a trade for over 7 days are dropped from the snapshot.",
  "Hạn chế: điều khoản CW lấy từ snapshot hiện tại; không mô phỏng giới hạn khối lượng": "Limitation: warrant terms come from the current snapshot; volume limits are not simulated",
  "Khi data_quality < 0,45 hệ thống trả 'CHƯA ĐỦ DỮ LIỆU' thay vì một khuyến nghị hành động.": "When data_quality < 0.45 the system returns 'NOT ENOUGH DATA' instead of an actionable recommendation.",
  "Không hiển thị dữ liệu cũ như realtime: mọi bảng có cột 'phiên' và cảnh báo nếu quá 4 ngày.": "Stale data is never shown as realtime: every table carries a session column and a banner when older than 4 days.",
  "Gearing hiệu dụng = gearing gộp × delta tuỳ chọn; là mức thay đổi giá CW khi underlying thay đổi 1%.": "Effective gearing = gross gearing × option delta; it is the warrant's % move for a 1% underlying move.",
  "0–100, là điểm TƯƠNG ĐỐI trong vũ trụ CW hiện tại (xếp hạng percentile), không phải xác suất sinh lời.": "0–100, a RELATIVE score within the current warrant universe (percentile rank), not a probability of profit.",
  "Chỉ nhận IV khi giá CW > giá trị nội tại và ≤ S/n; gắn cờ chất lượng thấp khi giá CW ≤ 30 VND, T < 7 ngày hoặc IV > 300%.": "IV is only accepted when the warrant price > intrinsic and ≤ S/n; low quality is flagged when the price ≤ 30 VND, T < 7 days or IV > 300%.",
  "Điểm số là tương đối theo vũ trụ hiện tại; khi thị trường xấu, điểm cao vẫn có thể đi kèm kỳ vọng âm (xem kết quả backtest).": "Scores are relative to the current universe; in a bad market a high score can still carry a negative expectation (see the backtest).",
  "0–1, tổng hợp: điều khoản hợp lệ, nguồn sigma, độ mới giá, số phiên, độ dài lịch sử underlying, có IV, tỷ lệ phiên giao dịch.": "0–1, combining: valid terms, sigma source, price freshness, number of sessions, underlying history length, IV availability, trading-session ratio.",
  "Mô phỏng BS khi underlying +5% / +10% sau 10 / 20 phiên (sigma = HV hiện tại, T đã trừ thời gian nắm giữ); backtest dùng TP = 2R": "BS simulation for underlying +5% / +10% after 10 / 20 sessions (sigma = current HV, T net of holding time); the backtest uses TP = 2R",
  "Đơn vị: cổ phiếu quy đổi trên 1 CW. 'Δ tuỳ chọn' hiển thị trên UI là N(d1) (delta của quyền trên 1 cổ phiếu) để so sánh moneyness.": "Unit: shares converted per warrant. 'Option Δ' in the UI is N(d1) — the option delta per share — for comparing moneyness.",
  "CW Việt Nam điều chỉnh strike/ratio khi có cổ tức, thưởng. Dùng strike gốc sẽ làm break-even lệch trung vị ~811 VND (xem docs/AUDIT.md).": "Vietnamese warrants adjust strike/ratio for dividends and bonus issues. Using the raw strike shifts break-even by a median ~811 VND (see docs/AUDIT.md).",
  "Mỗi thành phần có confidence = tỷ lệ trọng số có dữ liệu. Điểm tổng chuẩn hoá lại theo trọng số khả dụng, nên CW thiếu dữ liệu không bị điểm 0 oan.": "Each component has a confidence equal to the share of weights with data. The total renormalises by available weights, so a warrant with missing data is not unfairly zeroed.",
  "Walk-forward, tín hiệu tại t, vào lệnh tại close phiên kế tiếp, nắm giữ 20 phiên, tái cân bằng mỗi 20 phiên, top-5 điểm cao nhất, giới hạn 40% vốn mỗi issuer.": "Walk-forward: signal at t, entry at the next close, 20-session holding, rebalance every 20 sessions, top-5 by score, 40% capital cap per issuer.",
  "30% vùng RSI + 20% MACD dương + 10% MACD tăng + 20% trên MA20 + 10% trên MA50 + 10% breakout 20 phiên (giảm độ tin cậy nếu < 30 phiên)": "30% RSI band + 20% positive MACD + 10% rising MACD + 20% above MA20 + 10% above MA50 + 10% 20-session breakout (lower confidence under 30 sessions)",
  "40% percentile return 21 phiên + 20% return 63 phiên + 20% vị thế so với MA20/MA50 + 15% vùng RSI + 5% khoảng cách đỉnh 60 phiên": "40% 21-session return percentile + 20% 63-session return + 20% position vs MA20/MA50 + 15% RSI band + 5% distance from the 60-session high",
  "30% theta %/ngày + 25% khoảng cách tới break-even + 25% thời gian đáo hạn + 10% vùng biến động + 10% mức gearing hiệu dụng": "30% theta %/day + 25% distance to break-even + 25% time to maturity + 10% volatility band + 10% effective gearing",
  "35% percentile log(ADV20) + 20% percentile Amihud (thấp tốt) + 20% độ phủ giao dịch từ khi niêm yết + 15% dải tác động giá ước tính cho vị thế 50 triệu + 10% xu hướng ADV5/ADV20": "35% log(ADV20) percentile + 20% Amihud percentile (lower is better) + 20% coverage since listing + 15% estimated impact band for a VND 50m position + 10% ADV5/ADV20 trend",
  "30% percentile premium hoà vốn (thấp tốt) + 30% percentile IV residual so với smile + 15% percentile IV/HV + 10% percentile upside so với fair value smile + 5% IV rank + 10% vùng delta": "30% break-even premium percentile (lower is better) + 30% IV residual vs smile percentile + 15% IV/HV percentile + 10% upside vs smile fair value percentile + 5% IV rank + 10% delta band",
  "Nếu R² < 0,15 thì dùng kernel Gaussian theo z. 'IV residual' = IV thực / IV trên đường cong − 1. Giá trị hợp lý (fair value smile) = BS với IV trên đường cong. Đây là thước đo đắt/rẻ TƯƠNG ĐỐI trong cùng cổ phiếu cơ sở.": "When R² < 0.15 a Gaussian kernel over z is used. 'IV residual' = actual IV / curve IV − 1. Fair value (smile) = BS priced with the curve IV. This is a RELATIVE rich/cheap measure within the same underlying.",
  "Quyền châu Âu, thanh toán tiền mặt, không trừ cổ tức (đã nằm trong K, n).": "European exercise, cash settled, no dividend subtraction (already inside K and n).",

  /* ---------- liquidity.json ---------- */
  "thấp": "low",
  "rất thấp": "very low",
  "trung bình": "medium",
  "rất cao": "very high",
  "dưới 10 triệu": "below VND 10m",
  "10–50 triệu": "VND 10–50m",
  "50–200 triệu": "VND 50–200m",
  "200–500 triệu": "VND 200–500m",
  "trên 500 triệu": "above VND 500m",
  "ADV tính trên lịch giao dịch đầy đủ: phiên không có giao dịch = 0 VND.": "ADV uses the full trading calendar: sessions without a trade count as 0 VND.",
  "Days-to-liquidate dùng vị thế tham chiếu 50 triệu VND và tham gia 20% ADV.": "Days-to-liquidate uses a VND 50m reference position at 20% of ADV.",
  "Amihud = trung vị |r|/giá trị giao dịch × 1e9 — % giá dịch chuyển trên 1 tỷ VND.": "Amihud = median |r| / traded value × 1e9 — the % price move per VND 1bn traded.",


  /* ---------- cuối: nhãn backtest / thanh khoản / công cụ ---------- */
  "⇩ Tải trades (CSV)": "⇩ Download trades (CSV)",
  "Lợi nhuận theo tháng — top-5 Score": "Monthly returns — top-5 by score",
  "Lợi nhuận 20 phiên tới theo nhóm điểm (toàn bộ CW)": "Next 20-session return by score bucket (all warrants)",
  "Cơ sở: top-5 theo CW Score": "Base: top-5 by CW Score",
  "Chỉ mua khi cổ phiếu cơ sở trên MA50": "Only buy when the underlying is above MA50",
  "Chỉ CW Score ≥ 80": "Only CW Score ≥ 80",
  "Toàn bộ lệnh (215)": "All trades (215)",
  "Không có dữ liệu bid/ask thật: giả định nửa chênh lệch 0,50% + hoa hồng 0,15% + trượt giá 0,30% mỗi chiều.": "No real bid/ask data: assumes a 0.50% half-spread + 0.15% commission + 0.30% slippage per side.",
  "Không mô phỏng giới hạn khối lượng: với CW giao dịch dưới 50 triệu VND/phiên, kết quả thực tế sẽ kém hơn.": "No volume limits are simulated: for warrants trading under VND 50m/session, real results will be worse.",
  "Điều khoản CW (strike/ratio điều chỉnh) lấy từ snapshot hiện tại — có thể lệch nếu có điều chỉnh cổ tức trong quá khứ.": "Warrant terms (adjusted strike/ratio) come from the current snapshot — they can differ if dividends were adjusted in the past.",
  "Lãi suất phi rủi ro dùng hằng số hiện tại cho toàn bộ giai đoạn (cache HNX chỉ có 57 phiên).": "The risk-free rate is a constant applied to the whole period (the HNX cache covers only 57 sessions).",
  "Số kỳ tái cân bằng ít (~40) → sai số thống kê lớn; kết quả không nên được hiểu là kỳ vọng chắc chắn.": "Few rebalance periods (~40) → large statistical error; do not read the result as a firm expectation.",
  "Biên độ high-low 20P": "20-session high-low range",
  "10% CW thanh khoản nhất": "Top 10% most liquid warrants",
  "tỷ lệ phiên có khớp lệnh / 20 phiên": "share of sessions with a match / 20 sessions",
  "% giá / 1 tỷ VND giao dịch": "% price per VND 1bn traded",
  "Giao dịch < 50% phiên": "Trades on < 50% of sessions",
  "Cần > 5 phiên để thoát 50 tr": "Needs > 5 sessions to exit VND 50m",
  "Biên độ high-low > 12%": "High-low range > 12%",
  "ADV20 từ": "ADV20 from",
  "Ngưỡng ADV20": "ADV20 threshold",
  "Nếu thoát trong 1 phiên": "If exited within 1 session",
  "ở mức 20% ADV20 mỗi phiên": "at 20% of ADV20 per session",
  "20 phiên nắm giữ · đã trừ chi phí 2 chiều": "20-session holding · net of two-way costs",
  "Lợi nhuận 20 phiên theo nhóm ADV20 (toàn vũ trụ)": "20-session return by ADV20 bucket (whole universe)",
  "không chỉ top-5 theo điểm": "not only the top-5 by score",
  "Nếu chỉ mua CW có ADV20 ≥ ngưỡng (phần còn lại bị loại):": "If only warrants with ADV20 ≥ threshold are bought (the rest excluded):",
  "Chiến lược top-5 với bộ lọc thanh khoản (so với dòng \"Cơ sở\"):": "Top-5 strategy with a liquidity filter (vs the \"Base\" row):",
  "tổng ADV20 của các CW cùng cơ sở": "total ADV20 of warrants on the same underlying",
  "giá trị giao dịch phiên gần nhất và ADV20 trung vị": "last-session traded value and median ADV20",
  "Tổng giá trị giao dịch 20/5 phiên ÷ số phiên, trên lịch đầy đủ (phiên trắng = 0)": "Traded value over 20/5 sessions ÷ sessions, on the full calendar (no-trade sessions = 0)",
  "% số phiên thực sự có khớp lệnh trong 20 phiên": "% of the last 20 sessions with an actual match",
  "Trung vị |lợi suất ngày| ÷ giá trị giao dịch × 1e9 (% giá trên 1 tỷ VND)": "Median |daily return| ÷ traded value × 1e9 (% price per VND 1bn)",
  "Khối lượng ÷ lượng CW lưu hành, bình quân 20 phiên": "Volume ÷ outstanding warrants, 20-session average",
  "Vị thế ÷ (20% × ADV20)": "Position ÷ (20% × ADV20)",
  "KL đột biến (× TB20)": "Volume spike (× avg20)",
  "GT giao dịch TB20 ≤": "Avg traded value20 ≤",
  "Cơ sở mất MA50": "Underlying loses MA50",
  "CW vượt đỉnh 20 phiên": "Warrant breaks 20-session high",
  "Giá mua là giá bạn tự nhập (VND/CW); để trống sẽ dùng giá cuối phiên. Số lượng mặc định 10.000 CW.": "The purchase price is yours to enter (VND/CW); leave it blank to use the last price. Default quantity is 10,000 warrants.",
  "Thiếu dữ liệu underlying sẽ làm HV và momentum sai.": "Missing underlying data corrupts HV and momentum.",
  "→ GitHub Pages phục vụ SPA này.": "→ GitHub Pages serves this SPA.",
  ", có test; build in ra metadata phiên bản và thời điểm sinh. Không có số liệu nào được nhập tay.": ", with tests; the build prints version metadata and generation time. No figure is typed by hand.",
  "không có API key trong repo; workflow dùng GitHub Secrets khi cần.": "no API keys live in the repository; the workflow uses GitHub Secrets when needed.",
  "mọi trang đều hiển thị ngày dữ liệu. Không có dữ liệu realtime. Nếu phiên dữ liệu cũ hơn 4 ngày, banner cảnh báo xuất hiện trên tất cả các trang và khuyến nghị mới không được phát hành.": "every page shows the data date. Nothing is realtime. When the data session is older than 4 days a warning banner appears on every page and new recommendations are not published.",
  "Percentile return 21/63 phiên + vị thế so MA20/MA50 + RSI cổ phiếu cơ sở": "21/63-session return percentiles + position vs MA20/MA50 + underlying RSI",
  "log giá trị giao dịch TB 20 phiên, tỷ lệ phiên có giao dịch, tăng tốc khối lượng": "log of 20-session average traded value, session coverage, volume acceleration",
  "RSI, MACD histogram & độ dốc, trên MA20/MA50, breakout 20 phiên (giảm độ tin cậy nếu <30 phiên)": "RSI, MACD histogram & slope, above MA20/MA50, 20-session breakout (lower confidence under 30 sessions)",
  "Số ngày còn lại, ưu tiên 45–180 ngày": "Days remaining, preferring 45–180 days",
  "Chuỗi giá: 12.0 MB cho 759 mã (chỉ CW đang giao dịch hoặc giao dịch trong 365 ngày).": "Price series: 12.0 MB for 759 tickers (warrants trading now or within 365 days).",
  "Mỗi khuyến nghị là kết quả của CW Score (0–100) + cổng chất lượng. Phiên dữ liệu": "Every recommendation combines the CW Score (0–100) with the quality gates. Data session",
  "điểm ≥ 80 và đạt mọi cổng": "score ≥ 80 and passes every gate",
  "Tín hiệu chấm điểm tại ngày T, vào lệnh phiên T+1, nắm giữ 20 phiên. Chi phí 0.95%/chiều (bid-ask + phí + trượt giá).": "Scored at date T, entry on T+1, 20-session holding. Costs 0.95%/side (bid-ask + fee + slippage).",


  /* ---------- ghi chú dài (nội dung tĩnh, khớp chính xác) ---------- */
  "Màu xanh = diễn biến tích cực/điểm cao/rẻ hơn; đỏ = tiêu cực/điểm thấp/đắt hơn. Với IV, màu xanh chỉ thể hiện độ lớn, không hàm ý tốt/xấu. Kích thước theo giá trị giao dịch trung bình 20 phiên giúp tránh ảo giác thanh khoản từ một phiên đột biến.": 'Green = positive move / high score / cheaper; red = negative / low score / richer. For IV, green only shows magnitude, not good or bad. Sizing by 20-session average traded value avoids a false sense of liquidity from a single spike session.',
  "Mỗi dòng là một khuyến nghị trong quá khứ: giá vào lệnh (phiên kế tiếp), điểm, hạng, lợi nhuận sau đó, MFE/MAE và việc chạm stop/take-profit. Bảng này dùng để đánh giá mô hình,": 'Each row is a past recommendation: entry price (next session), score, rank, subsequent P&L, MFE/MAE and whether stop/take-profit was hit. This table evaluates the model,',
  "ADV20 tính trên lịch giao dịch đầy đủ: phiên CW không khớp lệnh được tính là 0 VND. Vì vậy ADV20 thấp hơn \"giá trị giao dịch bình quân\" chỉ tính trên các phiên có giao dịch.": 'ADV20 uses the full trading calendar: sessions without a warrant trade count as 0 VND. ADV20 is therefore lower than an "average traded value" computed only over traded sessions.',
  "công thức công bố, tính trực tiếp từ ADV20 của phiên dữ liệu": 'published formula, computed directly from ADV20 at the data session',
  "nhóm đều âm trong giai đoạn 2023–2026 — đây là đặc điểm của thị trường CW Việt Nam (theta + premium cao), không phải lỗi mô hình. Thanh khoản": 'every bucket is negative over 2023–2026 — a feature of the Vietnamese warrant market (theta plus high premium), not a model bug. Liquidity',
  "CW có bước giá 10 VND và giá sàn 10 VND; lô khớp tối thiểu 100 CW; tổ chức phát hành có nghĩa vụ yết giá trong 5 phút khi lệnh một chiều/không có lệnh/chênh lệch >5%, khối lượng mỗi lệnh tối thiểu 100 CW, và được miễn khi giá lý thuyết ≤ 10 VND. Vì vậy CW giá rất thấp thường \"có giá mà không có thanh khoản\" — đúng nhóm mà cảnh báo ADV20/độ phủ nhắm tới.": 'Vietnamese warrants use a 10 VND tick and a 10 VND floor price, with a minimum 100-warrant lot. Issuers must quote within 5 minutes when orders are one-sided, absent, or the spread exceeds 5%, with at least 100 warrants per quote, and are exempt when the theoretical price is ≤ 10 VND. Very cheap warrants therefore often "have a price but no liquidity" — exactly the group the ADV20/coverage alerts target.',
  "(1) Không có dữ liệu sổ lệnh/bid-ask, nên chênh lệch mua-bán chỉ được suy ra từ biên độ high-low; (2) volume bao gồm giao dịch của tổ chức tạo lập thị trường — có thể thổi phồng độ sâu thực tế; (3) DTL giả định tham gia đều 20% ADV mỗi phiên và thanh khoản không xấu đi; (4) vũ trụ chỉ gồm CW còn niêm yết trong dữ liệu, các CW huỷ niêm yết sớm có thể không được phản ánh đầy đủ.": '(1) There is no order-book/bid-ask data, so the spread is inferred from the high-low range; (2) volume includes market-maker trading, which can inflate true depth; (3) DTL assumes a steady 20% of ADV per session and no deterioration in liquidity; (4) the universe only covers warrants still listed in the data, so early delistings may be underrepresented.',
  "Gearing_gộp = S / (P_CW·n); Gearing_hiệu_dụng = N(d1)·S/(P_CW·n)": 'Gearing_gross = S / (P_CW·n);  Gearing_effective = N(d1)·S/(P_CW·n)',
  "TR = max(H−L, |H−C_{t−1}|, |L−C_{t−1}|); ATR = Wilder EMA của TR": 'TR = max(H−L, |H−C_{t−1}|, |L−C_{t−1}|); ATR = Wilder EMA of TR',
  "Điểm cao không đủ để nâng hạng nếu vi phạm cổng thanh khoản (ADV20, độ phủ, biên độ high-low) / chất lượng dữ liệu / thời gian đáo hạn / IV quá cao so với HV. Cổng thanh khoản phản ánh khả năng thoát vị thế, không phải kỳ vọng lợi nhuận — xem docs/RESEARCH_LIQUIDITY.md.": 'A high score is not enough to upgrade if the liquidity gate (ADV20, coverage, high-low range), data quality, time to maturity or IV-above-HV gate is breached. The liquidity gate reflects the ability to exit, not profit expectation — see docs/RESEARCH_LIQUIDITY.md.',
  "Tỷ lệ CW có ADV20 < 5 triệu VND/phiên. Thanh khoản thấp là đặc điểm thị trường, không phải lỗi dữ liệu — nhưng làm giảm khả năng thoát vị thế (xem RESEARCH_LIQUIDITY.md).": 'Share of warrants with ADV20 < VND 5m/session. Thin liquidity is a market feature, not a data error — but it lowers the ability to exit (see RESEARCH_LIQUIDITY.md).',


  /* ---------- heatmap ---------- */
  'Không có CW nào khớp bộ lọc hiện tại. Thử bỏ bớt điều kiện lọc.': 'No warrants match the current filters. Try removing a filter condition.',
  "cao": "high",
  "Ô xám = không có dữ liệu cho chỉ số này": "Grey tile = no data for this metric",

  /* ---------- khuyến nghị & tab ---------- */
  "THEO DÕI": "WATCH",
  "MUA MẠNH": "STRONG BUY",
  "TRÁNH": "AVOID",
  "RỦI RO CAO": "HIGH RISK",
  "MUA": "BUY",
  "NẮM GIỮ": "HOLD",
  "Chi tiết": "Details",
  "Phân tích →": "Analyse →",
  "Điểm": "Score",
  "Điểm CW": "CW score",
  "Khuyến nghị": "Recommendation",
  "Tổng quan": "Overview",
  "Định giá & Greeks": "Valuation & Greeks",
  "Phân tích kịch bản": "Scenario analysis",
  "So sánh cùng cơ sở": "Peer comparison",
  "Kế hoạch & rủi ro": "Plan & risk",
  "Thanh khoản": "Liquidity",
  "Premium hoà vốn": "Break-even premium",
  "Giá CW": "Warrant price",
  "Giá trị hợp lý (smile)": "Fair value (smile)",
  "Động lượng": "Momentum",
  "Định giá": "Valuation",
  "Rủi ro/LN": "Risk/Reward",
  "Kỹ thuật": "Technicals",
  "Thời gian": "Time",
  "Cơ sở": "Underlying",
  "Mã": "Ticker",
  "Mã CW": "Warrant",
  "Số CW": "Warrants",
  "Giá": "Price",
  "Tổng": "Total",
  "Trung vị": "Median",
  "Bộ lọc": "Filters",
  "Nhóm": "Group",
  "Cổng": "Gate",
  "Ngưỡng": "Threshold",
  "Tất cả": "All",
  "không": "no",
  "Vào": "Entry",
  "Phiên": "Session",
  "Thoát": "Exit",
  "Giá vào": "Entry price",
  "Giá ra": "Exit price",
  "Phiên giữ": "Held sessions",
  "Ngẫu nhiên": "Random",
  "Quan sát": "Observations",
  "Cảnh báo": "Alerts",
  "Hạng": "Rank",
  "Tỷ lệ": "Rate",
  "Tỷ lệ lãi": "Win rate",
  "Tỷ lệ thắng": "Win rate",
  "Cập nhật": "Updated",
  "Đáo hạn": "Maturity",
  "Lợi nhuận": "P&L",
  "Lý do thoát": "Exit reason",
  "GT/phiên": "Value/session",
  "TB/lệnh": "Avg/trade",
  "TB/kỳ": "Avg/period",
  "%Ngày": "%/day",
  "% kỳ dương": "% positive periods",
  "% giá trị phiên": "% of session value",
  "Số lệnh": "Trades",
  "Số phiên": "Sessions",
  "Số kỳ": "Periods",
  "Điểm TB": "Avg score",
  "Điểm TB toàn thị trường": "Market-wide average score",
  "Chế độ": "Regime",
  "Chiến lược": "Strategy",
  "Tổng LN": "Total P&L",
  "Thời gian nắm giữ": "Holding period",
  "Ngưỡng điểm tối thiểu": "Minimum score threshold",
  "Chi phí mỗi chiều": "Cost per side",
  "%/chiều": "%/side",
  "Bộ lọc bổ sung (mỗi lệnh)": "Extra filter (per trade)",
  "Nhóm điểm": "Score bucket",
  "Chưa đủ dữ liệu": "Not enough data",
  "☆ Theo dõi": "☆ Watch",
  "★ Đang theo dõi": "★ Watching",
  "Gearing hiệu dụng": "Effective gearing",
  "Giá cơ sở": "Underlying price",
  "Luận điểm mô hình:": "Model thesis:",
  "Toàn vũ trụ": "Whole universe",
  "Toàn vũ trụ CW": "Whole CW universe",
  "Cổ phiếu cơ sở": "Underlying",
  "Cổ phiếu cơ sở (EW)": "Underlying (EW)",
  "Benchmark cổ phiếu cơ sở": "Underlying benchmark",
  "So sánh chiến lược": "Strategy comparison",
  "Thống kê theo nhóm điểm": "Stats by score bucket",
  "Kết quả theo chế độ thị trường": "Results by market regime",
  "Cơ sở TĂNG": "Underlying UP",
  "Cơ sở GIẢM": "Underlying DOWN",
  "Độ nhạy & kiểm định bộ lọc": "Sensitivity & filter tests",
  "Chỉ mua khi IV ≤ HV": "Only buy when IV ≤ HV",
  "Chỉ mua khi IV thấp hơn smile cùng underlying": "Only buy when IV is below the same-underlying smile",
  "Lợi nhuận TB/lệnh": "Avg P&L per trade",
  "Kết quả theo tổ chức phát hành": "Results by issuer",
  "Kết quả theo cổ phiếu cơ sở": "Results by underlying",
  "Tệp": "File",
  "Tệp phát hành": "Published files",
  "Kích thước": "Size",
  "Phiên bản": "Version",
  "Phiên bản phương pháp": "Methodology version",
  "Phương pháp": "Methodology",
  "Phương pháp luận": "Methodology",
  "Phương pháp backtest": "Backtest methodology",
  "Phương pháp →": "Methodology →",
  "Nguồn dữ liệu": "Data sources",
  "Nguồn & tham chiếu": "Sources & references",
  "Nguồn lãi suất": "Rate source",
  "Nguồn lãi suất phi rủi ro": "Risk-free rate source",
  "Vũ trụ dữ liệu có bao gồm CW đã đáo hạn": "Data universe includes matured warrants",
  "Panel giữ cả CW đã đáo hạn để backtest không bị survivorship bias. Screener tách rõ: còn hiệu lực / đã đáo hạn / ngừng giao dịch sớm / chờ niêm yết.": "The panel keeps matured warrants so the backtest is free of survivorship bias. The screener separates live / matured / stopped-early / pending contracts.",
  "Tổng vũ trụ khớp tổng các trạng thái vòng đời": "Universe total equals the sum of lifecycle states",
  "Mỗi CW phải thuộc đúng một trạng thái: còn hiệu lực, chờ niêm yết, đã đáo hạn, ngừng giao dịch sớm hoặc thiếu ngày đáo hạn. Lệch nghĩa là có mã bị đếm trùng/bỏ sót.": "Every warrant must fall in exactly one state: live, pending listing, matured, stopped early or missing maturity. A gap means a ticker is counted twice or dropped.",
  "Snapshot chỉ chứa CW còn hiệu lực (không lẫn mã đã đáo hạn)": "Snapshot only holds live warrants (no matured tickers)",
  "CW đã đáo hạn phải nằm trong danh sách đã đáo hạn của screener, không được chấm điểm/khuyến nghị. DTE luôn tính lại tại phiên dữ liệu nên không thể âm.": "Matured warrants belong to the screener's matured list and are never scored or recommended. DTE is always rebased to the data session, so it cannot be negative.",
  "Khuyến nghị chỉ phát hành cho CW còn hiệu lực": "Recommendations are issued for live warrants only",
  "Mã đã đáo hạn không thể giao dịch được nữa nên không được khuyến nghị.": "A matured warrant can no longer be traded, so it is never recommended.",
  "Phát hiện niêm yết mới & đáo hạn theo phiên": "Per-session detection of new listings & maturities",
  "CW liên tục niêm yết và đáo hạn: mỗi lần build đều so sánh ngày giao dịch đầu tiên và ngày đáo hạn với cửa sổ phiên gần nhất, nên mã mới/ mã hết hạn được nhận diện ngay trong phiên, không phụ thuộc việc có ai mở dashboard hay không.": "Warrants are listed and matured continuously: every build compares first trade date and maturity against the latest session window, so new and expiring tickers are detected in-session without anyone opening the dashboard.",
  "Lãi suất phi rủi ro": "Risk-free rate",
  "Ngày lãi suất": "Rate date",
  "Giới hạn đã biết": "Known limitations",
  "Giới hạn dữ liệu:": "Data limitations:",
  "Giới hạn:": "Limitations:",
  "Quy ước đơn vị": "Unit conventions",
  "Công thức & quy ước": "Formulas & conventions",
  "Giá thực hiện & tỷ lệ chuyển đổi": "Strike & conversion ratio",
  "Giá trị nội tại & thời gian": "Intrinsic & time value",
  "Đòn bẩy": "Leverage",
  "Đường cong biến động (smile) cùng underlying": "Volatility curve (smile) of the same underlying",
  "CW Score — trọng số & thành phần": "CW Score — weights & components",
  "Thành phần": "Component",
  "Trọng số": "Weight",
  "Đo lường": "Measures",
  "Phân loại khuyến nghị & cổng chất lượng": "Recommendation bands & quality gates",
  "Vận hành & triển khai": "Operations & deployment",
  "Kiến trúc:": "Architecture:",
  "Không có backend:": "No backend:",
  "Tính tái lập:": "Reproducibility:",
  "Bảo mật:": "Security:",
  "Miễn trừ trách nhiệm:": "Disclaimer:",
  "Nguyên tắc công bố:": "Disclosure principles:",
  "Chất lượng dữ liệu": "Data quality",
  "Danh sách kiểm tra": "Checklist",
  "Điểm cần lưu ý": "Points to note",
  "Đạt": "Pass",
  "Lỗi": "Error",
  "không chặn pipeline": "does not block the pipeline",
  "chặn phát hành khuyến nghị": "blocks recommendation output",
  "Tuổi dữ liệu": "Data age",
  "trong ngưỡng cho phép": "within the allowed threshold",
  "Vũ trụ": "Universe",
  "Ngày không đọc được": "Unreadable dates",
  "OHLC bất khả thi (close ngoài [low, high])": "Impossible OHLC (close outside [low, high])",
  "CW thiếu strike / tỷ lệ chuyển đổi hợp lệ": "Warrants missing a valid strike / conversion ratio",
  "Moneyness tự tính khác Vietstock": "Computed moneyness differs from Vietstock",
  "CW đang giao dịch nhưng không có dữ liệu giá": "Warrants trading without price data",
  "Không thể phân tích các mã này.": "These tickers cannot be analysed.",
  "Độ tin cậy của IV suy ra từ giá": "Confidence of IV implied from price",
  "Số quan sát IV lịch sử (backfill từ giá CW)": "Historical IV observations (backfilled from warrant prices)",
  "CW active được chấm điểm": "Active warrants scored",
  "Điểm cần dữ liệu giá, underlying và điều khoản.": "Scoring needs price, underlying and term data.",
  "Độ mới dữ liệu cổ phiếu cơ sở": "Underlying data freshness",
  "Độ sâu thanh khoản vũ trụ": "Universe liquidity depth",
  "VNINDEX": "VNINDEX",

  /* ---------- vòng đời chứng quyền (niêm yết / đáo hạn) ---------- */
  "Vòng đời chứng quyền": "Warrant lifecycle",
  "Đang đối chiếu vòng đời CW (niêm yết / đáo hạn)…": "Reconciling warrant lifecycle (listings / maturities)…",
  "CW còn hiệu lực": "Live warrants",
  "Niêm yết mới": "New listings",
  "Vừa đáo hạn": "Recently matured",
  "Sắp đáo hạn": "Upcoming maturities",
  "Ngừng giao dịch sớm": "Early trading stop",
  "Lịch niêm yết & đáo hạn theo tháng": "Listings & maturities by month",
  "Tháng": "Month",
  "Niêm yết": "Listings",
  "Còn hiệu lực, đáo hạn trong tháng": "Live, maturing this month",
  "Trạng thái vòng đời": "Lifecycle status",
  "Còn hiệu lực": "Live",
  "Chờ niêm yết": "Pending listing",
  "Đã đáo hạn": "Matured",
  "GIAO DỊCH": "TRADED",
  "ĐÁO HẠN": "MATURED",
  "NGỪNG GD": "STOPPED",
  "CHỜ NIÊM YẾT": "PENDING",
  "Số ngày từ lần khớp lệnh cuối": "Days since last trade",
  "Ngày từ lần khớp cuối": "Days since last trade",
  "mã đang còn hiệu lực": "warrants currently live",
  "giao dịch phiên này": "traded this session",
  "không giao dịch": "not traded",
  "đã đáo hạn": "matured",
  "còn hiệu lực": "live",
  "trong toàn vũ trụ": "across the universe",
  "hợp đồng": "contracts",
  "CW đang giao dịch": "Warrants trading",

};

/* ---------------------------------------------------------------
   2. MẪU CÂU CÓ SỐ LIỆU  (regex → hàm ghép tiếng Anh)
   --------------------------------------------------------------- */

// Số kiểu Việt Nam: 1.234,5 → giữ nguyên chuỗi, chỉ đổi đơn vị từ.
const NUM = '([-+]?\\d[\\d.,]*)';
const TIC = '([A-Z]{2,6})';

/* Bảng mẫu: [RegExp, (…captures) => string] */
export const TEMPLATES = [
  /* ---- vòng đời CW ---- */
  [/^Hợp đồng gần đáo hạn nhất: (\S+) \((.*)\) — ([\d/]+), còn (\d+) ngày\. Sau ngày đáo hạn mã này tự chuyển sang danh sách đã đáo hạn và không còn được khuyến nghị\.$/,
    (t, u, d, n) => `Next contract to mature: ${t} (${u}) — ${d}, ${n} days left. `
      + 'After maturity it moves to the matured list and is no longer recommended.'],
  [/^Dữ liệu là snapshot cuối phiên ([\d/]+) \(cập nhật (.*)\), không phải realtime\.$/,
    (d, t) => `Data is the end-of-session snapshot ${d} (updated ${t}), not realtime.`],
  [/^KHÔNG GD (\d+)N$/, (d) => `NO TRADE ${d}d`],
  [/^ĐÁO HẠN (\d+)N$/, (d) => `MATURED ${d}d`],
  [/^Bao gồm CW đã đáo hạn \((\d[\d.,]*)\)$/, (n) => `Include matured warrants (${n})`],
  [/^mã thoả điều kiện \/ (\d[\d.,]*) (còn hiệu lực|trong toàn vũ trụ)$/,
    (n, scope) => `${n} matches / ${scope === 'còn hiệu lực' ? 'live universe' : 'whole universe'}`],
  [/^(\d+) phiên gần nhất · từ (\d{2}\/\d{2}\/\d{4})$/,
    (n, d) => `Last ${n} sessions · since ${d}`],
  [/^(\d+) phiên · (\d[\d.,]*) mã đang còn hiệu lực$/,
    (n, k) => `${n} sessions · ${k} warrants currently live`],
  [/^(\d+) phiên · tổng đã đáo hạn (\d[\d.,]*)$/,
    (n, k) => `${n} sessions · ${k} matured in total`],
  [/^≤ 30 ngày · (\d[\d.,]*) mã trong 60 ngày · (\d[\d.,]*) trong 90 ngày$/,
    (a, b, c) => `≤ 30 days · ${a} warrants within 60 days · ${b} within 90 days`],
  [/^còn hạn nhưng không còn khớp lệnh$/, () => 'still live but no longer trading'],
  [/^không có mã nào bị ngừng sớm$/, () => 'no warrant stopped trading early'],
  [/^(\d[\d.,]*) giao dịch phiên này · (\d[\d.,]*) không giao dịch$/,
    (a, b) => `${a} traded this session · ${b} not traded`],
  [/^(\d[\d.,]*) đã đáo hạn · tổng (\d[\d.,]*) hợp đồng$/,
    (a, b) => `${a} matured · ${b} contracts in total`],
  [/^Tổng vũ trụ (\d[\d.,]*) hợp đồng = còn hiệu lực (\d[\d.,]*) \+ đã đáo hạn (\d[\d.,]*)$/,
    (t, a, b) => `Universe total ${t} contracts = ${a} live + ${b} matured`],
  [/^Còn hiệu lực (\d[\d.,]*) \((\d[\d.,]*) giao dịch phiên này\) · đã đáo hạn (\d[\d.,]*) · tổng (\d[\d.,]*) hợp đồng\. Bộ lọc chạy trên toàn bộ tập đang chọn\.$/,
    (a, b, c, t) => `Live ${a} (${b} traded this session) · matured ${c} · ${t} contracts in total. `
      + 'Filters run over the whole selected set.'],
  /* ---- luận điểm / yếu tố tích cực ---- */
  [new RegExp(`^${TIC} xếp thứ ${NUM}/100 về động lượng so với các cổ phiếu cơ sở khác: return 21 phiên ${NUM}%, 63 phiên ${NUM}%, giá (trên|dưới) MA50\\.$`),
    (u, r, r21, r63, tr) => `${u} ranks ${r}/100 on momentum vs other underlyings: 21-session return ${r21}%, 63-session ${r63}%, price ${tr === 'trên' ? 'above' : 'below'} MA50.`],
  [new RegExp(`^${TIC} đang trong xu hướng tăng so với mặt bằng chung\\.$`),
    (u) => `${u} is trending up relative to the peer group.`],
  [new RegExp(`^${TIC} đang yếu: return 21 phiên ${NUM}%, giá dưới MA20/MA50\\.$`),
    (u, r) => `${u} is weak: 21-session return ${r}%, price below MA20/MA50.`],
  [new RegExp(`^IV thấp hơn đường cong biến động của các CW cùng ${TIC} ${NUM}% → CW đang rẻ tương đối so với nhóm cùng cơ sở\\.$`),
    (u, p) => `IV sits ${p}% below the volatility curve of other ${u} warrants → relatively cheap vs its underlying peer group.`],
  [new RegExp(`^IV cao hơn đường cong cùng ${TIC} ${NUM}% → đang trả giá cao cho biến động\\.$`),
    (u, p) => `IV sits ${p}% above the ${u} curve → paying up for volatility.`],
  [new RegExp(`^Premium hoà vốn ${NUM}% thấp hơn trung vị nhóm ${TIC} \\(${NUM}%\\)\\.$`),
    (p, u, q) => `Break-even premium ${p}% is below the ${u} peer median (${q}%).`],
  [new RegExp(`^Thanh khoản cao: ADV20 ${NUM} triệu VND/phiên(?:, giao dịch ${NUM}% số phiên)?\\.$`),
    (v, c) => `Deep liquidity: ADV20 ${v}m VND/session` + (c ? `, traded on ${c}% of sessions.` : '.')],
  [new RegExp(`^Thanh khoản cải thiện: ADV5 gấp ${NUM}× ADV20 \\(${NUM} triệu VND/phiên\\)\\.$`),
    (x, v) => `Improving liquidity: ADV5 is ${x}× ADV20 (${v}m VND/session).`],
  [new RegExp(`^Đủ thanh khoản để thoát vị thế 50 triệu VND trong ~${NUM} phiên \\(giả định tham gia 20% ADV\\)\\.$`),
    (d) => `Liquid enough to exit a VND 50m position in ~${d} sessions (20% participation).`],
  [new RegExp(`^Tốc độ mất giá theo thời gian thấp \\(${NUM}%/ngày\\)\\.$`),
    (x) => `Low time decay (${x}%/day).`],
  [new RegExp(`^Kỹ thuật CW tích cực: RSI\\(14\\) ${NUM}, giá (trên|dưới) MA20\\.$`),
    (r, tr) => `Constructive warrant technicals: RSI(14) ${r}, price ${tr === 'trên' ? 'above' : 'below'} MA20.`],
  [new RegExp(`^Thời gian đáo hạn hợp lý \\(${NUM} ngày\\) — đủ để luận điểm đầu tư phát huy mà không bị theta bào mòn quá nhanh\\.$`),
    (d) => `Reasonable time to maturity (${d} days) — enough runway for the thesis without fast theta erosion.`],
  [/^Giá CW vượt đỉnh 20 phiên \(breakout\) với dữ liệu khối lượng xác nhận\.$/,
    () => 'Warrant price broke its 20-session high (breakout) on confirming volume.'],
  [/^Điểm tổng hợp thuộc nhóm dẫn đầu vũ trụ CW hiện tại\.$/,
    () => 'Composite score is in the top cohort of the current warrant universe.'],

  /* ---- yếu tố tiêu cực / cảnh báo ---- */
  [new RegExp(`^Thanh khoản rất thấp: ADV20 chỉ ${NUM} triệu VND/phiên — khó vào/ra vị thế mà không làm giá chạy\\.$`),
    (v) => `Very thin liquidity: ADV20 only ${v}m VND/session — hard to enter or exit without moving the price.`],
  [new RegExp(`^Thanh khoản thấp: ADV20 chỉ ${NUM} triệu VND/phiên\\.$`),
    (v) => `Thin liquidity: ADV20 only ${v}m VND/session.`],
  [new RegExp(`^Thanh khoản đang suy giảm: ADV5 chỉ bằng ${NUM}% ADV20\\.$`),
    (p) => `Liquidity is fading: ADV5 is only ${p}% of ADV20.`],
  [new RegExp(`^Tác động giá lớn: 1 tỷ VND giao dịch làm giá dịch chuyển ~${NUM}% \\(Amihud 20 phiên\\)\\.$`),
    (x) => `Large price impact: VND 1bn of trading moves the price ~${x}% (20-session Amihud).`],
  [new RegExp(`^Biên độ high-low 20 phiên rộng \\(${NUM}%\\) — chênh lệch mua-bán và trượt giá thực tế cao\\.$`),
    (x) => `Wide 20-session high-low range (${x}%) — wide effective spread and slippage.`],
  [new RegExp(`^Premium hoà vốn cao \\(${NUM}%\\): cổ phiếu cơ sở phải tăng thêm ${NUM}% mới hoà vốn tại ngày đáo hạn\\.$`),
    (p, q) => `High break-even premium (${p}%): the underlying must rise another ${q}% to break even at maturity.`],
  [new RegExp(`^IV cao hơn biến động lịch sử ${NUM}% — giá CW đã phản ánh kỳ vọng biến động lớn, dễ giảm nếu IV hạ nhiệt\\.$`),
    (p) => `IV is ${p}% above historical volatility — the warrant already prices in a big move and is exposed to IV compression.`],
  [new RegExp(`^CW đang OTM ${NUM}% — cần cổ phiếu tăng mạnh mới có giá trị nội tại\\.$`),
    (p) => `Warrant is ${p}% OTM — needs a strong rally to gain intrinsic value.`],
  [/^Delta rất thấp \(< 0,10\): phần lớn giá trị là thời gian, xác suất ITM thấp\.$/,
    () => 'Very low delta (< 0.10): value is mostly time, low probability of finishing ITM.'],
  [/^Delta gần 1 \(ITM sâu\): CW gần như cổ phiếu, đòn bẩy thấp và thường kém thanh khoản\.$/,
    () => 'Delta near 1 (deep ITM): behaves like the stock, low leverage and usually thin liquidity.'],
  [new RegExp(`^Theta decay cao: mất ${NUM}% giá trị CW mỗi ngày nếu mọi yếu tố khác không đổi\\.$`),
    (x) => `High theta decay: loses ${x}% of value per day, all else equal.`],
  [new RegExp(`^Chỉ còn ${NUM} ngày tới đáo hạn — rủi ro thời gian rất lớn\\.$`),
    (d) => `Only ${d} days to maturity — severe time risk.`],
  [new RegExp(`^RỦI RO ĐÁO HẠN: còn ${NUM} ngày\\. Nếu CW hết hạn OTM, toàn bộ vốn có thể mất\\.$`),
    (d) => `MATURITY RISK: ${d} days left. If the warrant expires OTM the entire capital can be lost.`],
  [new RegExp(`^Chỉ giao dịch ${NUM}% số phiên kể từ khi niêm yết \\(${NUM} phiên không khớp lệnh\\) — rủi ro không thoát được hàng\\.$`),
    (p, n) => `Trades on only ${p}% of sessions since listing (${n} sessions without a match) — exit risk.`],
  [/^Lịch sử giao dịch ngắn \(< 15 phiên\): ATR, RSI và thanh khoản chưa đại diện\.$/,
    () => 'Short trading history (< 15 sessions): ATR, RSI and liquidity are not representative.'],
  [new RegExp(`^CW mới niêm yết \\(${NUM} phiên giao dịch\\) — chưa đủ lịch sử để đánh giá chỉ báo kỹ thuật và thanh khoản ổn định\\.$`),
    (n) => `Newly listed warrant (${n} sessions) — not enough history for technical indicators and stable liquidity.`],
  [/^Biến động 20 phiên của cổ phiếu cơ sở đang cao hơn nhiều mức 1 năm — định giá CW nhạy cảm\.$/,
    () => '20-session underlying volatility is far above its 1-year level — warrant valuation is sensitive.'],
  [/^Giá CW sát bước giá tối thiểu — biến động % lớn do làm tròn tick, IV suy ra kém tin cậy\.$/,
    () => 'Warrant price is near the minimum tick — % moves are driven by rounding and implied IV is less reliable.'],

  /* ---- kế hoạch / vô hiệu hoá ---- */
  [new RegExp(`^${TIC} đóng cửa dưới MA50 \\(${NUM} VND\\) trong 2 phiên liên tiếp\\.$`),
    (u, px) => `${u} closes below MA50 (${px} VND) for 2 consecutive sessions.`],
  [/^Điểm CW Score giảm xuống dưới 45 hoặc bị hạ khuyến nghị\.$/,
    () => 'CW Score falls below 45 or the recommendation is downgraded.'],
  [new RegExp(`^Thời gian còn lại tới đáo hạn dưới ${NUM} ngày\\.$`),
    (d) => `Less than ${d} days left to maturity.`],
  [/^ADV20 giảm dưới 5 triệu VND\/phiên hoặc độ phủ giao dịch xuống dưới 50% số phiên \(mất khả năng thoát hàng\)\.$/,
    () => 'ADV20 drops below VND 5m/session or coverage falls under 50% of sessions (exit ability lost).'],
  [new RegExp(`^IV tăng vượt ${NUM} \\(${NUM}%\\) — CW trở nên quá đắt so với chính nó\\.$`),
    (x, p) => `IV rises above ${x} (${p}%) — the warrant becomes expensive relative to itself.`],
  [new RegExp(`^Vị thế 50 triệu VND cần ~${NUM} phiên để thoát ở mức 20% ADV\\.$`),
    (d) => `A VND 50m position needs ~${d} sessions to exit at 20% of ADV.`],
  [/^Vùng vào lệnh ±0,5 ATR\(14\); stop −2 ATR\(14\); take-profit là giá CW mô phỏng theo Black‑Scholes.*$/,
    () => 'Entry zone ±0.5 ATR(14); stop −2 ATR(14); take-profit is the Black-Scholes warrant price if the underlying gains 5%/10% with the corresponding time decay. This is a hypothetical scenario, not a price target.'],


  /* ---- nhãn có số liệu (đếm, phiên, %) ---- */
  [/^(\d[\d.,]*) đã đáo hạn · tổng (\d[\d.,]*)$/u, (a, b) => `${a} matured · ${b} total`],
  [/^(\d[\d.,]*) cảnh báo · (\d[\d.,]*) lỗi$/u, (a, b) => `${a} warnings · ${b} errors`],
  [/^(\d[\d.,]*) mã MUA MẠNH · (\d[\d.,]*) chưa đủ dữ liệu$/u, (a, b) => `${a} STRONG BUY · ${b} no data`],
  [/^(\d[\d.,]*) MUA MẠNH · (\d[\d.,]*) chưa đủ dữ liệu$/u, (a, b) => `${a} STRONG BUY · ${b} no data`],
  [/^(\d[\d.,]*)% CW giao dịch < 50% phiên$/u, (a) => `${a}% of warrants trade on < 50% of sessions`],
  [/^trung bình ([\d.,]+) (triệu|tỷ)$/u, (v, u) => `average ${v} ${u === 'triệu' ? 'm' : 'bn'}`],
  [/^([\d.,]+) phiên gần nhất$/u, (n) => `last ${n} sessions`],
  [/^([\d.,]+) CW đang lưu hành$/u, (n) => `${n} warrants outstanding`],
  [/^([\d.,]+) CW trong vũ trụ$/u, (n) => `${n} warrants in the universe`],
  [/^([\d.,]+) kỳ tái cấu trúc$/u, (n) => `${n} rebalance periods`],
  [/^([\d.,]+) lệnh$/u, (n) => `${n} trades`],
  [/^([\d.,]+) quan sát$/u, (n) => `${n} observations`],
  [/^trên ([\d.,]+) kiểm tra$/u, (n) => `across ${n} checks`],
  [/^Xem thêm \(([\d.,]+)\)$/u, (n) => `Show more (${n})`],
  [/^TB thắng ([+\-]?[\d.,]+%) \/ lỗ ([+\-]?[\d.,]+%)$/u, (a, b) => `avg win ${a} / loss ${b}`],
  [/^giữ TB ([\d.,]+) phiên$/u, (n) => `held avg ${n} sessions`],
  [/^thắng TB ([+\-]?[\d.,]+%) \/ lỗ ([+\-]?[\d.,]+%)$/u, (a, b) => `avg win ${a} / loss ${b}`],
  [/^\+?([\d.,]+)% hôm nay · (.*)$/u, (p, rest) => `+${p}% today · ${rest}`],
  [/^· sinh lúc (.*)$/u, (t) => `· generated ${t}`],
  [/^([\d.,]+)% giá \/ 1 tỷ VND giao dịch$/u, (p) => `${p}% price move per VND 1bn traded`],
  [/^Quy tắc của bạn \(([\d]+)\)$/u, (n) => `Your rules (${n})`],
  [/^Quy tắc của bạn \(([\d]+)\)\.?$/u, (n) => `Your rules (${n})`],


  [/^trung bình ([\d.,]+) m$/u, (v) => `average ${v} m`],
  [/^trung bình ([\d.,]+) (tỷ|triệu)$/u, (v, u) => `average ${v} ${u === 'tỷ' ? 'bn' : 'm'}`],
  [/^([\d.,]+) CW cần lưu ý thanh khoản$/u, (n) => `${n} warrants flagged for liquidity`],
  [/^ADV20 < 5 triệu VND\/phiên · ([\d.,]+) CW không giao dịch 14 phiên$/u, (n) => `ADV20 < VND 5m/session · ${n} warrants without a trade for 14 sessions`],
  [/^start=(.*) · end=(.*) · rebalance=(.*) · top_n=(.*) · cost=(.*) · r=(.*)$/u,
    (a, b, c, d, e, f) => `start=${a} · end=${b} · rebalance=${c.replace('mỗi ', 'every ').replace('phiên', 'sessions')} · top_n=${d} · cost=${e} · r=${f}`],


  [/^· ([\d.,]+) CW còn hiệu lực \(([\d.,]+) giao dịch phiên này\) · ([\d.,]+) cổ phiếu cơ sở · ([\d.,]+) tổ chức phát hành$/u,
    (a, b, c, d) => `· ${a} live warrants (${b} traded this session) · ${c} underlyings · ${d} issuers`],
  [/^· ([\d.,]+) CW đang giao dịch · ([\d.,]+) cổ phiếu cơ sở · ([\d.,]+) tổ chức phát hành$/u,
    (a, b, c) => `· ${a} warrants trading · ${b} underlyings · ${c} issuers`],
  [/^Lọc CW có giá trị giao dịch ≥ ([\d.,]+) triệu\/phiên$/u, (m) => `Only warrants traded ≥ VND ${m}m/session`],
  [/^snapshot cuối phiên ([\d\/.]+)$/u, (d) => `end-of-session snapshot ${d}`],
  [/^Nguồn: Vietstock \(điều khoản\) · vnstock VCI\/KBS \(OHLCV\) · HNX\/VBMA \(lãi suất phi rủi ro 10Y = ([\d.,]+)%\)\.$/u,
    (r) => `Sources: Vietstock (terms) · vnstock VCI/KBS (OHLCV) · HNX/VBMA (10Y risk-free rate = ${r}%).`],
  [/^\(cập nhật (.*)\), không phải realtime\. Các mã không giao dịch trong 14 phiên bị loại khỏi thống kê tổng quan\. Premium hoà vốn = \(K \+ giá CW × tỷ lệ\)\/S − 1\. Điểm CW là$/u,
    (t) => `(updated ${t}), not realtime. Tickers without a trade for 14 sessions are excluded from the overview statistics. Break-even premium = (K + warrant price × ratio)/S − 1. The CW score is`],
  [/^Giá CW ([A-Z0-9]+) — nến ngày, MA20\/MA50, khối lượng$/u, (t) => `${t} warrant price — daily candles, MA20/MA50, volume`],
  [/^Gearing_gộp = S \/ \(P_CW·n\);\s*Gearing_hiệu_dụng = N\(d1\)·S\/\(P_CW·n\)$/u,
    () => 'Gearing_gross = S / (P_CW·n);  Gearing_effective = N(d1)·S/(P_CW·n)'],
  [/^Cổ phiếu cơ sở ([A-Z0-9]+) — giá đóng cửa & MA50$/u, (u) => `${u} underlying — close & MA50`],
  [/^Chia ([\d.,]+) kỳ tái cấu trúc theo dấu lợi nhuận của cổ phiếu cơ sở trong cùng kỳ — cho thấy chiến lược có phụ thuộc vào xu hướng thị trường hay không\.$/u,
    (n) => `Splits ${n} rebalance periods by the sign of the underlying's return over the same window — showing whether the strategy depends on market direction.`],

  /* ---- lý do khuyến nghị (rec_reason) ---- */
  [/^Điểm trong vùng THEO DÕI — chưa đủ hấp dẫn để hành động$/,
    () => 'Score sits in the WATCH band — not attractive enough to act on'],
  [/^Điểm đạt ngưỡng MUA và vượt cổng thanh khoản\/chất lượng$/,
    () => 'Score clears the BUY threshold and passes the liquidity/quality gates'],
  [/^Điểm đạt ngưỡng MUA MẠNH và vượt toàn bộ cổng thanh khoản, chất lượng dữ liệu, thời hạn$/,
    () => 'Score clears the STRONG BUY threshold and passes every liquidity, data-quality and maturity gate'],
  [/^Điểm thấp — định giá và\/hoặc cấu trúc rủi ro không thuận lợi$/,
    () => 'Low score — valuation and/or risk structure unfavourable'],
  [/^Hạ từ MUA MẠNH do (.+)$/, (why) => `Downgraded from STRONG BUY: ${translateList(why)}`],
  [/^Hạ từ MUA do (.+)$/, (why) => `Downgraded from BUY: ${translateList(why)}`],
];

/* ---------------------------------------------------------------
   3. CỤM TỪ DỰ PHÒNG  (chỉ cho chuỗi ngắn; dài→ngắn để không đè nhau)
   --------------------------------------------------------------- */
const W = (vi, en) => [new RegExp('(?<![\\p{L}\\p{N}])' + vi + '(?![\\p{L}\\p{N}])', 'giu'), en];

const PHRASE_RULES = [
  /* đơn vị & số lượng (khớp cả chuỗi) */
  [/^([\d.,]+) cảnh báo$/u, '$1 alerts'],
  [/^([\d.,]+) phiên$/u, '$1 sessions'],
  [/^([\d.,]+) ngày$/u, '$1 days'],
  [/^([\d.,]+) yếu tố \+ · ([\d.,]+) yếu tố −$/u, '$1 factors + · $2 factors −'],
  [/^([\d.,]+) đ · (OTM|ATM|ITM)$/u, '$1 VND · $2'],
  [/^([A-Z]{2,6}) · (OTM|ATM|ITM) · ([\d.,]+) ngày$/u, '$1 · $2 · $3 days'],
  /* cụm danh từ — dài trước, ngắn sau */
  W('Độ phủ giao dịch', 'Trading coverage'),
  W('độ phủ giao dịch', 'trading coverage'),
  W('Độ phủ phiên', 'Session coverage'),
  W('độ phủ phiên', 'session coverage'),
  W('Độ phủ trung vị', 'Median coverage'),
  W('Phủ từ niêm yết', 'Coverage since listing'),
  W('Độ sâu thị trường', 'Market depth'),
  W('độ sâu thị trường', 'market depth'),
  W('Giá trị giao dịch', 'Traded value'),
  W('giá trị giao dịch', 'traded value'),
  W('Giá trị lưu hành', 'Outstanding value'),
  W('giá trị lưu hành', 'outstanding value'),
  W('Khối lượng phiên', 'Session volume'),
  W('khối lượng phiên', 'session volume'),
  W('Số lệnh', 'Trades'),
  W('số lệnh', 'trades'),
  W('TB/lệnh', 'avg/trade'),
  W('GT/phiên', 'value/session'),
  W('GT giao dịch TB', 'avg traded value'),
  W('Phiên trắng', 'No-trade sessions'),
  W('Phiên dữ liệu', 'Data session'),
  W('Biên độ HL', 'High-low range'),
  W('Tác động giá', 'Price impact'),
  W('trung vị', 'median'),
  W('Trung vị', 'Median'),
  W('vũ trụ', 'universe'),
  W('Vũ trụ', 'Universe'),
  W('cổ phiếu cơ sở', 'underlying'),
  W('Cổ phiếu cơ sở', 'Underlying'),
  W('tổ chức phát hành', 'issuer'),
  W('Tổ chức phát hành', 'Issuer'),
  W('khuyến nghị', 'recommendation'),
  W('Khuyến nghị', 'Recommendation'),
  W('đáo hạn', 'maturity'),
  W('Đáo hạn', 'Maturity'),
  W('phiên', 'sessions'),
  W('Phiên', 'Session'),
  W('ngày', 'days'),
  W('cảnh báo', 'alert'),
  W('Cảnh báo', 'Alert'),
  W('quan sát', 'observations'),
  W('mã', 'ticker'),
  W('điểm', 'score'),
  W('giá', 'price'),
  W('thanh khoản', 'liquidity'),
  W('Thanh khoản', 'Liquidity'),
  W('động lượng', 'momentum'),
  W('tăng', 'up'),
  W('giảm', 'down'),
  W('triệu', 'm'),
  W('tỷ', 'bn'),
  W('so với', 'vs'),
  W('trên', 'above'),
  W('dưới', 'below'),
  W('còn lại', 'left'),
  W('tối thiểu', 'minimum'),
  W('tối đa', 'maximum'),
  W('từ niêm yết', 'since listing'),
  W('niêm yết', 'listing'),
  W('đã đáo hạn', 'matured'),
  W('chưa đủ dữ liệu', 'not enough data'),
  W('đang giao dịch', 'trading'),
  W('thay đổi', 'change'),
  W('xếp thứ', 'ranks'),
  W('tỷ lệ', 'ratio'),
  W('giá trị', 'value'),
  W('khối lượng', 'volume'),
  W('độ phủ', 'coverage'),
  W('chỉ số', 'metric'),
  W('nguồn', 'source'),
  W('cập nhật', 'updated'),
  W('không phải', 'not'),
  W('thoả điều kiện', 'matching'),
  W('điều kiện', 'conditions'),
  W('nhóm', 'group'),
  W('tổng', 'total'),
  W('còn lại', 'left'),
  W('còn', 'left'),
  W('tới', 'to'),
  W('trước', 'ago'),
  W('mỗi', 'every'),
  W('hoà vốn', 'break-even'),
  W('thực tế', 'actual'),
  W('dự báo', 'forecast'),
  W('xác suất', 'probability'),
  W('biến động', 'volatility'),
  W('rủi ro', 'risk'),
  W('lợi nhuận', 'P&L'),
  W('thời gian', 'time'),
  W('cao', 'high'),
  W('thấp', 'low'),
  W('tốt', 'good'),
  W('xấu', 'poor'),
  W('của', 'of'),
  W('và', 'and'),
  W('hoặc', 'or'),
  W('với', 'with'),
];

/* Cụm lý do trong rec_reason (nối bằng "; ") */
const REASONS = {
  'giá trị giao dịch bình quân thấp': 'average traded value too low',
  'thanh khoản chưa đạt chuẩn': 'liquidity below the required standard',
  'thanh khoản thấp': 'low liquidity',
  'IV quá cao so với biến động lịch sử': 'IV far above historical volatility',
  'biên độ giá quá rộng': 'price range too wide',
  'lịch sử giao dịch quá ngắn': 'trading history too short',
  'chất lượng dữ liệu thấp': 'low data quality',
  'thời gian tới đáo hạn quá ngắn': 'too little time to maturity',
};

function translateList(why) {
  return why.split(';').map((part) => {
    const key = part.trim();
    return REASONS[key] || phrase(key) || key;
  }).join('; ');
}

function phrase(text) {
  let out = text;
  for (const [re, rep] of PHRASE_RULES) {
    out = out.replace(re, rep);
  }
  if (out === text) return null;
  // Chỉ nhận bản dịch đã "sạch" tiếng Việt: thà giữ nguyên câu gốc còn hơn
  // trả về câu nửa Việt nửa Anh khó đọc.
  if (/[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]/i.test(out)) return null;
  return out;
}

/* ---------------------------------------------------------------
   4. TRA CỨU + ÁP DỤNG LÊN DOM
   --------------------------------------------------------------- */
export function translateText(text) {
  if (!text) return null;
  const key = text.trim();
  if (!key) return null;
  if (Object.prototype.hasOwnProperty.call(STRINGS, key)) return STRINGS[key];
  for (const [re, fn] of TEMPLATES) {
    const m = key.match(re);
    if (m) {
      try { return fn(...m.slice(1)); } catch { return null; }
    }
  }
  // Nhiều khối văn bản được ghép từ 2–3 câu: dịch từng câu rồi nối lại.
  if (key.length > 24 && key.length <= 480) {
    const parts = key.split(/(?<=\.)\s+/u).filter(Boolean);
    if (parts.length > 1) {
      const done = parts.map((p) => translateText(p));
      if (done.every(Boolean)) return done.join(' ');
    }
  }
  if (key.length <= 60) return phrase(key);
  return null;
}

const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'CANVAS', 'TEXTAREA', 'CODE', 'PRE',
  'SELECT', 'KBD', 'SAMP', 'SVG', 'PATH']);
const SKIP_CLASS = new Set(['i18n-en', 'i18n-skip']);
const origTextSnapshot = new Map();
const addedNodes = new Set();
let applying = false;
let observer = null;

function eligible(node) {
  const parent = node.parentElement;
  if (!parent || SKIP_TAGS.has(parent.tagName)) return false;
  if (parent.closest('[data-no-i18n], .i18n-skip')) return false;
  for (const c of parent.classList) if (SKIP_CLASS.has(c)) return false;
  return true;
}

function applyNode(node) {
  const raw = node.nodeValue;
  if (!raw || !raw.trim()) return;
  const lead = raw.match(/^\s*/)[0];
  const trail = raw.match(/\s*$/)[0];
  const core = raw.trim();
  const en = translateText(core);
  if (!en || en === core) return;
  remember(node, raw);
  if (lang === 'en') {
    node.nodeValue = lead + en + trail;
    return;
  }
  if (lang !== 'both') return;
  // Trong bảng, chỉ dịch song song ở header: thêm chữ vào từng ô sẽ làm bảng rối.
  if (node.parentElement?.tagName === 'TD') return;
  /* both: giữ tiếng Việt, thêm bản dịch ngay sau — chỉ với nhãn ngắn để câu
     không bị vỡ khi chuỗi gốc bị chia nhỏ bởi thẻ inline. */
  if (core.length > 48) return;
  if (node.nextSibling && node.nextSibling.nodeType === 1 && node.nextSibling.classList.contains('i18n-en')) return;
  const span = document.createElement('span');
  span.className = 'i18n-en';
  span.lang = 'en';
  span.textContent = ' · ' + en;
  node.parentNode.insertBefore(span, node.nextSibling);
  addedNodes.add(span);
}

function applyAttrs(root) {
  const nodes = root.querySelectorAll('[placeholder], [title], [aria-label]');
  for (const el of nodes) {
    for (const attr of ['placeholder', 'title', 'aria-label']) {
      const v = el.getAttribute(attr);
      if (!v) continue;
      const storeKey = 'data-en-' + attr;
      if (!el.hasAttribute(storeKey)) el.setAttribute(storeKey, v);
      const base = el.getAttribute(storeKey);
      const en = translateText(base);
      if (!en) continue;
      el.setAttribute(attr, lang === 'en' ? en : base);
    }
  }
}

export function applyI18n(root = document.body) {
  if (!root || applying) return;
  applying = true;
  if (observer) observer.takeRecords();
  try {
    if (root.nodeType === 3) { applyNode(root); }
    else {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      const batch = [];
      let n;
      while ((n = walker.nextNode())) if (eligible(n)) batch.push(n);
      batch.forEach(applyNode);
      applyAttrs(root);
    }
  } finally {
    applying = false;
    if (observer) observer.takeRecords();
  }
}

function resetI18n() {
  for (const [node, original] of origTextSnapshot) {
    if (node.isConnected) node.nodeValue = original;
  }
  origTextSnapshot.clear();
  for (const span of addedNodes) if (span.isConnected) span.remove();
  addedNodes.clear();
  document.querySelectorAll('[data-en-placeholder], [data-en-title], [data-en-aria-label]').forEach((el) => {
    for (const attr of ['placeholder', 'title', 'aria-label']) {
      const saved = el.getAttribute('data-en-' + attr);
      if (saved) el.setAttribute(attr, saved);
    }
  });
}

function remember(node, raw) {
  if (!origTextSnapshot.has(node)) origTextSnapshot.set(node, raw);
}

export function getLang() { return lang; }

/** Chọn chuỗi theo ngôn ngữ hiện tại cho nội dung sinh động trong page. */
export function bi(vi, en) { return lang === 'en' ? en : vi; }

export function setLang(next) {
  const value = next === 'en' || next === 'both' ? next : 'vi';
  if (value === lang) return;
  lang = value;
  try { localStorage.setItem(KEY_LANG, value); } catch { /* private mode */ }
  document.documentElement.lang = value === 'vi' ? 'vi' : 'en';
  document.documentElement.dataset.lang = value;
  resetI18n();
  applyI18n(document.body);
  syncLangButtons();
  window.dispatchEvent(new CustomEvent('cwintel:lang', { detail: { lang: value } }));
}

export function onLangChange(fn) {
  window.addEventListener('cwintel:lang', (e) => fn(e.detail.lang));
}

function syncLangButtons() {
  document.querySelectorAll('[data-lang-set]').forEach((b) => {
    const on = b.dataset.langSet === lang;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}

export function initI18n() {
  document.documentElement.lang = lang === 'en' ? 'en' : 'vi';
  document.documentElement.dataset.lang = lang;
  document.querySelectorAll('[data-lang-set]').forEach((b) => {
    b.addEventListener('click', () => setLang(b.dataset.langSet));
  });
  syncLangButtons();
  applyI18n(document.body);
  observer = new MutationObserver(() => {
    if (applying) return;
    window.clearTimeout(initI18n._t);
    initI18n._t = window.setTimeout(() => applyI18n(document.body), 60);
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
