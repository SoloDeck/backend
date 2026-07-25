"""LeadQualifier Groq chain."""

import asyncio
import json
from typing import Any

import structlog
from groq import Groq

from src.ai.shared.base import BaseAIChain
from src.ai.shared.json_output import extract_json_object
from src.ai.shared.prompt import load_prompt, prompt_version
from src.ai.shared.token_usage import extract_usage
from src.config.settings import settings
from src.shared.exceptions.domain import AIOutputParseError

log = structlog.get_logger()

MODEL = "llama-3.3-70b-versatile"


def build_qualifier_prompt(
    prompt_template: str,
    inquiry_text: str,
    profession: str | None = None,
    scam_hint: str | None = None,
    retrieved_knowledge: str | None = None,
) -> str:
    """Ghép prompt cuối gửi Groq: template + kiến thức truy hồi + ngữ cảnh nghề + inquiry.

    Tách riêng để test được mà không cần gọi Groq. ``profession``/``scam_hint``/
    ``retrieved_knowledge`` là DỮ LIỆU đầu vào theo request, không nằm trong system.txt
    nên KHÔNG đổi prompt_version.
    """
    context_lines = ""
    if profession:
        context_lines += f"Nghề của freelancer: {profession}\n"
    if scam_hint:
        context_lines += f"Mẫu lừa đảo phổ biến của nghề này: {scam_hint}\n"

    # Kiến thức lấy từ FAISS retriever (khung đánh giá chung + tài liệu theo nghề). Đặt
    # TRƯỚC inquiry để model đọc tiêu chí rồi mới đọc dữ liệu cần chấm.  #Huynh
    knowledge_block = ""
    if retrieved_knowledge:
        knowledge_block = f"\nKiến thức tham chiếu:\n{retrieved_knowledge}\n"

    return f"""{prompt_template}
{knowledge_block}
{context_lines}Client Inquiry:
{inquiry_text}
"""


