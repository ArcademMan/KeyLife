# -*- mode: python ; coding: utf-8 -*-

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

try:
    import tomllib  # 3.11+
except ModuleNotFoundError:  # pragma: no cover — 3.10 fallback
    import tomli as tomllib  # type: ignore[no-redef]


def _read_version() -> str:
    pyproject = Path(SPECPATH).resolve() / 'pyproject.toml'
    return tomllib.loads(pyproject.read_text(encoding='utf-8'))['project']['version']


APP_VERSION = _read_version()
print(f'[spec] KeyLife version: {APP_VERSION}')


# --- Personal build switch -------------------------------------------------
# Set KEYLIFE_PERSONAL_BUILD=1 to produce a build that:
#   1. sets uiAccess=true in the manifest via PyInstaller's uac_uiaccess,
#   2. signs the exe with the personal cert (CN=ArcademMan) found in the
#      current user's certificate store via signtool /n,
#   3. drives ISCC against installer_local.iss (which imports the cert as
#      a machine root and installs into Program Files).
# All three pieces are required together: a uiAccess binary that isn't
# signed by a trusted root cert won't be allowed to start by Windows.
# These artifacts live in gitignored paths so the public repo is never tied
# to the personal CA.
PERSONAL_BUILD = os.environ.get('KEYLIFE_PERSONAL_BUILD') == '1'
PERSONAL_INSTALLER = Path(SPECPATH).resolve() / 'installer_local.iss'
SIGN_SUBJECT = 'ArcademMan'  # public CN, not a secret

if PERSONAL_BUILD:
    print('[spec] PERSONAL build attivo (uiAccess + sign + installer_local).')
    if not PERSONAL_INSTALLER.is_file():
        raise FileNotFoundError(
            f'KEYLIFE_PERSONAL_BUILD=1 ma {PERSONAL_INSTALLER} mancante. '
            'Crea l\'installer personale prima di builddare.'
        )
else:
    print('[spec] PUBLIC build (no uiAccess, no signing).')


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
        ('backend/app/api/data', 'backend/app/api/data'),
        ('frontend/dist', 'frontend/dist'),
    ],
    hiddenimports=[
        # Importati dinamicamente da Alembic env.py / migration scripts.
        'app',
        'app.core.config',
        'app.storage.models',
        # uvicorn/fastapi caricano i loro impl dinamicamente via stringhe;
        # senza questi il `--api` thread crasha silenziosamente nell'exe e
        # il bottone WEB resta disabilitato.
        *collect_submodules('uvicorn'),
        *collect_submodules('fastapi'),
        *collect_submodules('starlette'),
        *collect_submodules('anyio'),
        *collect_submodules('h11'),
        # SQLCipher: il .pyd con libsqlcipher statica viene incluso
        # automaticamente, ma il package usa import lazy del submodulo
        # dbapi2 — esplicitiamolo per non rischiare un MissingModule.
        'sqlcipher3',
        'sqlcipher3.dbapi2',
        # keyring: il backend giusto su Windows (WinVaultKeyring) è
        # selezionato dinamicamente a runtime via entry_points; PyInstaller
        # non li vede senza help. Includiamo l'intero subtree dei backend.
        'keyring',
        'keyring.backend',
        'keyring.backends',
        *collect_submodules('keyring.backends'),
        # WinVaultKeyring chiama in pywin32 → win32cred per parlare con il
        # Credential Manager. Senza questo la prima keyring.set_password
        # fallisce con NoKeyringError dentro al bundle.
        'win32cred',
        'win32ctypes',
        'pywintypes',
        # Pillow per il rendering delle icone exe → PNG. _imaging è il
        # modulo C nativo, gli altri spesso si importano dinamicamente.
        'PIL',
        'PIL.Image',
        'PIL._imaging',
        *collect_submodules('PIL'),
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

_exe_kwargs = {}
if PERSONAL_BUILD:
    # uac_uiaccess=True fa scrivere a PyInstaller `uiAccess="true"` nel
    # manifest del bootloader. NON usiamo `manifest=` con un XML custom
    # perché PyInstaller in 6.x sanitizza l'attributo uiAccess
    # riscrivendolo a "false" — e tentare di sovrascriverlo a posteriori
    # con mt.exe rompe il PKG archive che PyInstaller appende a fine exe
    # (il bootloader poi non riesce più a caricarsi).
    _exe_kwargs['uac_uiaccess'] = True

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
    **_exe_kwargs,
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


# --- Post-build: sign exe (personal only) ---------------------------------
# Firma l'exe con il cert personale dal CurrentUser\My (subject CN=ArcademMan).
# Va fatta dopo che PyInstaller ha finito di scrivere/appendere il PKG, e
# prima di passare l'exe a Inno Setup. Niente .pfx letta da disco, niente
# password: signtool usa la chiave privata DPAPI dello store utente.

def _find_signtool() -> str | None:
    candidate = shutil.which('signtool')
    if candidate:
        return candidate
    sdk_root = Path(r'C:\Program Files (x86)\Windows Kits\10\bin')
    if not sdk_root.is_dir():
        return None
    matches: list[Path] = []
    for ver_dir in sdk_root.iterdir():
        if not ver_dir.is_dir():
            continue
        for arch in ('x64', 'x86'):
            p = ver_dir / arch / 'signtool.exe'
            if p.is_file():
                matches.append(p)
    if not matches:
        return None
    matches.sort(key=lambda p: p.parent.parent.name, reverse=True)
    return str(matches[0])


def _sign_exe() -> None:
    if not PERSONAL_BUILD:
        return
    project_root = Path(SPECPATH).resolve()
    target = project_root / 'dist' / 'keylife' / 'keylife.exe'
    if not target.is_file():
        raise FileNotFoundError(f'exe da firmare non trovato: {target}')
    signtool = _find_signtool()
    if signtool is None:
        raise RuntimeError(
            'signtool.exe non trovato. Installa Windows 10/11 SDK '
            'oppure metti signtool nel PATH.'
        )
    cmd = [
        signtool, 'sign',
        '/n', SIGN_SUBJECT,           # cert per subject CN, dal CurrentUser\My
        '/fd', 'SHA256',              # digest del file
        '/td', 'SHA256',              # digest del timestamp
        '/tr', 'http://timestamp.digicert.com',
        str(target),
    ]
    print(f'[spec] Firmo {target.name} con cert subject="{SIGN_SUBJECT}"')
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f'signtool ha fallito (exit {result.returncode})')


_sign_exe()


# --- Post-build: compila l'installer Inno Setup ---------------------------
# Eseguito automaticamente al termine di `pyinstaller run.spec`.
# Salta in silenzio se ISCC non è installato o se l'iss manca.

def _build_installer() -> None:
    project_root = Path(SPECPATH).resolve()
    iss = (
        project_root / 'installer_local.iss' if PERSONAL_BUILD
        else project_root / 'installer.iss'
    )
    if not iss.is_file():
        print(f'[spec] {iss.name} non trovato, salto build Inno Setup.')
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

    print(f'[spec] Compilazione installer: {iscc} {iss} /DMyAppVersion={APP_VERSION}')
    result = subprocess.run(
        [iscc, f'/DMyAppVersion={APP_VERSION}', str(iss)],
        cwd=str(project_root),
    )
    if result.returncode != 0:
        print(f'[spec] ISCC ha restituito {result.returncode}', file=sys.stderr)


_build_installer()
