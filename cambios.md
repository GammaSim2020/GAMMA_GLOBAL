# Registro de cambios — GAMMA_OSF_LECG

---

## [2026-11-24] La bahia de fichas (ATCBahia) deja de tener formato de Barajas — RaElements.py, FIR.py

**Archivo:** `lib/RaElements.py` — `ATCBahia.update()`, `insertar_ficha()` (antes `insertar_ficha_estandar()`), `_ficha_lemd()`, `_es_ad_principal()`, `insertar_ficha_LEMD()`, `leftclicked_LEMD()`, `openTaxiKeyboard()`, `openRedFreeTextKeyboard()`; `lib/FIR.py` — `_default_params()`

Madrid trabaja con OSF, asi que el segundo formato de ficha que convivia en la bahia (el de
Barajas) ya no tiene usuarios y solo estorbaba: duplicaba ~770 lineas de dibujo y de zonas
de clic que nadie ejecuta, y su rastro provocaba fallos reales en los demas escenarios.

1. **Eliminadas `insertar_ficha_LEMD()` y `leftclicked_LEMD()`** y, con ellas,
   `openTaxiKeyboard()` y `openRedFreeTextKeyboard()`, que solo se abrian desde el clic de
   la ficha de Barajas. `insertar_ficha()` ya no reparte entre dos formatos: la que era
   `insertar_ficha_estandar()` pasa a llamarse `insertar_ficha()`.
2. **Corregido `NameError: apron` al insertar una ficha de llegada** (reventaba
   `UCS.process_message` -> `atc_bahia.update()`). La variable `apron` (letra W/E/S del
   estacionamiento de Barajas) solo se calculaba bajo `_ficha_lemd()`, que en la ficha
   estandar es siempre falso, pero se dibujaba cuando el destino era el aerodromo principal
   del escenario. En la unificacion la guarda `f.ades in ('LEMD', 'LEME')` se habia
   traducido a `_es_ad_principal(f.ades)`, cierta en **cualquier** escenario: desde entonces
   toda llegada al aerodromo principal rompia la bahia. Esos dibujos (letra de apron y pista
   en Courier 20/40) son del formato de Barajas y se han quitado.
3. **Retiradas las ramas muertas** de la ficha estandar (todos los `if not
   self._ficha_lemd()` eran tautologicos) y el filtro de vuelos de `update()` que colgaba de
   `fir.name == 'XXXX'` (era el antiguo `== 'LEMD'` neutralizado, nunca entraba).
   Desaparecen los metodos `_ficha_lemd()` y `_es_ad_principal()`, ya sin uso, y los
   locales muertos `escenario = fir.name` de `insertar_ficha()` y `leftclicked()`.
4. **Parametros de escenario**: se elimina `ficha_formato_lemd` (`lib/FIR.py`, `_PARAM_BOOL`
   y su defecto) y `alias_ads` pasa a tener **defecto vacio** en vez de `{'LEME': 'LEMD'}`.
   El mecanismo `alias_ads` se mantiene porque es generico (renombrar el aerodromo escrito
   en la ficha) y esta documentado; solo deja de traer el alias de Barajas de serie.
   Actualizado `docs/PARAMETROS_ESCENARIO.md`.

Las divisiones con nombre de la ficha (`ficha_w1..w11`, `ficha_h1..h4`) se mantienen aunque
la mayoria solo las usaba el formato de Barajas: documentan la geometria de la ficha.

Cambio aplicado **solo en `C:\GAMMA_GLOBAL`**: en `C:\GAMMA` la bahia conserva el codigo
anterior a la unificacion (con `'LEMD'`/`'LEME'` escritos a mano) y no sufre el fallo 2.

---

## [2026-11-04] Mover un punto de la ruta lo borraba en vez de desplazarlo — Pseudopilot.py, GTA.py, Aircraft.py

**Archivos:** `lib/Pseudopilot.py` — `draw_way_point()`; `lib/GTA.py` — `_h_replace_wp()`; `lib/Aircraft.py` — `insert_wp()`

En el pseudopiloto, mover un punto de la ruta con el **botón central** (y, por el mismo
camino, el último punto de la ruta) podía dejar el vuelo **sin ese punto y sin el nuevo**.
En `C:\GAMMA` esto ya estaba resuelto y aquí no se portó completo.

El motivo es una carrera entre cliente y servidor: desde que se pulsa el botón central
hasta que se suelta en la nueva posición pasan segundos, y el avión puede **rebasar** ese
punto mientras tanto. Cuando el mensaje llega a GTA, `fix_old` ya no está en `f.route`:

1. `Aircraft.insert_wp()` sí tenía el escudo de `C:\GAMMA` (`fix_after`: si no encuentra
   `fix_next`, inserta antes del punto siguiente conocido), pero **nadie le pasaba
   `fix_after`** en este camino. `draw_way_point()` lo calculaba solo en el bucle de
   *tramos* (`fix_after_wl`), no en el de *puntos*, y `centerclicked_on_waypoint()` no lo
   enviaba. Ahora se calcula `fix_after_wp` y viaja en el mensaje `replace_wp`;
   `_h_replace_wp()` lo reenvía a `insert_wp()`.
2. `_h_replace_wp()` hacía `insert_wp(...)` y **a continuación `remove_wp(fix_old)` sin
   comprobar nada**. Si la inserción fallaba (solo deja un `logging.warning` y vuelve), el
   borrado sí se ejecutaba: de ahí la desaparición del punto. `insert_wp()` ahora devuelve
   `True`/`False` y el borrado solo se hace si la inserción ha funcionado.

Se mantiene el mensaje atómico `replace_wp` de esta versión (un solo viaje al servidor) en
lugar del `insert_wp` + `remove_wp` por separado de `C:\GAMMA`: con `fix_after` el
comportamiento es el mismo y se evita que las dos órdenes se procesen en ciclos distintos.

3. Quitado un `print "Fallo en insert_wp"` de depuración que quedó dentro del
   `except ValueError` de `rightclicked_on_wayline()` (detrás de un `pass`, así que se
   ejecutaba siempre que se insertaba un punto de parada en un tramo).

No se toca el redibujado limitado a ~30 ms de la ruta en definición (`_route_preview()`,
Fase 4 bloque 3): es solo pintado, no interviene en la carrera.

**Verificación:** sintaxis Python 2.7 (`py_compile`) de los tres ficheros; CRLF y
codificación iso8859-15 conservados.

**Pruebas en el simulador:**
- Pseudopiloto, avión rodando o en vuelo: botón central sobre un punto de la ruta,
  arrastrar unos segundos (dejando que el avión llegue a rebasarlo) y soltar: el punto
  nuevo aparece delante del siguiente punto de la ruta y el antiguo desaparece.
- Botón central sobre el **último** punto de la ruta: se mueve, no se pierde.
- Botón central/derecho sobre un **tramo**: sigue insertando igual que antes.

---

## [2026-10-30] Frustrada automatica y rate de descenso en APP configurables por escenario — Aircraft.py, FIR.py, RaDisplay.py

**Archivo:** `lib/Aircraft.py` — `get_hdg_obj()` (rama `to_do == 'app'`); `lib/FIR.py` — `ESCENARIO.__init__()`, `FIR.__init__()`; `lib/RaDisplay.py` — titulo de ventana

Replicado desde `C:\GAMMA` (ver la entrada homologa alli). El bloque de la aproximacion en `Aircraft.py` era identico al de `C:\GAMMA`, y la lectura de las tres claves nuevas sigue el estilo `try/except` que esta version ya usa para `ifr_taxi_ias`/`vfr_taxi_ias`/`ret_ias`.

### 1. Frustrada automatica (`auto_map`, `auto_map_alt`)

Al llegar a 0.5 NM del umbral (0.05 NM para helicopteros), si la aeronave estaba mas de
200 ft por encima de la senda, el simulador lanzaba `execute_map()` por su cuenta, sin
orden del CTA. Ahora:

```
if fir.auto_map and (self.lvl - fl_gp) > fir.auto_map_alt / 100.:
    self.execute_map()
```

Con `auto_map = 0` (el valor por defecto) la frustrada **solo se ejecuta por orden**.
`auto_map_alt` son los pies por encima de la senda que la disparan cuando esta activada,
asi que se puede dejar encendida solo para desviaciones extremas (p. ej. 1000).

### 2. Limite del rate de descenso en la senda (`app_max_rod`)

El calculo era un termino nominal mas una correccion proporcional, recortado despues al
maximo BADA de la aeronave:

```
rate = ((self.lvl - fl_gp) * 2.0 + self.ground_spd * pdte_ayuda)
if rate < self.perf.max_rod / 60:
    self.set_rate_descend(rate * 100.)
else:
    self.set_rate_descend(self.perf.max_rod * 100. / 60)
```

Pasa a calcularse geometricamente con la **distancia lineal al umbral** (`dist_thr`, no la
distancia de ruta real): tiempo restante hasta el umbral y altitud a perder.

```
rate = self.ground_spd * pdte_ayuda
if dist_thr > 0.1 and self.ground_spd > 1.0:
    t_min = dist_thr / self.ground_spd * 60.
    rate = (self.lvl - alt_pista / 100.) / t_min
max_rod_app = fir.app_max_rod / 100.
if max_rod_app > 0. and rate > max_rod_app:
    rate = max_rod_app
self.set_rate_descend(rate * 100., force=True)
```

`app_max_rod` esta en **ft/min** y `0` (por defecto) significa **sin limite**: ya no se
recorta por `perf.max_rod`, de ahi el `force=True`, que tambien hace falta porque
`set_rate_descend()` vuelve a recortar por su cuenta si no se le pasa. El primer `rate`
queda como respaldo para los casos degenerados (umbral a menos de 0.1 NM, o aeronave
practicamente parada). Cuando la aeronave ya esta sobre la senda la formula geometrica
degenera en el rate nominal de siempre, por lo que el termino proporcional `* 2.0` deja de
hacer falta. La rama de "por debajo de la senda" (`set_rate_descend(0.001)`) no se toca.

### 3. Lectura en FIR.py

`ESCENARIO.__init__` inicializa `auto_map = 0.0`, `auto_map_alt = 200.0` y
`app_max_rod = 0.0`, los lee del sheet `Escenario` como las demas claves y `FIR.__init__`
los propaga. Si la fila no existe en el Excel se mantiene el valor por defecto, asi que
los escenarios antiguos siguen funcionando sin tocar nada.

**Excel del escenario:** filas opcionales en la hoja `Escenario`:

```
auto_map     | 0      (1 para reactivar la frustrada automatica)
auto_map_alt | 200    (pies por encima de la senda que la disparan)
app_max_rod  | 0      (ft/min; 0 = sin limite)
```

### 4. Numero de display en el titulo de ventana

`tl.wm_title()` pasa a incluir el numero de display:
`'GammaSim_' + str(disp_number) + "_" + conf.ver + ': ' + title`. **El formato es
obligatorio**: hay otra aplicacion que parsea ese titulo, asi que no se debe reordenar ni
cambiar los separadores.

**Motivo:** un trafico vectorizado alto no podia recuperar la senda por el tope de
`max_rod`, llegaba alto al umbral y frustraba solo, invalidando el ejercicio. Los dos
defectos se alimentaban entre si, y la decision de si un ejercicio debe comportarse asi
es del instructor, no del codigo.

**Efecto lateral a vigilar:** con `auto_map = 0`, un trafico que aun asi llegue alto al
umbral lo cruzara por encima de la senda y seguira descendiendo hasta la comprobacion de
toma (`lvl < alt_pista/100. + 10 ft`), es decir, tomara largo en lugar de frustrar. Y sin
`app_max_rod` el descenso puede ser mas fuerte de lo que daria de si un avion real.

Verificado solo con `py_compile` (Python 2.7.14); sin prueba en simulacion.

---

## [2026-10-14] Frustrada (MAP) con puntos sin nivel en el escenario — Aircraft.py

**Archivo:** `lib/Aircraft.py` — `execute_map()`, `get_hdg_obj()`

Al ejecutar una frustrada se rompia el bucle de simulacion con
`TypeError: unsupported operand type(s) for /: 'NoneType' and 'float'`.

La causa es de datos, pero el codigo no la toleraba: en la hoja `Procedimientos`
la columna de altitud de la fase `MIS` puede venir vacia, y `FIR` guarda entonces
`None` en el nivel de ese punto de `puntos_map`. Los bucles que construyen la ruta
ya lo contemplaban (`if p[3] is not None`), pero no los dos sitios que dividen
directamente entre 100:

1. `execute_map()` tomaba siempre `puntos_map[0][3]` como nivel de frustrada. Ahora
   busca el primer punto del MAP que si traiga nivel; si ninguno lo trae, se mantiene
   el CFL actual en lugar de abortar el `timer()` del GTA.
2. `get_hdg_obj()`, rama *going around*: al alcanzar cada punto del MAP asignaba
   `h / 100.` sin comprobar `None`. Ahora un punto sin nivel se interpreta como
   "sin restriccion" (se mantiene el CFL), igual que ya se hacia con `puntos_alt`.

Detectado con `C:\03 ESCENARIOS\DRNA_CN\LEAS\LEAS.xlsx`: el procedimiento
`LEAS29ISAC` tiene los dos primeros puntos de su `MIS` sin altitud (solo el ultimo,
`_ISAAC`, lleva 2700).

**Dato corregido en el escenario:** en `LEAS.xlsx`, hoja `Procedimientos`, celda
`H478` (primer punto de la `MIS` de `LEAS29ISAC`) = **5000**. Ese punto es el mismo
exacto que el primer punto de la `MIS` de `LEAS29RNPZ`/`LEAS29RNPY` (filas 470 y 484),
que ya declaraban 5000; los puntos intermedios se dejan vacios como en el resto del
fichero. Copia previa en `LEAS_backup_20261014.xlsx`.

**Pendiente (otro escenario):** `DRNA_CN\LEMD\LEMD.xlsx` tiene el mismo hueco en
`LEMD18LILSY` (fila 780); su gemelo `LEMD18L_3NM` declara 2900 en ese mismo punto.

---

## [2026-10-05] Unificación — Fase 5 (pendientes de GAMMA): botón SEP, F7 y recuperación de la bahía de fichas — UCS.py

Tres puntos de alta prioridad del análisis que no se habían portado (detectados al preparar el checklist de pruebas):

1. **Botón SEP** de la barra del controlador: activa/desactiva la separación automática de etiquetas (`toggle_auto_separation`). Antes se creaba sin comando y no hacía nada. Arranca encendido si la separación está activa (en LEMD/LEBL sigue apagada por el parámetro `separar_etiquetas`).
2. **F7** imprime en la bahía de fichas la ficha del vuelo seleccionado (solo posiciones sin OSF; la función `imprimir_ficha` existía pero la tecla no estaba asociada).
3. **Bahía de fichas (posiciones sin OSF):** al arrancar se recuperan su posición/tamaño (`atc_bahia_geometry`) y si estaba visible u oculta (`atc_bahia`). Se guardaban al salir pero no se leían. No se fuerza la ventana maximizada (en GAMMA sí).

**Verificación:** sintaxis Python 2.7 (lib2to3); CRLF conservado.

**Pruebas:** botón SEP encendido/apagado con etiquetas solapadas; F7 con un vuelo seleccionado en LEGR/LEMH/LEST; mover y ocultar la bahía, salir y volver a entrar.

---

## [2026-10-05] Unificación — Fase 5: arranque, configuración, codificación, datos y retoques de GAMMA — GAMMA_Start.py, GAMMA.py, GAMMA.ini, ConfMgr.py, 8 .py (codificación), bada.txt, Modelos_avo.txt, RaElements.py, RaDisplay.py, Pseudopilot.py, Editor.py, Pantalla.py, Route.py

Decisiones del usuario: versión **1.0.0**; carpeta de red de actualización **`\\nacl0400\INTERREGIONAL\GAMMA\08 GAMMA PRODUCCION\GAMMA_GLOBAL`**.

### A. Arranque y actualización (`GAMMA_Start.py`, reescrito)
1. Carpeta de red leída de `GAMMA.ini` (`update_dir`, y `update_dir_alt` si la primera no responde; por defecto las dos de `GAMMA_GLOBAL` con `nacl0400` y `nacl0400.nav.es`). Antes estaba fija en el código (`GAMMA_TWRAPS`).
2. Carpeta local = la del propio script (antes fija `C:/GAMMA_TWRAPS`, también las imágenes de la ventana de arranque).
3. Al actualizar **no se copian**: `gamma_settings.json` (configuración de cada puesto), `*.log`, `log/`, `*.pyc`, `*.bak`, `*.tmp`, `Thumbs.db`, `.git`, `.idea`, `.vscode`, `.claude`. Antes se copiaba todo, y una actualización podía pisar la configuración personal de pantallas.
4. **Sin red/VPN** o sin `GAMMA.ini` remoto: se arranca la versión local (antes `int('')` daba error y no arrancaba).
5. Se mantiene el criterio de versión: cualquier diferencia con la del servidor actualiza (por eso bajar de 1.0.05 a 1.0.0 funciona).

