"""Read-only comparison engine. No source-file writes, no image resampling for metrics."""
from __future__ import annotations
import difflib, hashlib, os, re, threading
from itertools import zip_longest
from dataclasses import dataclass, field
from collections import OrderedDict
from pathlib import Path
import cv2
import numpy as np
from color_space import project,difference

cv2.setNumThreads(1)
IMAGE_EXTS = {'.png','.jpg','.jpeg','.bmp','.tif','.tiff','.webp','.gif'}
DOC_EXTS = {'.docx','.pdf','.xlsx','.xlsm'}
MAX_CHARS = 800_000
MAX_LINES = 12000

class Cancelled(Exception): pass

class ImageCache:
    """Bounded decoded-image cache; validate file metadata on worker threads."""
    def __init__(self,limit=192*1024*1024):
        self.limit=limit;self.items=OrderedDict();self.bytes=0;self.lock=threading.Lock()
    def key(self,path,storage,standard):
        stat=os.stat(path)
        return (os.path.normcase(os.path.abspath(path)),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,storage,standard)
    def get(self,key):
        with self.lock:
            value=self.items.get(key)
            if value:self.items.move_to_end(key);return value[0]
    def put(self,key,item):
        size=sum(a.nbytes for a in {id(item[k]):item[k] for k in ('raw','display')}.values())
        if size>self.limit:return
        with self.lock:
            old=self.items.pop(key,None)
            if old:self.bytes-=old[1]
            self.items[key]=(item,size);self.bytes+=size
            while self.bytes>self.limit:
                _,(_,cost)=self.items.popitem(last=False);self.bytes-=cost
    def clear(self):
        with self.lock:self.items.clear();self.bytes=0
def checkpoint(cancel):
    if cancel and cancel.is_set(): raise Cancelled()

def natural_key(s):
    return tuple((1,int(p)) if p.isdigit() else (0,p.casefold()) for p in re.split(r'(\d+)',s))

@dataclass
class Entry:
    name: str
    paths: list[str | None]
    sizes: list[int | None]
    status: str
    errors: list[str] = field(default_factory=list)
    pairing: str = ''

def digest(path, cancel=None):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while b:=f.read(1024*1024):
            checkpoint(cancel); h.update(b)
    return h.hexdigest()

def scan_folders(roots, recursive=True, exact=False, cancel=None, progress=None, *, pairing='name'):
    """Match relative paths, or pair equal positions in independently sorted folders."""
    if pairing not in ('auto','name','name_order','time_order'):
        raise ValueError(f'未知的文件夹配对方式：{pairing}')
    inventories=[]; errors=[]
    for slot,root in enumerate(roots):
        if not Path(root).is_dir(): raise ValueError(f'不是可访问的文件夹：{root}')
        inventory={}; stack=[Path(root)]
        while stack:
            checkpoint(cancel); folder=stack.pop()
            try:
                with os.scandir(folder) as entries:
                    for e in entries:
                        checkpoint(cancel)
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if recursive: stack.append(Path(e.path))
                            elif e.is_file():
                                rel=Path(e.path).relative_to(root).as_posix()
                                stat=e.stat()
                                inventory[rel]=(e.path,stat.st_size,stat.st_mtime_ns)
                        except OSError as exc: errors.append(f'{e.path}: {exc}')
            except OSError as exc: errors.append(f'{folder}: {exc}')
            if progress: progress(f'扫描 {chr(65+slot)} · 已发现 {len(inventory):,} 个文件')
        inventories.append(inventory)
    names=set().union(*inventories)
    if pairing=='auto':
        # A shared relative path is evidence of a name-based correspondence.
        # Keep explicit missing rows in partial matches rather than shifting them.
        nonempty=[inventory for inventory in inventories if inventory]
        shared=any(a.keys() & b.keys() for i,a in enumerate(nonempty) for b in nonempty[i+1:])
        pairing='name' if len(nonempty)<2 or shared else 'name_order'
    if pairing=='name':
        ordered=sorted(names,key=lambda name:(natural_key(name),name))
        groups=((name,[d.get(name) for d in inventories]) for name in ordered)
        count=len(ordered)
    else:
        def order_key(item):
            name,metadata=item
            return ((metadata[2],) if pairing=='time_order' else ())+(natural_key(name.rsplit('/',1)[-1]),natural_key(name),name)
        ordered=[sorted(inventory.items(),key=order_key) for inventory in inventories]
        count=max(map(len,ordered),default=0)
        groups=(
            (' ↔ '.join(dict.fromkeys(entry[0] for entry in group if entry)),
             [entry[1] if entry else None for entry in group])
            for group in zip_longest(*ordered)
        )
    rows=[]
    for idx,(name,found) in enumerate(groups):
        checkpoint(cancel)
        paths=[x[0] if x else None for x in found];sizes=[x[1] if x else None for x in found]
        status='单源浏览' if len(paths)==1 else '缺少文件' if None in paths else ('大小不同' if len(set(sizes))>1 else '待校验')
        row=Entry(name,paths,sizes,status,pairing=pairing)
        if exact and len(paths)>1 and None not in paths:
            try: row.status='字节相同' if len({digest(p,cancel) for p in paths})==1 else '内容不同'
            except OSError as exc: row.status='读取失败';row.errors.append(str(exc))
        rows.append(row)
        if progress and idx%40==0: progress(f'整理 {idx+1:,} / {count:,}'+(' · SHA-256 精确校验' if exact and len(paths)>1 else ''))
    return rows,errors

