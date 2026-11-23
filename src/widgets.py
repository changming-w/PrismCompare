from __future__ import annotations
from collections import OrderedDict
from pathlib import Path
import math,re
import numpy as np
from PySide6.QtCore import Qt, QObject, QEvent, Signal, QSize, QRectF, QPointF, QAbstractTableModel, QModelIndex
from PySide6.QtGui import QColor,QImage,QPixmap,QPainter,QPainterPath,QPen,QFont,QTextCharFormat,QSyntaxHighlighter,QTextCursor,QTransform
from PySide6.QtWidgets import QWidget,QGraphicsObject,QGraphicsView,QGraphicsScene,QGraphicsPixmapItem,QVBoxLayout,QHBoxLayout,QLabel,QPlainTextEdit,QStackedWidget,QStyledItemDelegate,QStyle,QTextEdit,QSizePolicy,QToolButton
from core import IMAGE_EXTS

COLORS=['#7ca9ff','#54dbb0','#ffca72','#cf9eff']

class SettingsToggle(QToolButton):
    """Flat disclosure button with a drawn chevron (no font glyph dependency)."""
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#71849a'),1.4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin))
        x=self.width()-17;y=self.height()/2;direction=-1 if self.isChecked() else 1
        painter.drawLine(QPointF(x,y-direction*1.5),QPointF(x+3,y+direction*1.5))
        painter.drawLine(QPointF(x+3,y+direction*1.5),QPointF(x+6,y-direction*1.5))

def qimage(a):
    a=np.ascontiguousarray(a,dtype=np.uint8)
    fmt=QImage.Format.Format_RGBA8888 if a.shape[2]==4 else QImage.Format.Format_RGB888
    return QImage(a.data,a.shape[1],a.shape[0],a.strides[0],fmt).copy()

