import json
import os
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from passlib.context import CryptContext

from app.database import SessionLocal, get_db
from app import models
from app.ai_model import load_ai_model, predict_image_top3, check_disease_map

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(os.path.join(BASE_DIR, "static", "uploads"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "saved_models"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "templates"), exist_ok=True)

app = FastAPI(title="Hệ thống Chẩn đoán Bệnh Sầu Riêng")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ACTIVE_MODEL_CACHE = {"model_id": None, "model_obj": None, "model_path": None}

# Thư mục lưu mô hình (tự nhận saved_models cạnh main.py, có thể ghi đè bằng biến môi trường)
MODEL_STORAGE_DIR = os.getenv(
    "DURIAN_MODEL_STORAGE_DIR",
    os.path.join(BASE_DIR, "saved_models")
)
MAX_MODEL_UPLOAD_BYTES = int(os.getenv("MAX_MODEL_UPLOAD_BYTES", str(1024 ** 3)))  # Mặc định 1 GB
ALLOWED_MODEL_EXTENSIONS = {".pth", ".pt"}
SUPPORTED_MODEL_NAMES = ("efficientnet", "resnet", "vgg")
os.makedirs(MODEL_STORAGE_DIR, exist_ok=True)
CLASS_NAMES_PATH = os.path.join(MODEL_STORAGE_DIR, "class_names.json")

DEFAULT_MODEL_CANDIDATES = [
    ("best_efficientnet_b2.pth", "EfficientNet-B2", "v1.0"),
    ("durian_efficientnet_b2.pth", "EfficientNet-B2", "v1.0"),
    ("durian_resnet18.pth", "ResNet18", "v1.0"),
    ("durian_vgg16.pth", "VGG16", "v1.0"),
]


def get_disease_map(db: Session) -> dict[str, int]:
    """Ánh xạ class_key -> disease_id từ bảng Benh."""
    rows = (
        db.query(models.Benh)
        .filter(models.Benh.class_key.isnot(None))
        .all()
    )
    return {row.class_key: row.disease_id for row in rows}


def _read_default_model_metrics(model_name: str) -> tuple[float, float]:
    """Đọc accuracy & f1_score từ meta.json nếu có, mặc định (0.0, 0.0)."""
    meta_path = os.path.join(MODEL_STORAGE_DIR, "meta.json")
    if not os.path.exists(meta_path):
        return 0.0, 0.0
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        info = meta.get("metrics", {}).get(model_name) or meta.get(model_name) or {}
        acc = float(info.get("test_accuracy", info.get("accuracy", 0.0)))
        f1 = float(info.get("weighted_f1", info.get("f1_score", 0.0)))
        acc = acc if 0.0 <= acc <= 1.0 else 0.0
        f1 = f1 if 0.0 <= f1 <= 1.0 else 0.0
        return acc, f1
    except Exception:
        return 0.0, 0.0


def get_active_ai_model(db: Session):
    """Lấy và kiểm tra phiên bản mô hình đang kích hoạt (is_active = 1) trong CSDL."""
    active_ver = db.query(models.PhienBanMoHinh).filter(models.PhienBanMoHinh.is_active == True).first()
    if not active_ver:
        raise HTTPException(
            status_code=503,
            detail="Hệ thống chưa có mô hình AI nào được kích hoạt. Vui lòng liên hệ quản trị viên."
        )
    if not os.path.exists(active_ver.model_path):
        raise HTTPException(
            status_code=503,
            detail=f"Không tìm thấy tệp mô hình tại: {active_ver.model_path}"
        )

    if (
        ACTIVE_MODEL_CACHE["model_id"] != active_ver.model_id
        or ACTIVE_MODEL_CACHE["model_path"] != active_ver.model_path
        or ACTIVE_MODEL_CACHE["model_obj"] is None
    ):
        try:
            model_obj = load_ai_model(
                active_ver.model_path,
                active_ver.model_name,
                class_names_path=CLASS_NAMES_PATH
            )
            check_disease_map(model_obj.class_names, get_disease_map(db))
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Không thể nạp mô hình AI đang kích hoạt: {exc}"
            )
        ACTIVE_MODEL_CACHE["model_obj"] = model_obj
        ACTIVE_MODEL_CACHE["model_id"] = active_ver.model_id
        ACTIVE_MODEL_CACHE["model_path"] = active_ver.model_path

    return active_ver, ACTIVE_MODEL_CACHE["model_obj"]


