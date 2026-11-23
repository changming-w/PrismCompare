"""Oversized Explorer batches must not poison the next selection or reopening."""
import os,sys,time,tempfile,json
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication
from app import Window,setup_fonts
from shell_bridge import ShellBridge,attach_shell
from demo import create_demo
app=QApplication([]);setup_fonts(app)
def wait(fn):
    end=time.monotonic()+30
    while not fn():
        app.processEvents();time.sleep(.01)
        assert time.monotonic()<end,'timeout'
with tempfile.TemporaryDirectory() as temp:
    os.environ['PRISM_CONFIG_DIR']=temp;os.environ['PRISM_SHELL_ID']=temp
    root=create_demo(Path(temp)/'demo');w=Window();w.show();bridge=ShellBridge();assert bridge.start([]);attach_shell(w,bridge,[])
    paths=[str(root/x/'01_color_study.png') for x in 'ABCD']+[str(root/x/'02_identical.png') for x in 'AB']
    with patch('PySide6.QtWidgets.QMessageBox.warning') as warning:
        bridge.received.emit(paths);wait(lambda:warning.call_count==1)
        bridge.received.emit(paths[:1]);bridge.received.emit(paths[1:2])
        wait(lambda:w.bundle and w.preview_id is None)
        assert w.active_count()==2 and warning.call_count==1
        # Overflow an already populated four-source group, then replace cleanly.
        bridge.received.emit(paths[2:4]);wait(lambda:w.active_count()==4 and w.preview_id is None)
        bridge.received.emit(paths[4:]);wait(lambda:warning.call_count==2)
        bridge.received.emit(paths[:2]);wait(lambda:w.active_count()==2 and w.preview_id is None)
    # Closing must immediately release IPC even when a worker has not returned.
    with patch.object(w.pool,'activeThreadCount',return_value=1):w.close()
    assert w.closing and not bridge.server.isListening() and not w.shell_timer.isActive()
    reopened=ShellBridge();assert reopened.start([]),'Closing process retained IPC endpoint'
    bridge.received.emit(paths);assert not w.shell_timer.isActive()
    other=Window();other.show();attach_shell(other,reopened,paths[:2]);wait(lambda:other.bundle and other.preview_id is None)
    assert other.active_count()==2
    other.close();w.close();wait(lambda:not w.pool.activeThreadCount() and not other.pool.activeThreadCount() and not w.thumb_pool.activeThreadCount() and not other.thumb_pool.activeThreadCount())
    result={'ok':True,'checks':['six rejected then two accepted','overflow of existing four then new pair','IPC released before worker shutdown','old window cannot receive or reopen','new window opens two sources']}
    Path('validation/shell_recovery_results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
