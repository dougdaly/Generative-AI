import numpy as np
import cv2
import pytesseract
from PIL import Image
import re
from typing import Tuple, Dict, Any
import math
from pathlib import Path
import cv2

# HELPER FUNCTIONS

def _rotate_upright(arr_bgr, rot: int):
    import cv2
    # Tesseract's "Rotate" is the correction rotation needed.
    # The direction is the gotcha; this mapping matches typical OSD behavior.
    if rot == 90:
        return cv2.rotate(arr_bgr, cv2.ROTATE_90_CLOCKWISE)
    if rot == 180:
        return cv2.rotate(arr_bgr, cv2.ROTATE_180)
    if rot == 270:
        return cv2.rotate(arr_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return arr_bgr


def _deskew_inplace(arr_bgr):
    gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    coords = np.column_stack(np.where(bw > 0))
    if len(coords) <= 2000:
        return arr_bgr

    rect = cv2.minAreaRect(coords)
    angle = rect[-1]  # OpenCV gives something like [0, 90) or (-90, 0], depending

    # Convert to a "skew from horizontal" in degrees, in [-45, 45]
    if angle > 45:
        angle = angle - 90

    # Hard clamp: deskew should never rotate a page 90 degrees
    if abs(angle) > 15:
        return arr_bgr  # ignore nonsense

    if abs(angle) <= 0.2:
        return arr_bgr

    h, w = arr_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(arr_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _load_bgr(image_path: Path):
    img = Image.open(image_path).convert("RGB")
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)


def _save_bgr(arr_bgr, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_img = Image.fromarray(cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB))
    out_img.save(out_path)
    return out_path



def pil_to_cv(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert('RGB'))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def cv_to_pil(arr_bgr: np.ndarray) -> Image.Image:
    arr_rgb = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr_rgb)

