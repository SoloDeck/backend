"""Mẫu điều khoản gồm nhiều KHỐI — `src/shared/domain/template_blocks.py`.

Trước đây một "mẫu" là MỘT đoạn văn đổ vào MỘT khoá, render thành MỘT mục ở gần cuối tờ giấy —
nên freelancer chọn mẫu xong gần như không thấy gì khác, và nhìn từ ngoài thì như chưa làm.

Ba bất biến khoá ở đây, mất cái nào cũng nguy hiểm: mẫu KHÔNG chạm tiền, mẫu KHÔNG chạm phần
đặc thù dự án, và mẫu cũ (khoá `body`) vẫn phải chạy.  #Huynh
"""

import re

from src.shared.domain.template_blocks import (
    CONTRACT_CLAUSE_DEFAULTS,
    CONTRACT_HIDEABLE,
    CONTRACT_SKELETON_BLOCKS,
    CONTRACT_TEMPLATE_BLOCKS,
    MAX_EXTRA_SECTIONS,
    MAX_SECTION_TITLE_LEN,
    MONEY_KEYS,
    PROPOSAL_HIDEABLE,
    PROPOSAL_SKELETON_BLOCKS,
    PROPOSAL_TEMPLATE_BLOCKS,
    apply_template_blocks,
    blocks_for,
    body_blocks_for,
    build_skeleton_content,
    collect_clause_texts,
    collect_extra_sections,
    collect_hidden_sections,
    collect_section_titles,
    skeleton_block_labels,
    skeleton_blocks_for,
    template_block_labels,
    template_preview,
)


