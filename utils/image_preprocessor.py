"""
image_preprocessor.py
---------------------
Pipeline for cheque images:
  1. Resize every image to 1000 × 500 px (fixed).
  2. Crop the cheque body at static coordinates (20, 88) → (978, 423).
  3. Apply medium-strength background removal / cleaning.

Advanced background removal uses background SUBTRACTION.
Preserves original text weight – no artificial darkening or thickening.

Key principle: result = 255 − (background − original)
  → background pixels → white
  → text pixels → same relative darkness as original
"""

import cv2
import numpy as np
from typing import Tuple, List, Dict, Any

# ---------------------------------------------------------------------------
# RESIZE / CROP CONSTANTS
# ---------------------------------------------------------------------------
RESIZE_WIDTH  = 1000
RESIZE_HEIGHT = 500

CROP_X1, CROP_Y1 = 20,  88
CROP_X2, CROP_Y2 = 978, 423

# Drawer-name ROI — bottom-right corner of the cheque (signature area).
# Coordinates are relative to the 1000 × 500 resized image.
DRAWER_ROI_X1, DRAWER_ROI_Y1 = 474, 230
DRAWER_ROI_X2, DRAWER_ROI_Y2 = 988, 483

# ---------------------------------------------------------------------------
# STRENGTH PRESETS  (only "medium" is used by default; others kept for ref)
# ---------------------------------------------------------------------------
PRESETS = {
    "light": dict(
        bg_method        = "gaussian",
        bg_sigma         = 20,
        bg_kernel        = 41,
        lut_threshold    = 170,
        lut_gamma        = 1.8,
        bilateral_d      = 7,
        bilateral_sigma  = 20,
        fft_percentile   = 0,
        fft_suppression  = 0.10,
        fft_center_ratio = 0.06,
    ),
    "medium": dict(
        bg_method        = "gaussian",
        bg_sigma         = 30,
        bg_kernel        = 61,
        lut_threshold    = 155,
        lut_gamma        = 2.4,
        bilateral_d      = 9,
        bilateral_sigma  = 28,
        fft_percentile   = 98.5,
        fft_suppression  = 0.08,
        fft_center_ratio = 0.06,
    ),
    "strong": dict(
        bg_method        = "both",
        bg_sigma         = 40,
        bg_kernel        = 81,
        lut_threshold    = 140,
        lut_gamma        = 3.2,
        bilateral_d      = 11,
        bilateral_sigma  = 35,
        fft_percentile   = 97.5,
        fft_suppression  = 0.05,
        fft_center_ratio = 0.05,
    ),
}

# ---------------------------------------------------------------------------
# CORE PROCESSING FUNCTIONS
# ---------------------------------------------------------------------------