class ImageView(QGraphicsView):
    changed=Signal(object)
    pixel=Signal(int,int)
    wipe_changed=Signal(float)
    def __init__(self,parent=None):
        super().__init__(parent);self.scene_=QGraphicsScene(self);self.setScene(self.scene_)
        self.presentation_only=False;self.info_title='';self.info_meta='';self._display_array=None;self.histogram=None;self.wipe_fraction=None;self.dragging_wipe=False;self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.item=QGraphicsPixmapItem();self.scene_.addItem(self.item);self.guard=False;self.fit_mode=True
        self.setBackgroundBrush(QColor('#10141b'));self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.setMinimumHeight(30)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag);self.setMouseTracking(True);self.cursor_pixel=None
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
    def set_image(self,array,preserve=False):
        if preserve and self._display_array is array:return
        self._display_array=array
        bounds=self.item.boundingRect()
        if preserve and bounds.width()==array.shape[1] and bounds.height()==array.shape[0]:
            # Same canvas: replace pixels only. Re-fitting/re-centering can round
            # scroll positions and move the image during continuous updates.
            self.item.setPixmap(QPixmap.fromImage(qimage(array)));self.viewport().update();return
        state=self.state();self.guard=True;self.item.setPixmap(QPixmap.fromImage(qimage(array)));self.item.setTransformOriginPoint(self.item.boundingRect().center());self.scene_.setSceneRect(self.item.sceneBoundingRect());self.guard=False
        if preserve and state:self.apply_state(state)
        else:self.fit(emit=False)
    def fit(self,emit=True):
        self.guard=True;self.fit_mode=True
        if not self.item.pixmap().isNull():
            if self.presentation_only:
                bounds=self.item.sceneBoundingRect();scale=min(self.viewport().width()/bounds.width(),self.viewport().height()/bounds.height());self.setTransform(QTransform.fromScale(scale,scale));self.centerOn(bounds.center())
            else:self.fitInView(self.item,Qt.AspectRatioMode.KeepAspectRatio)
        self.guard=False
        if emit:self.notify()
    def actual(self):
        self.guard=True;self.fit_mode=False;self.resetTransform();self.guard=False;self.notify()
    def state(self):
        r=self.item.boundingRect()
        if not r.width():return None
        p=self.item.mapFromScene(self.mapToScene(self.viewport().rect().center()));bounds=self.item.sceneBoundingRect();fit=min(self.viewport().width()/bounds.width(),self.viewport().height()/bounds.height())
        return {'zoom':self.transform().m11()/max(fit,1e-9),'x':p.x()/r.width(),'y':p.y()/r.height(),'fit':self.fit_mode}
    def apply_state(self,state):
        if not state:return
        r=self.item.boundingRect()
        if not r.width():return
        self.guard=True;self.fit_mode=state['fit']
        if self.fit_mode:self.fit(emit=False)
        else:
            bounds=self.item.sceneBoundingRect();fit=min(self.viewport().width()/bounds.width(),self.viewport().height()/bounds.height())
            self.setTransform(QTransform.fromScale(fit*state['zoom'],fit*state['zoom']));self.centerOn(self.item.mapToScene(QPointF(state['x']*r.width(),state['y']*r.height())))
        self.guard=False
    def notify(self,*_):
        if not self.guard:self.changed.emit(self.state())
    def wheelEvent(self,event):
        if self.item.pixmap().isNull():return
        factor=1.25 if event.angleDelta().y()>0 else .8
        proposed=self.transform().m11()*factor
        if not .005<proposed<64:return
        before=self.mapToScene(event.position().toPoint());self.guard=True;self.fit_mode=False;self.scale(factor,factor)
        after=self.mapToScene(event.position().toPoint());self.translate(after.x()-before.x(),after.y()-before.y());self.guard=False;self.notify();event.accept()
    def mouseMoveEvent(self,event):
        if self.dragging_wipe:
            self.move_wipe(event.position().toPoint());event.accept();return
        self.viewport().setCursor(Qt.CursorShape.SplitHCursor if self.near_wipe(event.position().toPoint()) else Qt.CursorShape.CrossCursor)
        p=self.item.mapFromScene(self.mapToScene(event.position().toPoint()));self.pixel.emit(math.floor(p.x()),math.floor(p.y()));super().mouseMoveEvent(event)
        if event.buttons() & Qt.MouseButton.LeftButton:self.notify()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.near_wipe(event.position().toPoint()):
            self.dragging_wipe=True;self.viewport().setCursor(Qt.CursorShape.SplitHCursor);event.accept();return
        super().mousePressEvent(event);self.viewport().setCursor(Qt.CursorShape.CrossCursor)
    def mouseReleaseEvent(self,event):
        if self.dragging_wipe:
            self.move_wipe(event.position().toPoint());self.dragging_wipe=False;event.accept();return
        super().mouseReleaseEvent(event);self.viewport().setCursor(Qt.CursorShape.CrossCursor)
    def near_wipe(self,point):
        if self.wipe_fraction is None:return False
        bounds=self.item.boundingRect();line=self.mapFromScene(self.item.mapToScene(QPointF(bounds.width()*self.wipe_fraction,bounds.height()/2)))
        return abs(point.x()-line.x())<=10
    def move_wipe(self,point):
        width=self.item.boundingRect().width()
        if width:
            x=self.item.mapFromScene(self.mapToScene(point)).x();self.wipe_changed.emit(max(0,min(1,x/width)))
    def set_cursor_pixel(self,x,y):
        self.cursor_pixel=(x,y);self.viewport().update()
    def drawForeground(self,painter,rect):
        if self.presentation_only:return
        super().drawForeground(painter,rect)
        if self.wipe_fraction is not None:
            bounds=self.item.boundingRect();x=bounds.width()*self.wipe_fraction;pen=QPen(QColor('#4da2e8'),2);pen.setCosmetic(True);painter.setPen(pen)
            painter.drawLine(QPointF(x,0),QPointF(x,bounds.height()))
            radius=6/max(.005,self.transform().m11());painter.setBrush(QColor('#f8fbff'));painter.drawEllipse(QPointF(x,bounds.height()/2),radius,radius)
        if self.info_title:
            painter.save();painter.resetTransform()
            available=max(40,self.viewport().width()-16)
            text=self.info_title+'  |  '+self.info_meta
            text=painter.fontMetrics().elidedText(text,Qt.TextElideMode.ElideMiddle,available-12)
            width=min(available,painter.fontMetrics().horizontalAdvance(text)+12)
            painter.fillRect(QRectF(8,self.viewport().height()-28,width,22),QColor(16,20,27,135))
            painter.setPen(QColor('#edf2fa'));painter.drawText(QRectF(14,self.viewport().height()-28,width-12,22),Qt.AlignmentFlag.AlignVCenter,text);painter.restore()
        if self.histogram is not None and self.histogram.isVisible():
            painter.save();painter.resetTransform();painter.translate(8,8);self.histogram.paint(painter,None);painter.restore()
        if self.cursor_pixel is None:return
        x,y=self.cursor_pixel
        if not self.item.boundingRect().contains(QPointF(x+.5,y+.5)):return
        radius=5/max(self.transform().m11(),.005);center=self.item.mapToScene(QPointF(x+.5,y+.5))
        for color,width in [('#10141b',3),('#ffffff',1)]:
            pen=QPen(QColor(color),width);pen.setCosmetic(True);painter.setPen(pen)
            painter.drawLine(center+QPointF(-radius,0),center+QPointF(radius,0))
            painter.drawLine(center+QPointF(0,-radius),center+QPointF(0,radius))
    def set_zoom(self,percent):
        center=self.mapToScene(self.viewport().rect().center());self.fit_mode=False
        self.setTransform(QTransform.fromScale(percent/100,percent/100));self.centerOn(center);self.viewport().update()
    def fit_width(self):
        bounds=self.item.sceneBoundingRect()
        if bounds.isEmpty():return
        self.set_zoom(max(1,self.viewport().width()-4)/bounds.width()*100);self.centerOn(bounds.center());self.notify()
    def match_reference(self,reference):
        target=self.item.sceneBoundingRect();base=reference.item.sceneBoundingRect()
        if target.isEmpty() or base.isEmpty():return
        scale=reference.transform().m11()*min(base.width()/target.width(),base.height()/target.height())
        self.set_zoom(scale*100);self.centerOn(target.center())
    def rotate_image(self,degrees):
        self.item.setRotation((self.item.rotation()+degrees)%360);self.scene_.setSceneRect(self.item.sceneBoundingRect());self.fit()
    def reset_rotation(self):
        self.item.setRotation(0);self.scene_.setSceneRect(self.item.sceneBoundingRect());self.fit()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.fit_mode:
            self.guard=True
            if not self.item.pixmap().isNull():self.fit(emit=False)
            self.guard=False

