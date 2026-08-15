"""Mốc thanh toán có cấu trúc trong báo giá (Phase B — Stage 1).

Kiểm 2 chỗ net-new: (1) ProposalContent ép kiểu `payment_milestones` từ output LLM thất
thường, (2) build_proposal_document trích milestones từ cả shape AI lẫn shape DTO.
"""

from decimal import Decimal

from src.ai.proposal_generator.schemas.proposal_content import ProposalContent
from src.ai.proposal_generator.schemas.proposal_document import default_payment_milestones
from src.modules.proposals.application.pdf_content import (
    build_proposal_document,
    infer_due_type,
    resolve_cost_items,
)
from src.modules.proposals.application.service import (
    _cost_items_to_payloads,
    _milestones_to_payloads,
)
from src.modules.tasks.application.service import PAYMENT_TASK_PREFIX

_BASE = {
    "project_overview": "Website ban hang",
    "scope_of_work": ["UI"],
    "deliverables": ["Source"],
    "timeline": "2 thang",
    "pricing": "",
    "payment_terms": "Coc 50% + 50%",
    "assumptions": "x",
}

_META = {
    "freelancer_name": "Huynh",
    "client_name": "Cong ty ABC",
    "company_name": "Cong ty ABC",
    "project_type": "Website",
    "proposal_date": "2026-07-27",
}


class TestProposalContentMilestones:
    def test_percent_string_and_alt_keys(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=[
                {"label": "Coc", "percent": "50%", "due": "Khi ky"},
                {"description": "Ban giao", "percentage": 50, "when": "Nghiem thu"},
            ],
        )
        assert [m.percent for m in c.payment_milestones] == [50, 50]
        assert c.payment_milestones[1].label == "Ban giao"
        assert c.payment_milestones[1].due == "Nghiem thu"

    def test_string_entry_and_malformed_skipped(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=["Thanh toan 1 lan", {"nolabel": 1}, 123],
        )
        assert [m.label for m in c.payment_milestones] == ["Thanh toan 1 lan"]
        assert c.payment_milestones[0].percent is None

    def test_khong_neu_moc_thi_de_RONG_chu_khong_tu_dien_50_50(self):
        """Validator tự điền lịch 50/50 ĐÃ BỎ.

        Nó có lý khi thu tiền theo mốc %. Giờ thu theo hạng mục, và prompt đã yêu cầu model trả
        mảng rỗng — giữ validator thì mọi báo giá mới lại mọc ra một lịch 50/50 ma, mâu thuẫn
        với chính bảng chi phí in ngay bên trên nó.

        Lưới an toàn nằm ở `billing_task_payloads_for_deal`: báo giá không có hạng mục LẪN không
        có mốc thì lúc sinh task mới rơi về 50/50, nên không deal nào đi tới lúc ký mà không có
        gì để thu.  #Huynh
        """
        assert ProposalContent(**_BASE).payment_milestones == []

    def test_explicit_milestones_not_overridden_by_default(self):
        c = ProposalContent(
            **_BASE,
            payment_milestones=[{"label": "Trả 1 lần", "percent": 100, "due": "Khi bàn giao"}],
        )
        assert len(c.payment_milestones) == 1
        assert c.payment_milestones[0].percent == 100


class TestBuildProposalDocumentMilestones:
    def test_ai_shape(self):
        doc = build_proposal_document(
            {**_BASE, "payment_milestones": [{"label": "Coc", "percent": 50, "due": "Khi ky"}]},
            **_META,
        )
        assert len(doc.payment_milestones) == 1
        assert doc.payment_milestones[0].percent == 50

    def test_dto_payment_schedule(self):
        doc = build_proposal_document(
            {
                "executive_summary": "x",
                "terms": {
                    "payment_schedule": [
                        {"label": "Dot 1", "amount": "5.000.000 VND", "due": "Khi ky"}
                    ]
                },
            },
            **_META,
        )
        assert len(doc.payment_milestones) == 1
        assert doc.payment_milestones[0].amount == "5.000.000 VND"

    def test_no_milestones_ok(self):
        doc = build_proposal_document({**_BASE}, **_META)
        assert doc.payment_milestones == []


