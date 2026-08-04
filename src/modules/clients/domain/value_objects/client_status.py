from enum import StrEnum


class ClientStatus(StrEnum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ClientType(StrEnum):
    INDIVIDUAL = "individual"
    COMPANY = "company"


class CommChannel(StrEnum):
    """Kênh liên hệ của một dòng nhật ký trao đổi.

    PHẢI khớp từng giá trị với enum `comm_channel` dưới Postgres (xem
    `_comm_channel` trong infrastructure/database/models.py). Trước đây schema khai
    `channel: str` nên giá trị nào cũng qua được cửa pydantic rồi mới chết ở tầng
    INSERT — asyncpg ném InvalidTextRepresentation, handler cuối cùng bắt được và
    trả 500. Người gọi chỉ nhận "An unexpected error occurred", không hề biết là
    mình gõ sai tên kênh ("call" thay vì "phone").  #Huynh
    """

    EMAIL = "email"
    PHONE = "phone"
    MEETING = "meeting"
    MESSAGE = "message"
    ZALO = "zalo"


TERMINAL_CLIENT_STATUSES: frozenset[ClientStatus] = frozenset({ClientStatus.ARCHIVED})

CLIENT_STATUS_TRANSITIONS: dict[ClientStatus, frozenset[ClientStatus]] = {
    ClientStatus.PROSPECT: frozenset({ClientStatus.ACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.ACTIVE: frozenset({ClientStatus.INACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.INACTIVE: frozenset({ClientStatus.ACTIVE, ClientStatus.ARCHIVED}),
    ClientStatus.ARCHIVED: frozenset(),
}