class Histogram(QObject):
    """Viewport-pixel overlay, painted independently of image transforms."""
    def __init__(self,view):
        super().__init__(view);self.view=view;view.histogram=self;self.values=None;self.mode='RGB';self.log=False;self.light=True;self.visible=False
    def boundingRect(self):return QRectF(0,0,180,88)
    def viewport_rect(self):return QRectF(8,8,180,88)
    def width(self):return 180
    def height(self):return 88
    def update(self):self.view.viewport().update()
    def setVisible(self,visible):self.visible=visible;self.update()
    def isVisible(self):return self.visible
    def hide(self):self.setVisible(False)
    def configure(self,values=None,mode=None,log=None):
        if values is not None:self.values=values
        if mode is not None:self.mode=mode
        if log is not None:self.log=log
        self.update()
    def paint(self,p,option,widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255,255,255,45),1));p.setBrush(QColor(245,248,252,45))
        p.drawRoundedRect(self.boundingRect().adjusted(.5,.5,-.5,-.5),5,5)
        rect=QRectF(8,23,max(1,self.width()-16),max(1,self.height()-31))
        keys=list(self.mode) if self.mode in ('RGB','HSV') else ['Y','Cb','Cr'] if self.mode=='YUV' else ['Y']
        colors={'R':'#da5269','G':'#329f72','B':'#488cdb','Cb':'#488cdb','Cr':'#da5269','Y':'#927c42','H':'#a36cd4','S':'#39a99d','V':'#c99d48'}
        p.setFont(QFont('Segoe UI',8));x=8
        for k in keys:
            p.setPen(QColor(colors[k]));p.drawText(x,16,k if k!='Y' else 'Y′');x+=20
        p.setPen(QColor(67,79,96,190));p.drawText(self.width()-40,16,'LOG' if self.log else '')
        p.setPen(QPen(QColor(100,120,145,55),1));p.drawLine(rect.bottomLeft(),rect.bottomRight())
        if not self.values:return
        arrays=[np.log1p(self.values[k]) if self.log else self.values[k].astype(float) for k in keys]
        maximum=max(max(a) for a in arrays) or 1
        for k,a in zip(keys,arrays):
            line=QPainterPath();line.moveTo(rect.left(),rect.bottom())
            for i,v in enumerate(a):line.lineTo(rect.left()+i/255*rect.width(),rect.bottom()-float(v)/maximum*rect.height())
            line.lineTo(rect.right(),rect.bottom());line.closeSubpath()
            fill=QColor(colors[k]).lighter(145);fill.setAlpha(45)
            outline=QColor(colors[k]);outline.setAlpha(125)
            p.setBrush(fill);p.setPen(QPen(outline,1));p.drawPath(line)

