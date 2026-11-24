# -*- coding: iso8859-15 -*-
"""Motor de alertas CATC (Conflicting ATC Clearances).

Detecta autorizaciones conflictivas entre pares de moviles en pistas
relacionadas (misma pista, opuestas, cruzadas, convergentes).
Evalua combinaciones de fases de autorizacion activa cargadas del Excel
(CATCsubtipos) con 4 categorias y 20 combinaciones.

Reutiliza zonas de proteccion INCW para deteccion de pista en cruces (CRU).
"""

import logging
from MathUtil import point_within_polygon, get_distance, get_cross_point
from alertas.alert_types import reciprocal_rwy
from alertas.alert_types import (Alert, ALERT_CATC, ALERT_INCW, ALERT_CMAC,
                                 SEVERITY_NONE, SEVERITY_WNG, SEVERITY_VIO, SEVERITY_MAP)

# Fases OSF_pof que representan autorizaciones activas para CATC
LININGUP = 'L/U'
DEPARTING = 'DEP'
LANDING = 'LDG'
CROSSING = 'CRU'
ENTERING = 'ENT'
MAP = 'MAP'
GA = 'GA'

# Fases previas a autorizacion (para prediccion)
TAXIING_OUT = 'TOU'
INCOMING = 'INC'
APPROACH = 'APP'
CRUREQ = 'CRR'
ENTREQ = 'ENR'

# Fases pof fisicas - filtro inicial
LOADING = 'LOADING'
INACTIVE = 'INACTIVE'

# Fases CATC (las que aparecen en la columna Combinacion del Excel)
CATC_PHASES = frozenset(['L/U', 'DEP', 'LDG', 'CRU', 'ENT', 'MAP'])

# Categorias
CAT_MISMA = 'MISMA_PISTA'
CAT_OPUESTAS = 'OPUESTAS'
CAT_CRUZADAS = 'CRUZADAS'
CAT_CONVERGENTES = 'CONVERGENTES'


