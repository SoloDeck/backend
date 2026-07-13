# Nhật ký sửa Backend — Huynh

> Tôi (**Huynh**) ghi lại ở đây mọi thay đổi mình thực hiện trong repo backend, để ai review cũng biết tôi đã đụng vào cái gì và vì sao.
>
> **Quy ước tôi tự đặt:**
> - Không commit thẳng lên `main` — luôn tách nhánh `<type>/<scope>` trước (theo `AGENTS.md`).
> - `contracts/openapi.yaml` đã khai gì thì tôi làm theo, không tự chế. Muốn đổi shape thì để contract-keeper sửa file đó trước.
> - Mọi comment tôi thêm vào code đều kết thúc bằng `#Huynh`.
> - Mỗi lần sửa = **một mục ngắn** bên dưới, mới nhất lên đầu.

---

## 2026-07-12 · 22:10 — Sửa `GET /proposals/{id}/pdf` trả 500

**Nhánh:** `fix/lead-qualifier-json-parse`

**Vấn đề:** Xuất PDF báo giá **500 với mọi báo giá do frontend tạo hoặc sửa**.

Điều tôi phát hiện làm lật ngược kết luận ban đầu: **frontend làm ĐÚNG hợp đồng, backend mới là bên sai.**

`contracts/openapi.yaml` (dòng 5511) **chính thức khai** `ProposalContentDTO` với đúng shape mà frontend lưu:
```
{title, executive_summary, scope_of_work: str, timeline: {...}, pricing: {...}, terms: {payment_terms}, notes}
```

Nhưng `generate_pdf` lại index cứng một shape **không hề có trong hợp đồng** — shape nội bộ của AI:
```python
project_overview=proposal.content["project_overview"],   # ← [...] chứ không .get()
deliverables=proposal.content["deliverables"],
```

Thiếu **một** khoá là `KeyError` → **500**. Mà `content` khai là `dict` trần nên backend không validate gì: PATCH vẫn 200, mãi tới lúc render PDF mới nổ.

**Sửa:**

| File | Sửa gì |
|---|---|
| `src/modules/proposals/application/pdf_content.py` *(mới)* | `build_proposal_document()` — đọc được **cả hai shape**, ưu tiên shape của hợp đồng. Dùng `.get()` khắp nơi: thiếu dữ liệu thì để trống chứ không nổ. Chuyển `pricing`/`timeline` dạng object thành văn bản đọc được |
| `src/modules/proposals/application/service.py` | `generate_pdf()` dùng hàm trên thay vì index cứng |
| `tests/unit/modules/proposals/test_pdf_content.py` *(mới)* | 5 test: shape hợp đồng, shape AI, thiếu khoá, content rỗng, `content=None` |

**Kiểm chứng:**

```
docker compose run --rm test python -m pytest tests/unit/ -q   → 197 passed
uv run ruff check ... / uv run mypy ...                         → sạch
```

Gọi thật `GET /proposals/{id}/pdf` với **3 ca**, cả 3 đều **200 + `%PDF`**:
- shape hợp đồng (frontend lưu) — *trước đây: 500 `KeyError: 'project_overview'`*
- shape AI — *vẫn phải chạy, không được làm hỏng*
- `content` rỗng `{}` — *trước đây: 500*

Bên frontend đã **bật lại nút "Tải PDF"** (trước phải làm mờ kèm nhãn "Chờ BE"). Drive thật trên giao diện: file `bao-gia-nguyen-van-a.pdf` tải về được.

**Không đổi shape API** → không đụng `openapi.yaml`.

**Ghi chú cho contract-keeper:** `/proposals/ai-generate` đang lưu shape nội bộ của AI (`project_overview`, `deliverables`...) vào cột `content`, trong khi hợp đồng khai `content` là `ProposalContentDTO`. Tức là **chính endpoint đó đang vi phạm hợp đồng**. Tôi không sửa vì đụng vào đó là đổi hành vi của một endpoint đang chạy — cần thống nhất trước.

