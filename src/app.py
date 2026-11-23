from __future__ import annotations
import csv,json,os,sys,threading,traceback,subprocess,tempfile,hashlib
from collections import OrderedDict
from pathlib import Path
import cv2,numpy as np
from PySide6.QtCore import Qt,QObject,Signal,QRunnable,QThreadPool,QSortFilterProxyModel,QTimer,QSettings,QUrl
from PySide6.QtGui import QPixmap,QImage,QShortcut,QKeySequence,QDesktopServices,QTextCursor,QColor,QIcon,QFontDatabase,QFont,QAction,QActionGroup
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QPushButton,QLineEdit,QComboBox,QCheckBox,QDoubleSpinBox,QSlider,QFrame,QSplitter,QTableView,QAbstractItemView,QHeaderView,QFileDialog,QMessageBox,QProgressBar,QStyleFactory,QMenu,QToolButton
from core import rethreshold_bundle,ImageCache,Entry,Cancelled,checkpoint,scan_folders,file_entry,IMAGE_EXTS,image_bundle,text_bundle,read_image,display_rgb
from widgets import SettingsToggle,ComparePane,PaneArea,FileModel,ThumbDelegate,STYLE,LIGHT_STYLE,qimage,COLORS
from details import DetailPanel

APP_VERSION='0.1.13'

def setup_fonts(app):
    # Also makes offscreen render tests use the same fonts as the native Windows UI.
    for name in ['msyh.ttc','msyhbd.ttc','segoeui.ttf','consola.ttf']:
        p=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
        if p.exists():QFontDatabase.addApplicationFont(str(p))
    app.setFont(QFont('Microsoft YaHei UI',9))

class Signals(QObject):
    done=Signal(int,object)
    failed=Signal(int,str)
    progress=Signal(int,str)
    partial=Signal(int,object)

class Task(QRunnable):
    def __init__(self,ident,fn,cancel):
        super().__init__();self.ident=ident;self.fn=fn;self.cancel=cancel;self.signals=Signals()
    def run(self):
        try:
            checkpoint(self.cancel);result=self.fn(self.cancel,lambda s:self.signals.progress.emit(self.ident,s));checkpoint(self.cancel);self.signals.done.emit(self.ident,result)
        except Cancelled:self.signals.failed.emit(self.ident,'__cancelled__')
        except Exception:self.signals.failed.emit(self.ident,traceback.format_exc())

class FilterModel(QSortFilterProxyModel):
    def __init__(self):super().__init__();self.query='';self.images=False;self.different=False
    def filterAcceptsRow(self,row,parent):
        e=self.sourceModel().rows[row]
        if self.query and self.query.casefold() not in e.name.casefold():return False
        if self.images and not any(p and Path(p).suffix.lower() in IMAGE_EXTS for p in e.paths):return False
        if self.different and e.status in ['字节相同','内容相同','像素相同']:return False
        return True

