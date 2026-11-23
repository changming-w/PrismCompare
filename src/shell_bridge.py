"""User-local IPC for Explorer context-menu invocations (sources remain read-only)."""
import hashlib,json,os,tempfile
from pathlib import Path
from PySide6.QtCore import QLockFile,QTimer,QObject,Signal
from PySide6.QtNetwork import QLocalServer,QLocalSocket

class ShellBridge(QObject):
    received=Signal(list)
    def __init__(self):
        super().__init__();self.connections=[]
        key=os.environ.get('PRISM_SHELL_ID',str(Path.home()))
        self.name='PrismCompare-'+hashlib.sha256(key.encode()).hexdigest()[:20]
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.accept)
    def start(self,paths):
        lock=QLockFile(str(Path(tempfile.gettempdir())/(self.name+'.lock')))
        if not lock.tryLock(5000):raise RuntimeError('右键比较窗口正在启动，请稍后重试。')
        try:
            socket=QLocalSocket();socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                payload=(json.dumps(paths,ensure_ascii=False)+'\n').encode('utf-8')
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
                paths=json.loads(bytes(socket.readLine()).decode('utf-8'))
                if isinstance(paths,list) and len(paths)<=64 and all(isinstance(p,str) for p in paths):self.received.emit(paths)
            except (ValueError,UnicodeError):pass
    def dispose(self,socket):
        self.read(socket)
        if socket in self.connections:self.connections.remove(socket)
        socket.deleteLater()
    def stop(self):
        # Release the IPC endpoint immediately, even while workers finish closing.
        self.server.close()
        for socket in list(self.connections):socket.abort()

def attach_shell(window,bridge,paths):
    pending=[];timer=QTimer(window);timer.setSingleShot(True);timer.setInterval(350)
    state={'reset_next':False,'warning':False}
    def apply():
        from PySide6.QtWidgets import QMessageBox
        if window.closing or state['warning']:pending.clear();return
        incoming=list(dict.fromkeys(pending));pending.clear()
        if not incoming:return
        if not all(Path(p).exists() for p in incoming):
            QMessageBox.warning(window,'路径不可用','所选文件或文件夹已不存在。');return
        folders=Path(incoming[0]).is_dir()
        if any(Path(p).is_dir()!=folders for p in incoming):
            QMessageBox.warning(window,'选择类型','请全部选择文件，或全部选择文件夹。');return
        current=[e.text().strip() for e in window.path_edits[:window.active_count()] if e.text().strip()]
        if state['reset_next']:current=[];state['reset_next']=False
        if window.mode.currentIndex()!=(0 if folders else 1):current=[]
        combined=list(dict.fromkeys(current+incoming))
        if len(combined)>4:
            state['reset_next']=True;state['warning']=True
            try:QMessageBox.warning(window,'数量限制','最多比较 4 个文件或文件夹。本次超量选择未加入；请重新选择 2–4 个来源，下一次选择将开始新的一组。')
            finally:pending.clear();timer.stop();state['warning']=False
            return
        window.set_paths(combined,folders)
        if len(combined)==1:window.statusBar().showMessage('已加入来源 A。请右键另一个文件/文件夹加入比较，或在窗口中选择来源 B。')
        window.showNormal();window.raise_();window.activateWindow()
    def queue(paths):
        if window.closing or state['warning']:return
        pending.extend(paths);timer.start()
    def shutdown():
        timer.stop();pending.clear();bridge.stop()
    window.shell_shutdown=shutdown
    timer.timeout.connect(apply);bridge.received.connect(queue);window.shell_bridge=bridge;window.shell_timer=timer;queue(paths)
