============================================================
  SOLODESK API - TEST FILES
  Server: http://localhost:8000
  Swagger UI: http://localhost:8000/docs
============================================================

FILES:
  01_auth.txt       - Dang ky, dang nhap, dang xuat
  02_users.txt      - Xem/cap nhat profile
  03_clients.txt    - Quan ly khach hang
  04_deals.txt      - Quan ly deal + AI qualification
  05_proposals.txt  - Quan ly de xuat + tao PDF
  06_intake_form.txt - Form tiep nhan khach hang (public)
  07_admin.txt      - Quan tri vien

HUONG DAN SU DUNG:
  1. Chay server: uvicorn src.main:app --reload --port 8000
  2. Dang ky tai khoan: xem 01_auth.txt -> REGISTER
  3. Dang nhap, copy access_token tu response
  4. Thay <TOKEN> bang access_token trong cac lenh curl
  5. Chay tung buoc theo thu tu (tao client truoc, roi tao deal, roi tao proposal)

LUONG TEST CHINH:
  Register -> Login -> Get Me (lay intake_token)
  -> Create Client -> Create Deal
  -> Qualify Deal (AI)
  -> Create Proposal -> Generate PDF
  -> Submit Public Intake Form

CHU Y:
  - <TOKEN>        = access_token tu login
  - <ADMIN_TOKEN>  = access_token cua tai khoan co role=admin
  - <CLIENT_ID>    = id tu response cua Create Client
  - <DEAL_ID>      = id tu response cua Create Deal
  - <PROPOSAL_ID>  = id tu response cua Create Proposal
  - <INTAKE_TOKEN> = intake_share_token tu GET /users/me
  - PDF endpoint tra ve file nhi phan, dung --output de luu file
