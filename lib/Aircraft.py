# !/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: Aircraft.py 2353 2007-03-02 14:19:55Z rodrigo $
# This file is part of GAMMA.
#
# GAMMA is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# GAMMA is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GAMMA; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

"""Contains the Aircraft class, which models an aircraft flying a given route
and following ATC commands"""

# Module imports
from ConfigParser import ConfigParser
from MathUtil import *
from math import pi, tan
import copy
import sys
import logging
import random
import datetime
from datetime import timedelta
import BADA
import Route
import TLPV  # This is used as an optimization in set_route. Could be removed
import FIR

RWY_IAS = 50.
# Constants
CALLSIGN_FILE = "Callsigns.txt"
LEFT = "LEFT"
RIGHT = "RIGHT"

# TODO These will be taken out of here and into TLPV
PREACTIVE = "PREACTIVE"
READY = "READY"

# Phases of flight
LOADING = "LOADING"  # Internal status before the aircraft is 'ready to fly'
GROUND = "GROUND"   #
# Cuidado que también se utiliza LANDED que se comparte con OSF pof
TAKEOFF = "TAKEOFF"
FLYING = "FLYING"   #
INACTIVE = "INACTIVE"  # Prior to the aircraft entering the first route point

# Subphases of flight
# Flying
COASTING = "COASTING"  # After the aircraft reached its final waypoint and it's coasting along
TAXING = "TAXING"
VACATING = "VACATING"
# Globals

# OSF phases of flight
# Logical sequence for departures
PREPARING = "PRE"  # Internal status before the aircraft is 'ready to fly'
AUTHORIZATION = "ATC"  # Paso intermedio PREPARING->STARTING, solo usado en PrevDesp (ver OSF_DEPSEQ)
STARTING = "S/U"  # Autorización puesta en marcha
PUSH = "P/B"  # Autorización retroceso
PUSH_N = "P/N"  # Autorización retroceso N
PUSH_S = "P/S"  # Autorización retroceso S
PUSH_E = "P/E"  # Autorización retroceso E
PUSH_W = "P/W"  # Autorización retroceso W
PUSH_LIST = ["P/B","P/N","P/S","P/E","P/W"]
TAXIING_OUT = "TOU"  # Autorización rodadura salida
LININGUP = "L/U"  # Autorización alinear
DEPARTING = "DEP"  # Autorización despegue
AIRBORNE = "AIR"  # Anotación en el aire

# Logical sequence for arrivals
INCOMING = "INC"  # Arribada entrante
APROXIM = "APP"
HOLDING = "HLD"
LEAVEHLD = "AHL"
LANDING = "LDG"  # Autorización aterrizaje
LANDED = "LND"  # Anotación toma
TAXIING_IN = "TIN"  # Autorización rodadura llegada
PARKED = "FIN"  # Anotación estacionado
MAP = "MAP"  # Autorizacion frustrada
GA = "GA"  # Autorizacion GoArround

# Logical sequence for OVERFLIGHTS
ENTERING = "ENT"  # Autorización a entrar
HOLDING = "HLD"  # Autorización a esperar
CROSSING = "CRU"  # Autorización a cruzar pista
LIB = "LIB"        # Anotacion pista libre (tras cruce)

# Other states
TRANSFERRED = "***"
TERMINATED = "###"

ABORT = "ABO"
SALIDA = "SAL"

# Requests
STARTREQ = "SUR"
STICEREQ = "SIR"
REAREQ = "REA"
PUSHREQ = "PBR"
TAXIREQ = "TXR"
DEPREQ = "DPR"
LDGREQ = "LDR"
TGLREQ = "TGL"
CRUREQ = "CRR"    # Solicitud de cruce de pista (pseudopiloto la genera)
ENTREQ = "ENR"    # Solicitud de entrada a pista (controlador la genera para VEH)

# ATC Authorization status
ATC_NA = "ATC_NA.gif"  # not applicable, traffic is not a departure
ATC_PENDING = "ATC_PENDING.gif"
ATC_REQUEST = "ATC_REQUEST.gif"
ATC_OK = "ATC_OK.gif"
ATC_MISSING = "ATC_MISSING.gif"
ATC_OBSOLETE = "ATC_OBSOLETE.gif"

# OSF_DEPSEQ = [PREPARING, AUTHORIZATION, STARTING, PUSH, TAXIING_OUT, LININGUP, DEPARTING, AIRBORNE]
OSF_DEPSEQ = [PREPARING, STARTING, PUSH, TAXIING_OUT, LININGUP, DEPARTING, AIRBORNE]
OSF_ARRSEQ = [INCOMING, LANDING, LANDED, TAXIING_IN, PARKED]
OSF_ARRSEQ_APP = [INCOMING, APROXIM, HOLDING, LEAVEHLD, LANDING, LANDED, TAXIING_IN, PARKED]
OSF_OVFSEQ = [INCOMING, ENTERING, HOLDING, CROSSING]
OSF_BACKPARKSEQ = [ABORT, TAXIREQ, TAXIING_OUT, TERMINATED]

LDGANOT = "LGA"
DEPANOT = "DPA"
HELI_WVC = ['*L', '*M']

a = BADA.Atmosphere()
tas_from_cas = a.get_tas_from_cas
cas_from_tas = a.get_cas_from_tas
tas_from_mach = a.get_tas_from_mach
mach_from_tas = a.get_mach_from_tas

# TODO Wind should be a properperty of the Atmosphere object
# and we would probably like to model the wind gradient and
# the wind direction backing with raising altitude
wind = [0.0, 0.0]

callsigns = {}  # Callsign database
fir = None  # GTA will set the proper FIR data


def _ad_param(key, ad, default):
    """Parametro de escenario por aerodromo (dict con clave '*' como valor general)."""
    try:
        d = fir.param(key, {})
        return float(d.get(ad, d.get('*', default)))
    except:
        return default


# GTA.py sets fir as a module global

# Load the callsign database


def load_callsigns():
    global callsigns
    cf = ConfigParser()
    try:
        cf.readfp(open(CALLSIGN_FILE, "r"))
    except:
        cf.readfp(open("../" + CALLSIGN_FILE, "r"))
    callsigns = {}
    for cs, rcs in cf.items('Callsigns'):
        callsigns[cs.upper()] = rcs.upper()


load_callsigns()


def get_radio_callsign(cs):
    global callsigns
    try:
        rc = callsigns[cs.strip("*")[:3]]
    except:
        rc = ''
        logging.debug("No radio callsign for " + cs)
        callsigns[cs.strip("*")[:3]] = ''
    return rc


def v(self):
    """Returns the target TAS to acquire"""
    # Devuelve TAS
    if not self.std_speed:  # Velocidad minima manteniendo IAS
        try:
            return tas_from_cas(self.tgt_ias, self.lvl * 100)
        except:
            logging.error("Error setting standard TAS for %s" % self.callsign, exc_info=True)
            return 250.
    if self.perf.bada:
        if self.lvl < self.cfl:
            tas = self.perf.get_climb_perf(self.lvl)[0]
        elif self.lvl > self.cfl:
            tas = self.perf.get_descent_perf(self.lvl)[0]
        else:
            if self.app_auth and self.to_do == 'app':
                tas = self.perf.get_descent_perf(self.lvl)[0]
            else:
                tas = self.perf.get_cruise_perf(self.lvl)[0]
        # JRAR: reduce 10% the tabulated speeds for approach
        if self.lvl < 150:
            tas = 0.9 * tas
        return tas

    # TODO we should delete all the following. We should simply have equivalents for
    # all known aircraft to the BADA models

    if self.perf.max_fl > 290.:  # Fast moving traffic
        inicio_lnd = 00.
        trans_app = 15
        inicio_app = 00.
        trans_tma = 50.
        vel_tma = 150.
    elif self.perf.max_fl > 200.:  # Medium speed traffic
        inicio_lnd = 00.
        trans_app = 15
        inicio_app = 00.
        trans_tma = 35.
        vel_tma = 80.
    else:
        inicio_lnd = 00.
        trans_app = 15
        inicio_app = 00.
        trans_tma = 25.
        vel_tma = 35.

    if self.lvl <= inicio_app:  # Velocidad de aproximacion
        return self.perf.app_tas
    elif self.lvl <= inicio_lnd:  # Velocidad de rodadura
        p = (self.lvl - inicio_lnd) / (trans_app - inicio_lnd)
        return self.perf.lnd_tas * (1. - p) + self.perf.app_tas * p
    elif self.lvl <= trans_tma:  # Transicion entre vel aprox y tma
        p = (self.lvl - inicio_app) / (trans_tma - inicio_app)
        return self.perf.app_tas * (1. - p) + self.perf.tma_tas * p
    elif self.lvl <= vel_tma:  # Transicion entre ruta y tma
        p = (self.lvl - trans_tma) / (vel_tma - trans_tma)
        ias_std = self.perf.cruise_tas / (1 + 0.002 * self.perf.max_fl * 0.90)
        return self.perf.tma_tas * (1. - p) + ias_std * (1.0 + 0.002 * self.lvl) * p
    #    return self.perf.tma_tas
    else:
        ias_std = self.perf.cruise_tas / (1 + 0.002 * self.perf.max_fl * 0.90)
        return min(ias_std * (1 + 0.002 * self.lvl), self.perf.max_tas)
    #     p=min((self.lvl-vel_tma)/(self.perf.max_fl-vel_tma),1.)
    #     return min(self.perf.max_tas * p + self.perf.tma_tas * (1-p),self.perf.cruise_tas)


def f_vert(self):
    # Devuelve factor correccion de velocidad vertical
    # TODO Probably this is unneeded now that we have a the BADA summary table
    q = self.lvl / self.perf.max_fl
    if q < .75:
        return 1.0
    elif q < .90:
        return 0.80
    else:
        return 0.60