def file_entry(paths):
    sizes=[]
    for p in paths:
        if not Path(p).is_file(): raise ValueError(f'文件不存在：{p}')
        sizes.append(Path(p).stat().st_size)
    return Entry(' ↔ '.join(Path(p).name for p in paths),list(paths),sizes,'待校验')

def read_image(path, cancel=None):
    checkpoint(cancel)
    if Path(path).suffix.lower()=='.gif':
        # Qt supports GIF first frame without an additional dependency.
        from PySide6.QtGui import QImage
        q=QImage(path).convertToFormat(QImage.Format.Format_RGBA8888)
        if q.isNull(): raise ValueError('GIF 解码失败')
        raw=np.frombuffer(q.constBits(),np.uint8).reshape(q.height(),q.bytesPerLine())[:,:q.width()*4].reshape(q.height(),q.width(),4).copy()
    else:
        a=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_UNCHANGED)
        if a is None: raise ValueError('不支持或已损坏的图片')
        if a.dtype not in (np.dtype('uint8'),np.dtype('uint16')): raise ValueError('目前支持 8bit / 16bit 整数图片')
        if a.ndim==2: raw=np.repeat(a[:,:,None],3,axis=2)
        elif a.shape[2]==3: raw=cv2.cvtColor(a,cv2.COLOR_BGR2RGB)
        elif a.shape[2]==4: raw=cv2.cvtColor(a,cv2.COLOR_BGRA2RGBA)
        else: raise ValueError('不支持的通道数')
    checkpoint(cancel)
    return raw

def divisor(raw, storage='auto'):
    if raw.dtype==np.uint8: return 255.0
    return 65472.0 if storage=='left10' else 65535.0

def display_rgb(raw, storage='auto'):
    if raw.dtype==np.uint8:return raw
    scale=255.0/divisor(raw,storage)
    return np.clip(np.rint(raw.astype(np.float32)*scale),0,255).astype(np.uint8)

def histogram(raw, standard='BT.709', storage='auto', cancel=None):
    coeff={'BT.709':(.2126,.7152,.0722),'BT.2020':(.2627,.678,.0593),'BT.601':(.299,.587,.114)}[standard]
    result={k:np.zeros(256,np.int64) for k in ['R','G','B','Y','H','S','V','Cb','Cr']}
    for y in range(0,len(raw),128):
        checkpoint(cancel)
        rgb=np.clip(raw[y:y+128,:,:3].astype(np.float32)/divisor(raw,storage),0,1)
        for i,k in enumerate('RGB'): result[k]+=np.bincount(np.minimum((rgb[:,:,i]*255).astype(np.int32),255).ravel(),minlength=256)
        luma=rgb@np.array(coeff,np.float32)
        result['Y']+=np.bincount(np.minimum((luma*255).astype(np.int32),255).ravel(),minlength=256)
        yuv=project(rgb,'YUV',standard)
        for i,k in [(1,'Cb'),(2,'Cr')]:result[k]+=np.bincount(np.clip((yuv[:,:,i]*255).astype(np.int32),0,255).ravel(),minlength=256)
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);hsv[:,:,0]/=360
        for i,k in enumerate('HSV'): result[k]+=np.bincount(np.clip((hsv[:,:,i]*255).astype(np.int32),0,255).ravel(),minlength=256)
    return result

