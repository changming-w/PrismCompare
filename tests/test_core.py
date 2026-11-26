import sys,tempfile,unittest,threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np,cv2
from core import *

class CoreTests(unittest.TestCase):
    def test_16bit_low_bits_and_tolerance(self):
        a=np.zeros((4,5,3),np.uint16);b=a.copy();b[1,2,0]=64;b[2,3,1]=128
        r=compare_images(a,b,threshold=1,units=1023,storage='left10')
        self.assertEqual(r['changed'],2);self.assertEqual(r['above'],1)
        self.assertEqual(tuple(r['heat'][1,2]),(47,135,255));self.assertEqual(tuple(r['heat'][2,3]),(255,67,82))
        self.assertAlmostEqual(r['max'],2,places=5)
    def test_alpha_and_mixed_depth(self):
        a=np.full((2,2,3),255,np.uint8);b=np.full((2,2,4),65535,np.uint16)
        self.assertTrue(compare_images(a,b)['equal']);b[0,0,3]=0
        self.assertEqual(compare_images(a,b)['above'],1);self.assertTrue(compare_images(a,b,alpha=False)['equal'])
    def test_shape_mismatch(self):self.assertFalse(compare_images(np.zeros((2,3,3),np.uint8),np.zeros((3,2,3),np.uint8))['compatible'])
    def test_psnr_and_ssim_reference(self):
        a=np.full((31,29,3),128,np.uint8);b=np.full_like(a,129)
        r=compare_images(a,b);self.assertAlmostEqual(r['psnr'],20*np.log10(255),places=4);self.assertAlmostEqual(r['mae'],1,places=4)
        x,y=128/255,129/255;expected=(2*x*y+.01**2)/(x*x+y*y+.01**2)
        self.assertAlmostEqual(r['ssim'],expected,places=8)
        self.assertAlmostEqual(ssim_luma(a,a),1,places=10)
        altered=a.copy();altered[10:20,10:20]=255;self.assertLess(ssim_luma(a,altered),1)
    def test_full_histogram_counts(self):
        a=np.zeros((5,9,3),np.uint16);a[:,:,0]=65472
        h=histogram(a,'BT.2020','left10')
        for v in h.values():self.assertEqual(int(v.sum()),45)
        self.assertEqual(h['R'][255],45);self.assertEqual(h['Y'][int(.2627*255)],45)
    def test_png_native_precision(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'中文.png';a=np.array([[[1,64,65535],[511,512,513]]],np.uint16);cv2.imencode('.png',cv2.cvtColor(a,cv2.COLOR_RGB2BGR))[1].tofile(p)
            np.testing.assert_array_equal(read_image(p),a)
    def test_folders_four_way_missing_and_exact(self):
        with tempfile.TemporaryDirectory() as t:
            roots=[]
            for i in range(4):
                p=Path(t)/str(i);p.mkdir();roots.append(str(p));(p/'same.txt').write_text('abc');(p/'different.txt').write_text('abc' if i==0 else 'xyz')
                if i!=2:(p/'missing.txt').write_text('a')
            rows,errors=scan_folders(roots,exact=False);d={r.name:r.status for r in rows};self.assertEqual(d['different.txt'],'待校验');self.assertEqual(d['missing.txt'],'缺少文件');self.assertFalse(errors)
            rows,_=scan_folders(roots,exact=True);d={r.name:r.status for r in rows};self.assertEqual(d['different.txt'],'内容不同');self.assertEqual(d['same.txt'],'字节相同')
    def test_folder_pairing_and_single_source(self):
        with tempfile.TemporaryDirectory() as t:
            a,b=[Path(t)/name for name in ('a','b')]
            for root in (a,b):root.mkdir()
            for root,name,mtime in [(a,'pred10.png',1),(a,'pred2.png',3),(a,'pred30.png',4),(b,'gt8.png',2),(b,'gt21.png',1)]:
                path=root/name;path.write_bytes(b'x');os.utime(path,(mtime,mtime))
            def names(rows):
                return [[Path(p).name if p else None for p in row.paths] for row in rows]
            browse,_=scan_folders([a],exact=True,pairing='auto')
            self.assertEqual(names(browse),[['pred2.png'],['pred10.png'],['pred30.png']])
            self.assertTrue(all(row.status=='单源浏览' for row in browse))
            def paired(mode):return scan_folders([a,b],pairing=mode)[0]
            natural=[['pred2.png','gt8.png'],['pred10.png','gt21.png'],['pred30.png',None]]
            self.assertEqual(names(paired('auto')),natural)
            self.assertEqual(names(paired('name_order')),natural)
            self.assertEqual(names(paired('time_order')),[['pred10.png','gt21.png'],['pred2.png','gt8.png'],['pred30.png',None]])
            self.assertTrue(all(row.status=='缺少文件' for row in paired('name')))
            (b/'pred2.png').write_bytes(b'x')
            self.assertEqual(names(paired('auto')),names(paired('name')))
            self.assertIn(['pred2.png','pred2.png'],names(paired('auto')))
    def test_aligned_insert_delete_four_way(self):
        original=[['a','b','c'],['insert','a','b','c','tail'],['a','c'],['a','changed','c']]
        columns,diffs=align_texts([{'lines':x} for x in original])
        self.assertEqual(len({len(c) for c in columns}),1);self.assertTrue(diffs)
        for expected,col in zip(original,columns):self.assertEqual([t for t,n,s in col if n is not None],expected)
    def test_missing_baseline(self):
        columns,diffs=align_texts([None,{'lines':['a','b']},{'lines':['b']}])
        self.assertEqual([t for t,n,_ in columns[1] if n],['a','b']);self.assertTrue(diffs)
    def test_cancel(self):
        e=threading.Event();e.set()
        with self.assertRaises(Cancelled):histogram(np.zeros((3,3,3),np.uint8),cancel=e)
    def test_docx_xlsx_and_text(self):
        from docx import Document
        import openpyxl
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);d=Document();d.add_paragraph('正文');table=d.add_table(rows=1,cols=2);table.cell(0,0).text='列一';table.cell(0,1).text='列二';d.save(p/'test.docx')
            self.assertIn('列一\t列二',extract_text(p/'test.docx')['lines'])
            w=openpyxl.Workbook();w.active['A1']='内容';w.active['B1']='=1+2';w.save(p/'test.xlsx');self.assertIn('=1+2','\n'.join(extract_text(p/'test.xlsx')['lines']))
            (p/'test.txt').write_text('中文\ntext',encoding='utf-16');self.assertIn('中文',extract_text(p/'test.txt')['lines'])
    def test_scan_error_not_silent(self):
        with self.assertRaises(ValueError):scan_folders(['Z:/__missing_prism_directory__','Z:/another_missing'])
    def test_pdf_extracted_content_and_scan_detection(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);w=PdfWriter();page=w.add_blank_page(width=300,height=300)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 250 Td (Hello Prism) Tj ET');page[NameObject('/Contents')]=w._add_object(stream)
            w.write(p/'text.pdf');self.assertIn('Hello Prism','\n'.join(extract_text(p/'text.pdf')['lines']))
            blank=PdfWriter();blank.add_blank_page(width=100,height=100);blank.write(p/'blank.pdf')
            with self.assertRaisesRegex(ValueError,'OCR'):extract_text(p/'blank.pdf')

if __name__=='__main__':unittest.main()
