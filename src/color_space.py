"""Normalized code-value spaces, shared by metrics and difference classification."""
import cv2
import numpy as np

WEIGHTS={'BT.709':(.2126,.7152,.0722),'BT.2020':(.2627,.678,.0593),'BT.601':(.299,.587,.114)}

def project(rgb,mode,standard):
    if mode=='RGB':return rgb
    if mode=='HSV':
        hsv=cv2.cvtColor(np.clip(rgb,0,1).astype(np.float32),cv2.COLOR_RGB2HSV).astype(rgb.dtype)
        hsv[:,:,0]/=360
        return hsv
    coeff=np.asarray(WEIGHTS[standard],dtype=rgb.dtype);y=rgb@coeff
    if mode=='Y':return y[:,:,None]
    if mode=='YUV':
        # Full-range Y'CbCr; chroma offset cancels when computing differences.
        cb=(rgb[:,:,2]-y)/(2*(1-coeff[2]))+.5
        cr=(rgb[:,:,0]-y)/(2*(1-coeff[0]))+.5
        return np.stack((y,cb,cr),axis=2)
    raise ValueError('Unknown comparison space: '+mode)

def difference(a,b,mode):
    delta=np.abs(a-b)
    if mode=='HSV':
        hue=np.minimum(delta[:,:,0],1-delta[:,:,0])
        valid=(a[:,:,1]>1e-5)&(b[:,:,1]>1e-5)&(a[:,:,2]>1e-5)&(b[:,:,2]>1e-5)
        delta[:,:,0]=np.where(valid,hue,0)
    return delta
