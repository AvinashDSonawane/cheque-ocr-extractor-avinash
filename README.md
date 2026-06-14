# Cheque Drawer-Name OCR Extractor

A desktop application built with **PyQt5** that automates drawer-name extraction from bank cheque images using **Google Gemini Vision (2.5 Flash Lite)**, with seamless integration into legacy **DBF**-based banking systems.

---

## Overview

Manual data entry from scanned cheque images is slow and error-prone. This tool streamlines the process by:

1. Loading a folder of cheque images
2. Pre-processing each image (resize, background cleaning, noise removal) for optimal OCR accuracy
3. Sending the cleaned image to Google Gemini Vision to extract the **drawer name**
4. Displaying results live in a desktop GUI with progress tracking and token usage stats
5. Merging extracted drawer names directly into an existing **DBF** database used by legacy systems

---

## Features

- **Drag-and-drop style folder selection** — point the app at a folder of cheque images and let it process the entire batch
- **Parallel processing** — images are pre-processed and sent to the OCR engine concurrently for faster throughput
- **Live results table** — see extracted drawer names appear in real time as each cheque is processed
- **Image preview with zoom & pan** — inspect each cheque image directly within the app
- **Dark / light theme toggle**
- **DBF integration** — automatically matches OCR results to existing database records by filename and writes the drawer name back into the correct field
- **Token & cost tracking** — monitors API token usage per image and cumulative totals
- **License-protected distribution** — MAC-address-based authorization for controlled deployment to client machines

---

## Tech Stack

| Component | Technology |
|---|---|
| GUI Framework | PyQt5 |
| OCR / Vision | Google Gemini 2.5 Flash Lite (`google-generativeai`) |
| Image Processing | OpenCV, NumPy, Pillow |
| Database | DBF (via `python-dbf`) |
| Concurrency | `ThreadPoolExecutor`, `QThread` |
| Packaging | PyInstaller |

---

## Project Structure

```
project/
├── main_app.py              # Application entry point
├── license_guard.py         # MAC-based license verification
├── hook_ssl.py              # SSL certificate fix for frozen .exe
├── core/
│   └── ocr_engine.py         # Gemini Vision API integration
├── gui/
│   ├── main_window.py        # Main application window
│   ├── image_viewer.py        # Zoomable/pannable image display
│   ├── styles.py              # Light/dark theme stylesheets
│   └── worker.py               # Background processing pipeline
└── utils/
    ├── image_loader.py        # Image discovery & loading
    ├── image_preprocessor.py  # Resize, crop, background cleaning
    └── dbf_handler.py          # DBF read/write/merge operations
```

---

## How It Works

1. **Image Discovery** — `image_loader.py` scans the selected folder for supported image formats (`.jpg`, `.png`, `.bmp`, `.tiff`)

2. **Preprocessing** — `image_preprocessor.py` resizes each cheque to a standard resolution and applies background subtraction to improve text contrast for OCR

3. **OCR Extraction** — `ocr_engine.py` sends each pre-processed image to Gemini Vision with a structured prompt and parses the JSON response containing the drawer name

4. **Pipeline Orchestration** — `worker.py` runs the full pipeline on a background `QThread`, emitting progress, log, and result signals to keep the UI responsive

5. **Database Merge** — `dbf_handler.py` matches OCR results to existing DBF records by normalized filename and writes the extracted drawer name into the appropriate field

---

## Setup

```bash
# Clone the repo
git clone https://github.com/AvinashDSonawane/<repo-name>.git
cd <repo-name>

# Install dependencies
pip install -r requirements.txt

# Set your Gemini API key as an environment variable
# (do not hardcode it in source files)
export GEMINI_API_KEY="your-api-key-here"

# Run the application
python main_app.py
```

> **Note:** The API key in this repository is a placeholder. Obtain your own key from [Google AI Studio](https://aistudio.google.com/) to run the application.

---

## License & Distribution

This project includes a MAC-address-based license guard for controlled distribution as a standalone `.exe` to client machines, ensuring the application only runs on authorized devices.

---

## Author

**Avinash D. Sonawane**
