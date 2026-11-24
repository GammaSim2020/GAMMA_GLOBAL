#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: UCS.py 2382 2007-06-01 17:19:14Z rodrigo $
#
#
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
"""Classes used by the air traffic controller's interface of GAMMA"""

import logging
from doctest import master
from RaDisplay import *  # This also imports all RaElements classes
import Aircraft
import Route
from RaElements import ATCBahia


def _reciprocal_rwy(des):
    """Pista reciproca: '06L' -> '24R', '02' -> '20', '13' -> '31'."""
    try:
        num = ''.join([ch for ch in des if ch.isdigit()])
        suf = des[len(num):].upper()
        rnum = (int(num) + 18) % 36 or 36
        rsuf = {'L': 'R', 'R': 'L'}.get(suf, suf)
        return '%02d%s' % (rnum, rsuf)
    except:
        return des



class UCS(RaDisplay):
    """Air Traffic Controllers' radar display and user interface"""

    def __init__(self, conf, title, icon_path, fir, tlpv, sector, flights, disp_number, mode='atc',
                 display_remote=None):
        """Instantiate an ATC Radar Display
        title - window title
        icon_path - path to the windows task bar icon
        fir -- fir object
        sector -- name of the sector to work with
        """
        self.display_remote = display_remote
        self.conf = conf
        self.toolbar_height = 60  # Pseudopilot display toolbar height
        self._flights_tracks = {}
        self._tracks_flights = {}
        layout_str = "Layout" + str(disp_number)
        sector = self.conf.read_option(layout_str, "sector", sector, 'string')
        self.sector = sector
        self.mode = mode
        self.smrOn = False
        self._falt_enabled = False

        RaDisplay.__init__(self, self.conf, title, icon_path, fir, tlpv, sector, self.toolbar_height, disp_number)

        # Inicializar presets de escala F1/F2 (heredados de RaDisplay pero no inicializados alli)
        self.f1scale = self.scale
        self.f1center_x = self.center_x
        self.f1center_y = self.center_y
        self.f2scale = self.scale
        self.f2center_x = self.center_x
        self.f2center_y = self.center_y

        self.flights = flights
        for f in self.flights:
            vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
            vt.adep = f.adep
            vt.ades = f.ades
            vt.local_dep = self._is_local_ad(vt.adep)
            vt.local_des = self._is_local_ad(vt.ades)
            vt.ades_has_ifr = self.fir.AdHasIfrRwys(f.ades)
            vt.adep_has_ifr = self.fir.AdHasIfrRwys(f.adep)
            # Setting mode implicitly configures label
            vt.rules = f.fr
            vt._has_pvh = getattr(f, 'has_pvh', False)
            if self.correlar_off:
                vt.mode = 'atc-nocorrel'
            else:
                vt.mode = 'atc'
            vt.l_font_size = self.label_font_size
            vt.cfl = f.cfl
            self.tracks.append(vt)
            self._flights_tracks[f] = vt
            self._tracks_flights[vt] = f

        self._flights_by_cs = {f.callsign: f for f in self.flights}
        self.killed_flights = set()
        self.landed_flights = []
        self.fs_zone = {}
        self.fs_line = {}
        self.t = datetime.datetime.today()
        self.synchronised = False
        self.last_update = self.t - datetime.timedelta(seconds=5)
        self.last_update_aire = self.t - datetime.timedelta(seconds=5)

        self.routes = []  # List of tracks whose routes are displayed
        self.waypoints = []  # List of tracks whose waypoints are displayed 
        self.current_runway_config = [] #Actual runways states

        self.speed_vector_var = tix.IntVar()
        self.speed_vector_var.set(0)
        self.clock_speed_var = tix.DoubleVar()
        self.clock_speed_var.set(1.0)

        self.l1_onoff_var = tix.BooleanVar()
        self.l1_onoff_var.set(True)

        self.l2_onoff_var = tix.BooleanVar()
        self.l2_onoff_var.set(True)

        self.l3_onoff_var = tix.BooleanVar()
        self.l3_onoff_var.set(True)

        self.l4_onoff_var = tix.BooleanVar()
        self.l4_onoff_var.set(False)

        self.wake_oaci_var = tix.BooleanVar()
        self.wake_oaci_var.set(True)  # Activo por defecto

        self.wake_recat_var = tix.BooleanVar()
        self.wake_recat_var.set(False)  # Inactivo por defecto

        self.toolbar = ventana_auxiliar(self)

        # Restore local map visibility from Layout<n> (single source of truth)
        for map_name in self.fir.local_maps:
            self.toolbar.var_ver_localmap[map_name].set(
                self.conf.read_option(layout_str, map_name, False, "bool"))
        self.toolbar.b_show_hide_localmaps()

        self.update_tracks()

        offset = 0
        delta = 5

        self.giw = GeneralInformationWindow(self, fir.sectors, sector.split(','), position=(219, -11))
        offset += delta
        # self.clock=RaClock(self.c,position=[offset, offset])
        self.clock = RaClock(self.c, position=[1700, 40])
        self.clock.configure(time='%02d:%02d:%02d' % (self.t.hour, self.t.minute, self.t.second))
        offset += delta

        self.windrose = RaWindRose(self.c, position=[0, 0])
        self.windrose.configure(wind_spd='20', wind_dir=0.0, metar='')
        offset += delta

        self.coor_tabular = CoorTabular(self, self.c, mode='atc', position=[240, 40])
        self.coor_tabular.adjust(0, 32, 0, 0)
        self.preact_tabular = PreactTabular(self, self.c, mode='atc', position=[750, 40])
        self.preact_tabular.adjust(0, 32, 0, 0)
        self.act_tabular = ActTabular(self, self.c, mode='atc', position=[1240, 40])
        self.act_tabular.adjust(0, 32, 0, 0)

        # self.lcl_sector_list = [lcl for lcl in self.sector_list if "TWR" in lcl]
        # Parametros de escenario 'sob_tabular' (por defecto LEPA) y 'smr_ad' (por defecto LEST)
        if self.fir.param('sob_tabular', False):
            self.sob_tabular = SobTabular(self, self.c, mode='atc', position=[1300, 300])
            self.sob_tabular.adjust(0, 20, 0, 0)
        if self.fir.param('smr_ad', ''):
            self.alarmNoCorr_tab = AlarmNoCorrTabular(self, self.c, mode='atc', position=[240, 200])
            self.alarmNoCorr_tab.adjust(0, 20, 0, 0)

        self.display_remote = []

        self.bahia_type = None

        logging.info("UCS __init__: sector=%r mode=%r sacta_mode=%r",
                     self.sector, self.mode,
                     self.fir.sacta_mode.get(self.sector.split(',')[0], 'KEY_NOT_FOUND'))
        if self.fir.sacta_mode[self.sector.split(',')[0]] != 'OSF':
            if self.mode != 'pp' and self.disp_number == 1:
                self.atc_bahia = ATCBahia(self)
                # Recuperar visibilidad y posicion/tamano de la bahia guardados al salir
                # (save_state los escribia pero nunca se leian; de GAMMA)
                try:
                    _ly = "Layout" + str(self.disp_number)
                    _geo = self.conf.read_option(_ly, "atc_bahia_geometry", '', 'string')
                    if _geo and not _geo.startswith('0x0') and not _geo.startswith('1x1'):
                        self.atc_bahia.wm_geometry(_geo)
                    if not self.conf.read_option(_ly, "atc_bahia", True, "bool"):
                        self.atc_bahia.hide()
                except Exception:
                    logging.warning("No se ha podido recuperar la bahia de fichas", exc_info=True)

        if self.fir.sacta_mode[self.sector.split(',')[0]] == 'OSF':
            self.lcl_sector_list = []
            self.gnd_sector_list = []
            role_gnd = role_lcl = role_clr = False

            for sector in self.sector.split(','):
                if (sector.find('GND') > -1) or (sector.find('GMC') > -1):
                    self.gnd_sector_list.append(sector)
                    role_gnd = True
                if (sector.find('LCL') > -1) or (sector.find('TWR') > -1):
                    self.lcl_sector_list.append(sector)
                    role_lcl = True
                if (sector.find('CLD') > -1) or (sector.find('CLR') > -1):
                    role_clr = True

            if role_gnd and role_lcl:
                self.bahia_type = 'GND+LCL'
            elif role_clr and role_gnd:
                self.bahia_type = 'GND+CLR'
            elif role_gnd:
                self.bahia_type = 'GND'
            elif role_lcl:
                self.bahia_type = 'LCL'
            elif role_clr:
                self.bahia_type = 'CLR'

            if self.bahia_type is None:
                return

            if self.disp_number == 1:
                # primera pantalla: crea (o recrea) la instancia
                self.fichas_tabular = OSF.get_instance(self, self.bahia_type)
                self.display_remote.append(self.fichas_tabular)
                # PrevDesp aparece en roles con responsabilidad GND o CLR.
                # En escenarios con CLR explícito: CLR, GND+CLR.
                # En escenarios sin CLR (ej. LEST): GND, GND+LCL asumen esa función.
                if self.bahia_type in ('CLR', 'GND+CLR', 'GND', 'GND+LCL'):
                    self.predesp_tabular = PrevDesp.get_instance(self, 'CLR')
                    self.display_remote.append(self.predesp_tabular)
            else:
                # Pantallas siguientes: reutilizan la instancia ya creada, sin abrir ventana nueva
                live = next((inst for inst in OSF._instances.values()
                             if hasattr(inst, 'root') and inst.root.winfo_exists()), None)
                if live is not None:
                    self.fichas_tabular = live

        # Binding para cerrar popups de OSF al hacer click en el canvas de UCS
        def _close_osf_popups_on_ucs_click(event):
            """Cierra los popups de OSF cuando se hace click en el canvas de UCS"""
            if hasattr(self, 'fichas_tabular') and self.fichas_tabular:
                try:
                    # No cerrar si los popups se acaban de abrir
                    if not getattr(self.fichas_tabular, "_popup_just_opened", False):
                        self.fichas_tabular._close_all_popups()
                except:
                    pass
        
        # Añadir binding A TODAS LAS PANTALLAS UCS
        if hasattr(self, 'fichas_tabular') and self.fichas_tabular:
            self.c.bind("<Button-1>", _close_osf_popups_on_ucs_click, add="+")

 
        if not self.fir.param('tabulares_aux', True):  # parametro de escenario (por defecto ocultas en LEMD y LEBL)
            self.coor_tabular.hide()
            self.preact_tabular.hide()
            self.act_tabular.hide()

        self.reposition()
        self.toolbar.redraw()
        self.update_tracks()
        self.redraw()
        self.separate_labels()
        # F7: imprimir en la bahia de fichas la ficha del vuelo seleccionado (posiciones sin OSF)
        self.c.master.bind('<F7>', self.imprimir_ficha)

    def _is_local_ad(self, ad):
        """True si el aerodromo es local para alguno de los sectores de esta posicion.
        Admite posiciones multisector ('A,B') y sectores ausentes en local_ads."""
        return any(ad in self.fir.local_ads.get(s.strip(), []) for s in self.sector.split(','))

    def imprimir_ficha(self, e=None):
        for radisp in self.master.display:
            if radisp.selected_flight != None and hasattr(radisp, 'atc_bahia'):
                radisp.atc_bahia.insertar_ficha(self.selected_flight)

    def process_message(self, m):
        if m['message'] == 'runway_config_update':
            """Procesar actualizacion de configuracion de pistas"""
            self.update_runway_maps(m['ad'], m['pistas_config'])
            return
        """
        if m['message'] == 'receive_obstaculo':
            Recibir obstáculo transferido desde otro sector
            try:
                sector_destino = m.get('sector_destino', '')
                
                # Verificar si este obstáculo es para mi sector
                # self.sector puede ser "GMC GN" o "GMC GN,LCL ARR"
                mis_sectores = [s.strip() for s in self.sector.split(',') if s.strip()]
                
                if sector_destino in mis_sectores:
                    if hasattr(self, 'fichas_tabular') and self.fichas_tabular:
                        obstaculo_texto = m.get('obstaculo_texto', '')
                        obstaculo_color = m.get('obstaculo_color', '#ffffff')
                        self.fichas_tabular.receive_transferred_obstaculo(obstaculo_texto, obstaculo_color)
                        logging.info("Obstáculo '%s' recibido para mi sector %s" % (obstaculo_texto, sector_destino))
                else:
                    logging.debug("Obstáculo ignorado - es para sector '%s', yo soy '%s'" % (sector_destino, self.sector))
            except Exception as e:
                logging.warning("Error recibiendo obstáculo transferido: %s" % str(e))
            return
        """
        if m['message'] == 'receive_obstaculo':
            """Recibir obstáculo transferido desde otro sector"""
            try:
                from twisted.internet import reactor

                obstaculo_texto = m.get('obstaculo_texto', '')
                obstaculo_color = m.get('obstaculo_color', '#ffffff')
                sector_destino = m.get('sector_destino', '')

                # Verificar si este obstáculo es para mi sector
                mis_sectores = [s.strip() for s in self.sector.split(',') if s.strip()]
                if sector_destino not in mis_sectores:
                    logging.debug("Obstáculo ignorado - es para sector '%s', yo soy '%s'" % (sector_destino, self.sector))
                    return

                # Usar el OSF (singleton) para acumular obstáculos (compartido entre displays)
                if not hasattr(self, 'fichas_tabular') or not self.fichas_tabular:
                    return

                osf = self.fichas_tabular

                # Crear lista temporal en OSF si no existe
                if not hasattr(osf, '_pending_obstaculos'):
                    osf._pending_obstaculos = []

                # Agregar este obstáculo a la lista
                obst_data = (obstaculo_texto, obstaculo_color, sector_destino)
                osf._pending_obstaculos.append(obst_data)

                # Procesar después de un pequeño delay (para acumular duplicados)
                def process_accumulated():
                    if not hasattr(osf, '_pending_obstaculos') or not osf._pending_obstaculos:
                        return

                    # Eliminar duplicados (quedarse con uno solo de cada)
                    unique_obstaculos = list(set(osf._pending_obstaculos))

                    # Procesar cada obstáculo único
                    for obst_texto, obst_color, sector_dest in unique_obstaculos:
                        osf.receive_transferred_obstaculo(obst_texto, obst_color)
                        logging.info("Obstáculo '%s' recibido para mi sector %s" % (obst_texto, sector_dest))

                    # Limpiar lista
                    osf._pending_obstaculos = []

                # Cancelar timer anterior si existe
                if hasattr(osf, '_obst_timer') and osf._obst_timer:
                    try:
                        osf._obst_timer.cancel()
                    except:
                        pass
                    
                # Programar procesamiento después de 0.1 segundos
                osf._obst_timer = reactor.callLater(0.1, process_accumulated)

            except Exception as e:
                logging.warning("Error recibiendo obstáculo transferido: %s" % str(e))
            return

        def update_flight(new):
            if new.callsign in self.killed_flights:
                return
            # Check whether this is a new flight
            if new.callsign not in self._flights_by_cs:
                vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
                vt.adep = new.adep
                vt.ades = new.ades
                sector_list = self.sector.split(",")
                vt.local_dep = False
                vt.local_des = False
                #for sector in sector_list:
                #    if (vt.adep in self.fir.local_ads[sector]):
                #        vt.local_dep = (vt.adep in self.fir.local_ads[sector])
                vt.local_dep = self._is_local_ad(vt.adep)
                vt.local_des = self._is_local_ad(vt.ades)
                vt.ades_has_ifr = self.fir.AdHasIfrRwys(new.ades)
                vt.adep_has_ifr = self.fir.AdHasIfrRwys(new.adep)

                #  vt.local_des = (vt.ades in self.fir.local_ads[self.sector])
                # Fijar line_onoff ANTES de que vt.mode dispare el primer redraw
                if getattr(self, '_cached_values_ready', False):
                    vt.line_onoff = list(self._cached_line_onoff)
                else:
                    vt.line_onoff = [self.l1_onoff_var.get(), True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(), True]
                # Setting mode implicitly configures label
                vt._has_pvh = getattr(new, 'has_pvh', False)
                if self.correlar_off:
                    vt.mode = 'atc-nocorrel'
                else:
                    vt.mode = 'atc'
                vt.l_font_size = self.label_font_size
                vt.cfl = new.cfl

                self.tracks.append(vt)
                self._flights_tracks[new] = vt
                self._tracks_flights[vt] = new
                self.flights.append(new)
                self._flights_by_cs[new.callsign] = new
                return new

            else:  # Otherwise we are updating
                old = self._flights_by_cs[new.callsign]
                for name, value in new.__dict__.items():
                    setattr(old, name, value)
                return old

        def reload_flights(flights, time):

            self.clock.configure(time='%02d:%02d:%02d' % (time.hour, time.minute, time.second))
            self.last_update = time - datetime.timedelta(seconds=5)
            self.last_update_aire = time - datetime.timedelta(seconds=5)

            for vt in self._tracks_flights:
                vt.destroy()

            self.flights = flights

            self.tracks = []
            self._flights_tracks = {}
            self._tracks_flights = {}

            for f in self.flights:
                vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
                vt.adep = f.adep
                vt.ades = f.ades
                # Con posiciones multisector ('A,B') self.sector no es clave de local_ads (KeyError)
                vt.local_dep = self._is_local_ad(vt.adep)
                vt.local_des = self._is_local_ad(vt.ades)
                vt.ades_has_ifr = self.fir.AdHasIfrRwys(f.ades)
                vt.adep_has_ifr = self.fir.AdHasIfrRwys(f.adep)
                # Fijar line_onoff ANTES de que vt.mode dispare el primer redraw
                if getattr(self, '_cached_values_ready', False):
                    vt.line_onoff = list(self._cached_line_onoff)
                else:
                    vt.line_onoff = [self.l1_onoff_var.get(), True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(), True]
                # Setting mode implicitly configures label
                vt.rules = f.fr
                vt._has_pvh = getattr(f, 'has_pvh', False)
                if self.correlar_off:
                    vt.mode = 'atc-nocorrel'
                else:
                    vt.mode = 'atc'
                vt.l_font_size = self.label_font_size
                vt.cfl = f.cfl
                self.tracks.append(vt)
                self._flights_tracks[f] = vt
                self._tracks_flights[vt] = f

            self._flights_by_cs = {f.callsign: f for f in self.flights}
            self.killed_flights = set()

            self.reposition()
            self.redraw()
            self.toolbar.redraw()
            self.separate_labels()

            if self.fir.sacta_mode[self.sector.split(',')[0]] == 'OSF':
                predesp = getattr(self, 'predesp_tabular', None)
                for w in self.display_remote:
                    if w is predesp:
                        continue
                    try:
                        if w.root.winfo_exists():
                            w.update()
                    except:
                        pass
                if predesp is not None:
                    try:
                        if predesp.root.winfo_exists():
                            predesp.update()
                    except:
                        pass
            else:
                if hasattr(self, 'atc_bahia') and self.atc_bahia.showed:
                    self.atc_bahia.update()

            if self.fir.param('tabulares_aux_actualizar', True):  # por defecto no en LEMD
                self.coor_tabular.update()
                self.preact_tabular.update()
                self.act_tabular.update()

            if hasattr(self, 'sob_tabular'):
                self.sob_tabular.update()

            # SMR. No Correlados tab update
            if hasattr(self, 'alarmNoCorr_tab'):
                self.alarmNoCorr_tab.update()

        def step_update_flight(flight_update):
            if flight_update.callsign in self.killed_flights: return
            old = self._flights_by_cs[flight_update.callsign]
            old.pos = flight_update.pos
            old.lvl = flight_update.lvl
            old.cfl = flight_update.cfl
            old.ias = flight_update.ias
            old.ground_spd = flight_update.ground_spd
            old.hdg = flight_update.hdg
            old.track = flight_update.track
            old.pof = flight_update.pof
            # Alertas aeroportuarias (INCW, CMAC, CATC)
            old.max_alert_severity = getattr(flight_update, 'max_alert_severity', 0)
            old.top_alert = getattr(flight_update, 'top_alert', None)
            old.active_alerts = getattr(flight_update, 'active_alerts', [])
            old.catc_pred = getattr(flight_update, 'catc_pred', False)
            return old

        if m['message'] == 'squawk_ident':
            flight = self._flights_by_cs[m['flight'].callsign]
            self._flights_tracks[flight].flash_p(0)

        if m['message'] == 'time':
            t = m['data']
            self.update_clock(t)
            self.t = t
            if not self.synchronised:
                self.last_update = self.t - datetime.timedelta(seconds=1)
                self.synchronised = True

        if m['message'] == 'update':
            # if self.updating:
            #     print("Not update")
            #     return
            # self.updating = True
            try:
                flight_updates = m['flight_updates']
                for flight_update in flight_updates: step_update_flight(flight_update)
                complete_flight_updates = m['complete_flight_updates']
                for complete_flight_update in complete_flight_updates:
                    f = update_flight(complete_flight_update)  # Returns the updated flight
                    if f is not None:
                        self.update_track(f)
                if self.disp_number == 1:
                    self.write_Cesium_file()
                self.wind = m['wind']
                self.metar = m['metar']
                self.update_wind(self.wind, self.metar)
                self.giw.qnh = m['qnh']
                self.radar_off = m['radar_off']
                self.correlar_off = m['correlar_off']
                # JRAR: Why stop separating labels?
                # self.stop_separating = True
                if self.fir.sacta_mode[self.sector.split(",")[0]] == 'OSF':
                    if self.disp_number == 1:
                        # if len(self.lcl_sector_list) > 1 and self.fir.aps[0] == 'LEPA': # DCM: doble bahia
                        #     # for fichas_tabular in self.display_remote:
                        #     #     if fichas_tabular.bahia_type is "LCL":
                        #     #         self.fichas_tabular.update()
                        #     self.fichas_tabular_1.update()
                        #     self.fichas_tabular_2.update()
                        # else:
                        #     self.fichas_tabular.update()
                        predesp = getattr(self, 'predesp_tabular', None)
                        for w in self.display_remote:
                            if w is predesp:
                                continue
                            try:
                                if w.root.winfo_exists():
                                    w.update()
                            except:
                                pass
                        if predesp is not None:
                            try:
                                if predesp.root.winfo_exists():
                                    predesp.update()
                            except:
                                pass

                else:
                    # self.write_flightstrips_file()
                    if hasattr(self, 'atc_bahia') and self.atc_bahia.showed:
                        self.atc_bahia.update()

                # Parametro de escenario 'tabulares_aux_actualizar' (por defecto no en LEMD)
                if self.fir.param('tabulares_aux_actualizar', True):
                    self.coor_tabular.update()
                    self.preact_tabular.update()
                    self.act_tabular.update()

                if hasattr(self, 'sob_tabular'):
                    self.sob_tabular.update()

                # SMR. No Correlados tab update
                if hasattr(self, 'alarmNoCorr_tab'):
                    self.alarmNoCorr_tab.update()

                if (self.t - self.last_update).seconds >= self.refresco:
                    self.update()
                    self.last_update = self.t

                # self.updating = False
            except:
                logging.warning("Error in update cycle", exc_info=True)

        if m['message'] == 'update_complete_flight':
            complete_flight_updates = m['complete_flight_updates']
            for complete_flight_update in complete_flight_updates:
                f = update_flight(complete_flight_update)  # Returns the updated flight
                if f is not None:
                    self.update_track(f)

        if m['message'] == 'update_flight':
            f = update_flight(m['flight'])  # Returns the updated flight
            if f is not None:
                self.update_track(f)
        if m['message'] == "restart":
            reload_flights(m['flights'], m['init_time'])

        if m['message'] == 'update_strip':
            f = update_flight(m['flight'])  # Returns the updated flight
            if f is not None:
                self.update_track(f)
            # if self.fir.sacta_mode[self.sector.split(",")[0]] == 'OSF':
            #     if self.disp_number == 1:
            #         if len(self.lcl_sector_list) > 1:
            #             for fichas_tabular in self.display_remote:
            #                 if fichas_tabular.bahia_type is "LCL":
            #                     fichas_tabular.update_strip(m['flight'])
            #         else:
            #             self.fichas_tabular.update_strip(m['flight'])
            #
            #         if self.fir.aps[0] not in ('LEMD', 'LEBL'):
            #             self.predesp_tabular.update_strip(m['flight'])
            # else:
            #     if self.atc_bahia.showed:
            #         self.atc_bahia.update_strip(m['flight'])
            if self.fir.sacta_mode[self.sector.split(",")[0]] == 'OSF':
                if self.disp_number == 1:
                    predesp = getattr(self, 'predesp_tabular', None)
                    for w in self.display_remote:
                        if w is predesp:
                            continue
                        try:
                            if w.root.winfo_exists():
                                w.update_strip(m['flight'])
                        except:
                            pass
                    if predesp is not None and self.fir.param('prevdesp_actualizar_ficha', True):
                        try:
                            if predesp.root.winfo_exists():
                                predesp.update_strip(m['flight'])
                        except:
                            pass
            else:
                if hasattr(self, 'atc_bahia') and self.atc_bahia.showed:
                    self.atc_bahia.update_strip(m['flight'])

        if m['message'] == 'kill_flight':
            try:
                f = self._flights_by_cs[m['cs']]
            except:
                return
            self.flights.remove(f)
            del self._flights_by_cs[f.callsign]
            ###################### If the pseudopilot remove the track, the strip is deleted in the UCS_bahia
            try:
                self.fichas_tabular.remove_fs(f)
                self.atc_bahia.remove_fs(f)
            except:
                pass
            ######################
            vt = self._flights_tracks[f]
            vt.destroy()
            del self._flights_tracks[f]
            del self._tracks_flights[vt]
            self.tracks.remove(vt)
            self.killed_flights.add(m['cs'])

    def update_runway_maps(self, ad, pistas_config):
        """
        Actualiza mapas segun configuracion de pistas.
        Soporta distintas convenciones de nombres de mapas entre ejercicios
        (ej: ARR_24R vs 24R_ARR, MIXTO_24L vs 24L_MIXTO, etc.)
        """

        available = self.toolbar.var_ver_localmap

        def resolve(*candidates):
            """Busca el primer nombre de mapa que exista en var_ver_localmap"""
            for name in candidates:
                if name in available:
                    return name
            return None

        # Nombres de mapa candidatos por pista (Fase 3 parte 2): se generan para cada
        # pista de pistas_config en lugar de una tabla fija de pistas de LEBL.
        #   ARR: ARR_<p>, <p>_ARR, '<p> ARR'   DEP: DEP_<p>, <p>_DEP
        #   MIXTO: MIXTO_<p>, MIXTO_<p sin cero inicial>, <p>_MIXTO
        #   CERRADA: parametro de escenario 'mapas_pista_cerrada' (por defecto la tabla de
        #   LEBL) o, si la pista no esta, <p>_CLSD y <reciproca>_CLSD
        cerrada_cfg = self.fir.param('mapas_pista_cerrada', {})
        designadores = []
        for config in pistas_config:
            for k in ('sentido1', 'sentido2'):
                des = config[k]['designador']
                if des not in designadores:
                    designadores.append(des)

        MAPA_CERRADA = {}
        MAPA_ARR = {}
        MAPA_DEP = {}
        MAPA_MIXTO = {}
        for des in designadores:
            if des in cerrada_cfg:
                cands = tuple(cerrada_cfg[des])
            else:
                cands = (des + '_CLSD', _reciprocal_rwy(des) + '_CLSD')
            r = resolve(*cands)
            if r:
                MAPA_CERRADA[des] = r
            r = resolve('ARR_' + des, des + '_ARR', des + ' ARR')
            if r:
                MAPA_ARR[des] = r
            r = resolve('DEP_' + des, des + '_DEP')
            if r:
                MAPA_DEP[des] = r
            r = resolve('MIXTO_' + des, 'MIXTO_' + des.lstrip('0'), des + '_MIXTO')
            if r:
                MAPA_MIXTO[des] = r

        for config in pistas_config:
            designador1 = config['sentido1']['designador']
            designador2 = config['sentido2']['designador']

            mapas_a_desactivar = []

            for des in [designador1, designador2]:
                if des in MAPA_CERRADA:
                    mapas_a_desactivar.append(MAPA_CERRADA[des])
                if des in MAPA_ARR:
                    mapas_a_desactivar.append(MAPA_ARR[des])
                if des in MAPA_DEP:
                    mapas_a_desactivar.append(MAPA_DEP[des])
                if des in MAPA_MIXTO:
                    mapas_a_desactivar.append(MAPA_MIXTO[des])

            # Desactivar todos los mapas relacionados
            for mapa in set(mapas_a_desactivar):
                if mapa in available:
                    available[mapa].set(0)

            # Activar los mapas segun la configuracion actual
            if config['cerrada'] == 1:
                for designador in [designador1, designador2]:
                    if designador in MAPA_CERRADA:
                        mapa = MAPA_CERRADA[designador]
                        if mapa in available:
                            available[mapa].set(1)

            # ARR y DEP (solo si NO esta cerrada ni en no_en_uso)
            if config['cerrada'] == 0 and config['no_en_uso'] == 0:
                for sentido in [config['sentido1'], config['sentido2']]:
                    op = sentido['operacion']
                    des = sentido['designador']

                    # Operacion mixta (DEP/ARR)
                    if op == 'DEP/ARR' and des in MAPA_MIXTO:
                        available[MAPA_MIXTO[des]].set(1)
                        continue

                    # ARR normal
                    if 'ARR' in op and des in MAPA_ARR:
                        available[MAPA_ARR[des]].set(1)

                    # DEP normal
                    if 'DEP' in op and des in MAPA_DEP:
                        available[MAPA_DEP[des]].set(1)

        # Guardar config actual para persistencia
        self.current_runway_config = pistas_config

        # Aplicar cambios
        if hasattr(self.toolbar, 'b_show_hide_localmaps'):
            self.toolbar.b_show_hide_localmaps()
        else:
            logging.warning("b_show_hide_localmaps not available yet")

    def set_active_sectors(self, sector_list):
        """Override de RaDisplay.set_active_sectors para actualizar estado del boton USO PISTAS"""
        # Llamar al metodo padre primero
        RaDisplay.set_active_sectors(self, sector_list)

        # Informar al GTA del nuevo sector para el historico
        if hasattr(self, 'sendMessage'):
            self.sendMessage({'message': 'set_client_sector', 'sector': self.sector})
        
        # Actualizar estado del boton USO PISTAS segun nuevo rol
        if hasattr(self.toolbar, 'but_uso_pistas'):
            has_lcl_role = False
            for sector in self.sector.split(','):
                if 'LCL' in sector or 'TWR' in sector:
                    has_lcl_role = True
                    break
            
            if has_lcl_role:
                self.toolbar.but_uso_pistas['state'] = tix.NORMAL
            else:
                self.toolbar.but_uso_pistas['state'] = tix.DISABLED

    def toggle_select(self, f, vfe_call=False):
        for radisp in self.master.display:
            flight = [fl for fl in radisp.flights if fl.callsign == f.callsign][0]
            vt = radisp._flights_tracks[flight]
            if radisp.disp_number == 1:
                canvas = radisp.c
                # GAC:  Selecciona los vuelos llamando a la funcion 'centerclicked' de la bahia de controlador,
                # solo si modo OSF
                if self.fir.sacta_mode[self.sector.split(",")[0]] == 'OSF':
                    # Joserra. If function called from vfe, this part is already done
                    if not vfe_call:
                        radisp.fichas_tabular.clicklabel(vt.cs, True)
            remove_flag = radisp.selected_track != None
            add_flag = (radisp.selected_track != vt)
            if remove_flag:
                try:
                    radisp.selected_track.selected = False
                except:
                    logging.warning('Unable to unselect track')
                radisp.selected_track = None
                radisp.selected_flight = None

            # If current track was not selected already, select it
            if add_flag:
                vt.selected = True
                radisp.selected_track = vt
                radisp.selected_flight = flight

            # Auto-actualizar ventana INFORMACION DE PV si esta abierta
            if hasattr(radisp, 'toolbar') and hasattr(radisp.toolbar, '_info_pv_window_open'):
                if radisp.toolbar._info_pv_window_open:
                    radisp.toolbar.refresh_info_pv()

    def delete_routes(self, e=None):
        for track in self.tracks:
            self.c.delete(track.cs + 'fpr')
            self.c.delete(track.cs + 'wp')
            self.routes = []
            self.waypoints = []

    def draw_fpr(self, track):
        canvas = self.c
        canvas.delete(track.callsign + 'fpr')
        canvas.delete(track.callsign + 'wp')
        line = ()
        # TODO This must be changed now that UCS will not have direct info from the Aircraft
        if track.to_do == 'fpr':
            line = line + self.do_scale(track.pos)
        for a in [wp for wp in track.route if wp.type == Route.WAYPOINT]:
            if a.fix == '_LLZ': break
            try:
                pto = self.do_scale(a.pos())
            except:
                continue
            if a.fix[0] != '_' or a.fix in self.fir.iaps.keys():
                try:
                    eto = '%02d:%02d' % (a.eto.hour, a.eto.minute)
                except:
                    eto = ''
                if len(a.fix) <= 5:
                    canvas.create_text(pto, text=a.fix, fill='orange', tag=track.callsign + 'fpr', anchor=tix.SE,
                                       font='-*-Helvetica-*--*-10-*-')
                    canvas.create_text(pto, text=eto, fill='orange', tag=track.callsign + 'fpr', anchor=tix.NE,
                                       font='-*-Helvetica-*--*-10-*-')
            line = line + pto
        if len(line) > 3: canvas.create_line(line, fill='orange', tags=track.callsign + 'fpr')
        self.routes.append(track)
        self.c.lift(track.callsign + 'fpr')
        self.c.lift('track')
        # self.master.delete_routes

    def draw_way_point(self, track):
        canvas = self.c
        do_scale = self.do_scale

        canvas.delete(track.callsign + 'fpr')
        canvas.delete(track.callsign + 'wp')
        line = ()
        # TODO must be changed now that UCS will not have info from the actual aircraft
        if track.to_do == 'fpr':
            line = line + do_scale(track.pos)
        for a in [wp for wp in track.route if wp.type == Route.WAYPOINT]:
            try:
                pto = do_scale(a.pos())
            except:
                continue
            if a.fix[0] != '_':
                try:
                    eto = '%02d:%02d' % (a.eto.hour, a.eto.minute)
                except:
                    eto = ''
                canvas.create_text(pto, text=a.fix, fill='yellow', tag=track.callsign + 'wp', anchor=tix.SE,
                                   font='-*-Helvetica-*--*-10-*-')
                canvas.create_text(pto, text=eto, fill='yellow', tag=track.callsign + 'wp', anchor=tix.NE,
                                   font='-*-Helvetica-*--*-10-*-')
            line = line + pto
        if len(line) > 3: canvas.create_line(line, fill='yellow', tags=track.callsign + 'wp')
        size = 2
        for a in track.route:
            (rect_x, rect_y) = do_scale(a.pos())
            point_ident = canvas.create_rectangle(rect_x - size, rect_y - size, rect_x + size, rect_y + size,
                                                  fill='yellow', outline='yellow', tags=track.callsign + 'wp')

            def clicked_on_waypoint(e, point_coord=a.pos(), point_name=a.fix):
                # Display window offering "Direct to..." and "Cancel" options.
                track.last_lad = e.serial
                win = tix.Frame(canvas)
                id_avo = tix.Label(win, text=track.callsign, bg='blue', fg='white')
                id_pto = tix.Entry(win, width=8, justify=tix.CENTER)
                id_pto.insert(0, point_name)
                but_direct = tix.Button(win, text="Dar directo")
                but_cancel = tix.Button(win, text="Cancelar")
                id_avo.grid(row=0, column=0, columnspan=1, sticky=tix.W + tix.E)
                id_pto.grid(row=1, column=0, columnspan=1, sticky=tix.W + tix.E)
                but_direct.grid(row=2, column=0, columnspan=1, sticky=tix.W + tix.E)
                but_cancel.grid(row=3, column=0, columnspan=1, sticky=tix.W + tix.E)
                win_identifier = canvas.create_window(e.x, e.y, window=win)

                def close_win(ident=win_identifier):
                    canvas.delete(ident)

                def direct_to():
                    pto = id_pto.get()
                    # Caso de dar directo al punto seleccionado
                    if pto == point_name:
                        # print "Selected plane should fly direct to point", point_coord
                        for i in range(len(track.route)):
                            if point_coord == track.route[i].pos():
                                aux = track.route[i:]
                        # TODO all of this must be rewritten, pending
                        # proper implementation of TLPV. Currently we are only
                        # showing the actual aircraft's route
                        # track.set_route(aux)
                        close_win()
                        canvas.delete(track.callsign + 'wp')
                    else:
                        aux = None
                        # Si es un punto intermedio de la ruta, lo detecta
                        for i in range(len(track.route)):
                            if track.route[i][1] == pto.upper():
                                aux = track.route[i:]
                                # Si no esta en la ruta, insertamos el punto como n 1
                        if aux == None:
                            for [nombre, coord] in self.fir.coords.items():
                                if nombre == pto.upper():
                                    aux = [[coord, nombre, '']]
                                    # print "Selected plane should fly direct to point", nombre,coord
                                    for a in track.route:
                                        aux.append(a)
                                        # Si no encuentra el punto, fondo en rojo y no hace nada
                        if aux == None:
                            id_pto.config(bg='red')
                            # print 'Punto ',pto.upper(),' no encontrado'
                        else:
                            # TODO all of this must be rewritten, pending
                            # proper implementation of TLPV. Currently we are only
                            # showing the actual aircraft's route
                            # track.set_route(aux)
                            close_win()
                            canvas.delete(track.callsign + 'wp')

                but_cancel['command'] = close_win
                but_direct['command'] = direct_to

            canvas.tag_bind(point_ident, "<1>", clicked_on_waypoint)
        self.waypoints.append(track)
        self.c.lift(track.callsign + 'wp')
        self.c.lift('track')

    def show_hide_way_point(self, track):
        canvas = self.c
        do_scale = self.do_scale

        if canvas.itemcget(track.callsign + 'wp', "fill") == 'yellow':
            canvas.delete(track.callsign + 'wp')
            self.waypoints.remove(track)
            return

        self.draw_way_point(track)

    def change_size(self, e):
        RaDisplay.change_size(self, e)
        self.toolbar.redraw()

    def reformat_labels(self):
        """Override: usar reconfigure() en vez de redraw() para que los colores
        (assumed/not-assumed, dep/arr) se recalculen al cambiar lineas o wake."""
        for f in self.flights:
            self.update_track(f)
        for a in self.tracks:
            a.reconfigure()

    def update(self):
        # def after_tracks(x):
        #    self.c.lift('track')
        #    self.c.lift('plot')  # Otherwise the most recent history dot comes above
        # and prevents correct clicking of the plot
        #    RaDisplay.update(self)
        # threads.deferToThread(self.update_tracks).addCallback(after_tracks)
        self.update_tracks()
        self.c.lift('track')
        self.c.lift('plot')
        RaDisplay.update(self)
        # after_tracks(True)
        self.update_clock()

    def update_clock(self, t=None):
        if t == None:
            t = self.t
        else:
            self.t = t
        self.clock.configure(time='%02d:%02d:%02d' % (t.hour, t.minute, t.second))

    def update_wind(self, wind, metar):
        self.windrose.configure(wind_spd='%02d' % wind[0], wind_dir=(wind[1] + 180.0) % 360.0, metar=metar)

    def update_tracks(self):
        # If we update the tracks all at once from here, when we are dealing with
        # many of them it will take a long time and the display will feel sluggish
        # Instead we cycle through them inside a thread, and let the main thread
        # update the actual tracks in bunches of 30. This improves responsiveness
        # JRAR: remove sleep, it will probably make the responsiveness worse

        # Precalcular valores comunes a todos los vuelos
        self._cached_sector_list = self.sector.split(",")
        self._cached_oaci_active = self.wake_oaci_var.get()
        self._cached_recat_active = self.wake_recat_var.get()
        self._cached_line_onoff = [self.l1_onoff_var.get(), True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(), True]
        self._cached_values_ready = True

        # Parametro de escenario 'refresco_aire' (s): si es mayor que 0, los moviles en vuelo
        # se refrescan solo cada refresco_aire segundos; los de tierra en cada ciclo.
        # Sin el parametro (0) todos se refrescan en cada ciclo, como antes.
        refresco_aire = 0
        try:
            refresco_aire = float(self.fir.param('refresco_aire', 0) or 0)
        except (AttributeError, TypeError, ValueError):
            refresco_aire = 0
        if refresco_aire <= 0 or (self.t - self.last_update_aire).seconds >= refresco_aire:
            self.last_update_aire = self.t
            for i in range(len(self.flights)):
                self.update_track(self.flights[i])
                #if not i % 5:
                #    self.c.update_idletasks()  # Let the display refresh for every n=5 tracks ??
        else:
            for i in range(len(self.flights)):
                if self.flights[i].pof in (Aircraft.GROUND, Aircraft.TAKEOFF, Aircraft.LANDED):
                    self.update_track(self.flights[i])

        # Dibujar lineas de conflicto entre pares de moviles con alerta (solo si hay alertas)
        self._update_conflict_lines()
        return True

    def _update_conflict_lines(self):
        """Dibuja/actualiza lineas rojas (VIO) o amarillas (WNG) entre pares de moviles
        con alerta multiple (alertas aeroportuarias INCW/CMAC/CATC)."""
        had_lines = getattr(self, '_conflict_lines_drawn', False)
        pairs = []
        drawn_pairs = set()
        for f in self.flights:
            for a in getattr(f, 'active_alerts', None) or []:
                if a.severity >= 1 and a.related_cs:
                    pair = frozenset([f.callsign, a.related_cs])
                    if pair in drawn_pairs:
                        continue
                    drawn_pairs.add(pair)
                    pairs.append((f, a))
        if not pairs and not had_lines:
            return  # Escenario sin alertas: nada que borrar ni dibujar
        self.c.delete('conflict_line')
        self._conflict_lines_drawn = False
        for f, a in pairs:
            other_f = self._flights_by_cs.get(a.related_cs)
            if other_f is None:
                continue
            vt1 = self._flights_tracks.get(f)
            vt2 = self._flights_tracks.get(other_f)
            if vt1 and vt2 and vt1.visible and vt2.visible:
                line_color = 'red' if a.severity >= 2 else 'yellow'
                try:
                    self.c.create_line(vt1.x, vt1.y, vt2.x, vt2.y,
                                       fill=line_color, width=2, tags=('conflict_line',))
                    self._conflict_lines_drawn = True
                except Exception:
                    pass

    def sec2minsec(self, sec):
        min = trunc(sec / 60)
        secs = trunc(abs(min * 60 - sec))
        return min, secs

    def update_track(self, f):
        vt = self._flights_tracks[f]

        if f.pof in (Aircraft.GROUND, Aircraft.LANDED):
            vt.alt = 'GND'
        else:
            vt.alt = f.lvl

        vt.cs = f.callsign
        vt.release_atc_pos = f.release_atc_pos
        vt.OSF_warning = f.OSF_warning
        # Vehiculo con Plan de Vehiculo (PVH): formato y color de etiqueta propios
        new_has_pvh = getattr(f, 'has_pvh', False)
        if vt._has_pvh != new_has_pvh:
            vt._has_pvh = new_has_pvh
            vt.reconfigure()
        vt.pvh_notes = getattr(f, 'pvh_notes', '')
        # Alertas aeroportuarias (INCW, CMAC, CATC)
        vt.alert_severity = getattr(f, 'max_alert_severity', 0)
        vt.alert_text = getattr(f, 'top_alert', None)
        vt.set_active_alerts(getattr(f, 'active_alerts', []))
        old_pred = vt.catc_pred
        vt.catc_pred = getattr(f, 'catc_pred', False)
        if vt.catc_pred != old_pred:
            vt.color_change()
        
        # Controlar visualización de wake según botones E.OACI y E.RECAT
        wake_str = ''
        if f.wake:
            #oaci_active = self.wake_oaci_var.get()
            #recat_active = self.wake_recat_var.get()
            oaci_active = self._cached_oaci_active if getattr(self, '_cached_values_ready', False) else self.wake_oaci_var.get()
            recat_active = self._cached_recat_active if getattr(self, '_cached_values_ready', False) else self.wake_recat_var.get()
            
            if oaci_active and recat_active:
                # Mostrar todo (letra + signo)
                wake_str = f.wake
            elif oaci_active and not recat_active:
                # Mostrar solo letra (sin último carácter si es signo)
                if len(f.wake) > 1 and f.wake[-1] in ('+', '-'):
                    wake_str = f.wake[:-1]  # Quitar último carácter
                else:
                    wake_str = f.wake  # Mostrar todo si no hay signo
            elif not oaci_active and recat_active:
                # Mostrar solo signo (último carácter si existe)
                if len(f.wake) > 1 and f.wake[-1] in ('+', '-'):
                    wake_str = f.wake[-1]  # Solo el signo
                else:
                    wake_str = ''  # No hay signo para mostrar
            # Si ambos inactivos, wake_str queda vacío
        
        vt.wake = wake_str
        vt.ltype = f.type
        vt.lrwy = f.lrwy_atc
        # VEH con PVH: mostrar pista CRU/ENT en lrwy (azul, se limpia al volver a TAX)
        if getattr(f, 'fr', '') == 'VEH' and getattr(f, 'has_pvh', False):
            osf_pof = getattr(f, 'OSF_pof', '')
            if osf_pof in (Aircraft.CRUREQ, Aircraft.CROSSING):
                vt.lrwy = getattr(f, 'cru_runway', '') or ''
            elif osf_pof in (Aircraft.ENTREQ, Aircraft.ENTERING):
                vt.lrwy = getattr(f, 'ent_runway', '') or ''
            else:
                vt.lrwy = ''
        vt.flight_phase = f.AirportElev
        vt.rutrod = f.rutrod
        vt.gate = f.gate

        if f.pof == Aircraft.GROUND:
            vt.echo = '   '
        else:
            vt.echo = f.campo_eco

        # if f.pof == Aircraft.GROUND and f.adep in self.fir.aerodromes:
        #     vt.holdp = f.holdp
        # else:
        #     vt.holdp = ''
        vt.holdp = f.holdp

        # if f.pof == Aircraft.GROUND and f.adep in self.fir.aerodromes:
        #     if f.sid_check:
        #         vt.sidok = " ? "
        #     else:
        #         vt.sidok = ' O '
        # else:
        #     vt.sidok = ''
        vt.sidok = ''

        if f.sid == None or f.fr == 'VEH':
            if f.park == 'None':
                vt.stand_sid = ''
            else:
                vt.stand_sid = f.park
        else:
            vt.stand = f.park
            vt.stand_sid = f.stand_sid_atc

        #if self.fir.AdHasIfrRwys(f.ades):
        if vt.ades_has_ifr:
            vt.trans = ' ' + f.campo_trans
        else:
            vt.trans = f.campo_trans
        vt.gs = f.ground_spd
        vt.osf_act = f.OSF_pof

        # Tiempo desde el takeoff
        if f.adep in self.fir.aerodromes and f.pof == 'FLYING':
            if vt.t_takeoff == None:
                vt.t_takeoff = self.t
            else:
                pass
            try:
                dif = self.t - vt.t_takeoff
                # vt.tfto = str(dif.total_seconds())
                sec = (dif.total_seconds())
                mins, secs = self.sec2minsec(sec)
                if secs < 10:
                    secs = '0' + str(secs)
                else:
                    secs = str(secs)
                vt.tfto = str(mins) + '\'' + secs
            except:
                vt.tfto = ''
        else:
            vt.tfto = ''
        
        #if self.fir.AdHasIfrRwys(f.ades) and f.pof == 'FLYING':
        if vt.ades_has_ifr and f.pof == 'FLYING':
            try:
                [xy_llz, rdl, dist_ayuda, pdte_ayuda, alt_pista] = f.llz
                (rx, ry) = r(xy_llz, f.pos)  # Coordenadas relativas a la radioayuda
                dist_thr = rp((rx, ry))[0] - dist_ayuda
                vt.thr_nm = dist_thr
                vt.thr_min = dist_thr / f.ground_spd * 60.

            except:
                vt.thr_nm = ''
                vt.thr_min = ''
        else:
            vt.thr_nm = ''
            vt.thr_min = ''
        vt.mach = f.get_mach()
        vt.rules = f.fr
        vt.colat = f.colat
        vt.colat_app = f.colat_app
        # vt.r_speed= f.r_speed
        # vt.r_head= f.r_head
        # vt.r_rate= f.r_rate
        vt.hdg = f.hdg
        vt.track = f.track
        vt.rate = f.get_rate_descend()
        vt.ias = f.ias

        #vt.adep = f.adep
        #sector_list = self.sector.split(",")
        #vt.local_dep = False
        #for sector in sector_list:
        #    if (vt.adep in self.fir.local_ads[sector]):
        #        vt.local_dep = True
        #vt.ades = f.ades
        #vt.local_des = False
        #for sector in sector_list:
        #    if (vt.ades in self.fir.local_ads[sector]):
        #        vt.local_des = True
        vt.type = f.type
        vt.radio_cs = f.radio_callsign
        if f.cfl != f.lvl:
            vt.cfl = f.cfl_c

        vt.arrow = f.cfl
        vt.rfl = f.rfl
        vt.ecl = f.ecl
        if not vt.remove_tfl:
            vt.tfl = f.tfl  # TFL IS A CONTROLLER CONCEPT, NOT AN AIRCRAFT VARIABLE

        #vt.line_onoff = [self.l1_onoff_var.get(), True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(), True]
        vt.line_onoff = self._cached_line_onoff if getattr(self, '_cached_values_ready', False) else [self.l1_onoff_var.get(), True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(), True]

        if self.smrOn and f.adep == self.fir.param('smr_ad', ''):  # Salidas del aerodromo SMR: solo 1 linea
            vt.line_onoff = [True, True, False, False, False, True]

        # Parpadeo selectivo: solo para los sectores involucrados (actual y siguiente)
        if f.trans_atc_pos or f.pedir_trf:
            sector_list = self._cached_sector_list if getattr(self, '_cached_values_ready', False) else self.sector.split(",")
            vt.flashing = any(s == f.atc_sector or s == f.next_atc_sector for s in sector_list)
        else:
            vt.flashing = False
        # JRAR: Change from position assignment to sector assignment
        # if (f.atc_pos == None) or (f.atc_pos != self.pos_number): vt.assumed = False
        # if f.atc_pos == self.pos_number: vt.assumed = True

        # Asumido si el sector que controla el vuelo es uno de los de esta posicion. Antes se buscaba
        # como subcadena (find) y daba falsos positivos, p.ej. 'LCL' dentro de 'LCL ARR'
        vt.assumed = f.atc_sector is not None and \
            (f.atc_sector == self.sector or f.atc_sector in self.sector.split(','))
        [x0, y0] = self.do_scale(f.pos)
        vt.coords(x0, y0, self.t)
        if self.fir.cob_radar_inf > 0 and f.lvl < self.fir.cob_radar_inf:
            vt.visible = False
        elif self._falt_enabled and f.lvl < self.select_FALT_varmin.get():
            vt.visible = False
        elif self._falt_enabled and f.lvl > self.select_FALT_varmax.get():
            vt.visible = False  # Filtro de altitud (FALT) independiente del controlador
        elif not self.filterFGND:
            if f.ias < 50.0:
                vt.visible = False
            else:
                vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING)) and not (
                        f.pof == Aircraft.GROUND and f.spof == Aircraft.PARKED and f.pp_pos == None)
        else:
            if self.radar_off and f.pof == 'FLYING':
                vt.visible = False
            elif self.sector in self.fir.param('min_alt_visible', {}) \
                    and vt.alt < self.fir.param('min_alt_visible', {})[self.sector]:
                vt.visible = False  # Filtro de altitud por sector (parametro 'min_alt_visible'; LEGR 5000 ft)
            elif vt.local_dep and self.smrOn:
                # Departures if smrOn show only 1 line and are visibles
                vt.line_onoff = [True, True, False, False, False, True]
                # LEST departures if SMR is On are visibles
                if (f.eobt - self.t) < (datetime.timedelta(minutes=30)):
                    vt.assumed = True
                    vt.visible = True
                    vt.redraw_p()
            else:
                vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING)) and not (
                        f.pof == Aircraft.GROUND and f.spof == Aircraft.PARKED and f.pp_pos == None)
            # Mostrar aviones en parking aunque no los haya asumido un pseudo
            # vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING))
        # Setting mode implicitly redraws labels
        if self.correlar_off:
            vt.mode = 'atc-nocorrel'
        else:
            vt.mode = 'atc'
        # Label color update when:
        # 1. Dep and Lnd Aircraft. After last Sid point
        # 2. Dep or Overflight. If the Aircraft needs to do App procedure
        # No aplicar en modo OSF: reconfigure() ya gestiona los colores assumed/not-assumed
        sacta_mode = self.fir.sacta_mode[self._cached_sector_list[0]] if getattr(self, '_cached_values_ready', False) else self.fir.sacta_mode[self.sector.split(',')[0]]
        if sacta_mode != 'OSF':
            vt_color = vt.color.get_basecolor()
            #if self.fir.AdHasIfrRwys(f.ades) and f.fr != 'VEH' and vt_color != vt.ASSUMED_COLOR_UCS:
            if vt.ades_has_ifr and f.fr != 'VEH' and vt_color != vt.ASSUMED_COLOR_UCS:
                #if self.fir.AdHasIfrRwys(f.adep) and (len(f.route) != 0 and f.star is not None and f.route[
                #    0].fix == f.star.start_fix) or f.to_do == 'app':
                if vt.adep_has_ifr and (len(f.route) != 0 and f.star is not None and f.route[
                    0].fix == f.star.start_fix) or f.to_do == 'app':
                    if sacta_mode == 'UCS':
                        vt.color.set(vt.NONASSUMED_COLOR_UCS)
                    else:
                        vt.color.set(vt.ASSUMED_COLOR_PICT)
                    vt.color_change()

        # Refresh Label to update Arrow (Next Aircraft Level)
        vt.refresh()

    def vt_handler(self, vt, item, action, value, e=None):
        f = self._tracks_flights[vt]
        pvh_on = self.fir.param('pvh', False)
        # VEH sin PVH (escenarios con 'pvh'): click en callsign abre CREAR PV en vez de asumir
        if pvh_on and item == 'cs' and action == '<Button-1>':
            if getattr(f, 'fr', None) == 'VEH' and not getattr(f, 'has_pvh', False):
                osf = getattr(self, 'fichas_tabular', None)
                if osf:
                    osf._handle_veh_button()
                    if getattr(osf, '_pvh_cs_var', None):
                        osf._pvh_cs_var.set(f.callsign)
                return  # No llamar a RaDisplay.vt_handler (no enviar assume)
        RaDisplay.vt_handler(self, vt, item, action, value, e)
        if item == 'ecl':
            if action == 'update':
                self.sendMessage({"message": "set_ecl", "cs": f.callsign, "ecl": int(value)})
        if item == 'cfl_c':
            if action == 'update':
                self.sendMessage({"message": "set_cfl_c", "cs": f.callsign, "cfl": int(value)})
        if item == 'tfl':
            if action == 'update':
                self.sendMessage({"message": "set_tfl", "cs": f.callsign, "tfl": int(value)})
            if action == '<Double-Button-1>':
                vt.cfl = int(value)
                #vt.set_label_item('cfl', True)
                #self.sendMessage({"message": "set_tfl", "cs": f.callsign, "tfl": int(value)})
                self.sendMessage({"message": "set_cfl_c", "cs": f.callsign, "cfl": int(value)})
                if hasattr(self, 'atc_bahia'):
                    self.atc_bahia.update_cfl(f.callsign, int(value))
                if vt.label_format == 'atc-ucs':
                    vt.remove_tfl = True
        if item == 'plot':
            if action == '<Button-1>': self.show_hide_fpr(f)
            elif pvh_on and action == '<Button-2>':
                # Vehiculo: rellena el indicativo del dialogo CREAR PV si esta abierto
                if getattr(f, 'fr', None) == 'VEH':
                    osf = getattr(self, 'fichas_tabular', None)
                    if osf and getattr(osf, '_pvh_dialog', None) and osf._pvh_dialog.winfo_exists():
                        if getattr(osf, '_pvh_cs_var', None):
                            osf._pvh_cs_var.set(f.callsign)
                        return True
            elif pvh_on and action == '<Button-3>':
                # Vehiculo con PVH en TAX o ENR: dialogo PISTA ENTRADA
                if (getattr(f, 'fr', None) == 'VEH' and
                        getattr(f, 'has_pvh', False) and
                        getattr(f, 'OSF_pof', None) in (Aircraft.TAXIING_OUT, Aircraft.ENTREQ)):
                    osf = getattr(self, 'fichas_tabular', None)
                    if osf:
                        osf.open_pista_entrada(f.callsign)
                        return True
        if item == 'cs':
            if action == '<Button-1>':
                # DCM: Esta en RaDisplay -> def vt_handler()
                pass
        if item == 'sid_star':
            if action == 'change_procedure':
                self.sid_dialog(f, e)
        # if item=='echo':
        #    if action=='<Button-3>':
        #        self.show_hide_way_point(track)

        elif item == 'rutrod':
            if action == 'update':
                m = {"message": "set_rutrod", "cs": f.callsign, "rutrod": value}
                self.sendMessage(m)

        elif item == 'gate':
            if action == 'update':
                m = {"message": "set_gate", "cs": f.callsign, "gate": value}
                self.sendMessage(m)

        elif item == 'holdp':
            if action == 'update':
                m = {"message": "set_holdp", "cs": f.callsign, "holdp": value}
                self.sendMessage(m)

        elif item == 'sidok':
            if action == 'update':
                if f.sid_check == True:
                    f.sid_check = False
                else:
                    f.sid_check = True
                m = {"message": "set_sid_check", "cs": f.callsign, "sid_check": f.sid_check}
                self.sendMessage(m)

    def show_hide_fpr(self, track):
        canvas = self.c
        if canvas.itemcget(track.callsign+'fpr', "fill") == 'orange':
            canvas.delete(track.callsign+'fpr')
            self.routes.remove(track)
        else:
            self.draw_fpr(track)
        canvas = self.c

    def sid_dialog(self, f, e=None):
        """Show a dialog to allow the user to define rwy and sid"""

        def change_sid(e=None):
            sid = sid_listbox.get(tix.ACTIVE)
            rwy = rwy_listbox.get(tix.ACTIVE)
            self.sendMessage({"message": "change_atc_sid", "cs": f.callsign, "sid": sid, "rwy": rwy})

            #Prueba actualizacion datos puntuales en fve
            # self.fichas_tabular.update_valores_ficha(f.callsign, sid)

            self.update_tracks()
            sid_toplevel.destroy()

        def sort_sids(sid_list, current_sid):
            """Ordena las SIDs poniendo primero las que coinciden con la actual (excepto numero/letra final),
            luego el resto alfabeticamente"""
            import re
            if not current_sid or not sid_list:
                return sorted(sid_list)
            
            # Extraer el prefijo de la SID actual (sin numero y letra final)
            # Ej: "LOBAR1C" -> "LOBAR"
            match = re.match(r'^([A-Z]+)', current_sid)
            current_prefix = match.group(1) if match else ""
            
            # Separar SIDs en dos grupos
            similar_sids = []
            other_sids = []
            
            for sid in sid_list:
                match = re.match(r'^([A-Z]+)', sid)
                sid_prefix = match.group(1) if match else ""
                
                if sid_prefix and sid_prefix == current_prefix:
                    similar_sids.append(sid)
                else:
                    other_sids.append(sid)
            
            # Ordenar ambos grupos alfabeticamente y concatenar
            return sorted(similar_sids) + sorted(other_sids)

        def select_rwy(e=None):
            selected_rwy = rwy_listbox.get(rwy_listbox.nearest(e.y))
            sid_listbox.delete(0, tix.END)
            sid_list = []

            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig == selected_rwy:
                    for sid in rwy.sid_dict.values():
                        sid_list.append(sid.txt_desig)
                    
                    # Ordenar las SIDs con la logica de prioridad
                    current_sid = getattr(f, 'stand_sid_atc', None) or getattr(f, 'sid', None) or ''
                    sorted_list = sort_sids(sid_list, current_sid)
                    
                    for sid_name in sorted_list:
                        sid_listbox.insert(tix.END, sid_name)
                    return
                    return

        sid_toplevel = tix.Toplevel()
        sid_toplevel.attributes('-topmost', True)
        sid_toplevel.title(f.callsign)
        sid_toplevel.geometry("+%d+%d" % (e.x_root, e.y_root))
        rwy_listbox = tix.Listbox(sid_toplevel, width=30, height=6)
        rwy_listbox.pack()
        sid_listbox = tix.Listbox(sid_toplevel, width=30, height=20)
        sid_listbox.pack()
        if not self.fir.AdHasIfrRwys(f.adep):
            sid_toplevel.destroy()
            return
        else:
            ad = self.fir.aerodromes[f.adep]
            for rwy in ad.rwy_direction_list:
                if len(rwy.sid_dict) > 0:
                    rwy_listbox.insert(tix.END, rwy.txt_desig)
            # Build the GUI Dialog
            try:
                ad = self.fir.aerodromes[f.adep]
                sid_list = []
                for rwy in ad.rwy_direction_list:
                    if rwy.txt_desig == f.rdep:
                        rwy_in_use = rwy
                for sid in rwy_in_use.sid_dict.values():
                    sid_list.append(sid.txt_desig)
                
                # Ordenar las SIDs con la logica de prioridad
                current_sid = getattr(f, 'stand_sid_atc', None) or getattr(f, 'sid', None) or ''
                sorted_list = sort_sids(sid_list, current_sid)
                
                for sid_name in sorted_list:
                    sid_listbox.insert(tix.END, sid_name)
            except:
                logging.warning("No SIDs found for %s departing from %s" % (f.callsign, f.adep))

            tix.Button(sid_toplevel, text='Aceptar', command=change_sid).pack()
            rwy_listbox.bind("<Button-1>", select_rwy)

    def reposition(self):
        RaDisplay.reposition(self)
        r = self.routes[:]
        w = self.waypoints[:]
        self.delete_routes()
        for track in r:
            self.draw_fpr(track)
        for track in w:
            self.draw_way_point(track)

    def redraw(self):
        RaDisplay.redraw(self)
        self.update_tracks()

    def b1_cb(self, e):
        self.toolbar.close_windows(keep_info_pv=self.toolbar._info_pv_window_open)
        if not self.smrOn:
            RaDisplay.b1_cb(self, e)
        else:
            pass

    def b2_cb(self, e):
        self.toolbar.close_windows(keep_info_pv=self.toolbar._info_pv_window_open)
        if not self.smrOn:
            RaDisplay.b2_cb(self, e)
        else:
            pass

    def b3_cb(self, e):
        self.toolbar.close_windows(keep_info_pv=self.toolbar._info_pv_window_open)
        if not self.smrOn:
            RaDisplay.b3_cb(self, e)
        else:
            pass

    def f3(self, e=None):
        self.toolbar.show_info_pv()

    def cf3(self, e=None):
        pass  # Ctrl+F3 deshabilitado para controladores (no necesitan escalas)

    def play(self):
        pass

    def pause(self):
        pass

    def save_state(self):
        """Save UCS-specific state, then delegate to RaDisplay.save_state()."""
        layout_str = "Layout" + str(self.disp_number)
        if self.fir.sacta_mode[self.sector.split(",")[0]] == 'OSF':
            if self.disp_number == 1:
                # self.conf.write_option(layout_str, "Predesp_tabular", self.predesp_tabular.showed)
                self.conf.write_option(layout_str, "fichas_tabular", self.fichas_tabular.showed)
        elif hasattr(self, 'atc_bahia'):
            self.conf.write_option(layout_str, "atc_bahia", self.atc_bahia.showed)
            if self.atc_bahia.showed:
                self.atc_bahia.update_idletasks()
                self.conf.write_option(layout_str, "atc_bahia_geometry", self.atc_bahia.wm_geometry())
        self.conf.write_option(layout_str, "sector", self.sector)
        RaDisplay.save_state(self)

    def exit(self):
        if self.fir.sacta_mode[self.sector.split(",")[0]] != 'OSF':
            if hasattr(self, 'atc_bahia'):
                self.atc_bahia.destroy()
        # save_state() + conf.save() + window/track cleanup handled by RaDisplay
        RaDisplay.exit(self)

    def __del__(self):
        logging.debug("PpDisplay.__del__")


