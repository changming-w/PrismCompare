"""Histogram-dependent metrics on native-resolution, normalized stored samples."""
import numpy as np
import cv2
from core import divisor,checkpoint,ssim_luma
from color_space import project,difference

def selected_metrics(base,other,mode,units,storage,standard,cancel=None,luma_ssim=None):
    coeff=np.array({'BT.709':(.2126,.7152,.0722),'BT.2020':(.2627,.678,.0593),'BT.601':(.299,.587,.114)}[standard],np.float64)
    absolute=squared=maximum=0.;count=0;hue_sum=0.;hue_count=0;sv_sum=np.zeros(2)
    for y in range(0,len(base),128):
        checkpoint(cancel);values=[]
        for raw in (base,other):
            rgb=raw[y:y+128,:,:3].astype(np.float64)/divisor(raw,storage)
            values.append(project(rgb,mode,standard))
        delta=np.abs(values[0]-values[1])
        if mode=='HSV':
            hue=np.minimum(delta[:,:,0],1-delta[:,:,0]);valid=(values[0][:,:,1]>1e-5)&(values[1][:,:,1]>1e-5)&(values[0][:,:,2]>1e-5)&(values[1][:,:,2]>1e-5)
            delta[:,:,0]=np.where(valid,hue,0);hue_sum+=float(hue[valid].sum())*360;hue_count+=int(valid.sum());sv_sum+=delta[:,:,1:].sum(axis=(0,1))
        absolute+=float(delta.sum());squared+=float((delta*delta).sum());maximum=max(maximum,float(delta.max()));count+=delta.size
    mse=squared/count
    if mode=='RGB':score=float(np.mean([ssim_luma(base,other,standard,storage,cancel,channel=i) for i in range(3)]));ssim_basis='RGB'
    elif mode in ('Y','YUV'):score=luma_ssim if luma_ssim is not None else ssim_luma(base,other,standard,storage,cancel);ssim_basis='Y′'
    else:score=ssim_luma(base,other,standard,storage,cancel,channel='V');ssim_basis='V'
    return {'mode':mode,'basis':'Y′' if mode=='Y' else mode,'psnr':float('inf') if mse==0 else float(-10*np.log10(mse)),
            'mae':absolute/count*units,'max':maximum*units,'ssim':score,'ssim_basis':ssim_basis,
            'hue_mae_degrees':hue_sum/hue_count if hue_count else None,'sv_mae_percent':(sv_sum/(base.shape[0]*base.shape[1])*100).tolist()}
