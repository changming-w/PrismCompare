"""Measure painted fullscreen switches and continuous full-resolution tolerance updates."""
import os,sys,time,tempfile,json
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import cv2,numpy as np
from PySide6.QtWidgets import QApplication,QProgressBar
from PySide6.QtCore import QTimer
from app import Window,setup_fonts
from fullscreen import FullscreenImages

app=QApplication([]);setup_fonts(app)
def wait(fn,timeout=60):
    start=time.monotonic()
    while not fn():
        app.processEvents();time.sleep(.002)
        assert time.monotonic()-start<timeout,'timeout'

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);os.environ['PRISM_CONFIG_DIR']=str(root/'config')
    a=np.zeros((2160,3840,3),np.uint16);a[:,:,0]=np.arange(3840,dtype=np.uint16)*16
    b=a.copy();b[:,:,1]=np.arange(2160,dtype=np.uint16)[:,None]*30
    paths=[]
    for i,raw in enumerate([a,b]):
        path=root/f'{i}.png';cv2.imencode('.png',raw)[1].tofile(path);paths.append(str(path))
    del a,b,raw
    w=Window();w.resize(1500,950);w.show();w.set_paths(paths,False)
    wait(lambda:w.bundle and w.preview_id is None)
    wait(lambda:not w.thumb_pending and not w.thumb_timer.isActive())
    # Observe every event-loop iteration, not just the final settled geometry.
    w.details.view.set_zoom(37);app.processEvents()
    def geometry():
        v=w.details.view;t=v.transform()
        return (w.details.metrics.geometry().getRect(),w.image_split.geometry().getRect(),w.workspace.geometry().getRect(),v.viewport().size().width(),v.viewport().size().height(),t.m11(),t.m22(),t.dx(),t.dy(),v.horizontalScrollBar().value(),v.verticalScrollBar().value())
    stable=geometry();observed=[]
    assert not w.findChildren(QProgressBar)
    probe=QTimer();probe.setInterval(1);probe.timeout.connect(lambda:observed.append(geometry()));probe.start()
    values=[];beats=[];tick=[0];timer=QTimer();timer.setInterval(30);started=time.monotonic()
    def drag():
        tick[0]+=1;beats.append(time.monotonic());w.details.threshold_slider.setValue(tick[0]*3);values.append(w.bundle.get('threshold'))
        if tick[0]>=60:timer.stop()
    timer.timeout.connect(drag);timer.start();wait(lambda:not timer.isActive());wait(lambda:w.preview_id is None and w.bundle.get('threshold')==180)
    probe.stop()
    assert observed and all(g==stable for g in observed),'Layout or viewport moved during tolerance updates'
    assert len(set(values))>=5
    metric=w.bundle['comparisons'][1];expected=int((metric['magnitude']>180/255+1e-8).sum());assert metric['above']==expected
    full=FullscreenImages(w.bundle['images'],0,w,pixmaps=[p.image.item.pixmap() for p in w.panes[:2]]);full.resize(1500,950);full.show();app.processEvents()
    times=[]
    for i in range(30):
        t=time.monotonic();full.select(i%2);app.processEvents();times.append(time.monotonic()-t)
    result={'stable_geometry_samples':len(observed),'ok':True,'resolution':[3840,2160],'bit_depth':16,'threshold_updates_while_dragging':len(set(values)),'drag_duration_seconds':round(beats[-1]-beats[0],3),'max_ui_tick_gap_seconds':round(max(np.diff(beats)),3),'fullscreen_painted_switch_median_ms':round(float(np.median(times))*1000,2),'fullscreen_painted_switch_max_ms':round(max(times)*1000,2)}
    Path('validation/interactive_4k_results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    full.close();w.close();wait(lambda:not w.pool.activeThreadCount() and not w.thumb_pool.activeThreadCount())