class Window(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('Prism Compare · 棱镜比对');self.resize(1560,990);self.setMinimumSize(1160,760);self.setAcceptDrops(True)
        config=Path(os.environ.get('PRISM_CONFIG_DIR',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PrismCompare')));config.mkdir(parents=True,exist_ok=True)
        self.settings=QSettings(str(config/'settings.ini'),QSettings.Format.IniFormat);self.pool=QThreadPool(self);self.pool.setMaxThreadCount(2);self.thumb_pool=QThreadPool(self);self.thumb_pool.setMaxThreadCount(2)
        self.two_image_details=str(self.settings.value('two_image_details',self.settings.value('options/show_details','true'))).lower()=='true';self.restoring_settings=True
        self.jobs={};self.serial=0;self.scan_id=None;self.preview_id=None;self.thumb_jobs={};self.thumb_cache=OrderedDict();self.thumb_pending=set();self.thumb_fail=set();self.generation=0
        self.image_cache=ImageCache();self.last_metric_mode='RGB';self.current_entry=None;self.bundle=None;self.rows=[];self.syncing=False;self.text_syncing=False;self.diff_position=-1;self.closing=False;self.scan_errors=[]
        self.thumb_directory=tempfile.TemporaryDirectory(prefix='PrismCompare-thumbs-')
        self.thumb_sources={};self.thumb_completed=set();self.thumb_paths=[];self.thumb_position=0;self.thumbs_paused=False
        self.thumb_timer=QTimer(self);self.thumb_timer.setInterval(40);self.thumb_timer.timeout.connect(self.pump_thumbnails)
        self.threshold_timer=QTimer(self);self.threshold_timer.setInterval(40);self.threshold_timer.timeout.connect(self.update_live_threshold)
        self.debounce=QTimer(self);self.debounce.setSingleShot(True);self.debounce.setInterval(240);self.debounce.timeout.connect(self.refresh_content)
        self.selection_timer=QTimer(self);self.selection_timer.setSingleShot(True);self.selection_timer.setInterval(110);self.selection_timer.timeout.connect(self.load_selected)
        self.build_ui();self.update_view_controls();self.shortcuts();self.configure_count();self.init_sidebar();self.restore_settings();self.restoring_settings=False;self.show_details.setChecked(self.two_image_details if self.active_count()==2 else False);self.build_menus();self.build_toolbar();self.apply_theme()
        QApplication.styleHints().colorSchemeChanged.connect(self.apply_theme)
    def button(self,label,callback,primary=False):
        b=QPushButton(label);b.clicked.connect(callback)
        if primary:b.setObjectName('primary')
        return b
    def combo(self,items):
        c=QComboBox();c.addItems(items);return c
    def build_ui(self):
        root=QWidget();self.setCentralWidget(root);outer=QVBoxLayout(root);outer.setContentsMargins(12,10,12,0);outer.setSpacing(7)
        self.focus_active=False;self.settings_toggle=SettingsToggle();self.settings_toggle.setText('设置');self.settings_toggle.setObjectName('settingsToggle');self.settings_toggle.setCursor(Qt.CursorShape.PointingHandCursor);self.settings_toggle.setToolTip('展开 / 收起来源与比较参数，不改变现有设置。');self.settings_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);self.settings_toggle.setCheckable(True);self.settings_toggle.setChecked(True);self.settings_toggle.setAutoRaise(True);self.settings_toggle.toggled.connect(self.toggle_settings);
        self.header=QWidget(self);self.header.hide()
        self.theme_combo=self.combo(['跟随系统','浅色','深色']);self.theme_combo.currentIndexChanged.connect(self.apply_theme)
        self.top=QWidget(self);self.top.hide();bar=QHBoxLayout(self.top);bar.setContentsMargins(0,0,0,0)
        bar.addWidget(self.button('打开文件…',self.open_files));bar.addWidget(self.button('添加文件夹…',self.add_folder))
        self.mode=self.combo(['文件夹','文件']);bar.addWidget(self.mode);bar.addWidget(QLabel('比较数量'))
        self.count=self.combo(['2','3','4']);self.count.currentIndexChanged.connect(self.configure_count);bar.addWidget(self.count)
        self.recursive=QCheckBox('包含子目录');self.recursive.setChecked(True);bar.addWidget(self.recursive)
        self.exact=QCheckBox('SHA-256 精确校验');self.exact.setToolTip('读取每个文件内容。关闭时只比较存在性与大小，大小相同显示“待校验”。网络文件夹建议先关闭。');bar.addWidget(self.exact);bar.addStretch()
        self.start=self.button('开始比对',self.compare,True);bar.addWidget(self.start);self.cancel_button=self.button('停止',self.cancel_work);self.set_busy(False);bar.addWidget(self.cancel_button)
        bar.addWidget(self.button('保存会话',self.save_session));bar.addWidget(self.button('打开会话',self.open_session));bar.addWidget(self.theme_combo)
        self.sources=QWidget();grid=QGridLayout(self.sources);grid.setContentsMargins(0,0,0,0);grid.setHorizontalSpacing(16);self.path_edits=[];self.source_cards=[]
        for i in range(4):
            card=QWidget();line=QHBoxLayout(card);line.setContentsMargins(0,0,0,0);badge=QLabel(chr(65+i));badge.setStyleSheet(f'font-weight:700;color:{COLORS[i]};');line.addWidget(badge)
            edit=QLineEdit();edit.setPlaceholderText('选择文件夹或文件，也可以粘贴完整路径');edit.returnPressed.connect(self.compare);line.addWidget(edit);self.path_edits.append(edit)
            line.addWidget(self.button('选择…',lambda _=False,j=i:self.choose_source(j)));grid.addWidget(card,i//2,i%2);self.source_cards.append(card)
        outer.addWidget(self.sources)
        self.controls=QWidget();controls=QVBoxLayout(self.controls);controls.setContentsMargins(0,0,0,0);controls.setSpacing(6)
        line=QHBoxLayout();line.setSpacing(4);line.addWidget(QLabel('基准'));self.baseline=self.combo(['A','B']);self.baseline.setFixedWidth(140);self.baseline.setToolTip('选择基准图片或基准文件夹；文件夹中的每组图片都会使用此来源作为基准。');self.baseline.currentIndexChanged.connect(self.schedule_refresh);line.addWidget(self.baseline)
        for edit in self.path_edits:edit.textChanged.connect(self.refresh_baseline_labels)
        self.view_mode=self.combo(['原图','红蓝差异','绝对差值','半透明叠加','滑动分割']);self.view_mode.currentIndexChanged.connect(self.select_result_mode);line.addWidget(self.view_mode)
        self.swap_button=self.button('左右交换',self.swap_sources);self.swap_button.setToolTip('仅交换当前打开的图片：两路交换 A/B，多路交换基准和所选图片。不修改文件夹路径，不重新扫描。');line.addWidget(self.swap_button)
        self.threshold=QDoubleSpinBox();self.threshold.setRange(0,255);self.threshold.setDecimals(3);self.threshold.setSingleStep(1);self.threshold.setMaximumWidth(90);self.threshold.valueChanged.connect(self.request_live_threshold);self.threshold.hide()
        self.units=self.combo(['8bit 码值','10bit 码值','16bit 码值']);self.units.currentIndexChanged.connect(self.units_changed);line.addWidget(self.units)
        self.storage=self.combo(['自动 8/16bit','10bit 左移6位']);self.storage.setToolTip('自动：8bit÷255，16bit÷65535。左移6位：16bit÷65472，适用于 v16=v10<<6 的 PNG。');self.storage.currentIndexChanged.connect(self.schedule_refresh);line.addWidget(self.storage)
        self.alpha=QCheckBox('Alpha');self.alpha.setToolTip('将 Alpha 通道纳入比较');self.alpha.setChecked(True);self.alpha.toggled.connect(self.schedule_refresh);line.addWidget(self.alpha)
        self.layout_mode=self.combo(['自动布局','横向并排','四宫格']);self.layout_mode.currentIndexChanged.connect(self.layout_panes)
        self.sync=QCheckBox('联动');self.sync.setToolTip('同步缩放与平移');self.sync.setChecked(True);line.addWidget(self.button('适应 F',self.fit_all));line.addWidget(self.button('100%  1',self.actual_all))
        line.addSpacing(8);self.hist_label=QLabel('通道');self.hist_label.setToolTip('直方图、指标和差异图共用的通道模式');line.addWidget(self.hist_label);self.hist_mode=self.combo(['RGB','Y','YUV','HSV','关闭']);self.hist_mode.setToolTip('直方图、指标和差异图使用同一通道模式；YUV 表示全范围 Y′CbCr，HSV 色相使用环形距离。');self.hist_mode.currentTextChanged.connect(self.hist_changed);line.addWidget(self.hist_mode)
        self.standard_label=QLabel('Y′权重');line.addWidget(self.standard_label)
        self.standard=self.combo(['BT.709','BT.2020','BT.601']);self.standard.setToolTip('用于 Y′ 直方图和 SSIM(Y′) 的 RGB 加权系数，不进行色域转换。');self.standard.currentIndexChanged.connect(self.schedule_refresh);line.addWidget(self.standard)
        self.log_hist=QCheckBox('对数');self.log_hist.setToolTip('直方图使用对数纵轴');self.log_hist.toggled.connect(self.hist_changed);line.addWidget(self.log_hist)
        self.show_details=QCheckBox('底部');self.show_details.setToolTip('显示底部对比区');self.show_details.setChecked(True);self.show_details.toggled.connect(self.details_visibility);line.addWidget(self.show_details)
        self.gain_label=QLabel('差值增益');line.addWidget(self.gain_label);self.gain=self.combo(['×1','×4','×16','×64']);self.gain.currentIndexChanged.connect(self.render_images);line.addWidget(self.gain)
        self.mix_label=QLabel('混合比例');line.addWidget(self.mix_label)
        self.mix=QSlider(Qt.Orientation.Horizontal);self.mix.setRange(0,100);self.mix.setValue(50);self.mix.setMinimumWidth(70);self.mix.setMaximumWidth(110);self.mix.valueChanged.connect(self.render_mix);line.addWidget(self.mix)
        line.addStretch();line.addWidget(self.layout_mode);line.addWidget(self.sync)
        self.ignore_space=QCheckBox('文本忽略行首尾空白');self.ignore_space.toggled.connect(self.schedule_refresh);line.addWidget(self.ignore_space)
        line.addWidget(self.button('上一处差异',lambda:self.jump_diff(-1)));line.addWidget(self.button('下一处差异 F7',lambda:self.jump_diff(1)));controls.addLayout(line);outer.addWidget(self.controls)
        for widget,width in [(self.units,90),(self.storage,112),(self.hist_mode,64),(self.standard,84),(self.layout_mode,100)]:widget.setFixedWidth(width)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.setTextVisible(False);self.progress.hide();outer.addWidget(self.progress)
        self.split=QSplitter(Qt.Orientation.Horizontal);outer.addWidget(self.split,1)
        self.sidebar=QWidget();left=QVBoxLayout(self.sidebar);left.setContentsMargins(0,0,5,0);left.setSpacing(6)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('搜索相对路径…');self.search.textChanged.connect(self.filter_changed);row.addWidget(self.search)
        self.list_style=self.combo(['缩略图','文件名']);self.list_style.currentIndexChanged.connect(self.list_style_changed);row.addWidget(self.list_style);self.sidebar_refresh=self.button('刷新',self.refresh_sources);self.sidebar_refresh.setToolTip('重新扫描来源，更新缩略图和当前图片；尽量保留当前项目');row.addWidget(self.sidebar_refresh);left.addLayout(row)
        row=QHBoxLayout();self.only_images=QCheckBox('仅图片');self.only_images.toggled.connect(self.filter_changed);row.addWidget(self.only_images);self.only_diff=QCheckBox('隐藏已确认相同');self.only_diff.toggled.connect(self.filter_changed);row.addWidget(self.only_diff);row.addStretch();left.addLayout(row)
        self.model=FileModel();self.model.thumb_provider=self.thumbnail;self.proxy=FilterModel();self.proxy.setSourceModel(self.model)
        self.table=QTableView();self.table.setModel(self.proxy);self.table.setItemDelegate(ThumbDelegate(self.table));self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.setShowGrid(False);self.table.verticalHeader().hide();self.table.setWordWrap(True);self.table.setSortingEnabled(False)
        self.table.selectionModel().currentRowChanged.connect(lambda *_:self.selection_timer.start());left.addWidget(self.table,1)
        self.counter=QLabel('尚未载入文件');left.addWidget(self.counter)
        row=QHBoxLayout();left.addLayout(row)
        self.split.addWidget(self.sidebar);self.workspace=PaneArea();self.panes=[ComparePane(i) for i in range(4)]
        self.workspace.panes=self.panes
        for p in self.panes:p.setParent(self.workspace)
        for i,p in enumerate(self.panes):
            p.image.changed.connect(lambda state,j=i:self.sync_views(j,state));p.image.pixel.connect(self.pixel_values)
            p.image.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu);p.image.customContextMenuRequested.connect(lambda pos,j=i:self.image_context_menu(j,pos))
            p.text.verticalScrollBar().valueChanged.connect(lambda v,j=i:self.sync_text(j,v))
        self.image_split=QSplitter(Qt.Orientation.Vertical);self.image_split.addWidget(self.workspace);self.details=DetailPanel();self.image_split.addWidget(self.details);self.details.hide();self.image_split.setSizes([440,330]);self.image_split.setChildrenCollapsible(False);self.saved_detail_sizes=None;self.image_split.splitterMoved.connect(self.remember_detail_sizes)
        self.details.threshold_changed.connect(self.threshold.setValue);self.threshold.valueChanged.connect(self.detail_threshold);self.units.currentIndexChanged.connect(self.detail_threshold)
        self.details.zoom_changed.connect(self.detail_zoom);self.details.fit_requested.connect(self.fit_all);self.details.actual_requested.connect(self.actual_all);self.details.pixel.connect(self.pixel_values)
        self.details.swap_requested.connect(self.swap_sources)
        self.details.view.wipe_changed.connect(lambda value:self.mix.setValue(round(value*100)))
        self.split.addWidget(self.image_split);self.split.setStretchFactor(0,0);self.split.setStretchFactor(1,1);self.split.setSizes([430,1100])
        self.statusBar().showMessage('就绪 · 拖入 2–4 个文件或文件夹 · Alt+← / → 切换项目 · Ctrl+B 隐藏列表 · F10 全屏查看')
    def init_sidebar(self):
        from sidebar import SidebarController
        self.sidebar_controller=SidebarController(self)
    def preference_widgets(self):
        return {name:getattr(self,name) for name in ['mode','count','baseline','view_mode','units','storage','hist_mode','standard','gain','layout_mode','list_style','theme_combo','recursive','exact','alpha','sync','log_hist','show_details','ignore_space','only_images','only_diff','threshold','mix']}
    def restore_settings(self):
        self.settings_toggle.setChecked(str(self.settings.value('settings_expanded','true')).lower()=='true')
        for name,widget in self.preference_widgets().items():
            legacy={'hist_mode':'hist','theme_combo':'theme'}.get(name,name)
            value=self.settings.value('options/'+name,self.settings.value(legacy))
            if value is None:continue
            if isinstance(widget,QComboBox):
                if widget.findText(str(value))>=0:widget.setCurrentText(str(value))
            elif isinstance(widget,QCheckBox):widget.setChecked(str(value).lower()=='true')
            elif isinstance(widget,QSlider):widget.setValue(int(float(value)))
            else:widget.setValue(float(value))
        self.baseline.setCurrentIndex(min(self.active_count()-1,int(self.settings.value('baseline_index',0))))
        self.last_metric_mode=str(self.settings.value('last_metric_mode','RGB'))
        if self.last_metric_mode not in ('RGB','Y','YUV','HSV'):self.last_metric_mode='RGB'
        if self.hist_mode.currentText()!='关闭':self.last_metric_mode=self.hist_mode.currentText()
        try:self.history=json.loads(str(self.settings.value('history','[]')))
        except (ValueError,TypeError):self.history=[]
        if not isinstance(self.history,list):self.history=[]
    def save_preferences(self):
        for name,widget in self.preference_widgets().items():
            value=widget.currentText() if isinstance(widget,QComboBox) else widget.isChecked() if isinstance(widget,QCheckBox) else widget.value()
            self.settings.setValue('options/'+name,value)
        self.settings.setValue('two_image_details',self.two_image_details)
        self.settings.setValue('baseline_index',self.baseline.currentIndex())
        self.settings.setValue('last_metric_mode',self.last_metric_mode);self.settings.sync()
    def record_history(self):
        paths=[e.text().strip().strip('"') for e in self.path_edits[:self.active_count()]]
        item={'paths':paths,'mode':self.mode.currentIndex(),'baseline':self.baseline.currentIndex(),'recursive':self.recursive.isChecked(),'exact':self.exact.isChecked()}
        key=lambda d:(d.get('mode'),[os.path.normcase(os.path.normpath(p)) for p in d.get('paths',[])])
        self.history=[item]+[d for d in self.history if isinstance(d,dict) and key(d)!=key(item)][:29]
        self.settings.setValue('history',json.dumps(self.history,ensure_ascii=False));self.settings.sync()
    def populate_history(self,menu):
        menu.clear();menu.setToolTipsVisible(True)
        if not self.history:menu.addAction('暂无比较历史').setEnabled(False);return
        for item in self.history:
            paths=item.get('paths',[])
            label=('文件夹' if item.get('mode')==0 else '文件')+' · '+' ↔ '.join(Path(p).name for p in paths)
            action=menu.addAction(label.replace('&','&&'));action.setToolTip('\n'.join(paths));action.triggered.connect(lambda checked=False,d=item:self.open_history(d))
        menu.addSeparator();menu.addAction('清空历史记录',self.clear_history)
    def clear_history(self):
        self.history=[];self.settings.setValue('history','[]');self.settings.sync()
    def open_history(self,item):
        paths=item.get('paths',[])
        if not 2<=len(paths)<=4:return
        # Existence checks are performed by the background scan, including UNC paths.
        self.count.setCurrentText(str(len(paths)));self.mode.setCurrentIndex(item.get('mode',0))
        for i,edit in enumerate(self.path_edits):edit.setText(paths[i] if i<len(paths) else '')
        self.baseline.setCurrentIndex(min(item.get('baseline',0),len(paths)-1));self.recursive.setChecked(item.get('recursive',True));self.exact.setChecked(item.get('exact',False));self.compare()
    def apply_theme(self,*_):
        if not hasattr(self,'model'):return
        choice=self.theme_combo.currentText();light=choice=='浅色' or (choice=='跟随系统' and QApplication.styleHints().colorScheme()!=Qt.ColorScheme.Dark)
        style=LIGHT_STYLE if light else STYLE
        asset=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets'
        check=asset/'check.png';arrow=asset/('down_light.png' if light else 'down_dark.png')
        if check.exists():style+=f'QCheckBox::indicator:checked {{ image: url("{check.as_posix()}"); }}'
        if arrow.exists():style+=f'QComboBox::drop-down {{ width: 18px; border: none; }} QComboBox::down-arrow {{ image: url("{arrow.as_posix()}"); width: 10px; height: 6px; }}'
        style+='QToolBar { spacing: 3px; padding: 4px; border-bottom: 1px solid '+('#d9dfe7' if light else '#344050')+'; } QToolBar QToolButton { padding: 2px 6px; min-width: 30px; border-radius: 2px; } QToolBar QToolButton:checked { background: '+('#cfe5fa' if light else '#355579')+'; }'
        style+='QWidget#floatingSidebar { background: '+('#f5f6f8' if light else '#1d2531')+'; border: 1px solid '+('#d4dae3' if light else '#3d4b5c')+'; } QToolButton#sidebarHandle { background: '+('#e5eff9' if light else '#30465f')+'; border: none; }'
        style+='QToolButton#settingsToggle { border: none; border-radius: 5px; background: transparent; color: '+('#526172' if light else '#c4cfdd')+'; padding: 5px 12px; min-width: 58px; font-weight: 500; } QToolButton#settingsToggle:hover { background: '+('#e4edf7' if light else '#34475d')+'; color: '+('#175b98' if light else '#e3efff')+'; } QToolButton#settingsToggle:pressed { background: '+('#d2e3f4' if light else '#405b78')+'; }'
        QApplication.instance().setStyleSheet(style);self.model.light=light
        if hasattr(self,'command_toolbar'):
            from toolbar import refresh_icons
            refresh_icons(self,light)
        for pane in self.panes:pane.set_theme(light)
        self.table.viewport().update()
    def build_toolbar(self):
        from toolbar import build_toolbar
        build_toolbar(self)
    def refresh_command_state(self):
        if not hasattr(self,'toolbar_actions'):return
        image_mode=bool(self.bundle and self.bundle['kind']=='image' and any(self.bundle['images']))
        for name in ['左右交换当前图片','自动缩放：对齐基准显示大小','适应窗口','原始像素 1:1','全屏查看当前图片组','纯图片专注模式']:
            self.toolbar_actions[name].setEnabled(image_mode)
        for action in self.mode_actions.values():action.setEnabled(image_mode)
        for name in ['上一项','下一项','上一处差异','下一处差异']:self.toolbar_actions[name].setEnabled(bool(self.rows))
    def build_menus(self):
        menus=[('文件(&F)',[('打开文件…\tCtrl+O',self.open_files),('添加文件夹…',self.add_folder),('重新比对\tCtrl+R',self.compare),('保存会话…',self.save_session),('打开会话…',self.open_session),('导出比较列表…',self.export_list),('退出',self.close)]),('视图(&V)',[('上一项\tAlt+←',lambda:self.navigate(-1)),('下一项\tAlt+→',lambda:self.navigate(1)),('适应窗口\tF',self.fit_all),('原始像素\t1',self.actual_all),('显示/隐藏文件列表\tCtrl+B',lambda:self.sidebar_controller.toggle()),('全屏查看图片\tF10',self.fullscreen_images),('专注图片\tF11',self.focus_mode)]),('比较(&C)',[('上一处差异\tShift+F7',lambda:self.jump_diff(-1)),('下一处差异\tF7',lambda:self.jump_diff(1)),('停止后台任务\tEsc',self.cancel_work)]),('帮助(&H)',[('使用说明与快捷键',self.help),('打开示例',self.demo)])]
        menu_map={}
        for title,items in menus:
            menu=self.menuBar().addMenu(title);menu_map[title]=menu
            for label,fn in items:action=QAction(label,self);action.triggered.connect(fn);menu.addAction(action)
        self.option_actions={}
        def combo_menu(parent,title,combo):
            submenu=parent.addMenu(title);group=QActionGroup(self);group.setExclusive(True);actions=[]
            for index in range(combo.count()):
                action=submenu.addAction(combo.itemText(index));action.setCheckable(True);action.setChecked(index==combo.currentIndex());group.addAction(action)
                action.triggered.connect(lambda checked=False,i=index,c=combo:c.setCurrentIndex(i));actions.append(action)
            combo.currentIndexChanged.connect(lambda index,a=actions:a[index].setChecked(True) if index>=0 else None)
            self.option_actions[title]=actions
        options=menu_map['比较(&C)'].addMenu('来源与扫描设置')
        combo_menu(options,'来源类型',self.mode);combo_menu(options,'比较数量',self.count)
        for label,checkbox in [('包含子目录',self.recursive),('SHA-256 精确校验',self.exact)]:
            action=options.addAction(label);action.setCheckable(True);action.setChecked(checkbox.isChecked());action.toggled.connect(checkbox.setChecked);checkbox.toggled.connect(action.setChecked);self.option_actions[label]=action
        combo_menu(menu_map['比较(&C)'],'Y′ / SSIM 亮度权重',self.standard)
        combo_menu(menu_map['视图(&V)'],'主题',self.theme_combo)
    def active_count(self):return int(self.count.currentText())
    def refresh_baseline_labels(self,*_):
        for i in range(self.baseline.count()):
            path=self.path_edits[i].text().strip();name=Path(path).name if path else '未选择'
            self.baseline.setItemText(i,f'{chr(65+i)} · {name}');self.baseline.setItemData(i,path,Qt.ItemDataRole.ToolTipRole)
    def configure_count(self,*_):
        if self.scan_id is not None:self.cancel_work()
        n=self.active_count();previous=self.baseline.currentIndex();self.baseline.blockSignals(True);self.baseline.clear();self.baseline.addItems([chr(65+i) for i in range(n)]);self.baseline.setCurrentIndex(min(max(previous,0),n-1));self.baseline.blockSignals(False)
        for i,w in enumerate(self.source_cards):w.setVisible(i<n)
        self.show_details.setChecked(self.two_image_details if n==2 else False)
        self.refresh_baseline_labels()
        self.layout_panes()
        self.split.setSizes([180+n*94,max(650,self.width()-180-n*94)])
        if self.rows:self.clear_results('比较数量已改变，请重新点击“开始比对”')
    def layout_panes(self,*_):
        n=self.active_count();grid=self.layout_mode.currentIndex()==2 or (self.layout_mode.currentIndex()==0 and n==4)
        self.workspace.count=n;self.workspace.grid=grid;self.workspace.arrange()
    def shortcuts(self):
        for key,fn in [('Ctrl+O',self.open_files),('Ctrl+R',self.compare),('Alt+Left',lambda:self.navigate(-1)),('Alt+Right',lambda:self.navigate(1)),('F7',lambda:self.jump_diff(1)),('Shift+F7',lambda:self.jump_diff(-1)),('Ctrl+B',lambda:self.sidebar_controller.toggle()),('F10',self.fullscreen_images),('F11',self.focus_mode),('Escape',self.escape_action)]:
            s=QShortcut(QKeySequence(key),self)
            if key in ['F','1']:
                s.activated.connect(lambda callback=fn:self.image_shortcut(callback))
            else:s.activated.connect(fn)
        for pane in self.panes:
            for key,fn in [('F',self.fit_all),('1',self.actual_all)]:
                s=QShortcut(QKeySequence(key),pane.image);s.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut);s.activated.connect(fn)
    def image_shortcut(self,fn):
        if isinstance(QApplication.focusWidget(),(QLineEdit,QDoubleSpinBox)):return
        fn()
    def escape_action(self):
        if self.focus_active:self.focus_mode()
        else:self.cancel_work()
    def focus_mode(self,*_):
        if not self.focus_active and (not self.bundle or self.bundle['kind']!='image'):return
        layout=self.centralWidget().layout()
        if not self.focus_active:
            m=layout.contentsMargins()
            self.focus_saved={'rect':self.geometry(),'maximized':self.isMaximized(),'geometry':self.saveGeometry(),'margins':(m.left(),m.top(),m.right(),m.bottom()),'spacing':layout.spacing(),'split':self.split.saveState(),'image_split':self.image_split.saveState(),'brushes':[p.image.backgroundBrush() for p in self.panes]}
            self.focus_active=True
            for widget in [self.menuBar(),self.command_toolbar,self.statusBar(),self.sources,self.controls,self.progress,self.details]:widget.hide()
            self.sidebar_controller.focus(True);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
            self.split.setHandleWidth(0);self.image_split.setHandleWidth(0);self.workspace.gap=0;self.workspace.setStyleSheet('background: #404040;')
            for pane in self.panes:
                pane.image.presentation_only=True;pane.image.setBackgroundBrush(QColor('#404040'));pane.title.hide();pane.meta.hide();pane.image.viewport().update()
            self.workspace.arrange();self.showFullScreen()
            if not hasattr(self,'focus_controls'):
                from focus_controls import FocusControls
                self.focus_controls=FocusControls(self)
            self.focus_controls.set_active(True)
        else:
            saved=self.focus_saved;self.focus_active=False;self.focus_controls.set_active(False)
            self.showNormal();self.restoreGeometry(saved['geometry'])
            if not saved['maximized']:self.setGeometry(saved['rect'])
            layout.setContentsMargins(*saved['margins']);layout.setSpacing(saved['spacing'])
            self.split.setHandleWidth(4);self.image_split.setHandleWidth(4);self.workspace.gap=5;self.workspace.setStyleSheet('')
            for pane,brush in zip(self.panes,saved['brushes']):pane.image.presentation_only=False;pane.image.setBackgroundBrush(brush);pane.image.viewport().update()
            for widget in [self.menuBar(),self.command_toolbar,self.statusBar()]:widget.show()
            self.sidebar_controller.focus(False);self.toggle_settings(self.settings_toggle.isChecked());self.details_visibility()
            self.split.restoreState(saved['split']);self.image_split.restoreState(saved['image_split']);self.workspace.arrange()
            self.progress.setVisible(self.scan_id is not None or (self.preview_id in self.jobs and self.jobs[self.preview_id][2] not in ('threshold','recompute')))
    def toggle_settings(self,expanded):
        self.settings_toggle.update()
        for widget in [self.sources,self.controls]:widget.setVisible(expanded and not self.focus_active)
        self.settings.setValue('settings_expanded',expanded)
    def choose_source(self,i):
        if self.mode.currentIndex()==0:p=QFileDialog.getExistingDirectory(self,'选择文件夹',self.path_edits[i].text())
        else:p,_=QFileDialog.getOpenFileName(self,'选择文件',self.path_edits[i].text())
        if p:self.path_edits[i].setText(p)
    def open_files(self):
        files,_=QFileDialog.getOpenFileNames(self,'选择 2–4 个文件（图片、文档、代码均可）')
        if files:self.set_paths(files,False)
    def add_folder(self):
        p=QFileDialog.getExistingDirectory(self,'添加待比较文件夹')
        if not p:return
        if self.mode.currentIndex()!=0:
            for edit in self.path_edits:edit.clear()
        self.mode.setCurrentIndex(0)
        empty=next((i for i,e in enumerate(self.path_edits) if not e.text().strip()),None)
        if empty is None:QMessageBox.information(self,'最多四个','请通过 A–D 旁的“选择”按钮替换某个文件夹。');return
        if empty>=self.active_count():self.count.setCurrentText(str(empty+1))
        self.path_edits[empty].setText(p)
        if all(e.text().strip() for e in self.path_edits[:self.active_count()]):self.compare()
    def set_paths(self,paths,folders):
        if len(paths)>4:QMessageBox.warning(self,'数量限制','一次最多比较 4 个文件或文件夹。');return
        self.mode.setCurrentIndex(0 if folders else 1);self.count.setCurrentText(str(max(2,len(paths))))
        for i,e in enumerate(self.path_edits):e.setText(str(paths[i]) if i<len(paths) else '')
        if len(paths)>=2:self.compare()
    def dragEnterEvent(self,e):
        if e.mimeData().hasUrls():e.acceptProposedAction()
    def dropEvent(self,e):
        paths=[u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths:return
        kinds=[Path(p).is_dir() for p in paths]
        if len(set(kinds))!=1:QMessageBox.warning(self,'选择类型','请全部选择文件，或全部选择文件夹。');return
        self.set_paths(paths,kinds[0])
    def submit(self,fn,kind,staged=False):
        self.serial+=1;ident=self.serial;event=threading.Event();job=Task(ident,fn,event);self.jobs[ident]=(job,event,kind)
        if staged:job.fn=lambda cancel,progress:fn(cancel,lambda result:job.signals.partial.emit(ident,result))
        job.signals.partial.connect(self.preview_ready)
        job.signals.done.connect(self.finished);job.signals.failed.connect(self.failed);job.signals.progress.connect(self.job_progress)
        if kind not in ('threshold','recompute') and not self.focus_active:self.progress.show()
        self.set_busy(True);self.pool.start(job);return ident
    def set_busy(self,busy):
        busy=busy or (not self.thumbs_paused and bool(self.thumb_pending or self.thumb_position<len(self.thumb_paths)))
        self.cancel_button.setEnabled(busy)
        if hasattr(self,'toolbar_actions'):self.toolbar_actions['停止'].setEnabled(busy)
        if not busy and hasattr(self,'table'):self.table.viewport().update()
    def preview_ready(self,ident,result):
        if ident!=self.preview_id or self.closing:return
        self.thumb_sources={item['path']:item['display'] for item in result['images'] if item}
        for i,item in enumerate(result['images']):
            if item:self.panes[i].set_image(item,self.hist_mode.currentText(),self.log_hist.isChecked())
            else:self.panes[i].message(result['errors'][i])
        self.details.metrics.setText('正在计算原分辨率比较指标…')
        self.statusBar().showMessage('图片已显示 · 正在后台计算直方图和原分辨率指标')
    def cancel_id(self,ident):
        if ident in self.jobs:self.jobs[ident][1].set()
    def cancel_work(self):
        self.debounce.stop();self.selection_timer.stop();self.threshold_timer.stop();self.thumb_timer.stop();self.thumbs_paused=True
        for job,_,_ in self.thumb_jobs.values():job.cancel.set()
        for _,event,_ in self.jobs.values():event.set()
        self.scan_id=self.preview_id=None;self.progress.hide();self.set_busy(False);self.statusBar().showMessage('已请求停止；正在进行的单次文件读取会在返回后停止。')
    def clear_results(self,message='就绪'):
        self.cancel_id(self.preview_id);self.preview_id=None;self.bundle=None;self.current_entry=None;self.rows=[];self.model.reset([],self.active_count())
        for p in self.panes:p.message(message)
        self.details.hide();self.details.bundle=None
        self.counter.setText(message);self.refresh_command_state()
    def refresh_sources(self):
        name=self.current_entry.name if self.current_entry else None
        self.compare(restore_name=name)
    def compare(self,*_,restore_name=None):
        self.restore_row_name=restore_name;self.image_cache.clear()
        paths=[e.text().strip().strip('"') for e in self.path_edits[:self.active_count()]]
        if not all(paths):QMessageBox.information(self,'选择来源','请先填写当前所有 A–D 来源；或减少比较数量。');return
        if self.active_count()>2:self.show_details.setChecked(False)
        self.cancel_work();self.clear_results('正在载入…');self.generation+=1;self.thumb_cache.clear();self.thumb_pending.clear();self.thumb_fail.clear()
        for job,_,_ in self.thumb_jobs.values():job.cancel.set()
        self.thumb_pool.clear();self.thumb_jobs.clear()
        self.thumb_sources.clear();self.thumb_completed.clear();self.thumb_paths=[];self.thumb_position=0;self.thumbs_paused=False
        recursive=self.recursive.isChecked();exact=self.exact.isChecked();folders=self.mode.currentIndex()==0
        self.scan_id=self.submit(lambda cancel,progress:scan_folders(paths,recursive,exact,cancel,progress) if folders else ([file_entry(paths)],[]),'scan')
        self.statusBar().showMessage('正在扫描文件夹…' if folders else '正在打开文件…')
    def job_progress(self,ident,message):
        if ident in (self.scan_id,self.preview_id):self.statusBar().showMessage(message)
    def finished(self,ident,result):
        task=self.jobs.pop(ident,None);kind=task[2] if task else None
        if self.closing:return
        if ident==self.scan_id:
            self.scan_id=None;self.record_history();self.rows,self.scan_errors=result;self.model.reset(self.rows,self.active_count());self.list_style_changed();self.update_counter()
            self.thumb_paths=list(dict.fromkeys(p for row in self.rows for p in row.paths if p and Path(p).suffix.lower() in IMAGE_EXTS));self.thumb_position=0;self.thumb_timer.start()
            if self.rows:
                name=getattr(self,'restore_row_name',None)
                row=next((i for i in range(self.proxy.rowCount()) if self.proxy.index(i,0).data(Qt.ItemDataRole.UserRole).name==name),0) if name else 0
                self.table.selectRow(row);self.restore_row_name=None
            else:
                for p in self.panes:p.message('没有可比较的文件')
            if self.scan_errors:self.statusBar().showMessage(f'扫描完成，但 {len(self.scan_errors)} 个路径无法读取；导出列表附带错误信息。')
            else:self.statusBar().showMessage(f'扫描完成 · {len(self.rows):,} 项 · 按相对路径配对')
        elif ident==self.preview_id:
            self.preview_id=None;self.bundle=result
            if kind=='threshold':self.details.update_threshold_result(result)
            else:self.show_bundle()
            if result['kind']=='image' and result.get('threshold')!=self.threshold.value():self.threshold_timer.start()
        self.progress.setVisible(not self.focus_active and (self.scan_id is not None or (self.preview_id in self.jobs and self.jobs[self.preview_id][2] not in ('threshold','recompute')))); self.set_busy(self.scan_id is not None or self.preview_id is not None)
    def failed(self,ident,error):
        self.jobs.pop(ident,None)
        if ident not in (self.scan_id,self.preview_id):return
        if ident==self.scan_id:self.scan_id=None
        if ident==self.preview_id:self.preview_id=None
        self.progress.hide();self.set_busy(False)
        if error!='__cancelled__':
            self.statusBar().showMessage('操作失败，请检查路径或文件格式');QMessageBox.warning(self,'无法完成比对',error[-2500:])
    def filter_changed(self,*_):
        self.proxy.query=self.search.text();self.proxy.images=self.only_images.isChecked();self.proxy.different=self.only_diff.isChecked();self.proxy.invalidateFilter();self.update_counter()
        if self.proxy.rowCount() and not self.table.currentIndex().isValid():self.table.selectRow(0)
    def list_style_changed(self,*_):
        self.model.thumbnails=self.list_style.currentIndex()==0;self.table.verticalHeader().setDefaultSectionSize(92 if self.model.thumbnails else 48)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(0,180)
        for c in range(1,self.model.columnCount()):self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.Interactive);self.table.setColumnWidth(c,94 if self.model.thumbnails else 104)
        self.table.setColumnHidden(0,True)
        for c in range(1,self.model.columnCount()):self.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.Stretch)
        self.table.viewport().update()
    def update_counter(self):
        row=self.table.currentIndex().row();self.counter.setText(f'{row+1 if row>=0 else 0} / {self.proxy.rowCount():,} 项  ·  总计 {len(self.rows):,}'+(f'  ·  缩略图 {len(self.thumb_completed):,}/{len(self.thumb_paths):,}'+(f'，失败 {len(self.thumb_fail)}' if self.thumb_fail else '') if self.thumb_paths else ''))
    def load_selected(self):
        index=self.table.currentIndex()
        if not index.isValid():return
        entry=index.data(Qt.ItemDataRole.UserRole)
        if entry is self.current_entry and self.bundle:return
        self.debounce.stop();self.threshold_timer.stop();self.thumb_sources.clear();self.details.hide();self.details.bundle=None
        self.current_entry=entry;self.display_paths=list(entry.paths);self.bundle=None;self.diff_position=-1
        for i,p in enumerate(self.panes[:self.active_count()]):p.set_title(entry.paths[i],i==self.baseline.currentIndex());p.message('正在载入…' if entry.paths[i] else '此文件夹缺少该文件')
        self.refresh_content();self.update_counter()
    def request_live_threshold(self,*_):
        if self.current_entry and not self.threshold_timer.isActive():self.threshold_timer.start()
    def update_live_threshold(self):
        if self.preview_id is not None or self.debounce.isActive():return
        if not self.bundle or self.bundle['kind']!='image':self.threshold_timer.stop();return
        value=self.threshold.value();units=[255,1023,65535][self.units.currentIndex()]
        if self.bundle.get('threshold')==value:self.threshold_timer.stop();return
        bundle=self.bundle
        self.preview_id=self.submit(lambda cancel,_:rethreshold_bundle(bundle,value,units,cancel),'threshold')
    def fullscreen_images(self,index=None):
        if not self.bundle or self.bundle['kind']!='image':return
        from fullscreen import FullscreenImages
        if not any(self.bundle['images']):return
        pixmaps=[self.panes[i].image.item.pixmap() if item else None for i,item in enumerate(self.bundle['images'])]
        dialog=FullscreenImages(self.bundle['images'],self.baseline.currentIndex() if index is None else index,self,pixmaps=pixmaps)
        dialog.exec()
    def schedule_refresh(self,*_):
        if self.current_entry:self.debounce.start()
    def units_changed(self,*_):
        self.threshold.setMaximum([255,1023,65535][self.units.currentIndex()]);self.schedule_refresh()
    def refresh_content(self,*,memory_only=False):
        if not self.current_entry:return
        self.cancel_id(self.preview_id);paths=list(getattr(self,'display_paths',self.current_entry.paths));base=self.baseline.currentIndex();present=[p for p in paths if p]
        if not present:return
        for i,p in enumerate(self.panes[:self.active_count()]):p.set_title(paths[i],i==base)
        if all(Path(p).suffix.lower() in IMAGE_EXTS for p in present):
            old=self.bundle['images'] if self.bundle and self.bundle['kind']=='image' else None
            args=(paths,base,self.threshold.value(),[255,1023,65535][self.units.currentIndex()],self.standard.currentText(),'left10' if self.storage.currentIndex()==1 else 'auto',self.alpha.isChecked())
            previous=self.bundle if old else None;compute_comparisons=memory_only or self.show_details.isChecked()
            metric_mode=self.hist_mode.currentText() if self.hist_mode.currentText()!='关闭' else self.last_metric_mode
            self.preview_id=self.submit(lambda cancel,ready:image_bundle(*args,cancel=cancel,existing=old,metric_mode=metric_mode,ready=None if memory_only else ready,previous_bundle=previous,cache=None if memory_only else self.image_cache,cached_only=memory_only,compute_comparisons=compute_comparisons),'recompute' if memory_only else 'preview',staged=not memory_only)
        else:
            ignore=self.ignore_space.isChecked();self.preview_id=self.submit(lambda cancel,_:text_bundle(paths,base,ignore,cancel),'preview')
        self.statusBar().showMessage('正在更新指标 · 使用已缓存的图片' if memory_only else '正在比较 · 可继续操作，或按 Esc 停止')
    def show_bundle(self):
        b=self.bundle;n=self.active_count()
        if self.focus_active and b['kind']!='image':self.focus_mode()
        if b['kind']=='image':
            for i,p in enumerate(self.panes[:n]):
                p.set_title(self.display_paths[i],i==b['baseline'])
                if b['images'][i]:p.set_image(b['images'][i],self.hist_mode.currentText(),self.log_hist.isChecked())
                else:p.message(b['errors'][i])
            self.render_images();self.hist_changed()
            complete=all(b['images']);results=[r for r in b['comparisons'] if r]
            if complete and len(results)==n-1 and all(r.get('equal',False) for r in results):self.update_status('像素相同')
            elif complete and any(not r.get('compatible',False) or not r.get('equal',False) for r in results):self.update_status('像素不同')
            self.statusBar().showMessage('图片 · 滚轮缩放，拖动平移 · 红=超过阈值，蓝=阈值内差异 · 指针显示原始码值')
        else:
            for i,p in enumerate(self.panes[:n]):
                if b['texts'][i]:p.set_text(b['columns'][i],b['texts'][i]['note'])
                else:p.message(b['errors'][i])
            if all(b['texts']) and not any(t['truncated'] for t in b['texts']):self.update_status('内容不同' if b['diff_rows'] else '内容相同')
            self.statusBar().showMessage(f'文本内容 · {len(b["diff_rows"]):,} 行存在差异 · F7 / Shift+F7 定位 · 文档仅比较提取内容')
        self.update_view_controls();self.details_visibility();self.update_counter();self.refresh_command_state()
    def update_status(self,value):
        if not self.current_entry:return
        # Never overwrite a stronger byte-identical result with an extraction-level result.
        if self.current_entry.status!='字节相同':self.current_entry.status=value
        self.table.viewport().update()
    def update_view_controls(self):
        text_mode=bool(self.bundle and self.bundle['kind']=='text')
        for widget in (self.units,self.storage,self.alpha,self.hist_label,self.hist_mode,self.log_hist,self.show_details):widget.setVisible(not text_mode)
        self.standard.setVisible(self.hist_mode.currentText() in ('Y','YUV') and not (self.bundle and self.bundle['kind']=='text'));self.standard_label.setVisible(self.hist_mode.currentText() in ('Y','YUV') and not (self.bundle and self.bundle['kind']=='text'))
        self.ignore_space.setVisible(bool(self.bundle and self.bundle['kind']=='text'))
        mode=self.view_mode.currentIndex()
        self.gain.setVisible(mode==2 and not text_mode);self.gain_label.setVisible(mode==2 and not text_mode)
        self.mix.setVisible(mode in (3,4) and not text_mode);self.mix_label.setVisible(mode in (3,4) and not text_mode)
        self.mix_label.setText(('混合比例' if mode==3 else '分割位置')+f' {self.mix.value()}%')
        self.mix.setToolTip('调整另一张图的叠加比例，0% 为基准，100% 为另一张图。' if mode==3 else '调整基准图与另一张图的左右分界位置。')
    def activate_result_mode(self,index):
        if self.view_mode.currentIndex()==index:self.select_result_mode()
        else:self.view_mode.setCurrentIndex(index)
    def select_result_mode(self,*_):
        if self.bundle and self.bundle['kind']=='image':self.show_details.setChecked(True)
        self.render_images()
    def render_images(self,*_):
        self.update_view_controls()
        if not self.bundle or self.bundle['kind']!='image':return
        b=self.bundle;base=b['baseline'];mode=self.view_mode.currentIndex();gain=[1,4,16,64][self.gain.currentIndex()];mix=self.mix.value()/100
        for i,p in enumerate(self.panes[:self.active_count()]):
            item=b['images'][i]
            if not item:continue
            p.image.set_image(item['display'],preserve=True)
        self.details.mode=mode;self.details.mix=mix;self.details.gain=gain;self.details.set_bundle(b);self.detail_threshold()
    def render_mix(self,*_):
        self.update_view_controls()
        if self.details.bundle and self.view_mode.currentIndex() in (3,4):
            self.details.mix=self.mix.value()/100;self.details.render()
    def remember_detail_sizes(self,*_):
        if not self.focus_active and self.details.isVisible():self.saved_detail_sizes=self.image_split.sizes()
    def details_visibility(self,*_):
        if not hasattr(self,'details'):return
        if self.active_count()==2 and not self.restoring_settings:self.two_image_details=self.show_details.isChecked()
        visible=bool(not self.focus_active and self.bundle and self.bundle['kind']=='image' and self.show_details.isChecked())
        was_visible=self.details.isVisible();self.details.setVisible(visible)
        if visible and not was_visible:
            height=self.image_split.height();bottom=min(380,max(260,round(height*.45)))
            self.image_split.setSizes(self.saved_detail_sizes or [max(200,height-bottom),bottom])
        if visible and self.bundle.get('dirty_comparisons') and self.preview_id is None:self.refresh_content(memory_only=True)
    def detail_threshold(self,*_):
        self.details.set_threshold(self.threshold.value(),[255,1023,65535][self.units.currentIndex()])
    def detail_zoom(self,percent):
        for pane in self.panes[:self.active_count()]:pane.image.set_zoom(percent)
        self.details.view.set_zoom(percent);self.details.update_zoom(percent)
        if self.focus_active:self.focus_controls.update_zoom()
    def swap_sources(self):
        if not self.bundle or self.bundle['kind']!='image':return
        n=self.active_count();left=0 if n==2 else self.baseline.currentIndex()
        right=1 if n==2 else self.details.target.currentData()
        if right is None or right==left or right>=n:right=next(i for i in range(n) if i!=left)
        pending=self.preview_id is not None or self.debounce.isActive();self.debounce.stop();self.threshold_timer.stop()
        self.cancel_id(self.preview_id);self.preview_id=None
        self.bundle=dict(self.bundle)
        for key in ['images','errors','comparisons']:self.bundle[key]=list(self.bundle[key])
        pixmaps={left:self.panes[left].image.item.pixmap(),right:self.panes[right].image.item.pixmap()}
        self.display_paths[left],self.display_paths[right]=self.display_paths[right],self.display_paths[left]
        for key in ['images','errors']:
            items=self.bundle[key];items[left],items[right]=items[right],items[left]
        for dest,source in [(left,right),(right,left)]:
            item=self.bundle['images'][dest]
            if item:self.panes[dest].image.set_image(item['display'],preserve=True,pixmap=pixmaps[source])
        if n>2 or pending:
            valid_pair=self.bundle['comparisons'][right] if n>2 and not pending else None
            self.bundle['comparisons']=[None]*n
            if n>2:self.bundle['comparisons'][right]=valid_pair
            self.bundle['dirty_comparisons']=True
        self.progress.hide();self.show_bundle()
        if self.bundle.get('dirty_comparisons') and not self.show_details.isChecked():
            self.statusBar().showMessage('已交换当前图片 · 打开底部对比区时计算新的基准关系')
        self.set_busy(self.preview_id is not None)
    def image_context_menu(self,index,pos=None):
        view=self.panes[index].image;menu=QMenu(self)
        commands=[('全屏查看',lambda:self.fullscreen_images(index)),('设为基准',lambda:self.baseline.setCurrentIndex(index)),('自动缩放（对齐基准）',self.align_to_baseline),('适应窗口',lambda:view.fit()),('原始大小（1:1）',lambda:view.actual()),('水平缩放（适应宽度）',view.fit_width),None,
                  ('顺时针旋转 90°',lambda:view.rotate_image(90)),('逆时针旋转 90°',lambda:view.rotate_image(-90)),('重置旋转',view.reset_rotation),None,
                  ('在文件夹中定位',lambda:self.reveal_source(index))]
        valid=bool(self.bundle and self.bundle['kind']=='image' and self.bundle['images'][index])
        for command in commands:
            if command is None:menu.addSeparator();continue
            name,fn=command;action=menu.addAction(name);action.triggered.connect(fn);action.setEnabled(valid)
        if pos is not None:menu.exec(view.mapToGlobal(pos));menu.deleteLater()
        return menu
    def align_to_baseline(self):
        if not self.bundle or self.bundle['kind']!='image':return
        base=self.baseline.currentIndex()
        if not self.bundle['images'][base]:return
        reference=self.panes[base].image
        for i,pane in enumerate(self.panes[:self.active_count()]):
            if i!=base and self.bundle['images'][i]:pane.image.match_reference(reference)
        self.statusBar().showMessage('已按基准图的显示尺寸等比对齐；宽高比不同时保留比例，原始像素和指标不变。')
    def reveal_source(self,index):
        if not self.bundle or self.bundle['kind']!='image':return
        item=self.bundle['images'][index]
        if item:subprocess.Popen(['explorer.exe','/select,',os.path.normpath(item['path'])])
    def hist_changed(self,*_):
        mode=self.hist_mode.currentText()
        if mode!='关闭':self.last_metric_mode=mode
        if self.bundle and self.bundle['kind']=='image' and self.bundle.get('metric_mode')!=self.last_metric_mode:self.schedule_refresh()
        self.standard.setVisible(self.hist_mode.currentText() in ('Y','YUV') and not (self.bundle and self.bundle['kind']=='text'));self.standard_label.setVisible(self.hist_mode.currentText() in ('Y','YUV') and not (self.bundle and self.bundle['kind']=='text'))
        for p in self.panes:
            if p.raw is not None:p.hist.configure(mode=self.hist_mode.currentText(),log=self.log_hist.isChecked());p.hist.setVisible(self.hist_mode.currentText()!='关闭')
    def sync_views(self,index,state):
        if self.syncing or not self.sync.isChecked():return
        self.syncing=True
        for i,p in enumerate(self.panes[:self.active_count()]):
            if i!=index:p.image.apply_state(state)
        if self.details.bundle:self.details.view.apply_state(state);self.details.update_zoom(self.details.view.transform().m11()*100)
        self.syncing=False
    def sync_text(self,index,value):
        if self.text_syncing or not self.sync.isChecked():return
        self.text_syncing=True
        for i,p in enumerate(self.panes[:self.active_count()]):
            if i!=index:p.text.verticalScrollBar().setValue(value)
        self.text_syncing=False
    def pixel_values(self,x,y):
        signature=(x,y,tuple(id(p.raw) for p in self.panes[:self.active_count()]))
        if getattr(self,'last_pixel_signature',None)==signature:return
        self.last_pixel_signature=signature
        for p in self.panes[:self.active_count()]:p.show_pixel(x,y);p.image.set_cursor_pixel(x,y)
        self.details.set_pixel(x,y)
    def fit_all(self):
        for p in self.panes[:self.active_count()]:p.image.fit()
        self.details.view.fit(emit=False);self.details.update_zoom(self.details.view.transform().m11()*100)
        if self.focus_active:self.focus_controls.update_zoom()
    def actual_all(self):
        self.syncing=True
        for p in self.panes[:self.active_count()]:p.image.actual()
        self.syncing=False
        self.details.view.actual();self.details.update_zoom(100)
        if self.focus_active:self.focus_controls.update_zoom()
    def navigate(self,delta):
        n=self.proxy.rowCount()
        if not n:return
        row=self.table.currentIndex().row();row=max(0,min(n-1,row+delta));self.table.selectRow(row);self.table.scrollTo(self.proxy.index(row,0));self.update_counter()
    def jump_diff(self,delta):
        if self.bundle and self.bundle['kind']=='text' and self.bundle['diff_rows']:
            rows=self.bundle['diff_rows'];self.diff_position=(self.diff_position+delta)%len(rows);line=rows[self.diff_position]
            for p in self.panes[:self.active_count()]:p.text.setTextCursor(QTextCursor(p.text.document().findBlockByNumber(line)));p.text.centerCursor()
            self.statusBar().showMessage(f'差异行 {self.diff_position+1} / {len(rows)}');return
        start=self.table.currentIndex().row()
        for row in range(start+delta,self.proxy.rowCount() if delta>0 else -1,delta):
            entry=self.proxy.index(row,0).data(Qt.ItemDataRole.UserRole)
            if entry.status not in ['字节相同','像素相同','内容相同']:
                self.table.selectRow(row);self.table.scrollTo(self.proxy.index(row,0));return
    def thumb_file(self,path):
        key=hashlib.sha256((str(self.generation)+'|'+path).encode('utf-8')).hexdigest()
        return str(Path(self.thumb_directory.name)/(key+'.png'))
    def pump_thumbnails(self):
        if self.closing or self.thumbs_paused:return
        while len(self.thumb_pending)<2 and self.thumb_position<len(self.thumb_paths):
            path=self.thumb_paths[self.thumb_position];self.thumb_position+=1
            if path not in self.thumb_completed and path not in self.thumb_pending and path not in self.thumb_fail:self.thumbnail(path)
        total=len(self.thumb_paths);done=len(self.thumb_completed)+len(self.thumb_fail)
        self.sidebar_refresh.setToolTip(f'缩略图：{min(done,total)} / {total}，失败 {len(self.thumb_fail)}。点击重新扫描文件并刷新图片。')
        self.update_counter();self.set_busy(self.preview_id is not None or self.scan_id is not None)
        if self.thumb_position>=total and not self.thumb_pending:self.thumb_timer.stop()
    def thumbnail(self,path):
        if path in self.thumb_cache:self.thumb_cache.move_to_end(path);return self.thumb_cache[path]
        if self.closing or self.thumbs_paused or self.scan_id is not None:return None
        if path in self.thumb_pending or path in self.thumb_fail or len(self.thumb_pending)>=2:return None
        self.thumb_pending.add(path);self.set_busy(True);self.serial+=1;ident=self.serial;generation=self.generation
        cached=path in self.thumb_completed;cache_file=self.thumb_file(path);source=self.thumb_sources.get(path)
        def fn(cancel,progress):
            checkpoint(cancel)
            if generation!=self.generation:raise Cancelled()
            if cached:
                img=QImage(cache_file)
                if not img.isNull():return (generation,path,img)
            if source is not None:
                h,w=source.shape[:2];scale=min(140/w,80/h,1);small=cv2.resize(source[:,:,:3],(max(1,int(w*scale)),max(1,int(h*scale))),interpolation=cv2.INTER_AREA);a=cv2.cvtColor(small,cv2.COLOR_RGB2BGR)
            else:a=cv2.imdecode(np.fromfile(path,np.uint8),cv2.IMREAD_REDUCED_COLOR_8)
            checkpoint(cancel)
            if a is None:
                raw=read_image(path,cancel);a=cv2.cvtColor(display_rgb(raw)[:,:,:3],cv2.COLOR_RGB2BGR)
            h,w=a.shape[:2];scale=min(140/w,80/h,1);a=cv2.resize(a,(max(1,int(w*scale)),max(1,int(h*scale))),interpolation=cv2.INTER_AREA)
            img=qimage(cv2.cvtColor(a,cv2.COLOR_BGR2RGB));checkpoint(cancel)
            if not img.save(cache_file):raise OSError('缩略图缓存写入失败')
            return (generation,path,img)
        job=Task(ident,fn,threading.Event());self.thumb_jobs[ident]=(job,generation,path);job.signals.done.connect(self.thumb_done);job.signals.failed.connect(self.thumb_failed);self.thumb_pool.start(job);return None
    def thumb_done(self,ident,result):
        self.thumb_jobs.pop(ident,None);generation,path,img=result
        if generation!=self.generation:return
        self.thumb_pending.discard(path);self.thumb_completed.add(path);self.thumb_cache[path]=QPixmap.fromImage(img)
        while len(self.thumb_cache)>256:self.thumb_cache.popitem(last=False)
        self.table.viewport().update();self.set_busy(self.preview_id is not None or self.scan_id is not None)
    def thumb_failed(self,ident,error):
        item=self.thumb_jobs.pop(ident,None)
        if item and item[1]==self.generation:
            self.thumb_pending.discard(item[2])
            if error!='__cancelled__':self.thumb_fail.add(item[2])
            self.table.viewport().update()
    def export_list(self):
        if not self.rows:return
        path,_=QFileDialog.getSaveFileName(self,'导出比较列表','comparison.csv','CSV (*.csv)')
        if not path:return
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(['relative_path','status']+[chr(65+i)+'_path' for i in range(self.active_count())]+['errors'])
                for row in self.rows:w.writerow([row.name,row.status,*[p or '' for p in row.paths],' | '.join(row.errors)])
                for error in self.scan_errors:w.writerow(['','扫描错误',*['']*self.active_count(),error])
            self.statusBar().showMessage('已导出列表：'+path)
        except OSError as exc:QMessageBox.warning(self,'导出失败',str(exc))
    def save_session(self):
        path,_=QFileDialog.getSaveFileName(self,'保存比较会话','comparison.prism.json','Prism 会话 (*.json)')
        if not path:return
        data={'version':1,'mode':self.mode.currentIndex(),'paths':[e.text() for e in self.path_edits[:self.active_count()]],'baseline':self.baseline.currentIndex(),'threshold':self.threshold.value(),'units':self.units.currentIndex(),'storage':self.storage.currentIndex(),'standard':self.standard.currentText(),'hist':self.hist_mode.currentText(),'recursive':self.recursive.isChecked(),'exact':self.exact.isChecked()}
        try:Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');self.statusBar().showMessage('会话已保存')
        except OSError as exc:QMessageBox.warning(self,'保存失败',str(exc))
    def open_session(self):
        path,_=QFileDialog.getOpenFileName(self,'打开比较会话','','Prism 会话 (*.json)')
        if not path:return
        try:
            d=json.loads(Path(path).read_text(encoding='utf-8'));paths=d['paths']
            if not 2<=len(paths)<=4 or not all(isinstance(p,str) for p in paths):raise ValueError('会话必须包含 2–4 个路径')
            self.count.setCurrentText(str(len(paths)));self.mode.setCurrentIndex(d.get('mode',0))
            for i,e in enumerate(self.path_edits):e.setText(paths[i] if i<len(paths) else '')
            self.units.setCurrentIndex(d.get('units',0));self.storage.setCurrentIndex(d.get('storage',0));self.threshold.setValue(d.get('threshold',0));self.baseline.setCurrentIndex(d.get('baseline',0));self.standard.setCurrentText(d.get('standard','BT.709'));self.hist_mode.setCurrentText(d.get('hist','RGB'));self.recursive.setChecked(d.get('recursive',True));self.exact.setChecked(d.get('exact',False));self.compare()
        except Exception as exc:QMessageBox.warning(self,'会话读取失败',str(exc))
    def demo(self):
        from demo import create_demo
        target=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PrismCompare'/'demo';create_demo(target);self.count.setCurrentText('4');self.set_paths([str(target/chr(65+i)) for i in range(4)],True)
    def help(self):
        QMessageBox.information(self,'Prism Compare · 使用说明',
            '2–4 个文件或文件夹：按相对路径配对。拖入即可打开。\n\n'
            '图片：滚轮缩放，拖动平移；F 适应窗口，1 原始像素。\nAlt+← / → 上一项 / 下一项；F7 / Shift+F7 下一处 / 上一处差异。\nCtrl+B 显隐列表，F10 全屏查看，Esc 停止后台任务。\n\n'
            '红蓝差异：最大通道绝对差超过阈值为红，非零但阈值内为蓝，相同为黑。\n阈值单位可选 8bit / 10bit / 16bit，指标来自原尺寸图片。\n16bit PNG 若存储 v10<<6，请选“10bit 左移6位”。\nY′ 为加权码值，不是屏幕亮度 nit；直方图使用全图像素。\n\n'
            '文本/代码：对齐行并高亮；DOCX/PDF/XLSX 仅比较提取的文字/值/公式。\n不比较文档排版，不执行 OCR、宏或脚本。旧 DOC/XLS 请先转换格式。\nGIF 仅第一帧。图片不做色彩管理或 HDR 显示映射。\n\n'
            '默认文件夹扫描不读取内容，大小相同仅标记“待校验”。\n勾选 SHA-256 可完整读取精确比较。所有来源只读。\n大文本超过 80 万字符/12000 行、PDF 超过 200 页时会明确标注截断。')
    def closeEvent(self,event):
        self.closing=True
        if hasattr(self,'shell_shutdown'):self.shell_shutdown()
        self.cancel_work();self.generation+=1
        for job,_,_ in self.thumb_jobs.values():job.cancel.set()
        self.pool.clear();self.thumb_pool.clear()
        if self.pool.activeThreadCount() or self.thumb_pool.activeThreadCount():
            event.ignore();self.hide();QTimer.singleShot(200,self.close);return
        self.save_preferences()
        event.accept()

