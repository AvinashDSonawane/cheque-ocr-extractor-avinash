"""
gui/main_window.py
------------------
Main application window for the Cheque OCR Extractor.

Layout
──────
  Left panel  : action buttons (vertical) + processing log
  Right panel : vertical splitter
                  ├─ top    → zoomable cheque image preview + navigation
                  └─ bottom → extracted-fields table (filter / context menu)
  Bottom row  : progress bar + status counts
"""

import os
import csv
import glob

from PyQt5.QtCore    import Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter,
    QMessageBox, QGroupBox, QLineEdit, QApplication, QMenu, QAction,
    QComboBox,
)
from PyQt5.QtGui import QPixmap, QFont

from gui.worker       import ProcessingWorker
from gui.image_viewer import ImageViewer
from gui.styles       import (
    DARK_STYLESHEET, LIGHT_STYLESHEET,
    STOP_BTN_STYLESHEET, CELL_INFO_DARK, CELL_INFO_LIGHT,
)

from utils.dbf_handler import (
    load_dbf_for_display, merge_ocr_into_dbf_records, diagnose_match,
    write_dbf, FILENAME_FIELD, DRAWER_FIELD, FILE_MARK_FIELD,
    OPR_NO_FIELD, OPR_NO_VALUE,
)


class ChequeOCRGUI(QMainWindow):

    # ── Column definitions for the results table ──────────────────────
    COLUMNS = [
        ("File Name",   "file_name"),
        ("Drawer Name", "drawer_name"),
    ]

    # ═══════════════════════ INIT ════════════════════════════════════
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cheque OCR Extractor")
        self.setGeometry(100, 100, 1400, 900)

        self.folder_path      = None
        self.stop_flag        = {"stop": False}
        self.worker           = None
        self.results          = []
        self.dark_mode        = False
        self.total_images     = 0
        self.image_paths      = []
        self.current_idx      = 0
        self.credentials_path = None

        # ── DBF state ─────────────────────────────────────────────────
        self.dbf_path        = None   # path to the loaded DBF file
        self.dbf_records     = []     # raw records read from the DBF
        self.dbf_field_names = []     # field names from the DBF header

        self.init_ui()
        self.set_dark_mode(False)

    # ═══════════════════════ UI CONSTRUCTION ═════════════════════════
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(6)
        root_layout.setContentsMargins(10, 10, 10, 10)

        # ── Main horizontal splitter ──────────────────────────────────
        main_splitter = QSplitter(Qt.Horizontal)

        # ── LEFT PANEL ────────────────────────────────────────────────
        left_widget = QWidget()
        left_widget.setMinimumWidth(260)
        left_widget.setMaximumWidth(380)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(4, 4, 4, 4)

        self._build_left_buttons(left_layout)
        self._build_left_controls(left_layout)

        self.folder_label = QLabel("No folder selected")
        self.folder_label.setFont(QFont("Segoe UI", 9))
        self.folder_label.setWordWrap(True)
        left_layout.addWidget(self.folder_label)

        self._build_log_box(left_layout)

        # ── RIGHT PANEL ───────────────────────────────────────────────
        right_panel  = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self._build_image_viewer())
        right_splitter.addWidget(self._build_table())

        right_layout.addWidget(right_splitter)

        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([280, 1120])
        root_layout.addWidget(main_splitter)

        # ── Progress row ──────────────────────────────────────────────
        self._build_progress_row(root_layout)

        # ── Status bar ────────────────────────────────────────────────
        self.statusBar().showMessage("Ready  •  Select a folder and press Start.")

        # ── Signal connections ─────────────────────────────────────────
        self.select_btn.clicked.connect(self.select_folder)
        self.start_btn.clicked.connect(self.start_processing)
        self.stop_btn.clicked.connect(self.stop_processing)
        self.export_btn.clicked.connect(self.export_results)
        self.dark_btn.clicked.connect(self.toggle_dark_mode)
        self.upload_dbf_btn.clicked.connect(self.upload_dbf)
        self.update_dbf_btn.clicked.connect(self.update_dbf)
        self.table.cellClicked.connect(self.on_cell_clicked)
        self.table.cellClicked.connect(self.on_row_clicked_show_image)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        self.export_btn.hide()
        self.setMinimumSize(1000, 700)
        self.showMaximized()

    # ── Left panel sub-builders ───────────────────────────────────────
    def _build_left_buttons(self, layout):
        self.select_btn     = QPushButton("📁  Upload Folder")
        self.start_btn      = QPushButton("▶  Start Extracting")
        self.stop_btn       = QPushButton("⏹  Stop Execution")
        self.export_btn     = QPushButton("💾  Export CSV")
        self.export_btn.hide()
        self.upload_dbf_btn = QPushButton("🗄  Upload DBF")
        self.update_dbf_btn = QPushButton("✅  Update DBF")
        self.update_dbf_btn.hide()          # shown only after a DBF is loaded
        self.dark_btn       = QPushButton("🌙  Change Mode")

        self.stop_btn.setStyleSheet(STOP_BTN_STYLESHEET)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        self.upload_dbf_btn.setEnabled(True)
        self.update_dbf_btn.setEnabled(False)

        for btn in (self.select_btn, self.start_btn, self.stop_btn,
                    self.export_btn, self.upload_dbf_btn,
                    self.update_dbf_btn, self.dark_btn):
            btn.setFixedHeight(38)
            btn.setMinimumWidth(180)
            btn.setFont(QFont("Segoe UI", 10))
            layout.addWidget(btn)

    def _build_left_controls(self, layout):
        pass  # controls removed; Gemini is the only parser

    def _build_log_box(self, layout):
        log_box    = QGroupBox("Processing Log")
        log_layout = QVBoxLayout(log_box)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        self.log_text.setMinimumHeight(200)
        log_layout.addWidget(self.log_text)

        clear_log_btn = QPushButton("🗑  Clear Log")
        clear_log_btn.setFixedHeight(28)
        clear_log_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(clear_log_btn)

        layout.addWidget(log_box, stretch=1)

    # ── Right panel sub-builders ──────────────────────────────────────
    def _build_image_viewer(self):
        viewer_box    = QGroupBox("Cheque Image Preview")
        viewer_layout = QVBoxLayout(viewer_box)

        self.image_label = ImageViewer()
        self.image_label.setMinimumHeight(400)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet(
            "border: 1px solid gray; background-color: #f0f0f0; min-height: 400px;"
        )
        self.image_label.setText("No image selected")
        viewer_layout.addWidget(self.image_label)

        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀  Previous")
        self.next_btn = QPushButton("Next  ▶")
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.show_previous_image)
        self.next_btn.clicked.connect(self.show_next_image)
        nav_layout.addWidget(self.prev_btn)
        nav_layout.addWidget(self.next_btn)
        viewer_layout.addLayout(nav_layout)

        self.image_count_lbl = QLabel("Images uploaded: 0")
        self.image_count_lbl.setFont(QFont("Segoe UI", 9))
        self.image_count_lbl.setAlignment(Qt.AlignCenter)
        viewer_layout.addWidget(self.image_count_lbl)

        return viewer_box

    def _build_table(self):
        table_box    = QGroupBox("Extracted Drawer Names")
        table_layout = QVBoxLayout(table_box)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.DoubleClicked)
        self.table.setFont(QFont("Segoe UI", 9))
        table_layout.addWidget(self.table)

        self.cell_info_lbl = QLabel("Click any cell to see field details")
        self.cell_info_lbl.setFont(QFont("Segoe UI", 9))
        self.cell_info_lbl.setStyleSheet(CELL_INFO_LIGHT)
        self.cell_info_lbl.setWordWrap(True)
        table_layout.addWidget(self.cell_info_lbl)

        self.cell_edit_box = QLineEdit()
        self.cell_edit_box.setFont(QFont("Segoe UI", 9))
        self.cell_edit_box.setPlaceholderText("Double-click a cell or click here to edit…")
        self.cell_edit_box.hide()
        self.cell_edit_box.editingFinished.connect(self._commit_cell_edit)
        table_layout.addWidget(self.cell_edit_box)

        self._selected_row = -1
        self._selected_col = -1

        # ── Filter row with dropdown ──────────────────────────────────
        filter_layout = QHBoxLayout()

        filter_label = QLabel("🔍 Filter:")
        self.filter_col_box = QComboBox()
        self.filter_col_box.addItem("All Columns", userData=None)
        for header, key in self.COLUMNS:
            self.filter_col_box.addItem(header, userData=key)
        self.filter_col_box.setCurrentIndex(0)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to filter results…")
        self.search_box.textChanged.connect(self.filter_table)
        self.filter_col_box.currentIndexChanged.connect(
            lambda: self.filter_table(self.search_box.text())
        )

        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_col_box)
        filter_layout.addWidget(self.search_box)
        table_layout.addLayout(filter_layout)

        return table_box

    def _build_progress_row(self, layout):
        prog_row = QHBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setTextVisible(True)

        self.cheque_count_lbl = QLabel("Cheques: 0 / 0")
        self.token_lbl        = QLabel("Tokens  in: 0  out: 0")

        self.cheque_count_lbl.setFont(QFont("Segoe UI", 9))
        self.cheque_count_lbl.setFixedWidth(130)
        self.token_lbl.setFont(QFont("Segoe UI", 9))
        self.token_lbl.setFixedWidth(220)

        prog_row.addWidget(self.cheque_count_lbl)
        prog_row.addWidget(self.token_lbl)
        prog_row.addWidget(self.progress_bar)
        layout.addLayout(prog_row)

    # ═══════════════════════ IMAGE NAVIGATION ═════════════════════════
    def update_image_preview(self):
        if not self.image_paths or self.current_idx < 0 or \
                self.current_idx >= len(self.image_paths):
            self.image_label.setText("No image to display")
            self.image_count_lbl.setText("Images: 0")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return

        path   = self.image_paths[self.current_idx]
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.image_label.set_image(pixmap)
        else:
            self.image_label.setText("Failed to load image")

        self.image_count_lbl.setText(
            f"Image {self.current_idx + 1} of {len(self.image_paths)}"
        )
        self.prev_btn.setEnabled(self.current_idx > 0)
        self.next_btn.setEnabled(self.current_idx < len(self.image_paths) - 1)

    def on_row_clicked_show_image(self, row: int, col: int):
        if row < len(self.results):
            full_path = self.results[row].get("full_path", "")
            if full_path and os.path.exists(full_path):
                pixmap = QPixmap(full_path)
                if not pixmap.isNull():
                    self.image_label.set_image(pixmap)
                    self.current_idx = row
                    self.image_count_lbl.setText(
                        f"Image {row + 1} of {len(self.image_paths)}"
                    )
                    self.log_text.append(f"Showing: {os.path.basename(full_path)}")
                else:
                    self.log_text.append("Could not load image for this row.")
            else:
                self.log_text.append("Image path not found for this row.")

    def resizeEvent(self, event):
        self.update_image_preview()

    def show_previous_image(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.update_image_preview()

    def show_next_image(self):
        if self.current_idx < len(self.image_paths) - 1:
            self.current_idx += 1
            self.update_image_preview()

    # ═══════════════════════ SLOT HANDLERS ════════════════════════════
    def select_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Cheque Images Folder")
        if path:
            self.folder_path  = path
            self.folder_label.setText(f"📂  {path}")
            self.image_paths  = (
                glob.glob(os.path.join(path, "*.jpg"))  +
                glob.glob(os.path.join(path, "*.jpeg")) +
                glob.glob(os.path.join(path, "*.png"))  +
                glob.glob(os.path.join(path, "*.tif"))  +
                glob.glob(os.path.join(path, "*.tiff"))
            )
            self.total_images = len(self.image_paths)
            self.current_idx  = 0 if self.image_paths else -1
            self.update_image_preview()
            self.start_btn.setEnabled(True)
            self.log_text.append(
                f"📂  Folder selected: {path} (found {self.total_images} images)"
            )
            self.statusBar().showMessage(f"Folder: {path}")

    def start_processing(self):
        if not self.folder_path:
            QMessageBox.warning(self, "No Folder", "Please select a folder first.")
            return

        self.stop_flag  = {"stop": False}
        self.results    = []
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.token_lbl.setText("Tokens  in: 0  out: 0")
        self.cheque_count_lbl.setText("Cheques: 0 / 0")
        self.image_count_lbl.setText(f"Images: 0 / {self.total_images}")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.statusBar().showMessage("Processing…")
        self.log_text.append("▶  Starting processing…")

        self.worker = ProcessingWorker(self.folder_path, self.stop_flag)
        self.worker.progress_update.connect(self.progress_bar.setValue)
        self.worker.log_update.connect(self.log_text.append)
        self.worker.token_update.connect(self.on_token_update)
        self.worker.cheque_count_update.connect(self.on_cheque_count_update)
        self.worker.single_result_ready.connect(self.on_single_result_ready)
        self.worker.result_ready.connect(self.on_result_ready)
        self.worker.process_finished.connect(self.on_process_finished)
        self.worker.start()

    def stop_processing(self):
        self.stop_flag["stop"] = True
        self.log_text.append("⏹  Stop requested — finishing current item…")
        self.stop_btn.setEnabled(False)

    def on_token_update(self, data: dict):
        total_in  = data.get("total_in",  0)
        total_out = data.get("total_out", 0)
        self.token_lbl.setText(f"Tokens  in: {total_in:,}  out: {total_out:,}")

    def on_cheque_count_update(self, done: int, total: int):
        self.cheque_count_lbl.setText(f"Cheques: {done} / {total}")
        self.image_count_lbl.setText(f"Images: {done} / {self.total_images}")

    def on_single_result_ready(self, row_data: dict):
        """Called each time ONE cheque finishes — appends row immediately."""
        self.results.append(row_data)
        self._append_table_row(row_data)
        self.export_btn.setEnabled(True)
        self.table.scrollToBottom()

    def on_result_ready(self, results: list):
        """Re-populate in correct folder order once all done."""
        self.results = results
        self.table.setRowCount(0)
        for row_data in results:
            self._append_table_row(row_data)
        self.export_btn.setEnabled(bool(results))

    def on_process_finished(self, success: bool):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if success:
            self.progress_bar.setValue(100)
            msg = f"✅  Done — {len(self.results)} cheque(s) processed."
            self.log_text.append(msg)
            self.statusBar().showMessage(msg)
            self.image_count_lbl.setText(
                f"Images: {len(self.results)} / {self.total_images}"
            )
            # Enable Update DBF button if a DBF has already been loaded
            if self.dbf_path:
                self.update_dbf_btn.setEnabled(True)
        else:
            self.statusBar().showMessage("Processing stopped or failed.")
            if self.stop_flag["stop"]:
                self.image_count_lbl.setText(
                    f"Images: {len(self.results)} / {self.total_images} (stopped)"
                )

    def export_results(self):
        if not self.results:
            QMessageBox.information(self, "No Data", "Nothing to export yet.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save CSV", "cheque_results.csv", "CSV Files (*.csv)"
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                headers = [key for _, key in self.COLUMNS]
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for row in range(self.table.rowCount()):
                    row_data = {}
                    for col, (_, key) in enumerate(self.COLUMNS):
                        item = self.table.item(row, col)
                        row_data[key] = item.text() if item else ""
                    writer.writerow(row_data)
            self.log_text.append(f"💾  Exported {len(self.results)} rows → {path}")
            self.statusBar().showMessage(f"Exported: {path}")
            QMessageBox.information(self, "Export Complete", f"Results saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def filter_table(self, text: str):
        text = text.lower().strip()
        selected_key = self.filter_col_box.currentData()

        if not text:
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)
            return

        if selected_key is None:
            for row in range(self.table.rowCount()):
                match = False
                for col in range(self.table.columnCount()):
                    item = self.table.item(row, col)
                    if item and item.text().lower().startswith(text):
                        match = True
                        break
                self.table.setRowHidden(row, not match)
        else:
            col_idx = None
            for idx, (_, key) in enumerate(self.COLUMNS):
                if key == selected_key:
                    col_idx = idx
                    break
            if col_idx is None:
                return
            for row in range(self.table.rowCount()):
                item = self.table.item(row, col_idx)
                if item and item.text().lower().startswith(text):
                    self.table.setRowHidden(row, False)
                else:
                    self.table.setRowHidden(row, True)

    # ═══════════════════════ TABLE INTERACTION ═════════════════════════
    def on_cell_clicked(self, row: int, col: int):
        item = self.table.item(row, col)
        if item:
            col_name = self.COLUMNS[col][0]
            value    = item.text()
            self._selected_row = row
            self._selected_col = col
            if self.COLUMNS[col][1] == "file_name":
                self.cell_info_lbl.setText(f"📌 Field: {col_name}  |  Value: {value}")
                self.cell_edit_box.hide()
                self.cell_info_lbl.show()
            else:
                self.cell_edit_box.setText(value)
                self.cell_edit_box.show()
                self.cell_info_lbl.hide()
            self.table.selectRow(row)

    def _commit_cell_edit(self):
        if self._selected_row < 0 or self._selected_col < 0:
            return
        new_value = self.cell_edit_box.text()
        item = self.table.item(self._selected_row, self._selected_col)
        if item:
            item.setText(new_value)
        col_name = self.COLUMNS[self._selected_col][0]
        self.cell_info_lbl.setText(f"📌 Field: {col_name}  |  Value: {new_value}")

    def show_context_menu(self, pos):
        menu              = QMenu()
        copy_cell_action  = QAction("📋 Copy Cell", self)
        copy_row_action   = QAction("📄 Copy Row", self)
        clear_cell_action = QAction("✖️ Clear Cell", self)

        selected_indexes = self.table.selectedIndexes()
        if not selected_indexes:
            copy_cell_action.setEnabled(False)
            copy_row_action.setEnabled(False)
            clear_cell_action.setEnabled(False)

        copy_cell_action.triggered.connect(self.copy_selected_cell)
        copy_row_action.triggered.connect(self.copy_selected_row)
        clear_cell_action.triggered.connect(self.clear_selected_cell)

        menu.addAction(copy_cell_action)
        menu.addAction(copy_row_action)
        menu.addSeparator()
        menu.addAction(clear_cell_action)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def copy_selected_cell(self):
        selected = self.table.selectedIndexes()
        if not selected:
            return
        texts = []
        for idx in selected:
            item = self.table.item(idx.row(), idx.column())
            if item:
                texts.append(item.text())
        if texts:
            QApplication.clipboard().setText("\n".join(texts))
            self.log_text.append(f"📋 Copied {len(texts)} cell(s) to clipboard")

    def copy_selected_row(self):
        selected = self.table.selectedIndexes()
        if not selected:
            return
        row    = selected[0].row()
        values = []
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                values.append(item.text())
        if values:
            QApplication.clipboard().setText(",".join(values))
            self.log_text.append(f"📋 Copied row {row + 1} to clipboard")

    def clear_selected_cell(self):
        selected = self.table.selectedIndexes()
        if not selected:
            return
        count = 0
        for idx in selected:
            item = self.table.item(idx.row(), idx.column())
            if item:
                item.setText("")
                count += 1
        self.log_text.append(f"✖️ Cleared {count} cell(s)")

    # ═══════════════════════ DBF UPLOAD & UPDATE ══════════════════════

    def upload_dbf(self):
        """
        Let the user pick a DBF file, read it, and show a summary in the log.
        Enables the Update DBF button if OCR results are also available.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DBF File", "", "DBF Files (*.dbf);;All Files (*)"
        )
        if not path:
            return

        try:
            records, field_names, summary = load_dbf_for_display(path)
        except ImportError as exc:
            QMessageBox.critical(self, "Missing Library", str(exc))
            return
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.critical(self, "DBF Error", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "DBF Read Error",
                                 f"Could not read DBF file:\n{exc}")
            return

        self.dbf_path        = path
        self.dbf_records     = records
        self.dbf_field_names = field_names

        self.log_text.append(f"🗄  {summary}")
        self.statusBar().showMessage(f"DBF loaded: {os.path.basename(path)}")

        # Show the Update button — enable it only when OCR results also exist
        self.update_dbf_btn.show()
        self.update_dbf_btn.setEnabled(bool(self.results))

        QMessageBox.information(
            self, "DBF Loaded",
            f"Loaded {len(records)} record(s) from:\n{path}\n\n"
            f"Fields found: {', '.join(field_names)}"
        )

    def update_dbf(self):
        """
        Merge the current OCR results into the loaded DBF records and
        write the updated file back (user can choose overwrite or save-as).

        Only DRAWER_FIELD, FILE_MARK_FIELD, and OPR_NO_FIELD are changed:
          FILE_MARK = 'F'  when a drawer name was extracted
          FILE_MARK = 'T'  when the drawer name is blank
          OPR_NO    = 'AS601' for every record
        All other DBF fields remain untouched.
        """
        if not self.dbf_path:
            QMessageBox.warning(self, "No DBF", "Please upload a DBF file first.")
            return
        if not self.results:
            QMessageBox.warning(self, "No Results",
                                "Run extraction first so there are OCR results to merge.")
            return

        # ── Sync any manual table edits back into self.results ────────
        for row in range(self.table.rowCount()):
            if row >= len(self.results):
                break
            for col_idx, (_, key) in enumerate(self.COLUMNS):
                item = self.table.item(row, col_idx)
                if item:
                    self.results[row][key] = item.text()

        # ── Merge OCR data into DBF records (in memory) ───────────────
        # ── Diagnostic: show filename comparison in log ───────────────
        for diag_line in diagnose_match(self.dbf_records, self.results):
            self.log_text.append(diag_line)

        try:
            updated_records, matched, unmatched = merge_ocr_into_dbf_records(
                self.dbf_records, self.results
            )
        except Exception as exc:
            QMessageBox.critical(self, "Merge Error", str(exc))
            return

        if matched == 0:
            QMessageBox.warning(
                self, "No Matches",
                "No DBF records matched the extracted filenames.\n\n"
                "Check that FILENAME_FIELD in dbf_handler.py matches your DBF schema, "
                "and that the image filenames (without extension) appear in that column."
            )
            return

        # ── Ask: overwrite original or save to a new file ─────────────
        reply = QMessageBox.question(
            self,
            "Save DBF",
            f"Matched {matched} record(s).\n\n"
            "• Yes  — overwrite the original DBF file\n"
            "• No   — save to a new file\n"
            "• Cancel — abort",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )

        if reply == QMessageBox.Cancel:
            return

        output_path = None
        if reply == QMessageBox.No:
            output_path, _ = QFileDialog.getSaveFileName(
                self, "Save Updated DBF As",
                os.path.splitext(self.dbf_path)[0] + "_updated.dbf",
                "DBF Files (*.dbf)"
            )
            if not output_path:
                return  # user cancelled the save dialog

        # ── Write to disk ─────────────────────────────────────────────
        try:
            written_path = write_dbf(
                self.dbf_path,
                updated_records,
                self.dbf_field_names,
                output_path,
            )
        except ImportError as exc:
            QMessageBox.critical(self, "Missing Library", str(exc))
            return
        except ValueError as exc:
            QMessageBox.critical(self, "Schema Error", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Write Error",
                                 f"Could not write DBF file:\n{exc}")
            return

        # ── Update in-memory DBF records so a second Update is correct
        self.dbf_records = updated_records

        summary_msg = (
            f"DBF updated successfully\n\n"
            f"  File      : {os.path.basename(written_path)}\n"
            f"  Matched   : {matched} record(s) updated\n"
            f"  Unmatched : {unmatched} OCR result(s) had no DBF counterpart\n"
            f"  Total DBF rows: {len(updated_records)}"
        )
        self.log_text.append(
            f"✅  DBF saved → {os.path.basename(written_path)}  |  "
            f"Matched: {matched}  |  Unmatched: {unmatched}"
        )
        self.statusBar().showMessage(
            f"DBF saved → {os.path.basename(written_path)}  "
            f"({matched} updated, {unmatched} unmatched)"
        )
        QMessageBox.information(self, "DBF Updated", summary_msg)

    # ═══════════════════════ HELPERS ══════════════════════════════════
    def _append_table_row(self, row_data: dict):
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)
        for col_idx, (_, key) in enumerate(self.COLUMNS):
            item = QTableWidgetItem(str(row_data.get(key, "")))
            item.setTextAlignment(Qt.AlignCenter)
            if key == "file_name":
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.table.setItem(row_idx, col_idx, item)

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self.set_dark_mode(self.dark_mode)
        self.dark_btn.setText("☀  Light Mode" if self.dark_mode else "🌙  Dark Mode")

    def set_dark_mode(self, enabled: bool):
        self.setStyleSheet(DARK_STYLESHEET if enabled else LIGHT_STYLESHEET)
        self.stop_btn.setStyleSheet(STOP_BTN_STYLESHEET)
        self.cell_info_lbl.setStyleSheet(
            CELL_INFO_DARK if enabled else CELL_INFO_LIGHT
        )