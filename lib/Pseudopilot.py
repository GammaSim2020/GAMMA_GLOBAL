#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: Pseudopilot.py 2382 2007-06-01 17:19:14Z rodrigo $
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
"""Classes used by the pseudopilot interface of GAMMA"""

import datetime
from RaDisplay import *  # This also imports all RaElements classes
import Aircraft
import Route
from Tkinter import *


SNDDIR = './snd/'
COUNT = 0


class PpDisplay(RaDisplay):
    """Radar display with a pseudopilot interface"""
    
    def __init__(self, conf, title, icon_path, fir, tlpv, sector, flights, disp_number, mode='pp'):
        """Instantiate a Pseudopilot Radar Display
        
        title - window title
        icon_path - path to the windows task bar icon
        fir -- fir object
        sector -- name of the sector to work with
        """
        self.conf = conf
        self.toolbar_height = 60  # Pseudopilot display toolbar height
        self._flights_tracks = {}
        self._tracks_flights = {}
        self.mode = mode
        RaDisplay.__init__(self, self.conf, title, icon_path, fir, tlpv, sector, self.toolbar_height, disp_number)

        self.flights = flights
        for f in self.flights:
            vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
            # Setting mode implicitly configures label
            vt.mode = 'pp'
            if f.fr == 'VEH':
                vt.label_format = 'pp-veh'
            vt.l_font_size = self.label_font_size
            self.tracks.append(vt)
            self._flights_tracks[f] = vt
            self._tracks_flights[vt] = f

        self.killed_flights = []
        self.t = datetime.datetime.today()
        self.synchronised = False
        self.last_update = self.t - datetime.timedelta(seconds=5)
        
        self.routes = []  # List of tracks whose routes are displayed
        self.waypoints = []  # List of tracks whose waypoints are displayed 
        
        self.speed_vector_var = tk.IntVar()
        self.speed_vector_var.set(0)

        self.clock_speed_var = tk.DoubleVar()
        self.clock_speed_var.set(1.0)

        self.radar_off_var = tk.BooleanVar()
        self.radar_off_var.set(self.radar_off)

        self.correlar_off_var = tk.BooleanVar()
        self.correlar_off_var.set(self.correlar_off)

        self.l2_onoff_var = tk.BooleanVar()
        self.l2_onoff_var.set(True)

        self.l3_onoff_var = tk.BooleanVar()
        self.l3_onoff_var.set(True)

        self.l4_onoff_var = tk.BooleanVar()
        self.l4_onoff_var.set(True)

        self.l5_onoff_var = tk.BooleanVar()
        self.l5_onoff_var.set(True)

        # Casillas WheelMouse / GrabDisplay de la barra del pseudopiloto (de GAMMA)
        self.mouse_wheel_enabled_var = tk.BooleanVar()
        self.mouse_wheel_enabled_var.set(True)
        self.grab_display_enabled_var = tk.BooleanVar()
        self.grab_display_enabled_var.set(True)

        self.toolbar = ventana_auxiliar(self)
        
        # To get previous position of clock and tabs
        self.PosGI = [0, 0]
        self.PosClock = [1800, 40]
        self.PosDepTabular = [240, 0]
        self.PosActTabular = [850, 0]
        self.PosArrTabular = [1280, 0]

        self.f1scale = float(self.conf.read_option(self.sector, "F1scale", "1"))
        self.f1center_x = float(self.conf.read_option(self.sector, "F1center_x", "0"))
        self.f1center_y = float(self.conf.read_option(self.sector, "F1center_y", "0"))

        self.f2scale = float(self.conf.read_option(self.sector, "F2scale", "1"))
        self.f2center_x = float(self.conf.read_option(self.sector, "F2center_x", "0"))
        self.f2center_y = float(self.conf.read_option(self.sector, "F2center_y", "0"))

        self.f3scale = float(self.conf.read_option(self.sector, "F3scale", "1"))
        self.f3center_x = float(self.conf.read_option(self.sector, "F3center_x", "0"))
        self.f3center_y = float(self.conf.read_option(self.sector, "F3center_y", "0"))

        self.giw = PPGeneralInformationWindow(self, fir.sectors, (self.sector), position=self.PosGI)

        # self.clock = RaClock(self.c, position=self.PosClock)
        self.clock = RaClock(self.c, position=[5, 350])
        self.clock.configure(time='%02d:%02d:%02d' % (self.t.hour, self.t.minute, self.t.second))
        self.clock._time['command'] = self.modify_time

        self.windrose = RaWindRose(self.c, position=[0, 40])
        self.windrose.configure(wind_spd='20', wind_dir=0.0, metar='')

        self.dep_tabular = DepTabular(self, self.c, position=self.PosDepTabular)
        self.dep_tabular.adjust(0, 32, 0, 0)

        self.act_tabular = ActTabular(self, self.c, position=self.PosActTabular)
        self.act_tabular.adjust(0, 32, 0, 0)

        self.arr_tabular = ArrTabular(self, self.c, position=self.PosArrTabular)
        self.arr_tabular.adjust(0, 32, 0, 0)

        # Restore local map visibility from Layout<n> (single source of truth)
        layout_str = "Layout" + str(self.disp_number)
        for map_name in self.fir.local_maps:
            self.toolbar.var_ver_localmap[map_name].set(self.conf.read_option(layout_str, map_name, False, "bool"))
        self.toolbar.b_show_hide_localmaps()

        # Get stored values to show/hide the auxiliary tabs (Departures and Printed Strips)
        dep_tab = self.conf.read_option("Aux_Tabs", "Dep_tabular", True, "bool")
        if dep_tab:
            self.dep_tabular.show()
        else:
            self.dep_tabular.hide()

        act_tab = self.conf.read_option("Aux_Tabs", "Act_tabular", True, "bool")
        if act_tab:
            self.act_tabular.show()
        else:
            self.act_tabular.hide()

        arr_tab = self.conf.read_option("Aux_Tabs", "Arr_tabular", True, "bool")
        if arr_tab:
            self.arr_tabular.show()
        else:
            self.arr_tabular.hide()

        # Scale and center done in RaDisplay
        # self.center_x = self.width/2
        # self.center_y = (self.height-40.)/2
        # self.get_scale()

        self.reposition()
        self.toolbar.redraw()
        self.update_tracks()
        self.redraw()
        self.separate_labels()
        self.c.master.bind('<Alt-r>', self.redraw)
        self.c.master.bind('<MouseWheel>', self.b2_mw)


    def modify_time(self):
        def dialog_cb(entries):
            ent_h = entries['H:']
            ent_m = entries['M:']
            ent_s = entries['S:']
            if int(ent_h.get()) >= self.t.hour or int(ent_h.get()) == self.t.hour and int(ent_m.get()) >= self.t.minute:
                self.sendMessage({"message": "modify_time", "H": ent_h.get(), "M": ent_m.get(), "S": ent_s.get()})
        entries = [{'label': 'H:','width': 2,'def_value': "%02d" % self.t.hour}]
        entries.append({'label': 'M:', 'width': 2, 'def_value': "%02d" % self.t.minute})
        entries.append({'label': 'S:', 'width': 2, 'def_value': "%02d" % self.t.second})
        RaDialog(self.c, label='Modificar hora', entries=entries, ok_callback=dialog_cb)

    def process_message(self, m):
        def update_flight(new):
            # canvas = self.c
            # canvas.bind_all(self,'<MouseWheel>',self.b_zoom_menos)
            # Check whether this is a new flight
            # JRAR: Sometimes the order of the messages is not right and an update for
            # a traffic arrives after it has been killed. We cope with that to avoid local "resurrection".
            # TODO: JRAR This synchronization problem should be looked into in more detail
            if new.callsign in self.killed_flights:
                return
            if new.callsign not in [f.callsign for f in self.flights]:
                vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
                # Setting mode implicitly configures label
                vt.mode = 'pp'
                vt.l_font_size = self.label_font_size
                self.tracks.append(vt)
                self._flights_tracks[new] = vt
                self._tracks_flights[vt] = new
                self.flights.append(new)
                return new
                    
            else:  # Otherwise we are updating
                old = [f for f in self.flights if f.callsign == new.callsign][0]
                for name, value in new.__dict__.items():
                    setattr(old, name, value)
                return old

        def reload_flights(flights, time):

            self.clock.configure(time='%02d:%02d:%02d' % (time.hour, time.minute, time.second))
            self.last_update = time - datetime.timedelta(seconds=5)
            for vt in self._tracks_flights:
                vt.destroy()

            self.flights = flights

            self.tracks = []
            self._flights_tracks = {}
            self._tracks_flights = {}
            for f in self.flights:
                vt = VisTrack(self, self.vt_handler, self.do_scale, self.undo_scale)
                # Setting mode implicitly configures label
                vt.mode = 'pp'
                vt.l_font_size = self.label_font_size
                self.tracks.append(vt)
                self._flights_tracks[f] = vt
                self._tracks_flights[vt] = f

            self.killed_flights = []

            self.reposition()
            self.toolbar.redraw()
            self.update_tracks()
            self.redraw()
            self.separate_labels()

            self.dep_tabular.update()
            self.act_tabular.update()
            self.arr_tabular.update()

        def step_update_flight(flight_update):
            if flight_update.callsign in self.killed_flights:
                return
            old = [f for f in self.flights if f.callsign == flight_update.callsign][0]
            old.pos = flight_update.pos
            old.lvl = flight_update.lvl
            old.cfl = flight_update.cfl
            old.ias = flight_update.ias
            old.ground_spd = flight_update.ground_spd
            old.hdg = flight_update.hdg
            old.track = flight_update.track
            return old

        if m['message'] == 'squawk_ident':
            flight = [f for f in self.flights if f.callsign == m['flight'].callsign][0]
            self._flights_tracks[flight].flash_p(0)

        if m['message'] == 'time':
            t = m['data']
            self.update_clock(t)
            self.t = t
            if not self.synchronised:
                self.last_update = self.t - datetime.timedelta(seconds=5)
                self.synchronised = True

        if m['message'] == 'update':
            # if self.updating:
            #    print('Caught updating. Falling behind')
            #    return
            self.updating = True
            # flights = m['flights']
            # for f in flights: update_flight(f)
            flight_updates = m['flight_updates']
            for flight_update in flight_updates:
                step_update_flight(flight_update)
            complete_flight_updates = m['complete_flight_updates']
            for complete_flight_update in complete_flight_updates:
                f = update_flight(complete_flight_update)  # Returns the updated flight
                if f is not None:
                    self.update_track(f)
            if self.disp_number == 1:
                self.write_Cesium_file()
            self.wind = m['wind']
            self.new_wind = m['new_wind']                                         
            self.windset = m['windset']
            self.metar = m['metar']
            self.update_wind(self.wind, self.metar)
            self.giw.qnh = m['qnh']
            self.radar_off = m['radar_off']
            self.radar_off_var.set(m['radar_off'])
            self.correlar_off = m['correlar_off']
            self.correlar_off_var.set(m['correlar_off'])
            # JRAR: Why stop separating labels?
            # self.stop_separating = True

            self.dep_tabular.update()
            self.act_tabular.update()
            self.arr_tabular.update()

            if (self.t-self.last_update).seconds >= self.refresco:
                self.update()
                self.last_update = self.t
            self.updating = False
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
            reload_flights(m['flights'], m['init_time'])  # Returns the updated flight

        if m['message'] == 'radar_off':
            off = m['off']
            self.radar_off.set(off)

        if m['message'] == 'correlar_off':
            off = m['off']
            self.correlar_off.set(off)

        if m['message'] == 'rwy_in_use':
            # Formatos: {'ad': ad, 'rwy': rwy} (GTA) o {'ad': {ad: rwy, ...}}.
            # Antes solo se actualizaba el ultimo aerodromo y se asignaba una lista en vez de la pista.
            ad_rwyinuse = m['ad'] if isinstance(m['ad'], dict) else {m['ad']: m.get('rwy')}
            for ad_code, rwy_desig in ad_rwyinuse.items():
                try:
                    ad = self.fir.aerodromes[ad_code]
                    ad.rwy_in_use = [rwy for rwy in ad.rwy_direction_list if rwy.txt_desig == str(rwy_desig)][0]
                except (KeyError, IndexError):
                    logging.error("No runway direction %s defined for airport %s" % (rwy_desig, ad_code),
                                  exc_info=True)
            
        if m['message'] == 'kill_flight':
            try:
                f = [f for f in self.flights if f.callsign == m['cs']][0]
                self.kill_flight(f)
            except:
                return


    def kill_flight(self, f):
        self.flights.remove(f)
        vt = self._flights_tracks[f]
        if self.selected_track == vt:
            self.selected_track = None
            self.selected_flight = None
        vt.destroy()
        del self._flights_tracks[f]
        del self._tracks_flights[vt]
        self.tracks.remove(vt)
        self.killed_flights.append(f.callsign)

        # Delete fpr and waypoints if any
        canvas = self.c
        canvas.delete(f.callsign+'fpr')
        try:
            self.routes.remove(f)
        except ValueError:
            pass  # Don't act if the fpr did not exist
        canvas.delete(f.callsign+'wp')
        canvas.delete(f.callsign+'wl')
        try:
            self.waypoints.remove(f)
        except ValueError:
            pass  # Don't act if the waypoints did not exist
        # Delete LADS attached if any
        for lad in (lad for lad in self.lads[:] if lad.start==vt or lad.end==vt):
            lad.delete()

    def delete_routes(self, e=None):
        for track in self.tracks:
            self.c.delete(track.cs+'fpr')
            # self.c.delete(track.cs+'wp')
            # self.c.delete(track.cs+'wl')
            self.routes = []
            # self.waypoints=[]
            
    def draw_fpr(self, track):
        canvas = self.c
        line = ()
        if track.to_do == 'fpr':
            line = line+self.do_scale(track.pos)
        # for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        for a in [wp for wp in track.route]:
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
                    canvas.create_text(pto, text=a.fix, fill='orange', tag=track.callsign+'fpr', anchor=tix.SE, font='-*-Helvetica-*--*-10-*-')
                    canvas.create_text(pto, text=eto, fill='orange', tag=track.callsign+'fpr', anchor=tix.NE, font='-*-Helvetica-*--*-10-*-')
            line = line+pto
        if len(line) > 3:
            canvas.create_line(line, fill='orange', tags=track.callsign+'fpr')
        self.routes.append(track)
        self.c.lift(track.callsign+'fpr')
        self.c.lift('track')

    def show_hide_fpr(self, track):
        canvas = self.c
        if canvas.itemcget(track.callsign+'fpr', "fill") == 'orange':
            canvas.delete(track.callsign+'fpr')
            self.routes.remove(track)
        else:
            self.draw_fpr(track)
        canvas = self.c

    def draw_way_point(self, track):
        do_scale = self.do_scale
        canvas = self.c
        canvas.delete(track.callsign+'fpr')
        canvas.delete(track.callsign+'wp')
        canvas.delete(track.callsign+'wl')
        try:
            self.waypoints.remove(track)
        except:
            pass

        size = 4
        font_size = 15
        prev_pto = do_scale(track.pos)
        first_point = True
        # for a_next in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        for a_next in [wp for wp in track.route]:
            if first_point:
                first_point = False
            else:
                a_center.prev_pto = prev_pto
                a_center.next_pto = do_scale(a_next.pos())
                prev_pto = do_scale(a_center.pos())
                first_point = False
            a_center = a_next
        if not first_point:
            a_center.prev_pto = prev_pto
            a_center.next_pto = None
        # for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        route_list_wp = [wp for wp in track.route]
        for i_wp, a in enumerate(route_list_wp):
            # Punto siguiente al que se va a mover: si el avion rebasa este ultimo mientras
            # se define la nueva posicion, GTA inserta el nuevo antes de fix_after
            fix_after_wp = route_list_wp[i_wp+1].fix if i_wp+1 < len(route_list_wp) else None
            (rect_x, rect_y) = pto = do_scale(a.pos())
            if a.stop and a.push_back:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size, fill='purple',activeoutline='orange', outline='yellow', tags=track.callsign+'wp')
                # point_ident = canvas.create_text(rect_x,rect_y,text='+',font=('Helvetica',font_size,'bold'), fill='purple', anchor = 'center',justify = 'center',activefill='orange',tags=track.callsign+'wp')
            elif a.stop:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size, fill='red',activeoutline='orange', outline='yellow', tags=track.callsign+'wp')
                # point_ident = canvas.create_text(rect_x,rect_y,text='Y',font=('Helvetica',font_size,'bold'), fill='red', anchor = 'center',justify = 'center',activefill='orange',tags=track.callsign+'wp')
            elif a.push_back:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size, fill='blue',activeoutline='orange', outline='yellow', tags=track.callsign+'wp')
                # point_ident = canvas.create_text(rect_x,rect_y,text='+',font=('Helvetica',font_size,'bold'), fill='blue', anchor = 'center',justify = 'center',activefill='orange',tags=track.callsign+'wp')
            else:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size, fill='yellow',activeoutline='orange', outline='yellow', tags=track.callsign+'wp')
                # point_ident = canvas.create_text(rect_x,rect_y,text='+',font=('Helvetica',font_size), fill='yellow', anchor = 'center',justify = 'center',activefill='orange',tags=track.callsign+'wp')

            def clicked_on_waypoint(e, point_coord=a.pos(), point_name=a.fix):
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                # If the Delete key is held down when clicking, remove point
                if self.delete_pressed:
                    pto = point_name
                    self.sendMessage({"message": "remove_wp", "cs": track.callsign, "fix": pto})
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    # track.remove_wp(pto)
                    self.draw_way_point(track)
                    return
                # Display window offering "Direct to..." and "Cancel" options.
                track.last_lad = e.serial
                win = tix.Frame(canvas)
                id_avo = tix.Label(win, text=track.callsign, bg='blue', fg='white')
                id_pto = tix.Entry(win, width=8, justify=tix.CENTER)
                id_pto.insert(0, point_name)
                but_direct = tix.Button(win, text="Dar directo")
                but_final = tix.Button(win, text="Final")
                but_remove = tix.Button(win, text="Eliminar")
                but_toggle_stop = tix.Button(win, text="Toggle stop")
                but_cancel = tix.Button(win, text="Cancelar")
                id_avo.grid(row=0, column=0, columnspan=1, sticky=tix.W+tix.E)
                id_pto.grid(row=1, column=0, columnspan=1, sticky=tix.W+tix.E)
                but_direct.grid(row=2, column=0, columnspan=1, sticky=tix.W+tix.E)
                but_final.grid(row=3, column=0, columnspan=1, sticky=tix.W+tix.E)
                but_remove.grid(row=4, column=0, columnspan=1, sticky=tix.W+tix.E)
                but_toggle_stop.grid(row=5, column=0, columnspan=1, sticky=tix.W+tix.E)
                but_cancel.grid(row=6, column=0, columnspan=1, sticky=tix.W+tix.E)
                win_identifier = canvas.create_window(e.x, e.y, window=win)

                def close_win(ident=win_identifier):
                    canvas.delete(ident)

                def remove_wp():
                    pto = id_pto.get()
                    self.sendMessage({"message": "remove_wp", "cs": track.callsign, "fix": pto})
                    # track.remove_wp(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    close_win()

                def final_wp():
                    pto = id_pto.get()
                    self.sendMessage({"message": "final_wp", "cs": track.callsign, "fix": pto})
                    # track.final_wp(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    close_win()

                def direct_to():
                    pto = id_pto.get()
                    self.sendMessage({"message": "route_direct", "cs": track.callsign, "fix": pto})
                    # track.route_direct(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    close_win()

                def toggle_stop():
                    pto = id_pto.get()
                    self.sendMessage({"message": "toggle_stop", "cs": track.callsign, "fix": pto})
                    # track.toggle_stop(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    close_win()

                def push_back():
                    pto = id_pto.get()
                    self.sendMessage({"message": "push_back", "cs": track.callsign, "fix": pto})
                    # track.push_back(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    close_win()
                but_cancel['command'] = close_win
                but_final['command'] = final_wp
                but_remove['command'] = remove_wp
                but_direct['command'] = direct_to
                but_toggle_stop['command'] = toggle_stop
            canvas.tag_bind(point_ident, "<1>", clicked_on_waypoint)
            def rightclicked_on_waypoint(e, point_coord=a.pos(), point_name=a.fix):
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                pto = point_name
                self.sendMessage({"message": "toggle_stop", "cs": track.callsign, "fix": pto})
                # track.toggle_stop(pto)
                canvas.delete(track.callsign+'wp')
                canvas.delete(track.callsign+'wl')
                try:
                    self.waypoints.remove(track)
                except ValueError:
                    pass  # Don't act if the waypoints did not exist
                self.draw_way_point(track)
            canvas.tag_bind(point_ident, "<3>", rightclicked_on_waypoint)

            def ctrl_rightclicked_on_waypoint(e, point_coord=a.pos(), point_name=a.fix):  # Push_back
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                pto = point_name
                self.sendMessage({"message": "push_back", "cs": track.callsign, "fix": pto})
                # track.push_back(pto)
                canvas.delete(track.callsign+'wp')
                canvas.delete(track.callsign+'wl')
                try:
                    self.waypoints.remove(track)
                except ValueError:
                    pass  # Don't act if the waypoints did not exist
                self.draw_way_point(track)
            canvas.tag_bind(point_ident, "<Control-Button-3>", ctrl_rightclicked_on_waypoint)

            def centerclicked_on_waypoint(e, prev_coord=a.prev_pto, next_coord=a.next_pto, point_next=a.fix, fix_after=fix_after_wp, stop=a.stop, push_back=a.push_back):
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    # canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                    # canvas.create_text(e.x,e.y,text='+',font=('Helvetica',font_size), fill='yellow', anchor = 'center',justify = 'center',tags='route_definition')

                def insert_wp(e):
                    # (x,y) = self.undo_scale((e.x, e.y))
                    # fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message": "replace_wp", "cs": track.callsign, "fix_new": fix, "fix_old": point_next, "fix_after": fix_after, "stop": stop, "push_back": push_back})
                    #self.sendMessage({"message": "insert_wp", "cs": track.callsign, "fix": fix, "fix_next": point_next, "stop": stop, "push_back": push_back})
                    # track.insert_wp(fix,point_next)
                    #self.sendMessage({"message": "remove_wp", "cs": track.callsign, "fix": point_next})
                    # track.remove_wp(point_next)
                    self._route_preview_cancel(canvas)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    # ra_bind(self, self.c, '<Button-1>', self.b1_cb) #remove grab display option
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)

                def update_route_being_defined(e):
                    if next_coord is None:
                        line = prev_coord+(e.x, e.y)
                    else:
                        line = prev_coord+(e.x, e.y)+next_coord
                    self._route_preview(canvas, e.x, e.y, size, line)  # redibujado limitado (~30 ms)

                def cancel_def_route(e):
                    if self.latest_processed_serial == e.serial:
                        return
                    self._route_preview_cancel(canvas)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                    # rd.defining_route = False
                ra_unbind(self, self.c, '<Motion>')
                ra_unbind(self, self.c, '<Button-2>')
                ra_unbind(self, self.c, '<Button-3>')
                ra_bind(self, self.c, '<Button-2>', cancel_def_route)
                ra_bind(self, self.c, '<Button-3>', insert_wp)
                ra_bind(self, self.c, '<Motion>', update_route_being_defined)
            canvas.tag_bind(point_ident, "<2>", centerclicked_on_waypoint)

        # size=4
        # (rect_x, rect_y) = prev_pto = do_scale(track.pos)
        # canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='yellow',outline='yellow',tags=track.callsign+'wp')
        prev_pto = do_scale(track.pos)
        line = ()
        if track.to_do == 'fpr':
            line = line+do_scale(track.pos)
        # for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        route_list_wl = [wp for wp in track.route]
        for i_wl, a in enumerate(route_list_wl):
            # Punto siguiente a fix_next: si el avion pasa fix_next mientras se define el nuevo punto,
            # GTA lo inserta antes de este (fix_after)
            fix_after_wl = route_list_wl[i_wl+1].fix if i_wl+1 < len(route_list_wl) else None
            try:
                pto = do_scale(a.pos())
            except:
                continue
            # if a.fix[0] <> '_':
            #    try: eto = '%02d:%02d'%(a.eto.hour, a.eto.minute)
            #    except: eto = ''
            #    canvas.create_text(pto,text=a.fix,fill='yellow',tag=track.callsign+'wp',anchor=tix.SE,font='-*-Helvetica-*--*-10-*-')
            #    canvas.create_text(pto,text=eto,fill='yellow',tag=track.callsign+'wp',anchor=tix.NE,font='-*-Helvetica-*--*-10-*-')
            line = prev_pto+pto
            line_ident = canvas.create_line(line, fill='yellow', width=size, activefill='orange', tags=track.callsign+'wl')

            def clicked_on_wayline(e, prev_coord=prev_pto, next_coord=pto, point_next=a.fix, fix_after=fix_after_wl):
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    # canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',activeoutline='orange',outline='yellow',tags='route_definition')
                    # canvas.create_text(e.x,e.y,text='+',font=('Helvetica',font_size), fill='yellow', anchor = 'center',justify = 'center',tags='route_definition')

                def insert_wp(e):
                    # (x,y) = self.undo_scale((e.x, e.y))
                    # fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message": "insert_wp", "cs": track.callsign, "fix": fix, "fix_next": point_next, "fix_after": fix_after})
                    # track.insert_wp(fix,point_next)
                    self._route_preview_cancel(canvas)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)

                def update_route_being_defined(e):
                    line = prev_coord+(e.x, e.y)+next_coord
                    self._route_preview(canvas, e.x, e.y, size, line)  # redibujado limitado (~30 ms)

                def cancel_def_route(e):
                    if self.latest_processed_serial == e.serial:
                        return
                    self._route_preview_cancel(canvas)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                    # rd.defining_route = False
                ra_unbind(self, self.c, '<Motion>')
                ra_unbind(self, self.c, '<Button-2>')
                ra_unbind(self, self.c, '<Button-3>')
                ra_bind(self, self.c, '<Button-2>', cancel_def_route)
                ra_bind(self, self.c, '<Button-3>', insert_wp)
                ra_bind(self, self.c, '<Motion>', update_route_being_defined)
            canvas.tag_bind(line_ident, "<2>", clicked_on_wayline)
            # JRAR: rightclick on wayline inserts point with stop

            def rightclicked_on_wayline(e, prev_coord=prev_pto, next_coord=pto, point_next=a.fix, fix_after=fix_after_wl):
                if e is not None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    # canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                    # canvas.create_text(e.x,e.y,text='+',font=('Helvetica',font_size), fill='yellow', anchor = 'center',justify = 'center',tags='route_definition')

                def insert_wp(e):
                    # (x,y) = self.undo_scale((e.x, e.y))
                    # fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message": "insert_wp", "cs": track.callsign, "fix": fix, "fix_next": point_next, "fix_after": fix_after})
                    self.sendMessage({"message": "toggle_stop", "cs": track.callsign, "fix": fix})
                    # track.insert_wp(fix,point_next)
                    # track.toggle_stop(fix)
                    self._route_preview_cancel(canvas)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    try:
                        self.waypoints.remove(track)
                    except ValueError:
                        pass  # Don't act if the waypoints did not exist
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                insert_wp(e)
            canvas.tag_bind(line_ident, "<3>", rightclicked_on_wayline)
            prev_pto = pto

        self.waypoints.append(track)
        self.c.lift(track.callsign+'wl')
        self.c.lift('track')
        self.c.lift(track.callsign+'wp')
        canvas.update_idletasks()

    def _route_preview(self, canvas, x, y, size, line):
        """Dibuja el punto y la linea de la ruta que se esta definiendo con el raton.
        Como mucho un redibujado cada ~30 ms y reutilizando los items del canvas
        (antes se borraban y creaban en cada evento de movimiento)."""
        self._route_preview_args = (canvas, x, y, size, line)
        if getattr(self, '_route_preview_job', None) is not None:
            return

        def do_redraw():
            self._route_preview_job = None
            args = getattr(self, '_route_preview_args', None)
            if args is None:
                return
            cv, px, py, sz, ln = args
            rect = getattr(self, '_route_preview_rect', None)
            if rect is None or not cv.type(rect):
                self._route_preview_rect = cv.create_rectangle(
                    px - sz, py - sz, px + sz, py + sz, fill='yellow', activeoutline='orange',
                    outline='yellow', tags='route_definition')
            else:
                cv.coords(rect, px - sz, py - sz, px + sz, py + sz)
            lid = getattr(self, '_route_preview_line', None)
            if lid is None or not cv.type(lid):
                self._route_preview_line = cv.create_line(ln, width=sz, fill='yellow', tags='route_definition')
            else:
                cv.coords(lid, *ln)

        self._route_preview_job = canvas.after(30, do_redraw)

    def _route_preview_cancel(self, canvas):
        """Borra la ruta en definicion y cancela un redibujado pendiente."""
        job = getattr(self, '_route_preview_job', None)
        if job is not None:
            try:
                canvas.after_cancel(job)
            except Exception:
                pass
        self._route_preview_job = None
        self._route_preview_args = None
        self._route_preview_rect = None
        self._route_preview_line = None
        canvas.delete('route_definition')

    def show_hide_way_point(self, f):
        for radisp in self.master.display:
            canvas = radisp.c
            flight = [fl for fl in radisp.flights if fl.callsign == f.callsign][0]
            vt = radisp._flights_tracks[flight]
            # Remove previous selection
            remove_flag = (radisp.selected_track != None)
            add_flag = (radisp.selected_track != vt)
            if remove_flag:
                try:
                    radisp.selected_track.selected = False
                except:
                    logging.warning('Unable to unselect track')
                try:
                    radisp.waypoints.remove(radisp.selected_flight)
                except ValueError:
                    logging.error(ValueError)  # Do not act if the waypoints did not exist
                canvas.delete(radisp.selected_flight.callsign+'wp')
                canvas.delete(radisp.selected_flight.callsign+'wl')
                radisp.selected_track = None
                radisp.selected_flight = None
                ra_unbind(radisp, canvas, '<Control-Button-3>')
            # If current track was not selected already, select it
            if add_flag:
                vt.selected = True
                radisp.draw_way_point(flight)
                radisp.selected_track = vt
                radisp.selected_flight = flight
                ra_bind(radisp, canvas, '<Control-Button-3>', radisp.extend_route)

    def get_point_or_geo(self, e):
        min_snap_distance = 8/self.scale
        min_snap_d2 = min_snap_distance * min_snap_distance
        (x, y) = self.undo_scale((e.x, e.y))
        fix = "X%.5fY%.5f" % (x, y)
        for [nombre, coord] in self.fir.coords.items():
            d2 = (coord[0]-x)*(coord[0]-x)+(coord[1]-y)*(coord[1]-y)
            if d2 < min_snap_d2:
                fix = nombre
                break
        return fix

    def extend_route(self, e):
        if self.selected_flight is None:
            return
        if self.cancel_geotab_serial == e.serial:
            return
        canvas = self.c
        (x, y) = self.undo_scale((e.x, e.y))
        flight = self.selected_flight
        track = self._flights_tracks[flight]

        fix = self.get_point_or_geo(e)
        d = self.sendMessage({"message": "extend_route", "cs": flight.callsign, "fix": fix})

        canvas.delete(track.cs+'wp')
        canvas.delete(track.cs+'wl')
        try:
            self.waypoints.remove(track)
        except ValueError:
            pass  # Don't act if the waypoints did not exist
        self.draw_way_point(flight)

    def change_size(self, e):
        RaDisplay.change_size(self, e)
        self.toolbar.redraw()
        
    def update(self):

        # def after_tracks(x):
        #    self.c.lift('track')
        #    self.c.lift('plot')  # Otherwise the most recent history dot comes above and prevents correct clicking
        #    of the plot
        # threads.deferToThread(self.update_tracks).addCallback(after_tracks)

        self.update_tracks()
        self.c.lift('track')
        self.c.lift('plot')
        RaDisplay.update(self)
        self.update_clock()

        RaDisplay.update(self)
                            
    def update_clock(self, t=None):
        if t is None:
            t = self.t
        else:
            self.t = t
        self.clock.configure(time='%02d:%02d:%02d' % (t.hour, t.minute, t.second))

    def update_wind(self, wind, metar):
        self.windrose.configure(wind_spd='%02d' % wind[0], wind_dir=(wind[1]+180.0) % 360.0, metar=metar)

    def update_tracks(self):

        # If we update the tracks all at once from here, when we are dealing with
        # many of them it will take a long time and the display will feel sluggish
        # Instead we cycle through them inside a thread, and let the main thread
        # update the actual tracks in bunches of 30. This improves responsiveness
        # JRAR: remove sleep, it will probably make the responsiveness worse
        # Let tkinter take care of the efficiency and responsiveness
        for i in range(len(self.flights)):
            self.update_track(self.flights[i])
        return True
            
    def update_track(self, f):
        # TODO This should be a RaDisplay method
        vt = self._flights_tracks[f]

        if f.pof in (Aircraft.GROUND, Aircraft.LANDED):
            vt.alt = 'GND'
        else:
            vt.alt = f.lvl

        vt.cs = f.callsign
        vt.wake = f.wake
        vt.ltype = f.type
        vt.lrwy = f.lrwy
        vt.AirportElev = f.AirportElev
        if f.pof == Aircraft.GROUND:
            vt.echo = '   '
            vt.lrwy = '   '
        else:
            vt.echo = f.campo_eco
            vt.lrwy = f.lrwy

        if f.sid == None or f.fr == 'VEH':
            if f.park == 'None':
                vt.stand_sid = ''
            else:
                vt.stand_sid = f.park
        else:
            vt.stand_sid = f.sid.txt_desig[0:3]

        vt.trans = f.campo_trans
        vt.gs = f.ground_spd
        vt.mach = f.get_mach()
        vt.rules = f.fr
        vt.colat = f.colat
        # vt.r_speed= f.r_speed
        # vt.r_head= f.r_head
        # vt.r_rate= f.r_rate
        vt.lvl_blocked = f.lvl_blocked

        if self.fir.AdHasIfrRwys(f.ades) and f.pof == 'FLYING':
            try:
                [xy_llz, rdl, dist_ayuda, pdte_ayuda, alt_pista] = f.llz
                (rx, ry) = r(xy_llz, f.pos)  # Coordenadas relativas a la radioayuda
                dist_thr = rp((rx, ry))[0]-dist_ayuda
                vt.thr_nm = dist_thr
                vt.thr_min = dist_thr / f.ground_spd * 60.
            except:
                vt.thr_nm = ''
                vt.thr_min = ''
        else:
            vt.thr_nm = ''
            vt.thr_min = ''

        vt.to_do = f.to_do
        vt.hdg = f.hdg
        vt.track = f.track
        vt.rate = f.get_rate_descend()
        vt.ias = f.ias
        vt.adep = f.adep
        sector_list = self.sector.split(",")
        vt.local_dep = False
        for sector in sector_list:
            if (vt.adep in self.fir.local_ads[sector]):
                vt.local_dep = True
        vt.ades = f.ades
        vt.local_des = False
        for sector in sector_list:
            if (vt.ades in self.fir.local_ads[sector]):
                vt.local_des = True
        vt.type = f.type
        vt.radio_cs = f.radio_callsign
        vt.rfl = f.rfl
        vt.cfl = f.cfl
        vt.arrow = f.cfl
        vt.ecl = f.ecl
        vt.eclfix = f.eclfix
        vt.tfl = f.tfl
        vt.line_onoff = [True, True, self.l2_onoff_var.get(), self.l3_onoff_var.get(), self.l4_onoff_var.get(),
                         self.l5_onoff_var.get()]
        vt.flashing = f.trans_pp_pos
        if (f.lvl < self.select_FALT_varmin.get()) or (f.lvl > self.select_FALT_varmax.get()):
            vt.visible = False
        elif self.ojeo:
            vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING))
        else:
            vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING)) and ((f.pp_pos == None) or (f.pp_pos == self.pos_number) or f.trans_pp_pos)
        if (f.pp_pos == None) or (f.pp_pos != self.pos_number):
            vt.assumed = False
        elif f.pp_pos == self.pos_number:
            vt.assumed = True
        if vt.selected:
            self.draw_way_point(f)
        # Label color update when:
        # 1. Dep and Lnd Aircraft. After last Sid point
        # 2. Dep or Overflight. If the Aircraft needs to do App procedure
        vt_color = vt.color.get_basecolor()
        if self.fir.AdHasIfrRwys(f.ades) and f.fr != 'VEH' and vt.assumed and vt_color != vt.ASSUMED_COLOR_PICT:
            if self.fir.AdHasIfrRwys(f.adep) and (len(f.route) != 0 and f.star is not None and f.route[0].fix == f.star.start_fix) or f.to_do == 'app':
                vt.color.set(vt.ASSUMED_COLOR_PICT)
                vt.color_change()

        [x0, y0] = self.do_scale(f.pos)
        vt.coords(x0, y0, self.t)
        vt.refresh()

    def vt_handler(self, vt, item, action, value, e=None):
        RaDisplay.vt_handler(self, vt, item, action, value, e)
        f = self._tracks_flights[vt]
        if item == 'plot':
            if action == '<Button-1>':
                self.show_hide_fpr(f)
        # if item=='ecl':
        #    if action=='update':
        #        self.sendMessage({"message":"set_ecl", "cs": f.callsign, "ecl":int(value)})
        if item == 'cfl':
            if action == 'update':
                d = self.sendMessage({"message": "set_cfl", "cs": f.callsign, "cfl": float(value)})
                return d
        if item == 'rate':
            if action == 'update':
                (rate, force) = value
                return self.sendMessage({"message": "set_rate", "cs": f.callsign,
                                         "rate": rate, "force": force})
        if item == 'hdg':
            if action == 'update':
                (hdg, opt, flagLLZ) = value
                self.sendMessage({"message": "set_hdg", "cs": f.callsign, "hdg": int(hdg), "opt": opt, "flagLLZ": flagLLZ})
        if item == 'ias':
            if action == 'update':
                (spd, force_speed) = value
                d = self.sendMessage({"message": "set_ias", "cs": f.callsign, "ias": spd, "force_speed": force_speed})
                return d
        if item == 'action':
            if action == 'start':
                d = self.sendMessage({"message": "start", "cs": f.callsign})
                return d
        if item == 'engine':
            if action == 'fire':
                d = self.sendMessage({"message": "fire", "cs": f.callsign})
                return d
        if item == 'mach':
            if action == 'update':
                (spd, force_speed) = value
                d = self.sendMessage({"message": "set_mach", "cs": f.callsign, "mach": spd, "force_speed": force_speed})
                return d
        # if item=='echo':
        #    if action=='<Button-3>':
        #        self.show_hide_way_point(f)
        #        if e!=None:
        #            self.cancel_geotab_serial = e.serial

        if item == 'set_trans':
            if action == 'update':
                trans = value
                d = self.sendMessage({"message": "set_trans", "cs": f.callsign, "trans": trans})
                return d

        if item == 'sid_star':
            if action == 'change_procedure':
                self.change_procedure_dialog(f, e)

    def change_procedure_dialog(self, f, e=None):
        """Show a dialog to allow the user to define rwy and sid"""
        # def close():
        #     toplevel.destroy()
        #     return

        def change(e=None):
            def change_element(e=None):
                selected_procedure = Procedure_listbox.get(tix.ACTIVE)
                selected_rwy = rwy_listbox.get(tix.ACTIVE)
                self.sendMessage({"message": "change_procedure", "cs": f.callsign, "procedure_type": proctype, "procedure": selected_procedure, "rwy": selected_rwy})
                Newtoplevel.destroy()

            def select_rwy(e=None):
                selected_rwy = rwy_listbox.get(rwy_listbox.nearest(e.y))
                Procedure_listbox.delete(0, tix.END)
                Element_list = []

                if Element == 'Change SID Procedure':
                    for rwy in ad.rwy_direction_list:
                        if rwy.txt_desig == selected_rwy:
                            rwy_in_use = rwy
                    for sid in rwy_in_use.sid_dict.values():
                        Procedure_listbox.insert(tix.END, sid.txt_desig)
                        Element_list.append(sid.txt_desig)

                elif Element == 'Change STAR Procedure':
                    for rwy in ad.rwy_direction_list:
                        if rwy.txt_desig == selected_rwy:
                            rwy_in_use = rwy
                    for star in rwy_in_use.star_dict.values():
                        Procedure_listbox.insert(tix.END, star.txt_desig)
                        Element_list.append(star.txt_desig)

                return

            def select_procedure(e=None):
                selected_rwy = rwy_listbox.get(rwy_listbox.nearest(e.y))
                selected_procedure = Procedure_listbox.get(Procedure_listbox.nearest(e.y))
                return

            # Element = Element_listbox.get(tix.ACTIVE)
            Element = 'Change SID Procedure'
            # x, y = toplevel.winfo_pointerxy()
            # toplevel.destroy()
            x, y = 100, 100

            Newtoplevel = tix.Toplevel()
            Newtoplevel.title(f.callsign)
            Newtoplevel.geometry("+%d+%d" % (x, y))

            rwy_listbox = tix.Listbox(Newtoplevel, width=30, height=6)
            rwy_listbox.pack()
            Procedure_listbox = tix.Listbox(Newtoplevel, width=30, height=20)
            rwy_list = []
            Element_list = []

            if Element == 'Change SID Procedure':
                proctype = 'SID'
                # if f.adep in self.fir.aerodromes.keys() and f.route[0].fix in [f.park, 'P1000'] and f.fr != 'VEH':
                if f.adep in self.fir.aerodromes.keys() and f.fr != 'VEH':
                    ad = self.fir.aerodromes[f.adep]
                    for rwy in ad.rwy_direction_list:
                        if len(rwy.sid_dict) > 0:
                            rwy_list.append(rwy.txt_desig)
                else:
                    logging.warning("No SIDs found for %s departing from %s" % (f.callsign, f.adep))

                rwy_listbox.insert(0, *rwy_list)
                try:
                    for rwy in ad.rwy_direction_list:
                        if rwy.txt_desig == f.rdep:
                            rwy_in_use = rwy
                            break

                    for sid in rwy_in_use.sid_dict.values():
                        Procedure_listbox.insert(tix.END, sid.txt_desig)
                        Element_list.append(sid.txt_desig)

                except:
                    logging.warning("No SIDs found for %s from %s" % (f.callsign, f.adep))
                    Newtoplevel.destroy()
                    return

            elif Element == 'Change STAR Procedure':
                proctype = 'STAR'
                if f.ades in self.fir.aerodromes.keys() and f.iaf not in f.log and f.fr != 'VEH':
                    ad = self.fir.aerodromes[f.ades]
                    for rwy in ad.rwy_direction_list:
                        if len(rwy.star_dict) > 0:
                            rwy_list.append(rwy.txt_desig)
                else:
                    logging.warning("No STARs found for %s landing from %s" % (f.callsign, f.ades))

                rwy_listbox.insert(0, *rwy_list)
                try:
                    for rwy in ad.rwy_direction_list:
                        if rwy.txt_desig == f.rdes:
                            rwy_in_use = rwy
                            break

                    for star in rwy_in_use.star_dict.values():
                        Procedure_listbox.insert(tix.END, star.txt_desig)
                        Element_list.append(star.txt_desig)
                except:
                    logging.warning("No STARs found for %s from %s" % (f.callsign, f.ades))
                    Newtoplevel.destroy()
                    return

            scrollbar = Scrollbar(Newtoplevel)

            # Attaching Listbox to Scrollbar
            Procedure_listbox.config(yscrollcommand=scrollbar.set)

            # setting scrollbar command parameter
            # to listbox.yview method to have a vertical view
            scrollbar.config(command=Procedure_listbox.yview)
            tix.Button(Newtoplevel, text='Aceptar', command=change_element).pack(side=BOTTOM)
            Procedure_listbox.pack(side=LEFT, fill=BOTH)
            scrollbar.pack(side=RIGHT, fill=BOTH)
            rwy_listbox.bind("<Button-1>", select_rwy)
            Procedure_listbox.bind("<Button-1>", select_procedure)

        # toplevel = tix.Toplevel()
        # toplevel.title(f.callsign)
        # toplevel.geometry("+%d+%d" % (e.x_root, e.y_root))
        #
        # Element_listbox = tix.Listbox(toplevel, width=30, height=6)
        # Element_listbox.pack()
        # items = (
        #     'Change SID Procedure',
        #     'Change STAR Procedure',
        # )
        # Element_listbox.insert(0, *items)
        # tix.Button(toplevel, text='Aceptar', bg='gray', command=change).pack(side=BOTTOM, expand=True)

        change()

    def reposition(self):
        RaDisplay.reposition(self)
        r = self.routes[:]
        w = self.waypoints[:]
        self.delete_routes()
        for track in r:
            self.draw_fpr(track)
        for track in w:
            self.draw_way_point(track)


    def redraw(self,e=None):
        RaDisplay.redraw(self)
        self.update_tracks()

    def b1_cb(self, e):
        # RaDisplay.b1_cb(self,e)
        if self.fir.param('pp_arrastre_pantalla', True):  # parametro de escenario (por defecto off en LEMD)
            self.grab_display(e)
        self.toolbar.close_windows()
    
    def b2_cb(self, e):
        RaDisplay.b2_cb(self, e)
        self.toolbar.close_windows()
    
    def b3_cb(self, e):
        RaDisplay.b3_cb(self, e)
        self.toolbar.close_windows()
        
    def save_state(self):
        """Save pseudopilot-specific state, then delegate to RaDisplay.save_state()."""
        self.conf.write_option(self.sector, "PosGIx", str(self.giw._x))
        self.conf.write_option(self.sector, "PosGIy", str(self.giw._y))
        self.conf.write_option(self.sector, "PosClockx", str(self.clock._x))
        self.conf.write_option(self.sector, "PosClocky", str(self.clock._y))

        self.conf.write_option(self.sector, "PosDepTabularx", str(self.dep_tabular._x))
        self.conf.write_option(self.sector, "PosDepTabulary", str(self.dep_tabular._y))
        self.conf.write_option(self.sector, "PosActTabularx", str(self.act_tabular._x))
        self.conf.write_option(self.sector, "PosActTabulary", str(self.act_tabular._y))
        self.conf.write_option(self.sector, "PosArrTabularx", str(self.arr_tabular._x))
        self.conf.write_option(self.sector, "PosArrTabulary", str(self.arr_tabular._y))

        self.conf.write_option(self.sector, "F1scale", str(self.f1scale))
        self.conf.write_option(self.sector, "F1center_x", str(self.f1center_x))
        self.conf.write_option(self.sector, "F1center_y", str(self.f1center_y))

        self.conf.write_option(self.sector, "F2scale", str(self.f2scale))
        self.conf.write_option(self.sector, "F2center_x", str(self.f2center_x))
        self.conf.write_option(self.sector, "F2center_y", str(self.f2center_y))

        self.conf.write_option(self.sector, "F3scale", str(self.f3scale))
        self.conf.write_option(self.sector, "F3center_x", str(self.f3center_x))
        self.conf.write_option(self.sector, "F3center_y", str(self.f3center_y))

        self.conf.write_option("Aux_Tabs", "Dep_tabular", bool(self.dep_tabular.showed))
        self.conf.write_option("Aux_Tabs", "Act_tabular", bool(self.act_tabular.showed))
        self.conf.write_option("Aux_Tabs", "Arr_tabular", bool(self.arr_tabular.showed))

        # Local map state is written by RaDisplay.save_state() into Layout<n>
        RaDisplay.save_state(self)

    def exit(self):
        self.clock.close()
        # Avoid memory leaks due to circular references preventing
        # the garbage collector from discarding this object
        del(self.toolbar.master)
        del(self.dep_tabular.master)
        del(self.act_tabular.master)
        del(self.arr_tabular.master)
        # Destroy radar windows - save_state() + conf.save() + cleanup by RaDisplay
        self.giw.exit()
        RaDisplay.exit(self)
        del self._flights_tracks
        del self._tracks_flights

    def __del__(self):
        logging.debug("PpDisplay.__del__")


