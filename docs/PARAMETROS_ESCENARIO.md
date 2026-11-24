# Parámetros de escenario — GammaSim unificado

Guía para quien prepara o mantiene los Excel de escenario. Recoge **todo lo que antes estaba escrito en el código para un aeropuerto concreto** (`if fir.name == 'LEMD'`, `'LEST' in aerodromes`...) y ahora se configura desde el Excel.

**Regla básica: no hace falta tocar ningún Excel.** Si una clave no está, se usa un valor por defecto que reproduce lo que el programa hacía antes con ese escenario (por el nombre del fichero: `LEMD.xlsx` → escenario `LEMD`). Solo hay que añadir filas para **cambiar** ese comportamiento o para configurar un escenario nuevo.

Al cargar el escenario, el log (`GAMMA.log`) muestra la línea `Parametros de escenario <nombre>: {...}` con los valores efectivos: es la forma de comprobar que lo que se ha puesto en el Excel se ha leído.

Los valores por defecto están en un solo sitio del código: `lib/FIR.py`, funciones `_default_params()`, `_default_bahia_fijos()` y la lista `_DEFAULT_SECTOR_SEQ_RULES`.

---

## 1. Filas de la hoja `Escenario`

Mismo formato que `taxi_ias` o `zonasOSF`: **columna A = clave**, columna B = valor (y columna C cuando se indica).

- **Sí/No**: `1` / `0` (también `SI`/`NO`).
- **Lista**: valores separados por comas en la columna B (`NORTH,FIELD`).
- **Por elemento**: una fila por elemento; columna B = aeródromo/sector/fijo/pista, columna C = valor. Una fila con la columna C **vacía elimina** el valor por defecto de ese elemento. En las claves de aeródromo, `*` en la columna B es el valor general.

### 1.1 Radar y tabulares (puesto de controlador)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `stca` | Sí/No | Cálculo de alertas STCA | No en LEMD y LEBL; sí en el resto |
| `separar_etiquetas` | Sí/No | Separación automática de etiquetas | No en LEMD y LEBL |
| `tabulares_aux` | Sí/No | Muestra las tabulares COOR / PREACT / ACT | Ocultas en LEMD y LEBL |
| `tabulares_aux_actualizar` | Sí/No | Actualiza esas tabulares | No en LEMD |
| `prevdesp_actualizar_ficha` | Sí/No | La ventana de previsión de despegues recibe cada ficha actualizada | No en LEMD y LEBL |
| `sob_tabular` | Sí/No | Tabular SOB | Sí si el escenario tiene LEPA |
| `smr_ad` | Aeródromo | Aeródromo del SMR: activa el botón SMR, la tabular de No Correlados y el modo de una línea de sus salidas. Vacío = sin SMR | LEST si el escenario tiene LEST |
| `orientaciones` | Lista | Orientaciones del botón GEOSTANDAR | `FIELD,NORTH,EAST,SOUTH,WEST` en LEMD; `NORTH,FIELD` en el resto |
| `min_alt_visible` | Por sector (B = sector, C = cientos de pies) | Oculta los tracks por debajo de esa altitud en esa posición | LEGR → 50 |
| `osf_lcl_por_sector` | Sí/No | Una ventana OSF por cada sector LCL | Sí en LEPA |

### 1.2 Pseudopiloto

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `pp_arrastre_pantalla` | Sí/No | Arrastrar la imagen con el botón 1 | No en LEMD |
| `pp_asumir_arranca` | Sí/No | Al asumir el PP un vuelo en PREPARING pasa a S/U y queda liberado para el ATC | Sí en LEMD y LEBL |
| `pp_asumir_rodaje_salvo` | Lista de sectores | Si el primer sector del vuelo no está en la lista, al asumirlo pasa directamente a TAX | `GND ES,GND EN` en LEMD; vacío (no se aplica) en el resto |

