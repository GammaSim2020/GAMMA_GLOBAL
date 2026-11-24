#!/usr/bin/python
#-*- coding:iso8859-15 -*-
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
from time import time, sleep
SNDDIR = './snd/'

from RaDisplay import *  # This also imports all RaElements classes
import Aircraft
import Route

class EditDisplay(RaDisplay):
    """Radar display with a pseudopilot interface"""
    
    def __init__(self,conf,title,icon_path,fir,tlpv,sector,e):
        """Instantiate a Pseudopilot Radar Display
        
        title - window title
        icon_path - path to the windows task bar icon
        fir -- fir object
        sector -- name of the sector to work with
        e -- exercise object
        """
        self.conf = conf
        self.toolbar_height = 60  # Pseudopilot display toolbar height
        self._flights_tracks = {}
        self._tracks_flights = {}
        RaDisplay.__init__(self,self.conf,title,icon_path,fir,tlpv,sector,self.toolbar_height,1)
        self.flights = []
        self.killed_flights = []
        self.mode = 'ExeGen'
        t = datetime.datetime.today()
        self.t = t.replace(t.year, t.month, t.day,
						   int(e.start_time[0:2]), int(e.start_time[3:5]), 0, 0)
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

        self.select_FALT_varmin = tk.IntVar()
        self.select_FALT_varmin.set(0)

        self.select_FALT_varmax = tk.IntVar()
        self.select_FALT_varmax.set(990)

            
        self.toolbar = ventana_auxiliar(self)
        
        #To get previous position of clock and tabs
        
        posx = int(self.conf.read_option(self.sector, "PosGIx", "0"))
        posy = int(self.conf.read_option(self.sector, "PosGIy", "0"))
        #self.PosGI = [posx, posy]
        self.PosGI = [0, 0]
        posx = int(self.conf.read_option(self.sector, "PosClockx", "10"))
        posy = int(self.conf.read_option(self.sector, "PosClocky", "50"))
        #self.PosClock = [posx, posy]
        self.PosClock = [1200, 40]
        posx = int(self.conf.read_option(self.sector, "PosTabularx", "10"))
        posy = int(self.conf.read_option(self.sector, "PosTabulary", "120"))
        #self.PosTabular = [posx, posy]
        self.PosTabular = [1000, 0]
        posx = int(self.conf.read_option(self.sector, "PosDepTabularx", "720"))
        posy = int(self.conf.read_option(self.sector, "PosDepTabulary", "580"))
        #self.PosDepTabular = [posx, posy]
        self.PosDepTabular = [240, 0]
        posx = int(self.conf.read_option(self.sector, "PosActTabularx", "720"))
        posy = int(self.conf.read_option(self.sector, "PosActTabulary", "580"))
        #self.PosActTabular = [posx, posy]
        self.PosActTabular = [580, 0]
        posx = int(self.conf.read_option(self.sector, "PosArrTabularx", "720"))
        posy = int(self.conf.read_option(self.sector, "PosArrTabulary", "580"))
        #self.PosArrTabular = [posx, posy]
        self.PosArrTabular = [830, 0]

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

        self.clock=RaClock(self.c,position=self.PosClock)
        self.clock.configure(time='%02d:%02d:%02d' % (self.t.hour, self.t.minute, self.t.second))

        self.windrose=RaWindRose(self.c,position=[110, 180])
        self.windrose.configure(wind_spd='20', wind_dir = 0.0, metar = '')




        self.dep_tabular = DepTabular(self, self.c,position=self.PosDepTabular)
        self.dep_tabular.adjust(0,32,0,0)

        self.act_tabular = ActTabular(self, self.c,position=self.PosActTabular)
        self.act_tabular.adjust(0,32,0,0)

        self.arr_tabular = ArrTabular(self, self.c,position=self.PosArrTabular)
        self.arr_tabular.adjust(0,32,0,0)

        #Get stored values to show/hide the local maps
        for map_name in self.fir.local_maps:
            self.toolbar.var_ver_localmap[map_name].set(self.conf.read_option("Aux_Maps",map_name,False,"bool"))
    
        #Get stored values to show/hide the auxiliary tabs (Departures and Printed Strips)
        dep_tab = self.conf.read_option("Aux_Tabs","Dep_tabular",True,"bool")
        if dep_tab: self.dep_tabular.show()
        else: self.dep_tabular.hide()

        act_tab = self.conf.read_option("Aux_Tabs","Act_tabular",True,"bool")
        if act_tab: self.act_tabular.show()
        else: self.act_tabular.hide()

        arr_tab = self.conf.read_option("Aux_Tabs","Arr_tabular",True,"bool")
        if arr_tab: self.arr_tabular.show()
        else: self.arr_tabular.hide()

        self.center_x = self.width/2
        self.center_y = (self.height-40.)/2
        self.get_scale()
        self.reposition()
        self.toolbar.redraw()
        self.update_tracks()
        self.redraw()
        self.separate_labels()
        
    def process_message(self, m):
        
        def update_flight(new):
            #canvas = self.c
            #canvas.bind_all(self,'<MouseWheel>',self.b_zoom_menos)
            # Check whether this is a new flight
            # JRAR: Sometimes the order of the messages is not right and an update for
            # a traffic arrives after it has been killed. We cope with that to avoid local "resurrection".
            # TODO: JRAR This synchronization problem should be looked into in more detail
            if new.callsign in self.killed_flights: return
            if new.callsign not in [f.callsign for f in self.flights]:
                vt = VisTrack(self,self.vt_handler,self.do_scale,self.undo_scale)
                #Setting mode implicitly configures label
                vt.mode = 'pp'
                vt.l_font_size=self.label_font_size
                self.tracks.append(vt)
                self._flights_tracks[new] = vt
                self._tracks_flights[vt] = new
                self.flights.append(new)
                return new
                    
            else: # Otherwise we are updating
                old = [f for f in self.flights if f.callsign==new.callsign][0]
                for name, value in new.__dict__.items():
                    setattr(old, name, value)
                return old
        
        if m['message']=='time':
            t = m['data']
            self.update_clock(t)
            self.t = t
            if not self.synchronised:
                self.last_update = self.t - datetime.timedelta(seconds=5)
                self.synchronised = True

        if m['message']=='update':
            flights = m['flights']
            for f in flights: update_flight(f)
            # self.write_flightstrips_file()
            self.write_Cesium_file()
            # self.write_CZML_file()
            self.wind = m['wind']
            self.metar = m['metar']
            self.update_wind(self.wind,self.metar)
            self.giw.qnh = m['qnh']
            self.radar_off = m['radar_off']
            self.radar_off_var.set( m['radar_off'])
            self.correlar_off = m['correlar_off']
            self.correlar_off_var.set( m['correlar_off'])
            #JRAR: Why stop separating labels?
            #self.stop_separating = True

            refresco = 1.
            if (self.t-self.last_update).seconds>=refresco:
                self.dep_tabular.update()
                self.act_tabular.update()
                self.arr_tabular.update()
                self.update()
                self.last_update = self.t


        if m['message']=='update_flight':
            f = update_flight(m['flight'])  # Returns the updated flight
            self.update_track(f)
            
        if m['message'] == 'radar_off':
            off = m['off']
            self.radar_off.set(off)

        if m['message'] == 'correlar_off':
            off = m['off']
            self.correlar_off.set(off)

        if m['message'] == 'rwy_in_use':
            ad_code_id, rwy_direction_desig = m['ad'], m['rwy']
            try:
                ad = self.fir.aerodromes[ad_code_id]
                rwy_direction = [rwy for rwy in ad.rwy_direction_list
                                         if rwy.txt_desig == rwy_direction_desig][0]
            except:
                logging.error("No runway direction %s defined for airport %s"%(ad_code_id,rwy_direction_desig),
                              exc_info=True)
            ad.rwy_in_use = rwy_direction            
            
        if m['message'] == 'kill_flight':
            try: f = [f for f in self.flights if f.callsign == m['cs']][0]
            except: return
            self.flights.remove(f)
            vt = self._flights_tracks[f]
            vt.destroy()
            del self._flights_tracks[f]
            del self._tracks_flights[vt]
            self.tracks.remove(vt)
            self.killed_flights.append(m['cs'])
            
            # Delete fpr and waypoints if any
            canvas = self.c
            canvas.delete(f.callsign+'fpr')
            try: self.routes.remove(f)
            except ValueError: pass  # Don't act if the fpr did not exist
            canvas.delete(f.callsign+'wp')
            canvas.delete(f.callsign+'wl')
            try: self.waypoints.remove(vt)
            except ValueError: pass  # Don't act if the waypoints did not exist
            # Delete LADS attached if any
            for lad in (lad for lad in self.lads[:] if lad.start==vt or lad.end==vt):
                lad.delete()

    def delete_routes(self,e=None):
        for track in self.tracks:
            self.c.delete(track.cs+'fpr')
            self.c.delete(track.cs+'wp')
            self.c.delete(track.cs+'wl')
            self.routes=[]
            self.waypoints=[]
            
    def draw_fpr(self,track):
        canvas=self.c
        line=()
        if track.to_do=='fpr':
            line=line+self.do_scale(track.pos)
        #for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        #JRAR: include both Waypoints and TLPV points
        for a in [wp for wp in track.route]:
            try: pto=self.do_scale(a.pos())
            except: continue
            if a.fix[0] <> '_' or a.fix in self.fir.iaps.keys():
                try: eto = '%02d:%02d'%(a.eto.hour, a.eto.minute)
                except: eto = ''
                if len(a.fix)<=5:
                    canvas.create_text(pto,text=a.fix,fill='orange',tag=track.callsign+'fpr',anchor=tix.SE,font='-*-Helvetica-*--*-10-*-')
                    canvas.create_text(pto,text=eto,fill='orange',tag=track.callsign+'fpr',anchor=tix.NE,font='-*-Helvetica-*--*-10-*-')
            line=line+pto
        if len(line)>3: canvas.create_line(line,fill='orange',tags=track.callsign+'fpr')
        self.routes.append(track)
        self.c.lift(track.callsign+'fpr')
        self.c.lift('track')

    def show_hide_fpr(self,track):
        print('showing estimates')
        canvas=self.c
        if canvas.itemcget(track.callsign+'fpr',"fill")=='orange':
            canvas.delete(track.callsign+'fpr')
            self.routes.remove(track)
        else:
            self.draw_fpr(track)
    
    def draw_way_point(self,track):
        canvas=self.c
        do_scale=self.do_scale

        canvas.delete(track.callsign+'fpr')
        canvas.delete(track.callsign+'wp')
        canvas.delete(track.callsign+'wl')
        try: self.waypoints.remove(track)
        except: pass

        size=4
        prev_pto = do_scale(track.pos)
        first_point = True
        #for a_next in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
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
        #for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        for a in [wp for wp in track.route]:
            (rect_x, rect_y) = pto = do_scale(a.pos())
            if a.stop:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='red',outline='yellow',tags=track.callsign+'wp')
                if a.push_back:
                    point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='purple',outline='yellow',tags=track.callsign+'wp')
            elif a.push_back:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='blue',outline='yellow',tags=track.callsign+'wp')
                if a.stop:
                    point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='purple',outline='yellow',tags=track.callsign+'wp')
            else:
                point_ident = canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='yellow',outline='yellow',tags=track.callsign+'wp')
            def clicked_on_waypoint(e, point_coord=a.pos(),point_name=a.fix):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                # Display window offering "Direct to..." and "Cancel" options.
                track.last_lad = e.serial
                win = tix.Frame(canvas)
                id_avo = tix.Label(win,text=track.callsign,bg='blue',fg='white')
                id_pto = tix.Entry(win,width=8, justify = tix.CENTER)
                id_pto.insert(0,point_name)
                but_direct = tix.Button(win, text="Dar directo")
                but_final = tix.Button(win, text="Final")
                but_remove = tix.Button(win, text="Eliminar")
                but_toggle_stop = tix.Button(win, text="Toggle stop")
                but_cancel = tix.Button(win, text="Cancelar")
                id_avo.grid(row=0, column=0, columnspan=1,sticky=tix.W+tix.E)
                id_pto.grid(row=1, column=0, columnspan=1,sticky=tix.W+tix.E)
                but_direct.grid(row=2, column=0, columnspan=1,sticky=tix.W+tix.E)
                but_final.grid(row=3, column=0, columnspan=1,sticky=tix.W+tix.E)
                but_remove.grid(row=4, column=0, columnspan=1,sticky=tix.W+tix.E)
                but_toggle_stop.grid(row=5, column=0, columnspan=1,sticky=tix.W+tix.E)
                but_cancel.grid(row=6, column=0, columnspan=1,sticky=tix.W+tix.E)
                win_identifier = canvas.create_window(e.x, e.y, window=win)
                def close_win(ident=win_identifier):
                    canvas.delete(ident)
                def remove_wp():
                    pto=id_pto.get()
                    self.sendMessage({"message":"remove_wp", "cs":track.callsign, "fix":pto})
                    #track.remove_wp(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    close_win()
                def final_wp():
                    pto=id_pto.get()
                    self.sendMessage({"message":"final_wp", "cs":track.callsign, "fix":pto})
                    #track.final_wp(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    close_win()
                def direct_to():
                    pto=id_pto.get()
                    self.sendMessage({"message":"route_direct", "cs":track.callsign, "fix":pto})
                    #track.route_direct(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    ##self.show_hide_way_point(track)
                    self.draw_way_point(track)
                    close_win()

                def toggle_stop():
                    pto=id_pto.get()
                    self.sendMessage({"message":"toggle_stop", "cs":track.callsign, "fix":pto})
                    #track.toggle_stop(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    close_win()
                def push_back():
                    pto=id_pto.get()
                    self.sendMessage({"message":"push_back", "cs":track.callsign, "fix":pto})
                    #track.toggle_stop(pto)
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    close_win()
                but_cancel['command'] = close_win
                but_final['command'] = final_wp
                but_remove['command'] = remove_wp
                but_direct['command'] = direct_to
                but_toggle_stop['command'] = toggle_stop
            canvas.tag_bind(point_ident, "<1>", clicked_on_waypoint)
            def rightclicked_on_waypoint(e, point_coord=a.pos(),point_name=a.fix):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                pto=point_name
                self.sendMessage({"message":"toggle_stop", "cs":track.callsign, "fix":pto})
                #track.toggle_stop(pto)
                canvas.delete(track.callsign+'wp')
                canvas.delete(track.callsign+'wl')
                self.waypoints.remove(track)
                self.draw_way_point(track)
            canvas.tag_bind(point_ident, "<3>", rightclicked_on_waypoint)
            def ctrl_rightclicked_on_waypoint(e, point_coord=a.pos(),point_name=a.fix):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                pto=point_name
                self.sendMessage({"message":"push_back", "cs":track.callsign, "fix":pto})
                #track.toggle_stop(pto)
                canvas.delete(track.callsign+'wp')
                canvas.delete(track.callsign+'wl')
                self.waypoints.remove(track)
                self.draw_way_point(track)
            canvas.tag_bind(point_ident, "<Control-Button-3>", ctrl_rightclicked_on_waypoint)
            def centerclicked_on_waypoint(e, prev_coord=a.prev_pto,next_coord=a.next_pto,point_next=a.fix,stop = a.stop,push_back = a.push_back):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                def insert_wp(e):
                    #(x,y) = self.undo_scale((e.x, e.y))
                    #fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message":"insert_wp", "cs":track.callsign, "fix":fix, "fix_next":point_next, "stop":stop, "push_back":push_back})
                    #track.insert_wp(fix,point_next)
                    self.sendMessage({"message":"remove_wp", "cs":track.callsign, "fix":point_next})
                    #track.remove_wp(point_next)
                    canvas.delete('route_definition')
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                def update_route_being_defined(e):
                    if next_coord == None:
                        line = prev_coord+(e.x, e.y)
                    else:
                        line = prev_coord+(e.x, e.y)+next_coord
                    canvas.delete('route_definition')
                    canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                    canvas.create_line(line,fill='yellow',tags='route_definition')
                def cancel_def_route(e):
                    if self.latest_processed_serial == e.serial: return
                    canvas.delete('route_definition')
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                    rd.defining_route = False
                ra_unbind(self, self.c, '<Motion>')
                ra_unbind(self, self.c, '<Button-2>')
                ra_unbind(self, self.c, '<Button-3>')
                ra_bind(self, self.c, '<Button-2>', cancel_def_route)
                ra_bind(self, self.c, '<Button-3>', insert_wp)
                ra_bind(self, self.c, '<Motion>', update_route_being_defined)
            canvas.tag_bind(point_ident, "<2>", centerclicked_on_waypoint)

        size=4
        (rect_x, rect_y) = prev_pto = do_scale(track.pos)
        canvas.create_rectangle(rect_x-size, rect_y-size, rect_x+size, rect_y+size,fill='yellow',outline='yellow',tags=track.callsign+'wp')
        line=()
        if track.to_do=='fpr':
            line=line+do_scale(track.pos)
        #for a in [wp for wp in track.route if wp.type==Route.WAYPOINT]:
        # JRAR: include both Waypoints and TLPV points
        for a in [wp for wp in track.route]:
            try: pto=do_scale(a.pos())
            except: continue
            #if a.fix[0] <> '_':
            #    try: eto = '%02d:%02d'%(a.eto.hour, a.eto.minute)
            #    except: eto = ''
            #    canvas.create_text(pto,text=a.fix,fill='yellow',tag=track.callsign+'wp',anchor=tix.SE,font='-*-Helvetica-*--*-10-*-')
            #    canvas.create_text(pto,text=eto,fill='yellow',tag=track.callsign+'wp',anchor=tix.NE,font='-*-Helvetica-*--*-10-*-')
            line=prev_pto+pto
            line_ident = canvas.create_line(line,fill='yellow',width=2,tags=track.callsign+'wl')
            def clicked_on_wayline(e, prev_coord=prev_pto,next_coord=pto,point_next=a.fix):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                def insert_wp(e):
                    #(x,y) = self.undo_scale((e.x, e.y))
                    #fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message":"insert_wp", "cs":track.callsign, "fix":fix, "fix_next":point_next})
                    #track.insert_wp(fix,point_next)
                    canvas.delete('route_definition')
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)

                def update_route_being_defined(e):
                    line = prev_coord+(e.x, e.y)+next_coord
                    canvas.delete('route_definition')
                    canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                    canvas.create_line(line,fill='yellow',tags='route_definition')
                def cancel_def_route(e):
                    if self.latest_processed_serial == e.serial: return
                    canvas.delete('route_definition')
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                    rd.defining_route = False
                ra_unbind(self, self.c, '<Motion>')
                ra_unbind(self, self.c, '<Button-2>')
                ra_unbind(self, self.c, '<Button-3>')
                ra_bind(self, self.c, '<Button-2>', cancel_def_route)
                ra_bind(self, self.c, '<Button-3>', insert_wp)
                ra_bind(self, self.c, '<Motion>', update_route_being_defined)
            canvas.tag_bind(line_ident, "<2>", clicked_on_wayline)
            #JRAR: rightclick on wayline inserts point with stop
            def rightclicked_on_wayline(e, prev_coord=prev_pto,next_coord=pto,point_next=a.fix):
                if e!=None:
                    self.cancel_geotab_serial = e.serial
                    self.cancel_lad_serial = e.serial
                    self.latest_processed_serial = e.serial
                    canvas.create_rectangle(e.x-size, e.y-size, e.x+size, e.y+size,fill='yellow',outline='yellow',tags='route_definition')
                def insert_wp(e):
                    #(x,y) = self.undo_scale((e.x, e.y))
                    #fix=(x,y)
                    fix = self.get_point_or_geo(e)
                    self.sendMessage({"message":"insert_wp", "cs":track.callsign, "fix":fix, "fix_next":point_next})
                    self.sendMessage({"message":"toggle_stop", "cs":track.callsign, "fix":fix})
                    #track.insert_wp(fix,point_next)
                    canvas.delete('route_definition')
                    canvas.delete(track.callsign+'wp')
                    canvas.delete(track.callsign+'wl')
                    self.waypoints.remove(track)
                    self.draw_way_point(track)
                    ra_unbind(self, self.c, '<Motion>')
                    ra_unbind(self, self.c, '<Button-2>')
                    ra_unbind(self, self.c, '<Button-3>')
                    ra_bind(self, self.c, '<Button-1>', self.b1_cb)
                    ra_bind(self, self.c, '<Button-2>', self.b2_cb)
                    ra_bind(self, self.c, '<Button-3>', self.b3_cb)
                insert_wp(e)
            canvas.tag_bind(line_ident, "<3>", rightclicked_on_wayline)
            prev_pto=pto

        self.waypoints.append(track)
        self.c.lift(track.callsign+'wl')
        self.c.lift('track')
        self.c.lift(track.callsign+'wp')
        
            
    def show_hide_way_point(self,track):
        canvas=self.c
        do_scale=self.do_scale
        #if route was selected, hide route and re-assign button functions
        if canvas.itemcget(track.callsign+'wp',"fill") in ('yellow','red'):
            canvas.delete(track.callsign+'wp')
            canvas.delete(track.callsign+'wl')
            self.waypoints.remove(track)
            self.selected_route_track = None
            ra_bind(self, self.c, '<Button-1>', self.b1_cb)
            ra_bind(self, self.c, '<Button-2>', self.b2_cb)
            ra_bind(self, self.c, '<Button-3>', self.b3_cb)
            return
        #if new route selection, remove previous if any...
        if self.selected_route_track != None:
            prev_track = self.selected_route_track
            canvas.delete(prev_track.callsign+'wp')
            canvas.delete(prev_track.callsign+'wl')
            try: self.waypoints.remove(prev_track)
            except ValueError: pass  # Don't act if the waypoints did not exist
        #... and draw new one
        self.draw_way_point(track)
        self.selected_route_track = track
        # re-assign button functions with route extension
        ra_bind(self, self.c, '<Button-1>', self.b1_cb)
        ra_bind(self, self.c, '<Button-2>', self.b2_cb)
        ra_bind(self, self.c, '<Control-Button-3>', self.extend_route)

    def get_point_or_geo(self, e):
        min_snap_distance = 8/self.scale
        min_snap_d2 = min_snap_distance * min_snap_distance
        (x,y) = self.undo_scale((e.x, e.y))
        fix = "X%.5fY%.5f"%(x,y)
        for [nombre,coord] in self.fir.points:
            d2 = (coord[0]-x)*(coord[0]-x)+(coord[1]-y)*(coord[1]-y)
            if (d2 < min_snap_d2):
                fix = nombre
                break
        return(fix)


    def extend_route(self,e):
        if self.cancel_geotab_serial == e.serial: return
        canvas=self.c
        (x,y) = self.undo_scale((e.x, e.y))
        track = self.selected_route_track
        #fix=(x,y)
        fix = self.get_point_or_geo(e)
        d = self.sendMessage({"message":"extend_route", "cs":track.callsign, "fix":fix})
        track.extend_route(fix)
        canvas.delete(track.callsign+'wp')
        canvas.delete(track.callsign+'wl')
        self.waypoints.remove(track)
        self.draw_way_point(track)

    def change_size(self,e):
        RaDisplay.change_size(self,e)
        self.toolbar.redraw()
            
    def update(self):
        def after_tracks(x):
            self.c.lift('track')
            self.c.lift('plot')  # Otherwise the most recent history dot comes above
                                 # and prevents correct clicking of the plot
            RaDisplay.update(self)
        threads.deferToThread(self.update_tracks).addCallback(after_tracks)
        self.update_clock()
                            
    def update_clock(self,t=None):
        if t==None: t=self.t
        else: self.t=t
        self.clock.configure(time='%02d:%02d:%02d' % (t.hour, t.minute, t.second))

    def update_wind(self,wind,metar):
        self.windrose.configure(wind_spd='%02d'%wind[0], wind_dir = (wind[1]+180.0) % 360.0, metar = metar)


    def update_tracks(self):
        # If we update the tracks all at once from here, when we are dealing with
        # many of them it will take a long time and the display will feel sluggish
        # Instead we cycle through them inside a thread, and let the main thread
        # update the actual tracks in bunches of 30. This improves responsiveness
        # JRAR: remove sleep, it will probably make the responsiveness worse
        for i in range(len(self.flights)):
            reactor.callFromThread(self.update_track,self.flights[i])
            #if not i%25: sleep(0.01) # Let the display refresh for every n tracks
        return True
            
    def update_track(self, f):
        # TODO This should be a RaDisplay method
        vt = self._flights_tracks[f]
        vt.alt=f.lvl
        vt.cs=f.callsign
        vt.wake=f.wake
        vt.ltype = f.type
        vt.lrwy = f.lrwy
        vt.echo=f.campo_eco
        vt.stand_sid=f.stand_sid
        vt.trans=f.campo_trans
        vt.gs=f.ground_spd
        vt.mach=f.get_mach()
        vt.rules=f.fr
        vt.colat=f.colat
        #vt.r_speed= f.r_speed
        #vt.r_head= f.r_head
        #vt.r_rate= f.r_rate

        if self.fir.AdHasIfrRwys(f.ades) and f.pof== 'FLYING':
            [xy_llz,rdl,dist_ayuda,pdte_ayuda,alt_pista] = f.llz
            (rx,ry) = r(xy_llz,f.pos) # Coordenadas relativas a la radioayuda
            dist_thr = rp((rx,ry))[0]-dist_ayuda
            vt.thr_nm = dist_thr
            vt.thr_min = dist_thr / f.ground_spd * 60.
        else:
            vt.thr_nm = ''
            vt.thr_min = ''
        vt.to_do=f.to_do
        vt.hdg=f.hdg
        vt.track=f.track
        vt.rate=f.get_rate_descend()
        vt.ias=f.ias
        vt.visible = (f.pof not in (Aircraft.INACTIVE, Aircraft.LOADING))
        vt.adep = f.adep
        vt.local_dep = (vt.adep in self.fir.local_ads[self.sector])
        vt.ades = f.ades
        vt.type = f.type
        vt.radio_cs = f.radio_callsign
        vt.rfl = f.rfl
        vt.cfl=f.cfl
        vt.ecl=f.ecl
        vt.eclfix = f.eclfix
        vt.tfl=f.tfl
        vt.line_onoff = [True,True,self.l2_onoff_var.get(),self.l3_onoff_var.get(),self.l4_onoff_var.get(),self.l5_onoff_var.get()]
        vt.flashing = f.trans_pp_pos
        if (vt.alt < self.select_FALT_varmin)or(vt.alt > self.select_FALT_varmax) : vt.visible = FALSE #Temporary altitude filter at 1000 feet for the controller
        if (f.pp_pos == None) or (f.pp_pos != self.pos_number): vt.assumed = False
        if f.pp_pos == self.pos_number: vt.assumed = True
        try:
            if vt.selected:
                self.draw_way_point(f)
        except:
            vt.selected = False


        [x0,y0]=self.do_scale(f.pos)

        try:
            vt.coords(x0,y0,f.t)
        except:
            return vt

        
    def vt_handler(self,vt,item,action,value,e=None):
        print(item)
        print(action)
        RaDisplay.vt_handler(self,vt,item,action,value,e)
        f=self._tracks_flights[vt]
        if item=='plot':
            if action=='<Button-1>':self.show_hide_fpr(f)
        #if item=='ecl':
        #    if action=='update':
        #        self.sendMessage({"message":"set_ecl", "cs": f.callsign, "ecl":int(value)})
        if item=='cfl':
            if action=='update':
                d = self.sendMessage({"message":"set_cfl", "cs": f.callsign, "cfl":float(value)})
                return d
        if item=='rate':
            if action=='update':
                (rate, force) = value
                return self.sendMessage({"message":"set_rate", "cs": f.callsign,
                                         "rate":rate, "force":force})
        if item=='hdg':
            if action=='update':
                (hdg,opt)=value
                self.sendMessage({"message":"set_hdg", "cs": f.callsign, "hdg":int(hdg), "opt":opt})
        if item=='ias':
            if action=='update':
                (spd,force_speed)=value
                d = self.sendMessage({"message":"set_ias", "cs": f.callsign,
                                  "ias":spd, "force_speed":force_speed})
                return d
        if item=='action':
            if action=='start':
                d = self.sendMessage({"message":"start", "cs": f.callsign})
                return d
        if item=='engine':
            if action=='fire':
                d = self.sendMessage({"message":"fire", "cs": f.callsign})
                return d
        if item=='mach':
            if action=='update':
                (spd,force_speed)=value
                d = self.sendMessage({"message":"set_mach", "cs": f.callsign,
                                  "mach":spd, "force_speed":force_speed})
                return d
        if item=='echo':
            if action=='<Button-3>':
                self.show_hide_way_point(f)
                if e!=None:
                    self.cancel_geotab_serial = e.serial

        if item=='set_trans':
            if action=='update':
                trans=value
                d = self.sendMessage({"message":"set_trans", "cs": f.callsign,
                                  "trans":trans})
                return d

        #if item=='cs':
            #if action=='<tix.ButtonRelease-2>':
                #self.show_hide_way_point(f)
                
    def reposition(self):
        RaDisplay.reposition(self)
        r=self.routes[:]
        w=self.waypoints[:]
        self.delete_routes()
        for track in r:
            self.draw_fpr(track)
        for track in w:
            self.draw_way_point(track)

    def redraw(self):
        RaDisplay.redraw(self)
        self.update_tracks()

    def b1_cb(self,e):
        RaDisplay.b1_cb(self,e)
        self.toolbar.close_windows()
    
    def b2_cb(self,e):
        RaDisplay.b2_cb(self,e)
        self.toolbar.close_windows()
    
    def b3_cb(self,e):
        RaDisplay.b3_cb(self,e)
        self.toolbar.close_windows()
        
    def exit(self):
        self.clock.close()
        
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

        
        for map_name in self.fir.local_maps:
            self.conf.write_option("Aux_Maps",map_name,bool(self.toolbar.var_ver_localmap[map_name].get()))
      
        # Avoid memory leaks due to circular references preventing
        # the garbage collector from discarding this object
        del(self.toolbar.master)
        del(self.dep_tabular.master)
        del(self.act_tabular.master)
        del(self.arr_tabular.master)
        # Destroy radar windows
        self.giw.exit()        
        RaDisplay.exit(self)
        del self._flights_tracks
        del self._tracks_flights
        
    def __del__(self):
        logging.debug("PpDisplay.__del__")
    
