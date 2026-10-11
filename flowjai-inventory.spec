# -*- mode: python ; coding: utf-8 -*-
#
# Folder build (onedir): dist/flowjAI/flowjai-inventory.exe + dist/flowjAI/_internal/
# Chosen over a single-file exe because a single file unpacks ~100 MB to a temp
# folder on EVERY start (slow), and that self-extracting pattern is what hospital
# antivirus most often quarantines.

import os
import sys
from PyInstaller.utils.hooks import collect_submodules

sys.path.insert(0, os.path.abspath('backend'))   # so collect_submodules can find app/ and tools/

datas = [
    (os.path.join('frontend', 'dist'), os.path.join('frontend', 'dist')),
    (os.path.join('backend', 'alembic.ini'), 'backend'),
    (os.path.join('backend', 'migrations'), os.path.join('backend', 'migrations')),
]
binaries = []
hiddenimports = [
    'passlib.handlers.bcrypt',
    'uvicorn.logging',
    'uvicorn.loops.auto',
    'uvicorn.protocols.http.auto',
    'app.models',
    'app.routers',
    'app.services',
    # numpy — only the submodules actually used (not tests, f2py, random benchmarks, etc.)
    'numpy',
    'numpy.core',
    'numpy.core.multiarray',
    'numpy.core._dtype',
    'numpy.lib',
    'numpy.lib.format',
    'numpy.linalg',
    'numpy.linalg.lapack_lite',
    'numpy.fft',
    # pandas — only the core and IO submodules used
    'pandas',
    'pandas.core',
    'pandas.core.api',
    'pandas.io',
    'pandas.io.sql',
    'pandas._libs',
    'pandas._libs.tslibs',
    'pandas._libs.interval',
    'pandas._libs.hashtable',
    'pandas._libs.parsers',
    'pandas._libs.join',
    'pandas._libs.testing',
    # SQLAlchemy dialects needed
    'sqlalchemy.dialects.sqlite',
    # FastAPI imports the multipart parser lazily; without it every File/Form
    # route (shipment QC evidence upload) fails and the app won't start.
    'multipart',
    # --transfer-db mode
    'tools.transfer_db',
    # Antibody import of .xlsx files: pandas loads its Excel reader lazily
    'openpyxl',
    'pandas.io.excel._openpyxl',
]
# Every router / service module, including ones imported inside functions
hiddenimports += collect_submodules('app')

# Alembic migration environment is loaded dynamically by run.py and won't be
# discovered by static analysis.
hiddenimports += [
    'alembic',
    'alembic.config',
    'alembic.runtime.migration',
    'logging.config',
]

a = Analysis(
    ['run.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # strip tests, docs, benchmarks
        'numpy.tests', 'numpy.doc', 'numpy.core.overlap', 'numpy.random.tests',
        'numpy.typing.tests', 'numpy.ma.tests', 'numpy.matrixlib.tests',
        'numpy.fft.tests', 'numpy.polynomial.tests', 'numpy.lib.tests',
        'pandas.tests', 'pandas.io.clipboard',
        # unused optional backends and heavy libs
        'scipy', 'matplotlib', 'PIL', 'Pillow', 'cv2',
        'tkinter', 'Tkinter', '_tkinter', 'tcl',
        'test', 'doctest', 'pytest',
        'xlsxwriter', 'xlrd', 'xlwt',
        'httpx', 'httpcore',
        'uvloop', 'httptools', 'watchfiles', 'websockets',
        'pyyaml', '_yaml',
        'urllib3', 'chardet', 'certifi', 'charset_normalizer',
        'pip',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='flowjai-inventory',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='flowjAI',
)
