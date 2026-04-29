# KeyLife — Security TODO

Findings dell'audit del 2026-04-27. Tutti chiusi.

## Critici / alta

- [x] **Privacy: rimuovere sequenza ricostruibile dal monitor UI**
  `backend/app/ui/monitor.py` — rimosso il `deque` di `KeyEvent` e la lista
  cronologica "Recent events". Ora il monitor mostra solo l'ultimo evento
  (senza timestamp) e la tabella aggregata per `(vk, scancode)`.

- [x] **Atomicità snapshot+flush (data loss)**
  `backend/app/aggregator/buffer.py` + `backend/app/service/daemon.py` —
  aggiunto `Aggregator.restore_snapshot()`; `_flush_once` ora rimette indietro
  i contatori se `flush_snapshot` solleva.

- [x] **Serializzare flush manuale e periodico**
  `backend/app/service/daemon.py` — aggiunto `self._flush_lock` in
  `KeyLifeDaemon`; `_flush_once` lo acquisisce per l'intera operazione.

## Medi

- [x] **`check_same_thread=False` documentato**
  `backend/app/storage/session.py` — aggiunto commento che lega il flag
  all'invariante "single writer via `_flush_lock`".

- [x] **Secret key generata al primo avvio**
  `backend/app/core/config.py` — `get_settings()` ora genera un token
  `secrets.token_urlsafe(32)` su `backend/.secret_key` (mode 0o600, O_EXCL)
  se assente; rifiuta di partire con il placeholder. `.secret_key` è già in
  `.gitignore`.

## Bassi

- [x] **Log del path DB**
  `backend/app/service/daemon.py` — logga solo `db_filename`, non il path
  completo che includerebbe lo username.

- [x] **Hook setup timeout esplicito**
  `backend/app/hook/win_hook.py` — `start()` ora solleva `TimeoutError` se
  `_ready` non viene settato entro 5s, anziché tornare silenziosamente.

- [x] **`Aggregator._down` con TTL anti-stale**
  `backend/app/aggregator/buffer.py` — `_down` è ora `dict[(vk,sc) → ts]`;
  un DOWN successivo a 10s di "hold" è trattato come pressione fresca,
  evitando che un UP perso blocchi i conteggi.

---

Findings del secondo audit (2026-04-27, post-merge). Tutti chiusi.

## Alti

- [x] **Hook callback inghiotte eccezioni in silenzio**
  `backend/app/hook/win_hook.py` — il `except Exception: pass` nel callback
  Win32 ora logga via `logging.exception(...)`. Le eccezioni continuano a
  non attraversare il confine Win32, ma un listener rotto non degrada più
  silenziosamente.

- [x] **`_down` accumulo monotono di entry stale (memory leak + count loss)**
  `backend/app/aggregator/buffer.py` — il TTL filtrava il prossimo DOWN ma
  non rimuoveva mai le entry orfane (UP perso per focus change, sleep,
  secure desktop, `SendInput` di soli DOWN). `take_snapshot` ora fa sweep
  delle entry più vecchie di `_DOWN_STALE_MS`: il dict resta bounded e la
  prossima ripressione entro 10s non viene più scartata come auto-repeat.

## Medi

- [x] **Signal handler non idempotente**
  `backend/app/__main__.py` — `_handle_sig` ora controlla
  `stop_evt.is_set()` prima di settare: una seconda Ctrl+C durante lo
  shutdown non perturba più lo stato.

## Bassi

- [x] **WAL senza autocheckpoint esplicito**
  `backend/app/storage/session.py` — aggiunto
  `PRAGMA wal_autocheckpoint=100;` per evitare che il sidecar `-wal`
  cresca senza limite tra una close e l'altra.

- [x] **`db_filename` non sanificato (path traversal locale via env)**
  `backend/app/core/config.py` — `db_path` ora applica `os.path.basename`
  al `db_filename`: env var malevole tipo `../../evil.db` non possono più
  redirigere il DB fuori da `data_dir`.

---

## Encryption-at-rest (2026-04-29)

Il DB è cifrato con SQLCipher 4 (default settings). La chiave è 256 bit
random hex-encoded, generata al primo avvio e salvata nel Windows
Credential Manager via `keyring`. Slot:
  - `KeyLife/db` su build frozen (PyInstaller / installer).
  - `KeyLife-dev/db` su checkout sorgente.

### Threat model

