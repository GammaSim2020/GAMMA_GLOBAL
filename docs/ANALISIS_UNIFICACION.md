# Análisis de unificación GammaSim — GAMMA_GLOBAL + GAMMA + GAMMA_OSF_LEBL

Fecha: 2026-10-01 · Base: **GAMMA_GLOBAL** · Análisis solo de lectura (ningún fichero de código modificado).

---

## 0. Cómo retomar el trabajo (leer primero en una sesión nueva)

**Reglas de trabajo fijadas por el usuario**
- Se trabaja **directamente sobre `C:\GAMMA_OSF_U\GAMMA_GLOBAL`** (el usuario tiene copia de seguridad). GAMMA y GAMMA_OSF_LEBL son **solo de consulta**.
- **No escribir nada fuera de `C:\GAMMA_OSF_U`**; preguntar siempre antes si hiciera falta.
- **git: solo lectura** (`git log`, `git status`) y solo en GAMMA. Nunca escribir en git.
- **`C:\03 ESCENARIOS`: acceso de SOLO LECTURA** (Excel de escenarios y ejercicios). En una sesión nueva hay que volver a pedir acceso a esa carpeta.
- Ficheros `.py`: Python 2.7, CRLF y codificación iso8859-15 → editar a nivel de bytes, conservando finales de línea; texto nuevo sin tildes.
- Cada cambio se anota en `GAMMA_GLOBAL/cambios.md` (entrada nueva arriba) y se actualiza este documento.
- Verificación disponible: sintaxis Py2.7 con la gramática de lib2to3 (no hay intérprete 2.7; en el equipo hay `python3` 3.10 con openpyxl 3.1.5). El usuario prueba con `python GAMMA.py` desde `GAMMA_GLOBAL` (no usar `GAMMA_Start.py` ni tocar producción).
- Trabajar por fases y esperar a que el usuario pruebe antes de pasar a la siguiente.
- Técnica usada en la Fase 3: script `patch.py` (python3 en el equipo) que sustituye bloques exactos a nivel de bytes, exige una única coincidencia y convierte `\n`→`\r\n`; copias previas en el directorio temporal de la sesión (no en `GAMMA_OSF_U`).

**Siguiente paso:** el usuario prueba la Fase 3 parte 2 y la Fase 4 bloques 1 (alertas), 2 (PVH/CRU/ENT/LIB) y 3 (rendimiento) — listas de pruebas en `cambios.md` y la Fase 5 → Fase 6 (validación por escenario). Pendiente de Fase 5 que no se ha hecho: eliminar el `process_message` comentado de LEBL y los módulos muertos solo existen en GAMMA_OSF_LEBL (no se tocan, es de consulta).

**Modificaciones de Excel que debe hacer el usuario:** lista viva en `GAMMA_GLOBAL/docs/MODIFICACIONES_EXCEL.md` (actualizarla en cada fase y recordársela al usuario al final). El usuario ha confirmado que le basta el parámetro `alertas` del Excel (no quiere interruptor global en código).

**Pendiente de decisión del usuario (Fase 4):** las alertas se activan también en **LEPA** (su Excel trae las hojas INCW/CMAC/CATC). El usuario dice que en principio solo serán útiles para LEBL → si no se quieren en LEPA, fila `alertas | 0` en la hoja `Escenario` de LEPA (lo hace el usuario en el Excel).

**Documentación viva:** `GAMMA_GLOBAL/docs/PARAMETROS_ESCENARIO.md` (guía de todas las claves de escenario para quien edita los Excel) y sección *Scenario parameters* de `GAMMA_GLOBAL/CLAUDE.md` (norma: no escribir nombres de aeropuerto en el código; usar `fir.param`).

---

## 1. Cómo funciona la herramienta (resumen)

- **GAMMA_Start.py** → comprueba versión en el servidor de red (`ver` en `GAMMA.ini`), actualiza copiando el árbol y lanza **GAMMA.py**.
- **GAMMA.py** → diálogo de conexión; arranca en local o remoto el servidor y los clientes.
- **Servidor `lib/GTA.py`** (Generador de Tráfico Aéreo): servidor TCP Twisted (puerto 20123). Carga escenario (`FIR.py`) + ejercicio (`Exercise.py`), crea objetos `Aircraft`, avanza la simulación en `timer()` (1 s) y atiende ~40-60 comandos vía `_dispatch_table`. Envía `update` serializados (dill/cPickle + zlib). El objeto FIR viaja serializado a los clientes (`RemoteClient`, `m['fir']`).
- **Clientes** (`lib/RemoteClient.py`): rol **ATC** → `UCS.py` (pantalla radar controlador) y rol **PSEUDOPILOT** → `Pseudopilot.py`. Ambos heredan de `RaDisplay.py`; los elementos gráficos (tracks, etiquetas, bahía de fichas, diálogos) están en `RaElements.py`.
- **Escenario** = Excel con hojas (`Escenario`, `Stands`, `Rodaje`, `Procedimientos`, `Sector`, `SACTA`, `OSF`, `OSF_Layout`, `Velocidades`, `RetrocesosOSF`...). El modo de cada posición lo decide `sacta_mode` por sector (PICT / UCS / OSF / APP). Un ejercicio puede cargar varios Excel (`FIR.LoadFirs` + `Add_fir`, p. ej. LEST+LECO+LEVX); el FIR resultante conserva `name`/`aps` del primero.
- **OSF** (`lib/osf/OSF.py`, `PrevDesp.py`): operativa sin ficha de papel en torre — VFVE con zonas, Indicador de Acción (S/U → P/B → TAX → L/U → DEP; LDG → TAX → FIN), transferencias, ficha extendida.
- **Configuración**: `ConfMgr.py` → `gamma_settings.json` con espacio por escenario (`fir.ap[0]`); `GAMMA.ini` solo guarda `ver`.

