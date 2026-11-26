import json
import time
from pathlib import Path

import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image, ImageOps

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# Khớp tập Test lúc train: Resize thẳng về 224x224, chuẩn hoá ImageNet
test_transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])


def load_ai_model(model_path: str, model_name: str = "EfficientNet-B2", class_names_path: str | None = None):
    """Nạp model. File class_names.json phải nằm cùng thư mục với file .pth (hoặc truyền class_names_path)."""
    model_path = Path(model_path)
    cn_path = Path(class_names_path) if class_names_path else model_path.with_name("class_names.json")
    if not cn_path.exists():
        raise FileNotFoundError(f"Thiếu {cn_path}. Hãy chép class_names.json của đúng lần train này cạnh file model.")
    class_names = json.loads(cn_path.read_text(encoding="utf-8"))
    num_classes = len(class_names)

    name_lower = model_name.lower()
    if "efficientnet" in name_lower:
        head_key = "classifier.1.weight"
        model = models.efficientnet_b2(weights=None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    elif "resnet" in name_lower:
        head_key = "fc.weight"
        model = models.resnet18(weights=None)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
    elif "vgg" in name_lower:
        head_key = "classifier.6.weight"
        model = models.vgg16(weights=None)
        model.classifier[6] = nn.Linear(model.classifier[6].in_features, num_classes)
    else:
        raise ValueError(f"Kiến trúc chưa hỗ trợ: {model_name}")

    state_dict = torch.load(model_path, map_location=device)
    if state_dict[head_key].shape[0] != num_classes:
        raise ValueError(
            f"File model có {state_dict[head_key].shape[0]} lớp nhưng class_names.json có {num_classes} lớp. "
            f"Hai file này không cùng một lần train."
        )
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    model.class_names = class_names          # giữ danh sách lớp đi kèm model
    return model


def check_disease_map(class_names: list[str], disease_map: dict[str, int]) -> None:
    """Gọi 1 lần khi khởi động: báo ngay nếu bảng Benh thiếu bệnh nào của model."""
    missing = [c for c in class_names if c not in disease_map]
    if missing:
        raise RuntimeError("Bảng Benh chưa có class_key cho: " + ", ".join(missing))    


def predict_image_top3(image_path: str, model, threshold: float = 0.50, *, disease_map: dict[str, int], tiles: int = 3):
    start_time = time.perf_counter()
    img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")

    with torch.no_grad():
        whole = torch.softmax(model(test_transform(img).unsqueeze(0).to(device)), dim=1)[0]
        if tiles >= 2:
            batch = torch.stack([test_transform(p) for p in _tiles(img, tiles)]).to(device)
            probs = torch.softmax(model(batch), dim=1).mean(dim=0)       # trung bình các ô
        else:
            probs = whole
        top_probs, top_idxs = torch.topk(probs, min(3, len(model.class_names)))

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    top3_results = []
    for rank, (prob, idx) in enumerate(zip(top_probs, top_idxs), start=1):
        class_name = model.class_names[int(idx.item())]
        top3_results.append({
            "rank_no": rank,
            "class_name": class_name,
            "disease_id": disease_map[class_name],
            "confidence_score": round(float(prob.item()), 4)
        })

    return {
        "top3": top3_results,
        "is_uncertain": top3_results[0]["confidence_score"] < threshold,
        "views_disagree": bool(whole.argmax() != probs.argmax()),   # cả ảnh và các ô cho kết quả khác nhau
        "is_healthy": top3_results[0]["class_name"] == "healthy_leaf",
        "processing_time_ms": elapsed_ms
    }

def _tiles(img, n):
    w, h = img.size
    return [img.crop((c * w // n, r * h // n, (c + 1) * w // n, (r + 1) * h // n))
            for r in range(n) for c in range(n)]