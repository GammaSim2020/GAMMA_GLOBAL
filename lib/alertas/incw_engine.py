# -*- coding: iso8859-15 -*-
"""Motor de alertas INCW (Incursion en Pista).

Evalua alertas individuales y multiples basandose en:
- Posicion del movil respecto a zonas de proteccion de pista (poligonos BDAP)
- Fase del movil (L/U, DEP-S/D, DEP-F/D, ARR-L/F, ARR-S/F, ARR-ApT, CROSS)
- Uso de pista actual (EN_USO DEP/ARR/DEP-ARR, NO_EN_USO, CERRADA)
- Matrices de severidad cargadas del Excel de escenario
"""

import logging
from MathUtil import point_within_polygon
from alertas.alert_types import reciprocal_rwy
from alertas.alert_types import (Alert, ALERT_INCW, SEVERITY_NONE, SEVERITY_WNG,
                                 SEVERITY_VIO, SEVERITY_MAP)

# Constantes de fase de vuelo del Aircraft
# NOTA: Aircraft tiene DOS campos de fase:
#   - pof: fase fisica (LOADING, GROUND, TAKEOFF, FLYING, LANDED, INACTIVE)
#   - OSF_pof: fase operativa OSF (PRE, S/U, P/B, TOU, L/U, DEP, AIR, INC, LDG, LND, TIN, FIN...)
# Las alertas INCW usan OSF_pof porque tiene las fases detalladas (L/U, DEP, LDG, TOU, TIN)

# Fases OSF_pof relevantes
LININGUP = 'L/U'
DEPARTING = 'DEP'
LANDING = 'LDG'
LANDED = 'LND'
TAXIING_OUT = 'TOU'
TAXIING_IN = 'TIN'
AIRBORNE = 'AIR'
CROSSING = 'CRU'
CRUREQ = 'CRR'

# Fases pof (fisicas) - para filtro inicial
LOADING = 'LOADING'
INACTIVE = 'INACTIVE'
TAKEOFF = 'TAKEOFF'

# Fases OSF_pof que NO nos interesan para INCW.
# Nota: LND (LANDED) NO se filtra aqui aunque "no es incursion" individual:
# necesitamos que entre a flights_in_zones (via NO-LVP) para participar en
# _evaluate_multiple - un avion aterrizado aun en pista contra otro en LDG
# debe generar MULT. El control de no-alerta individual se hace en la matriz
# BDAP (que para PHASE_ARR_APT sobre la propia pista ARR devuelve 'NO').
OSF_SKIP = frozenset(['PRE', 'S/U', 'P/B', 'P/N', 'P/S', 'P/E', 'P/W',
                       'INC', 'APP', 'HLD', 'AHL', 'MAP', 'GA',
                       'AIR', 'FIN', 'DEP', '***', '###'])

# Fases INCW validas
PHASE_LINEUP = 'L/U'
PHASE_DEP_SD = 'DEP-S/D'
PHASE_DEP_FD = 'DEP-F/D'
PHASE_ARR_LF = 'ARR-L/F'
PHASE_ARR_SF = 'ARR-S/F'
PHASE_ARR_APT = 'ARR-ApT'
PHASE_CROSS = 'CROSS'  # CRU/CRR: autorizado o solicitando autorizacion de cruce
PHASE_TAX = 'TAX'      # TOU/TIN: rodaje SIN autorizacion de cruce -> incursion
PHASE_VEH = 'VEH'

# Fases que implican uso real de pista (alineacion, despegue, aterrizaje).
# PHASE_CROSS (CRU/CRR), PHASE_TAX (rodaje), PHASE_VEH no estan aqui: son
# trafico que solo PASA por la pista y cuando la pista esta NO_EN_USO no
# constituye incursion.
RWY_USE_PHASES = frozenset([PHASE_LINEUP,
                            PHASE_DEP_SD, PHASE_DEP_FD,
                            PHASE_ARR_LF, PHASE_ARR_SF, PHASE_ARR_APT])