def ssim_luma(base,other,standard='BT.709',storage='auto',cancel=None,channel=None):
    """Mean SSIM over valid Gaussian windows (11x11, sigma 1.5), population covariance.

    Nonlinear RGB luma, data_range=1, K1=.01/K2=.03. Uses row tiles with halos so
    4K/16-bit inputs retain native resolution without huge full-frame float arrays.
    """
    h,w=base.shape[:2];window=min(11,h,w);window-=1-window%2;r=window//2
    coeff=np.array({'BT.709':(.2126,.7152,.0722),'BT.2020':(.2627,.678,.0593),'BT.601':(.299,.587,.114)}[standard],np.float64)
    total=0.;count=0
    for y in range(r,h-r,128):
        checkpoint(cancel);end=min(h-r,y+128)
        def project(raw):
            if isinstance(channel,int):return raw[y-r:end+r,:,channel].astype(np.float64)/divisor(raw,storage)
            rgb=raw[y-r:end+r,:,:3].astype(np.float64)/divisor(raw,storage)
            if channel=='V':return rgb.max(axis=2)
            return rgb@coeff
        a,b=project(base),project(other)
        blur=lambda x:cv2.GaussianBlur(x,(window,window),1.5)
        ma,mb=blur(a),blur(b);va=np.maximum(blur(a*a)-ma*ma,0);vb=np.maximum(blur(b*b)-mb*mb,0);cov=blur(a*b)-ma*mb
        score=((2*ma*mb+.01**2)*(2*cov+.03**2))/((ma*ma+mb*mb+.01**2)*(va+vb+.03**2))
        valid=score[r:r+end-y,r:w-r];total+=float(valid.sum(dtype=np.float64));count+=valid.size
    return float(np.clip(total/max(1,count),-1,1))

def compare_images(base, other, threshold=0, units=255, storage='auto', alpha=True, cancel=None, standard='BT.709', space='RGB', calculate_ssim=True):
    if base.shape[:2]!=other.shape[:2]: return {'compatible':False,'reason':'尺寸不同：不拉伸、不进行像素差异计算'}
    h,w=base.shape[:2];heat=np.zeros((h,w,3),np.uint8);magnitude=np.zeros((h,w),np.float32 if space=='RGB' else np.float64)
    changed=above=0;absolute_sum=squared_sum=0.;maximum=0.;has_alpha=alpha and (base.shape[2]==4 or other.shape[2]==4)
    channel_count=(1 if space=='Y' else 3)+int(has_alpha);pixel_equal=True
    for y in range(0,h,128):
        checkpoint(cancel)
        arrays=[];native=[]
        for a in [base,other]:
            b=a[y:y+128].astype(np.float32 if space=='RGB' else np.float64)/divisor(a,storage)
            if has_alpha and b.shape[2]==3:b=np.concatenate([b,np.ones((*b.shape[:2],1),b.dtype)],axis=2)
            native.append(b[:,:,:4 if has_alpha else 3]);arrays.append(project(b[:,:,:3],space,standard))
        delta=difference(arrays[0],arrays[1],space)
        if has_alpha:delta=np.concatenate((delta,np.abs(native[0][:,:,3:4]-native[1][:,:,3:4])),axis=2)
        pixel_equal=pixel_equal and bool(np.all(np.abs(native[0]-native[1])<=1e-8))
        mx=delta.max(2)
        # Tolerance is maximum per-channel absolute error, not an average across RGB.
        any_change=mx>1e-8;large=mx>(threshold/units+1e-8)
        changed+=int(any_change.sum());above+=int(large.sum())
        magnitude[y:y+len(mx)]=mx
        section=heat[y:y+len(mx)];section[any_change]=(47,135,255);section[large]=(255,67,82)
        absolute_sum+=float(delta.sum(dtype=np.float64));squared_sum+=float(np.square(delta).sum(dtype=np.float64));maximum=max(maximum,float(mx.max()))
    count=h*w*channel_count;mse=squared_sum/count
    return {'compatible':True,'heat':heat,'magnitude':magnitude,'changed':changed,'above':above,'total':h*w,
            'mae':absolute_sum/count*units,'max':maximum*units,'psnr':float('inf') if mse==0 else float(-10*np.log10(mse)),
            'ssim':ssim_luma(base,other,standard,storage,cancel) if calculate_ssim else None,'metric_channels':channel_count,
            'equal':pixel_equal,'within':above==0,'units':units,'difference_space':space,'difference_basis':('Y′' if space=='Y' else space)+('+A' if has_alpha else '')}

