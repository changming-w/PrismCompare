import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cv2
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import core
from metrics import selected_metrics

class PerformanceMetricsTests(unittest.TestCase):
    def test_threshold_reuses_native_results_and_histograms(self):
        a=np.full((32,32,3),100,np.uint16);b=a+64
        with tempfile.TemporaryDirectory() as t:
            paths=[str(Path(t)/f'{i}.png') for i in range(2)]
            for path,raw in zip(paths,[a,b]):cv2.imencode('.png',raw)[1].tofile(path)
            args=(paths,0,0,1023,'BT.709','left10',True)
            stages=[];cache=core.ImageCache()
            first=core.image_bundle(*args,metric_mode='Y',ready=stages.append,cache=cache)
            self.assertTrue(stages[0]['pending']);self.assertIsNone(stages[0]['images'][0]['hist'])
            with patch('core.read_image',side_effect=AssertionError('unexpected reread')),patch('core.histogram',side_effect=AssertionError('unexpected histogram')),patch('core.ssim_luma',side_effect=AssertionError('unexpected SSIM')):
                second=core.image_bundle(paths,0,2,1023,'BT.709','left10',True,existing=first['images'],previous_bundle=first,metric_mode='Y',cache=cache)
            self.assertEqual(second['comparisons'][1]['above'],0)
            self.assertEqual(first['comparisons'][1]['above'],1024)
            self.assertEqual(second['comparisons'][1]['selected'],first['comparisons'][1]['selected'])
            with patch('core.read_image',side_effect=AssertionError('cache miss')):
                core.image_bundle(*args,cache=cache)
            # A changed source must invalidate the decoded cache.
            cv2.imencode('.png',np.zeros((33,32,3),np.uint16))[1].tofile(paths[0])
            changed=core.image_bundle(*args,cache=cache)
            self.assertEqual(changed['images'][0]['raw'].shape[0],33)
    def test_metric_spaces_and_circular_hue(self):
        a=np.full((12,12,3),80,np.uint8)
        for mode in ['RGB','Y','HSV']:
            m=selected_metrics(a,a,mode,255,'auto','BT.709')
            self.assertEqual(m['mae'],0);self.assertAlmostEqual(m['ssim'],1,places=12);self.assertTrue(np.isinf(m['psnr']))
        hsv=np.ones((12,12,3),np.float32);hsv[:,:,0]=359
        a=np.rint(cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)*65535).astype(np.uint16)
        hsv[:,:,0]=1;b=np.rint(cv2.cvtColor(hsv,cv2.COLOR_HSV2RGB)*65535).astype(np.uint16)
        m=selected_metrics(a,b,'HSV',1023,'auto','BT.709')
        self.assertAlmostEqual(m['hue_mae_degrees'],2,places=2);self.assertEqual(m['ssim_basis'],'V')
    def test_cache_is_bounded(self):
        cache=core.ImageCache(limit=90);raw=np.zeros((3,3,3),np.uint8)
        for i in range(10):cache.put(i,{'raw':raw.copy(),'display':raw.copy()})
        self.assertLessEqual(cache.bytes,90);self.assertEqual(len(cache.items),1)

if __name__=='__main__':unittest.main()
