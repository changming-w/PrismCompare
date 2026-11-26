"""User-local IPC for Explorer context-menu invocations (sources remain read-only)."""
import hashlib,json,os,tempfile
from pathlib import Path
from PySide6.QtCore import QLockFile,QTimer,QObject,Signal
from PySide6.QtNetwork import QLocalServer,QLocalSocket

class ShellBridge(QObject):
    received=Signal(list)
    received_new=Signal(list)
    def __init__(self):
        super().__init__();self.connections=[]
        key=os.environ.get('PRISM_SHELL_ID',str(Path.home()))
        self.name='PrismCompare-'+hashlib.sha256(key.encode()).hexdigest()[:20]
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
    def start(self,paths,*,new_window=False):
        lock=QLockFile(str(Path(tempfile.gettempdir())/(self.name+'.lock')))
        if not lock.tryLock(5000):raise RuntimeError('右键比较窗口正在启动，请稍后重试。')
        try:
            socket=QLocalSocket();socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                message={'new_window':True,'paths':paths} if new_window else paths
                payload=(json.dumps(message,ensure_ascii=False)+'\n').encode('utf-8')
                socket.write(payload)
                if not socket.waitForBytesWritten(3000):raise RuntimeError('无法发送右键选择的路径。')
                socket.disconnectFromServer();return False
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):raise RuntimeError(self.server.errorString())
            return True
        finally:lock.unlock()
    def accept(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection();self.connections.append(socket)
            socket.readyRead.connect(lambda s=socket:self.read(s))
            socket.disconnected.connect(lambda s=socket:self.dispose(s))
            self.read(socket)
    def read(self,socket):
        while socket.canReadLine():
            try:
                message=json.loads(bytes(socket.readLine()).decode('utf-8'))
                new_window=isinstance(message,dict) and message.get('new_window') is True
                paths=message.get('paths') if new_window else message
                if isinstance(paths,list) and len(paths)<=64 and all(isinstance(p,str) for p in paths):
                    (self.received_new if new_window else self.received).emit(paths)
            except (ValueError,UnicodeError):pass
    def dispose(self,socket):
        self.read(socket)
        if socket in self.connections:self.connections.remove(socket)
        socket.deleteLater()
    def stop(self):
        # Release the IPC endpoint immediately, even while workers finish closing.
        self.server.close()
        for socket in list(self.connections):socket.abort()

def attach_shell(window,bridge,paths,*,new_window=False):
    from PySide6.QtWidgets import QApplication
    pending={False:[],True:[]}
    timers={intent:QTimer(bridge) for intent in pending}
    windows=[]
    reuse_startup_window=new_window
    reset_next=False
    warning=False

    def register(target):
        windows.append(target)
        target.shell_register=register
        target.shell_bridge=bridge
        target.shell_timer=timers[False]
        target.shell_shutdown=lambda:unregister(target)

    def unregister(target):
        if target in windows:windows.remove(target)
        if windows:return
        for intent,timer in timers.items():
            timer.stop()
            pending[intent].clear()
        bridge.stop()

    def apply(intent):
        from PySide6.QtWidgets import QMessageBox
        nonlocal reuse_startup_window,reset_next,warning
        incoming=list(dict.fromkeys(pending[intent]));pending[intent].clear()
        if not incoming or not windows or warning:return
        target=windows[-1]
        if not all(Path(p).exists() for p in incoming):
            QMessageBox.warning(target,'路径不可用','所选文件或文件夹已不存在。');return
        folders=Path(incoming[0]).is_dir()
        if any(Path(p).is_dir()!=folders for p in incoming):
            QMessageBox.warning(target,'选择类型','请全部选择文件，或全部选择文件夹。');return
        current=[]
        if not intent and not reset_next and target.mode.currentIndex()==(0 if folders else 1):
            current=[e.text().strip() for e in target.path_edits[:target.active_count()] if e.text().strip()]
        reset_next=False
        combined=list(dict.fromkeys(current+incoming))
        if len(combined)>4:
            reset_next=not intent
            warning=True
            try:QMessageBox.warning(target,'数量限制','最多比较 4 个文件或文件夹。请重新选择，或使用“在新窗口中比对”另开一组。')
            finally:
                for key,timer in timers.items():
                    pending[key].clear();timer.stop()
                warning=False
            return
        if intent and not reuse_startup_window:
            target=target.new_comparison_window()
        reuse_startup_window=False
        target.set_paths(combined,folders)
        if len(combined)==1 and not folders:target.statusBar().showMessage('已加入来源 A。可拖入或通过普通右键命令加入来源 B。')
        if target.isMinimized():target.showNormal()
        target.raise_();target.activateWindow()

    def queue(paths,intent=False):
        if not windows or warning or not paths:return
        pending[intent].extend(paths)
        timers[intent].start()

    bridge.setParent(QApplication.instance())
    register(window)
    for intent,timer in timers.items():
        timer.setSingleShot(True);timer.setInterval(350)
        timer.timeout.connect(lambda key=intent:apply(key))
    bridge.received.connect(queue)
    bridge.received_new.connect(lambda paths:queue(paths,True))
    queue(paths,new_window)