class PixelGrid(QWidget):
    """Nearest-neighbour pixel neighbourhood, with native numeric readout elsewhere."""
    def __init__(self):
        super().__init__();self.item=None;self.xy=None;self.setFixedSize(90,90)
    def configure(self,item,xy):self.item=item;self.xy=xy;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#151b24'));cell=10
        if self.item is not None and self.xy is not None:
            x,y=self.xy;display=self.item['display'];h,w=display.shape[:2]
            for row in range(9):
                for col in range(9):
                    xx,yy=x+col-4,y+row-4
                    if 0<=x<w and 0<=y<h and 0<=xx<w and 0<=yy<h:
                        rgb=display[yy,xx,:3];p.fillRect(col*cell,row*cell,cell,cell,QColor(*map(int,rgb)))
        p.setPen(QColor('#48515d'))
        for i in range(10):
            p.drawLine(i*cell,0,i*cell,90);p.drawLine(0,i*cell,90,i*cell)
        p.setPen(QPen(QColor('#000000'),3));p.drawRect(40,40,10,10)
        p.setPen(QPen(QColor('#ffffff'),1));p.drawRect(40,40,10,10)

class CodeHighlighter(QSyntaxHighlighter):
    def __init__(self,document):
        super().__init__(document);self.light=True
        self.rules=[(r'\b(def|class|return|if|else|elif|for|while|import|from|as|try|except|finally|with|yield|async|await|public|private|static|void|int|float|const|let|var|function|new|true|false|null|None|True|False|include|switch|case|break|continue|struct|namespace|using)\b','#c5a3ff'),(r'\b\d+(?:\.\d+)?\b','#ffcc86'),(r'"[^"\n]*"|\x27[^\x27\n]*\x27','#8fdbac'),(r'(?://|#).*$', '#73879b')]
    def highlightBlock(self,text):
        for pattern,color in self.rules:
            if self.light:color={'#c5a3ff':'#7946b5','#ffcc86':'#97620c','#8fdbac':'#20754c','#73879b':'#667684'}[color]
            fmt=QTextCharFormat();fmt.setForeground(QColor(color))
            for m in re.finditer(pattern,text):self.setFormat(m.start(),m.end()-m.start(),fmt)