def get_hdg_obj(self, deriva, t):
    # Da el rumbo objetivo en funcion de la demanda
    self.yaw = 0.0
    if self.to_do == 'fpr':  # Mantener plan de vuelo
        # self.pto=self.route[0].pos() # Punto al que se dirige con correccion de deriva
        try:
            self.pto = self.route[0].pos()  # Punto al que se dirige con correccion de deriva
        except:
            self.to_do = 'hdg'
            self.to_do_aux = [self.hdg, 'ECON']
            self.tgt_hdg = self.hdg
            return self.hdg

        self.vect = rp(r(self.pto, self.pos))
        if self.vect[0] < 1e-8:
            self.vect = (0, self.route.get_outbd_track(0))
        # Establecer orientación para las salidas (push-back)
        if self.pof == GROUND and self.route[0].push_back:
            self.yaw = 180.0
        # Correcion de deriva
        return self.vect[1] - deriva
    elif self.to_do == 'hdg':  # Mantener rumbo
        hdg_obj = self.to_do_aux[0]
        if self.hdg < 180.0 and hdg_obj > self.hdg + 180.0:
            hdg_obj -= 360.0
        elif self.hdg > 180.0 and hdg_obj < self.hdg - 180.0:
            hdg_obj += 360.0
        aux_hdg = self.hdg - hdg_obj
        self.vect = rp((2.0 * self.ground_spd, hdg_obj))
        if self.to_do_aux[1] == 'DCHA':
            if aux_hdg > 0.:  # El rumbo est? a su izquierda
                return (self.hdg + 90.) % 360.
            else:  # Est? a su derecha o ya est? en rumbo
                return hdg_obj
        elif self.to_do_aux[1] == 'IZDA':
            if aux_hdg < 0.:  # El rumbo est? a su derecha
                return (self.hdg - 90.) % 360.
            else:  # Est? a su izquierda o ya est? en rumbo
                return hdg_obj
        else:
            return hdg_obj
    elif self.to_do == 'orbit':  # Orbitar en presente posición
        self.pto = self.route[0].pos()  # Punto al que se dirige con correcci?n de deriva
        self.vect = rp(r(self.pto, self.pos))
        if self.to_do_aux[0] == 'DCHA':
            return (self.hdg + 90.0) % 360.0
        else:
            return (self.hdg - 90.0) % 360.0

    elif self.to_do == 'hld':  # Hacer esperas sobre un punto
        if not self.to_do_aux[4] and self.to_do_aux[0] in self.route:
            # Aun no ha llegado a la espera, sigue volando en ruta
            self.pto = self.route[0].pos()  # Punto al que se dirige con correcci?n de deriva
            self.vect = rp(r(self.pto, self.pos))
            # Correcion de deriva
            return self.vect[1] - deriva
        else:  # Esta dentro de la espera, entramos bucle de la espera
            self.to_do_aux[4] = True
            # Mantener el stop en el fijo para que no pase a 'app' en mitad de la espera,
            # salvo que el usuario lo haya quitado (se aproxima al terminar la vuelta)
            if len(self.route) > 0 and not getattr(self, 'hold_stop_removed', False):
                self.route[0].stop = True
            if not self.to_do_aux[0] in self.route:  # El fijo principal debe estar en la ruta. Si no est? se pone
                self.route.insert(0, Route.WayPoint(self.to_do_aux[0]))
                self.route[0].stop = True
            self.vect = rp((2.0 * self.ground_spd, self.track))  # Con esta operacion no nos borra el punto de la espera
            if len(self.to_do_aux) == 6:  # Vamos a definir el rumbo objetivo, a?adiendolo al final
                r_acerc = (self.to_do_aux[1] - deriva) % 360.0
                aux = self.hdg - r_acerc
                # Reduce to -180,180 interval
                if aux < -180.0:
                    aux += 360.0
                elif aux > 180.0:
                    aux -= 360.0
                # Para hacer una espera con entrada falsa
                # if aux > -(360-(self.hdg+20)) and aux < self.hdg-180+20: # entrada falsa
                # r_obj = (self.to_do_aux[1]  +180.0 * self.to_do_aux[5] - deriva) %360. # Rumbo de alejamiento (con correcci?n de deriva)
                # if (t>self.to_do_aux[2] + self.to_do_aux[3]):
                # else: # Entrada directa
                # r_obj = (self.to_do_aux[1] + 180.0  - deriva) %360. # Rumbo de alejamiento (con correcci?n de deriva)
                # Calcular rumbo de alejamiento (con correcci?n de deriva)
                if aux < -60.0:  # Entrada en falsa (cambiamos el sentido de giro para asegurar
                    # que volvemos por el lado protegido de la espera)
                    r_obj = -((self.to_do_aux[1] + 180.0 - deriva) % 360.)
                    self.to_do_aux[5] = -self.to_do_aux[5]
                elif aux > 120.0:  # Entrada en gota
                    r_obj = -((self.to_do_aux[1] + 180.0 - 30.0 * self.to_do_aux[5] - deriva) % 360.)
                else:  # Entrada directa
                    r_obj = (self.to_do_aux[1] + 180.0 - deriva) % 360.

                self.to_do_aux.append(r_obj)
            r_obj = self.to_do_aux[6]
            if r_obj < 0.0:
                r_obj = -r_obj
            else:
                if abs(r_obj - self.hdg) > 60.0:
                    r_obj = (self.hdg + 90.0 * self.to_do_aux[5]) % 360.0
            if self.to_do_aux[3] == 0.0 or self.to_do_aux[3] == -10.0:  # Est? en el viraje hacia el tramo de alejamiento
                if abs(r_obj - self.hdg) < 1.:  # Ha terminado el viraje
                    if self.to_do_aux[3] == -10.0:
                        self.to_do_aux[4] = False
                        self.to_do_aux[3] = 0.0
                        self.to_do_aux.pop(6)
                        # Si el usuario quito el stop durante la espera, ahora ejecuta la aproximacion
                        if getattr(self, 'hold_stop_removed', False) and self.ades in fir.aerodromes.keys():
                            try:
                                self.execute_app(self.ades, self.lrwy, self.iaf)
                            except Exception:
                                logging.warning('Error ejecutando aproximacion tras espera', exc_info=True)
                        self.hold_stop_removed = False
                    else:
                        self.to_do_aux[3] = t
            elif t > self.to_do_aux[2] + self.to_do_aux[3]:  # Comprobar tiempo que lleva en alejamiento y al terminar entra en acercamiento
                self.to_do_aux[3] = -10.0
                self.to_do_aux[6] = self.to_do_aux[1]
        return r_obj
    elif self.to_do == 'hdg<fix':
        if self.to_do_aux[0] in self.route:
            self.pto = self.route[0].pos()  # Punto al que se dirige con correcci?n de deriva
            self.vect = rp(r(self.pto, self.pos))
            # Correci?n de deriva
            return self.vect[1] - deriva
        else:
            self.vect = rp((2.0 * self.ground_spd, self.track))
            return self.to_do_aux[1]
    elif self.to_do == 'int_rdl':
        (rx, ry) = r(Route.WP(self.to_do_aux[0]).pos(), self.pos)  # Coordenadas relativas a la radioayuda
        rdl_actual = rp((rx, ry))[1]
        rdl = self.to_do_aux[1]
        if rdl < 180.0 and rdl_actual > rdl + 180.0:
            rdl_actual = rdl_actual - 360.0
        elif rdl > 180.0 and rdl_actual < rdl - 180.0:
            rdl_actual = rdl_actual + 360.0
        ang_aux = rdl - rdl_actual  # Positivo, el radial est?a la izquierda de posición actual
        (rdlx, rdly) = pr((1.0, self.to_do_aux[1]))
        dist_perp = abs(rx * rdly - ry * rdlx)
        if dist_perp < 0.1:  # Consideramos que est?en el radial
            self.vect = rp((2.0 * self.ground_spd, self.track))
            self.tgt_hdg = self.to_do_aux[1]
            return self.to_do_aux[1] - deriva
        elif dist_perp < 0.8:
            self.vect = rp((2.0 * self.ground_spd, self.track))
            self.tgt_hdg = (self.to_do_aux[1] - 20.0 * sgn(ang_aux)) % 360.0
            return (self.to_do_aux[1] - deriva - 20.0 * sgn(ang_aux)) % 360.0
        else:
            self.vect = rp((2.0 * self.ground_spd, self.track))
            return (self.tgt_hdg - deriva) % 360.0
        #       return (self.to_do_aux[1] - deriva - 45.0 * sgn(ang_aux))%360.0

    elif self.to_do == 'app':

        try:
            [xy_llz, rdl, dist_ayuda, pdte_ayuda, alt_pista] = self.llz
            self.AirportElev = alt_pista / 100.
            (rx, ry) = r(xy_llz, self.pos)  # Coordenadas relativas a la radioayuda
            # Primero intersecta la senda de planeo cuando es inferior. Solamente tocamos el rate de descenso
            self.dist_thr = dist_thr = rp((rx, ry))[0]-dist_ayuda
        except:
            logging.warning('Failed loading app data. Changing to fpr mode.')
            self.to_do = 'fpr'
            return self.hdg
        if self.lvl < alt_pista / 100. + 10. / 100. and self.wake_hint not in HELI_WVC:  # Consider touchdown below 10 feet
            #Joserra OSF LEMD
            # if self.ades == 'LEMD':
            #     self.set_osf_pof(LANDED)
            self.set_osf_pof(LANDED)
            self.send_strip = True
            self.pof = LANDED
            self.spof = VACATING
            self.to_do = 'fpr'
            if not self.lvl_blocked:
                self.cfl = alt_pista / 100.
            self.pitch = 0.0
            self.send_flight = True

            self.set_ias(RWY_IAS)  # Automatically reduce speed on the rwy
            if len(self.route) != 0 and self.route[0].fix == '_LLZ':
                self.log_waypoint()
            try:
                self.pto = self.route[0].pos()  # Punto al que se dirige con correccion de deriva
                self.vect = rp(r(self.pto, self.pos))
                # Correcion de deriva
                self.hdg = self.vect[1]
                return self.vect[1]
            except:
                return self.hdg
        elif len(self.route) != 0 and self.route[0].fix == '_LLZ':  # Interceptar localizador y senda de planeo
            # JRAR conviene ajustar la velocidad ya aquí, que nuestra referencia ya es el localizador
            # La reduccion a velocidad de aproximacion se hace mas abajo, una vez interceptado el LLZ
            (rx, ry) = r(xy_llz, self.pos)  # Coordenadas relativas a la radioayuda
            # Primero intersecta la senda de planeo cuando es inferior. Solamente tocamos el rate de descenso
            self.dist_thr = dist_thr = rp((rx, ry))[0] - dist_ayuda
            derrota = rp((rx, ry))[1]
            fl_gp = (alt_pista / 100. + dist_thr * pdte_ayuda * 60.7612)

            # Reducir a velocidad de aproximacion solo con el localizador interceptado y a menos de 10 NM,
            # y si el ATC no ha ordenado una velocidad (ias_blocked). Antes se reducia nada mas entrar en _LLZ.
            if self.esta_en_llz and dist_thr < 10.0 and not getattr(self, 'ias_blocked', False) \
                    and self.ias > self.perf.app_tas:
                self.set_ias(self.perf.app_tas / (1.0 + 0.002 * self.lvl))

            if self.action == 0:
                self.action = 1  # start up ON

            # Intercept de la senda de planeo. Se ajusta rate descenso y ajuste ias = perf.app_tas
            if self.esta_en_llz:
                fl_gp = (alt_pista / 100. + dist_thr * pdte_ayuda * 60.7612)
                if fl_gp <= self.lvl and not self.lvl_blocked:
                    # self.set_ias(self.perf.app_tas/(1.0+0.002*self.lvl))
                    self.cfl = alt_pista / 100.

                    # Rate nominal de la senda (FL/min), por si no podemos usar la distancia
                    rate = self.ground_spd * pdte_ayuda
                    # Rate necesario para llegar al umbral en su altitud, calculado con la
                    # distancia lineal al LLZ (no la distancia de ruta real).
                    if dist_thr > 0.1 and self.ground_spd > 1.0:
                        t_min = dist_thr / self.ground_spd * 60.  # minutos al umbral
                        rate = (self.lvl - alt_pista / 100.) / t_min  # FL/min
                    # Limite configurable por escenario ('app_max_rod', en ft/min).
                    # 0 = sin limite, que es el valor por defecto: en APP no se
                    # recorta por perf.max_rod, de ahi el force=True.
                    max_rod_app = fir.app_max_rod / 100.  # FL/min
                    if max_rod_app > 0. and rate > max_rod_app:
                        rate = max_rod_app
                    self.set_rate_descend(rate * 100., force=True)  # Unidades en ft/min
                else:
                    self.set_rate_descend(0.001)
            if self.wake_hint not in HELI_WVC and abs(dist_thr) < 0.5 or self.wake_hint in HELI_WVC and abs(
                    dist_thr) < 0.05:  # Criterio toma asegurada o frustrada a 0.5 NM del umbral
                if self.wake_hint in HELI_WVC and not self.lvl_blocked:
                    self.cfl = (alt_pista + 6.0) / 100.  # Rodaje para los helicópteros a 6 pies
                    self.pof = LANDED
                    self.set_ias(self.get_taxi_ias(fir))  # Automatically reduce speed on the rwy

                if self.wake_hint not in HELI_WVC:
                    self.pitch = 10.0
                self.send_flight = True
                # if (self.lvl-alt_pista)>2.or abs(derrota-rdl)>90.: # En caso de estar 200 ft por encima, hace MAP o si ya ha pasado el LLZ
                # DCM: frustrada automatica configurable por escenario ('auto_map' en la
                # hoja Escenario; 0 = desactivada, que es el valor por defecto, y entonces
                # la frustrada solo se ejecuta por orden). 'auto_map_alt' son los pies por
                # encima de la senda que la disparan.
                if fir.auto_map and (self.lvl - fl_gp) > fir.auto_map_alt / 100.:  # or abs(derrota-rdl) > 90.:  # En caso de estar 200 ft por encima de la senda, hace MAP o si ya ha pasado el LLZ
                    self.execute_map()

            # Ahora el movimiento en planta
            r_aux = rp(r(self.pos, xy_llz))
            rdl_actual = r_aux[1]
            # rdl_actual is clockwise heading from LLZ to traffic
            # rdl clockwise INCOMING heading from LOC to LLZ
            rdl_out = (rdl + 180.0) % 360  # Orientacion pista contraria
            #  Heading (-180,180) al tráfico relativo al radial del LOC, Positivo, tráfico desviado a la derecha
            ang_aux = (rdl_out - rdl_actual)
            if ang_aux > 180:
                ang_aux -= 360.
            if ang_aux < -180:
                ang_aux += 360.
            dist_perp = abs(r_aux[0] * sin(radians(ang_aux)))
            if dist_perp < 0.1:  # Consideramos que esta en el radial
                # if abs(self.lvl-self.cfl)<002.0:
                #    self.esta_en_llz = True
                self.esta_en_llz = True
                self.int_loc = False
                self.vect = rp((2.0 * self.ground_spd, self.track))
                # return rdl - deriva
                return (rdl_actual + 180.0 - deriva) % 360.0
            elif dist_perp < 0.8:
                # if abs(self.lvl-self.cfl)<002.0:
                #    self.esta_en_llz = True
                self.esta_en_llz = True
                self.int_loc = False
                self.vect = rp((2.0 * self.ground_spd, self.track))
                # return (rdl - deriva - 20.0 * sgn(ang_aux))%360.0
                return (rdl - deriva - 20.0 * sgn(ang_aux)) % 360.0
            else:
                rdl_actual = self.hdg
                if self.int_loc:
                    if rdl < 180.0 and rdl_actual > rdl + 180.0:
                        rdl_actual = rdl_actual - 360.0
                    elif rdl > 180.0 and rdl_actual < rdl - 180.0:
                        rdl_actual = rdl_actual + 360.0
                    ang_aux2 = rdl - rdl_actual  # Positivo, el radial esta la izquierda de posicion actual
                    if ang_aux * ang_aux2 > 0.:
                        return self.tgt_hdg - deriva
                    else:
                        self.int_loc = False
                        self.vect = rp((2.0 * self.ground_spd, self.track))
                        self.tgt_hdg = rdl - 45.0 * sgn(ang_aux)
                        return (rdl - deriva - 45.0 * sgn(ang_aux)) % 360.0
                else:
                    self.vect = rp((2.0 * self.ground_spd, self.track))
                    if (self.tgt_hdg - rdl) < 10.:
                        return self.tgt_hdg - deriva
                    else:
                        # Turn to intercept because we are almost parallel to the LOC
                        return (rdl - deriva - 45.0 * sgn(ang_aux)) % 360.0

        elif self._map and '_LLZ' not in self.route:  # Going around
            for [a, b, c, h] in self.puntos_map:
                if len(self.route) != 0 and b == self.route[0].fix:
                    # El nivel del punto puede venir vacio en el escenario
                    # (hoja 'Procedimientos', fase MIS): entonces no hay
                    # restriccion y se mantiene el CFL actual.
                    if h is not None and not self.lvl_blocked:
                        self.cfl = h / 100.
                        self.set_std_rate()
                    break
            self.pto = self.route[0].pos()  # Punto al que se dirige con correcci?n de deriva
            self.vect = rp(r(self.pto, self.pos))
            # Correcion de deriva
            return self.vect[1] - deriva
        else:  # Continue approach
            for [a, b, c, h] in self.puntos_alt:
                if len(self.route) != 0 and b == self.route[0].fix:
                    if h is not None and not self.lvl_blocked:
                        self.cfl = h / 100.
                        break
            # Punto al que se dirige con correccion de deriva
            self.pto = self.route[0].pos()
            self.vect = rp(r(self.pto, self.pos))
            # Correcion de deriva
            return self.vect[1] - deriva


