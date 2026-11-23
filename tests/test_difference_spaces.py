import sys,unittest
from pathlib import Path
import numpy as np,cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import compare_images,rethreshold_bundle
from metrics import selected_metrics

class DifferenceSpaces(unittest.TestCase):
    def test_equal_luma_is_not_equal_rgb(self):
        a=np.zeros((12,12,3),np.uint16);b=a.copy();a[:,:,0]=114*64;b[:,:,2]=299*64
        rgb=compare_images(a,b,threshold=.1,units=1023,standard='BT.601')
        y=compare_images(a,b,threshold=.1,units=1023,standard='BT.601',space='Y')
        yuv=compare_images(a,b,threshold=.1,units=1023,standard='BT.601',space='YUV')
        self.assertEqual(rgb['above'],144);self.assertEqual(y['above'],0);self.assertEqual(yuv['above'],144)
        self.assertFalse(y['equal']);self.assertFalse(y['heat'].any())
        metric=selected_metrics(a,b,'YUV',1023,'auto','BT.601')
        self.assertAlmostEqual(metric['max'],yuv['max'],places=6)
    def test_hue_wrap_changes_classification(self):
        hsv=np.ones((12,12,3),np.float32);hsv[:,:,0]=359
        a=np.rint(cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)*65535).astype(np.uint16)
        hsv[:,:,0]=1;b=np.rint(cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)*65535).astype(np.uint16)
        rgb=compare_images(a,b,threshold=2,space='RGB');hsv=compare_images(a,b,threshold=2,space='HSV')
        self.assertEqual(rgb['above'],144);self.assertEqual(hsv['above'],0)
        np.testing.assert_array_equal(hsv['heat'][0,0],[47,135,255])
        changed=rethreshold_bundle({'comparisons':[None,hsv]},1,255)['comparisons'][1]
        self.assertEqual(changed['above'],144);np.testing.assert_array_equal(changed['heat'][0,0],[255,67,82])
    def test_alpha_applies_to_each_space(self):
        a=np.full((12,12,4),255,np.uint8);b=a.copy();b[:,:,3]=0
        for space in ['RGB','Y','YUV','HSV']:
            on=compare_images(a,b,space=space);off=compare_images(a,b,space=space,alpha=False)
            self.assertEqual(on['above'],144);self.assertEqual(off['above'],0)
            self.assertTrue(on['difference_basis'].endswith('+A'))

if __name__=='__main__':unittest.main()