class ComparePane(QWidget):
    def __init__(self,index):
        super().__init__();self.index=index;self.raw=None;self.light=True;self.text_columns=None;self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Ignored)
        lay=QVBoxLayout(self);lay.setContentsMargins(0,0,0,0);lay.setSpacing(0)
        self.title=QLabel(f'  {chr(65+index)}  ·  尚未选择文件');self.title.setObjectName('paneTitle');self.title.setStyleSheet(f'border-top: 3px solid {COLORS[index]};');self.title.setMinimumHeight(38);self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.meta=QLabel('');self.meta.setObjectName('meta');self.meta.setWordWrap(True);self.meta.setTextFormat(Qt.TextFormat.PlainText)
        self.stack=QStackedWidget();self.image=ImageView();self.text=QPlainTextEdit();self.text.setReadOnly(True);self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap);self.text.setFont(QFont('Cascadia Mono',10));self.text.setObjectName('codeEditor');self.highlighter=CodeHighlighter(self.text.document())
        self.empty=QLabel('选择文件，开始比对');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);self.empty.setWordWrap(True);self.empty.setObjectName('empty');self.empty.setTextFormat(Qt.TextFormat.PlainText)
        for w in [self.image,self.text,self.empty]:self.stack.addWidget(w)
        self.stack.setCurrentWidget(self.empty);self.hist=Histogram(self.image);self.hist.hide();self.pixel=QLabel('');self.pixel.setObjectName('pixel');self.pixel.setMinimumHeight(23);self.stats=QLabel('');self.stats.setWordWrap(True);self.stats.setObjectName('stats')
        for w in [self.title,self.meta,self.stack]:lay.addWidget(w)
        self.pixel.hide();self.stats.hide()
        lay.setStretch(2,1)
        self.title.setFixedHeight(36);self.meta.setFixedHeight(28);self.pixel.setFixedHeight(23);self.stats.setFixedHeight(46)
    def set_title(self,path,baseline=False):
        name=Path(path).name if path else '缺少文件';self.title.setText(f'  {chr(65+self.index)}'+('  基准' if baseline else '')+'  ·  '+name);self.title.setToolTip(path or '');self.image.info_title=self.title.text().strip();self.image.setToolTip(path or '');self.image.viewport().update()
    def message(self,text):
        self.title.setVisible(not self.image.presentation_only);self.meta.hide();self.raw=None;self.meta.clear();self.stats.clear();self.pixel.clear();self.empty.setText(text);self.stack.setCurrentWidget(self.empty);self.hist.hide()
    def set_image(self,item,histmode,log):
        preserve=self.raw is not None;self.raw=item['raw'];h,w=self.raw.shape[:2];self.meta.setText(f'  {w} × {h}  ·  {self.raw.dtype.itemsize*8}bit / {self.raw.shape[2]} 通道')
        self.title.hide();self.meta.hide();self.image.info_meta=self.meta.text().strip()
        self.stack.setCurrentWidget(self.image);self.image.set_image(item['display'],preserve=preserve);self.hist.configure(item['hist'],histmode,log);self.hist.setVisible(histmode!='关闭' and item['hist'] is not None);self.pixel.setText('移动指针查看原始 RGB 码值')
    def show_pixel(self,x,y):
        if self.raw is None or not(0<=x<self.raw.shape[1] and 0<=y<self.raw.shape[0]):self.pixel.setText('');return
        vals=', '.join(str(int(v)) for v in self.raw[y,x]);self.pixel.setText(f'  ({x}, {y})   '+('RGBA' if self.raw.shape[2]==4 else 'RGB')+f' [{vals}]')
    def set_text(self,columns,note):
        self.title.show();self.meta.show();self.text_columns=columns
        self.raw=None;self.hist.hide();self.pixel.clear();self.stats.clear();self.meta.setText(note);self.stack.setCurrentWidget(self.text)
        self.text.setPlainText('\n'.join(f'{number:5d} │ {text}' if number is not None else '      │' for text,number,_ in columns))
        selections=[];palette=({'changed':'#ffe3e7','added':'#def2e6','missing':'#e8edf3'} if self.light else {'changed':'#4c2e39','added':'#1f443e','missing':'#273449'})
        for i,(_,_,tag) in enumerate(columns):
            if tag=='same':continue
            selection=QTextEdit.ExtraSelection();selection.cursor=QTextCursor(self.text.document().findBlockByNumber(i));selection.format.setBackground(QColor(palette.get(tag,'#4c2e39')));selection.format.setProperty(QTextCharFormat.Property.FullWidthSelection,True);selections.append(selection)
        self.text.setExtraSelections(selections)
    def set_theme(self,light):
        self.light=light;self.hist.light=light;self.hist.update();self.highlighter.light=light;self.highlighter.rehighlight()
        if self.stack.currentWidget()==self.text and self.text_columns is not None:self.set_text(self.text_columns,self.meta.text())