class LeadQualifier(BaseAIChain):
    module_name = "lead_qualifier"

    _client: Groq | None = None
    # Token của lần gọi gần nhất — service đọc để ghi vào ai_cost_records.
    last_usage: dict[str, Any] | None = None

    # Dựng một lần cho cả vòng đời process: build FAISS index tốn thời gian và tốn lượt
    # gọi embeddings của Gemini.  #Huynh
    _retriever: Any | None = None

    @classmethod
    def _get_retriever(cls) -> Any:
        if cls._retriever is None:
            # Import trong hàm chứ không phải đầu file: retriever kéo theo langchain +
            # faiss, mà những gói đó chỉ cần khi THẬT SỰ truy hồi. Import ở top-level làm
            # chết cả module ở môi trường chưa cài chúng.  #Huynh
            from src.ai.lead_qualifier.retriever import LeadQualificationRetriever

            cls._retriever = LeadQualificationRetriever()

        return cls._retriever

    # ---------------------------------------------------------
    # Groq Client
    # ---------------------------------------------------------

    def _get_client(self) -> Groq:
        if self._client is not None:
            return self._client

        api_key = settings.groq_api_key
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")

        self._client = Groq(api_key=api_key)
        return self._client

    def set_client_for_tests(self, client: Any) -> None:
        """ONLY used in unit tests."""
        self._client = client

    def _build_chain(self) -> Any:
        """Required by BaseAIChain."""
        return None

    # ---------------------------------------------------------
    # Output Parser
    # ---------------------------------------------------------

    def _parse_output(self, raw: str) -> dict[str, Any]:
        """Bóc khối JSON ra khỏi câu trả lời của model.

        Phần bóc nằm ở ``src/ai/shared/json_output.py`` để proposal_generator dùng
        chung — trước đây mỗi chain một bản, sửa nơi này quên nơi kia.  #Huynh
        """
        try:
            return extract_json_object(raw)
        except json.JSONDecodeError as exc:
            log.error("ai.lead_qualifier.parse_failed", raw=raw, error=str(exc))
            raise AIOutputParseError(
                f"Unable to parse LeadQualifier output: {exc}",
                raw_output=raw,
            ) from exc

    # ---------------------------------------------------------
    # LLM Call
    # ---------------------------------------------------------

    def _call_groq(self, prompt: str) -> str:
        """Blocking Groq API call executed in a worker thread."""
        client = self._get_client()

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            # Chấm điểm phải LẶP LẠI ĐƯỢC. Ở 0.2, chấm cùng một deal hai lần ra 70 rồi 52
            # — cùng dữ liệu, khác kết quả. Không ai tin nổi một thang điểm như thế, và khi
            # bảo vệ đồ án mà chấm lại ra số khác là hỏng.
            #
            # 0 không đảm bảo tuyệt đối giống nhau (model vẫn có sai số nội tại), nhưng loại
            # bỏ phần ngẫu nhiên do ta tự thêm vào. Các module khác (soạn hợp đồng 0.1, viết
            # tin nhắn nhắc 0.3) thì cần chút biến thiên vì đó là VIẾT VĂN — còn đây là ĐO
            # LƯỜNG.  #Huynh
            temperature=0,
            # Cùng đầu vào -> cùng đầu ra, kể cả khi Groq gom batch khác nhau giữa hai lần
            # gọi. Chỉ temperature=0 thôi vẫn thấy chấm 70 rồi 80 trên cùng một deal.  #Huynh
            seed=42,
            # Buộc model trả JSON thuần. Thiếu cờ này, model bọc câu trả lời trong văn bản
            # ("Here is the draft qualification result:") và parser vỡ. Prompt vốn đã yêu
            # cầu trả JSON, nhưng chỉ cờ này mới khiến API BẢO ĐẢM điều đó.  #Huynh
            response_format={"type": "json_object"},
        )

        self.last_usage = extract_usage(response, model=getattr(response, "model", None) or MODEL)

        return response.choices[0].message.content or ""

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    async def run(self, **kwargs: Any) -> dict[str, Any]:
        # `inquiry_context` là tên tham số bên main, `inquiry_text` là tên bên nhánh này.
        # Nhận cả hai để lần gộp này không phải sửa hết caller của một trong hai phía.
        inquiry_text = kwargs.get("inquiry_text") or kwargs.get("inquiry_context")
        if not inquiry_text:
            raise ValueError("inquiry_context is required for LeadQualifier")

        # Ngữ cảnh nghề của freelancer (nếu có): nhãn nghề để ước giá đúng nghề, và mẫu
        # lừa đảo đặc thù nghề để đối chiếu. Đây là DỮ LIỆU đầu vào (như inquiry_text) nên
        # KHÔNG tính vào prompt_version — version chỉ băm system.txt tĩnh.  #Huynh
        profession = kwargs.get("profession")
        scam_hint = kwargs.get("scam_hint")

        # Retriever tra kiến thức theo TÊN THƯ MỤC dưới `src/ai/knowledge/professions/`,
        # nên nó cần SLUG. `profession` ở trên là nhãn hiển thị (tiếng Việt) dành cho
        # prompt — đưa nhãn cho retriever thì không khớp thư mục nào và mất sạch phần
        # kiến thức theo nghề. Không truyền slug thì lùi về dùng `profession`.  #Huynh
        profession_slug = kwargs.get("profession_slug") or profession

        # Truy hồi khung đánh giá + kiến thức theo nghề. Hỏng thì VẪN chấm tiếp: retriever
        # là phần làm tốt thêm, không phải điều kiện đúng/sai — cả nhánh này chấm không có
        # nó vẫn chạy. Nhưng log cảnh báo để không ai tưởng RAG đang hoạt động.  #Huynh
        retrieved_knowledge = ""
        try:
            retrieved_knowledge = self._get_retriever().retrieve(
                profession=profession_slug,
                query=inquiry_text,
            )
        except Exception as exc:
            log.warning("ai.lead_qualifier.retrieval_failed", error=str(exc))

        # KHÔNG có prompt dự phòng. Trước đây thiếu file thì rơi về một prompt rác 2 dòng
        # ("Qualify the following lead as JSON...") và hệ thống VẪN CHẤM ĐIỂM — sai bét mà
        # không ai biết. Thà nổ to còn hơn âm thầm chấm sai.  #Huynh
        prompt_template = load_prompt("lead_qualifier")
        full_prompt = build_qualifier_prompt(
            prompt_template,
            inquiry_text,
            profession,
            scam_hint,
            retrieved_knowledge,
        )

        try:
            raw_response = await asyncio.to_thread(
                self._call_groq,
                full_prompt,
            )

            result = self._parse_output(raw_response)
            # Truy nguồn: bản ghi này sinh ra bởi prompt phiên bản nào.  #Huynh
            result["prompt_version"] = prompt_version("lead_qualifier")
            return result

        except Exception as exc:
            log.error(
                "ai.lead_qualifier.failed",
                error=str(exc),
            )
            raise
