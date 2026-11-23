"""Single command surface with compact two-character captions."""
from PySide6.QtCore import Qt,QSize,QPoint
from PySide6.QtGui import QAction,QActionGroup
from PySide6.QtWidgets import QToolBar,QPushButton,QWidget,QSizePolicy,QMenu,QToolButton
from command_icons import command_icon

def refresh_icons(window,light):
    for action in window.command_toolbar.actions():
        key=action.property('iconKey')
        if key:action.setIcon(command_icon(key,not light))

def build_toolbar(window):
    bar=QToolBar('常用功能',window);bar.setObjectName('commandToolbar');bar.setMovable(False);bar.setIconSize(QSize(20,20));bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon);window.addToolBar(bar)
    window.command_toolbar=bar;window.toolbar_actions={}
    def add(label,name,key,callback,shortcut=''):
        action=QAction(command_icon(key),label,window);action.setProperty('iconKey',key);action.setToolTip(name+(' · '+shortcut if shortcut else ''));action.setStatusTip(action.toolTip());action.triggered.connect(callback);bar.addAction(action);window.toolbar_actions[name]=action
        bar.widgetForAction(action).setAccessibleName(name)
        return action
    add('文件','打开文件','file',window.open_files,'Ctrl+O');add('目录','添加文件夹','folder',window.add_folder)
    history=add('历史','最近比较历史','history',lambda:None);menu=QMenu(window);menu.aboutToShow.connect(lambda:window.populate_history(menu));history.triggered.connect(lambda:menu.popup(bar.widgetForAction(history).mapToGlobal(QPoint(0,bar.widgetForAction(history).height()))))
    bar.addSeparator();add('比较','开始 / 重新比对','play',window.compare,'Ctrl+R');add('停止','停止','stop',window.cancel_work,'Esc')
    window.toolbar_actions['停止'].setEnabled(window.cancel_button.isEnabled())
    bar.addSeparator();window.mode_actions={};group=QActionGroup(window);group.setExclusive(True)
    for i,(label,key) in enumerate([('容差','heat'),('差值','difference'),('混合','blend'),('分割','wipe')],1):
        action=add(label,window.view_mode.itemText(i),key,lambda checked=False,j=i:window.activate_result_mode(j));action.setCheckable(True);group.addAction(action);window.mode_actions[i]=action
    window.view_mode.setCurrentIndex(max(1,window.view_mode.currentIndex()));window.mode_actions[window.view_mode.currentIndex()].setChecked(True)
    window.view_mode.currentIndexChanged.connect(lambda i:window.mode_actions[max(1,i)].setChecked(True));window.view_mode.hide()
    bar.addSeparator();add('交换','左右交换当前图片','swap',window.swap_sources)
    add('对齐','自动缩放：对齐基准显示大小','align',window.align_to_baseline)
    add('适应','适应窗口','fit',window.fit_all,'F');add('原大','原始像素 1:1','actual',window.actual_all,'1')
    bar.addSeparator();add('上项','上一项','prev',lambda:window.navigate(-1),'Alt+←');add('下项','下一项','next',lambda:window.navigate(1),'Alt+→')
    add('前差','上一处差异','prevdiff',lambda:window.jump_diff(-1),'Shift+F7');add('后差','下一处差异','nextdiff',lambda:window.jump_diff(1),'F7')
    bar.addSeparator();add('全屏','全屏查看当前图片组','focus',lambda:window.fullscreen_images(),'F10');add('专注','纯图片专注模式','concentrate',window.focus_mode,'F11')
    for name in ['上一处差异','下一处差异']:
        window.toolbar_actions[name].setToolTip(name+'：文本中跳转差异行；文件夹中跳过已确认相同的项目')
    for area in [window.header,window.top,window.controls]:
        for button in area.findChildren(QPushButton):button.hide()

    spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);bar.addWidget(spacer);bar.addWidget(window.settings_toggle)

    window.refresh_command_state()