class ventana_auxiliar:
    def __init__(self, master):
        self.master = master
        self.conf = master.conf
        self.opened_windows = []
        self.vr = tk.IntVar()
        self.vr.set(master.draw_routes)
        self.vf = tk.IntVar()
        self.vf.set(master.draw_point)
        self.vfn = tk.IntVar()
        self.vfn.set(master.draw_point_names)
        self.vs = tk.IntVar()
        self.vs.set(master.draw_sector)
        self.vsl = tk.IntVar()
        self.vsl.set(master.draw_lim_sector)
        self.vt = tk.IntVar()
        self.vt.set(master.draw_tmas)
        self.vd = tk.IntVar()
        self.vd.set(master.draw_deltas)
        self.var_ver_localmap = {}
        self.var_ver_desp_tab = tk.IntVar()
        self.var_ver_act_tab = tk.IntVar()
        self.var_ver_arr_tab = tk.IntVar()
        self.var_ver_windrose = tix.IntVar()
        self.var_ver_fichas_tab = tk.IntVar()
        for map_name in master.fir.local_maps:
            self.var_ver_localmap[map_name] = tk.IntVar()
        self.auto_sep = tk.IntVar()
        self.auto_sep.set(self.master.auto_separation)
        self.speed_vector_var = tk.IntVar()
        self.speed_vector_var.set(0)
        self.clock_speed_var = tk.DoubleVar()
        self.clock_speed_var.set(1.0)
        # self.select_FALT_varmin = tk.IntVar()
        # self.select_FALT_varmin.set(0)
        self.select_FALT_varmax = tk.IntVar()
        self.select_FALT_varmax.set(990)
        self.toolbar_id = None
        
        self.new_route_RaD = None
        self.acft_data_RaD = None

    def close_windows(self):
        for w in self.opened_windows[:]:
            self.master.c.delete(w)
            self.opened_windows.remove(w)

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
            self.close_windows()
            # master.x0 -= ancho/set_displacement(event.num)/scale
            master.center_x += ancho/set_displacement(event.num)
            master.reposition()
            
        def b_derecha(event):
            self.close_windows()
            # master.x0 += ancho/set_displacement(event.num)/scale
            master.center_x -= ancho/set_displacement(event.num)
            master.reposition()
            
        def b_arriba(event):
            self.close_windows()
            # master.y0 += ancho/set_displacement(event.num)/scale
            # master.center_y += alto/set_displacement(event.num)
            # master.reposition()
            # PARA QUE SUBA EL MAPA CUANDO YO PULSO ARRIBA
            master.center_y += alto/set_displacement(event.num)
            master.reposition()

        def b_abajo(event):
            self.close_windows()
            # master.y0 -= ancho/set_displacement(event.num)/scale
            # master.center_y -= alto/set_displacement(event.num)
            # master.reposition()
            # PARA QUE BAJE EL MAPA CUANDO YO PULSO ABAJO
            master.center_y -= alto/set_displacement(event.num)
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
            elif event_number == 4:
                return MINIMUM_SCALE_FACTOR
            elif event_number == 5:
                return MINIMUM_SCALE_FACTOR
            
        def b_zoom_mas(event):
            self.close_windows()
            master.scale *= set_zoom_scale_on_event(event.num)
            master.reposition()
            
        def b_zoom_menos(event):
            self.close_windows()
            master.scale /= set_zoom_scale_on_event(event.num)
            master.reposition()
            
        def b_standard():
            self.close_windows()
            master.center_x = ancho/2
            master.center_y = (alto-40.)/2
            master.get_scale()
            master.reposition()
            
        def b_inicio():
            self.close_windows()
            master.sendMessage({"message": "play"})
                
        def b_parar():
            self.close_windows()
            master.sendMessage({"message": "pause"})

        def b_reinicio():
            self.close_windows()

            def close(e=None):
                master.sendMessage({"message": "restart_exercise"})

            RaDialog(self.master.c, label='Reinicio', text=u"¿Desea recargar el ejercicio?", ok_callback=close)

        def b_tamano_fichas(event):
            self.close_windows()
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
                        
        self.b_show_hide_localmaps()

        def b_auto_separationaration():
            self.close_windows()
            global auto_separation
            auto_separation = not auto_separation

        def get_selected(label=''):
            if master.selected_track is None:
                RaDialog(master.c, label=label,
                    text='No hay ningún vuelo seleccionado')
            return master.selected_track

        def kill_acft():
            self.close_windows()
            if (get_selected('Matar vuelo')==None): return
            a = master.selected_track
            def kill():
                master.sendMessage({"message": "kill", "cs": a.cs})
                # a.visible=False
            RaDialog(master.c, label=str(a.cs)+': Matar vuelo',
                       text='Matar '+str(a.cs), ok_callback=kill,
                       position=(a.x, a.y))
                    
        def quitar_fpr():
            self.close_windows()
            for a in ejercicio:
                if w.itemcget(a.callsign+'fpr', 'fill') == 'orange':
                    w.delete(a.callsign+'fpr')
                    
        def quitar_lads():
            self.close_windows()
            global all_lads, superlad
            for lad_to_remove in all_lads:
                if lad_to_remove.line_id != None:
                    w.delete(lad_to_remove.line_id)
                if lad_to_remove.text_id1 != None:
                    w.delete(lad_to_remove.text_id1)
                if lad_to_remove.text_id2 != None:
                    w.delete(lad_to_remove.text_id2)
                if lad_to_remove.text_id3 != None:
                    w.delete(lad_to_remove.text_id3)
                if lad_to_remove.text_id4 != None:
                    w.delete(lad_to_remove.text_id4)
                #     all_lads.remove(lad_to_remove)
                #     lad_to_remove.destroy()
                if superlad == lad_to_remove:
                    superlad = None
            all_lads = []  
        win_identifier = None
        
        # def quitar_tormentas():
        #    for s in storms[:]:
        #        s.delete()
        #        storms.remove(s)
        
                        
        def define_holding():
            """Show a dialog to set the selected aircraft in a holding pattern over the selected fix"""
            self.close_windows()
            if (get_selected('Poner en espera')==None): return
            sel = master._tracks_flights[master.selected_track]
                
            def set_holding(e=None, entries=None):
                error = False
                ent_hold = entries['Fijo Principal:']
                ent_side = entries['Virajes (I/D):']
                fijo = ent_hold.get().upper()
                lado = ent_side.get().upper()
                if not fijo in sel.route:
                    ent_hold['bg'] = 'red'
                    ent_hold.focus_set()
                    error = True
                if lado.upper() == 'I': std_turns = False
                elif lado.upper() == 'D' or lado.strip() == '': std_turns = True
                else:
                    ent_side['bg'] = 'red'
                    ent_side.focus_set()
                    error = True
                if error:
                    return False  # Not validated correctly
                
                master.sendMessage({"message":"hold", "cs":sel.callsign,
                                    "fix": fijo, "std_turns": std_turns})
                
            # Build the GUI Dialog
            entries=[]
            entries.append({'label': 'Fijo Principal:', 'width': 5, 'def_value': sel.route[0].fix})
            entries.append({'label': 'Virajes (I/D):', 'width': 1, 'def_value': ''})
            RaDialog(w, label=sel.callsign+': Poner en espera', ok_callback=set_holding, entries=entries)
            
        def nueva_ruta():
            self.close_windows()

            """Ask the user to set a new route and destination airdrome for the currently selected aircraft"""
            self.close_windows()
            if (get_selected('Nueva ruta')==None): return
            sel = master._tracks_flights[master.selected_track]

            def change_fpr_unsaved(e=None, entries=None):
                ent_route, ent_destino = entries['Ruta:'], entries['Destino:']
                pts = ent_route.get()
                try:
                    pts_split = pts.split('_LLZ')
                    if len(pts_split) == 2:
                        r1 = Route.Route(Route.get_waypoints(pts_split[0]),
                            raise_on_unknown=True)
                        r2 = Route.Route(Route.get_waypoints(pts_split[1]),
                            raise_on_unknown=True)
                    else:
                        r = Route.Route(Route.get_waypoints(pts),
                            raise_on_unknown=True)
                except:
                    ent_route['bg'] = 'red'
                    ent_route.focus_set()
                    logging.debug("Unable to set the new route", exc_info=True)
                    return False  # Validation failed
                # TODO we should validate the destination
                sel.ades = ent_destino.get().upper()

                # SAVED/UNSAVED OPTION
                master.sendMessage({"message": "change_fpr",
                                    "cs":      sel.callsign,
                                    "route":   pts,
                                    # JRAR: We were losing stop and push_back info
                                    # "route":   str(r),
                                    "ades":    sel.ades})

            def change_fpr(e=None, entries=None):
                ent_route, ent_destino=entries['Ruta:'], entries['Destino:']
                pts = ent_route.get()

                ##############################################Devolver los valores de los puntos de la nueva ruta
                pts_split = pts.split(' ')
                if sel.sid != None:
                    park = sel.park
                    rwy = sel.deprwy
                    coord = ''
                    for pt in pts_split:
                        if pt == sel.sid_start:
                            break
                        coord = coord + ',' + pt
                    coord = coord[1:]
                    fir_path = master.fir.file
                    str_dep = '[dep_'+sel.adep+rwy+']\n'
                    rwy_found = False
                    file_str = ''
                    fir_file = open(fir_path, 'r')
                    for line in fir_file:
                        if rwy_found:
                            split_line = line.split('=')
                            this_park = split_line[0].strip()
                            if this_park == park:
                                line = park + ' = ' + coord +'\n'
                                rwy_found = False
                        elif line == str_dep:
                            rwy_found = True
                        file_str = file_str + line
                    fir_file.close()
                    fir_file = open(fir_path, 'w')
                    fir_file.write(file_str)
                    fir_file.close()
                if sel.star != None:
                    park = sel.park
                    rwy = sel.desrwy
                    coord = ''
                    for i in range(len(pts_split), 1, -1):
                        pt = pts_split[i-1]
                        if pt == '_LLZ':
                            break
                        coord = pt + ',' + coord
                    coord = coord[:-1]
                    fir_path = master.fir.file
                    str_lnd = '[lnd_'+sel.ades+rwy+']\n'
                    rwy_found = False
                    file_str = ''
                    fir_file= open(fir_path, 'r')
                    for line in fir_file:
                        if rwy_found:
                            split_line = line.split('=')
                            this_park = split_line[0].strip()
                            if this_park == park:
                                line = park + '= ' + coord +'\n'
                                rwy_found = False
                        elif line == str_lnd:
                            rwy_found = True
                        file_str = file_str + line
                    fir_file.close()
                    fir_file = open(fir_path, 'w')
                    fir_file.write(file_str)
                    fir_file.close()
                ###################################################################################################

                try:
                    pts_split = pts.split('_LLZ')
                    if len(pts_split) == 2:
                        r1 = Route.Route(Route.get_waypoints(pts_split[0]),
                            raise_on_unknown=True)
                        r2 = Route.Route(Route.get_waypoints(pts_split[1]),
                            raise_on_unknown=True)
                    else:
                        r = Route.Route(Route.get_waypoints(pts),
                            raise_on_unknown=True)
                except:
                    ent_route['bg'] = 'red'
                    ent_route.focus_set()
                    logging.debug("Unable to set the new route", exc_info=True)
                    return False  # Validation failed
                # TODO we should validate the destination
                sel.ades = ent_destino.get().upper()

                # SAVED/# D OPTION

                master.sendMessage({"message": "change_fpr",
                                    "cs":      sel.callsign,
                                    "route":   pts,
                                    # JRAR: We were losing stop and push_back info
                                    # "route":   str(r),
                                    "ades":    sel.ades})
            # Build the GUI Dialog
            entries = []
            ruta = ""
            # for fix in [wp.fix for wp in sel.route if wp.type==Route.WAYPOINT]:
            for wp in sel.route:
                # if wp.type==Route.WAYPOINT:
                #    ruta += " " + wp.fix
                #    if wp.stop:
                #        ruta+='*'
                #    if wp.push_back:
                #        ruta+='<'
                # JRAR: Include all waypoint types
                ruta += " " + wp.fix
                if wp.stop:
                    ruta += '*'
                if wp.push_back:
                    ruta += '<'
            ruta = ruta.strip()

            entries.append({'label': 'Ruta:', 'width': 50, 'def_value': ruta})
            entries.append({'label': 'Destino:', 'width': 5, 'def_value': sel.ades})

            # Elige la opcion de guardar ruta o no
            RaDialog(w, label=sel.callsign+': Nueva ruta', ok_callback=change_fpr_unsaved, entries=entries)
            #                     ok_callback=change_fpr,entries=entries)

        def cambiar_viento():
            """Show a dialog to allow the user to change the wind in real time"""
            self.close_windows()
            wind = master.windset
            def change_wind(e=None,entries=None):
                ent_dir = entries['Dirección:']
                ent_int = entries['Intensidad (kts):']
                int = ent_int.get()
                dir = ent_dir.get()
                fallo = False
                if dir.isdigit():
                    new_rumbo = (float(dir)+180.0) % 360.0
                else:
                    ent_dir['bg'] = 'red'
                    ent_dir.focus_set()
                    fallo = True
                if int.isdigit():
                    new_intensidad = float(int)
                else:
                    ent_int['bg'] = 'red'
                    ent_int.focus_set()
                    fallo = True
                if fallo:
                    return False  # Validation failed

                # Change String Meteo
                viento = master.metar.split()[2]
                n_viento = dir+int+'KT'

                master.metar = master.metar.replace(viento, n_viento)
                meteo = master.metar
                master.sendMessage({"message": "metar", "metar": meteo})

                master.sendMessage({"message": "wind",
                                    "wind": [master.wind[0], master.wind[1]]})

                master.sendMessage({"message": "new_wind",
                                    "new_wind": [new_intensidad, new_rumbo]})

                master.wind = [master.wind[0], master.wind[1]]
                
            # Build the GUI Dialog
            entries=[]
            entries.append({'label': 'Dirección:','width': 3,'def_value': int((wind[1]+180.0) % 360.0)})
            entries.append({'label': 'Intensidad (kts):', 'width': 2, 'def_value': int(wind[0])})
            RaDialog(w, label='Definir viento', ok_callback=change_wind, entries=entries)
            
            
        def hdg_after_fix():
            """Show a dialog to command the selected aircraft to follow a heading after a certain fix"""
            self.close_windows()
            if (get_selected('Rumbo después de fijo')==None): return
            sel = master._tracks_flights[master.selected_track]
                
            def set_fix_hdg(e=None,entries=None):
                error = False
                ent_fix = entries['Fijo:']
                ent_hdg = entries['Rumbo:']
                fijo = ent_fix.get().strip().upper()
                hdg = ent_hdg.get().strip()
                if fijo not in sel.route:
                    ent_fix['bg'] = 'red'
                    ent_fix.focus_set()
                if not hdg.isdigit():
                    ent_hdg['bg'] = 'red'
                    ent_hdg.focus_set()
                    error = True
                else: 
                    hdg = float(hdg)
                if error:
                    return False  # Validation failed
                
                master.sendMessage({"message": "hdg_after_fix",
                                    "cs": sel.callsign,
                                    "fix": fijo,
                                    "hdg": hdg})

            # Build the GUI Dialog
            entries=[]
            entries.append({'label': 'Fijo:', 'width': 5, 'def_value': str(sel.route[0].fix)})
            entries.append({'label': 'Rumbo:', 'width': 3})
            RaDialog(w, label=sel.callsign+': Rumbo después de fijo', ok_callback=set_fix_hdg, entries=entries)
            
        def int_rdl():
            """Show a dialog to command the selected aircraft to intercept a radial"""
            self.close_windows()
            if (get_selected('Interceptar radial')==None): return
            sel = master._tracks_flights[master.selected_track]
            def set_rdl(e=None,entries=None):
                error = True
                ent_fix=entries['Fijo:']
                ent_rdl=entries['Radial:']
                ent_d_h=entries['Desde/Hacia (D/H)']
                fijo = ent_fix.get().upper()
                rdl = ent_rdl.get().upper()
                d_h = ent_d_h.get().upper()
                for [nombre,coord] in master.fir.points:
                    if nombre == fijo:
                        auxiliar = coord
                        error = False
                        break
                if error:
                    ent_fix['bg'] = 'red'
                    ent_fix.focus_set()
                if not rdl.isdigit():
                    ent_rdl['bg'] = 'red'
                    ent_rdl.focus_set()
                    error = True
                else: 
                    rdl = float(rdl)
                if d_h == 'H':
                    correccion = 180.
                elif d_h == 'D':
                    correccion = 0.
                else:
                    ent_d_h['bg'] = 'red'
                    ent_d_h.focus_set()
                    error = True
                if error:
                    return False  # Validation failed
                
                master.sendMessage({"message": "int_rdl",
                                    "cs": sel.callsign,
                                    "fix": fijo,
                                    "track": (rdl + correccion)% 360.})
                
            # Build the GUI Dialog
            entries = []
            entries.append({'label': 'Fijo:', 'width':5,'def_value': str(sel.route[0].fix)})
            entries.append({'label': 'Radial:', 'width': 3})
            entries.append({'label': 'Desde/Hacia (D/H)', 'width': 1, 'def_value': 'D'})
            RaDialog(w, label=sel.callsign+': Interceptar radial', ok_callback=set_rdl, entries=entries)

        # DISTINGUIMOS ENTRE LOS PROCEDIMIENTOS MAP Y FRUSTRADA: FRUSTRADA ES UN ABORTO DE ATERRIZAJE POR LO QUE SE DETIENE EL DESCENSO, MIENTRAS QUE MAP CONTINUARÁ DESCENDIENDO HASTA COMPLETAR LA PASADA BAJA

        def b_execute_map():
            """Show a dialog to command the selected aircraft to miss the approach"""
            self.close_windows()
            if (get_selected('Ejectuar MAP')==None): return
            sel = master._tracks_flights[master.selected_track]
            if not master.fir.AdHasIfrRwys(sel.ades):
                RaDialog(w, label='Ejecutar MAP',
                         text='Aeropuerto de destino sin procedimientos de APP')
                return                
            def exe_map(e=None):
                master.sendMessage({"message":"execute_map", "cs":sel.callsign})
            RaDialog(w, label=sel.callsign+': Ejecutar MAP',
                     text='Ejecutar MAP', ok_callback=exe_map)

        def b_execute_lowpass():
            """Show a dialog to command the selected aircraft to miss the approach"""
            self.close_windows()
            if (get_selected('Ejectuar pasada baja')==None): return
            sel = master._tracks_flights[master.selected_track]
            if not master.fir.AdHasIfrRwys(sel.ades):
                RaDialog(w, label='Ejecutar pasada baja',
                         text='Aeropuerto de destino sin procedimientos de APP')
                return
            def exe_lowpass(e=None):
                master.sendMessage({"message":"execute_lowpass", "cs":sel.callsign})
            RaDialog(w, label=sel.callsign+': Ejecutar pasada baja',
                     text='Ejecutar pasada baja', ok_callback=exe_lowpass)

        def b_int_ils():
            """Show a dialog to command the selected aircraft to intercept and follow the ILS"""
            self.close_windows()
            if (get_selected('Interceptar ILS')==None): return
            sel = master._tracks_flights[master.selected_track]
            if not master.fir.AdHasIfrRwys(sel.ades):
                RaDialog(w, label=sel.callsign+': Interceptar ILS',
                         text='Aeropuerto de destino sin procedimientos de APP')
                return
            elif sel.iaf == 'N/A':
                RaDialog(w,label=sel.callsign+': Interceptar ILS',
                         text='Vuelo sin procedimiento asociado. Añada procedimiento de aproximación y reintente')
                return
                
            def int_ils(e=None):
                master.sendMessage({"message": "int_ils", "cs":sel.callsign})
            RaDialog(w, label=sel.callsign+': Interceptar ILS',
                     text='Interceptar ILS', ok_callback=int_ils)
            
        def b_llz():
            """Show a dialog to command the selected aircraft to intercept and follow \
            the LLZ (not the GP)"""
            self.close_windows()
            if (get_selected('Interceptar LLZ')==None): return
            sel = master._tracks_flights[master.selected_track]
            if not master.fir.AdHasIfrRwys(sel.ades):
                RaDialog(w, label=sel.callsign+': Interceptar LLZ',
                         text='Aeropuerto de destino sin procedimientos de APP')
                return
            elif sel.iaf == 'N/A':
                RaDialog(w, label=sel.callsign+': Interceptar LLZ',
                         text='Vuelo sin procedimiento asociado. Añada procedimiento de aproximación y reintente')
                return
            def int_llz(e=None):
                master.sendMessage({"message":"int_llz", "cs":sel.callsign})
            RaDialog(w, label=sel.callsign+': Interceptar LLZ',
                     text='Interceptar LLZ', ok_callback=int_llz)

        def b_arrv():
            """Show a dialog to command the selected aircraft to intercept and follow \
            the LLZ (not the GP)"""
            self.close_windows()
            if (get_selected('Interceptar ARRV')==None): return
            sel = master._tracks_flights[master.selected_track]
            if not master.fir.AdHasIfrRwys(sel.ades):
                RaDialog(w, label=sel.callsign+': Interceptar ARRV',
                         text='Aeropuerto de destino sin procedimientos de APP')
                return
            elif sel.iaf == 'N/A':
                RaDialog(w, label=sel.callsign+': Interceptar ARRV',
                         text='Vuelo sin IAF. Añada la ruta hasta el IAF y reintente')
                return
            def int_arrv(e=None):
                master.sendMessage({"message":"int_arrv", "cs":sel.callsign})
            RaDialog(w, label=sel.callsign+': Interceptar ARRV',
                     text='Interceptar ARRV', ok_callback=int_arrv)
            
        def ver_detalles():
            """Show a dialog to view details of the selected flight"""
            self.close_windows()
            if (get_selected('Ver Detalles')==None): return
            sel = self.master.selected_track
            # TODO The RaDialog should probably export the contents frame
            # and we could use it here to build the contents using a proper grid
            RaDialog(self.master.c, label=sel.cs+': Detalles',
                     text='Origen: ' + sel.adep +
                     '\tDestino: '   + sel.ades +
                     '\nTipo:   '    + sel.type.ljust(4) +
                     '\tRFL:     '   + str(int(sel.rfl)) +
                     '\nCallsign: '  + sel.radio_cs +
                     '\tFR:     '   + self.master._tracks_flights[sel].fr)

        def b_orbitar():
            """Show a dialog to command the selected aircraft to make orbits"""    
            self.close_windows()
            if (get_selected('Órbita inmediata')==None):
                return
            sel = master._tracks_flights[master.selected_track]

            def set_orbit(e=None, sel=sel, entries=None):
                side_aux = entries['Orbitar hacia:']['value']
                if side_aux.upper() == 'IZDA':
                    dir = Aircraft.LEFT  # Constant defined in Aircraft.py
                else:
                    dir = Aircraft.RIGHT
                master.sendMessage({"message":"orbit", "cs":sel.callsign, "direction":dir})
            entries=[]
            entries.append({'label': 'Orbitar hacia:',
                            'values': ('IZDA','DCHA'),
                            'def_value': 'IZDA'})
            RaDialog(w, label=sel.callsign+': Orbitar',
                     ok_callback=set_orbit, entries=entries)

        def meteo_visual():

            varActualmeteo = master.metar.split()[4]
            print ("Updated meteo settings: "+varActualmeteo)

            def lluvia():

                patronQNH = re.compile('Q[0-9]{3,4}')
                findQNH = patronQNH.search(master.metar)
                qnh = findQNH.group()
                valActual = master.metar.split()[4]
                visibilidad = master.metar.split()[3]

                HoraCambio = master.metar.split()[1]
                HoraActual = str('0%1s' % master.t.day if len(str(master.t.day)) < 2 else master.t.day) + str(
                    '0%1s' % master.t.hour if len(str(master.t.hour)) < 2 else master.t.hour) \
                             + str('0%1s' % master.t.minute if len(str(master.t.minute)) < 2 else master.t.minute) + 'Z'

                if valActual in ['--', 'FU', 'HZ', 'BR', 'FG', 'SS']:
                    but_lluvia.configure(text="On", fg="red", relief=SUNKEN)
                    but_niebla.configure(text="Off", fg="black", relief=RAISED)
                    radBtn1.configure(state=NORMAL)
                    radBtn2.configure(state=NORMAL)
                    radBtn3.configure(state=NORMAL)
                    radBtn4.configure(state=DISABLED)
                    radBtn5.configure(state=DISABLED)
                    radBtn6.configure(state=DISABLED)
                    radBtn7.configure(state=DISABLED)
                    rs.set(1)
                    fs.set(0)
                    master.metar = master.metar.replace(valActual, 'DZ')
                    master.metar = master.metar.replace(visibilidad, '4000')
                    master.metar = master.metar.replace(qnh, 'Q1000')

                elif valActual in ['--', 'DZ', 'RA', 'SN']:
                    but_lluvia.configure(text="Off", fg="black", relief=RAISED)
                    but_niebla.configure(text="Off", fg="black", relief=RAISED)
                    radBtn1.configure(state=DISABLED)
                    radBtn2.configure(state=DISABLED)
                    radBtn3.configure(state=DISABLED)
                    rs.set(0)
                    master.metar = master.metar.replace(valActual, '--')
                    master.metar = master.metar.replace(visibilidad, 'CAVOK')
                    master.metar = master.metar.replace(qnh, 'Q1013')

                master.metar = master.metar.replace(HoraCambio, HoraActual)
                meteo = master.metar
                print(master.metar)
                master.sendMessage({"message": "rain", "meteo": meteo})

            def niebla():

                patronQNH = re.compile('Q[0-9]{3,4}')
                findQNH = patronQNH.search(master.metar)
                qnh = findQNH.group()
                valActual = master.metar.split()[4]
                visibilidad = master.metar.split()[3]

                HoraCambio = master.metar.split()[1]
                HoraActual = str('0%1s' % master.t.day if len(str(master.t.day)) < 2 else master.t.day) + str(
                    '0%1s' % master.t.hour if len(str(master.t.hour)) < 2 else master.t.hour) \
                             + str('0%1s' % master.t.minute if len(str(master.t.minute)) < 2 else master.t.minute) + 'Z'

                if valActual in ['--', 'DZ', 'RA', 'SN']:
                    but_lluvia.configure(text="Off", fg="black", relief=RAISED)
                    but_niebla.configure(text="On", fg="red", relief=SUNKEN)
                    radBtn1.configure(state=DISABLED)
                    radBtn2.configure(state=DISABLED)
                    radBtn3.configure(state=DISABLED)
                    radBtn4.configure(state=NORMAL)
                    radBtn5.configure(state=NORMAL)
                    radBtn6.configure(state=NORMAL)
                    radBtn7.configure(state=NORMAL)
                    fs.set(1)
                    rs.set(0)
                    master.metar = master.metar.replace(valActual, 'HZ')
                    master.metar = master.metar.replace(visibilidad, '4000')
                    master.metar = master.metar.replace(qnh, 'Q1013')

                elif valActual in ['--', 'FU', 'HZ', 'BR', 'FG', 'SS']:
                    but_lluvia.configure(text="Off", relief=RAISED, fg="black")
                    but_niebla.configure(text="Off", relief=RAISED, fg="black")
                    radBtn4.configure(state=DISABLED)
                    radBtn5.configure(state=DISABLED)
                    radBtn6.configure(state=DISABLED)
                    radBtn7.configure(state=DISABLED)
                    fs.set(0)
                    master.metar = master.metar.replace(valActual, '--')
                    master.metar = master.metar.replace(visibilidad, 'CAVOK')
                    master.metar = master.metar.replace(qnh, 'Q1013')

                master.metar = master.metar.replace(HoraCambio, HoraActual)
                meteo = master.metar
                print(master.metar)
                master.sendMessage({"message": "fog", "meteo": meteo})

            def rainSetting():
                selection = "You selected the option " + str(rs.get())
                print(selection)

                patronQNH = re.compile('Q[0-9]{3,4}')
                findQNH = patronQNH.search(master.metar)
                qnh = findQNH.group()
                varActual = master.metar.split()[4]
                visibilidad = master.metar.split()[3]

                HoraCambio = master.metar.split()[1]
                HoraActual = str('0%1s' % master.t.day if len(str(master.t.day)) < 2 else master.t.day) + str(
                    '0%1s' % master.t.hour if len(str(master.t.hour)) < 2 else master.t.hour) \
                             + str('0%1s' % master.t.minute if len(str(master.t.minute)) < 2 else master.t.minute) + 'Z'

                if rs.get() == 1:
                    master.metar = master.metar.replace(varActual, 'DZ')
                    master.metar = master.metar.replace(visibilidad, '4000')
                    master.metar = master.metar.replace(qnh, 'Q1000')
                elif rs.get() == 2:
                    master.metar = master.metar.replace(varActual, 'RA')
                    master.metar = master.metar.replace(visibilidad, '2000')
                    master.metar = master.metar.replace(qnh, 'Q1000')
                elif rs.get() == 3:
                    master.metar = master.metar.replace(varActual, 'SN')
                    master.metar = master.metar.replace(visibilidad, '2000')
                    master.metar = master.metar.replace(qnh, 'Q1000')

                master.metar = master.metar.replace(HoraCambio, HoraActual)
                meteo = master.metar
                print(master.metar)
                master.sendMessage({"message": "rain", "meteo": meteo})

            def fogSetting():
                selection = "You selected the option " + str(fs.get())
                print(selection)

                patronQNH = re.compile('Q[0-9]{3,4}')
                findQNH = patronQNH.search(master.metar)
                qnh = findQNH.group()
                varActual = master.metar.split()[4]
                visibilidad = master.metar.split()[3]

                HoraCambio = master.metar.split()[1]
                HoraActual = str('0%1s' % master.t.day if len(str(master.t.day)) < 2 else master.t.day) + str(
                    '0%1s' % master.t.hour if len(str(master.t.hour)) < 2 else master.t.hour) \
                             + str('0%1s' % master.t.minute if len(str(master.t.minute)) < 2 else master.t.minute) + 'Z'

                if fs.get() == 1:
                    master.metar = master.metar.replace(varActual, 'HZ')
                    master.metar = master.metar.replace(visibilidad, '4000')
                    master.metar = master.metar.replace(qnh, 'Q1013')
                elif fs.get() == 2:
                    master.metar = master.metar.replace(varActual, 'BR')
                    master.metar = master.metar.replace(visibilidad, '2000')
                    master.metar = master.metar.replace(qnh, 'Q1013')
                elif fs.get() == 3:
                    master.metar = master.metar.replace(varActual, 'FG')
                    master.metar = master.metar.replace(visibilidad, '0500')
                    master.metar = master.metar.replace(qnh, 'Q1013')
                else:
                    master.metar = master.metar.replace(varActual, 'SS')
                    master.metar = master.metar.replace(visibilidad, '0500')
                    master.metar = master.metar.replace(qnh, 'Q1013')

                master.metar = master.metar.replace(HoraCambio, HoraActual)
                meteo = master.metar
                print(master.metar)
                master.sendMessage({"message": "fog", "meteo": meteo})


            root = tix.Toplevel()
            root.title("Meteo VisualGamma")
            img_dir = os.path.join(conf.common_dir, 'img')
            ico_file = os.path.join(img_dir, 'GAMMASIM.ico')
            root.iconbitmap(ico_file)
            x = self.but_meteo.winfo_rootx()+120
            y = self.but_meteo.winfo_rooty()-120
            root.geometry("+%d+%d" % (x, y))
            frameMeteo = tix.Frame(root)
            frameMeteo.grid(column=0, row=0)
            frameMeteo.columnconfigure(0, weight=1)
            frameMeteo.rowconfigure(0, weight=1)

            rainLabel = tix.Label(frameMeteo, text="Precipitación")
            rainLabel.grid(column=1, row=1, padx=(10, 10), pady=(10, 10), sticky="e")
            but_lluvia = tix.Button(frameMeteo, command=lluvia)
            but_lluvia.grid(column=2, row=1)

            rs = IntVar()
            radBtn1 = Radiobutton(frameMeteo, text="DZ", value=1, variable=rs, state=DISABLED, command=rainSetting)
            radBtn1.grid(column=3, row=1, padx=(10, 10), pady=(10, 10), sticky="w")
            radBtn2 = Radiobutton(frameMeteo, text="RA", value=2, variable=rs, state=DISABLED, command=rainSetting)
            radBtn2.grid(column=4, row=1, sticky="w")
            radBtn3 = Radiobutton(frameMeteo, text="SN", value=3, variable=rs, state=DISABLED, command=rainSetting)
            radBtn3.grid(column=5, row=1)

            fogLabel = tix.Label(frameMeteo, text="Visibilidad")
            fogLabel.grid(column=1, row=2, padx=(10, 10), pady=(10, 10), sticky="e")
            but_niebla = tix.Button(frameMeteo, command=niebla)
            but_niebla.grid(column=2, row=2)

            fs = IntVar()
            radBtn4 = Radiobutton(frameMeteo, text="HZ/FU", value=1, variable=fs, state=DISABLED, command=fogSetting)
            radBtn4.grid(column=3, row=2, padx=(10, 10), pady=(10, 10), sticky="w")
            radBtn5 = Radiobutton(frameMeteo, text="BR", value=2, variable=fs, state=DISABLED, command=fogSetting)
            radBtn5.grid(column=4, row=2, sticky="w")
            radBtn6 = Radiobutton(frameMeteo, text="FG", value=3, variable=fs, state=DISABLED, command=fogSetting)
            radBtn6.grid(column=5, row=2, padx=(10, 10), pady=(10, 10), sticky="w")
            radBtn7 = Radiobutton(frameMeteo, text="SS", value=4, variable=fs, state=DISABLED, command=fogSetting)
            radBtn7.grid(column=6, row=2, padx=(10, 10), pady=(10, 10), sticky="w")

            # Set actual meteo settings from Visual_Cesium meteo line
            if varActualmeteo == "":
                but_lluvia.configure(text="Off", fg="black", relief=RAISED)
                but_niebla.configure(text="Off", fg="black", relief=RAISED)
                radBtn1.configure(state=DISABLED)
                radBtn2.configure(state=DISABLED)
                radBtn3.configure(state=DISABLED)
                radBtn4.configure(state=DISABLED)
                radBtn5.configure(state=DISABLED)
                radBtn6.configure(state=DISABLED)
                radBtn7.configure(state=DISABLED)
            elif varActualmeteo in ["DZ","RA","SN"]:
                but_lluvia.configure(text="On", fg="red", relief=SUNKEN)
                but_niebla.configure(text="Off", fg="black", relief=RAISED)
                radBtn1.configure(state=NORMAL)
                radBtn2.configure(state=NORMAL)
                radBtn3.configure(state=NORMAL)
                radBtn4.configure(state=DISABLED)
                radBtn5.configure(state=DISABLED)
                radBtn6.configure(state=DISABLED)
                radBtn7.configure(state=DISABLED)
                if varActualmeteo == "DZ":
                    rs.set(1)
                elif varActualmeteo == "RA":
                    rs.set(2)
                elif varActualmeteo == "SN":
                    rs.set(3)

            elif varActualmeteo in ['FU', 'HZ', 'BR', 'FG', 'SS']:
                but_lluvia.configure(text="Off", fg="black", relief=RAISED)
                but_niebla.configure(text="On", fg="red", relief=SUNKEN)
                radBtn1.configure(state=DISABLED)
                radBtn2.configure(state=DISABLED)
                radBtn3.configure(state=DISABLED)
                radBtn4.configure(state=NORMAL)
                radBtn5.configure(state=NORMAL)
                radBtn6.configure(state=NORMAL)
                radBtn7.configure(state=NORMAL)
                if varActualmeteo in ['FU', 'HZ']:
                    fs.set(1)
                elif varActualmeteo == 'BR':
                    fs.set(2)
                elif varActualmeteo == 'FG':
                    fs.set(3)
                elif varActualmeteo == 'SS':
                    fs.set(4)

        def b_rwy_change():
            # TODO THIS IS PROBABLY NOT WORKING!!
            # Needs to be retested and probably rethought
            self.close_windows()
            # Find airports with several runways
            ad_list = []
            for ad in master.fir.aerodromes.values():
                if len(ad.rwy_direction_list) > 1:
                    ad_list.append(ad)

            if len(ad_list) == 0:
                RaDialog(w, label='Cambio de pista', text='No hay aeropuertos con más de una pista IFR')
                return
            
            def close_rwy_chg(e=None, entries=None):
                ads_rwyinuse = {}
                for ad in ad_list:
                    ads_rwyinuse[ad.code_id]=entries[ad.code_id]['value']

                master.sendMessage({"message": "rwy_in_use", "ad": ads_rwyinuse})
            
            entries = []
            for ad in ad_list:
                entries.append({'label': ad.code_id,
                            'values': [rwy.txt_desig for rwy in ad.rwy_direction_list if 'H' not in rwy.txt_desig],
                            'def_value': ad.rwy_in_use.txt_desig})
            RaDialog(w, label='Cambiar pistas en uso', ok_callback=close_rwy_chg, entries=entries)
            
        def b_auth_approach():
            self.close_windows()
            if (get_selected('Autorizar a Aproximación')==None):
                return
            sel = master._tracks_flights[master.selected_track]
            if master.fir.AdHasIfrRwys(sel.ades):
                ad = master.fir.aerodromes[sel.ades]
            elif master.fir.AdHasIfrRwys(sel.adep):
                ad = master.fir.aerodromes[sel.adep]
                RaDialog(w, label=sel.callsign+': Autorizar a aproximación',
                        text='Aeropuertos de destino sin procedimientos de APP. Utilizando aeropuerto de origen')
            else:
                RaDialog(w, label=sel.callsign+': Autorizar a aproximación',
                        text='Aeropuertos de destino y origen sin procedimientos de APP')
                return

            def auth_app(e=None, avo=sel, entries=None):
                master.sendMessage({"message":"execute_app", "cs": sel.callsign,
                                    "ades": entries['Destino:'].get().upper(),
                                    "iaf": entries['IAF:']['value']})
            # Build entries
            # TODO We should be able of cleanly finding what's the current IAF
            iaf = ''
            # Get all iafs for wry in use
            iaps = ad.rwy_in_use.iaps.keys()
            # Get all iafs for rest of rwys
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig != ad.rwy_in_use.txt_desig:
                    iaps = iaps + rwy.iaps.keys()
            # Find a potential iaf
            for i in range(0, len(sel.route)):
                if sel.route[i-1].fix == sel.iaf:
                    iaf = sel.route[i-1].fix
                    break
            if iaf == '':
                for i in range(0, len(sel.route)):
                    if sel.route[i-1].fix in ad.rwy_in_use.iaps.keys():
                        iaf = sel.iaf = sel.route[i-1].fix
                        break
            if iaf == '':
                for i in range(0, len(sel.route)):
                    if sel.route[i-1].fix in iaps:
                        iaf = sel.iaf = sel.route[i-1].fix
                        break
            if iaf == '':
                iaf = sel.iaf
            entries = []
            entries.append({'label': 'Destino:', 'width': 4, 'def_value':ad.code_id})
            entries.append({'label': 'IAF:', 'width': 5, 'values': iaps, 'def_value': iaf})
            RaDialog(w, label=sel.callsign+': Autorizar a Aproximación',
                     ok_callback=auth_app, entries=entries)      

        ventana = tix.Frame(w, bg='gray', width=ancho)
        grid_column = 0
        self.but_restart = tix.Button(ventana, text="RESET " + u"\u21BA", command=b_reinicio)
        self.but_restart.grid(row=0, column=grid_column)
        grid_column += 1
        self.but_inicio = tix.Button(ventana,bitmap='@'+IMGDIR+'start.xbm', command=b_inicio)
        # self.but_inicio.pack(side=tix.LEFT,expand=1,fill=X)
        self.but_inicio.grid(row=0, column=grid_column)
        self.but_parar = tix.Button(ventana, bitmap='@'+IMGDIR+'pause.xbm', command=b_parar)
        # self.but_parar.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_parar.grid(row=0, column=grid_column)

        self.but_orient = tix.Button(ventana, text='ORIENT')
        grid_column += 1
        self.but_orient.grid(row=0, column=grid_column)
        # self.but_orient.pack(side=tix.LEFT,expand=1,fill=X)

        def orient_buttons():
            self.close_windows()
            ventana_orient = tix.Frame(w, bg='gray')
            self.but_north = tix.Button(ventana_orient, text='NORTH', command=b_north)
            self.but_north.grid(column=0, row=0, sticky=tix.E+tix.W)
            self.but_field = tix.Button(ventana_orient, text='FIELD', command=b_field)
            self.but_field.grid(column=0, row=1, sticky=tix.E+tix.W)
            i = w.create_window(ventana.winfo_x()+self.but_orient.winfo_x(), alto-ventana.winfo_height(), window=ventana_orient, anchor='sw')
            self.opened_windows.append(i)
        self.but_orient['command'] = orient_buttons

        def b_north(e=None):
            self.close_windows()
            master.orient = 'NORTH'
            master.refresco = 5.
            master.reposition()

        def b_field(e=None):
            self.close_windows()
            master.orient = 'FIELD'
            master.refresco = 1.
            master.reposition()

        def elev_airp():
            """Show a dialog to view details of the selected flight"""
            self.close_windows()
            airports = []
            fl = []
            for airport in self.master.fir.aerodromes:

                airports.append(airport)
                fl.append(str("%.2f" % round(self.master.fir.aerodromes[airport].val_elev, 2)))


            cob_inf = self.master.fir.cob_radar_inf
            cob_text = '\nCob. Radar: %.2f' % cob_inf if cob_inf > 0 else ''
            # TODO The RaDialog should probably export the contents frame
            # and we could use it here to build the contents using a proper grid
            RaDialog(w, label='Elevaciones', text='Aeropuerto: ' + ' '.join(airports) +
                                                              '       \nElev. :  ' + '  '.join(fl) + cob_text)


        self.but_izq = tix.Button(ventana, bitmap='@'+IMGDIR+'left.xbm')
        # self.but_izq.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_izq.grid(row=0, column=grid_column)
        self.but_izq.bind("<Button-1>", b_izquierda)
        self.but_izq.bind("<Button-2>", b_izquierda)
        self.but_izq.bind("<Button-3>", b_izquierda)

        self.but_arriba = tix.Button(ventana, bitmap='@'+IMGDIR+'up.xbm')
        # self.but_arriba.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_arriba.grid(row=0, column=grid_column)
        self.but_arriba.bind("<Button-1>", b_arriba)
        self.but_arriba.bind("<Button-2>", b_arriba)
        self.but_arriba.bind("<Button-3>", b_arriba)
        
        self.but_abajo = tix.Button(ventana, bitmap='@'+IMGDIR+'down.xbm')
        # self.but_abajo.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_abajo.grid(row=0, column=grid_column)
        self.but_abajo.bind("<Button-1>", b_abajo)
        self.but_abajo.bind("<Button-2>", b_abajo)
        self.but_abajo.bind("<Button-3>", b_abajo)
    
        self.but_derecha = tix.Button(ventana, bitmap='@'+IMGDIR+'right.xbm')
        # self.but_derecha.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_derecha.grid(row=0,column=grid_column)
        self.but_derecha.bind("<Button-1>", b_derecha)
        self.but_derecha.bind("<Button-2>", b_derecha)
        self.but_derecha.bind("<Button-3>", b_derecha)
        
        # self.but_zoom_mas = tix.Button(ventana,bitmap='@'+IMGDIR+'zoom.xbm',command=b_zoom_mas)
        self.but_zoom_mas = tix.Button(ventana, bitmap='@'+IMGDIR+'zoom.xbm')
        # self.but_zoom_mas.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_zoom_mas.grid(row=0, column=grid_column)
        self.but_zoom_mas.bind("<Button-1>", b_zoom_mas)
        self.but_zoom_mas.bind("<Button-2>", b_zoom_mas)
        self.but_zoom_mas.bind("<Button-3>", b_zoom_mas)

        
        # self.but_zoom_menos = tix.Button(ventana,bitmap='@'+IMGDIR+'unzoom.xbm',command=b_zoom_menos)
        self.but_zoom_menos = tix.Button(ventana, bitmap='@'+IMGDIR+'unzoom.xbm')
        # self.but_zoom_menos.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_zoom_menos.grid(row=0,column=grid_column)
        self.but_zoom_menos.bind("<Button-1>", b_zoom_menos)
        self.but_zoom_menos.bind("<Button-2>", b_zoom_menos)
        self.but_zoom_menos.bind("<Button-3>", b_zoom_menos)
        
        self.but_standard = tix.Button(ventana, bitmap='@'+IMGDIR+'center.xbm', command=b_standard)
        # self.but_standard.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_standard.grid(row=0, column=grid_column)

        self.but_tamano_etiq = tix.Button(ventana, bitmap='@'+IMGDIR+'labelsize.xbm')
        # self.but_tamano_etiq.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_tamano_etiq.grid(row=0,column=grid_column)
        self.but_tamano_etiq.bind("<Button-1>", b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-2>", b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-3>", b_tamano_fichas)
        
        self.but_term = tix.Button(ventana, text='Kill', command=kill_acft)
        # self.but_term.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_term.grid(row=0, column=grid_column)

        self.but_ruta = tix.Button(ventana, text='Ruta', command=nueva_ruta)
        #self.but_ruta.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_ruta.grid(row=0, column=grid_column)

        self.but_datos = tix.Button(ventana, text='Datos', command=ver_detalles)
        # self.but_datos.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_datos.grid(row=0, column=grid_column)

        self.but_quitar_lads = tix.Button(ventana, text='LADs', fg = 'red', command=self.master.delete_lads)
        # self.but_quitar_lads.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_quitar_lads.grid(row=0, column=grid_column)

        self.but_quitar_fpr = tix.Button(ventana, text='Rutas', fg='red', command=self.master.delete_routes)
        # self.but_quitar_fpr.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_quitar_fpr.grid(row=0, column=grid_column)

        # self.but_quitar_tormentas = tix.Button(ventana,text='TS', fg = 'red',command = self.master.quitar_tormentas)
        # self.but_quitar_tormentas.pack(side=tix.LEFT,expand=1,fill=X)
        self.but_ver_proc = tix.Button(ventana, text='PROCs')
        # self.but_ver_proc.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_ver_proc.grid(row=0, column=grid_column)

        def procs_buttons():
            self.close_windows()
            ventana_procs = tix.Frame(w, bg='gray')
            # self.but_espera = tix.Button(ventana_procs, text='Esperas', command = define_holding)
            # self.but_espera.grid(column=0,row=0,sticky=tix.E+tix.W)
            # self.but_hdg_fix = tix.Button(ventana_procs, text = 'HDG despues fijo', command = hdg_after_fix)
            # self.but_hdg_fix.grid(column=0,row=1,sticky=tix.E+tix.W)
            # self.but_int_rdl = tix.Button(ventana_procs, text = 'Int. RDL', command = int_rdl)
            # self.but_int_rdl.grid(column=0,row=2,sticky=tix.E+tix.W)
            self.but_chg_rwy = tix.Button(ventana_procs, text='Cambio RWY', command=b_rwy_change)
            self.but_chg_rwy.grid(column=0, row=0, sticky=tix.E+tix.W)
            # self.but_orbit = tix.Button(ventana_procs, text = 'Orbitar aquí', command = b_orbitar)
            # self.but_orbit.grid(column=0,row=4,sticky=tix.E+tix.W)
            self.but_wind = tix.Button(ventana_procs, text='Cambiar viento', command=cambiar_viento)
            self.but_wind.grid(column=0, row=1, sticky=tix.E+tix.W)
            self.but_meteo = tix.Button(ventana_procs, text='Meteo Visual', command=meteo_visual)
            self.but_meteo.grid(column=0, row=2, sticky=tix.E+tix.W)
            i = w.create_window(ventana.winfo_x()+self.but_ver_proc.winfo_x(), alto-ventana.winfo_height(), window=ventana_procs, anchor='sw')
            self.opened_windows.append(i)

        self.but_ver_proc['command'] = procs_buttons
        ############## QUITO EL BOTÓN 'APP' DE LA VENTANA DE CONTROLADOR Y TRANSFIERO LAS ACCIONES AL CALLSIGN DE LA ETIQUETA
        # self.but_ver_app = tix.Button(ventana, text = 'APP')
        # self.but_ver_app.pack(side=tix.LEFT,expand=1,fill=X)
        # grid_column+=1
        # self.but_ver_app.grid(row=0,column=grid_column)

        # def maps_buttons():
        #    self.close_windows()
        #    ventana_maps = tix.Frame(w,bg='gray')
        #    self.but_app_proc = tix.Button(ventana_maps, text = 'APP PROC.', command = b_auth_approach)
        #    self.but_app_proc.grid(column=0,row=0,sticky=tix.E+tix.W)
        #    self.but_ils_vec = tix.Button(ventana_maps, text = 'ILS (vectores)', command = b_int_ils)
        #    self.but_ils_vec.grid(column=0,row=1,sticky=tix.E+tix.W)
        #    self.but_exe_map = tix.Button(ventana_maps, text = 'PASADA BAJA', command = b_execute_lowpass)
        #    self.but_exe_map.grid(column=0,row=3,sticky=tix.E+tix.W)
        #    self.but_exe_lowpass = tix.Button(ventana_maps, text = 'EJECUTAR MAP', command = b_execute_map)
        #    self.but_exe_lowpass.grid(column=0,row=4,sticky=tix.E+tix.W)
        #    i=w.create_window(ventana.winfo_x()+self.but_ver_app.winfo_x(),alto-ventana.winfo_height(),window=ventana_maps,anchor='sw')
        #    self.opened_windows.append(i)
        # self.but_ver_app['command'] = maps_buttons

        self.but_auto_separation = tix.Checkbutton(ventana, text='SEP', variable=self.auto_sep, command=lambda: master.toggle_auto_separation())
        # self.but_auto_separation.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_auto_separation.grid(row=0, column=grid_column)

        self.but_bri = tix.Button(ventana, text='BRI', command=master.rabrightness.conmuta)
        # self.but_bri.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_bri.grid(row=0, column=grid_column)

        self.but_ver_maps = tix.Button(ventana, text='MAPAS')
        # self.but_ver_maps.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_ver_maps.grid(row=0, column=grid_column)

        def mapas_buttons():
            self.close_windows()
            ventana_mapas = tix.Frame(w)
            myrow = 0
            self.but_ver_nombrs_ptos = tix.Checkbutton(ventana_mapas, text='Nombres Fijos', variable=self.vfn, command=self.master.toggle_point_names)
            self.but_ver_nombrs_ptos.grid(column=0, row=myrow, sticky=tix.W)
            myrow += 1
            self.but_ver_ptos = tix.Checkbutton(ventana_mapas, text='Fijos', variable=self.vf, command=self.master.toggle_point)
            self.but_ver_ptos.grid(column=0, row=myrow, sticky=tix.W)
            myrow += 1
            # self.but_ver_routes = tix.Checkbutton(ventana_mapas, text = 'Aerovias', variable=self.vr, command=self.master.toggle_routes)
            # self.but_ver_routes.grid(column=0,row=myrow,sticky=tix.W)
            # myrow+= 1
            self.but_ver_sector = tix.Checkbutton(ventana_mapas, text='Sector', variable=self.vs, command=self.master.toggle_sector)
            self.but_ver_sector.grid(column=0, row=myrow, sticky=tix.W)
            myrow += 1
            self.but_ver_lim_sector = tix.Checkbutton(ventana_mapas, text='Lim. Sector', variable=self.vsl, command=self.master.toggle_lim_sector)
            self.but_ver_lim_sector.grid(column=0, row=myrow, sticky=tix.W)
            myrow += 1
            # self.but_ver_tmas = tix.Checkbutton(ventana_mapas, text = 'TMAs',  variable=self.vt, command=self.master.toggle_tmas)
            # self.but_ver_tmas.grid(column=0,row=myrow,sticky=tix.W)
            # myrow+= 1
            # self.but_ver_deltas = tix.Checkbutton(ventana_mapas, text = 'Deltas', variable=self.vd, command=self.master.toggle_deltas)
            # self.but_ver_deltas.grid(column=0,row=myrow,sticky=tix.W)
            # myrow += 1
            map_name_list = master.fir.local_maps.keys()
            map_name_list.sort()

            mycolumn = 0
            for map_name in self.master.fir.local_maps_order:  # map_name_list:
                self.but_ver_local_map = tix.Checkbutton(ventana_mapas, text=map_name, variable=self.var_ver_localmap[map_name], command=self.b_show_hide_localmaps)
                self.but_ver_local_map.grid(column=mycolumn, row=myrow, sticky=tix.W)
                if myrow > 10:
                    mycolumn += 1
                    myrow = 0
                else:
                    myrow += 1

            i = w.create_window(ventana.winfo_x()+self.but_ver_maps.winfo_x(), alto-ventana.winfo_height(), window=ventana_mapas, anchor='sw')
            self.opened_windows.append(i)
        self.but_ver_maps['command'] = mapas_buttons

        self.but_ver_tabs = tix.Button(ventana, text='TABs')
        # self.but_ver_tabs.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        self.but_ver_tabs.grid(row=0, column=grid_column)

        def tabs_buttons():
            self.close_windows()
            ventana_tabs = tix.Frame(w)
            # self.but_reports = tix.Button(ventana_tabs, text='Notificaciones', command = acftnotices.show, state=DISABLED)
            # self.but_reports.grid(column=0,row=0,sticky=tix.E+tix.W)
            self.var_ver_desp_tab.set(master.dep_tabular.showed)
            self.var_ver_act_tab.set(master.act_tabular.showed)
            self.var_ver_arr_tab.set(master.arr_tabular.showed)
            self.var_ver_windrose.set(master.windrose.showed)
            self.but_departures = tix.Checkbutton(ventana_tabs, text='Despegues', variable=self.var_ver_desp_tab,
                                 command=master.dep_tabular.conmuta)
            self.but_departures.grid(column=0, row=1, sticky=tix.W)
            self.but_active = tix.Checkbutton(ventana_tabs, text='Activos', variable=self.var_ver_act_tab,
                                 command=master.act_tabular.conmuta)
            self.but_active.grid(column=0, row=2, sticky=tix.W)
            #
            self.but_arrivals = tix.Checkbutton(ventana_tabs, text='Llegadas', variable=self.var_ver_arr_tab,
                                 command=master.arr_tabular.conmuta)
            self.but_arrivals.grid(column=0, row=3, sticky=tix.W)

            self.but_windrose = tix.Checkbutton(ventana_tabs, text='Anemómetro', variable=self.var_ver_windrose,
                                                command=master.windrose.conmuta)
            self.but_windrose.grid(column=0, row=4, sticky=tix.W)
            i = w.create_window(ventana.winfo_x()+self.but_ver_tabs.winfo_x(), alto-ventana.winfo_height(), window=ventana_tabs, anchor='sw')
            self.opened_windows.append(i)
        self.but_ver_tabs['command'] = tabs_buttons

        def cambia_vect_vel(e=None):
            self.close_windows()
            master.change_speed_vector(self.speed_vector_var.get()/60.)
        cnt_vect_vel = tix.Control(ventana, label="Vel:", min=0, max=5, integer=1, command=cambia_vect_vel, variable=self.speed_vector_var)
        # cnt_vect_vel.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        cnt_vect_vel.grid(row=0, column=grid_column)

        def cambia_vel_reloj(e=None):
            self.close_windows()
            try:
                master.sendMessage({"message":"clock_speed",
                                    "data": float(master.clock_speed_var.get())})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send clock_speed command", exc_info=True)
        cnt_vel_reloj = tix.Control(ventana, label="Reloj X:", min=0.5, max=99.0, step=0.1, command=cambia_vel_reloj, variable=master.clock_speed_var)
        # cnt_vel_reloj.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column += 1
        cnt_vel_reloj.grid(row=0, column=grid_column)

        def toggle_radar_off(e=None):
            self.close_windows()
            try:
                master.sendMessage({"message":"radar_off", "data": self.master.radar_off_var.get()})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send radar_off command", exc_info=True)
        but_radar_off = tix.Checkbutton(ventana, text='RADAR OFF', command=toggle_radar_off, variable=self.master.radar_off_var)
        grid_column += 1
        but_radar_off.grid(row=0, column=grid_column)

        def toggle_correlar_off(e=None):
            self.close_windows()
            try:
                master.sendMessage({"message": "correlar_off", "data": self.master.correlar_off_var.get()})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send correlar_off command", exc_info=True)
        but_correlar_off = tix.Checkbutton(ventana, text='CORRELAR OFF', command=toggle_correlar_off, variable=self.master.correlar_off_var)
        grid_column += 1
        but_correlar_off.grid(row=0, column=grid_column)

        but_l2_onoff = tix.Checkbutton(ventana, text='L2', command=self.master.reformat_labels, variable=self.master.l2_onoff_var)
        grid_column += 1
        but_l2_onoff.grid(row=0, column=grid_column)

        but_l3_onoff = tix.Checkbutton(ventana, text='L3', command=self.master.reformat_labels, variable=self.master.l3_onoff_var)
        grid_column += 1
        but_l3_onoff.grid(row=0, column=grid_column)

        but_l4_onoff = tix.Checkbutton(ventana, text='L4', command=self.master.reformat_labels, variable=self.master.l4_onoff_var)
        grid_column += 1
        but_l4_onoff.grid(row=0, column=grid_column)

        but_l5_onoff = tix.Checkbutton(ventana, text='L5', command=self.master.reformat_labels, variable=self.master.l5_onoff_var)
        grid_column += 1
        but_l5_onoff.grid(row=0, column=grid_column)

        self.toolbar_id = w.create_window(0, alto, width=ancho, window=ventana, anchor='sw')
        ventana.update_idletasks()

        # INCLUIR ETIQUETA FALT PARA DETERMINAR UN MINIMO Y UN MAXIMO DE ALTITUD
        # Minimo
        # def selecciona_FALTmin (e=None):
        #    master.select_FALT_varmin=self.select_FALT_varmin.get()
        # faltmin = tix.Control(ventana, label='FALT:', min=0, max=990, step=10, command=selecciona_FALTmin, variable=self.select_FALT_varmin)
        faltmin = tix.Control(ventana, label='FALT:', min=0, max=990, step=10, variable=self.master.select_FALT_varmin)
        grid_column += 1
        faltmin.grid(row=0, column=grid_column)
        # Maximo
        # def selecciona_FALTmax (e=None):
        #    master.select_FALT_varmax=self.select_FALT_varmax.get()
        #    #master.change_FALTmax(self.select_FALT_varmax.get())
        # faltmax = tix.Control(ventana, label='', min=0, max=990, step=10, command=selecciona_FALTmax, variable=self.select_FALT_varmax)
        faltmax = tix.Control(ventana, label='', min=0, max=990, step=10, variable=self.master.select_FALT_varmax)
        grid_column += 1
        faltmax.grid(row=0, column=grid_column)

        self.but_elev_airp = tix.Button(ventana, text='Elevaciones', command=elev_airp)
        grid_column += 1
        self.but_elev_airp.grid(row=0, column=grid_column)

        def toggle_mouse_wheel(e=None):
            self.close_windows()

        but_mouse_wheel = tix.Checkbutton(ventana, text='WheelMouse', variable=self.master.mouse_wheel_enabled_var, command=toggle_mouse_wheel)
        grid_column += 1
        but_mouse_wheel.grid(row=0, column=grid_column)

        def toggle_grab_display(e=None):
            self.close_windows()

        but_grab_display = tix.Checkbutton(ventana, text='GrabDisplay', variable=self.master.grab_display_enabled_var, command=toggle_grab_display)
        grid_column += 1
        but_grab_display.grid(row=0, column=grid_column)

        '''ventana2=tix.Frame(w,bg='gray',width=ancho)
        self.but_inicio = tix.Button(ventana2,bitmap='@'+IMGDIR+'start.xbm',command=b_inicio)
        self.but_inicio.pack(side=tix.LEFT,expand=1,fill=X)
        self.but_parar = tix.Button(ventana2,bitmap='@'+IMGDIR+'pause.xbm',command=b_parar)
        self.but_parar.pack(side=tix.LEFT,expand=1,fill=X)
        self.toolbar2_id=w.create_window(0,alto-30,width=ancho,window=ventana2,anchor='sw')
        ventana2.update_idletasks()'''