## 2. Qué es cada versión

| Versión | Perfil | Estado relativo |
|---|---|---|
| **GAMMA_GLOBAL** | LECG/GCLP/GCTS/LEST... con OSF + PrevDesp, config JSON, muchas correcciones (cambios.md hasta 2026-09-10) | **Más avanzada en casi todo** |
| **GAMMA** | Versión nacional sin OSF (PICT/UCS), con git (`GammaSim2020/GAMMA`), v1.3.08 | Es básicamente una versión **anterior** de GLOBAL, más algunas mejoras propias del motor de vuelo y escenario posteriores |
| **GAMMA_OSF_LEBL** | OSF para LEBL + **alertas aeroportuarias INCW/CMAC/CATC** + vehículos (PVH) + cruce/entrada a pista | Código base **antiguo** (mayo-junio) pero con 3 bloques funcionales nuevos |

**Conclusión principal:** no se debe copiar ningún fichero entero de GAMMA ni de LEBL sobre GLOBAL (reintroduciría regresiones ya corregidas). La unificación consiste en **injertar bloques concretos** en GLOBAL y **convertir los hardcodes por aeropuerto en parámetros de escenario**.

### Magnitud de diferencias (líneas distintas vs GLOBAL, ignorando espacios)

| Fichero | GLOBAL | GAMMA | LEBL | Δ GAMMA | Δ LEBL |
|---|---|---|---|---|---|
| UCS.py | 3894 | 2013 | 3768 | 3236 | 740 |
| RaElements.py | 8563 | 9397 | 9197 | 2146 | 870 |
| GTA.py | 1794 | 1498 | 2607 | 1094 | 1057 |
| osf/OSF.py | 4546 | — | 5423 | — | 1517 |
| FIR.py | 1309 | 1179 | 1871 | 238 | 784 |
| RaDisplay.py | 1631 | 1339 | 1666 | 548 | 167 |
| Aircraft.py | 2632 | 2587 | 2644 | 231 | 80 |
| ConfMgr.py | 201 | 196 | 188 | 11 | 323 |
| Pseudopilot.py | 2780 | 2804 | 2872 | 52 | 180 |
| Resto (Exercise, TLPV, RemoteClient, GAMMA*.py, Editor...) | | | | pequeñas | pequeñas |

Ficheros exclusivos: GLOBAL → `lib/osf/PrevDesp.py`. LEBL → `lib/alertas/*` (2.200 líneas, **vivo**), `scripts/add_cmac_sheets.py` (utilidad), `lib/osf/vfve_osf.py` y `osfredimscrollmove.py` (**muertos**, no portar), múltiples `.backup`/`- copia` (descartar). GAMMA → carpeta `Edit/` (la usa `Pantalla.py`).

---

## 3. Bloqueantes: sin esto la versión única no carga todos los escenarios

| # | Problema (verificado en código) | Dónde | Acción |
|---|---|---|---|
| B1 | `self.book['OSF']` sin comprobar si la hoja existe; solo captura `ValueError`. Un Excel nacional sin hoja `OSF` lanza `KeyError` y aborta la carga | FIR.py l.352 | `if 'OSF' in self.book.sheetnames` (como ya se hace con `OSF_Layout`) |
| B2 | `_normalize_sector` sustituye **subcadenas**: `GMC→GND`, `TWR→LCL`. Los sectores de LEBL (`GMC GN`, `GMC ES`...) pasarían a `GND GN` y las reglas de GTA que comparan con `"GMC GN"`, `'GMC ES'`, `"GMC" in` (GTA l.442, 458, 1434) dejan de cumplirse. Mismo origen que el bug LEST del 2026-09-10 | FIR.py l.50-66 | Normalizar por palabra completa / coincidencia exacta y revisar todos los literales de sector |
| B3 | LEBL usa la clave `zonesOSF` en la hoja `Escenario`; GLOBAL solo lee `zonasOSF` | FIR.py l.136 | Aceptar ambas claves |
| B4 | Protocolo `rwy_in_use` roto: Pseudopilot envía `{"ad": {ad: rwy,...}}` pero `_h_rwy_in_use` lee `m['ad'], m['rwy']` → excepción silenciada, la pista no cambia. Editor sí usa el formato antiguo | GTA.py l.1034-1040, Pseudopilot l.2259, Editor l.1632 | Portar `change_rwy_in_use(ads)` multi-aeródromo de GAMMA aceptando los dos formatos (y sus fixes `deprwy`/`lrwy`) |
| B5 | `ATCBahia.update`: `for sect in sector_list: if f.fs_print_t.has_key(sector)` (usa `sector` y no `sect`) → en posiciones multisector no se imprime ninguna ficha | RaElements.py l.1247-1248 | Usar `sect` |
| B6 | REVOCAR / USO PISTAS llaman a `fichas_tabular` sin comprobar → `AttributeError` en escenarios no-OSF; `local_ads[self.sector]` / `sacta_mode[self.sector]` dan `KeyError` con sector compuesto | UCS.py `revocar` l.3421, `process_message` l.402/431 | Guardas `hasattr` y usar `sector_list` |

