"""Fixed geometry for the lower-left comparison metrics."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView

class MetricTable(QTableWidget):
    def __init__(self):
        super().__init__(7,2)
        self.horizontalHeader().hide();self.verticalHeader().hide()
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setWordWrap(False);self.setShowGrid(False);self.setAlternatingRowColors(False)
        self.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0,85)
        height=max(21,self.fontMetrics().height()+5)
        self.verticalHeader().setDefaultSectionSize(height)
        self.setFixedHeight(height*7+2*self.frameWidth())
        for row,label in enumerate(['比较','PSNR','SSIM','MAE','最大差','超阈值','比例']):
            self.setItem(row,0,QTableWidgetItem(label));item=QTableWidgetItem('—')
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);self.setItem(row,1,item)
    def setText(self,text):
        for row in range(7):self.item(row,1).setText(text if row==0 else '—')
        self.item(0,1).setToolTip(text)
    def text(self):
        return '\n'.join(self.item(r,0).text()+' '+self.item(r,1).text() for r in range(7))
    def set_result(self,result,base,target):
        metric=result.get('selected',result);basis=result.get('difference_basis','RGB')
        self.item(2,0).setText('SSIM('+metric.get('ssim_basis','Y′')+')')
        values=[f'{chr(65+base)} ↔ {chr(65+target)} · {basis}',
                ('∞' if np.isinf(metric['psnr']) else f"{metric['psnr']:.2f}")+' dB',
                f"{metric['ssim']:.6f}",f"{metric['mae']:.4f}",f"{result['max']:.3f}",
                f"{result['above']:,} / {result['total']:,}",f"{result['above']/result['total']*100:.3f}%"]
        for row,value in enumerate(values):self.item(row,1).setText(value);self.item(row,1).setToolTip(value)
