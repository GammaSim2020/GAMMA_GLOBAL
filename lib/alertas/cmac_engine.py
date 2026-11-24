# -*- coding: iso8859-15 -*-
"""Motor de alertas CMAC (Conformance Monitoring Alerts for Controllers).

Detecta moviles que no cumplen con sus autorizaciones:
- Alineacion/despegue/aterrizaje sin autorizacion
- Operacion en pista incorrecta
- Autorizacion en pista cerrada
- Cruce/entrada sin autorizacion
- Falta de contacto con torre

Reutiliza las zonas de proteccion INCW (fir.incw_zones).
Severidades y subtipos se cargan del Excel (CMACsubtipos).
"""

import logging
from MathUtil import point_within_polygon
from alertas.alert_types import reciprocal_rwy
from alertas.alert_types import (Alert, ALERT_CMAC, SEVERITY_NONE, SEVERITY_WNG,
                                 SEVERITY_VIO, SEVERITY_MAP)

# Fases OSF_pof relevantes
LININGUP = 'L/U'
DEPARTING = 'DEP'
LANDING = 'LDG'
LANDED = 'LND'
TAXIING_OUT = 'TOU'
TAXIING_IN = 'TIN'
CROSSING = 'CRU'
CRUREQ = 'CRR'
ENTERING = 'ENT'
ENTREQ = 'ENR'
INCOMING = 'INC'
APPROACH = 'APP'

# Fases pof (fisicas) - para filtro inicial
LOADING = 'LOADING'
INACTIVE = 'INACTIVE'

# Fases OSF_pof que NO generan CMAC (excepto NO_CONTACTO que tiene bucle propio)
CMAC_SKIP = frozenset(['PRE', 'S/U', 'P/B', 'P/N', 'P/S', 'P/E', 'P/W',
                        'HLD', 'AHL', 'MAP', 'GA',
                        'AIR', 'FIN', '***', '###'])