class TestApDungKhoiMau:
    def test_moi_khoi_vao_dung_khoa_cua_no(self):
        out = apply_template_blocks(
            {},
            {
                "out_of_scope": ["Mua font bản quyền", "Chi phí in ấn"],
                "revision_policy": "2 vòng miễn phí.",
                "standard_terms": "Bàn giao file nguồn sau khi thanh toán đủ.",
            },
            "proposal",
        )
        assert out["out_of_scope"] == ["Mua font bản quyền", "Chi phí in ấn"]
        assert out["revision_policy"] == "2 vòng miễn phí."
        assert out["standard_terms"] == "Bàn giao file nguồn sau khi thanh toán đủ."

    def test_mau_thang_ai(self):
        """Khối nào mẫu có thì chép đè lên phần AI vừa viết.

        Đó chính là lý do admin ngồi soạn mẫu: để chữ đó không bị AI viết lại mỗi lần một kiểu.
        """
        out = apply_template_blocks(
            {"out_of_scope": ["AI tự nghĩ ra"], "revision_policy": "AI tự viết"},
            {"out_of_scope": ["Đúng chữ admin"], "revision_policy": "Đúng chữ admin"},
            "proposal",
        )
        assert out["out_of_scope"] == ["Đúng chữ admin"]
        assert out["revision_policy"] == "Đúng chữ admin"

    def test_khoi_de_trong_thi_giu_phan_ai_viet(self):
        # Mẫu điền vài khối, phần còn lại vẫn nhờ AI — đó là cách một mẫu "dùng chung" sống
        # chung được với nhiều loại dự án.
        out = apply_template_blocks(
            {"out_of_scope": ["AI viết"], "revision_policy": "AI viết"},
            {"standard_terms": "Chỉ có khối này"},
            "proposal",
        )
        assert out["out_of_scope"] == ["AI viết"]
        assert out["revision_policy"] == "AI viết"
        assert out["standard_terms"] == "Chỉ có khối này"

    def test_khoi_toan_khoang_trang_khong_de_len(self):
        out = apply_template_blocks(
            {"revision_policy": "AI viết"}, {"revision_policy": "   "}, "proposal"
        )
        assert out["revision_policy"] == "AI viết"

    def test_mau_tuyet_doi_khong_cham_tien(self):
        """Bất biến quan trọng nhất.

        Ba nơi — cổng gửi báo giá, `resolve_cost_items`, bộ sinh task thu tiền — cùng dựa trên
        "tổng hạng mục = giá chào khách". Cho một mẫu DÙNG CHUNG ghi đè tiền là phá bất biến
        đó từ bên ngoài, mà lại im lặng.
        """
        goc = {
            "pricing_items": [{"label": "Thật", "amount": 50_000_000}],
            "pricing": "50.000.000 VND",
            "pricing_detail": {"final_price": 50_000_000},
        }
        out = apply_template_blocks(
            goc,
            {
                "pricing_items": [{"label": "Mẫu chèn bậy", "amount": 1}],
                "pricing": "1 VND",
                "pricing_detail": {"final_price": 1},
                "standard_terms": "Điều khoản thật",
            },
            "proposal",
        )
        assert out["pricing_items"] == goc["pricing_items"]
        assert out["pricing"] == goc["pricing"]
        assert out["pricing_detail"] == goc["pricing_detail"]
        assert out["standard_terms"] == "Điều khoản thật"

    def test_mau_khong_cham_phan_dac_thu_du_an(self):
        # Tổng quan / phạm vi / bàn giao / tiến độ là việc của AI vì phải đọc yêu cầu THẬT của
        # khách. Mẫu dùng chung mà ghi đè mấy mục này là gửi khách một tờ giấy nói về dự án khác.
        goc = {
            "project_overview": "Đúng dự án của khách",
            "scope_of_work": ["Việc thật"],
            "deliverables": ["Sản phẩm thật"],
            "timeline": "8 tuần",
        }
        out = apply_template_blocks(
            goc,
            {
                "project_overview": "Mẫu chèn bậy",
                "scope_of_work": ["Bậy"],
                "deliverables": ["Bậy"],
                "timeline": "Bậy",
            },
            "proposal",
        )
        assert out == goc

    def test_khoi_hop_dong_khac_khoi_bao_gia(self):
        out = apply_template_blocks(
            {},
            {
                "ip_ownership": "Bàn giao mã nguồn",
                "termination_clause": "Báo trước 15 ngày",
                "custom_clauses": "Điều khoản riêng",
                # Khoá của báo giá — không thuộc bộ hợp đồng nên phải bị bỏ qua.
                "out_of_scope": ["Không được vào"],
            },
            "contract",
        )
        assert out["ip_ownership"] == "Bàn giao mã nguồn"
        assert out["termination_clause"] == "Báo trước 15 ngày"
        assert out["custom_clauses"] == "Điều khoản riêng"
        assert "out_of_scope" not in out

    def test_khoa_la_bi_bo_qua(self):
        # Danh sách CHO PHÉP, không phải danh sách cấm. Admin nhét gì thêm cũng không đi tới đâu.
        out = apply_template_blocks({}, {"khoa_la": "gì đó", "is_admin": True}, "proposal")
        assert out == {}


class TestTuongThichNguoc:
    def test_mau_cu_chi_co_body_van_chay(self):
        """Bốn mẫu admin đã nhập đang dùng khoá `body`.

        Nâng cấp cấu trúc KHÔNG được làm hỏng dữ liệu người ta đã gõ.
        """
        out = apply_template_blocks({}, {"body": "Điều khoản kiểu cũ"}, "proposal")
        assert out["standard_terms"] == "Điều khoản kiểu cũ"

    def test_mau_moi_ghi_ro_thi_khoa_cu_khong_de_len(self):
        out = apply_template_blocks(
            {},
            {"body": "Bản cũ", "standard_terms": "Bản mới"},
            "proposal",
        )
        assert out["standard_terms"] == "Bản mới"

    def test_body_rong_thi_khong_ghi_gi(self):
        assert apply_template_blocks({}, {"body": "   "}, "proposal") == {}


