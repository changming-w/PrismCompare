import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen';sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from PySide6.QtWidgets import QApplication
from widgets import ImageView,Histogram
from app import setup_fonts
app=QApplication([]);setup_fonts(app);view=ImageView();view.resize(500,300);hist=Histogram(view)
raw=np.zeros((512,512,3),np.uint8);raw[:]=[16,20,27];values={key:np.arange(256,dtype=float) for key in ['R','G','B','H','S','V','Y']}
view.set_image(raw);hist.configure(values,'RGB',False);hist.setVisible(True);view.show();app.processEvents()
def patch():app.processEvents();return view.viewport().grab().toImage().copy(8,8,180,88)
expected=patch()
view.set_zoom(200);view.centerOn(400,400);assert patch()==expected,'overlay moved or rescaled during zoom/pan'
view.resize(700,400);assert patch()==expected,'overlay changed during resize'
view.rotate_image(90);assert patch()==expected,'overlay rotated with image'
view.fit();assert patch()==expected,'overlay changed during fit'
hist.hide();assert patch()!=expected,'overlay did not hide'
print('Fixed histogram render pixels passed: zoom, pan, resize, rotation, fit, hide')
view.close()
