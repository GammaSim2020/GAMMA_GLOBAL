# Modificaciones pendientes en los Excel de escenario

Lista viva de lo que hay que cambiar **a mano** en los Excel de `C:\03 ESCENARIOS` para la versión unificada (el código no escribe en los Excel). Se actualiza en cada fase. Detalle de cada clave: `PARAMETROS_ESCENARIO.md`.

**Regla general:** si no se toca nada, cada escenario se comporta como antes. Las filas de abajo son correcciones necesarias (marcadas **Obligatorio**) o decisiones opcionales.

Formato de las filas nuevas en la hoja `Escenario`: columna A = clave, columna B = valor (y C cuando se indique).

| # | Escenario (fichero) | Hoja | Qué cambiar | Motivo | Tipo | Fase |
|---|---|---|---|---|---|---|
| 1 | LEST (`DRNA_CN\LECG_nosedeque\LEST.xlsx`) | `OSF_Layout` | Renombrar el campo `csrr` → `cssr` | GLOBAL usa el nombre `cssr`; con `csrr` el campo no se pinta en la ficha extendida GND dep_local | **Obligatorio** (decisión 7: lo corrige el usuario) | 1 |
| 2 | LEPA (`DRNA_B\LEPA\LEPA.xlsx`) | `Escenario` | Añadir fila `alertas` \| `0` | Su Excel trae las hojas INCW/CMAC/CATC y las alertas se activarían; en principio solo se quieren en LEBL | Opcional (recomendado si no se quieren alertas en LEPA) | 4 |
| 3 | LEST | `Escenario` | Fila `ficha_borde_salida_ads` \| `LPPR` | Borde azul de salidas a LPPR en la bahía de fichas (pensado para LECG, nunca estuvo activo) | Opcional, pendiente de decisión | 3 |
| 4 | LEST | `Escenario` | Fila `ficha_freq_teclado` \| `1` | Teclado en el campo frecuencia de la ficha (mismo caso) | Opcional, pendiente de decisión | 3 |
| 5 | LEBL (`DRNA_E\LEBL\LEBL.xlsx`) | `Escenario` | Fila `ifr_taxi_ias` \| `20` | La versión LEBL sugería 20 kt en la ventana de velocidad para aviones parados (valor fijo en código); GLOBAL sugiere la velocidad de rodaje del escenario (15 por defecto). **Ojo:** también cambia la velocidad de rodaje automática del motor | Opcional, solo si se quiere 20 kt | 1 |
| 6 | Cualquier escenario OSF que quiera vehículos con PVH y cruce/entrada a pista (p. ej. LEPA, LEMD) | `Escenario` | Fila `pvh` \| `1` | Solo LEBL lo tiene activo por defecto | Opcional | 4 |
| 7 | LEBL (y los que activen `pvh`) | `OSF` | Filas con las acciones `CRR`, `ENR`, `ENT`, `LIB` y su zona (`CRU` ya está) | La hoja de LEBL no las tiene: la ficha se queda en la zona en que estaba. Solo si se quiere que cambien de zona | Opcional | 4 |
| 8 | Escenarios con ejercicios largos y mucho tráfico (p. ej. LEBL, que lo tenía fijo en 3 s) | `Escenario` | Fila `refresco_aire` \| `3` | Los aviones en vuelo se refrescan cada 3 s en el radar; menos carga de pantalla | Opcional | 4 |
| 9 | GCLP, GCTS, GCXO, LEBB (hoja vacía), LEST, LERS, LEMG (sin hoja) | `RetrocesosOSF` | Rellenar una fila por stand: B = stand, C = `S` si admite retroceso, D-G = direcciones (N, S, E, W) | Sin datos se aplica la regla general (S/U → P/B con P/W y P/E). Solo si se quiere decidir por stand | Opcional | 4 |

## Escenarios sin cambios necesarios

LEBL (alertas y vehículos PVH activos sin tocar nada), LEMD, LEMG, GCLP, GCTS, GCXO, LEBB, LERS y los PICT (LEMH, LEAS, LEPP, LERJ, LESO, LEXJ, LEVT, LECO, LEVX, LEAM, LEGR, LEGE): cargan y funcionan con los valores por defecto.

## Cómo comprobar que se ha leído

Al cargar el escenario, `GAMMA.log` muestra `Parametros de escenario <nombre>: {...}` con los valores efectivos. Para las alertas: `AlertManager: activo con N zonas INCW` o `AlertManager: desactivado por el parametro de escenario 'alertas'`.
