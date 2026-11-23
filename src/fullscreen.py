"""Preloaded fullscreen viewer for rapid, aligned A/B/C/D switching."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QShortcut,QKeySequence
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QWidget,QPushButton,QLabel
from widgets import ImageView,qimage

class FullscreenImages(QDialog):
    def __init__(self,images,index=0,parent=None,pixmaps=None):
        super().__init__(parent);self.setWindowTitle('Prism Compare · 全屏');self.images=images
        # Upload once, before switching is enabled. Sources are never opened here.
        self.pixmaps=list(pixmaps) if pixmaps is not None else [QPixmap.fromImage(qimage(item['display'])) if item else None for item in images]
        self.current=None;self.buttons=[];self.shortcuts=[]
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        bar=QWidget();row=QHBoxLayout(bar);row.setContentsMargins(8,4,8,4)
        row.addWidget(QLabel('全屏 · ← / → 切换 · F 适应 · 1 原大 · Esc 退出'));row.addStretch()
        for i,item in enumerate(images):
            button=QPushButton(chr(65+i));button.setCheckable(True);button.setStyleSheet('QPushButton:checked { background: #0067c0; color: white; border: 1px solid #0067c0; }');button.setFixedWidth(42);button.setEnabled(item is not None)
            button.setToolTip(item['path'] if item else '来源缺失');button.clicked.connect(lambda checked=False,j=i:self.select(j));row.addWidget(button);self.buttons.append(button)
        row.addStretch();close=QPushButton('退出全屏');close.clicked.connect(self.reject);row.addWidget(close);layout.addWidget(bar)
        self.view=ImageView();layout.addWidget(self.view,1)
        for key,fn in [('Left',lambda:self.step(-1)),('Right',lambda:self.step(1)),('F',self.view.fit),('1',self.view.actual),('F10',self.reject)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(fn);self.shortcuts.append(shortcut)
        for i,key in enumerate('ABCD'[:len(images)]):
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(lambda j=i:self.select(j));self.shortcuts.append(shortcut)
        if not self.pixmaps[index]:index=next((i for i,p in enumerate(self.pixmaps) if p),index)
        self.select(index);self.setWindowState(Qt.WindowState.WindowFullScreen)
    def select(self,index):
        if not 0<=index<len(self.images) or self.pixmaps[index] is None:return
        state=self.view.state() if self.current is not None else None
        self.current=index;self.view.guard=True;self.view.item.setPixmap(self.pixmaps[index]);self.view.item.setTransformOriginPoint(self.view.item.boundingRect().center());self.view.scene_.setSceneRect(self.view.item.sceneBoundingRect());self.view.guard=False
        if state:self.view.apply_state(state)
        else:self.view.fit(emit=False)
        item=self.images[index];h,w=item['raw'].shape[:2]
        self.view.info_title=chr(65+index)+' · '+item['path'];self.view.info_meta=f'{w} × {h} · {item["raw"].dtype.itemsize*8}bit'
        for i,button in enumerate(self.buttons):button.setChecked(i==index)
        self.view.viewport().update()
    def step(self,delta):
        for distance in range(1,len(self.images)+1):
            index=(self.current+delta*distance)%len(self.images)
            if self.images[index]:self.select(index);return