---

## 4. Acciones: traer de GAMMA (versión nacional) a GLOBAL

### Alta prioridad
| Acción | Ficheros | Notas |
|---|---|---|
| `ifr_taxi_ias` / `vfr_taxi_ias` / `ret_ias` por escenario + `Aircraft.get_taxi_ias()` | FIR, Aircraft (l.463, 1053, 1328), RaElements `change_speed` | Mantener `taxi_ias` como sinónimo de `ifr_taxi_ias` para no romper Excel de LECG/LEBL. LEBL tiene `'20'` hardcoded → poner en su Excel |
| Rama `AUTODEP` en `Aircraft.initialize()` | Aircraft.py ~l.857 | Sin ella la salida AUTODEP va descartando todos los puntos de la ruta |
| `rwy_in_use` multi-aeródromo (ver B4) y pista en uso inicial para todos los aeródromos | GTA `load`/`reload_exercise`/`change_rwy_in_use` | |
| Unificar clave `'rwy'`/`'pista'` en `depart` y `change_star` | GTA `_h_change_star` l.~1308, RaElements l.4251/4684 | Hoy la STAR cambia pero `lrwy`/`rdes` no |
| Restaurar visibilidad/geometría de `atc_bahia` al arrancar (se guarda pero nunca se lee) | UCS `__init__` | Respetar guarda `disp_number == 1` |
| Botón SEP funcional (`toggle_sep`) | UCS `ventana_auxiliar.redraw` l.3341 | Hoy `command=None` |

### Media prioridad
| Acción | Ficheros |
|---|---|
| `ias_blocked`: no pisar velocidad del controlador en el LLZ | Aircraft (`app`, resets), GTA `_h_set_ias`/`_h_set_mach` |
| `hold_stop_removed`: terminar la vuelta de espera antes de aproximar | Aircraft `hold`/`next`/`toggle_stop` |
| `insert_wp(..., fix_after=None)` (añadir al **final** de la firma) | Aircraft, GTA, Pseudopilot |
| Búfer de reordenación de mensajes por secuencia (mejorando lo de GAMMA) | GTA `stringReceived` |
| F7 → `imprimir_ficha` (solo no-OSF) | UCS |

### Baja prioridad
Botón AC de 3 estados (PAC/VAC), checks WheelMouse/GrabDisplay del pseudopiloto, `Route.WayPoint.elvl = 0.0` por defecto, `RaDialog.close` con `pop`, `notify()` en Editor (GLOBAL lo llama y no existe), crear carpeta `Edit/` (o `os.makedirs`), tipos `CRUZ`/`TOBA`/`F18` en `bada.txt` y `Modelos_avo.txt` (con estela RECAT), cambio `THR` en `Aircraft.depart()` con respaldo si el punto no existe (decisión 3).

### No portar de GAMMA
`RaBahia`/`VFPVfield` (bahía antigua, sustituida por OSF), forzado `sacta_mode='PICT'`, `set_tfl` en doble click, fallos de `Stands` y `NM2Geo` de GAMMA, colisión de rodaje sin `abs()`.

---

## 5. Acciones: traer de GAMMA_OSF_LEBL a GLOBAL

**Mantener GLOBAL** en todo lo que LEBL tiene antiguo: singleton multi-instancia OSF, `self.sector` por ventana, `zonasOSF` dinámico, merge `OSF_Layout`, `cssr`, `_eobt_slot`/CTOT, ficha extendida con valores reales, TRANSFERIR dinámico, guardas multipantalla, ConfMgr JSON, `QNH_STD`, `register_squawk`, CTOT datetime, redondeo `+0.5`, `echo_b1`, `remove_tfl`, FALT nuevo, `abs()` en colisión de rodaje.

### Bloque 1 — Alertas aeroportuarias INCW / CMAC / CATC (Alta)
Orden de porte:
1. Copiar `lib/alertas/` completo. Debe ser importable también en clientes (los objetos `Alert` viajan serializados con dill).
2. `FIR.py`: `_load_incw_sheets`, `_load_cmac_sheets`, `_load_catc_sheets`, `_parse_dms_value`, `_load_incw_zone_maps` (LEBL l.372-840 y 1310-1463). Inicializar siempre `incw_zones={}`, `cmac_params={}`...
3. `Aircraft.py`: constantes `LIB`, `CRUREQ`, `ENTREQ`; atributos `active_alerts`, `max_alert_severity`, `top_alert`, `catc_pred`, `cmac_inhibited`; copiarlos en `Aircraft_update`. Conservar `AUTHORIZATION` de GLOBAL.
4. `GTA.py`: import opcional, `AlertManager` en `load()` **y** `reload_exercise()` (LEBL no lo recrea), `evaluate()` en `timer()`, `_current_pistas_config` en `_h_runway_config_update`, comando `ack_alert`.
5. `RaElements.py` (VisTrack): visualización, parpadeo, ventana tabular de alertas, color morado CATC — **fusión manual** respetando colores de GLOBAL.
6. `UCS.py`: copia de campos de alerta, `_update_conflict_lines()`, pista sin operación ⇒ NO EN USO.
7. `OSF.py`: "alitas" W/V, color CATC, redibujado por cambio de alertas.

