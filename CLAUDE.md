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