def main():
    app=QApplication(sys.argv);setup_fonts(app);app.setApplicationName('Prism Compare');app.setStyle('windowsvista' if 'windowsvista' in QStyleFactory.keys() else 'Fusion')
    asset=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))/'assets'/'prism.png'
    if asset.exists():app.setWindowIcon(QIcon(str(asset)))
    def exception_hook(kind,value,tb):
        text=''.join(traceback.format_exception(kind,value,tb));folder=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'PrismCompare'/'logs'
        try:folder.mkdir(parents=True,exist_ok=True);(folder/'last_error.log').write_text(text,encoding='utf-8')
        except OSError:pass
        QMessageBox.warning(None,'Prism Compare 遇到错误',str(value)+'\n\n日志位置：'+str(folder/'last_error.log'))
    sys.excepthook=exception_hook
    args=sys.argv[1:]
    bridge=None
    if '--shell' in args:
        from shell_bridge import ShellBridge
        bridge=ShellBridge()
        shell_paths=[p for p in args[args.index('--shell')+1:] if not p.startswith('--')]
        if not bridge.start(shell_paths):return 0
    if '--smoke-test' in args:os.environ['PRISM_CONFIG_DIR']=str(Path(args[args.index('--smoke-test')+1])/'config')
    window=Window();window.show()
    if bridge is not None:
        from shell_bridge import attach_shell
        attach_shell(window,bridge,shell_paths)
    elif '--demo' in args:QTimer.singleShot(100,window.demo)
    elif '--smoke-test' in args:
        from smoke import packaged_smoke
        QTimer.singleShot(100,lambda:packaged_smoke(window,app,args))
    elif args:
        paths=[p for p in args if not p.startswith('--')]
        if paths:QTimer.singleShot(100,lambda:window.set_paths(paths,all(Path(p).is_dir() for p in paths)))
    return app.exec()

if __name__=='__main__':raise SystemExit(main())