### 1.3 Planes de vuelo y fichas

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `preimpresion_arr` / `preimpresion_dep` | Minutos | Antelación con que se imprimen las fichas de llegadas / salidas | 10 / 2 en LEMD, LEBL y BarcelonaTWR; 30 / 30 en el resto |
| `ads_sin_fichas_fijo` | Lista de aeródromos | Las salidas locales de estos aeródromos no generan fichas de fijo | `LEAM,LEGR` |
| `tfl_dep_local` / `tfl_defecto` | Nivel | TFL inicial de salidas locales / resto de vuelos | 240 / 250 |
| `tfl_fijo` | Por fijo (C = `local,resto` o un único valor) | TFL de los vuelos que pasan por ese fijo | `PEKOP` → 130,150 |

### 1.4 Motor de vuelo

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `decel_aterrizaje` | Por aeródromo (C = kt/s) | Frenada en el aterrizaje por encima de 50 kt | `*` 7, LESO 8, LEBL 4 |
| `acel_despegue` | Por aeródromo (C = kt/s) | Aceleración en la carrera de despegue | `*` 5, GEML 9, LESO 8 |

(Velocidades de rodaje: `ifr_taxi_ias`/`taxi_ias`, `vfr_taxi_ias`, `ret_ias`, ya existentes.)

### 1.5 Bahía de fichas de papel (posiciones no OSF)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `bahia_torre_ads` | Lista de aeródromos | En posiciones de torre solo se ponen en la bahía las fichas de estos aeródromos. Vacío = todas | `LEST` en LEST/LECO/LEVX; vacío en el resto |
| `alias_ads` | Por aeródromo (C = aeródromo mostrado) | Aeródromo que se escribe en la ficha | Vacío (se escribe el del plan de vuelo) |
| `ficha_borde_salida_ads` | Lista de aeródromos | Borde azul (de salida) para vuelos de estos aeródromos aunque no sean locales | Vacío (ver nota) |
| `ficha_freq_teclado` | Sí/No | El campo frecuencia abre un teclado en lugar de recorrer las frecuencias | No (ver nota) |
| `ficha_pistas_config` | Por `AD CONFIG` (C = `salidas,llegadas`) | Pista escrita en la ficha según la configuración en uso. Ej.: B = `LEBL WRL`, C = `25L,25R` | Solo para el antiguo escenario `Barcelona` |

Nota: `ficha_borde_salida_ads` (LPPR) y `ficha_freq_teclado` estaban pensados para "LECG", pero el código los condicionaba a un escenario llamado `LECG`, que no existe (el Excel es `LEST.xlsx`), así que nunca se aplicaban. Para activarlos en LECG: fila `ficha_borde_salida_ads | LPPR` y/o `ficha_freq_teclado | 1` en `LEST.xlsx`.

### 1.6 Ventana USO PISTAS (OSF)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `uso_pistas` | Lista de pares | Pistas que aparecen en la ventana. Ej.: `02/20,06L/24R` | `13/31,02/20,06L/24R,06R/24L` (las de LEBL, en todos los escenarios, como antes) |
| `mapas_pista_cerrada` | Por pista (C = nombres de mapa separados por comas) | Mapa que se activa al cerrar esa pista (se usa el primero que exista) | Tabla de LEBL: 02 y 20 → `02_CLSD`; 06L y 24R → `06L_CLSD`/`06_CLSD`; 24L y 06R → `24_CLSD`. Pistas no listadas: `<pista>_CLSD` o `<recíproca>_CLSD` |

Los mapas de llegadas, salidas y uso mixto se buscan por nombre para cualquier pista: `ARR_<p>` / `<p>_ARR` / `<p> ARR`, `DEP_<p>` / `<p>_DEP`, `MIXTO_<p>` / `<p>_MIXTO`.

### 1.7 Editor

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `editor_mapas_reducidos` | Sí/No | El editor arranca sin rutas, puntos ni sectores y sin los botones de fijos | Sí en LECB |

### 1.8 Alertas aeroportuarias INCW / CMAC / CATC (Fase 4)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `alertas` | Sí/No | Con `0` desactiva las alertas aunque el Excel traiga las hojas | Sí (se activan solo si existen las hojas) |

Las alertas se activan **solo si el Excel trae la hoja `INCWareaIncur`** con zonas del aeródromo del escenario. Hojas que se leen (formato del Excel de LEBL: 2 filas de cabecera, columnas A = dependencia, B = aeródromo):

