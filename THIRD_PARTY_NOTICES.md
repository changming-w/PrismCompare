# Third-party components

Prism Compare uses the following packages. Copyright and license rights remain with their respective authors.

| Component | Purpose | License family / upstream |
|---|---|---|
| PySide6 / Qt for Python | Desktop UI | LGPLv3 / GPLv3 / commercial options; https://doc.qt.io/qtforpython-6/licenses.html |
| shiboken6 | Qt Python bindings | Qt for Python licensing |
| NumPy | Numeric arrays | BSD-3-Clause; https://numpy.org/ |
| OpenCV / opencv-python-headless | Image decoding and processing | Apache-2.0 and bundled third-party notices; https://opencv.org/ |
| pypdf | PDF text extraction | BSD-3-Clause; https://pypdf.readthedocs.io/ |
| python-docx | Word text extraction | MIT; https://python-docx.readthedocs.io/ |
| lxml | XML support | BSD-style and underlying libraries; https://lxml.de/ |
| openpyxl / et-xmlfile | Spreadsheet extraction | MIT; https://openpyxl.readthedocs.io/ |
| PyInstaller | Build tooling and bootloader | GPL with distribution exception; https://pyinstaller.org/ |

Installed distribution metadata under `.venv/Lib/site-packages` includes the specific package license files. The build script collects these notices into the portable distribution's `licenses` directory. Keep that directory and the Qt DLLs when redistributing. Review applicable upstream terms before external distribution; this file is an inventory, not a substitute for the licenses.