class INCWEngine(object):
    """Motor de evaluacion de alertas INCW."""

    def __init__(self, fir):
        self.fir = fir
        self.zones = fir.incw_zones            # {(pista, tipo): [(x_nm, y_nm), ...]}
        self.params = fir.incw_params           # {'taxi': 50, 'despegue': 35, ...}
        self.param_pista = fir.incw_param_pista  # {pista: {campo: valor}}
        self.alert_indiv = fir.incw_alert_indiv  # {(uso_pista, cabecera): {fase: sev}}
        self.mult_en_uso = fir.incw_mult_en_uso
        self.mult_no_en_uso = fir.incw_mult_no_en_uso
        self.mult_cerrada = fir.incw_mult_cerrada
        self.conf_opuesto = fir.incw_conf_opuesto

        # Parametros con defaults
        self.niv_desc_desp = self.params.get('niv_desc_desp', 1500)  # ft
        self.vel_despegue = self.params.get('despegue', 35)          # kts
        self.vel_desp_rapido = self.params.get('desp_rapido', 70)    # kts
        self.vel_taxi = self.params.get('taxi', 50)                  # kts

        # Extraer pistas unicas de las zonas
        self.runways = set()
        for (pista, tipo) in self.zones:
            self.runways.add(pista)

        # Pre-mapear pistas reciprocas
        self.reciprocal = {}
        # Calculada a partir del nombre de la pista (antes tabla fija de LEBL)
        for rwy in self.runways:
            self.reciprocal[rwy] = reciprocal_rwy(rwy)

        # Construir set de pares de pistas cruzadas desde Excel (INCWpistasCruzadas)
        self.crossed_runways = set()  # {frozenset([rwy1, rwy2])}
        for entry in getattr(fir, 'incw_pistas_cruzadas', []):
            p1 = str(entry.get('Pista1', '')).strip()
            p2 = str(entry.get('Pista2', '')).strip()
            if p1 and p2:
                self.crossed_runways.add(frozenset([p1, p2]))

        # Tracking de alertas ya logueadas para no repetir cada ciclo
        self._logged_indiv = set()   # {(callsign, runway, fase)}
        self._logged_mult = set()    # {frozenset([cs_a, cs_b, rwy])}

        # Tracking de alertas asumidas (persiste entre ciclos de evaluacion)
        self._acknowledged_alerts = set()  # {(callsign, runway, subtype)}

        logging.info("INCWEngine: %d pistas, %d zonas, params=%s",
                     len(self.runways), len(self.zones), self.params)

    def evaluate(self, flights, pistas_config):
        """Evalua alertas INCW para todos los vuelos.

        Args:
            flights: lista de Aircraft activos
            pistas_config: lista de dicts con config de pistas del controlador
        """
        # Parsear config de pistas
        rwy_use = self._parse_runway_config(pistas_config)

        # Determinar zona LVP/NO-LVP activa (por ahora siempre NO-LVP)
        # TODO: integrar con METAR/visibilidad para alternar LVP
        zone_type = 'NO-LVP'

        # Paso 1: Para cada vuelo, determinar si esta en zona de pista
        flights_in_zones = {}  # {callsign: [(pista, fase_incw), ...]}

        for f in flights:
            # Guardar estado acknowledged antes de limpiar
            for a in f.active_alerts:
                if a.alert_type == ALERT_INCW and a.acknowledged:
                    self._acknowledged_alerts.add(
                        (f.callsign, a.runway, a.subtype))
            # Limpiar alertas INCW anteriores
            f.active_alerts = [a for a in f.active_alerts if a.alert_type != ALERT_INCW]

            # Filtro por fase fisica: descartar inactivos
            if f.pof in (LOADING, INACTIVE):
                continue

            # Obtener fase OSF (la detallada: L/U, DEP, LDG, TOU, TIN, LND...)
            osf_pof = getattr(f, 'OSF_pof', None)
            if osf_pof is None or osf_pof in OSF_SKIP:
                continue

            # Filtro por altitud (ft): descarta trafico en ruta
            if f.lvl is not None and f.lvl * 100 > self.niv_desc_desp:
                continue

            # Filtro por posicion: no evaluar si no tiene posicion valida
            if f.pos is None or len(f.pos) < 2:
                continue

            # Verificar en que zona(s) de pista esta
            matched_zones = []  # [(rwy, fase)]
            for rwy in self.runways:
                # Zona principal (NO-LVP o LVP segun zone_type).
                # ALIN solo se considera para aterrizajes (LDG en long/short
                # final): asi un avion que llega por el cono se empareja en
                # _evaluate_multiple con otro que aun no ha vacado la pista,
                # incluso cuando esta fuera de la ventana predictiva t_pred.
                # Para el resto de fases (TOU/TIN/L/U/CROSS/VEH) ALIN NO
                # participa porque el cono incluye el hold-short y generaba
                # falsos positivos en cruces/entradas.
                zone_key = (rwy, zone_type)
                in_main = (zone_key in self.zones
                           and point_within_polygon(f.pos, self.zones[zone_key]))
                in_alin_ldg = False
                if not in_main and osf_pof == LANDING:
                    alin_key = (rwy, 'ALIN')
                    in_alin_ldg = (alin_key in self.zones
                                   and point_within_polygon(f.pos,
                                                            self.zones[alin_key]))
                if not in_main and not in_alin_ldg:
                    continue

                fase = self._classify_phase(f, rwy)
                if fase is None:
                    continue

                # Exencion pistas cruzadas: aviones en LANDED/DEPARTING en su pista
                # asignada no deben alertar al cruzar zonas de OTRA pista que les
                # queda en medio (ej: 02/20 cruza 24R/06L y 24L/06R en LEBL)
                if osf_pof in (LANDED, DEPARTING):
                    acft_rwy = (getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
                                or getattr(f, 'deprwy', ''))
                    if acft_rwy and rwy != acft_rwy and self.reciprocal.get(rwy) != acft_rwy:
                        if frozenset([rwy, acft_rwy]) in self.crossed_runways:
                            continue

                matched_zones.append((rwy, fase))

            # Deduplicar pistas reciprocas: si esta en 24R y 06L (misma pista fisica),
            # elegir solo la que tenga operacion asignada para evitar alertas dobles
            if len(matched_zones) > 1:
                matched_zones = self._deduplicate_reciprocal_zones(matched_zones, rwy_use)

            for rwy, fase in matched_zones:
                # Guardar para evaluacion multiple
                if f.callsign not in flights_in_zones:
                    flights_in_zones[f.callsign] = []
                flights_in_zones[f.callsign].append((rwy, fase))

                # Evaluacion individual (CRU/CRR no generan alerta individual
                # porque tienen autorizacion o estan parados esperandola,
                # pero si participan en evaluacion multiple paso 2)
                osf_pof = getattr(f, 'OSF_pof', None)
                if osf_pof not in (CROSSING, CRUREQ) and fase != PHASE_VEH:
                    self._evaluate_individual(f, rwy, fase, rwy_use)

        # Paso 1b: Deteccion predictiva de arribadas fuera de zona
        # Aviones en INC/APP/LDG/LND con dist_thr valido que NO estan en ningun poligono.
        # INC y APP estan en OSF_SKIP (no se evaluan en paso 1), pero aqui SI los
        # necesitamos para detectar aproximaciones antes de que entren en la zona.
        # LANDED excluido: aviones aterrizados en pista se detectan por poligono (paso 1),
        # y si ya salieron del poligono han vacado la pista -> no deben generar alerta.
        PREDICTIVE_PHASES = frozenset([LANDING, 'INC', 'APP'])
        for f in flights:
            if f.callsign in flights_in_zones:
                continue  # Ya esta en zona, evaluado en paso 1
            osf_pof = getattr(f, 'OSF_pof', None)
            if osf_pof not in PREDICTIVE_PHASES:
                continue
            if f.pof in (LOADING, INACTIVE):
                continue
            dist_thr = getattr(f, 'dist_thr', None)
            gs = f.ground_spd if f.ground_spd else 0.0
            if dist_thr is None or dist_thr <= 0 or gs <= 0:
                continue

            # Determinar pista de aterrizaje desde la ruta de aproximacion
            landing_rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
            if not landing_rwy or landing_rwy in ('', 'ZZ'):
                continue

            # Calcular tiempo estimado al umbral (segundos)
            time_to_thr = dist_thr / gs * 3600.0

            # Obtener T_Pred para esta pista
            params = self.param_pista.get(landing_rwy, {})
            t_pred = params.get('NoLVP_T_Pred', 60)

            if time_to_thr > t_pred:
                continue  # Demasiado lejos

            # Clasificar fase segun distancia temporal
            t_cort = params.get('NoLVP_T_Cort_Arr', 20)
            if time_to_thr <= t_cort:
                fase = PHASE_ARR_SF
            else:
                fase = PHASE_ARR_LF

            # Registrar como ocupante virtual de la pista
            flights_in_zones[f.callsign] = [(landing_rwy, fase)]

            # Evaluar alerta individual (pista cerrada, solo DEP, etc.)
            self._evaluate_individual(f, landing_rwy, fase, rwy_use)

            log_key = (f.callsign, landing_rwy, 'PRED')
            if log_key not in self._logged_indiv:
                self._logged_indiv.add(log_key)
                logging.debug("INCW PRED: %s en %s a %.1fs del umbral (T_Pred=%.0f) -> %s",
                              f.callsign, landing_rwy, time_to_thr, t_pred, fase)

        # Paso 2: Evaluacion multiple (pares en misma pista)
        self._evaluate_multiple(flights, flights_in_zones, rwy_use)

        # Paso 3: Actualizar max_alert_severity y top_alert de cada vuelo
        for f in flights:
            if f.active_alerts:
                f.active_alerts.sort(key=lambda a: a.priority_key())
                f.top_alert = f.active_alerts[0]
                f.max_alert_severity = max(a.severity for a in f.active_alerts)
            else:
                f.top_alert = None
                f.max_alert_severity = SEVERITY_NONE

        # Limpiar tracking de alertas que ya no estan activas
        active_indiv = set()
        active_mult = set()
        for f in flights:
            for a in f.active_alerts:
                if a.alert_type == ALERT_INCW:
                    if a.related_cs:
                        active_mult.add(frozenset([f.callsign, a.related_cs, a.runway]))
                    else:
                        active_indiv.add((f.callsign, a.runway, a.subtype))
        self._logged_indiv &= active_indiv
        self._logged_mult &= active_mult

        # Limpiar acknowledged de alertas que ya no existen
        active_ack_keys = set()
        for f in flights:
            for a in f.active_alerts:
                if a.alert_type == ALERT_INCW:
                    active_ack_keys.add((f.callsign, a.runway, a.subtype))
        self._acknowledged_alerts &= active_ack_keys

    def _parse_runway_config(self, pistas_config):
        """Convierte pistas_config del controlador a lookup de uso por pista.

        Returns:
            dict: {designador: {'uso': str, 'operacion': str}}
                  uso: 'EN_USO', 'NO_EN_USO', 'CERRADA'
                  operacion: 'DEP', 'ARR', 'DEP/ARR', ''
        """
        rwy_use = {}
        if not pistas_config:
            return rwy_use

        for entry in pistas_config:
            cerrada = entry.get('cerrada', 0)
            no_en_uso = entry.get('no_en_uso', 0)

            for sentido_key in ('sentido1', 'sentido2'):
                sentido = entry.get(sentido_key, {})
                desig = sentido.get('designador', '')
                oper = sentido.get('operacion', '')

                if not desig:
                    continue

                if cerrada:
                    uso = 'CERRADA'
                elif no_en_uso:
                    uso = 'NO_EN_USO'
                else:
                    uso = 'EN_USO'

                rwy_use[desig] = {'uso': uso, 'operacion': oper}

        return rwy_use

    def _classify_phase(self, acft, runway):
        """Clasifica la fase INCW de un movil en relacion a una pista.

        Usa OSF_pof (fase operativa detallada) en lugar de pof (fase fisica).
        OSF_pof tiene: L/U, DEP, LDG, LND, TOU, TIN, AIR, PRE, S/U, P/B...
        pof solo tiene: GROUND, TAKEOFF, FLYING, LANDED, LOADING, INACTIVE

        Returns:
            str or None: Fase INCW (L/U, DEP-S/D, DEP-F/D, ARR-L/F, ARR-S/F,
                         ARR-ApT, CROSS) o None si no se puede clasificar.
        """
        osf_pof = getattr(acft, 'OSF_pof', None)
        gs = acft.ground_spd if acft.ground_spd else 0.0

        # Vehiculo: lo que decide es la FASE, no has_pvh (el flag solo indica
        # que el controlador creo el plan de vehiculo, no autorizacion). Mismo
        # criterio que aeronaves:
        #   - ENT/ENR (entrada autorizada/solicitada) -> PHASE_VEH (sin
        #     alerta individual; participa en pares vs otros moviles)
        #   - CRU/CRR (cruce autorizado/solicitado)   -> PHASE_CROSS
        #     (excluido de individual en evaluate(); idem aeronaves)
        #   - TOU/TIN (rodaje sin autorizacion)       -> PHASE_TAX
        #     (alerta NO AUTH CRUCE en zona de pista en uso)
        #   - otros estados                           -> None (no participa)
        if getattr(acft, 'fr', None) == 'VEH':
            if osf_pof in ('ENT', 'ENR'):
                return PHASE_VEH
            if osf_pof in (CROSSING, CRUREQ):
                return PHASE_CROSS
            if osf_pof in (TAXIING_OUT, TAXIING_IN):
                return PHASE_TAX
            return None

        if osf_pof == LININGUP:
            return PHASE_LINEUP

        elif osf_pof == DEPARTING:
            if gs < self.vel_despegue:
                return PHASE_DEP_SD
            elif gs >= self.vel_desp_rapido:
                return PHASE_DEP_FD
            else:
                return PHASE_DEP_SD

        elif osf_pof == LANDING:
            # Distinguir L/F vs S/F usando tiempo de corte de arribada
            t_cort = 20  # segundos por defecto
            if runway in self.param_pista:
                t_cort = self.param_pista[runway].get('NoLVP_T_Cort_Arr', 20)
            dist_sf = gs * t_cort / 3600.0 if gs > 0 else 0.5
            dist_sf = max(dist_sf, 0.3)  # minimo 0.3 NM

            dist_thr = getattr(acft, 'dist_thr', None)
            if dist_thr is not None and dist_thr <= dist_sf:
                return PHASE_ARR_SF
            else:
                return PHASE_ARR_LF

        elif osf_pof == LANDED:
            return PHASE_ARR_APT

        elif osf_pof in (CROSSING, CRUREQ):
            # Autorizado a cruzar (CRU) o solicitando autorizacion (CRR):
            # el controlador conoce el cruce. Matriz BDAP lo absorbe sin alerta.
            return PHASE_CROSS

        elif osf_pof in (TAXIING_OUT, TAXIING_IN):
            # Rodando sin clearance de cruce. Si esta dentro de la zona de
            # una pista en uso es incursion (alerta NO AUTH CRUCE).
            return PHASE_TAX

        return None

    def _evaluate_individual(self, acft, runway, fase, rwy_use):
        """Evalua alerta individual INCW para un movil en una zona de pista.

        Consulta la matriz incw_alert_indiv con (uso_pista, cabecera) x fase.
        """
        rwy_info = rwy_use.get(runway, {})
        uso = rwy_info.get('uso', 'NO_EN_USO')
        oper = rwy_info.get('operacion', '')

        # Pista NO EN USO: solo alertar si la fase representa uso real de pista
        # (L/U, DEP, ARR). Aviones rodando (PHASE_TAX), cruzando autorizados
        # (PHASE_CROSS) y vehiculos (PHASE_VEH) que pasan por una pista no
        # operativa no son incursion y no deben generar alerta.
        if uso == 'NO_EN_USO' and fase not in RWY_USE_PHASES:
            return

        # PHASE_TAX (rodaje sin autorizacion de cruce): si la pista esta EN_USO
        # o CERRADA, el avion no deberia estar dentro de la zona. La matriz BDAP
        # solo tiene entradas para PHASE_CROSS (autorizado) por lo que aqui se
        # fuerza la severidad sin pasar por la matriz.
        if fase == PHASE_TAX:
            if uso == 'EN_USO':
                severity = SEVERITY_WNG
                desc = 'RWY %s NO AUTH CRUCE' % runway
            elif uso == 'CERRADA':
                severity = SEVERITY_VIO
                desc = 'RWY %s CRUCE PISTA CERRADA' % runway
            else:
                return
            alert = Alert(ALERT_INCW, severity, desc,
                          runway=runway, subtype=fase)
            ack_key = (acft.callsign, runway, fase)
            if ack_key in self._acknowledged_alerts:
                alert.acknowledged = True
            acft.active_alerts.append(alert)
            log_key = (acft.callsign, runway, fase)
            if log_key not in self._logged_indiv:
                self._logged_indiv.add(log_key)
                sev_txt = 'VIO' if severity == SEVERITY_VIO else 'WNG'
                logging.debug("INCW ALERTA: %s %s - %s (rodaje sin cruce auth)",
                              acft.callsign, sev_txt, desc)
            return

        # Determinar tipo de cabecera segun operacion de la pista
        if oper == 'DEP':
            cabecera = 'Cab_DEP'
        elif oper == 'ARR':
            cabecera = 'Cab_ARR'
        elif oper == 'DEP/ARR':
            cabecera = 'Cab_DEP/ARR'
        elif oper == '' and runway in self.reciprocal:
            # Sin operacion: consultar la operacion del reciproco
            recip = self.reciprocal[runway]
            recip_oper = rwy_use.get(recip, {}).get('operacion', '')
            if recip_oper == 'ARR':
                cabecera = 'Cab_ARR'   # Reciproca es ARR -> DEP aqui es VIO
            elif recip_oper == 'DEP':
                cabecera = 'Cab_DEP'   # Reciproca es DEP
            elif recip_oper == 'DEP/ARR':
                cabecera = 'Cab_DEP/ARR'
            else:
                cabecera = 'Cab_DEP'
        else:
            cabecera = 'Cab_DEP'

        # Buscar en matriz de severidad
        # La matriz puede usar diferentes formatos de clave segun el BDAP
        severity_str = None
        for key_uso, key_cab in [(uso, cabecera)]:
            entry = self.alert_indiv.get((key_uso, key_cab))
            if entry:
                severity_str = entry.get(fase)
                break

        # Intentar variantes de clave si no se encontro
        if severity_str is None:
            for key in self.alert_indiv:
                k_uso, k_cab = key
                if self._match_uso(k_uso, uso) and self._match_cabecera(k_cab, cabecera):
                    severity_str = self.alert_indiv[key].get(fase)
                    if severity_str is not None:
                        break

        if severity_str is None or severity_str == 'NO':
            return

        # Resolver W/V por distancia temporal al umbral
        if severity_str == 'W/V':
            severity = self._resolve_wv_by_distance(acft, runway)
        else:
            severity = SEVERITY_MAP.get(severity_str, SEVERITY_NONE)
        if severity == SEVERITY_NONE:
            return

        sev_txt = 'VIO' if severity == SEVERITY_VIO else 'WNG'
        desc = 'RWY %s %s' % (runway, fase)
        alert = Alert(ALERT_INCW, severity, desc, runway=runway, subtype=fase)
        # Restaurar estado acknowledged si existia
        ack_key = (acft.callsign, runway, fase)
        if ack_key in self._acknowledged_alerts:
            alert.acknowledged = True
        acft.active_alerts.append(alert)
        log_key = (acft.callsign, runway, fase)
        if log_key not in self._logged_indiv:
            self._logged_indiv.add(log_key)
            logging.debug("INCW ALERTA: %s %s - %s (uso=%s, cab=%s, fase=%s)",
                          acft.callsign, sev_txt, desc, uso, cabecera, fase)

    def _evaluate_multiple(self, flights, flights_in_zones, rwy_use):
        """Evalua alertas multiples INCW (dos moviles en misma pista)."""
        # Construir indice: {pista: [(callsign, fase), ...]}
        # Solo usar la pista "principal" de cada movil para evitar duplicados
        # por pistas reciprocas (06L/24R son la misma pista fisica)
        rwy_occupants = {}
        cs_to_flight = {}
        for f in flights:
            cs_to_flight[f.callsign] = f

        # Para cada movil, elegir solo UNA pista (la que tenga operacion asignada,
        # o la primera si ninguna tiene). Evita evaluar el mismo par 2 veces
        # en pistas reciprocas.
        for cs, zone_list in flights_in_zones.items():
            # Preferir la pista con operacion asignada (DEP/ARR/DEP-ARR)
            best_rwy = None
            best_fase = None
            for (rwy, fase) in zone_list:
                rwy_info = rwy_use.get(rwy, {})
                oper = rwy_info.get('operacion', '')
                if oper:  # tiene operacion asignada
                    best_rwy = rwy
                    best_fase = fase
                    break
            if best_rwy is None:
                # Ninguna tiene operacion, usar la primera
                best_rwy, best_fase = zone_list[0]

            if best_rwy not in rwy_occupants:
                rwy_occupants[best_rwy] = []
            rwy_occupants[best_rwy].append((cs, best_fase))

        # Para cada pista con 2+ ocupantes
        for rwy, occupants in rwy_occupants.items():
            if len(occupants) < 2:
                continue

            rwy_info = rwy_use.get(rwy, {})
            uso = rwy_info.get('uso', 'NO_EN_USO')

            # Seleccionar tabla segun uso
            if uso == 'CERRADA':
                tabla = self.mult_cerrada
            elif uso == 'NO_EN_USO':
                tabla = self.mult_no_en_uso
            else:
                tabla = self.mult_en_uso

            oper = rwy_info.get('operacion', '')

            # Evaluar cada par
            for i in range(len(occupants)):
                for j in range(i + 1, len(occupants)):
                    cs_a, fase_a = occupants[i]
                    cs_b, fase_b = occupants[j]

                    # Pista NO EN USO: suprimir el par si CUALQUIERA de los dos
                    # esta solo de paso (CROSS/VEH/rodaje). Solo se mantienen
                    # los pares en los que AMBOS estan haciendo uso real de la
                    # pista (L/U, DEP, ARR).
                    if uso == 'NO_EN_USO' and (fase_a not in RWY_USE_PHASES
                                               or fase_b not in RWY_USE_PHASES):
                        continue

                    # Buscar severidad en la tabla
                    severity_str = self._lookup_multiple(tabla, uso, oper, fase_a, fase_b)

                    # Fallback para fase TAX (rodaje sin auth de cruce; no en
                    # matrices Excel). Mismo patron que el fallback VEH de abajo.
                    if severity_str is None and (fase_a == PHASE_TAX or fase_b == PHASE_TAX):
                        other = fase_b if fase_a == PHASE_TAX else fase_a
                        if other in (PHASE_DEP_SD, PHASE_DEP_FD, PHASE_ARR_LF, PHASE_ARR_SF, PHASE_ARR_APT):
                            severity_str = 'V'
                        elif other in (PHASE_LINEUP, PHASE_TAX, PHASE_CROSS, PHASE_VEH):
                            severity_str = 'W'
                        else:
                            severity_str = 'NO'

                    # Fallback para fase VEH (no presente en matrices Excel)
                    if severity_str is None and (fase_a == PHASE_VEH or fase_b == PHASE_VEH):
                        other = fase_b if fase_a == PHASE_VEH else fase_a
                        if other in (PHASE_DEP_SD, PHASE_DEP_FD, PHASE_ARR_LF, PHASE_ARR_SF, PHASE_ARR_APT):
                            severity_str = 'V'
                        elif other == PHASE_LINEUP:
                            severity_str = 'W'
                        else:
                            severity_str = 'NO'

                    if severity_str is None or severity_str == 'NO':
                        continue

                    # Resolver W/V por distancia: usar el movil que tenga dist_thr
                    if severity_str == 'W/V':
                        f_a = cs_to_flight.get(cs_a)
                        f_b = cs_to_flight.get(cs_b)
                        # Intentar con ambos, el que tenga dist_thr valido
                        sev_a = self._resolve_wv_by_distance(f_a, rwy) if f_a else SEVERITY_WNG
                        sev_b = self._resolve_wv_by_distance(f_b, rwy) if f_b else SEVERITY_WNG
                        severity = max(sev_a, sev_b)  # Usar la mas severa
                    else:
                        severity = SEVERITY_MAP.get(severity_str, SEVERITY_NONE)
                    if severity == SEVERITY_NONE:
                        continue

                    sev_txt = 'VIO' if severity == SEVERITY_VIO else 'WNG'
                    mult_key = frozenset([cs_a, cs_b, rwy])
                    if mult_key not in self._logged_mult:
                        self._logged_mult.add(mult_key)
                        logging.debug("INCW ALERTA MULT: %s(%s) vs %s(%s) rwy=%s -> %s",
                                      cs_a, fase_a, cs_b, fase_b, rwy, sev_txt)

                    # Generar alerta para ambos moviles
                    desc_a = 'RWY %s vs %s' % (rwy, cs_b)
                    desc_b = 'RWY %s vs %s' % (rwy, cs_a)
                    f_a = cs_to_flight.get(cs_a)
                    f_b = cs_to_flight.get(cs_b)

                    if f_a:
                        sub_a = 'MULT_%s' % fase_b
                        alert_a = Alert(ALERT_INCW, severity, desc_a,
                                        runway=rwy, related_cs=cs_b,
                                        subtype=sub_a)
                        ack_key_a = (cs_a, rwy, sub_a)
                        if ack_key_a in self._acknowledged_alerts:
                            alert_a.acknowledged = True
                        f_a.active_alerts.append(alert_a)
                    if f_b:
                        sub_b = 'MULT_%s' % fase_a
                        alert_b = Alert(ALERT_INCW, severity, desc_b,
                                        runway=rwy, related_cs=cs_a,
                                        subtype=sub_b)
                        ack_key_b = (cs_b, rwy, sub_b)
                        if ack_key_b in self._acknowledged_alerts:
                            alert_b.acknowledged = True
                        f_b.active_alerts.append(alert_b)

    def _lookup_multiple(self, tabla, uso, oper, fase_a, fase_b):
        """Busca severidad en tabla multiple. Intenta ambas direcciones.

        Las claves del Excel BDAP tienen formato descriptivo:
          'EN USO para DEP', 'EN USO para ARR', 'EN USO Mixto (para ARR y DEP)',
          'NO EN USO (ambas cabeceras)', 'CERRADA (ambas cabeceras)'
        Se necesita matching flexible contra uso+operacion de runtime.
        """
        # Buscar todas las entradas de la tabla que coincidan con uso+oper
        matching_entries = []
        for key in tabla:
            k_uso, k_fase = key
            if self._match_uso_mult(k_uso, uso, oper):
                matching_entries.append((k_fase, tabla[key]))

        if not matching_entries:
            return None

        # Intento directo: fase_a como fila, fase_b como columna
        for k_fase, severidades in matching_entries:
            if k_fase == fase_a:
                sev = severidades.get(fase_b)
                if sev is not None:
                    return sev

        # Intento invertido (tabla es simetrica): fase_b como fila, fase_a como columna
        for k_fase, severidades in matching_entries:
            if k_fase == fase_b:
                sev = severidades.get(fase_a)
                if sev is not None and sev != '-':
                    return sev

        return None

    def _deduplicate_reciprocal_zones(self, matched_zones, rwy_use):
        """Elimina pistas reciprocas duplicadas (ej: 06L/24R son la misma pista fisica).

        Cuando un avion esta en una zona compartida por pistas reciprocas,
        elige solo la pista con operacion asignada. Si ambas o ninguna
        tiene operacion, elige la primera. Pistas de pares diferentes
        se mantienen todas (ej: puede estar en 24R y 02 a la vez - cruce real).
        """
        # Agrupar por par reciproco
        by_pair = {}  # {frozenset: [(rwy, fase), ...]}
        standalone = []

        for rwy, fase in matched_zones:
            recip = self.reciprocal.get(rwy)
            if recip:
                pair_key = frozenset([rwy, recip])
            else:
                pair_key = frozenset([rwy])

            if pair_key not in by_pair:
                by_pair[pair_key] = []
            by_pair[pair_key].append((rwy, fase))

        result = []
        for pair_key, entries in by_pair.items():
            if len(entries) == 1:
                result.append(entries[0])
            else:
                # Multiples pistas del mismo par: elegir la que tenga operacion
                best = None
                for rwy, fase in entries:
                    oper = rwy_use.get(rwy, {}).get('operacion', '')
                    if oper:
                        best = (rwy, fase)
                        break
                if best is None:
                    best = entries[0]
                result.append(best)

        return result

    def _resolve_wv_by_distance(self, acft, runway):
        """Resuelve severidad 'W/V por dist' usando tiempo al umbral.

        Si el movil tiene dist_thr valido, calcula tiempo al umbral y compara
        con T_Viol de la pista: <= T_Viol -> VIO, > T_Viol -> WNG.
        Si no tiene dist_thr, devuelve WNG como default conservador.
        """
        dist_thr = getattr(acft, 'dist_thr', None)
        gs = acft.ground_spd if acft.ground_spd else 0.0
        if dist_thr is not None and dist_thr > 0 and gs > 0:
            time_to_thr = dist_thr / gs * 3600.0
            params = self.param_pista.get(runway, {})
            t_viol = params.get('NoLVP_T_Viol', 5)
            if time_to_thr <= t_viol:
                return SEVERITY_VIO
        return SEVERITY_WNG

    @staticmethod
    def _match_uso_mult(bdap_uso, runtime_uso, runtime_oper):
        """Compara uso de pista del BDAP con uso+operacion en runtime (tablas multiples).

        Las claves BDAP de tablas multiples codifican la operacion en el propio uso:
          'EN USO para DEP'                -> uso=EN_USO, oper=DEP
          'EN USO para ARR'                -> uso=EN_USO, oper=ARR
          'EN USO Mixto (para ARR y DEP)'  -> uso=EN_USO, oper=DEP/ARR
          'NO EN USO (ambas cabeceras)'    -> uso=NO_EN_USO (cualquier oper)
          'CERRADA (ambas cabeceras)'      -> uso=CERRADA (cualquier oper)
        """
        bdap = bdap_uso.upper()

        if runtime_uso == 'CERRADA':
            return 'CERRAD' in bdap
        if runtime_uso == 'NO_EN_USO':
            return 'NO' in bdap and 'USO' in bdap

        # runtime_uso == 'EN_USO': discriminar por operacion
        if 'NO' in bdap and 'USO' in bdap:
            return False  # NO EN USO no matchea con EN_USO
        if 'CERRAD' in bdap:
            return False

        # Es algun tipo de EN USO - discriminar por operacion
        if runtime_oper == 'DEP/ARR' or runtime_oper == 'DEP-ARR':
            return 'MIXTO' in bdap or ('ARR' in bdap and 'DEP' in bdap)
        if runtime_oper == 'DEP':
            # Match "EN USO para DEP" pero NO "EN USO Mixto" ni "EN USO para ARR"
            if 'MIXTO' in bdap:
                return False
            return 'DEP' in bdap and 'ARR' not in bdap
        if runtime_oper == 'ARR':
            if 'MIXTO' in bdap:
                return False
            return 'ARR' in bdap and 'DEP' not in bdap

        # Sin operacion especifica: matchear cualquier EN USO
        return 'EN' in bdap and 'USO' in bdap

    @staticmethod
    def _match_uso(bdap_uso, runtime_uso):
        """Compara uso de pista del BDAP con el uso en runtime (flexible).

        Para tablas individuales donde la cabecera discrimina la operacion.
        """
        bdap = bdap_uso.upper().replace(' ', '_')
        rt = runtime_uso.upper().replace(' ', '_')
        if bdap == rt:
            return True
        # Variantes comunes
        if 'EN_USO' in bdap and rt == 'EN_USO':
            return True
        if 'NO_EN_USO' in bdap and rt == 'NO_EN_USO':
            return True
        if 'NO' in bdap and 'USO' in bdap and rt == 'NO_EN_USO':
            return True
        if 'CERRAD' in bdap and rt == 'CERRADA':
            return True
        return False

    @staticmethod
    def _match_cabecera(bdap_cab, runtime_cab):
        """Compara cabecera del BDAP con la de runtime (flexible)."""
        bdap = bdap_cab.upper().replace(' ', '_')
        rt = runtime_cab.upper().replace(' ', '_')
        if bdap == rt:
            return True
        if 'DEP/ARR' in bdap and rt == 'CAB_DEP/ARR':
            return True
        if 'DEP' in bdap and 'ARR' not in bdap and rt == 'CAB_DEP':
            return True
        if 'ARR' in bdap and 'DEP' not in bdap and rt == 'CAB_ARR':
            return True
        return False
