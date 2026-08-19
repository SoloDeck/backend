# Lead Qualifier — Cách chấm điểm (Scoring Rubric)

> Tài liệu này trả lời bốn câu hỏi hay bị hỏi khi bảo vệ:
> **(1) Chấm điểm theo tiêu chí nào?** · **(2) Vì sao có con điểm đó?** ·
> **(3) Vì sao MẤT phần điểm còn lại?** · **(4) Làm sao để lên 100?**
> Đối chiếu code: `src/ai/lead_qualifier/scoring.py` (trọng số + ngưỡng + barem) và
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

**Backend ÉP mức rời rạc, không chỉ nhờ prompt.** Prompt cấm chấm số nằm giữa, nhưng prompt
là *lời khuyên*. `snap_to_level()` kéo mọi số lẻ về nấc dưới trước khi cộng — model chấm 22
cho `scope` thì backend tính 20. Làm tròn **XUỐNG** để cùng luật với phần chống phồng điểm:
thà chấm thấp rồi đi hỏi khách, còn hơn chấm hào phóng rồi báo giá mù.

*Nếu không có bước này:* cả lập luận "thang điểm tái lập được" chỉ đứng trên thiện chí của
model, và hội đồng hỏi "lấy gì đảm bảo" thì không có câu trả lời.

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

## 7. Vì sao MẤT điểm — và làm sao lên 100

Hai câu "vì sao được 27 điểm" và "vì sao **không** được 73 điểm còn lại" là **hai câu khác
nhau**, và chúng đến từ **hai nguồn khác nhau**:

| | Nguồn | Bảo đảm gì |
|---|---|---|
| **Được điểm** | AI đọc yêu cầu khách, trích `evidence` | Mỗi điểm truy được về một câu khách đã nói |
| **Mất điểm** | **Code tra bảng barem** (`RUBRIC_LEVELS`) | Luôn có, luôn đúng, không phụ thuộc AI |

Vì mỗi tiêu chí chỉ có vài nấc và mỗi nấc có điều kiện viết sẵn (bảng mục 4), hệ thống
**tra bảng ra được** phần thiếu. `explain_gap(key, points)` trả về:

```
Ngân sách  0/25  →  lost_points   : 25
                    current_state : "Khách chưa nhắc gì tới tiền."
                    steps         : [ 15đ (+15) nếu khách nói ước lượng về tiền
                                      25đ (+25) nếu khách nêu CON SỐ ngân sách ]
                    fill_field    : "client_budget"   ← ô để ghi lại khi hỏi được
```

`build_gap_summary()` gộp cả 5 tiêu chí, **sắp giảm dần theo số điểm mất** (hỏi một câu về
ngân sách được 25 điểm, làm rõ bối cảnh chỉ được 10 — thứ tự đó phải nhìn thấy ngay), kèm:

- `lost_points` — tổng còn thiếu so với 100.
- `points_to_hot` — còn bao nhiêu nữa mới đạt HOT.
- `essential_missing` — tiêu chí **thiết yếu** chưa đạt trần. Còn tên nào trong đây thì chắc
  chắn chưa thể HOT, vì HOT = 75 = đúng tổng ba tiêu chí ấy.

**Câu hỏi gửi khách.** Mỗi khoảng thiếu kèm một câu freelancer copy được và nhắn thẳng cho
khách. AI viết cho bám dự án ("Shop mình dự trù bao nhiêu cho phần website bán vợt ạ?"); AI
trả thiếu thì rơi về câu mẫu trong `DEFAULT_ASK`. Ô "nên hỏi gì" **không bao giờ được trống**
— đó chính là việc tiếp theo người dùng cần làm.

**Không lưu xuống database.** Gap suy ra thuần tuý từ `(tiêu chí, điểm)`, nên
`LeadScoreHistoryResponse.score_gaps` tính lại lúc đọc. Nhờ vậy bản đánh giá **cũ** — lưu từ
trước khi có tính năng này — mở lại vẫn hiện đủ phần thiếu, và không có bản sao nào để có
ngày lệch với barem.

## 8. Chốt bản đánh giá chưa đủ 100 điểm

Điểm đo **độ rõ của yêu cầu khách**, mà freelancer có quyền quyết định làm việc với một yêu
cầu chưa rõ. Nên hệ thống **cảnh báo, không chặn** — việc của nó là bảo đảm người dùng biết
mình đang đánh đổi gì:

