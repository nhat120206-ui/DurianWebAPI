# Hệ thống Chẩn đoán Bệnh Sầu Riêng (FastAPI + SQL Server + PyTorch)
python 3.14
## Bước 1: Chuẩn bị Cơ sở dữ liệu (SQL Server)
1. Mở SSMS và chạy file `CSDL.txt` của bạn để tạo CSDL `SauRieng`.
2. Chạy tiếp file `fix_constraint.sql` đi kèm trong thư mục này để sửa ràng buộc `processing_time_ms >= 0`.
3. Kiểm tra tên SQL Server trong `app/database.py` (`SERVER_NAME = "localhost"` hoặc `".\SQLEXPRESS"`).

## Bước 2: Đặt file trọng số AI (.pth)
Copy file `durian_efficientnet_b2.pth` của bạn vào thư mục:
`DurianWebAPI/saved_models/durian_efficientnet_b2.pth`

## Bước 3: Cài đặt thư viện & Chạy Web
```powershell
python -m venv venv
venv\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```
## Bước 4: chỉnh sửa kết nối đến db
tại `app\database.py`, sửa lại 
    SERVER_NAME = ".\SQLEXPRESS01" 
    DATABASE_NAME = "SauRieng" 
    cho phù hợp với csdl máy
## Chạy lệnh này trên thư mục để main.py
```
uvicorn main:app --reload
```
Truy cập: http://127.0.0.1:8000
- Tài khoản User mẫu: `user@phucdeptrai.vn` / `123456`
- Tài khoản Admin mẫu: `admin@phucdeptrai.vn` / `123456`
