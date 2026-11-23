"""Exercise uninterrupted dragging, hidden-sidebar preloading and cached fullscreen."""
import os,sys,time,tempfile,json
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import cv2,numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from app import Window,setup_fonts
from fullscreen import FullscreenImages

app=QApplication([]);setup_fonts(app)
def wait(fn,seconds=30):
    deadline=time.monotonic()+seconds
    while not fn():
        app.processEvents();time.sleep(.005)
        if time.monotonic()>deadline:raise AssertionError('Timed out')
    app.processEvents()

with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);os.environ['PRISM_CONFIG_DIR']=str(root/'config')
    for folder in ['A','B']:
        (root/folder).mkdir()
        for i in range(24):
            raw=np.full((128,256,3),i,np.uint8)
            if folder=='B':raw[:,:,0]=np.arange(256,dtype=np.uint8)
            cv2.imencode('.png',raw)[1].tofile(root/folder/f'{i:03}.png')
    w=Window();w.show();w.set_paths([str(root/x) for x in ['A','B']],True)
    wait(lambda:w.bundle and w.preview_id is None)
    assert not w.sidebar.isVisible()
    wait(lambda:len(w.thumb_completed)==48 and not w.thumb_pending)
    # Even offscreen items have been decoded; evicted RAM entries reload local cache only.
    path=str(root/'A/023.png');w.thumb_cache.pop(path,None)
    with patch('app.np.fromfile',side_effect=AssertionError('Source reread')):
        w.thumbnail(path);wait(lambda:path in w.thumb_cache)
    values=[];ticks=[0];timer=QTimer();timer.setInterval(30)
    def drag():
        ticks[0]+=1;w.details.threshold_slider.setValue(ticks[0]*5)
        if w.bundle:values.append(w.bundle.get('threshold'))
        if ticks[0]>=30:timer.stop()
    timer.timeout.connect(drag)
    with patch('core.read_image',side_effect=AssertionError('Threshold reread')),patch('core.ssim_luma',side_effect=AssertionError('Threshold SSIM')):
        timer.start();wait(lambda:not timer.isActive())
        assert len(set(values))>=5,values
        wait(lambda:w.preview_id is None and w.bundle.get('threshold')==150)
    assert w.bundle['comparisons'][1]['above']==128*105
    images=w.bundle['images']
    with patch('core.read_image',side_effect=AssertionError('Fullscreen source read')):
        full=FullscreenImages(images,0,w);full.show();app.processEvents();full.view.actual()
        keys=[p.cacheKey() for p in full.pixmaps];started=time.monotonic()
        for i in range(80):full.select(i%2);app.processEvents()
        switch_seconds=time.monotonic()-started
        assert keys==[p.cacheKey() for p in full.pixmaps]
        assert abs(full.view.transform().m11()-1)<.001
        full.grab().save(str(Path('validation')/'12_fullscreen.png'))
        QTest.keyClick(full,Qt.Key.Key_Escape);app.processEvents();assert not full.isVisible()
    history=w.toolbar_actions['最近比较历史'];assert history.menu() is None
    # Refresh an overwritten image plus an added/deleted file, keeping selected row.
    selected=w.current_entry.name
    cv2.imencode('.png',np.full((128,256,3),77,np.uint8))[1].tofile(root/'A'/selected)
    (root/'A/023.png').unlink()
    cv2.imencode('.png',np.zeros((8,8,3),np.uint8))[1].tofile(root/'A/024.png')
    w.sidebar_refresh.click();wait(lambda:w.scan_id is None and w.preview_id is None and w.bundle and w.bundle['images'][0]['raw'][0,0,0]==77)
    assert w.current_entry.name==selected and len(w.rows)==25
    wait(lambda:not w.thumb_timer.isActive() and not w.thumb_pending)
    assert len(w.thumb_completed)==48
    w.sidebar_controller.reveal();w.grab().save(str(Path('validation')/'13_live_sidebar.png'))
    result={'ok':True,'threshold_updates_during_drag':len(set(values)),'background_thumbnails':48,'fullscreen_80_switch_seconds':round(switch_seconds,4),'refresh_preserves_selection':True}
    Path('validation/live_interaction_results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
    w.close();wait(lambda:not w.pool.activeThreadCount() and not w.thumb_pool.activeThreadCount())
