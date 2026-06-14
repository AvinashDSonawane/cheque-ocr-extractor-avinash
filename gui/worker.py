"""
gui/worker.py
-------------
Background QThread that orchestrates the drawer-name extraction pipeline:
  1. Discover all image files in the selected folder.
  2. Crop + preprocess the drawer-name ROI in parallel (ThreadPoolExecutor).
  3. Send each ROI to Google Gemini 2.5 Flash Lite.
  4. Parse the response into the drawer_name field.
  5. Emit Qt signals for UI updates (progress, logs, tokens, results).
"""

import os
import cv2
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QThread, pyqtSignal

from utils.image_loader       import get_image_paths
from core.ocr_engine          import GeminiChequeExtractor
from utils.image_preprocessor import preprocess_drawer_roi


class ProcessingWorker(QThread):
    """
    Runs in a background thread; emits progress/result signals to the GUI.

    Signals
    -------
    progress_update(int)          – overall progress 0-100 %
    log_update(str)               – single log line for the log panel
    cheque_count_update(int, int) – (processed_so_far, total)
    single_result_ready(dict)     – one result dict as soon as it completes
    result_ready(list)            – full list of result dicts when all done
    process_finished(bool)        – True = success, False = stopped / error
    token_update(dict)            – token and pixel usage per image + totals
    """

    progress_update     = pyqtSignal(int)
    log_update          = pyqtSignal(str)
    cheque_count_update = pyqtSignal(int, int)
    single_result_ready = pyqtSignal(dict)
    result_ready        = pyqtSignal(list)
    process_finished    = pyqtSignal(bool)
    token_update        = pyqtSignal(dict)

    def __init__(self, folder_path: str, stop_flag: dict):
        super().__init__()
        self.folder_path    = folder_path
        self.stop_flag      = stop_flag
        self._finished_once = False   # FIX (Bug 5): guard against multiple finish emits

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _stopped(self) -> bool:
        """
        Returns True if the user pressed Stop.
        FIX (Bug 5): process_finished(False) is emitted only on the first call
        that finds the stop flag set, preventing duplicate signal emissions that
        would call on_process_finished() multiple times and flicker the UI.
        """
        if self.stop_flag.get("stop"):
            if not self._finished_once:
                self._finished_once = True
                self.log_update.emit("[STOP] Stopped by user.")
                self.process_finished.emit(False)
            return True
        return False

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def run(self):
        try:
            # ── Discover images ───────────────────────────────────────
            image_files = get_image_paths(self.folder_path)

            if not image_files:
                self.log_update.emit("[ERROR] No images found in the selected folder.")
                self.process_finished.emit(False)
                return

            total = len(image_files)
            self.cheque_count_update.emit(0, total)
            self.log_update.emit(
                f"[INFO] Found {total} image(s). "
                "Cropping drawer-name ROI → Gemini 2.5 Flash Lite extraction…"
            )

            # ── Initialise Gemini extractor ───────────────────────────
            try:
                extractor = GeminiChequeExtractor()
                self.log_update.emit(
                    f"[OK] Gemini extractor ready (model: {GeminiChequeExtractor.MODEL_NAME})"
                )
            except EnvironmentError as env_err:
                self.log_update.emit(f"[ERROR] {env_err}")
                self.process_finished.emit(False)
                return

            # ── Accumulator variables ─────────────────────────────────
            total_tokens_in  = 0
            total_tokens_out = 0
            total_pixels     = 0

            # ── Parallel ROI preprocessing ────────────────────────────
            self.log_update.emit("[INFO] Preprocessing drawer-name ROIs in parallel (4 threads)...")
            drawer_roi_map = {}

            def _preprocess(path):
                img = cv2.imread(path)
                if img is None:
                    return path, None
                return path, preprocess_drawer_roi(img)

            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(_preprocess, p): p for p in image_files}
                for future in as_completed(futures):
                    if self._stopped():
                        return
                    path, roi = future.result()
                    basename  = os.path.basename(path)
                    if roi is None:
                        self.log_update.emit(f"[WARN] Could not preprocess: {basename}")
                    else:
                        self.log_update.emit(f"[OK] Preprocessed ROI: {basename}")
                    drawer_roi_map[path] = roi

            # ── Separate valid from failed-preprocess paths ───────────
            valid_paths = [p for p in image_files if drawer_roi_map.get(p) is not None]
            for p in image_files:
                if drawer_roi_map.get(p) is None:
                    self.log_update.emit(
                        f"[WARN] Skipping {os.path.basename(p)} (preprocessing failed)."
                    )

            results         = []
            results_map     = {}
            processed_count = 0

            def _call_gemini(path):
                """Calls Gemini for one ROI; runs inside thread pool."""
                return path, extractor.extract_drawer_name(drawer_roi_map[path])

            # ── Parallel Gemini API extraction (3 concurrent calls) ───
            with ThreadPoolExecutor(max_workers=3) as pool:
                future_to_path = {pool.submit(_call_gemini, p): p for p in valid_paths}

                for future in as_completed(future_to_path):
                    if self._stopped():
                        pool.shutdown(wait=False)
                        return

                    path     = future_to_path[future]
                    basename = os.path.basename(path)

                    try:
                        _, fields = future.result()
                    except Exception as api_err:
                        self.log_update.emit(f"[ERROR] Gemini error for {basename}: {api_err}")
                        fields = {
                            "drawer_name": "",
                            "_pixels": 0, "_tokens_in": 0, "_tokens_out": 0,
                        }

                    # ── Extract and accumulate token / pixel metadata ──
                    px    = fields.pop("_pixels",    0)
                    t_in  = fields.pop("_tokens_in",  0)
                    t_out = fields.pop("_tokens_out", 0)

                    total_pixels     += px
                    total_tokens_in  += t_in
                    total_tokens_out += t_out

                    self.token_update.emit({
                        "pixels":       px,
                        "tokens_in":    t_in,
                        "tokens_out":   t_out,
                        "total_in":     total_tokens_in,
                        "total_out":    total_tokens_out,
                        "total_pixels": total_pixels,
                    })

                    fields["file_name"] = basename
                    fields["full_path"] = path
                    results_map[path]   = fields

                    # ── Emit single result immediately ─────────────────
                    self.single_result_ready.emit(dict(fields))

                    processed_count += 1
                    self.progress_update.emit(int(processed_count / total * 100))
                    self.cheque_count_update.emit(processed_count, total)

                    self.log_update.emit(
                        f"[OK] [{processed_count}/{total}] {basename} | "
                        f"Drawer: {fields.get('drawer_name') or 'N/A'} | "
                        f"Tokens in: {t_in} | out: {t_out} | Pixels: {px:,}"
                    )

            # ── Restore original folder order for the final results ───
            results = [results_map[p] for p in valid_paths if p in results_map]

            # ── Emit final results ────────────────────────────────────
            self.result_ready.emit(results)
            if not self._finished_once:
                self._finished_once = True
                self.process_finished.emit(True)

        except Exception as exc:
            self.log_update.emit(f"[ERROR] Unexpected error: {exc}")
            if not self._finished_once:
                self._finished_once = True
                self.process_finished.emit(False)