def _auto_register_default_model(db: Session) -> None:
    """Khi khởi động, nếu chưa có model nào trong CSDL thì tự tìm 1 checkpoint hợp lệ để đăng ký."""
    if db.query(models.PhienBanMoHinh).first():
        return

    if not os.path.exists(CLASS_NAMES_PATH):
        print(f"[STARTUP] Không tìm thấy {CLASS_NAMES_PATH}. Vui lòng thêm model ở giao diện Admin.")
        return

    disease_map = get_disease_map(db)
    for filename, model_name, version in DEFAULT_MODEL_CANDIDATES:
        candidate_path = os.path.abspath(os.path.join(MODEL_STORAGE_DIR, filename))
        if not os.path.exists(candidate_path):
            continue
        try:
            candidate_model = load_ai_model(
                candidate_path,
                model_name,
                class_names_path=CLASS_NAMES_PATH
            )
            check_disease_map(candidate_model.class_names, disease_map)
            acc, f1 = _read_default_model_metrics(model_name)

            new_ver = models.PhienBanMoHinh(
                model_name=model_name,
                version=version,
                model_path=candidate_path,
                accuracy=acc,
                f1_score=f1,
                is_active=True
            )
            db.add(new_ver)
            db.commit()
            db.refresh(new_ver)

            ACTIVE_MODEL_CACHE.update({
                "model_id": new_ver.model_id,
                "model_obj": candidate_model,
                "model_path": candidate_path
            })
            print(f"[STARTUP] Đã tự động đăng ký và kích hoạt model mặc định: {model_name} ({filename})")
            return
        except Exception as exc:
            db.rollback()
            print(f"[STARTUP] Bỏ qua checkpoint {filename} do không hợp lệ: {exc}")

    print("[STARTUP] Chưa có checkpoint hợp lệ trong saved_models. Hệ thống vẫn khởi động — Admin cần thêm model qua giao diện.")


@app.on_event("startup")
def seed_initial_data():
    db = SessionLocal()
    try:
        _auto_register_default_model(db)
    except Exception as e:
        db.rollback()
        print("[STARTUP] Lưu ý khi khởi tạo model mặc định:", e)
    finally:
        db.close()