class AcftNotices(RaTabular):
    """A tabular window showing reports and requests from aircraft"""
    def __init__(self, master=None, flights=None):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, master, label='Notificaciones',
                           position=(120, 200), closebuttonhides=True)
        self._last_updated = 0.
        self._flights = flights
        
    def update(self, t):
        """Check whether any new message should be printed"""
        # We need only update this tabular at most once a second
        if t-self._last_updated < 1/60./60.:
            return
            
        # Check whether the pilots have anything to report.
        for acft in self._flights:
            for i, report in enumerate(acft.reports):
                if t > report['time']:
                    h = int(t)
                    m = int(60*(t-h))
                    report = '%02d:%02d %s %s' % (h, m, acft.callsign, report['text'])
                    self.insert(tix.END, report)
                    self.notify()
                    del acft.reports[i]
        self._last_updated = t

    def notify(self):
        """Make it obvious to the user that there has been a new notification"""
        import sys
        if sys.platform == 'win32':
            import winsound
            try:
                winsound.PlaySound(SNDDIR+'/chime.wav', winsound.SND_NOSTOP | winsound.SND_ASYNC)
            except:
                pass


class PPGeneralInformationWindow(GeneralInformationWindow):
    """A window containing generic information related to the position"""
    def __init__(self, radisplay, sectors, activesectors, **kw):
        """GeneralInformationWindow tailored for Pseudopilots displays"""
        GeneralInformationWindow.__init__(self, radisplay, sectors, activesectors, **kw)
        
        self.qnh_b['command'] = self.modify_qnh
        
    def modify_qnh(self):
        def dialog_cb(entries):
            error = False
            ent_qnh = entries['QNH:']
            ent_dir = entries['Sube(S)/Baja(B):']
            try:
                self.qnh = float(ent_qnh.get())
            except:
                ent_qnh['bg'] = 'red'
                ent_qnh.focus_set()
                error = True
            dir = ent_dir.get()
            if dir.upper() not in ('S', 'B', ''):
                ent_dir['bg'] = 'red'
                ent_dir.focus_set()
                error = True
            else:
                if dir.upper() == 'S':
                    dir = +1
                elif dir.upper() == 'B':
                    dir = -1
                else:
                    dir = 0
            if error:
                return False  # Validation failed
            self.radisplay.sendMessage({"message": "qnh",
                                    "qnh": self.qnh,
                                    "dir": dir})
        entries = [{'label': 'QNH:','width': 6, 'def_value': "%.1f"%self.qnh}]
        entries.append({'label': 'Sube(S)/Baja(B):', 'width': 1, 'def_value': ''})
        RaDialog(self.radisplay.c, label='Modificar QNH', entries=entries, ok_callback=dialog_cb)
