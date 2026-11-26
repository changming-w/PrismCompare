"""Theme-aware vector artwork for the comparison toolbar."""
from functools import lru_cache
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer

# Every command uses the same 24-unit grid and stroke width.
SHAPES = {
    'file': ('blue', '<path d="M6 3h8l4 4v14H6zM14 3v5h4"/><path stroke="@accent" d="M9 12h6m-6 4h6"/>'),
    'folder': ('amber', '<path d="M3 7m0 12V6h6l2 2h10v11z"/><path stroke="@accent" d="M4 11h16"/>'),
    'history': ('blue', '<path d="M4 9a8 8 0 1 1 0 7M4 4v5h5"/><path stroke="@accent" d="M12 7v5l3 2"/>'),
    'play': ('green', '<circle cx="12" cy="12" r="9"/><path fill="@accent" stroke="none" d="m10 7.5 6 4.5-6 4.5z"/>'),
    'stop': ('rose', '<circle cx="12" cy="12" r="9"/><rect fill="@accent" stroke="none" x="8.5" y="8.5" width="7" height="7" rx="1"/>'),
    'heat': ('rose', '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path stroke="@accent" d="M8 15v-3m4 3V8m4 7v-5"/>'),
    'difference': ('violet', '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path stroke="@accent" d="m7 15 3-6 3 3 4-4"/>'),
    'blend': ('green', '<circle cx="9" cy="12" r="5.5"/><circle stroke="@accent" cx="15" cy="12" r="5.5"/>'),
    'wipe': ('blue', '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path fill="@accent" fill-opacity=".26" stroke="none" d="M5 6h7v12H5z"/><path stroke="@accent" d="M12 3v18"/>'),
    'swap': ('blue', '<path d="M4 8h16l-4-4m4 4-4 4M20 16H4l4-4m-4 4 4 4"/>'),
    'align': ('amber', '<path d="M3 4h18M3 20h18M5 4v12h5V4m4 0v9h5V4"/><path stroke="@accent" d="M14 17h5"/>'),
    'fit': ('blue', '<rect x="4" y="4" width="16" height="16" rx="2"/><path stroke="@accent" d="M11 8H8v3m5-3h3v3m-8 2v3h3m5-3v3h-3"/>'),
    'actual': ('blue', '<rect x="4" y="4" width="16" height="16" rx="2"/><path stroke="@accent" d="m8 10 1.5-1.5V16m5-6 1.5-1.5V16"/>'),
    'prev': ('blue', '<path d="m14.5 6-6 6 6 6"/>'),
    'next': ('blue', '<path d="m9.5 6 6 6-6 6"/>'),
    'prevdiff': ('amber', '<path d="m7 14 5-5 5 5"/><path stroke="@accent" d="M6 5h12"/>'),
    'nextdiff': ('amber', '<path d="m7 10 5 5 5-5"/><path stroke="@accent" d="M6 19h12"/>'),
    'focus': ('blue', '<path d="M3 9V3h6m6 0h6v6M3 15v6h6m6 0h6v-6"/><rect stroke="@accent" x="8" y="8" width="8" height="8" rx="1"/>'),
    'concentrate': ('violet', '<path d="M2.5 12c5-7.5 14-7.5 19 0-5 7.5-14 7.5-19 0Z"/><circle stroke="@accent" cx="12" cy="12" r="3"/>'),
}

LIGHT_ACCENTS={'blue':'#2066a8','amber':'#936020','green':'#167c63','rose':'#bc4758','violet':'#7054a8'}
DARK_ACCENTS={'blue':'#91c3ff','amber':'#f5ca87','green':'#72dfb7','rose':'#ff9da8','violet':'#c5b1ff'}

@lru_cache(maxsize=64)
def command_icon(name,dark=False):
    color,art=SHAPES[name]
    accent=(DARK_ACCENTS if dark else LIGHT_ACCENTS)[color]
    ink='#dce7f6' if dark else '#35475f'
    icon=QIcon()
    for mode,stroke,highlight in (
        (QIcon.Mode.Normal,ink,accent),
        (QIcon.Mode.Disabled,'#677990' if dark else '#a1aebf','#677990' if dark else '#a1aebf'),
    ):
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g stroke="{stroke}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none">{art.replace("@accent",highlight)}</g></svg>'
        renderer=QSvgRenderer(QByteArray(svg.encode()))
        for dpr in (1,2):
            image=QPixmap(22*dpr,22*dpr)
            image.fill(Qt.GlobalColor.transparent)
            painter=QPainter(image)
            renderer.render(painter)
            painter.end()
            image.setDevicePixelRatio(dpr)
            icon.addPixmap(image,mode)
    return icon
