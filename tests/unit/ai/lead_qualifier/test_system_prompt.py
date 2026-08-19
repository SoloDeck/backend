"""Luật chấm điểm trong system.txt — kiểm bằng chuỗi, KHÔNG gọi LLM.

Vì sao cần: prompt là MÃ NGUỒN của phần chấm điểm, nhưng nó là file .txt nên không có gì
bắt lỗi khi ai đó sửa nhầm. Một dòng luật viết quá rộng ("chỉ chấm khối lời khách") đã làm
mọi deal gõ tay mất trọn 45 điểm ngân sách + thời gian, và không test nào chặn được.  #Huynh
"""

import re

from src.ai.lead_qualifier.scoring import RUBRIC_LEVELS
from src.ai.shared.prompt import load_prompt, prompt_version

RUBRIC_READ_ALL_TAG = '[đọc HẾT khối "YÊU CẦU DỰ ÁN"]'


def _muc_diem_prompt_cho_phep(key: str) -> list[int]:
    """Bóc các mức điểm prompt liệt kê cho một tiêu chí.

    Prompt viết dạng::

        1. scope — Phạm vi công việc   [đọc HẾT khối "YÊU CẦU DỰ ÁN"]
           30 : nói rõ làm những gì...
           20 : biết loại việc...
    """
    section = re.search(
        rf"^\d+\. {key} —.*?$(.*?)(?=^\d+\. \w+ —|^CỜ ĐỎ)",
        load_prompt("lead_qualifier"),
        re.MULTILINE | re.DOTALL,
    )
    assert section is not None, f"không tìm thấy mục chấm điểm của {key} trong prompt"
    return [int(m) for m in re.findall(r"^\s+(\d+)\s*:", section.group(1), re.MULTILINE)]


def test_muc_diem_trong_prompt_khop_dung_bang_barem_trong_code() -> None:
    """Prompt bảo AI được chấm mức nào, RUBRIC_LEVELS giải thích vì sao mất điểm.

    Hai bên lệch nhau là hỏng theo kiểu tệ nhất: AI chấm 25 cho một tiêu chí mà code không
    biết nấc 25 tồn tại, nên kéo tụt điểm hoặc giải thích sai — mà chẳng ai báo lỗi.  #Huynh
    """
    for key, levels in RUBRIC_LEVELS.items():
        assert _muc_diem_prompt_cho_phep(key) == [level.points for level in levels], key


def test_prompt_doi_cau_hoi_gui_khach_thay_cho_meo_cat_chuoi() -> None:
    """Phần "làm sao lên điểm" chuyển từ chuỗi tự do sang barem tra bảng.

    Cũ: bắt AI ghép câu 'Để lên tối đa: ...' vào `reason` rồi frontend cắt chuỗi theo đúng
    cụm đó — AI viết lệch một chữ là mất sạch phần giải thích.
    """
    prompt = load_prompt("lead_qualifier")

    assert '"question"' in prompt
    assert 'bắt đầu bằng "Để lên tối đa: "' not in prompt


def test_ca_5_tieu_chi_deu_duoc_nhac_doc_het_khoi_yeu_cau() -> None:
    """Trước đây chỉ scope/detail/context mang nhãn này; budget và timeline thì KHÔNG.

    Đúng hai tiêu chí thiếu nhãn là đúng hai tiêu chí bị chấm 0 khi người dùng dán chữ vào
    ô "Nội dung yêu cầu". Sự bất đối xứng đó không phải trùng hợp.
    """
    assert load_prompt("lead_qualifier").count(RUBRIC_READ_ALL_TAG) == 5


def test_khong_con_goi_o_noi_dung_yeu_cau_la_ghi_chu_noi_bo() -> None:
    prompt = load_prompt("lead_qualifier")

    assert "Ghi chú nội bộ" not in prompt
    assert '"Nội dung yêu cầu"' in prompt


def test_van_cam_tuyet_doi_o_gia_tri_du_kien() -> None:
    """Nới luật cho ô "Nội dung yêu cầu" KHÔNG được kéo theo việc nới ô "Giá trị dự kiến".

    Đó là con số freelancer tự đoán. Từng bị AI đọc thành "khách đã nêu ngân sách" và chấm
    20/25 — freelancer đi báo giá cho một khách chưa duyệt đồng nào.
    """
    prompt = load_prompt("lead_qualifier")

    assert "Giá trị dự kiến" in prompt
    assert "budget = 0" in prompt


def test_van_giu_luat_chong_phong_diem() -> None:
    prompt = load_prompt("lead_qualifier")

    assert "aaaa" in prompt  # mô tả rác vẫn coi như không có
    assert "TỐI ĐA 12" in prompt  # chỉ có tên dự án -> scope tối đa 12
    assert "Chắc tầm 100 triệu" in prompt  # phỏng đoán của freelancer vẫn budget = 0


def test_ma_phien_ban_prompt_van_dai_8_ky_tu() -> None:
    """Cột `lead_scores.prompt_version` là String(16) — băm phải lọt vào đó."""
    assert len(prompt_version("lead_qualifier")) == 8
