#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: GTA.py 2381 2007-05-30 19:32:42Z rodrigo $

#


"""GTA (Generador de Tráfico Aéreo - Air Traffic Generator)
This is the main simulation engine to which clients connect"""


# System imports
from time import time, sleep
import sched
import logging
import random
import cPickle
pickle = cPickle
import sys
if not (sys.version_info[0]==2 and sys.version_info[1]<7):
    import dill
import zlib
import os
import datetime
from MathUtil import *
import RaDisplay

# Twisted imports
try:
  from twisted.internet.protocol import Factory
  from twisted.internet import reactor, defer, task, threads
  from twisted.protocols.basic import NetstringReceiver
except:
  logging.exception("Error while importing the Twisted Framefork modules")

# Application imports
# import ConfMgr
import Aircraft
import Route
# conf = ConfMgr.GammaConfig()
from RemoteClient import PSEUDOPILOT, ATC
import FIR
from Exercise import Exercise
import TLPV
import socket
import openpyxl
import json
try:
    from alertas import AlertManager
except ImportError:
    AlertManager = None
    logging.warning("Paquete alertas no disponible, alertas desactivadas")

# Constants
# QNH standard variation mB per second
QNH_STD_VAR = 0.0005
QNH_STD = 1013.0  # Fallback QNH (mB) when the exercise doesn't provide one
CLEARANCE_DISTANCE = 35 * 0.000621371  # 35 meters in mile units
CLEARANCE_SQUARED_DISTANCE = 35 * 35 * 0.000621371 * 0.000621371  # 35 meters in mile units
SIM_TIME_STEP = 1.0
COMPUTATION_TIME_STEP = 1.0