### B. Configuración (`ConfMgr.py`, `GAMMA.py`, `GAMMA.ini`)
6. `gamma_settings.json` y `GAMMA.ini` se buscan **junto al programa** (`_script_dir`, como en LEBL), no en la carpeta desde la que se arranca. `GAMMA.py` y `GAMMA_Start.py` hacen además `chdir` a su carpeta (log, `img/`, `lib/`... siempre relativos a la instalación). `GAMMA.py` crea `log/` si no existe.
7. `common_dir` por defecto = carpeta del programa (se guarda como `.` para que la configuración siga valiendo si se mueve la instalación).
8. **Guardado atómico** de `gamma_settings.json`: se escribe `gamma_settings.json.tmp` y luego se sustituye; si el principal falta o está dañado, se lee el temporal.
9. **Migración desde `GAMMA.ini` antiguo**: nunca había funcionado (llamaba a `save()` antes de crear los atributos) → corregido. Además limpia los valores en forma de lista de la versión LEBL (`['2']` → `2`).
10. `GAMMA.ini`: `ver = 1.0.0`, `update_dir`, `update_dir_alt`.

### C. Codificación (ficheros declarados iso8859-15)
11. Texto UTF-8 dentro de ficheros iso8859-15 pasado a iso8859-15 (se veía `Ã³` en vez de `ó` en mensajes como «Obstáculo...» o «desconexión»): FIR, GTA, Pseudopilot, RaDisplay, RaElements, UCS, PrevDesp.
12. Caracteres perdidos (� o `?`) restaurados por palabra: textos del pseudopiloto («No hay ningún vuelo seleccionado», «Dirección:», «Rumbo después de fijo», «Añada procedimiento de aproximación», «Órbita inmediata», «Precipitación», «Anemómetro», «¿Desea recargar el ejercicio?»...), RaElements («Aproximación», «después»), UCS («ningún»), GTA («está ocupado... aplicación») y comentarios.
13. Comprobado: el código (todo lo que no es texto ni comentario) es idéntico token a token; mismas líneas y CRLF. `osf/OSF.py` (declarado utf-8) no se toca.

### D. Datos y retoques de GAMMA
14. `bada.txt`: perfiles BADA de **CRUZ, F18 y TOBA** (de GAMMA). `Modelos_avo.txt`: modelos **CRUZ, TOBA y P28A** (formato RECAT de GLOBAL, estela L). F18 ya estaba.
15. Botón **AC de 3 estados** (de GAMMA): verde = PAC + VAC, amarillo = solo VAC, rojo = sin avisos. Antes solo PAC verde/rojo. Arranca en verde en todas las posiciones (en GAMMA el pseudopiloto arrancaba en rojo; no se ha copiado).
16. Pseudopiloto: casillas **WheelMouse** (zoom con la rueda) y **GrabDisplay** (arrastre de pantalla) en la barra, activadas por defecto.
17. `RaDialog.close`: quita el diálogo por la etiqueta con que se registró (antes `del` con el texto del título podía fallar).
18. Editor: método `notify()` que se llamaba y no existía (aviso sonoro). `Pantalla.py` crea la carpeta `Edit/` si no existe. `Route.WayPoint.elvl = 0.0` por defecto.

### E. Limpieza
19. Borrados (con permiso del usuario): `GAMMA_interface/Nuevo documento de texto.txt` (vacío) y `lib/UCS.py.mioNoJoserra` (copia antigua de UCS.py).

**Verificación:** sintaxis Python 2.7 (lib2to3) de todos los `.py` de GAMMA_GLOBAL; CRLF/LF conservados; `ConfMgr` probado fuera del simulador (rutas, versión, guardado atómico, migración de un `GAMMA.ini` de LEBL).

**Para poner en producción:** copiar GAMMA_GLOBAL a la carpeta de red `...\08 GAMMA PRODUCCION\GAMMA_GLOBAL` **sin** `gamma_settings.json` ni `log/`, con su `GAMMA.ini` (`ver = 1.0.0`). Los puestos que hoy arrancan desde `GAMMA_TWRAPS`, `GAMMA` o `GAMMA_OSF_LEBL` necesitan una vez el `GAMMA_Start.py` y el `GAMMA.ini` nuevos (los suyos apuntan a la carpeta antigua).

