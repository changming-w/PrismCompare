"""Bottom image comparison inspector: pixel grids, tolerances and difference view."""
import math
import numpy as np
import cv2
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QSlider,QDoubleSpinBox,QPushButton,QScrollArea
from widgets import ImageView,PixelGrid
from metric_table import MetricTable

class DetailPanel(QWidget):
    threshold_changed=Signal(float)
    zoom_changed=Signal(float)
    fit_requested=Signal()
    actual_requested=Signal()
    swap_requested=Signal()
    pixel=Signal(int,int)
    def __init__(self):
        super().__init__();self.bundle=None;self.xy=None;self.mode=0;self.mix=.5;self.gain=1
        self.setMinimumHeight(240)
        outer=QHBoxLayout(self);outer.setContentsMargins(0,4,0,0);outer.setSpacing(8)
        left=QWidget();layout=QVBoxLayout(left);layout.setContentsMargins(6,4,6,4);layout.setSpacing(4)
        row=QHBoxLayout();self.pair=QLabel('基准 A  对');row.addWidget(self.pair);self.target=QComboBox();row.addWidget(self.target);row.addStretch();layout.addLayout(row)
        self.target.currentIndexChanged.connect(self.render)
        row=QHBoxLayout();self.zoom_label=QLabel('缩放');row.addWidget(self.zoom_label);self.zoom=QSlider(Qt.Orientation.Horizontal);self.zoom.setRange(-200,300);self.zoom.setValue(0);row.addWidget(self.zoom,1)
        self.actual_button=QPushButton('100%');self.actual_button.setFixedWidth(48);self.actual_button.setToolTip('恢复原始像素大小');self.actual_button.clicked.connect(self.actual_requested.emit);row.addWidget(self.actual_button)
        self.fit_button=QPushButton('适应');self.fit_button.setFixedWidth(44);self.fit_button.setToolTip('适应窗口');self.fit_button.clicked.connect(self.fit_requested.emit);row.addWidget(self.fit_button)
        for button in (self.actual_button,self.fit_button):button.setStyleSheet('padding: 2px 4px;');button.setFixedHeight(24)
        layout.addLayout(row);self.zoom.valueChanged.connect(lambda v:self.zoom_changed.emit(100*10**(v/100)))
        row=QHBoxLayout();row.addWidget(QLabel('容差'));self.threshold_slider=QSlider(Qt.Orientation.Horizontal);self.threshold_slider.setRange(0,255);row.addWidget(self.threshold_slider,1)
        self.threshold=QDoubleSpinBox();self.threshold.setDecimals(3);self.threshold.setRange(0,255);self.threshold.setFixedWidth(85);row.addWidget(self.threshold);layout.addLayout(row)
        self.threshold.valueChanged.connect(self.threshold_changed.emit);self.threshold_slider.valueChanged.connect(lambda v:self.threshold_changed.emit(float(v)))
        row=QHBoxLayout();self.grids=[];self.readouts=[];self.pixel_titles=[]
        for _ in range(2):
            column=QVBoxLayout();title=QLabel('像素细节');grid=PixelGrid();readout=QLabel('移动光标查看像素');readout.setWordWrap(True);readout.setMinimumHeight(30)
            for widget in (title,grid,readout):
                policy=widget.sizePolicy();policy.setRetainSizeWhenHidden(True);widget.setSizePolicy(policy);widget.hide()
            column.addWidget(title);column.addWidget(grid);column.addWidget(readout);row.addLayout(column);self.grids.append(grid);self.readouts.append(readout);self.pixel_titles.append(title)
        layout.addLayout(row)
        layout.addStretch()
        self.metrics=MetricTable();self.metrics.setText('选择两张图片查看指标')
        scroll=QScrollArea();scroll.setWidget(left);scroll.setWidgetResizable(True);scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        controls=QWidget();controls.setFixedWidth(302);column=QVBoxLayout(controls);column.setContentsMargins(0,0,0,0);column.setSpacing(4);column.addWidget(scroll,1);column.addWidget(self.metrics);outer.addWidget(controls)
        right=QWidget();column=QVBoxLayout(right);column.setContentsMargins(0,0,0,0);column.setSpacing(3)
        self.caption=QLabel('差异图 · 红：超过阈值  蓝：阈值内差异  黑：相同');column.addWidget(self.caption)
        self.view=ImageView();self.view.pixel.connect(self.pixel.emit);self.view.changed.connect(lambda _:self.update_zoom(self.view.transform().m11()*100));column.addWidget(self.view,1);outer.addWidget(right,1)
    def set_threshold(self,value,maximum):
        for widget in [self.threshold,self.threshold_slider]:
            widget.blockSignals(True);widget.setMaximum(maximum);widget.setValue(value if widget is self.threshold else round(value));widget.blockSignals(False)
    def update_zoom(self,percent):
        self.zoom_label.setText(f'缩放 {percent:.0f}%');self.zoom.blockSignals(True);self.zoom.setValue(round(100*math.log10(max(.01,percent/100))));self.zoom.blockSignals(False)
    def set_bundle(self,bundle):
        self.bundle=bundle;base=bundle['baseline'];selected=self.target.currentData();self.target.blockSignals(True);self.target.clear()
        for i in range(len(bundle['images'])):
            if i!=base:self.target.addItem(chr(65+i),i)
        index=self.target.findData(selected);self.target.setCurrentIndex(max(0,index));self.target.blockSignals(False);self.pair.setText(f'基准 {chr(65+base)}  对');self.render()
    def update_threshold_result(self,bundle):
        self.bundle=bundle;self.render(threshold_only=True)
    def render(self,*_,threshold_only=False):
        if not self.bundle:return
        b=self.bundle;base=b['baseline'];target=self.target.currentData()
        if target is None:return
        result=b['comparisons'][target];valid=result and result.get('compatible')
        self.view.setVisible(bool(valid))
        if valid:
            basis=result.get('difference_basis','RGB');title=f'{basis} 差异图 · 红：超过阈值  蓝：阈值内差异  黑：相同';display=result['heat'];self.view.wipe_fraction=None
            if self.mode==2:
                gray=np.clip(result['magnitude']*255*self.gain,0,255).astype(np.uint8);display=np.repeat(gray[:,:,None],3,axis=2);title=basis+' 绝对差值'
            elif self.mode in (3,4):
                a=b['images'][base]['display'][:,:,:3];other=b['images'][target]['display'][:,:,:3]
                if self.mode==3:display=cv2.addWeighted(a,1-self.mix,other,self.mix,0);title=f'混合 · {self.mix*100:.0f}%'
                else:
                    display=other.copy();cut=int(display.shape[1]*self.mix);display[:,:cut]=a[:,:cut];self.view.wipe_fraction=self.mix;title='分割 · 拖动竖线调整位置（左侧基准 / 右侧对比）'
            self.caption.setText(f'{chr(65+base)} ↔ {chr(65+target)} '+title)
            self.view.set_image(display,preserve=self.view.item.pixmap().isNull()==False)
            self.metrics.set_result(result,base,target)
            self.metrics.setToolTip('原分辨率计算。差异图、最大差和超阈值计数使用当前通道模式，可包含 Alpha；PSNR/SSIM/MAE 不含 Alpha。容差只影响红蓝分类。')
            if not threshold_only:self.update_zoom(self.view.transform().m11()*100)
        else:
            reason='正在更新比较指标…' if b.get('dirty_comparisons') else result.get('reason','不能计算差异') if result else '来源缺失，不能计算差异';self.caption.setText(reason);self.metrics.setText(reason)
        if not threshold_only:self.set_pixel(*(self.xy or (-1,-1)))
    def set_pixel(self,x,y):
        self.xy=(x,y)
        if not self.bundle:return
        base=self.bundle['baseline'];target=self.target.currentData()
        if target is None:return
        for slot,index in enumerate([base,target]):
            item=self.bundle['images'][index];self.pixel_titles[slot].setText(f'{chr(65+index)} · 像素细节');self.grids[slot].configure(item,self.xy)
            visible=item is not None and 0<=x<item['raw'].shape[1] and 0<=y<item['raw'].shape[0]
            for widget in (self.pixel_titles[slot],self.grids[slot],self.readouts[slot]):widget.setVisible(visible)
            if not visible:self.readouts[slot].clear();continue
            raw=item['raw']
            if not(0<=x<raw.shape[1] and 0<=y<raw.shape[0]):self.readouts[slot].clear();continue
            values=raw[y,x];text=f"X:{x} Y:{y}\nRGB:"+','.join(str(int(v)) for v in values[:3])
            if len(values)==4:text+=f'\nA:{int(values[3])}'
            self.readouts[slot].setText(text);self.readouts[slot].setToolTip('原始存储码值，不经过预览量化。')
        self.view.set_cursor_pixel(x,y)
