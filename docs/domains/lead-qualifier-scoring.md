# Lead Qualifier — Cách chấm điểm (Scoring Rubric)

> Tài liệu này trả lời hai câu hỏi hay bị hỏi khi bảo vệ:
> **(1) Chấm điểm theo tiêu chí nào?** và **(2) Vì sao có con điểm đó?**
> Đối chiếu code: `src/ai/lead_qualifier/scoring.py` (trọng số + ngưỡng) và
> `src/ai/lead_qualifier/prompts/system.txt` (mức điểm + luật chấm).

## 1. Điểm này ĐO GÌ

Điểm Lead Qualifier đo đúng **một** thứ:

> **"Yêu cầu của khách đã đủ rõ để freelancer BÁO GIÁ chính xác chưa?"**

Nó **KHÔNG** đo khách có đáng tin không, có trả tiền không — dữ liệu đầu vào (mô tả
yêu cầu) không chứa thông tin đó, suy ra là bịa. Điểm **thấp** nghĩa là *"cần hỏi thêm
khách"*, **không** phải *"deal xấu"*.

## 2. Năm tiêu chí và VÌ SAO có trọng số đó

Thang 100 điểm, chia cho 5 tiêu chí. **Trọng số = mức độ yếu tố đó quyết định việc
ra được một báo giá đúng.**

| Tiêu chí | Trọng số | Vì sao trọng số này |
|---|---:|---|
| **scope** — phạm vi công việc | **30** | Không biết **LÀM GÌ** thì **không thể báo giá**. Scope là nền của mọi con số → nặng nhất vì nó *chặn* việc báo giá. |
| **budget** — ngân sách | **25** | Biết ngân sách → biết deal **khả thi không** + báo giá *premium hay lean*, đỡ hỏi tới lui. Quyết định "có nên theo" và neo giá. |
| **timeline** — thời gian | **20** | Ảnh hưởng **giá** (gấp = phụ phí) và **có nhận nổi không**. Vẫn báo giá được nếu giả định timeline chuẩn → nhẹ hơn budget. |
| **detail** — mức độ chi tiết | **15** | Làm **sắc** báo giá + chống phình scope, nhưng chỉ *tinh chỉnh* scope đã có, không định nghĩa nó. |
| **context** — bối cảnh & kênh | **10** | Ngành/quy mô/kênh — giúp cá nhân hoá + tạo thiện cảm, **ít dính trực tiếp tới con số** → nhẹ nhất. |
| | **= 100** | |

### Cấu trúc trọng số có logic, không phải số ngẫu nhiên

- **Top 3 (scope + budget + timeline = 75)** = *"báo giá được hay chưa"* — nhóm **thiết yếu**.
- **Bottom 2 (detail + context = 25)** = *"báo giá tốt tới đâu"* — nhóm **tinh chỉnh**.

Và **ngưỡng HOT = 75 = đúng tổng ba tiêu chí thiết yếu**. Nghĩa là:

> **HOT ⇔ có đủ ba thứ cốt lõi (biết làm gì + ngân sách + thời gian) để báo giá tự tin.**

Đây là câu trả lời mạnh nhất cho *"vì sao có con điểm đó"*: cả rubric ăn khớp với nhau.

## 3. Vì sao mức điểm RỜI RẠC (không cho dải, không cho số lẻ)

Mỗi tiêu chí chỉ nhận **một** trong vài giá trị cố định (xem bảng mục 4), **không** được
chọn số nằm giữa (không "22", không "+0.5").

**Lý do:** thang điểm phải **LẶP LẠI ĐƯỢC** — cùng một deal chấm hai lần phải ra **cùng
một số**. Cho một dải ("20–25") hoặc cho cộng/trừ lẻ tự do là mời model chọn bừa → chấm
lại ra số khác → con số mất ý nghĩa. Kết hợp với `temperature=0` + `seed=42` (xem
`chain.py`), hệ thống cho kết quả **tái lập được** — một điểm mạnh khi bảo vệ.