**Pruebas:**
- `python GAMMA.py` desde otra carpeta (p. ej. `cd C:\` y `python C:\GAMMA_OSF_U\GAMMA_GLOBAL\GAMMA.py`): arranca y conserva la configuración de pantallas.
- Pseudopiloto: textos con tildes en los diálogos; casillas WheelMouse/GrabDisplay; botón AC verde→amarillo→rojo.
- Editor: recibir un informe de piloto (sin error de `notify`).
- `GAMMA_Start.py` (solo cuando se quiera probar la actualización): sin red debe arrancar la versión local.

---

## [2026-10-05] Unificación — Fase 4 (resto LEBL): regla de retroceso (push-back) por stand para todos los escenarios — osf/OSF.py, FIR.py

Decisión del usuario: la regla por stand vale para todos los escenarios; si el escenario no tiene la hoja `RetrocesosOSF` o está vacía, se usa la regla que estaba escrita en el código solo para LEBB. Desaparece la condición `fir.ap[0] == "LEBB"`.

Nuevo `OSF._pushback_rule(f)`:
- **Hoja con datos y stand con retroceso** (`S` en la columna C): menú ACCIONES con SOLICITUD/AUTORIZACIÓN P/B y las direcciones permitidas (P/W, P/E, P/S, P/N) + AUTORIZACIÓN TAX (igual que antes).
- **Hoja con datos y stand sin retroceso** (nuevo, de LEBL): S/U → SOLICITUD TAX / AUTORIZACIÓN TAX; clic en el indicador S/U → TAX (sin pasar por P/B); REVOCAR de TAX o de TXR vuelve a S/U.
- **Sin hoja o vacía** → regla general (antes solo LEBB): S/U → SOLICITUD P/B, AUTORIZACIÓN P/W, AUTORIZACIÓN P/E, AUTORIZACIÓN TAX; secuencia S/U → P/B → TAX como hasta ahora.

Además, `FIR` leía solo 3 columnas de direcciones (D-F) de `RetrocesosOSF`: en LEPA, cuyos stands tienen N, S, E y W, se perdía **W**. Ahora se leen D-G.

Efecto por escenario (Excel de `C:\03 ESCENARIOS`):
- LEBL, LEPA, LEMD: hoja con datos → regla por stand (cambia: los stands sin `S` ya no pasan por P/B).
- LEBB: hoja vacía → la misma regla de antes.
- GCLP, GCTS, GCXO (hoja vacía), LEST, LERS, LEMG (sin hoja): **cambia el menú de S/U**: antes SOLICITUD P/B, SOLICITUD TAX, AUTORIZACIÓN TAX; ahora SOLICITUD P/B, AUTORIZACIÓN P/W, AUTORIZACIÓN P/E, AUTORIZACIÓN TAX. Para tener regla por stand, rellenar su hoja `RetrocesosOSF`.

**Verificación:** sintaxis Python 2.7 (lib2to3) de OSF.py; CRLF conservado; contenido de `RetrocesosOSF` comprobado en los Excel vigentes.

**Pruebas en el simulador:** LEBL con un stand con retroceso (p. ej. 100, dirección E) y otro sin él: menú ACCIONES en S/U, clic en el indicador y REVOCAR desde TAX. LEBB y GCLP: menú de S/U con P/W y P/E.

---

## [2026-10-05] Unificación — Fase 4 (bloque 3): rendimiento en ejercicios largos (de GAMMA_OSF_LEBL) — UCS.py, Pseudopilot.py, osf/OSF.py, FIR.py, docs/

Ajustes que LEBL tenía para que la pantalla no vaya a tirones con mucho tráfico (ejercicios de ~2 h). Decisión del usuario: el refresco del radar, opcional por Excel; las otras dos mejoras, para todos los escenarios.

1. **Refresco de los móviles en vuelo (parámetro `refresco_aire`, segundos; opcional).** Si vale más de 0, en el radar del controlador las etiquetas de los móviles en vuelo se refrescan solo cada `refresco_aire` s; los que están en tierra (rodaje, despegue, aterrizados) siguen en cada ciclo. Por defecto 0 = todos en cada ciclo, como antes. En LEBL era fijo en 3 s; aquí **no se activa en ningún escenario** salvo que se añada la fila (p. ej. `refresco_aire | 3`). Solo tiene efecto si es mayor que el refresco del radar (1 s en orientación FIELD/NORTH, 5 s en el resto).
2. **Pseudopiloto — ruta que se está definiendo con el ratón** (mover un punto, insertar punto en un tramo): como mucho un redibujado cada ~30 ms y reutilizando el punto y la línea del canvas (antes se borraban y creaban en cada movimiento del ratón y se forzaba `update_idletasks`). Mejorado respecto a LEBL: dibuja la última posición del ratón (LEBL dibujaba la primera de cada intervalo) y cancela el redibujado pendiente al terminar o cancelar. Todos los escenarios.
3. **Bahía OSF — no se redibuja con un campo en edición** (campo libre, stand, anotaciones...): el redibujado periódico ya no interrumpe lo que se está escribiendo; al guardar o cancelar se redibuja. Todos los escenarios. (El redibujado por cambio de alertas, bloque 1, tampoco actúa durante un arrastre.)

No incluido: la propuesta `docs/2026-02-26-optimizacion-ejercicios-2h.md` de LEBL, que no está implementada en ninguna versión.

**Verificación:** sintaxis Python 2.7 (lib2to3) de UCS, Pseudopilot, OSF y FIR; CRLF conservado.

**Pruebas en el simulador:**
- Pseudopiloto: mover un punto de ruta y insertar un punto en un tramo (botón central y derecho): la línea amarilla sigue al ratón con fluidez; al confirmar o cancelar no queda nada amarillo en pantalla.
- OSF: escribir en un campo libre/stand mientras llegan fichas nuevas: el campo no se cierra ni se mueve; al pulsar Intro aparecen las fichas nuevas.
- Opcional: en un escenario con mucho tráfico, añadir `refresco_aire | 3` y comprobar que los aviones en tierra se mueven cada segundo y los del aire cada 3 s.

---

## [2026-10-05] Unificación — Fase 4 (bloque 2): vehículos con Plan de Vehículo (PVH) y cruce/entrada a pista CRU/ENT/LIB (de GAMMA_OSF_LEBL) — FIR.py, GTA.py, Aircraft.py, osf/OSF.py, UCS.py, RaElements.py, docs/

Portado desde GAMMA_OSF_LEBL el flujo de vehículos y de cruce/entrada a pista en OSF. Se controla con el **parámetro de escenario `pvh`** (Sí/No): por defecto **sí en LEBL** (era la única versión que lo tenía) y no en el resto. Con `pvh` = 0 todo queda como antes de este bloque.

### A. Servidor y avión
1. `Aircraft`: constantes `LIB` (pista libre), `CRUREQ` (`CRR`), `ENTREQ` (`ENR`); atributos `cru_runway`, `pre_cru_pof`, `has_pvh`, `pvh_notes`, `ent_runway`, `pre_ent_pof`.
2. `GTA`: comandos `request_cru`, `cancel_cru`, `create_pvh`, `delete_pvh`, `authorize_ent`, `request_ent`, `set_pvh_notes` (código de LEBL). `_h_set_osf_pof` limpia pista y fase previa de CRU/ENT al volver a TAX.

### B. Bahía OSF (`osf/OSF.py`)
3. Botón **VEH** en la barra (solo con `pvh`): diálogo CREAR PLAN DE VEHÍCULO (indicativo + anotaciones). Los vehículos solo tienen ficha cuando tienen PVH; ficha propia `act | callsign | pista_ent | anotaciones` en azul, sin ficha extendida.
4. Indicador de acción: `CRR`→CRU→LIB→TAX (aviones y vehículos), `ENR`→diálogo de pista→ENT→LIB→TAX (vehículos). Textos CRU/ENT/LIB, solicitudes en amarillo y LIB en gris.
5. Menú ACCIONES: vehículo con PVH → SOLICITUD/AUTORIZACIÓN ENT, SOLICITUD CRU, ANOTACIÓN RWY LIBRE, AUTORIZACIÓN TAX, TERMINAR PVH, ELIMINAR PVH. Aviones en rodaje → SOLICITUD CRU y ANOTACIÓN RWY LIBRE (solo con `pvh`). EDITAR OBSERVACIONES de un vehículo edita sus anotaciones.
6. REVOCAR deshace los pasos CRR/CRU/ENR/ENT/LIB.
7. Diálogos de pista (PISTA ENTRADA / PISTA CRUCE): cabeceras del aerodromo del móvil; **si no se conoce, todas las del escenario** (antes, lista fija de pistas de LEBL `02, 06L, 06R, 20, 24L, 24R`).
8. Clic en el campo `anotaciones` → edición en la ficha; ahora envía `set_pvh_notes` (en LEBL enviaba `create_pvh` por error, que además devolvía el vehículo a TAX).
9. Zona de las fichas en CRR/CRU/ENR/ENT/LIB: si la hoja `OSF` del escenario no recoge esos estados (la de LEBL no los tiene), la ficha se queda en su zona; si no se conoce, zona según el estado (como hacía LEBL).
10. Ventana OSF: usa `self.sector` (sector propio de la ventana, multi-LCL de GLOBAL) en lugar de `radisplay.sector` de LEBL.

### C. Radar (`UCS.py`, `RaElements.py`)
11. Etiqueta de vehículo con PVH (`atc-veh-pvh`): indicativo, fase, pista de entrada/cruce (azul) y anotaciones; color `#5599FF` (sin PVH `#99DD99`) — solo con `pvh`; los colores del resto de móviles no cambian.
12. Con `pvh`: clic izquierdo en el indicativo de un vehículo sin PVH abre CREAR PV (en vez de asumir); botón central sobre el plot rellena el indicativo del diálogo; botón derecho sobre el plot de un vehículo con PVH en TAX/ENR abre PISTA ENTRADA.
13. **Botón central del plot**: antes solo en salidas de `LEST` (escrito en el código) → salidas del aerodromo del parámetro `smr_ad` (el mismo comportamiento en LEST) o escenarios con `pvh`. El botón derecho primero deja actuar a la pantalla y, si no hace nada, alterna «solo plot» como antes.

### D. No portado
- Menú CRU del pseudopiloto (`_show_cru_menu`): en LEBL estaba desactivado (llamada comentada). Las solicitudes de cruce las crea el controlador desde ACCIONES.
- Regla de pushback por stand de LEBL (`S/U`→P/B o TAX según `RetrocesosOSF`) y la rama fija de LEBB: se tratan aparte (pendiente).

**Verificación:** sintaxis Python 2.7 (lib2to3) de FIR, GTA, Aircraft, UCS, RaElements y OSF; CRLF conservado; sin caracteres no ASCII nuevos; parámetro `pvh` = Sí solo en LEBL y la fila `pvh | 0` lo desactiva. Fuera del simulador no se puede probar la interfaz.

**Pruebas en el simulador (LEBL, posición GND con OSF):**
- Botón VEH → crear PVH a un vehículo (o clic en su indicativo en el radar): aparece la ficha azul y la etiqueta con fase y anotaciones.
- ACCIONES → SOLICITUD ENT → elegir cabecera (ENR amarillo) → clic en el indicador → PISTA ENTRADA → ENT → ANOTACIÓN RWY LIBRE (LIB) → AUTORIZACIÓN TAX. REVOCAR en cada paso.
- Avión rodando: ACCIONES → SOLICITUD CRU → cabecera → CRR → CRU → LIB → TAX. REVOCAR en CRR (vuelve a TAX).
- Editar anotaciones del vehículo (campo de la ficha y EDITAR OBSERVACIONES): el vehículo no cambia de fase.
- TERMINAR PVH / ELIMINAR PVH.
- Con alertas: CMAC/CATC de cruce y entrada (CRU_NA, ENT_NA...) con vehículos.
- Otro escenario OSF (LEST, GCLP): sin botón VEH ni opciones CRU; en LEST el botón central del plot sigue funcionando en salidas.

---

## [2026-10-05] Unificación — Fase 4 (bloque 1): alertas aeroportuarias INCW / CMAC / CATC (de GAMMA_OSF_LEBL) — lib/alertas/ (nuevo), FIR.py, GTA.py, Aircraft.py, RaElements.py, UCS.py, osf/OSF.py, docs/PARAMETROS_ESCENARIO.md

Portadas desde GAMMA_OSF_LEBL las alertas de incursión en pista (INCW), de autorización (CMAC) y de conflicto entre móviles (CATC). **Solo se activan si el Excel del escenario trae la hoja `INCWareaIncur`** con zonas del aeródromo; en el resto de escenarios no cambia nada (no se crea el motor, no se dibujan alitas ni líneas). Hoy traen las hojas **LEBL y LEPA**: para no tener alertas en LEPA basta añadir en su hoja `Escenario` la fila `alertas | 0` (parámetro nuevo, por defecto 1).

### A. Motores (`lib/alertas/`, copiado de LEBL)
1. `AlertManager`, `INCWEngine`, `CMACEngine`, `CATCEngine` y `alert_types` (los `.pyc` no se copian).
2. **Pista recíproca calculada** (`alert_types.reciprocal_rwy`: `06L`→`24R`, `02`→`20`, `13`→`31`) en lugar de la tabla fija de pistas de LEBL repetida en los tres motores. Para las pistas de LEBL da el mismo resultado.
3. `AlertManager` respeta el parámetro `alertas`; sin zonas INCW o con `alertas = 0` no crea los motores (`available = False`).
4. Comentarios con caracteres UTF-8 (→, —, ñ) pasados a ASCII.

### B. Carga del escenario (`FIR.py`)
5. `ESCENARIO._load_incw_sheets()` / `_load_cmac_sheets()` / `_load_catc_sheets()` / `_parse_dms_value()` (código de LEBL sin cambios de lógica), llamados al final de la lectura del Excel dentro de `try`: un error en esas hojas se registra y deja las alertas desactivadas, sin impedir la carga del escenario.
6. `FIR._load_incw_zone_maps()`: zonas en NM para los motores (`fir.incw_zones`) y mapas `INCW NO-LVP`, `INCW LVP`, `INCW ALIN`. Siempre inicializa los atributos (`incw_*`, `cmac_*`, `catc_subtypes`) aunque no haya hojas.
7. Parámetro `alertas` (Sí/No) en `_default_params` / `_PARAM_BOOL`.

### C. Servidor (`GTA.py`) y avión (`Aircraft.py`)
8. Import opcional de `alertas`; `_init_alert_manager()` en `load()` **y en `reload_exercise()`** (en LEBL no se recreaba al recargar y se arrastraban los reconocimientos del ejercicio anterior).
9. `timer()`: `alert_manager.evaluate(...)` cada ciclo, solo si está activo.
10. `_h_runway_config_update` guarda la configuración de pistas de la ventana USO PISTAS para las alertas; comando nuevo `ack_alert` (asumir alertas de un móvil y de su par).
11. `Aircraft`: atributos `active_alerts`, `max_alert_severity`, `top_alert`, `cmac_inhibited`, `catc_pred`; `set_osf_pof(LDG)` marca `lnd_auth` (lo usa CMAC). `Aircraft_update` lleva los campos de alerta (con **copia** de la lista, porque el broadcast se serializa en otro hilo).

### D. Pantallas
12. `RaElements.VisTrack`: texto WNG/VIO encima de la etiqueta con parpadeo hasta asumirla (clic izquierdo = asumir, derecho = ventana del móvil), marco rojo para VIO, ventana tabular RW/AS/CMAC/CATC (▲ en la ventana del móvil), fase en morado con predicción CATC, clic derecho en el indicativo abre la ventana de alertas si las hay. Colores de GLOBAL respetados.
13. `UCS`: copia de los campos de alerta al recibir `update`, líneas roja/amarilla entre pares en conflicto (`_update_conflict_lines`, no hace nada si no hay alertas). Ventana USO PISTAS: una pista sin operación ni NO EN USO ni CERRADA se envía como NO EN USO (sin efecto en los mapas; evita alertas de cruce en pistas sin uso declarado).
14. `osf/OSF.py`: alitas W/V en los márgenes de la ficha, fase en morado con predicción CATC, ancho del campo `alerta` (layout de LEBL) y redibujado de la bahía solo cuando cambia el estado de alertas (no con un campo en edición ni durante un arrastre).

**No incluido (Fase 4, bloque 2):** vehículos PVH y cruce/entrada a pista CRU/ENT/LIB. Los motores ya leen esos atributos con valor por defecto, así que funcionan sin ellos (sin alertas de vehículos ni de cruce autorizado).

**Verificación:** sintaxis Python 2.7 (lib2to3) de todos los ficheros tocados y de `lib/alertas`; CRLF conservado; sin caracteres no ASCII nuevos. Fuera del simulador (python3): lectura de las hojas con los Excel reales — LEBL (24 zonas, 8 pistas, 8 cruces, 12 subtipos CMAC, 20 CATC), LEPA (12 zonas, 4 pistas), LEST (sin hojas → desactivado); `AlertManager` activo en LEBL, inactivo con `alertas = 0` y en LEST; evaluación de los tres motores con móviles sintéticos en las zonas de la 02 (genera CMAC/INCW/CATC sin errores).

**Pruebas en el simulador:**
- LEBL: aparecen los mapas `INCW NO-LVP/LVP/ALIN`; tras **EJECUTAR en USO PISTAS**, un avión rodando a la pista sin autorización da WNG/VIO sobre la etiqueta y alitas W/V en la ficha OSF; clic izquierdo en el texto lo asume (deja de parpadear, también en las otras posiciones); clic derecho abre la ventana del móvil y ▲ la tabular; líneas entre pares en conflicto.
- LEBL: reiniciar el ejercicio y comprobar que las alertas vuelven a salir (motor nuevo).
- LEPA: decidir si se quieren alertas (si no, fila `alertas | 0`).
- Un escenario sin hojas (LEST/LECG, un PICT): sin cambios respecto a antes.

---

## [2026-10-02] Unificación — Fase 3 (parte 2): bahía de fichas, USO PISTAS y Editor sin nombres de aeropuerto — FIR.py, RaElements.py, UCS.py, Editor.py, img/LEGR, docs/PARAMETROS_ESCENARIO.md, CLAUDE.md

Continuación de la Fase 3 (la parte 1 la ha probado el usuario el 2026-10-02 sin incidencias). Mismo criterio: lo que dependía del nombre del escenario pasa a parámetros con valor por defecto igual al comportamiento anterior. **Guía completa para quien edita los Excel: `docs/PARAMETROS_ESCENARIO.md`** (todas las claves de las partes 1 y 2, hojas `SectorSequence` y `BahiaFijos`, ejemplos).

### A. Fijos de la bahía de fichas (`RaElements.ATCBahia`, posiciones no OSF)
1. **`insert_fijo()` y `update_fijos()` reescritos (≈800 → 140 líneas).** Había un bloque copiado por escenario (LEAM, LEGR, LEMH, LEST/LECO/LEVX, Lleida, Malaga, LEMD, Barcelona) que solo cambiaba el texto, la posición x o la carpeta de imágenes. Ahora un único `_crear_fijo()` dibuja cada fijo a partir de una descripción (`fir.bahia_fijos`):
   - hoja opcional **`BahiaFijos`** del escenario (posición, tipo `TEXTO`/`TEXTOLIBRE`/`IMAGEN`/`IMAGENES`, texto o ruta, x, id);
   - si no existe, `FIR._default_bahia_fijos()` con los mismos fijos que había en el código.
   - Al arrastrar un fijo se reconstruye con su descripción (`canvas.fijo_spec`), no buscando su escenario: antes, en LEMH los fijos `PISTA 01`/`PISTA 19` reaparecían como `PISTA01`/`PISTA19` tras moverlos.
2. **Carpeta de imágenes inexistente ya no rompe la pantalla.** `update_fijos` hacía `os.listdir('img/LEGR')` sin protección y GAMMA_GLOBAL no tenía esa carpeta → excepción al crear la bahía en cualquier posición de LEGR. Ahora se registra un aviso y la bahía se abre sin esos fijos. Además se ha **copiado `img/LEGR` (Fijo1-4.jpg) desde GAMMA** a `GAMMA_GLOBAL/img/LEGR`.
3. **Imágenes numeradas:** se cargan todos los `Fijo<n>.jpg` de la carpeta en orden numérico. Antes en LEGR se usaba `range(1, nº de ficheros)` y se perdía la última imagen (Fijo4) si no había otro fichero en la carpeta (p. ej. `Thumbs.db`). LEMD sigue empezando por `Fijo0`.
4. `SEÑALERO` (LEMH) se ve de nuevo con Ñ (el fichero tenía `SE?ALERO` por la pérdida de codificación).
5. **Filtro de la bahía de torre (`ATCBahia.update`).** El código insertaba en las posiciones de torre (`LCL`/`TWR`) **solo fichas de LEST, en todos los escenarios** (en GAMMA solo se hacía para la posición `LEST TWR`): las torres de LEGR, LEAM, LEMH... no veían ninguna ficha. Ahora es el parámetro `bahia_torre_ads` (por defecto `LEST` solo en LEST/LECO/LEVX; vacío = todas en el resto). **Cambio de comportamiento a probar** en un escenario PICT con posición de torre.
6. Barcelona (escenario antiguo `Barcelona.xlsx`, ya no existe): la elección de carpeta de imágenes por configuración y sector (`GMC-N`...) **no se ha portado**; con la hoja `BahiaFijos` y los comodines `{config}`/`{sector}` se puede reproducir si hiciera falta.

### B. Fichas de la bahía (`insertar_ficha*`, `leftclicked*`)
7. `fir.name == 'LEMD'` (formato de ficha y clic de Barajas) → parámetro `ficha_formato_lemd`. `('LEMD', 'LEME')` → "aeródromo principal del escenario" contando alias; `LEME → LEMD` → parámetro `alias_ads`.
8. Pista según configuración de Barcelona (6 bloques repetidos) → parámetro `ficha_pistas_config` (`AD CONFIG` → salidas, llegadas), en un único `_rwy_txt_config()`.
9. `fir.name == 'LECG'` (borde azul de LPPR y teclado en el campo frecuencia) → parámetros `ficha_borde_salida_ads` y `ficha_freq_teclado`. **Nota:** esas dos condiciones nunca se cumplían (el escenario de LECG se llama `LEST`); el valor por defecto mantiene ese comportamiento. Para activarlas hay que añadir las filas en `LEST.xlsx`.
10. **Posiciones multisector en la bahía:** las 25 consultas `fir.local_ads[sector]` daban `KeyError` con `'A,B'` (la Fase 2 solo corrigió la inserción). Ahora `ATCBahia._local_ads()` une los aeródromos locales de cada sector.

### C. Ventana USO PISTAS y mapas (`UCS`)
11. Pares de pistas de la ventana (`13/31`, `02/20`, `06L/24R`, `06R/24L`, fijos para todos los escenarios) → parámetro `uso_pistas` (por defecto los mismos).
12. `update_runway_maps`: los nombres de mapa candidatos se generan para cada pista de la configuración (`ARR_<p>`, `<p>_ARR`, `DEP_<p>`, `MIXTO_<p>`...) en lugar de una tabla solo con pistas de LEBL; los mapas de pista cerrada salen del parámetro `mapas_pista_cerrada` (por defecto la tabla de LEBL; para otras pistas `<p>_CLSD` o el de la recíproca). Nueva función `_reciprocal_rwy()`.
13. Salidas en una línea con SMR activo: `f.adep == 'LEST'` → aeródromo del parámetro `smr_ad` (quedaba de la parte 1).

### D. Editor
14. `fir.name == 'LECB'` (arranque sin rutas/puntos/sectores y sin botones de fijos) → parámetro `editor_mapas_reducidos`.

### E. Documentación
- `docs/PARAMETROS_ESCENARIO.md`: guía de todas las claves de escenario y de las hojas opcionales.
- `CLAUDE.md`: nueva sección *Scenario parameters* (norma: no escribir nombres de aeropuerto en el código; cómo añadir un parámetro) y nota de velocidades de rodaje actualizada.

**Verificación:** sintaxis Python 2.7 (lib2to3) de FIR, RaElements, UCS y Editor; CRLF conservado. Probados fuera del simulador: selección de fijos por posición (LEST APP/LCL/GND, LEMH, LEAM, LEGR, LEMD), expansión de la carpeta de imágenes con `img/LEGR` real, lectura de una hoja `BahiaFijos` de prueba, parámetros nuevos en la hoja `Escenario`, pista recíproca y tabla de pista cerrada igual a la anterior.

**Pruebas en el simulador:**
- LEGR (posición GRANADA): la bahía abre con 4 fijos de imagen (antes fallaba en GLOBAL); fichas visibles.
- Un PICT con posición de torre (LEAM, LEMH o LEGE): **ahora sí aparecen fichas en la bahía**; fijos de LEAM/LEMH; arrastrar un fijo y un campo de texto libre.
- LECG (LEST, posición APP y TWR): fijos y 5 campos libres; en TWR solo fichas de LEST, como antes.
- Posición multisector en un escenario PICT: fichas en la bahía sin errores.
- LEBL/LEPA: ventana USO PISTAS y mapas de pista cerrada/llegadas/salidas como antes.

---

## [2026-10-02] Unificación — Fase 3 (parte 1): parámetros de escenario en lugar de reglas fijas por aeropuerto — FIR.py, GTA.py, Aircraft.py, TLPV.py, RaDisplay.py, UCS.py, Pseudopilot.py, RaElements.py

Tercera fase de la unificación (ver `..\ANALISIS_UNIFICACION.md`, §6). Las condiciones del tipo `if fir.name == 'LEMD'` pasan a ser **parámetros de escenario** que se leen de la hoja `Escenario` (columna A = clave, igual que `taxi_ias` o `zonasOSF`). **No hace falta tocar ningún Excel**: si la fila no existe se usa un valor por defecto que reproduce exactamente lo que hacía el código para ese escenario. Todos los valores por defecto están en un único sitio: `FIR._default_params()`.

Al cargar, el log muestra `Parametros de escenario <nombre>: {...}` con los valores efectivos.

### A. Parámetros (hoja `Escenario`)
Valores sí/no: `1`/`0` (también `SI`/`NO`). Listas separadas por comas en la columna B.

| Clave (col. A) | Col. B | Col. C | Por defecto (= comportamiento previo) | Dónde |
|---|---|---|---|---|
| `stca` | 1/0 | | 0 en LEMD y LEBL, 1 resto | RaDisplay.update |
| `separar_etiquetas` | 1/0 | | 0 en LEMD y LEBL, 1 resto | RaDisplay.update |
| `tabulares_aux` | 1/0 (mostrar COOR/PREACT/ACT) | | 0 en LEMD y LEBL | UCS |
| `tabulares_aux_actualizar` | 1/0 | | 0 en LEMD | UCS |
| `prevdesp_actualizar_ficha` | 1/0 | | 0 en LEMD y LEBL | UCS.process_message |
| `sob_tabular` | 1/0 | | 1 si el escenario tiene LEPA | UCS |
| `smr_ad` | aeródromo del SMR (vacío = sin SMR) | | LEST si el escenario tiene LEST | UCS (tabular No Correlados, botón SMR, plot de salidas) |
| `osf_lcl_por_sector` | 1/0 (una OSF por cada LCL) | | 1 en LEPA | RaDisplay.set_active_sectors |
| `orientaciones` | lista | | `FIELD,NORTH,EAST,SOUTH,WEST` en LEMD; `NORTH,FIELD` resto | UCS (botón GEOSTANDAR) |
| `pp_arrastre_pantalla` | 1/0 (arrastre con botón 1 en pseudopiloto) | | 0 en LEMD | Pseudopilot.b1_cb |
| `pp_asumir_arranca` | 1/0 (al asumir el PP un vuelo PREPARING pasa a S/U) | | 1 en LEMD y LEBL | GTA._h_assume |
| `pp_asumir_rodaje_salvo` | lista de sectores | | `GND ES,GND EN` en LEMD; vacío resto | GTA._h_assume (si el 1.er sector no está en la lista, pasa a TAX) |
| `preimpresion_arr` / `preimpresion_dep` | minutos | | 10 / 2 en LEMD, LEBL y BarcelonaTWR; 30 / 30 resto | TLPV |
| `tfl_dep_local` / `tfl_defecto` | nivel | | 240 / 250 | GTA.load_flight |
| `tfl_fijo` | fijo | `local,resto` (o un único valor) | `PEKOP` → 130,150 | GTA.load_flight |
| `decel_aterrizaje` | aeródromo (o `*` = general) | kt/s | `*` 7, LESO 8, LEBL 4 | Aircraft.next |
| `acel_despegue` | aeródromo (o `*`) | kt/s | `*` 5, GEML 9, LESO 8 | Aircraft.next |
| `min_alt_visible` | sector | cientos de pies | LEGR 50 | UCS.update_track |
| `activacion_manual_ads` | lista de aeródromos | | `LEGR` si el primer sector es GRANADA | RaElements DepTabular/ActTabular |
| `ads_sin_fichas_fijo` | lista de aeródromos | | `LEAM,LEGR` | TLPV (sin fichas de fijo para salidas locales) |

En las claves con columna C, dejar la columna C vacía **elimina** el valor por defecto de ese elemento (p. ej. `tfl_fijo | PEKOP |` (vacío) quita la regla de PEKOP).

Escenarios compuestos (varios Excel en un ejercicio, `Add_fir`): los parámetros se recalculan con los aeródromos unidos; si los dos Excel traen la misma clave, prevalece el principal.

### B. Reglas de secuencia de sectores (hoja opcional `SectorSequence`)
Las reglas fijas de `GTA.load_flight` (LEBL ELR/ENR, salidas LEST/LECO/LEVX con APP al final, Canarias) pasan a `FIR._DEFAULT_SECTOR_SEQ_RULES`. Si un Excel trae la hoja `SectorSequence`, sus reglas **sustituyen** a las de por defecto. Fila 1 = cabecera; columnas:

| A aeropuerto | B operacion | C pista | D posicion | E accion | F valor | G si_escenario |
|---|---|---|---|---|---|---|
| uno o varios (coma); vacío = cualquiera | `DEP` / `ARR` / vacío | texto contenido en la pista | `TWR` (posición solo torre) / `APP` / vacío | `QUITAR`, `QUITAR_PRIMERO`, `AL_FINAL`, `FIJAR` | sector(es) | aplica solo si el escenario tiene alguno de estos aeródromos |

Ejemplo (equivale a lo actual en Canarias): `GCXO,GCTS | ARR | | APP | FIJAR | APP,LCL,GND | GCXO,GCTS,GCLP`.

Comprobado con 24.000 vuelos sintéticos frente al código anterior: mismo resultado salvo dos casos extremos, ahora mejor resueltos:
- El código anterior lanzaba `IndexError` (vuelo no cargado) en LEBL si en una llegada por la 02 la secuencia quedaba vacía tras quitar `LCL DEP`.
- Vuelo LEBL→LEBL que sale por la 06R y llega por la 02: antes no se aplicaba la regla de llegada por la 02; ahora sí.

### C. Pendiente (Fase 3, parte 2)
Bloques por escenario de `ATCBahia` (fijos e imágenes de Málaga, LEMH, LEST, LEGR, LEAM, Barcelona, LEMD), `LEME→LEMD`, mapas de USO PISTAS de LEBL, `RaElements` con `LECG`/`LEMD` en las fichas, `Editor` (`LECB`). No se ha cambiado `Aircraft.get_rot` (decisión 2). El pushback fijo de LEBB en OSF se hará en la Fase 4.

**Verificación:** sintaxis Python 2.7 (gramática lib2to3) de los 8 ficheros; CRLF conservado. Lectura de parámetros probada con los Excel reales de LEST, GCLP, LEPA, LEMH, LEBL y LEMD (ninguno trae aún estas claves → valores por defecto correctos) y con una copia de LEST con filas y hoja `SectorSequence` añadidas.

**Pruebas en el simulador:** LEMD o LEBL (sin STCA, tabulares auxiliares ocultas, PP asume → S/U); LEST (botón SMR y tabular No Correlados); LEPA (SobTabular y una OSF por LCL); Canarias y LEBL (secuencia de sectores / transferencias como antes); un escenario PICT cualquiera (preimpresión de fichas a 30 min).

---

## [2026-10-02] Unificación — Fase 2: motor de vuelo y protocolo cliente-servidor — GTA.py, Aircraft.py, Pseudopilot.py, RaElements.py, UCS.py

Segunda fase de la unificación (ver `..\ANALISIS_UNIFICACION.md`). Correcciones portadas de GAMMA y fallos detectados al comparar las tres versiones. Revisado además por un segundo análisis independiente del código modificado.

### A. Protocolo
1. **Cambio de pista en uso (`GTA._h_rwy_in_use`, `GTA.change_rwy_in_use`, `Pseudopilot.process_message`).** Estaba roto: el pseudopiloto envía `{'ad': {ad: pista, ...}}` y el servidor leía `m['ad'], m['rwy']` → excepción silenciada y la pista no cambiaba. Ahora:
   - `change_rwy_in_use(ads, rwy_direction_desig=None)` admite varios aeródromos (`dict`) y el formato antiguo `ad`+`rwy` (Editor).
   - Solo se replanifican los vuelos de los aeródromos que cambian (antes se comparaba la pista nueva con vuelos de cualquier aeródromo IFR). Si a una salida ya no se le puede cambiar la pista (ya ha salido del stand), se evalúa su llegada.
   - Corregidos dos fallos del original: en salidas se escribía `desrwy` en vez de `deprwy`; en llegadas se usaba el aeródromo de la iteración anterior y no se actualizaban `lrwy`/`desrwy`.
   - El aviso a los pseudopilotos se envía para cada aeródromo cambiado (antes solo el último). El cliente acepta ambos formatos y asigna la pista (antes asignaba una lista y solo al último aeródromo).
2. **Pista en uso inicial (`GTA.load()`).** Antes solo se fijaba para el primer aeródromo (`e.fir[0]`) a partir del primer vuelo del ejercicio. Ahora, para cada aeródromo, la pista del primer vuelo que sale o llega a él.
3. **Claves `rwy`/`pista` (`GTA._h_change_star`, `_h_depart`).** El cliente envía `'pista'`; `_h_change_star` leía además `m['rwy']` → la STAR cambiaba pero `lrwy`/`rdes` no. Se acepta `m.get('rwy', m.get('pista'))` y se actualizan `lrwy`, `rdes` y `desrwy`.

### B. Motor de vuelo (portado de GAMMA)
4. **AUTODEP (`Aircraft.initialize()`).** Con `fix_exe == 'AUTODEP'` se iban descartando todos los puntos de la ruta. Ahora el vuelo empieza en el primer punto a la EOBT (igual que GAMMA). **Probar**: afecta a vuelos AUTODEP entre aeródromos con pistas IFR.
5. **`ias_blocked`.** La reducción automática a velocidad de aproximación ya no se hace nada más entrar en `_LLZ`, sino con el localizador interceptado, a menos de 10 NM y solo si el ATC no ha ordenado una velocidad (`GTA._h_set_ias`/`_h_set_mach` activan el flag solo si la orden se acepta; se resetea al autorizar aproximación, ILS o directo).
6. **Esperas (`hold_stop_removed`).** Si se quita el stop del fijo durante una espera activa, el avión completa la vuelta y después ejecuta la aproximación (antes abandonaba la espera en el acto). `Aircraft.toggle_stop()` y función de espera.
7. **`insert_wp(..., fix_after=None)`.** Si el avión ha pasado `fix_next` mientras se definía el punto, se inserta antes del siguiente (`fix_after`). Parámetro añadido al final de la firma para no romper llamadas existentes; las líneas de ruta del pseudopiloto lo envían.
8. **`Aircraft.depart()` con avión rodando** (decisión del usuario): si el escenario tiene el punto `'THR'+pista` (hoja `Lado aire`) va directo al umbral, como en GAMMA; si no existe, mantiene el rodaje restante (comportamiento previo).

### C. Fallos de cliente y compartidos
9. **`ATCBahia.update()` (RaElements.py).** En el bucle `for sect in sector_list` se consultaba `fs_print_t[sector]` (la posición completa): en posiciones multisector no se insertaba ninguna ficha. Ahora usa `sect`.
10. **Posiciones multisector en `UCS.process_message`.** `local_ads[self.sector]` y `sacta_mode[self.sector]` daban `KeyError` con `'A,B'`. Nuevo `UCS._is_local_ad(ad)`, usado en los tres puntos donde se calcula `local_dep`/`local_des`.
11. **Asumido (`UCS.update_track`).** Se buscaba el sector como subcadena (`find`) → falsos positivos (`'LCL'` dentro de `'LCL ARR'`). Ahora por pertenencia a los sectores de la posición.
12. **REVOCAR sin OSF (`UCS`).** Llamaba a `fichas_tabular.revocar()` sin comprobar → `AttributeError` en posiciones no OSF. Ahora muestra un aviso.
13. **QNH en el METAR (`GTA`).** `str(qnh)[:4]` daba `'999.'` con 999.6; ahora `'%04d'` redondeado (`Q0999`, `Q1014`).
14. **Giro progresivo del viento (`GTA.timer`).** Sin módulo 360: al cruzar el norte crecía sin límite u oscilaba y el paso de 4° podía no alcanzar nunca el objetivo. Ahora gira por el camino más corto y termina exactamente en el objetivo.
15. `Aircraft.sector_sequence = []` inicializado; `Aircraft.depart()`: corregido el formato del aviso de SID no encontrada (lanzaba `NameError`).

**Verificación:** sintaxis Python 2.7 (gramática lib2to3) en los 6 ficheros. Pendiente prueba en el simulador: cambio de pista desde el pseudopiloto (uno y varios aeródromos), cambio de STAR, vuelo AUTODEP, quitar stop en espera, velocidad ordenada en aproximación, posición multisector, REVOCAR en escenario PICT.

---

## [2026-10-02] Unificación — Fase 1: carga multi-escenario (hoja OSF opcional, zonesOSF, velocidades de rodaje, normalización de sectores) — FIR.py, Aircraft.py, RaElements.py, GTA.py

Primer paso de la unificación de GAMMA_GLOBAL con GAMMA (nacional) y GAMMA_OSF_LEBL (ver `..\ANALISIS_UNIFICACION.md`). Objetivo: que esta versión cargue todos los escenarios vigentes de `C:\03 ESCENARIOS` sin tocar sus Excel.

1. **Hoja `OSF` opcional (`FIR.py` — `ESCENARIO.__init__()`).** Se leía con `self.book['OSF']` capturando solo `ValueError`; openpyxl lanza `KeyError` si la hoja no existe, así que los 12 escenarios PICT sin hoja `OSF` (LEMH, LEAS, LEPP, LERJ, LESO, LEXJ, LEVT, LECO, LEVX, LEAM, LEGR, LEGE) abortaban la carga del FIR. Ahora, si falta, `state_to_bahia` queda vacío y se registra un `logging.info`.

2. **`zonesOSF` aceptado como sinónimo de `zonasOSF` (`FIR.py`).** Los Excel de LEBL, LEPA, LEMD y LEMG usan `zonesOSF`; se ignoraban y `OSF.py` caía al número de zonas por defecto.

3. **Velocidades de rodaje por escenario (`FIR.py`, `Aircraft.py`, `RaElements.py`).** Portado de GAMMA (cambios del 2026-07-23 y 2026-09-11), con valores por defecto que mantienen el comportamiento previo de GLOBAL:
   - Hoja `Escenario`: `ifr_taxi_ias` (o `taxi_ias`, que se sigue aceptando como sinónimo; defecto 15), `vfr_taxi_ias` (defecto: sin valor) y `ret_ias` (defecto 4). Ya existían Excel con cada formato: GCLP y LEGR usan `ifr/vfr_taxi_ias` (hasta ahora ignorados: GCLP rodaba a 15 kt en vez de 20), GCTS/GCXO/LEBB/LEST/LEGE usan `taxi_ias`, LEGE trae `ret_ias`.
   - `FIR` expone `ifr_taxi_ias`, `vfr_taxi_ias`, `ret_ias` y mantiene `taxi_ias` (= `ifr_taxi_ias`) por compatibilidad.
   - `Aircraft.get_taxi_ias(fir)` (nuevo): VFR → `vfr_taxi_ias` **solo si el escenario lo define**; en otro caso `ifr_taxi_ias` (antes todos los vuelos usaban `taxi_ias` en el motor). Sustituye los 5 usos de `fir.taxi_ias` (aterrizaje helicópteros, auto-depart ×3, salida de pista).
   - `RaElements.change_speed()`: valor sugerido VFR = `vfr_taxi_ias` o 6 si no está definido; IFR = `ifr_taxi_ias`; push-back = `ret_ias` (antes `'4'` fijo).

4. **Normalización de sectores determinista (`FIR.py` — `_normalize_sector()`).** Recorría `_SECTOR_ALIASES.items()`, cuyo orden en Python 2.7 no está garantizado: `'LEST TMA'` podía quedar `'APP'` o `'LEST APP'`. Ahora los alias se aplican en orden fijo (más largos primero, `_SECTOR_ALIAS_ORDER`) y se repite hasta que no haya cambios, de modo que `'LEBB TMA'` (Posicion de ejercicios de LEBB) → `'LEBB APP'` → `'APP'`. No se cambian los alias ni la sustitución por subcadena (resultado verificado: `'LEST TMA'`→`APP`, `'GMC GN'`→`GND GN`, `'TWR 36L/18R'`→`LCL 36L/18R`, `'GRANADA'` sin cambios).

5. **Comparaciones literales con nombres sin normalizar (`GTA.py`).** `sector_sequence` contiene nombres ya normalizados, así que las reglas de LEBL (`== "GMC GN"`, `"GMC" in ...`, `load_flight()`) y de LEMD (`('GMC ES', 'GMC EN')`, `_h_assume()`) no se cumplían nunca. Se aceptan ambas formas (`GMC`/`GND`). Se dejan para la Fase 3 (parametrización) los nombres de LEMD de `RaElements.py` (`'TWR DEP36R/ARR18L'`...), que ya no coinciden con los del Excel actual.

**Verificación:** sintaxis Python 2.7 comprobada (gramática lib2to3) en los 4 ficheros. `ESCENARIO` cargado contra 19 Excel reales (GCLP, GCXO, LECO, LEVX, LEBL, LEPA, LEMD, LEMG, LERS, LEMH, LEAS, LEGE, LEGR, LEAM, LESO, LEPP, LERJ, LEXJ, LEVT) sin errores; valores leídos correctos (p. ej. GCLP ifr=20/vfr=15, LEGE ifr=8/ret=3, LEBL zonas GND 5/LCL 4). Pendiente: prueba de ejecución completa con Python 2.7 en el equipo del simulador.

---

## [2026-09-10] Fichas de LEST/LECO/LEVX (incluida la editable) no aparecían — comparación de `sector` rota por `_normalize_sector`; ahora son 5 editables — RaElements.py

**Archivo:** `lib/RaElements.py` — `ATCBahia.update_fijos()`, `ATCBahia.insert_fijo()`.

`update_fijos()` decidía el sub-bloque de fijos (TMA vs TWR) con `if sector == 'LEST TMA':` / `elif sector == 'LEST TWR':`. Pero `FIR._normalize_sector()` (llamada al construir `fir.sectors` desde la hoja `Sector` del Excel) reemplaza alias por sustring sobre el `dict` `_SECTOR_ALIASES` (`'TWR': 'LCL'`, `'TMA': 'APP'`, `'LEST TMA': 'APP'`, ...), así que el nombre de sector que realmente llega a `self.radisplay.sector` en tiempo de ejecución **nunca es** el literal `'LEST TMA'`/`'LEST TWR'`. Confirmado contra `gamma_settings.json` (`LEST/Layout1/sector == "APP"`) y reproduciendo `_normalize_sector`: `'LEST TMA' -> 'APP'`, `'LEST TWR' -> 'LEST LCL'`. Como ninguna de las dos comparaciones coincidía jamás, **todo el bloque de fijos de LEST/LEVX/LECO se saltaba entero** (ni los fijos fijos LEST/LECO/LEVX/LPPR ni la ficha editable se creaban).

Se cambian las comparaciones a `if 'APP' in sector:` / `elif 'LCL' in sector or 'TWR' in sector:` (robustas frente a las dos formas "mangled" posibles según el orden de iteración del `dict` de alias, que en Python 2.7 no está garantizado). No se toca `_normalize_sector`/`_SECTOR_ALIASES` en sí — es código compartido por `zonasOSF`, `fir.sectors` y `state_to_bahia`, y arreglarlo de raíz requiere más análisis de impacto.

De paso, a petición del usuario, cada uno de los dos sub-bloques (antes con 1 sola ficha `TEXTOLIBRE`) pasa a crear **5 fichas editables** (`callsign`/`txt` = `'TEXTOLIBRE1'`..`'TEXTOLIBRE5'`, cada una con su propio `tix.Entry` + `trace`). En `insert_fijo()` se cambia `if txt == 'TEXTOLIBRE':` por `if txt.startswith('TEXTOLIBRE'):` para que el drag&drop reconozca cualquiera de las 5 y reconstruya el `Entry` en vez de perder la ficha.

Nota: se había añadido por error una rama `elif escenario == 'GCLP':` en un intento anterior, basada en los commits recientes de GCLP en `cambios.md`; el usuario confirmó que el escenario activo es LEST, así que esa rama (y `'GCLP'` en la tupla de `insert_fijo`) se ha revertido — no se llegó a dejar en el código final.

`ATCBahia.update()` (línea ~1254) tenía el mismo bug: `if sector == 'LEST TWR':` (filtro que limita qué vuelos se insertan automáticamente en la bahía de torre de LEST a los que operan en LEST, descartando LECO/LEVX) tampoco coincidía nunca, así que entraban fichas de los tres aeródromos sin filtrar. Corregido igual: `if 'LCL' in sector or 'TWR' in sector:`.

---

## [2026-09-10] Ficha editable (TEXTOLIBRE) de ATCBahia perdía el texto al arrastrarla — RaElements.py

**Archivo:** `lib/RaElements.py` — `ATCBahia.update_fijos()` (creación inicial de fijos LEST TMA/TWR), `ATCBahia.insert_fijo()`.

La ficha editable (`callsign`/`txt` = `'TEXTOLIBRE'`, disponible para escenarios `LEST`/`LEVX`/`LECO`) se rompía en cuanto se hacía drag&drop:

1. `insert_fijo()` comprobaba `if txt == 'TEXTOVARIABLE':` (typo) contra un `canvas.txt` que en realidad vale `'TEXTOLIBRE'`. La comparación nunca era cierta, así que al reconstruir la ficha en la nueva posición se caía siempre al `else` y se creaba un `canvas.create_text(...)` con el texto literal `"TEXTOLIBRE"`, sustituyendo el `tix.Entry` editable por una etiqueta fija.
2. `canvas.textolibre` solo se asignaba una vez, justo al crear el widget (con el campo aún vacío) — no había ningún `trace` sobre la `StringVar` que lo mantuviera sincronizado mientras el usuario escribía, así que aunque se corrigiera el typo se habría restaurado siempre una cadena vacía.
3. En el bloque de `LEST TWR` había además un descuido: guardaba el valor en `self.textolibre` (atributo de `ATCBahia`) en vez de `canvas.textolibre`.

Se corrige el typo (`'TEXTOLIBRE'`), se añade `canvas.text_variable` + `text.trace('w', ...)` en los tres puntos donde se crea el `Entry` para que `canvas.textolibre` refleje siempre el contenido actual, y `insert_fijo()` ahora lee el valor desde `self.dragged_canvas.textolibre` (el canvas original, que conserva el trace) antes de reconstruir la ficha en la nueva zona/fila. Nota: `lambda *args, c=canvas: ...` (keyword-only tras `*args`) es sintaxis Python 3; se usa la firma real del callback de `trace` (`name, index, mode`) con defaults normales.

Mismo bug presente en `C:\GAMMA\lib\RaElements.py` (líneas ~1460, ~1904-1905, ~1961-1962) — no replicado, a petición del usuario, por la política de no asumir cambios entre versiones.

---

## [2026-09-09] Escudo ante QNH ausente en el ejercicio — GTA.py, Exercise.py

**Archivo:** `lib/GTA.py` — `load()` y `reload_exercise()`. `lib/Exercise.py` — `load_excel()`.

`self.qnh = float(e.qnh_ini)` lanzaba `AttributeError: Exercise instance has no attribute 'qnh_ini'` cuando el METAR del ejercicio no contenía un grupo `Qxxxx` reconocible (o no había fila METAR), ya que `Exercise.qnh_ini` solo se crea dentro del `try` que parsea ese grupo. Esto abortaba el arranque del ejercicio (`GAMMA.Launch`).

Se añade `QNH_STD = 1013.0` (QNH estándar) como valor de repliegue en `GTA.py`, y en ambos puntos de carga se usa `getattr(e, 'qnh_ini', None)` + conversión protegida con `try/except (TypeError, ValueError)`, registrando un `logging.warning` y continuando con `QNH_STD` si el dato falta o es inválido. Además, `Exercise.load_excel()` inicializa `self.qnh_ini = None` antes de intentar el parseo, para que el atributo exista siempre aunque el regex no encuentre nada.

---

## [2026-09-09] Tabulares DESPEGUES/PREACTIVOS/ACTIVOS no se actualizaban en UCS — UCS.py

**Archivo:** `lib/UCS.py` — bloque de redibujado completo (`update_flight`, antiguas líneas 451-453) y bucle periódico del mensaje `'update'` (antiguas líneas 542-545).

Las llamadas `self.coor_tabular.update()`, `self.preact_tabular.update()` y `self.act_tabular.update()` estaban comentadas en ambos puntos, junto con la condición `if self.fir.aps[0] not in ('LEMD')` que las envolvía. Resultado: las tabulares DESPEGUES/PREACTIVOS/ACTIVOS se creaban y podían mostrarse/ocultarse desde el menú, pero nunca refrescaban su contenido (listas vacías o congeladas) para ningún aeródromo, no solo para LEMD.

Verificado con `git log -p -L` que el comentado viene ya del commit de importación masiva `76f9a42` ("Añadimos version nueva para torres con APP y OSF"), no es una regresión posterior. En `C:\GAMMA` estas mismas llamadas están activas (sin la guarda LEMD), lo que confirma que aquí quedó deshabilitado por error al portar el fichero.

Se restauran ambos bloques, descomentando y manteniendo la guarda `if self.fir.aps[0] not in ('LEMD')` tal como estaba escrita originalmente.

---

## [2026-08-26] Slot único `eobt`/`ctot` en las fichas OSF — OSF.py

**Archivo:** `lib/osf/OSF.py` — nuevo método `_eobt_slot()`; usado en `insert_or_update_fs()` (bloque `values`/`ficha`) y en `_toggle_extended()` (ficha extendida).

Decisión de dominio: `eobt` y `ctot` ocupan el mismo slot visual en la ficha. Normalmente se muestra el EOBT; solo cuando el vuelo trae CTOT registrado desde el ejercicio (columna P, ver [[project_ctot_pendiente]]) ese mismo campo pasa a mostrar el CTOT. No existen dos campos separados — se elimina la entrada `"ctot"` de `field_defs` y de `values`, que no estaba referenciada en ningún layout (código muerto).

`_eobt_slot(f)` centraliza la decisión (antes duplicada entre la ficha normal y la extendida) y devuelve `(texto "HHMM", is_ctot)`. Cada ficha guarda `eobt_mode` (`"eobt"` o `"ctot"`) para que la lógica de resaltes sepa qué juego de reglas aplicar. La ficha extendida hereda `eobt_mode` de la madre, igual que ya hereda `field_colors`.

**Resalte CTOT** (mismo commit): cuando `eobt_mode == "ctot"`, el fondo del campo pasa a blanco (color de fuente sin cambios). Se implementa vía `ficha["field_bg"] = {"eobt": "white"}` — mecanismo ya existente en el motor de dibujo (`bg_color = field_bg_overrides.get(name, self.ficha_bg)`, antes solo usado por el campo `obstaculo`). La ficha extendida hereda `field_bg` de la madre igual que `eobt_mode`. Los resaltes de `eobt` (umbral ±15min) siguen viviendo aparte, en `PrevDesp.py`, sin tocar.

---

## [2026-08-25] Campo `vel` en ficha extendida no se mostraba (usaba IAS en vez de la tabla del escenario) — OSF.py

**Archivo:** `lib/osf/OSF.py` — `_toggle_extended()`.

Bug reportado: el campo `vel` de la ficha extendida (hoja `OSF_Layout`) aparecía casi siempre en blanco. Escenario de referencia: `C:\03 ESCENARIOS\DRNA_C\GCLP\GCLP.xlsx`, hoja `Velocidades` (tabla `Modelo -> Velocidad`, ej. `A320 -> 450`), cargada en `fir.vel_cruz` por `FIR.py` (líneas 400-412 y 657) pero **nunca consultada** en ningún otro punto del código (confirmado por búsqueda global — solo se define y se copia, no se lee).

Causa: `_toggle_extended()` calculaba `vel` a partir de la IAS real de la aeronave (`f.ias`), con condición `> 0` para mostrar algo. Como las fichas OSF son de operaciones en tierra (parking/rodaje, antes de despegar o tras aterrizar), la IAS suele ser 0 en ese momento, así que el campo quedaba vacío casi siempre. `vel` en realidad debía representar la velocidad de crucero **asignada por tipo de aeronave** (tabla estática del escenario), no una medida en tiempo real.

Fix: `vel` se calcula ahora como `fir.vel_cruz.get(f.type, "")`, igual que el resto de datos estáticos por tipo/escenario. Al depender solo del tipo de aeronave (conocido desde el principio del vuelo), el campo se muestra siempre que el tipo esté en la hoja `Velocidades`.

---

## [2026-08-25] `campolibre` en ficha extendida: valor estático y no editable — OSF.py

**Archivo:** `lib/osf/OSF.py` — `_toggle_extended()`, `_on_campolibre_click()`, `_commit_campolibre_changes()` (interna de `_on_campolibre_click`).

Bug reportado: cuando el layout de la ficha *extendida* incluye `campolibre` (vía hoja `OSF_Layout` del escenario), el campo aparecía siempre con el texto de relleno `-libre-`, desconectado del valor real, y no se podía editar.

Causas:
1. **Valor estático**: `ext_values_full` (diccionario de valores calculados para la ficha extendida en `_toggle_extended()`) no incluía la clave `"campolibre"`. Al faltar, `ext_values = {k: ext_values_full.get(k, self._field_value(k)) for k in ext_fields}` caía al fallback `_field_value("campolibre")`, que es el valor por defecto estático de `field_defs` (`"-libre-"`), en vez del valor real `f.rutrod` (la fuente de verdad que sí usa `insert_fs()` para la ficha normal). Fix: se calcula `campolibre_ext` a partir de `f.rutrod` igual que en `insert_fs()`, y se añade a `ext_values_full`.
2. **No editable**: `_on_campolibre_click()` (y el guardado desde click global) resolvían el callsign del vuelo leyendo `ficha["values"]["callsign"]`, pero la ficha extendida no tiene esa clave en su layout (usa `parent_callsign` en su lugar). Al no encontrar callsign, la función salía sin abrir el editor. Fix: se añade fallback a `ficha.get("parent_callsign", "")` en `_on_campolibre_click()`, en el envío del mensaje `set_rutrod` tras confirmar edición, y ya funciona igual para ficha normal y extendida (ambas comparten el mismo campo `rutrod` en el objeto `Aircraft`, así que quedan sincronizadas).

---

## [2026-08-25] Nuevo campo `resto_fijo` (como `resto` pero de ancho fijo) — OSF.py

**Archivo:** `lib/osf/OSF.py` — `__init__()`, `get_instance()`, `insert_fs()`.

Necesidad: el campo `resto` existente es flexible (`"width": "flex"`) y reparte el espacio sobrante entre los campos flex de la ficha. Se pedía un campo hermano que ocupe un hueco de tamaño **fijo** en vez de repartir espacio, disponible tanto en la ficha normal como en la extendida, sin modificar el comportamiento de `resto`.

Cambios:
1. Nuevo parámetro `resto_fijo_width` en `OSF.__init__()` y `OSF.get_instance()` (por defecto `100` si no se indica), guardado en `self.resto_fijo_width`.
2. Nueva entrada `"resto_fijo": {"width": self.resto_fijo_width, "value": ""}` en `field_defs`, añadida tanto en el bloque de la ficha normal como en el de la ficha extendida (y en el `setdefault` de seguridad tras el merge con `fir.osf_layouts`/`osf_ext_layouts`).
3. `"resto_fijo": ""` añadido también al diccionario `values` de `insert_fs()`, igual que `resto`.

No se ha tocado `_default_layouts`/`_default_ext_layouts`: el nombre `resto_fijo` se añadirá manualmente a la hoja `OSF_Layout` del escenario donde se quiera usar. Tampoco se ha propagado `resto_fijo_width` desde los llamadores de `OSF.get_instance()` (`lib/UCS.py`, `lib/RaDisplay.py`) — queda pendiente de cablear cuando el parámetro de ancho esté definido en el escenario.

---

## [2026-08-18] Campo `sid` siempre en blanco en fichas OSF/PrevDesp (afecta a todos los escenarios) — TLPV.py

**Archivo:** `lib/TLPV.py` — `get_stand_sid()`.

Bug reportado tras el fix anterior de `cfl`/`hp` en GCLP: el campo `sid` de la ficha OSF de departures seguía sin mostrar nada.

Causa: `get_stand_sid()` decidía si mostrar la SID auto-asignada (`flight.sid.txt_desig`) comprobando `flight.fix_exe == 'EOBT'`. Pero `Exercise.py` (líneas 202 y 214), al parsear el fichero de ejercicio, sustituye ese valor por el puesto de estacionamiento **antes** de construir el `Aircraft` (`fijo = ... # fijo = parking`), de forma que `flight.fix_exe` nunca contiene literalmente la cadena `'EOBT'` en tiempo de ejecución — en ningún escenario, no solo en GCLP. La rama que devuelve la SID real era código muerto; siempre se caía al `else: return flight.sid_desig`, que solo tiene contenido si el ejercicio fija una SID explícita con el patrón `[1-9][a-zA-Z]` en la ruta. Con autoselección de SID por pista en uso (caso habitual), `sid_desig` queda `''` y el campo se veía vacío.

Fix: sustituir la comprobación por `flight.sid is not None` (además de `flight.adep in fir.aerodromes.keys()`, que ya estaba). `self.sid` se inicializa a `None` (`Aircraft.py:741`) y solo se asigna a un objeto `Procedure` real cuando se calcula la SID de una salida (`Aircraft.py:1512`/`1584`), así que es un indicador fiable de "hay SID asignada", a diferencia de `fix_exe`. Se confirma que `self.sid` ya está asignado (vía `set_route()` → `complete_flight_plan()`) antes de que `initialize()` llame a `set_campo_stand_sid()`, así que no hay problema de orden de inicialización.

Alcance: al ser `lib/TLPV.py` código compartido por todos los escenarios (no específico de GCLP), este fix corrige el campo `sid` allá donde se muestre (OSF, ficha extendida, PrevDesp) en cualquier escenario que use autoselección de SID.

---

## [2026-08-18] Campos `cfl` y `hp` no aparecían en la ficha normal de departures (GCLP) — OSF.py

**Archivo:** `lib/osf/OSF.py` — `insert_fs()`, `_resolve_field_names()`, `_resolve_ext_fields()`.

Bug reportado: en la bahía GND del escenario GCLP (`C:\03 ESCENARIOS\DRNA_C\GCLP\GCLP.xlsx`, hoja `OSF_Layout`, fila `GND,dep_local`), `campos_normal` incluye `hp,sid,cfl`, pero ninguno de los dos primeros se mostraba en la ficha normal (no extendida) de departures.

Causas distintas para cada campo:

1. **`cfl`**: el diccionario `values` que construye la ficha *normal* (`insert_fs()`) nunca calculaba `cfl` — solo se calculaba en la rama de la ficha *extendida* (`_toggle_extended()`, ya corregido el 2026-04-23). Al faltar la clave, el renderer caía al fallback `_field_value("cfl")`, que devuelve `""` (valor por defecto en `field_defs`). Fix: se añade el mismo cálculo ya usado en la extendida (`f.cfl_c` redondeado, formato `%03d`) también en `insert_fs()`.

2. **`hp`**: la hoja Excel usa el nombre de campo `hp` (la etiqueta visible del widget), pero la clave interna real en todo el código (`field_defs`, diccionario `values`, manejador de click `_on_holdp_click`, etc.) es `holdp`. Al no coincidir, `"hp"` no resolvía ningún valor ni click handler y quedaba en blanco. Fix: se añade una tabla de alias `_FIELD_NAME_ALIASES = {"hp": "holdp"}` aplicada en `_resolve_field_names()` y `_resolve_ext_fields()`, que normaliza los nombres de campo leídos de `self.layouts`/`self.ext_layouts` (procedan del Excel o del fallback hardcoded) antes de guardarlos en `ficha["fields"]`. Así el resto del código (que ya usa `holdp` de forma consistente) no necesita cambios.

`sid` ya se calculaba y mostraba correctamente en la ficha normal (`S(getattr(f, "stand_sid_atc", "SID"))`); no requería cambios.

---

## [2026-07-30] Click izquierdo en S/U saltaba a TAX en vez de P/B — OSF.py

**Archivo:** `lib/osf/OSF.py` — `_on_act_click()`, `revocar()`.

Bug reportado: con el campo `act` en `S/U`, el click izquierdo pasaba directamente a `TAX`, saltándose `P/B`, en vez de seguir la secuencia de salidas (`Aircraft.OSF_DEPSEQ`).

Causa: `_on_act_click()` tenía una rama especial para `pof_anterior == Aircraft.STARTING` que decidía entre `P/B` y `TAX` según si `park` estaba en `fir.pushbacks` (dict cargado de la hoja Excel `RetrocesosOSF`, columna "requiere pushback"). En este escenario ningún `park` está registrado en `fir.pushbacks` (mismo problema ya detectado para LEBB el 2026-07-22, ver entrada de esa fecha), así que la condición nunca se cumplía y siempre caía al `else: pof_nuevo = TAXIING_OUT`.

Fix: se elimina esa rama especial. `STARTING` ya forma parte de `Aircraft.OSF_DEPSEQ` (`[PREPARING, STARTING, PUSH, TAXIING_OUT, ...]`), así que al caer en la rama genérica de avance por secuencia (`elif local_dep and pof_anterior in Aircraft.OSF_DEPSEQ`) el siguiente estado ya es `PUSH` (`P/B`) sin depender de `fir.pushbacks`. Las direcciones concretas `P/W`/`P/E` (o `P/N`/`P/S`) solo se autorizan desde el popup de botón derecho (`AUTORIZACION P/W`/`AUTORIZACION P/E`), que ya funcionaba correctamente y no se toca.

Por simetría, se aplica el mismo criterio en `revocar()` (retroceso): tanto desde `TXR` (solicitud de rodaje) como desde `TAXIING_OUT`, el retroceso aterrizaba en `S/U` cuando `park` no estaba en `fir.pushbacks`, saltándose `P/B` igual que en el avance. Ahora ambos casos retroceden siempre a `P/B`, coherente con que el avance ya pasa siempre por ese estado.

---

## [2026-07-29] Vaciar visualmente `tfl` tras transferirlo a `cfl` (doble click) — UCS.py, RaElements.py

**Archivo:** `lib/RaElements.py` — `VisTrack.__init__()` (nuevo atributo `remove_tfl`), `Label.refresh()` (rama `tfl`).
**Archivo:** `lib/UCS.py` — `configure()` (sync `vt.tfl = f.tfl`), `vt_handler()` (rama `item == 'tfl'`, `action == '<Double-Button-1>'`).

El doble click sobre el campo `tfl` de la etiqueta `atc-ucs` ya transfería su valor a `cfl` (`vt.cfl = int(value)`), pero el campo `tfl` seguía mostrando el mismo nivel. Un primer intento de vaciar `vt.tfl` directamente (asignándole un string) no funcionaba: cada frame, `configure()` volvía a pisarlo con `vt.tfl = f.tfl` (sincronización desde el vuelo), así que el valor "vacío" duraba un ciclo y reaparecía.

Solución (comparada con la versión de referencia en `C:\GAMMA_OSF_LECG\lib`, que ya implementa esto): se añade el flag `vt.remove_tfl` (por defecto `False`).
1. `configure()` solo sincroniza `vt.tfl = f.tfl` si `not vt.remove_tfl` — así el valor numérico deja de refrescarse desde el vuelo una vez transferido.
2. El doble click (`vt_handler`, item `tfl`, action `<Double-Button-1>`) pone `vt.remove_tfl = True` cuando `vt.label_format == 'atc-ucs'`.
3. `Label.refresh()`, rama `tfl`/`atc-ucs`: si `vt.remove_tfl` es `True`, sobrescribe `self.tfl.t = '   '` después del formateo habitual.

`vt.tfl` en sí sigue siendo siempre numérico (no se convierte a string), evitando romper otros usos aritméticos (`vt.cfl - vt.tfl`) o el diálogo `change_altitude` que lee `int(vt.tfl+0.5)`.

---

## [2026-07-22] Formato del campo `echo` y sustitución de BD por BI — TLPV.py, RaElements.py

**Archivo:** `lib/TLPV.py` — `get_exit_ades()`.
**Archivo:** `lib/RaElements.py` — `Label.redraw()` (bind), `Label.refresh()` (rama `echo`), nueva `Label.echo_b1()` (sustituye a `echo_b3()`).

1. **Formato del texto**: cuando el destino es un aeródromo local (`flight.ades in fir.aerodromes.keys()`), el campo `echo` mostraba solo las 2 últimas letras del aeropuerto (p.ej. `"BB"`). Ahora se antepone `"TW"` y se añade un guion bajo final: `"TW" + ades[-2:] + "_"` (p.ej. `"TWBB_"`).

2. **BD → BI**: se elimina el bind de `<Button-3>` (BD) sobre el campo `echo`, que llamaba a `echo_b3()` — función ya inerte, pues enviaba el item `'echo'` al `_message_handler` y tanto `UCS.py` como `Pseudopilot.py` tienen esa rama comentada (solo escuchan `'set_echo'`). Se añade en su lugar un bind de `<Button-1>` (BI) a la nueva `echo_b1()`, que sustituye todo el texto del campo por un único acento circunflejo (`'^'`), sin más.

   Para que el circunflejo no se pierda en el siguiente refresco (`Label.refresh()` sincroniza `echo.t` con `vt.echo` en cada ciclo), se añade una guarda igual a la que ya existía para `colat`/`colat_app` con su `'SAL^'`: si `echo.t == '^'` se conserva, si no se recalcula desde `vt.echo`.

---

## [2026-07-22] QNH visible solo con autorización anotada — PrevDesp.py

**Archivo:** `lib/osf/PrevDesp.py` — `insert_fs()`.

El campo `qnh` se calculaba y mostraba siempre, sin relación con el estado de autorización ATC de la ficha (campo `autorizacion`). Se pide que solo sea visible una vez que se ha anotado la autorización (BI sobre `autorizacion`, es decir `f.ATC_status == Aircraft.ATC_OK`).

Fix: `qnh_txt` solo se calcula (y por tanto solo se ve, ya que el resto de fichas usan `""` como vacío) cuando `atc_status == Aircraft.ATC_OK`; en cualquier otro estado (`ATC_PENDING`, `ATC_MISSING`, etc.) queda `""`. Se reutiliza la variable `atc_status` ya calculada unas líneas antes para la imagen del campo `autorizacion`.

---

## [2026-07-22] Pushback por defecto para LEBB sin datos de `fir.pushbacks` — OSF.py

**Archivo:** `lib/osf/OSF.py` — construcción dinámica de `actions_list` para SALIDAS (bloque de acciones OSF_pof).

En LEBB el escenario no trae `fir.pushbacks` con direcciones por `park` (a diferencia de otros aeropuertos donde sí se define por posición de estacionamiento), así que la rama que depende de `park in fir.pushbacks` nunca se cumplía y un vuelo en `STARTING` se quedaba sin ninguna acción de pushback disponible.

Nueva rama `elif osf_pof == Aircraft.STARTING and fir.ap[0] == "LEBB"`: si el aeropuerto es LEBB, se ofrecen por defecto `SOLICITUD P/B`, `AUTORIZACION P/W` y `AUTORIZACION P/E`, sin depender de datos por posición de estacionamiento.

---

## [2026-07-21] Campos HOPM, DTOT y QNH en PrevDesp — PrevDesp.py

**Archivo:** `lib/osf/PrevDesp.py` — `__init__()` (`field_defs`, `column_titles`), `insert_fs()`.

Montaje en PrevDesp de los campos `hopm`/`dtot` (calculados en `Aircraft.py`, ver entrada anterior) y `qnh`, ya colocados por el usuario en `self.layouts[("CLR","dep_local")]`:

- `hopm`/`dtot`: mismo patrón que `ctot` en `values` — `"%02d%02d" % (f.X.hour, f.X.minute) if getattr(f, "X", None) else ""`.
- `qnh`: copiado tal cual del cálculo que ya existe en `OSF.py` (`_toggle_extended`) — `self.radisplay.giw.qnh`, formateado como `"Q%04d"`, con try/except a `""` si falla.

`field_defs` y `column_titles` ya los había añadido el usuario para `hopm`/`dtot`; para `qnh` se han añadido aquí siguiendo el mismo estilo (`{"width": 80, "value": ""}`, título `"QNH"`).

---

## [2026-07-21] Nuevos campos HOPM y DTOT — Aircraft.py

**Archivo:** `lib/Aircraft.py` — `__init__()`, nuevos métodos `set_hopm()`, `set_dtot()`.

Preparación para dos nuevos campos que se van a mostrar en PrevDesp/OSF (pendiente de definir layout, se hace en un paso posterior):

1. **`hopm`** (Hora de Puesta en Marcha): `EOBT` + aleatorio entre 4 y 7 minutos. Se calcula junto a `tobt`/`tsat`, reutilizando el helper `random_time()` ya existente, solo si el vuelo tiene `eobt`.
2. **`dtot`**: `CTOT` + aleatorio entre 0 y 1 minutos. Se calcula solo si el vuelo tiene `ctot` (no todos los vuelos lo tienen), en un `if` separado ya que `ctot` es independiente de `eobt`.

Mismo patrón que `set_tobt()`/`set_tsat()`: si el vuelo no tiene el atributo base (`eobt` o `ctot`), el atributo derivado (`hopm`/`dtot`) no se crea en absoluto — los consumidores deben usar `getattr(f, "hopm", None)` / `getattr(f, "dtot", None)`, igual que ya hacen con `tobt`/`tsat`/`ctot`.

---

## [2026-07-21] Fix desplegable HP (holding point) no aparecía — FIR.py

**Archivo:** `lib/FIR.py` — carga de la hoja `Escenario`, fila `hp`.

Bug reportado: al hacer click en el campo HP (tanto en ficha normal como extendida de OSF/PrevDesp) no aparecía el desplegable con los holding points del escenario.

Causa: `self.hp` se indexaba con `row[1].value` sin convertir a string. En los escenarios donde la pista se introduce como número en Excel (p.ej. LEBB: pistas `10,12,28,30` sin letra), openpyxl devuelve ese valor como `long`, así que la clave quedaba como entero (`12`) en vez de cadena (`"12"`). `OSF.py._on_holdp_click()` busca con `hp_by_rwy.get(str(rwy), [])`, y un `int` nunca es igual a un `str` en Python, así que la búsqueda fallaba siempre y el código cortaba en silencio (`if not items: return`) sin abrir el popup — para cualquier pista del escenario, no solo en la ficha extendida.

Fix: normalizar la clave con `str(row[1].value)` antes de guardarla en `self.hp`, igual que ya se hace para la fila `pistas` dos líneas más arriba en el mismo bucle. De paso corrige el mismo problema en el selector de HP de `RaElements.py` (`change_holdp`), que compara `key == self.vt.lrwy` (string) contra las claves de `self.fir.hp`.

Nota aparte (no corregida, pendiente de decisión): en la hoja `OSF_Layout` del escenario LEBB, la fila `(GND, dep_local)` tiene un typo en `campos_extendida`: `csrr` en vez de `cssr` — ese campo tampoco se pintaría en la ficha extendida de GND. Es un dato del Excel del escenario, no del código; avisar al usuario si procede corregirlo ahí.

---

## [2026-07-21] Paso intermedio "ATC" en secuencia de salidas de PrevDesp — Aircraft.py, PrevDesp.py

**Archivo:** `lib/Aircraft.py` — constante `AUTHORIZATION`; `lib/osf/PrevDesp.py` — `_on_act_click()`.

En `Aircraft.py` existía una constante `AUTHORIZATION = "ATC"` comentada, junto con una versión anterior de `OSF_DEPSEQ` que la incluía entre `PREPARING` y `STARTING`. En algún momento se quitó de la secuencia compartida y quedó sin uso.

Petición del usuario: al hacer el primer click izquierdo sobre el campo ACT en PrevDesp, debe mostrarse "ATC" antes de llegar a "S/U", pero **solo en PrevDesp, no en OSF** (que comparte la misma clase base `OSF` y el mismo `Aircraft.OSF_DEPSEQ`).

Se descomenta la constante `AUTHORIZATION` en `Aircraft.py` pero **no se reintroduce en `Aircraft.OSF_DEPSEQ`** (esa lista la usa también `OSF.py`, y el cambio no debe afectarle). En su lugar, `PrevDesp._on_act_click()` construye una copia local de la secuencia e inserta `AUTHORIZATION` justo después de `PREPARING` antes de calcular el siguiente estado. Resultado: en PrevDesp la secuencia pasa a ser `PREPARING → ATC → S/U → ...` (con el límite de avance máximo de PrevDesp, que sigue siendo `STARTING`); en OSF no cambia nada. El texto "ATC" se renderiza sin tocar `_act_text_color()` (heredado de `OSF.py`): al no tener mapeo especial, cae en el formato por defecto `"%3s" % pof`, que ya produce "ATC" con el color normal de salida asumida.

---

## [2026-07-17] Carga y tratamiento de la nueva columna CTOT del Excel — Exercise.py, GTA.py

**Archivo:** `lib/Exercise.py` — `load_excel()`, `load_flights()`, `Flight.__init__()`, nuevo método `sacta_time()`; `lib/GTA.py` — `load_flight()`.

El Excel de ejercicio incorpora una columna nueva **CTOT** (columna P, índice 15). Hasta ahora `Flight.ctot` se rellenaba siempre con `''` (había un intento antiguo comentado que leía la columna O, hoy ocupada por el transpondedor).

1. **Lectura y normalización (`Exercise.py`).** El bloque inline de la HoraSacta (columna M: texto de más de 4 caracteres = hora absoluta `HH:MM:SS`; si no, minutos a sumar a la hora de inicio con `total_time()`) se extrae **tal cual, sin cambios de comportamiento**, al nuevo método `sacta_time()`, y tanto la HoraSacta como el CTOT (columna P) lo usan — tratamiento idéntico por construcción, a petición del usuario. Una primera versión del helper añadía conversiones extra (celdas `datetime`/`time` vía `strftime`, float → int) y se descartó: la rama `strftime` mandaba una celda con formato de hora por el camino de hora absoluta y producía CTOTs fantasma (p. ej. `12:18:30` cuando el usuario escribía minutos). Igual que en la HoraSacta, la celda debe ser de tipo **texto**; una celda numérica o con formato de hora no es procesable. Un CTOT inválido se ignora con warning en el log y queda `''` (no descarta el vuelo entero, que es lo que haría el `except` general del bucle; en la HoraSacta, en cambio, el vuelo sí se descarta, como siempre).

2. **Conversión a datetime (`GTA.py`, `Aircraft.py`).** `load_flight()` convierte el `'HHMMSS'` a `datetime` exactamente igual que hace con `ef.eto`, y pasa ese datetime (o `''`) al constructor de `Aircraft` en sus dos ramas (salidas y no-salidas). Así `Aircraft.ctot` queda como instancia datetime, que es lo que ya esperaban los consumidores existentes (TABs de `RaElements.py` con `f.ctot.hour/minute`, `UCS.py` con `strftime`, `PrevDesp.py`).

3. **Separación CTOT / ETOT (`Aircraft.py` — `__init__()`, `calc_eto()`, despegue en `next()`).** `ctot` ya existía en `Aircraft` pero con el significado de "despegue estimado/real": `calc_eto()` vuela una copia simulada del avión y copiaba su hora de despegue simulada (EOBT + rodaje) a `self.ctot`, y el despegue al rotar también lo asignaba (era el origen de valores tipo `12:18:30` con segundos variables según el parking, aunque la celda P estuviera vacía). Decisión del usuario: eso no es un CTOT sino un **ETOT**. Nuevo atributo `self.etot` (uso futuro) que recibe ahora todas esas asignaciones (`calc_eto()` → `self.etot = sim.etot`; despegue → `self.etot = self.hora = t`). `self.ctot` queda reservado en exclusiva para el valor del ejercicio: hora de inicio + minutos de la columna P, o `''` si no hay — nada lo sobreescribe durante la carga. Efecto visible: los TABs de salidas y PrevDesp (que pintan `f.ctot`) muestran ahora el CTOT del ejercicio, y quedan en blanco para vuelos sin CTOT (antes mostraban el despegue estimado).

4. **Convenio "sin valor → `''`" (nunca `None`), a petición del usuario y coherente con `Aircraft.hora`.** Se aplica en toda la cadena: `load_excel()`, `load_flights()` (formato `.eje`, que no tiene CTOT), el constructor de `Flight` vacío (el que usa el Editor) y el default del parámetro `ctot` en `Aircraft.__init__` (`None` → `''`). Ningún consumidor hacía `ctot is None`, todos usan truthiness o try/except, por lo que `''` se comporta igual que `None` en las guardas.

---

## [2026-07-16] Fixes en asignación de transpondedor — TLPV.py, GTA.py, Exercise.py

**Archivo:** `lib/TLPV.py` — `get_squawk()`, nuevo método `register_squawk()`; `lib/GTA.py` — carga inicial y `reload_exercise()` (pre-registro de squawks antes del bucle de `load_flight`); `lib/Exercise.py` — `load_excel()`, nuevo método `normalize_transp()`.

1. **Control anti-duplicados de squawks era código muerto.** `TLPV.squawks` (lista de códigos ya asignados) se consultaba en `get_squawk()` pero nunca se rellenaba, por lo que dos vuelos podían recibir el mismo squawk aleatorio. Ahora `get_squawk()` registra cada código que entrega, y los squawks fijados a mano en el ejercicio se pre-registran (vía `register_squawk()`) en los dos puntos de carga de GTA **antes** de crear los planes de vuelo, para que un aleatorio no pueda coincidir con uno manual de un vuelo aún no cargado.

2. **La columna de transpondedor del Excel solo funcionaba con celdas de tipo texto.** Con celdas numéricas openpyxl devuelve int/float: se perdía el cero inicial (`0445` → `'445'`) o aparecía un `.0` (`'445.0'`), y el valor se usaba sin validar. Nuevo `normalize_transp()`: convierte float entero → int, reconstruye 4 dígitos con `zfill(4)` y valida que todos sean octales (0–7); si la celda está vacía o el valor no es válido devuelve el centinela `'None'` (con warning en el log), de modo que GTA asigna squawk aleatorio como hasta ahora.

---

## [2026-07-10] Nuevo botón F/M y label VFVE en barra superior de OSF — OSF.py

**Archivo:** `lib/osf/OSF.py` — `OSF.__init__()` (creación de `btn_fm` y `lbl_vfve`), nuevo método `_handle_fm_button()`.

Se añade un botón "F/M" en la barra superior de la ventana OSF, en el lado izquierdo, con el mismo formato visual que los botones W y OBST (mismo fondo, fuente, ancho y relieve). Por ahora el handler `_handle_fm_button()` no tiene funcionalidad asignada; queda como punto de anclaje para la lógica que se defina más adelante. A su derecha, separado 30 px, se añade un label estático "VFVE" (`lbl_vfve`) con la misma tipografía y colores de la barra.

---

## [2026-07-06] Reducir velocidad de giro en el aire — Aircraft.py

**Archivo:** `lib/Aircraft.py` — `get_rot()`.

Se reduce la capacidad de viraje por defecto de las aeronaves en vuelo (rama `else` de `get_rot()`, aeronaves no en tierra/aterrizando/despegando y no en `hld`): de 9º/s (estela M) o 5º/s (resto) a **3º/s** por defecto para cualquier estela distinta de `L` (que sigue en 15º/s, sin cambios).

Excepción: las aeronaves de tipo `AT*` (`self.type`, p. ej. ATR — AT42/AT43/AT72/AT76/ATP) mantienen **9º/s** cuando el escenario activo (`fir.aps[0]`) no es uno de `GCXO`, `GCTS`, `LEST`, `LEBB` o `LEMG`; en esos 5 escenarios caen también al nuevo default de 3º/s.

El caso `to_do == 'orbit'` se mantiene fijo a 9º/s para cualquier estela (incluida `L`), igual que en el comportamiento previo.

---

## [2026-07-02] Restaurar guardas multi-pantalla en atc_bahia — UCS.py, RaDisplay.py

**Archivo:** `lib/UCS.py` — `__init__()`, `imprimir_ficha()`, gestor de doble-click de CFL, `save_state()`, `exit()`; `lib/RaDisplay.py` — `set_active_sectors()`.

El commit anterior (`1414d82`) había eliminado, en varios sitios, la guarda `and self.disp_number == 1` y los `hasattr(self/radisp, 'atc_bahia')` que exige la invariante multi-pantalla documentada en `CLAUDE.md` (`atc_bahia`/OSF solo se crean en `disp_number == 1`; las pantallas secundarias no tienen el atributo). Sin la guarda, la pantalla 2 creaba su propia `ATCBahia` (rompiendo el singleton) y varios métodos (`imprimir_ficha`, asignación de CFL por doble-click, `save_state`, `exit`) lanzaban `AttributeError` en pantalla 2 o en modo OSF. Se restauran las guardas en los 6 puntos afectados. También se revierte un comentario incorrecto sobre el filtro FALT (`"Temporary altitude filter at 1000 feet..."`, copiado por error de un comentario de LEGR) a su descripción original.

No se toca el cambio de `GTA.py` sobre el orden de `sector_sequence` para `LEST/LECO/LEVX` (confirmado como intencional).

---

## [2026-07-02] Revertir regresión accidental de fixes previos — OSF.py, PrevDesp.py

**Archivo:** `lib/osf/OSF.py` — `OSF.__init__()` (`field_defs`, `_default_layouts`/`_default_ext_layouts`, merge con `self.fir.osf_layouts`), método de construcción de ficha extendida (`ext_values_full`); `lib/osf/PrevDesp.py` — `__init__()` (`field_defs`, `layouts`, `column_titles`), `_construir_ficha()` (dict `values`).

Una edición reciente sobre `OSF.py`/`PrevDesp.py` (comentarios "OK" añadidos a los layouts) reintrodujo, sin querer, tres regresiones ya corregidas y documentadas el 2026-05-26/27:

1. **Merge con la hoja `OSF_Layout` eliminado**: `self.layouts`/`self.ext_layouts` en `OSF.py` habían pasado a ser diccionarios fijos, sin el `dict(_default...).update(getattr(self.fir, 'osf_*_layouts', {}))`. Efecto: la hoja `OSF_Layout` del escenario dejaba de tener efecto alguno pese a que `FIR.py` la sigue parseando. Restaurado el merge.
2. **`cssr` vuelto a `csrr` en `OSF.py`**: reintroducía la inconsistencia con `PrevDesp.py` (que usa `cssr`) que ya se había unificado. Revertido a `cssr` en `field_defs`, `_default_ext_layouts` y `ext_values_full`.
3. **`rwydep` vuelto a `rwydes` en `PrevDesp.py`**: el campo sigue mostrando la pista de despegue (`f.deprwy`), así que el nombre `rwydes` (reservado para pista de llegada en `OSF.py`) volvía a ser incorrecto. Revertido a `rwydep` (`field_defs`, `layouts`, `column_titles`, `values`).
4. **Formato de `cfl` en `PrevDesp.py` roto**: se había sustituido `"%03d" % int(round(f.cfl_c))` por `str(f.cfl)` sin formatear ni redondear, mostrando p.ej. `60.0` en vez de `060` y usando el nivel autorizado real (`cfl`) en vez del introducido por el controlador (`cfl_c`). Restaurado el cálculo con `cfl_c` y formato `%03d`.

---

## [2026-06-16] Filtro de altitud FALT con controles de C:/GAMMA — UCS.py

**Archivo:** `lib/UCS.py` — `__init__()`, `update_track()`, `redraw()` (barra inferior).

Se sustituyen los controles del filtro de altura del menú inferior por los de la versión `C:/GAMMA`, para unificar el comportamiento. Antes había dos spinners `tix.Control` (FALT inferior/superior) más un botón `000 - 250` sin función. Ahora hay tres controles: **FALT INF** y **FALT SUP** (botones que muestran el valor `%03d` y abren un selector emergente con Listbox 990→000 + Entry de entrada manual, paso de 10) y **FALT** (botón master que activa/desactiva el filtro).

1. `__init__()`: se añade `self._falt_enabled = False` (estado inicial del filtro desactivado, no se persiste; igual que en `C:/GAMMA`).
2. `update_track()`: el filtro de altitud pasa a ser **independiente** del filtro FGND. Antes el corte por `select_FALT_varmin/varmax` solo se aplicaba dentro de la rama `filterFGND`; ahora son dos `elif` de alto nivel condicionados a `self._falt_enabled`, de modo que el botón FALT gobierna el filtro con independencia de FGND.
3. `redraw()`: se eliminan `faltmin`, `faltmax` y `but_000250`; se añaden `but_falt_min`, `but_falt_max` y `but_falt` con sus helpers (`_update_falt_labels`, `_toggle_falt`, `open_falt_selector`). Los tres botones no fijan `font`, de modo que heredan la fuente por defecto y quedan del mismo tamaño que el resto de botones de la barra.

4. Selector emergente de altitud (`open_falt_selector`): (a) se quita `SMALL_FONT` de Label de título, botón de cierre, Listbox y Entry para que usen la fuente por defecto (antes se veían demasiado pequeños). (b) El campo libre (Entry) aplicaba mal el valor: `_apply_and_close` truncaba al múltiplo de 10 inferior (`(val // 10) * 10`), por lo que escribir `126` + ENTER aplicaba `120`. Ahora se aplica el valor exacto introducido, solo acotado a `[0, 990]`.

---

## [2026-05-27] Unificar origen del campo `cfl` en PrevDesp — PrevDesp.py

**Archivo:** `lib/osf/PrevDesp.py` — `_construir_ficha()` (dict `values`).

El campo `cfl` se tomaba de `f.cfl` (valor crudo, sin formatear), mientras que en la ficha extendida de `OSF.py` se toma de `f.cfl_c` (nivel en FL) con formato `%03d`. Se unifica `PrevDesp` al mismo origen y formato que `OSF.py` para que el nivel autorizado se muestre igual en ambos sitios. Se usa `int(round(cfl_val))` (redondeo al más cercano), conforme a la regla de redondeo de niveles del proyecto (nunca `int()` directo).

---

## [2026-05-27] Renombrar campos de squawk y pista en fichas OSF/PrevDesp — OSF.py, PrevDesp.py

**Archivos:** `lib/osf/PrevDesp.py` — `__init__()` (`field_defs`, `layouts`, `column_titles`), `_construir_ficha()` (dict `values`); `lib/osf/OSF.py` — `OSF.__init__()` (`field_defs`, `_default_ext_layouts`), método de construcción de ficha extendida (`ext_values_full`); `CLAUDE.md`.

Unificación de nomenclatura de dos campos que estaban mal nombrados o duplicados entre módulos.

1. **`rwydes` → `rwydep` en `PrevDesp.py`**: el campo mostraba la pista de *despegue* (`f.deprwy`, título `PD`) pero se llamaba `rwydes`, que en `OSF.py` designa la pista de *llegada*. Se renombra a `rwydep` para que el nombre refleje el dato. Valor placeholder por defecto cambiado de `24R` a `24L` por coherencia con `rwydep` en `OSF.py` (es solo placeholder, siempre se sobrescribe con `f.deprwy`).
2. **`csrr` → `cssr` en `OSF.py`**: el campo de código SSR/squawk se llamaba `csrr` en OSF y `cssr` en PrevDesp. Se unifica a `cssr` (coincide con `TLPV.cssr`). Afecta a `field_defs`, a los seis layouts de `_default_ext_layouts` que lo incluían y a la clave de `ext_values_full`.

Nota: `FIR.py` lee los tokens de la hoja `OSF_Layout` del escenario tal cual (sin catálogo de validación). Un escenario cuyo `campos_extendida` incluya `csrr` dejaría de mostrar el squawk tras este cambio; revisar/actualizar esas hojas a `cssr` si las hubiera.

---

## [2026-05-26] Parametrizar layouts de fichas OSF desde el escenario — FIR.py, OSF.py, GCTS.xlsx

**Archivos:** `lib/FIR.py` — `ESCENARIO.__init__()`, `FIR.__init__()`; `lib/osf/OSF.py` — `OSF.__init__()`; `C:\03 ESCENARIOS\DRNA_C\GCTS\GCTS.xlsx` — nueva hoja `OSF_Layout`.

Se saca la estructura de las fichas OSF (normales y extendidas) del código a una hoja del Excel del escenario, para que dependa del aeropuerto y no haga falta tocar `.py` para añadir/quitar campos por bahía.

1. **Nueva hoja `OSF_Layout`** en el xlsx del escenario, con columnas `bahia | depdes | campos_normal | campos_extendida`. Una fila por `(bahia, depdes)`. `bahia` admite combos con `+` (p.ej. `GND+LCL`). `campos_extendida` puede quedar vacío (caso `CLR`). 10 filas iniciales replicando exactamente los layouts hardcoded.
2. **`FIR.ESCENARIO.__init__`**: nuevo bloque tras parseo de la hoja `OSF`. Lee `OSF_Layout`, expone `self.osf_layouts` y `self.osf_ext_layouts` como `{(bahia, depdes): [campos]}`. Si la hoja falta, los dicts quedan vacíos (warning en log).
3. **`FIR.__init__`**: copia ambos dicts desde `datos_escenario` (`self.osf_layouts`, `self.osf_ext_layouts`).
4. **`OSF.__init__`**: los dicts hardcoded pasan a ser `_default_layouts` / `_default_ext_layouts` (defaults). `self.layouts` y `self.ext_layouts` se construyen como `dict(default).update(getattr(self.fir, 'osf_*_layouts', {}))`, así una clave presente en el Excel sobrescribe el default y una clave ausente cae al default.
5. **`PrevDesp.py`**: sin cambios. Tiene su propio `self.layouts` con campos específicos (`tobt`, `tsat`, `ctot`, `tsac`, `asrt`, `cssr`) que no pertenecen al catálogo OSF.

`OSF_Fields` (catálogo `nombre → {width, value}`) se mantiene hardcoded en `OSF.py` por ahora — solo se parametriza la *composición* de cada ficha, no la definición de cada campo.

Validado: cargar el escenario GCTS con el nuevo parser produce 10 layouts normales + 9 extendidos idénticos a los defaults (0 mismatches). Backup del xlsx en `GCTS.xlsx.bak`.

---

## [2026-05-24] ATCBahia duplicada al usar dos displays — UCS.py, RaDisplay.py

**Archivos:** `lib/UCS.py` — `__init__()`, `imprimir_ficha()`, `vt_handler()`, `save_state()`, `exit()`; `lib/RaDisplay.py` — `change_sector()`

Con dos displays raster activos, se creaba una ventana `ATCBahia` por cada display en lugar de una sola. Causa: no había guard de `disp_number == 1` al construir `ATCBahia`, a diferencia del bloque OSF que ya lo tenía. Correcciones:

1. `UCS.__init__` y `RaDisplay.change_sector`: añadido `and self.disp_number == 1` en la condición de creación de `ATCBahia`.
2. `imprimir_ficha`: añadido `hasattr(radisp, 'atc_bahia')` para que display 2 no falle al iterar los displays.
3. `vt_handler` (update_cfl): añadido `if hasattr(self, 'atc_bahia')`.
4. `save_state`: cambiado `else:` por `elif hasattr(self, 'atc_bahia'):`.
5. `exit`: añadido `if hasattr(self, 'atc_bahia')` antes de `destroy()`.

---

## [2026-05-24] Fix redondeo CFL/TFL/RFL en etiqueta y diálogo de niveles — RaElements.py

**Archivo:** `lib/RaElements.py` — `VisTrack.refresh()` y popup de edición de niveles

Tres focos del mismo bug: `int()` trunca hacia abajo, por lo que un float como `299.999...` daba **299** en lugar de **300**.

1. **Etiqueta CFL — caso ascendente** (línea ~6837): `int(vt.cfl-0.5)` → `int(vt.cfl+0.5)`. El `-0.5` era incorrecto y causaba que FL300 apareciera como **299** siempre que el avión estuviera por debajo del CFL.
2. **Etiqueta TFL** (líneas ~6851-6862): `int(vt.tfl)` → `int(vt.tfl+0.5)` en las 5 ocurrencias (formatos `atc-ucs` y `atc-na`).
3. **Diálogo de edición** (líneas ~7360, 7366, 7377): `int(self.vt.cfl)`, `int(self.vt.tfl)`, `int(self.vt.rfl)` → con `+0.5` en los tres campos al abrir el popup.

---

## [2026-05-24] Color track asumido y comando nivel — UCS.py

**Archivo:** `lib/UCS.py` — correlación de tracks (líneas ~1234 y ~1257)

Dos cambios en la lógica de correlación:

1. **Color de track asumido según modo SACTA**: si `sacta_mode == 'UCS'` el track asumido pasa a `NONASSUMED_COLOR_UCS`; en cualquier otro modo usa `ASSUMED_COLOR_PICT`. Antes siempre se usaba `ASSUMED_COLOR_PICT`.

2. **Comando al asignar nivel de vuelo**: se usa `set_cfl_c` en lugar de `set_tfl`. Se comentan `vt.set_label_item('cfl', True)` y el envío de `set_tfl`; antes eran los activos y `set_cfl_c` estaba comentado.

---

## [2026-05-22] Color APP: verde pálido/fuerte según asumido — RaElements.py

**Archivo:** `lib/RaElements.py` — `VisTrack.reconfigure()`

En modo APP (sacta_mode distinto de OSF y UCS), el color ahora sigue la lógica de asumido: verde pálido (`NONASSUMED_COLOR_UCS` = `#99DD99`) si no asumido, verde fuerte (`ASSUMED_COLOR_UCS` = `green`) si asumido. Antes se pintaba siempre verde/naranja/gris independientemente del estado de asunción. VEH sigue en gris. Afecta a etiqueta, plot y leader (estos dos ya leían `self.color` correctamente).

---

## [2026-05-22] Menú MAPAS: segunda ventana para mapas 37+ — UCS.py

**Archivo:** `lib/UCS.py` — `ventana_auxiliar.mapas_buttons()`, `__init__`, `close_windows()`

El popup de MAPAS ahora genera dos ventanas `Toplevel` separadas lado a lado, justificadas por abajo. La primera muestra mapas 1-36 y la segunda (subnivel) muestra mapas 37 en adelante. Añadido `_mapas_toplevel2` para gestionar el ciclo de vida de la segunda ventana. Preparado para que en el futuro la segunda ventana sea un submenú contextual de la primera.

---

## [2026-05-21] Quitar topmost del popup MAPAS — UCS.py

**Archivo:** `lib/UCS.py` — `ventana_auxiliar.redraw()`, función `mapas_buttons()`

Eliminado `popup.attributes('-topmost', 1)` del popup de MAPAS. Las ventanas OSF y PrevDesp mantienen `topmost=1` y deben quedar siempre por encima. El popup de MAPAS, al ser `overrideredirect=True` hijo del canvas radar, aparece sobre la botonera sin necesitar topmost.

---

## [2026-05-20] Ventana OSF duplicada en pantalla secundaria — UCS.py

**Archivo:** `lib/UCS.py` — `__init__()`, bloque `else` (disp_number > 1)

Para display > 1, `get_instance(self, self.bahia_type)` usaba la bahia_type derivada del sector de Layout2, que podía diferir de la de Layout1. Eso generaba una `instance_key` distinta → el singleton no encontraba la instancia existente y abría una ventana OSF nueva. Solución: para display > 1, buscar directamente la primera instancia viva en `OSF._instances.values()` en lugar de calcular una clave potencialmente diferente.

---

## [2026-05-20] ValueError en UCS disp_number>1: bahia_type None al llamar OSF.get_instance — UCS.py

**Archivo:** `lib/UCS.py` — `__init__()`, línea ~170

`self.bahia_type` se calculaba solo dentro del bloque `if self.disp_number == 1`, quedando `None` para pantallas secundarias. Al llegar al bloque `if self.disp_number > 1`, `OSF.get_instance(self, None)` lanzaba `ValueError`. Solución: mover el cálculo de `bahia_type` (y la inicialización de `lcl_sector_list`/`gnd_sector_list`) fuera del check de `disp_number`, dentro del bloque `sacta_mode == 'OSF'`, y luego ramificar en `disp_number == 1` (crea) vs `else` (reutiliza).

---

## [2026-05-20] "SOLICITUD P/B" no aparecía si no había hoja RetrocesosOSF — OSF.py

**Archivo:** `lib/osf/OSF.py` — popup acciones salidas, línea ~2243

Cuando `fir.pushbacks` estaba vacío (hoja `RetrocesosOSF` inexistente o sin stands configurados), el bloque `else` solo añadía "AUTORIZACION TAX" para el estado `STARTING`, omitiendo "SOLICITUD P/B". Añadida la opción antes de "AUTORIZACION TAX" para que aparezca siempre que el ACT esté en S/U, independientemente de si el stand tiene retroceso configurado.

---

## [2026-05-19] Sector activo no persistía entre sesiones en GCXO — RaDisplay.py

**Archivo:** `lib/RaDisplay.py` — `save_state()`, línea ~1465

El bucle de mapas locales sobreescribía la clave `Layout1.sector` con el booleano `False` cuando el escenario tenía un mapa local llamado exactamente `"sector"` (caso GCXO). Esto hacía que en la siguiente sesión la validación fallara (`"False"` no está en `fir.sectors`) y el sector se reseteara siempre al primero de la lista. Solución: mover la escritura de `"sector"` al final de `save_state()`, después del bucle de mapas, para que siempre gane.

---

## [2026-05-19] Simplificar check twr_only tras normalización — GTA.py / FIR.py

**Archivos:** `lib/FIR.py` línea 50, `lib/GTA.py` línea 430

Añadido `'TORRE': 'LCL'` y `'TMA': 'APP'` a `_SECTOR_ALIASES` en FIR.py para coherencia con los demás alias. Simplificado el check `twr_only` en GTA.py: eliminados `"TWR"` y `"TORRE"` del tuple positivo, y colapsadas las negaciones `"TMA"` y `"APROXIMACION"` en un único `"APP" not in pos_upper`, ya que tras la normalización nunca llegan en su forma original.

---

## [2026-05-19] Normalizar sector de Exercise antes de usarlo — GTA.py

**Archivo:** `lib/GTA.py` — `load()` línea 208, `reload()` línea 262

`e.sector` venía sin normalizar desde Exercise.py (p.ej. `'TWR'`), pero `fir.release_required_ads` y `fir.local_ads` usan claves canónicas (`'LCL'`, `'GND'`, `'CLR'`), causando `KeyError`. Aplicado `FIR._normalize_sector()` en los dos puntos de asignación de `self.sector`.

---

## [2026-05-18] sector_sequence Tenerife condicionado a "Posicion" del ejercicio — GTA.py

**Archivo:** `lib/GTA.py` — función de carga de vuelos, bloque Tenerife (GCXO/GCTS)

El `sector_sequence` para Tenerife ahora depende del parámetro "Posicion" del ejercicio (`self.sector`):
- **TWR / GND / LCL** (contiene alguna de estas palabras y no "APP"/"TMA"): secuencia sin APP → llegadas `['LCL','GND']`, salidas `['GND','LCL']`
- **APP / TMA** (o cualquier otro valor): secuencia completa → llegadas `['APP','LCL','GND']`, salidas `['GND','LCL','APP']`

---

## [2026-05-18] Fix: sectores TRANSFERIR dinámicos en popup ACT — OSF.py

**Archivo:** `lib/osf/OSF.py` — `_show_act_popup()`, bloque `elif kind == "TRANSFERIR":`

Lista de sectores hardcodeada (`GMC_N`, `GMC_C`, `GMC_S`, `LCL_24L/06R`, `LCL_24R/06L`) sustituida por lista dinámica leída de `self.fir.sectors`, excluyendo el sector propio, igual que ya se hizo en el submenú "Transferir" de obstáculo:

```python
# Antes:
add_row(body, 0, "GMC_N", lambda: self._secondary_click(kind, "GMC_N"))
add_row(body, 1, "GMC_C", ...)
...
# Después:
sectores_disponibles = [s for s in self.fir.sectors if s != self.sector]
for idx, sec in enumerate(sectores_disponibles):
    add_row(body, idx, sec, lambda s=sec: self._secondary_click(kind, s))
```

---

## [2026-05-18] Optimizaciones timer() — GTA.py

**Archivo:** `lib/GTA.py` — función `timer()`

9 optimizaciones portadas desde análisis previo en C:\GAMMA:

1. **Bug bounding-box anti-colisión**: `dx < CLEARANCE_DISTANCE` → `abs(dx) < CLEARANCE_DISTANCE` (y lo mismo para `dy`). El filtro previo al O(n²) ahora descarta correctamente pares con gran distancia negativa.
2. **Código muerto eliminado**: `self.metar = self.metar` era un NOP (sin property setter). Eliminado del bucle `while`.
3. **Timedelta en catch-up reutilizado**: `datetime.timedelta(seconds=delta)` dentro del `while` de catch-up sustituido por `td`, objeto ya creado antes del bucle.
4. **`total_seconds()` calculado dos veces**: añadido `lag = (self.t - f.t).total_seconds()` antes del `if`; el `while` interior recalcula correctamente porque `f.t` avanza. Añadida constante `two_delta = 2 * delta` antes del bucle de vuelos.
5. **`self.e.auto_taxi` en O(n²)**: cacheado en `auto_taxi = self.e.auto_taxi` antes de los bucles de pares. Variable local más rápida que doble lookup de atributo.
6. **`self.fir.aerodromes` por vuelo**: cacheado en `aerodromes = self.fir.aerodromes` antes del bucle. Evita 3 lookups por vuelo cada tick.
7. **`from twisted.internet import threads` movido a imports globales** (línea 31). Dejaba de ejecutarse la sentencia de import cada segundo.
8. **`import sys` eliminado de `serialize_update_message`**: `sys` ya estaba importado globalmente en línea 19.
9. **`import dill` eliminado de `serialize_update_message`**: `dill` ya estaba importado globalmente en línea 21.

---

## [2026-05-14] Fix: sectores_disponibles dinámico desde FIR

**Archivo:** `lib/osf/OSF.py` — submenú "Transferir" de obstáculo

Sustituida lista hardcodeada de sectores (específica de otro aeropuerto) por lista dinámica leída de `self.fir.sectors`, excluyendo el sector propio:

```python
# Antes:
sectores_disponibles = ["GMC_N", "GMC_C", "GMC_S", "LCL_24L/06R", "LCL_24R/06L"]
# Después:
sectores_disponibles = [s for s in self.fir.sectors if s != self.sector]
```

---

## [2026-05-14] Ventana MAPAS: nuevo formato lista vertical con Toplevel

**Archivo:** `lib/UCS.py` — `mapas_buttons()`, `close_windows()`, `__init__`

Rediseño completo de la ventana MAPAS:
- Lista vertical única numerada (`1 NOMBRE_MAPA`, `2 ...`) en lugar del grid de varias columnas anterior
- `tix.Toplevel` con `overrideredirect(True)` y `attributes('-topmost', 1)` — siempre visible por encima de la botonera y demás widgets
- Posicionado con `winfo_rootx/rooty` del botón MAPAS; se coloca justo encima del botón
- Frame simple sin Canvas (el Toplevel se dimensiona automáticamente al contenido, sin altura fija)
- Fondo `#534d4d` igual que la botonera inferior; texto blanco; fuente Helvetica 8
- `self._mapas_toplevel` gestiona el ciclo de vida; `close_windows()` lo destruye con `.destroy()`

---

## [2026-05-14] Fix ventana MAPAS: Toplevel con -topmost

**Archivo:** `lib/UCS.py` — `mapas_buttons()`, `close_windows()`, `__init__`

Sustituido el Frame incrustado en canvas por un `tix.Toplevel` con:
- `overrideredirect(True)` — sin borde ni barra de título
- `attributes('-topmost', 1)` — siempre por encima de otras ventanas
- Posicionado con `winfo_rootx/rooty` del botón MAPAS, ajustando Y para que quede justo encima
- `self._mapas_toplevel` como nuevo atributo de ciclo de vida; `close_windows()` lo destruye con `.destroy()`

---

## [2026-05-14] Fix ventana MAPAS: posicionamiento sobre la botonera

**Archivo:** `lib/UCS.py` — función `mapas_buttons()`

`ventana.winfo_height()` devolvía 0 si la geometría no estaba calculada, colocando el menú en `y=alto` (debajo del canvas). Fix:
- `w.update_idletasks()` y `ventana_mapas.update_idletasks()` antes de consultar tamaños
- `winfo_reqheight()` (altura solicitada, siempre disponible) con fallback a `winfo_height()` y luego a 50 px
- `w.tag_raise(i)` para garantizar z-order sobre la botonera

---

## [2026-05-14] Fix ventana MAPAS: z-order y color de fondo

**Archivo:** `lib/UCS.py` — función `mapas_buttons()`

- `w.tag_raise(i)` tras `create_window` para que el menú quede por delante de la botonera en el canvas
- `BG` cambiado de `#1e1e1e` a `#534d4d` para igualar el color de fondo de la botonera inferior (`ventana`)
- `selectcolor` y `activebackground` ajustados a `#6a6060` (tono coherente con el nuevo fondo)

---

## [2026-05-14] Nuevo formato ventana MAPAS

**Archivo:** `lib/UCS.py` — función `mapas_buttons()` (dentro de `ventana_auxiliar`)

La ventana de MAPAS pasó de un grid de varias columnas (nueva columna cada 10 filas) a una lista vertical única numerada con scroll.

- Lista numerada (`1 NOMBRE_MAPA`, `2 ...`) en columna única
- Canvas con Scrollbar vertical; se muestra la barra solo si hay más de 32 mapas
- Scroll con rueda del ratón (`<MouseWheel>`)
- Fondo oscuro (`#1e1e1e`) con texto blanco, fuente pequeña (`Helvetica 8`)
- Máximo 32 filas visibles; el resto se alcanza con scroll

---

## [2026-05-13] Fix: ATCBahia no desaparecía al cambiar de modo

**Archivo:** `lib/RaDisplay.py` — método `set_active_sectors`

`ATCBahia` se asignaba a `self.atc_bahia` pero nunca se añadía a `display_remote`, por lo que el bucle de destrucción del paso 1 no la alcanzaba. Al cambiar a modo OSF la ventana permanecía visible.

**Fix:** Se oculta `atc_bahia` (con `hide()`) al inicio de `set_active_sectors`, junto con la destrucción de las ventanas OSF de `display_remote`, antes de calcular el nuevo `bahia_type`:

```python
if hasattr(self, 'atc_bahia') and self.atc_bahia.showed:
    self.atc_bahia.hide()
```

---

## [2026-05-13] Fix: sector guardado en settings siempre volvía a LCL al reiniciar

**Archivo:** `lib/RaDisplay.py` — `__init__`, línea de validación de sector

El sector puede guardarse como combo (`'LCL,GND'`), pero la validación comparaba el string completo contra `fir.sectors`, que solo contiene nombres individuales. El combo nunca estaba en la lista → siempre caía a `fir.sectors[0]` (= `'LCL'`).

**Fix:** Ahora se valida cada parte del combo por separado:

```python
# Antes:
if self.sector not in fir.sectors:
# Después:
if not all(s in fir.sectors for s in self.sector.split(',')):
```

---

## [2026-05-13] Portado de cambios desde C:\GAMMA\cambios.md

Implementados los 12 grupos de cambios descritos en `C:\GAMMA\cambios.md`:

| Archivo | Cambio |
|---|---|
| `lib/ConfMgr.py` | Reescritura completa: ConfigParser+GAMMA.ini → json+gamma_settings.json. Nuevos métodos `set_scenario()`, `_section_dict()`. Acumulación en memoria, escritura atómica en `save()`. Migración automática desde GAMMA.ini. `ver` sigue leyéndose de GAMMA.ini vía ConfigParser. |
| `lib/FIR.py` | `ESCENARIO` inicializa `taxi_ias=15.0` y lo lee de la hoja. `FIR.__init__` copia `self.taxi_ias` y `self.ap`. Restaurada función `_normalize_sector` y sus 3 llamadas. |
| `lib/Aircraft.py` | Eliminada constante `TAXI_IAS=15.`; sus 3 usos sustituidos por `fir.taxi_ias`. |
| `lib/RaElements.py` | Ventana `change_speed`: sugerencia IFR parado usa `fir.taxi_ias`; VFR parado = 6 kt; push-back = 4 kt. |
| `lib/RaDisplay.py` | `save_current_state()` renombrado a `save_state()` (no escribe a disco). `exit()` llama `save_state()` + `conf.save()`. Brightness lee de `self.conf` en lugar de crear instancias nuevas. Fix sector inválido al cambiar FIR: cae a `fir.sectors[0]`. |
| `lib/UCS.py` | Nuevo `save_state()` (delega a RaDisplay). `pause()` vacío. `exit()` simplificado. Mapas locales cargados de `Layout<n>` + `b_show_hide_localmaps()` en `__init__`. Fix `sector_list[0]` en lugar de `sector.split(',')[0]`. |
| `lib/Pseudopilot.py` | Nuevo `save_state()` (delega a RaDisplay). `exit()` simplificado. Mapas locales cargados de `Layout<n>`. `b_show_hide_localmaps` convertida de closure a método real de `ventana_auxiliar`. |
| `GAMMA.py` | `_remote_client=None` global. `_save_all_displays()` guarda todos los displays. `atexit.register(_save_all_displays)`. `Exit()` llama `_save_all_displays()`. `connect()` guarda referencia y pasa `connectionLost=_save_all_displays`. |
| `lib/RemoteClient.py` | `process_message('init')` llama a `conf.set_scenario(fir.ap[0])`. `save_current_state()` → `save_state()`. |

---

## [2026-04-23] Portado de funcionalidades de ficha extendida desde LEPA

**Archivo:** `lib/osf/OSF.py`

### 1. Redirect de clic en ficha extendida → ficha madre (`on_middle_click`)

Cuando el usuario hace clic central sobre una ficha extendida, ahora se redirige automáticamente a la ficha madre en lugar de operar sobre la extendida.

```python
# Si se ha clicado la ficha extendida, redirigir a la ficha madre
if ficha.get("is_extended"):
    parent_cs = ficha.get("parent_callsign", "")
    if parent_cs:
        parent_found = self._find_ficha_by_callsign(parent_cs)
        if parent_found:
            zi, fi = parent_found[0], parent_found[1]
            zona_idx, ficha_idx = zi, fi
            ficha = self.zonas[zi]["fichas"][fi]
```

### 2. Resaltado solidario de ficha extendida (`draw_zonas`)

Cuando se selecciona o arrastra una ficha principal, su ficha extendida también se resalta con borde blanco.

```python
_hl = (self.dragging_line == (i, actual_idx)) or (self.selected_line == (i, actual_idx))
if not _hl and ficha.get("is_extended"):
    _parent_cs = ficha.get("parent_callsign", "")
    for _ref in (self.selected_line, self.dragging_line):
        if _ref and _ref[0] == i:
            _rfi = _ref[1]
            if 0 <= _rfi < len(self.zonas[i]["fichas"]):
                _rf = self.zonas[i]["fichas"][_rfi]
                if not _rf.get("is_extended") and _rf.get("values", {}).get("callsign") == _parent_cs:
                    _hl = True
                    break
if _hl:
    self.canvas.create_rectangle(...)
```

**Nota:** La diferencia inversa (LECG más avanzado que LEPA) se conservó: el cálculo de `zonas_count` en LECG lee el número de zonas dinámicamente desde el Excel/FIR via `zonasOSF`, mientras que LEPA los tiene hardcodeados.

---

## [2026-04-23] Corrección de campos en blanco en ficha extendida

**Archivo:** `lib/osf/OSF.py` — método `_toggle_extended`

### 3. `sid_ext` — siempre en blanco

**Causa:** No estaba definido en `field_defs` ni en `ext_values_full`. Al no existir en ningún dict, `_field_value("sid_ext")` devolvía `""`.

**Fix:**
- Añadido a `field_defs` con `{"width": 100, "value": ""}`.
- Añadido a `ext_values_full` mapeando a `f.stand_sid_atc` (igual que `sid`).

### 4. `vel` — mostraba "240" hardcodeado

**Causa:** La línea `vel = "240"` ignoraba la velocidad real del vuelo.

**Fix:** Ahora usa `f.ias` (IAS en nudos, redondeado a entero). Devuelve `""` si el avión está parado (ias = 0).

```python
ias_val = getattr(f, "ias", None) if f else None
vel = "%d" % int(round(ias_val)) if (ias_val is not None and ias_val > 0) else ""
```

### 5. `cfl` — mostraba "060" hardcodeado

**Causa:** La línea `cfl = "060"` ignoraba el CFL real del vuelo.

**Fix:** Ahora usa `f.cfl_c` (nivel de vuelo autorizado almacenado en FL, formateado como 3 dígitos: 350.0 → "350").

```python
cfl_val = getattr(f, "cfl_c", None) if f else None
cfl = "%03d" % int(round(cfl_val)) if cfl_val is not None else ""
```

### 6. `airline` — mostraba "VUELING" siempre

**Causa:** `getattr(f, "airline", "VUELING")` — el atributo `airline` **no existe en Aircraft.py**. Siempre usaba el fallback.

**Fix:** Ahora usa `f.radio_callsign`, que es el nombre de compañía ICAO derivado del callsign mediante la tabla de callsigns (e.g. "IBE..." → "IBERIA").

```python
airline = str(getattr(f, "radio_callsign", "") or "") if f else ""
```

### 7. `qnh` — mostraba "Q1013" siempre

**Causa:** `getattr(f, "qnh_txt", "Q1013")` — el atributo `qnh_txt` **no existe en Aircraft.py**. El QNH es una propiedad global de la atmósfera gestionada por GTA (`GTA.self.qnh`), no de cada vuelo.

**Fix:** Ahora lee `self.radisplay.giw.qnh` (float, e.g. 1013.4) y lo formatea como "Q1013".

```python
try:
    qnh_float = self.radisplay.giw.qnh
    qnh = "Q%04d" % int(round(qnh_float))
except Exception:
    qnh = ""
```

### 8. `csrr` — mostraba "None" para vuelos sin squawk

**Causa:** `str(getattr(f, "squawk", ""))` — Aircraft inicializa `self.squawk = None`. Como el atributo existe (aunque sea None), `getattr` devuelve `None` y no usa el fallback `""`. Resultado: `str(None)` = `"None"`.

**Fix:** Comprueba `None` explícitamente antes de convertir a string.

```python
squawk = getattr(f, "squawk", None) if f else None
csrr = str(squawk) if squawk is not None else ""
```

### 9. `eobt`, `eldt`, `park` en ficha extendida — mostraban placeholders

**Causa:** No estaban en `ext_values_full`. El fallback `_field_value()` devolvía los valores por defecto de `field_defs` ("1234" para eobt/eldt, "152" para park) en lugar de los valores reales del vuelo.

**Fix:** Añadidos a `ext_values_full` con los valores reales del vuelo.

```python
# eobt
eobt_raw = getattr(f, "eobt", None) if f else None
try:
    eobt_ext = "%02d%02d" % (eobt_raw.hour, eobt_raw.minute)
except Exception:
    eobt_ext = str(eobt_raw) if eobt_raw is not None else str(getattr(f, "etd", "") or "")

# eldt
eldt_raw = getattr(f, "eldt", None) if f else None
eldt_ext = str(eldt_raw) if eldt_raw is not None else ""

# park
park_ext = str(getattr(f, "park", "") or "") if f else ""
```