def rethreshold_bundle(bundle,threshold,units,cancel=None):
    """Reclassify cached native differences without decoding or recomputing metrics."""
    output=dict(bundle);comparisons=[]
    for original in bundle['comparisons']:
        checkpoint(cancel)
        if not original or not original.get('compatible'):comparisons.append(original);continue
        result=dict(original);mx=result['magnitude'];large=mx>(threshold/units+1e-8)
        labels=(mx>1e-8).astype(np.uint8);labels[large]=2
        lut=np.zeros((256,1,3),np.uint8);lut[:3,0]=[(0,0,0),(47,135,255),(255,67,82)]
        heat=cv2.applyColorMap(labels,lut)
        scale=units/result['units'];above=cv2.countNonZero(large.view(np.uint8))
        result.update(heat=heat,above=above,within=above==0,units=units,mae=result['mae']*scale,max=result['max']*scale)
        if 'selected' in result:
            result['selected']=dict(result['selected']);result['selected']['mae']*=scale;result['selected']['max']*=scale
        comparisons.append(result)
    output.update(comparisons=comparisons,threshold=threshold)
    return output


def image_bundle(paths, baseline, threshold, units, standard, storage, alpha, cancel=None, existing=None, metric_mode=None, ready=None, previous_bundle=None, cache=None, cached_only=False, compute_comparisons=True, compute_histograms=True, image_ready=None):
    images=[];errors=[]
    for i,p in enumerate(paths):
        checkpoint(cancel)
        if p is None:
            images.append(None);errors.append('此文件夹缺少该文件')
            if image_ready:image_ready(i,None,errors[-1])
            continue
        try:
            previous=existing[i] if existing and existing[i] and existing[i]['path']==p else None
            key=cache.key(p,storage,standard) if cache else None
            if cache and previous and (previous.get('cache_key') or ())[:4]!=key[:4]:previous=None
            if previous is None and cache:previous=cache.get(key)
            if cached_only and previous is None:raise ValueError('此图片尚未载入')
            raw=previous['raw'] if previous else read_image(p,cancel)
            display=previous['display'] if previous and previous.get('storage')==storage else display_rgb(raw,storage)
            hist=previous['hist'] if previous and previous.get('storage')==storage and previous.get('standard')==standard else None
            cache_key=key if cache else previous.get('cache_key') if previous else None
            images.append({'raw':raw,'display':display,'hist':hist,'path':p,'storage':storage,'standard':standard,'cache_key':cache_key})
            errors.append('')
        except Cancelled: raise
        except Exception as exc: images.append(None);errors.append(str(exc))
        if image_ready:
            checkpoint(cancel)
            image_ready(i,dict(images[-1]) if images[-1] else None,errors[-1])
    if ready:
        ready({'kind':'image','images':[dict(a) if a else None for a in images],'errors':errors,'comparisons':[None]*len(images),'baseline':baseline,'metric_mode':metric_mode,'pending':True})
    for a in images:
        if a and a['hist'] is None and compute_histograms:a['hist']=histogram(a['raw'],standard,storage,cancel)
        if a and cache:cache.put(a['cache_key'],a)
    if not compute_comparisons:
        return {'kind':'image','images':images,'errors':errors,'comparisons':[None]*len(images),'baseline':baseline,'metric_mode':metric_mode,'threshold':threshold,'dirty_comparisons':True,'parameters':(standard,storage,alpha,metric_mode)}
    comparisons=[]
    for i,a in enumerate(images):
        if i==baseline or not a or not images[baseline]: comparisons.append(None)
        else:
            previous=previous_bundle
            if (previous and previous.get('parameters')==(standard,storage,alpha,metric_mode)
                and previous['baseline']==baseline and len(previous['images'])==len(images)
                and previous['images'][i] and previous['images'][baseline]
                and previous['images'][i]['raw'] is a['raw']
                and previous['images'][baseline]['raw'] is images[baseline]['raw']
                and previous['comparisons'][i] and previous['comparisons'][i].get('compatible')):
                result=dict(previous['comparisons'][i]);mx=result['magnitude'];large=mx>(threshold/units+1e-8)
                heat=np.zeros((*mx.shape,3),np.uint8);heat[mx>1e-8]=(47,135,255);heat[large]=(255,67,82)
                scale=units/result['units'];result.update(heat=heat,above=int(large.sum()),within=not large.any(),units=units,mae=result['mae']*scale,max=result['max']*scale)
                if 'selected' in result:
                    result['selected']=dict(result['selected']);result['selected']['mae']*=scale;result['selected']['max']*=scale
                comparisons.append(result);continue
            result=compare_images(images[baseline]['raw'],a['raw'],threshold,units,storage,alpha,cancel,standard,space=metric_mode or 'RGB',calculate_ssim=metric_mode not in ('RGB','HSV'))
            if metric_mode and result['compatible']:
                from metrics import selected_metrics
                result['selected']=selected_metrics(images[baseline]['raw'],a['raw'],metric_mode,units,storage,standard,cancel,result['ssim'])
                result['ssim']=result['selected']['ssim'];result['ssim_basis']=result['selected']['ssim_basis']
            comparisons.append(result)
    return {'kind':'image','images':images,'errors':errors,'comparisons':comparisons,'baseline':baseline,'metric_mode':metric_mode,'threshold':threshold,'parameters':(standard,storage,alpha,metric_mode)}

