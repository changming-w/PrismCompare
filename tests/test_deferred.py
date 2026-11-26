import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np,cv2
import core

class DeferredTests(unittest.TestCase):
    def test_hidden_then_native_metrics_without_io(self):
        with tempfile.TemporaryDirectory() as t:
            paths=[]
            for i in range(4):
                a=np.full((25,31,3),100+i,np.uint8);p=Path(t)/f'{i}.png';cv2.imencode('.png',a)[1].tofile(p);paths.append(str(p))
            args=(paths,0,3,255,'BT.709','auto',True)
            with patch('core.compare_images',side_effect=AssertionError('hidden panel computed metrics')):
                hidden=core.image_bundle(*args,metric_mode='RGB',compute_comparisons=False)
            self.assertTrue(hidden['dirty_comparisons'])
            with patch('core.read_image',side_effect=AssertionError('reread')),patch('core.ssim_luma',side_effect=AssertionError('unused luma SSIM')):
                full=core.image_bundle(*args,metric_mode='RGB',existing=hidden['images'],cached_only=True)
            self.assertAlmostEqual(full['comparisons'][1]['selected']['mae'],1,places=5)
            self.assertEqual(full['comparisons'][1]['ssim_basis'],'RGB')
            self.assertGreater(full['comparisons'][1]['selected']['ssim'],.99)
    def test_change_interpretation_reuses_valid_raw(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a.png';cv2.imencode('.png',np.full((20,20,3),6400,np.uint16))[1].tofile(p)
            cache=core.ImageCache();args=([str(p),str(p)],0,3,1023)
            first=core.image_bundle(*args,'BT.709','auto',True,cache=cache,compute_comparisons=False)
            with patch('core.read_image',side_effect=AssertionError('raw pixels unnecessarily decoded')):
                second=core.image_bundle(*args,'BT.2020','left10',True,existing=first['images'],cache=cache,compute_comparisons=False)
            self.assertIs(first['images'][0]['raw'],second['images'][0]['raw'])
            self.assertEqual(second['images'][0]['storage'],'left10')
    def test_each_original_is_delivered_before_later_decodes_and_analysis(self):
        reports=[]
        def decode(path,cancel):
            if path=='b.png':self.assertEqual([event[0] for event in reports],[0])
            return np.zeros((16,16,3),np.uint8)
        with patch('core.read_image',side_effect=decode),patch('core.histogram',side_effect=AssertionError('histograms disabled')),patch('core.compare_images',side_effect=AssertionError('comparisons disabled')):
            result=core.image_bundle(['a.png','b.png'],0,0,255,'BT.709','auto',True,
                image_ready=lambda *event:reports.append(event),compute_comparisons=False,compute_histograms=False)
        self.assertEqual([item['path'] for _,item,_ in reports],['a.png','b.png'])
        self.assertTrue(result['dirty_comparisons'])

if __name__=='__main__':unittest.main()