def _resize_and_crop(image: np.ndarray) -> np.ndarray:
    """
    Step 1 – Resize to RESIZE_WIDTH × RESIZE_HEIGHT (1000 × 500).
    Step 2 – Crop the static cheque ROI: (x1=20, y1=88) → (x2=978, y2=423).

    Returns the cropped region as a numpy array (same channels as input).
    """
    resized = cv2.resize(
        image,
        (RESIZE_WIDTH, RESIZE_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )
    cropped = resized[CROP_Y1:CROP_Y2, CROP_X1:CROP_X2]
    return cropped


def _fft_remove_periodic(gray: np.ndarray, p: Dict) -> np.ndarray:
    """Suppress periodic noise peaks in frequency domain (optional step)."""
    if p["fft_percentile"] <= 0:
        return gray

    rows, cols = gray.shape
    crow, ccol = rows // 2, cols // 2

    f      = np.fft.fft2(gray.astype(np.float32))
    fshift = np.fft.fftshift(f)
    mag    = np.abs(fshift)

    pry = max(int(rows * p["fft_center_ratio"]), 4)
    prx = max(int(cols * p["fft_center_ratio"]), 8)
    cmask = np.zeros((rows, cols), np.uint8)
    cv2.ellipse(cmask, (ccol, crow), (prx, pry), 0, 0, 360, 1, -1)

    outside_mag = mag.copy()
    outside_mag[cmask == 1] = 0
    valid = outside_mag[outside_mag > 0]
    if valid.size == 0:
        return gray

    thr   = np.percentile(valid, p["fft_percentile"])
    peaks = (mag > thr) & (cmask == 0)

    smask = np.where(peaks, p["fft_suppression"], 1.0).astype(np.float32)
    bk    = max(3, min(21, (min(rows, cols) // 10) | 1))
    smask = cv2.GaussianBlur(smask, (bk, bk), 0)
    smask[cmask == 1] = 1.0

    fshift_f = fshift * smask
    out      = np.abs(np.fft.ifft2(np.fft.ifftshift(fshift_f)))
    p1, p99  = np.percentile(out, 1), np.percentile(out, 99)
    if p99 > p1:
        out = (out - p1) / (p99 - p1) * 255.0
    return np.clip(out, 0, 255).astype(np.uint8)


def _estimate_background_gaussian(gray: np.ndarray, sigma: float) -> np.ndarray:
    sigma = max(sigma, 3.0)
    return cv2.GaussianBlur(gray, (0, 0), sigma)


def _estimate_background_morph(gray: np.ndarray, kernel_size: int) -> np.ndarray:
    h, w = gray.shape
    k    = min(kernel_size, int(min(h, w) * 0.42))
    k    = k | 1
    k    = max(k, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)


def _subtract_background(gray: np.ndarray, background: np.ndarray) -> np.ndarray:
    diff   = background.astype(np.int32) - gray.astype(np.int32)
    result = np.clip(255 - diff, 0, 255).astype(np.uint8)
    return result


def _whiten_background(gray: np.ndarray, threshold: int, gamma: float) -> np.ndarray:
    lut   = np.arange(256, dtype=np.float32)
    above = lut > threshold
    span  = 255.0 - threshold
    if span > 0:
        lut[above] = threshold + span * ((lut[above] - threshold) / span) ** (1.0 / gamma)
    return cv2.LUT(gray, np.clip(lut, 0, 255).astype(np.uint8))


def _bilateral_denoise(gray: np.ndarray, d: int, sigma: float) -> np.ndarray:
    if d < 3:
        return gray
    d = d | 1
    return cv2.bilateralFilter(gray, d, sigma, sigma)


# ---------------------------------------------------------------------------
# MAIN CLEANING FUNCTION
# ---------------------------------------------------------------------------

def clean_cheque(image: np.ndarray, params: Dict, keep_color: bool = False) -> np.ndarray:
    """
    Full cleaning pipeline (applied AFTER resize + crop):
      grayscale → (optional FFT) → background estimation →
      background subtraction → bilateral filter → selective whitening.

    Args:
        image      : BGR or grayscale image (already resized + cropped).
        params     : Parameter dict from PRESETS.
        keep_color : If True, return 3-channel BGR.

    Returns:
        Cleaned grayscale (or BGR) image.
    """
    if image is None or image.size == 0:
        raise ValueError("Empty image passed to clean_cheque()")

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    p = params

    gray = _fft_remove_periodic(gray, p)

    method = p.get("bg_method", "gaussian")
    if method == "gaussian":
        background = _estimate_background_gaussian(gray, p["bg_sigma"])
    elif method == "morph":
        background = _estimate_background_morph(gray, p["bg_kernel"])
    elif method == "both":
        bg_g       = _estimate_background_gaussian(gray, p["bg_sigma"])
        background = _estimate_background_morph(bg_g, p["bg_kernel"])
    else:
        background = _estimate_background_gaussian(gray, p["bg_sigma"])

    result = _subtract_background(gray, background)
    result = _bilateral_denoise(result, p["bilateral_d"], p["bilateral_sigma"])
    result = _whiten_background(result, p["lut_threshold"], p["lut_gamma"])

    if keep_color:
        return cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    return result


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------

def preprocess_image(image: np.ndarray, strength: str = "medium") -> np.ndarray:
    """
    Main entry point used by ProcessingWorker.

    Pipeline:
      1. Resize to 1000 × 500 px (no crop — full cheque is kept).
      2. Apply medium-strength background cleaning  (strength arg is accepted
         for GUI compatibility but always runs at "medium" internally).

    Args:
        image    : BGR image from cv2.imread()  (grayscale also accepted).
        strength : Accepted for backward compatibility; always uses "medium".

    Returns:
        Cleaned grayscale image of the full resized cheque.
    """
    if image is None or image.size == 0:
        raise ValueError("Empty image passed to preprocess_image()")

    # Step 1 — resize to target dimensions (no crop)
    resized = cv2.resize(
        image,
        (RESIZE_WIDTH, RESIZE_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )

    # Step 2 — always medium cleaning
    params = PRESETS["medium"]
    return clean_cheque(resized, params, keep_color=False)

def preprocess_drawer_roi(image: np.ndarray) -> np.ndarray:
    """
    Dedicated preprocessing for the drawer-name region.

    Pipeline:
      1. Resize the full cheque to 1000 × 500 px.
      2. Crop the drawer-name ROI: (474, 230) → (988, 483).
      3. Apply *light*-strength background cleaning to the crop.

    Light cleaning is intentional — the ROI is small and the printed
    name is always present; aggressive cleaning risks over-whitening
    faint text.

    Args:
        image : BGR (or grayscale) image from cv2.imread().

    Returns:
        Cleaned grayscale crop of the drawer-name area.
    """
    if image is None or image.size == 0:
        raise ValueError("Empty image passed to preprocess_drawer_roi()")

    # Step 1 — resize to target dimensions
    resized = cv2.resize(
        image,
        (RESIZE_WIDTH, RESIZE_HEIGHT),
        interpolation=cv2.INTER_AREA,
    )

    # Step 2 — crop the drawer-name ROI
    roi = resized[DRAWER_ROI_Y1:DRAWER_ROI_Y2, DRAWER_ROI_X1:DRAWER_ROI_X2]

    if roi.size == 0:
        raise ValueError(
            f"Drawer ROI crop produced an empty array. "
            f"Check constants: ({DRAWER_ROI_X1},{DRAWER_ROI_Y1}) → "
            f"({DRAWER_ROI_X2},{DRAWER_ROI_Y2})"
        )

    # Step 3 — light cleaning only
    params = PRESETS["light"]
    return clean_cheque(roi, params, keep_color=False)


# ---------------------------------------------------------------------------
# Compatibility helpers (kept for any code that still imports them)
# ---------------------------------------------------------------------------

def get_visibility_score(image: np.ndarray) -> float:
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    total = gray.size
    mid   = np.sum((gray >= 100) & (gray <= 200))
    return (mid / total) * 100.0


def preprocess_batch(
    images: List[np.ndarray],
    strength: str = "medium",
) -> Tuple[List[np.ndarray], List[float]]:
    cleaned = []
    scores  = []
    for img in images:
        scores.append(get_visibility_score(img))
        cleaned.append(preprocess_image(img, strength))
    return cleaned, scores


# ---------------------------------------------------------------------------
# TEST MODE
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python image_preprocessor.py <image_path>")
        print("Resizes to 1000×500, crops ROI (20,88)→(978,423), then cleans (medium).")
        sys.exit(1)

    path = sys.argv[1]
    img  = cv2.imread(path)
    if img is None:
        print("Could not load image.")
        sys.exit(1)

    cleaned = preprocess_image(img)
    out     = "output_cleaned.png"
    cv2.imwrite(out, cleaned)
    print(f"Saved: {out}  |  size: {cleaned.shape[1]}×{cleaned.shape[0]} px")