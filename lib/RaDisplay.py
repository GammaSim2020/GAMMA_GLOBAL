#!/usr/bin/python
# -*- coding:iso8859-15 -*-

"""Container module for the RaDisplay class, a generic radar display"""

from tkFont import Font

from twisted.internet import reactor, threads
import Tkinter as tk
import Tix as tix
import Aircraft

from RaElements import *
# from lib.osf.vfve_osf import RaBahia
from lib.osf.OSF import OSF
from lib.osf.PrevDesp import PrevDesp

conf = ConfMgr.GammaConfig()

FREEZE_STEPS = 5
freeze_countdown = {}


class RaDisplay(object):
    """Generic radar display in which tracks and lads are shown

    This class requires that a Tk session is already active
    """

    def __init__(self, conf, title, icon_path, fir, tlpv, sector, toolbar_height, disp_number, display_client=None):
        """Instantiate a generic Radar Display

        title - window title
        icon_path - path to the windows task bar icon
        fir -- fir object
        sector -- name of the sector to work with
        """

        self.fir = fir
        Aircraft.fir = fir  # Rather than passing globals

        tlpv.fir = fir
        self.tlpv = tlpv
        self.orient = 'north'
        self.refresco = 5.
        self.field_up = fir.field_up
        self.twr = 'este'  # Used if more than one control tower (e.g. LEBL)
        self.fov = 360
        self.conf = conf

        self.display_remote = []

        self.disp_number = disp_number
        layout_str = "Layout" + str(self.disp_number)
        self.geometry = self.conf.read_option(layout_str, "geometry", '0x0+0+0', 'string')
        self.orient = self.conf.read_option(layout_str, "orientation", 'north', 'string')
        self.filterFGND = self.conf.read_option(layout_str, "filterFGND", True, "bool")

        self.scale = self.conf.read_option(layout_str, "scale", 1.0, 'float')

        self.select_FALT_varmin = tk.DoubleVar()

        self.select_FALT_varmin.set(self.conf.read_option(layout_str, "select_FALT_varmin", 1, 'float'))

        self.select_FALT_varmax = tk.DoubleVar()
        self.select_FALT_varmax.set(self.conf.read_option(layout_str, "select_FALT_varmax", 990, 'float'))

        self.center_y = self.conf.read_option(layout_str, "center_y", 0.0, 'float')
        self.center_x = self.conf.read_option(layout_str, "center_x", 0.0, 'float')
        # self.x0=self.conf.read_option(layout_str,"origin_x",0.0,'float')
        # self.y0=self.conf.read_option(layout_str,"origin_y",0.0,'float')
        self.x0 = 0
        self.y0 = 0

        self.maps = {}  # Dictionary of map objects

        if self.mode == 'pp':
            self.draw_point_names = self.conf.read_option("Maps", "Point_names", True, "bool")
            self.draw_point = self.conf.read_option("Maps", "Points", True, "bool")
            self.draw_routes = self.conf.read_option("Maps", "Routes", True, "bool")
            self.draw_sector = self.conf.read_option("Maps", "Sector", True, "bool")
            self.draw_lim_sector = self.conf.read_option("Maps", "Lim_sector", True, "bool")
            self.draw_tmas = self.conf.read_option("Maps", "TMAs", True, "bool")
            self.draw_deltas = self.conf.read_option("Maps", "Deltas", True, "bool")
            self.sector = sector
            if self.orient.upper() == 'FIELD':
                self.refresco = 1.
            else:
                self.refresco = 5.
        else:
            self.draw_point_names = False
            self.draw_point = False
            self.draw_routes = False
            self.draw_sector = False
            self.draw_lim_sector = False
            self.draw_tmas = False
            self.draw_deltas = False

            self.sector = self.conf.read_option(layout_str, "sector", sector, 'string')
            if not all(s in fir.sectors for s in self.sector.split(',')):
                self.sector = fir.sectors[0] if fir.sectors else sector

            # if self.filterFGND:
            #     self.refresco = 1.
            # else:
            #     self.refresco = 5.

        self.sector_list = self.sector.split(',')
        # We are not using these maps any more
        self.draw_routes = self.draw_tmas = self.draw_deltas = False

        # Restaurar mapas activos desde la configuración guardada
        active_maps_str = self.conf.read_option(layout_str, "active_maps", "[]", 'string')
        try:
            # Convertir string a lista (la configuración guarda listas como string)
            import ast
            self.local_maps_shown = ast.literal_eval(active_maps_str)
            if not isinstance(self.local_maps_shown, list):
                self.local_maps_shown = []
        except:
            self.local_maps_shown = []

        self.top_level = tix.Toplevel()
        tl = self.top_level

        if sys.platform.startswith('win'):
            tl.wm_iconbitmap(icon_path)

        tl.wm_title('GammaSim_' + str(disp_number) + "_" + conf.ver + ': ' + title)

        SmartColor.winfo_rgb = tl.winfo_rgb  # SmartColors needs a valid winfo_rgb function
        # which is only available once Tkinter
        # in initialized

        self.screen_width = tl.winfo_screenwidth()
        self.screen_height = tl.winfo_screenheight()
        # screen_width = self.screen_width
        # screen_height = self.screen_height
        # tl.wm_geometry("%dx%d+%d+%d" % (screen_width, screen_height, screen_width, 0))
        # tl.wm_geometry("%dx%d+%d+%d" % (0, 0, screen_width, 0))
        tl.wm_geometry(self.geometry)
        tl.update_idletasks()
        tl.wm_state('zoomed')
        tl.update_idletasks()
        self.c = c = tix.Canvas(tl, bg='gray3')
        # self.c = c = tix.Canvas(tl,bg='white')
        c.pack(expand=1, fill=tix.BOTH)
        ra_bind(self, c, '<Configure>', self.change_size)

        # Used to prevent the Display update code to be run nested
        self.updating = False
        # Used to prevent the label separation code to be run nested
        self.separating_labels = False
        # Same thing with the STCA code
        self.stca_running = False

        # Screen parameters
        self.width = tl.winfo_width()
        self.height = tl.winfo_height()
        self.toolbar_height = toolbar_height
        # self.center_x=self.width/2
        # self.center_y=(self.height-self.toolbar_height)/2

        # Now the scale and center are read from Gamma.ini file
        # World coordinates parameters
        # self.x0=0.  # x0 and y0 define the center of the sector to display
        # self.y0=0.  # in world coordinates
        # self.scale=1.0  # Scale factor between screen and world coordinates
        # self.get_scale() # Calculate initial x0, y0 and scale

        self.auto_separation = True  # Separate labels automatically
        self.correlar_off = False
        self.radar_off = False
        self.pac = True
        self.vac = True  # Avisos de conflicto VAC (boton AC de 3 estados)

        VisTrack.timer_id = None  # Reset the VisTrack class
        self.tracks = []  # List of tracks (VisualTrack instances)
        self.selected_track = None
        self.selected_flight = None
        self.lads = []  # List of LADs
        self.geotabs = []  # List of GEOTABs
        self.cancel_lad_serial = -1
        self.cancel_geotab_serial = -1  # To be used to cancel lad creation after middle clicking some virtual track label item
        self.latest_processed_serial = -1  # Generally used to avoid double actions
        self.defining_lad = False

        self.selected_fs = None

        self.pos_number = None  # Radar position number (identifies this radar display)

        self.lcl_sector_list = [lcl for lcl in self.sector_list if "TWR" in lcl]

        self.label_font_size = 11
        self.label_font = Font(family="Helvetica", size=self.label_font_size)
        # self.label_moved = False  # Whether a label has recently been manually moved

        ra_bind(self, self.c, '<Button-1>', self.b1_cb)
        ra_bind(self, self.c, '<Button-2>', self.b2_cb)
        ra_bind(self, self.c, '<Button-3>', self.b3_cb)

        self.delete_pressed = False
        self.ojeo = False
        self.c.master.bind('<KeyPress-Delete>', self.delete_press)
        self.c.master.bind('<KeyRelease-Delete>', self.delete_release)
        self.c.master.bind('<F5>', self.toggle_ojeo)

        self.c.master.bind('<Pause>', self.b_parar)
        self.c.master.bind('<Home>', self.b_inicio)

        # self.c.master.bind( '<MouseWheel>', self.b2_mw)
        self.c.master.bind('<F1>', self.f1)
        self.c.master.bind('<F2>', self.f2)
        self.c.master.bind('<F3>', self.f3)
        self.c.master.bind('<Control-F1>', self.cf1)
        self.c.master.bind('<Control-F2>', self.cf2)
        self.c.master.bind('<Control-F3>', self.cf3)

        self.c.master.bind('<Alt-w>', self.swap_background)

        self.intensity = {"GLOBAL": self.conf.read_option("Brightness", "GLOBAL", 1.0, "float"),
                          "TRACKS": self.conf.read_option("Brightness", "TRACKS", 1.0, "float"),
                          "MAP": self.conf.read_option("Brightness", "MAP", 0.35, "float"),
                          "LADS": self.conf.read_option("Brightness", "LADS", 1.0, "float")}

        self.rabrightness = RaBrightness(c, self.set_element_intensity, self.intensity, position=(self.width * 0.4, self.height * 0.8))
        self.rabrightness.hide()

    def b_inicio(self, e=None):
        self.sendMessage({"message": "play"})

    def b_parar(self, e=None):
        self.sendMessage({"message": "pause"})

    def swap_background(self, e=None):
        self.c.configure(background='white')

    def change_size(self, e):
        self.width = e.width
        self.height = e.height
        self.c.update_idletasks()

    def change_speed_vector(self, minutes, e=None):
        for track in self.tracks:
            track.speed_vector_length = minutes

    def vt_handler(self, vt, item, action, value, e=None):
        """Handle events raised by visual tracks
        Visual tracks have their own GUI code to present the user
        with CFL and ECL dialog, for instance, but then they notify the parent
        about the result using this function"""
        if e is not None:
            self.cancel_geotab_serial = e.serial
        if action == "precall": return
        if action == "<Button-2>" and item != 'plot':
            self.cancel_lad_serial = e.serial
        pass
        if item == 'cs':
            if action == '<Button-1>':
                # if not vt.assumed or vt.flashing:
                #     vt.assumed

                m = {"message": "assume", "cs": vt.cs, "sector": self.sector,
                     "assumed": not vt.assumed or vt.flashing}
                # If flashing or not yet assumed always assume the traffic.
                self.sendMessage(m)
            #            elif action=='<Motion>':
            #                self.label_moved = True
            elif action == '<ButtonRelease-2>':
                f = self._tracks_flights[vt]
                if self.mode == 'pp':
                    self.show_hide_way_point(f)
                else:
                    self.toggle_select(f)

        elif item == 'leader':
            if action == '<Button-1>' or action == '<Button-3>':
                reactor.callInThread(self.separate_labels, vt)
        elif item == 'transfer':
            m = {"message": "transfer", "cs": vt.cs}
            self.sendMessage(m)
        elif item == 'set_echo':
            m = {"message": "set_echo", "cs": vt.cs, "echo": value}
            self.sendMessage(m)

    def b1_cb(self, e=None):
        pass

    def b2_cb(self, e=None):
        self.def_lad(e)

    def b3_cb(self, e=None):
        pass

    def b2_mw(self, e=None):
        # Zoom con la rueda: se puede desactivar en el pseudopiloto (casilla WheelMouse)
        if hasattr(self, 'mouse_wheel_enabled_var') and not self.mouse_wheel_enabled_var.get():
            return
        if e.delta < 0:
            inc_s = 0.9
        elif e.delta > 0:
            inc_s = 1.1
        else:
            inc_s = 1
        # Apply scale factor to scale around the center of the sector
        self.scale *= inc_s
        # Opt.1 Displace the map to simulate scaling around the center of the screen
        # self.center_x += (1-inc_s) * (0.5*self.width-self.center_x)
        # self.center_y += (1-inc_s) * (0.5*(self.height-40.)-self.center_y)
        # Opt.2 Displace the map to simulate scaling around the cursor position
        # JRAR self.top_level.winfo_x() corrects multi-display variation
        self.center_x += (1 - inc_s) * (e.x_root - self.top_level.winfo_x() - self.center_x)
        self.center_y += (1 - inc_s) * (e.y_root - self.top_level.winfo_y() - self.center_y - 20.)
        self.reposition()

    def b2_mw_future(self, e=None):
        porcentaje = 0.1
        factorescala = 0
        x = self.c.canvasx(e.x)
        y = self.c.canvasy(e.y)
        if e.delta > 0:
            factorescala = 1 + porcentaje
        elif e.delta < 0:
            factorescala = 1 - porcentaje
        self.c.scale("all", 0, 0, factorescala, factorescala)
        self.scale = self.scale * factorescala
        self.c.scan_mark(int(x * factorescala), int(y * factorescala))
        self.c.scan_dragto(int(x), int(y), gain=1)

    def delete_press(self, e=None):
        self.delete_pressed = True

    def delete_release(self, e=None):
        self.delete_pressed = False

    def toggle_ojeo(self, e=None):
        self.ojeo = not self.ojeo

    def f1(self, e=None):
        self.scale = self.f1scale
        self.center_x = self.f1center_x
        self.center_y = self.f1center_y
        self.reposition()

    def cf1(self, e=None):
        self.f1scale = self.scale
        self.f1center_x = self.center_x
        self.f1center_y = self.center_y

    def f2(self, e=None):
        self.scale = self.f2scale
        self.center_x = self.f2center_x
        self.center_y = self.f2center_y
        self.reposition()

    def cf2(self, e=None):
        self.f2scale = self.scale
        self.f2center_x = self.center_x
        self.f2center_y = self.center_y

    def f3(self, e=None):
        self.scale = self.f3scale
        self.center_x = self.f3center_x
        self.center_y = self.f3center_y
        self.reposition()

    def cf3(self, e=None):
        self.f3scale = self.scale
        self.f3center_x = self.center_x
        self.f3center_y = self.center_y

    def grab_display(self, e=None):
        # Arrastre de pantalla: se puede desactivar en el pseudopiloto (casilla GrabDisplay)
        if hasattr(self, 'grab_display_enabled_var') and not self.grab_display_enabled_var.get():
            return
        # No se estaba definiendo un LAD. Comenzar a definir uno
        self.e_grabbed = e
        ra_unbind(self, self.c, '<Motion>')
        ra_unbind(self, self.c, '<ButtonRelease-1>')
        ra_bind(self, self.c, '<Motion>', self.move_display)
        ra_bind(self, self.c, '<ButtonRelease-1>', self.release_display)

    def release_display(self, e=None):
        # No se estaba definiendo un LAD. Comenzar a definir uno
        self.e_grabbed = e
        ra_unbind(self, self.c, '<Motion>')
        ra_unbind(self, self.c, '<ButtonRelease-1>')

    def move_display(self, e=None):
        # master.x0 -= ancho/set_displacement(event.num)/scale
        self.center_x += e.x - self.e_grabbed.x
        self.center_y += e.y - self.e_grabbed.y
        self.reposition()
        self.e_grabbed = e

    def def_lad(self, e=None):
        # if self.mode == 'pp': return  ##########Temporaly disable the lad for pseudopilot
        if e.serial == self.cancel_lad_serial or self.defining_lad: return
        self.defining_lad = True
        LAD(self, e)

    def delete_lads(self, e=None):
        for lad in self.lads[:]:
            lad.delete()

    def update(self):
        # Tracks are updated by the superclass when it gives them the new coords
        self.update_lads()
        self.update_fprs()
        self.update_geotabs()
        # Parametros de escenario 'stca' y 'separar_etiquetas' (por defecto desactivados en LEMD y LEBL por rendimiento)
        if not self.stca_running:
            if self.fir.param('stca', True):
                reactor.callInThread(self.update_stca)
            if self.fir.param('separar_etiquetas', True):
                reactor.callInThread(self.separate_labels)

    def toggle_auto_separation(self):
        self.auto_separation = not self.auto_separation
        if self.auto_separation:
            reactor.callInThread(self.separate_labels)
    
    #Antes sin algoritmo de spatial hashing
    """
    def separate_labels(self, single_track=None):
        tracks = self.tracks
        width, height = self.width, self.height
        canvas = self.c
        if not self.auto_separation or self.separating_labels: return
        self.separating_labels = True
        self.stop_separating = False

        # Find the tracks that we have to separate
        sep_list = []  # List of track whose labels we must separate
        for track in tracks:
            x, y = track.label_x, track.label_y
            h, w = track.label_height, track.label_width
            if not track.visible or track.plot_only or x < 0 or y < 0 or x + w > width or y + h > height:
                continue
            sep_list.append(track)

        def compute_label_clearance(x1, y1, sw1, sh1, x2, y2, sw2, sh2):
            # Compute horizontal and vertical clearance space between labels
            # First compute horizontal and vertical distance between centers
            dx = x2 - x1
            dy = y2 - y1
            # Then compare to sum of semi-widths and semi-heights
            x_clear = abs(dx) - sw1 - sw2
            y_clear = abs(dy) - sh1 - sh2
            # return best clearance. Negative means there is overlap
            return max(x_clear, y_clear)

        # Find intersecting labels and select the worst pair
        lowest_clearance = 0
        worst_pair = 0, 0
        for i in range(len(sep_list)):
            ti = sep_list[i]  # Track i
            if ti in freeze_countdown.keys(): continue
            # Use label center coordinates and semi-width and semi-height to compute
            # horizontal and vertical clearance space between labels
            swi, shi = 0.5 * ti.label_width, 0.5 * ti.label_height
            xci, yci = ti.label_x + swi, ti.label_y + shi
            for j in range(i + 1, len(sep_list)):
                tj = sep_list[j]  # Track j
                if tj in freeze_countdown.keys(): continue
                if single_track and ti != single_track and tj != single_track: continue
                swj, shj = 0.5 * tj.label_width, 0.5 * tj.label_height
                xcj, ycj = tj.label_x + swj, tj.label_y + shj
                # If the caller provided a specific track as an argument, we only want
                # to separate that label. Else try to separate everything
                clearance_ij = compute_label_clearance(xci, yci, swi, shi, xcj, ycj, swj, shj)
                if clearance_ij < lowest_clearance:
                    lowest_clearance = clearance_ij
                    worst_pair = i, j

        # Solve the worst conflict, if any
        new_pos = {}
        if lowest_clearance < 0:
            i, j = worst_pair
            ti = sep_list[i]
            tj = sep_list[j]
            xi, yi = ti.x, ti.y
            xj, yj = tj.x, tj.y
            relative_heading = atan2(yj - yi, xj - xi)
            # JRAR: New positions set labels in opposite directions
            xi_l = xi - ti.label_radius * cos(relative_heading)
            if xi_l < xi: xi_l -= ti.label_width
            yi_l = yi - ti.label_radius * sin(relative_heading)
            xj_l = xj + tj.label_radius * cos(relative_heading)
            if xj_l < xj: xj_l -= tj.label_width
            yj_l = yj + tj.label_radius * sin(relative_heading)
            # JRAR: Avoid moving to a position that is worst than current
            # Check clearance for new positions
            move_flag_i = True
            move_flag_j = True
            swi, shi = 0.5 * ti.label_width, 0.5 * ti.label_height
            xci, yci = xi_l + swi, yi_l + shi
            swj, shj = 0.5 * tj.label_width, 0.5 * tj.label_height
            xcj, ycj = xj_l + swj, yj_l + shj
            for m in range(len(sep_list)):
                if m == i or m == j:
                    continue
                tm = sep_list[m]
                swm, shm = 0.5 * tm.label_width, 0.5 * tm.label_height
                xcm, ycm = tm.label_x + swm, tm.label_y + shm
                clearance_im = compute_label_clearance(xci, yci, swi, shi, xcm, ycm, swm, shm)
                if clearance_im < lowest_clearance:
                    move_flag_i = False
                clearance_jm = compute_label_clearance(xcj, ycj, swj, shj, xcm, ycm, swm, shm)
                if clearance_jm < lowest_clearance:
                    move_flag_j = False
            if move_flag_i:
                new_pos[ti] = (xi_l, yi_l)
            if move_flag_j:
                new_pos[tj] = (xj_l, yj_l)
            # JRAR: avoid dealing with the same labels for several steps
            # This prevents "zig-zag" and gives opportunity to deal with other pairs
            freeze_countdown[ti] = FREEZE_STEPS + 1
            freeze_countdown[tj] = FREEZE_STEPS + 1
        for t in freeze_countdown.keys():
            freeze_countdown[t] -= 1
            if freeze_countdown[t] == 0:
                del freeze_countdown[t]

        # Once we have reached the result, we can't really update the labels from
        # here, because Tkinter is not thread safe
        def move_labels(move_list):
            # Update the labels
            if not self.stop_separating:
                for t in move_list:
                    (x, y) = new_pos[t]
                    t.label_coords(x, y)
            self.separating_labels = False

        # We make sure that the label moving is done from the main thread and event loop
        reactor.callFromThread(move_labels, new_pos.keys())
    """
    #Ahora con algoritmo mejorado de spatial hashing + spatial grid
    def separate_labels(self, single_track=None):
        """Separación optimizada con Spatial Hashing"""

        # Configuración inicial (sin cambios)
        tracks = self.tracks
        width, height = self.width, self.height
        if not self.auto_separation or self.separating_labels:
            return
        self.separating_labels = True
        self.stop_separating = False

        # Filtrar tracks visibles
        sep_list = []
        for track in tracks:
            x, y = track.label_x, track.label_y
            h, w = track.label_height, track.label_width
            if not track.visible or track.plot_only or x < 0 or y < 0 or x + w > width or y + h > height:
                continue
            sep_list.append(track)

        # =================================================================
        # OPTIMIZACIÓN: Crear Spatial Grid
        # =================================================================
        grid = self._create_spatial_grid(sep_list, width, height)

        # Función auxiliar (sin cambios)
        def compute_label_clearance(x1, y1, sw1, sh1, x2, y2, sw2, sh2):
            dx = x2 - x1
            dy = y2 - y1
            x_clear = abs(dx) - sw1 - sw2
            y_clear = abs(dy) - sh1 - sh2
            return max(x_clear, y_clear)

        # =================================================================
        # PARTE 1 OPTIMIZADA: Buscar solapamientos solo en celdas cercanas
        # Antes: O(N²) con 1,225 comparaciones
        # Ahora: O(N) con ~400 comparaciones
        # =================================================================
        lowest_clearance = 0
        worst_pair = None

        # Iterar sobre celdas del grid (constante: 100 celdas)
        for cell_key, labels_in_cell in grid.items():
            # A) Comparar labels dentro de la misma celda
            for i in range(len(labels_in_cell)):
                ti = labels_in_cell[i]
                if ti in freeze_countdown.keys():
                    continue
                
                swi, shi = 0.5 * ti.label_width, 0.5 * ti.label_height
                xci, yci = ti.label_x + swi, ti.label_y + shi

                # Comparar con otros labels en MISMA celda
                for j in range(i + 1, len(labels_in_cell)):
                    tj = labels_in_cell[j]
                    if tj in freeze_countdown.keys():
                        continue
                    if single_track and ti != single_track and tj != single_track:
                        continue
                    
                    swj, shj = 0.5 * tj.label_width, 0.5 * tj.label_height
                    xcj, ycj = tj.label_x + swj, tj.label_y + shj

                    clearance_ij = compute_label_clearance(xci, yci, swi, shi, xcj, ycj, swj, shj)
                    if clearance_ij < lowest_clearance:
                        lowest_clearance = clearance_ij
                        worst_pair = (ti, tj)

                # B) Comparar con labels en celdas ADYACENTES
                for adj_cell_key in self._get_adjacent_cells(cell_key, grid):
                    for tj in grid[adj_cell_key]:
                        if tj in freeze_countdown.keys():
                            continue
                        if single_track and ti != single_track and tj != single_track:
                            continue
                        
                        swj, shj = 0.5 * tj.label_width, 0.5 * tj.label_height
                        xcj, ycj = tj.label_x + swj, tj.label_y + shj

                        clearance_ij = compute_label_clearance(xci, yci, swi, shi, xcj, ycj, swj, shj)
                        if clearance_ij < lowest_clearance:
                            lowest_clearance = clearance_ij
                            worst_pair = (ti, tj)

        # =================================================================
        # PARTE 2 OPTIMIZADA: Validar nuevas posiciones solo contra cercanas
        # Antes: O(N) con 50 comparaciones
        # Ahora: O(1) con ~5 comparaciones
        # =================================================================
        new_pos = {}
        if lowest_clearance < 0 and worst_pair:
            ti, tj = worst_pair
            xi, yi = ti.x, ti.y
            xj, yj = tj.x, tj.y
            relative_heading = atan2(yj - yi, xj - xi)

            # Calcular nuevas posiciones (sin cambios)
            xi_l = xi - ti.label_radius * cos(relative_heading)
            if xi_l < xi:
                xi_l -= ti.label_width
            yi_l = yi - ti.label_radius * sin(relative_heading)

            xj_l = xj + tj.label_radius * cos(relative_heading)
            if xj_l < xj:
                xj_l -= tj.label_width
            yj_l = yj + tj.label_radius * sin(relative_heading)

            # OPTIMIZACIÓN: Validar solo contra labels CERCANAS
            move_flag_i = True
            move_flag_j = True

            swi, shi = 0.5 * ti.label_width, 0.5 * ti.label_height
            xci, yci = xi_l + swi, yi_l + shi
            swj, shj = 0.5 * tj.label_width, 0.5 * tj.label_height
            xcj, ycj = xj_l + swj, yj_l + shj

            # Obtener labels cercanas a las nuevas posiciones
            nearby_labels_i = self._get_nearby_labels(grid, xi_l, yi_l)
            nearby_labels_j = self._get_nearby_labels(grid, xj_l, yj_l)

            # Validar ti contra labels cercanas (en lugar de TODOS)
            for tm in nearby_labels_i:
                if tm == ti or tm == tj:
                    continue
                swm, shm = 0.5 * tm.label_width, 0.5 * tm.label_height
                xcm, ycm = tm.label_x + swm, tm.label_y + shm
                clearance_im = compute_label_clearance(xci, yci, swi, shi, xcm, ycm, swm, shm)
                if clearance_im < lowest_clearance:
                    move_flag_i = False
                    break
                
            # Validar tj contra labels cercanas (en lugar de TODOS)
            for tm in nearby_labels_j:
                if tm == ti or tm == tj:
                    continue
                swm, shm = 0.5 * tm.label_width, 0.5 * tm.label_height
                xcm, ycm = tm.label_x + swm, tm.label_y + shm
                clearance_jm = compute_label_clearance(xcj, ycj, swj, shj, xcm, ycm, swm, shm)
                if clearance_jm < lowest_clearance:
                    move_flag_j = False
                    break
                
            # Aplicar movimientos si son válidos
            if move_flag_i:
                new_pos[ti] = (xi_l, yi_l)
            if move_flag_j:
                new_pos[tj] = (xj_l, yj_l)

            freeze_countdown[ti] = FREEZE_STEPS + 1
            freeze_countdown[tj] = FREEZE_STEPS + 1

        # Decrementar freeze countdown
        for t in freeze_countdown.keys():
            freeze_countdown[t] -= 1
            if freeze_countdown[t] == 0:
                del freeze_countdown[t]

        # Mover labels (sin cambios)
        def move_labels(move_list):
            if not self.stop_separating:
                for t in move_list:
                    (x, y) = new_pos[t]
                    t.label_coords(x, y)
            self.separating_labels = False

        reactor.callFromThread(move_labels, new_pos.keys())

    # =================================================================
    # MÉTODOS AUXILIARES PARA SPATIAL GRID
    # =================================================================
    def _create_spatial_grid(self, tracks, width, height):
        """
        Crea un grid espacial con los tracks.
        Returns: dict {(col, row): [lista de tracks]}
        """
        cell_size = 100  # Tamaño de celda en pixels
        grid = {}
        
        for track in tracks:
            # Calcular celda del track
            col = int(track.label_x / cell_size)
            row = int(track.label_y / cell_size)
            cell_key = (col, row)
            
            # Agregar track a la celda
            if cell_key not in grid:
                grid[cell_key] = []
            grid[cell_key].append(track)
        
        return grid
    
    def _get_adjacent_cells(self, cell_key, grid):
        """
        Obtiene las celdas adyacentes a una celda dada.
        Returns: lista de keys de celdas adyacentes que existen en el grid
        """
        col, row = cell_key
        adjacent = []
        
        for dc in [-1, 0, 1]:
            for dr in [-1, 0, 1]:
                if dc == 0 and dr == 0:
                    continue
                adj_key = (col + dc, row + dr)
                if adj_key in grid:
                    adjacent.append(adj_key)
        
        return adjacent
    
    def _get_nearby_labels(self, grid, x, y):
        """
        Obtiene todos los labels cerca de una posición (x, y).
        Returns: lista de tracks cercanos
        """
        cell_size = 100
        col = int(x / cell_size)
        row = int(y / cell_size)
        cell_key = (col, row)
        
        nearby = []
        
        # Labels en la misma celda
        if cell_key in grid:
            nearby.extend(grid[cell_key])
        
        # Labels en celdas adyacentes
        for adj_key in self._get_adjacent_cells(cell_key, grid):
            nearby.extend(grid[adj_key])
        
        return nearby
    
    
    def update_stca(self):
        """Process short term collision alert"""
        # Calculate each track's position in 30 and 60 seconds

        if self.stca_running:
            logging.warning("update_stca has been called when it was already running.\nWe are falling behind on the processing, and alerts may not be accurate")
            return

        self.stca_running = True
        t_alerts = {}  # Alert status for each track
        NONE = 0
        PAC  = 2
        VAC  = 4

        flying_tracks = [vt_aux for vt_aux in self.tracks if (self._tracks_flights[vt_aux].pof == Aircraft.FLYING)]

        for track in flying_tracks:
            if not track.visible:
                continue
            track.future_pos = []
            t_alerts[track] = NONE
            delta = 1./60./6  # delta = 10s
            # for t in [delta, delta*2, delta*3, delta*4, delta*5, delta*6]:
            for t in [delta*2, delta*3, delta*4, delta*5, delta*6]:
                gtx = sin(radians(track.track))  # Ground track projection on x
                gty = cos(radians(track.track))  # Ground track projection on y
                (x, y, alt) = (track.wx, track.wy, track.alt)  # Current position
                gs = track.gs  # Ground speed
                nx = x + gs*t*gtx  # Future x coord in t hours
                ny = y + gs*t*gty  # Future y coord in t hours
                nalt = alt + track.rate*t
                track.future_pos.append((nx, ny, nalt))

        try: min_sep = self.fir.min_sep[self.sector.split(",")[0]]
        except:
            min_sep = 8.0  # 8 nautical miles
            logging.warning("Sector minimum separation not found. Using 8nm")
        min_sep2 = min_sep*min_sep
        minvert = 9.5  # 950 feet minimum vertical distance

        # Vertical filter
        vfilter = max([ad.val_elev for ad in self.fir.aerodromes.values()]) + 1  # 1000 feet over the highest AD

        for i in range(len(flying_tracks)):
            ti = flying_tracks[i]
            if not getattr(self, 'vac', True):
                continue  # boton AC en rojo: sin avisos VAC ni STCA
            if not ti.visible:
                continue
            if ti.alt < vfilter:
                continue
            for j in range(i+1, len(flying_tracks)):
                tj = flying_tracks[j]
                distx = ti.wx-tj.wx
                disty = ti.wy-tj.wy
                if not tj.visible:
                    continue
                if tj.alt < vfilter:
                    continue
                # First sieve: vertical distance
                distalt = ti.alt-tj.alt
                if abs(distalt) < minvert:
                    # Second sieve: x distance
                    distx2 = distx * distx
                    if distx2 < min_sep2:
                        # Third sieve: y distance
                        disty2 = disty * disty
                        if disty2 < min_sep2:
                            # Test for conflict
                            # ix,iy,jx,jy = ti.wx,ti.wy,tj.wx,tj.wy
                            # dist=sqrt((ix-jx)**2+(iy-jy)**2)

                            # Final check: Compare squared distances instead of distances for computing efficiency (save time consuming square root computation)
                            dist2 = distx2+disty2
                            # if dist2<min_sep2 and abs(ti.alt-tj.alt)<minvert:
                            if dist2 < min_sep2:
                                t_alerts[ti] |= VAC
                                t_alerts[tj] |= VAC
                                continue

                # STCA
                if not self.pac:
                    continue

                ix_60, iy_60, ialt_60 = ti.future_pos[4]
                jx_60, jy_60, jalt_60 = tj.future_pos[4]
                # First sieve: vertical distance still larger than minimum and no crossing
                distalt_60 = ialt_60 - jalt_60
                if abs(distalt_60) < minvert or (distalt_60 * distalt) < 0:
                    # Second sieve: x distance, distance still larger than minimum and no crossing
                    distx_60 = ix_60-jx_60
                    distx2_60 = distx_60 * distx_60
                    if distx2_60 < min_sep2 or (distx_60 * distx) < 0:
                        # Third sieve: y distance, distance still larger than minimum and no crossing
                        disty_60 = iy_60-jy_60
                        disty2_60 = disty_60 * disty_60
                        if disty2_60 < min_sep2 or (disty_60 * disty) < 0:
                            t_alerts[ti] |= PAC
                            t_alerts[tj] |= PAC
                            break
                            # Final check (sampling at 10 sec interval)
                           # for ((ix, iy, ialt),(jx, jy, jalt)) in zip(ti.future_pos, tj.future_pos):
                                # dist=sqrt((ix-jx)**2+(iy-jy)**2)
                           #     if ialt > vfilter and jalt > vfilter and abs(ialt-jalt)<minvert:
                           #         dist2=(ix-jx)*(ix-jx)+(iy-jy)*(iy-jy)
                           #         if dist2<min_sep2:
                           #             t_alerts[ti] |= PAC
                           #             t_alerts[tj] |= PAC
                           #             break
        self.stca_running = False
        # Once we have reached the result, we can't really update the labels from
        # here, because Tkinter is not thread safe

        def set_track_alerts():
            # Update the labels
            for t, v in t_alerts.items():
                if v & PAC: t.pac = True
                else: t.pac = False
                if v & VAC: t.vac = True
                else: t.vac = False
            self.stca_running = False

        # We make sure that the label updating is done from the main thread and event loop
        reactor.callFromThread(set_track_alerts)

    def update_lads(self):
        # A lad might be deleted, so we need to iterate over a copy of the list
        for lad in self.lads[:]:
            lad.redraw()

    def update_fprs(self):
        r = self.routes[:]
        w = self.waypoints[:]
        self.delete_routes()
        for track in r:
            self.draw_fpr(track)
        # for track in w:
        #    self.draw_way_point(track)

    def update_geotabs(self):
        # A lad might be deleted, so we need to iterate over a copy of the list
        for geotab in self.geotabs[:]:
            geotab.redraw()

    def get_scale(self):
        """Calculates the display center and the scale to display it all"""
        xmax = -1.e8
        xmin = 1.e8
        ymax = -1.e8
        ymin = 1.e8
        for a in self.fir.boundaries[self.sector.split(",")[0]]:
            if a[0] > xmax:
                xmax = a[0]
            if a[0] < xmin:
                xmin = a[0]
            if a[1] > ymax:
                ymax = a[1]
            if a[1] < ymin:
                ymin = a[1]
        self.x0 = (xmax + xmin) / 2
        self.y0 = (ymax + ymin) / 2
        x_scale = self.width / (xmax - xmin)
        y_scale = (self.height - self.toolbar_height) / (ymax - ymin)
        self.scale = min(x_scale, y_scale) * 0.9

    def redraw_maps(self):

        c = self.c  # Canvas
        fir = self.fir
        sector = self.sector
        do_scale = self.do_scale

        # Delete Map objects
        for map in self.maps.values():
            map.destroy()
        self.maps = {}

        # Create Map Objects

        map_intensity = self.intensity["GLOBAL"] * self.intensity["MAP"]

        # Currect sector background
        sectormap = RaMap(self.c, self.do_scale, intensity=map_intensity)
        kw = {'color': 'black'}
        sector_list = self.sector.split(",")
        for sector in sector_list:
            sectormap.add_polygon(*fir.boundaries[sector], **kw)
        self.maps['sector'] = sectormap
        if not self.draw_sector: sectormap.hide()

        # TMAs
        # map = RaMap(self.c, self.do_scale, intensity = map_intensity)
        # kw = {'color': 'gray30'}
        # for tma in fir.tmas:
        #    map.add_polyline(*tma, **kw)
        # self.maps['tmas'] = map
        # if not self.draw_tmas: map.hide()

        # Airways
        # map = RaMap(self.c, self.do_scale, intensity = map_intensity)
        # kw = {'color': 'gray25'}
        # for airway in fir.airways:
        #    map.add_polyline(*airway, **kw)
        # self.maps['airways'] = map
        # if not self.draw_routes: map.hide()

        # Taxiways
        # map = RaMap(self.c, self.do_scale, intensity = map_intensity)
        # kw = {'color': 'gray25'}
        # for taxiway in fir.taxiways:
        #    map.add_polyline(*taxiway, **kw)
        # self.maps['taxiways'] = map
        # if not self.draw_routes: map.hide()

        # Special Use Areas
        # map = RaMap(self.c, self.do_scale, intensity = map_intensity)
        # kw = {'color': 'gray40'}
        # for delta in fir.deltas:
        #  map.add_polyline(*delta, **kw)
        # self.maps['SUA'] = map
        # if not self.draw_deltas: map.hide()

        # Fixes (VORs, NDBs, FIXes)
        map = RaMap(self.c, self.do_scale, intensity=map_intensity)
        if self.mode == 'pp':
            for p in [(key, value) for key, value in fir.coords.items() if key[:2] != '__']:
                if p[0] in fir.iafs:
                    fix_color = 'yellow'
                else:
                    fix_color = 'gray40'
                if len(p[0]) == 3:
                    map.add_symbol(VOR, p[1], color=fix_color)
                elif len(p[0]) == 2:
                    map.add_symbol(NDB, p[1], color=fix_color)
                else:
                    map.add_symbol(FIX, p[1], color=fix_color)
        else:
            for p in [(key, value) for key, value in fir.coords.items() if key[0] != '_']:
                if len(p[0]) == 3:
                    map.add_symbol(VOR, p[1], color='gray40')
                elif len(p[0]) == 2:
                    map.add_symbol(NDB, p[1], color='gray40')
                else:
                    map.add_symbol(FIX, p[1], color='gray40')
        self.maps['points'] = map
        if not self.draw_point: map.hide()

        # Fix names
        map = RaMap(self.c, self.do_scale, intensity=map_intensity)
        if self.mode == 'pp':
            for p in [(key,value) for key, value in fir.coords.items() if key[:2] != '__']:
                if p[0][0] == '_':
                    undashed_text = p[0][1:]
                else:
                    undashed_text = p[0]
                if p[0] in fir.iafs:
                    fix_color = 'yellow'
                else:
                    fix_color = 'gray40'
                map.add_text(undashed_text, p[1], color=fix_color)
        else:
            for p in [(key,value) for key, value in fir.coords.items() if key[0] != '_']:
                map.add_text(p[0], p[1], color='gray40')
        self.maps['point_names'] = map
        if not self.draw_point_names: map.hide()

        # Sector border
        seclimitmap = RaMap(self.c, self.do_scale, intensity=map_intensity)
        kw = {'color': 'blue'}
        sector_list = self.sector.split(",")
        for sector in sector_list:
            seclimitmap.add_polyline(*fir.boundaries[sector], **kw)
        self.maps['sector_limit'] = seclimitmap
        if not self.draw_lim_sector: seclimitmap.hide()

        def draw_SID_STAR_GND(map, object):

            def draw_single_SID_STAR_GND(single_sid_star_gnd, remove_underscored=True):
                rte = single_sid_star_gnd.rte
                wp0 = rte[0]
                for i in range(1, len(rte)):
                    wp1 = rte[i]
                    if wp1.fix[0] == '_' and remove_underscored: continue
                    map.add_polyline(wp0.pos(), wp1.pos(), color=color)
                    wp0 = wp1

            sid_star_gnd_rwy = object[1]
            sid_star_gnd_name = object[2]
            if len(object) > 3:
                color = object[3]
            else:
                color = 'white'

            try:
                ad = self.fir.aerodromes[sid_star_gnd_rwy[:4]]
                rwy_desig = sid_star_gnd_rwy[4:]
                rwy = [rwy for rwy in ad.rwy_direction_list if rwy.txt_desig == rwy_desig][0]
            except:
                logging.error("Unable to draw procedure for %s" % sid_star_gnd_rwy, exc_info=True)
            if object[0] == 'draw_sid':
                dict = rwy.sid_dict
            elif object[0] == 'draw_star':
                dict = rwy.star_dict
            elif object[0] == 'draw_gnd':
                dict = rwy.gnd_dict

            for proc in (proc for proc in dict.values()
                         if sid_star_gnd_name == '' or sid_star_gnd_name == proc.txt_desig):
                draw_single_SID_STAR_GND(proc, True)

        # Local Maps
        for map_name in fir.local_maps.keys():
            map = RaMap(self.c, self.do_scale, intensity=map_intensity)
            objects = fir.local_maps[map_name]
            for ob in objects:
                if ob[0] == 'linea':
                    cx0 = float(ob[1])
                    cy0 = float(ob[2])
                    cx1 = float(ob[3])
                    cy1 = float(ob[4])
                    if len(ob) > 5:
                        col = ob[5]
                        if ob[5] in ['13', '11', '9', '7', '6']:
                            col = 'white'
                    else:
                        col = 'gray'
                    map.add_polyline((cx0, cy0), (cx1, cy1), color=col)
                elif ob[0] == 'polyline':
                    if len(ob) > 5:
                        col = ob[1]
                        if ob[1] in ['13', '11', '9', '7', '6']:
                            col = 'white'
                    else:
                        col = 'gray'
                    coords = []
                    for i in range(2, len(ob), 2):
                        coords.append((float(ob[i]), float(ob[i + 1])))
                    kw = {'color': col}
                    map.add_polyline(*coords, **kw)
                elif ob[0] == 'pointsline':
                    color = ob[1]
                    if ob[1] in ['13', '11', '9', '7', '6']:
                        color = 'white'
                    if ob[1] == '':
                        color = 'gray'
                    coords = []
                    for p in ob[2:]:
                        coords.append(self.fir.GetPointCoordinates(p))
                    kw = {'color': color}
                    map.add_polyline(*coords, **kw)
                elif ob[0] == 'polygon':
                    color = ob[1]
                    if ob[1] in ['13', '11', '9', '7', '6']:
                        color = 'white'
                    if ob[1] == '':
                        color = 'gray'
                    coords = []
                    for i in range(2, len(ob), 2):
                        coords.append((float(ob[i]), float(ob[i + 1])))
                    kw = {'color': color}
                    map.add_polygon(*coords, **kw)
                elif ob[0] == 'pointsgon':
                    color = ob[1]
                    if ob[1] in ['13', '11', '9', '7', '6']:
                        color = 'white'
                    if ob[1] == '':
                        color = 'gray'
                    coords = []
                    for p in ob[2:]:
                        coords.append(self.fir.GetPointCoordinates(p))
                    kw = {'color': color}
                    map.add_polygon(*coords, **kw)
                elif ob[0] == 'arco':
                    cx0, cy0, cx1, cy1 = float(ob[1]), float(ob[2]), float(ob[3]), float(ob[4])
                    start, extent = 90.0 - float(ob[5]), -(float(ob[6]) - float(ob[5]))
                    if len(ob) > 7:
                        col = ob[7]
                        if ob[7] in ['13', '11', '9', '7', '6']:
                            col = 'white'
                    else:
                        col = 'gray'
                    map.add_arc((cx0, cy0), (cx1, cy1), start, extent, color=col)
                #################################################################Para dibujar los circulos con relleno-->barras de parada, esperas intermedias
                elif ob[0] == 'circulo':
                    cx0, cy0, cx1, cy1 = float(ob[1]), float(ob[2]), float(ob[3]), float(ob[4])
                    start, extent = float(ob[5]), float(ob[6])
                    if len(ob) > 7:
                        col = ob[7]
                        if ob[7] in ['13', '11', '9', '7', '6']:
                            col = 'white'
                    else:
                        col = 'gray'
                    map.add_circle((cx0, cy0), (cx1, cy1), start, extent, color=col)
                elif ob[0] == 'ovalo':
                    cx0 = float(ob[1])
                    cy0 = float(ob[2])
                    cx1 = float(ob[3])
                    cy1 = float(ob[4])
                    if len(ob) > 5:
                        col = ob[5]
                    else:
                        col = 'gray'
                    map.add_arc(cx0, cy0, cx1, cy1, 0, 360, color=col)
                elif ob[0] == 'rectangulo':
                    cx0 = float(ob[1])
                    cy0 = float(ob[2])
                    cx1 = float(ob[3])
                    cy1 = float(ob[4])
                    if len(ob) > 5:
                        col = ob[5]
                    else:
                        col = 'gray'
                    map.add_polyline(cx0, cy0, cx0, cy1, cx1, cy1, cx1, cy0, cx0, cy0, color=col)
                elif ob[0] == 'texto':
                    if len(ob) == 6:
                        anc = ob[5]
                        col = ob[4]
                    elif len(ob) == 5:
                        anc = 'sw'
                        col = ob[4]
                        if ob[4] in ['13', '11', '9', '7', '6']:
                            col = 'white'
                    else:
                        anc = 'sw'
                        col = 'gray'
                    x, y = float(ob[1]), float(ob[2])
                    txt = ob[3]
                    map.add_text(ob[3], (x, y), color=col, anchor=anc)  # , anchor=anc
                elif ob[0] == 'simbolo':
                    col = ob[4].upper()
                    symbol_type = ob[3].upper()
                    x, y = float(ob[1]), float(ob[2])
                    map.add_symbol(symbol_type, (x, y), color=col)
                elif ob[0] == 'draw_star' or ob[0] == 'draw_sid':
                    draw_SID_STAR_GND(map, ob)
                elif ob[0] == 'polyline':
                    object = ob
                    color = object[1]
                    if object[1] in ['13', '11', '9', '7', '6']:
                        color = 'white'
                    if object[1] == '':
                        color = 'gray'
                    coords = []
                    for p in object[2:]:
                        coords.append(self.fir.GetPointCoordinates(p))
                    kw = {'color': color}
                    map.add_polyline(*coords, **kw)
            self.maps[map_name] = map
            if map_name not in self.local_maps_shown: map.hide()
        # _draw_deltas()

        # Local Maps

        #       In the future we might try something more simple
        # color='gray25'
        # for map_name in fir.excel_maps.keys():
        #    for obj in fir.excel_maps[map_name]:
        #        if len(obj[2])==1:
        # self.c.create_text(obj[2], text=obj[1], anchor='sw', font=('helvetica', 8), fill=color, activefill='yellow', tag=map_name)
        #        elif len(obj[2])>1:
        # self.c.create_line(obj[2], fill=color, activefill='yellow', tag=map_name)
        # self.c.scale('all', 0, 0, self.scale, -self.scale)
        # if map_name not in self.local_maps_shown: map.hide()
        self.c.lift('track')

    def reformat_labels(self):
        for f in self.flights:
            self.update_track(f)
        for a in self.tracks:
            #            a._l.reformat()
            a.redraw()

    def redraw(self):
        """Delete and redraw all elements of the radar display"""
        self.redraw_maps()

        # Refresh tracks. No es un refresh, se estan volviendo a crear las etiquetas
        for a in self.tracks:
            a.redraw()

        self.update_lads()
        self.update_fprs()
        self.update_geotabs()

    def reposition(self):
        self.stop_separating = True  # If the label separation code is running
        # we want to make sure that it will not try to
        # move the labels because results would be
        # incorrect

        for map_name, map in self.maps.items():
            if not map.hidden:
                map.reposition()
        for vt in self.tracks:
            if vt.visible:
                (x, y) = self.do_scale((vt.wx, vt.wy))
                vt.coords(x, y, None)
        self.update_lads()
        self.update_fprs()
        self.update_geotabs()
        self.c.lift('track')

        self.stop_separating = False

    def do_scale(self, a):
        """Convert world coordinates into screen coordinates"""
        # screen origin in upper left corner?
        # return s((self.center_x,self.center_y),p(r((a[0],-a[1]),(self.x0,-self.y0)),self.scale))
        # Better to do the calculations inline to avoid the overhead of the function calling
        # on this very often called function
        try:
            if self.orient == 'NORTH':
                phi = 0.0
            else:
                phi = -self.field_up * math.pi / 180.0

            sphi = sin(phi)
            cphi = cos(phi)
            # re_center and scale
            vaux = ((a[0] - self.x0) * self.scale, (-a[1] + self.y0) * self.scale)
            # rotate
            vaux2 = (vaux[0] * cphi - vaux[1] * sphi, vaux[0] * sphi + vaux[1] * cphi)

            return (self.center_x + vaux2[0], self.center_y + vaux2[1])
        except:
            logging.error('do_scale: Unable to scale point %s' % a)
            raise

    def undo_scale(self, a):
        """Convert screen coodinates into world coordinates"""
        if self.orient == 'NORTH':
            phi = 0.0
        else:
            phi = self.field_up * math.pi / 180.0

        sphi = sin(phi)
        cphi = cos(phi)
        # re_center and scale
        vaux = ((a[0] - self.center_x), (a[1] - self.center_y))
        # rotate
        vaux2 = (vaux[0] * cphi - vaux[1] * sphi, vaux[0] * sphi + vaux[1] * cphi)
        # re-scale and re-center
        return (self.x0 + vaux2[0] / self.scale, self.y0 - vaux2[1] / self.scale)

    def set_active_sectors(self, sector_list):
        # TODO this needs to deal with several possible sectors active at the same time
        # is_CLD = False
        old_sector = self.sector

        # if sector_list == ['CLD']:  # DCM: Si es Clearance debe contener todos los grounds
        #     is_CLD = True
        #     sector_list = ['GMC_N', 'GMC_C', 'GMC_S']

        if len(sector_list) < 1:
            return
        self.sector_list = sector_list
        self.sector = ','.join(sector_list)

        for a in self.tracks:
            a.reconfigure()

        fs_list = []
        for sector in sector_list:
            fs_list += self.tlpv.get_sector_flightstrips(sector)
        self.fs_list = fs_list

        role_gnd = role_lcl = role_double_lcl = False

        # 1) Destruir las ventanas actuales que tengas en display_remote
        for window in self.display_remote:
            if window and hasattr(window, "root") and window.root.winfo_exists():
                window.root.destroy()

        self.display_remote = []

        if hasattr(self, 'atc_bahia') and self.atc_bahia.showed:
            self.atc_bahia.hide()

        # 2) Calcular bahia_type de nuevo
        bahia_type = None

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
                bahia_type = 'GND+LCL'
            elif role_clr and role_gnd:
                bahia_type = 'GND+CLR'
            elif role_gnd:
                bahia_type = 'GND'
            elif role_lcl:
                bahia_type = 'LCL'
            elif role_clr:
                bahia_type = 'CLR'

            # 3) Crear/reutilizar OSF segun pantalla
            if self.disp_number == 1:
                if bahia_type is not None:
                    # LEPA con multiples LCL puros: una ventana OSF por cada sector LCL
                    # (parametro de escenario 'osf_lcl_por_sector', por defecto solo LEPA)
                    if self.fir.param('osf_lcl_por_sector', False) and bahia_type == 'LCL' and len(self.lcl_sector_list) > 1:
                        for lcl_sector in self.lcl_sector_list:
                            osf_lcl = OSF.get_instance(self, 'LCL', instance_key=lcl_sector, display_name=lcl_sector, osf_sector=lcl_sector)
                            self.display_remote.append(osf_lcl)
                        self.fichas_tabular = self.display_remote[0]
                    else:
                        # Comportamiento habitual: una sola ventana OSF
                        self.fichas_tabular = OSF.get_instance(self, bahia_type, display_name=self.sector)
                        self.display_remote.append(self.fichas_tabular)
                    if bahia_type in ('CLR', 'GND+CLR', 'GND', 'GND+LCL'):
                        self.predesp_tabular = PrevDesp.get_instance(self, 'CLR')
                        self.display_remote.append(self.predesp_tabular)
                else:
                    return
                    #self.fichas_tabular = RaBahia(self, 'GND+LCL')
                    #if self.fir.aps[0] not in ('LEMD', 'LEBL'):
                    #    self.predesp_tabular = RaBahia(self, 'CLR')
                    #    self.display_remote.append(self.predesp_tabular)

            else:  # self.disp_number > 1
                if bahia_type is not None:
                    # Reutiliza (o crea, si la ventana anterior ya no existe)
                    self.fichas_tabular = OSF.get_instance(self, bahia_type)

        else:
            if self.mode != 'pp' and self.disp_number == 1:
                # if self.atc_bahia.showed:
                self.atc_bahia = ATCBahia(self)


    def toggle_routes(self):
        self.draw_routes = not self.draw_routes
        self.maps['airways'].toggle()

    def toggle_point_names(self):
        self.draw_point_names = not self.draw_point_names
        self.maps['point_names'].toggle()

    def toggle_point(self):
        self.draw_point = not self.draw_point
        self.maps['points'].toggle()

    def toggle_sector(self):
        self.draw_sector = not self.draw_sector
        self.maps['sector'].toggle()

    def toggle_lim_sector(self):
        self.draw_lim_sector = not self.draw_lim_sector
        self.maps['sector_limit'].toggle()

    def toggle_tmas(self):
        self.draw_tmas = not self.draw_tmas
        self.maps['tmas'].toggle()

    def toggle_deltas(self):
        self.draw_deltas = not self.draw_deltas
        # Special Use Areas
        self.maps['SUA'].toggle()

    def save_state(self):
        """Accumulate current display state into self.conf (no disk write).

        Called from exit() and also from _save_all_displays() in GAMMA.py so
        that all exit paths (aspa ventana, cierre CMD, servidor termina) graban
        el estado correctamente.
        """
        # Map options (pp mode only; atc mode leaves these at False)
        self.conf.write_option("Maps", "Point_names", self.draw_point_names)
        self.conf.write_option("Maps", "Points", self.draw_point)
        self.conf.write_option("Maps", "Routes", self.draw_routes)
        self.conf.write_option("Maps", "Sector", self.draw_sector)
        self.conf.write_option("Maps", "Lim_sector", self.draw_lim_sector)
        self.conf.write_option("Maps", "TMAs", self.draw_tmas)
        self.conf.write_option("Maps", "Deltas", self.draw_deltas)

        # Brightness
        self.conf.write_option("Brightness", "GLOBAL", self.intensity["GLOBAL"])
        self.conf.write_option("Brightness", "TRACKS", self.intensity["TRACKS"])
        self.conf.write_option("Brightness", "MAP", self.intensity["MAP"])
        self.conf.write_option("Brightness", "LADS", self.intensity["LADS"])

        # Window position, orientation, zoom, FALT filter and active sector
        tl = self.top_level
        tl.update_idletasks()
        layout_str = "Layout" + str(self.disp_number)
        self.conf.write_option(layout_str, "geometry", tl.wm_geometry())
        self.conf.write_option(layout_str, "orientation", self.orient)
        self.conf.write_option(layout_str, "scale", self.scale)
        self.conf.write_option(layout_str, "center_x", self.center_x)
        self.conf.write_option(layout_str, "center_y", self.center_y)
        self.conf.write_option(layout_str, "select_FALT_varmax", self.select_FALT_varmax.get())
        self.conf.write_option(layout_str, "select_FALT_varmin", self.select_FALT_varmin.get())
        self.conf.write_option(layout_str, "filterFGND", self.filterFGND)

        # Local map visibility - single source of truth: Layout<n>
        for map_name in self.fir.local_maps:
            self.conf.write_option(layout_str, map_name,
                                   bool(self.toolbar.var_ver_localmap[map_name].get()))

        # Escribir después del bucle de mapas: evita colisión si un mapa local
        # se llama "sector" (p.ej. GCXO), que machacaba el valor correcto con False
        self.conf.write_option(layout_str, "sector", self.sector)

    def exit(self):
        self.save_state()
        self.conf.save()  # single disk write for this display
        # self.conf.write_option("Layout","origin_x",self.x0)
        # self.conf.write_option("Layout","origin_y",self.y0)
        # Drop aings
        #        ra_clearbinds(self)
        # Delete map objects
        for map in self.maps.values():
            map.destroy()
        del self.maps
        # Delete tracks
        for t in self.tracks:
            t.destroy()
        try:
            self.tracks[0].reset_timer()
        except:
            logging.error("Error resetting timer")
        del self.tracks
        self.top_level.destroy()
        # Avoid memory leaks due to circular references preventing
        # the garbage collector from discarding this object
        try:
            self.sendMessage = None  # Clear the callback to the protocol
        except:
            pass

    def set_element_intensity(self, v):
        """Changes the brightness of radar elements"""

        def set_LAD_intensity():
            LAD.lad_color.set_intensity(self.intensity["GLOBAL"] * self.intensity["LADS"])
            LAD.super_lad_color.set_intensity(self.intensity["GLOBAL"] * self.intensity["LADS"])
            self.update_lads()
            self.update_fprs()
            self.update_geotabs()

        def set_MAP_intensity():
            for map in self.maps.values():
                map.intensity = self.intensity["GLOBAL"] * self.intensity["MAP"]

        def set_TRACKS_intensity():
            for track in self.tracks:
                track.intensity = self.intensity["GLOBAL"] * self.intensity["TRACKS"]


        # Copy the values from the given dictionary into the stored intensity
        previous = self.intensity.copy()
        self.intensity.update(v)

        if v.has_key("GLOBAL") and v["GLOBAL"] != previous["GLOBAL"]:
            set_LAD_intensity()
            set_MAP_intensity()
            set_TRACKS_intensity()
        if v.has_key("MAP") and v["MAP"] != previous["MAP"]:
            set_MAP_intensity()
        if v.has_key("TRACKS") and v["TRACKS"] != previous["TRACKS"]:
            set_TRACKS_intensity()
        if v.has_key("LADS") and v["LADS"] != previous["LADS"]:
            set_LAD_intensity()

    def __del__(self):
        logging.debug("RaDisplay.__del__")

    def write_Cesium_file(self):
        meteo_visual = None
        try:
            meteo_visual = self.metar.split()[4]
        except:
            self.metar = ''
        if meteo_visual == 'SS':
            visual = 1
        elif meteo_visual == 'SN':
            visual = 2
        elif meteo_visual == 'DZ':
            visual = 3
        elif meteo_visual == 'RA':
            visual = 4
        elif meteo_visual in ['HZ', 'FU']:
            visual = 5
        elif meteo_visual == 'BR':
            visual = 6
        elif meteo_visual == 'FG':
            visual = 7
        else:
            visual = 0
        file = conf.cesium_dir + '/GAMMA_interface/Cesium_file.txt'
        output_date = "%04d-%02d-%02dT%02d:%02d:%06.3fZ" % (
        self.t.year, self.t.month, self.t.day, self.t.hour, self.t.minute, self.t.second + self.t.microsecond * 1e-6)
        output_visual = "%s\n" % (visual)
        output = output_date + ' ' + output_visual

        lCount = 0

        for track in self.flights:
            if track.pof not in (Aircraft.INACTIVE, Aircraft.LOADING):
                speed = track.ground_spd
                heading = track.hdg
                altitude = (track.lvl - track.AirportElev) * 100 * 0.3048
                callsign = track.callsign
                yaw = track.yaw
                tilt = - track.pitch
                roll = track.roll
                apparent_heading = (heading + yaw) % 360
                (latitude, longitude) = self.fir.NM2Geo(track.pos[0], track.pos[1])
                model_file = track.model_file
                x1, y1 = self.fir.DesMagRotation(track.pos[0], track.pos[1])
                x = x1 * 1852
                y = y1 * 1852
                action = track.action
                wake = track.wake_hint
                fire = track.fire

                output_track = """%s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s""" % (
                callsign, model_file, longitude, latitude, altitude, apparent_heading, tilt, roll, 'ok', x, y, speed,
                yaw, action, fire, wake)

                if lCount > 0:
                    output = output + '\n' + output_track
                else:
                    output = output + output_track
                lCount += 1

        f = open(file, 'w')
        f.write(output)
        f.close()


# This is here just for debugging purposes
if __name__ == "__main__":
    import Pseudopilot

    root = tix.Tk()
    canvas = tix.Canvas(root, bg='black')


    def message_handler(*a):
        pass


    def do_scale(a): return a


    def undo_scale(a): return a


    vt = VisTrack(canvas, message_handler, do_scale, undo_scale)
    vt.x = 2
    label = vt.Label(vt)
    label.redraw()
    # for i in label.items:
    #    print label[i].__dict__
    l = canvas.create_line(0, 0, 1, 1)
    ra_tag_bind(canvas, l, "<2>", ra_tag_bind)
    ra_tag_unbind(canvas, l, "<2>")
    ra_cleartagbinds(l)