class TestBillingTaskPayloads:
    """Hạng mục chi phí (mục 7) → task THU TIỀN, một đổi một."""

    def test_one_task_per_cost_item_named_after_it(self):
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {
                        "label": "Trang đăng nhập",
                        "amount": 76_000_000,
                        "due_type": "on_signing",
                    },
                    {"label": "Tích hợp ngân hàng", "amount": 63_500_000},
                ]
            }
        )
        payloads = _cost_items_to_payloads(items)

        assert len(payloads) == 2
        # Tên task là NHÃN HẠNG MỤC nguyên văn — bảng việc phải đọc ra công việc thật, không
        # phải "Thu tiền: Đặt cọc khi ký hợp đồng".
        assert payloads[0].title == "Trang đăng nhập"
        assert payloads[0].amount == Decimal(76_000_000)
        assert "Khi ký hợp đồng" in payloads[0].description
        # Loại đi theo task để bảng việc biết dòng nào đòi được ngay.
        assert payloads[0].due_type == "on_signing"
        assert payloads[1].due_type == "on_completion"
        assert "Khi hoàn thành hạng mục" in payloads[1].description

    def test_amount_lives_on_the_column_not_in_the_title(self):
        # Cả điểm của thay đổi này: đổi tên task KHÔNG được làm đứt đường xuất hoá đơn.
        payloads = _cost_items_to_payloads(
            resolve_cost_items({"pricing_items": [{"label": "A", "amount": 1_000_000}]})
        )
        assert payloads[0].amount == Decimal(1_000_000)
        assert "1.000.000" not in payloads[0].title

    def test_no_cost_items_no_tasks(self):
        assert _cost_items_to_payloads(resolve_cost_items({})) == []