- INCW: `INCWareaIncur` (polígonos NO-LVP/LVP/ALIN por pista; también se dibujan como mapas `INCW NO-LVP`, `INCW LVP`, `INCW ALIN`), `INCWareaIncurParam`, `INCWpistasCruzadas`, `INCWparamt` y las matrices de severidad `INCWalerInIndividuales`, `INCWalerInMultENuso`, `INCWalerInMultNOenUSO`, `INCWalerInMultCERRADA`, `INCWalerConfMultTraOp`.
- CMAC: `CMACparamt`, `CMACsubtipos`, `CMACpistasCerradas`. CATC: `CATCsubtipos`.

Hoy traen estas hojas **LEBL y LEPA**. Si en LEPA no se quieren alertas, añadir en su hoja `Escenario` la fila `alertas | 0`.

La pista recíproca se calcula del nombre (`06L`→`24R`, `02`→`20`); ya no hay tabla fija de pistas de LEBL en los motores.

### 1.9 Vehículos (PVH) y cruce/entrada a pista (Fase 4)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `pvh` | Sí/No | Botón VEH y Plan de Vehículo en OSF, fichas y etiquetas de vehículo con PVH, flujo de cruce (CRR/CRU/LIB) y entrada a pista (ENR/ENT/LIB), opciones CRU en ACCIONES, botones central/derecho del plot para vehículos | Sí en LEBL; no en el resto |

Opcional en la hoja `OSF`: filas con las acciones `CRR`, `CRU`, `ENR`, `ENT`, `LIB` para fijar la zona de la ficha en esas fases. Si no están, la ficha se queda en la zona en que estaba.

### 1.10 Rendimiento (Fase 4)

| Clave | Tipo | Qué hace | Por defecto |
|---|---|---|---|
| `refresco_aire` | Número (s) | Radar del controlador: los móviles en vuelo se refrescan solo cada N segundos (los de tierra, en cada ciclo). Útil en ejercicios largos con mucho tráfico. Solo tiene efecto si es mayor que el refresco del radar (1 s en FIELD/NORTH, 5 s en el resto) | 0 = todos en cada ciclo |

---

## 2. Hoja opcional `SectorSequence` — secuencia de sectores por vuelo

Ajusta la lista de sectores que recorre cada vuelo (transferencias). Si el Excel **no** tiene esta hoja se aplican las reglas por defecto (las que antes estaban en `GTA.load_flight`); si la tiene, **sus reglas sustituyen a todas las de por defecto**.

Fila 1 = cabecera. Una regla por fila; se aplican en orden:

| Col. | Campo | Valores |
|---|---|---|
| A | aeropuerto | Uno o varios separados por comas. Vacío = cualquiera |
| B | operacion | `DEP` (el aeropuerto es el de salida), `ARR` (el de llegada) o vacío |
| C | pista | Texto contenido en la pista de salida/llegada (`06L`). Vacío = cualquiera |
| D | posicion | `TWR` = el ejercicio es de torre pura (la posición tiene LCL o GND y no APP); `APP` = el resto; vacío = siempre |
| E | accion | `QUITAR` (quita esos sectores), `QUITAR_PRIMERO` (quita el primero si contiene alguno de los valores), `AL_FINAL` (los mueve al final), `FIJAR` (sustituye la secuencia; solo cuenta el primer FIJAR que se cumpla) |
| F | valor | Sector o sectores separados por comas (se normalizan: `GMC`→`GND`, `TWR`→`LCL`) |
| G | si_escenario | Opcional: la regla solo se aplica si el escenario tiene alguno de estos aeródromos |

Reglas por defecto (equivalentes a lo que había en el código):