## 4. Bảng mức điểm từng tiêu chí

| Tiêu chí | Mức & điều kiện |
|---|---|
| **scope** | **30** nói rõ làm gì, bao nhiêu hạng mục, bàn giao gì · **20** biết loại việc + vài hạng mục nhưng chưa đủ báo giá chắc · **12** CHỈ có tên dự án · **0** không hiểu phải làm gì |
| **budget** | **25** nêu CON SỐ cụ thể · **15** chỉ ngụ ý ("vài chục triệu") · **0** không đề cập tiền |
| **timeline** | **20** mốc cụ thể ("trước 30/09") · **10** mơ hồ ("càng sớm càng tốt") · **0** không đề cập |
| **detail** | **15** mô tả kỹ, có ràng buộc cụ thể · **8** sơ sài một hai câu · **0** không mô tả / mô tả rác |
| **context** | **10** rõ ngành/quy mô/hiện trạng/kênh · **5** biết một phần · **0** không có |

## 5. Cộng tổng và phân loại HOT / WARM / COLD

- **AI KHÔNG cộng tổng.** Nó chấm từng tiêu chí (kèm lý do + bằng chứng); **backend**
  cộng lại (`compute_readiness` trong `scoring.py`). Không giao phép cộng cho LLM vì
  chúng làm toán ẩu.
- Nhãn suy ra **TỪ** điểm tổng (không để AI tự dán nhãn rồi tra ngược):

| Tổng điểm | Nhãn | Ý nghĩa |
|---|---|---|
| **≥ 75** | **HOT** | Có đủ 3 tiêu chí thiết yếu → báo giá tự tin |
| **45 – 74** | **WARM** | Thiếu một mảng thiết yếu → hỏi thêm rồi báo giá |
| **< 45** | **COLD** | Thiếu nền (thường là scope) → cần làm rõ nhiều |

## 6. "reason" và "evidence" — hai thứ KHÁC nhau

Mỗi tiêu chí trả về `{points, reason, evidence}`:

- **reason** = *nhận xét* của AI: vì sao được ngần này điểm. VD: "Khách nêu mốc bàn giao cụ thể."
- **evidence** = *dữ kiện THẬT* khách đã nói, trích nguyên (giữ con số/ngày). VD: "Bàn giao trước 30/09/2026."

Nếu khách không nhắc tới tiêu chí đó → `evidence = null`, **tuyệt đối không bịa**. Đây là
cơ chế **chống AI phán bừa**: mỗi con số phải trích được ra một câu chứng minh từ dữ liệu
thật; không trích được thì phải chấm 0.

## 7. Nghề của freelancer (profession) ảnh hưởng gì

Khi biết nghề của freelancer (xem `users.profession`), hệ thống dùng nó để:

1. **Ước giá đúng nghề** — `price_range` neo theo giá thị trường của *đúng* nghề
   (designer, lập trình, nhiếp ảnh… giá rất khác nhau), thay vì đoán mò từ mô tả.
2. **Cảnh báo scam theo nghề** — mỗi nghề có kiểu lừa đặc thù (xem
   `src/modules/intake_form/professions.py`), đưa vào `red_flags` để nhắc freelancer.

Nghề **KHÔNG** làm phồng hay tụt điểm readiness — điểm vẫn chấm theo độ rõ của yêu cầu.

## 8. Tóm tắt để trả lời hội đồng

- Chấm theo **5 tiêu chí cố định** (scope/budget/timeline/detail/context), trọng số
  phản ánh mức độ mỗi yếu tố quyết định việc **báo giá được**.
- **AI map** yêu cầu vào rubric (chọn mức + trích bằng chứng), **backend cộng** — tách
  bạch, không để AI tự quyết con số cuối.
- **Tái lập được**: mức rời rạc + `temperature=0` + `seed=42`.
- **Minh bạch**: mỗi điểm có `reason` + `evidence` trích từ dữ liệu thật; 0 điểm thì
  bằng chứng phải null.