class TestXemTruocChoBoChon:
    def test_chi_liet_ke_khoi_co_noi_dung(self):
        labels = template_block_labels(
            {"out_of_scope": ["A"], "revision_policy": "", "standard_terms": "B"}, "proposal"
        )
        assert labels == ["Ngoài phạm vi", "Điều khoản chuẩn"]

    def test_mau_cu_van_co_nhan(self):
        assert template_block_labels({"body": "Cũ"}, "proposal") == ["Điều khoản chuẩn"]

    def test_mau_rong_thi_khong_co_nhan_nao(self):
        assert template_block_labels({}, "proposal") == []

    def test_trich_doan_gop_mang_thanh_mot_dong(self):
        assert template_preview({"out_of_scope": ["A", "B"]}, "proposal") == "A · B"

    def test_trich_doan_dai_thi_cat_va_bao_la_con_nua(self):
        preview = template_preview({"standard_terms": "x" * 300}, "proposal")
        assert len(preview) <= 120
        assert preview.endswith("…")


class TestDungKhungKhongCanAI:
    """`build_skeleton_content` — nền tài liệu cho đường soạn KHÔNG dùng AI."""

    def test_khung_voi_toi_ca_phan_dac_thu_du_an(self):
        # Đây là khác biệt cốt lõi với chế độ AI: không có AI nào viết mục 3-6 hộ nữa, nên mẫu
        # phải với được tới đó, bằng không tờ giấy chỉ có điều khoản mà không có nội dung.
        out = build_skeleton_content(
            {
                "project_overview": "Dự án thiết kế nhận diện thương hiệu.",
                "scope_of_work": ["Khảo sát", "Phác thảo", "Hoàn thiện"],
                "deliverables": ["File nguồn AI", "Bộ hướng dẫn sử dụng"],
                "timeline": "4 tuần kể từ ngày tạm ứng.",
                "payment_terms": "Tạm ứng 30% khi ký.",
                "standard_terms": "Bàn giao sau khi thanh toán đủ.",
            },
            "proposal",
        )
        assert out["project_overview"] == "Dự án thiết kế nhận diện thương hiệu."
        assert out["scope_of_work"] == ["Khảo sát", "Phác thảo", "Hoàn thiện"]
        assert out["deliverables"] == ["File nguồn AI", "Bộ hướng dẫn sử dụng"]
        assert out["timeline"] == "4 tuần kể từ ngày tạm ứng."
        assert out["payment_terms"] == "Tạm ứng 30% khi ký."

    def test_hop_dong_lay_scope_of_work_la_chuoi_khong_phai_mang(self):
        """Tính-mảng khác nhau giữa hai loại tài liệu, cùng một tên khoá.

        Tờ báo giá render `<ul data-field="scope_of_work">` (gạch đầu dòng), Điều 1 của hợp đồng
        render `<p data-field="scope_of_work">` (một đoạn văn). Dùng chung một tập khoá-mảng là
        in một mảng Python vào chỗ chờ chuỗi.
        """
        out = build_skeleton_content(
            {"scope_of_work": "Thiết kế và bàn giao bộ nhận diện.", "payment_terms": "50/50."},
            "contract",
        )
        assert out["scope_of_work"] == "Thiết kế và bàn giao bộ nhận diện."
        assert out["payment_terms"] == "50/50."

    def test_hai_bo_khoa_tach_rieng(self):
        """Nới bộ khoá của chế độ AI là hỏng chế độ AI.

        Cùng một mẫu: ở chế độ khung thì `project_overview` được lấy, ở chế độ AI thì KHÔNG —
        vì ở đó AI vừa đọc yêu cầu thật của khách, mẫu chép đè lên là xoá đúng phần đáng giá nhất.
        """
        mau = {"project_overview": "Chữ của admin", "standard_terms": "Điều khoản"}

        khung = build_skeleton_content(mau, "proposal")
        assert khung["project_overview"] == "Chữ của admin"

        ai = apply_template_blocks(
            {"project_overview": "AI viết theo yêu cầu khách"}, mau, "proposal"
        )
        assert ai["project_overview"] == "AI viết theo yêu cầu khách"

    def test_khung_cung_tuyet_doi_khong_cham_tien(self):
        # Nguyên tắc 1 áp cho CẢ HAI chế độ. Đường khung không có AI nhưng vẫn đi qua đúng cổng
        # gửi và đúng bộ sinh task thu tiền, nên bất biến tiền không được lỏng ra một chút nào.
        out = build_skeleton_content(
            {
                "standard_terms": "Điều khoản thật",
                "pricing_items": [{"label": "Mẫu chèn bậy", "amount": 1}],
                "pricing_detail": {"final_price": 1},
                "payment_milestones": [{"percent": 100}],
                "total_amount": 1,
            },
            "proposal",
        )
        assert out == {"standard_terms": "Điều khoản thật"}

    def test_khong_khoa_tien_nao_lot_vao_bat_ky_bo_nao(self):
        # Kẹp nguyên tắc 1 thành khẳng định máy kiểm tra được, thay vì một dòng chú thích. Ai
        # thêm khoá mới vào bảng mà lỡ tay chạm tiền sẽ bị bài này chặn ngay.
        for bo in (
            PROPOSAL_TEMPLATE_BLOCKS,
            CONTRACT_TEMPLATE_BLOCKS,
            PROPOSAL_SKELETON_BLOCKS,
            CONTRACT_SKELETON_BLOCKS,
        ):
            assert MONEY_KEYS.isdisjoint(bo.keys())

    def test_mau_chua_soan_khung_thi_tra_rong_chu_khong_no(self):
        # Kết quả HỢP LỆ, không phải lỗi: freelancer nhận tờ giấy trống với đủ ô để tự điền.
        # "Khung trắng" (không chọn mẫu nào) cũng đi vào đúng nhánh này.
        assert build_skeleton_content({}, "proposal") == {}
        assert build_skeleton_content({"khoa_la": "gì đó"}, "proposal") == {}

    def test_khong_bia_chu_moi_cho_khoi_admin_de_trong(self):
        """Không một chữ nội dung nào được nằm trong code.

        Đặt sẵn văn bản mồi là biến một quyết định nghiệp vụ của admin thành hằng số lập trình —
        và tờ giấy gửi khách sẽ mang chữ mà không ai ngồi soạn.
        """
        out = build_skeleton_content({"standard_terms": "Chỉ có khối này"}, "proposal")
        assert out == {"standard_terms": "Chỉ có khối này"}

    def test_mau_cu_chi_co_body_van_dung_lam_khung_duoc(self):
        out = build_skeleton_content({"body": "Điều khoản kiểu cũ"}, "proposal")
        assert out["standard_terms"] == "Điều khoản kiểu cũ"

    def test_nhan_khung_liet_ke_dung_muc_admin_da_soan(self):
        labels = skeleton_block_labels(
            {"project_overview": "A", "timeline": "B", "revision_policy": ""}, "proposal"
        )
        assert labels == ["Tổng quan dự án", "Thời gian thực hiện"]

    def test_mau_thuan_dieu_khoan_thi_nhan_khung_phai_rong(self):
        """Ba khoá điều khoản nằm trong CẢ HAI bộ, nên đếm gộp là nói quá.

        Đây là hai mẫu đang nằm trong DB thật. Nếu `skeleton_block_labels` kể luôn phần điều
        khoản thì mẫu thuần-điều-khoản vẫn ra "có khung", và bộ chọn khoe "Soạn sẵn: Ngoài phạm
        vi · Điều khoản chuẩn" — trong khi mục 3 đến mục 6 của tờ giấy vẫn trắng y như khung
        trắng. Rỗng ở đây PHẢI có nghĩa "mẫu này không đỡ được phần thân nào".
        """
        ban_giao = {
            "out_of_scope": ["Mua font bản quyền"],
            "revision_policy": "2 vòng miễn phí.",
            "standard_terms": "Bàn giao file nguồn.",
            "valid_days": 14,
        }
        assert skeleton_block_labels(ban_giao, "proposal") == []
        # ...nhưng phần điều khoản KHÔNG mất đi đâu cả, nó được kể ở danh sách còn lại.
        assert template_block_labels(ban_giao, "proposal") == [
            "Ngoài phạm vi",
            "Chính sách chỉnh sửa",
            "Điều khoản chuẩn",
        ]

    def test_mau_cu_chi_co_body_cung_khong_tinh_la_co_khung(self):
        assert skeleton_block_labels({"body": "Đặt cọc 50%."}, "proposal") == []
        assert template_block_labels({"body": "Đặt cọc 50%."}, "proposal") == ["Điều khoản chuẩn"]

    def test_phan_than_la_phan_bu_cua_hai_bo_khoa(self):
        # Kẹp định nghĩa thành khẳng định máy kiểm được: thêm khoá mới vào bộ khung mà quên nghĩ
        # xem nó là "thân" hay "điều khoản" sẽ bị bài này chặn.
        for loai in ("proposal", "contract"):
            than = set(body_blocks_for(loai))
            assert than.isdisjoint(blocks_for(loai))
            assert than <= set(skeleton_blocks_for(loai))