def decode_text(data):
    if data.startswith((b'\xff\xfe',b'\xfe\xff')): return data.decode('utf-16'),'UTF-16'
    if data.startswith(b'\xef\xbb\xbf'): return data.decode('utf-8-sig'),'UTF-8 BOM'
    if b'\0' in data[:4096]: raise ValueError('二进制文件')
    for enc in ['utf-8','gb18030']:
        try: return data.decode(enc),enc.upper()
        except UnicodeDecodeError: pass
    raise ValueError('无法识别文本编码')

def extract_text(path,cancel=None):
    ext=Path(path).suffix.lower();note='';truncated=False
    if ext in {'.doc','.xls','.ppt','.pptx'}: raise ValueError('此格式暂不支持；请另存为 DOCX / XLSX / PDF 或纯文本')
    if ext=='.docx':
        from docx import Document
        from docx.text.paragraph import Paragraph
        from docx.table import Table
        d=Document(path);parts=[];length=0
        for element in d.element.body:
            checkpoint(cancel)
            if element.tag.endswith('}p'): text=Paragraph(element,d).text
            elif element.tag.endswith('}tbl'): text='\n'.join('\t'.join(c.text for c in row.cells) for row in Table(element,d).rows)
            else: continue
            parts.append(text);length+=len(text)
            if length>MAX_CHARS: truncated=True;break
        text='\n'.join(parts);note='DOCX 正文与表格文本；不比较排版、图片、页眉页脚或批注'
    elif ext=='.pdf':
        from pypdf import PdfReader
        d=PdfReader(path)
        if d.is_encrypted and not d.decrypt(''): raise ValueError('加密 PDF 需要先解密')
        parts=[];length=0
        for i,page in enumerate(d.pages):
            checkpoint(cancel)
            if i>=200: truncated=True;break
            t=page.extract_text() or '';parts.append(f'── 第 {i+1} 页 ──\n{t}');length+=len(t)
            if length>MAX_CHARS: truncated=True;break
        if length==0: raise ValueError('PDF 没有可提取文字；扫描件需先 OCR，本版本不执行 OCR')
        text='\n'.join(parts);note='PDF 提取文字；不比较页面版式、图像或字体'
    elif ext in {'.xlsx','.xlsm'}:
        import openpyxl
        d=openpyxl.load_workbook(path,read_only=True,data_only=False);parts=[];length=0
        try:
            for sheet in d:
                parts.append(f'── 工作表 {sheet.title} ──')
                for i,row in enumerate(sheet.iter_rows(values_only=True),1):
                    checkpoint(cancel)
                    t=f'{i}\t'+'\t'.join('' if v is None else str(v) for v in row);parts.append(t);length+=len(t)
                    if length>MAX_CHARS or len(parts)>MAX_LINES: truncated=True;break
                if truncated: break
        finally: d.close()
        text='\n'.join(parts);note='XLSX 单元格值与公式；不比较样式、图表或宏'
    else:
        with open(path,'rb') as f: data=f.read(4*MAX_CHARS+1)
        truncated=len(data)>4*MAX_CHARS
        try: text,enc=decode_text(data[:4*MAX_CHARS]);note=enc+' · 忽略换行符编码差异'
        except (ValueError,UnicodeDecodeError):
            data=data[:65536];text='\n'.join(f'{i:08X}  '+data[i:i+16].hex(' ').upper() for i in range(0,len(data),16));note='二进制十六进制预览（最多 64 KiB，非文档内容解析）';truncated=Path(path).stat().st_size>65536
    if len(text)>MAX_CHARS: text=text[:MAX_CHARS];truncated=True
    lines=text.replace('\r\n','\n').replace('\r','\n').split('\n')
    if len(lines)>MAX_LINES: lines=lines[:MAX_LINES];truncated=True
    if truncated: note+=' · 已截断，不能据此判定完整文件相同'
    return {'lines':lines,'note':note,'truncated':truncated}