Parametrización: se autoactiva solo si el Excel trae las hojas `INCW*`, `CMAC*`, `CATC*` (sin hojas ⇒ `available=False`, sin cambios). Sacar `RECIPROCAL_MAP` (pistas de LEBL repetidas en los 3 motores) a un cálculo común desde `fir.aerodromes`. Generalizar `scripts/add_cmac_sheets.py` (ruta OneDrive y LEBL fijos).

### Bloque 2 — Vehículos (PVH) y cruce/entrada a pista CRU/ENT/LIB (Alta/Media)
- GTA: comandos `create_pvh`, `delete_pvh`, `set_pvh_notes`, `authorize_ent`, `request_cru`, `request_ent`, `cancel_cru`; limpieza en `_h_set_osf_pof`.
- Aircraft: `has_pvh`, `pvh_notes`, `ent_runway`, `pre_ent_pof`, `cru_runway`, `pre_cru_pof`.
- OSF.py: botón VEH y diálogos, campos `pista_ent`/`anotaciones`, layout de vehículo, flujo CRU/ENT/LIB en `_on_act_click`/popup/`revocar`/`_act_text_color` (cambiar `radisplay.sector` → `self.sector`). Unificar guardado de notas en `set_pvh_notes` (LEBL usa `create_pvh` por error).
- UCS/RaElements: formato `atc-veh-pvh`, colores de vehículo, CRR/ENR, handlers del plot (quitar condición `adep=='LEST'` del Button-2).
- Pseudopilot: `_show_cru_menu` (hoy comentado).
- Parametrizar: flag de escenario `pvh=1`; pistas de respaldo fijas `['02','06L',...]` → `rwy_direction_list`.

### Bloque 3 — Rendimiento / ejercicios de 2 h (Media)
- `refresco_aire` (tracks en vuelo cada 3 s, tierra cada ciclo) en UCS/RaDisplay, **opcional** con valor por defecto = `refresco`.
- Pseudopilot: redibujado de ruta limitado a 30 ms y reutilizando ítems.
- OSF: no redibujar con campo en edición ni durante arrastre (aplica a todos los escenarios).
- La propuesta de `docs/2026-02-26-optimizacion-ejercicios-2h.md` **no está implementada en ninguna versión** (pendiente).

### Otros de LEBL
`get_zone` con respaldo por estado como último recurso; ruta absoluta de config (`_script_dir`) en ConfMgr; pushback: regla por stand si `fir.pushbacks` tiene datos, si no siempre P/B (elimina la rama fija `LEBB`); limpiar el `GAMMA.ini` de LEBL (valores `['x']`) antes de la migración automática a JSON.

---

## 6. Hardcodes por aeropuerto → parámetros de escenario

Implementado (Fase 3 parte 1): filas en la hoja `Escenario` leídas en `fir.params` (acceso `fir.param(clave, defecto)`), con valores por defecto en `FIR._default_params()` que reproducen el comportamiento anterior; reglas de secuencia de sectores en la hoja opcional `SectorSequence` (por defecto `FIR._DEFAULT_SECTOR_SEQ_RULES`). Tabla completa de claves en `GAMMA_GLOBAL/cambios.md`.

