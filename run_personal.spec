# -*- mode: python ; coding: utf-8 -*-
#
# Wrapper personale: forza KEYLIFE_PERSONAL_BUILD=1 e poi delega tutto a
# run.spec. Da lanciare con:
#
#     .\.venv\Scripts\pyinstaller.exe run_personal.spec
#
# Tutta la logica (build frontend, hidden imports, firma, ISCC con
# installer_local.iss) vive in run.spec — questo file esiste solo per
# evitare di dover ricordare di settare la variabile d'ambiente.

import os
from pathlib import Path

os.environ['KEYLIFE_PERSONAL_BUILD'] = '1'
print('[run_personal.spec] KEYLIFE_PERSONAL_BUILD=1 forzato; delego a run.spec.')

# Eseguo run.spec nello stesso namespace globale così le sue assegnazioni
# top-level (a, pyz, exe, coll) sono visibili a PyInstaller dopo questo
# file — è la convenzione che PyInstaller usa per riconoscere l'output di
# uno spec. SPECPATH è già impostato da PyInstaller alla dir di QUESTO
# file (che coincide con quella di run.spec), quindi i path relativi
# usati in run.spec restano corretti.
_main_spec = Path(SPECPATH) / 'run.spec'
exec(_main_spec.read_text(encoding='utf-8'), globals())