def align_texts(texts,baseline=0,ignore_space=False):
    """One shared row axis across 2–4 files; insertion slots precede baseline lines."""
    base=texts[baseline]['lines'] if texts[baseline] else []
    norm=lambda s:s.strip() if ignore_space else s
    maps=[];inserts=[]
    for item in texts:
        if item is None: maps.append({});inserts.append({});continue
        other=item['lines'];mapping={};insertion={}
        matcher=difflib.SequenceMatcher(None,[norm(s) for s in base],[norm(s) for s in other],autojunk=True)
        for tag,a,b,c,d in matcher.get_opcodes():
            if tag=='equal':
                for j,k in zip(range(a,b),range(c,d)):mapping[j]=(other[k],k+1,'same')
            elif tag=='replace':
                for offset,j in enumerate(range(a,b)):
                    mapping[j]=(other[c+offset],c+offset+1,'changed') if c+offset<d else ('',None,'missing')
                if d-c>b-a: insertion[b]=[(other[k],k+1,'added') for k in range(c+b-a,d)]
            elif tag=='delete':
                for j in range(a,b):mapping[j]=('',None,'missing')
            else: insertion[a]=[(other[k],k+1,'added') for k in range(c,d)]
        maps.append(mapping);inserts.append(insertion)
    columns=[[] for _ in texts];diff_rows=[]
    def append(cells):
        valid=[norm(c[0]) if c[1] is not None else None for c in cells]
        different=len(set(valid))>1
        if different: diff_rows.append(len(columns[0]))
        for i,c in enumerate(cells): columns[i].append((c[0],c[1],('changed' if i==baseline else c[2]) if different else 'same'))
    for pos in range(len(base)+1):
        n=max((len(x.get(pos,[])) for x in inserts),default=0)
        for j in range(n): append([ins[pos][j] if j<len(ins.get(pos,[])) else ('',None,'missing') for ins in inserts])
        if pos<len(base):append([m.get(pos,('',None,'missing')) for m in maps])
    return columns,diff_rows

def text_bundle(paths,baseline=0,ignore_space=False,cancel=None):
    texts=[];errors=[]
    for p in paths:
        checkpoint(cancel)
        if not p: texts.append(None);errors.append('此文件夹缺少该文件');continue
        try: texts.append(extract_text(p,cancel));errors.append('')
        except Cancelled:raise
        except Exception as exc:texts.append(None);errors.append(str(exc))
    checkpoint(cancel);columns,diff_rows=align_texts(texts,baseline,ignore_space)
    return {'kind':'text','texts':texts,'errors':errors,'columns':columns,'diff_rows':diff_rows}
