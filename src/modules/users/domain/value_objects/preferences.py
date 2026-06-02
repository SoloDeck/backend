from dataclasses import dataclass


@dataclass(frozen=True)
class Preferences:
    locale: str                     # e.g. "vi", "en"
    timezone: str                   # IANA tz string e.g. "Asia/Ho_Chi_Minh"
    notification_channel: str       # "email" | "in_app" | "both" | "zalo"
    theme: str                      # "light" | "dark"

    VALID_CHANNELS = frozenset({"email", "in_app", "both", "zalo"})
    VALID_THEMES = frozenset({"light", "dark"})

    def __post_init__(self) -> None:
        if self.notification_channel not in self.VALID_CHANNELS:
            raise ValueError(f"Invalid notification_channel: {self.notification_channel!r}")
        if self.theme not in self.VALID_THEMES:
            raise ValueError(f"Invalid theme: {self.theme!r}")

    @classmethod
    def default_vietnamese(cls) -> "Preferences":
        return cls(
            locale="vi",
            timezone="Asia/Ho_Chi_Minh",
            notification_channel="both",
            theme="light",
        )
