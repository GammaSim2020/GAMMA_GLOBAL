# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**GAMMA_TWRAPS** is a Python-based Air Traffic Control (ATC) training simulator for the LECG airport variant. It simulates ground and air operations with real-time radar displays, flight strip management (OSF — *Oficina Suelo Funcional*), and a pilot/controller interface. The networking layer uses Twisted; the GUI uses Tkinter/Tix.

## Running the Application

```
python GAMMA.py           # Main launcher
python GAMMA_Start.py     # Version updater/launcher
```

The application is run directly. The *Editor* is launched through `lib/Editor.py` (invoked via `lib/Pantalla.py`).

## Language & Dependencies

**Python 2.7 exclusively — non-negotiable.** No f-strings, no type hints, no `pathlib`, no walrus, no `async`. Many legacy modules use `cPickle` and source encoding `iso8859-15`; preserve both. `print` statements may appear bare or via `from __future__ import print_function` — match the style of the file you are editing.

Key packages: `twisted`, `openpyxl`, `Pillow`, `matplotlib`, `numpy`, `dill`, `tix` (Tkinter extension).

## Parallel Version

A sibling working copy lives at `C:\GAMMA`. Multiple GAMMA versions coexist on disk; **do not assume a change in this tree applies to the others**. When making a change here, ask explicitly whether it should be replicated to `C:\GAMMA` (or other `C:\GAMMA_*` / `C:\Versiones-OSF\*` trees).

## Architecture

### Client-Server Model

- **Server**: `lib/GTA.py` — the simulation engine (*Generador de Tráfico Aéreo*). Manages all aircraft states via a `_dispatch_table` of 40+ command handlers. Runs a Twisted TCP server.
- **Clients**: `lib/UCS.py` (ATC radar display), `lib/Pseudopilot.py` (virtual pilot interface). Connect via `lib/RemoteClient.py`, which deserializes compressed pickle messages in a thread with a queue.
- **Local mode**: `GAMMA.py` can start GTA and UCS in-process without networking.

### Key Modules

| Module | Role |
|---|---|
| `lib/GTA.py` | Simulation engine: aircraft movement, ATC commands, weather, runway config |
| `lib/Aircraft.py` | Aircraft data model: flight phases, performance, navigation |
| `lib/FIR.py` | FIR/airport data: sectors, procedures, waypoints, `ESCENARIO` config including `taxi_ias` |
| `lib/RaDisplay.py` | Base radar display: map rendering, zoom/pan, sector switching, settings save/restore |
| `lib/UCS.py` | ATC display extending RaDisplay: tracks, labels, strips, correlation |
| `lib/Pseudopilot.py` | Pilot display extending RaDisplay: flight plan, navigation, approach |
| `lib/RaElements.py` | UI component library: `VisTrack`, `ATCBahia`, dialogs, strip widgets (~8500 lines) |
| `lib/osf/OSF.py` | Ground operations strips (OSF): departure/arrival zones, extended strips (`fichas extendidas`) |
| `lib/osf/PrevDesp.py` | Departure preview window for CLR bahia |
| `lib/ConfMgr.py` | JSON config manager (`gamma_settings.json`); accumulates in memory, writes atomically on `save()` |
| `lib/Exercise.py` | Exercise file parser (Excel `.xlsx` and `.eje` formats) |
| `lib/BADA.py` | Eurocontrol BADA aircraft performance data |
| `lib/MathUtil.py` | Navigation math: great-circle distance, bearing, intercept geometry |

### Configuration System

`ConfMgr.py` wraps `gamma_settings.json`. Structure:
- Top-level `Global` section for app-wide settings
- Per-layout sections `Layout1`, `Layout2`, `Layout3`
- Other sections: `Brightness`, `Aux_Tabs`, `APP`, `Maps`

`GAMMA.ini` is now legacy — only the `ver` key is still read from it via ConfigParser.

Settings are accumulated in memory via `save_state()` methods in each display, then written to disk by `conf.save()` on exit (via `atexit` in `GAMMA.py`).

### OSF Module (`lib/osf/`)