class TestDauMucTuSoan:
    """Bộ mục cứng của tờ giấy không phủ hết mọi nghề.

    Nhiếp ảnh cần "Quyền sử dụng hình ảnh", dịch thuật cần "Quy tắc thuật ngữ". Tên mục nằm
    trong DỮ LIỆU chứ không nằm trong template.  #Huynh
    """

    def test_ban_gui_khach_bo_muc_khong_co_ten(self):
        # Mục không tên in ra thành `<h2>9. </h2>`: số mục vẫn nhảy nhưng đầu đề trống trơn,
        # khách đọc tưởng tài liệu lỗi.
        noi_dung = {
            "extra_sections": [
                {"title": "", "body": "Có nội dung mà không có tên"},
                {"title": "Quyền sử dụng hình ảnh", "body": "Bên B được dùng thương mại."},
            ]
        }
        assert collect_extra_sections(noi_dung) == [
            {"title": "Quyền sử dụng hình ảnh", "body": "Bên B được dùng thương mại."}
        ]

    def test_man_soan_giu_muc_chua_dat_ten(self):
        # Admin vừa bấm "Thêm đầu mục" thì mục đó chưa có tên; lọc đi ngay là nó không hiện lên
        # giấy và admin không có chỗ nào để gõ tên vào. Cùng nguyên tắc với cờ `editable`.
        noi_dung = {"extra_sections": [{"title": "", "body": ""}]}
        assert collect_extra_sections(noi_dung) == []
        assert collect_extra_sections(noi_dung, keep_untitled=True) == [{"title": "", "body": ""}]

    def test_co_tran_vi_mau_in_vao_moi_to_giay(self):
        nhieu = {"extra_sections": [{"title": f"Mục {i}"} for i in range(50)]}
        assert len(collect_extra_sections(nhieu)) == MAX_EXTRA_SECTIONS

    def test_bo_rac_thay_vi_no(self):
        assert collect_extra_sections({"extra_sections": "khong-phai-mang"}) == []
        assert collect_extra_sections({"extra_sections": [1, "x", None]}) == []
        assert collect_extra_sections({}) == []

    def test_cat_ve_dung_hai_khoa(self):
        # Admin nhét khoá lạ vào một mục cũng không đi tới đâu — cùng nguyên tắc allowlist.
        out = collect_extra_sections(
            {"extra_sections": [{"title": " A ", "body": " B ", "is_admin": True}]}
        )
        assert out == [{"title": "A", "body": "B"}]

    def test_ap_cho_ca_hai_che_do(self):
        """Đây là chữ admin ngồi soạn, không tranh chấp gì với phần AI đọc yêu cầu khách."""
        mau = {"extra_sections": [{"title": "Bảo hành", "body": "30 ngày."}]}
        assert apply_template_blocks({}, mau, "proposal")["extra_sections"] == [
            {"title": "Bảo hành", "body": "30 ngày."}
        ]
        assert build_skeleton_content(mau, "proposal")["extra_sections"] == [
            {"title": "Bảo hành", "body": "30 ngày."}
        ]

    def test_khong_co_muc_nao_thi_khong_sinh_khoa_rong(self):
        out = apply_template_blocks({}, {"standard_terms": "x"}, "proposal")
        assert "extra_sections" not in out


