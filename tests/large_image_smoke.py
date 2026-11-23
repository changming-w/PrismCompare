"""Synthetic 4K/16-bit validation. No user images or shared folders are read."""
import sys,json,time,tempfile,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np,cv2
from core import image_bundle

out=Path(__file__).resolve().parents[1]/'validation';out.mkdir(exist_ok=True)
start=time.monotonic()
with tempfile.TemporaryDirectory() as t:
    root=Path(t);x=np.arange(3840,dtype=np.uint16)%1024
    a=np.empty((2160,3840,3),np.uint16)
    for c in range(3):a[:,:,c]=np.broadcast_to(((x+c*100)%1024)<<6,(2160,3840))
    paths=[]
    for i in range(4):
        b=a.copy()
        if i:b[100:110,200:210,0]+=64*i
        p=root/f'{i}.png';cv2.imencode('.png',b)[1].tofile(p);paths.append(str(p))
    del a,b
    stage_times=[];load_started=time.monotonic()
    b=image_bundle(paths,0,1,1023,'BT.2020','left10',True,metric_mode='RGB',ready=lambda _:stage_times.append(time.monotonic()-load_started))
    full_time=time.monotonic()-load_started
    refresh_started=time.monotonic()
    refreshed=image_bundle(paths,0,3,1023,'BT.2020','left10',True,metric_mode='RGB',existing=b['images'],previous_bundle=b)
    refresh_time=time.monotonic()-refresh_started
    assert all(r['above']==0 for r in refreshed['comparisons'][1:])
    assert not any(b['errors'])
    for im in b['images']:
        assert im['raw'].dtype==np.uint16 and im['raw'].shape==(2160,3840,3)
        assert all(int(v.sum())==3840*2160 for v in im['hist'].values())
    for i,r in enumerate(b['comparisons'][1:],1):
        assert r['changed']==100 and r['above']==(0 if i==1 else 100)
        assert abs(r['max']-i)<.001
    results={'first_preview_seconds':round(stage_times[0],3),'full_rgb_metrics_seconds':round(full_time,3),'threshold_refresh_seconds':round(refresh_time,3),'ok':True,'images':4,'resolution':[3840,2160],'dtype':'uint16','storage':'10bit<<6','elapsed_seconds':round(time.monotonic()-start,3),
             'comparisons':[{k:v for k,v in r.items() if k not in ['heat','magnitude']} for r in b['comparisons'][1:]]}
    (out/'large_image_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results),flush=True)
