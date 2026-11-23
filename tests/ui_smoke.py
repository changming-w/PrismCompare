import os,sys,time,json,tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPointF,QEvent
from app import Window,setup_fonts
from widgets import STYLE
from demo import create_demo

app=QApplication([]);setup_fonts(app);app.setStyle('Fusion');app.setStyleSheet(STYLE)
out=Path(__file__).resolve().parents[1]/'validation';out.mkdir(exist_ok=True)
def wait(predicate,timeout=30):
    start=time.monotonic()
    while not predicate():
        if time.monotonic()-start>timeout:
            print('STATE',w.scan_id,w.preview_id,list(w.jobs),w.pool.activeThreadCount(),w.debounce.isActive(),w.current_entry.name if w.current_entry else None,flush=True)
            raise AssertionError('UI wait timeout')
        app.processEvents();time.sleep(.01)
    for _ in range(8):app.processEvents();time.sleep(.01)

with tempfile.TemporaryDirectory() as t:
    os.environ['PRISM_CONFIG_DIR']=str(Path(t)/'config')
    root=create_demo(Path(t)/'demo');w=Window();w.theme_combo.setCurrentText('浅色');w.resize(1700,1040);w.show();w.set_paths([str(root/c) for c in 'ABCD'],True)
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert len(w.rows)==5 and w.active_count()==4
    assert not w.show_details.isChecked() and not w.details.isVisible()
    from unittest.mock import patch
    original_raw=[item['raw'] for item in w.bundle['images']];serial=w.serial
    with patch('core.read_image',side_effect=AssertionError('Swap must not reread images')),patch('core.ImageCache.key',side_effect=AssertionError('Swap must not stat source files')):
        w.swap_sources();assert w.bundle['images'][0]['raw'] is original_raw[1] and w.serial==serial and w.preview_id is None
        w.swap_sources();assert w.bundle['images'][0]['raw'] is original_raw[0] and w.serial==serial
        w.show_details.setChecked(True);assert w.details.isVisible()
        wait(lambda:w.preview_id is None)
        assert not w.bundle.get('dirty_comparisons')
    w.show_details.setChecked(False)
    w.mode_actions[w.view_mode.currentIndex()].trigger();app.processEvents()
    assert w.show_details.isChecked() and w.details.isVisible(), 'Selected mode must reopen hidden panel'
    w.image_split.setSizes([540,330]);w.remember_detail_sizes();saved_sizes=w.image_split.sizes()
    w.show_details.setChecked(False);w.show_details.setChecked(True);app.processEvents()
    assert w.image_split.sizes()==saved_sizes, 'User splitter size must survive hide/show'
    w.show_details.setChecked(False)
    assert all(w.bundle['images'])
    w.focus_mode();app.processEvents()
    assert w.focus_active and w.isFullScreen() and w.workspace.gap==0
    assert all(not x.isVisible() for x in [w.menuBar(),w.command_toolbar,w.statusBar(),w.sources,w.controls,w.sidebar,w.details])
    assert all(p.image.presentation_only and p.image.backgroundBrush().color().name()=='#404040' for p in w.panes)
    assert w.panes[0].geometry().right()+1==w.panes[1].geometry().left()
    if w.workspace.grid:assert w.panes[0].geometry().bottom()+1==w.panes[2].geometry().top()
    w.grab().save(str(out/'14_focus_images.png'))
    focus=w.focus_controls;assert not focus.bar.isVisible()
    QTest.mouseMove(focus.edge,focus.edge.rect().center());wait(lambda:focus.bar.isVisible())
    rect=w.workspace.geometry();focus.actual.click();app.processEvents();assert abs(w.panes[0].image.transform().m11()-1)<.001
    focus.fit.click();app.processEvents();assert w.panes[0].image.fit_mode and w.workspace.geometry()==rect
    w.grab().save(str(out/'15_focus_zoom.png'))
    QTest.mouseMove(w.panes[0].image.viewport(),w.panes[0].image.viewport().rect().center());wait(lambda:not focus.bar.isVisible())
    QTest.keyClick(w,Qt.Key.Key_Escape);app.processEvents()
    assert not w.focus_active and w.command_toolbar.isVisible() and w.workspace.gap==5

    saved_paths=[e.text() for e in w.path_edits];saved_threshold=w.threshold.value();height_before=w.image_split.height()
    w.settings_toggle.click();app.processEvents()
    assert all(not widget.isVisible() for widget in [w.sources,w.controls])
    assert w.image_split.height()>height_before and [e.text() for e in w.path_edits]==saved_paths and w.threshold.value()==saved_threshold
    w.settings_toggle.click();app.processEvents();assert w.sources.isVisible() and w.controls.isVisible()
    controller=w.sidebar_controller
    assert not controller.pinned and not w.sidebar.isVisible()
    width_before=w.image_split.width()
    QTest.mouseMove(controller.handle,controller.handle.rect().center())
    wait(lambda:w.sidebar.isVisible())
    assert w.image_split.width()==width_before
    w.grab().save(str(out/'08_sidebar_hover.png'))
    QTest.mouseMove(w.panes[-1].image.viewport(),w.panes[-1].image.viewport().rect().center())
    wait(lambda:not w.sidebar.isVisible())
    controller.reveal();controller.pin.setChecked(True);app.processEvents()
    assert w.sidebar.isVisible() and w.sidebar.parentWidget() is w.split
    assert str(w.settings.value('sidebar_pinned')).lower()=='true'
    w.grab().save(str(out/'09_sidebar_pinned.png'))
    controller.pin.setChecked(False)
    QTest.mouseMove(w.panes[-1].image.viewport(),w.panes[-1].image.viewport().rect().center())
    wait(lambda:not w.sidebar.isVisible())
    assert all(not a.icon().isNull() and a.toolTip() for a in w.command_toolbar.actions() if not a.isSeparator() and a.text())
    assert all(len(a.text())==2 for a in w.command_toolbar.actions() if not a.isSeparator() and a.text())
    w.mode_actions[1].trigger();assert w.view_mode.currentIndex()==1 and w.mode_actions[1].isChecked()
    assert 0 not in w.mode_actions and '打开会话' not in w.toolbar_actions
    assert w.mix.isHidden() and w.gain.isHidden()
    w.mode_actions[3].trigger();assert not w.mix.isHidden() and '混合比例' in w.mix_label.text()
    w.mode_actions[4].trigger();assert not w.mix.isHidden() and '分割位置' in w.mix_label.text()
    w.mode_actions[2].trigger();assert w.mix.isHidden() and not w.gain.isHidden()
    w.mode_actions[1].trigger()
    print('four images loaded',flush=True)
    w.grab().save(str(out/'01_four_images.png'))
    app.processEvents()
    viewport_sizes=[p.image.viewport().size() for p in w.panes]
    assert all(p.hist.view is p.image and p.hist.width()==180 for p in w.panes)
    fixed=[p.hist.viewport_rect() for p in w.panes]
    w.detail_zoom(50);w.detail_zoom(100);w.panes[0].image.centerOn(120,90);w.panes[0].image.notify();app.processEvents()
    assert [p.hist.viewport_rect() for p in w.panes]==fixed
    w.grab().save(str(out/'06_histogram_zoom_pan.png'))
    w.fit_all();app.processEvents();w.grab().save(str(out/'07_histogram_fit.png'))
    w.hist_mode.setCurrentText('关闭');app.processEvents()
    assert all(not p.hist.isVisible() for p in w.panes)
    assert viewport_sizes==[p.image.viewport().size() for p in w.panes]
    w.hist_mode.setCurrentText('Y');assert all(p.hist.mode=='Y' for p in w.panes)
    assert all(p.hist.isVisible() for p in w.panes)
    w.hist_mode.setCurrentText('HSV');w.log_hist.setChecked(True)
    w.view_mode.setCurrentIndex(1);w.threshold.setValue(8)
    wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    print('threshold updated',flush=True)
    assert any(r and r.get('above',0)>0 for r in w.bundle['comparisons'])
    w.grab().save(str(out/'02_difference_histograms.png'))
    w.units.setCurrentIndex(1);w.storage.setCurrentIndex(1);w.threshold.setValue(1)
    wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert all(r is None or r.get('units')==1023 for r in w.bundle['comparisons'])
    # True one-to-one pixel zoom plus synchronized navigation.
    w.actual_all();assert all(abs(p.image.transform().m11()-1)<1e-6 for p in w.panes)
    w.fit_all();w.navigate(1)
    wait(lambda:w.current_entry and w.current_entry.name=='02_identical.png' and w.preview_id is None)
    assert all(r is None or r['equal'] for r in w.bundle['comparisons'])
    original_rows=w.rows;original_entry=w.current_entry;original_paths=list(w.current_entry.paths)
    from unittest.mock import patch
    with patch('core.read_image',side_effect=AssertionError('swap must not read images')),patch('app.scan_folders',side_effect=AssertionError('swap must not rescan folders')):
        w.swap_button.click()
        wait(lambda:w.bundle and w.current_entry and w.current_entry.name=='02_identical.png' and w.preview_id is None)
    assert w.rows is original_rows and w.current_entry is original_entry and w.current_entry.paths==original_paths
    w.navigate(1)
    wait(lambda:w.current_entry and w.current_entry.name=='03_missing_in_C.png' and w.preview_id is None)
    assert w.bundle['images'][2] is None
    w.baseline.setCurrentIndex(2);wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert all(r is None for r in w.bundle['comparisons'])
    w.baseline.setCurrentIndex(0)
    code_row=next(i for i in range(w.proxy.rowCount()) if 'normalize.py' in w.proxy.index(i,0).data())
    w.table.selectRow(code_row)
    wait(lambda:w.bundle and w.bundle['kind']=='text' and w.current_entry.name.endswith('normalize.py') and w.preview_id is None)
    assert w.bundle['diff_rows'];w.jump_diff(1);w.grab().save(str(out/'03_code_compare.png'))
    assert len({len(c) for c in w.bundle['columns']})==1
    # Rapid changes must leave the latest selection, not a stale background result.
    w.table.selectRow(0)
    for _ in range(15):app.processEvents();time.sleep(.01)
    w.table.selectRow(w.proxy.rowCount()-1)
    wait(lambda:w.current_entry and w.current_entry.name=='notes.txt' and w.bundle and w.bundle['kind']=='text' and w.preview_id is None)
    w.count.setCurrentText('3');w.set_paths([str(root/c/'01_color_study.png') for c in 'ABC'],False)
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert len(w.bundle['images'])==3
    before=[e.text() for e in w.path_edits[:3]];w.details.target.setCurrentIndex(1);w.swap_button.click()
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert [e.text() for e in w.path_edits[:3]]==before
    assert w.display_paths==[before[2],before[1],before[0]]
    w.count.setCurrentText('2');w.set_paths([str(root/c/'01_color_study.png') for c in 'AB'],False)
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert len(w.bundle['images'])==2
    from widgets import qimage
    assert w.controls.layout().count()==1
    for mode in (1,2,3,4):
        w.view_mode.setCurrentIndex(mode)
        original=qimage(w.bundle['images'][1]['display'])
        assert w.panes[1].image.item.pixmap().toImage().convertToFormat(original.format())==original
        assert w.details.mode==mode and w.details.isVisible()
    w.view_mode.setCurrentIndex(1)
    menu=w.image_context_menu(0);actions={a.text():a for a in menu.actions() if not a.isSeparator()}
    raw=w.bundle['images'][0]['raw'];metrics_before=w.bundle['comparisons'][1]['ssim']
    actions['顺时针旋转 90°'].trigger();assert w.panes[0].image.item.rotation()==90
    rotated=w.panes[0].image;point=rotated.mapFromScene(rotated.item.mapToScene(QPointF(300.5,200.5)))
    QTest.mouseMove(rotated.viewport(),point);app.processEvents()
    assert abs(w.details.xy[0]-300)<=1 and abs(w.details.xy[1]-200)<=1
    assert w.bundle['images'][0]['raw'] is raw and w.bundle['comparisons'][1]['ssim']==metrics_before
    actions['逆时针旋转 90°'].trigger();assert rotated.item.rotation()==0
    actions['水平缩放（适应宽度）'].trigger()
    assert abs(rotated.item.sceneBoundingRect().width()*rotated.transform().m11()-(rotated.viewport().width()-4))<1e-6
    with patch('app.subprocess.Popen') as launch:
        actions['在文件夹中定位'].trigger();assert launch.call_args.args[0][-1]==os.path.normpath(w.bundle['images'][0]['path'])
    actions['适应窗口'].trigger();menu.deleteLater()
    base_view=w.panes[0].image;target_view=w.panes[1].image
    target_view.set_image(w.bundle['images'][1]['display'][::2,::2]);base_view.set_zoom(60)
    w.align_to_baseline()
    assert abs(base_view.item.sceneBoundingRect().width()*base_view.transform().m11()-target_view.item.sceneBoundingRect().width()*target_view.transform().m11())<1e-6
    assert w.bundle['images'][0]['raw'] is raw and w.bundle['comparisons'][1]['ssim']==metrics_before
    w.render_images();other_menu=w.image_context_menu(1)
    next(a for a in other_menu.actions() if a.text()=='设为基准').trigger()
    wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert w.bundle['baseline']==1
    w.baseline.setCurrentIndex(0);wait(lambda:not w.debounce.isActive() and w.preview_id is None);other_menu.deleteLater()
    assert w.details.isVisible() and w.details.view.isVisible()
    assert w.panes[0].image.viewport().cursor().shape()==Qt.CursorShape.CrossCursor
    view=w.panes[0].image;point=view.mapFromScene(QPointF(300.5,200.5));QTest.mouseMove(view.viewport(),point)
    app.processEvents();x,y=w.details.xy
    assert abs(x-300)<=1 and abs(y-200)<=1
    assert all(p.image.cursor_pixel==(x,y) for p in w.panes[:2])
    expected=','.join(str(int(v)) for v in w.bundle['images'][0]['raw'][y,x,:3])
    assert expected in w.details.readouts[0].text() and 'PSNR' in w.details.metrics.text()
    w.details.threshold.setValue(3)
    wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert w.threshold.value()==3 and w.details.threshold_slider.value()==3
    w.details.zoom.setValue(0);w.detail_zoom(100)
    assert all(abs(p.image.transform().m11()-1)<1e-6 for p in w.panes[:2])
    w.fit_all();w.show_details.setChecked(False);assert not w.details.isVisible()
    w.show_details.setChecked(True);assert w.details.isVisible()
    w.view_mode.setCurrentIndex(4);w.mix.setValue(70);w.hist_mode.setCurrentText('RGB');w.grab().save(str(out/'04_two_images_wipe.png'))
    from widgets import qimage
    assert w.panes[1].image.item.pixmap().toImage().convertToFormat(qimage(w.bundle['images'][1]['display']).format())==qimage(w.bundle['images'][1]['display'])
    assert w.details.view.wipe_fraction==.7
    wipe=w.details.view;bounds=wipe.item.boundingRect();start=wipe.mapFromScene(QPointF(bounds.width()*.7,bounds.height()/2));end=wipe.mapFromScene(QPointF(bounds.width()*.3,bounds.height()/2))
    QTest.mousePress(wipe.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start)
    QTest.mouseMove(wipe.viewport(),end);QTest.mouseRelease(wipe.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end);app.processEvents()
    assert abs(w.mix.value()-30)<=1 and abs(w.details.view.wipe_fraction-.3)<.02
    w.grab().save(str(out/'10_split_dragged.png'))
    w.view_mode.setCurrentIndex(3);assert '混合' in w.details.caption.text() and w.details.view.wipe_fraction is None
    assert w.panes[1].image.item.pixmap().toImage().convertToFormat(qimage(w.bundle['images'][1]['display']).format())==qimage(w.bundle['images'][1]['display'])
    w.view_mode.setCurrentIndex(1);w.pixel_values(300,200);w.grab().save(str(out/'05_bottom_inspector.png'))
    wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    before=[e.text() for e in w.path_edits[:2]];raw_before=w.bundle['images'][1]['raw'];serial_before=w.serial
    w.swap_button.click()
    assert w.bundle['images'][0]['raw'] is raw_before and w.serial==serial_before
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert [e.text() for e in w.path_edits[:2]]==before
    assert w.display_paths==list(reversed(before))
    assert w.bundle['images'][0]['path']==before[1]
    assert '纯图片专注模式' in w.toolbar_actions
    w.details.actual_button.click();app.processEvents();assert abs(w.details.view.transform().m11()-1)<.001
    w.details.fit_button.click();app.processEvents();assert w.details.view.fit_mode
    w.details.set_pixel(-1,-1);assert all(not label.text() for label in w.details.readouts)
    w.pixel_values(100,100);app.processEvents();assert all(g.isVisible() for g in w.details.grids)
    geometry=w.details.metrics.geometry();w.panes[0].image.leaveEvent(QEvent(QEvent.Type.Leave));app.processEvents()
    assert all(g.isHidden() for g in w.details.grids) and all(t.isHidden() for t in w.details.pixel_titles)
    assert w.details.metrics.geometry()==geometry
    w.focus_mode();app.processEvents();w.focus_controls.reveal();assert w.focus_controls.swap.isVisible()
    saved=[i['raw'] for i in w.bundle['images']];serial=w.serial
    w.focus_controls.swap.click();assert w.bundle['images'][0]['raw'] is saved[1] and w.serial==serial
    w.focus_controls.swap.click();w.escape_action();app.processEvents()
    assert w.table.isColumnHidden(0)
    assert all(p.title.isHidden() and p.meta.isHidden() and p.image.info_title and p.image.info_meta for p in w.panes[:2])
    assert not w.toolbar_actions['停止'].isEnabled()
    assert w.history and w.history[0]['paths']==before
    from PySide6.QtWidgets import QMenu
    menu=QMenu();w.populate_history(menu);assert len(menu.actions())>=3
    w.hist_mode.setCurrentText('HSV');wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert w.bundle['comparisons'][1]['selected']['mode']=='HSV' and 'SSIM(V)' in w.details.metrics.text()
    w.hist_mode.setCurrentText('YUV');wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    assert w.bundle['comparisons'][1]['difference_space']=='YUV' and 'YUV' in w.details.caption.text()
    assert w.details.metrics.rowCount()==7
    w.hist_mode.setCurrentText('HSV');wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    w.units.setCurrentIndex(1);w.threshold.setValue(21);wait(lambda:not w.debounce.isActive() and w.preview_id is None)
    w.save_preferences();w.settings.sync()
    other=Window();assert other.units.currentIndex()==1 and other.threshold.value()==21 and other.hist_mode.currentText()=='HSV' and other.history
    other.close()
    w.open_history(w.history[0]);wait(lambda:w.bundle and w.preview_id is None and w.scan_id is None)
    assert w.display_paths==before
    w.grab().save(str(out/'11_compact_history.png'))
    (out/'ui_results.json').write_text(json.dumps({'ok':True,'checks':['hover sidebar and pin persistence','two-character vector icon toolbar','rotation preserves raw pixels and metrics','rotated pixel coordinates','fit width and Explorer command','4 folder thumbnails','crosshair and native pixel grids','bottom difference and metrics','inspector threshold and zoom','swap two and three sources','swap folders preserves selected relative path','overlay histogram show/hide without layout change','Y/RGB/HSV histograms','threshold red/blue','10bit storage','pixel zoom','missing source/baseline','4-way aligned text','latest selection wins','3-way files','2-way files','wipe']},indent=2))
    w.close();wait(lambda:not w.pool.activeThreadCount() and not w.thumb_pool.activeThreadCount())
print('UI SMOKE PASSED',flush=True)