class TestDoiTenDauMuc:
    """Tên mục là DỮ LIỆU, không phải chữ cứng trong template.

    Cách gọi tên là thứ khác nhau nhiều nhất giữa các nghề: chỗ gọi "Sản phẩm bàn giao", chỗ gọi
    "Hạng mục nghiệm thu".  #Huynh
    """

    def test_lay_ten_admin_da_doi(self):
        out = collect_section_titles(
            {"section_titles": {"deliverables": "Hạng mục nghiệm thu"}}, "proposal"
        )
        assert out == {"deliverables": "Hạng mục nghiệm thu"}

    def test_bo_ten_trung_mac_dinh(self):
        """Tiêu đề trên giấy là ô sửa tại chỗ: bấm vào rồi bấm ra là nó "lưu" lại tên cũ.

        Không lọc thì `content` đầy khoá vô nghĩa, và tệ hơn — tờ giấy mất dòng tiếng Anh phụ,
        vì dòng đó chỉ hiện khi tên CHƯA bị đổi.
        """
        out = collect_section_titles(
            {"section_titles": {"deliverables": "Sản Phẩm Bàn Giao"}}, "proposal"
        )
        assert out == {}

    def test_bo_khoa_khong_thuoc_to_giay(self):
        # Danh sách CHO PHÉP: admin nhét khoá lạ cũng không đi tới đâu.
        out = collect_section_titles(
            {"section_titles": {"khoa_bia_dat": "X", "party_a": "Bên thi công"}}, "proposal"
        )
        assert out == {"party_a": "Bên thi công"}

    def test_hop_dong_co_bo_khoa_rieng(self):
        # `dispute` chỉ có ở hợp đồng; `deliverables` chỉ có ở báo giá.
        rieng = {"section_titles": {"dispute": "Xử lý mâu thuẫn"}}
        assert collect_section_titles(rieng, "contract")
        assert collect_section_titles({"section_titles": {"dispute": "X"}}, "proposal") == {}

    def test_cat_ten_qua_dai_va_gop_khoang_trang(self):
        out = collect_section_titles(
            {"section_titles": {"timeline": "  Lịch   chạy  việc  "}}, "proposal"
        )
        assert out == {"timeline": "Lịch chạy việc"}
        dai = collect_section_titles({"section_titles": {"timeline": "x" * 500}}, "proposal")
        assert len(dai["timeline"]) <= MAX_SECTION_TITLE_LEN

    def test_bo_rac_thay_vi_no(self):
        assert collect_section_titles({"section_titles": "khong-phai-dict"}, "proposal") == {}
        assert collect_section_titles({"section_titles": {"timeline": 5}}, "proposal") == {}
        assert collect_section_titles({}, "proposal") == {}