---

## 2026-07-12 · 21:05 — Sửa `/proposals/ai-generate` trả 500 mọi lúc

**Nhánh:** `fix/lead-qualifier-json-parse` (làm tiếp trên cùng nhánh — cùng gốc: di trú Groq làm dở dang)

**Vấn đề:** Endpoint AI báo giá **500 mọi lúc**, không liên quan API key. Tôi tìm ra **ba lỗi chồng lên nhau**:

1. **Sai client.** `modules/proposals/api/router.py` và `shared/dependencies/ai.py` dựng `genai.Client` (Gemini) rồi đưa vào `ProposalGenerationService` — vốn gọi `client.chat.completions.create` (cú pháp Groq). Gemini client không có `.chat` → `AttributeError` → 500. Cuộc di trú sang Groq đã sửa `lead_qualifier` nhưng **bỏ sót đúng route frontend đang gọi**.
2. **Cùng bug parser.** `ProposalGenerationService._clean_response()` cũng chỉ cắt fence khi cả chuỗi bắt đầu bằng ` ``` ` — y hệt `lead_qualifier`. Sửa client mà quên cái này thì báo giá vẫn chết.
3. **Model trả sai kiểu.** Sau khi sửa 2 lỗi trên, endpoint **lúc được lúc 500**: llama-4-scout thỉnh thoảng trả `pricing` dạng **object** (`{"total": "50.000.000 VND", ...}`) trong khi schema khai `pricing: str` → `ValidationError`. Prompt **đã** yêu cầu chuỗi, model chỉ đơn giản là phớt lờ.

**Sửa:**

| File | Sửa gì |
|---|---|
| `src/ai/shared/json_output.py` *(mới)* | Tách hàm `extract_json_object()` dùng chung. Trước đây logic bóc JSON viết ở 2 nơi — sửa nơi này quên nơi kia, **đúng cái đã gây ra bug này** |
| `src/ai/lead_qualifier/chain.py` | Dùng hàm chung thay bản riêng |
| `src/ai/proposal_generator/application/service.py` | Bỏ `_clean_response()`, dùng hàm chung. Thêm `response_format={"type": "json_object"}` |
| `src/modules/proposals/api/router.py` | `genai.Client` → `Groq` |
| `src/shared/dependencies/ai.py` | `genai.Client` → `Groq` (worker Celery lấy facade từ đây) |
| `src/ai/proposal_generator/schemas/proposal_content.py` | Thêm `field_validator(mode="before")` ép kiểu — chịu được khi model trả object thay vì chuỗi |
| `tests/unit/ai/shared/test_json_output.py` *(mới)* | 9 test cho hàm bóc JSON |
| `tests/unit/ai/proposal_generator/test_proposal_content.py` *(mới)* | 5 test, có 1 test tái hiện **đúng ca `pricing` là object đã gây 500** |

**Kiểm chứng:**

```
docker compose run --rm test python -m pytest tests/unit/ai/ -q   → 32 passed
uv run ruff check src/ai tests/unit/ai                             → All checks passed
uv run mypy src/ai/...                                             → Success: no issues
```

Gọi `POST /proposals/ai-generate` **5 lần liên tiếp**: **5/5 đều HTTP 201**, mỗi lần ~1,4s. (Trước: 500 mọi lúc. Sau khi chỉ sửa client: lúc được lúc 500.)

**Không đổi shape API.** `ProposalContent` là schema **nội bộ của AI** — `openapi.yaml` khai `ProposalContentDTO` là shape khác, dành cho frontend. Đầu ra vẫn đúng kiểu như cũ, chỉ đầu vào được nới lỏng.

---

## 2026-07-12 · 20:40 — Sửa `lead_qualifier` vứt bỏ kết quả AI

**Nhánh:** `fix/lead-qualifier-json-parse` ← `main` @ `1f4a935`

**Vấn đề:** AI chấm điểm lead **chưa bao giờ chạy được**, job luôn `failed` — dù `GROQ_API_KEY` hợp lệ và Groq trả về **HTTP 200 với kết quả đúng**. Nguyên nhân: model `llama-4-scout` thêm câu dẫn *"Here is the draft qualification result:"* trước JSON, mà `_parse_output` chỉ cắt code fence khi **cả chuỗi bắt đầu bằng** ` ``` ` → `json.loads` vỡ → retry 3 lần → luôn thất bại.