class ventana_auxiliar:
    def __init__(self,master):
        self.master=master
        self.conf=master.conf
        self.opened_windows=[]
        if self.master.fir.param('editor_mapas_reducidos', False):  # parametro de escenario (antes fir.name == 'LECB')
            master.draw_routes=master.draw_point=master.draw_point_names=False
            master.draw_sector=master.draw_lim_sector=master.draw_tmas=master.draw_deltas=False


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
        self.var_ver_fichas_tab = tk.IntVar()
        for map_name in master.fir.local_maps:
            self.var_ver_localmap[map_name] = tk.IntVar()
        self.auto_sep = tk.IntVar()
        self.auto_sep.set(self.master.auto_separation)
        self.speed_vector_var = tk.IntVar()
        self.speed_vector_var.set(0)
        self.clock_speed_var = tk.DoubleVar()
        self.clock_speed_var.set(1.0)
        self.select_FALT_varmin = tk.IntVar()
        self.select_FALT_varmin.set(0)
        self.select_FALT_varmax = tk.IntVar()
        self.select_FALT_varmax.set(990)
        self.toolbar_id = None
        
        self.new_route_RaD=None
        self.acft_data_RaD=None
        
    
    def close_windows(self):
        for w in self.opened_windows[:]:
            self.master.c.delete(w)
            self.opened_windows.remove(w)
        
    def redraw(self):
        master=self.master
        w=master.c
        ancho=master.width
        alto=master.height
        scale=master.scale
        
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
            #master.x0 -= ancho/set_displacement(event.num)/scale
            master.center_x -= ancho/set_displacement(event.num)
            master.reposition()
            
        def b_derecha(event):
            #master.x0 += ancho/set_displacement(event.num)/scale
            master.center_x += ancho/set_displacement(event.num)
            master.reposition()
            
        def b_arriba(event):
            #master.y0 += ancho/set_displacement(event.num)/scale
            #master.center_y += alto/set_displacement(event.num)
            #master.reposition()
            ##############################PARA QUE SUBA EL MAPA CUANDO YO PULSO ARRIBA
            master.center_y -= alto/set_displacement(event.num)
            master.reposition()

        def b_abajo(event):
            #master.y0 -= ancho/set_displacement(event.num)/scale
            #master.center_y -= alto/set_displacement(event.num)
            #master.reposition()
            ##############################PARA QUE BAJE EL MAPA CUANDO YO PULSO ABAJO
            master.center_y += alto/set_displacement(event.num)
            master.reposition()
            
        MINIMUM_SCALE_FACTOR = 1.01
        NORMAL_SCALE_FACTOR = 1.1
        MAXIMUM_SCALE_FACTOR = 1.5
        
        LABEL_MIN_FONT_SIZE = 7
        LABEL_MAX_FONT_SIZE = 11
        LABEL_SIZE_STEP = 1

        def set_zoom_scale_on_event (event_number=1):
            if event_number==3:
                return MINIMUM_SCALE_FACTOR
            elif event_number==2:
                return MAXIMUM_SCALE_FACTOR
            elif event_number==1:
                return NORMAL_SCALE_FACTOR
            elif event_number==4:
                return MINIMUM_SCALE_FACTOR
            elif event_number==5:
                return MINIMUM_SCALE_FACTOR
            
        def b_zoom_mas(event):
            master.scale *= set_zoom_scale_on_event(event.num)
            master.reposition()
            
        def b_zoom_menos(event):
            master.scale /= set_zoom_scale_on_event(event.num)
            master.reposition()
            
        def b_standard():
            master.center_x=ancho/2
            master.center_y=(alto-40.)/2
            master.get_scale()
            master.reposition()
            
        def b_inicio():
            master.sendMessage({"message": "play"})
                
        def b_parar():
            master.sendMessage({"message": "pause"})
                
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
                        
        def b_show_hide_localmaps():
            master.local_maps_shown = []
            for map_name in master.fir.local_maps:
                try:
                    if self.var_ver_localmap[map_name].get() != 0:
                        master.local_maps_shown.append(map_name)
                        self.master.maps[map_name].show()
                    else:
                        self.master.maps[map_name].hide()
                except:
                    logging.debug("Unable to show/hide localmaps", exc_info=True)
                    
        #TODO: To show maps from FIR file at start           
        b_show_hide_localmaps()
           
        def b_auto_separationaration():
            global auto_separation
            auto_separation = not auto_separation

        def get_selected(label=''):
            if master.selected_track==None:
                RaDialog(master.c, label=label,
                    text='No hay ningún vuelo seleccionado')
            return master.selected_track

        def kill_acft():
            self.close_windows()
            if (get_selected('Matar vuelo')==None): return
            a = master.selected_track
            def kill():
                master.sendMessage({"message": "kill", "cs": a.cs})
                #a.visible=False
            RaDialog(master.c,label=str(a.cs)+': Matar vuelo',
                       text='Matar '+str(a.cs),ok_callback=kill,
                       position=(a.x, a.y))
                    
        def quitar_fpr():
            for a in ejercicio:
                if w.itemcget(a.callsign+'fpr','fill')=='orange':
                    w.delete(a.callsign+'fpr')
                    
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
        win_identifier=None
        
        #def quitar_tormentas():
        #    for s in storms[:]:
        #        s.delete()
        #        storms.remove(s)
        
                        
        def define_holding():
            """Show a dialog to set the selected aircraft in a holding pattern over the selected fix"""
            self.close_windows()
            if (get_selected('Poner en espera')==None): return
            sel = master._tracks_flights[master.selected_track]
                
            def set_holding(e=None,entries=None):
                error = False
                ent_hold=entries['Fijo Principal:']
                ent_side=entries['Virajes (I/D):']
                fijo = ent_hold.get().upper()
                lado = ent_side.get().upper()
                if not fijo in sel.route:
                    ent_hold['bg'] = 'red'
                    ent_hold.focus_set()
                    error = True
                if lado.upper() == 'I': std_turns = False
                elif lado.upper() == 'D' or lado.strip()=='': std_turns = True
                else:
                    ent_side['bg'] = 'red'
                    ent_side.focus_set()
                    error=True
                if error:
                    return False  # Not validated correctly
                
                master.sendMessage({"message":"hold", "cs":sel.callsign,
                                    "fix":fijo, "std_turns": std_turns})
                
            # Build the GUI Dialog
            entries=[]
            entries.append({'label':'Fijo Principal:','width':5,'def_value':sel.route[0].fix})
            entries.append({'label':'Virajes (I/D):','width':1,'def_value':''})
            RaDialog(w,label=sel.callsign+': Poner en espera',ok_callback=set_holding,entries=entries)    
            
        def nueva_ruta():

            """Ask the user to set a new route and destination airdrome for the currently selected aircraft"""
            self.close_windows()
            if (get_selected('Nueva ruta')==None): return
            sel = master._tracks_flights[master.selected_track]

            def change_fpr_unsaved(e=None,entries=None):
                ent_route,ent_destino=entries['Ruta:'],entries['Destino:']
                pts = ent_route.get()
                try:
                    pts_split = pts.split('_LLZ')
                    if len(pts_split) == 2:
                        r1 = Route.Route(Route.get_waypoints(pts_split[0]),
                            raise_on_unknown = True)
                        r2 = Route.Route(Route.get_waypoints(pts_split[1]),
                            raise_on_unknown = True)
                    else:
                        r = Route.Route(Route.get_waypoints(pts),
                            raise_on_unknown = True)
                except:
                    ent_route['bg'] = 'red'
                    ent_route.focus_set()
                    logging.debug("Unable to set the new route", exc_info=True)
                    return False  # Validation failed
                # TODO we should validate the destination
                sel.ades = ent_destino.get().upper()

                #SAVED/UNSAVED OPTION
                master.sendMessage({"message": "change_fpr_unsaved",
                                    "cs":      sel.callsign,
                                    "route":   pts,
                                    #JRAR: We were losing stop and push_back info
                                    # "route":   str(r),
                                    "ades":    sel.ades})

            def change_fpr(e=None,entries=None):
                ent_route,ent_destino=entries['Ruta:'],entries['Destino:']
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
                    str_dep ='[dep_'+sel.adep+rwy+']\n'
                    rwy_found = False
                    file_str = ''
                    fir_file= open(fir_path,'r')
                    for line in fir_file:
                        if rwy_found:
                            split_line=line.split('=')
                            this_park = split_line[0].strip()
                            if this_park == park:
                                line = park + ' = ' + coord +'\n'
                                rwy_found = False
                        elif line == str_dep:
                            rwy_found = True
                        file_str = file_str + line
                    fir_file.close()
                    fir_file= open(fir_path,'w')
                    fir_file.write(file_str)
                    fir_file.close()
                if sel.star != None:
                    park = sel.park
                    rwy = sel.desrwy
                    coord = ''
                    for i in range(len(pts_split),1,-1):
                        pt = pts_split[i-1]
                        if pt == '_LLZ':
                            break
                        coord = pt + ',' + coord
                    coord = coord[:-1]
                    fir_path = master.fir.file
                    str_lnd ='[lnd_'+sel.ades+rwy+']\n'
                    rwy_found = False
                    file_str = ''
                    fir_file= open(fir_path,'r')
                    for line in fir_file:
                        if rwy_found:
                            split_line=line.split('=')
                            this_park = split_line[0].strip()
                            if this_park == park:
                                line = park + '= ' + coord +'\n'
                                rwy_found = False
                        elif line == str_lnd:
                            rwy_found = True
                        file_str = file_str + line
                    fir_file.close()
                    fir_file= open(fir_path,'w')
                    fir_file.write(file_str)
                    fir_file.close()
                ###################################################################################################

                try:
                    pts_split = pts.split('_LLZ')
                    if len(pts_split) == 2:
                        r1 = Route.Route(Route.get_waypoints(pts_split[0]),
                            raise_on_unknown = True)
                        r2 = Route.Route(Route.get_waypoints(pts_split[1]),
                            raise_on_unknown = True)
                    else:
                        r = Route.Route(Route.get_waypoints(pts),
                            raise_on_unknown = True)
                except:
                    ent_route['bg'] = 'red'
                    ent_route.focus_set()
                    logging.debug("Unable to set the new route", exc_info=True)
                    return False  # Validation failed
                # TODO we should validate the destination
                sel.ades = ent_destino.get().upper()

                #SAVED/UNSAVED OPTION

                master.sendMessage({"message": "change_fpr",
                                    "cs":      sel.callsign,
                                    "route":   pts,
                                    #JRAR: We were losing stop and push_back info
                                    # "route":   str(r),
                                    "ades":    sel.ades})
            #Build the GUI Dialog
            entries=[]
            ruta = ""
            #for fix in [wp.fix for wp in sel.route if wp.type==Route.WAYPOINT]:
            for wp in sel.route:
                #if wp.type==Route.WAYPOINT:
                #    ruta += " " + wp.fix
                #    if wp.stop:
                #        ruta+='*'
                #    if wp.push_back:
                #        ruta+='<'
                # JRAR: Include all waypoint types
                ruta += " " + wp.fix
                if wp.stop:
                    ruta+='*'
                if wp.push_back:
                    ruta+='<'
            ruta = ruta.strip()

            entries.append({'label':'Ruta:','width':50,'def_value':ruta})
            entries.append({'label':'Destino:','width':5,'def_value':sel.ades})

            #Elige la opcion de guardar ruta o no
            RaDialog(w,label=sel.callsign+': Nueva ruta',
                                 ok_callback=change_fpr,entries=entries)
            #                     ok_callback=change_fpr_unsaved,entries=entries)

        def cambiar_viento():
            """Show a dialog to allow the user to change the wind in real time"""
            self.close_windows()
            wind = master.wind
            def change_wind(e=None,entries=None):
                ent_dir=entries['Dirección:']
                ent_int=entries['Intensidad (kts):']
                int=ent_int.get()
                dir=ent_dir.get()
                fallo = False
                if dir.isdigit():
                    rumbo = (float(dir)+180.0) % 360.0
                else:
                    ent_dir['bg'] = 'red'
                    ent_dir.focus_set()
                    fallo = True
                if int.isdigit():
                    intensidad = float(int)
                else:
                    ent_int['bg'] = 'red'
                    ent_int.focus_set()
                    fallo = True
                if fallo:
                    return False  # Validation failed
                
                master.sendMessage({"message":"wind",
                                    "wind":[intensidad,rumbo]})
                master.wind = [intensidad, rumbo]
                
            # Build the GUI Dialog
            entries=[]
            entries.append({'label':'Dirección:','width':3,'def_value':int((wind[1]+180.0)%360.0)})
            entries.append({'label':'Intensidad (kts):','width':2,'def_value':int(wind[0])})
            RaDialog(w,label='Definir viento',
                    ok_callback=change_wind,entries=entries)    
            
            
        def hdg_after_fix():
            """Show a dialog to command the selected aircraft to follow a heading after a certain fix"""
            self.close_windows()
            if (get_selected('Rumbo después de fijo')==None): return
            sel = master._tracks_flights[master.selected_track]
                
            def set_fix_hdg(e=None,entries=None):
                error = False
                ent_fix=entries['Fijo:']
                ent_hdg=entries['Rumbo:']
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
                
                master.sendMessage({"message":"hdg_after_fix",
                                    "cs":sel.callsign,
                                    "fix":fijo,
                                    "hdg":hdg})

            # Build the GUI Dialog
            entries=[]
            entries.append({'label':'Fijo:','width':5,'def_value':str(sel.route[0].fix)})
            entries.append({'label':'Rumbo:','width':3})
            RaDialog(w,label=sel.callsign+': Rumbo después de fijo',
                    ok_callback=set_fix_hdg,entries=entries)    
            
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
                
                master.sendMessage({"message":"int_rdl",
                                    "cs": sel.callsign,
                                    "fix": fijo,
                                    "track":(rdl + correccion)% 360.})
                
            # Build the GUI Dialog
            entries=[]
            entries.append({'label':'Fijo:','width':5,'def_value':str(sel.route[0].fix)})
            entries.append({'label':'Radial:','width':3})
            entries.append({'label':'Desde/Hacia (D/H)','width':1,'def_value':'D'})
            RaDialog(w,label=sel.callsign+': Interceptar radial',
                    ok_callback=set_rdl,entries=entries)    

        #DISTINGUIMOS ENTRE LOS PROCEDIMIENTOS MAP Y FRUSTRADA: FRUSTRADA ES UN ABORTO DE ATERRIZAJE POR LO QUE SE DETIENE EL DESCENSO, MIENTRAS QUE MAP CONTINUARÁ DESCENDIENDO HASTA COMPLETAR LA PASADA BAJA

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
            RaDialog(w,label=sel.callsign+': Ejecutar MAP',
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
            RaDialog(w,label=sel.callsign+': Ejecutar pasada baja',
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
                master.sendMessage({"message":"int_ils", "cs":sel.callsign})
            RaDialog(w,label=sel.callsign+': Interceptar ILS',
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
                RaDialog(w,label=sel.callsign+': Interceptar LLZ',
                         text='Vuelo sin procedimiento asociado. Añada procedimiento de aproximación y reintente')
                return
            def int_llz(e=None):
                master.sendMessage({"message":"int_llz", "cs":sel.callsign})
            RaDialog(w,label=sel.callsign+': Interceptar LLZ',
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
                RaDialog(w,label=sel.callsign+': Interceptar ARRV',
                         text='Vuelo sin IAF. Añada la ruta hasta el IAF y reintente')
                return
            def int_arrv(e=None):
                master.sendMessage({"message":"int_arrv", "cs":sel.callsign})
            RaDialog(w,label=sel.callsign+': Interceptar ARRV',
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
            if (get_selected('Órbita inmediata')==None): return
            sel = master._tracks_flights[master.selected_track]
            def set_orbit(e=None,sel=sel,entries=None):
                side_aux = entries['Orbitar hacia:']['value']
                if side_aux.upper() == 'IZDA':
                    dir = Aircraft.LEFT  # Constant defined in Aircraft.py
                else:
                    dir = Aircraft.RIGHT
                master.sendMessage({"message":"orbit", "cs":sel.callsign, "direction":dir})
            entries=[]
            entries.append({'label':'Orbitar hacia:',
                            'values':('IZDA','DCHA'),
                            'def_value':'IZDA'})
            RaDialog(w,label=sel.callsign+': Orbitar',
                     ok_callback=set_orbit, entries=entries)      

        def meteo_visual():
            def lluvia():
                if master.metar.split()[4] in ['BR','FG']:
                    but_lluvia['fg'] = 'red'
                    but_niebla['fg'] = 'black'
                    but_lluvia.pack(side=tix.TOP,expand=True,fill=tix.BOTH)
                    but_niebla.pack(side=tix.BOTTOM,expand=True,fill=tix.BOTH)
                    if master.metar.split()[4] == 'BR':
                        master.metar = master.metar.replace('BR','RA')
                    elif master.metar.split()[4] == 'FG':
                        master.metar = master.metar.replace('FG','RA')
                elif master.metar.split()[4] == 'RA':
                    but_lluvia['fg'] = 'black'
                    but_niebla['fg'] = 'black'
                    but_lluvia.pack(side=tix.TOP,expand=True,fill=tix.BOTH)
                    but_niebla.pack(side=tix.BOTTOM,expand=True,fill=tix.BOTH)
                    master.metar = master.metar.replace('RA','BR')
                meteo = master.metar
                master.sendMessage({"message":"rain","meteo":meteo})
            def niebla():
                if master.metar.split()[4] in ['BR','RA']:
                    but_lluvia['fg'] = 'black'
                    but_niebla['fg'] = 'red'
                    but_lluvia.pack(side=tix.TOP,expand=True,fill=tix.BOTH)
                    but_niebla.pack(side=tix.BOTTOM,expand=True,fill=tix.BOTH)
                    if master.metar.split()[4] == 'BR':
                        master.metar = master.metar.replace('BR','FG')
                    elif master.metar.split()[4] == 'RA':
                        master.metar = master.metar.replace('RA','FG')
                elif master.metar.split()[4]=='FG':
                    but_lluvia['fg'] = 'black'
                    but_niebla['fg'] = 'black'
                    but_lluvia.pack(side=tix.TOP,expand=True,fill=tix.BOTH)
                    but_niebla.pack(side=tix.BOTTOM,expand=True,fill=tix.BOTH)
                    master.metar = master.metar.replace('FG','BR')
                meteo = master.metar
                master.sendMessage({"message":"fog","meteo":meteo})
            root = Toplevel()
            root.geometry('%dx%d+%d+%d' % (100, 50, 900, 900))
            condiciones = tix.Frame(root, bg='gray')
            condiciones.grid()
            but_lluvia = tix.Button(condiciones, text='Lluvia',  fg='black', command=lluvia)
            but_lluvia.pack(side=tix.TOP,expand=True,fill=tix.BOTH)
            but_niebla = tix.Button(condiciones, text='Niebla',  fg='black', command=niebla)
            but_niebla.pack(side=tix.BOTTOM,expand=True,fill=tix.BOTH)

        def b_rwy_change():
            # TODO THIS IS PROBABLY NOT WORKING!!
            # Needs to be retested and probably rethought
            self.close_windows()
            # Find airports with several runways
            ad_list = [ad for ad in master.fir.aerodromes.values()
                        if len(ad.rwy_direction_list)>1]

            if len(ad_list) == 0:
                RaDialog(w,label='Cambio de pista', text='No hay aeropuertos con más de una pista IFR')
                return
            
            def close_rwy_chg(e=None,entries=None):
                for ad in ad_list:
                    if entries[ad.code_id]['value']!=ad.rwy_in_use.txt_desig:
                        master.sendMessage({"message":"rwy_in_use", "ad":ad.code_id,
                                            "rwy":entries[ad.code_id]['value']})
            
            entries=[]
            for ad in ad_list:
                entries.append({'label':ad.code_id,
                            'values':[rwy.txt_desig for rwy in ad.rwy_direction_list],
                            'def_value':ad.rwy_in_use.txt_desig})
            RaDialog(w,label='Cambiar pistas en uso',
                     ok_callback=close_rwy_chg, entries=entries)      
            
        def b_auth_approach():
            self.close_windows()
            if (get_selected('Autorizar a Aproximación')==None): return
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

                
            def auth_app(e=None,avo=sel, entries=None):
                master.sendMessage({"message":"execute_app", "cs":sel.callsign,
                                    "ades": entries['Destino:'].get().upper(),
                                    "iaf": entries['IAF:']['value']})
            # Build entries
            # TODO We should be able of cleanly finding what's the current IAF
            iaf = ''
            #Get all iafs for wry in use
            iaps = ad.rwy_in_use.iaps.keys()
            #Get all iafs for rest of rwys
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig != ad.rwy_in_use.txt_desig:
                    iaps = iaps + rwy.iaps.keys()
            #Find a potential iaf
            for i in range(0,len(sel.route)):
                if sel.route[i].fix == sel.iaf:
                    iaf = sel.route[i].fix
                    break
            if iaf == '':
                for i in range(0,len(sel.route)):
                    if sel.route[i].fix in ad.rwy_in_use.iaps.keys():
                        iaf = sel.iaf = sel.route[i].fix
                        break
            if iaf == '':
                for i in range(0,len(sel.route)):
                    if sel.route[i].fix in iaps:
                        iaf = sel.iaf = sel.route[i].fix
                        break
            if iaf == '': iaf = sel.iaf
            entries=[]
            entries.append({'label':'Destino:', 'width':4, 'def_value':ad.code_id})
            entries.append({'label':'IAF:', 'width':5, 'values':iaps, 'def_value':iaf})
            RaDialog(w,label=sel.callsign+': Autorizar a Aproximación',
                     ok_callback=auth_app, entries=entries)      

        ventana=tix.Frame(w,bg='gray',width=ancho)
        grid_column=0
        self.but_inicio = tix.Button(ventana,bitmap='@'+IMGDIR+'start.xbm',command=b_inicio)
        #self.but_inicio.pack(side=tix.LEFT,expand=1,fill=X)
        self.but_inicio.grid(row=0,column=grid_column)
        self.but_parar = tix.Button(ventana,bitmap='@'+IMGDIR+'pause.xbm',command=b_parar)
        #self.but_parar.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_parar.grid(row=0,column=grid_column)

        self.but_orient = tix.Button(ventana, text = 'ORIENT')
        grid_column += 1
        self.but_orient.grid(row=0,column=grid_column)
        #self.but_orient.pack(side=tix.LEFT,expand=1,fill=X)

        def orient_buttons():
            self.close_windows()
            ventana_orient = tix.Frame(w,bg='gray')
            self.but_north = tix.Button(ventana_orient, text = 'NORTH', command = b_north)
            self.but_north.grid(column=0,row=0,sticky=tix.E+tix.W)
            self.but_field = tix.Button(ventana_orient, text = 'FIELD', command = b_field)
            self.but_field.grid(column=0,row=1,sticky=tix.E+tix.W)
            i=w.create_window(ventana.winfo_x()+self.but_orient.winfo_x(),alto-ventana.winfo_height(),window=ventana_orient,anchor='sw')
            self.opened_windows.append(i)
        self.but_orient['command'] = orient_buttons
        def b_north(e=None):
            self.close_windows()
            master.orient = 'north'
            master.reposition()
        def b_field(e=None):
            self.close_windows()
            master.orient = 'field'
            master.reposition()
        
        self.but_izq = tix.Button(ventana,bitmap='@'+IMGDIR+'left.xbm')
        #self.but_izq.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_izq.grid(row=0,column=grid_column)
        self.but_izq.bind("<Button-1>",b_izquierda)
        self.but_izq.bind("<Button-2>",b_izquierda)
        self.but_izq.bind("<Button-3>",b_izquierda)

        self.but_arriba = tix.Button(ventana,bitmap='@'+IMGDIR+'up.xbm')
        #self.but_arriba.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_arriba.grid(row=0,column=grid_column)
        self.but_arriba.bind("<Button-1>",b_arriba)
        self.but_arriba.bind("<Button-2>",b_arriba)
        self.but_arriba.bind("<Button-3>",b_arriba)            
        
        self.but_abajo = tix.Button(ventana,bitmap='@'+IMGDIR+'down.xbm')
        #self.but_abajo.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_abajo.grid(row=0,column=grid_column)
        self.but_abajo.bind("<Button-1>",b_abajo)
        self.but_abajo.bind("<Button-2>",b_abajo)
        self.but_abajo.bind("<Button-3>",b_abajo)            
    
        self.but_derecha = tix.Button(ventana,bitmap='@'+IMGDIR+'right.xbm')
        #self.but_derecha.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_derecha.grid(row=0,column=grid_column)
        self.but_derecha.bind("<Button-1>",b_derecha)
        self.but_derecha.bind("<Button-2>",b_derecha)
        self.but_derecha.bind("<Button-3>",b_derecha)            
        
        #self.but_zoom_mas = tix.Button(ventana,bitmap='@'+IMGDIR+'zoom.xbm',command=b_zoom_mas)
        self.but_zoom_mas = tix.Button(ventana,bitmap='@'+IMGDIR+'zoom.xbm')
        #self.but_zoom_mas.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_zoom_mas.grid(row=0,column=grid_column)
        self.but_zoom_mas.bind("<Button-1>",b_zoom_mas)
        self.but_zoom_mas.bind("<Button-2>",b_zoom_mas)
        self.but_zoom_mas.bind("<Button-3>",b_zoom_mas)

        
        #self.but_zoom_menos = tix.Button(ventana,bitmap='@'+IMGDIR+'unzoom.xbm',command=b_zoom_menos)
        self.but_zoom_menos = tix.Button(ventana,bitmap='@'+IMGDIR+'unzoom.xbm')
        #self.but_zoom_menos.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_zoom_menos.grid(row=0,column=grid_column)
        self.but_zoom_menos.bind("<Button-1>",b_zoom_menos)
        self.but_zoom_menos.bind("<Button-2>",b_zoom_menos)
        self.but_zoom_menos.bind("<Button-3>",b_zoom_menos)
        
        self.but_standard = tix.Button(ventana,bitmap='@'+IMGDIR+'center.xbm',command=b_standard)
        #self.but_standard.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_standard.grid(row=0,column=grid_column)

        self.but_tamano_etiq = tix.Button(ventana,bitmap='@'+IMGDIR+'labelsize.xbm')
        #self.but_tamano_etiq.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_tamano_etiq.grid(row=0,column=grid_column)
        self.but_tamano_etiq.bind("<Button-1>",b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-2>",b_tamano_fichas)
        self.but_tamano_etiq.bind("<Button-3>",b_tamano_fichas)
        
        self.but_term = tix.Button(ventana,text='Kill',command=kill_acft)
        #self.but_term.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_term.grid(row=0,column=grid_column)

        self.but_ruta = tix.Button(ventana,text='Ruta',command=nueva_ruta)
        #self.but_ruta.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_ruta.grid(row=0,column=grid_column)

        self.but_datos = tix.Button(ventana,text='Datos',command=ver_detalles)
        #self.but_datos.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_datos.grid(row=0,column=grid_column)

        self.but_quitar_lads = tix.Button(ventana,text='LADs', fg = 'red',command = self.master.delete_lads)
        #self.but_quitar_lads.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_quitar_lads.grid(row=0,column=grid_column)

        self.but_quitar_fpr = tix.Button(ventana,text='Rutas', fg = 'red',command = self.master.delete_routes)
        #self.but_quitar_fpr.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_quitar_fpr.grid(row=0,column=grid_column)

        #self.but_quitar_tormentas = tix.Button(ventana,text='TS', fg = 'red',command = self.master.quitar_tormentas)
        #self.but_quitar_tormentas.pack(side=tix.LEFT,expand=1,fill=X)
        self.but_ver_proc = tix.Button(ventana, text = 'PROCs')
        #self.but_ver_proc.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_ver_proc.grid(row=0,column=grid_column)

        def procs_buttons():
            self.close_windows()
            ventana_procs = tix.Frame(w,bg='gray')
            self.but_espera = tix.Button(ventana_procs, text='Esperas', command = define_holding)
            self.but_espera.grid(column=0,row=0,sticky=tix.E+tix.W)
            self.but_hdg_fix = tix.Button(ventana_procs, text = 'HDG despues fijo', command = hdg_after_fix)
            self.but_hdg_fix.grid(column=0,row=1,sticky=tix.E+tix.W)
            self.but_int_rdl = tix.Button(ventana_procs, text = 'Int. RDL', command = int_rdl)
            self.but_int_rdl.grid(column=0,row=2,sticky=tix.E+tix.W)
            self.but_chg_rwy = tix.Button(ventana_procs, text = 'Cambio RWY', command = b_rwy_change)
            self.but_chg_rwy.grid(column=0,row=3,sticky=tix.E+tix.W)
            self.but_orbit = tix.Button(ventana_procs, text = 'Orbitar aquí', command = b_orbitar)
            self.but_orbit.grid(column=0,row=4,sticky=tix.E+tix.W)
            self.but_wind = tix.Button(ventana_procs, text = 'Cambiar viento', command = cambiar_viento)
            self.but_wind.grid(column=0,row=5,sticky=tix.E+tix.W)
            self.but_meteo = tix.Button(ventana_procs, text = 'Meteo Visual', command = meteo_visual)
            self.but_meteo.grid(column=0,row=6,sticky=tix.E+tix.W)
            i=w.create_window(ventana.winfo_x()+self.but_ver_proc.winfo_x(),alto-ventana.winfo_height(),window=ventana_procs,anchor='sw')
            self.opened_windows.append(i)

        self.but_ver_proc['command'] = procs_buttons
        self.but_ver_app = tix.Button(ventana, text = 'APP')
        #self.but_ver_app.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_ver_app.grid(row=0,column=grid_column)

        def maps_buttons():
            self.close_windows()
            ventana_maps = tix.Frame(w,bg='gray')
            self.but_app_proc = tix.Button(ventana_maps, text = 'APP PROC.', command = b_auth_approach)
            self.but_app_proc.grid(column=0,row=0,sticky=tix.E+tix.W)
            self.but_ils_vec = tix.Button(ventana_maps, text = 'ILS (vectores)', command = b_int_ils)
            self.but_ils_vec.grid(column=0,row=1,sticky=tix.E+tix.W)
            self.but_loc = tix.Button(ventana_maps, text = 'LOCALIZADOR', command = b_llz)
            self.but_loc.grid(column=0,row=2,sticky=tix.E+tix.W)
            self.but_exe_map = tix.Button(ventana_maps, text = 'PASADA BAJA', command = b_execute_lowpass)
            self.but_exe_map.grid(column=0,row=3,sticky=tix.E+tix.W)
            self.but_exe_lowpass = tix.Button(ventana_maps, text = 'EJECUTAR MAP', command = b_execute_map)
            self.but_exe_lowpass.grid(column=0,row=4,sticky=tix.E+tix.W)
            i=w.create_window(ventana.winfo_x()+self.but_ver_app.winfo_x(),alto-ventana.winfo_height(),window=ventana_maps,anchor='sw')
            self.opened_windows.append(i)
        self.but_ver_app['command'] = maps_buttons

        self.but_auto_separation = tix.Checkbutton(ventana, text = 'SEP', variable = self.auto_sep, command=lambda: master.toggle_auto_separation())
        #self.but_auto_separation.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_auto_separation.grid(row=0,column=grid_column)

        self.but_bri = tix.Button(ventana, text = 'BRI', command = master.rabrightness.conmuta)
        #self.but_bri.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_bri.grid(row=0,column=grid_column)

        self.but_ver_maps = tix.Button(ventana, text = 'MAPAS')
        #self.but_ver_maps.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_ver_maps.grid(row=0,column=grid_column)

        def mapas_buttons():
            self.close_windows()
            ventana_mapas = tix.Frame(w)
            myrow = 0
            if not self.master.fir.param('editor_mapas_reducidos', False):  # antes fir.name not in ['LECB']
                self.but_ver_nombrs_ptos = tix.Checkbutton(ventana_mapas, text = 'Nombres Fijos', variable=self.vfn, command=self.master.toggle_point_names)
                self.but_ver_nombrs_ptos.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_ptos = tix.Checkbutton(ventana_mapas, text = 'Fijos', variable=self.vf, command=self.master.toggle_point)
                self.but_ver_ptos.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_routes = tix.Checkbutton(ventana_mapas, text = 'Aerovias', variable=self.vr, command=self.master.toggle_routes)
                self.but_ver_routes.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_sector = tix.Checkbutton(ventana_mapas, text = 'Sector', variable=self.vs, command=self.master.toggle_sector)
                self.but_ver_sector.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_lim_sector = tix.Checkbutton(ventana_mapas, text = 'Lim. Sector', variable=self.vsl, command=self.master.toggle_lim_sector)
                self.but_ver_lim_sector.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_tmas = tix.Checkbutton(ventana_mapas, text = 'TMAs',  variable=self.vt, command=self.master.toggle_tmas)
                self.but_ver_tmas.grid(column=0,row=myrow,sticky=tix.W)
                myrow+= 1
                self.but_ver_deltas = tix.Checkbutton(ventana_mapas, text = 'Deltas', variable=self.vd, command=self.master.toggle_deltas)
                self.but_ver_deltas.grid(column=0,row=myrow,sticky=tix.W)

                myrow += 1
            #map_name_list = master.fir.local_maps.keys()
            #map_name_list.sort()
            
            for map_name in self.master.fir.local_maps_order:#map_name_list:
                self.but_ver_local_map = tix.Checkbutton(ventana_mapas, text = map_name, variable = self.var_ver_localmap[map_name], command=b_show_hide_localmaps)
                self.but_ver_local_map.grid(column=0,row=myrow,sticky=tix.W)
                myrow += 1

            i=w.create_window(ventana.winfo_x()+self.but_ver_maps.winfo_x(),alto-ventana.winfo_height(),window=ventana_mapas,anchor='sw')
            self.opened_windows.append(i)
        self.but_ver_maps['command'] = mapas_buttons

        self.but_ver_tabs = tix.Button(ventana, text = 'TABs')
        #self.but_ver_tabs.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        self.but_ver_tabs.grid(row=0,column=grid_column)

        def tabs_buttons():
            self.close_windows()
            ventana_tabs = tix.Frame(w)
            #self.but_reports = tix.Button(ventana_tabs, text='Notificaciones',
            #                     command = acftnotices.show, state=DISABLED)
            #self.but_reports.grid(column=0,row=0,sticky=tix.E+tix.W)
            self.var_ver_desp_tab.set(master.dep_tabular.showed)
            self.var_ver_act_tab.set(master.act_tabular.showed)
            self.var_ver_arr_tab.set(master.arr_tabular.showed)
            self.but_departures = tix.Checkbutton(ventana_tabs, text='Despegues',variable=self.var_ver_desp_tab,
                                 command = master.dep_tabular.conmuta)
            self.but_departures.grid(column=0,row=1,sticky=tix.W)
            self.but_active = tix.Checkbutton(ventana_tabs, text='Activos',variable=self.var_ver_act_tab,
                                 command = master.act_tabular.conmuta)
            self.but_active.grid(column=0,row=2,sticky=tix.W)
            #
            self.but_arrivals = tix.Checkbutton(ventana_tabs, text='Llegadas',variable=self.var_ver_arr_tab,
                                 command = master.arr_tabular.conmuta)
            self.but_arrivals.grid(column=0,row=3,sticky=tix.W)
            #
            i=w.create_window(ventana.winfo_x()+self.but_ver_tabs.winfo_x(),alto-ventana.winfo_height(),window=ventana_tabs,anchor='sw')
            self.opened_windows.append(i)
        self.but_ver_tabs['command'] = tabs_buttons

        def cambia_vect_vel(e=None):
            master.change_speed_vector(self.speed_vector_var.get()/60.)
        cnt_vect_vel = tix.Control(ventana, label="Vel:", min=0, max=5, integer=1, command=cambia_vect_vel, variable=self.speed_vector_var)
        #cnt_vect_vel.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        cnt_vect_vel.grid(row=0,column=grid_column)

        def cambia_vel_reloj(e=None):
            try:
                master.sendMessage({"message":"clock_speed",
                                    "data": float(master.clock_speed_var.get())})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send clock_speed command", exc_info=True)
        cnt_vel_reloj = tix.Control(ventana, label="Reloj X:", min=0.5, max=99.0, step=0.1, command=cambia_vel_reloj, variable=master.clock_speed_var)
        #cnt_vel_reloj.pack(side=tix.LEFT,expand=1,fill=X)
        grid_column+=1
        cnt_vel_reloj.grid(row=0,column=grid_column)
		
        def toggle_radar_off(e=None):
            try:
                master.sendMessage({"message":"radar_off", "data": self.master.radar_off_var.get()})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send radar_off command", exc_info=True)
        but_radar_off = tix.Checkbutton(ventana, text = 'RADAR OFF', command=toggle_radar_off, variable = self.master.radar_off_var)
        grid_column+=1
        but_radar_off.grid(row=0,column=grid_column)

        def toggle_correlar_off(e=None):
            try:
                master.sendMessage({"message":"correlar_off", "data": self.master.correlar_off_var.get()})
            except:
                # TODO Tkinter will call this function at interface build time
                # before the sendMessage function has been created
                # and thus will always fail at first
                logging.debug("Unable to send correlar_off command", exc_info=True)
        but_correlar_off = tix.Checkbutton(ventana, text = 'CORRELAR OFF', command=toggle_correlar_off, variable = self.master.correlar_off_var)
        grid_column+=1
        but_correlar_off.grid(row=0,column=grid_column)

        but_l2_onoff = tix.Checkbutton(ventana, text = 'L2',command = self.master.reformat_labels, variable = self.master.l2_onoff_var)
        grid_column+=1
        but_l2_onoff.grid(row=0,column=grid_column)

        but_l3_onoff = tix.Checkbutton(ventana, text = 'L3',command = self.master.reformat_labels, variable = self.master.l3_onoff_var)
        grid_column+=1
        but_l3_onoff.grid(row=0,column=grid_column)

        but_l4_onoff = tix.Checkbutton(ventana, text = 'L4',command = self.master.reformat_labels, variable = self.master.l4_onoff_var)
        grid_column+=1
        but_l4_onoff.grid(row=0,column=grid_column)

        but_l5_onoff = tix.Checkbutton(ventana, text = 'L5',command = self.master.reformat_labels, variable = self.master.l5_onoff_var)
        grid_column+=1
        but_l5_onoff.grid(row=0,column=grid_column)

        self.toolbar_id=w.create_window(0,alto,width=ancho,window=ventana,anchor='sw')
        ventana.update_idletasks()

        #INCLUIR ETIQUETA FALT PARA DETERMINAR UN MINIMO Y UN MAXIMO DE ALTITUD
        #Minimo
        def selecciona_FALTmin (e=None):
            master.select_FALT_varmin=self.select_FALT_varmin.get()
        faltmin = tix.Control(ventana, label='FALT:', min=0, max=990, step=10, command=selecciona_FALTmin, variable=self.select_FALT_varmin)
        grid_column+=1
        faltmin.grid(row=0,column=grid_column)
        #Maximo
        def selecciona_FALTmax (e=None):
            master.select_FALT_varmax=self.select_FALT_varmax.get()
            #master.change_FALTmax(self.select_FALT_varmax.get())
        faltmax = tix.Control(ventana, label='', min=0, max=990, step=10, command=selecciona_FALTmax, variable=self.select_FALT_varmax)
        grid_column+=1
        faltmax.grid(row=0,column=grid_column)

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
                           position=(120,200), closebuttonhides=True)
        self._last_updated=0.
        self._flights=flights
        
    def update(self,t):
        """Check whether any new message should be printed"""
        # We need only update this tabular at most once a second
        if t-self._last_updated<1/60./60.:
            return
            
        # Check whether the pilots have anything to report.
        for acft in self._flights:
            for i,report in enumerate(acft.reports):
                if t>report['time']:
                    h=int(t)
                    m=int(60*(t-h))
                    report='%02d:%02d %s %s'%(h,m,acft.callsign,report['text'])
                    self.insert(tix.END, report)
                    self.notify()
                    del acft.reports[i]
        self._last_updated=t

    def notify(self):
        """Aviso sonoro de nueva notificacion (de GAMMA; antes se llamaba y no existia)."""
        import sys
        if sys.platform == 'win32':
            try:
                import winsound
                winsound.PlaySound(SNDDIR + '/chime.wav', winsound.SND_NOSTOP | winsound.SND_ASYNC)
            except Exception:
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
                eng_dir.focus_set()
                error = True
            else:
                if dir.upper() == 'S': dir = +1
                elif dir.upper() == 'B': dir = -1
                else: dir = 0
            if error:
                return False  # Validation failed
            self.radisplay.sendMessage({"message":"qnh",
                                    "qnh":self.qnh,
                                    "dir":dir})
        entries = [{'label':'QNH:','width':6,'def_value':"%.1f"%self.qnh}]
        entries.append({'label':'Sube(S)/Baja(B):','width':1,'def_value':''})
        RaDialog(self.radisplay.c,label='Modificar QNH',entries=entries, ok_callback=dialog_cb)    