| Hardcode anterior | Dónde | Parámetro | Estado |
|---|---|---|---|
| Reglas `sector_sequence` LEBL ELR, LEST/LECO/LEVX, GCXO/GCTS/GCLP | GTA `load_flight` | Hoja `SectorSequence` (aeropuerto, operación, pista, posición, acción, valor, si_escenario) | Hecho |
| TFL 240/250, PEKOP 130/150 | GTA `load_flight` | `tfl_dep_local`, `tfl_defecto`, `tfl_fijo` | Hecho (el `tfl=350` de `Aircraft.__init__` se sobrescribe siempre: sin cambio) |
| `fir.name in ('LEMD','LEBL')` en assume PP / GMC ES-EN | GTA `_h_assume` | `pp_asumir_arranca`, `pp_asumir_rodaje_salvo` | Hecho |
| Giro AT* 9º/s salvo GCXO/GCTS/LEST/LEBB/LEMG | Aircraft `get_rot` | Sin parámetro (decisión 2) | Se deja como está |
| Frenada/aceleración LESO, LEBL, GEML | Aircraft `next` | `decel_aterrizaje`, `acel_despegue` (por aeródromo) | Hecho |
| `hrls` por defecto ("en LEST es al revés") | Aircraft `__init__` | — | Solo es un comentario; no hay código específico de LEST |
| Preimpresión 10/2 min LEMD/LEBL/BarcelonaTWR | TLPV | `preimpresion_arr`, `preimpresion_dep` | Hecho |
| Sin fichas de fijo para salidas locales LEAM/LEGR | TLPV | `ads_sin_fichas_fijo` | Hecho |
| Echo `"TW"+ades[-2:]+"_"` | TLPV `get_exit_ades` | — | Genérico, sin cambio |
| Tabulares ocultas/no actualizadas en LEMD/LEBL; PrevDesp | UCS | `tabulares_aux`, `tabulares_aux_actualizar`, `prevdesp_actualizar_ficha` | Hecho |
| STCA y separación de etiquetas off en LEMD/LEBL | RaDisplay | `stca`, `separar_etiquetas` | Hecho |
| OSF LCL por sector en LEPA; SobTabular LEPA | RaDisplay, UCS | `osf_lcl_por_sector`, `sob_tabular` | Hecho |
| SMR / AlarmNoCorr LEST; `self.sector=='LEGR'` alt<50 | UCS | `smr_ad`, `min_alt_visible` (por sector) | Hecho (botón 2 del plot solo LEST en VisTrack → Fase 4) |
| Orientaciones extra LEMD | UCS | `orientaciones` | Hecho |
| Arrastre de pantalla del PP off en LEMD | Pseudopilot `b1_cb` | `pp_arrastre_pantalla` | Hecho |
| Activación manual `fir.sectors[0]=='GRANADA'` | RaElements Dep/ActTabular | `activacion_manual_ads` | Hecho |
| USO PISTAS: pares LEBL y mapas `MAPA_DEP/ARR/...` | UCS | `uso_pistas`, `mapas_pista_cerrada`; candidatos ARR/DEP/MIXTO generados por pista | Hecho (parte 2) |
| Fijos de ATCBahia por escenario, filtro de torre LEST, LEME→LEMD, config LEBL→pista, `LECG`/`LEMD` en fichas | RaElements ATCBahia | Hoja `BahiaFijos`; `bahia_torre_ads`, `ficha_formato_lemd`, `alias_ads`, `ficha_pistas_config`, `ficha_borde_salida_ads`, `ficha_freq_teclado` | Hecho (parte 2); carpetas de Barcelona no portadas (escenario inexistente) |
| Editor `fir.name == 'LECB'` | Editor | `editor_mapas_reducidos` | Hecho (parte 2) |
| Pushback fijo LEBB | OSF l.2304 | regla por stand (`fir.pushbacks`) | Fase 4 |
| Paletas de color VisTrack / LAD | RaElements | Paleta por `sacta_mode` | Pendiente |
| Ruta servidor de actualización `GAMMA_TWRAPS` / `GAMMA` / `GAMMA_OSF_LEBL` | ConfMgr l.14, GAMMA_Start | `update_dir` en `GAMMA.ini`; `dst_dir` relativo al script | Fase 5 |

---

## 7. Infraestructura y empaquetado

- **GAMMA_Start.py**: reescribir desde GLOBAL con lista de exclusión (`gamma_settings.json`, `*.log`, `log/`, `Thumbs.db`, `*.pyc`), respaldo si no hay VPN y rutas relativas. Nota: el §13 del cambios.md de GAMMA describe cambios que **no están en su código**.
- **`gamma_settings.json`**: no distribuirlo (estado de usuario).
- **ConfMgr.save()**: hacerlo atómico de verdad (tmp + rename).
- **Codificación**: `RaElements.py` de GLOBAL tiene ñ/tildes convertidas a `?` (`SE?ALERO`, `Aproximaci?n`...) → restaurar en iso8859-15. Además varios `.py` declarados iso8859-15 contienen bytes UTF-8 (FIR, GTA, UCS, Aircraft...).
- **Versión**: decidir numeración de la versión unificada (`ver` 1.0.05 GLOBAL / 1.3.08 GAMMA).
- **Limpieza**: borrar backups y `- copia` de LEBL, `UCS.py.mioNoJoserra` y `Nuevo documento de texto.txt` de GLOBAL, `process_message` comentado de LEBL (~730 líneas).

---

## 8. Fallos compartidos detectados (corregir durante la unificación)

- QNH en METAR: `str(qnh)[:4]` da `"999."` con 999.6 → `'%04d' % int(round(qnh))`. (Hecho, Fase 2)
- Giro progresivo del viento sin módulo 360 (oscila al cruzar el norte). (Hecho, Fase 2)
- Asumido con `self.sector.find(f.atc_sector)` (subcadena) → `in self.sector_list`. (Hecho en UCS, Fase 2; en GTA `_h_assume` sigue `m['sector'].find(f.atc_sector)`)
- Serialización del broadcast en hilo leyendo objetos `Aircraft` vivos → serializar copias.
- `Aircraft.sector_sequence` no inicializado en `__init__`. (Hecho, Fase 2)
- LEBL: `IndexError` en `load_flight` si una llegada por la 02 se queda sin secuencia de sectores. (Hecho, Fase 3)
- Bahía de fichas: filtro "solo LEST" aplicado a las torres de todos los escenarios (sin fichas en LEGR/LEAM/LEMH...); `os.listdir('img/LEGR')` sin carpeta en GLOBAL; `local_ads[sector]` con multisector. (Hecho, Fase 3 parte 2; `img/LEGR` copiado de GAMMA)
- Condiciones `fir.name == 'LECG'` en RaElements nunca ciertas (el escenario se llama LEST): convertidas en parámetros con el mismo efecto (inactivas); activarlas es decisión del usuario.

---

## 9. Plan de trabajo propuesto (por fases)