# =====================================================================
# GIAO DIỆN CHÍNH
# =====================================================================
@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# =====================================================================
# XÁC THỰC KHÔNG COOKIE / SESSION
# =====================================================================
basic_security = HTTPBasic(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPBasicCredentials] = Depends(basic_security),
    db: Session = Depends(get_db)
):
    """Xác minh email/mật khẩu trên từng request; không tạo cookie/session/token."""
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Vui lòng đăng nhập.",
            headers={"WWW-Authenticate": "Basic"}
        )
    user = db.query(models.NguoiDung).filter_by(email=credentials.username).first()
    if not user or not pwd_context.verify(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Thông tin đăng nhập không hợp lệ.",
            headers={"WWW-Authenticate": "Basic"}
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa.")
    return user


def require_admin(current_user: models.NguoiDung = Depends(get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Bạn không có quyền quản trị chức năng này.")
    return current_user


@app.get("/api/model-status")
def get_model_status(
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kiểm tra hệ thống đã có mô hình AI hoạt động hay chưa."""
    has_models = db.query(models.PhienBanMoHinh).first() is not None
    active_ver = db.query(models.PhienBanMoHinh).filter(models.PhienBanMoHinh.is_active == True).first()
    if not active_ver:
        return {
            "available": False,
            "has_models": has_models,
            "message": "Hệ thống chưa có mô hình AI nào được kích hoạt. Quản trị viên cần thêm hoặc kích hoạt mô hình."
        }
    try:
        active_ver, _ = get_active_ai_model(db)
        return {
            "available": True,
            "has_models": True,
            "model_id": active_ver.model_id,
            "model_name": active_ver.model_name,
            "version": active_ver.version,
            "message": f"Đang sử dụng mô hình {active_ver.model_name} ({active_ver.version})."
        }
    except HTTPException as exc:
        return {
            "available": False,
            "has_models": has_models,
            "message": exc.detail
        }


@app.post("/api/auth/login")
def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(models.NguoiDung).filter_by(email=email).first()
    if not user or not pwd_context.verify(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không chính xác.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.")
    return {
        "user_id": user.user_id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role
    }


@app.post("/api/auth/register")
def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Mật khẩu và xác nhận mật khẩu không khớp.")
    if db.query(models.NguoiDung).filter(models.NguoiDung.email == email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại trong hệ thống.")
    new_user = models.NguoiDung(
        full_name=full_name,
        email=email,
        password_hash=pwd_context.hash(password),
        role="User",
        is_active=True
    )
    db.add(new_user)
    db.commit()
    return {"message": "Đăng ký tài khoản thành công! Bạn có thể đăng nhập."}


@app.put("/api/profile/{user_id}")
def update_profile(
    user_id: int,
    full_name: Optional[str] = Form(None),
    current_password: Optional[str] = Form(None),
    new_password: Optional[str] = Form(None),
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Bạn không thể cập nhật tài khoản khác.")
    user = db.query(models.NguoiDung).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    if full_name:
        user.full_name = full_name
    if current_password and new_password:
        if not pwd_context.verify(current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không chính xác.")
        user.password_hash = pwd_context.hash(new_password)
    db.commit()
    return {"message": "Cập nhật thông tin cá nhân thành công!", "full_name": user.full_name}


# =====================================================================
# NHÓM USE CASE NGƯỜI DÙNG: CHẨN ĐOÁN, LỊCH SỬ, PHẢN HỒI, TRA CỨU
# =====================================================================
@app.post("/api/diagnose")
def diagnose_image(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Không thể chẩn đoán bằng tài khoản khác.")

    # Kiểm tra model đang hoạt động TRƯỚC khi lưu ảnh và tạo bản ghi
    active_ver, model_obj = get_active_ai_model(db)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        raise HTTPException(status_code=400, detail="Định dạng ảnh không hợp lệ (chỉ nhận .jpg, .png, .webp).")

    saved_filename = f"{uuid.uuid4().hex}{ext}"
    rel_path = f"static/uploads/{saved_filename}"
    abs_upload_path = os.path.join(BASE_DIR, "static", "uploads", saved_filename)
    with open(abs_upload_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    diag = models.ChanDoan(
        user_id=user_id,
        model_id=active_ver.model_id,
        image_path=f"/{rel_path}",
        status="Pending",
        is_uncertain=False
    )
    db.add(diag)
    db.commit()
    db.refresh(diag)

    try:
        disease_map = get_disease_map(db)
        pred_out = predict_image_top3(abs_upload_path, model_obj, threshold=0.50, disease_map=disease_map)
        diag.status = "Completed"
        diag.is_uncertain = pred_out["is_uncertain"]
        diag.processing_time_ms = pred_out["processing_time_ms"]

        detailed_top3 = []
        for item in pred_out["top3"]:
            kq = models.KetQuaChanDoan(
                diagnosis_id=diag.diagnosis_id,
                disease_id=item["disease_id"],
                rank_no=item["rank_no"],
                confidence_score=item["confidence_score"]
            )
            db.add(kq)

            disease = db.query(models.Benh).options(joinedload(models.Benh.treatments)).filter_by(
                disease_id=item["disease_id"]
            ).first()

            detailed_top3.append({
                "rank_no": item["rank_no"],
                "disease_id": item["disease_id"],
                "disease_name": disease.disease_name if disease else f"Lớp #{item['disease_id']}",
                "confidence_percent": round(item["confidence_score"] * 100, 2),
                "symptoms": disease.symptoms if disease else "",
                "description": disease.description if disease else "",
                "treatments": [
                    {
                        "treatment_name": t.treatment_name,
                        "treatment_type": t.treatment_type,
                        "description": t.description,
                        "prevention": t.prevention
                    } for t in (disease.treatments if disease else [])
                ]
            })

        db.commit()
        return {
            "diagnosis_id": diag.diagnosis_id,
            "image_path": diag.image_path,
            "status": diag.status,
            "is_uncertain": diag.is_uncertain,
            "is_healthy": pred_out.get("is_healthy", False),
            "processing_time_ms": diag.processing_time_ms,
            "model_used": f"{active_ver.model_name} ({active_ver.version})",
            "top3": detailed_top3
        }
    except Exception as e:
        diag.status = "Failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Lỗi khi chạy mô hình chẩn đoán: {str(e)}")


@app.get("/api/history/{user_id}")
def get_user_history(
    user_id: int,
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Không thể xem lịch sử của tài khoản khác.")
    records = (
        db.query(models.ChanDoan)
        .options(joinedload(models.ChanDoan.results).joinedload(models.KetQuaChanDoan.disease))
        .filter(models.ChanDoan.user_id == user_id)
        .order_by(models.ChanDoan.diagnosis_date.desc())
        .all()
    )
    output = []
    for r in records:
        sorted_res = sorted(r.results, key=lambda x: x.rank_no)
        top1_name = sorted_res[0].disease.disease_name if sorted_res and sorted_res[0].disease else "N/A"
        top1_conf = round(float(sorted_res[0].confidence_score) * 100, 2) if sorted_res else 0
        output.append({
            "diagnosis_id": r.diagnosis_id,
            "image_path": r.image_path,
            "diagnosis_date": r.diagnosis_date.strftime("%d/%m/%Y %H:%M:%S") if r.diagnosis_date else "",
            "status": r.status,
            "is_uncertain": r.is_uncertain,
            "top1_disease": top1_name,
            "top1_confidence": top1_conf,
            "is_correct": r.is_correct
        })
    return output


@app.delete("/api/history/{diagnosis_id}")
def delete_history(
    diagnosis_id: int,
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    diag = db.query(models.ChanDoan).filter_by(diagnosis_id=diagnosis_id).first()
    if not diag:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi chẩn đoán.")
    if diag.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Không thể xóa lịch sử của tài khoản khác.")
    db.delete(diag)
    db.commit()
    return {"message": "Đã xóa lịch sử chẩn đoán thành công."}


@app.post("/api/diagnose/{diagnosis_id}/feedback")
def submit_feedback(
    diagnosis_id: int,
    is_correct: bool = Form(...),
    actual_disease_id: Optional[int] = Form(None),
    current_user: models.NguoiDung = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    diag = db.query(models.ChanDoan).filter_by(diagnosis_id=diagnosis_id).first()
    if not diag:
        raise HTTPException(status_code=404, detail="Không tìm thấy lần chẩn đoán.")
    if diag.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="Không thể phản hồi chẩn đoán của tài khoản khác.")
    diag.is_correct = is_correct
    diag.actual_disease_id = None if is_correct else actual_disease_id
    db.commit()
    return {"message": "Cảm ơn bạn đã gửi phản hồi chất lượng chẩn đoán!"}


@app.get("/api/diseases")
def search_diseases(keyword: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Benh).options(joinedload(models.Benh.treatments))
    if keyword:
        query = query.filter(models.Benh.disease_name.ilike(f"%{keyword}%"))
    diseases = query.order_by(models.Benh.disease_id).all()
    return [
        {
            "disease_id": d.disease_id,
            "disease_name": d.disease_name,
            "symptoms": d.symptoms or "",
            "description": d.description or "",
            "treatments": [
                {
                    "treatment_id": t.treatment_id,
                    "treatment_name": t.treatment_name,
                    "treatment_type": t.treatment_type,
                    "description": t.description,
                    "prevention": t.prevention
                } for t in d.treatments
            ]
        } for d in diseases
    ]


# =====================================================================
# NHÓM USE CASE QUẢN TRỊ VIÊN
# =====================================================================
@app.get("/api/admin/users")
def list_users(admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(models.NguoiDung).order_by(models.NguoiDung.user_id).all()
    return [
        {
            "user_id": u.user_id,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.strftime("%d/%m/%Y") if u.created_at else ""
        } for u in users
    ]


@app.post("/api/admin/users")
def create_admin_user(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("User"),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Họ và tên không được để trống.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 6 ký tự.")
    if role not in ("Admin", "User"):
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ.")
    if db.query(models.NguoiDung).filter(models.NguoiDung.email == email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại trong hệ thống.")
    user = models.NguoiDung(
        full_name=full_name, email=email, password_hash=pwd_context.hash(password),
        role=role, is_active=True
    )
    db.add(user)
    db.commit()
    return {"message": "Đã thêm người dùng thành công.", "user_id": user.user_id}


@app.put("/api/admin/users/{user_id}")
def update_admin_user(
    user_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    password: Optional[str] = Form(None),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip()
    if not full_name:
        raise HTTPException(status_code=400, detail="Họ và tên không được để trống.")
    if role not in ("Admin", "User"):
        raise HTTPException(status_code=400, detail="Vai trò không hợp lệ.")
    user = db.query(models.NguoiDung).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    duplicate = db.query(models.NguoiDung).filter(
        models.NguoiDung.email == email, models.NguoiDung.user_id != user_id
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="Email đã được sử dụng bởi tài khoản khác.")
    if user_id == admin.user_id and role != "Admin":
        raise HTTPException(status_code=400, detail="Không thể hạ quyền Admin của tài khoản đang đăng nhập.")
    if user.role == "Admin" and role != "Admin":
        admin_count = db.query(models.NguoiDung).filter_by(role="Admin", is_active=True).count()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Không thể hạ quyền Admin cuối cùng đang hoạt động.")
    if password and len(password) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu mới phải có ít nhất 6 ký tự.")
    user.full_name = full_name
    user.email = email
    user.role = role
    if password:
        user.password_hash = pwd_context.hash(password)
    db.commit()
    return {
        "message": "Đã cập nhật người dùng thành công.",
        "user_id": user.user_id,
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role
    }


@app.post("/api/admin/users/{user_id}/toggle-lock")
def toggle_user_lock(
    user_id: int,
    current_admin_id: int = Form(...),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if current_admin_id != admin.user_id:
        raise HTTPException(status_code=403, detail="Thông tin quản trị viên không hợp lệ.")
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Không thể khóa chính tài khoản đang sử dụng.")
    user = db.query(models.NguoiDung).filter_by(user_id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng.")
    user.is_active = not user.is_active
    db.commit()
    return {"message": "Đã cập nhật trạng thái tài khoản.", "is_active": user.is_active}


@app.post("/api/admin/diseases")
def save_disease(
    disease_id: Optional[int] = Form(None),
    disease_name: str = Form(...),
    symptoms: str = Form(""),
    description: str = Form(""),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if disease_id:
        d = db.query(models.Benh).filter_by(disease_id=disease_id).first()
        if not d:
            raise HTTPException(status_code=404, detail="Không tìm thấy bệnh.")
        d.disease_name = disease_name
        d.symptoms = symptoms
        d.description = description
    else:
        d = models.Benh(disease_name=disease_name, symptoms=symptoms, description=description)
        db.add(d)
    db.commit()
    return {"message": "Đã lưu thông tin danh mục bệnh."}


@app.post("/api/admin/treatments")
def add_treatment(
    disease_id: int = Form(...),
    treatment_name: str = Form(...),
    treatment_type: str = Form(...),
    description: str = Form(""),
    prevention: str = Form(""),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    t = models.BienPhap(
        disease_id=disease_id,
        treatment_name=treatment_name,
        treatment_type=treatment_type,
        description=description,
        prevention=prevention
    )
    db.add(t)
    db.commit()
    return {"message": "Đã thêm biện pháp xử lý thành công."}


@app.delete("/api/admin/treatments/{treatment_id}")
def delete_treatment(treatment_id: int, admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.query(models.BienPhap).filter_by(treatment_id=treatment_id).first()
    if t:
        db.delete(t)
        db.commit()
    return {"message": "Đã xóa biện pháp xử lý."}

@app.get("/api/admin/models")
def list_models(admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(models.PhienBanMoHinh)
        .options(joinedload(models.PhienBanMoHinh.training_data))
        .order_by(models.PhienBanMoHinh.model_id)
        .all()
    )
    return [
        {
            "model_id": m.model_id,
            "model_name": m.model_name,
            "version": m.version,
            "model_path": m.model_path,
            "accuracy": m.accuracy,
            "f1_score": m.f1_score,
            "is_active": m.is_active,
            "training_data": {
                "file_format": m.training_data.file_format,
                "file_size": m.training_data.file_size,
                "source": m.training_data.source,
                "description": m.training_data.description,
            } if m.training_data else None
        }
        for m in rows
    ]


@app.post("/api/admin/models")
async def add_model_version(
    model_name: str = Form(...),
    version: str = Form(...),
    accuracy: float = Form(...),
    f1_score: float = Form(...),
    file: UploadFile = File(...),
    file_format: str = Form(...),
    file_size: Optional[int] = Form(None),
    source: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    admin: models.NguoiDung = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Nhận file PyTorch .pth/.pt kèm bắt buộc thông tin DuLieuHuanLuyen (1-1)."""
    if not (0 <= accuracy <= 1 and 0 <= f1_score <= 1):
        raise HTTPException(status_code=400, detail="Accuracy và F1-Score phải nằm trong khoảng 0 đến 1.")

    if not any(key in model_name.lower() for key in SUPPORTED_MODEL_NAMES):
        raise HTTPException(
            status_code=400,
            detail="Kiến trúc chưa hỗ trợ. Chỉ hỗ trợ EfficientNet-B2, ResNet18 hoặc VGG16."
        )

    clean_format = file_format.strip()
    if not clean_format or len(clean_format) > 10:
        raise HTTPException(status_code=400, detail="Định dạng dữ liệu huấn luyện là bắt buộc (tối đa 10 ký tự).")

    if file_size is not None and file_size < 0:
        raise HTTPException(status_code=400, detail="Dung lượng dữ liệu huấn luyện không được âm.")

    original_name = (file.filename or "").strip()
    extension = os.path.splitext(original_name)[1].lower()
    if extension not in ALLOWED_MODEL_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận tệp mô hình .pth hoặc .pt.")

    safe_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(MODEL_STORAGE_DIR, exist_ok=True)
    destination = os.path.abspath(os.path.join(MODEL_STORAGE_DIR, safe_name))
    bytes_written = 0

    try:
        with open(destination, "xb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_MODEL_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Tệp vượt quá giới hạn {MAX_MODEL_UPLOAD_BYTES // (1024 ** 2)} MB."
                    )
                output.write(chunk)

        if bytes_written == 0:
            raise HTTPException(status_code=400, detail="Tệp mô hình đang trống.")

        m = models.PhienBanMoHinh(
            model_name=model_name.strip(),
            version=version.strip(),
            model_path=destination,
            accuracy=accuracy,
            f1_score=f1_score,
            is_active=False
        )
        db.add(m)
        db.flush()  # Lấy model_id vừa tạo để gắn cho DuLieuHuanLuyen (1-1)

        dl = models.DuLieuHuanLuyen(
            model_id=m.model_id,
            file_format=clean_format,
            file_size=file_size,
            source=(source.strip() or None) if source else None,
            description=(description.strip() or None) if description else None,
        )
        db.add(dl)
        db.commit()
        db.refresh(m)

        return {
            "message": "Đã tải lên mô hình và lưu dữ liệu huấn luyện thành công.",
            "model_id": m.model_id,
            "file_name": safe_name,
            "model_path": destination
        }
    except HTTPException:
        db.rollback()
        if os.path.exists(destination):
            os.remove(destination)
        raise
    except Exception as exc:
        db.rollback()
        if os.path.exists(destination):
            os.remove(destination)
        raise HTTPException(status_code=500, detail=f"Không thể lưu phiên bản mô hình: {exc}")
    finally:
        await file.close()
@app.post("/api/admin/models/{model_id}/activate")
def activate_model(model_id: int, admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.query(models.PhienBanMoHinh).filter_by(model_id=model_id).first()
    if not target or not os.path.exists(target.model_path):
        raise HTTPException(status_code=400, detail="Tệp mô hình không tồn tại, không thể kích hoạt.")
    try:
        model_obj = load_ai_model(target.model_path, target.model_name, class_names_path=CLASS_NAMES_PATH)
        check_disease_map(model_obj.class_names, get_disease_map(db))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Mô hình không tương thích, không thể kích hoạt: {exc}")

    db.query(models.PhienBanMoHinh).update({models.PhienBanMoHinh.is_active: False})
    target.is_active = True
    db.commit()
    ACTIVE_MODEL_CACHE.update({
        "model_id": target.model_id,
        "model_obj": model_obj,
        "model_path": target.model_path
    })
    return {"message": f"Đã kích hoạt mô hình {target.model_name} ({target.version})."}


@app.get("/api/admin/stats")
def get_system_stats(admin: models.NguoiDung = Depends(require_admin), db: Session = Depends(get_db)):
    total = db.query(models.ChanDoan).count()
    uncertain = db.query(models.ChanDoan).filter_by(is_uncertain=True).count()
    failed = db.query(models.ChanDoan).filter_by(status="Failed").count()
    correct_fb = db.query(models.ChanDoan).filter_by(is_correct=True).count()
    wrong_fb = db.query(models.ChanDoan).filter_by(is_correct=False).count()

    wrong_cases = (
        db.query(models.ChanDoan)
        .filter(models.ChanDoan.is_correct == False)
        .order_by(models.ChanDoan.diagnosis_date.desc())
        .limit(20)
        .all()
    )
    wrong_list = []
    for w in wrong_cases:
        actual = db.query(models.Benh).filter_by(disease_id=w.actual_disease_id).first()
        wrong_list.append({
            "diagnosis_id": w.diagnosis_id,
            "date": w.diagnosis_date.strftime("%d/%m/%Y %H:%M") if w.diagnosis_date else "",
            "image_path": w.image_path,
            "actual_disease": actual.disease_name if actual else "Chưa rõ"
        })

    return {
        "total_diagnoses": total,
        "uncertain_count": uncertain,
        "failed_count": failed,
        "correct_feedback": correct_fb,
        "wrong_feedback": wrong_fb,
        "wrong_cases": wrong_list
    }