**Cosa proteggiamo**: esfiltrazione del solo `data_dir`. Backup cloud
sync che leakano, immagine forense del disco, laptop senza BitLocker che
viene rubato. La chiave non viaggia con il file `.sqlite` perché vive
nel keychain (DPAPI, legato al profilo Windows dell'utente).

**Cosa NON proteggiamo**:
  - Malware che gira come l'utente. DPAPI sprotegge la chiave senza
    challenge → qualunque processo nostro-utente legge sia il keychain
    sia il DB. Non è il threat model: per quello servono strumenti
    diversi (EDR, app sandboxing).
  - Attacco con credenziali Windows compromesse. Stessa storia: DPAPI
    è bound all'account, non alla password in input.

### Migrazione e recovery

- Al primo avvio post-upgrade un DB plaintext esistente viene migrato
  in-place via `sqlcipher_export()`. Il file originale finisce in
  `<db>.pre-encrypt.bak` e va cancellato a mano dall'utente quando ha
  verificato che tutto funziona.
- Se la chiave nel Credential Manager sparisce mentre il DB è cifrato,
  `run.py:_ensure_db_state` esce con codice 2 e messaggio chiaro: non
  cancella nulla. Recovery: cancellare il `.sqlite` cifrato (perdita
  totale dei dati) oppure rinominare un `.pre-encrypt.bak` salvato
  precedentemente.

### Punti di iniezione del PRAGMA key

Tre engine indipendenti aprono il DB; tutti emettono `PRAGMA key` come
*primo* statement della connection:
  - `backend/app/storage/session.py:_set_sqlite_pragmas` — engine del
    daemon/UI/API.
  - `backend/alembic/env.py:_apply_key` — engine di Alembic, isolato per
    `engine_from_config()`.
  - `backend/app/storage/encryption.py` — connessioni dirette per detect
    e migrate.

L'invariante "single writer via `_flush_lock` + WAL readers" non cambia:
SQLCipher è trasparente sopra il dialect SQLite.

---

## Per-application tracking (2026-04-30, opt-in)

Feature opzionale (default OFF) che attribuisce ogni keystroke
all'eseguibile della finestra in foreground al momento del DOWN. Tre
tabelle nuove (`daily_app_counts`, `hourly_app_totals`, `app_icons`) +
una kv (`app_settings`) che persiste opt-in e blocklist.

### Cosa salviamo / cosa NO

**Salviamo** solo il basename dell'exe (`chrome.exe`, `code.exe`), in
lowercase. Più due bucket di fallback:
  - `unknown` — `OpenProcess` rifiutato (anti-cheat, lsass, processi protetti).
  - `system` — HWND==0 (lockscreen, secure desktop, transizioni di focus).

**Non salviamo mai**:
  - Window title (rivela URL del browser, nomi file, clienti del meeting).
  - Full path dell'exe (rivela username e installazioni).
  - Cross-tab `(vk × exe)`: per ora teniamo le due dimensioni ortogonali
    perché la cardinalità del prodotto esplode per use case che ancora
    non abbiamo.

### Threat model (delta rispetto al baseline)

Il dato è significativamente più sensibile dei conteggi per-tasto: la
lista delle app rivela software dating/banking/terapia/gambling/lavoro
proprietario. Per questo:
  - **Encryption-at-rest sopra è ora load-bearing**, non cosmetica.
  - Tracking è **opt-in con disclosure dialog**: l'utente vede cosa
    viene salvato prima del primo enable.
  - **Blocklist** utente: lista di exe da non registrare mai (default
    vuota). Comparazione su basename lowercase.
  - **Forget app**: bottone in Settings che fa DELETE su tutte le tabelle
    per uno specifico exe (incluso `app_icons`).

### Architettura

- `backend/app/hook/foreground.py` — `ForegroundHook`: thread message-only
  con `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)`, cache `(exe_name, exe_path)`
  letta dall'aggregator senza syscall per evento.
- `backend/app/hook/icons.py` — `extract_icon_png()`: GDI
  (`ExtractIconExW` → `GetIconInfo` → `GetDIBits`) + Pillow per il PNG
  finale 32x32 RGBA.
- `backend/app/aggregator/buffer.py` — `set_exe_provider(callable)`
  attiva il tracking; il callable può ritornare `None` (blocklist) o lo
  string del bucket. Snapshot/restore esteso per `per_app_daily` e
  `per_app_hourly`.
- `backend/app/service/daemon.py` — orchestra: legge `app_settings`,
  avvia/ferma foreground hook + icon worker, costruisce l'`exe_provider`
  con la blocklist snapshot-ata. `refresh_per_app_state()` per hot-reload
  via API senza riavvio.
- `backend/app/api/routes.py` — endpoint `/api/settings/per-app` (GET/PUT),
  `/api/apps/summary`, `/api/apps/hourly`, `/api/app-icons/{exe}` (con
  ETag), `/api/apps/forget`.

### Limitazioni note

- App UWP (Calculator, Photos, Edge, ...): finiscono tutte sotto
  `applicationframehost.exe`. Risolverlo richiede walk dei child window
  alla ricerca di un PID diverso — TODO follow-up.
- Toggle off → on → off: i counts in-memory non flushed al toggle off
  vengono **scartati** (vedi `Aggregator.set_exe_provider(None)`).
  Privacy-first: se l'utente disabilita, intende non persistere quanto
  raccolto nel buffer.
- L'icona è memo-izzata in `_icons_known` anche su fallimento di
  estrazione: nel worst case un exe resta senza icona (frontend mostra
  placeholder), ma non riaccodiamo mai lo stesso job in loop.