class ventana_auxiliar:
    def __init__(self, master):
        self.master = master
        self.conf = master.conf
        self.opened_windows = []
        
        # Colores para sistema de toggle visual (estilo SACTA)
        self.NORMAL_BG = '#534d4d'
        self.NORMAL_FG = 'white'
        self.ACTIVE_BG = 'white'
        self.ACTIVE_FG = 'black'
        self.vr = tix.IntVar()
        self.vr.set(master.draw_routes)
        self.vf = tix.IntVar()
        self.vf.set(master.draw_point)
        self.vfn = tix.IntVar()
        self.vfn.set(master.draw_point_names)
        self.vs = tix.IntVar()
        self.vs.set(master.draw_sector)
        self.vsl = tix.IntVar()
        self.vsl.set(master.draw_lim_sector)
        self.vt = tix.IntVar()
        self.vt.set(master.draw_tmas)
        self.vd = tix.IntVar()
        self.vd.set(master.draw_deltas)
        self.var_ver_localmap = {}
        self.var_ver_coor_tab = tix.IntVar()
        self.var_ver_predesp_tab = tix.IntVar()
        self.var_ver_preact_tab = tix.IntVar()
        self.var_ver_act_tab = tix.IntVar()
        self.var_ver_windrose = tix.IntVar()
        self.var_ver_fichas_tab = tix.IntVar()
        self.var_ver_bahia_tab = tix.IntVar()

        for map_name in master.fir.local_maps:
            self.var_ver_localmap[map_name] = tix.IntVar()

        self.auto_sep = tix.IntVar()
        self.auto_sep.set(self.master.auto_separation)
        self.speed_vector_var = tix.IntVar()
        self.speed_vector_var.set(0)
        self.clock_speed_var = tix.DoubleVar()
        self.clock_speed_var.set(1.0)
        self.toolbar_id = None
        self.smrOn = master.smrOn
        self.filterFGND = master.filterFGND
        self._mapas_window_open = False
        self._mapas_toplevel = None
        self._mapas_toplevel2 = None
        self._tabs_window_open = False
        self._pistas_window_open = False
        self._orient_window_open = False
        self._tamano_window_open = False
        self._info_pv_window_open = False

        # IDs especificos de cada ventana emergente
        self._mapas_window_id = None
        self._tabs_window_id = None
        self._pistas_window_id = None
        self._orient_window_id = None
        self._tamano_window_id = None
        self._info_pv_window_id = None
        
        # Control global de botones activos
        self.active_buttons = [] 
        self.any_button_pressed = False

    #def close_windows(self):
    #    for w in self.opened_windows[:]:
    #        self.master.c.delete(w)
    #        self.opened_windows.remove(w)
    #    reseteo de ventanas abiertas
    #    self._mapas_window_open = False
    #    self._tabs_window_open = False
    #    self._pistas_window_open = False
    def close_windows(self, keep_info_pv=False):
        """Cierra ventanas emergentes y desactiva sus botones.
        Se llama desde b1_cb/b2_cb/b3_cb cuando se hace clic en el canvas.
        keep_info_pv=True preserva la ventana INFORMACION DE PV (para auto-actualización)."""
        
        # Cerrar ventana de MAPAS
        if self._mapas_toplevel:
            self._mapas_toplevel.destroy()
            self._mapas_toplevel = None
        if self._mapas_toplevel2:
            self._mapas_toplevel2.destroy()
            self._mapas_toplevel2 = None
        if self._mapas_window_id:
            self.master.c.delete(self._mapas_window_id)
            if self._mapas_window_id in self.opened_windows:
                self.opened_windows.remove(self._mapas_window_id)
        self._mapas_window_open = False
        self._mapas_window_id = None
        
        # Cerrar ventana de TABS
        if self._tabs_window_id:
            self.master.c.delete(self._tabs_window_id)
            if self._tabs_window_id in self.opened_windows:
                self.opened_windows.remove(self._tabs_window_id)
        self._tabs_window_open = False
        self._tabs_window_id = None
        
        # Cerrar ventana de USO DE PISTAS
        if self._pistas_window_id:
            self.master.c.delete(self._pistas_window_id)
            if self._pistas_window_id in self.opened_windows:
                self.opened_windows.remove(self._pistas_window_id)
        self._pistas_window_open = False
        self._pistas_window_id = None
        
        # Cerrar ventana de ORIENTACION
        if self._orient_window_id:
            self.master.c.delete(self._orient_window_id)
            if self._orient_window_id in self.opened_windows:
                self.opened_windows.remove(self._orient_window_id)
        self._orient_window_open = False
        self._orient_window_id = None
        
        # Cerrar ventana de TAMANO ETIQUETAS
        if self._tamano_window_id:
            self.master.c.delete(self._tamano_window_id)
            if self._tamano_window_id in self.opened_windows:
                self.opened_windows.remove(self._tamano_window_id)
        self._tamano_window_open = False
        self._tamano_window_id = None

        # Cerrar ventana de INFORMACION DE PV (salvo si keep_info_pv=True)
        if not keep_info_pv:
            if self._info_pv_window_id:
                self.master.c.delete(self._info_pv_window_id)
                if self._info_pv_window_id in self.opened_windows:
                    self.opened_windows.remove(self._info_pv_window_id)
            self._info_pv_window_open = False
            self._info_pv_window_id = None

        # Desactivar visualmente TODOS los botones que controlan ventanas
        botones_con_ventanas = []
        if hasattr(self, 'but_ver_maps'):
            botones_con_ventanas.append(self.but_ver_maps)
        if hasattr(self, 'but_ver_tabs'):
            botones_con_ventanas.append(self.but_ver_tabs)
        if hasattr(self, 'but_uso_pistas'):
            botones_con_ventanas.append(self.but_uso_pistas)
        if hasattr(self, 'but_orient'):
            botones_con_ventanas.append(self.but_orient)
        if hasattr(self, 'but_tamano_etiq'):
            botones_con_ventanas.append(self.but_tamano_etiq)
        
        for btn in botones_con_ventanas:
            if hasattr(btn, 'toggle_state'):
                btn.toggle_state['active'] = False
                btn.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                if btn in self.active_buttons:
                    self.active_buttons.remove(btn)
        
        # Actualizar el flag global
        self.any_button_pressed = len(self.active_buttons) > 0

    def refresh_info_pv(self):
        """Refresca la ventana INFORMACION DE PV con el vuelo actualmente seleccionado.
        Cierra y reabre la ventana sin comportamiento de toggle."""
        if not self._info_pv_window_open:
            return
        # Cerrar la ventana existente directamente (sin pasar por show_info_pv toggle)
        if self._info_pv_window_id:
            self.master.c.delete(self._info_pv_window_id)
            if self._info_pv_window_id in self.opened_windows:
                self.opened_windows.remove(self._info_pv_window_id)
        self._info_pv_window_open = False
        self._info_pv_window_id = None
        # Reabrir con el vuelo actualmente seleccionado
        self.show_info_pv()

    def show_info_pv(self):
        """Muestra/oculta la ventana INFORMACION DE PV para el vuelo seleccionado."""
        w = self.master.c

        if self._info_pv_window_open:
            self.close_windows()
            return

        sel = self.master.selected_track
        f = None
        if sel is not None:
            try:
                f = self.master._tracks_flights[sel]
            except (KeyError, IndexError):
                f = None

        self.close_windows()

        # --- Construir ventana ---
        # Grid de 17 columnas: 0-14 contenido, 15-16 margen derecho
        NCOLS = 17
        ventana_pv = tix.Frame(w, bg='#666666', relief='raised', bd=2)

        FONT_HEADER = ('Arial', 7, 'bold')
        FONT_VALUE = ('Arial', 8)
        FONT_TITLE = ('Arial', 10, 'bold')
        FONT_BTN = ('Arial', 7)
        BG = '#666666'
        BG_FIELD = '#888888'
        FG = 'white'
        FG_HEADER = '#CCCCCC'

        # Configurar pesos de columnas para que el grid se distribuya
        for c in range(NCOLS):
            ventana_pv.columnconfigure(c, weight=1, minsize=30)
        # Columnas mitad (E, ER, W, Y, R, T) mas estrechas
        for c in []:
            ventana_pv.columnconfigure(c, weight=0, minsize=15)
        # Margen derecho
        ventana_pv.columnconfigure(15, weight=0, minsize=8)
        ventana_pv.columnconfigure(16, weight=0, minsize=8)

        def make_header(parent, text, row, col, colspan=1):
            lbl = tix.Label(parent, text=text, bg=BG, fg=FG_HEADER, font=FONT_HEADER, anchor='w')
            lbl.grid(row=row, column=col, columnspan=colspan, padx=1, pady=0, sticky='ew')
            return lbl

        def make_value(parent, text, row, col, colspan=1, width=4):
            lbl = tix.Label(parent, text=str(text), bg=BG_FIELD, fg=FG, font=FONT_VALUE,
                            anchor='w', width=width, relief='sunken', bd=1)
            lbl.grid(row=row, column=col, columnspan=colspan, padx=1, pady=1, sticky='ew')
            return lbl

        # =================================================================
        # FILA 0: Barra rosa + boton X
        # =================================================================
        barra_frame = tix.Frame(ventana_pv, bg='#CC6699', height=10)
        barra_frame.grid(row=0, column=0, columnspan=NCOLS, sticky='ew')
        barra_frame.grid_propagate(False)
        barra_frame.columnconfigure(0, weight=1)
        btn_x = tix.Button(barra_frame, text='X', bg='#CC6699', fg='white',
                           font=('Arial', 7, 'bold'), bd=0, padx=2, pady=0,
                           command=lambda: self.close_windows())
        btn_x.pack(side='right')

        # =================================================================
        # FILA 1 (row=1): Headers de identificacion
        # Columnas:  0-1=INDICATIVO(x2), 2-3=FIJO(x2), 4=ETO(x1), 5=ECL(x1),
        #            6=CSSR(x1), 7=ORIG(x1), 8=DEST(x1), 9=N/TIPO(~x1.25),
        #            10=E(x0.5), 11=ER(x0.5), 12=VELO(x1),
        #            13=W(x0.5), => usamos misma col que Y por espacio
        #            Reajuste: mapeamos a 15 cols de contenido
        # Para manejar x0.5 usamos columnas de 1 unidad y ajustamos width
        # =================================================================
        r = 1
        # col 0-1: INDICATIVO (x2)
        make_header(ventana_pv, 'INDICATIVO', r, 0, colspan=2)
        # col 2-3: FIJO (x2)
        make_header(ventana_pv, 'FIJO', r, 2, colspan=2)
        # col 4: ETO (x1)
        make_header(ventana_pv, 'ETO', r, 4)
        # col 5: ECL (x1)
        make_header(ventana_pv, 'ECL', r, 5)
        # col 6: CSSR (x1)
        make_header(ventana_pv, 'CSSR', r, 6)
        # col 7: ORIG (x1)
        make_header(ventana_pv, 'ORIG', r, 7)
        # col 8: DEST (x1)
        make_header(ventana_pv, 'DEST', r, 8)
        # col 9: N/TIPO (x1.25 -> usamos 1 col con width mayor)
        make_header(ventana_pv, 'N/TIPO', r, 9)
        # col 10: E (x0.5)
        lbl_e = tix.Label(ventana_pv, text='E', bg=BG, fg=FG_HEADER, font=FONT_HEADER, anchor='center')
        lbl_e.grid(row=r, column=10, padx=1, pady=0, sticky='ew')
        # col 11: ER (x0.5 -> comparte con siguiente)
        lbl_er = tix.Label(ventana_pv, text='ER', bg=BG, fg=FG_HEADER, font=FONT_HEADER, anchor='center')
        lbl_er.grid(row=r, column=11, padx=1, pady=0, sticky='ew')
        # col 12: VELO (x1)
        make_header(ventana_pv, 'VELO', r, 12)
        # W col 13 (width pequeno)
        lbl_w = tix.Label(ventana_pv, text='W', bg=BG, fg=FG_HEADER, font=FONT_HEADER, anchor='center')
        lbl_w.grid(row=r, column=13, padx=1, pady=0, sticky='ew')
        ventana_pv.columnconfigure(13, weight=0, minsize=18)

        # Eliminar los headers ya creados y rehacerlo todo
        for child in ventana_pv.winfo_children():
            if child != barra_frame:
                child.destroy()

        # Unidad base de ancho en caracteres
        U = 4  # 1 unidad = 4 chars de width

        def make_row_frame(parent, row_num):
            fr = tix.Frame(parent, bg=BG)
            fr.grid(row=row_num, column=0, columnspan=NCOLS, sticky='ew', padx=2)
            return fr

        def add_header_cell(parent, text, row, col, width, colspan=1):
            lbl = tix.Label(parent, text=text, bg=BG, fg=FG_HEADER,
                            font=FONT_HEADER, anchor='w', width=width)
            lbl.grid(row=row, column=col, columnspan=colspan, padx=1, pady=0, sticky='ew')
            return lbl

        def add_value_cell(parent, text, row, col, width, colspan=1):
            lbl = tix.Label(parent, text=str(text), bg=BG_FIELD, fg=FG,
                            font=FONT_VALUE, anchor='w', width=width,
                            relief='sunken', bd=1)
            lbl.grid(row=row, column=col, columnspan=colspan, padx=1, pady=1, sticky='ew')
            return lbl

        # =================================================================
        # FILAS 1-2 (row=1): Headers + Valores en un mismo frame con grid
        # =================================================================
        fr12 = make_row_frame(ventana_pv, 1)

        # Definir columnas: (nombre_header, width, valor)
        # Obtener datos del vuelo (placeholders vacios si no hay vuelo seleccionado)
        if f is not None:
            callsign = getattr(f, 'callsign', '')
            sid_str = getattr(f, 'stand_sid', '') or ''
            star_str = ''
            if getattr(f, 'star', None):
                star_str = getattr(f.star, 'txt_desig', '') or ''
            fijo_str = sid_str or star_str
            cfl_str = str(int(getattr(f, 'cfl', 0))) if getattr(f, 'cfl', 0) else '--'
            squawk_str = getattr(f, 'squawk', '') or '--'
            adep_str = getattr(f, 'adep', '') or '--'
            ades_str = getattr(f, 'ades', '') or '--'
            type_str = getattr(f, 'type', '') or '--'
        else:
            callsign = ''
            fijo_str = '--'
            cfl_str = '--'
            squawk_str = '--'
            adep_str = '--'
            ades_str = '--'
            type_str = '--'

        # col, header, width, valor
        cols_fila1 = [
            (0,  'INDICATIVO', U*2,          callsign),
            (1,  'FIJO',       U*2,          fijo_str),
            (2,  'ETO',        U,            '--'),
            (3,  'ECL',        U,            cfl_str),
            (4,  'CSSR',       U,            squawk_str),
            (5,  'ORIG',       U,            adep_str),
            (6,  'DEST',       U,            ades_str),
            (7,  'N/TIPO',     int(U*1.25),  type_str),
            (8,  'E',          max(1, U//2), '--'),
            (9,  'ER',         max(1, U//2), '--'),
            (10, 'VELO',       U,            '--'),
            (11, 'W',          max(1, U//2), '--'),
            (12, 'Y',          max(1, U//2), '--'),
            (13, 'ESTADO',     U*2,          '--'),
            (14, 'STS',        U,            '--'),
        ]
        for col, header, width, val in cols_fila1:
            add_header_cell(fr12, header, 0, col, width)
            add_value_cell(fr12, val, 1, col, width)

        # =================================================================
        # FILA 3 (row=3): Linea vacia separadora
        # =================================================================
        sep3 = tix.Frame(ventana_pv, bg=BG, height=4)
        sep3.grid(row=3, column=0, columnspan=NCOLS, sticky='ew')
        sep3.grid_propagate(False)

        # =================================================================
        # FILAS 4-5 (row=4): Headers + Valores RUTA + OBSERV. en grid
        # =================================================================
        fr45 = make_row_frame(ventana_pv, 4)
        # RUTA ocupa casi todo el ancho (hasta inicio de ESTADO ~ 13 cols)
        ruta_w = U*2 + U*2 + U + U + U + U + U + int(U*1.25) + max(1,U//2) + max(1,U//2) + U + max(1,U//2) + max(1,U//2)
        add_header_cell(fr45, 'RUTA', 0, 0, ruta_w)
        add_header_cell(fr45, 'OBSERV.', 0, 1, U*2)

        ruta_str = (getattr(f, 'fp_route', '') or '') if f is not None else ''
        if len(ruta_str) > 90:
            ruta_str = ruta_str[:90] + '...'
        ruta_lbl = tix.Label(fr45, text=ruta_str, bg=BG_FIELD, fg=FG,
                             font=('Arial', 7), anchor='w', width=ruta_w,
                             relief='sunken', bd=1)
        ruta_lbl.grid(row=1, column=0, padx=1, pady=1, sticky='ew')

        # OBSERV. = rutrod editable (siempre en mayusculas, max 10 caracteres)
        ob_var = tix.StringVar()
        ob_val = (getattr(f, 'rutrod', '--') if f is not None else '--') or '--'
        ob_var.set(ob_val.upper())
        ob_entry = tix.Entry(fr45, textvariable=ob_var, bg=BG_FIELD, fg='yellow',
                             font=FONT_VALUE, width=U*2, relief='sunken', bd=1,
                             insertbackground='yellow')
        ob_entry.grid(row=1, column=1, padx=1, pady=1, sticky='ew')

        # Forzar mayusculas mientras escribe (consistente con OSF.py)
        def _ob_normalize(*args):
            v = ob_var.get()
            if len(v) > 10:
                v = v[:10]
            if v != v.upper():
                v = v.upper()
            if v != ob_var.get():
                ob_var.set(v)
        ob_var.trace("w", _ob_normalize)

        _ob_confirmed = [False]  # flag para evitar envios duplicados

        def on_ob_confirm(event=None):
            if f is None or _ob_confirmed[0]:
                return
            _ob_confirmed[0] = True
            nuevo = ob_var.get().strip().upper()[:10]
            if not nuevo:
                nuevo = '--'
            if hasattr(self.master, 'sendMessage'):
                self.master.sendMessage({"message": "set_rutrod", "cs": f.callsign, "rutrod": nuevo})

        ob_entry.bind('<Return>', on_ob_confirm)

        # =================================================================
        # FILA 6 (row=6): Linea vacia separadora
        # =================================================================
        sep6 = tix.Frame(ventana_pv, bg=BG, height=4)
        sep6.grid(row=6, column=0, columnspan=NCOLS, sticky='ew')
        sep6.grid_propagate(False)

        # =================================================================
        # FILA 7 (row=7): Headers tiempos
        # RFL(1), EOBT(1.25), CTOT(1.25), C.REG.(2), ELDT(1.25),
        # R(0.5), T(0.5), E.NCA(4), SSR(2), AALT(1), SELC(1), RFP(0.8), NIV2(1)
        # =================================================================
        fr78 = make_row_frame(ventana_pv, 7)

        if f is not None:
            rfl_str = str(int(getattr(f, 'rfl', 0))) if getattr(f, 'rfl', 0) else '--'

            eobt_str = '--'
            eobt = getattr(f, 'eobt', None)
            if eobt:
                try:
                    eobt_str = eobt.strftime('%H%M')
                except Exception:
                    eobt_str = str(eobt)

            ctot_str = '--'
            ctot = getattr(f, 'ctot', None)
            if ctot:
                try:
                    ctot_str = ctot.strftime('%H%M')
                except Exception:
                    ctot_str = str(ctot)
        else:
            rfl_str = '--'
            eobt_str = '--'
            ctot_str = '--'

        # col, header, width, valor
        cols_fila7 = [
            (0,  'RFL',       U,              rfl_str),
            (1,  'EOBT',      int(U*1.25),    eobt_str),
            (2,  'CTOT',      int(U*1.25),    ctot_str),
            (3,  'C. REG.',   U*2,            '--'),
            (4,  'ELDT',      int(U*1.25),    '--'),
            (5,  'R',         max(1, U//2),   '--'),
            (6,  'T',         max(1, U//2),   '--'),
            (7,  'E. NCA',    U*4,            '--'),
            (8,  'SSR',       U*2,            squawk_str),
            (9,  'AALT',      U,              '--'),
            (10, 'SELC',      U,              '--'),
            (11, 'RFP',       max(1, int(U*0.8)), '--'),
            (12, 'NIV2',      U,              '--'),
        ]
        for col, header, width, val in cols_fila7:
            add_header_cell(fr78, header, 0, col, width)
            add_value_cell(fr78, val, 1, col, width)

        # =================================================================
        # FILA 9 (row=9): Linea separadora blanca + titulo + botones
        # =================================================================
        sep_frame = tix.Frame(ventana_pv, bg=BG)
        sep_frame.grid(row=9, column=0, columnspan=NCOLS, sticky='ew', padx=2, pady=2)

        # Linea blanca
        linea_blanca = tix.Frame(sep_frame, bg='white', height=2)
        linea_blanca.pack(fill='x', pady=(4, 2))
        linea_blanca.pack_propagate(False)

        # Titulo INFORMACION DE PV en amarillo
        titulo = tix.Label(sep_frame, text='INFORMACION DE PV', bg=BG, fg='yellow',
                           font=FONT_TITLE)
        titulo.pack(anchor='w', pady=(2, 4))

        # Botones alineados a la derecha
        frame_botones = tix.Frame(sep_frame, bg=BG)
        frame_botones.pack(anchor='e', pady=(0, 4))

        # EJECUTAR - aplica los cambios de los campos editables y cierra la ventana
        def ejecutar_cambios():
            on_ob_confirm()
            self.close_windows()

        btn_ejecutar = tix.Button(frame_botones, text='EJECUTAR', bg='white', fg='black',
                                  font=FONT_BTN, width=10, height=1, command=ejecutar_cambios)
        btn_ejecutar.pack(side='left', padx=2)

        btn_analizar = tix.Button(frame_botones, text='ANALIZAR', bg='white', fg='black',
                                  font=FONT_BTN, width=10, height=1)
        btn_analizar.pack(side='left', padx=2)

        # ANULAR (rojo) - cierra la ventana sin guardar cambios
        btn_anular = tix.Button(frame_botones, text='ANULAR', bg='#CC3333', fg='white',
                                font=FONT_BTN, width=8, height=1,
                                command=lambda: self.close_windows())
        btn_anular.pack(side='left', padx=2)

        btn_fijo = tix.Button(frame_botones, text='FIJO/SECT', bg='white', fg='black',
                              font=FONT_BTN, width=8, height=1)
        btn_fijo.pack(side='left', padx=2)

        # ANOTACIONES - funcional: da focus al campo OBSERV.
        def abrir_anotaciones():
            ob_entry.focus_set()
            ob_entry.select_range(0, 'end')

        btn_anot = tix.Button(frame_botones, text='ANOTACIONES', bg='white', fg='black',
                              font=FONT_BTN, width=12, height=1, command=abrir_anotaciones)
        btn_anot.pack(side='left', padx=2)

        # V. HISTORICO - abre ventana con log de autorizaciones (desde Aircraft.history)
        def abrir_historico():
            if f is None:
                return
            cs = f.callsign
            hist = getattr(f, 'history', [])
            hist_win = tix.Toplevel(ventana_pv)
            hist_win.title('Historico - %s' % cs)
            hist_win.configure(bg=BG)
            hist_win.geometry('550x350')
            hist_win.attributes('-topmost', True)

            titulo_h = tix.Label(hist_win, text='HISTORICO DE %s' % cs,
                                 bg=BG, fg='yellow', font=FONT_TITLE)
            titulo_h.pack(pady=4)

            # Cabecera
            hdr_frame = tix.Frame(hist_win, bg=BG)
            hdr_frame.pack(fill='x', padx=4)
            tix.Label(hdr_frame, text='  HORA      SECTOR          ACCION',
                      bg=BG, fg=FG_HEADER, font=('Courier', 8, 'bold'), anchor='w').pack(fill='x')

            frame_list = tix.Frame(hist_win, bg=BG)
            frame_list.pack(fill='both', expand=True, padx=4, pady=4)

            scrollbar = tix.Scrollbar(frame_list)
            scrollbar.pack(side='right', fill='y')

            listbox = tix.Listbox(frame_list, bg=BG_FIELD, fg=FG,
                                  font=('Courier', 8), yscrollcommand=scrollbar.set,
                                  width=70, height=18)
            listbox.pack(side='left', fill='both', expand=True)
            scrollbar.config(command=listbox.yview)

            if not hist:
                listbox.insert('end', '  (Sin registros)')
            else:
                for entry in hist:
                    if len(entry) == 3:
                        t_str, sector, desc = entry
                        listbox.insert('end', '  [%s]  %-14s  %s' % (t_str, sector, desc))
                    elif len(entry) == 2:
                        t_str, desc = entry
                        listbox.insert('end', '  [%s]  %-14s  %s' % (t_str, '?', desc))
                listbox.see('end')

            btn_cerrar = tix.Button(hist_win, text='Cerrar', bg='white', fg='black',
                                    font=FONT_BTN, width=8, command=hist_win.destroy)
            btn_cerrar.pack(pady=4)

        btn_hist = tix.Button(frame_botones, text='V. HISTORICO', bg='white', fg='black',
                              font=FONT_BTN, width=10, height=1, command=abrir_historico)
        btn_hist.pack(side='left', padx=2)

        # --- Drag para mover la ventana por el canvas ---
        drag_data = {'x': 0, 'y': 0}

        def on_drag_start(event):
            drag_data['x'] = event.x_root
            drag_data['y'] = event.y_root

        def on_drag_motion(event):
            dx = event.x_root - drag_data['x']
            dy = event.y_root - drag_data['y']
            drag_data['x'] = event.x_root
            drag_data['y'] = event.y_root
            coords = w.coords(self._info_pv_window_id)
            if coords:
                w.coords(self._info_pv_window_id, coords[0] + dx, coords[1] + dy)

        ventana_pv.bind('<ButtonPress-1>', on_drag_start)
        ventana_pv.bind('<B1-Motion>', on_drag_motion)
        barra_frame.bind('<ButtonPress-1>', on_drag_start)
        barra_frame.bind('<B1-Motion>', on_drag_motion)

        # --- Posicionar ventana centrada en el canvas ---
        alto = self.master.height
        ancho = self.master.width
        x_pos = ancho / 2
        y_pos = alto / 2

        i = w.create_window(x_pos, y_pos, window=ventana_pv, anchor='center')
        self._info_pv_window_id = i
        self._info_pv_ventana_frame = ventana_pv
        self.opened_windows.append(i)
        self._info_pv_window_open = True

        # La ventana se cierra con: F3 (toggle), boton X, o boton EJECUTAR

    def create_toggle_button(self, parent, button_config, original_command=None):
        """
        Crea un boton con toggle visual (cambia de color al presionar)
        """
        # Estado del boton (apagado por defecto)
        button_state = {'active': False}
        
        def toggle_and_execute():
            """Toggle visual + ejecutar comando original"""
            button_state['active'] = not button_state['active']
            
            # Estado de botones global
            if button_state['active'] and original_command is not None:
                button.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
                if button not in self.active_buttons:
                    self.active_buttons.append(button)
                self.any_button_pressed = len(self.active_buttons) > 0
            elif button_state['active'] and original_command is None:
                button.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
            else:
                button.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                if button in self.active_buttons:
                    self.active_buttons.remove(button)
                self.any_button_pressed = len(self.active_buttons) > 0
                
            #ejecutar comando siempre para permitir toggle
            if original_command is not None:
                    original_command()
        
        # Crear el boton con la funcion wrapeada
        button = tix.Button(parent, **button_config)
        button.configure(command=toggle_and_execute, 
                        bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        
        # Guardar referencia al estado para acceso externo
        button.toggle_state = button_state
        
        return button
    
    def wrap_button_with_toggle(self, button):
        """
        Envuelve un boton existente con funcionalidad de toggle visual
        util para botones cuyo command se asigna despues de crearlos

        Args:
            button: Boton existente a envolver
        """
        button_state = {'active': False}
        original_command_holder = {'func': None}
        
        def toggle_wrapper():
            """Toggle visual + ejecutar comando asignado"""
            button_state['active'] = not button_state['active']
            
            if button_state['active'] and original_command_holder['func'] is not None:
                button.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
                if button not in self.active_buttons:
                    self.active_buttons.append(button)
                self.any_button_pressed = len(self.active_buttons) > 0
            elif button_state['active'] and original_command_holder['func'] is None:
                button.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
            else:
                button.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                if button in self.active_buttons:
                    self.active_buttons.remove(button)
                self.any_button_pressed = len(self.active_buttons) > 0

            #ejecutar funcion siempre (para permitir toggle)
            if original_command_holder['func'] is not None:
                    original_command_holder['func']()
        
        # Guardar la configuracion original del boton
        button.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        button.toggle_state = button_state
        button._original_command_holder = original_command_holder
        button._toggle_wrapper = toggle_wrapper
        
        # Sobrescribir __setitem__ para interceptar asignacion de command
        original_setitem = button.__setitem__
        
        def custom_setitem(key, value):
            if key == 'command':
                # Guardar la funcion original
                original_command_holder['func'] = value
                # Asignar el wrapper en su lugar
                original_setitem(key, toggle_wrapper)
            else:
                original_setitem(key, value)
        
        button.__setitem__ = custom_setitem

    def b_show_hide_localmaps(self):
        master = self.master
        master.local_maps_shown = []
        for map_name in master.fir.local_maps:
            try:
                if self.var_ver_localmap[map_name].get() != 0:
                    master.local_maps_shown.append(map_name)
                    master.maps[map_name].show()
                else:
                    master.maps[map_name].hide()
            except:
                logging.debug("Unable to show/hide localmaps", exc_info=True)

    def redraw(self):
        master = self.master
        w = master.c
        ancho = master.width
        alto = master.height
        scale = master.scale

        w.delete(self.toolbar_id)
        
        # ===== CONFIGURACION DE TAMANOS DE BOTONES =====
        # Altura uniforme para todos los botones (en lineas de texto)
        BUTTON_HEIGHT = 1
        
        # Altura para botones con bitmap (en pixeles, aprox 2 lineas)
        BUTTON_HEIGHT_PX = 25
        
        # Ancho base de botones (en caracteres)
        # Ajustar segun numero de botones por fila
        BUTTON_WIDTH_NORMAL = 8   # Ancho normal
        BUTTON_WIDTH_HALF = 4     # Mitad de ancho

        #para fuentes pequenas
        SMALL_FONT = ('TkDefaultFont', 7)

        MINIMUM_DISPLACEMENT = 80
        NORMAL_DISPLACEMENT = 10
        MAXIMUM_DISPLACEMENT = 3

        def set_displacement(mouse_pressed_button):
            if mouse_pressed_button == 1:
                return NORMAL_DISPLACEMENT
            elif mouse_pressed_button == 2:
                return MAXIMUM_DISPLACEMENT
            elif mouse_pressed_button == 3:
                return MINIMUM_DISPLACEMENT

        def b_izquierda(event):
            # master.x0 -= ancho/set_displacement(event.num)/scale
            master.center_x += ancho / set_displacement(event.num)
            master.reposition()

        def b_derecha(event):
            # master.x0 += ancho/set_displacement(event.num)/scale
            master.center_x -= ancho / set_displacement(event.num)
            master.reposition()

        def b_arriba(event):
            # master.y0 += ancho/set_displacement(event.num)/scale
            # master.center_y += alto/set_displacement(event.num)
            # master.reposition()
            master.center_y += alto / set_displacement(event.num)
            master.reposition()

        def b_abajo(event):
            # master.y0 -= ancho/set_displacement(event.num)/scale
            # master.center_y -= alto/set_displacement(event.num)
            # master.reposition()
            master.center_y -= alto / set_displacement(event.num)
            master.reposition()

        MINIMUM_SCALE_FACTOR = 1.01
        NORMAL_SCALE_FACTOR = 1.1
        MAXIMUM_SCALE_FACTOR = 1.5

        LABEL_MIN_FONT_SIZE = 8
        LABEL_MAX_FONT_SIZE = 12
        LABEL_SIZE_STEP = 1

        def set_zoom_scale_on_event(event_number=1):
            if event_number == 3:
                return MINIMUM_SCALE_FACTOR
            elif event_number == 2:
                return MAXIMUM_SCALE_FACTOR
            elif event_number == 1:
                return NORMAL_SCALE_FACTOR

        def b_zoom_mas(event):
            master.scale *= set_zoom_scale_on_event(event.num)
            master.reposition()
            update_scale_display()

        def b_zoom_menos(event):
            master.scale /= set_zoom_scale_on_event(event.num)
            master.reposition()
            update_scale_display()

        def b_standard():
            master.center_x = ancho / 2
            master.center_y = (alto - 40.) / 2
            master.get_scale()
            master.reposition()
            update_scale_display()

        def scale_to_nm(scale):
            """Convierte valor de scale a millas nauticas
            Basado en: scale 469.7 = 0.84 NM (rodadura visible)
            """
            if scale == 0:
                return 0.0
            nm_value = (469.7 * 0.84) / scale
            return nm_value
        
        def update_scale_display():
            """Actualiza el display de escala de zoom en formato NM"""
            nm_value = scale_to_nm(master.scale)
            scale_text = "%.1f NM" % nm_value
            self.distance_var.set(scale_text)

        def b_tamano_fichas(event):
            if event.num == 1:
                step_increment = LABEL_SIZE_STEP
            elif event.num == 3:
                step_increment = -LABEL_SIZE_STEP
            elif event.num == 2:
                step_increment = LABEL_MIN_FONT_SIZE

            font_size = master.label_font_size
            font_size += step_increment
            if font_size > LABEL_MAX_FONT_SIZE:
                font_size = LABEL_MIN_FONT_SIZE
            elif font_size < LABEL_MIN_FONT_SIZE:
                font_size = LABEL_MAX_FONT_SIZE
            master.label_font_size = font_size

            for vt in self.master.tracks:
                vt.l_font_size = font_size
            master.label_font.configure(size=master.label_font_size)


        
        def b_auto_separationaration():
            global auto_separation
            auto_separation = not auto_separation

        # def quitar_fpr():
        #     for a in ejercicio:
        #         if w.itemcget(a.callsign + 'fpr', 'fill') == 'orange':
        #             w.delete(a.callsign + 'fpr')

        def quitar_lads():
            global all_lads, superlad
            for lad_to_remove in all_lads:
                if lad_to_remove.line_id != None: w.delete(lad_to_remove.line_id)
                if lad_to_remove.text_id1 != None: w.delete(lad_to_remove.text_id1)
                if lad_to_remove.text_id2 != None: w.delete(lad_to_remove.text_id2)
                if lad_to_remove.text_id3 != None: w.delete(lad_to_remove.text_id3)
                if lad_to_remove.text_id4 != None: w.delete(lad_to_remove.text_id4)
                #     all_lads.remove(lad_to_remove)
                #     lad_to_remove.destroy()
                if superlad == lad_to_remove: superlad = None
            all_lads = []

        win_identifier = None

        def ver_detalles():
            """Show a dialog to view details of the selected flight"""
            sel = self.master.selected_track
            if sel == None:
                RaDialog(w, label='Ver Detalles', text='No hay ningún vuelo seleccionado')
                return
            # TODO The RaDialog should probably export the contents frame
            # and we could use it here to build the contents using a proper grid
            RaDialog(self.master.c, label=sel.cs + ': Detalles',
                     text='Origen: ' + sel.adep +
                          '\tDestino: ' + sel.ades +
                          '\nTipo:   ' + sel.type.ljust(4) +
                          '\tRFL:     ' + str(int(sel.rfl)) +
                          '\nCallsign: ' + sel.radio_cs)

        """Desde aqui comienza parte visual de botonera a editar para estilo mas SACTA"""

        """===== Nueva botonera tipo SACTA (4 filas) ====="""
        # Crear frame UNIFICADO con fondo oscuro
        ventana = tix.Frame(w, bg="#534d4d", width=ancho)
        
        # ===== GRID UNIFICADO: 23 columnas globales =====
        NUM_COLUMNAS = 42
        for col in range(NUM_COLUMNAS):
            ventana.grid_columnconfigure(col, weight=1, uniform='unified')
        
        # Configurar 4 filas
        for row in range(4):
            ventana.grid_rowconfigure(row, weight=1)


            #elif isinstance(child, tix.Checkbutton):
            #    print(f"Checkbutton encontrado: {child}")

            #elif isinstance(child, tix.Button) and hasattr(child, 'toggle_state'):
            #    print(f"Botón con toggle encontrado: {child}")
            #    # Acceder al estado del toggle:
            #    # is_active = child.toggle_state['active']

        
        """===== FILA 1 (Abajo - row 3) ====="""
        # Usar ventana directamente en lugar de fila1_frame
        current_col = 0


        # self.but_inicio = tix.Button(ventana,bitmap='@'+IMGDIR+'start.xbm',state=DISABLED)
        # self.but_inicio.pack(side=LEFT,expand=1,fill=X)
        # self.but_parar = tix.Button(ventana,bitmap='@'+IMGDIR+'pause.xbm',state=DISABLED)
        # self.but_parar.pack(side=LEFT,expand=1,fill=X)

        self.but_menu = self.create_toggle_button(ventana, {'text': 'MENU', 'height': BUTTON_HEIGHT}, None)
        self.but_menu.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        def mapas_buttons():
            if self._mapas_window_open:
                self.close_windows()
                return

            self.close_windows()

            BG = '#534d4d'
            FG = 'white'
            FONT = ('Helvetica', 8)

            popup = tix.Toplevel(w)
            popup.overrideredirect(True)
            popup.configure(bg=BG)

            SPLIT = 36
            maps = list(self.master.fir.local_maps_order)
            maps1 = maps[:SPLIT]
            maps2 = maps[SPLIT:]

            def make_cb(parent, idx, map_name):
                label = '{:2d} {}'.format(idx + 1, map_name)
                return tix.Checkbutton(parent, text=label,
                                       variable=self.var_ver_localmap[map_name],
                                       command=self.b_show_hide_localmaps,
                                       bg=BG, fg=FG, selectcolor='#6a6060',
                                       activebackground='#6a6060', activeforeground=FG,
                                       font=FONT, anchor='w', padx=4, pady=0,
                                       indicatoron=1)

            # --- Primera ventana: mapas 1-36 ---
            inner = tix.Frame(popup, bg=BG)
            inner.grid(row=0, column=0, sticky='nsew')
            for idx, map_name in enumerate(maps1):
                make_cb(inner, idx, map_name).grid(row=idx, column=0, sticky='ew')

            popup.update_idletasks()
            popup_w = popup.winfo_reqwidth()
            menu_h = popup.winfo_reqheight()
            bx = self.but_ver_maps.winfo_rootx()
            by = self.but_ver_maps.winfo_rooty()
            popup.geometry('+{}+{}'.format(bx, by - menu_h))

            self._mapas_toplevel = popup
            self._mapas_window_open = True

            # --- Segunda ventana: mapas 37+ ---
            if maps2:
                popup2 = tix.Toplevel(w)
                popup2.overrideredirect(True)
                popup2.configure(bg=BG)
                inner2 = tix.Frame(popup2, bg=BG)
                inner2.grid(row=0, column=0, sticky='nsew')
                for idx, map_name in enumerate(maps2):
                    make_cb(inner2, SPLIT + idx, map_name).grid(row=idx, column=0, sticky='ew')

                popup2.update_idletasks()
                menu_h2 = popup2.winfo_reqheight()
                popup2.geometry('+{}+{}'.format(bx + popup_w + 2, by - menu_h2))
                self._mapas_toplevel2 = popup2

        self.but_ver_maps = tix.Button(ventana, text='MAPAS', height=BUTTON_HEIGHT)
        self.wrap_button_with_toggle(self.but_ver_maps)
        self.but_ver_maps.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        self.but_ver_maps['command'] = mapas_buttons

        self.but_dates = self.create_toggle_button(ventana, {'text': 'DAT AES', 'height': BUTTON_HEIGHT}, None)
        self.but_dates.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        #AALWGND
        self.but_orient = tix.Button(ventana, text="GEOSTANDAR", height=BUTTON_HEIGHT, font=SMALL_FONT)
        self.wrap_button_with_toggle(self.but_orient)  # Aplicar toggle
        self.but_orient.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_orient.pack(side=LEFT,expand=1,fill=X)

        # Parametro de escenario 'orientaciones' (por defecto NORTH,FIELD; LEMD FIELD,NORTH,EAST,SOUTH,WEST)
        orientations = list(master.fir.param('orientaciones', ['NORTH', 'FIELD'])) or ['NORTH', 'FIELD']

        def orient_buttons():
            # Si abierta, cerrar con variable de estado
            if self._orient_window_open:
                self.close_windows()
                return
            
            # Si esta cerrada, abrir
            self.close_windows()
            ventana_orient = tix.Frame(w, bg='gray')
            irow = 0
            for orientation in orientations:
                command = lambda x=orientation: select(x)
                self.but_north = tix.Button(ventana_orient, text=orientation, command=command)
                self.but_north.grid(column=0, row=irow, sticky=tix.E + tix.W)
                irow += 1

            i = w.create_window(ventana.winfo_x() + self.but_orient.winfo_x(), alto - ventana.winfo_height(),
                                window=ventana_orient, anchor='sw')
            self._orient_window_id = i
            self.opened_windows.append(i)
            self._orient_window_open = True

        self.but_orient['command'] = orient_buttons

        def select(value):
            self.close_windows()
            master.orient = value
            self.but_orient['text'] = value
            # if self.filterFGND:
            #     master.refresco = 1.
            # else:
            #     master.refresco = 5.

            if value == 'FIELD' or value == 'NORTH':
                master.refresco = 1.
            else:
                master.refresco = 5.

            master.reposition()

        #ZOOM in/out pequenos
        self.but_zoom_in_small = tix.Button(ventana, bitmap='@' + IMGDIR + 'zoom_small.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_zoom_in_small.bind("<Button-1>", lambda e: b_zoom_mas(type('obj', (object,), {'num':3})()))
        self.but_zoom_in_small.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_zoom_out_small = tix.Button(ventana, bitmap='@' + IMGDIR + 'unzoom_small.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_zoom_out_small.bind("<Button-1>", lambda e: b_zoom_menos(type('obj', (object,), {'num':3})()))
        self.but_zoom_out_small.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_descent = self.create_toggle_button(ventana, {'text': 'DESC', 'height': BUTTON_HEIGHT}, None)
        self.but_descent.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_standard = self.create_toggle_button(ventana, {'text': 'CENT', 'height': BUTTON_HEIGHT}, b_standard)
        self.but_standard.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_standard.pack(side=LEFT,expand=1,fill=X) 

        #ZOOM in/out grandes
        self.but_zoom_in_big = tix.Button(ventana, bitmap='@' + IMGDIR + 'zoom.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_zoom_in_big.bind("<Button-1>", b_zoom_mas)
        self.but_zoom_in_big.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_zoom_out_big = tix.Button(ventana, bitmap='@' + IMGDIR + 'unzoom.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_zoom_out_big.bind("<Button-1>", b_zoom_menos)
        self.but_zoom_out_big.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_izq = tix.Button(ventana, bitmap='@' + IMGDIR + 'left.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_izq.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_izq.pack(side=LEFT,expand=1,fill=X)
        self.but_izq.bind("<Button-1>", b_izquierda)
        self.but_izq.bind("<Button-2>", b_izquierda)
        self.but_izq.bind("<Button-3>", b_izquierda)

        self.but_derecha = tix.Button(ventana, bitmap='@' + IMGDIR + 'right.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_derecha.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_derecha.pack(side=LEFT,expand=1,fill=X)
        self.but_derecha.bind("<Button-1>", b_derecha)
        self.but_derecha.bind("<Button-2>", b_derecha)
        self.but_derecha.bind("<Button-3>", b_derecha)

        self.but_abajo = tix.Button(ventana, bitmap='@' + IMGDIR + 'down.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_abajo.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_abajo.pack(side=LEFT,expand=1,fill=X)
        self.but_abajo.bind("<Button-1>", b_abajo)
        self.but_abajo.bind("<Button-2>", b_abajo)
        self.but_abajo.bind("<Button-3>", b_abajo)

        self.but_arriba = tix.Button(ventana, bitmap='@' + IMGDIR + 'up.xbm', height=BUTTON_HEIGHT_PX, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_arriba.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_arriba.pack(side=LEFT,expand=1,fill=X)
        self.but_arriba.bind("<Button-1>", b_arriba)
        self.but_arriba.bind("<Button-2>", b_arriba)
        self.but_arriba.bind("<Button-3>", b_arriba)

        self.but_desccon = self.create_toggle_button(ventana, {'text': 'DESC\nCON', 'height': BUTTON_HEIGHT}, None)
        self.but_desccon.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        # Definir funcion toggle_filterFGND ANTES de usarla
        def toggle_filterFGND():
            # Sincronizar filterFGND con el estado del boton (activo = True, inactivo = False)
            self.filterFGND = master.filterFGND = but_filterFGND.toggle_state['active']
            # Actualizar todos los tracks para aplicar el filtro inmediatamente
            master.update_tracks()
        
        but_filterFGND = self.create_toggle_button(ventana, {'text': 'FGND', 'height': BUTTON_HEIGHT}, toggle_filterFGND)
        but_filterFGND.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        # Sincronizar estado inicial del boton con filterFGND
        if self.filterFGND:
            but_filterFGND.toggle_state['active'] = True
            but_filterFGND.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
            if but_filterFGND not in self.active_buttons:
                self.active_buttons.append(but_filterFGND)
        current_col += 2

        self.but_sombra = self.create_toggle_button(ventana, {'text': 'SOMBRA', 'height': BUTTON_HEIGHT}, None)
        self.but_sombra.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        # FALT: filtro de altitud con selector emergente MIN/MAX + boton on/off
        self._falt_min_textvar = tix.StringVar(ventana)
        self._falt_max_textvar = tix.StringVar(ventana)

        def _update_falt_labels(*_args):
            min_val = int(self.master.select_FALT_varmin.get())
            max_val = int(self.master.select_FALT_varmax.get())
            self._falt_min_textvar.set('%03d' % min_val)
            self._falt_max_textvar.set('%03d' % max_val)
            enabled = self.master._falt_enabled
            but_min = getattr(self, 'but_falt_min', None)
            but_max = getattr(self, 'but_falt_max', None)
            if but_min:
                if enabled and min_val > 0:
                    but_min.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
                else:
                    but_min.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
            if but_max:
                if enabled and max_val < 990:
                    but_max.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
                else:
                    but_max.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)

        def _toggle_falt():
            self.master._falt_enabled = not self.master._falt_enabled
            but_falt = getattr(self, 'but_falt', None)
            if but_falt:
                if self.master._falt_enabled:
                    but_falt.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
                else:
                    but_falt.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
            _update_falt_labels()
            master.update_tracks()

        self.master.select_FALT_varmin.trace('w', _update_falt_labels)
        self.master.select_FALT_varmax.trace('w', _update_falt_labels)
        _update_falt_labels()

        # --- Toplevel reutilizable para elegir un valor de altitud ---
        self._falt_selector_win = None

        def open_falt_selector(is_min, anchor_button):
            """Abre Toplevel con Listbox+Entry para elegir MIN o MAX."""
            if self._falt_selector_win is not None:
                try:
                    self._falt_selector_win.destroy()
                except Exception:
                    pass
                self._falt_selector_win = None

            var = self.master.select_FALT_varmin if is_min else self.master.select_FALT_varmax
            title_text = 'FALT INF' if is_min else 'FALT SUP'

            win = tix.Toplevel(ventana)
            win.title(title_text)
            win.resizable(False, False)
            win.configure(bg=self.NORMAL_BG)
            win.overrideredirect(True)
            self._falt_selector_win = win

            # Crear widgets primero, luego posicionar tras calcular altura real
            anchor_button.update_idletasks()
            bx = anchor_button.winfo_rootx()
            by = anchor_button.winfo_rooty()
            win.geometry('+%d+%d' % (-2000, -2000))  # fuera de pantalla hasta posicionar

            # Barra de titulo con aspa de cierre
            frame_title = tix.Frame(win, bg='#3a3535')
            frame_title.pack(fill='x')
            tix.Label(frame_title, text=title_text, bg='#3a3535', fg=self.NORMAL_FG,
                      font=SMALL_FONT).pack(side='left', padx=4)
            btn_close = tix.Button(frame_title, text='x', bg='#3a3535', fg=self.NORMAL_FG,
                                   font=SMALL_FONT, relief='flat', bd=0,
                                   activebackground='#666060', activeforeground='white',
                                   padx=4, pady=0)
            btn_close.pack(side='right')

            frame_list = tix.Frame(win, bg=self.NORMAL_BG)
            frame_list.pack(fill='both', expand=True, padx=2, pady=2)

            scrollbar = tix.Scrollbar(frame_list, orient='vertical')
            # 990 arriba, 000 abajo
            values = ['%03d' % v for v in range(990, -10, -10)]
            listbox = tix.Listbox(frame_list, yscrollcommand=scrollbar.set,
                                  height=8, width=6,
                                  bg='#3a3535', fg=self.NORMAL_FG,
                                  selectbackground='#7a7070',
                                  font=SMALL_FONT, exportselection=False)
            scrollbar.configure(command=listbox.yview)
            scrollbar.pack(side='right', fill='y')
            listbox.pack(side='left', fill='both', expand=True)

            for v in values:
                listbox.insert('end', v)

            # Preseleccionar el valor actual (indice en lista invertida)
            current_val = int(var.get())
            current_idx = (990 - (current_val // 10) * 10) // 10
            if 0 <= current_idx < len(values):
                listbox.selection_set(current_idx)
                listbox.see(current_idx)

            entry_var = tix.StringVar(win, value='%03d' % current_val)
            entry = tix.Entry(win, textvariable=entry_var, width=6,
                              bg='#a0a0a0', fg=self.NORMAL_FG,
                              insertbackground=self.NORMAL_FG,
                              font=SMALL_FONT)
            entry.pack(fill='x', padx=2, pady=(0, 2))

            # Posicionar ahora que los widgets tienen altura real
            win.update_idletasks()
            win_h = win.winfo_reqheight()
            win.geometry('+%d+%d' % (bx, by - win_h - 60))

            def _close_selector():
                try:
                    if self._falt_selector_win is win:
                        win.destroy()
                        self._falt_selector_win = None
                except Exception:
                    pass

            btn_close.configure(command=_close_selector)

            def _apply_and_close(raw):
                try:
                    # Campo libre: se aplica el valor exacto introducido, solo acotado
                    # a [0, 990] (la lista usa multiplos de 10, pero el Entry no obliga a ello)
                    val = max(0, min(990, int(raw)))
                    var.set(val)
                    master.update_tracks()
                except ValueError:
                    pass
                _close_selector()

            def _on_listbox_select(*_):
                sel = listbox.curselection()
                if sel:
                    _apply_and_close(listbox.get(sel[0]))

            def _on_entry_enter(*_):
                _apply_and_close(entry_var.get())

            # Rueda del raton -> scroll del listbox
            def _on_mousewheel(event):
                listbox.yview('scroll', -1 if event.delta > 0 else 1, 'units')

            listbox.bind('<MouseWheel>', _on_mousewheel)
            win.bind('<MouseWheel>', _on_mousewheel)

            # Limitar Entry a 3 caracteres numericos
            def _validate_entry(P):
                return P.isdigit() and len(P) <= 3 or P == ''

            vcmd = win.register(_validate_entry)
            entry.configure(validate='key', validatecommand=(vcmd, '%P'))

            listbox.bind('<ButtonRelease-1>', _on_listbox_select)
            entry.bind('<Return>', _on_entry_enter)

            entry.focus_set()

        # Boton MIN (valor inferior del filtro de altitud)
        self.but_falt_min = tix.Button(ventana, textvariable=self._falt_min_textvar,
                                       height=BUTTON_HEIGHT, font=SMALL_FONT,
                                       bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_falt_min.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        self.but_falt_min.bind('<Button-1>', lambda *_: open_falt_selector(True, self.but_falt_min))
        current_col += 2

        # Boton MAX (valor superior del filtro de altitud)
        self.but_falt_max = tix.Button(ventana, textvariable=self._falt_max_textvar,
                                       height=BUTTON_HEIGHT, font=SMALL_FONT,
                                       bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_falt_max.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        self.but_falt_max.bind('<Button-1>', lambda *_: open_falt_selector(False, self.but_falt_max))
        current_col += 2

        # Boton FALT (master on/off del filtro de altitud)
        self.but_falt = tix.Button(ventana, text='FALT', height=BUTTON_HEIGHT,
                                   font=SMALL_FONT, bg=self.NORMAL_BG, fg=self.NORMAL_FG,
                                   command=_toggle_falt)
        self.but_falt.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        # Funcion para cambiar a una escala predefinida
        def set_predefined_scale(nm_target):
            """Ajusta master.scale para mostrar un valor especifico en NM"""
            # Calcular scale necesario: scale = (469.7 * 0.84) / nm_target
            master.scale = (469.7 * 0.84) / nm_target
            master.reposition()
            update_scale_display()
        
        # Crear menu desplegable para escalas predefinidas
        def show_scale_menu(event=None):
            """Muestra menu con escalas predefinidas"""
            menu = tix.Menu(self.but_distance, tearoff=0, bg='#534d4d', fg='white')
            
            # Escalas predefinidas del sistema real SACTA
            predefined_scales = [0.84, 4.0, 8.0, 16.0, 24.0, 32.0, 40.0]
            
            for nm_value in predefined_scales:
                menu.add_command(
                    label="%.2f NM" % nm_value if nm_value < 1.0 else "%.1f NM" % nm_value,
                    command=lambda nm=nm_value: set_predefined_scale(nm)
                )
            
            # Mostrar menu en posicion del mouse
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        
        self.distance_var = tix.StringVar()
        self.distance_var.set("-- NM")
        self.but_distance = tix.Button(ventana, textvariable=self.distance_var, height=BUTTON_HEIGHT, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_distance.grid(row=3, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        self.but_distance.bind("<Button-1>", show_scale_menu)  # Click izquierdo abre menu
        current_col += 2
        update_scale_display()  # Inicializar con escala actual

        """===== FILA 2 ====="""
        current_col = 0

        self.but_sonidodcl = self.create_toggle_button(ventana, {'text': 'SONIDO\nDCL', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_sonidodcl.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_silenciar_alerta = self.create_toggle_button(ventana, {'text': 'SILENCIAR\nALERTA', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_silenciar_alerta.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_aes_inact = self.create_toggle_button(ventana, {'text': 'AES INACT', 'height': BUTTON_HEIGHT}, None)
        self.but_aes_inact.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_gml = self.create_toggle_button(ventana, {'text': 'GML', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_gml.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        self.but_defecto = self.create_toggle_button(ventana, {'text': 'DEFECTO', 'height': BUTTON_HEIGHT}, None)
        self.but_defecto.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_bri = self.create_toggle_button(ventana, {'text': 'BRILL', 'height': BUTTON_HEIGHT}, master.rabrightness.conmuta)
        self.but_bri.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2
        # self.but_bri.pack(side=LEFT,expand=1,fill=X)

        self.but_or_auto = self.create_toggle_button(ventana, {'text': 'OR\nAUTO', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_or_auto.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        #Para movimiento diagonal (tipo estrella de la muerte aereo)

        # FUNCIONES PARA MOVIMIENTO DIAGONAL DE ETIQUETAS
        def b_arriba_izquierda(event):
            """Mueve etiquetas en diagonal arriba-izquierda
            Si hay etiqueta seleccionada, mueve solo esa. Si no, mueve todas."""
            from math import sin, cos, radians
            
            # Si hay una etiqueta seleccionada, mover solo esa
            if master.selected_track is not None:
                track = master.selected_track
                if track.visible:
                    track.auto_separation = False
                    track.label_heading = 225.0  # Diagonal arriba-izquierda
                    track.label_radius = track.l_font_size * 3
                    new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                    new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                    track.reposition_label(new_label_x, new_label_y)
            else:
                # Si no hay etiqueta seleccionada, mover todas
                for track in master.tracks:
                    if track.visible:
                        track.auto_separation = False
                        track.label_heading = 225.0  # Diagonal arriba-izquierda
                        track.label_radius = track.l_font_size * 3
                        new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                        new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                        track.reposition_label(new_label_x, new_label_y)

        def b_arriba_derecha(event):
            """Mueve etiquetas en diagonal arriba-derecha
            Si hay etiqueta seleccionada, mueve solo esa. Si no, mueve todas."""
            from math import sin, cos, radians
            
            # Si hay una etiqueta seleccionada, mover solo esa
            if master.selected_track is not None:
                track = master.selected_track
                if track.visible:
                    track.auto_separation = False
                    track.label_heading = 135.0  # Diagonal arriba-derecha
                    track.label_radius = track.l_font_size * 3
                    new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                    new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                    track.reposition_label(new_label_x, new_label_y)
            else:
                # Si no hay etiqueta seleccionada, mover todas
                for track in master.tracks:
                    if track.visible:
                        track.auto_separation = False
                        track.label_heading = 135.0  # Diagonal arriba-derecha
                        track.label_radius = track.l_font_size * 3
                        new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                        new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                        track.reposition_label(new_label_x, new_label_y)

        def b_abajo_izquierda(event):
            """Mueve etiquetas en diagonal abajo-izquierda
            Si hay etiqueta seleccionada, mueve solo esa. Si no, mueve todas."""
            from math import sin, cos, radians
            
            # Si hay una etiqueta seleccionada, mover solo esa
            if master.selected_track is not None:
                track = master.selected_track
                if track.visible:
                    track.auto_separation = False
                    track.label_heading = 315.0  # Diagonal abajo-izquierda
                    track.label_radius = track.l_font_size * 3
                    new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                    new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                    track.reposition_label(new_label_x, new_label_y)
            else:
                # Si no hay etiqueta seleccionada, mover todas
                for track in master.tracks:
                    if track.visible:
                        track.auto_separation = False
                        track.label_heading = 315.0  # Diagonal abajo-izquierda
                        track.label_radius = track.l_font_size * 3
                        new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                        new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                        track.reposition_label(new_label_x, new_label_y)

        def b_abajo_derecha(event):
            """Mueve etiquetas en diagonal abajo-derecha
            Si hay etiqueta seleccionada, mueve solo esa. Si no, mueve todas."""
            from math import sin, cos, radians
            
            # Si hay una etiqueta seleccionada, mover solo esa
            if master.selected_track is not None:
                track = master.selected_track
                if track.visible:
                    track.auto_separation = False
                    track.label_heading = 45.0  # Diagonal abajo-derecha
                    track.label_radius = track.l_font_size * 3
                    new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                    new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                    track.reposition_label(new_label_x, new_label_y)
            else:
                # Si no hay etiqueta seleccionada, mover todas
                for track in master.tracks:
                    if track.visible:
                        track.auto_separation = False
                        track.label_heading = 45.0  # Diagonal abajo-derecha
                        track.label_radius = track.l_font_size * 3
                        new_label_x = track.x + track.label_radius * sin(radians(track.label_heading))
                        new_label_y = track.y + track.label_radius * cos(radians(track.label_heading))
                        track.reposition_label(new_label_x, new_label_y)
        
        # Arriba-Izquierda 
        self.but_upleft = tix.Button(ventana, bitmap='@' + IMGDIR + 'upleft.xbm', height=BUTTON_HEIGHT_PX, width=BUTTON_WIDTH_HALF, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_upleft.bind("<Button-1>", b_arriba_izquierda)
        self.but_upleft.bind("<Button-2>", b_arriba_izquierda)
        self.but_upleft.bind("<Button-3>", b_arriba_izquierda)
        self.but_upleft.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # Arriba-Derecha 
        self.but_upright = tix.Button(ventana, bitmap='@' + IMGDIR + 'upright.xbm', height=BUTTON_HEIGHT_PX, width=BUTTON_WIDTH_HALF, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_upright.bind("<Button-1>", b_arriba_derecha)
        self.but_upright.bind("<Button-2>", b_arriba_derecha)
        self.but_upright.bind("<Button-3>", b_arriba_derecha)
        self.but_upright.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # Abajo-Izquierda 
        self.but_downleft = tix.Button(ventana, bitmap='@' + IMGDIR + 'downleft.xbm', height=BUTTON_HEIGHT_PX, width=BUTTON_WIDTH_HALF, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_downleft.bind("<Button-1>", b_abajo_izquierda)
        self.but_downleft.bind("<Button-2>", b_abajo_izquierda)
        self.but_downleft.bind("<Button-3>", b_abajo_izquierda)
        self.but_downleft.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # Abajo-Derecha 
        self.but_downright = tix.Button(ventana, bitmap='@' + IMGDIR + 'downright.xbm', height=BUTTON_HEIGHT_PX, width=BUTTON_WIDTH_HALF, bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_downright.bind("<Button-1>", b_abajo_derecha)
        self.but_downright.bind("<Button-2>", b_abajo_derecha)
        self.but_downright.bind("<Button-3>", b_abajo_derecha)
        self.but_downright.grid(row=2, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        self.but_rac = self.create_toggle_button(ventana, {'text': 'RAC', 'height': BUTTON_HEIGHT}, None)
        self.but_rac.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_metais = self.create_toggle_button(ventana, {'text': 'METAIS', 'height': BUTTON_HEIGHT}, None)
        self.but_metais.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_vrsup = self.create_toggle_button(ventana, {'text': 'VRSUP', 'height': BUTTON_HEIGHT}, None)
        self.but_vrsup.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_vaux = self.create_toggle_button(ventana, {'text': 'VAUX', 'height': BUTTON_HEIGHT}, None)
        self.but_vaux.grid(row=2, column=current_col, padx=0, pady=0, sticky='nsew')
        current_col += 1
        
        def tabs_buttons():
            #si ya esta abierta, solo cerrar
            if self._tabs_window_open:
                self.close_windows()
                return
            
            #si no esta abierta, abrir
            self.close_windows()
            ventana_tabs = tix.Frame(w)

            self.var_ver_coor_tab.set(master.coor_tabular.showed)
            # self.var_ver_predesp_tab.set(master.predesp_tabular.showed)
            self.var_ver_preact_tab.set(master.preact_tabular.showed)
            self.var_ver_act_tab.set(master.act_tabular.showed)
            self.var_ver_windrose.set(master.windrose.showed)
            if master.fir.sacta_mode[master.sector.split(",")[0]] == 'OSF':
                if self.master.disp_number == 1:
                    # OSF window visibility: check if root window exists and is visible
                    try:
                        is_visible = master.fichas_tabular.root.winfo_ismapped()
                    except:
                        is_visible = False
                    self.var_ver_fichas_tab.set(is_visible)
                    # self.var_ver_predesp_tab.set(master.predesp_tabular.showed)
                else:
                    self.var_ver_fichas_tab.set(False)
                    self.var_ver_predesp_tab.set(False)
            else:
                if hasattr(master, 'atc_bahia'):
                    self.var_ver_bahia_tab.set(master.atc_bahia.showed)

            self.but_coordinated = tix.Checkbutton(ventana_tabs, text='Coordinados', variable=self.var_ver_coor_tab,
                                                   command=master.coor_tabular.conmuta)
            self.but_coordinated.grid(column=0, row=1, sticky=tix.W)
            self.but_preactive = tix.Checkbutton(ventana_tabs, text='Preactivos', variable=self.var_ver_preact_tab,
                                                 command=master.preact_tabular.conmuta)
            self.but_preactive.grid(column=0, row=2, sticky=tix.W)
            self.but_active = tix.Checkbutton(ventana_tabs, text='Activos', variable=self.var_ver_act_tab,
                                              command=master.act_tabular.conmuta)
            self.but_active.grid(column=0, row=3, sticky=tix.W)
            self.but_windrose = tix.Checkbutton(ventana_tabs, text='Anemometro', variable=self.var_ver_windrose,
                                                command=master.windrose.conmuta)
            self.but_windrose.grid(column=0, row=4, sticky=tix.W)
            if master.fir.sacta_mode[master.sector.split(",")[0]] == 'OSF':
                if self.master.disp_number == 1:
                    # self.but_predesp = tix.Checkbutton(ventana_tabs, text='Previstos',
                    #                                    variable=self.var_ver_predesp_tab,
                    #                                    command=master.predesp_tabular.conmuta)
                    # self.but_predesp.grid(column=0, row=4, sticky=tix.W)
                    self.but_printlist = tix.Checkbutton(ventana_tabs, text='OSF', variable=self.var_ver_fichas_tab,
                                                         command=master.fichas_tabular.conmuta)
                    self.but_printlist.grid(column=0, row=5, sticky=tix.W)
            elif hasattr(master, 'atc_bahia'):  ###Bahia de fichas
                self.but_printlist = tix.Checkbutton(ventana_tabs, text='Bahia', variable=self.var_ver_bahia_tab,
                                                     command=master.atc_bahia.conmuta)
                self.but_printlist.grid(column=0, row=5, sticky=tix.W)


            i = w.create_window(ventana.winfo_x() + self.but_ver_tabs.winfo_x(), alto - ventana.winfo_height(),
                                window=ventana_tabs, anchor='sw')
            self._tabs_window_id = i
            self.opened_windows.append(i)
            self._tabs_window_open = True

        self.but_ver_tabs = tix.Button(ventana, text='MENU\nTABS', height=BUTTON_HEIGHT, font=SMALL_FONT)
        self.wrap_button_with_toggle(self.but_ver_tabs)
        self.but_ver_tabs.grid(row=2, column=current_col, columnspan=3, padx=0, pady=0, sticky='nsew')
        current_col += 3
        # self.but_ver_tabs.pack(side=LEFT,expand=1,fill=X)
        self.but_ver_tabs['command'] = tabs_buttons

        self.but_contador = self.create_toggle_button(ventana, {'text': 'CONTADOR', 'height': BUTTON_HEIGHT}, None)
        self.but_contador.grid(row=2, column=current_col, columnspan=3, padx=0, pady=0, sticky='nsew')
        current_col += 3

        self.but_cam_tv = self.create_toggle_button(ventana, {'text': 'CAM TV', 'height': BUTTON_HEIGHT}, None)
        self.but_cam_tv.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_eliminar_termsusp = self.create_toggle_button(ventana, {'text': 'ELIMINAR\nTERM/SUSP', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_eliminar_termsusp.grid(row=2, column=current_col, columnspan=3, padx=0, pady=0, sticky='nsew')
        current_col += 3

        #Boton para ASUMIR en SACTA sin funcionalidad (mirar de añadirlo lo antes posible)
        self.but_asumir = self.create_toggle_button(ventana, {'text': 'ASUMIR', 'height': BUTTON_HEIGHT}, None)
        self.but_asumir.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_quitar_lads = self.create_toggle_button(ventana, {'text': 'BORRAR\nLADs', 'fg': 'red', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, self.master.delete_lads)
        # self.but_quitar_lads.pack(side=LEFT,expand=1,fill=X)
        self.but_quitar_lads.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_geo = self.create_toggle_button(ventana, {'text': 'GEO', 'height': BUTTON_HEIGHT}, None)
        self.but_geo.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_ojeo = self.create_toggle_button(ventana, {'text': 'OJEOS', 'height': BUTTON_HEIGHT}, None)
        self.but_ojeo.grid(row=2, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        """===== FILA 3 ====="""
        current_col = 0

        self.but_corr = self.create_toggle_button(ventana, {'text': 'CORR', 'height': BUTTON_HEIGHT}, None)
        self.but_corr.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_no_corr = self.create_toggle_button(ventana, {'text': 'NO CORR', 'height': BUTTON_HEIGHT}, None)
        self.but_no_corr.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_no_corr_gnd = self.create_toggle_button(ventana, {'text': 'NO CORR GND', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_no_corr_gnd.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        timpo_en_horas = tix.Control(ventana, label="H", min=1, max=24, integer=1, height=BUTTON_HEIGHT, command=None)
        timpo_en_horas.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        def cambia_vect_vel(e=None):
            master.change_speed_vector(self.speed_vector_var.get() / 60.)

        cnt_vect_vel = tix.Control(ventana, label="V", min=0, max=5, integer=1, height=BUTTON_HEIGHT, command=cambia_vect_vel,
                                   variable=self.speed_vector_var)
        cnt_vect_vel.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_t = self.create_toggle_button(ventana, {'text': 'T', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_t.grid(row=1, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # Ventana desplegable para tamano de etiquetas
        def tamano_etiq_window():
            """Abre ventana desplegable para seleccionar tamano de etiquetas"""
            if self._tamano_window_open:
                self.close_windows()
                return
            
            # Si esta cerrada, abrir
            self.close_windows()
            ventana_tamano = tix.Frame(w, bg='gray')
            irow = 0
            
            # Rangos de tamaño disponibles (según LABEL_MIN_FONT_SIZE y LABEL_MAX_FONT_SIZE)
            tamanos = range(LABEL_MIN_FONT_SIZE, LABEL_MAX_FONT_SIZE + 1)
            
            for size in tamanos:
                def select_size(tamano=size):
                    """Seleccionar un tamano especifico"""
                    master.label_font_size = tamano
                    for vt in master.tracks:
                        vt.l_font_size = tamano
                    master.label_font.configure(size=master.label_font_size)
                    self.close_windows()
                
                btn_size = tix.Button(ventana_tamano, text=str(size), command=select_size)
                btn_size.grid(column=0, row=irow, sticky=tix.E + tix.W)
                irow += 1
            
            i = w.create_window(ventana.winfo_x() + self.but_tamano_etiq.winfo_x(), alto - ventana.winfo_height(),
                                window=ventana_tamano, anchor='sw')
            self._tamano_window_id = i
            self.opened_windows.append(i)
            self._tamano_window_open = True
        
        self.but_tamano_etiq = tix.Button(ventana, text='P', height=BUTTON_HEIGHT, width=BUTTON_WIDTH_HALF)
        self.wrap_button_with_toggle(self.but_tamano_etiq)
        self.but_tamano_etiq.grid(row=1, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        self.but_tamano_etiq['command'] = tamano_etiq_window
        current_col += 1


        self.but_meteo = self.create_toggle_button(ventana, {'text': 'METEO', 'height': BUTTON_HEIGHT}, None)
        self.but_meteo.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_prim = self.create_toggle_button(ventana, {'text': 'PRIM', 'height': BUTTON_HEIGHT}, None)
        self.but_prim.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_plt_app = self.create_toggle_button(ventana, {'text': 'PLT\nAPP', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_plt_app.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_cancelar_ficticio = self.create_toggle_button(ventana, {'text': 'CANCELAR\nFICTICIO', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_cancelar_ficticio.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_fictio = self.create_toggle_button(ventana, {'text': 'FICTICIO', 'height': BUTTON_HEIGHT}, None)
        self.but_fictio.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_vgpv = self.create_toggle_button(ventana, {'text': 'VGPV', 'height': BUTTON_HEIGHT}, None)
        self.but_vgpv.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_vfve = self.create_toggle_button(ventana, {'text': 'VFVE', 'height': BUTTON_HEIGHT}, None)
        self.but_vfve.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        relleno = tix.Frame(ventana, height=BUTTON_HEIGHT_PX, bg='black')
        relleno.grid(row=1, column=current_col, columnspan=6,
                     padx=0, pady=0, sticky='nsew')
        current_col += 6

        self.but_pv_operacion = self.create_toggle_button(ventana, {'text': 'PV\nOPERACION', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_pv_operacion.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_crear_pva = self.create_toggle_button(ventana, {'text': 'CREAR\nPVA', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_crear_pva.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        # Opcion de 'Pedir transferencia'
        def pedir_trf():
            sel = self.master.selected_track
            if sel == None:
                RaDialog(w, label="Pedir TRF", text='No hay ningun vuelo seleccionado')
            else:
                print("Has pedido transferencia del ", sel.cs)
                f = [f for f in self.master.flights if f.callsign == sel.cs][0]
                self.master.sendMessage({"message": "pedir_trf", "cs": f.callsign})
                # self.master.sendMessage({"message": "transfer", "cs": f.callsign})
            
            # Desactivar el boton inmediatamente despues de ejecutar
            if hasattr(self.but_pedir_trf, 'toggle_state'):
                self.but_pedir_trf.toggle_state['active'] = False
                self.but_pedir_trf.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                if self.but_pedir_trf in self.active_buttons:
                    self.active_buttons.remove(self.but_pedir_trf)

        self.but_pedir_trf = self.create_toggle_button(ventana, {'text': 'Pedir TRF', 'height': BUTTON_HEIGHT}, pedir_trf)
        self.but_pedir_trf.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_quitar_fpr = self.create_toggle_button(ventana, {'text': 'BORRAR\nRUTAS', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, self.master.delete_routes)
        self.but_quitar_fpr.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_dat_ruta = self.create_toggle_button(ventana, {'text': 'DAT\nRUTA', 'height': BUTTON_HEIGHT, 'font': SMALL_FONT}, None)
        self.but_dat_ruta.grid(row=1, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        """===== FILA 4 (ARRIBA) ====="""
        current_col = 0


        self.obs = self.create_toggle_button(ventana, {'text': 'OBS', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.obs.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        def create_label_toggle(line_var):
            """Crea funcion de toggle para lineas de etiqueta"""
            def toggle():
                line_var.set(0 if line_var.get() else 1)
                self.master._cached_values_ready = False
                self.master.reformat_labels()
            return toggle
        
        self.but_l1_onoff = self.create_toggle_button(
            ventana,
            {'text': 'L1', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF},
            create_label_toggle(self.master.l1_onoff_var)
        )
        self.but_l1_onoff.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        # Sincronizar estado visual con variable inicial
        if self.master.l1_onoff_var.get():
            self.but_l1_onoff.toggle_state['active'] = True
            self.but_l1_onoff.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        current_col += 1

        self.but_l2_onoff = self.create_toggle_button(
            ventana, 
            {'text': 'L2', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, 
            create_label_toggle(self.master.l2_onoff_var)
        )
        self.but_l2_onoff.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        # Sincronizar estado visual con variable inicial
        if self.master.l2_onoff_var.get():
            self.but_l2_onoff.toggle_state['active'] = True
            self.but_l2_onoff.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        current_col += 1

        self.but_l3_onoff = self.create_toggle_button(
            ventana, 
            {'text': 'L3', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, 
            create_label_toggle(self.master.l3_onoff_var)
        )
        self.but_l3_onoff.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        # Sincronizar estado visual con variable inicial
        if self.master.l3_onoff_var.get():
            self.but_l3_onoff.toggle_state['active'] = True
            self.but_l3_onoff.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        current_col += 1

        self.but_cfl = self.create_toggle_button(ventana, {'text': 'CFL', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_cfl.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        self.but_l4_onoff = self.create_toggle_button(
            ventana, 
            {'text': 'L4', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, 
            create_label_toggle(self.master.l4_onoff_var)
        )
        self.but_l4_onoff.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        # Sincronizar estado visual con variable inicial
        if self.master.l4_onoff_var.get():
            self.but_l4_onoff.toggle_state['active'] = True
            self.but_l4_onoff.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        current_col += 1

        self.but_vrut = self.create_toggle_button(ventana, {'text': 'VRUT', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_vrut.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # SEP: separacion automatica de etiquetas (antes el boton no hacia nada; de GAMMA)
        def toggle_sep():
            self.master.toggle_auto_separation()
            self.auto_sep.set(self.master.auto_separation)
            self.but_sep.toggle_state['active'] = bool(self.master.auto_separation)
            if self.master.auto_separation:
                self.but_sep.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
            else:
                self.but_sep.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
        self.but_sep = self.create_toggle_button(ventana, {'text': 'SEP', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, toggle_sep)
        self.but_sep.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        if self.master.auto_separation:
            self.but_sep.toggle_state['active'] = True
            self.but_sep.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        current_col += 1

        self.but_lad = self.create_toggle_button(ventana, {'text': 'LAD', 'height': BUTTON_HEIGHT, 'width': BUTTON_WIDTH_HALF}, None)
        self.but_lad.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        def toggle_wake_oaci():
            """Toggle para mostrar/ocultar estela turbulenta OACI"""
            self.master.wake_oaci_var.set(0 if self.master.wake_oaci_var.get() else 1)
            self.master._cached_values_ready = False
            self.master.reformat_labels()
        
        self.but_e_oaci = self.create_toggle_button(ventana, {'text': 'E.OACI', 'height': BUTTON_HEIGHT}, toggle_wake_oaci)
        self.but_e_oaci.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        # Inicializar como activo (blanco) porque wake_oaci_var inicia en True
        self.but_e_oaci.toggle_state['active'] = True
        self.but_e_oaci.configure(bg=self.ACTIVE_BG, fg=self.ACTIVE_FG)
        if self.but_e_oaci not in self.active_buttons:
            self.active_buttons.append(self.but_e_oaci)
        current_col += 2

        def toggle_wake_recat():
            """Toggle para mostrar/ocultar signo RECAT (+/-)"""
            self.master.wake_recat_var.set(0 if self.master.wake_recat_var.get() else 1)
            self.master._cached_values_ready = False
            self.master.reformat_labels()
        
        self.but_e_recat = self.create_toggle_button(ventana, {'text': 'E.RECAT', 'height': BUTTON_HEIGHT}, toggle_wake_recat)
        self.but_e_recat.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        # Inicializar como inactivo (gris) porque wake_recat_var inicia en False
        current_col += 2

        
        # Opcion "SMR" (solo activa para LEST)
        def smr():
            if not self.master.smrOn:
                self.master.orient = 'FIELD'
                self.master.scale = 700
                self.master.center_x = ancho / 2
                self.master.center_y = (alto - 40.) / 2
                self.master.select_FALT_varmin.set(0)
                self.master.select_FALT_varmax.set(25)
                self.master._falt_enabled = True
                self.master.reposition()
                for vt in self.master.tracks:
                    if vt.adep == self.master.fir.param('smr_ad', ''):
                        vt.plot_only = True
                        # vt.visible = True
                        # vt.redraw_p()
                    else:
                        pass
                        vt.plot_only = False

                self.master.smrOn = True
                self.but_smr.configure(text='SMR ON', fg="red")
            else:
                for vt in self.master.tracks:
                    vt.plot_only = False
                self.but_smr.configure(text='SMR OFF', fg="black")
                self.master.smrOn = False

        self.but_smr = self.create_toggle_button(ventana, {'text': 'SMR OFF', 'fg': 'black', 'height': BUTTON_HEIGHT}, smr)
        self.but_smr.grid(row=0, column=current_col, columnspan=1, padx=0, pady=0, sticky='nsew')
        current_col += 1

        # Boton "SMR" solo activo si el escenario define 'smr_ad' (por defecto LEST)
        if master.fir.param('smr_ad', ''):
            self.but_smr['state'] = tix.NORMAL
        else:
            self.but_smr['state'] = tix.DISABLED

        # Separador horizontal negro
        separador = tix.Frame(ventana, height=BUTTON_HEIGHT_PX, bg='black')
        separador.grid(row=0, column=current_col, columnspan=20, 
                       padx=0, pady=0, sticky='nsew')
        current_col += 20

        # Opcion de 'Revocar'
        def revocar():
            cs = None
            sel = self.master.selected_track
            if sel is not None:
                cs = sel.cs
            else:
                # Fallback: obtener callsign de la ficha seleccionada en OSF
                if hasattr(self.master, 'fichas_tabular'):
                    osf = self.master.fichas_tabular
                    if hasattr(osf, 'selected_line') and osf.selected_line:
                        try:
                            zi, fi = osf.selected_line
                            ficha = osf.zonas[zi]["fichas"][fi]
                            cs = ficha.get("values", {}).get("callsign", "")
                        except Exception:
                            pass
            if not cs:
                RaDialog(w, label='Revocar', text='No hay ningun vuelo seleccionado')
                # Desactivar boton incluso si no hay vuelo seleccionado
                if hasattr(self.but_revocar, 'toggle_state'):
                    self.but_revocar.toggle_state['active'] = False
                    self.but_revocar.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                    if self.but_revocar in self.active_buttons:
                        self.active_buttons.remove(self.but_revocar)
                return
            # Iniciar la funcion revocar generada en RaElements (solo existe en posiciones OSF)
            if self.master.fir.sacta_mode.get(self.master.sector.split(',')[0]) == 'OSF' \
                    and hasattr(self.master, 'fichas_tabular'):
                self.master.fichas_tabular.revocar(cs)
            else:
                RaDialog(w, label='Revocar', text='REVOCAR solo esta disponible en posiciones OSF')
            
            # Desactivar el boton inmediatamente despues de ejecutar
            if hasattr(self.but_revocar, 'toggle_state'):
                self.but_revocar.toggle_state['active'] = False
                self.but_revocar.configure(bg=self.NORMAL_BG, fg=self.NORMAL_FG)
                if self.but_revocar in self.active_buttons:
                    self.active_buttons.remove(self.but_revocar)

        self.but_revocar = self.create_toggle_button(ventana, {'text': 'REVOCAR', 'height': BUTTON_HEIGHT}, revocar)
        self.but_revocar.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        def pistas_window():
            """Abre ventana de configuracion de USO DE PISTAS (estilo canvas window)"""

            if self._pistas_window_open:
                self.close_windows()
                return

            self.close_windows()

            ventana_pistas = tix.Frame(w, bg='#666666', relief='raised', bd=2)

            barra_titulo = tix.Frame(ventana_pistas, bg='#CC6699', height=12)
            barra_titulo.grid(row=0, column=0, columnspan=6, sticky='ew')

            titulo = tix.Label(ventana_pistas, text='USO DE PISTAS', 
                              bg='#666666', fg='white',
                              font=('Arial', 12, 'bold'))
            titulo.grid(row=1, column=0, columnspan=6, pady=8, sticky='ew')

            headers = [
                ('PISTAS', 0),
                ('NO EN USO', 1),
                ('SENTIDO DE USO', 2),
                ('', 3),  # Columna extra para segundo combobox
                ('CERRADA', 4)
            ]

            for header_text, col in headers:
                if header_text:
                    lbl = tix.Label(ventana_pistas, text=header_text, 
                                   bg='#666666', fg='white',
                                   font=('Arial', 9, 'bold'))
                    lbl.grid(row=2, column=col, padx=5, pady=5, sticky='w')

            # Pistas de la ventana: parametro de escenario 'uso_pistas' (por defecto las de LEBL)
            pistas_data = []
            for par in self.master.fir.param('uso_pistas', ['13/31', '02/20', '06L/24R', '06R/24L']):
                sentidos = par.split('/')
                if len(sentidos) == 2:
                    pistas_data.append((par, sentidos[0], sentidos[1]))

            check_no_uso_vars = []
            combo_sentido1_vars = []
            combo_sentido2_vars = []
            check_cerrada_vars = []

            combo_sentido1_widgets = []
            combo_sentido2_widgets = []
            check_no_uso_widgets = []
            check_cerrada_widgets = []

            for idx, (pista, sentido1, sentido2) in enumerate(pistas_data):
                fila = 3 + idx

                # Columna 0: Nombre de pista
                lbl_pista = tix.Label(ventana_pistas, text=pista, 
                                     bg='#666666', fg='white',
                                     font=('Arial', 9))
                lbl_pista.grid(row=fila, column=0, padx=8, pady=3, sticky='w')

                # Columna 1: Checkbox NO EN USO
                var_no_uso = tix.IntVar()
                check_no_uso = tix.Checkbutton(ventana_pistas, 
                                               variable=var_no_uso,
                                               bg='#666666', 
                                               selectcolor='yellow',
                                               activebackground='#666666',
                                               highlightthickness=0)
                check_no_uso.grid(row=fila, column=1, padx=15, pady=3)
                check_no_uso_vars.append(var_no_uso)
                check_no_uso_widgets.append(check_no_uso)

                # Columna 2: Sentido 1 (Label + ComboBox)
                frame_s1 = tix.Frame(ventana_pistas, bg='#666666')
                frame_s1.grid(row=fila, column=2, padx=3, pady=3, sticky='w')

                lbl_s1 = tix.Label(frame_s1, text=sentido1, 
                                  bg='#666666', fg='white',
                                  font=('Arial', 8))
                lbl_s1.pack(side='top', anchor='center')

                var_s1 = tix.StringVar()
                var_s1.set('')  # FIX 1: Vacio por defecto
                combo_s1 = tix.ComboBox(frame_s1, 
                                       variable=var_s1,
                                       dropdown=True,
                                       editable=False,
                                       command=lambda v=var_s1: None)
                combo_s1.subwidget('entry').configure(bg='#666666', fg='white')
                combo_s1.subwidget('listbox').configure(bg='#666666', fg='white', selectbackground='#888888')
                combo_s1.subwidget('entry').configure(width=8)
                combo_s1.insert(0, '---')  # Opcion vacia para deseleccionar
                combo_s1.insert(1, 'DEP')
                combo_s1.insert(2, 'ARR')
                combo_s1.insert(3, 'DEP/ARR')
                combo_s1.pack(side='top')
                combo_sentido1_vars.append(var_s1)
                combo_sentido1_widgets.append(combo_s1)

                # Columna 3: Sentido 2 (Label + ComboBox)
                frame_s2 = tix.Frame(ventana_pistas, bg='#666666')
                frame_s2.grid(row=fila, column=3, padx=3, pady=3, sticky='w')

                lbl_s2 = tix.Label(frame_s2, text=sentido2,
                                  bg='#666666', fg='white',
                                  font=('Arial', 8))
                lbl_s2.pack(side='top', anchor='center')

                var_s2 = tix.StringVar()
                var_s2.set('')  #  FIX 1: Vacio por defecto
                combo_s2 = tix.ComboBox(frame_s2,
                                       variable=var_s2,
                                       dropdown=True,
                                       editable=False,
                                       command=lambda v=var_s2: None)
                combo_s2.subwidget('entry').configure(bg='#666666', fg='white', width=8)
                combo_s2.subwidget('listbox').configure(bg='#666666', fg='white', selectbackground='#888888', width=8)
                combo_s2.insert(0, '---')  # Opcion vacia para deseleccionar
                combo_s2.insert(1, 'DEP')
                combo_s2.insert(2, 'ARR')
                combo_s2.insert(3, 'DEP/ARR')
                combo_s2.pack(side='top')
                combo_sentido2_vars.append(var_s2)
                combo_sentido2_widgets.append(combo_s2)

                # Columna 4: Checkbox CERRADA
                var_cerrada = tix.IntVar()
                check_cerrada = tix.Checkbutton(ventana_pistas,
                                                variable=var_cerrada,
                                                bg='#666666',
                                                selectcolor='yellow',
                                                activebackground='#666666',
                                                highlightthickness=0)
                check_cerrada.grid(row=fila, column=4, padx=15, pady=3)
                check_cerrada_vars.append(var_cerrada)
                check_cerrada_widgets.append(check_cerrada)

                widgets_fila = {
                    'combo_s1': combo_s1,
                    'combo_s2': combo_s2,
                    'var_s1': var_s1,
                    'var_s2': var_s2,
                    'check_no_uso': check_no_uso,
                    'check_cerrada': check_cerrada,
                    'var_no_uso': var_no_uso,
                    'var_cerrada': var_cerrada
                }

                def make_no_uso_callback(widgets):
                    def callback():
                        if widgets['var_no_uso'].get() == 1:
                            widgets['var_s1'].set('')
                            widgets['var_s2'].set('')
                            widgets['combo_s1'].configure(state='disabled')
                            widgets['combo_s2'].configure(state='disabled')
                            widgets['check_cerrada'].configure(state='disabled')
                        else:
                            widgets['combo_s1'].configure(state='normal')
                            widgets['combo_s2'].configure(state='normal')
                            widgets['check_cerrada'].configure(state='normal')
                    return callback
                
                def make_cerrada_callback(widgets):
                    def callback():
                        if widgets['var_cerrada'].get() == 1:
                            widgets['var_s1'].set('')
                            widgets['var_s2'].set('')
                            widgets['combo_s1'].configure(state='disabled')
                            widgets['combo_s2'].configure(state='disabled')
                            widgets['check_no_uso'].configure(state='disabled')
                        else:
                            widgets['combo_s1'].configure(state='normal')
                            widgets['combo_s2'].configure(state='normal')
                            widgets['check_no_uso'].configure(state='normal')
                    return callback
                
                check_no_uso.configure(command=make_no_uso_callback(widgets_fila))
                check_cerrada.configure(command=make_cerrada_callback(widgets_fila))

            if hasattr(self.master, 'current_runway_config') and self.master.current_runway_config:
                for idx, config in enumerate(self.master.current_runway_config):
                    if idx < len(check_no_uso_vars):
                        # Cargar valores
                        check_no_uso_vars[idx].set(config.get('no_en_uso', 0))
                        check_cerrada_vars[idx].set(config.get('cerrada', 0))
                        combo_sentido1_vars[idx].set(config.get('sentido1', {}).get('operacion', ''))
                        combo_sentido2_vars[idx].set(config.get('sentido2', {}).get('operacion', ''))
     
                        if config.get('no_en_uso', 0) == 1:
                            # NO EN USO esta marcado: deshabilitar combos y CERRADA
                            combo_sentido1_widgets[idx].configure(state='disabled')
                            combo_sentido2_widgets[idx].configure(state='disabled')
                            check_cerrada_widgets[idx].configure(state='disabled')

                        elif config.get('cerrada', 0) == 1:
                            # CERRADA esta marcado: deshabilitar combos y NO EN USO
                            combo_sentido1_widgets[idx].configure(state='disabled')
                            combo_sentido2_widgets[idx].configure(state='disabled')
                            check_no_uso_widgets[idx].configure(state='disabled')

            # === FILAS 7-8: Espacio ===

            # === FIX 2: Botones horizontales en FILA 9 ===
            def ejecutar():
                """Recolectar configuracion y enviar a GTA"""

                # Construir payload con estado de cada pista
                pistas_config = []

                for idx, (pista, sentido1, sentido2) in enumerate(pistas_data):
                    # Obtener operaciones y convertir "---" a string vacio
                    op_s1 = combo_sentido1_vars[idx].get()
                    op_s2 = combo_sentido2_vars[idx].get()
                    if op_s1 == '---':
                        op_s1 = ''
                    if op_s2 == '---':
                        op_s2 = ''

                    no_en_uso_val = check_no_uso_vars[idx].get()
                    cerrada_val = check_cerrada_vars[idx].get()
                    # Si no se marca DEP/ARR/Mixta en ningun sentido ni NO EN USO ni CERRADA,
                    # se normaliza a NO EN USO: asi la pista no recibe alertas de cruce.
                    if (not op_s1 and not op_s2
                            and not no_en_uso_val and not cerrada_val):
                        no_en_uso_val = 1

                    config = {
                        'pista_pair': pista,  # "13/31", "02/26", etc.
                        'no_en_uso': no_en_uso_val,  # 0 o 1
                        'sentido1': {
                            'designador': sentido1,  # "13", "02", "06L", "06R"
                            'operacion': op_s1  # "", "DEP", "ARR", "DEP/ARR"
                        },
                        'sentido2': {
                            'designador': sentido2,  # "31", "26", "24R", "24L"
                            'operacion': op_s2  # "", "DEP", "ARR", "DEP/ARR"
                        },
                        'cerrada': cerrada_val  # 0 o 1
                    }
                    pistas_config.append(config)

                # Enviar mensaje al GTA
                m = {
                    'message': 'runway_config_update',
                    'ad': master.fir.aps[0],  # Aerodromo (LEBL, LEMD, etc.)
                    'pistas_config': pistas_config
                }

                if hasattr(self.master, 'sendMessage'):
                    self.master.sendMessage(m)
                else:
                    print("ERROR: self.master does not have sendMessage method")

            def analizar():
                print("ANALIZAR - Verificar configuracion")

            def cancelar():
                """Resetear todos los valores y cerrar la ventana"""
                # Resetear todos los combos a vacio
                for var in combo_sentido1_vars:
                    var.set('')
                for var in combo_sentido2_vars:
                    var.set('')
                
                # Desmarcar todos los checkboxes
                for var in check_no_uso_vars:
                    var.set(0)
                for var in check_cerrada_vars:
                    var.set(0)
                
                # Habilitar todos los widgets
                for widget in combo_sentido1_widgets:
                    widget.configure(state='normal')
                for widget in combo_sentido2_widgets:
                    widget.configure(state='normal')
                for widget in check_no_uso_widgets:
                    widget.configure(state='normal')
                for widget in check_cerrada_widgets:
                    widget.configure(state='normal')

            # Frame contenedor para botones horizontales
            frame_botones = tix.Frame(ventana_pistas, bg='#666666')
            frame_botones.grid(row=9, column=0, columnspan=6, pady=15, sticky='ew')

            # Centrar botones horizontalmente
            frame_botones.grid_columnconfigure(0, weight=1)
            frame_botones.grid_columnconfigure(1, weight=0)
            frame_botones.grid_columnconfigure(2, weight=0)
            frame_botones.grid_columnconfigure(3, weight=0)
            frame_botones.grid_columnconfigure(4, weight=1)

            btn_ejecutar = tix.Button(frame_botones, text='EJECUTAR',
                                     command=ejecutar,
                                     bg='white', fg='black',
                                     width=12, height=1)
            btn_ejecutar.grid(row=0, column=1, padx=5)

            btn_analizar = tix.Button(frame_botones, text='ANALIZAR',
                                      command=analizar,
                                      bg='white', fg='black',
                                      width=12, height=1)
            btn_analizar.grid(row=0, column=2, padx=5)

            btn_cancelar = tix.Button(frame_botones, text='CANCELAR',
                                     command=cancelar,
                                     bg='white', fg='black',
                                     width=12, height=1)
            btn_cancelar.grid(row=0, column=3, padx=5)

            # Configurar expansion de columnas
            for col in range(6):
                ventana_pistas.grid_columnconfigure(col, weight=1)

            # Insertar ventana en canvas (centrada o en posicion especifica)
            x_pos = ventana.winfo_x() + self.but_cam_tv.winfo_x()
            y_pos = alto - ventana.winfo_height()

            i = w.create_window(x_pos, y_pos, window=ventana_pistas, anchor='sw')
            self._pistas_window_id = i
            self.opened_windows.append(i)
            self._pistas_window_open = True

        self.but_uso_pistas = self.create_toggle_button(ventana, {'text': 'USO PISTAS', 'height': BUTTON_HEIGHT}, pistas_window)
        self.but_uso_pistas.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        
        # Boton "USO PISTAS" solo activo para roles LCL/TWR
        has_lcl_role = False
        for sector in master.sector.split(','):
            if 'LCL' in sector or 'TWR' in sector:
                has_lcl_role = True
                break
        
        if has_lcl_role:
            self.but_uso_pistas['state'] = tix.NORMAL
        else:
            self.but_uso_pistas['state'] = tix.DISABLED
        
        current_col += 2

        self.but_aerod = self.create_toggle_button(ventana, {'text': 'AEROD', 'height': BUTTON_HEIGHT}, None)
        self.but_aerod.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        self.but_usuario = self.create_toggle_button(ventana, {'text': 'USUARIO', 'height': BUTTON_HEIGHT}, None)
        self.but_usuario.grid(row=0, column=current_col, columnspan=2, padx=0, pady=0, sticky='nsew')
        current_col += 2

        # Insertar el toolbar en el canvas (en la parte inferior)
        self.toolbar_id = w.create_window(0, alto, width=ancho, window=ventana, anchor='sw')
        ventana.update_idletasks()

        # Código viejo comentado
        # cnt_vect_vel.pack(side=LEFT,expand=1,fill=X)
        #        cnt_vel_reloj = tix.Control(ventana, label="Reloj X:", min=0.5, max=99.0, step=0.1, state=DISABLED)
        #        cnt_vel_reloj.pack(side=LEFT,expand=1,fill=X)
        """
        but_l2_onoff = tix.Checkbutton(ventana, text='L2', command=self.master.reformat_labels,
                                       variable=self.master.l2_onoff_var)
        grid_column += 1
        but_l2_onoff.grid(row=0, column=grid_column)

        but_l3_onoff = tix.Checkbutton(ventana, text='L3', command=self.master.reformat_labels,
                                       variable=self.master.l3_onoff_var)
        grid_column += 1
        but_l3_onoff.grid(row=0, column=grid_column)

        but_l4_onoff = tix.Checkbutton(ventana, text='L4', command=self.master.reformat_labels,
                                       variable=self.master.l4_onoff_var)
        grid_column += 1
        but_l4_onoff.grid(row=0, column=grid_column)
        """

        """ ZOOMs antiguos
        self.but_zoom_mas = tix.Button(ventana, bitmap='@' + IMGDIR + 'zoom.xbm')
        grid_column += 1
        self.but_zoom_mas.grid(row=0, column=grid_column)
        # self.but_zoom_mas.pack(side=LEFT,expand=1,fill=X)
        self.but_zoom_mas.bind("<Button-1>", b_zoom_mas)
        self.but_zoom_mas.bind("<Button-2>", b_zoom_mas)
        self.but_zoom_mas.bind("<Button-3>", b_zoom_mas)

        self.but_zoom_menos = tix.Button(ventana, bitmap='@' + IMGDIR + 'unzoom.xbm')
        grid_column += 1
        self.but_zoom_menos.grid(row=0, column=grid_column)
        # self.but_zoom_menos.pack(side=LEFT,expand=1,fill=X)
        self.but_zoom_menos.bind("<Button-1>", b_zoom_menos)
        self.but_zoom_menos.bind("<Button-2>", b_zoom_menos)
        self.but_zoom_menos.bind("<Button-3>", b_zoom_menos)
        """

        """
        self.but_tamano_etiq = tix.Button(ventana, bitmap='@' + IMGDIR + 'labelsize.xbm')
        grid_column += 1
        self.but_tamano_etiq.grid(row=0, column=grid_column)
        # self.but_tamano_etiq.pack(side=LEFT,expand=1,fill=X)
        self.but_tamano_etiq.bind("<Button-1>", b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-2>", b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-3>", b_tamano_fichas)
        """

        #        self.but_term = tix.Button(ventana,text='Kill',state=DISABLED)
        #        self.but_term.pack(side=LEFT,expand=1,fill=X)
        #        self.but_ruta = tix.Button(ventana,text='Ruta',state=DISABLED)
        #        self.but_ruta.pack(side=LEFT,expand=1,fill=X)
        #self.but_datos = tix.Button(ventana, text='Datos', command=ver_detalles)
        #grid_column += 1
        #self.but_datos.grid(row=0, column=grid_column)
        # self.but_datos.pack(side=LEFT,expand=1,fill=X)

        #self.but_quitar_lads = tix.Button(ventana, text='LADs', fg='red', command=self.master.delete_lads)
        # self.but_quitar_lads.pack(side=LEFT,expand=1,fill=X)
        #grid_column += 1
        #self.but_quitar_lads.grid(row=0, column=grid_column)
        
        # self.but_quitar_fpr.pack(side=LEFT,expand=1,fill=X)
        #        self.but_ver_proc = tix.Button(ventana, text = 'PROCs',state=DISABLED)
        #        self.but_ver_proc.pack(side=LEFT,expand=1,fill=X)

        #self.but_auto_separation = tix.Checkbutton(ventana, text='SEP', variable=self.auto_sep,
        #                                           command=lambda: master.toggle_auto_separation())
        #grid_column += 1
        #self.but_auto_separation.grid(row=0, column=grid_column)
        # self.but_auto_separation.pack(side=LEFT,expand=1,fill=X)

        

        #self.but_ver_maps = tix.Button(ventana, text='MAPAS')
        #grid_column += 1
        #self.but_ver_maps.grid(row=0, column=grid_column)

        # self.but_ver_maps.pack(side=LEFT,expand=1,fill=X)


        # toggle_filterFGND ya est? definida arriba (línea ~1493)
        #but_filterFGND = tix.Button(ventana, text='FGND', command=toggle_filterFGND, bg='gray90')
        #grid_column += 1
        #but_filterFGND.grid(row=0, column=grid_column)

        # if master.filterFGND:
        #     but_filterFGND.configure(bg='gray50')
        #     master.refresco = 1.
        # else:
        #     but_filterFGND.configure(bg='gray90')
        #     master.refresco = 5.