class Aircraft_update:

    def __init__(self, f):
        self.callsign = f.callsign
        self.pos = f.pos
        self.lvl = f.lvl
        self.cfl = f.cfl
        self.ias = f.ias
        self.ground_spd = f.ground_spd
        self.hdg = f.hdg
        self.track = f.track
        self.pof = f.pof
        # Alertas aeroportuarias: copia de la lista (el broadcast se serializa en otro hilo)
        self.max_alert_severity = getattr(f, 'max_alert_severity', 0)
        self.top_alert = getattr(f, 'top_alert', None)
        self.active_alerts = list(getattr(f, 'active_alerts', []))
        self.catc_pred = getattr(f, 'catc_pred', False)


class Aircraft_update_Unity:

    def __init__(self,
                 callsign,
                 type,
                 pos,
                 adep,
                 ades,
                 rdep,
                 rdes,
                 lvl,
                 action,
                 fire,
                 ground_spd,
                 hdg,
                 preact,
                 act,
                 fr,
                 sid,
                 star,
                 track,
                 pof,
                 squawk,
                 OSF_pof,
                 atc_sector,
                 next_atc_sector,
                 wake,
                 yaw,
                 roll,
                 app_auth,
                 ATC_status,
                 cfl,
                 eobt,
                 t_toma,
                 ctot,
                 ias,
                 park,
                 pitch,
                 model_file):

        self.callsign = callsign
        self.type = type
        self.pos = pos
        self.adep = adep
        self.ades = ades
        self.action = action
        self.fire = fire
        self.lvl = lvl
        self.ground_spd = ground_spd
        self.hdg = hdg
        self.preact = preact
        self.act = act
        self.fr = fr
        self.fire = fire
        self.model_file = model_file

        if sid:
            self.sid = str(sid)
        if star:
            self.star = str(star)
        self.track = track
        self.Drone = False
        self.pof = pof
        self.OSF_pof = OSF_pof
        self.atc_sector = atc_sector
        self.next_atc_sector = next_atc_sector
        self.ATC_status = ATC_status
        self.cfl = cfl
        self.rdes = rdes
        self.rdep = rdep
        self.ias = ias
        self.park = park.replace('PARK', '')
        self.pitch = pitch
        self.squawk = squawk
        self.wake = wake
        self.yaw = yaw
        self.roll = roll
        self.app_auth = app_auth
        if eobt:
            self.eobt = str(eobt)
        if t_toma:
            self.t_toma = str(t_toma)
        if ctot:
            self.ctot = str(ctot)
        self.Drone = False