1. **Fase 0 – Preparación**: se trabaja sobre GAMMA_GLOBAL; limpieza de backups; decidir versión.
2. **Fase 1 – Carga multi-escenario** (bloqueantes B1-B3, flags de escenario en FIR con defaults). Prueba: cargar LECG, un escenario nacional y LEBL.
3. **Fase 2 – Motor y protocolo** (B4-B6, taxi IAS, AUTODEP, ias_blocked, hold, insert_wp, rwy/pista, fallos compartidos).
4. **Fase 3 – Parametrización de hardcodes** (tabla §6): parte 1 GTA/Aircraft/TLPV/RaDisplay/UCS/Pseudopilot (probada); parte 2 ATCBahia, USO PISTAS, Editor (pendiente de prueba).
5. **Fase 4 – Bloques LEBL**: alertas → PVH/CRU/ENT → rendimiento 2 h.
6. **Fase 5 – UI menores y empaquetado** (GAMMA_Start, Edit/, datos BADA, codificación).
7. **Fase 6 – Validación** por escenario (LECG/GCLP con OSF, nacional PICT, LEBL con alertas) y actualización de `cambios.md`/`CLAUDE.md`.

---

## 10. Anexo — Verificación con los Excel reales (`C:\03 ESCENARIOS`, solo lectura)

Revisados 28 escenarios vigentes y 911 ejercicios (hoja `Ejercicio`).

### 10.1 Escenarios por tipo

| Tipo | Escenarios | Hojas OSF | Clave zonas | Velocidad rodaje |
|---|---|---|---|---|
| **PICT sin OSF** | LEMH, LEAS, LEPP, LERJ, LESO, LEXJ, LEVT, LECO, LEVX, LEAM, LEGR, LEGE | **No tienen hoja `OSF`** | — | LEGR: `ifr/vfr_taxi_ias`; LEGE: `taxi_ias` + `ret_ias` |
| **OSF (formato GLOBAL)** | GCLP, GCTS, GCXO, LEBB, LEST, LERS | `OSF` (+ `OSF_Layout` en GCLP, LEBB, LEST, GCTS de DRNA_CN) | `zonasOSF` | GCLP: `ifr_taxi_ias=20`, `vfr_taxi_ias=15`; resto `taxi_ias` |
| **OSF (formato LEBL)** | LEBL, LEPA, LEMD, LEMG | `OSF`, sin `OSF_Layout` | **`zonesOSF`** | — |
| **OSF + alertas** | LEBL, **LEPA** | + 13 hojas `INCW*`/`CMAC*`/`CATC*` + `ALERTAS` | `zonesOSF` | — |

### 10.2 Lo que confirman los datos

1. **B1 confirmado y crítico**: 12 escenarios PICT no tienen hoja `OSF` → hoy no cargarían en GLOBAL.
2. **B3 confirmado**: LEBL, LEPA, LEMD y LEMG usan `zonesOSF`; GLOBAL solo lee `zonasOSF` (OSF.py cae a zonas por defecto con warning).
3. **Velocidad de rodaje: tres formatos conviven**. GCLP y LEGR ya usan `ifr_taxi_ias`/`vfr_taxi_ias` (formato de GAMMA) → **GLOBAL los ignora hoy** y aplica 15 kt en GCLP en vez de 20. GCTS, GCXO, LEBB, LEST y LEGE usan `taxi_ias`; LEGE trae `ret_ias`. ⇒ Leer los tres nombres (`taxi_ias` = sinónimo de `ifr_taxi_ias`).
4. **Alertas no son solo de LEBL**: LEPA ya tiene todas las hojas INCW/CMAC/CATC → refuerza sacar `RECIPROCAL_MAP` y las pistas fijas de LEBL de los motores.
5. **`_normalize_sector` (B2) — matiz**: como se normaliza tanto la hoja `Sector` como la `Posicion` del ejercicio, los diccionarios por sector cuadran entre sí (`GMC GN`→`GND GN` en ambos lados). Lo que se rompe son:
   - las **comparaciones literales en código** (GTA `"GMC GN"`, `('GMC ES','GMC EN')` de LEMD, `'LEST TWR'`, `'GRANADA'`, `'LEGR'`...);
   - el **orden de sustitución**: `'LEST TMA'` (Posicion de 74 ejercicios LECG) puede quedar `'APP'` o `'LEST APP'` según el orden de iteración del dict en Python 2.7. ⇒ aplicar alias de **más largo a más corto** o por coincidencia exacta.
   - Posiciones existentes en ejercicios: `TWR`, `APP`, `LEST TMA`, `LEST TWR`, `LEBB TMA`, `GMC GN`, `GMC GC`, `GMC_N`, `GMC_W`, `LCL_W`, `TWR 36L/18R`, `TWR 36R/18L`, `ALMERIA`, `GRANADA`.