class CMACEngine(object):
    """Motor de evaluacion de alertas CMAC."""

    def __init__(self, fir):
        self.fir = fir
        self.zones = fir.incw_zones                # Reutiliza zonas INCW
        self.params = fir.cmac_params
        self.subtypes = fir.cmac_subtypes
        self.pistas_cerradas = fir.cmac_pistas_cerradas
        self.param_pista = fir.incw_param_pista    # Para NO_CONTACTO (T_Pred)

        # Umbrales (diferentes de INCW)
        self.vel_despegue = self.params.get('despegue', 40)
        self.vel_desp_rapido = self.params.get('desp_rapido', 70)
        self.vel_taxi = self.params.get('taxi', 50)
        self.niv_desc_desp = self.params.get('niv_desc_desp', 1500)
        self.tiempo_min_contacto = self.params.get('tiempo_min_contacto', 95)

        # Extraer pistas unicas de las zonas
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
        for entry in getattr(fir, 'incw_pistas_cruzadas', []):
            p1 = str(entry.get('Pista1', '')).strip()
            p2 = str(entry.get('Pista2', '')).strip()
            if p1 and p2:
                self.crossed_runways.add(frozenset([p1, p2]))

        # Tracking
        self._acknowledged_alerts = set()  # {(cs, rwy, subtype_code)}
        self._logged = set()               # {(cs, rwy, subtype_code)}

        logging.info("CMACEngine: %d subtipos, params=%s", len(self.subtypes), self.params)

    def evaluate(self, flights, pistas_config):
        """Evalua alertas CMAC para todos los vuelos."""

        # Parsear config de pistas
        rwy_use = self._parse_runway_config(pistas_config)

        # Zona activa (por ahora siempre NO-LVP)
        zone_type = 'NO-LVP'

        # Paso 1: Preservar acknowledged CMAC del ciclo anterior
        for f in flights:
            for a in f.active_alerts:
                if a.alert_type == ALERT_CMAC and a.acknowledged:
                    self._acknowledged_alerts.add(
                        (f.callsign, a.runway, a.subtype))
            # Limpiar alertas CMAC anteriores (mantener INCW intactas)
            f.active_alerts = [a for a in f.active_alerts if a.alert_type != ALERT_CMAC]

        # Paso 2: Evaluar cada vuelo contra zonas de pista
        evaluated_in_zone = set()  # Callsigns evaluados dentro de zona

        for f in flights:
            # Filtros basicos
            if f.pof in (LOADING, INACTIVE):
                continue
            if f.pos is None or len(f.pos) < 2:
                continue
            if f.lvl is not None and f.lvl * 100 > self.niv_desc_desp:
                continue
            if getattr(f, 'cmac_inhibited', False):
                continue

            osf_pof = getattr(f, 'OSF_pof', None)
            if osf_pof is None or osf_pof in CMAC_SKIP:
                continue

            is_veh = getattr(f, 'fr', None) == 'VEH'
            gs = f.ground_spd if f.ground_spd else 0.0

            # Verificar en que zona(s) de pista esta. Solo zona principal
            # (NO-LVP o LVP). ALIN ya no cuenta: el cono incluye el hold-short
            # y generaba falsos positivos en cruces/entradas (consistente con
            # el cambio paralelo en INCW).
            matched_zones = []
            for rwy in self.runways:
                zone_key = (rwy, zone_type)
                if zone_key in self.zones and point_within_polygon(f.pos, self.zones[zone_key]):
                    matched_zones.append(rwy)

            # Deduplicar reciprocas
            if len(matched_zones) > 1:
                matched_zones = self._deduplicate_reciprocal(matched_zones, rwy_use)

            if matched_zones:
                evaluated_in_zone.add(f.callsign)

            # Evaluar subtipos por zona
            for rwy in matched_zones:
                # Exencion pistas cruzadas: LANDED/DEPARTING en su pista asignada
                # no deben alertar al cruzar zonas de otra pista que les queda
                # en medio (ej: 02/20 cruza 24R/06L en LEBL)
                if osf_pof in (LANDED, DEPARTING):
                    acft_rwy = (getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
                                or getattr(f, 'deprwy', ''))
                    if acft_rwy and rwy != acft_rwy and self.reciprocal.get(rwy) != acft_rwy:
                        if frozenset([rwy, acft_rwy]) in self.crossed_runways:
                            continue

                rwy_info = rwy_use.get(rwy, {})
                uso = rwy_info.get('uso', 'NO_EN_USO')

                if is_veh:
                    self._check_ent_na(f, rwy, osf_pof)
                    self._check_ent_pi(f, rwy, osf_pof)
                    self._check_cru_na(f, rwy, osf_pof, gs, uso)
                    self._check_aut_cerrada(f, rwy, osf_pof, uso, is_veh)
                else:
                    self._check_alin_na(f, rwy, osf_pof, gs, rwy_use)
                    self._check_dep_na(f, rwy, osf_pof, gs)
                    self._check_alin_pi(f, rwy, osf_pof)
                    self._check_arr_na(f, rwy, osf_pof)
                    self._check_arr_pi(f, rwy, osf_pof, rwy_use)
                    self._check_cru_na(f, rwy, osf_pof, gs, uso)
                    self._check_aut_cerrada(f, rwy, osf_pof, uso, is_veh)

        # Paso 2b: Deteccion predictiva de arribadas fuera de zona
        # Aviones en LDG/INC/APP con dist_thr valido que NO estan en ningun poligono.
        # Mismo patron que INCW Paso 1b: si time_to_thr <= T_Pred, evaluar como si
        # estuvieran en la zona de su pista de aterrizaje.
        for f in flights:
            if f.callsign in evaluated_in_zone:
                continue  # Ya evaluado dentro de zona
            if f.pof in (LOADING, INACTIVE):
                continue
            if getattr(f, 'fr', None) == 'VEH':
                continue
            if getattr(f, 'cmac_inhibited', False):
                continue

            osf_pof = getattr(f, 'OSF_pof', None)
            if osf_pof not in (LANDING, LANDED, INCOMING, APPROACH):
                continue

            dist_thr = getattr(f, 'dist_thr', None)
            gs = f.ground_spd if f.ground_spd else 0.0
            if dist_thr is None or dist_thr <= 0 or gs <= 0:
                continue

            landing_rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
            if not landing_rwy or landing_rwy in ('', 'ZZ'):
                continue

            # Calcular tiempo estimado al umbral (segundos)
            time_to_thr = dist_thr / gs * 3600.0

            # Obtener T_Pred para esta pista (mismo parametro que INCW)
            params = self.param_pista.get(landing_rwy, {})
            t_pred = params.get('NoLVP_T_Pred', 60)

            if time_to_thr > t_pred:
                continue  # Demasiado lejos

            # Evaluar alertas CMAC como ocupante virtual de la pista
            rwy_info = rwy_use.get(landing_rwy, {})
            uso = rwy_info.get('uso', 'NO_EN_USO')

            self._check_arr_na_predictive(f, landing_rwy)
            self._check_arr_pi_predictive(f, landing_rwy)
            self._check_aut_cerrada(f, landing_rwy, osf_pof, uso, False)

            log_key = (f.callsign, landing_rwy, 'PRED')
            if log_key not in self._logged:
                self._logged.add(log_key)
                logging.debug("CMAC PRED: %s en %s a %.1fs del umbral (T_Pred=%.0f)",
                              f.callsign, landing_rwy, time_to_thr, t_pred)

        # Paso 2c: NO_CONTACTO (bucle separado, no requiere zona)
        for f in flights:
            if f.pof in (LOADING, INACTIVE):
                continue
            if getattr(f, 'fr', None) == 'VEH':
                continue
            if getattr(f, 'cmac_inhibited', False):
                continue
            self._check_no_contacto(f)

        # Paso 3: Re-sort active_alerts (incluye INCW + CMAC), actualizar top_alert
        for f in flights:
            if f.active_alerts:
                f.active_alerts.sort(key=lambda a: a.priority_key())
                f.top_alert = f.active_alerts[0]
                f.max_alert_severity = max(a.severity for a in f.active_alerts)
            else:
                f.top_alert = None
                f.max_alert_severity = SEVERITY_NONE

        # Limpiar tracking stale
        active_keys = set()
        for f in flights:
            for a in f.active_alerts:
                if a.alert_type == ALERT_CMAC:
                    active_keys.add((f.callsign, a.runway, a.subtype))
        self._logged &= active_keys
        self._acknowledged_alerts &= active_keys

    # ---------------------------------------------------------------
    # Checks individuales por subtipo
    # ---------------------------------------------------------------

    def _check_alin_na(self, f, rwy, osf_pof, gs, rwy_use):
        """ALIN_NA: AVO en zona pista con fase taxi, lento -> lineup sin auth.

        Solo para TAX: un avion taxeando que entra en zona ALIN sin autorizacion L/U.
        Si el controlador ya dio AUTORIZACION L/U (OSF_pof='L/U'), no es CMAC sino
        INCW quien evalua la seguridad (via matriz Excel con cabecera correspondiente).
        Bug 1: Para TAX, solo dispara si f.deprwy coincide con esta pista.
        """
        if osf_pof not in (TAXIING_OUT, TAXIING_IN):
            return
        # Bug 1: Solo alertar si el avion pretende despegar de ESTA pista
        deprwy = getattr(f, 'deprwy', '')
        if deprwy and deprwy != rwy and self.reciprocal.get(rwy) != deprwy:
            return  # No se esta alineando, solo cruza
        # Discriminar vs CRU_NA por velocidad: ALIN_NA si lento (5 < gs < vel_taxi)
        if gs < 5 or gs >= self.vel_taxi:
            return
        self._emit_alert(f, rwy, 'ALIN_NA')

    def _check_dep_na(self, f, rwy, osf_pof, gs):
        """DEP_NA: AVO acelerando en pista sin autorizacion de despegue."""
        if gs < self.vel_despegue:
            return
        # Solo si esta en fase que implica estar en pista
        if osf_pof not in (TAXIING_OUT, TAXIING_IN, LININGUP):
            # Si ya esta en DEP, verificar depart_auth
            if osf_pof == DEPARTING:
                if getattr(f, 'depart_auth', True):
                    return  # Tiene autorizacion, ok
            else:
                return
        self._emit_alert(f, rwy, 'DEP_NA')

    def _check_alin_pi(self, f, rwy, osf_pof):
        """ALIN_PI: AVO con L/U o DEP en pista incorrecta (no coincide con deprwy)."""
        if osf_pof not in (LININGUP, DEPARTING):
            return
        deprwy = getattr(f, 'deprwy', 'ZZ')
        if deprwy in ('', 'ZZ'):
            return  # No tiene pista asignada, no podemos comparar
        # Comparar zona actual con pista asignada (incluyendo reciproca)
        if rwy == deprwy:
            return
        recip = self.reciprocal.get(rwy)
        if recip and recip == deprwy:
            return
        self._emit_alert(f, rwy, 'ALIN_PI')

    def _check_arr_na(self, f, rwy, osf_pof):
        """ARR_NA: AVO aterrizando sin autorizacion de aterrizaje.

        OSF_pof == LDG significa que el controlador DIO autorizacion (click AUTORIZACION LDG).
        lnd_auth se activa en set_osf_pof(LDG) y persiste cuando pasa a LND.
        ARR_NA solo se dispara si el avion llego a LND sin que el controlador autorizara LDG.
        """
        if osf_pof == LANDING:
            return  # OSF_pof=LDG ES la autorizacion del controlador
        if osf_pof != LANDED:
            return  # Solo LND sin haber pasado por LDG
        if getattr(f, 'lnd_auth', False):
            return  # Paso por LDG antes (flag persistente)
        self._emit_alert(f, rwy, 'ARR_NA')

    def _check_arr_pi(self, f, rwy, osf_pof, rwy_use):
        """ARR_PI: AVO aterrizando en pista incorrecta.

        Bug 7: Tambien dispara si aterriza en pista configurada solo como DEP.
        """
        if osf_pof not in (LANDING, LANDED):
            return
        lrwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
        if not lrwy or lrwy in ('', 'ZZ'):
            return
        if rwy == lrwy:
            # Bug 7: pista correcta pero configurada solo como DEP
            rwy_info = rwy_use.get(rwy, {})
            oper = rwy_info.get('operacion', '')
            if oper == 'DEP':
                self._emit_alert(f, rwy, 'ARR_PI')
            return
        recip = self.reciprocal.get(rwy)
        if recip and recip == lrwy:
            # Bug 7: pista correcta (reciproca) pero configurada solo como DEP
            rwy_info = rwy_use.get(rwy, {})
            oper = rwy_info.get('operacion', '')
            if oper == 'DEP':
                self._emit_alert(f, rwy, 'ARR_PI')
            return
        self._emit_alert(f, rwy, 'ARR_PI')

    def _check_arr_na_predictive(self, f, landing_rwy):
        """ARR_NA predictivo: avion acercandose sin autorizacion LDG.

        Para aviones en INC/APP/LDG/LND fuera de zona pero dentro de T_Pred.
        Si OSF_pof es LDG, el controlador ya autorizo -> sin alerta.
        Si es INC o APP, no tiene autorizacion aun -> alerta.
        Si es LND y lnd_auth=True, paso por LDG -> sin alerta.
        """
        osf_pof = getattr(f, 'OSF_pof', None)
        if osf_pof == LANDING:
            return  # OSF_pof=LDG es la autorizacion
        if osf_pof == LANDED and getattr(f, 'lnd_auth', False):
            return  # Tuvo autorizacion LDG
        # INC, APP, o LND sin auth -> alerta
        self._emit_alert(f, landing_rwy, 'ARR_NA')

    def _check_arr_pi_predictive(self, f, landing_rwy):
        """ARR_PI predictivo: avion acercandose a pista diferente de la asignada.

        Solo aplica si el avion tiene autorizacion (LDG o lnd_auth) pero la pista
        a la que se acerca no coincide con su lrwy/desrwy.
        """
        osf_pof = getattr(f, 'OSF_pof', None)
        # ARR_PI solo tiene sentido si tiene autorizacion en la pista equivocada
        if osf_pof != LANDING and not getattr(f, 'lnd_auth', False):
            return  # Sin auth, ya se evaluo como ARR_NA
        lrwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
        if not lrwy or lrwy in ('', 'ZZ'):
            return
        if landing_rwy == lrwy:
            return
        recip = self.reciprocal.get(landing_rwy)
        if recip and recip == lrwy:
            return
        self._emit_alert(f, landing_rwy, 'ARR_PI')

    def _check_cru_na(self, f, rwy, osf_pof, gs, uso):
        """CRU_NA: AVO/VEH cruzando pista sin autorizacion.

        En EN_USO, cualquier rodaje (TOU/TIN) en zona de pista sin auth
        de cruce/entrada es CRU_NA, sea cual sea la velocidad. La unica
        excepcion es la PROPIA pista de despegue del avion a velocidad
        baja, que es territorio de ALIN_NA (lineup sin auth).

        Antes habia un umbral gs>=vel_taxi (50) para discriminar de
        ALIN_NA, pero eso ocultaba el caso comun: rodaje a velocidad
        normal cruzando una pista ajena en uso.

        Para CERRADA se mantiene el umbral historico para no chocar con
        AUT_CERR_CRU emitido por _check_aut_cerrada. NO_EN_USO no alerta.
        """
        if osf_pof in (CROSSING, CRUREQ, ENTERING, ENTREQ):
            return  # Tiene autorizacion explicita
        if osf_pof not in (TAXIING_OUT, TAXIING_IN):
            return

        if uso == 'NO_EN_USO':
            return  # Cruce de pista no operativa no es incursion (por config)

        if uso == 'EN_USO':
            # En propia deprwy a baja velocidad -> ALIN_NA, no duplicar
            deprwy = getattr(f, 'deprwy', '')
            if deprwy and (rwy == deprwy
                           or self.reciprocal.get(rwy) == deprwy):
                if gs < self.vel_taxi:
                    return
            self._emit_alert(f, rwy, 'CRU_NA')
            return

        # CERRADA u otros: comportamiento historico (umbral velocidad)
        if gs < self.vel_taxi:
            return
        self._emit_alert(f, rwy, 'CRU_NA')

    def _check_ent_na(self, f, rwy, osf_pof):
        """ENT_NA: VEH en zona de pista sin autorizacion de entrada."""
        if osf_pof in (ENTERING, ENTREQ):
            return  # Ya tiene fase ENT/ENR (autorizado o solicitado)
        if osf_pof in (CROSSING, CRUREQ):
            return  # Tiene auth de cruce
        if not getattr(f, 'has_pvh', False):
            # VEH sin PVH en zona de pista
            self._emit_alert(f, rwy, 'ENT_NA')
            return
        # VEH con PVH pero sin fase ENT -> no autorizado para pista
        if osf_pof not in (ENTERING, ENTREQ):
            self._emit_alert(f, rwy, 'ENT_NA')

    def _check_ent_pi(self, f, rwy, osf_pof):
        """ENT_PI: VEH con ENT autorizado pero en pista incorrecta."""
        if osf_pof != ENTERING:
            return
        ent_runway = getattr(f, 'ent_runway', None)
        if not ent_runway:
            return
        if rwy == ent_runway:
            return
        recip = self.reciprocal.get(rwy)
        if recip and recip == ent_runway:
            return
        self._emit_alert(f, rwy, 'ENT_PI')

    def _check_aut_cerrada(self, f, rwy, osf_pof, uso, is_veh):
        """AUT_CERR_*: Autorizacion en pista cerrada o no en uso."""
        if uso not in ('CERRADA', 'NO_EN_USO'):
            return

        # Determinar que autorizacion tiene segun OSF_pof
        if osf_pof == LININGUP:
            auth = 'Alineacion'
        elif osf_pof == DEPARTING:
            auth = 'Despegue'
        elif osf_pof in (LANDING, LANDED):
            auth = 'Aterrizaje'
        elif osf_pof in (CROSSING, CRUREQ):
            auth = 'Cruzar'
        elif osf_pof == ENTERING:
            auth = 'Entrar'
        else:
            return

        # Lookup en tabla CMACpistasCerradas
        entry = self.pistas_cerradas.get((uso, auth))
        if not entry:
            return
        subtipo = entry.get('subtipo', '')
        if not subtipo:
            return
        sev_str = entry.get('severidad', 'WNG')
        self._emit_alert(f, rwy, subtipo, severity_override=sev_str)

    def _check_no_contacto(self, f):
        """NO_CONTACTO: AVO en aproximacion sin asuncion por controlador."""
        osf_pof = getattr(f, 'OSF_pof', None)
        if osf_pof not in (INCOMING, APPROACH, LANDING):
            return
        if getattr(f, 'atc_sector', None) is not None:
            return  # Ya asumido

        gs = f.ground_spd if f.ground_spd else 0.0
        dist_thr = getattr(f, 'dist_thr', None)
        if dist_thr is None or dist_thr <= 0 or gs <= 0:
            return

        time_to_thr = dist_thr / gs * 3600.0
        if time_to_thr > self.tiempo_min_contacto:
            return  # Demasiado lejos

        landing_rwy = getattr(f, 'lrwy', '') or getattr(f, 'desrwy', '')
        if not landing_rwy or landing_rwy in ('', 'ZZ'):
            landing_rwy = None  # Pista desconocida

        self._emit_alert(f, landing_rwy, 'NO_CONTACTO')

    # ---------------------------------------------------------------
    # Emision y utilidades
    # ---------------------------------------------------------------

    def _emit_alert(self, f, rwy, subtype_code, severity_override=None):
        """Crea y emite una alerta CMAC."""
        # Obtener severidad del Excel (o override para AUT_CERR)
        if severity_override:
            severity = SEVERITY_MAP.get(severity_override, SEVERITY_WNG)
        else:
            st_info = self.subtypes.get(subtype_code, {})
            sev_str = st_info.get('severidad', 'WNG')
            severity = SEVERITY_MAP.get(sev_str, SEVERITY_WNG)

        if severity == SEVERITY_NONE:
            return

        # Descripcion
        st_info = self.subtypes.get(subtype_code, {})
        nombre = st_info.get('nombre', subtype_code)
        if rwy:
            desc = 'CMAC %s RWY %s' % (subtype_code, rwy)
        else:
            desc = 'CMAC %s' % subtype_code

        alert = Alert(ALERT_CMAC, severity, desc, runway=rwy, subtype=subtype_code)

        # Restaurar acknowledged si existia
        ack_key = (f.callsign, rwy, subtype_code)
        if ack_key in self._acknowledged_alerts:
            alert.acknowledged = True

        # Evitar duplicados en el mismo ciclo
        for existing in f.active_alerts:
            if (existing.alert_type == ALERT_CMAC and
                    existing.subtype == subtype_code and
                    existing.runway == rwy):
                return

        f.active_alerts.append(alert)

        # Logging con dedup
        log_key = (f.callsign, rwy, subtype_code)
        if log_key not in self._logged:
            self._logged.add(log_key)
            sev_txt = 'VIO' if severity == SEVERITY_VIO else 'WNG'
            logging.debug("CMAC ALERTA: %s %s - %s (rwy=%s)",
                          f.callsign, sev_txt, subtype_code, rwy)

    def _parse_runway_config(self, pistas_config):
        """Convierte pistas_config del controlador a lookup por pista."""
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

    def _deduplicate_reciprocal(self, matched_rwys, rwy_use):
        """Elimina pistas reciprocas duplicadas, eligiendo la con operacion."""
        by_pair = {}
        for rwy in matched_rwys:
            recip = self.reciprocal.get(rwy)
            if recip:
                pair_key = frozenset([rwy, recip])
            else:
                pair_key = frozenset([rwy])
            if pair_key not in by_pair:
                by_pair[pair_key] = []
            by_pair[pair_key].append(rwy)

        result = []
        for pair_key, entries in by_pair.items():
            if len(entries) == 1:
                result.append(entries[0])
            else:
                best = None
                for rwy in entries:
                    oper = rwy_use.get(rwy, {}).get('operacion', '')
                    if oper:
                        best = rwy
                        break
                if best is None:
                    best = entries[0]
                result.append(best)
        return result
