"""Self-contained packaged startup smoke check; invoked only with --smoke-test."""
import json,time
from pathlib import Path
from PySide6.QtCore import QTimer

def packaged_smoke(window,app,args):
    out=Path(args[args.index('--smoke-test')+1]);out.mkdir(parents=True,exist_ok=True);started=time.monotonic();window.demo()
    def check():
        if window.bundle and window.bundle['kind']=='image' and window.preview_id is None:
            window.grab().save(str(out/'packaged_window.png'))
            result={'ok':True,'rows':len(window.rows),'panes':window.active_count(),'images':sum(x is not None for x in window.bundle['images']),'errors':window.bundle['errors']}
            (out/'smoke_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');window.close();return
        if time.monotonic()-started>90:
            (out/'smoke_result.json').write_text(json.dumps({'ok':False,'reason':'timeout'}));window.close();return
        QTimer.singleShot(100,check)
    QTimer.singleShot(100,check)
