"""
gui/image_viewer.py
-------------------
Zoomable + Pannable image display widget used in the main window's preview panel.

Controls:
  Scroll wheel      → zoom in / out
  Left click + drag → pan / move the image inside the canvas
  Double-click      → reset zoom and pan to default
"""

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore    import Qt, QPoint
from PyQt5.QtGui     import QCursor, QPixmap


class ImageViewer(QLabel):
    """QLabel subclass — mouse-wheel zoom, left-click drag to pan inside canvas."""

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")

        self.pixmap_original = None
        self.scale_factor    = 1.0
        self.offset          = QPoint(0, 0)   # pan offset in pixels

        self._drag_active    = False
        self._drag_start_pos = QPoint(0, 0)   # mouse pos when drag began
        self._offset_at_drag = QPoint(0, 0)   # offset when drag began

        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_image(self, pixmap):
        """Load a new image and reset zoom + pan."""
        self.pixmap_original = pixmap
        self.scale_factor    = 1.0
        self.offset          = QPoint(0, 0)
        self._render()

    # ------------------------------------------------------------------
    # Internal rendering — crops the visible region from the scaled pixmap
    # ------------------------------------------------------------------

    def _render(self):
        if not self.pixmap_original:
            return

        # 1. Scale the full image
        scaled = self.pixmap_original.scaled(
            self.pixmap_original.size() * self.scale_factor,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        sw = scaled.width()
        sh = scaled.height()
        cw = self.width()
        ch = self.height()

        # 2. Centre offset — where the image would be if no pan applied
        cx = (cw - sw) // 2
        cy = (ch - sh) // 2

        # 3. Apply pan offset
        x = cx + self.offset.x()
        y = cy + self.offset.y()

        # 4. Clamp so image never moves completely out of view
        #    Always keep at least 40 px of the image visible
        margin = 40
        x = max(-(sw - margin), min(cw - margin, x))
        y = max(-(sh - margin), min(ch - margin, y))
        self.offset = QPoint(x - cx, y - cy)

        # 5. Draw: create a blank canvas and paint the scaled image onto it
        canvas = QPixmap(cw, ch)
        canvas.fill(Qt.transparent)

        from PyQt5.QtGui import QPainter
        painter = QPainter(canvas)
        painter.drawPixmap(x, y, scaled)
        painter.end()

        self.setPixmap(canvas)

    # ------------------------------------------------------------------
    # Zoom — scroll wheel
    # ------------------------------------------------------------------

    def wheelEvent(self, event):
        if self.pixmap_original is None:
            return
        if event.angleDelta().y() > 0:
            self.scale_factor *= 1.1
        else:
            self.scale_factor /= 1.1
        # Clamp scale
        self.scale_factor = max(0.1, min(self.scale_factor, 10.0))
        self._render()

    # ------------------------------------------------------------------
    # Pan — left click drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.pixmap_original is not None:
            self._drag_active    = True
            self._drag_start_pos = event.pos()
            self._offset_at_drag = QPoint(self.offset)
            self.setCursor(QCursor(Qt.ClosedHandCursor))

    def mouseMoveEvent(self, event):
        if self._drag_active:
            delta        = event.pos() - self._drag_start_pos
            self.offset  = self._offset_at_drag + delta
            self._render()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_active = False
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def enterEvent(self, event):
        if self.pixmap_original is not None:
            self.setCursor(QCursor(Qt.OpenHandCursor))

    def leaveEvent(self, event):
        self.setCursor(QCursor(Qt.ArrowCursor))

    # ------------------------------------------------------------------
    # Double-click → reset zoom and pan
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event):
        self.scale_factor = 1.0
        self.offset       = QPoint(0, 0)
        self._render()

    # ------------------------------------------------------------------
    # Re-render when widget is resized
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        self._render()
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Backward compat
    # ------------------------------------------------------------------

    def update_view(self):
        self._render()