**Sửa:**

| File | Sửa gì |
|---|---|
| `src/ai/lead_qualifier/chain.py` | `_call_groq()`: thêm `response_format={"type": "json_object"}` — buộc Groq trả JSON thuần (phòng tuyến chính) |
| `src/ai/lead_qualifier/chain.py` | `_parse_output()`: tìm khối `{...}` ở bất kỳ đâu trong câu trả lời (phòng tuyến dự phòng). Dùng regex **greedy** có chủ đích — non-greedy sẽ cắt cụt object lồng nhau |
| `tests/unit/ai/lead_qualifier/test_chain.py` | Thêm 5 test, có 1 test tái hiện **đúng chuỗi thật đã làm hỏng production** |

**Kiểm chứng:**

```
docker compose run --rm test python -m pytest tests/unit/ai/lead_qualifier/ -q   → 18 passed
uv run ruff check src/ai/lead_qualifier/                                          → All checks passed
uv run mypy src/ai/lead_qualifier/chain.py                                        → Success: no issues
```

Chạy AI thật qua `POST /ai/jobs`: **`failed` sau ~50s → `succeeded` sau 4s**. Điểm 80, mức HOT, khoảng giá 40–70 triệu.

**Không đổi shape API** → không đụng `openapi.yaml`, frontend không phải sửa gì.

**Cố ý KHÔNG sửa:** mã lỗi `AI_QUOTA_EXCEEDED` đang bị gán nhầm cho lỗi parse (`errors.py:36`) — rất dễ khiến người debug đi kiểm tra hoá đơn Groq thay vì nhìn vào parser. Nhưng `openapi.yaml` **liệt kê cứng** danh sách mã lỗi, nên thêm `AI_OUTPUT_INVALID` là đổi hợp đồng → phải để contract-keeper làm trước. Ghi lại để xử lý ở PR riêng.

---

## Lỗi backend tôi đã phát hiện nhưng chưa sửa

Ghi ra để lưu vết, không phải bỏ qua. Chi tiết đầy đủ (cách tái hiện + bằng chứng) ở `web/docs/BACKEND_REQUESTS.md`.

| Lỗi | Vì sao chưa sửa |
|---|---|
| `POST /proposals/ai-generate` **500 mọi lúc** — `modules/proposals/api/router.py:59` tạo `genai.Client` (Gemini) rồi đưa vào service gọi `.chat.completions` (cú pháp Groq) → `AttributeError` | Di trú sang Groq làm dở dang; phạm vi rộng hơn (cả `shared/dependencies/ai.py`) |
| `GET /proposals/{id}/pdf` **500** với mọi báo giá do FE tạo — BE index cứng 7 khoá theo shape AI, FE lưu shape khác | Phải thống nhất hợp đồng `content` trước |
| Mã lỗi `AI_QUOTA_EXCEEDED` gán sai cho lỗi parse | Cần contract-keeper thêm mã mới vào `openapi.yaml` |
| `SMTP_HOST=localhost` trong `.env.example`, `compose.yml` không ghi đè → **email chết** khi chạy Docker | Sửa hạ tầng, để PR riêng |
| Swagger lệch code — 24 endpoint trên Swagger trả 404, 7 endpoint có thật không được khai | Vấn đề kiến trúc: `main.py` serve YAML tĩnh thay vì schema sinh từ code |
