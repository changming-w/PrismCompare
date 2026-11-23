from pathlib import Path
import struct,sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QPainter,QColor,QPainterPath,QLinearGradient,QPen
from PySide6.QtCore import Qt,QBuffer,QIODevice
app=QApplication([]);root=Path(__file__).resolve().parents[1];out=root/'assets';out.mkdir(exist_ok=True)
img=QImage(256,256,QImage.Format.Format_ARGB32);img.fill(Qt.GlobalColor.transparent);p=QPainter(img);p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#142239'));p.drawRoundedRect(0,0,256,256,52,52)
gradient=QLinearGradient(45,35,210,220);gradient.setColorAt(0,QColor('#8ab8ff'));gradient.setColorAt(1,QColor('#5575e8'));p.setBrush(gradient)
path=QPainterPath();path.moveTo(128,38);path.lineTo(218,191);path.lineTo(38,191);path.closeSubpath();p.drawPath(path)
p.setBrush(QColor('#b5f7e5'));path=QPainterPath();path.moveTo(128,74);path.lineTo(128,171);path.lineTo(185,171);path.closeSubpath();p.drawPath(path);p.end();img.save(str(out/'prism.png'))
buffer=QBuffer();buffer.open(QIODevice.OpenModeFlag.WriteOnly);img.save(buffer,'PNG');data=bytes(buffer.data());header=struct.pack('<HHH',0,1,1)+struct.pack('<BBBBHHII',0,0,0,0,1,32,len(data),22);(out/'prism.ico').write_bytes(header+data)
for name,color in [('down_light','#404040'),('down_dark','#d4e0ef')]:
    a=QImage(20,12,QImage.Format.Format_ARGB32);a.fill(Qt.GlobalColor.transparent);p=QPainter(a);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(QColor(color),2));p.drawLine(3,3,10,9);p.drawLine(10,9,17,3);p.end();a.save(str(out/(name+'.png')))
a=QImage(20,20,QImage.Format.Format_ARGB32);a.fill(Qt.GlobalColor.transparent);p=QPainter(a);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.setPen(QPen(QColor('white'),2.4));p.drawLine(4,10,8,14);p.drawLine(8,14,16,5);p.end();a.save(str(out/'check.png'))
