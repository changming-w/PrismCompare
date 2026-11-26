"""Hover-only zoom controls; never consumes space in the image layout."""
import math
from PySide6.QtCore import QObject,QEvent,QTimer,Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QPushButton,QSlider

class FocusControls(QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.root=window.centralWidget();self.active=False
        self.edge=QWidget(self.root);self.edge.setMouseTracking(True);self.edge.setStyleSheet('background: transparent;')
        self.bar=QWidget(self.root);self.bar.setObjectName('focusZoomBar')
        self.bar.setStyleSheet('QWidget#focusZoomBar { background: rgba(28,34,43,235); border-radius: 5px; } QLabel { background: transparent; color: white; } QPushButton { color: white; background: #394452; border: 1px solid #596576; padding: 3px 7px; }')
        row=QHBoxLayout(self.bar);row.setContentsMargins(10,6,10,6);row.setSpacing(7)
        self.label=QLabel('缩放 100%');self.label.setFixedWidth(90);row.addWidget(self.label)
        minus=QPushButton('−');minus.setFixedWidth(30);minus.setToolTip('缩小');minus.clicked.connect(lambda:self.step(.8));row.addWidget(minus)
        self.slider=QSlider(Qt.Orientation.Horizontal);self.slider.setRange(-200,300);self.slider.valueChanged.connect(lambda value:window.detail_zoom(100*10**(value/100)));row.addWidget(self.slider,1)
        plus=QPushButton('+');plus.setFixedWidth(30);plus.setToolTip('放大');plus.clicked.connect(lambda:self.step(1.25));row.addWidget(plus)
        self.fit=QPushButton('适应窗口');self.fit.clicked.connect(window.fit_all);row.addWidget(self.fit)
        self.swap=QPushButton('交换');self.swap.setToolTip('交换两张图片和来源位置');self.swap.clicked.connect(window.swap_sources);row.addWidget(self.swap)
        self.actual=QPushButton('100%');self.actual.clicked.connect(window.actual_all);row.addWidget(self.actual)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.maybe_hide)
        for item in (self.edge,self.bar,self.root):item.installEventFilter(self)
        for pane in window.panes:pane.image.changed.connect(lambda _:self.update_zoom())
        self.edge.hide();self.bar.hide()
    def set_active(self,active):
        self.active=active;self.timer.stop();self.bar.hide();self.edge.setVisible(active);self.place()
    def place(self):
        if not self.active:return
        self.edge.setGeometry(0,0,self.root.width(),8);self.edge.raise_()
        width=min(600,self.root.width());self.bar.setGeometry((self.root.width()-width)//2,0,width,46)
        if self.bar.isVisible():self.bar.raise_()
    def update_zoom(self):
        if not self.active:return
        percent=self.window.panes[self.window.baseline.currentIndex()].image.transform().m11()*100
        self.label.setText(f'缩放 {percent:.0f}%');self.slider.blockSignals(True);self.slider.setValue(round(100*math.log10(max(.01,percent/100))));self.slider.blockSignals(False)
    def step(self,factor):
        percent=self.window.panes[self.window.baseline.currentIndex()].image.transform().m11()*100
        self.window.detail_zoom(max(1,min(10000,percent*factor)));self.update_zoom()
    def reveal(self):
        if not self.active:return
        self.timer.stop();self.swap.setVisible(self.window.active_count()==2);self.update_zoom();self.bar.show();self.place()
    def maybe_hide(self):
        if not self.active:return
        point=QCursor.pos()
        if self.bar.rect().contains(self.bar.mapFromGlobal(point)) or self.edge.rect().contains(self.edge.mapFromGlobal(point)):return
        self.bar.hide()
    def eventFilter(self,obj,event):
        if obj is self.root and event.type()==QEvent.Type.Resize:self.place()
        elif obj is self.edge and event.type()==QEvent.Type.Enter:self.reveal()
        elif obj is self.bar and event.type()==QEvent.Type.Enter:self.timer.stop()
        elif obj in (self.edge,self.bar) and event.type()==QEvent.Type.Leave:self.timer.start()
        return super().eventFilter(obj,event)