class TestChuTrongDieuCoSan:
    """Admin đổi được TÊN điều thì phải đổi được cả CHỮ bên trong.

    Bấm vào tiêu đề sửa được mà bấm vào đoạn ngay dưới thì không — vừa không nhất quán, vừa
    khoá cứng đúng những điều pháp lý mà mỗi nghề diễn đạt một kiểu.  #Huynh
    """

    def test_lay_chu_admin_da_sua(self):
        out = collect_clause_texts(
            {"clause_texts": {"confidentiality": "Hai Bên giữ kín vĩnh viễn."}}, "contract"
        )
        assert out == {"confidentiality": "Hai Bên giữ kín vĩnh viễn."}

    def test_bo_chu_trung_ban_mac_dinh(self):
        # Đoạn văn nào cũng là ô sửa tại chỗ: bấm vào rồi bấm ra là nó "lưu" lại đúng chữ cũ.
        goc = CONTRACT_CLAUSE_DEFAULTS["confidentiality"]
        assert collect_clause_texts({"clause_texts": {"confidentiality": goc}}, "contract") == {}

    def test_dieu_dang_danh_sach_nhan_mang(self):
        out = collect_clause_texts(
            {"clause_texts": {"party_a_duties": ["Nghĩa vụ A", "Nghĩa vụ B"]}}, "contract"
        )
        assert out == {"party_a_duties": ["Nghĩa vụ A", "Nghĩa vụ B"]}

    def test_danh_sach_trung_mac_dinh_cung_bi_bo(self):
        goc = CONTRACT_CLAUSE_DEFAULTS["party_a_duties"]
        assert collect_clause_texts({"clause_texts": {"party_a_duties": goc}}, "contract") == {}

    def test_sai_kieu_thi_bo_qua_chu_khong_no(self):
        # Gửi chuỗi cho khoá danh sách (hoặc ngược lại) là in nhầm kiểu vào tờ giấy.
        assert collect_clause_texts({"clause_texts": {"party_a_duties": "chuỗi"}}, "contract") == {}
        assert collect_clause_texts({"clause_texts": {"general": ["mảng"]}}, "contract") == {}
        assert collect_clause_texts({"clause_texts": "rác"}, "contract") == {}

    def test_bo_khoa_khong_thuoc_to_giay(self):
        out = collect_clause_texts(
            {"clause_texts": {"khoa_bia_dat": "X", "general": "Lập 03 bản."}}, "contract"
        )
        assert out == {"general": "Lập 03 bản."}

    def test_bao_gia_va_hop_dong_co_bo_khoa_rieng(self):
        # `confidentiality` chỉ có ở hợp đồng; `confirmation` chỉ có ở báo giá.
        assert collect_clause_texts({"clause_texts": {"confidentiality": "x"}}, "proposal") == {}
        assert collect_clause_texts({"clause_texts": {"confirmation": "x"}}, "proposal")

    def test_khong_con_dan_chieu_dieu_theo_so(self):
        """Số điều giờ thay đổi được, nên dẫn chiếu bằng số là sai bất cứ lúc nào.

        Bản trước viết "đã cam kết tại Điều 1 và Điều 2", "thanh toán theo Điều 3" — mà từ khi
        admin thêm/bớt/đổi tên được đầu mục thì mấy con số đó trỏ lung tung, trên giấy tờ pháp
        lý gửi khách.
        """
        moi_chu = " ".join(
            str(v) for v in CONTRACT_CLAUSE_DEFAULTS.values()
        )
        for so in ("Điều 1", "Điều 2", "Điều 3", "Điều 4"):
            assert so not in moi_chu, so