| aeropuerto | operacion | pista | posicion | accion | valor | si_escenario |
|---|---|---|---|---|---|---|
| LEBL | ARR | 06L | | QUITAR_PRIMERO | GND GN | LEBL |
| LEBL | DEP | 06R | | QUITAR | LCL ARR | LEBL |
| LEBL | ARR | 02 | | QUITAR | LCL DEP | LEBL |
| LEBL | ARR | 02 | | QUITAR_PRIMERO | GND | LEBL |
| LEST,LECO,LEVX | DEP | | | AL_FINAL | APP | |
| GCXO,GCTS,GCLP | ARR | | TWR | FIJAR | LCL,GND | GCXO,GCTS,GCLP |
| GCXO,GCTS,GCLP | DEP | | TWR | FIJAR | GND,LCL | GCXO,GCTS,GCLP |
| GCXO,GCTS | ARR | | APP | FIJAR | APP,LCL,GND | GCXO,GCTS,GCLP |
| GCXO,GCTS | DEP | | APP | FIJAR | GND,LCL,APP | GCXO,GCTS,GCLP |

Para añadir una regla a un escenario que ya usa las de por defecto, hay que copiar en la hoja las que le afecten y añadir la nueva.

---

## 3. Hoja opcional `BahiaFijos` — fijos de la bahía de fichas de papel

Fichas fijas (separadores, avisos, texto libre, imágenes) que aparecen al abrir la bahía en las posiciones **no OSF**. Si el Excel no tiene la hoja se usan las de por defecto; si la tiene, sustituye a las de por defecto.

Fila 1 = cabecera:

| Col. | Campo | Valores |
|---|---|---|
| A | posicion | Texto que debe contener el sector de la posición (`APP`, `LCL`...). Se usa el primer filtro que aparezca en el sector; si no aparece ninguno, las filas con la columna A vacía |
| B | tipo | `TEXTO`, `TEXTOLIBRE` (campo editable), `IMAGEN` (un fichero), `IMAGENES` (todos los `Fijo<n>.jpg` de una carpeta, en orden) |
| C | texto | `TEXTO`: texto mostrado. `IMAGEN`: fichero. `IMAGENES`: carpeta. En rutas: `{img}` = carpeta `img` de GAMMA, `{sector}` = sector de la posición, `{config}` = configuración de pistas en uso (minúsculas) |
| D | x | Posición horizontal del texto (opcional; 180) |
| E | id | Identificador interno (opcional; por defecto el texto) |

Fijos por defecto:

| Escenario | Fijos |
|---|---|
| LEAM | RWY 25, RWY 07, PISTA OCUPADA |
| LEGR | Imágenes de `img/LEGR` (Fijo1.jpg...) |
| LEMH | BOMBEROS, SEÑALERO, PISTA 01, PISTA 19, ficha en blanco |
| LEST, LECO, LEVX | Posición APP: LEST, LECO, LEVX, LPPR + 5 de texto libre. Posición LCL: LEST, PISTA OCUPADA + 5 de texto libre |
| LEMD | Imágenes de `img/LEMD/<sector>/NOR` (Fijo0.jpg...) |
| Lleida, Malaga | RWY 13 / RWY 31 y RWY 12/30 / RWY 13/31 (nombres de escenarios antiguos que ya no existen) |

Ejemplo (torre de LEGE con dos avisos y un campo libre):

| posicion | tipo | texto | x | id |
|---|---|---|---|---|
| | TEXTO | PISTA OCUPADA | 150 | |
| | TEXTO | BOMBEROS | 190 | |
| | TEXTOLIBRE | | | |

---

## 4. Lo que sigue dependiendo del aeropuerto en el código

- `Aircraft.get_rot`: giro a 9 º/s de los ATR salvo en GCXO/GCTS/LEST/LEBB/LEMG. Decisión 2 de la unificación: se mantiene sin parámetro.
- `osf/OSF.py`: pushback fijo de LEBB → ya no depende del nombre: hoja `RetrocesosOSF` con datos = regla por stand; sin hoja o vacía = la regla que antes era solo de LEBB (Fase 4).
- `RaElements.VisTrack`: botón 2 sobre el plot → ya no depende de LEST: salidas del aeródromo `smr_ad` o escenarios con `pvh` (Fase 4).
- Valores de ejemplo de las fichas en `OSF.py`/`PrevDesp.py` (`LEBL7Q`, `LEMD`): solo maquetación, sin efecto.
