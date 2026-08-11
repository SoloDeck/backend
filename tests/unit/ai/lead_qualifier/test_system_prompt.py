"""Luật chấm điểm trong system.txt — kiểm bằng chuỗi, KHÔNG gọi LLM.

Vì sao cần: prompt là MÃ NGUỒN của phần chấm điểm, nhưng nó là file .txt nên không có gì
bắt lỗi khi ai đó sửa nhầm. Một dòng luật viết quá rộng ("chỉ chấm khối lời khách") đã làm
mọi deal gõ tay mất trọn 45 điểm ngân sách + thời gian, và không test nào chặn được.  #Huynh
"""

from src.ai.shared.prompt import load_prompt, prompt_version

RUBRIC_READ_ALL_TAG = '[đọc HẾT khối "YÊU CẦU DỰ ÁN"]'


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