class PaneArea(QWidget):
    """Equal-sized viewports independent of wrapped label size hints."""
    def __init__(self):
        super().__init__();self.panes=[];self.count=2;self.grid=False;self.gap=5;self.setMinimumSize(250,200)
    def arrange(self):
        rows=2 if self.grid and self.count>2 else 1;cols=2 if self.grid else self.count;gap=self.gap
        width=(self.width()-(cols-1)*gap)/cols;height=(self.height()-(rows-1)*gap)/rows
        for i,p in enumerate(self.panes):
            p.setVisible(i<self.count)
            if i<self.count:
                row=i//cols;col=i%cols;x=round(col*(width+gap));y=round(row*(height+gap));right=round((col+1)*width+col*gap);bottom=round((row+1)*height+row*gap)
                p.setGeometry(x,y,right-x,bottom-y)
    def resizeEvent(self,event):super().resizeEvent(event);self.arrange()

class FileModel(QAbstractTableModel):
    def __init__(self):
        super().__init__();self.rows=[];self.count=2;self.thumbnails=True;self.thumb_provider=None;self.light=True
    def reset(self,rows,count):self.beginResetModel();self.rows=rows;self.count=count;self.endResetModel()
    def rowCount(self,parent=QModelIndex()):return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()):return self.count+1
    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:return '相对路径 / 状态' if section==0 else chr(64+section)
    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():return None
        row=self.rows[index.row()];col=index.column()
        if role==Qt.ItemDataRole.DisplayRole:
            if col==0:return row.name+'\n'+row.status
            return Path(row.paths[col-1]).name if row.paths[col-1] else '— 缺少 —'
        if role==Qt.ItemDataRole.ToolTipRole:return (row.name+'\n'+row.status+'\n'+'\n'.join(row.errors)) if col==0 else ((row.paths[col-1] or '缺少文件')+'\n'+row.status+'\n'+'\n'.join(row.errors))
        if role==Qt.ItemDataRole.UserRole:return row
        if role==Qt.ItemDataRole.ForegroundRole:
            if self.light:
                if col==0:return QColor('#167047' if row.status in ['字节相同','内容相同','像素相同'] else '#8b6500' if row.status=='待校验' else '#bc3343')
                return QColor('#344054')
            if col==0:return QColor('#66d7b0' if row.status in ['字节相同','内容相同','像素相同'] else '#f0c17a' if row.status=='待校验' else '#ff8e9b')
            return QColor('#c2cfdf')
        return None

class ThumbDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        model=index.model();source=model.sourceModel();row=index.data(Qt.ItemDataRole.UserRole);col=index.column()
        if not source.thumbnails or col==0 or not row.paths[col-1] or Path(row.paths[col-1]).suffix.lower() not in IMAGE_EXTS:return super().paint(painter,option,index)
        painter.save();selected=bool(option.state & QStyle.StateFlag.State_Selected);painter.fillRect(option.rect,QColor(('#e6f0fb' if selected else '#ffffff') if source.light else ('#293e5c' if selected else '#1a2330')))
        pix=source.thumb_provider(row.paths[col-1]) if source.thumb_provider else None
        r=option.rect.adjusted(5,5,-5,-22)
        if pix and not pix.isNull():
            fitted=pix.size().scaled(r.size(),Qt.AspectRatioMode.KeepAspectRatio);x=r.x()+(r.width()-fitted.width())//2;y=r.y()+(r.height()-fitted.height())//2;painter.drawPixmap(x,y,fitted.width(),fitted.height(),pix)
        else:painter.setPen(QColor('#61738b'));painter.drawText(r,Qt.AlignmentFlag.AlignCenter,'…')
        painter.setPen(QColor('#526073' if source.light else '#bdcadd'));painter.setFont(QFont('Segoe UI',8));text=option.fontMetrics.elidedText(Path(row.paths[col-1]).name,Qt.TextElideMode.ElideMiddle,option.rect.width()-8);painter.drawText(option.rect.adjusted(4,0,-4,-3),Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignHCenter,text);painter.restore()

STYLE='''
QMainWindow, QWidget { background: #101722; color: #dce5f2; font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 12px; }
QToolTip { background: #28374b; color: #e8f0fa; border: 1px solid #536882; padding: 6px; }
QFrame#toolbar { background: #182231; border-bottom: 1px solid #2b394d; }
QLabel#brand { color: #edf4ff; font-size: 22px; font-weight: 700; background: transparent; }
QLabel#subtitle { color: #8398b3; background: transparent; }
QLabel#paneTitle { background: #1b2635; color: #e5edf7; font-weight: 600; }
QLabel#meta { background: #17202d; color: #899db7; padding: 5px 8px; font-size: 11px; }
QLabel#pixel { background: #15202c; color: #9eb5d0; font-size: 11px; padding: 2px; }
QLabel#stats { background: #1b2635; color: #b3c5dc; padding: 7px; font-size: 11px; }
QLabel#empty { color: #8497b1; font-size: 15px; padding: 20px; }
QPushButton { background: #253449; border: 1px solid #354860; border-radius: 5px; padding: 7px 12px; }
QPushButton:hover { background: #324965; border-color: #597ba5; }
QPushButton:pressed { background: #172b43; }
QPushButton:disabled { color: #60718a; background: #1c2735; }
QPushButton#primary { background: #447ef5; border-color: #6596ff; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #568cff; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #0f1824; border: 1px solid #34445c; border-radius: 4px; padding: 6px; selection-background-color: #3766a0; }
QLineEdit:focus, QComboBox:focus { border-color: #76a5ff; }
QComboBox::drop-down { width: 20px; border: 0; }
QComboBox QAbstractItemView { background: #1b293b; selection-background-color: #355479; }
QCheckBox { spacing: 6px; background: transparent; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #536b89; border-radius: 3px; background: #172334; }
QCheckBox::indicator:checked { background: #5989f2; border-color: #7ca7ff; }
QTableView { background: #141e2b; alternate-background-color: #182232; gridline-color: #273548; border: none; selection-background-color: #294568; }
QTableView::item { padding: 5px; border-bottom: 1px solid #253246; }
QHeaderView::section { background: #223045; color: #9bb0cb; border: none; border-right: 1px solid #34435a; padding: 8px 4px; }
QPlainTextEdit#codeEditor { background: #111a26; color: #ccd9ea; border: 0; selection-background-color: #405f87; }
QSplitter::handle { background: #29364a; width: 4px; height: 4px; }
QStatusBar { background: #182437; color: #a6bad4; }
QScrollBar:vertical { background: #151f2c; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #3a4c65; min-height: 30px; border-radius: 5px; }
QScrollBar:horizontal { background: #151f2c; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #3a4c65; min-width: 30px; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QSlider::groove:horizontal { background: #293b53; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: #86adff; width: 13px; margin: -5px 0; border-radius: 6px; }
QProgressBar { border: 0; background: #233247; max-height: 3px; }
QProgressBar::chunk { background: #6895f8; }
'''

