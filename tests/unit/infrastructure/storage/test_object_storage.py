"""boto3 là thư viện ĐỒNG BỘ. Gọi thẳng nó trong hàm `async` là chặn event loop:
suốt lúc một người upload PDF 10MB lên S3, KHÔNG request nào khác được phục vụ —
cả API đứng hình, và nhìn ra ngoài thì giống hệt "server chậm".

Mấy test dưới đây bắt đúng chuyện đó bằng cách ĐO, không phải bằng cách đọc code:
cho boto3 giả ngủ 150ms (đồng bộ, y như boto3 thật khi đợi mạng), rồi đếm xem trong
lúc đó event loop còn chạy được việc khác không.

Nếu code gọi boto3 thẳng: bộ đếm đứng ở 0.
Nếu code đẩy boto3 sang thread khác (`asyncio.to_thread`): bộ đếm vẫn chạy.  #Huynh
"""

import asyncio
import time

from src.infrastructure.storage.object_storage import ObjectStorage

# Đủ dài để bộ đếm 10ms tích được vài chục nhịp, đủ ngắn để test không lê thê.
DO_TRE = 0.15
# Bị chặn thì bộ đếm ~0. Không bị chặn thì lý thuyết ~15 nhịp; đòi 5 cho máy CI chậm
# vẫn xanh, mà vẫn cách xa 0 để không bao giờ nhầm hai trạng thái với nhau.
NHIP_TOI_THIEU = 5


class _S3Gia:
    """boto3 giả: mọi lời gọi đều CHẬM và ĐỒNG BỘ — đúng bản chất boto3 thật."""

    def __init__(self, do_tre: float = DO_TRE) -> None:
        self.do_tre = do_tre
        self.da_goi: list[str] = []

    def put_object(self, **kwargs: object) -> dict:
        self.da_goi.append("put_object")
        time.sleep(self.do_tre)
        return {}

    def get_object(self, **kwargs: object) -> dict:
        self.da_goi.append("get_object")
        time.sleep(self.do_tre)

        class _Body:
            @staticmethod
            def read() -> bytes:
                return b"noi dung file"

        return {"Body": _Body(), "ContentType": "application/pdf"}

    def delete_object(self, **kwargs: object) -> dict:
        self.da_goi.append("delete_object")
        time.sleep(self.do_tre)
        return {}


class _BoDem:
    """Chạy nền, cứ 10ms cộng một nhịp. Nó là 'request khác' đang chờ được phục vụ."""

    def __init__(self) -> None:
        self.nhip = 0
        self._task: asyncio.Task | None = None

    async def _chay(self) -> None:
        while True:
            await asyncio.sleep(0.01)
            self.nhip += 1

    async def __aenter__(self) -> "_BoDem":
        self._task = asyncio.create_task(self._chay())
        await asyncio.sleep(0)  # nhường loop để task kịp khởi động
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._task is not None:
            self._task.cancel()


async def test_upload_khong_duoc_chan_event_loop() -> None:
    s3 = _S3Gia()
    storage = ObjectStorage(_client=s3)

    async with _BoDem() as dem:
        key = await storage.upload(
            data=b"gia lap mot file pdf",
            content_type="application/pdf",
            prefix="deals/abc",
            filename="brief.pdf",
        )

    assert s3.da_goi == ["put_object"], "phải thật sự gọi S3, không phải bỏ qua"
    assert key.startswith("deals/abc/"), "key phải nằm đúng thư mục đã yêu cầu"
    assert dem.nhip >= NHIP_TOI_THIEU, (
        f"event loop bị chặn suốt lúc upload: chỉ chạy được {dem.nhip} nhịp. "
        "boto3 đồng bộ phải được đẩy sang thread khác."
    )


async def test_download_khong_duoc_chan_event_loop() -> None:
    s3 = _S3Gia()
    storage = ObjectStorage(_client=s3)

    async with _BoDem() as dem:
        data, content_type = await storage.download("deals/abc/x.pdf")

    assert data == b"noi dung file"
    assert content_type == "application/pdf"
    assert dem.nhip >= NHIP_TOI_THIEU, (
        f"event loop bị chặn suốt lúc tải file: chỉ chạy được {dem.nhip} nhịp."
    )


async def test_delete_khong_duoc_chan_event_loop() -> None:
    s3 = _S3Gia()
    storage = ObjectStorage(_client=s3)

    async with _BoDem() as dem:
        await storage.delete("deals/abc/x.pdf")

    assert s3.da_goi == ["delete_object"]
    assert dem.nhip >= NHIP_TOI_THIEU, (
        f"event loop bị chặn suốt lúc xoá file: chỉ chạy được {dem.nhip} nhịp."
    )
