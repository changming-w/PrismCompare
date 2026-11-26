"""Move the existing comparison panel between the splitter and an owned window."""
from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QSplitter, QSplitterHandle, QToolButton, QVBoxLayout, QWidget
from widgets import WORKSPACE_BACKGROUND,WORKSPACE_DIVIDER


class DragTitle(QLabel):
    drag_started = Signal(QPoint, QPoint)
    drag_moved = Signal(QPoint)
    drag_finished = Signal(QPoint)
    double_clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setAccessibleName('拖动比较区')
        self.draggable = False
        self.anchor = None
        self.last_position = None

    def set_draggable(self, enabled):
        self.draggable = enabled
        self.setCursor(Qt.CursorShape.OpenHandCursor if enabled else Qt.CursorShape.ArrowCursor)

    def take_drag(self, position):
        # The splitter handle is removed when the panel is reparented.
        # Keep the same drag alive on the floating caption.
        self.anchor = self.last_position = position
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.grabMouse()

    def mousePressEvent(self, event):
        if not self.draggable or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.anchor = event.globalPosition().toPoint()
        self.last_position = None
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.anchor is None:
            return super().mouseMoveEvent(event)
        position = event.globalPosition().toPoint()
        event.accept()
        if self.last_position is not None:
            delta = position - self.last_position
            self.last_position = position
            self.drag_moved.emit(delta)
        elif (position - self.anchor).manhattanLength() >= QApplication.startDragDistance():
            self.last_position = position
            self.drag_started.emit(self.anchor, position)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.anchor is None:
            return super().mouseReleaseEvent(event)
        position = event.globalPosition().toPoint()
        dragged = self.last_position is not None
        delta = position - self.last_position if dragged else QPoint()
        self.anchor = self.last_position = None
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        event.accept()
        if dragged:
            if not delta.isNull():
                self.drag_moved.emit(delta)
            self.drag_finished.emit(position)

    def mouseDoubleClickEvent(self, event):
        if self.draggable and event.button() == Qt.MouseButton.LeftButton:
            self.anchor = self.last_position = None
            event.accept()
            self.double_clicked.emit()
        else:
            super().mouseDoubleClickEvent(event)


class ComparisonHandle(QSplitterHandle):
    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor(WORKSPACE_BACKGROUND))
        painter.setPen(QColor('#8395aa' if self.underMouse() else WORKSPACE_DIVIDER))
        y=self.rect().center().y()
        painter.drawLine(0,y,self.width()-1,y)


class ComparisonSplitter(QSplitter):
    def __init__(self, orientation):
        super().__init__(orientation)
        self.setObjectName('comparisonSplitter')

    def createHandle(self):
        handle = ComparisonHandle(self.orientation(), self)
        layout = QHBoxLayout(handle)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        handle.grip = DragTitle()
        handle.grip.setFixedWidth(88)
        handle.grip.setStyleSheet('background: transparent;')
        handle.grip.setToolTip('拖动中间浮出比较区；拖动两侧调整高度')
        handle.grip.set_draggable(True)
        layout.addStretch()
        layout.addWidget(handle.grip)
        layout.addStretch()
        return handle


class FloatingDetails(QDialog):
    dock_requested = Signal()

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMaximizeButtonHint)
        self.setObjectName('comparisonSurface')
        self.setWindowTitle('棱镜比对 · 比较区')
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        QVBoxLayout(self).setContentsMargins(8, 4, 8, 8)

    def closeEvent(self, event):
        event.ignore()
        self.dock_requested.emit()

    def reject(self):
        self.dock_requested.emit()


class DetailDock(QObject):
    def __init__(self, owner, splitter, panel):
        super().__init__(owner)
        self.owner = owner
        self.splitter = splitter
        self.panel = panel
        self.window = None
        self.floating = False
        self.saved_sizes = None
        self.title = panel.caption
        self.button = QToolButton()
        self.button.setText('停靠')
        self.button.setToolTip('将比较区停靠回主窗口底部')
        self.panel.caption_row.addWidget(self.button)
        self.button.hide()
        self.title.set_draggable(True)
        self.title.setToolTip('拖动整条标题可浮出比较区')
        self.title.drag_started.connect(self.start_title_drag)
        self.title.drag_moved.connect(self.move_window)
        self.title.drag_finished.connect(self.finish_drag)
        self.title.double_clicked.connect(self.undock)
        self.button.clicked.connect(self.dock)
        self.connect_separator()

    def connect_separator(self):
        self.separator = self.splitter.handle(1).grip
        self.separator.drag_started.connect(self.detach_drag)
        self.separator.double_clicked.connect(self.undock)

    def set_visible(self, visible):
        self.panel.setVisible(visible)
        if self.floating:
            self.window.setVisible(visible)

    def remember_sizes(self):
        if not self.floating and self.panel.isVisible():
            self.saved_sizes = self.splitter.sizes()

    def restore_sizes(self):
        if self.floating:
            return
        height = self.splitter.height()
        bottom = max(self.panel.minimumHeight() + 38, min(420, round(height * .48)))
        self.splitter.setSizes(self.saved_sizes or [max(200, height - bottom), bottom])

    def undock(self, position=None):
        if self.floating or not self.panel.isVisible():
            return
        self.remember_sizes()
        origin = self.panel.mapToGlobal(QPoint(0, 0))
        size = self.panel.size()
        if self.window is None:
            self.window = FloatingDetails(self.owner)
            self.window.dock_requested.connect(self.dock)
            self.window.resize(min(1100, size.width()), max(500, size.height()))
        self.floating = True
        self.window.layout().addWidget(self.panel)
        self.button.show()
        self.title.set_draggable(True)
        self.title.setToolTip('拖到主窗口底部可停靠')
        self.move_to_screen(position if position is not None else origin)
        self.set_visible(True)
        self.window.raise_()

    def detach_drag(self, anchor, position):
        panel_x = self.panel.mapFromGlobal(anchor).x()
        self.undock(position - QPoint(panel_x, 32))
        if not self.floating:
            return
        title_x = self.title.mapTo(self.panel, QPoint()).x()
        offset = QPoint(max(4, min(panel_x - title_x, self.title.width() - 8)), self.title.height() // 2)
        self.window.move(self.window.pos() + position - self.title.mapToGlobal(offset))
        self.title.take_drag(position)

    def start_title_drag(self, anchor, position):
        if self.floating:
            self.move_window(position - anchor)
        else:
            self.detach_drag(anchor, position)

    def dock(self):
        if not self.floating:
            return
        visible = self.window.isVisible() and not self.owner.closing
        self.window.hide()
        self.floating = False
        self.splitter.addWidget(self.panel)
        self.connect_separator()
        self.button.hide()
        self.title.setToolTip('拖动整条标题可浮出比较区')
        self.set_visible(visible)
        if visible:
            self.restore_sizes()

    def move_window(self, delta):
        if self.floating and not self.window.isMaximized():
            self.window.move(self.window.pos() + delta)

    def finish_drag(self, position):
        if self.floating:
            local = self.splitter.mapFromGlobal(position)
            if self.splitter.rect().contains(local) and local.y() >= self.splitter.height() - 96:
                self.dock()

    def move_to_screen(self, position):
        screen = QApplication.screenAt(position) or self.owner.screen()
        area = screen.availableGeometry()
        size = self.window.frameSize()
        x = max(area.x(), min(position.x(), area.right() - size.width() + 1))
        y = max(area.y(), min(position.y(), area.bottom() - size.height() + 1))
        self.window.move(x, y)