def rotate_image_cv(arr_bgr: np.ndarray, angle_deg: float) -> np.ndarray:
    h, w = arr_bgr.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos = abs(M[0, 0]); sin = abs(M[0, 1])
    new_w = int((h * sin) + (w * cos))
    new_h = int((h * cos) + (w * sin))
    M[0, 2] += (new_w / 2) - center[0]
    M[1, 2] += (new_h / 2) - center[1]
    return cv2.warpAffine(arr_bgr, M, (new_w, new_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def detect_orientation(image_path: Path) -> Tuple[int, float, str]:
    """
    Returns (rotate_deg, confidence, raw_osd_text).
    rotate_deg is one of {0, 90, 180, 270}.
    """
    # Safe defaults
    rot, conf, osd_raw = 0, 0.0, ""

    try:
        img = Image.open(image_path)

        osd_raw = pytesseract.image_to_osd(img, output_type=pytesseract.Output.STRING)

        rot_m = re.search(r"Rotate:\s*(\d+)", osd_raw)
        conf_m = re.search(r"Orientation confidence:\s*([0-9.]+)", osd_raw)

        rot = int(rot_m.group(1)) if rot_m else 0
        conf = float(conf_m.group(1)) if conf_m else 0.0

        # Normalize rotation to expected set
        if rot not in (0, 90, 180, 270):
            rot = 0

    except Exception as e:
        # Keep defaults, but include the error for debugging
        osd_raw = f"osd_failed: {e}"

    return rot, conf, osd_raw

def estimate_skew_angle_hough(arr_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # ignore margins to avoid page numbers / scribbles dragging angle
    h, w = bw.shape[:2]
    y0, y1 = int(0.12 * h), int(0.95 * h)
    x0, x1 = int(0.05 * w), int(0.92 * w)
    bw = bw[y0:y1, x0:x1]

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)

    edges = cv2.Canny(bw, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=200, minLineLength=200, maxLineGap=20)
    if lines is None:
        return 0.0

    angles = []
    for x1, y1, x2, y2 in lines[:, 0]:
        ang = math.degrees(math.atan2((y2 - y1), (x2 - x1)))
        if -45 < ang < 45:
            angles.append(ang)

    return float(np.median(angles)) if angles else 0.0

def deskew_hough(arr_bgr: np.ndarray, min_apply: float = 0.2, max_apply: float = 3.0):
    angle = estimate_skew_angle_hough(arr_bgr)
    if abs(angle) < min_apply or abs(angle) > max_apply:
        return arr_bgr, 0.0

    h, w = arr_bgr.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(arr_bgr, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return out, float(angle)

def crop_to_content(arr_bgr: np.ndarray, pad: int = 20) -> np.ndarray:
    """Crop large uniform margins. Conservative; keeps pad."""
    gray = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2GRAY)
    # find non-background pixels by adaptive threshold
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 51, 10)
    coords = cv2.findNonZero(thr)
    if coords is None:
        return arr_bgr
    x, y, w, h = cv2.boundingRect(coords)
    x0 = max(x - pad, 0); y0 = max(y - pad, 0)
    x1 = min(x + w + pad, arr_bgr.shape[1]); y1 = min(y + h + pad, arr_bgr.shape[0])
    return arr_bgr[y0:y1, x0:x1]


def crop_bbox(image_path: Path, bbox, pad: int = 30, out_path: Path | None = None) -> Path:
    """
    bbox = [x, y, w, h] in image pixel coords.
    """
    x, y, w, h = bbox
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    x0 = max(int(x - pad), 0)
    y0 = max(int(y - pad), 0)
    x1 = min(int(x + w + pad), W)
    y1 = min(int(y + h + pad), H)
    crop = img.crop((x0, y0, x1, y1))

    if out_path is None:
        out_path = image_path.parent / f"{image_path.stem}__crop_{x}_{y}_{w}_{h}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(out_path)
    return out_path


from pathlib import Path
from typing import Any, Dict, Tuple, Optional

def _preprocess_core(
    image_path: Path,
    *,
    pad: int = 30,
    rotate_conf_min: float = 0.0,   # keep 0.0 if you want current behavior
    deskew: str = "hough",          # "hough" or "inplace"
) -> Tuple[Any, Dict[str, Any]]:
    """
    Shared: load -> (optional rotate) -> deskew -> crop.
    Returns: (arr_bgr, meta)
    """
    arr = _load_bgr(image_path)

    rot, conf, _ = detect_orientation(image_path)
    do_rotate = (rot in (90, 180, 270)) and (float(conf) >= rotate_conf_min)
    if do_rotate:
        arr = _rotate_upright(arr, rot)

    deskew_deg: Optional[float] = None
    if deskew == "hough":
        arr, deskew_deg = deskew_hough(arr)
    else:
        arr = _deskew_inplace(arr)
        deskew_deg = None

    arr = crop_to_content(arr, pad=pad)

    meta = {
        "orientation_before": {"rotate_deg": int(rot), "conf": float(conf)},
        "deskew": {"method": deskew, "angle_deg": (float(deskew_deg) if deskew_deg is not None else None)},
    }
    return arr, meta


def preprocess_basic(image_path: Path, out_path: Path, return_meta: bool = False):
    arr, meta = _preprocess_core(
        image_path,
        pad=30,
        rotate_conf_min=0.0,   # or set higher if you want to be conservative
        deskew="hough",        # matches your current basic
    )

    clean_path = _save_bgr(arr, out_path)

    if return_meta:
        rot_after, conf_after, _ = detect_orientation(clean_path)
        meta["orientation_after"] = {"rotate_deg": int(rot_after), "conf": float(conf_after)}
        return clean_path, meta

    return clean_path

def preprocess_normalize(image_path: Path, out_path: Path) -> Path:
    arr, _meta = _preprocess_core(image_path, pad=30, rotate_conf_min=0.0, deskew="hough")

    lab = cv2.cvtColor(arr, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    L2 = clahe.apply(L)
    arr = cv2.cvtColor(cv2.merge([L2, A, B]), cv2.COLOR_LAB2BGR)

    return _save_bgr(arr, out_path)


def preprocess_denoise(image_path: Path, out_path: Path) -> Path:
    """
    Gentle denoise to reduce speckle without destroying handwriting.
    Shared core handles: load -> rotate -> deskew -> crop.
    """
    arr, _meta = _preprocess_core(
        image_path, pad=30, rotate_conf_min=0.0, deskew="hough", )

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(
        gray, None,
        h=10, templateWindowSize=7, searchWindowSize=21
    )
    arr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    return _save_bgr(arr, out_path)


def preprocess_binarize_for_ocr(image_path: Path, out_path: Path) -> Path:
    """
    Binarize to help OCR. Shared core handles: load -> rotate -> deskew -> crop.
    """
    arr, _meta = _preprocess_core(image_path, pad=30, rotate_conf_min=0.0, deskew="hough")

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

    # Light blur helps stabilize thresholding
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # Otsu binarization (simple + often good for handwriting pages)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Optional: small cleanup (avoid eating pen strokes)
    # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    # bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel, iterations=1)

    arr_out = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)
    return _save_bgr(arr_out, out_path)