class TestThoiDiemThuLaLOAIChuKhongPhaiChuTuDo:
    """Thời điểm thu là enum `on_signing` / `on_completion`, kèm ghi chú tự do tuỳ chọn.

    Bản đầu để chữ tự do, và hệ thống phải ĐOÁN xem câu đó có nghĩa "thu trước" không bằng cách
    dò từ khoá tiếng Việt — gõ "Ngay sau khi hai bên xác nhận" là đoán trượt, cảnh báo hiện sai.
    Chữ đẹp cho khách đọc nhưng máy không suy luận được gì trên nó.  #Huynh
    """

    def test_hang_muc_DAU_mac_dinh_thu_khi_ky_hop_dong(self):
        """MẶC ĐỊNH GIỮ CỌC — điểm quan trọng nhất của thay đổi này.

        Trước đó mọi hạng mục mặc định "thu khi hoàn thành", tức freelancer làm xong sạch dự án
        mới nhận đồng đầu tiên. TỆ HƠN hẳn lịch 50/50 của bản cũ, mà không ai để ý vì nó là
        mặc định im lặng.
        """
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {"label": "Phân tích yêu cầu", "amount": 39_000_000},
                    {"label": "Thiết kế hệ thống", "amount": 39_000_000},
                ]
            }
        )
        assert items[0].due_type == "on_signing"
        assert items[0].due_label == "Khi ký hợp đồng"
        assert items[1].due_type == "on_completion"

    def test_freelancer_da_chon_thi_khong_de_len(self):
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {"label": "A", "amount": 10, "due_type": "on_completion"},
                    {"label": "B", "amount": 10, "due_type": "on_signing"},
                ]
            }
        )
        assert [i.due_type for i in items] == ["on_completion", "on_signing"]

    def test_ghi_chu_tu_do_in_de_len_nhan_chuan(self):
        # Hợp đồng thật hay có điều kiện riêng — ép về hai câu cố định là làm nghèo tờ giấy.
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {
                        "label": "A",
                        "amount": 10,
                        "due_type": "on_completion",
                        "due_note": "Sau khi phòng Marketing duyệt demo",
                    }
                ]
            }
        )
        assert items[0].due_label == "Sau khi phòng Marketing duyệt demo"
        assert items[0].due_type == "on_completion"  # máy vẫn biết đây là thu khi xong

    def test_bang_suy_ra_tu_bo_dinh_gia_cung_giu_coc(self):
        # Freelancer chưa đụng vào panel: bảng tới từ bộ định giá, vẫn phải có dòng thu trước.
        items = resolve_cost_items(
            {
                "pricing_detail": {
                    "final_price": 100_000_000,
                    "suggested": 100_000_000,
                    "line_items": [
                        {"label": "A", "amount": 60_000_000},
                        {"label": "B", "amount": 40_000_000},
                    ],
                }
            }
        )
        assert items[0].due_type == "on_signing"
        assert items[1].due_type == "on_completion"

    def test_doc_duoc_du_lieu_cu_con_ghi_thoi_diem_thu_bang_chu(self):
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {"label": "A", "amount": 10, "due": "Khi ký hợp đồng"},
                    {"label": "B", "amount": 10, "due": "Khi hoàn thành hạng mục"},
                ]
            }
        )
        assert [i.due_type for i in items] == ["on_signing", "on_completion"]
        # Câu trùng y hệt nhãn chuẩn thì bỏ, không in lại thành ghi chú thừa.
        assert [i.due_note for i in items] == ["", ""]

    def test_chon_KHAC_thi_ghi_chu_thanh_chu_in_ra_bao_gia(self):
        """"Khác" = freelancer tự ghi. Máy coi như KHÔNG BIẾT.

        "Sau 30 ngày kể từ ngày ký" là thu TRƯỚC còn "Khi khách duyệt demo" là thu SAU — cùng
        rơi vào ô này mà ý nghĩa ngược nhau, nên không được đoán.  #Huynh
        """
        items = resolve_cost_items(
            {
                "pricing_items": [
                    {
                        "label": "Giai đoạn 2",
                        "amount": 10,
                        "due_type": "custom",
                        "due_note": "Sau khi bên A duyệt bản demo",
                    }
                ]
            }
        )
        assert items[0].due_type == "custom"
        assert items[0].due_label == "Sau khi bên A duyệt bản demo"
        # KHÔNG được coi là thu trước, dù câu chữ có chữ "ký" hay không.
        assert items[0].collected_upfront is False

    def test_doan_khong_ra_thi_tra_None_chu_khong_doan_bua(self):
        # Thà im còn hơn gắn nhãn sai rồi nhắc sai.
        assert infer_due_type("Ngay sau khi hai bên xác nhận") is None
        assert infer_due_type("") is None
        assert infer_due_type("Khi nghiệm thu & bàn giao") == "on_completion"
        assert infer_due_type("Đặt cọc trước khi bắt đầu") == "on_signing"