class GTA:
    def __init__(self, conf):
        self.conf = conf
        self.startTCP()
        self.send_update_flights = True

        self._dispatch_table = {
            # --- 1. SISTEMA E INFRAESTRUCTURA ---
            'hello': self._h_hello,
            'modify_time': self._h_modify_time,
            'play': self._h_play,
            'pause': self._h_pause,
            'restart_exercise': self._h_restart_exercise,
            'clock_speed': self._h_clock_speed,
            'radar_off': self._h_radar_off,
            'correlar_off': self._h_correlar_off,

            # --- 2. METEOROLOGÍA Y ENTORNO ---
            'wind': self._h_wind,
            'new_wind': self._h_new_wind,
            'metar': self._h_metar,
            'rain': self._h_rain,
            'fog': self._h_fog,
            'qnh': self._h_qnh,
            'rwy_in_use': self._h_rwy_in_use,
            'runway_config_update': self._h_runway_config_update,
            'ack_alert': self._h_ack_alert,

            # --- 3. PARÁMETROS DE VUELO E INTERACCIÓN ---
            'kill': self._h_kill,
            'set_cfl': self._h_set_cfl,
            'set_cfl_c': self._h_set_cfl_c,
            'set_rate': self._h_set_rate,
            'set_hdg': self._h_set_hdg,
            'set_ias': self._h_set_ias,
            'set_mach': self._h_set_mach,
            'start': self._h_start,
            'fire': self._h_fire,

            # --- 4. NAVEGACIÓN Y RUTAS ---
            'hold': self._h_hold,
            'change_fpr': self._h_change_fpr,
            'hdg_after_fix': self._h_hdg_after_fix,
            'int_rdl': self._h_int_rdl,
            'orbit': self._h_orbit,
            'remove_wp': self._h_remove_wp,
            'toggle_stop': self._h_toggle_stop,
            'push_back': self._h_push_back,
            'final_wp': self._h_final_wp,
            'insert_wp': self._h_insert_wp,
            'replace_wp': self._h_replace_wp,
            'route_direct': self._h_route_direct,
            'extend_route': self._h_extend_route,

            # --- 5. PROCEDIMIENTOS Y APROXIMACIÓN ---
            'depart': self._h_depart,
            'change_atc_sid': self._h_change_atc_sid,
            'change_procedure': self._h_change_procedure,
            'change_star': self._h_change_star,
            'execute_map': self._h_execute_map,
            'execute_lowpass': self._h_execute_lowpass,
            'int_ils': self._h_int_ils,
            'dir_fin': self._h_dir_fin,
            'int_arrv': self._h_int_arrv,
            'execute_app': self._h_execute_app,
            'change_app_rwy': self._h_change_app_rwy,

            # --- 6. LÓGICA ATC / STRIPS (FICHAS) ---
            'preact': self._h_preact,
            'act': self._h_act,
            'correlado': self._h_correlado,
            'pedir_trf': self._h_pedir_trf,
            'assume': self._h_assume,
            'transfer': self._h_transfer,
            'transfer_obstaculo': self._h_transfer_obstaculo,
            'set_osf_pof': self._h_set_osf_pof,
            'set_osf_warning': self._h_set_osf_warning,
            'set_next_atc_sector': self._h_set_next_atc_sector,
            'set_atc_status': self._h_set_atc_status,
            'set_ecl': self._h_set_ecl,
            'set_eclfix': self._h_set_eclfix,
            'set_rfl': self._h_set_rfl,
            'set_tfl': self._h_set_tfl,
            'set_echo': self._h_set_echo,
            'set_trans': self._h_set_trans,
            'set_rutrod': self._h_set_rutrod,
            'set_park': self._h_set_park,
            'set_gate': self._h_set_gate,
            'set_holdp': self._h_set_holdp,
            'set_sid_check': self._h_set_sid_check,
            'set_hrls': self._h_set_hrls,
            'set_client_sector': self._h_set_client_sector,
            # Vehiculos (PVH) y cruce/entrada a pista (CRU/ENT), Fase 4 bloque 2
            'request_cru': self._h_request_cru,
            'cancel_cru': self._h_cancel_cru,
            'create_pvh': self._h_create_pvh,
            'delete_pvh': self._h_delete_pvh,
            'authorize_ent': self._h_authorize_ent,
            'request_ent': self._h_request_ent,
            'set_pvh_notes': self._h_set_pvh_notes,
        }

        # Mensajes que generan entrada en el historico del vuelo
        self._history_labels = {
            'set_osf_pof': 'Accion',
            'set_cfl': 'CFL', 'set_cfl_c': 'CFL',
            'set_rfl': 'RFL', 'set_tfl': 'TFL',
            'set_hdg': 'HDG', 'set_ias': 'IAS', 'set_mach': 'Mach',
            'set_rate': 'Rate',
            'change_procedure': 'Procedimiento', 'change_atc_sid': 'SID',
            'change_star': 'STAR', 'change_app_rwy': 'APP/RWY',
            'set_rutrod': 'Observaciones',
            'set_ecl': 'ECL', 'set_eclfix': 'ECL Fix',
            'set_park': 'Stand', 'set_gate': 'Gate', 'set_holdp': 'Hold Point',
            'assume': 'Asumir', 'transfer': 'Transferir',
            'depart': 'Despegue', 'execute_map': 'MAP',
            'hold': 'Espera', 'change_fpr': 'Ruta',
            'kill': 'Eliminado',
        }


    def load(self, exc_file=""):
        self.exercise_file = exc_file

        logging.info("Loading exercise "+exc_file)
        try:
            self.e = e = Exercise(exc_file)
        except:
            logging.critical("Unable to load Exercise file % "+str(exc_file))
            raise
            return

        # Find the FIR mentioned by the exercise file
        logging.info("Loading scenario ")
        # fir_list = FIR.LoadFirs(os.path.dirname(exc_file),e.fir)
        try:
            fir = FIR.LoadFirs(os.path.dirname(exc_file), e.fir)  # os.path.abspath(exc_file),e.fir)
        except:
            logging.critical("Unable to load FIR file for "+str(exc_file))
            raise
            return

        self.fir = fir
        Aircraft.fir = fir  # Rather than passing globals
        Route.fir = fir
        TLPV.fir = fir
        # Initialize rwy in Use
        # Para cada aerodromo del escenario, la pista del primer vuelo del ejercicio que lo usa
        # (antes solo se miraba el primer vuelo y solo para el primer aerodromo, e.fir[0])
        for ad_code, ad_obj in self.fir.aerodromes.items():
            found = False
            for i in e.flights:
                ef = e.flights[i]
                for desig, ad_f in ((ef.rdep, ef.adep), (ef.rdes, ef.ades)):
                    if desig != '' and ad_f == ad_code:
                        for rwy in ad_obj.rwy_direction_list:
                            if rwy.txt_desig == desig:
                                ad_obj.rwy_in_use = rwy
                                found = True
                                break
                    if found:
                        break
                if found:
                    break

        self.sector = FIR._normalize_sector(e.sector)
        self.sector_list = e.sector_list
        # TODO wind and qnh should be properties of the atmosphere object
        # and should be variables dependent on location and height in the case of wind
        self.wind = [e.wind_knots, (e.wind_azimuth+180.0) % 360.0]
        self.new_wind = [None, None]
        self.windset = self.wind
        self.metar = e.metar
        self.radar_off = False
        self.correlar_off = False
        # We have set somewhere else a fixed seed so that squawks are reproducible
        # but we want the qnh to be different in each exercise, so we use getstate and setstate
        st = random.getstate()
        random.seed()
        qnh_ini = getattr(e, 'qnh_ini', None)
        if qnh_ini is None:
            logging.warning('No qnh_ini found in exercise %s, using standard QNH %.1f', self.exercise_file, QNH_STD)
            qnh_ini = QNH_STD
        try:
            self.qnh = float(qnh_ini)  # get value from metar field in Exercise
        except (TypeError, ValueError):
            logging.warning('Invalid qnh_ini %r in exercise %s, using standard QNH %.1f', qnh_ini, self.exercise_file, QNH_STD)
            self.qnh = QNH_STD
        self.qnh_var = random.gauss(0, QNH_STD_VAR)  # Variation in mB per second.
                                                # Should not be much more than 1mB per 10minutes
        random.setstate(st)

        # Initializes time
        self.cont = True  # Marks when the main loop should exit
        t = datetime.datetime.today()
        self.t = t.replace(t.year, t.month, t.day, int(e.start_time[0:2]), int(e.start_time[3:5]), 0, 0)
        # self.last_update = self.t - datetime.timedelta(seconds=5) # Copy the datetimeobject
        self.last_wind_update = self.t - datetime.timedelta(seconds=5)

        fact_t = self.fact_t = 1.0
        self.paused = True

        self.tlpv = tlpv = TLPV.TLPV(exc_file)
        RaDisplay.tlpv = tlpv

        # Create the aircraft for each of the flights in the exercise
        logging.info("Creating flights")
        self.flights = []
        logging.debug("Loading aircraft")

        # Register exercise-supplied squawks first so that the random ones
        # generated in tlpv.create_fp cannot collide with them
        for ef in e.flights.values():
            transp = getattr(ef, 'transp', 'None')
            if transp != 'None':
                self.tlpv.register_squawk(transp)

        for ef in e.flights.values():  # Exercise flights

            # TODO Because the current exercise format cannot distiguish between
            # overflights and departures first we create them all as overflights
            if ef.fix[0] == '>':
                aux = str(a.t_toma)[11:19]
                ef.eto = aux[:2]+aux[3:5]+aux[6:]
            a = self.load_flight(ef)
            if a is not None and a.SuccessLoadFlight:
                self.flights.append(a)
            else:
                logging.info('Unable to load flight%s', a.callsign)

        self._init_alert_manager()

    def _init_alert_manager(self):
        """Motor de alertas aeroportuarias (INCW, CMAC, CATC). Solo se activa si el
        escenario trae las hojas INCW*/CMAC*/CATC* y el parametro 'alertas' no es 0."""
        self.alert_manager = None
        if AlertManager is None:
            return
        try:
            self.alert_manager = AlertManager(self.fir)
        except Exception:
            logging.exception("Error inicializando AlertManager")
            self.alert_manager = None

    def reload_exercise(self):
        logging.info("Reloading exercise " + self.exercise_file)
        self.e = e = Exercise(self.exercise_file)

        fir = self.fir
        self.sector = FIR._normalize_sector(e.sector)
        self.sector_list = e.sector_list
        # TODO wind and qnh should be properties of the atmosphere object
        # and should be variables dependent on location and height in the case of wind
        self.wind = [e.wind_knots, (e.wind_azimuth + 180.0) % 360.0]
        self.new_wind = [None, None]
        self.windset = self.wind
        self.metar = e.metar
        self.radar_off = False
        self.correlar_off = False
        # We have set somewhere else a fixed seed so that squawks are reproducible
        # but we want the qnh to be different in each exercise, so we use getstate and setstate
        st = random.getstate()
        random.seed()
        qnh_ini = getattr(e, 'qnh_ini', None)
        if qnh_ini is None:
            logging.warning('No qnh_ini found in exercise %s, using standard QNH %.1f', self.exercise_file, QNH_STD)
            qnh_ini = QNH_STD
        try:
            self.qnh = float(qnh_ini)  # get value from metar field in Exercise
        except (TypeError, ValueError):
            logging.warning('Invalid qnh_ini %r in exercise %s, using standard QNH %.1f', qnh_ini, self.exercise_file, QNH_STD)
            self.qnh = QNH_STD
        self.qnh_var = random.gauss(0, QNH_STD_VAR)  # Variation in mB per second.
        # Should not be much more than 1mB per 10minutes
        random.setstate(st)

        # Initializes time
        self.cont = True  # Marks when the main loop should exit
        t = datetime.datetime.today()
        self.t = t.replace(t.year, t.month, t.day, int(e.start_time[0:2]), int(e.start_time[3:5]), 0, 0)
        # self.last_update = self.t - datetime.timedelta(seconds=5) # Copy the datetimeobject
        self.last_wind_update = self.t - datetime.timedelta(seconds=5)

        fact_t = self.fact_t = 1.0

        self.tlpv = tlpv = TLPV.TLPV(self.exercise_file)
        RaDisplay.tlpv = tlpv

        # Create the aircraft for each of the flights in the exercise
        logging.info("Creating flights")
        logging.debug("Loading aircraft")
        self.flights = []
        Aircraft.Aircraft.max_uid = 0

        # Register exercise-supplied squawks first so that the random ones
        # generated in tlpv.create_fp cannot collide with them
        for ef in e.flights.values():
            transp = getattr(ef, 'transp', 'None')
            if transp != 'None':
                self.tlpv.register_squawk(transp)

        for ef in e.flights.values():  # Exercise flights
            a = self.load_flight(ef)
            # TODO Because the current exercise format cannot distiguish between
            # overflights and departures first we create them all as overflights
            if a is not None and a.SuccessLoadFlight:
                self.flights.append(a)
                a.send_flight = True
            else:
                logging.info('Unable to load flight%s', a.callsign)

        # Motor de alertas nuevo: descarta reconocimientos del ejercicio anterior
        self._init_alert_manager()


    def load_flight(self, ef):
        fir = self.fir
        tlpv = self.tlpv
        eto = datetime.datetime.today()
        eto = eto.replace(hour=int(ef.eto[:2]), minute=int(ef.eto[2:4]), second=int(ef.eto[4:6]))
        # Same datetime conversion as eto, from the 'HHMMSS' string built by
        # Exercise.sacta_time() ('' when the exercise has no CTOT)
        ctot = ''
        if getattr(ef, 'ctot', ''):
            try:
                ctot = datetime.datetime.today()
                ctot = ctot.replace(hour=int(ef.ctot[:2]), minute=int(ef.ctot[2:4]), second=int(ef.ctot[4:6]))
            except:
                # logging.warning('Invalid CTOT %r for %s, ignored' % (ef.ctot, ef.callsign))
                ctot = ''
        print('load_flight ' + ef.callsign)

        # TODO We need to know which of the flights are true departures. We assume that
        # if the aircraft departs from an airfield local to the FIR,
        # the EOBT is the estimate to the first point in the route
        # We substitute the overflight (created using next_wp_eto) with a departure
        # (created using an EOBT)
        if ef.adep in fir.aerodromes.keys():
            a = Aircraft.Aircraft(ef.callsign, ef.type, ef.fr, ef.adep, ef.ades, ef.rdep, ef.rdes, ef.park, ef.sid_desig,
                                  ef.star_desig, float(ef.cfl), float(ef.rfl), float(ef.firstlevel), ef.route, ef.model_file,
                                  self.t, ef.fix, eobt=eto, ctot=ctot, wake_hint=ef.wtc)
            # if not fir.auto_departures[self.sector] \
            #  and a.adep in fir.release_required_ads[self.sector]:
            if self.sector not in fir.release_required_ads:
                logging.warning("Sector '%s' not found in fir.release_required_ads (check exercise 'Posicion' field vs scenario 'Sector' sheet)", self.sector)
            if a.adep in fir.release_required_ads.get(self.sector, []):
                if a.auto_depart:
                    pass
                else:
                    a.auto_depart = False
            else:
                a.auto_depart = True
        else:
            try:
                a = Aircraft.Aircraft(ef.callsign, ef.type, ef.fr, ef.adep, ef.ades, ef.rdep, ef.rdes, ef.park, ef.sid_desig,
                                      ef.star_desig, float(ef.cfl), float(ef.rfl), float(ef.firstlevel), ef.route, ef.model_file,
                                      self.t, ef.fix, next_wp = ef.fix, next_wp_eto = eto, ctot = ctot, wake_hint = ef.wtc)
                # a.lvl = float(ef.firstlevel)
                # If sector is in AUTO mode, clear for approach all incoming traffic
                # Joserra: Apply this only to IFR traffic
                if fir.ifr_auto_approach.get(self.sector, False) and a.fr == 'IFR':
                    if fir.AdHasIfrRwys(a.ades):
                        # JRAR: execute app but do not set app route again. Otherwise estimates could be removed
                        a.execute_app(a.ades, a.rdes, a.iaf, update_route=False)
            except:
                logging.warning("Unable to load "+ef.callsign, exc_info=True)
                return
        # TFL por defecto: parametros de escenario tfl_dep_local / tfl_defecto / tfl_fijo
        # (antes 240/250 fijos y PEKOP 130/150 "temporal fix for Santiago")
        if self.sector not in fir.local_ads:
            logging.warning("Sector '%s' not found in fir.local_ads (check exercise 'Posicion' field vs scenario 'Sector' sheet)", self.sector)
        local_dep = a.adep in fir.local_ads.get(self.sector, [])
        if local_dep:
            a.tfl = int(fir.param('tfl_dep_local', 240))
        else:
            a.tfl = int(fir.param('tfl_defecto', 250))
        tfl_fijo = fir.param('tfl_fijo', {})
        if tfl_fijo:
            for wp in a.route:
                if wp.fix in tfl_fijo:
                    a.tfl = tfl_fijo[wp.fix][0 if local_dep else 1]
        # self.flights.append(a)

        # Creates new flight plans from the loaded aircraft
        if a.eobt:
            ecl = tfl = a.rfl  # If it's a departure
        else:
            ecl = tfl = a.cfl
        sid_desig = "       "
        star_desig = "       "
        if a.sid:
            sid_desig = a.sid.txt_desig
        if a.star:
            star_desig = a.star.txt_desig
        if ef.fr != 'VEH':
            # eobt =a.eobt
            fp = tlpv.create_fp(ef.callsign, ef.type, ef.fr, ef.adep, ef.ades,
                                float(ef.rfl), ecl, a.route, sid_desig, star_desig, a.park, eobt=a.eobt,
                                next_wp=a.next_wp, next_wp_eto=a.next_wp_eto)

            if ef.transp != 'None':
                a.campo_trans = a.squawk = ef.transp
            else:
                a.campo_trans = a.squawk = fp.squawk  # Set the aircraft's transponder to what the flight plan says

            a.fs_print_t = fp.fs_print_t
            a.sector_sequence = fp.sector_sequence


            # Reglas de secuencia de sectores por escenario: hoja 'SectorSequence' o, si no
            # existe, las reglas por defecto de FIR._DEFAULT_SECTOR_SEQ_RULES (LEBL ELR/ENR,
            # salidas LEST/LECO/LEVX con APP al final, Canarias), antes fijas aqui.
            if a.sector_sequence:
                a.sector_sequence = FIR.apply_sector_seq_rules(fir.sector_seq_rules, a, self.sector,
                                                                fir.aerodromes.keys())

            if len(a.sector_sequence) > 1:
                # a.atc_sector = a.sector_sequence[0]  # ATC sector controlling this flight
                # a.next_atc_sector = a.sector_sequence[1]  # ATC sector about to control this flight
                a.next_atc_sector = a.sector_sequence[0]

            fp.wake = ef.wtc     # Keep the WTC in the exercise file, even if wrong
            fp.filed_tas = int(ef.tas)

        # print('load_flight '+ef.callsign+' '+str(a.eobt)+' '+str(a.ctot))

        return a

    def modify_time(self, new_t):
        if new_t < self.t:
            self.paused = True
            self.flights = []
            e = self.e
            logging.debug("Loading aircraft")
            for ef in e.flights.values():  # Exercise flights
                # TODO Because the current exercise format cannot distiguish between
                # overflights and departures first we create them all as overflights
                a = self.load_flight(ef)
                if a is not None and a.SuccessLoadFlight:
                    self.flights.append(a)
                else:
                    logging.info('Unable to load flight%s', a.callsign)

        self.t = new_t

    def startTCP(self, port=-1):
        self.protocol_factory = GTA_Protocol_Factory(self)
        self.pseudopilots = []  # List of connected pseudopilot clients
        self.controllers  = []  # List of connected controller clients
        if port == -1:
            port = self.conf.server_port
        try:
            self.listening_port = reactor.listenTCP(port, self.protocol_factory)
            logging.info("Servidor iniciado y esperando conexiones en el puerto "+str(port))
        except:
            logging.critical("No se ha podido iniciar el servidor. El puerto "+str(port)+" está ocupado. Verifique si ya hay un servidor corriendo y reinicie la aplicación", exc_info=True)


    def start(self, port=-1):
        # Use Twisted reactor instead of sleep. It should be more precise and less blocking
        logging.info('Starting GTA')
        self.gtaLoop = task.LoopingCall(self.timer)
        self.gtaLoop.start(SIM_TIME_STEP)  # call every second
        logging.info("Restarting connected clients")
        for client in self.controllers+self.pseudopilots:
            # Send the client initialization data
            m = {'message': 'init',
                'fir': self.fir,
                'tlpv': self.tlpv,
                'sector': self.sector,
                'pos_number': client.number,
                'exercise_file': self.exercise_file,
                'flights': self.flights}
            client.protocol.sendMessage(m)

            # Create and send the set of flightstrips to the client
            m = {'message': 'flightstrips',
               'fs_list': self.tlpv.get_sector_flightstrips(self.sector)}
            client.protocol.sendMessage(m)
        try:
            # Truco para obtener la direccion IP del servidor
            serverIP = ([l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0])
            logging.info("Ejercicio listo y esperando conexiones en direccion IP(:puerto) = "+serverIP+'(:'+str(self.conf.server_port)+')')
        except:
            logging.info('Ejercicio listo y esperando conexiones')

    def stop(self):
        # Use Twisted reactor instead of sleep. It should be more precise and less blocking
        self.gtaLoop.stop()
        logging.info("Stopping connected clients")
        for client in self.controllers+self.pseudopilots:
            m = {'message':'stop'}
            client.protocol.sendMessage(m)

    def set_vel_reloj(self, k):
        self.fact_t = k

    def timer(self):
        """Advance the simulation"""
        # Make sure we call this function again later
        st = time()
        if self.paused:
            return
        fir = self.fir
        sector = self.sector
        sector_list = self.sector_list

        refresco = 1.
        # Si el reloj no está pausado avanzamos el tiempo
        # IMPORTANT: Force advance in one second steps, instead of real clock time affected by performance
        # The exercise may run a bit slower than real time, but at constant steps close to one second
        # We advance a number of one second simulation steps during each real time second
        delta = SIM_TIME_STEP
        td = datetime.timedelta(seconds=delta)
        two_delta = 2 * delta
        target_t = self.t + datetime.timedelta(seconds=self.fact_t * delta)
        while self.t < target_t:
            self.t += td

            # Calculate new QNH
            self.qnh = self.qnh+self.qnh_var*delta*self.fact_t
            # Update wind every 2 seconds. That's means, change rwy in 5 minutes.
            deltat_wind = self.t-self.last_wind_update
            deltas_wind = deltat_wind.seconds + deltat_wind.microseconds*1.e-6
            if deltas_wind > 2.0:
                if self.new_wind[0] is not None:
                    intdad = round(self.wind[0])
                    if intdad != self.new_wind[0]:
                        if intdad < self.new_wind[0]:
                            self.windset[0] = self.wind[0] = self.wind[0] + 1.0
                        else:
                            self.windset[0] = self.wind[0] = self.wind[0] - 1.0
                    else:
                        self.new_wind[0] = None

                if self.new_wind[1] is not None:
                    # Giro progresivo de 4 grados por el camino mas corto. new_wind[1] llega en el mismo
                    # convenio que wind[1] (rumbo + 180). Antes no se aplicaba modulo 360: al cruzar el
                    # norte crecia sin limite u oscilaba, y el paso de 4 podia no coincidir nunca con el objetivo.
                    objetivo = self.new_wind[1] % 360.0
                    dif = ((objetivo - self.wind[1] + 540.0) % 360.0) - 180.0  # diferencia angular en (-180, 180]
                    if abs(dif) > 4.0:
                        self.windset[1] = self.wind[1] = (self.wind[1] + (4.0 if dif > 0 else -4.0)) % 360.0
                    else:
                        self.windset[1] = self.wind[1] = objetivo
                        print("Wind target Ok")
                        self.new_wind[1] = None

                self.wind = [max(self.windset[0], self.windset[0]+random.gauss(0, 1)),
                             max(self.windset[1],self.windset[1]+random.gauss(0, 2))]
                self.last_wind_update = self.t

            # Advance flights
            for f in self.flights:
                # logging.debug("Advancing "+f.callsign)
                f.old_pos = f.pos
                if f.pof in (Aircraft.INACTIVE, Aircraft.LOADING):
                    f.next(self.t)  # Solo detectar transiciones, sin catch-up
                    continue
                lag = (self.t - f.t).total_seconds()
                if lag > two_delta:
                    catchup_steps = 0
                    while (self.t - f.t).total_seconds() > two_delta:
                        f.next(f.t + td)
                        catchup_steps += 1
                    if catchup_steps >= 5:
                        f.t = self.t # Saltar al tiempo actual si el retraso es excesivo

                f.next(self.t)
                # JRAR: note the delay, clock time is t while simulation time is last_update#
                    # Detect and correct ground collisions

            f_sub = [f_aux for f_aux in self.flights \
                     if (f_aux.pof == Aircraft.GROUND or f_aux.pof == Aircraft.LANDED) \
                     and f_aux.spof != Aircraft.PARKED
                     and f_aux.fr !='VEH' \
                     and f_aux.wake_hint not in Aircraft.HELI_WVC]
                     # and not f_aux.auto_depart]
            auto_taxi = self.e.auto_taxi
            for i in range(0, len(f_sub)-1):
                f_this = f_sub[i]
                for j in range(i+1, len(f_sub)):
                    f_other = f_sub[j]
                    # In auto_depart mode allow crossing if both traffics are moving
                    if auto_taxi and f_this.ias > 0.01 and f_other.ias > 0.01:
                        continue
                    # Filter first x distance alone and y distance alone for computing speed
                    dx = f_this.pos[0]-f_other.pos[0]
                    if abs(dx) < CLEARANCE_DISTANCE:
                        dy = f_this.pos[1]-f_other.pos[1]
                        if abs(dy) < CLEARANCE_DISTANCE:
                            new_d2 = dx*dx+dy*dy
                            if new_d2 < CLEARANCE_SQUARED_DISTANCE:
                                if f_this.ias >0.01:
                                    # Stop if the other traffic is ahead of me
                                    stopthis_d2 = get_squareddistance(f_this.old_pos, f_other.pos)
                                    if stopthis_d2 > new_d2:
                                        #i_this = self.flights.index(f_this)
                                        #self.flights[i_this].pos = f_this.old_pos
                                        #self.flights[i_this].set_ias(0.)
                                        #self.flights[i_this].ias = 0.
                                        #self.flights[i_this].tas = 0.
                                        f_this.pos = f_this.old_pos
                                        f_this.set_ias(0.)
                                        f_this.ias = 0.
                                        f_this.tas = 0.
                                if f_other.ias > 0.01:
                                    stopother_d2 = get_squareddistance(f_this.pos, f_other.old_pos)
                                    if stopother_d2 > new_d2:
                                        #i_other = self.flights.index(f_other)
                                        #self.flights[i_other].pos = f_other.old_pos
                                        #self.flights[i_other].set_ias(0.)
                                        #self.flights[i_other].ias = 0.
                                        #self.flights[i_other].tas = 0.
                                        f_other.pos = f_other.old_pos
                                        f_other.set_ias(0.)
                                        f_other.ias = 0.
                                        f_other.tas = 0.

        # Kill flights that have been coasting for 5 minutes or have parked for 5 minutes
        for f in self.flights[:]:  # Since flights will be deleted, we iterate over a copy of the list
            if f.spof == Aircraft.COASTING and f.log[-1].ato+datetime.timedelta(minutes=1) < self.t:
                logging.info('Killing coasting flight ' + f.callsign)
                self.kill_flight(f)
            elif f.pof == Aircraft.LANDED and f.spof == Aircraft.PARKED:
                try:
                    if f.log[-1].ato+datetime.timedelta(minutes=1) < self.t:
                        logging.info('Killing parked flight' + f.callsign)
                        self.kill_flight(f)
                except:
                    logging.warning('Unable to retrieve parking time for ' + f.callsign)

        # Evaluar alertas aeroportuarias (INCW, CMAC, CATC)
        am = getattr(self, 'alert_manager', None)
        if am is not None and am.available:
            try:
                am.evaluate(self.flights, getattr(self, '_current_pistas_config', []))
            except Exception:
                logging.exception("Error evaluando alertas")

        flight_updates = []
        complete_flight_updates = []
        aerodromes = self.fir.aerodromes
        for f in self.flights:
            if f.adep in aerodromes:
                f.ad_lvl = aerodromes[f.adep].val_elev
            elif f.ades in aerodromes:
                f.ad_lvl = aerodromes[f.ades].val_elev

            if f.send_strip:
                self.send_strip(f, self.controllers)
                f.send_strip = False

            if f.send_flight:
                complete_flight_updates.append(f)
                f.send_flight = False

            elif f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING):
                flight_updates.append(Aircraft.Aircraft_update(f))
            # if f.send_flight and self.send_update_flights:
            #     self.send_update_flights = False
            #     f.send_flight = False
            #     self.send_flight(f, self.pseudopilots)
            #     self.send_flight(f, self.controllers)
            """if f.send_flight:
                f.send_flight = False
                self.send_flight(f, self.pseudopilots)
                self.send_flight(f, self.controllers)"""


        # Send formated time to clients
        for client in self.pseudopilots+self.controllers:
            if self.t != client.t:
                m = {'message': 'time', 'data': self.t}
                try:
                    client.protocol.sendMessage(m)
                # Test network delay
                # delay = random.uniform(0,5)
                # print(delay)
                # try: reactor.callLater(delay, client.protocol.sendMessage, m)
                except: logging.critical("Unable to send time message to client "+str(client.number))
                client.t = self.t

        # Send updates to clients (beafore)
        """
        for protocol in self.protocol_factory.protocols:

            protocol.sendMessage({'message': 'update',
                                  'complete_flight_updates': complete_flight_updates,
                                  'flight_updates': flight_updates,
                                  'wind': self.wind,
                                  'new_wind': self.new_wind,
                                  'windset': self.windset,
                                  'metar':(self.metar[:-4]+(str(self.qnh))[:4]),
                                  'radar_off': self.radar_off,
                                  'correlar_off': self.correlar_off,
                                  'qnh': self.qnh})
        #self.write_json_file(flight_updates_Unity)
        #self.write_viewer_file()
        #self.last_update = self.t
        """
        # Send updates to clients (now with parallelization)
        # ========== PARALELIZACION DE BROADCAST ==========
        def serialize_update_message(message_dict):
            if sys.version_info[0] == 2 and sys.version_info[1] < 7:
                line = pickle.dumps(message_dict, protocol=-1)
            else:
                line = dill.dumps(message_dict)
            return zlib.compress(line)

        def broadcast_serialized(zline):
            """Broadcast en reactor thread"""
            for protocol in self.protocol_factory.protocols:
                try:
                    protocol.sendString(zline)
                except:
                    logging.error("Failed to send to client", exc_info=True)

        # Construir mensaje una sola vez
        update_message = {
            'message': 'update',
            'complete_flight_updates': complete_flight_updates,
            'flight_updates': flight_updates,
            'wind': self.wind,
            'new_wind': self.new_wind,
            'windset': self.windset,
            # QNH con 4 cifras (Q0999): str(999.6)[:4] daba '999.'
            'metar': (self.metar[:-4]+('%04d' % int(round(self.qnh)))),
            'radar_off': self.radar_off,
            'correlar_off': self.correlar_off,
            'qnh': self.qnh
        }

        # Serializar en worker thread, broadcast en reactor thread
        d = threads.deferToThread(serialize_update_message, update_message)
        d.addCallback(broadcast_serialized)
        d.addErrback(lambda failure: logging.error("Broadcast serialization failed: %s" % failure))
        # ========== FIN PARALELIZACION ==========

    def jsonDefault(self, object):
        return object.__dict__

    def write_json_file(self, fu):  # Write Json file for Controller representation in Unity
        jsonJander = json.dumps(fu, default=self.jsonDefault)
        # print(jsonJander)

        escenario = [
            {"ad": self.fir.aerodromes.keys()[0]},  # DJCM: Cuidado, Si hay varios ad, solo pasamos el primero
            {"arp": [self.fir.y0, self.fir.x0]}  # coordinates of the arp
        ]
        jsonFile = open("GAMMA_interface/jsonOSF.json", "w")
        jsonFile.write('{"time":' + '"' + str(self.t) + '",' + '"weather":' + '"' + str(self.metar.split()[4]) + '"' +
                       ',' + '"escenario":' + json.dumps(escenario) +
                       ',' + '"flights":' + jsonJander + '}')
        jsonFile.close()


    #### Inicio prueba nuevo controlador de mensajes
    def process_message(self, m, p):
        """
        Usa la tabla de despacho para evitar el exceso de if/elif.
        """
        msg_type = m.get('message')

        # 1. Identificación del vuelo (f)
        # En Python 2.7 usamos .has_key() o 'cs' in m
        f = None
        if m.has_key("cs"):
            try:
                # Buscamos el vuelo en la lista
                flights_found = [flight_obj for flight_obj in self.flights if flight_obj.callsign == m["cs"]]
                if flights_found:
                    f = flights_found[0]
                else:
                    logging.warning("No flight with callsign %s found." % str(m["cs"]))
                    return
            except Exception as e:
                logging.warning("Error searching flight %s: %s" % (str(m.get("cs")), str(e)))
                return

        # 2. Despacho al handler correspondiente
        handler = self._dispatch_table.get(msg_type)

        if handler:
            try:
                # Registrar estado previo para historico
                hist_label = self._history_labels.get(msg_type)
                old_val = None
                if hist_label and f is not None:
                    if msg_type == 'set_osf_pof':
                        old_val = getattr(f, 'OSF_pof', None)
                    elif msg_type in ('set_cfl', 'set_cfl_c'):
                        old_val = getattr(f, 'cfl', None)
                    elif msg_type == 'set_rfl':
                        old_val = getattr(f, 'rfl', None)
                    elif msg_type == 'set_hdg':
                        old_val = getattr(f, 'hdg', None)
                    elif msg_type == 'set_ias':
                        old_val = getattr(f, 'ias', None)
                    elif msg_type == 'set_rutrod':
                        old_val = getattr(f, 'rutrod', None)

                # Ejecutamos el handler pasando el mensaje (m), protocolo (p) y vuelo (f)
                handler(m, p, f)

                # Registrar en historico del vuelo
                if hist_label and f is not None:
                    sector_str = '?'
                    if hasattr(p, 'client') and p.client is not None:
                        sector_str = getattr(p.client, 'sector', None) or '?'
                    t_str = self.t.strftime('%H:%M:%S')

                    # Construir descripcion con valor nuevo
                    if msg_type == 'set_osf_pof':
                        new_val = getattr(f, 'OSF_pof', '?')
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(new_val))
                    elif msg_type in ('set_cfl', 'set_cfl_c'):
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(getattr(f, 'cfl', '?')))
                    elif msg_type == 'set_rfl':
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(getattr(f, 'rfl', '?')))
                    elif msg_type == 'set_hdg':
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(getattr(f, 'hdg', '?')))
                    elif msg_type == 'set_ias':
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(getattr(f, 'ias', '?')))
                    elif msg_type == 'set_rutrod':
                        desc = '%s: %s -> %s' % (hist_label, str(old_val), str(getattr(f, 'rutrod', '?')))
                    else:
                        # Para acciones sin valor anterior/nuevo claro
                        extra = m.get('procedure', m.get('osf_pof', m.get('value', '')))
                        desc = '%s: %s' % (hist_label, str(extra)) if extra else hist_label

                    if not hasattr(f, 'history'):
                        f.history = []
                    f.history.append((t_str, sector_str, desc))

                # Enviar actualizaciones a pseudopilotos y controladores
                if f is not None and msg_type != 'kill':
                    self.send_flight(f, self.pseudopilots)
                    self.send_flight(f, self.controllers)
            except Exception as e:
                logging.error("Error executing handler for %s: %s" % (str(msg_type), str(e)))
        else:
            logging.critical("Unknown message type: %s" % str(msg_type))


    # 1. Handlers de Sistema e Infraestructura
    def _h_hello(self, m, p, f):
        client = Client(self)
        if m['client_type'] == ATC:
            client.type = ATC
            try:
                number = max([c.number for c in self.controllers]) + 1
            except:
                number = 0
            client.number = number
            client.protocol = p
            self.controllers.append(client)
            logging.info("Controller Client Number %d (%s:%d) connected" % (number, p.transport.client[0],
                                                                            p.transport.client[1]))
        else:
            client.type = PSEUDOPILOT
            try:
                number = max([c.number for c in self.pseudopilots]) + 1
            except:
                number = 1
            client.number = number
            client.protocol = p
            self.pseudopilots.append(client)
            logging.info("Pseudopilot Client Number %d (%s:%d) connected" % (number, p.transport.client[0],
                                                                             p.transport.client[1]))

        p.client = client
        init_msg = {'message': 'init', 'fir': self.fir, 'tlpv': self.tlpv, 'sector': self.sector,
                    'pos_number': number, 'exercise_file': self.exercise_file, 'flights': self.flights}
        p.sendMessage(init_msg)

        strips_msg = {'message': 'flightstrips', 'fs_list': self.tlpv.get_sector_flightstrips(self.sector)}
        p.sendMessage(strips_msg)

        if not hasattr(self.protocol_factory, "master_protocol"):
            self.protocol_factory.master_protocol = p
        self.protocol_factory.protocols.append(p)

    def _h_modify_time(self, m, p, f):
        print('Nueva hora ' + m['H'] + m['M'] + m['S'])
        new_t = self.t.replace(hour=int(m['H']), minute=int(m['M']), second=int(m['S']), microsecond=0)
        self.modify_time(new_t)

    def _h_play(self, m, p, f):
        logging.info("PLAY")
        self.paused = False

    def _h_pause(self, m, p, f):
        logging.info("PAUSE - guardando estado")
        self.paused = True
        for c in self.controllers + self.pseudopilots:
            try:
                c.protocol.sendMessage({"message": "save_state"})
            except:
                logging.warning("No se pudo solicitar guardado")

    def _h_restart_exercise(self, m, p, f):
        logging.info("RESTART")
        self.reload_exercise()
        for c in self.controllers + self.pseudopilots:
            c.protocol.sendMessage({"message": "restart", "flights": self.flights, 'init_time': self.t})
            c.protocol.sendMessage(
                {'message': 'flightstrips', 'fs_list': self.tlpv.get_sector_flightstrips(self.sector)})
        self.paused = True

    def _h_clock_speed(self, m, p, f):
        self.set_vel_reloj(m["data"])

    def _h_radar_off(self, m, p, f):
        self.radar_off = m["data"]

    def _h_correlar_off(self, m, p, f):
        self.correlar_off = m["data"]

    # 2. Handlers de Meteorología y Entorno
    def _h_wind(self, m, p, f):
        Aircraft.wind = self.wind = self.windset = m["wind"]

    def _h_new_wind(self, m, p, f):
        self.new_wind = m["new_wind"]
        logging.info('Viento ahora es %s' % str(self.new_wind))

    def _h_metar(self, m, p, f):
        self.metar = m["metar"]
        logging.info('METAR ahora es %s' % self.metar)

    def _h_rain(self, m, p, f):
        self.metar = m["meteo"]
        self.qnh = float(self.metar.split()[-1][1:])
        logging.info('Visual conditions changed (Rain)')

    def _h_fog(self, m, p, f):
        self.metar = m["meteo"]
        self.qnh = float(self.metar.split()[-1][1:])
        logging.info('Visual conditions changed (Fog)')

    def _h_qnh(self, m, p, f):
        self.qnh, direction = m['qnh'], m['dir']
        if not direction:
            self.qnh_var = 0
        else:
            var = 0
            while abs(var) < 1 / 600.:
                var = direction * abs(random.gauss(0, QNH_STD_VAR))
            self.qnh_var = var
        hora_cambio = self.metar.split()[1]
        hora_actual = self.t.strftime("%d%H%MZ")
        self.metar = self.metar.replace(hora_cambio, hora_actual)

    def _h_ack_alert(self, m, p, f):
        """Asume alertas de un movil (global). Propaga al par en conflictos multiples.

        Registra la asuncion en los motores INCW y CMAC para que persista entre ciclos.
        """
        cs = m.get('cs')
        if not cs:
            return
        target = None
        for fl in self.flights:
            if fl.callsign == cs:
                target = fl
                break
        if target is None:
            return

        # Obtener referencia al tracking de acknowledged del motor INCW
        incw_ack = None
        if self.alert_manager and self.alert_manager.incw:
            incw_ack = self.alert_manager.incw._acknowledged_alerts

        # Obtener referencia al tracking de acknowledged del motor CMAC
        cmac_ack = None
        if self.alert_manager and hasattr(self.alert_manager, 'cmac') and self.alert_manager.cmac:
            cmac_ack = self.alert_manager.cmac._acknowledged_alerts

        # Obtener referencia al tracking de acknowledged del motor CATC
        catc_ack = None
        if self.alert_manager and hasattr(self.alert_manager, 'catc') and self.alert_manager.catc:
            catc_ack = self.alert_manager.catc._acknowledged_alerts

        related = set()
        for a in getattr(target, 'active_alerts', []):
            a.acknowledged = True
            # Registrar en el motor para persistencia entre ciclos
            if incw_ack is not None and a.alert_type == 'INCW':
                incw_ack.add((cs, a.runway, a.subtype))
            if cmac_ack is not None and a.alert_type == 'CMAC':
                cmac_ack.add((cs, a.runway, a.subtype))
            if catc_ack is not None and a.alert_type == 'CATC':
                catc_ack.add((cs, a.related_cs, a.subtype))
            if a.related_cs:
                related.add(a.related_cs)
        # Propagar asuncion al otro movil del par
        for rcs in related:
            for fl in self.flights:
                if fl.callsign == rcs:
                    for a in getattr(fl, 'active_alerts', []):
                        a.acknowledged = True
                        if incw_ack is not None and a.alert_type == 'INCW':
                            incw_ack.add((rcs, a.runway, a.subtype))
                        if cmac_ack is not None and a.alert_type == 'CMAC':
                            cmac_ack.add((rcs, a.runway, a.subtype))
                        if catc_ack is not None and a.alert_type == 'CATC':
                            catc_ack.add((rcs, a.related_cs, a.subtype))
                    break

    def _h_rwy_in_use(self, m, p, f):
        try:
            # Formatos admitidos: {'ad': {ad: rwy, ...}} (Pseudopilot) y {'ad': ad, 'rwy': rwy} (Editor)
            updates = self.change_rwy_in_use(m['ad'], m.get('rwy'))
            for protocol in self.protocol_factory.protocols:
                protocol.sendMessage({'message': 'update_complete_flight', 'complete_flight_updates': updates})
        except:
            logging.warning("Error rwy_in_use", exc_info=True)

    def _h_runway_config_update(self, m, p, f):
        # Guardar config de pistas para evaluacion de alertas
        self._current_pistas_config = m.get('pistas_config', [])
        for protocol in self.protocol_factory.protocols:
            if protocol.client.type == ATC:
                protocol.sendMessage(
                    {'message': 'runway_config_update', 'ad': m['ad'], 'pistas_config': m['pistas_config']})

    # 3. Handlers de Parámetros de Vuelo e Interacción
    def _h_kill(self, m, p, f):
        logging.info("Killing %s" % str(m))
        try:
            self.kill_flight(f)
        except:
            logging.warning("Error killing", exc_info=True)
        self.send_flight(f, self.pseudopilots)
        if p.client.type == ATC: self.send_flight(f, self.controllers)

    def _h_set_cfl(self, m, p, f):
        try:
            p.sendReply(f.set_cfl(m["cfl"]))
            f.lvl_blocked = True
        except:
            logging.warning("Error set_cfl", exc_info=True)

    def _h_set_cfl_c(self, m, p, f):
        try:
            p.sendReply(f.set_cfl_c(m["cfl"]))
        except:
            logging.warning("Error set_cfl_c", exc_info=True)

    def _h_set_rate(self, m, p, f):
        try:
            if m["rate"] == "std":
                f.set_std_rate()
                p.sendReply(True)
            else:
                p.sendReply(f.set_rate_descend(int(m["rate"]), force=m["force"]))
        except:
            logging.warning("Error set_rate", exc_info=True)

    def _h_set_hdg(self, m, p, f):
        try:
            f.set_heading(m["hdg"], m["opt"])
            if m["flagLLZ"]: f.int_ils()
        except:
            logging.warning("Error set_hdg", exc_info=True)

    def _h_set_ias(self, m, p, f):
        try:
            if m["ias"] == "std":
                f.set_std_spd()
                f.ias_blocked = False
            else:
                r = f.set_ias(int(m["ias"]), force=m["force_speed"])
                p.sendReply(r)
                # Velocidad ordenada por ATC y aceptada: no la pisa la reduccion automatica en el LLZ
                f.ias_blocked = bool(r and r[0])
            if f.ias < 80.0 and f.action == 0: f.action = 1
        except:
            logging.warning("Error set_ias", exc_info=True)

    def _h_set_mach(self, m, p, f):
        try:
            if m["mach"] == "std":
                f.set_std_mach()
                f.ias_blocked = False
            else:
                r = f.set_mach(float(m["mach"]), force=m["force_speed"])
                p.sendReply(r)
                f.ias_blocked = bool(r and r[0])
            #self.send_flight(f, self.controllers + self.pseudopilots)
        except:
            logging.warning("Error set_mach", exc_info=True)

    def _h_start(self, m, p, f):
        f.action = 1 if f.action == 0 else 0
        #self.send_flight(f, self.controllers + self.pseudopilots)

    def _h_fire(self, m, p, f):
        f.fire = 1 if f.fire == 0 else 0
        #self.send_flight(f, self.controllers + self.pseudopilots)

    # 4. Handlers de Navegación y Rutas
    def _h_hold(self, m, p, f):
        try:
            f.hold(m.get("fix"), m.get("inbd_track"), m.get("outbd_time"), m.get("std_turns"))
        except:
            logging.warning("Error hold", exc_info=True)

    def _h_change_fpr(self, m, p, f):
        try:
            f.fly_route(m["route"])
            f.set_dest(m["ades"])
            self._maybe_recalc_sector_sequence(f)
        except:
            logging.warning("Error change_fpr", exc_info=True)

    def _h_hdg_after_fix(self, m, p, f):
        try:
            f.hdg_after_fix(aux=m["fix"], hdg=m["hdg"])
        except:
            logging.warning("Error hdg_after_fix", exc_info=True)

    def _h_int_rdl(self, m, p, f):
        try:
            f.int_rdl(aux=m["fix"], track=m["track"])
        except:
            logging.warning("Error int_rdl", exc_info=True)

    def _h_orbit(self, m, p, f):
        try:
            f.orbit(m["direction"])
        except:
            logging.warning("Error orbit", exc_info=True)

    def _h_remove_wp(self, m, p, f):
        try:
            f.remove_wp(m["fix"])
            self._maybe_recalc_sector_sequence(f)
        except:
            logging.warning("Error remove_wp", exc_info=True)

    def _h_toggle_stop(self, m, p, f):
        try:
            f.toggle_stop(m["fix"])
            if f.fix_exe == '_LLZ': f.fix_exe = f.iaf
        except:
            logging.warning("Error toggle_stop", exc_info=True)

    def _h_push_back(self, m, p, f):
        try:
            f.push_back(m["fix"])
        except:
            logging.warning("Error push_back", exc_info=True)

    def _h_final_wp(self, m, p, f):
        try:
            f.final_wp(m["fix"])
        except:
            logging.warning("Error final_wp", exc_info=True)

    def _h_insert_wp(self, m, p, f):
        try:
            f.insert_wp(m["fix"], m["fix_next"], stop=m.get("stop", False), push_back=m.get("push_back", False),
                        fix_after=m.get("fix_after"))
            self._maybe_recalc_sector_sequence(f)
        except:
            logging.warning("Error insert_wp", exc_info=True)

    def _h_replace_wp(self, m, p, f):
        try:
            # El punto antiguo solo se borra si el nuevo se ha podido insertar: si el avion
            # ya habia rebasado fix_old, antes se perdia el punto sin poner ninguno
            if f.insert_wp(m["fix_new"], m["fix_old"], stop=m.get("stop", False),
                           push_back=m.get("push_back", False), fix_after=m.get("fix_after")):
                f.remove_wp(m["fix_old"])
                self._maybe_recalc_sector_sequence(f)
        except:
            logging.warning("Error replace_wp", exc_info=True)

    def _h_route_direct(self, m, p, f):
        try:
            f.route_direct(m["fix"])
        except:
            logging.warning("Error route_direct", exc_info=True)

    def _h_extend_route(self, m, p, f):
        try:
            f.extend_route(m["fix"])
        except:
            logging.warning("Error extend_route", exc_info=True)

    # 5. Handlers de Procedimientos y Aproximación
    def _h_depart(self, m, p, f):
        try:
            f.depart(m['sid'], m['cfl'], m.get('rwy', m.get('pista')), self.t)
        except:
            logging.warning("Error depart", exc_info=True)

    def _h_change_atc_sid(self, m, p, f):
        f.stand_sid_atc, f.lrwy_atc = m['sid'], m['rwy']
        f.ATC_status, f.sid_atc_changed = Aircraft.ATC_MISSING, False
        self.send_strip(f, self.controllers)

    def _h_change_procedure(self, m, p, f):
        ptype = m['procedure_type']
        try:
            if ptype == 'SID':
                f.depart(m['procedure'], f.cfl, m['rwy'], self.t)
                f.stand_sid, f.rdep = m['procedure'], m['rwy']
                self._maybe_recalc_sector_sequence(f)

            elif ptype == 'STAR':
                f.change_star(m['procedure'], m['rwy'], self.t)
                f.lrwy = f.rdes = m['rwy']
        except:
            logging.warning("Error change_procedure", exc_info=True)

    def _maybe_recalc_sector_sequence(self, f):
        """Recalcula sector_sequence si el vuelo es una salida local con sector_sequence."""
        if not f.sector_sequence:
            return
        # Comprobar si f.adep pertenece a algun sector local
        is_local = any(
            f.adep in self.fir.local_ads.get(s, [])
            for s in self.fir.boundaries
        )
        if not is_local:
            return
        new_seq = self._derive_dep_sector_sequence(f)
        if new_seq and new_seq != f.sector_sequence:
            f.sector_sequence = new_seq
            logging.debug("sector_sequence recalculado para %s: %s", f.callsign, new_seq)
            self.send_strip(f, self.controllers)

    def _derive_dep_sector_sequence(self, f):
        """Deriva el sector_sequence de torre para un despegue no preferente.

        Tras f.depart(), la ruta ya tiene la SID nueva. Este metodo usa la
        geometria de fir.boundaries para determinar:
          - El sector LCL: el sector local cuyo limite contiene el primer
            waypoint de la SID (cabecera de pista / fix inicial de salida).
          - Los sectores GMC: los sectores locales que contienen puntos de
            la ruta de rodaje previa a la SID, ordenados por primera aparicion.

        Devuelve la nueva lista [GMC..., LCL] o None si no puede determinarse.
        Funciona para cualquier aeropuerto con limites de sector definidos en el
        Excel de escenario y local_ads correctamente configurado.
        """
        # Sectores locales con limite poligonal definido (al menos 3 puntos)
        local_sectors = {
            s: b for s, b in self.fir.boundaries.items()
            if len(b) >= 3 and f.adep in self.fir.local_ads.get(s, [])
        }
        if not local_sectors:
            return None

        # 1. Posicion del primer waypoint de la SID (inicio de despegue)
        sid_pos = None
        for wp in f.route:
            if wp.fix == f.sid_start:
                try:
                    sid_pos = wp.pos()
                except Exception:
                    pass
                break
        if sid_pos is None:
            return None

        # 2. Sector LCL: sector local cuyo limite contiene el inicio de la SID
        new_lcl = None
        for sector, boundary in local_sectors.items():
            if point_within_polygon(sid_pos, boundary):
                new_lcl = sector
                break
        if new_lcl is None:
            return None

        # 3. Sectores GMC: sectores locales que aparecen en la ruta de rodaje
        #    (waypoints anteriores al inicio de la SID), ordenados por primera aparicion
        sector_first_idx = {}
        for i, wp in enumerate(f.route):
            if wp.fix == f.sid_start:
                break
            try:
                pos = wp.pos()
            except Exception:
                continue
            for sector, boundary in local_sectors.items():
                if sector == new_lcl or sector in sector_first_idx:
                    continue
                if point_within_polygon(pos, boundary):
                    sector_first_idx[sector] = i

        gmc_sectors = sorted(sector_first_idx.keys(), key=lambda s: sector_first_idx[s])

        return gmc_sectors + [new_lcl]

    def _h_change_star(self, m, p, f):
        try:
            rwy = m.get('rwy', m.get('pista'))  # el cliente envia 'pista'
            f.change_star(m['star'], rwy, self.t)
            if rwy:
                f.lrwy = f.rdes = f.desrwy = rwy
        except:
            logging.warning("Error change_star", exc_info=True)

    def _h_execute_map(self, m, p, f):
        try:
            f.execute_map()
        except:
            logging.warning("Error execute_map", exc_info=True)

    def _h_execute_lowpass(self, m, p, f):
        try:
            f.execute_lowpass()
        except:
            logging.warning("Error lowpass", exc_info=True)

    def _h_int_ils(self, m, p, f):
        try:
            f.int_ils()
        except:
            logging.warning("Error int_ils", exc_info=True)

    def _h_dir_fin(self, m, p, f):
        try:
            f.dir_fin()
        except:
            logging.warning("Error dir_fin", exc_info=True)

    def _h_int_arrv(self, m, p, f):
        try:
            f.int_arrv()
        except:
            logging.warning("Error int_arrv", exc_info=True)

    def _h_execute_app(self, m, p, f):
        try:
            f.execute_app(ades=m["ades"], rdes=m["rdes"], iaf=m["iaf"])
            f.lrwy = f.lrwy_atc = f.desrwy = f.rdes = m["rdes"]
            f.iaf, f.ades = m["iaf"], m["ades"]
            if f.fix_exe == '_LLZ': f.fix_exe = m["iaf"]
        except:
            logging.warning("Error app", exc_info=True)

    def _h_change_app_rwy(self, m, p, f):
        try:
            f.change_lnd(ades=m["ades"], pista=m["rdes"])
        except:
            logging.warning("Error change_app_rwy", exc_info=True)

    # 6. Handlers de Lógica ATC / Strips
    def _h_preact(self, m, p, f):
        f.preact = m['preact']

    def _h_act(self, m, p, f):
        f.act = m['act']

    def _h_correlado(self, m, p, f):
        f.correlado = m['correlado']

    def _h_pedir_trf(self, m, p, f):
        f.pedir_trf = True
        self.send_strip(f, self.controllers)

    def _h_assume(self, m, p, f):
        # LOGICA PARA CONTROLADORES (ATC)
        if p.client.type == ATC:
            # Caso A: El avion no tiene sector o esta en transferencia (release)
            if f.atc_sector == None or f.release_atc_pos:
                sector_list = m['sector'].split(",")
                i_sector = -1

                # Buscamos la coincidencia exacta con tu doble bucle original
                for seq_sector in f.sector_sequence:
                    for sector in sector_list:
                        if sector == seq_sector:
                            i_sector = f.sector_sequence.index(sector)

                if i_sector == -1:  # Asume alguien fuera de la secuencia
                    f.atc_sector = sector_list[0]
                    f.next_atc_sector = None
                else:
                    f.atc_sector = f.sector_sequence[i_sector]
                    if i_sector < len(f.sector_sequence) - 1:
                        f.next_atc_sector = f.sector_sequence[i_sector + 1]
                    else:
                        f.next_atc_sector = None

                f.trans_atc_pos = False
                f.pedir_trf = False
                f.release_atc_pos = False

                try:
                    self.send_strip(f, self.controllers)
                except:
                    logging.warning("Error enviando strip tras assume ATC", exc_info=True)

            # Caso B: Segundo click (Transferencia silenciosa / Release)
            elif m['sector'].find(f.atc_sector) >= 0 and not f.release_atc_pos:
                f.trans_atc_pos = False
                f.release_atc_pos = True
                try:
                    self.send_strip(f, self.controllers)
                except:
                    logging.warning("Error enviando strip tras release ATC", exc_info=True)

        # LOGICA PARA PSEUDOPILOTOS
        else:
            if m['assumed']:
                # Asignacion de posicion de pseudopiloto antes de send_strip a controladores
                f.pp_pos = p.client.number
                f.trans_pp_pos = False
                
                # LLogica especifica LEMD / LEBL
                #if f.pp_pos == None and (f.OSF_pof == Aircraft.PREPARING): -> Ahora ya no necesitamos comprobar pp_pos == None porque ya asignamos pp_pos antes
                if f.OSF_pof == Aircraft.PREPARING:
                    # Parametros de escenario (antes fir.name in ('LEMD', 'LEBL') / == 'LEMD')
                    if self.fir.param('pp_asumir_arranca', False):
                        f.set_osf_pof(Aircraft.STARTING)
                        if len(f.sector_sequence) > 0:
                            f.next_atc_sector = f.sector_sequence[0]
                        f.release_atc_pos = True
                        f.ATC_status = Aircraft.ATC_OK

                    rodaje_salvo = self.fir.param('pp_asumir_rodaje_salvo', [])
                    if rodaje_salvo and len(f.sector_sequence) > 0:
                        if FIR._normalize_sector(f.sector_sequence[0]) not in rodaje_salvo:
                            f.set_osf_pof(Aircraft.TAXIING_OUT)

                    try:
                        self.send_strip(f, self.controllers)
                    except:
                        logging.warning("Error enviando strip tras assume PP", exc_info=True)

                # Asignacion de posicion de pseudopiloto
                #f.pp_pos = p.client.number
                #f.trans_pp_pos = False

    def _h_transfer(self, m, p, f):
        if p.client.type == ATC:
            f.next_atc_sector, f.trans_atc_pos, f.release_atc_pos = m['sector'], True, True
            self.send_strip(f, self.controllers)
        else:
            f.trans_pp_pos = True

    def _h_transfer_obstaculo(self, m, p, f):
        msg = {'message': 'receive_obstaculo', 'sector_destino': m.get('sector_destino'),
               'obstaculo_texto': m.get('obstaculo_texto', ''), 'obstaculo_color': m.get('obstaculo_color', '#ffffff')}
        for protocol in self.protocol_factory.protocols:
            if hasattr(protocol, 'client') and protocol.client.type == ATC:
                protocol.sendMessage(msg)

    def _h_set_osf_pof(self, m, p, f):
        new_pof = m["osf_pof"]
        f.set_osf_pof(new_pof)
        if "hacc" in m: f.set_hacc(m["hacc"])
        # Fin del flujo CRU: limpiar atributos al restaurar fase taxi
        if new_pof in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN) and getattr(f, 'pre_cru_pof', None):
            f.pre_cru_pof = None
            f.cru_runway = None
        # Fin del flujo ENT (vehiculos): limpiar atributos al restaurar fase taxi
        if new_pof in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN) and getattr(f, 'pre_ent_pof', None):
            f.pre_ent_pof = None
            f.ent_runway = None
        self.send_strip(f, self.controllers)

    def _h_request_cru(self, m, p, f):
        """Pseudopiloto o controlador solicita cruce de pista."""
        runway = m.get('runway', '')
        if f.OSF_pof not in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
            return
        # VEH ahora tambien puede solicitar CRU (antes solo usaba ENT)
        f.pre_cru_pof = f.OSF_pof
        f.cru_runway = runway
        f.set_osf_pof(Aircraft.CRUREQ)
        self.send_strip(f, self.controllers)

    def _h_cancel_cru(self, m, p, f):
        """Pseudopiloto cancela solicitud CRU (error)."""
        if f.OSF_pof != Aircraft.CRUREQ:
            return
        restore = getattr(f, 'pre_cru_pof', None) or Aircraft.TAXIING_OUT
        f.set_osf_pof(restore)
        f.pre_cru_pof = None
        f.cru_runway = None
        self.send_strip(f, self.controllers)

    def _h_create_pvh(self, m, p, f):
        """Controlador crea Plan de Vehiculo."""
        if getattr(f, 'fr', None) != 'VEH':
            return
        f.has_pvh = True
        f.pvh_notes = m.get('notes', '')
        f.set_osf_pof(Aircraft.TAXIING_OUT)
        sector_list = m['sector'].split(",")
        f.atc_sector = sector_list[-1]
        f.trans_atc_pos = False
        f.release_atc_pos = False
        self.send_strip(f, self.controllers)

    def _h_delete_pvh(self, m, p, f):
        """Controlador elimina Plan de Vehiculo."""
        f.has_pvh = False
        f.pvh_notes = ""
        f.ent_runway = None
        f.pre_ent_pof = None
        f.set_osf_pof(None)
        self.send_strip(f, self.controllers)

    def _h_authorize_ent(self, m, p, f):
        """Controlador autoriza entrada a pista (vehiculo)."""
        if not getattr(f, 'has_pvh', False):
            return
        if f.OSF_pof not in (Aircraft.TAXIING_OUT, Aircraft.ENTREQ):
            return
        f.ent_runway = m.get('runway', '')
        if f.pre_ent_pof is None:
            f.pre_ent_pof = Aircraft.TAXIING_OUT
        f.set_osf_pof(Aircraft.ENTERING)
        self.send_strip(f, self.controllers)

    def _h_request_ent(self, m, p, f):
        """Controlador solicita entrada a pista (paso intermedio ENR amarillo)."""
        if not getattr(f, 'has_pvh', False):
            return
        if f.OSF_pof != Aircraft.TAXIING_OUT:
            return
        runway = m.get('runway', '')
        f.pre_ent_pof = f.OSF_pof
        if runway:
            f.ent_runway = runway
        f.set_osf_pof(Aircraft.ENTREQ)
        self.send_strip(f, self.controllers)

    def _h_set_pvh_notes(self, m, p, f):
        """Controlador edita observaciones del PVH."""
        if getattr(f, 'has_pvh', False):
            f.pvh_notes = m.get('notes', '')
            self.send_strip(f, self.controllers)

    def _h_set_osf_warning(self, m, p, f):
        f.set_osf_warning(m["osf_warning"])
        self.send_strip(f, self.controllers)

    def _h_set_next_atc_sector(self, m, p, f):
        f.set_next_atc_sector(m["next_atc_sector"])
        self.send_strip(f, self.controllers)

    def _h_set_atc_status(self, m, p, f):
        f.set_atc_status(m["atc_status"])
        self.send_strip(f, self.controllers)

    def _h_set_ecl(self, m, p, f):
        f.set_ecl(m["ecl"])

    def _h_set_eclfix(self, m, p, f):
        f.set_eclfix(m["eclfix"])

    def _h_set_rfl(self, m, p, f):
        f.set_rfl(m["rfl"])

    def _h_set_tfl(self, m, p, f):
        f.set_tfl(m["tfl"])

    def _h_set_echo(self, m, p, f):
        f.campo_eco = m["echo"]

    def _h_set_trans(self, m, p, f):
        if m["trans"] == 'IDE':
            self.squawk_ident(f, self.controllers + self.pseudopilots)
        else:
            f.campo_trans = m["trans"]

    def _h_set_rutrod(self, m, p, f):
        f.rutrod = m["rutrod"]
        self.send_strip(f, self.controllers)

    def _h_set_park(self, m, p, f):
        f.park = m["park"]
        self.send_strip(f, self.controllers)

    def _h_set_gate(self, m, p, f):
        f.gate = m["gate"]
        self.send_strip(f, self.controllers)

    def _h_set_holdp(self, m, p, f):
        f.holdp = m["holdp"]
        self.send_strip(f, self.controllers)

    def _h_set_sid_check(self, m, p, f):
        f.sid_check = m["sid_check"]
        self.send_strip(f, self.controllers)

    def _h_set_hrls(self, m, p, f):
        f.hrls = m["hrls_status"]
        self.send_strip(f, self.controllers)

    def _h_set_client_sector(self, m, p, f):
        """Registra el sector del cliente conectado."""
        if hasattr(p, 'client') and p.client is not None:
            p.client.sector = m.get('sector', '?')
            logging.info("Client sector set to: %s" % p.client.sector)

    #### Fin prueba nuevo controlador de mensajes. Sin broadcast global automático.


    def change_rwy_in_use(self, ads, rwy_direction_desig=None):
        """Modifies the rwy in use for the given airports, and
        changes the SID and STAR procedures for the relevant aircraft.
        ads: {ad_code_id: rwy_desig} para varios aerodromos, o (compatibilidad)
        ads=ad_code_id y rwy_direction_desig=rwy_desig."""
        if not isinstance(ads, dict):
            ads = {ads: rwy_direction_desig}
        changed = {}
        for ad_code_id, rwy_desig in ads.items():
            rwy_desig = str(rwy_desig)
            try:
                ad = self.fir.aerodromes[ad_code_id]
                rwy_direction = [rwy for rwy in ad.rwy_direction_list if rwy.txt_desig == rwy_desig][0]
            except (KeyError, IndexError):
                logging.error("No runway direction %s defined for airport %s" % (rwy_desig, ad_code_id), exc_info=True)
                continue
            ad.rwy_in_use = rwy_direction
            Aircraft.fir.aerodromes[ad_code_id].rwy_in_use = rwy_direction
            changed[ad_code_id] = rwy_desig

        complete_flight_updates = []
        for flight in self.flights:
            handled = False
            # Cambiamos de pista si no hemos salido del stand y si es pista de salida
            if flight.adep in changed and self.fir.AdHasIfrRwys(flight.adep) and flight.rdep != changed[flight.adep]:
                ad = self.fir.aerodromes[flight.adep]
                if len(ad.rwy_in_use.dep_dict) > 0:
                    try:
                        dep = ad.rwy_in_use.dep_dict[flight.park]
                    except:
                        dep = ad.rwy_in_use.dep_dict[random.choice(list(ad.rwy_in_use.dep_dict.keys()))]

                    if dep.rte[0] == flight.route[0]:  # Solo modifico automaticamente si sigue en el parking
                        if flight.rdep != '':
                            flight.rdep = flight.deprwy = changed[flight.adep]  # antes se escribia desrwy

                        if flight.fr == 'VEH':
                            flight.complete_flight_plan(False)
                            flight.final_wp(flight.sid_start)
                            flight.remove_wp(flight.sid_start)
                            flight.stand_sid = ''
                            flight.stand_sid_atc = ''
                        else:
                            flight.complete_flight_plan(True)

                        complete_flight_updates.append(flight)
                        handled = True
            # Cambiamos de pista si no hemos llegado a la STAR y si es pista de llegada
            # (tambien si el destino ha cambiado y la salida no se ha podido aplicar)
            if not handled and flight.ades in changed and self.fir.AdHasIfrRwys(flight.ades) and flight.rdes != changed[flight.ades]:
                ad = self.fir.aerodromes[flight.ades]  # antes se usaba el 'ad' de la iteracion anterior
                if len(ad.rwy_in_use.lnd_dict) > 0:
                    if flight.star is not None and flight.star.start_fix not in flight.log:
                        if flight.rdes != '':
                            flight.rdes = flight.lrwy = flight.desrwy = changed[flight.ades]
                        flight.complete_flight_plan(True)
                        complete_flight_updates.append(flight)

        for c in self.pseudopilots:
            for ad_code_id, rwy_desig in changed.items():
                m = {"message": "rwy_in_use", "ad": ad_code_id, "rwy": rwy_desig}
                c.protocol.sendMessage(m)
        return complete_flight_updates

    def kill_flight(self, f):
        print ('killing flight ' + f.callsign)
        self.flights.remove(f)
        for c in self.pseudopilots+self.controllers:
            m = {"message": "kill_flight", "cs": f.callsign}
            c.protocol.sendMessage(m)

    def send_flight(self, f, clients):
        """Update a specific flight on the given clients"""
        for c in clients:
            m = {"message": "update_flight", "flight": f}
            c.protocol.sendMessage(m)

    def send_strip(self, f, clients):
        """Update a specific flight on the given clients"""
        for c in clients:
            m = {"message": "update_strip", "flight": f}
            c.protocol.sendMessage(m)

    def squawk_ident(self, f, clients):
        """Update a specific flight on the given clients"""
        for c in clients:
            m = {"message": "squawk_ident", "flight": f}
            c.protocol.sendMessage(m)


    def exit(self):
        # Close connection with all connected clients
        for p in self.protocol_factory.protocols:
            p.transport.loseConnection()

        try:
            self.listening_port.stopListening()
        except:
            logging.warning("Unable to stop listening to port", exc_info=True)
        self.cont = False
        del self.protocol_factory.gta

        self.tlpv.exit()

    def __del__(self):
        logging.debug("GTA.__del__")

