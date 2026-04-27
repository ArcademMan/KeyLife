# -*- mode: python ; coding: utf-8 -*-

import shutil
import subprocess
import sys
from pathlib import Path


# --- Pre-build: compila il frontend Vite -----------------------------------
# Eseguito prima dell'Analysis così `frontend/dist` è fresco quando viene
# bundle-ato nei datas più sotto.

def _build_frontend() -> None:
    project_root = Path(SPECPATH).resolve()
    frontend = project_root / 'frontend'
    if not (frontend / 'package.json').is_file():
        print('[spec] frontend/package.json non trovato, salto npm build.')
        return

    npm = shutil.which('npm') or shutil.which('npm.cmd')
    if npm is None:
        raise RuntimeError('npm non trovato nel PATH: impossibile buildare il frontend.')

    if not (frontend / 'node_modules').is_dir():
        print(f'[spec] node_modules mancante, eseguo `npm install` in {frontend}')
        subprocess.run([npm, 'install'], cwd=str(frontend), check=True, shell=False)

    print(f'[spec] Build frontend: {npm} run build (cwd={frontend})')
    subprocess.run([npm, 'run', 'build'], cwd=str(frontend), check=True, shell=False)


_build_frontend()


a = Analysis(
    ['run.py'],
    pathex=['backend'],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
        ('assets/icon.png', 'assets'),
        ('backend/alembic.ini', 'backend'),
        ('backend/alembic', 'backend/alembic'),
        ('frontend/dist', 'frontend/dist'),
    ],
    hiddenimports=[
        # Importati dinamicamente da Alembic env.py / migration scripts.
        'app',
        'app.core.config',
        'app.storage.models',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='keylife',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='keylife',
)


# --- Post-build: compila l'installer Inno Setup ---------------------------
# Eseguito automaticamente al termine di `pyinstaller run.spec`.
# Salta in silenzio se ISCC non è installato o se installer.iss manca.

def _build_installer() -> None:
    project_root = Path(SPECPATH).resolve()
    iss = project_root / 'installer.iss'
    if not iss.is_file():
        print('[spec] installer.iss non trovato, salto build Inno Setup.')
        return

    candidates = [
        shutil.which('ISCC'),
        r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        r'C:\Program Files\Inno Setup 6\ISCC.exe',
    ]
    iscc = next((c for c in candidates if c and Path(c).is_file()), None)
    if iscc is None:
        print('[spec] ISCC non trovato (Inno Setup 6 non installato?), salto.')
        return

    print(f'[spec] Compilazione installer: {iscc} {iss}')
    result = subprocess.run([iscc, str(iss)], cwd=str(project_root))
    if result.returncode != 0:
        print(f'[spec] ISCC ha restituito {result.returncode}', file=sys.stderr)


_build_installer()
