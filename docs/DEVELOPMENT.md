# 架构与开发

## 开发入口

运行 `run.cmd`，或 `.venv\Scripts\python.exe src\app.py`。
VS Code 打开项目根目录或 `PrismCompare.code-workspace` 后按 F5。
示例模式：`.venv\Scripts\python.exe src\app.py --demo`。
本项目是独立源码目录；不依赖之前数据处理脚本、网络共享路径或聊天临时目录。

## 模块边界

- `core.py`：与窗口无关的比较逻辑。文件扫描、原始像素解码、直方图、容差、PSNR/SSIM、文档内容提取、N 路文本行对齐。
- `widgets.py`：图片视口、等尺寸多图容器、直方图绘制、文本着色、文件列表模型和缩略图委托、浅/深主题。
- `app.py`：Qt 窗口、后台任务、菜单快捷键、过滤、会话持久化、报告导出。
- `demo.py`：程序化生成 16bit 示例图和文本，不依赖训练数据。
- `smoke.py`：打包后启动、解码、比较、窗口绘制测试。

## 后台任务

扫描和内容计算使用独立 QThreadPool（最多 2 个任务），缩略图使用另一线程池（最多 2 个任务），不等待指标计算。
每次任务都有编号和取消事件；仅当前任务的结果可更新视图。快速切换或刷新后，旧结果被丢弃。
扫描完成后缩略图持续后台预载，当前可见行可优先提交。内存缓存最多 256 张，其余保留于本次运行的临时磁盘缓存；刷新按 generation 隔离。
关闭窗口先取消任务，等待正在进行的读操作返回；单次网络文件读取不能强制中断。

## 正确性约束

1. 原始来源只读。新增写回/同步功能必须独立设计，不能混入比较流程。
2. 图片指标基于解码后的原始分辨率和原始位深；显示转换不能进入指标计算。
3. 尺寸不同不能静默缩放后报告“相同”。
4. 大小相同不是内容相同。目录快速扫描必须保留“待校验”。
5. 文档提取失败/截断不能报告完整内容相同。
6. SSIM 基础结果为 Y′；界面按直方图选择 RGB 三通道平均、Y′ 或 HSV 的 V，并明确标注。
7. UI 的 QPixmap 仅在主线程创建；后台仅返回 numpy 数组或 QImage。
8. 读取 Unicode/UNC 路径时，OpenCV 使用 `np.fromfile + imdecode`，避免 Windows 路径编码问题。

## 测试与打包

核心测试包含低 2bit 差异、容差边界、Alpha、位深混合、SSIM/PSNR 解析参考值、直方图总数、文档提取、4 路缺失和文本插入删除。
界面测试覆盖 2/3/4 路、三种直方图、缺失基准、快速切换、像素缩放、分割显示等。
界面测试循环使用 `processEvents + time.sleep` 释放 Python GIL，避免 Qt 测试等待阻塞后台 Python 线程。

`build.cmd` 先执行核心测试，再按 `PrismCompare.spec` 打包。使用 onedir 以缩短启动时间，且便于替换 Qt DLL 和排查依赖。
打包不是安装器，也未做代码签名。不要修改源码后直接分发旧 exe，必须重新执行 build。

## 后续扩展建议

- ROI 选择与局部直方图/指标。
- 图片差异连通区域导航、指标 CSV 和差异图导出。
- 按序号/用户配对表匹配文件夹，而不只按相对路径。
- 多标签会话、可配置快捷键、布局持久化。
- PDF 页面视觉对比或 OCR 作为独立可选模块。
- 在显示链路显式实现色彩管理或 HDR 色调映射，保持原始码值比较独立。

上述项目是扩展方向，不代表当前已实现。

image_bundle 的 ready 回调只提交已解码的图像快照，随后在工作线程完成直方图和指标。ImageCache 带锁且限制 192 MiB；调容差仅重建分类图，不重复 SSIM。

容差使用固定 40ms 调度器而非静止后 debounce，同一时刻只有一个阈值任务，结束后合并处理最新值。rethreshold_bundle 不读取源图，保留 PSNR/SSIM/MAE。fullscreen.py 共享已上传的 QPixmap；shell_bridge.stop 在窗口关闭第一步释放本进程服务端，不能 removeServer 以免误删新进程服务。

0.1.11：color_space.py 共享 RGB/Y/YUV/HSV 投影定义；difference_space 和 difference_basis 标注差异图口径，equal 仍按原始归一化 RGB(A) 判定。metric_table.py 固定尺寸避免数值引起布局变化。focus_controls.py 以根窗口子控件悬浮，不插入布局；专注 mode 隐藏信息叠层，fit 去掉 QGraphicsView 默认 2px 留边。


0.1.13: `image_bundle(compute_comparisons=False)` returns a dirty bundle without metrics when the inspector is hidden. Opening it recomputes from memory. RGB/HSV skip unused luma SSIM; transformed-space magnitude caches preserve float64 threshold classification. `tests/test_deferred.py` verifies no hidden computation or source reread. Mouse crosshairs repaint only local rectangles.
