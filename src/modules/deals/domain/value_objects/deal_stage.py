from enum import StrEnum


class DealStage(StrEnum):
    NEW_LEAD = "new_lead"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    IN_NEGOTIATION = "in_negotiation"
    ACTIVE = "active"
    COMPLETED_AND_BILLED = "completed_and_billed"
    LOST = "lost"


# Allowed forward (and occasional backward) transitions per stage.
STAGE_TRANSITIONS: dict[DealStage, frozenset[DealStage]] = {
    DealStage.NEW_LEAD: frozenset({DealStage.QUALIFIED, DealStage.LOST}),
    DealStage.QUALIFIED: frozenset({DealStage.PROPOSAL_SENT, DealStage.LOST}),
    DealStage.PROPOSAL_SENT: frozenset({DealStage.IN_NEGOTIATION, DealStage.LOST}),
    DealStage.IN_NEGOTIATION: frozenset({DealStage.ACTIVE, DealStage.LOST}),
    DealStage.ACTIVE: frozenset({DealStage.COMPLETED_AND_BILLED, DealStage.LOST}),
    DealStage.COMPLETED_AND_BILLED: frozenset(),
    DealStage.LOST: frozenset(),
}

TERMINAL_STAGES: frozenset[DealStage] = frozenset({DealStage.COMPLETED_AND_BILLED, DealStage.LOST})

# LƯU KHO: dự án hoàn thành quá bao nhiêu ngày thì rời khỏi bảng Kanban.
#
# Kho là thứ SUY RA từ `closed_at`, KHÔNG phải một cột trạng thái. Ba lý do, đều là né bẫy có
# thật chứ không phải cho gọn:
#
#   1. Mốc neo giá (`comparable_deal_values`) lấy 10 deal đã chốt gần nhất. Nếu lưu kho là một
#      `UPDATE`, `updated_at` đổi theo (`onupdate` + trigger PG) và thứ tự neo giá bị xáo theo
#      thứ tự LƯU KHO — giá gợi ý đổi mà không ai chạm vào giá.
#   2. `completed_and_billed` là giai đoạn cuối, `STAGE_TRANSITIONS` khai rỗng. Làm kho bằng
#      một giai đoạn thứ bảy là phải viết lại luật chuyển giai đoạn, và mọi chỗ đọc
#      `stage == "completed_and_billed"` (tỷ lệ thắng, neo giá) vỡ cùng lúc.
#   3. Suy ra thì không có gì để đồng bộ, và không thể lệch.
#
# 90 ngày = một quý: đủ dài để dự án vừa xong còn trong tầm mắt khi khách hỏi lại hay còn bảo
# hành, đủ ngắn để cột không phình. Đặt ở ĐÂY, cạnh luật giai đoạn, để truy vấn và giao diện
# không bao giờ hiểu khác nhau về "cũ".  #Huynh
ARCHIVE_AFTER_DAYS = 90