class Aircraft:

    max_uid = 0  # All aircraft are uniquely identified. We keep the maximum number used here.

    def __init__(self, callsign, type, fr, adep, ades, rdep, rdes, park, sid_desig, star_desig, cfl, rfl, ifl, rte,
                 model_file,
                 t_start_sim, fix, eobt=None, ctot='', next_wp=None, next_wp_eto=None, wake_hint=None, dsrwy='',
                 dprwy='', init=True):

        if not init:
            return  # The instance will be used as a copy in Aircraft.copy

        if (next_wp and not next_wp_eto) or (not next_wp and next_wp_eto):
            raise (
                "Unable to calculate flight profile, either the next waypoint or the eto for the next waypoint is missing")
        if not next_wp and not next_wp_eto and not eobt:
            raise ("Either the EOBT, or the next waypoint and its ETO are mandatory parameters")

        self.no_estimates = False  # If True we skip calculating estimates
        self.SuccessLoadFlight = False
        # Used to avoid recursion
        # and avoiding calling sector_intersection
        # which stops the GTA thread for unknown reasons
        self.Drone = False
        self.fix_exe = fix
        self.uid = None  # Unique identifier. Set at the end of the init
        self.callsign = None  # 'IBE767'
        self.radio_callsign = None  # 'IBERIA'
        self.set_callsign(callsign)
        self.type = None  # 'B747'
        self.wake = None  # 'H' Wake turbulence category
        self.lrwy = ''
        self.wake_hint = wake_hint  # We can use this to give default perf values if type is unknown
        self.fr = fr  # 'LEMD'
        self.model_file = model_file
        self.set_type(type)
        self.adep = adep  # 'LEBB'
        self.rdep = rdep
        self.ades = ades  # 'LEMD'
        self.rdes = rdes
        self.desrwy = 'ZZ'
        self.deprwy = 'ZZ'
        self.dsrwy = dsrwy
        self.dprwy = dprwy
        self.park = park  # 'LEMD'

        self.sid_desig = sid_desig
        self.star_desig = star_desig
        self.colat = 'SAL_'
        self.colat_app = 'SAL^'
        self.cfl = cfl   # Cleared Flight Level, the FL the aircraft is climbing/descending towards
        self.cfl_c = cfl  # Target Flight Level entered by the controller, only for UCS label purposes
        self.tfl = 350   # Transfer Flight Level, the FL coordinated for the transfer of the aircraft
        self.rfl = rfl   # Requested Flight Level. As filed in the flight plan
        self.ecl = rfl   # Planned Flight Level.
        # TODO This should not be an aircraft attribute,
        # but rather a TLPV.FlightPlan attribute
        self.eclfix = ''
        self.ifl = ifl  # initial level in the first point of the route

        self.AirportElev = 0.0  # Variable to send the correct elevation Airport to the 3D visual
        self.pof = LOADING  # Phase of flight
        self.spof = None  # Subphase of flight

        self.OSF_pof = INCOMING
        self.OSF_warning = False
        self.ATC_status = ATC_NA

        # Cruce de pista (CRU)
        self.cru_runway = None      # Pista que se va a cruzar (ej: "06L")
        self.pre_cru_pof = None     # Fase previa al CRU (TOU o TIN) para restaurar despues de LIB

        # Plan de Vehiculo (PVH)
        self.has_pvh = False         # Tiene PV activo (creado por controlador)
        self.pvh_notes = ""          # Anotaciones del PV
        self.ent_runway = None       # Pista autorizada para entrar (ej: "24R")
        self.pre_ent_pof = None      # Fase previa al ENT, para restaurar tras LIB

        # Alertas aeroportuarias (INCW, CMAC, CATC); las calcula GTA.alert_manager
        self.active_alerts = []        # Lista de Alert activas
        self.max_alert_severity = 0    # 0=none, 1=WNG, 2=VIO
        self.top_alert = None          # Alerta mas prioritaria (para etiqueta)
        self.cmac_inhibited = False    # Inhibicion individual CMAC (controlador puede desactivar)
        self.catc_pred = False         # Alerta CATC predictiva
        self.coq = 'center'
        self.zone = ""
        self.action = 0
        self.fire = 0

        self.preact = False
        self.act = True
        self.correlado = False

        # Time attributes (Datetime instances)
        self.eobt = eobt  # Estimated off block time
        self.ctot = ctot  # CTOT del ejercicio (columna P); '' si el vuelo no tiene
        self.etot = ''    # Estimated Take-Off Time (despegue calculado; uso futuro)
        self.hora = ''    # TAB active hour (etot to departures and touchdown to arrivals)
        if self.eobt:
            self.tobt = self.set_tobt(self.eobt)
            self.tsat = self.set_tsat(self.tobt)
            self.hopm = self.set_hopm(self.eobt)  # Hora de puesta en marcha
        if self.ctot:
            self.dtot = self.set_dtot(self.ctot)
        self.next_wp = next_wp
        self.next_wp_eto = next_wp_eto
        self.t = None
        self.t_start_sim = t_start_sim
        self.rocd = 0.0  # Rate Of Climb or Descent (flight levels per hour)
        self.route = None  # Route object (Route.py)
        self.sid = None  # SID to be flown
        self.star = None  # STAR to be flown
        self.lnd = None
        self.flag_lvl_heli = False
        self.pos_stand = None

        if fix == 'AUTODEP':
            self.auto_depart = True  # Whether or not it departs automatically
        else:
            self.auto_depart = False

        try:
            self.set_route(rte)
        except:
            logging.error('Unable to set route to ' + self.callsign + ' aircraft')
            return

        self.fp_route = rte
        self.log = Route.Route()  # A Route object to keep track of flight progress
        self.pos = None  # (0.0,0.0) x,y (Cartesian coordinates in nautical miles)
        # This just sets an initial value. The correct value is done on initialize()
        if eobt:
            self.t = self.eobt
        else:
            self.t = self.next_wp_eto

        self.hdg = 0.0  # Last calculated heading (deg magnetic)
        self.track = 0.0  # Last calculated track (deg magnetic)
        self.tgt_hdg = 0.0  # Target heading to acquire (deg magnetic)
        # Aircraft orientation for 3D representation
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        # TODO we are not currently simulating a transition altitude
        # In order to do so we should keep track of both the altitude and
        # the flight level
        self.lvl = None  # Flight Level
        self.lvl_blocked = False
        self.ias_blocked = False  # True si el ATC ha ordenado una velocidad: evita que la reduccion automatica en el LLZ la pise
        self.std_rate = True  # Whether the acft will climb/descend using standard rates
        # TODO Notice there is no tgt_rocd. The aircraft changes its rate of climb or descent
        # instantaneously. We might want to revise this.
        # TODO rocd should really be measured in feet per minute
        self.rocd = 0.0  # Rate Of Climb or Descent (flight levels per hour)
        self.tas = 0.0  # True Air Speed (knots)
        self.ground_spd = 0.0  # Ground Speed (knots)
        self.filed_tas = None  # TODO We probably don't need this here, but in TLPV (knots)
        self.std_speed = True  # Use standard speed for phase of flight
        self.ias = 0.0  # Indicated Air Speed (and for our purposes, it's the same as CAS) (knots)
        self.tgt_ias = None  # Target IAS to acquire (knots)

        self.to_do = 'fpr'
        self.to_do_aux = ''
        self.hold_stop_removed = False  # El usuario quito el stop del fijo durante una espera activa
        self.squawk = None  # Mode A transpoder code the aircraft is squawking
        # TLPV calculated fields to support using the Pseudopilot display as a controller
        self.fs_print_t = None
        self.campo_eco = ''
        self.stand_sid = ''
        self.stand_sid_atc = ''
        self.campo_trans = ''
        self.tlpv_trans = ''
        # IAP related attributes

        self.depart_auth = True
        self.app_auth = False
        self.lnd_auth = False
        self.iaf = ''
        self._map = False
        self._lnd = False
        self.int_loc = False
        self.esta_en_llz = False
        # self.esta_en_arrv   = False
        self.reports = []  # List of things an aircraft should report.

        self.pp_pos = None  # Pseudopilot position "piloting" this aircraft
        # TODO atc_pos should be an attribute of a TPV flight, not of the aircraft
        self.atc_pos = None  # UCS controlling this flight
        self.atc_sector = None  # ATC sector controlling this flight
        self.sector_sequence = []  # Lo asigna GTA.load_flight; se inicializa para que siempre exista
        self.next_atc_sector = None  # ATC sector about to control this flight
        self.trans_pp_pos = False  # Set to TRUE when ACFT is being transferred by a PP position
        self.trans_atc_pos = False  # Set to TRUE when ACFT is being transferred by a ATC position
        self.release_atc_pos = False  # Set to TRUE when ACFT is released by a ATC position
        self.pedir_trf = False

        # ATC labels
        self.rutrod = '--'
        self.gate = 'GT'
        self.holdp = 'HP'
        # DCM: LEMD only, check SID to L/U departures
        self.sid_check = False
        # DCM HLRS (Hold for release slot) flag. Cuidado que en LEST es al reves. En fin...
        self.hrls = True
        self.sid_atc_changed = True  # El tick de la OSF parpadea si esta en False

        self.send_flight = False
        self.send_strip = False
        self.history = []  # [(time_str, sector, descripcion), ...]

        if init is True:
            self.initialize()

        Aircraft.max_uid = self.uid = Aircraft.max_uid + 1
        self.SuccessLoadFlight = True

    def initialize(self):
        # Init code
        self.t_toma = None
        self.t_NMfinal = None
        self.dist_thr = None
        self.std_speed = True

        # Case Dep and Lnd. Aircraft start in some intermediate route point
        if fir.AdHasIfrRwys(self.adep) and fir.AdHasIfrRwys(self.ades) and self.fr != 'VEH' and \
                self.route[0].fix != self.fix_exe:
            route_copy = self.copyOfElement(self.route)
            if self.wake_hint in HELI_WVC:
                self.flag_lvl_heli = True

            for wp in route_copy:
                if self.fix_exe == 'AUTODEP':
                    # Salida automatica: empieza en el primer punto de la ruta a la EOBT (antes se iban
                    # descartando todos los puntos porque ninguno coincide con 'AUTODEP')
                    self.next_wp = wp.fix
                    self.next_wp_eto = self.eobt
                    self.t = self.next_wp_eto
                    self.lvl = self.cfl
                    break
                elif self.fix_exe != '_LLZ' and self.route[0].fix != self.fix_exe:
                    self.log.append(wp)
                    self.route.remove(wp)
                elif self.fix_exe == '_LLZ' and wp.fix != self.star.start_fix:
                    self.log.append(wp)
                    self.route.remove(wp)
                else:
                    if self.fix_exe == '_LLZ':
                        self.next_wp = '_LLZ'
                    else:
                        self.next_wp = wp.fix

                    self.next_wp_eto = self.eobt
                    self.t = self.next_wp_eto
                    self.lvl = self.cfl
                    break

        if not self.next_wp:
            self.pof = GROUND
            self.spof = PARKED
            self.act = False
        else:
            self.pof = FLYING
            self.osf_pof = AIRBORNE

        if self.pof == FLYING:
            self.lvl = self.ifl
            self.ground_spd = self.tas = v(self)

        else:  # GROUND
            if fir.AdHasIfrRwys(self.adep):
                self.lvl = fir.aerodromes[self.adep].val_elev
            if self.cfl < self.lvl:
                self.cfl = self.lvl
            # We need to start up with an initial speed because the
            # accelaration code is not realistic
            self.ground_spd = self.tas = 0.
        self.ias = cas_from_tas(self.tas, self.lvl * 100)
        self.set_ias(self.ias)

        # if self.ades in fir.aerodromes.keys():
        if fir.AdHasIfrRwys(self.ades):  # (1)
            self.set_app_fix()
            self.app_auth = True  # Only for pure ADI, to avoid manual authorisation

        self.pos = self.route[0].pos()
        if self.route[0].push_back:
            self.yaw = 180.0
        else:
            self.yaw = 0.0
        self.track = self.hdg = self.route.get_outbd_track(0)

        # Cuando la definición del vuelo es salida y llegada al mismo aeropuerto y fijo no es eobt

        self.calc_eto()

        if self.next_wp_eto:
            if self.next_wp[0] == '>':
                delta = self.t_NMfinal - self.next_wp_eto
            else:
                if self.next_wp not in [wp.fix for wp in self.route]:
                    raise ("Unable to create flight. Estimate waypoint (%s) not in the route (%s)" % (self.next_wp,
                                                                                                      self.route))
                delta = self.route[self.next_wp].eto - self.next_wp_eto
            for wp in self.route:
                try:
                    wp.eto -= delta
                    if wp.fix == '_LLZ':
                        self.t_toma = wp.eto
                except:
                    pass
            self.t -= delta

        self.set_campo_eco()
        self.set_campo_stand_sid()
        self.set_campo_rwy()
        # self.set_campo_trans()

        # Now that we have computed the ETOs, set null speed for aircraft on the ground
        if self.pof == GROUND:

            self.OSF_pof = PREPARING
            self.ATC_status = ATC_PENDING
            self.t = self.eobt - timedelta(minutes=10)
            if self.t < self.t_start_sim:
                self.t = self.t_start_sim
            self.std_speed = False
            self.pos = self.route[0].pos()
            self.set_ias(0.)
            self.ias = 0.
            self.tas = 0.
            self.depart_auth = True
            if self.adep in fir.aerodromes.keys():
                self.lvl = fir.aerodromes[self.adep].val_elev
                self.AirportElev = fir.aerodromes[self.adep].val_elev
        # remove ficticious SID for vehicles to avoid take-off
        if self.fr == 'VEH':
            self.final_wp(self.sid_start)
            self.remove_wp(self.sid_start)
            self.sid = None
            self.star = None
            self.sid_desig = ''
            self.star_desig = ''
            self.stand_sid = ''
            self.stand_sid_atc = ''

    def __getstate__(self):
        """This function is called by the pickler. We remove the attributes that we don't want to send through the wire"""
        odict = self.__dict__.copy()
        try:
            del odict['perf']
        except:
            pass
        return odict

    def __str__(self):
        return self.callsign

    def next(self, t):
        """Advance simulation to time t"""
        global wind

        if self.pof not in [GROUND,
                            LOADING] and self.lvl <= 25.0 and self.action == 0:  # Start UP ON -> FLYING Aircrafts
            self.action = 1

        # Stop and hold position if final taxi point has been reached
        if self.fix_exe == '_LLZ' and len(self.route) != 0 and self.route[0].fix == self.iaf and not self.route[0].stop:
            self.execute_app(self.ades, self.rdes, self.iaf)

        # Consider helicopter flying if altitude is 6 ft above aerodrome. Landed below 6 ft above aerodrome
        if self.wake_hint in HELI_WVC:
            if self.pof == GROUND:  # Departure Control
                if fir.AdHasIfrRwys(self.adep) and self.lvl >= 0.06 + fir.aerodromes[
                self.adep].val_elev and self.action == 1:
                    self.to_do = 'fpr'
                    self.pof = FLYING
                    self.osf_pof = AIRBORNE
                    self.send_flight = True
                    self.etot = self.hora = t
            elif self.pof == FLYING:
                if len(self.route) != 0 and self.route[0].fix == self.sid_start and self.ias != 0.0:  # Ascent Beginning
                    self.spof = ''
                    self.std_speed = True  # Necesario para que extraiga la velocidad/altitud de las tablas de BADA en funcion del nivel actual

        if len(self.route) == 0:
            if self.pof in (GROUND, LANDED):
                self.set_ias(0.)
                self.ias = 0.
                self.tas = 0.
                self.t = t
                if self.wake_hint in HELI_WVC:
                    self.action = 0
                    self.spof = PARKED
                    if fir.AdHasIfrRwys(self.ades):
                        self.lvl = self.cfl = fir.aerodromes[self.ades].val_elev
                if self.pof == LANDED:
                    if self.spof != PARKED:
                        # Detect parked state and store time to kill after a while
                        self.spof = PARKED
                        self.log[-1].ato = self.t
                return
            # Aircraft has reached its final waypoint, and its not known
            # airport, so we just coast along or orbit
            elif self.pof == FLYING and self.to_do not in ('hdg', 'orbit', 'hld'):
                self.to_do = 'hdg'
                self.to_do_aux = [self.hdg, 'ECON']
                self.tgt_hdg = self.hdg

                if self.spof != COASTING:
                    # Detect coasting state and store time to kill after a while
                    self.spof = COASTING
                    self.log[-1].ato = self.t
        else:
            if self.spof == PARKED and self.ias > 0:
                self.spof = TAXING
            elif self.spof == COASTING:
                self.spof = FLYING
        # Change to take-off phase if next point is the sid start (final taxi point has been reached) and we are moving
        if self.depart_auth and self.pof == GROUND and len(self.route) != 0 and self.route[
        0].fix == self.sid_start and self.fr != 'VEH':
            if self.tgt_ias > 0.01:
                self.pof = TAKEOFF
                self.send_flight = True
                self.std_speed = True
        # return
        try:

            if self.pof == GROUND and self.spof == PARKED and self.fr != 'VEH' and t > self.eobt:
                if self.pp_pos is None:
                    if not self.trans_pp_pos:
                        self.trans_pp_pos = True
                        self.send_flight = True
                if self.auto_depart:
                    self.set_ias(self.get_taxi_ias(fir))
                    self.ias = self.get_taxi_ias(fir)
                    self.tas = self.get_taxi_ias(fir)

        except TypeError:
            logging.error("Type error when checking phase of flight of %s, assuming departure" % self.callsign)
            # self.pof = TAKEOFF
            self.pof = GROUND
            self.send_flight = True
        #        if t < self.t or self.pof==GROUND:
        if t < self.t:
            if self.pof == FLYING:
                self.pof = INACTIVE
                self.send_flight = True
                return
            elif self.pof == GROUND:
                self.pof = LOADING
                self.send_flight = True
                return

        if self.pof == INACTIVE:
            if t > self.t:
                self.pof = FLYING
                self.osf_pof = AIRBORNE
                self.send_flight = True
        elif self.pof == LOADING:
            if t > self.t:
                self.pof = GROUND
                self.spof = PARKED
                self.act = False
                self.send_flight = True

        dh = (t - self.t).seconds / 3600. + (
                t - self.t).microseconds / 3600. / 1000000  # Delta hours (fractional hours since the last update)
        # Calculo de la altitud
        if self.cfl > round(self.lvl, 1) and (self.pof in FLYING or self.wake_hint in HELI_WVC):  # Ascent
            if self.std_rate:
                self.rocd = self.perf.std_roc * f_vert(self)
                if self.perf.bada:
                    self.rocd = self.perf.get_climb_perf(self.lvl)[2] * 60. / 100
        elif self.cfl < self.lvl and (
                self.pof in (FLYING, LANDED) or self.wake_hint in HELI_WVC and self.pof not in INACTIVE) \
                or len(self.route) == 0 and self.wake_hint in HELI_WVC and fir.AdHasIfrRwys(
            self.ades) and self.lvl > 0.06 + fir.aerodromes[self.ades].val_elev:  # Descent
            if self.std_rate:
                self.rocd = -min(self.tas / 0.2 / 100. * 60., self.perf.max_rod * f_vert(self))
                if self.perf.bada:
                    self.rocd = -self.perf.get_descent_perf(self.lvl)[1] * 60. / 100
        else:
            self.rocd = 0.

        inch = self.rocd * dh
        if len(self.route) == 0:
            pass
        else:
            # INCREMENTAMOS EL NIVEL DEL HELICOPTERO CUANDO SE TRATA DE UN SOBREVUELO
            if self.wake_hint in HELI_WVC and not fir.AdHasIfrRwys(self.adep) and not fir.AdHasIfrRwys(
                    self.ades) and self.pof == FLYING:
                self.lvl = self.lvl + inch
            # INCREMENTAMOS EL NIVEL DEL HELICOPTERO CUANDO DAMOS PUESTA EN MARCHA HASTA + 6 PIES
            if self.wake_hint in HELI_WVC and fir.AdHasIfrRwys(self.adep) and self.pof == GROUND and self.lvl < 0.06 + fir.aerodromes[self.adep].val_elev and self.action == 1:
                self.lvl = self.lvl + 0.06  # Al dar puesta en marcha a un helicoptero este asciende hasta + 6 pies
                self.spof = TAXING
            # INCREMENTAMOS NIVEL SI NO ES UN HELICOPTERO O SI EL SIGUIENTE PUNTO DE LA RUTA DEL HELICPTERO ES EL COMIENZO DE LA SID
            elif self.wake_hint not in HELI_WVC or self.wake_hint in HELI_WVC and fir.AdHasIfrRwys(self.adep) \
                    and len(self.route) != 0 and self.route[
                0].fix == self.sid_start and not self.flag_lvl_heli and self.ias != 0.0:
                self.flag_lvl_heli = True

            if self.flag_lvl_heli or not fir.AdHasIfrRwys(self.adep) and fir.AdHasIfrRwys(self.ades):

                if abs(self.lvl - self.cfl) < abs(inch):
                    if (self.cfl - self.lvl) > 0.:
                        self.pitch = 0.  # level off when reaching top of climb
                    self.lvl = self.cfl
                    self.rocd = 0.
                    self.send_flight = True
                    self.std_rate = True
                else:
                    self.lvl = self.lvl + inch

        # Iteracion para encontrar la posicion
        # Advance in 0.1 seconds steps
        while t >= self.t + timedelta(microseconds=100000):
            if (t - self.t).microseconds > 100000:
                dh = 100000. / 1000000. / 3600.
            else:
                dh = (t - self.t).seconds / 3600. + (t - self.t).microseconds / 3600. / 1000000
            aux_v = v(self)
            # These acceleration limits should be type of aircraft and phase of flight dependant
            if self.pof == LANDED:
                if self.ground_spd > 50.:
                    # Frenada en el aterrizaje (kt/s) por aerodromo: parametro de escenario 'decel_aterrizaje'
                    # (por defecto 7; LESO 8 por la longitud de pista; LEBL 4, ocupan pista mas tiempo)
                    inc_v_max = _ad_param('decel_aterrizaje', self.ades, 7.) * 3600. * dh
                else:
                    inc_v_max = 3. * 3600. * dh  # Inc. v = 3kts/seg TAS
            elif self.pof == GROUND:
                if self.ground_spd > 40.:
                    inc_v_max = 25. * 3600. * dh  # Inc. v = 5kts/seg TAS
                else:
                    inc_v_max = 3. * 3600. * dh  # Inc. v = 3kts/seg TAS
            elif self.pof == TAKEOFF:
                # JRAR: V2 about 10% higher than minimum approach speed
                aux_v = 1.1 * self.perf.app_tas
                # JRAR: Take-off acceleration 7-8 ft/s2 for commercial jets  -> 5 kts/seg
                # inc_v_max = 5 * 3600. * dh
                # Aceleracion en el despegue (kt/s) por aerodromo: parametro de escenario 'acel_despegue'
                # (por defecto 5; GEML 9 y LESO 8 por las dimensiones de la pista)
                inc_v_max = _ad_param('acel_despegue', self.adep, 5.) * 3600. * dh
            else:
                inc_v_max = 90. * 60. * dh  # Inc. v = 90kts/min TAS
            if abs(aux_v - self.tas) < inc_v_max:
                self.tas = aux_v
            else:
                self.tas = self.tas + inc_v_max * sgn(aux_v - self.tas)

            # Condition to be airborne
            if self.pof == TAKEOFF and (self.tas >= aux_v) or self.pof == TAKEOFF and self.wake_hint in HELI_WVC:
                if len(self.route) == 0:  # Se ha perdido la ruta
                    self.complete_delete_route()
                    self.route_direct(self.route[0].fix)
                if len(self.route) != 0 and self.route[0].fix == self.sid_start:
                    self.pof = FLYING
                    # self.osf_pof = AIRBORNE
                    self.set_osf_pof(AIRBORNE)
                    self.send_strip = True
                    self.spof = ''
                    self.send_flight = True
                    self.etot = self.hora = t
                    if self.wake_hint not in HELI_WVC:
                        self.pitch = 20.0
                        self.send_flight = True
                else:
                    if self.route[0].stop:
                        # JRAR A stop point has been added before sid start, this means we cancel take-off
                        self.pof = GROUND
                        self.send_flight = True
            if self.pof == LANDED and len(self.route) != 0 and self.route[0].fix == self.sid_start:
                self.etot = self.hora = t

            self.ias = cas_from_tas(self.tas, self.lvl * 100)
            (vx, vy) = pr((1.0, self.track))
            (wx, wy) = pr(wind)
            wind_perp = wx * vy - wy * vx
            wind_paral = wx * vx + wy * vy
            if self.pof == FLYING:
                self.ground_spd = self.tas + wind_paral
                try:
                    deriva = degrees(asin(wind_perp / self.tas))
                except ZeroDivisionError:
                    deriva = 0
                except ValueError:
                    deriva = 0  # TODO check what the hell is thiss
            else:
                self.ground_spd = self.tas  # Ignore wind effects on the ground
                deriva = 0
            r_obj = get_hdg_obj(self, deriva, t)

            if self.hdg < 180.0 and r_obj > self.hdg + 180.0:
                r_obj = r_obj - 360.0
            elif self.hdg > 180.0 and r_obj < self.hdg - 180.0:
                r_obj = r_obj + 360.0
            aux = r_obj - self.hdg

            rot = self.get_rot() * 60 * 60  # Rate of turn in degrees per hour
            if abs(aux) < rot * dh:
                self.hdg = r_obj % 360
                if abs(self.roll) > 0.0 and self.lvl < 30.0 and self.lvl > self.AirportElev:
                    self.roll = 0.0
                    self.send_flight = True
            else:
                self.hdg = (self.hdg + dh * rot * sgn(aux)) % 360
                if self.roll * aux >= 0.0 and self.lvl < 30.0 and self.lvl > self.AirportElev:
                    self.roll = - 0.15 * self.tas * sgn(aux)
                    self.send_flight = True


            self.track = (self.hdg + deriva) % 360
            self.salto = (self.ground_spd) * dh  # Distancia recorrida en este inc. de t incluyendo viento
            # Ha pasado el punto al que se dirige
            if len(self.route) > 0 and (self.salto > self.vect[0] or self.waypoint_reached()):
                if not self.lvl_blocked and len(self.route) > 1 and (self.to_do == 'app' or self._map):
                    if self.route[1].level is not None and self.route[0].stop is not True:
                        self.cfl = self.route[1].level
                elif not self.lvl_blocked and len(self.route) > 1 and self.route[0].level is not None and self.route[
                    0].stop is not True:
                    self.cfl = self.route[0].level
                if self.route[0].speed is not None:
                    self.set_ias(self.route[0].speed)
                if self.route[0].stop:
                    # if  self.pof == GROUND and not self.auto_depart:
                    if self.pof == GROUND and not self.no_estimates:
                        self.set_ias(0.)
                        self.ias = 0.
                        self.tas = 0.
                        self.t = t
                    if self.pof == LANDED and not self.no_estimates:
                        self.set_ias(0.)
                        self.ias = 0.
                        self.tas = 0.
                        self.t = t
                    elif self.pof == TAKEOFF and not self.no_estimates:
                        self.set_ias(0.)
                        self.ias = 0.
                        self.tas = 0.
                        self.t = t
                        self.pof = GROUND
                        self.send_flight = True
                    elif self.pof == FLYING:
                        if self.fr == 'IFR':
                            if self.to_do != 'hld' or self.to_do_aux[4] is False:
                                self.hold(self.route[0].fix)
                        # get_hdg_obj(self,deriva,t)
                        else:
                            if self.wake_hint in HELI_WVC and self.lvl <= 0.7 + self.AirportElev and len(
                                    self.route) > 1:
                                # EVITAMOS QUE EL HELICOPTERO ORBITE SI ESTA RODANDO
                                self.set_ias(0.)
                                self.ias = 0.
                                self.tas = 0.
                            else:
                                self.orbit(LEFT)

                elif len(self.route) == 1:

                    if self.app_auth and fir.AdHasIfrRwys(self.ades) and not self.route[
                        0].stop and not self.fr == 'VEH' and self.pof != LANDED:
                        self.to_do = 'app'
                        #             (puntos_alt,llz,puntos_map) = iaps[sel.iaf]
                        #             self.to_do_aux = app
                        self.salto = self.tas * dh  # Distancia recorrida en este inc.de t sin viento
                    # self.t = t
                    elif len(self.route) != 0 and self.route[0].fix in fir.aerodromes.keys():
                        # Si el ultimo punto esta en la lista de aeropuertos, orbita sobre el
                        if self.to_do == 'fpr':  # En caso de que llegue a ese punto en ruta
                            try:
                                ph = [hold for hold in fir.holds if hold.fix == self.route[0].fix][0]
                                self.to_do = 'hld'
                                if ph.std_turns == True:
                                    turn = 1.0
                                else:
                                    turn = -1.0
                                self.to_do_aux = [ph.fix, ph.inbd_track,
                                                  timedelta(minutes=ph.outbd_time),
                                                  0.0, True, turn]
                            # except: pass
                            # if len(self.route)==1: # En caso contrario, hace una espera de 1 min
                            except:
                                self.to_do = 'hld'
                                self.to_do_aux = [self.route[0], self.hdg, timedelta(minutes=1), 0.0, True, 1.0]
                        self.salto = self.tas * dh  # Distancia recorrida en este inc.de t sin viento
                    else:
                        # Aircraft has reached its final waypoint, and its not known
                        # airport, so we just coast along
                        if self.pof == FLYING:
                            self.to_do = 'hdg'
                            self.to_do_aux = [self.hdg, 'ECON']
                            self.tgt_hdg = self.hdg
                            self.salto = self.tas * dh  # Distancia recorrida en este inc.de t sin viento
                            self.spof = COASTING
                        else:
                            self.set_ias(0.)
                            self.ias = 0.
                            self.tas = 0.
                else:
                    self.salto = self.tas * dh  # Distancia recorrida en este inc.de t sin viento
                    if self.spof == VACATING and len(self.route) != 0 and self.route[0].fix != '_LLZ':
                        self.spof = ""
                        self.set_ias(self.get_taxi_ias(fir))  # Automatically reduce speed to taxing speed before vacating the rwy

                    if self.to_do == 'hld':
                        if self.app_auth:
                            self.to_do = 'app'
                        else:
                            self.to_do = 'fpr'
                # if not (self.pof == 'FLYING' and self.to_do in ('orbit','hld')):
                if self.to_do not in ('orbit', 'hld', 'hdg') or self.spof == COASTING:
                    self.log_waypoint()  # Pops the old waypoint, and saves it in the log
                    if self.yaw == 180 and len(self.route) > 0 and not self.route[0].push_back:
                        self.yaw = 0
                        self.hdg = (self.hdg + 180.0) % 360
            else:
                self.salto = self.tas * dh  # Distancia recorrida en este inc.de t sin viento
            self.old_pos = self.pos
            if self.pof == FLYING:
                efecto_viento = (wx * dh, wy * dh)  # Deriva por el viento
                self.pos = s(s(self.pos, pr((self.salto, self.hdg))), efecto_viento)  # Cambiamos la posicion
            else:
                self.pos = s(self.pos, pr((self.salto, self.hdg)))
                # Cambiamos la posicion #######################PARA QUE NO SALGAN LOS MENSAJES DEL EFECTO VIENTO
            self.t += timedelta(hours=dh)  # Incrementamos el tiempo
        # self.t = t

    def calc_eto(self):
        """Calculo del tiempo entre fijos"""

        if self.no_estimates:
            return
        if self.fr == 'VEH':
            return
        try:
            self.sid_start
        except:
            self.sid_start = self.route[0].fix
        estimadas = [0.0]
        last_point = False
        sim = self.copy()
        # JRAR: For local arrivals compute estimates only until the IAF
        for i in range(len(sim.route)):
            sim.route[i].stop = False
        sim.no_estimates = True
        # sim.std_speed = True #Compute estimates using standard speeds (especially for aircraft on ground)
        sim.auto_depart = True
        del sim.log[:]  # Remove previously logged points

        inc_t = timedelta(seconds=1)
        sim.to_do = 'fpr'
        if fir.AdHasIfrRwys(sim.ades):
            sim.execute_app(sim.ades, sim.rdes, sim.iaf, update_route=False)
        find_NMfinal = False
        if self.next_wp is not None:
            if self.next_wp[0] == '>':
                find_NMfinal = True
                NMfinal = float(self.next_wp[1:])
        while not last_point:
            t = sim.t + inc_t
            sim.next(t)
            if find_NMfinal:
                if sim.dist_thr is not None:
                    if sim.dist_thr < NMfinal:
                        [xy_llz, rdl, dist_ayuda, pdte_ayuda, alt_pista] = sim.llz
                        desv_loc = abs(rdl - sim.hdg)
                        if desv_loc < 10.0 or desv_loc > 350.0:
                            self.t_NMfinal = sim.t_NMfinal = t
                            find_NMfinal = False
            # Estimate stop criterion
            # if (not sim.to_do == 'fpr' and not sim.to_do == 'app') or sim.pof == PARKED:
            # Caso Frustrada: len(sim.route) == 1 and sim.route[0].stop
            if (sim.pof == LANDED and sim.spof == PARKED) or sim.spof == COASTING or len(sim.route) == 1 and sim.route[0].stop:
                last_point = True
        if not fir.AdHasIfrRwys(sim.adep) and not fir.AdHasIfrRwys(sim.ades):
            self.hora = ''

        self.etot = sim.etot
        # Copy the ATOs of the simulated aircraft as our estimates
        for rwp, swp in zip(self.route, sim.log):
            if rwp.fix == '_LLZ' and self.fix_exe != '_LLZ':
                self.hora = swp.ato
            rwp.eto = swp.ato
            rwp.elvl = swp.alvl
        if self.fix_exe == '_LLZ' and fir.AdHasIfrRwys(self.adep):
            self.hora = self.eobt
        elif self.fix_exe == '_LLZ' and not fir.AdHasIfrRwys(self.adep):
            self.hora = self.next_wp_eto

        return self.route

    def random_time(self, base_time, min_minutes, max_minutes):
        # Convierte el tiempo base en minutos
        base_time = base_time.hour * 60 + base_time.minute

        # Genera un tiempo aleatorio en minutos dentro del rango especificado
        random_minutes = random.randint(min_minutes, max_minutes)

        # Suma los minutos aleatorios al tiempo base
        new_minutes = base_time + random_minutes

        # Convierte los minutos nuevamente en formato de tiempo
        new_hour, new_minutes = divmod(new_minutes, 60)
        new_time = datetime.time(new_hour, new_minutes)

        return new_time

    def set_tobt(self, eobt):  # aleatorio EOBT+(1'-10')
        tobt = self.random_time(eobt, 1, 10)
        return tobt

    def set_tsat(self, tobt):  # aleatorio TSAT+(2'-8')
        tsat = self.random_time(tobt, 2, 8)
        return tsat

    def set_hopm(self, eobt):  # aleatorio EOBT+(4'-7')
        hopm = self.random_time(eobt, 4, 7)
        return hopm

    def set_dtot(self, ctot):  # aleatorio CTOT+(0'-1')
        dtot = self.random_time(ctot, 0, 1)
        return dtot

    def set_callsign(self, cs):
        self.callsign = cs = cs.strip().upper()
        self.radio_callsign = get_radio_callsign(cs)

    def set_route(self, points):
        """Takes a comma or spaced separated list of points and sets and
		replaces the aircraft route"""
        self.route = Route.Route(Route.get_waypoints(points))
        # In order to save processing time, we add the sector intersection
        # waypoints ahead of time, so that when the Aircraft calculates its ETO,
        # there already are ETOs for the TLPV important points as well.
        if not self.no_estimates:
            for wp in [wp for wp in self.route[:] if wp.type == Route.TLPV]:
                self.route.remove(wp)
        self.complete_flight_plan(False)
        if not self.no_estimates:
            self.route = TLPV.sector_intersections(self.route)
        # self.route = TLPV.tma_intersections(self.route)
        # This reduction of points sometimes removes _LLZ if it is close to a touchdown point
        self.route = self.route.reduce()  # Elimina waypoints de la ruta repetidos

    def set_dest(self, ades):
        # TODO we should do proper validation here
        self.ades = ades
        self.set_campo_eco()

    def complete_delete_route(self):

        if fir.AdHasIfrRwys(self.adep):  # aplico la SID que toque

            for wp in self.route:
                self.route.remove(wp)

            ad = fir.aerodromes[self.adep]
            rwy_direction = ad.rwy_in_use

            sid_list = [sid for sid in rwy_direction.sid_dict.values() if sid.end_fix in self.sid.end_fix]

            if len(sid_list) > 0:
                sid = ''
                if len(sid_list) > 1:
                    if self.sid_desig != '':
                        for i in range(len(sid_list)):
                            if sid_list[i].txt_desig == self.sid_desig:
                                sid = sid_list[i]
                                break
                            else:
                                sid = sid_list[0]

                    else:
                        # If there are more than one SID ending at the same point and it was not specified for this
                        # flight in the exercise file, we simply pick the first one listed in the scenario file.
                        # We need and index tracker because the order of dictionaries is not sequential
                        sid = sid_list[0]
                        index = sid_list[0].index
                        for i in range(len(sid_list)):
                            if sid_list[i].index < index:
                                sid = sid_list[i]
                                index = sid_list[i].index
                else:
                    sid = sid_list[0]

            self.route.substitute_before(sid.end_fix, sid.rte)
            self.sid = sid
            self.stand_sid = sid.txt_desig
            self.sid_start = sid.rte[0].fix
            self.deprwy = rwy_direction.txt_desig
        #######

    def complete_flight_plan(self, change):
        """Adds SID and/or STAR to the route if one is published"""

        # TODO should this function be really an Aircraft method?
        # or rather a Route method, or even a FIR method?

        if fir.AdHasIfrRwys(self.adep) and self.pof in (GROUND, LOADING):  # aplico la SID que toque
            ad = fir.aerodromes[self.adep]
            if not change:  # Flag que indica si el acceso a la funcion es para cargar los pvs o para modificar la ruta a un pv
                if self.rdep == '':
                    rwy_direction = ad.rwy_in_use
                else:
                    try:
                        for rwy in ad.rwy_direction_list:
                            if rwy.txt_desig == self.rdep:
                                rwy_direction = rwy
                    except:
                        logging.error("No runway direction %s defined for airport %s" % (self.adep, rwy.txt_desig),
                                      exc_info=True)

                sid_list = [sid for sid in rwy_direction.sid_dict.values()
                            if len(self.route) != 0 and sid.end_fix in self.route[0].fix and len(sid.end_fix) >= len(
                        self.route[0].fix)]
            else:

                self.route = Route.Route()
                rwy_direction = ad.rwy_in_use

                sid_list = [sid for sid in rwy_direction.sid_dict.values()
                            if sid.end_fix in self.sid.end_fix and len(sid.end_fix) >= len(self.sid.end_fix)]

            try:
                dep = rwy_direction.dep_dict[self.park]
            except:
                for k in rwy_direction.dep_dict.keys():
                    dep = rwy_direction.dep_dict[k]
                    break

            if len(sid_list) > 0:
                sid = ''
                if len(sid_list) > 1:
                    if self.sid_desig != '':
                        for i in range(len(sid_list)):
                            if sid_list[i].txt_desig == self.sid_desig:
                                sid = sid_list[i]
                                break
                            else:
                                sid = sid_list[0]

                    else:
                        # If there are more than one SID ending at the same point and it was not specified for this
                        # flight in the exercise file, we simply pick the first one listed in the scenario file.
                        # We need and index tracker because the order of dictionaries is not sequential
                        sid = sid_list[0]
                        index = sid_list[0].index
                        for i in range(len(sid_list)):
                            if sid_list[i].index < index:
                                sid = sid_list[i]
                                index = sid_list[i].index
                else:
                    sid = sid_list[0]

            sid = self.copyOfElement(sid)
            dep = self.copyOfElement(dep)

            self.route.substitute_before(sid.end_fix, sid.rte)
            self.sid = sid
            self.stand_sid = sid.txt_desig
            self.sid_start = sid.rte[0].fix
            self.deprwy = rwy_direction.txt_desig
            #
            for p in reversed(dep.rte):
                # Remove stop point with auto departure
                if self.auto_depart:
                    p.stop = False
                self.route.insert(0, p)

            self.pos_stand = self.route[0].pos()

        if fir.AdHasIfrRwys(self.ades):  # aplico la STAR que toque
            ad = fir.aerodromes[self.ades]
            if self.rdes == '':
                rwy_direction_des = ad.rwy_in_use
                self.desrwy = rwy_direction_des.txt_desig
            else:
                try:
                    for rwy in ad.rwy_direction_list:
                        if rwy.txt_desig == self.rdes:
                            rwy_direction_des = rwy
                            self.desrwy = rwy_direction_des.txt_desig
                except:
                    logging.error("No runway direction %s defined for airport %s" % (self.ades, rwy.txt_desig),
                                  exc_info=True)
            if not change:
                star_list = [star for star in rwy_direction_des.star_dict.values()
                             if star.start_fix in self.route[-1].fix and len(star.start_fix) >= len(self.route[-1].fix)]
            else:
                if self.fr == 'VEH':
                    return

                star_list = [star for star in rwy_direction_des.star_dict.values()
                             if star.start_fix in self.star.start_fix and len(star.start_fix) >= len(
                        self.star.start_fix)]

                self.route = Route.Route()

            if len(star_list) > 0:
                star = ''
                if len(star_list) > 1:
                    if self.star_desig != '':
                        for i in range(len(star_list)):
                            if star_list[i].txt_desig == self.star_desig:
                                star = star_list[i]
                                break
                        if star == '':
                            star = star_list[0]
                    else:
                        # If there are more than one STAR beggining at an IAF and it was not specified for this
                        # flight in the exercise file, we simply pick the first one listed in the scenario file.
                        # We need and index tracker because the order of dictionaries is not sequential
                        star = star_list[0]
                        index = star_list[0].index
                        for i in range(len(star_list)):
                            if star_list[i].index < index:
                                star = star_list[i]
                                index = star_list[i].index
                else:
                    star = star_list[0]

                if self.pof == LOADING and self.next_wp is not None and self.next_wp != '_LLZ' and self.next_wp[
                    0] != '>':
                    self.route.substitute_from(star.start_fix, star.rte, save=self.next_wp)
                else:
                    if not change:
                        self.route.substitute_from(star.start_fix, star.rte)
                    else:
                        pass

                self.star = self.copyOfElement(star)
                self.set_app_fix()
                # Call the approach and landing flight route
                # self.execute_app(self.ades, self.iaf)
                self.set_app_route(self.ades, self.rdes, self.iaf)

            self.pos_stand = self.route[-1].pos()

    def set_type(self, type):
        """Saves the aircraft type and loads performance data"""
        save_type = type
        try:
            while type[0].isdigit():  # Remove number of aircraft if present
                type = type[1:]
        except IndexError:
            logging.error("Unkown type %s for %s. The type code may not be a number" % (save_type, self.callsign))
        self.type = type
        try:
            self.perf = BADA.Performance(type)

        except:
            # The previous call only fails if there is no old style performance
            # info for the type
            try:
                std = {'J': 'B743', 'H': 'B743', 'M': 'A320', 'L': 'PA34', '*L': 'EC35', '*M': 'EC35', 'H+': 'B743', 'M+': 'A320', 'M-': 'A320'}

                std_type = std[self.wake_hint.upper()]
                self.perf = BADA.Performance(std_type)

            except:
                raise ("Unable to load perfomance data for " + self.callsign)
        self.wake = self.perf.wtc.upper()

    def set_campo_eco(self):
        # TODO This should be part of TLPV.py, and maybe duplicated here for the benefit of the pseudopilot
        self.campo_eco = TLPV.get_exit_ades(self)

    def set_campo_stand_sid(self):
        # TODO This should be part of TLPV.py, and maybe duplicated here for the benefit of the pseudopilot
        self.stand_sid = self.stand_sid_atc = TLPV.get_stand_sid(self)

    def set_campo_rwy(self):
        # TODO This should be part of TLPV.py, and maybe duplicated here for the benefit of the pseudopilot

        self.lrwy = self.lrwy_atc = TLPV.get_rwy(self)

    # def set_campo_trans(self):
    # TODO This should be part of TLPV.py, and maybe duplicated here for the benefit of the pseudopilot
    # self.campo_trans = TLPV.get_squawk(self)

    def get_taxi_ias(self, fir):
        # Velocidad de rodaje segun reglas de vuelo (hoja 'Escenario': ifr_taxi_ias / vfr_taxi_ias).
        # Si el escenario no define vfr_taxi_ias, los VFR ruedan a ifr_taxi_ias (comportamiento previo).
        vfr = getattr(fir, 'vfr_taxi_ias', None)
        if self.fr == 'VFR' and vfr is not None:
            return vfr
        return getattr(fir, 'ifr_taxi_ias', getattr(fir, 'taxi_ias', 15.0))

    def set_ias(self, ias, force=True):
        self.std_speed = False

        # TODO This is a very poor approximation to the max ias
        # we are just taking the maximum cruise TAS and trying to guess
        # the maximum IAS from there.
        # if self.pof in (GROUND,LANDED,TAKEOFF):
        #    self.tgt_ias = float(ias)
        #    return (True, None)
        ias_max = cas_from_tas(self.perf.max_tas, self.lvl * 100)
        ias_min = cas_from_tas(self.perf.app_tas, self.lvl * 100)
        # Para que no sea necesario introducir la velocidad 2 veces en el rodaje de los helicopteros:
        # ias < ias_min and self.spof == TAXING and self.wake_hint in HELI_WVC
        if ias < ias_min and self.spof == TAXING and self.wake_hint in HELI_WVC or \
                ((ias < ias_max) and (ias > ias_min)) or self.pof in (GROUND, LANDED, TAKEOFF) or force is True:
            self.tgt_ias = float(ias)
            # JRAR: I do not know what the line below is intended for
            # if self.auto_depart and ias>0.1: self.auto_depart =False
            return (True, None)
        elif ias < ias_min:
            return (False, ias_min)
        else:
            return (False, ias_max)

    def set_mach(self, mach, force=False):
        lvl = self.lvl * 100
        ias = cas_from_tas(tas_from_mach(mach, lvl), lvl)
        (r, ias_max) = self.set_ias(ias, force)
        if r:
            return (True, None)
        else:
            return (False, mach_from_tas(tas_from_cas(ias_max, lvl), lvl))

    def set_std_spd(self):
        self.std_speed = True
        self.set_ias(cas_from_tas(v(self), self.lvl * 100))

    def set_std_mach(self):
        self.std_speed = True
        self.set_ias(cas_from_tas(v(self), self.lvl * 100))

    def set_cfl(self, lvl):
        if lvl <= self.perf.max_fl:
            self.cfl = lvl
            self.set_std_rate()
            return (True, None)
        else:
            return (False, self.perf.max_fl)

    def set_cfl_c(self, cfl_c):
        self.cfl_c = cfl_c

    def set_ecl(self, ecl):
        # TODO This should be handled in TLPV, not here.
        self.ecl = ecl

    def set_eclfix(self, eclfix):
        # TODO This should be handled in TLPV, not here.
        self.eclfix = eclfix

    def set_tfl(self, tfl):
        # TODO This should be handled in TLPV, not here.
        self.tfl = tfl

    def set_osf_pof(self, osf_pof):
        # TODO This should be handled in TLPV, not here.
        self.OSF_pof = osf_pof
        # Check if traffic authorised to start, taxi, etc without ATC clearance
        if self.OSF_pof in (PREPARING, STARTING, PUSH, PUSH_N, PUSH_S, PUSH_E, PUSH_W, TAXIING_OUT, LININGUP, DEPARTING, AIRBORNE) and self.ATC_status != ATC_OK:
            self.ATC_status = ATC_MISSING
        # Autorizacion de aterrizaje cuando el controlador da LDG (la usan las alertas CMAC)
        if osf_pof == LANDING:
            self.lnd_auth = True

    def set_hacc(self, hacc):
        # TODO This should be handled in TLPV, not here.
        self.hacc = hacc

    # def set_next_atc_sector(self, next_atc_sector):
    #     # TODO This should be handled in TLPV, not here.
    #     self.next_atc_sector = next_atc_sector
    #     print self.next_atc_sector
    def set_osf_warning(self, osf_warning):
        # TODO This should be handled in TLPV, not here.
        if self.OSF_warning == osf_warning:
            return
        self.OSF_warning = osf_warning

    def set_atc_status(self, atc_status):
        # TODO This should be handled in TLPV, not here.
        self.ATC_status = atc_status

    def set_rfl(self, rfl):
        # TODO This should be handled in TLPV, not here.
        self.rfl = rfl

    def set_heading(self, hdg, opt):
        if self.to_do == 'app':
            self.app_auth = True
        else:
            self.app_auth = False

        self.tgt_hdg = hdg
        self.to_do = 'hdg'
        self.to_do_aux = [hdg, opt]
        logging.debug(str((self.to_do, self.to_do_aux)))

    def fly_route(self, route):
        """Introduces a new route, and changes the flight mode to FPR"""
        keep_llz = False
        if isinstance(route, str):
            r_split = route.split('_LLZ')
            if len(r_split) == 2:
                keep_llz = True
        if keep_llz:
            self.route.substitute_before('_LLZ', r_split[0])
            self.route.substitute_after('_LLZ', r_split[1])
        else:
            self.route = Route.Route(Route.get_waypoints(route))

        # self.route = TLPV.sector_intersections(self.route)
        # Check whether a different IAf has been included in the route
        if fir.AdHasIfrRwys(self.ades):
            prev_iaf = self.iaf
            self.set_app_fix()
            if self.iaf == 'N/A':
                self.iaf = prev_iaf
                if self.to_do == 'app' and self.iaf == 'N/A': self.to_do = 'fpr'

    # Is it neccesary to compute new ETOs?
    # self.calc_eto()
    # self.set_campo_eco()
    # self.set_campo_trans()

    def set_rate_descend(self, rate, force=False):
        self.std_rate = False
        if self.cfl > self.lvl:
            rate = rate / 100. * 60.
            if rate <= self.perf.max_roc * f_vert(self) or force is True:
                self.rocd = rate
                return (True, None)
            else:
                return (False, self.perf.max_roc * f_vert(self) * 100. / 60)
        else:
            rate = -abs(rate / 100. * 60.)
            if abs(rate) <= self.perf.max_rod or force is True:
                self.rocd = rate
                return (True, None)
            else:
                return (False, -self.perf.max_rod * 100. / 60)

    def set_app_fix(self):
        self.iaf = 'N/A'
        ad = fir.aerodromes[self.ades]
        for rwy in ad.rwy_direction_list:
            if rwy.txt_desig == self.desrwy:
                rwy_direction_des = rwy

        for i in range(0, len(self.route)):
            if self.route[i - 1].fix in rwy_direction_des.iaps.keys():
                self.iaf = self.route[i - 1].fix
                return
        if len(self.route) == 0:
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig == self.desrwy:
                    for i in range(0, len(self.star.rte)):
                        if self.star.rte[i - 1].fix in rwy.iaps.keys():
                            self.iaf = self.star.rte[i - 1].fix
        else:
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig != self.desrwy:
                    for i in range(0, len(self.route)):
                        if self.route[i - 1].fix in rwy.iaps.keys():
                            self.iaf = self.route[i - 1].fix

    def set_std_rate(self):
        self.std_rate = True
        if self.rocd > 0:
            self.rocd = self.perf.std_roc * f_vert(self)
        else:
            self.rocd = -self.perf.std_rod

    def get_rot(self):
        """Returns rate of turn in degrees per second"""
        # Rate of turn. See BADA user manual 5.3
        # bank_angle = 35  # Bank angle in degrees (THIS MAXIMUM APPLIES MORE TO TAKE-OFF AND LANDING PHASES)
        # bank_angle = 45
        # try: rot = 9.81*tan(pi*bank_angle/180)*180/(self.tas*.51444)/pi  # Rate of turn in degrees per second
        # except ZeroDivisionError: rot = 40
        # return rot
        # Airborne standard turn rate 180 degrees per minute = 3 degrees per second
        # Airborne standard turn rate for light traffics 180 degrees per minute = 9 degrees per second
        # On ground standard turn rate 180 degrees in 6 seconds = 30 degrees per second
        if self.pof in (GROUND, LANDED, TAKEOFF):
            return 45.0
        elif self.to_do in ['hld']:
            return 3.0
        else:
            if self.to_do in ['orbit']:
                return 9.0
            elif self.wake == 'L':
                return 15.0
            elif self.type is not None and self.type.upper().startswith('AT') \
                    and fir.aps[0] not in ('GCXO', 'GCTS', 'LEST', 'LEBB', 'LEMG'):
                return 9.0
            else:
                return 3.0

    def get_rate_descend(self):
        if hasattr(self, "perf"):
            return self.rocd
        return self.rocd / 60. * 100.

    def get_mach(self):
        # Devuelve el nmero de mach
        return mach_from_tas(self.tas, self.lvl * 100)

    def get_ias_max(self):
        return self.perf.max_tas / (1.0 + 0.002 * self.perf.max_fl)

    def get_sector_entry_fix(self):
        if self.sector_entry_fix is None:
            return ''
        else:
            return self.sector_entry_fix

    def set_sector_entry_fix(self, fix):
        self.sector_entry_fix = fix

    def set_sector_entry_time(self, time):
        self.sector_entry_time = time

    def cancel_app_auth(self):
        if self.app_auth:
            self.app_auth = False
            for i in range(len(self.route), 0, -1):
                if self.route[i - 1].fix == self.iaf:
                    self.route = self.route[:i]
                    break

    def hold(self, fix, inbd_track=None, outbd_time=None, std_turns=None):
        if self.to_do == 'hdg':
            return
        # If there is a published hold on the fix, use its defaults
        try:
            ph = [hold for hold in fir.holds if hold.fix == fix][0]
            if inbd_track is None:
                inbd_track = ph.inbd_track
            if outbd_time is None:
                outbd_time = ph.outbd_time
            if std_turns is None:
                std_turns = ph.std_turns
        except:
            logging.debug("No published hold over " + str(fix))
            # Otherwise fill the blanks with defaults
            if inbd_track is None:
                inbd_track = self.route.get_inbd_track(fix)
            if outbd_time is None:
                outbd_time = 1  # One minute legs
            if std_turns is None:
                std_turns = True

        if std_turns:
            turn = 1.0
        else:
            turn = -1.0
        self.to_do = 'hld'
        self.to_do_aux = [fix, inbd_track, timedelta(minutes=outbd_time), 0.0, True, turn]

    # self.cancel_app_auth()

    def hdg_after_fix(self, aux, hdg):
        self.to_do = 'hdg<fix'
        self.to_do_aux = [aux, hdg]

    # self.cancel_app_auth()

    def int_rdl(self, aux, track):
        if self.to_do != 'hdg':
            self.tgt_hdg = self.hdg
        self.to_do = 'int_rdl'
        self.to_do_aux = [aux, track]

    # self.cancel_app_auth()

    # DISTINGUIMOS ENTRE LOS PROCEDIMIENTOS MAP Y LOW PASS:
    # FRUSTRADA ES UN ABORTO DE ATERRIZAJE POR LO QUE SE DETIENE EL DESCENSO,
    # MIENTRAS QUE LOW PASS CONTINUARÁ DESCENDIENDO HASTA COMPLETAR LA PASADA BAJA
    def execute_map(self):

        if not fir.AdHasIfrRwys(self.adep) and not fir.AdHasIfrRwys(self.ades) or self.pof == LANDED:
            return

        self.esta_en_llz = False
        self.app_auth = False

        if len(self.route) != 0 and self.route[0].fix == '_LLZ':
            rte = Route.Route([Route.WayPoint(p[1]) for p in self.puntos_map])
            i = 0
            for p in self.puntos_map:
                rte[i]._pos = p[0]
                rte[i].lvl = p[3]
                if p[3] is not None:
                    rte[i].level = p[3] / 100.
                i += 1
            self.route.substitute_after('_LLZ', rte)
            self.remove_wp('_LLZ')

        else:
            # cont = 0
            # for point in self.route:
            #     if point.fix != '_LLZ':
            #         cont += 1
            #     else:
            #         break

            rte = Route.Route([Route.WayPoint(p[1]) for p in self.puntos_map])
            i = 0
            for p in self.puntos_map:
                rte[i]._pos = p[0]
                rte[i].lvl = p[3]
                if p[3] is not None:
                    rte[i].level = p[3] / 100.
                i += 1
            self.route.substitute_after(self.route[0].fix, rte)  # self.route[cont-1] = MAPT

        self.to_do = 'fpr'
        # Nivel inicial de la frustrada: primer punto del MAP que traiga nivel
        # en el escenario. Si ninguno lo trae, se mantiene el CFL actual.
        map_level = None
        for p in self.puntos_map:
            if p[3] is not None:
                map_level = p[3] / 100.
                break
        # if self.lvl > map_level:
        #    self.set_cfl(self.lvl)
        # else:
        if map_level is not None:
            self.set_cfl(map_level)
        self.set_std_spd()
        self.set_std_rate()
        self.std_speed = True
        self._map = True

    def execute_lowpass(self):

        if self.adep not in fir.aerodromes and self.ades not in fir.aerodromes or self.pof == LANDED:
            return

        self.esta_en_llz = False
        self.app_auth = False

        if len(self.route) != 0 and self.route[0].fix == '_LLZ':
            rte = Route.Route([Route.WayPoint(p[1]) for p in self.puntos_map])
            i = 0
            for p in self.puntos_map:
                rte[i]._pos = p[0]
                rte[i].lvl = p[3]
                if p[3] is not None:
                    rte[i].level = p[3] / 100.
                i += 1
            self.route.substitute_after('_LLZ', rte)

        else:
            cont = 0
            for point in self.route:
                if point.fix != '_LLZ':
                    cont += 1
                else:
                    break

            rte = Route.Route([Route.WayPoint(p[1]) for p in self.puntos_map])
            i = 0
            for p in self.puntos_map:
                rte[i]._pos = p[0]
                rte[i].lvl = p[3]
                if p[3] is not None:
                    rte[i].level = p[3] / 100.
                i += 1
            self.route.substitute_after(self.route[cont - 1].fix, rte)  # cont-1 = MAPT

        self.to_do = 'fpr'
        self.set_cfl(self.cfl + 0.8)  # rwy level + 80 feets
        self._map = True

    def int_ils(self):

        if self.adep not in fir.aerodromes and self.ades not in fir.aerodromes:
            return

        if self.to_do != 'hdg':
            self.tgt_hdg = self.hdg
        # Se supone que ha sido autorizado previamente
        self.to_do = 'app'
        self.app_auth = True
        self.int_loc = True
        self.lvl_blocked = False
        self.ias_blocked = False
        wp = Route.WayPoint("_LLZ")
        wp._pos = self.llz[0]
        wp.level = self.llz[4]
        self.route = Route.Route([wp])
        # JRAR: Set taxi route after landing
        ad = fir.aerodromes[self.ades]
        for rwy in ad.rwy_direction_list:
            if self.desrwy == rwy.txt_desig:
                lnd_aux = rwy.lnd_dict[self.park]
                break
        self.route.extend([p for p in lnd_aux.rte])

        self.set_std_rate()

    def dir_fin(self):

        if self.adep not in fir.aerodromes and self.ades not in fir.aerodromes:
            return
        try:
            ad = fir.aerodromes[self.ades]

            for ads in ad.rwy_direction_list:
                if ads.txt_desig == self.rdes:
                    rwy_ad = ads
                    break

            for app_name in rwy_ad.iaps.keys():
                if self.fr == 'IFR' and '_3_' in app_name:
                    proc_Name = app_name
                    break
                elif self.fr != 'IFR' and '_1_' in app_name:
                    proc_Name = app_name

            (self.puntos_alt, self.llz, self.puntos_map) = rwy_ad.iaps[proc_Name]
            [xy_llz, rdl, dist_ayuda, pdte_ayuda, alt_pista] = self.llz

            rdl_pista = rdl
            valid_hdg = False
            if rdl_pista - 90.0 < 0.0:
                rdl_margen_inf = rdl_pista + 90.0
                rdl_margen_sup = 360 - (90 - rdl_pista)
                r_aux = rp(r(self.pos, rwy_ad.iaps[proc_Name][0][0][0]))
                if self.hdg >= rdl_margen_sup or self.hdg <= rdl_margen_inf:
                    valid_hdg = True
            elif rdl_pista + 90.0 > 360.0:
                rdl_margen_inf = (rdl_pista + 90.0) - 360.0
                rdl_margen_sup = rdl_pista - 90.0
                r_aux = rp(r(self.pos, rwy_ad.iaps[proc_Name][0][0][0]))
                if self.hdg >= rdl_margen_sup or self.hdg <= rdl_margen_inf:
                    valid_hdg = True
            else:
                rdl_margen_inf = rdl_pista - 90.0
                rdl_margen_sup = rdl_pista + 90.0
                r_aux = rp(r(rwy_ad.iaps[proc_Name][0][0][0], self.pos))
                if self.hdg <= rdl_margen_sup and self.hdg >= rdl_margen_inf:
                    valid_hdg = True

            rdl_actual = r_aux[1]
            if rdl_margen_sup < rdl_actual or rdl_actual < rdl_margen_inf or not valid_hdg:
                logging.warning('Unable to perform turns over 90 degrees angle')
                return

            if self.to_do != 'hdg':
                self.tgt_hdg = self.hdg

            # Se supone que ha sido autorizado previamente
            self.to_do = 'app'
            self.app_auth = True
            self.int_loc = False
            self.lvl_blocked = False
            self.ias_blocked = False
            self.route = Route.Route()

            self.set_app_route(self.ades, self.rdes, proc_Name)
            self.set_std_rate()
        except:
            pass

    def int_fwp(self):
        # Se supone que ha sido autorizado previamente
        (puntos_lnd, fwp) = fir.parks[self.park]
        [xy_fwp, dist_ayuda] = fwp
        self.to_do = 'int_rdl'
        self.to_do_aux = ["X%fY%f" % xy_fwp]

    def orbit(self, turn_direction):
        self.to_do = 'orbit'
        if turn_direction == LEFT:
            self.to_do_aux = ['IZDA']
        else:
            self.to_do_aux = ['DCHA']

    def execute_app(self, ades, rdes, iaf, update_route=True):
        # TODO Currently we are not checking which destination the
        # user asked for, and just clear for approach to the current destination
        self.lvl_blocked = False
        self.ias_blocked = False
        self.app_auth = True
        self.std_speed = True
        self.std_rate = True
        self.int_loc = True
        self._map = False
        self.to_do = 'app'
        if update_route:
            self.set_app_route(ades, rdes, iaf)
        # Remove stop point at iaf
        for i in range(0, len(self.route)):
            if self.route[i - 1].fix == self.iaf:
                self.route[i - 1].stop = False
                break

        logging.debug('Altitud: ' + str(self.puntos_alt[0][3]))
        self.set_cfl(self.puntos_alt[0][3] / 100.)
        self.set_std_rate()
        logging.debug("Autorizado aproximacion: " + str(self.route))

    def change_lnd(self, ades, pista):
        if self.to_do != 'app':
            return
        ad = fir.aerodromes[ades]
        for rwy in ad.rwy_direction_list:
            if rwy.txt_desig == pista:
                rwy_direction_des = rwy

        puntos_alt, llz, puntos_map = rwy_direction_des.iaps[self.iaf]
        last_app_point = Route.WayPoint(str(puntos_alt[-1][1]))
        last_app_point._pos = puntos_alt[-1][0]
        last_app_point.level = float(puntos_alt[-1][3]) / 100
        llz_point = Route.WayPoint("_LLZ")
        llz_point._pos = llz[0]
        llz_point.level = float(llz[4]) / 100

        lnd = rwy_direction_des.lnd_dict[self.park]
        act_route = []
        new_route = Route.Route()
        new_route.append(last_app_point)
        new_route.append(llz_point)

        for wp in lnd.rte:
            new_route.append(wp)

        for wp in self.route:
            act_route.append(wp.fix)
        if self.route[0].fix == '_LLZ':
            self.route.substitute_from('_LLZ', new_route[1:])
        else:
            self.route.substitute_from(str(self.route[(act_route.index('_LLZ')) - 1].fix), new_route)

        self.llz = llz
        self.rdes = self.desrwy = self.lrwy = self.lrwy_atc = pista
        self.send_flight = True

    def set_app_route(self, ades, pista, iaf):
        # TODO Currently we are not checking which destination the
        # user asked for, and just clear for approach to the current destination
        if ades is not None:
            self.ades = ades

        ad = fir.aerodromes[ades]
        for rwy in ad.rwy_direction_list:
            if rwy.txt_desig == pista:
                rwy_direction_des = rwy

        if iaf is None:
            for i in range(0, len(self.route)):
                if self.route[i].fix in rwy_direction_des.iaps.keys():
                    self.iaf = self.route[i].fix
                    self.route = self.route[:i]
                    break
        else:
            self.iaf = iaf
            for i in range(0, len(self.route)):
                if self.route[i].fix == iaf:
                    self.iaf = self.route[i].fix
                    self.route = self.route[:i]
                    break
        if self.iaf == '':  # No encuentra procedimiento de aprox.
            pass
        if self.iaf in rwy_direction_des.iaps.keys():

            (self.puntos_alt, self.llz, self.puntos_map) = self.copyOfElement(rwy_direction_des.iaps[self.iaf])

            try:
                lnd_aux = rwy_direction_des.lnd_dict[self.park]
            except:
                lnd_aux = rwy_direction_des.lnd_dict[random.choice(list(rwy_direction_des.lnd_dict.keys()))]

            self.desrwy = rwy_direction_des.txt_desig
        else:

            if self.iaf in rwy_direction_des.iaps.keys():

                (self.puntos_alt, self.llz, self.puntos_map) = self.copyOfElement(rwy_direction_des.iaps[self.iaf])

                try:
                    lnd_aux = rwy_direction_des.lnd_dict[self.park]
                except:
                    lnd_aux = rwy_direction_des.lnd_dict[random.choice(list(rwy_direction_des.lnd_dict.keys()))]

                self.desrwy = rwy_direction_des.txt_desig
            else:
                logging.warning("IAF %s selected is not available for the runway %s", self.iaf, pista)
                return
        # En este paso se desciende el trafico y se añaden los puntos
        ###########################################################################################################
        for p in self.puntos_alt:
            if self.fix_exe == '_LLZ':  # TOMA
                wp = Route.WayPoint(p[1].replace('*', ''))
            else:
                wp = Route.WayPoint(p[1])
            wp._pos = p[0]
            if p[3] is not None:
                wp.level = p[3] / 100.

            self.route.append(wp)
        ###########################################################################################################
        wp = Route.WayPoint("_LLZ")
        wp._pos = self.llz[0]
        self.route.append(wp)
        lnd_aux = self.copyOfElement(lnd_aux)
        self.route.extend([p for p in lnd_aux.rte])

    def remove_wp(self, fix):
        aux = None
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix.upper():
                aux = self.route[:i] + self.route[i + 1:]
                break
        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix.upper() + ' no encontrado al tratar de hacer una ruta directa')
            return

        # This is what actually sets the route
        self.fly_route(aux)

    def toggle_stop(self, fix):

        if self.ades in fir.aerodromes.keys():
            ad = fir.aerodromes[self.ades]
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig == self.desrwy:
                    rwy_direction_des = rwy

        if self.ades in fir.aerodromes.keys() and self.adep in fir.aerodromes.keys() \
                and fix in rwy_direction_des.iaps.keys() and self.pof in (GROUND, TAKEOFF):
            return

        aux = None
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix.upper():
                aux = self.route[i]
                if self.route[i].stop is False:
                    self.route[i].stop = True
                else:
                    self.route[i].stop = False
                    # En espera activa no se aproxima ya: se termina la vuelta (ver hold)
                    in_active_hold = (self.to_do == 'hld' and len(self.to_do_aux) > 4 and self.to_do_aux[4] == True)
                    if in_active_hold:
                        self.hold_stop_removed = True
                    else:
                        if self.to_do in ('orbit'):
                            self.to_do = 'fpr'

                        if self.ades in fir.aerodromes.keys():
                            if self.route[i].fix == self.iaf:
                                self.execute_app(self.ades, self.lrwy, self.iaf)
                            elif fix in rwy_direction_des.iaps.keys():
                                self.iaf = fix
                                self.execute_app(self.ades, self.lrwy, self.iaf)
                            else:
                                if fix in rwy_direction_des.iaps.keys():
                                    self.iaf = fix
                                    self.execute_app(self.ades, self.lrwy, self.iaf)
                                    break
                                for ad_alt_key in fir.aerodromes.keys():
                                    ad_alt = fir.aerodromes[ad_alt_key]
                                    if ad_alt != ad:
                                        for rwy in ad_alt.rwy_direction_list:
                                            if fix in rwy.iaps.keys():
                                                self.iaf = fix
                                                self.ades = ad_alt_key
                                                self.execute_app(self.ades, self.lrwy, self.iaf)
                                                break
                break

        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix.upper() + ' no encontrado al tratar de hacer una ruta directa')
            return
        elif not self.route[0].stop and self.fr == 'VFR' and self.to_do == 'orbit':
            if self.iaf != '' and self.iaf not in self.route:
                self.to_do = 'app'
            else:
                self.to_do = 'fpr'
        # This is what actually sets the route
        self.fly_route(self.route)

    def push_back(self, fix):
        aux = None
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix.upper():
                aux = self.route[i]
                if self.route[i].push_back is False:
                    self.route[i].push_back = True
                else:
                    self.route[i].push_back = False
        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix.upper() + ' no encontrado al tratar de hacer una ruta directa')
            return
        # This is what actually sets the route
        self.fly_route(self.route)

    def final_wp(self, fix):
        aux = None
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix.upper():
                aux = self.route[:i + 1]
        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix.upper() + ' no encontrado al tratar de hacer final de ruta')
            return

        # This is what actually sets the route
        self.fly_route(aux)

    def route_direct(self, fix):
        aux = None
        self.lvl_blocked = False
        self.ias_blocked = False
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix.upper():
                aux = self.route[i:]
                break
        # Si no esta en la ruta, insertamos el punto como n=1
        if aux is None:
            wp = Route.WayPoint(fix)
            wp.pos()
            aux = [wp]

            for a in self.route:
                aux.append(a)
        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix.upper() + ' no encontrado al tratar de hacer una ruta directa')
            return

        # This is what actually sets the route
        if self.to_do in ('orbit', 'hld', 'hdg'):
            if self.to_do == 'hdg':  # Rumbo Fijado
                if self.app_auth:
                    self.to_do = 'app'
                else:
                    self.to_do = 'fpr'
            else:
                self.to_do = 'fpr'

        elif self.to_do == 'app':
            for point in aux:
                if point.fix != '_LLZ' and point.level is not None:
                    self.cfl = point.level
                    break
                if point.fix == '_LLZ':
                    self.cfl = point.level / 100
                    break


        self.fly_route(aux)

    def extend_route(self, fix):
        wp = Route.WayPoint(fix)
        wp_list = [wp]  # Conversion to list in case we prefer to do batch processing in the future
        self.route.extend(wp_list)
        # This is what actually sets the route
        self.fly_route(self.route)

    def insert_wp(self, fix, fix_next, stop=False, push_back=False, fix_after=None):
        aux = None
        wp = Route.WayPoint(str(fix), stop=stop, push_back=push_back)
        wp_list = [wp]  # Conversion to list in case we prefer to do batch processing in the future
        # Si es un punto intermedio de la ruta, lo detecta
        for i in range(len(self.route)):
            if self.route[i].fix == fix_next.upper():
                aux = self.route[:i] + wp_list + self.route[i:]
                break
        if aux is None and fix_after is not None:
            # fix_next ya no esta en la ruta (el avion lo ha pasado mientras se definia el punto):
            # se inserta antes del siguiente punto conocido para mantener el orden
            for i in range(len(self.route)):
                if self.route[i].fix == fix_after.upper():
                    aux = self.route[:i] + wp_list + self.route[i:]
                    logging.warning('Punto ' + fix_next.upper() + ' no encontrado, insertado antes de ' + fix_after.upper())
                    break
        if aux is None:
            # TODO we need to deal with exceptions here the same
            # we do with set_cfl, for instance
            logging.warning('Punto ' + fix_next.upper() + ' no encontrado al tratar de insertar punto anterior')
            return False

        # This is what actually sets the route
        self.fly_route(aux)
        return True

    def depart(self, sid_str, cfl, rdep, t):
        # Change SID and, if still in parking, taxi route as well
        # Store current taxi route in auxiliary variable
        if self.adep not in fir.aerodromes.keys():
            return

        idx = self.route.get_waypoint_index(self.sid_start)
        if idx:
            taxi_route = self.route[:idx - 1]
        else:
            taxi_route = self.route
        #        self.set_route(self.fp_route)
        # Change back to flight plan route (read from exercise file)
        self.route = Route.Route(Route.get_waypoints(self.fp_route))
        # Get the actual sid object, but only if a SID has been given,
        # and we had a previous SID
        (sid, dep, deprwy) = fir.aerodromes[self.adep].get_sid_dep(sid_str, rdep, self.park)
        if sid is None:
            logging.warning('Unable to find procedure for sid %s', sid_str)
        self.sid = sid
        self.deprwy = deprwy
        self.stand_sid = sid_str
        # Add SID before flight plan route
        self.route.substitute_before(sid.end_fix, sid.rte)
        # Add outbound taxi route before SID
        self.sid_start = sid.rte[0].fix
        if len(taxi_route) > 0:
            if dep.rte[0] == taxi_route[0]:  # Sólo modifico automáticamente si sigue en el parking
                self.route = dep.rte + self.route
            else:
                # Rodando: si el escenario define el umbral 'THR'+pista (hoja 'Lado aire'), va directo
                # a el (criterio de GAMMA); si no existe, mantiene el rodaje restante (criterio previo)
                cab_str = 'THR' + str(deprwy)
                if cab_str in getattr(fir, 'coords', {}):
                    self.route.insert(0, Route.WayPoint(cab_str))
                else:
                    self.route = taxi_route + self.route
        self.depart_auth = True
        self.cfl = cfl

    # JRAR: ESTIMATE COMPUTATION STALLS PROGRAM. AVOID IT
    #        self.calc_eto()

    def change_star(self, star_str, rdes, t):
        # Change STAR
        # First check if starting point is in present route, otherwise route direct
        star = fir.aerodromes[self.ades].get_star(star_str, rdes)
        self.star = star
        self.star_desig = star.txt_desig
        idx = self.route.get_waypoint_index(str(star.start_fix))
        if idx:
            self.route = self.route[:idx - 1] + star.rte
        else:
            self.route = star.rte
        self.set_app_fix()
        # Call the approach and landing flight route
        # self.execute_app(self.ades, self.iaf)
        self.set_app_route(self.ades, rdes, self.iaf)

    # JRAR: ESTIMATE COMPUTATION STALLS PROGRAM. AVOID IT
    #        self.calc_eto()

    def log_waypoint(self):
        wp = self.route.pop(0)
        wp.ato = self.t
        wp.alvl = self.lvl
        self.log.append(wp)

        self.send_flight = True

    def copy(self):
        s = self
        acft = Aircraft(s.callsign, s.type, s.fr, s.adep, s.ades, s.rdep, s.rdes, s.park, s.sid_desig, s.star_desig,
                        s.cfl, s.rfl,
                        s.ifl, s.route, s.model_file, s.t_start_sim, s.fix_exe, eobt=self.eobt, next_wp=self.next_wp,
                        next_wp_eto=self.next_wp_eto, wake_hint=self.wake_hint, init=False)
        acft.__dict__ = self.__dict__.copy()
        acft.no_estimates = True

        acft.route = self.route.copy()
        acft.log = self.log.copy()

        return acft

    def copyOfElement(self, element):
        return copy.deepcopy(element)

    def waypoint_reached(self):
        """Uses a hemiplane test to check whether we have gone abeam the next waypoint"""
        # There are times when waypoints will be so close to each other that
        # because of the limited turn performance of the aircraft it may never
        # reach the next waypoint, but rather orbit indefinitely around it.
        # In order to avoid this, besides checking for distance we use a geometrical
        # test to see whether it's not worth trying to pass over the waypoint anymore.
        # We consider a waypoint has been reached when the aircraft is placed in the
        # hemiplane defined by the next waypoint and the waypoint after that.
        # The check is done using the dot product of the leg track, and the vector
        # defined between the next waypoint and the aircraft's position
        # There is a special case. If the route is zig-zagging, the aircraft may start
        # in that hemiplane even before gettting any close to the waypoint,
        # so we also require that in order for the test to be successful, the
        # aircraft must have been in the wrong hemiplane before.
        # Also, it only applies if the aircraft is within 1.5 the turn radius
        # to the waypoint
        if len(self.route) == 0:
            return False  # No need to check.

        r_pos = r(self.pos, self.pto)
        self.vect = rp(r_pos)

        # Compute fly-by to avoid overshooting
        if self.pof in (GROUND, LANDED) and len(self.route) > 1 and len(self.route) != 0 and self.route[
            0].fix != '_LLZ' and not \
                self.route[0].stop and not self.route[0].push_back:
            r_pos = r(self.pos, self.pto)
            d_pos = rp(r_pos)[0]
            r_after = r(self.route[1].pos(), self.pto)
            d_after = rp(r_after)[0]
            if d_pos * d_after > 0.0:
                cos_angle = dp(r_pos, r_after) / (d_pos * d_after)
                if cos_angle < 1.0 and cos_angle > -1.0:
                    turn_angle = acos(cos_angle)
                    rot = self.get_rot()  # Rate of turn in degrees per second
                    d_overshoot = self.ground_spd / 3600.0 / radians(rot) / tan(0.5 * turn_angle)
                    if d_pos < d_overshoot:
                        return True

        v1 = pr((1, self.route.get_outbd_track(0)))  # Vector defining the hemiplane, from polar to rectangular
        v2 = r(self.pos, self.route[0].pos())  # Vector joining the wp and the aircraft, vactor diminish
        on_goal_hemiplane = dp(v1,
                               v2) > 0  # When the dot product (of vectors) is positive, the aircraft is on the goal hemiplane
        dist = rp(v2)[0]  # From rectangular to polar
        turn_radius = self.tas / (62.8318 * self.get_rot())  # In nautical miles
        try:
            reached = not self._prev_on_goal and on_goal_hemiplane and dist < turn_radius * 1.5
        except:
            reached = False
        if reached:
            self._prev_on_goal = None
        else:
            self._prev_on_goal = on_goal_hemiplane
        return reached

# def __del__(self):
#    logging.debug("Aircraft.__del__ (%s)"%self.callsign)


if __name__ == '__main__':
    pass
