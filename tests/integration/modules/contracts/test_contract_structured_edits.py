"""Chữ freelancer sửa trong các điều CÓ SẴN của hợp đồng phải được lưu và in ra tờ giấy.

Khung sửa tại chỗ của web ghi chữ sửa vào ba khoá gom — `clause_texts` (chữ trong điều),
`section_titles` (tên điều), `extra_sections` (đầu mục tự soạn). Trước đây nó ghi thẳng vào
`clause_party_a_duties`, `title_party_a_duties`... một khoá mà bộ dựng giấy không bao giờ đọc: chữ
hiện trên màn, nhưng mở lại là về mặc định và bản gửi khách cũng là bản mặc định.

Test này khoá hợp đồng phía backend mà web dựa vào: ghi đúng ba khoá gom thì tờ giấy đổi, còn ghi
khoá `clause_*` / `title_*` thì KHÔNG (để ai quay lại cách ghi cũ thì bài đỏ ngay).  #Huynh
"""

from httpx import AsyncClient

from tests.integration.modules.contracts.test_contracts_api import (
    _auth,
    _create_accepted_proposal,
    _create_client,
    _create_contract,
    _create_deal,
)


async def _hop_dong(client: AsyncClient, headers: dict) -> tuple[str, dict]:
    client_id = await _create_client(client, headers)
    deal_id = await _create_deal(client, headers, client_id)
    proposal_id = await _create_accepted_proposal(client, headers, deal_id)
    contract_id = await _create_contract(client, headers, deal_id, proposal_id, client_id)
    got = (await client.get(f"/api/v1/contracts/{contract_id}", headers=headers)).json()["data"]
    ids = {k: got[k] for k in ("deal_id", "proposal_id", "client_id")}
    return contract_id, {**ids, "content": got["content"]}


async def _luu(client: AsyncClient, headers: dict, contract_id: str, base: dict, **content) -> None:
    resp = await client.patch(
        f"/api/v1/contracts/{contract_id}",
        json={**{k: base[k] for k in ("deal_id", "proposal_id", "client_id")},
              "content": {**base["content"], **content}},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text


async def _giay(client: AsyncClient, headers: dict, contract_id: str) -> str:
    resp = await client.get(f"/api/v1/contracts/{contract_id}/preview", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["html"]


class TestChuSuaTrongDieuCoSan:
    async def test_chu_trong_dieu_duoc_ghi_vao_clause_texts_thi_hien_tren_giay(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        cid, base = await _hop_dong(client, headers)

        await _luu(
            client, headers, cid, base,
            clause_texts={
                "party_a_duties": ["Bên A làm đúng hạn", "Bên A báo cáo hằng tuần"],
                "dispute": "Tranh chấp được giải quyết tại VIAC.",
            },
        )
        html = await _giay(client, headers, cid)

        assert "Bên A báo cáo hằng tuần" in html
        assert "Tranh chấp được giải quyết tại VIAC." in html

    async def test_ten_dieu_duoc_ghi_vao_section_titles_thi_hien_tren_giay(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        cid, base = await _hop_dong(client, headers)

        await _luu(client, headers, cid, base, section_titles={"party_a_duties": "Nghĩa vụ riêng"})

        assert "Nghĩa vụ riêng" in await _giay(client, headers, cid)

    async def test_dau_muc_tu_soan_duoc_ghi_vao_extra_sections_thi_hien_tren_giay(
        self, client: AsyncClient
    ) -> None:
        headers = await _auth(client)
        cid, base = await _hop_dong(client, headers)

        await _luu(
            client, headers, cid, base,
            extra_sections=[
                {"title": "Quyền sử dụng hình ảnh", "body": "Khách dùng trong một năm."}
            ],
        )
        html = await _giay(client, headers, cid)

        assert "Quyền sử dụng hình ảnh" in html
        assert "Khách dùng trong một năm." in html

    async def test_ghi_thang_khoa_clause_va_title_thi_giay_khong_doi(
        self, client: AsyncClient
    ) -> None:
        """Cách ghi CŨ của web: lưu được (200) mà không có tác dụng gì. Khoá để không quay lại."""
        headers = await _auth(client)
        cid, base = await _hop_dong(client, headers)

        await _luu(
            client, headers, cid, base,
            clause_party_a_duties="Chữ này không bao giờ lên giấy",
            title_party_a_duties="Tên này cũng không",
        )
        html = await _giay(client, headers, cid)

        assert "Chữ này không bao giờ lên giấy" not in html
        assert "Tên này cũng không" not in html