LIGHT_STYLE='''
QMainWindow, QWidget { background: #f3f3f3; color: #202020; font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 12px; }
QToolTip { background: #ffffff; color: #202020; border: 1px solid #c8c8c8; padding: 6px; }
QMenuBar { background: #f3f3f3; border-bottom: 1px solid #dedede; }
QMenuBar::item { background: transparent; padding: 5px 10px; }
QMenuBar::item:selected, QMenu::item:selected { background: #e5edf7; }
QMenu { background: white; border: 1px solid #d6d6d6; padding: 4px; }
QMenu::item { padding: 6px 24px; }
QLabel#brand { color: #202020; font-size: 19px; font-weight: 600; background: transparent; }
QLabel#subtitle { color: #6c6c6c; background: transparent; }
QLabel#paneTitle { background: #f7f7f7; color: #25334a; font-weight: 600; border-bottom: 1px solid #e2e2e2; }
QLabel#meta { background: #ffffff; color: #606a77; padding: 4px 8px; font-size: 11px; }
QLabel#pixel { background: #fafafa; color: #526172; font-size: 11px; padding: 2px; }
QLabel#stats { background: #f5f7fa; color: #314155; border-top: 1px solid #e2e6ec; padding: 7px; font-size: 11px; }
QLabel#empty { background: #ffffff; color: #727b87; font-size: 14px; padding: 20px; }
QPushButton { background: #ffffff; border: 1px solid #d2d2d2; border-bottom-color: #bdbdbd; border-radius: 4px; padding: 6px 11px; }
QPushButton:hover { background: #f8f8f8; border-color: #a8bacd; }
QPushButton:pressed { background: #ebebeb; color: #545454; }
QPushButton:focus { border: 1px solid #0067c0; }
QPushButton:disabled { background: #f0f0f0; color: #a0a0a0; border-color: #dedede; }
QPushButton#primary { background: #0067c0; border-color: #0067c0; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background: #1975c5; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #ffffff; color: #202020; border: 1px solid #d4d4d4; border-bottom-color: #8e8e8e; border-radius: 3px; padding: 5px; selection-background-color: #cce4ff; selection-color: #202020; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus { border-bottom: 2px solid #0067c0; }
QComboBox QAbstractItemView { background: white; color: #202020; selection-background-color: #e3effb; selection-color: #202020; }
QCheckBox { spacing: 5px; background: transparent; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #858585; border-radius: 3px; background: #ffffff; }
QCheckBox::indicator:checked { background: #0067c0; border-color: #0067c0; }
QTableView { background: #ffffff; alternate-background-color: #fafbfc; border: 1px solid #dedede; gridline-color: #e8ebef; selection-background-color: #e2eefb; selection-color: #202020; }
QTableView::item { padding: 5px; border-bottom: 1px solid #edf0f3; }
QHeaderView::section { background: #f4f5f7; color: #4b5665; border: none; border-right: 1px solid #e0e4e9; border-bottom: 1px solid #d8dde4; padding: 8px 4px; }
QPlainTextEdit#codeEditor { background: #ffffff; color: #283441; border: none; selection-background-color: #cee5ff; selection-color: #172b42; }
QSplitter::handle { background: #e0e3e7; width: 4px; height: 4px; }
QStatusBar { background: #f7f7f7; color: #576474; border-top: 1px solid #dedede; }
QScrollBar:vertical { background: #f5f5f5; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #b4bbc4; min-height: 30px; border-radius: 5px; }
QScrollBar:horizontal { background: #f5f5f5; height: 11px; margin: 0; }
QScrollBar::handle:horizontal { background: #b4bbc4; min-width: 30px; border-radius: 5px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QSlider::groove:horizontal { background: #c5cbd3; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #0067c0; width: 13px; margin: -5px 0; border: 2px solid white; border-radius: 7px; }
QProgressBar { border: 0; background: #e4e8ed; max-height: 3px; }
QProgressBar::chunk { background: #0067c0; }
'''
