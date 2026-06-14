"""
ocr_engine.py
-------------
Sends the pre-cropped drawer-name ROI to Google Gemini 2.5 Flash Lite
and returns the drawer name as a string.

Only the bottom-right corner of the cheque (the signature / "FOR" area)
is processed.  All other fields have been removed.
"""

import os
import re
import json
import ssl
import cv2
import numpy as np
from PIL import Image as PILImage

# ---------------------------------------------------------------------------
# SSL fix for frozen .exe — must happen before any google import
# ---------------------------------------------------------------------------
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE",      certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
except Exception:
    pass

import google.generativeai as genai

# ---------------------------------------------------------------------------
# Prompt — drawer name only (focused ROI image)
# ---------------------------------------------------------------------------
_DRAWER_NAME_PROMPT = """\
You are reading a small cropped image from the bottom-right corner of an Indian bank cheque.

This region contains:
- A printed or typed company name or person name (this is the drawer name)
- A handwritten signature (ignore this completely)

The printed name is usually:
- In a clear readable font (not cursive)
- Located above or near the word "FOR" if it is present
- If "FOR" is not present, look for any printed or typed text in this region
- Could be a company name like "TATA MOTORS LTD" or a person name like "RAHUL SHARMA"

Do not mistake a bank name (e.g., "SBI", "HDFC BANK", "BANK LTD") for the drawer name. If you see a bank name but no clear drawer name, ignore the bank name.

Do not output broken, incomplete, or meaningless text (e.g., "SB", "HDF", "ICIC", random letters). If the printed name is partially cut off or unreadable, set drawer_name to null instead.

Extract ONLY the printed name. Do not read the signature.
If you do not find any printed name near the signature area, set drawer_name to null. Do not guess, do not return the signature, do not return anything else.

Return ONLY this JSON with no extra text:
{"drawer_name": "<name or null>"}
"""

# ---------------------------------------------------------------------------
# Helper: clean the drawer_name field
# ---------------------------------------------------------------------------
# Block common cheque boilerplate words that are not drawer names
_BLOCKED_WORDS = {
    "FOR", "PLEASE", "SIGN", "ABOVE", "PROPRIETOR",
    "AUTHORIZED", "AUTHORISED", "SIGNATORY", "SIGNATORIES",
    "SIGNATURE", "SIGNATURES", "AUTHORIZEDSIGNATORY",
    "AUTHORISEDSIGNATORY", "AUTHORIZEDSIGNATORIES",
}

def _clean_field(value: str) -> str:
    if not isinstance(value, str):
        value = str(value)

    value = value.replace("&", "AND").strip()

    if not value:
        return "XXX"

    value = re.sub(r"[^\x00-\x7F]", "", value)
    value = re.sub(r"[^A-Za-z ]", "", value)
    value = " ".join(value.split()).upper()

    # Remove boilerplate words token by token
    tokens = value.split()
    tokens = [t for t in tokens if t not in _BLOCKED_WORDS]
    value  = " ".join(tokens)

    return value if value else "XXX"

# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class GeminiChequeExtractor:

    MODEL_NAME = "gemini-2.5-flash-lite"

    def __init__(self):
        # FIX (Bug 4): Read the API key from the environment first (set by main_app.py
        # or a .env loader), then fall back to the hardcoded value so the app still
        # works when packaged.  The `if not api_key` guard is now meaningful because
        # os.environ.get() returns None when the variable is absent.
        api_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or "AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        )

        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Place a .env file next to the .exe with GEMINI_API_KEY=your-key"
            )

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(self.MODEL_NAME)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def extract_drawer_name(self, roi_image_np: np.ndarray) -> dict:
        """
        Sends the pre-cropped drawer-name ROI to Gemini and returns a dict:
            {
                "drawer_name": <str>,  # cleaned name, or "" if absent
                "_pixels":     <int>,
                "_tokens_in":  <int>,
                "_tokens_out": <int>,
            }
        """
        h, w    = roi_image_np.shape[:2]
        pil_img = self._numpy_to_pil(roi_image_np)

        try:
            resp = self.model.generate_content(
                [_DRAWER_NAME_PROMPT, pil_img],
                generation_config=genai.GenerationConfig(
                    temperature=0.0,
                    max_output_tokens=128,
                ),
            )
            raw   = resp.text.strip() if resp.text else ""
            u     = resp.usage_metadata
            t_in  = getattr(u, "prompt_token_count",  0) or 0
            t_out = (getattr(u, "total_token_count",  0) or 0) - t_in
        except Exception as exc:
            raise RuntimeError(f"Gemini drawer-name call failed: {exc}") from exc

        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip()

        drawer_name = "XXX"

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                raw_name = parsed.get("drawer_name")
                if raw_name is not None and str(raw_name).strip().lower() not in ("null", "none", ""):
                    drawer_name = _clean_field(str(raw_name))
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        return {
            "drawer_name": drawer_name,
            "_pixels":     h * w,
            "_tokens_in":  t_in,
            "_tokens_out": t_out,
        }

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _numpy_to_pil(image_np: np.ndarray) -> PILImage.Image:
        if image_np is None or image_np.size == 0:
            raise ValueError("Empty image array passed to GeminiChequeExtractor")
        if len(image_np.shape) == 2:
            rgb = cv2.cvtColor(image_np, cv2.COLOR_GRAY2RGB)
        elif len(image_np.shape) == 3 and image_np.shape[2] == 3:
            rgb = cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB)
        else:
            rgb = image_np
        return PILImage.fromarray(rgb)


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# ---------------------------------------------------------------------------
GoogleVisionOCR = GeminiChequeExtractor


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ocr_engine.py <image_path>")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    if img is None:
        print("Could not load image.")
        sys.exit(1)

    extractor = GeminiChequeExtractor()
    result    = extractor.extract_drawer_name(img)
    print("\nExtracted fields:")
    for k, v in result.items():
        print(f"  {k}: {v!r}")