6. **`csrr` sigue en el Excel de LEST** (`OSF_Layout`, campos extendida GND dep_local) → con el renombrado a `cssr` de GLOBAL ese campo no se pinta. Corregir en el Excel o añadir alias `csrr→cssr` en `_FIELD_NAME_ALIASES`.
7. **CTOT**: 62 ejercicios ya tienen 16-17 columnas (columna P en uso); 828 tienen 15 (sin CTOT) → el tratamiento "sin valor → `''`" de GLOBAL es necesario.
8. **Claves no leídas por ningún código**: `camposOSF` (LEMG), hojas `ALERTAS`, `datos_extra`, `Airlines` (LEMG; lectura comentada en LEBL), `Menu_optimizado`, `DATOS GUARDADOS`, `Actualizaciones`, `Notas` → informativas, no requieren cambios.
9. **Escenarios duplicados con contenido distinto**: `DRNA_C/GCLP|GCTS|GCXO` frente a `DRNA_CN/DRNA_C/...` (distinto md5; p. ej. GCLP 2026-09-11 vs 2026-06-15). Referencia elegida: la más reciente de cada uno (ver decisión 6).
10. **LECM** usa un formato antiguo (sin `Sector`, `LLZ`, `Esperas` ni fila `aeropuerto`) → fuera de alcance salvo que se quiera mantener.
11. **Parámetros de la Fase 3**: ningún Excel vigente revisado (LEST, GCLP, LEPA, LEMH, LEBL, LEMD) trae aún las claves nuevas ni la hoja `SectorSequence` → todos usan los valores por defecto (= comportamiento anterior).

### Estado de ejecución
- **Fase 1 (2026-10-02) — hecha** en GAMMA_GLOBAL: hoja `OSF` opcional, `zonesOSF`/`zonasOSF`, `ifr/vfr_taxi_ias` + `ret_ias` (con `taxi_ias` como sinónimo), `_normalize_sector` determinista, literales `GMC`/`GND` en GTA. Detalle en `GAMMA_GLOBAL/cambios.md`. Verificado: sintaxis Py2.7 y carga de `ESCENARIO` con 19 Excel reales.
- **Fase 1 probada por el usuario (2026-10-02)**: arrancan escenarios con y sin OSF.
- **Fase 2 (2026-10-02) — hecha y probada por el usuario**: protocolo de pista en uso multi-aeródromo, claves rwy/pista, pista inicial por aeródromo, AUTODEP, ias_blocked, esperas, insert_wp con fix_after, THR en depart con respaldo, ATCBahia multisector, UCS multisector/asumido/REVOCAR sin OSF, QNH en METAR, giro del viento.
- **Fase 5 pendientes de GAMMA (2026-10-05) — hecho, pendiente de prueba**: botón SEP funcional, F7 → `imprimir_ficha`, recuperación de visibilidad y geometría de `atc_bahia` al arrancar (UCS). Checklist de pruebas para pseudopiloto y controlador en el doc «Checklist de pruebas — GammaSim unificado» (Claude Docs).
- **Fase 5 (2026-10-05) — hecha, pendiente de prueba**: `GAMMA_Start.py` reescrito (`update_dir`/`update_dir_alt` en `GAMMA.ini`, carpeta local = la del script, exclusiones al copiar, arranque local sin red), `ConfMgr` (rutas junto al programa, guardado atómico con `.tmp`, migración desde `GAMMA.ini` corregida y limpieza de valores `['x']`), `GAMMA.py` hace `chdir` y crea `log/`, `ver = 1.0.0`; codificación normalizada a iso8859-15 en 8 ficheros (código idéntico token a token); BADA CRUZ/F18/TOBA y modelos CRUZ/TOBA/P28A; botón AC de 3 estados (arranca verde), casillas WheelMouse/GrabDisplay, `RaDialog.close`, `Editor.notify`, carpeta `Edit/`, `WayPoint.elvl`; borrados `Nuevo documento de texto.txt` y `UCS.py.mioNoJoserra`. Despliegue: ver entrada en `cambios.md`.
- **Fase 4 pushback por stand (2026-10-05) — hecho, pendiente de prueba**: `OSF._pushback_rule()` para todos los escenarios (decisión del usuario): hoja `RetrocesosOSF` con datos → por stand (stand sin `S` sale rodando S/U→TAX); sin hoja o vacía → regla antes fija de LEBB (S/U: SOLICITUD P/B, AUT. P/W, AUT. P/E, AUT. TAX). Corregido `FIR`: leía solo 3 direcciones (D-F), se perdía W en LEPA.
- **Fase 4 bloque 3 (2026-10-05) — hecho, pendiente de prueba**: parámetro opcional `refresco_aire` (s, por defecto 0 = sin cambio; LEBL lo tenía fijo en 3) en `UCS.update_tracks`; pseudopiloto con redibujado de la ruta en definición limitado a ~30 ms y reutilizando items (`_route_preview`/`_route_preview_cancel`, todos los escenarios); OSF `draw_zonas` no redibuja con un campo en edición (todos los escenarios). Decisión del usuario: refresco opcional por Excel, el resto para todos.
- **Fase 4 bloque 2 (2026-10-05) — hecho, pendiente de prueba**: parámetro `pvh` (por defecto Sí solo en LEBL); `Aircraft` (LIB/CRUREQ/ENTREQ, atributos PVH/CRU/ENT), GTA (7 comandos + limpieza en `set_osf_pof`), OSF (botón VEH y diálogos, ficha de vehículo, flujo CRR→CRU→LIB→TAX y ENR→ENT→LIB→TAX, ACCIONES, REVOCAR, notas con `set_pvh_notes`, cabeceras del aeródromo en vez de lista fija de LEBL, zona de respaldo para estados no recogidos en la hoja `OSF`), UCS/RaElements (etiqueta `atc-veh-pvh`, colores de vehículo solo con `pvh`, botones del plot; botón 2 del plot ya no depende de LEST sino de `smr_ad`/`pvh`). No portado: menú CRU del pseudopiloto (desactivado en LEBL) y regla de pushback por stand (pendiente).
- **Fase 4 bloque 1 (2026-10-05) — hecho, pendiente de prueba**: `lib/alertas/` copiado de LEBL (pista recíproca calculada con `reciprocal_rwy`, sin tabla fija de LEBL), carga de hojas INCW/CMAC/CATC y zonas en FIR (dentro de `try`), parámetro `alertas` (por defecto 1; solo actúa si existe la hoja `INCWareaIncur`), `AlertManager` en `load()` y `reload_exercise()`, `evaluate()` en `timer()`, `ack_alert`, campos de alerta en `Aircraft`/`Aircraft_update` (copia de la lista), VisTrack (WNG/VIO, parpadeo, ventanas), UCS (líneas de conflicto, USO PISTAS sin operación ⇒ NO EN USO), OSF (alitas W/V, color CATC, redibujado por cambio de alertas). Verificado con los Excel reales de LEBL, LEPA y LEST y con móviles sintéticos. PVH/CRU/ENT quedan para el bloque 2 (los motores ya toleran su ausencia).
- **Fase 3 parte 2 (2026-10-02) — hecha**: ATCBahia data-driven (hoja `BahiaFijos`, `_crear_fijo`), filtro de torre `bahia_torre_ads`, parámetros de ficha (`ficha_formato_lemd`, `alias_ads`, `ficha_pistas_config`, `ficha_borde_salida_ads`, `ficha_freq_teclado`), `_local_ads()` multisector, USO PISTAS (`uso_pistas`, `mapas_pista_cerrada`), Editor (`editor_mapas_reducidos`), `img/LEGR` copiado de GAMMA, guía `docs/PARAMETROS_ESCENARIO.md` y CLAUDE.md. Pendiente prueba en el simulador.
- **Fase 3 parte 1 probada por el usuario (2026-10-02)**: sin incidencias.
- **Fase 3 parte 1 (2026-10-02) — hecha**: 21 parámetros de escenario en la hoja `Escenario` + hoja opcional `SectorSequence`, aplicados en FIR, GTA, Aircraft, TLPV, RaDisplay, UCS, Pseudopilot y RaElements (Dep/ActTabular). Valores por defecto = comportamiento anterior; escenarios compuestos (`Add_fir`) recalculan con los aeródromos unidos. Verificado: sintaxis Py2.7, reglas de secuencia frente al código anterior con 24.000 vuelos sintéticos, lectura con Excel reales y con una copia de LEST con filas añadidas. Pendiente prueba en el simulador (lista en `cambios.md`).