class Client:
    """Holds data about each of the connected clients"""
    # TODO there is some overlap between information of the protocols
    # and information on these objects. It should probably be rethought and
    # most likely put everything here

    def __init__(self, gta):
        self.gta = gta
        self.number = None  # Identifies the client position number (used to track who controls or pilots a specific flight)
        self.type = None  # ATC or PSEUDOPILOT
        self.sector = None  # Which sector is the client connected to
        self.protocol = None  # The protocol throught which we are talking to this client
        self.t = None  # The last time sent

    def exit(self):
        # Guardar estado antes de desconectar
        try:
            self.protocol.sendMessage({"message": "save_state"})
            logging.info("Solicitado guardado de estado al cliente %d antes de desconectar" % self.number)
        except:
            logging.warning("No se pudo solicitar guardado al cliente %d durante desconexión" % self.number)
        
        if self.type == ATC:
            self.gta.controllers.remove(self)
        else:
            self.gta.pseudopilots.remove(self)
        del(self.protocol)
        del(self.gta)

    def __del__(self):
        logging.debug("Client.__del__")


class GTA_Protocol(NetstringReceiver):

    # TODO Pickle is not secure across a network by default
    # I believe it is possible to limit from which modules are classes
    # unpickled. We should implement those limits.

    def __init__(self):
        self._deferred = None
        self.command_no = None  # The current command number. Used in replies
        # COLA DE MENSAJES PARA PROCESARLOS SECUENCIALMENTE
        self._message_queue = []
        self._processing_message = False

    def connectionMade(self):
        logging.debug("Sending hello")
        self.sendMessage({"message": "hello"})

    def sendMessage(self, m):
        if sys.version_info[0] == 2 and sys.version_info[1] < 7:
            line = pickle.dumps(m, protocol=-1)  # Use the highest protocol version available
        else:
            line = dill.dumps(m)  # Use the highest protocol version available
        zline = zlib.compress(line)
        self.sendString(zline)
        # logging.debug("Sending %d characters"%len(zline))

    def sendReply(self, m):
        m2 = {"message": "reply", "command_no": self.command_no, "data": m}
        self.sendMessage(m2)

    def connectionLost(self, reason):
        if self._deferred is not None:
            self._deferred.cancel()
        
        # Guardar estado antes de perder la conexión
        try:
            self.sendMessage({"message": "save_state"})
            logging.info("Solicitado guardado de estado al cliente %s %d antes de perder conexion" % (self.client.type, self.client.number))
        except:
            logging.debug("No se pudo solicitar guardado durante perdida de conexión")
        
        logging.info("Connection lost to %s client %d" % (self.client.type, self.client.number))
        logging.debug(reason)
        try:
            self.factory.protocols.remove(self)
        except:
            logging.debug("Protocol "+str(id(self))+" already removed")
        try:
            self.client.exit()
        except:
            logging.debug("Client already removed", exc_info=True)
        del(self.client)
        # if self.factory.master_protocol==self:
        # logging.debug("The master connection has been lost. Cleaning up")
        # self.factory.gta.exit()

    """
    def stringReceived(self, line):
        line = zlib.decompress(line)
        try:
            if sys.version_info[0] == 2 and sys.version_info[1] < 7:
                m = pickle.loads(line)
            else:
                m = dill.loads(line)
        except:
            logging.error("Unable to unpickle client message")
            return

        self.command_no = m["command_no"]
        try:
            self.factory.gta.process_message(m["data"], self)
        except:
            return
    """

    def stringReceived(self, line):
        from twisted.internet import threads

        def deserialize_in_thread(compressed_line):
            decompressed = zlib.decompress(compressed_line)
            if sys.version_info[0] == 2 and sys.version_info[1] < 7:
                return pickle.loads(decompressed)
            else:
                return dill.loads(decompressed)
            
        def process_next_message():
            if not self._message_queue or self._processing_message:
                return
            
            self._processing_message = True
            m = self._message_queue.pop(0)
            
            self.command_no = m["command_no"]
            try:
                self.factory.gta.process_message(m["data"], self)
            except:
                pass
            
            self._processing_message = False
            process_next_message()  # Siguiente mensaje

        def on_deserialized(m):
            self._message_queue.append(m)
            process_next_message()
    
        # Deserializar en thread, pero procesar secuencialmente
        d = threads.deferToThread(deserialize_in_thread, line)
        d.addCallback(on_deserialized)
        d.addErrback(lambda failure: logging.error("Unable to unpickle: %s" % failure))

    # TODO Protocols don't seem to be garbage collected
    def __del__(self):
        logging.debug("GTA_Protocol.__del__")


class GTA_Protocol_Factory(Factory):

    protocol = GTA_Protocol  # Magic assignment necessary for twisted protocol factories
    protocols = []  # Internal variable used by GTA

    # def __init__(self, gta, fir_file, tlpv, sector, flights):
    def __init__(self, gta):
        self.gta = gta
        # self.fir_file = fir_file
        # self.tlpv = tlpv
        # self.sector = sector
        # self.flights = flights

    # TODO The Protocol Factory doesn't seem to be garbage collected
    def __del__(self):
        logging.debug("GTA_Protocol_Factory.__del__")