- `OSF.py` uses a singleton pattern (`get_instance()`) to manage one window per `bahia_type` (`LCL`, `GND`, `CLR`).
- Sectors can be combos like `'LCL,GND'` — always split on `','` before comparing against `fir.sectors`.
- Extended strips (*fichas extendidas*) have parent-child relationships within OSF.
- Key OSF fields: `sid_ext`, `vel`, `cfl`, `airline`, `qnh`, `cssr`, `eobt`, `eldt`, `park`.

### Multi-display invariants (recurring bug source)

These have caused several bugs already — respect them when touching display setup, `save_state`, or window lifecycle:

- **`ATCBahia` and OSF windows are created only on `disp_number == 1`.** Any new construction site for these widgets must include `and self.disp_number == 1` in the guard. Secondary displays must reuse the existing instance.
- **For `disp_number > 1`, do not recompute `instance_key` from the secondary display's sector** (Layout2 may differ from Layout1 and produce a different key, missing the singleton). Reuse the first live entry in `OSF._instances.values()`.
- **Defensive access**: when iterating displays or reacting to events, use `hasattr(radisp, 'atc_bahia')` / `hasattr(self, 'atc_bahia')`. Display 2 has no `atc_bahia` attribute and will raise otherwise.

### Flight-level rounding (CFL / TFL / RFL)

Levels are stored as floats but rendered as integers. **Never use `int(x)`** for label text or dialog defaults — it truncates and turns a `299.999...` (an FL300 aircraft a hair below) into `299`. Always use `int(x + 0.5)` (round-to-nearest) when formatting CFL/TFL/RFL for labels or popups. This bug recurs across `RaElements.VisTrack.refresh()` and the levels-edit dialog.

### Taxi IAS

`fir.ifr_taxi_ias` (alias `fir.taxi_ias`, default `15.0` kt), `fir.vfr_taxi_ias` and `fir.ret_ias` are read from the scenario Excel (`Escenario` sheet; `taxi_ias` is accepted as a synonym of `ifr_taxi_ias`). Use `Aircraft.get_taxi_ias(fir)`; never hardcode a taxi speed.

### Scenario parameters (no airport names in code)

Since the unification (Fase 3) **airport-specific behaviour must not be written as `if fir.name == 'LEMD'` / `'LEST' in fir.aerodromes`**. Use a scenario parameter instead:

- Read it with `fir.param('clave', default)`. Parameters come from rows of the `Escenario` sheet (column A = key) and are declared in `FIR._PARAM_BOOL / _PARAM_NUM / _PARAM_LIST / _PARAM_STR / _PARAM_MAP`.
- Add the default to `FIR._default_params(name, aps, sectors, ads)` so that **existing Excel files keep the old behaviour without changes**.
- Multi-row rules live in optional sheets: `SectorSequence` (`fir.sector_seq_rules`, applied by `FIR.apply_sector_seq_rules`) and `BahiaFijos` (`fir.bahia_fijos`, used by `ATCBahia`).
- `Add_fir` (exercises with several Excel files) recomputes `fir.params` with the merged aerodromes.
- Document every new key in `docs/PARAMETROS_ESCENARIO.md` (user guide for Excel authors) and in `cambios.md`.
- `fir` is pickled to the clients: parameters must be plain data (dict/list/str/number).

## Change Log

`cambios.md` in the repo root tracks all changes with file, method, and reason. **Update it with every modification made.** Follow the existing convention:

```
## [YYYY-MM-DD] Título corto — Archivos.py

**Archivo:** `lib/Foo.py` — `metodo_afectado()`, `otro_metodo()`

Explicación del **porqué** del cambio (no del qué — el diff ya lo muestra).
Numerar las correcciones cuando son varias en un mismo commit.

---
```

Entries go newest-first at the top of the file. Write in Spanish to match existing entries.

## Domain Vocabulary

- **FIR**: Flight Information Region
- **UCS**: User Control System (ATC radar display)
- **OSF**: *Oficina Suelo Funcional* — ground ops strip management
- **GTA**: *Generador de Tráfico Aéreo* — simulation engine
- **bahia / bahia_type**: strip bay type (`LCL` = Local, `GND` = Ground, `CLR` = Clearance)
- **ficha / strip**: flight strip widget
- **ESCENARIO**: scenario/airport config object within FIR
- **sector combo**: sectors like `'LCL,GND'` where a display covers multiple sector types
