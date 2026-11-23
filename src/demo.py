from pathlib import Path
import cv2,numpy as np

def create_demo(root):
    root=Path(root)
    for letter in 'ABCD':(root/letter/'code').mkdir(parents=True,exist_ok=True)
    w,h=960,540;y,x=np.mgrid[:h,:w];base=np.zeros((h,w,3),np.uint16)
    base[:,:,0]=np.clip(9000+x*37+y*8,0,65535);base[:,:,1]=np.clip(5000+x*18+y*40,0,65535);base[:,:,2]=np.clip(16000+x*10+y*23,0,65535)
    cv2.rectangle(base,(105,100),(405,390),(54000,31000,15000),-1);cv2.circle(base,(640,250),130,(9000,47000,58000),-1)
    mask=np.zeros((h,w),np.uint8);cv2.putText(mask,'PRISM / 16-BIT',(65,480),cv2.FONT_HERSHEY_SIMPLEX,1.8,255,3,cv2.LINE_AA);base[mask>0]=(61000,62000,64000)
    for i,letter in enumerate('ABCD'):
        a=base.copy()
        if i:
            a[160:300,160:350]=np.clip(a[160:300,160:350].astype(np.int32)+i*1800,0,65535).astype(np.uint16)
            cv2.circle(a,(640+i*8,250),35,(58000,11000+i*3000,18000),-1)
            a[15:80,700:900]=np.clip(a[15:80,700:900].astype(np.int32)+64*i,0,65535).astype(np.uint16)
        p=root/letter
        cv2.imencode('.png',a)[1].tofile(p/'01_color_study.png')
        cv2.imencode('.png',(base>>8).astype(np.uint8))[1].tofile(p/'02_identical.png')
        if i!=2:cv2.imencode('.png',(a>>8).astype(np.uint8))[1].tofile(p/'03_missing_in_C.png')
        text='import numpy as np\n\ndef normalize(image):\n    """Preserve the source precision."""\n    scale = '+('255.0' if i==0 else '1023.0' if i==1 else '65535.0')+'\n'
        if i in (1,3):text+='    image = image.astype(np.float32)\n'
        text+='    return image / scale\n\nthreshold = '+str(i*2)+'\n'
        (p/'code'/'normalize.py').write_text(text,encoding='utf-8')
        (p/'notes.txt').write_text('Prism Compare 示例\n\n支持 2–4 路对比\n'+('原始配置\n' if i==0 else '更新后的配置\n')+'只读来源文件\n',encoding='utf-8')
    return root
