"""Hover-revealed sidebar; pinned mode docks it without obscuring the image."""
from PySide6.QtCore import QObject,QEvent,QTimer,Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication,QToolButton,QCheckBox,QLabel,QHBoxLayout

class SidebarController(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.panel=window.sidebar;self.root=window.centralWidget();self.suspended=False
        self.pinned=str(window.settings.value('sidebar_pinned','false')).lower()=='true'
        row=QHBoxLayout();row.addWidget(QLabel('文件 / 缩略图'));row.addStretch();self.pin=QCheckBox('常驻');self.pin.setToolTip('勾选后左侧列表保持展开；取消后移出自动隐藏。');row.addWidget(self.pin);self.panel.layout().insertLayout(0,row)
        self.panel.setObjectName('floatingSidebar');self.panel.setAutoFillBackground(True)
        self.handle=QToolButton(self.root);self.handle.setText('›');self.handle.setObjectName('sidebarHandle');self.handle.setToolTip('移入展开文件和缩略图列表 · Ctrl+B');self.handle.clicked.connect(self.reveal)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.maybe_hide)
        self.root.installEventFilter(self);window.split.installEventFilter(self);self.panel.installEventFilter(self);self.handle.installEventFilter(self)
        self.pin.setChecked(self.pinned);self.pin.toggled.connect(self.set_pinned);self.set_pinned(self.pinned,initial=True)
    def place(self):
        area=self.window.split.geometry()
        self.handle.setGeometry(max(0,area.left()-10),area.top()+8,10,max(32,area.height()-16))
        self.handle.setVisible(not self.pinned and not self.suspended)
        if not self.pinned:
            self.panel.setGeometry(area.left(),area.top(),min(area.width()-40,200+self.window.active_count()*94),area.height())
            if self.panel.isVisible():self.panel.raise_()
            else:self.handle.raise_()
    def set_pinned(self,pinned,initial=False):
        visible=self.panel.isVisible();self.pinned=pinned;self.timer.stop()
        if pinned:
            self.window.split.insertWidget(0,self.panel);self.panel.show();self.window.split.setSizes([440,max(500,self.window.split.width()-440)])
        else:
            self.panel.setParent(self.root);self.panel.setVisible(visible and not initial)
        self.window.settings.setValue('sidebar_pinned',pinned);self.place()
        if not pinned and not initial:self.timer.start()
    def reveal(self):
        if self.suspended:return
        self.timer.stop();self.place();self.panel.show();self.panel.raise_()
    def maybe_hide(self):
        if self.pinned or self.suspended:return
        if QApplication.activePopupWidget() is not None:self.timer.start();return
        point=QCursor.pos()
        if self.panel.rect().contains(self.panel.mapFromGlobal(point)) or self.handle.rect().contains(self.handle.mapFromGlobal(point)):return
        self.panel.hide();self.handle.raise_()
    def toggle(self):
        if self.panel.isVisible():self.panel.hide()
        else:self.reveal()
    def focus(self,suspended):
        self.suspended=suspended
        if suspended:self.panel.hide();self.handle.hide()
        else:
            if self.pinned:self.panel.show()
            self.place()
    def eventFilter(self,obj,event):
        kind=event.type()
        if obj in (self.root,self.window.split) and kind in (QEvent.Type.Resize,QEvent.Type.Move,QEvent.Type.Show):self.place()
        elif obj is self.handle and kind==QEvent.Type.Enter:self.reveal()
        elif obj is self.panel and kind==QEvent.Type.Enter:self.timer.stop()
        elif obj in (self.handle,self.panel) and kind==QEvent.Type.Leave and not self.pinned:self.timer.start()
        return super().eventFilter(obj,event)