| Điểm | Khi bấm "Lưu đánh giá" |
|---|---|
| **100** | Chốt thẳng |
| **75 – 99** | Nhắc nhẹ: ba mảng thiết yếu đã đủ, phần thiếu chỉ làm báo giá sắc hơn |
| **< 75** | Cảnh báo nặng, nêu đích danh mảng thiết yếu đang thiếu, **phải tích ô xác nhận** mới chốt được |

Ngưỡng chia ở **75** không phải số chọn cho tròn — đó đúng là ranh giới "có đủ ba thứ cốt lõi
để báo giá hay chưa".

Chốt ở mức thiếu điểm thì `lead_scores.gap_acknowledged = true`. Số điểm thiếu suy lại được
từ `breakdown`, nhưng việc **có được cảnh báo** thì không suy ra từ đâu — không lưu thì nhìn
một bản 27/100 đã chốt sẽ không phân biệt được *hệ thống để lọt* với *người dùng biết rõ và
tự chịu trách nhiệm*.

## 9. Vòng khép kín: bổ sung → chấm lại → so sánh

Biết mình thiếu gì mà không có chỗ ghi thì luồng vẫn đứt. Trước đây đúng như vậy: hỏi được
khách ngân sách xong, ô duy nhất liên quan tới tiền trên màn sửa deal là "Giá trị dự kiến" —
đúng ô **bị cấm chấm điểm**, điền vào đó thì chấm lại vẫn 0 điểm ngân sách.

`fill_field` của mỗi khoảng thiếu chỉ thẳng ô cần điền:

| Tiêu chí thiếu | Ô | Cột |
|---|---|---|
| budget | "Ngân sách khách nêu" | `deals.client_budget` *(mới)* |
| timeline | "Mốc thời gian khách nêu" | `deals.desired_timeline` |
| scope / detail / context | "Bổ sung nội dung yêu cầu" | nối thêm vào `deals.notes` |

`deals.client_budget` ghi lại **lời khách**, nên nó nằm trong **KHỐI 1** của
`_build_inquiry_context` và **được chấm điểm** — khác hẳn `estimated_value` là phỏng đoán của
freelancer, vẫn nằm ở khối cấm.

Điền xong thì chấm lại, và màn hình so hai lần chấm gần nhất: **"27 → 72 (+45) · Ngân sách
+25 · Thời gian +20"**. Đây là thứ chứng minh vòng lặp có tác dụng thật, thay vì một con số
tĩnh người dùng phải tin.

## 10. Nghề của freelancer (profession) ảnh hưởng gì

Khi biết nghề của freelancer (xem `users.profession`), hệ thống dùng nó để:

1. **Ước giá đúng nghề** — `price_range` neo theo giá thị trường của *đúng* nghề
   (designer, lập trình, nhiếp ảnh… giá rất khác nhau), thay vì đoán mò từ mô tả.
2. **Cảnh báo scam theo nghề** — mỗi nghề có kiểu lừa đặc thù (xem
   `src/modules/intake_form/professions.py`), đưa vào `red_flags` để nhắc freelancer.

Nghề **KHÔNG** làm phồng hay tụt điểm readiness — điểm vẫn chấm theo độ rõ của yêu cầu.

## 11. Tóm tắt để trả lời hội đồng

- Chấm theo **5 tiêu chí cố định** (scope/budget/timeline/detail/context), trọng số
  phản ánh mức độ mỗi yếu tố quyết định việc **báo giá được**.
- **AI map** yêu cầu vào rubric (chọn mức + trích bằng chứng), **backend cộng** — tách
  bạch, không để AI tự quyết con số cuối.
- **Tái lập được**: mức rời rạc + backend ép về nấc + `temperature=0` + `seed=42`.
- **Minh bạch**: mỗi điểm có `reason` + `evidence` trích từ dữ liệu thật; 0 điểm thì
  bằng chứng phải null.
- **Giải thích được cả phần MẤT điểm**: tra bảng barem, không phải AI phán — nói rõ mất bao
  nhiêu, đang ở nấc nào, lên nấc trên cần gì, và nên hỏi khách câu gì.
- **Khép kín**: hỏi được khách thì có ô để ghi, ghi xong chấm lại thấy điểm tăng bao nhiêu.
- **Có trách nhiệm**: chốt bản chưa đủ điểm thì bị cảnh báo, và hệ thống lưu lại là người
  dùng đã được cảnh báo.