### Decisiones del usuario (cerradas el 2026-10-02)
1. **Parametrización** → filas nuevas en la hoja `Escenario` (opción A), mismo formato que `taxi_ias`/`zonasOSF`, con valores por defecto que reproducen el comportamiento actual. Los ajustes por sector van en la hoja `Sector`; las reglas con varias columnas, en hojas propias solo donde se usen. (En la Fase 3, `min_alt_visible` por sector se puso en `Escenario` con el sector en la columna B, como `zonasOSF`.)
2. **Velocidad de giro en vuelo** → criterio GLOBAL para todos (3 º/s salvo estela L; ATR a 9 º/s con sus excepciones). LEBL cambia de comportamiento. Sin parámetro.
3. **`THR` en `Aircraft.depart()`** → portar lo de GAMMA **con respaldo**: si existe el punto `THR`+pista en el escenario va directo al umbral; si no, se comporta como GLOBAL (rodaje restante + SID).
4. **`write_flightstrips_file`** → no se usa: **se descarta** (queda como en GLOBAL).
5. **Dónde** → directamente sobre **GAMMA_GLOBAL** (el usuario tiene copia de seguridad).
6. **Escenarios de referencia de Canarias** → la copia más reciente de cada uno: GCLP de `DRNA_C`; GCTS y GCXO de `DRNA_CN\DRNA_C`.
7. **`csrr` en LEST** → lo corrige el usuario en el Excel (`OSF_Layout`); sin cambios en código.
8. **Versión de la unificada** (2026-10-05) → `ver = 1.0.0` en `GAMMA.ini`. Nota: `GAMMA_Start.versions()` quita los puntos y compara con `!=` (cualquier diferencia con la del servidor fuerza la actualización), así que bajar de 1.0.05 a 1.0.0 funciona; para versiones futuras mantener siempre el mismo formato.
9. **Carpeta de red de actualización** (2026-10-05) → `\\nacl0400\INTERREGIONAL\GAMMA\08 GAMMA PRODUCCION\GAMMA_GLOBAL` (con el respaldo `\\nacl0400.nav.es\...` como hoy). Irá en `GAMMA.ini` (`update_dir`) en la Fase 5; la carpeta local de instalación se calcula a partir de la del script (hoy fija `C:/GAMMA_TWRAPS`).
10. **Alertas**: basta el parámetro `alertas` del Excel; no se quiere interruptor global en código.