class CATCEngine(object):
    """Motor de evaluacion de alertas CATC."""

    def __init__(self, fir):
        self.fir = fir
        self.zones = fir.incw_zones  # Reutiliza zonas INCW (para detectar CRU)

        # Construir tabla de conflictos desde CATCsubtipos
        # {(categoria, frozenset([faseA, faseB])): severidad}
        self.conflict_table = {}
        for entry in fir.catc_subtypes:
            cat = entry.get('categoria', '')
            comb = entry.get('combinacion', '')
            sev_str = entry.get('severidad', 'WNG')
            parts = comb.split('&')
            if len(parts) != 2:
                continue
            fase_a = parts[0].strip()
            fase_b = parts[1].strip()
            sev = SEVERITY_MAP.get(sev_str, SEVERITY_WNG)
            self.conflict_table[(cat, frozenset([fase_a, fase_b]))] = sev

        # Pistas del escenario
        self.runways = set()
        for (pista, tipo) in self.zones:
            self.runways.add(pista)

        # Pistas reciprocas
        self.reciprocal = {}
        # Calculada a partir del nombre de la pista (antes tabla fija de LEBL)
        for rwy in self.runways:
            self.reciprocal[rwy] = reciprocal_rwy(rwy)

        # Pistas cruzadas (desde Excel INCWpistasCruzadas)
        self.crossed_runways = set()  # {frozenset([rwy1, rwy2])}
        self.crossing_points = {}     # {frozenset([rwy1, rwy2]): (x, y)}
        self.crossing_dist_min = {}   # {frozenset([rwy1, rwy2]): dist_NM}
        for entry in getattr(fir, 'incw_pistas_cruzadas', []):
            p1 = str(entry.get('Pista1', '')).strip()
            p2 = str(entry.get('Pista2', '')).strip()
            if p1 and p2:
                pair = frozenset([p1, p2])
                self.crossed_runways.add(pair)
                dist_min = entry.get('Dist_Min_Sep', 0)
                if isinstance(dist_min, (int, float)) and dist_min > 0:
                    self.crossing_dist_min[pair] = float(dist_min)

        # Calcular puntos de cruce usando centroides de zonas ALIN
        for pair in self.crossed_runways:
            rwys = list(pair)
            cp = self._compute_crossing_point(rwys[0], rwys[1])
            if cp is not None:
                self.crossing_points[pair] = cp

        # Tablas CATC+CMAC (PPT slides 57, 59, 61)
        # {(relacion_pista, cmac_subtype, auth_fase): severidad}
        W = SEVERITY_WNG
        V = SEVERITY_VIO
        N = SEVERITY_NONE
        self.cmac_catc_table = {}
        # MISMA PISTA (slide 57)
        _misma = {
            ('ALIN_NA',  'L/U'): W, ('ALIN_NA',  'DEP'): W, ('ALIN_NA',  'LDG'): N,
            ('ALIN_NA',  'MAP'): N, ('ALIN_NA',  'ENT'): W, ('ALIN_NA',  'CRU'): W,
            ('ALIN_PI',  'L/U'): W, ('ALIN_PI',  'DEP'): W, ('ALIN_PI',  'LDG'): W,
            ('ALIN_PI',  'MAP'): W, ('ALIN_PI',  'ENT'): W, ('ALIN_PI',  'CRU'): W,
            ('DEP_NA',   'L/U'): W, ('DEP_NA',   'DEP'): W, ('DEP_NA',   'LDG'): W,
            ('DEP_NA',   'MAP'): W, ('DEP_NA',   'ENT'): W, ('DEP_NA',   'CRU'): W,
            ('ARR_NA',   'L/U'): W, ('ARR_NA',   'DEP'): W, ('ARR_NA',   'LDG'): W,
            ('ARR_NA',   'MAP'): W, ('ARR_NA',   'ENT'): W, ('ARR_NA',   'CRU'): W,
            ('ARR_PI',   'L/U'): W, ('ARR_PI',   'DEP'): W, ('ARR_PI',   'LDG'): W,
            ('ARR_PI',   'MAP'): W, ('ARR_PI',   'ENT'): W, ('ARR_PI',   'CRU'): W,
            ('AUT_CERR', 'L/U'): N, ('AUT_CERR', 'DEP'): W, ('AUT_CERR', 'LDG'): N,
            ('AUT_CERR', 'MAP'): N, ('AUT_CERR', 'ENT'): N, ('AUT_CERR', 'CRU'): N,
            ('NO_CONTACTO','L/U'):N, ('NO_CONTACTO','DEP'):N, ('NO_CONTACTO','LDG'):N,
            ('NO_CONTACTO','MAP'):N, ('NO_CONTACTO','ENT'):N, ('NO_CONTACTO','CRU'):N,
            ('CRU_NA',   'L/U'): N, ('CRU_NA',   'DEP'): N, ('CRU_NA',   'LDG'): W,
            ('CRU_NA',   'MAP'): N, ('CRU_NA',   'ENT'): N, ('CRU_NA',   'CRU'): N,
            ('ENT_NA',   'L/U'): N, ('ENT_NA',   'DEP'): N, ('ENT_NA',   'LDG'): W,
            ('ENT_NA',   'MAP'): W, ('ENT_NA',   'ENT'): N, ('ENT_NA',   'CRU'): N,
            ('ENT_PI',   'L/U'): N, ('ENT_PI',   'DEP'): N, ('ENT_PI',   'LDG'): W,
            ('ENT_PI',   'MAP'): N, ('ENT_PI',   'ENT'): N, ('ENT_PI',   'CRU'): N,
        }
        for (cmac_sub, auth_fase), sev in _misma.items():
            self.cmac_catc_table[(CAT_MISMA, cmac_sub, auth_fase)] = sev
        # PISTAS OPUESTAS (slide 59)
        _opuestas = {
            ('ALIN_NA',  'L/U'): W, ('ALIN_NA',  'DEP'): W, ('ALIN_NA',  'LDG'): N,
            ('ALIN_NA',  'MAP'): N, ('ALIN_NA',  'ENT'): W, ('ALIN_NA',  'CRU'): W,
            ('ALIN_PI',  'L/U'): W, ('ALIN_PI',  'DEP'): W, ('ALIN_PI',  'LDG'): W,
            ('ALIN_PI',  'MAP'): W, ('ALIN_PI',  'ENT'): W, ('ALIN_PI',  'CRU'): W,
            ('DEP_NA',   'L/U'): W, ('DEP_NA',   'DEP'): W, ('DEP_NA',   'LDG'): W,
            ('DEP_NA',   'MAP'): W, ('DEP_NA',   'ENT'): W, ('DEP_NA',   'CRU'): W,
            ('ARR_NA',   'L/U'): V, ('ARR_NA',   'DEP'): V, ('ARR_NA',   'LDG'): V,
            ('ARR_NA',   'MAP'): V, ('ARR_NA',   'ENT'): V, ('ARR_NA',   'CRU'): V,
            ('ARR_PI',   'L/U'): W, ('ARR_PI',   'DEP'): W, ('ARR_PI',   'LDG'): W,
            ('ARR_PI',   'MAP'): W, ('ARR_PI',   'ENT'): W, ('ARR_PI',   'CRU'): W,
            ('AUT_CERR', 'L/U'): N, ('AUT_CERR', 'DEP'): W, ('AUT_CERR', 'LDG'): N,
            ('AUT_CERR', 'MAP'): N, ('AUT_CERR', 'ENT'): N, ('AUT_CERR', 'CRU'): N,
            ('NO_CONTACTO','L/U'):N, ('NO_CONTACTO','DEP'):N, ('NO_CONTACTO','LDG'):N,
            ('NO_CONTACTO','MAP'):N, ('NO_CONTACTO','ENT'):N, ('NO_CONTACTO','CRU'):N,
            ('CRU_NA',   'L/U'): N, ('CRU_NA',   'DEP'): N, ('CRU_NA',   'LDG'): W,
            ('CRU_NA',   'MAP'): N, ('CRU_NA',   'ENT'): N, ('CRU_NA',   'CRU'): N,
            ('ENT_NA',   'L/U'): N, ('ENT_NA',   'DEP'): W, ('ENT_NA',   'LDG'): W,
            ('ENT_NA',   'MAP'): N, ('ENT_NA',   'ENT'): N, ('ENT_NA',   'CRU'): N,
            ('ENT_PI',   'L/U'): N, ('ENT_PI',   'DEP'): N, ('ENT_PI',   'LDG'): W,
            ('ENT_PI',   'MAP'): N, ('ENT_PI',   'ENT'): N, ('ENT_PI',   'CRU'): N,
        }
        for (cmac_sub, auth_fase), sev in _opuestas.items():
            self.cmac_catc_table[(CAT_OPUESTAS, cmac_sub, auth_fase)] = sev
        # PISTAS CRUZADAS (slide 61)
        _cruzadas = {
            ('ALIN_NA',  'DEP'): N, ('ALIN_NA',  'LDG'): N, ('ALIN_NA',  'MAP'): N, ('ALIN_NA',  'ENT'): W,
            ('ALIN_PI',  'DEP'): W, ('ALIN_PI',  'LDG'): W, ('ALIN_PI',  'MAP'): W, ('ALIN_PI',  'ENT'): W,
            ('DEP_NA',   'DEP'): W, ('DEP_NA',   'LDG'): W, ('DEP_NA',   'MAP'): W, ('DEP_NA',   'ENT'): W,
            ('ARR_NA',   'DEP'): W, ('ARR_NA',   'LDG'): W, ('ARR_NA',   'MAP'): W, ('ARR_NA',   'ENT'): W,
            ('ARR_PI',   'DEP'): W, ('ARR_PI',   'LDG'): W, ('ARR_PI',   'MAP'): W, ('ARR_PI',   'ENT'): W,
            ('AUT_CERR', 'DEP'): N, ('AUT_CERR', 'LDG'): N, ('AUT_CERR', 'MAP'): N, ('AUT_CERR', 'ENT'): N,
            ('NO_CONTACTO','DEP'):N, ('NO_CONTACTO','LDG'):N, ('NO_CONTACTO','MAP'):W, ('NO_CONTACTO','ENT'):N,
            ('CRU_NA',   'DEP'): N, ('CRU_NA',   'LDG'): N, ('CRU_NA',   'MAP'): N, ('CRU_NA',   'ENT'): N,
            ('ENT_NA',   'DEP'): N, ('ENT_NA',   'LDG'): N, ('ENT_NA',   'MAP'): N, ('ENT_NA',   'ENT'): N,
            ('ENT_PI',   'DEP'): N, ('ENT_PI',   'LDG'): N, ('ENT_PI',   'MAP'): N, ('ENT_PI',   'ENT'): N,
        }
        for (cmac_sub, auth_fase), sev in _cruzadas.items():
            self.cmac_catc_table[(CAT_CRUZADAS, cmac_sub, auth_fase)] = sev

        # Tracking
        self._acknowledged_alerts = set()  # {(cs, related_cs, subtype)}
        self._logged = set()

        logging.info("CATCEngine: %d combinaciones en conflict_table, %d pistas cruzadas, %d crossing_points, %d cmac_catc entries",
                     len(self.conflict_table), len(self.crossed_runways),
                     len(self.crossing_points), len(self.cmac_catc_table))

    def evaluate(self, flights, pistas_config):
        """Evalua alertas CATC para todos los vuelos."""

        self._logged = set()  # Reset duplicados cada ciclo

        # Paso 1: Preservar ACK del ciclo anterior y limpiar alertas CATC
        for f in flights:
            for a in f.active_alerts:
                if a.alert_type == ALERT_CATC and a.acknowledged:
                    self._acknowledged_alerts.add(
                        (f.callsign, a.related_cs, a.subtype))
            f.active_alerts = [a for a in f.active_alerts if a.alert_type != ALERT_CATC]

        # Paso 2: Construir mapa de autorizaciones activas por pista
        # rwy_auths = {rwy: [(callsign, catc_fase, flight_obj, rwy), ...]}
        rwy_auths = {}
        for f in flights:
            if f.pof in (LOADING, INACTIVE):
                continue
            result = self._map_phase(f)
            if result is None:
                continue
            catc_fase, rwy = result
            if not rwy or rwy in ('', 'ZZ'):
                continue
            if rwy not in rwy_auths:
                rwy_auths[rwy] = []
            rwy_auths[rwy].append((f.callsign, catc_fase, f, rwy))

        # Paso 3: MISMA_PISTA - agrupar por pista fisica (reciprocas = misma pista)
        physical_rwys = {}  # {frozenset: [(cs, fase, f, rwy), ...]}
        for rwy, auths in rwy_auths.items():
            recip = self.reciprocal.get(rwy)
            key = frozenset([rwy, recip]) if recip else frozenset([rwy])
            if key not in physical_rwys:
                physical_rwys[key] = []
            physical_rwys[key].extend(auths)

        for rwy_key, auths in physical_rwys.items():
            if len(auths) < 2:
                continue
            for i in range(len(auths)):
                for j in range(i + 1, len(auths)):
                    cs_a, fase_a, f_a, rwy_a = auths[i]
                    cs_b, fase_b, f_b, rwy_b = auths[j]
                    sev = self.conflict_table.get(
                        (CAT_MISMA, frozenset([fase_a, fase_b])))
                    if sev is not None and sev != SEVERITY_NONE:
                        self._emit_pair_alert(f_a, f_b, rwy_a, rwy_b,
                                              CAT_MISMA, fase_a, fase_b, sev)

        # Paso 4: OPUESTAS - pares en pistas reciprocas
        seen_pairs = set()
        for rwy_a in list(rwy_auths.keys()):
            rwy_b = self.reciprocal.get(rwy_a)
            if not rwy_b or rwy_b not in rwy_auths:
                continue
            pair_key = frozenset([rwy_a, rwy_b])
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            for cs_a, fase_a, f_a, _rwy_a in rwy_auths[rwy_a]:
                for cs_b, fase_b, f_b, _rwy_b in rwy_auths[rwy_b]:
                    if cs_a == cs_b:
                        continue
                    sev = self.conflict_table.get(
                        (CAT_OPUESTAS, frozenset([fase_a, fase_b])))
                    if sev is not None and sev != SEVERITY_NONE:
                        self._emit_pair_alert(f_a, f_b, rwy_a, rwy_b,
                                              CAT_OPUESTAS, fase_a, fase_b, sev)

        # Paso 5: CRUZADAS - pares en pistas cruzadas (con filtro de distancia)
        for crossed_pair in self.crossed_runways:
            rwys = list(crossed_pair)
            if len(rwys) != 2:
                continue
            rwy_x, rwy_y = rwys[0], rwys[1]
            cp = self.crossing_points.get(crossed_pair)
            dist_min = self.crossing_dist_min.get(crossed_pair, 0)
            # Buscar autorizaciones en ambas pistas (y sus reciprocas)
            auths_x = self._get_auths_for_physical_rwy(rwy_x, rwy_auths)
            auths_y = self._get_auths_for_physical_rwy(rwy_y, rwy_auths)
            for cs_a, fase_a, f_a, auth_rwy_x in auths_x:
                for cs_b, fase_b, f_b, auth_rwy_y in auths_y:
                    if cs_a == cs_b:
                        continue
                    # Filtro de distancia al punto de cruce
                    if cp and dist_min > 0:
                        pos_a = getattr(f_a, 'pos', None)
                        pos_b = getattr(f_b, 'pos', None)
                        if pos_a and len(pos_a) >= 2 and pos_b and len(pos_b) >= 2:
                            if get_distance(pos_a, cp) > dist_min or get_distance(pos_b, cp) > dist_min:
                                continue
                    sev = self.conflict_table.get(
                        (CAT_CRUZADAS, frozenset([fase_a, fase_b])))
                    if sev is not None and sev != SEVERITY_NONE:
                        self._emit_pair_alert(f_a, f_b, auth_rwy_x, auth_rwy_y,
                                              CAT_CRUZADAS, fase_a, fase_b, sev)

        # Paso 6: CONVERGENTES - stub (sin tabla de pistas convergentes)
        # Se implementara cuando se anada la hoja de datos al Excel

        # Paso 6b: CATC+INCW - moviles con INCW vs moviles con autorizacion activa
        for f in flights:
            incw_alerts = [a for a in f.active_alerts if a.alert_type == ALERT_INCW]
            if not incw_alerts:
                continue
            for incw_a in incw_alerts:
                incw_rwy = incw_a.runway
                if not incw_rwy:
                    continue
                # Buscar moviles con autorizacion activa en pista relacionada
                for auth_rwy, auths in rwy_auths.items():
                    rel = self._runway_relationship(incw_rwy, auth_rwy)
                    if rel is None:
                        continue
                    for cs_auth, fase_auth, f_auth, actual_rwy in auths:
                        if cs_auth == f.callsign:
                            continue
                        # Usar el incw occupant como CRU (esta en la pista sin autorizacion)
                        sev = self.conflict_table.get(
                            (rel, frozenset(['CRU', fase_auth])))
                        if sev is not None and sev != SEVERITY_NONE:
                            self._emit_pair_alert(f, f_auth, incw_rwy, actual_rwy,
                                                  'CINCW', 'CRU', fase_auth, sev)

        # Paso 6c: CATC+CMAC - moviles con CMAC vs moviles con autorizacion activa
        for f in flights:
            cmac_alerts = [a for a in f.active_alerts if a.alert_type == ALERT_CMAC]
            if not cmac_alerts:
                continue
            for cmac_a in cmac_alerts:
                cmac_rwy = cmac_a.runway
                cmac_sub = cmac_a.subtype  # ej: ALIN_NA, DEP_NA, ARR_PI...
                if not cmac_rwy or not cmac_sub:
                    continue
                for auth_rwy, auths in rwy_auths.items():
                    rel = self._runway_relationship(cmac_rwy, auth_rwy)
                    if rel is None:
                        continue
                    for cs_auth, fase_auth, f_auth, actual_rwy in auths:
                        if cs_auth == f.callsign:
                            continue
                        sev = self.cmac_catc_table.get((rel, cmac_sub, fase_auth))
                        if sev is not None and sev != SEVERITY_NONE:
                            self._emit_pair_alert(f, f_auth, cmac_rwy, actual_rwy,
                                                  'CCMAC', cmac_sub, fase_auth, sev)

        # Paso 8: Prediccion What-if - flag booleano (NO es una alerta, solo indicador visual)
        # Resetear flag de prediccion para todos los vuelos
        for f in flights:
            f.catc_pred = False

        for f in flights:
            pred = self._predict_next_phase(f)
            if pred is None:
                continue
            pred_fase, pred_rwy = pred
            if not pred_rwy or pred_rwy == 'ZZ':
                continue
            # Solo predecir si el movil esta en zona valida segun la fase predicha
            if not self._in_prediction_zone(f, pred_rwy, pred_fase):
                continue
            # No predecir si ya tiene CATC real
            if any(a.alert_type == ALERT_CATC for a in f.active_alerts):
                continue
            # Buscar conflicto con autorizaciones activas en pistas relacionadas
            for auth_rwy, auths in rwy_auths.items():
                rel = self._runway_relationship(pred_rwy, auth_rwy)
                if rel is None:
                    continue
                for cs_auth, fase_auth, f_auth, actual_rwy in auths:
                    if cs_auth == f.callsign:
                        continue
                    sev = self.conflict_table.get(
                        (rel, frozenset([pred_fase, fase_auth])))
                    if sev is not None and sev != SEVERITY_NONE:
                        f.catc_pred = True
                        break
                else:
                    continue
                break

        # Paso 9: Re-sort alertas por prioridad (incluye INCW + CMAC + CATC)
        active_ack_keys = set()
        for f in flights:
            if f.active_alerts:
                f.active_alerts.sort(key=lambda a: a.priority_key())
                top = f.active_alerts[0]
                f.top_alert = top
                f.max_alert_severity = max(a.severity for a in f.active_alerts)
                for a in f.active_alerts:
                    if a.alert_type == ALERT_CATC:
                        active_ack_keys.add((f.callsign, a.related_cs, a.subtype))

        # Purgar ACK huerfanos (alertas que ya no existen)
        self._acknowledged_alerts &= active_ack_keys

    def _map_phase(self, f):
        """Mapea un vuelo a (fase_catc, pista) o None si no tiene autorizacion activa."""
        osf_pof = getattr(f, 'OSF_pof', None)
        if osf_pof is None:
            return None

        if osf_pof == LININGUP:
            rwy = getattr(f, 'deprwy', '') or ''
            if not rwy or rwy == 'ZZ':
                return None
            # L/U solo cuenta como autorizacion activa si el avion esta
            # fisicamente sobre la pista (NO-LVP). Un L/U parado en el
            # hold-short (geometricamente en ALIN pero fuera de NO-LVP)
            # no es conflicto: emparejarlo con un LDG en aproximacion
            # generaba una alerta CATC falsa cada vez que el controlador
            # autorizaba L/U antes de que el avion entrara a pista.
            if not self._in_protection_zone(f, rwy):
                return None
            return ('L/U', rwy)

        if osf_pof == DEPARTING:
            rwy = getattr(f, 'deprwy', '') or ''
            if not rwy or rwy == 'ZZ':
                return None
            # Avion ya en el aire (>1500ft) no participa en CATC
            lvl = getattr(f, 'lvl', 0) or 0
            if lvl * 100 > 1500:
                return None
            return ('DEP', rwy)

        if osf_pof == LANDING:
            rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '') or ''
            return ('LDG', rwy) if rwy and rwy != 'ZZ' else None

        if osf_pof == CROSSING:
            rwy = self._detect_cru_runway(f)
            return ('CRU', rwy) if rwy else None

        if osf_pof == ENTERING:
            rwy = getattr(f, 'ent_runway', '') or ''
            return ('ENT', rwy) if rwy and rwy != 'ZZ' else None

        if osf_pof in (MAP, GA):
            rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '') or ''
            return ('MAP', rwy) if rwy and rwy != 'ZZ' else None

        return None

    def _detect_cru_runway(self, f, prediction=False):
        """Detecta en que pista esta un vuelo usando zonas BDAP.
        prediction=False: usa NO-LVP + ALIN (alertas reales)
        prediction=True:  usa LVP + ALIN (predicciones what-if, zona mas amplia)
        JOSERRA de momento no se considera la zona LVP, siempre NO-LVP"""
        if f.pos is None or len(f.pos) < 2:
            return None
        #main_zone = 'LVP' if prediction else 'NO-LVP' JOSERRA --> No consideramos LVP todavia
        main_zone = 'NO-LVP'
        for rwy in self.runways:
            for zone_type in (main_zone, 'ALIN'):
                zone_key = (rwy, zone_type)
                if zone_key in self.zones and point_within_polygon(f.pos, self.zones[zone_key]):
                    return rwy
        return None

    def _in_prediction_zone(self, f, rwy, pred_fase):
        """Comprueba si el movil esta dentro de la zona valida para predecir.

        Regla:
        - NO-LVP siempre vale (la zona protegida fisica de la pista).
        - ALIN se acepta SOLO si la fase predicha es una que requiere estar
          en NO-LVP para generar alerta real: 'DEP', 'LDG', 'CRU', 'ENT'.
          Una autorizacion a esas fases lleva (inevitablemente o por accion)
          al movil a la zona protegida, por lo que la prediccion es util.

          ALIN NO se acepta si la fase predicha es 'L/U': un avion en TOU
          autorizado a L/U puede quedarse en el hold-short (geometricamente
          en ALIN pero fuera de NO-LVP) sin generar alerta real, asi que
          predecirla ahi seria un morado sobre un estado inactivo.

        Esta regla preserva la prediccion util:
        - L/U sobre el cono ALIN (avion ya cleared) -> predice DEP -> morado.
        - INC/APP en cono ALIN -> predice LDG -> morado.
        - CRR/ENR cerca del cono -> predice CRU/ENT -> morado.
        Y suprime la falsa:
        - TOU/TIN en cono ALIN (hold-short) -> predice L/U -> sin morado.
        """
        if f.pos is None or len(f.pos) < 2:
            return False
        rwys_check = [rwy]
        recip = self.reciprocal.get(rwy)
        if recip:
            rwys_check.append(recip)

        # NO-LVP: siempre acepta
        for r in rwys_check:
            zone_key = (r, 'NO-LVP')
            if zone_key in self.zones and point_within_polygon(f.pos, self.zones[zone_key]):
                return True

        # ALIN: solo si la fase predicha implica uso real de pista
        if pred_fase in ('DEP', 'LDG', 'CRU', 'ENT'):
            for r in rwys_check:
                alin_key = (r, 'ALIN')
                if alin_key in self.zones and point_within_polygon(f.pos, self.zones[alin_key]):
                    return True

        return False

    def _in_protection_zone(self, f, rwy):
        """Devuelve True si el movil esta dentro de NO-LVP de la pista (o
        su reciproca).

        Se usa para gatear ciertas fases de _map_phase cuya presencia en
        ALIN no constituye conflicto CATC real. Caso paradigmatico: un
        avion autorizado a L/U pero todavia parado en el hold-short. Su
        posicion esta dentro del cono ALIN pero fuera de NO-LVP, y no
        debe contar como ocupante activo de pista para emparejar con LDG.
        """
        if f.pos is None or len(f.pos) < 2:
            return False
        rwys_check = [rwy]
        recip = self.reciprocal.get(rwy)
        if recip:
            rwys_check.append(recip)
        for r in rwys_check:
            zone_key = (r, 'NO-LVP')
            if zone_key in self.zones and point_within_polygon(f.pos, self.zones[zone_key]):
                return True
        return False

    def _get_auths_for_physical_rwy(self, rwy, rwy_auths):
        """Obtiene autorizaciones para una pista fisica (incluye reciproca)."""
        result = list(rwy_auths.get(rwy, []))
        recip = self.reciprocal.get(rwy)
        if recip and recip in rwy_auths:
            result.extend(rwy_auths[recip])
        return result

    def _emit_pair_alert(self, f_a, f_b, rwy_a, rwy_b, categoria, fase_a, fase_b, severity):
        """Genera alerta CATC en ambos moviles del par."""
        cs_a = f_a.callsign
        cs_b = f_b.callsign

        # Evitar duplicados (ya emitido en este ciclo)
        pair_key = frozenset([cs_a, cs_b, categoria])
        if pair_key in self._logged:
            return
        self._logged.add(pair_key)

        sev_txt = 'VIO' if severity == SEVERITY_VIO else 'WNG'
        phases = sorted([fase_a, fase_b])
        subtype = '%s_%s_%s' % (categoria, phases[0], phases[1])

        logging.debug("CATC %s: %s(%s@%s) vs %s(%s@%s) -> %s",
                      categoria, cs_a, fase_a, rwy_a, cs_b, fase_b, rwy_b, sev_txt)

        # Alerta para movil A
        desc_a = '%s %s vs %s' % (categoria[:4], rwy_a, cs_b)
        alert_a = Alert(ALERT_CATC, severity, desc_a,
                        runway=rwy_a, related_cs=cs_b, subtype=subtype)
        ack_key_a = (cs_a, cs_b, subtype)
        if ack_key_a in self._acknowledged_alerts:
            alert_a.acknowledged = True
        f_a.active_alerts.append(alert_a)

        # Alerta para movil B
        desc_b = '%s %s vs %s' % (categoria[:4], rwy_b, cs_a)
        alert_b = Alert(ALERT_CATC, severity, desc_b,
                        runway=rwy_b, related_cs=cs_a, subtype=subtype)
        ack_key_b = (cs_b, cs_a, subtype)
        if ack_key_b in self._acknowledged_alerts:
            alert_b.acknowledged = True
        f_b.active_alerts.append(alert_b)

    def _compute_crossing_point(self, rwy1, rwy2):
        """Calcula el punto de cruce de dos pistas usando centroides de zonas ALIN."""
        axis1 = self._get_runway_axis(rwy1)
        axis2 = self._get_runway_axis(rwy2)
        if axis1 is None or axis2 is None:
            return None
        try:
            return get_cross_point(axis1[0], axis1[1], axis2[0], axis2[1])
        except Exception:
            return None

    def _get_runway_axis(self, rwy):
        """Obtiene eje de pista como (punto_inicio, punto_fin) usando centroides ALIN de rwy y su reciproca."""
        c1 = self._zone_centroid(rwy, 'ALIN')
        recip = self.reciprocal.get(rwy)
        c2 = self._zone_centroid(recip, 'ALIN') if recip else None
        if c1 and c2:
            return (c1, c2)
        # Fallback: usar NO-LVP si no hay ALIN reciproca
        if c1:
            c2 = self._zone_centroid(rwy, 'NO-LVP')
            if c2 and c1 != c2:
                return (c1, c2)
        return None

    def _zone_centroid(self, rwy, zone_type):
        """Calcula centroide de una zona BDAP."""
        if not rwy:
            return None
        zone_key = (rwy, zone_type)
        poly = self.zones.get(zone_key)
        if not poly or len(poly) < 3:
            return None
        n = len(poly)
        cx = sum(p[0] for p in poly) / n
        cy = sum(p[1] for p in poly) / n
        return (cx, cy)

    def _runway_relationship(self, rwy1, rwy2):
        """Determina la relacion entre dos pistas: MISMA_PISTA, OPUESTAS, CRUZADAS o None."""
        # Misma pista
        if rwy1 == rwy2:
            return CAT_MISMA
        # Opuestas (reciprocas)
        if self.reciprocal.get(rwy1) == rwy2:
            return CAT_OPUESTAS
        # Cruzadas - incluir reciprocas de ambas pistas
        rwy1_set = set([rwy1])
        recip1 = self.reciprocal.get(rwy1)
        if recip1:
            rwy1_set.add(recip1)
        rwy2_set = set([rwy2])
        recip2 = self.reciprocal.get(rwy2)
        if recip2:
            rwy2_set.add(recip2)
        for r1 in rwy1_set:
            for r2 in rwy2_set:
                if frozenset([r1, r2]) in self.crossed_runways:
                    return CAT_CRUZADAS
        return None

    def _predict_next_phase(self, f):
        """Predice la siguiente fase CATC logica de un movil y su pista asociada.

        Returns:
            (fase_predicha, pista) o None si no aplica prediccion.
        """
        osf_pof = getattr(f, 'OSF_pof', None)
        if osf_pof is None:
            return None

        fr = getattr(f, 'fr', None)
        is_veh = fr == 'VEH'

        # Despegue: TOU -> predecir L/U
        if osf_pof == TAXIING_OUT and not is_veh:
            rwy = getattr(f, 'deprwy', '') or ''
            if rwy and rwy != 'ZZ':
                return ('L/U', rwy)

        # Despegue: L/U -> predecir DEP
        if osf_pof == LININGUP:
            rwy = getattr(f, 'deprwy', '') or ''
            if rwy and rwy != 'ZZ':
                return ('DEP', rwy)

        # Arribada: INC/APP -> predecir LDG
        if osf_pof in (INCOMING, APPROACH):
            rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '') or ''
            if rwy and rwy != 'ZZ':
                return ('LDG', rwy)

        # Vehiculo en TOU -> predecir ENT/CRU
        if is_veh and osf_pof == TAXIING_OUT:
            # Primero: runway asignada explicitamente
            rwy = getattr(f, 'ent_runway', '') or ''
            if rwy and rwy != 'ZZ':
                return ('ENT', rwy)
            rwy = getattr(f, 'cru_runway', '') or ''
            if rwy and rwy != 'ZZ':
                return ('CRU', rwy)
            # Segundo: detectar pista cercana por posicion (zonas BDAP, LVP para prediccion)
            rwy = self._detect_cru_runway(f, prediction=True)
            if rwy:
                return ('CRU', rwy)

        # Solicitud CRU (CRR) -> predecir CRU
        if osf_pof == CRUREQ:
            rwy = getattr(f, 'cru_runway', '') or ''
            if rwy and rwy != 'ZZ':
                return ('CRU', rwy)

        # Solicitud ENT (ENR) -> predecir ENT
        if osf_pof == ENTREQ:
            rwy = getattr(f, 'ent_runway', '') or ''
            if rwy and rwy != 'ZZ':
                return ('ENT', rwy)
            # ent_runway aun no asignado (se asigna en authorize_ent), usar proximidad
            rwy = self._detect_cru_runway(f, prediction=True)
            if rwy:
                return ('ENT', rwy)

        return None
