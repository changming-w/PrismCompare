import os,sys,time,json,tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from PySide6.QtWidgets import QApplication,QToolButton
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent,QMimeData,QUrl,QSize
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from widgets import PANE_MIME,WORKSPACE_BACKGROUND,WORKSPACE_DIVIDER
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
    w.show_details.setChecked(True)
    w.fit_all()
    for slot in (2,3):
        view=w.panes[slot].image
        point=view.mapFromScene(QPointF(300.5,200.5))
        QTest.mouseMove(view.viewport(),point)
        wait(lambda:w.details.target.currentData()==slot)
        assert all(grid.isVisible() for grid in w.details.grids)
        assert '对比' in w.details.pixel_titles[slot].text()
        assert f'A ↔ {chr(65+slot)}' in w.details.caption.text()
    class PaneDrop(QDropEvent):
        def source(self):return w.panes[2].image
    mime=QMimeData();mime.setData(PANE_MIME,b'1')
    # Deliver over the actual graphics viewport, not the main window.
    viewport=w.panes[3].image.viewport()
    before=list(w.bundle['comparisons']);serial=w.serial
    event=PaneDrop(QPointF(viewport.rect().center()),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    with patch('core.read_image',side_effect=AssertionError('reorder must not decode')):
        sources=[edit.text() for edit in w.path_edits]
        assert w.eventFilter(viewport,event) and event.isAccepted()
        assert w.bundle['images'][3]['raw'] is original_raw[2]
        assert w.bundle['comparisons'][3] is before[2] and w.serial==serial
        assert [edit.text() for edit in w.path_edits]==[sources[0],sources[1],sources[3],sources[2]]
        assert Path(w.rows[1].paths[3]).parent==Path(sources[2])
        w.swap_image_slots(2,3)
    w.grab().save(str(out/'16_four_pixel_cards.png'))
    dock=w.detail_dock
    panel=w.details
    w.remember_detail_sizes();docked_sizes=w.image_split.sizes()
    serial=w.serial
    separator=dock.separator
    assert separator.height()<=8 and not dock.button.isVisible()
    grip=dock.title
    # The right-hand blank end of the result title is part of the drag area.
    grab_point=QPoint(grip.width()-24,grip.height()//2)
    QTest.mousePress(grip,Qt.MouseButton.LeftButton,pos=grab_point)
    drag_position=grip.mapToGlobal(grab_point-QPoint(0,130))
    QTest.mouseMove(grip,grip.mapFromGlobal(drag_position))
    assert dock.floating and dock.window.isVisible(), 'The window must appear before mouse release'
    first_position=dock.window.pos()
    drag_position+=QPoint(70,-30)
    QTest.mouseMove(grip,grip.mapFromGlobal(drag_position))
    assert dock.window.pos()==first_position+QPoint(70,-30), 'The floating window must follow the mouse'
    QTest.mouseRelease(grip,Qt.MouseButton.LeftButton,pos=grip.mapFromGlobal(drag_position))
    app.processEvents()
    assert dock.floating and dock.window.isVisible() and panel.isVisible()
    assert w.image_split.count()==1 and panel.parentWidget() is dock.window
    assert w.serial==serial and panel.bundle is w.bundle
    original_workspace=w.workspace.geometry()
    old_size=dock.window.size();old_preview=panel.view.viewport().size()
    dock.window.resize(old_size+QSize(120,70));app.processEvents()
    assert panel.view.viewport().width()>old_preview.width() and panel.view.viewport().height()>old_preview.height()
    assert w.workspace.geometry()==original_workspace
    dock.window.showMaximized();app.processEvents();assert dock.window.isMaximized()
    dock.window.showNormal();app.processEvents()
    dock.window.grab().save(str(out/'18_floating_comparison.png'))
    w.show_details.setChecked(False);assert not dock.window.isVisible() and dock.floating
    w.show_details.setChecked(True);assert dock.window.isVisible()
    w.focus_mode();app.processEvents();assert not dock.window.isVisible()
    w.focus_mode();app.processEvents();assert dock.window.isVisible()
    # A drop near the bottom of this comparison window redocks the same panel.
    bottom=w.image_split.mapToGlobal(QPoint(40,w.image_split.height()-20))
    QTest.mousePress(grip,Qt.MouseButton.LeftButton,pos=QPoint(30,8))
    QTest.mouseMove(grip,grip.mapFromGlobal(bottom))
    QTest.mouseRelease(grip,Qt.MouseButton.LeftButton,pos=grip.mapFromGlobal(bottom))
    app.processEvents()
    assert not dock.floating and panel.parentWidget() is w.image_split
    assert w.image_split.sizes()==docked_sizes
    QTest.mouseDClick(dock.separator,Qt.MouseButton.LeftButton);assert dock.floating
    dock.window.close();assert not dock.floating and not dock.window.isVisible()
    old_size=w.size()
    w.resize(w.minimumSize());app.processEvents()
    for theme,tag in [('深色','dark'),('浅色','light')]:
        w.theme_combo.setCurrentText(theme)
        bar=w.menuBar();menu_action=bar.actions()[1]
        QTest.mouseClick(bar,Qt.MouseButton.LeftButton,pos=bar.actionGeometry(menu_action).center());app.processEvents()
        assert menu_action.menu().isVisible()
        bar.grab().save(str(out/f'19_{tag}_menu_bar.png'))
        menu_action.menu().grab().save(str(out/f'20_{tag}_menu.png'))
        menu_action.menu().hide()
        assert w.command_toolbar.widgetForAction(w.toolbar_actions['纯图片专注模式']).isVisible()
        assert dock.separator.isVisible() and dock.separator.height()<=8
        assert not panel.metrics.showGrid() and not panel.metrics.alternatingRowColors()
        assert panel.view.backgroundBrush().color().name()==WORKSPACE_BACKGROUND
        assert all(pane.image.backgroundBrush().color().name()==WORKSPACE_BACKGROUND for pane in w.panes)
        assert w.panes[1].x()-w.panes[0].geometry().right()==2
        handle=w.image_split.handle(1).grab().toImage()
        assert handle.pixelColor(10,(handle.height()-1)//2).name()==WORKSPACE_DIVIDER
        assert handle.pixelColor(10,0).name()==WORKSPACE_BACKGROUND
        w.grab().save(str(out/f'21_{tag}_separator.png'))
        scroll=panel.control_scroll
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        table_bottom=panel.metrics.mapTo(scroll.viewport(),panel.metrics.rect().bottomLeft()).y()
        assert table_bottom<scroll.viewport().height(), (tag,table_bottom,scroll.viewport().height(),scroll.widget().height(),scroll.verticalScrollBar().maximum(),scroll.verticalScrollBar().value())
        scroll.verticalScrollBar().setValue(0)
    w.resize(old_size);app.processEvents()
    w.theme_combo.setCurrentText('浅色')
    w.show_details.setChecked(False)
    w.focus_mode();app.processEvents()
    assert w.focus_active and w.isFullScreen() and w.workspace.gap==0
    assert all(not x.isVisible() for x in [w.menuBar(),w.command_toolbar,w.statusBar(),w.sources,w.controls,w.sidebar,w.details])
    assert all(p.image.presentation_only and p.image.backgroundBrush().color().name()=='#404040' for p in w.panes)
    assert w.panes[0].geometry().right()+1==w.panes[1].geometry().left()
    if w.workspace.grid:assert w.panes[0].geometry().bottom()+1==w.panes[2].geometry().top()
    w.grab().save(str(out/'14_focus_images.png'))
    focus=w.focus_controls;assert not focus.bar.isVisible()
    center=w.panes[0].image.viewport()
    QTest.mouseMove(center,center.rect().center());app.processEvents()
    QTest.mouseMove(focus.edge,focus.edge.rect().center());wait(lambda:focus.bar.isVisible())
    rect=w.workspace.geometry();focus.actual.click();app.processEvents();assert abs(w.panes[0].image.transform().m11()-1)<.001
    focus.fit.click();app.processEvents();assert w.panes[0].image.fit_mode and w.workspace.geometry()==rect
    w.grab().save(str(out/'15_focus_zoom.png'))
    QTest.mouseMove(w.panes[0].image.viewport(),w.panes[0].image.viewport().rect().center());wait(lambda:not focus.bar.isVisible())
    QTest.keyClick(w,Qt.Key.Key_Escape);app.processEvents()
    assert not w.focus_active and w.command_toolbar.isVisible() and w.workspace.gap==w.workspace.DIVIDER_WIDTH

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
    original_rows=w.rows;original_entry=w.current_entry
    original_columns=[edit.text() for edit in w.path_edits]
    original_paths=[list(row.paths) for row in w.rows]
    left=w.baseline.currentIndex();right=w.details.target.currentData()
    order=list(range(w.active_count()));order[left],order[right]=order[right],order[left]
    from unittest.mock import patch
    with patch('core.read_image',side_effect=AssertionError('swap must not read images')),patch('app.scan_folders',side_effect=AssertionError('swap must not rescan folders')):
        w.toolbar_actions['交换图片和来源位置'].trigger()
        wait(lambda:w.bundle and w.current_entry and w.current_entry.name=='02_identical.png' and w.preview_id is None)
        assert w.rows is original_rows and w.current_entry is original_entry
        assert [edit.text() for edit in w.path_edits]==[original_columns[i] for i in order]
        assert [row.paths for row in w.rows]==[[paths[i] for i in order] for paths in original_paths]
        assert w.display_paths==w.current_entry.paths==[item['path'] for item in w.bundle['images']]
        w.swap_image_slots(left,right);wait(lambda:w.preview_id is None)
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
    assert [e.text() for e in w.path_edits[:3]]==[before[2],before[1],before[0]]
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
    w.toolbar_actions['交换图片和来源位置'].trigger()
    assert w.bundle['images'][0]['raw'] is raw_before and w.serial==serial_before
    wait(lambda:w.bundle and w.bundle['kind']=='image' and w.preview_id is None)
    assert [e.text() for e in w.path_edits[:2]]==w.display_paths==list(reversed(before))
    assert w.bundle['images'][0]['path']==before[1]
    before=list(reversed(before))
    assert '纯图片专注模式' in w.toolbar_actions
    w.details.actual_button.click();app.processEvents();assert abs(w.details.view.transform().m11()-1)<.001
    w.details.fit_button.click();app.processEvents();assert w.details.view.fit_mode
    w.details.set_pixel(-1,-1);assert all(not label.text() for label in w.details.readouts)
    w.pixel_values(100,100);app.processEvents();assert all(g.isVisible() for g in w.details.grids[:2])
    geometry=w.details.metrics.geometry();w.panes[0].image.leaveEvent(QEvent(QEvent.Type.Leave));app.processEvents()
    assert all(g.isHidden() for g in w.details.grids) and all(t.isHidden() for t in w.details.pixel_titles)
    assert w.details.metrics.geometry()==geometry
    w.focus_mode();app.processEvents();w.focus_controls.reveal();assert w.focus_controls.swap.isVisible()
    saved=[i['raw'] for i in w.bundle['images']];serial=w.serial
    w.focus_controls.swap.click();assert w.bundle['images'][0]['raw'] is saved[1] and w.serial==serial
    assert [edit.text() for edit in w.path_edits[:2]]==list(reversed(before))
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
    fresh=w.new_comparison_window()
    def drop_file(widget,path):
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(path)])
        point=widget.rect().center()
        for event in (QDragEnterEvent(point,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier),
                      QDropEvent(QPointF(point),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)):
            QApplication.sendEvent(widget,event)
            assert event.isAccepted()
    drop_file(fresh.path_edits[0],before[0])
    assert fresh.path_edits[0].text()==before[0] and fresh.bundle is None
    drop_file(fresh,f'{before[1]}')
    wait(lambda:fresh.bundle and fresh.preview_id is None)
    third=str(root/'C'/'01_color_study.png')
    drop_file(fresh.panes[0].image.viewport(),third)
    wait(lambda:fresh.bundle and len(fresh.bundle['images'])==3 and fresh.preview_id is None)
    assert fresh.display_paths==[*before,third] and w.display_paths==before
    fresh.baseline.setCurrentIndex(2)
    wait(lambda:fresh.bundle['baseline']==2 and fresh.preview_id is None)
    menu=fresh.image_context_menu(1)
    next(action for action in menu.actions() if action.text()=='移除此图片来源').trigger()
    wait(lambda:fresh.bundle and fresh.preview_id is None)
    assert fresh.display_paths==[before[0],third] and fresh.baseline.currentIndex()==1
    fresh.settings_toggle.setChecked(True)
    fresh.grab().save(str(out/'18_remove_sources.png'))
    QTest.mouseClick(fresh.source_cards[0].findChild(QToolButton,'removeSource'),Qt.MouseButton.LeftButton)
    wait(lambda:fresh.bundle and fresh.preview_id is None)
    assert fresh.active_count()==1 and fresh.display_paths==[third] and not fresh.details.isVisible()
    single_history=fresh.history[0]
    QTest.mouseClick(fresh.source_cards[0].findChild(QToolButton,'removeSource'),Qt.MouseButton.LeftButton)
    assert fresh.bundle is None and not fresh.rows and not any(edit.text() for edit in fresh.path_edits)
    assert all(Path(path).is_file() for path in [*before,third])
    fresh.open_history(single_history)
    wait(lambda:fresh.bundle and fresh.preview_id is None)
    assert fresh.active_count()==1 and fresh.display_paths==[third]
    fresh.close();wait(lambda:not fresh.pool.activeThreadCount() and not fresh.thumb_pool.activeThreadCount())
    folders=w.new_comparison_window()
    drop_file(folders,str(root/'A'))
    wait(lambda:folders.bundle and folders.preview_id is None)
    assert folders.active_count()==1 and folders.sidebar.isVisible() and len(folders.rows)==5
    assert folders.panes[0].image.isVisible() and not folders.panes[1].isVisible()
    assert folders.rows[0].status=='单源浏览' and not folders.details.isVisible()
    folders.grab().save(str(out/'17_single_folder_browse.png'))
    # Distinct filenames with identical order across the two folders.
    renamed=Path(t)/'renamed';renamed.mkdir()
    import shutil
    for index,file in enumerate(sorted((root/'A').glob('*.png'))):
        shutil.copyfile(file,renamed/f'prediction{index+1}.png')
    folders.two_image_details=False
    with patch('core.compare_images',side_effect=AssertionError('hidden panel computed comparison')):
        drop_file(folders,str(renamed))
        wait(lambda:folders.bundle and folders.preview_id is None and folders.active_count()==2)
        assert folders.rows[0].pairing=='name_order' and folders.rows[0].paths[1]
        assert folders.bundle['dirty_comparisons']
        folders.folder_pairing.setCurrentIndex(folders.folder_pairing.findData('name'))
        wait(lambda:folders.bundle and folders.preview_id is None and folders.scan_id is None)
        assert all(row.status=='缺少文件' for row in folders.rows)
        folders.folder_pairing.setCurrentIndex(folders.folder_pairing.findData('name_order'))
        wait(lambda:folders.bundle and folders.preview_id is None and folders.scan_id is None)
    with patch('core.read_image',side_effect=AssertionError('enabling bottom decoded the originals again')):
        folders.show_details.setChecked(True)
        assert folders.jobs[folders.preview_id][2]=='recompute'
        interrupted=folders.preview_id
        folders.show_details.setChecked(False)
        assert folders.preview_id is None and folders.jobs[interrupted][1].is_set()
        folders.show_details.setChecked(True)
        wait(lambda:folders.preview_id is None)
        assert folders.bundle['comparisons'][1] and folders.details.view.isVisible()
    import threading
    from core import read_image
    second_started=threading.Event();continue_second=threading.Event()
    def slow_second(path,cancel):
        if Path(path).name=='prediction2.png':
            second_started.set()
            assert continue_second.wait(10)
        return read_image(path,cancel)
    def pane_geometry():
        return tuple(widget.geometry().getRect() for widget in
            (folders,folders.workspace,folders.panes[0].image.viewport(),folders.details,folders.details.view.viewport()))
    original_geometry=pane_geometry()
    with patch('core.read_image',side_effect=slow_second):
        try:
            folders.navigate(1)
            wait(lambda:second_started.is_set() and folders.panes[0].raw is not None)
            assert folders.panes[1].raw is None
            assert pane_geometry()==original_geometry
        finally:
            continue_second.set()
        wait(lambda:folders.bundle and folders.preview_id is None)
    assert folders.bundle['comparisons'][1] and pane_geometry()==original_geometry
    remaining_path=folders.current_entry.paths[1]
    menu=folders.image_context_menu(0)
    next(action for action in menu.actions() if action.text()=='移除此文件夹来源').trigger()
    wait(lambda:folders.bundle and folders.preview_id is None)
    assert folders.active_count()==1 and folders.sidebar.isVisible()
    assert folders.path_edits[0].text()==str(renamed) and folders.display_paths==[remaining_path]
    assert (root/'A').is_dir() and not folders.details.isVisible()
    # Opening a second folder restores the saved two-pane inspector preference.
    # Its synchronous toggled signal must never start work on the old single-pane bundle.
    folders.two_image_details=True
    folders.set_paths([str(root/'A')],True)
    wait(lambda:folders.bundle and folders.preview_id is None)
    assert folders.active_count()==1 and not folders.details.isVisible()
    with patch('sys.excepthook') as unhandled:
        drop_file(folders,str(root/'B'))
        wait(lambda:folders.bundle and folders.preview_id is None and folders.active_count()==2)
        unhandled.assert_not_called()
    assert folders.details.isVisible() and folders.bundle['comparisons'][1]
    QTest.mouseDClick(folders.detail_dock.separator,Qt.MouseButton.LeftButton)
    assert folders.detail_dock.window.isVisible()
    folders.close();wait(lambda:not folders.pool.activeThreadCount() and not folders.thumb_pool.activeThreadCount())
    assert not folders.detail_dock.window.isVisible()
    (out/'ui_results.json').write_text(json.dumps({'ok':True,'checks':['hover sidebar and pin persistence','two-character vector icon toolbar','rotation preserves raw pixels and metrics','rotated pixel coordinates','fit width and Explorer command','4 folder thumbnails','crosshair and native pixel grids','bottom difference and metrics','inspector threshold and zoom','swap two and three sources','swap folders preserves selected relative path','overlay histogram show/hide without layout change','Y/RGB/HSV histograms','threshold red/blue','10bit storage','pixel zoom','missing source/baseline','4-way aligned text','latest selection wins','3-way files','2-way files','wipe']},indent=2))
    w.close();wait(lambda:not w.pool.activeThreadCount() and not w.thumb_pool.activeThreadCount())
print('UI SMOKE PASSED',flush=True)
