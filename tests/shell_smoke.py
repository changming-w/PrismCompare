"""Exercise real cross-process Explorer handoff and accumulation."""
import os,sys,tempfile,time,subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
os.environ['QT_QPA_PLATFORM']='offscreen'
with tempfile.TemporaryDirectory(prefix='prism-shell-') as tmp:
    os.environ['PRISM_SHELL_ID']=tmp;os.environ['PRISM_CONFIG_DIR']=tmp
    from PySide6.QtWidgets import QApplication
    from app import Window,setup_fonts
    from shell_bridge import ShellBridge,attach_shell
    from demo import create_demo
    app=QApplication([]);setup_fonts(app);window=Window();window.show()
    bridge=ShellBridge();assert bridge.start([]);attach_shell(window,bridge,[])
    demo=Path(tmp)/'demo';create_demo(demo)
    exe=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'dist/PrismCompare/PrismCompare.exe'
    def pump(predicate,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents();time.sleep(.01)
            if predicate():return
        raise AssertionError('IPC/UI timeout')
    def send(paths):
        children=[subprocess.Popen([str(exe),'--shell',str(p)],creationflags=subprocess.CREATE_NO_WINDOW) for p in paths]
        pump(lambda:all(p.poll() is not None for p in children))
        assert all(p.returncode==0 for p in children)
    send([demo/'A/01_color_study.png']);pump(lambda:bool(window.path_edits[0].text()))
    assert not window.path_edits[1].text()
    send([demo/f'{letter}/01_color_study.png' for letter in 'BCD'])
    pump(lambda:window.bundle is not None and window.active_count()==4 and window.preview_id is None)
    assert len(window.bundle['images'])==4
    send([demo/'A',demo/'B'])
    pump(lambda:window.mode.currentIndex()==0 and window.active_count()==2 and len(window.rows)==5 and window.preview_id is None)
    window.grab().save(str(ROOT/'validation/shell_window.png'))
    result={'ok':True,'checks':['single file waits for partner','three concurrent packaged clients append to existing window','four image comparison','two folder comparison']}
    (ROOT/'validation/shell_results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result));window.close();pump(lambda:not window.isVisible())