class TestBaTangQuyenSua:
    """Mục nào admin tắt được — theo CHÍNH SÁCH, không theo việc admin đã gõ gì.

    Trước bản này "bỏ được hay không" là hệ quả tình cờ: mục nào có chữ mặc định thì không bao
    giờ rỗng nên không bao giờ biến mất. Báo giá bỏ được 7/11, hợp đồng chỉ 2/12.  #Huynh
    """

    def test_lay_dung_muc_duoc_phep_tat(self):
        noi = {"hidden_sections": ["standard_terms", "confidentiality"]}
        assert collect_hidden_sections(noi, "contract") == ["standard_terms", "confidentiality"]

    def test_khong_tat_duoc_muc_tien_du_nhet_thang_vao(self):
        """Cho ẩn mục tiền là lách nguyên tắc 1 bằng cửa sau.

        Tổng tiền biến khỏi tờ giấy gửi khách, trong khi cổng gửi báo giá và bộ sinh task thu
        tiền vẫn tưởng nó ở đó.
        """
        noi = {"hidden_sections": ["pricing", "payment"]}
        assert collect_hidden_sections(noi, "proposal") == []
        assert collect_hidden_sections(noi, "contract") == []

    def test_khong_tat_duoc_nam_muc_phieu_liet_ke(self):
        """Phiếu đề tài định nghĩa "báo giá dịch vụ đầy đủ" gồm năm thứ.

        Tắt đi là sản phẩm không còn làm đúng thứ đã hứa — đây là căn cứ khoá mạnh nhất, mạnh
        hơn hẳn viện dẫn luật (Phiếu tự ghi hợp đồng KHÔNG phải văn bản pháp lý chính thức).
        """
        noi = {
            "hidden_sections": [
                "scope_of_work",
                "deliverables",
                "timeline",
                "payment_terms",
                "pricing",
            ]
        }
        assert collect_hidden_sections(noi, "proposal") == []

    def test_khong_tat_duoc_danh_tinh_hai_ben_va_xac_nhan(self):
        noi = {"hidden_sections": ["party_a", "party_b", "confirmation"]}
        assert collect_hidden_sections(noi, "proposal") == []

    def test_hop_dong_giu_shtt_va_quyen_nghia_vu(self):
        # SHTT là thứ quan trọng nhất về thương mại với freelancer; quyền–nghĩa vụ là khung
        # tối thiểu. Cả hai thuộc tầng 2 — sửa chữ được, tắt thì không.
        noi = {"hidden_sections": ["ip_ownership", "party_a_duties", "party_b_duties", "dispute"]}
        assert collect_hidden_sections(noi, "contract") == []

    def test_bo_rac_va_bo_trung_lap(self):
        assert collect_hidden_sections({"hidden_sections": "x"}, "proposal") == []
        noi = {"hidden_sections": ["standard_terms", "standard_terms", "khoa_bia_dat"]}
        assert collect_hidden_sections(noi, "proposal") == ["standard_terms"]

    def test_trang_thai_tat_di_qua_ca_hai_che_do(self):
        mau = {"hidden_sections": ["standard_terms"], "standard_terms": "x"}
        ai = apply_template_blocks({}, mau, "proposal")
        assert ai["hidden_sections"] == ["standard_terms"]
        assert build_skeleton_content(mau, "proposal")["hidden_sections"] == ["standard_terms"]

    def test_khong_tat_gi_thi_khong_sinh_khoa_rong(self):
        ra = apply_template_blocks({}, {"standard_terms": "x"}, "proposal")
        assert "hidden_sections" not in ra

    # Tên gọi tắt hay dùng khi một điều nhắc tới điều khác. Khoá của bảng này phải PHỦ ĐÚNG
    # `CONTRACT_HIDEABLE` — thêm một điều vào tầng 3 mà quên khai tên gọi tắt thì bài dưới đỏ.
    TEN_GOI_TAT = {
        "confidentiality": ("bảo mật",),
        "termination_clause": ("chấm dứt", "sửa đổi"),
        "standard_terms": ("chuẩn",),
        "custom_clauses": ("bổ sung",),
    }

    def test_bang_ten_goi_tat_phu_dung_tang_3(self):
        assert set(self.TEN_GOI_TAT) == set(CONTRACT_HIDEABLE)

    def test_chu_mac_dinh_khong_dan_chieu_toi_dieu_co_the_bi_tat(self):
        """Ràng buộc chung: đừng để điều nào dẫn chiếu đích danh một điều tầng 3.

        `party_a_duties` từng viết "Bảo mật thông tin… THEO ĐIỀU KHOẢN BẢO MẬT của Hợp đồng" —
        mà Bảo mật giờ tắt được, nên câu đó có ngày trỏ vào một điều không còn trên giấy. Bắt
        đúng cấu trúc DẪN CHIẾU ("theo điều khoản X"), không bắt cụm danh từ trần: bản thân
        nghĩa vụ giữ kín thông tin đứng một mình vẫn đọc được khi không có điều Bảo mật.
        """
        moi_chu = " ".join(
            " ".join(v) if isinstance(v, list) else str(v)
            for v in CONTRACT_CLAUSE_DEFAULTS.values()
        ).lower()
        for khoa, tens in self.TEN_GOI_TAT.items():
            for ten in tens:
                assert f"điều khoản {ten}" not in moi_chu, f"{khoa}: dẫn chiếu tới điều tắt được"

    def test_chu_mac_dinh_khong_danh_so_dieu_cung(self):
        """Số điều tự nhảy theo mục bị tắt, nên viết "Điều 3" vào chữ là sai ngay lần tắt đầu."""
        for khoa, gia_tri in CONTRACT_CLAUSE_DEFAULTS.items():
            chu = " ".join(gia_tri) if isinstance(gia_tri, list) else str(gia_tri)
            assert not re.search(r"[Đđ]iều\s+\d", chu), khoa

    def test_hai_tap_tang_3_khong_giao_voi_khoa_tien(self):
        for tap in (PROPOSAL_HIDEABLE, CONTRACT_HIDEABLE):
            assert MONEY_KEYS.isdisjoint(tap)