class TestLegacyMilestonePayloads:
    """Lối rơi về cho báo giá CŨ không có hạng mục nào — vẫn chia theo % như trước."""

    def test_default_schedule_splits_agreed_price(self):
        payloads = _milestones_to_payloads(default_payment_milestones(), Decimal(100_000_000))
        assert len(payloads) == 2
        # Giữ tiền tố để nhìn bảng việc là biết ngay deal này chạy theo lịch cũ.
        assert all(p.title.startswith(PAYMENT_TASK_PREFIX) for p in payloads)
        assert [p.amount for p in payloads] == [Decimal(50_000_000), Decimal(50_000_000)]

    def test_rounding_remainder_goes_to_the_last_milestone(self):
        # 33/33/34 chia 100 triệu — làm tròn không được phép làm bay mất đồng nào, vì tổng
        # các task chính là thứ bảng doanh thu cộng lên.
        from src.ai.proposal_generator.schemas.proposal_document import PaymentMilestone

        payloads = _milestones_to_payloads(
            [
                PaymentMilestone(label="A", percent=33),
                PaymentMilestone(label="B", percent=33),
                PaymentMilestone(label="C", percent=34),
            ],
            Decimal(100_000_000),
        )
        assert sum(p.amount for p in payloads) == Decimal(100_000_000)

    def test_milestone_without_percent_shares_the_rest(self):
        # Hợp đồng thật hay ghi "50% khi ký, phần còn lại khi bàn giao".
        from src.ai.proposal_generator.schemas.proposal_document import PaymentMilestone

        payloads = _milestones_to_payloads(
            [PaymentMilestone(label="Cọc", percent=50), PaymentMilestone(label="Còn lại")],
            Decimal(100_000_000),
        )
        assert [p.amount for p in payloads] == [Decimal(50_000_000), Decimal(50_000_000)]

    def test_contract_summing_to_130_percent_is_not_silently_fixed(self):
        # Báo giá cũ lỡ ghi 50+50+30 thì phải phản ánh đúng thứ đã ký; tự ép về 100% là giấu
        # lỗi, freelancer không bao giờ phát hiện ra.
        from src.ai.proposal_generator.schemas.proposal_document import PaymentMilestone

        payloads = _milestones_to_payloads(
            [
                PaymentMilestone(label="A", percent=50),
                PaymentMilestone(label="B", percent=50),
                PaymentMilestone(label="C", percent=30),
            ],
            Decimal(100_000_000),
        )
        assert sum(p.amount for p in payloads) == Decimal(130_000_000)


class TestMotBangDuyNhatChoChiPhiVaThanhToan:
    """Mục 7 và mục 8 đã GỘP thành một: "7. Chi Phí & Thanh Toán".

    Trước đây tách hai bảng, mà từ khi thu tiền theo hạng mục thì mỗi hạng mục vừa là công việc
    vừa là một đợt thu — hai bảng thành hai bản sao của cùng một danh sách, khách đọc xong không
    biết bảng nào là thật.  #Huynh
    """

    def test_thoi_diem_thu_di_kem_ngay_tren_dong_chi_phi(self):
        doc = build_proposal_document(
            {
                **_BASE,
                "pricing_items": [
                    {"label": "Trang đăng nhập", "amount": 76_000_000, "due": "Khi ký hợp đồng"},
                    {"label": "Giỏ hàng", "amount": 63_500_000},
                ],
            },
            **_META,
        )
        assert [i.description for i in doc.pricing_line_items] == ["Trang đăng nhập", "Giỏ hàng"]
        assert doc.pricing_line_items[0].amount == "76.000.000 VND"
        # Chỗ freelancer giữ được khoản đặt cọc.
        assert doc.pricing_line_items[0].due == "Khi ký hợp đồng"
        # Không khai thì điền mặc định, để cột không có ô trống trên tờ giấy gửi khách.
        assert doc.pricing_line_items[1].due == "Khi hoàn thành hạng mục"

    def test_bao_gia_moi_khong_con_bang_moc_phan_tram(self):
        # Có hạng mục thì template dựng bảng chi phí; `payment_milestones` để rỗng nên nhánh
        # bảng mốc không chạy — không còn hai bảng nói hai kiểu.
        doc = build_proposal_document(
            {**_BASE, "pricing_items": [{"label": "A", "amount": 30_000_000}]}, **_META
        )
        assert doc.payment_milestones == []

    def test_bao_gia_cu_van_giu_duoc_bang_moc_cua_no(self):
        # Bản nháp cũ không có hạng mục nào: template rơi về bảng mốc %, in ngay trong mục 7.
        doc = build_proposal_document(
            {**_BASE, "payment_milestones": [{"label": "Cọc", "percent": 50, "due": "Khi ký"}]},
            **_META,
        )
        assert doc.pricing_line_items == []
        assert doc.payment_milestones[0].percent == 50
