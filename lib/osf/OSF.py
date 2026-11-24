# -*- coding: utf-8 -*-


import logging
import Tkinter as tk
from Tkinter import Canvas

from lib import Aircraft

import os
import time

from lib import ConfMgr
conf = ConfMgr.GammaConfig()


class OSF(object):
    _instances = {}  # dict: instance_key -> instancia viva

    @classmethod
    def get_instance(cls, radisplay=None, bahia_type=None, instance_key=None, display_name=None, osf_sector=None, resto_fijo_width=None):
        """
        Devuelve la instancia de OSF para la clave dada.
        - instance_key: clave del Singleton (por defecto usa bahia_type).
        - display_name: texto que aparece en el título de la ventana (por defecto usa instance_key).
        - Si ya existe y la ventana sigue viva, la reutiliza.
        - Si no existe, o su ventana se ha destruido, crea una nueva.
        """
        if instance_key is None:
            instance_key = bahia_type
        if display_name is None:
            display_name = instance_key

        inst = cls._instances.get(instance_key)

        # Si hay instancia, pero su ventana Tk ya no existe, la consideramos "muerta"
        if inst is not None:
            try:
                if not hasattr(inst, "root") or not inst.root.winfo_exists():
                    inst = None
            except:
                # Por seguridad, si hay cualquier problema, la damos por muerta
                inst = None

        # Si NO hay instancia viva, hay que crearla
        if inst is None:
            if radisplay is None or bahia_type is None:
                raise ValueError("OSF aún no existe: hay que pasar radisplay y bahia_type la primera vez")
            inst = cls(radisplay, bahia_type, display_name=display_name, osf_sector=osf_sector, resto_fijo_width=resto_fijo_width)
            cls._instances[instance_key] = inst

        return inst

    def __init__(self, radisplay, bahia_type, display_name=None, osf_sector=None, resto_fijo_width=None):
        self.root = tk.Toplevel()
        self.root.geometry("800x1000")  # ancho x alto en píxeles
        self.root.resizable(width=False, height=True)
        self.root.title("OSF - " + (display_name if display_name else bahia_type))
        self.root.attributes('-topmost', 1)  # Ventana siempre encima del resto

        # --- Parámetros recibidos / contexto ---
        self.radisplay = radisplay
        self.fir = getattr(radisplay, "fir", None)
        # sector propio de esta ventana OSF (puede diferir de radisplay.sector en LEPA multi-LCL)
        self.sector = osf_sector if osf_sector is not None else (getattr(radisplay, "sector", "") or "")

        # TODO: Bahia GND+CLR no soportada. 4 zonas. Ver documentacion. Se aplica el layout de GND para todos los vuelos.
        if bahia_type == "GND+CLR":
            bahia_type = "GND"
        self.bahia_type = bahia_type

        self.state_to_bahia = self.fir.state_to_bahia
        self.gates = list(getattr(self.fir, "gates", []))  # lista de gates desde FIR
        # self.hp = list(getattr(self.fir, "hp", []))  # lista de HPs desde FIR
        self.hp_by_rwy = getattr(self.fir, "hp", {}) or {}  # dict: rwy -> lista de HPs
        self.showed = True

        # --- Zonas según tipo de bahía (leído de zonesOSF en Excel/FIR) ---
        if self.bahia_type == 'CLR':
            self.zonas_count = 4
        else:
            zones_osf = getattr(self.fir, "zonasOSF", {}) or {}
            zonas_str = zones_osf.get(self.bahia_type)
            try:
                self.zonas_count = int(zonas_str)
            except (ValueError, TypeError):
                # Fallback si el bahia_type no está definido en el Excel
                self.zonas_count = 4
                logging.warning("zonesOSF: bahia_type '%s' no encontrado en Excel, usando %d zonas por defecto",
                                self.bahia_type, self.zonas_count)
        # Definimos la última zona
        # self.last_zona = self.zonas_count
        # Definir correctamente el índice de la última zona (0-based)
        self.last_zona_idx = self.zonas_count - 1

        self.fs_processed = set()
        self.fs_deleted = set()
        self.fs_last_zone_entry = {}  # callsign -> instante t en que entró en la última zona
        self.fs_airborne_t = {}       # callsign -> instante t en que pasó a AIRBORNE (solo dep locales)

        # --- Barra superior + botón OBST ---
        self.topbar = tk.Frame(self.root, bg="#555555")
        self.topbar.pack(side=tk.TOP, fill=tk.X)

        self.cabecera_popup = "#555555"
        self.body_popup = "#666666"
        self.fondo_btn_popup = "#666666"

        # --- Botones en barra superior ---
        self.btn_warning = tk.Button(
            self.topbar,
            text="W",
            bg="#555555",
            fg="white",
            width=8,
            font=('Lucida Sans Typewriter', 9, 'bold'),
            relief="raised",
            bd=2,
            command=self.warning_toggle
        )
        self.btn_warning.pack(side=tk.RIGHT, padx=1, pady=3)

        # Boton VEH (Plan de Vehiculo): solo si el escenario lo activa (parametro 'pvh')
        self.btn_veh = None
        if self._pvh_enabled():
            self.btn_veh = tk.Button(
                self.topbar,
                text="VEH",
                bg="#555555",
                fg="white",
                font=('Lucida Sans Typewriter', 9, 'bold'),
                width=8,
                relief="raised",
                bd=2,
                command=self._handle_veh_button
            )
            self.btn_veh.pack(side=tk.RIGHT, padx=1, pady=3)

        self.btn_obst = tk.Button(
            self.topbar,
            text="OBST",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            width=8,
            relief="raised",
            bd=2,
            command=self._handle_obst_button
        )
        self.btn_obst.pack(side=tk.RIGHT, padx=1, pady=3)

        self.btn_fm = tk.Button(
            self.topbar,
            text="F/M",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            width=8,
            relief="raised",
            bd=2,
            command=self._handle_fm_button
        )
        self.btn_fm.pack(side=tk.LEFT, padx=1, pady=3)

        self.lbl_vfve = tk.Label(
            self.topbar,
            text="VFVE",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold')
        )
        self.lbl_vfve.pack(side=tk.LEFT, padx=(250, 1), pady=3)

        # --- Widgets principales ---
        self.canvas = Canvas(self.root, bg="#666666")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # --- Binds de eventos ---
        self.canvas.bind("<Configure>", self.on_resize)
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-1>", self._campolibre_global_click, add="+")
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Button-2>", self.on_middle_click)
        self.canvas.bind("<B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_middle_release)

        # --- Estado interno ---
        self.dragging = None               # índice de divisor vertical (entre zonas) en arrastre
        self.active_scroll = None          # dict con info de arrastre de scrollbar
        self.dragging_line = None          # (zona_idx, ficha_idx) en arrastre con botón central
        self.dragging_visual = None        # reservado para recuadro visual temporal
        self.selected_line = None          # (zona_idx, ficha_idx) seleccionado de forma persistente
        self._drag_started = False         # para distinguir clic vs arrastre
        self._mid_down = None              # {"zona": int, "ficha": int, "callsign": str, "drag": bool}
        self._campolibre_edit_active = False
        self._park_edit_active = False
        self._park_ficha = None
        self._park_callsign = None
        self._pvh_dialog = None
        self._pvh_cs_var = None

        # --- Paleta / estilo ---
        self.color_dep_asum = "#009802"
        self.color_dep_noasum = "#90ee90"
        self.color_des_asum = "#ffa500"
        self.color_des_noasum = "#ffd383"
        self.font_style = ('Lucida Sans Typewriter', 13, 'bold')
        self.ficha_bg = "#232323"  # fondo único de las celdas

        # Layout / nudges
        self.margin = 50  # ancho de banda negra izquierda/derecha
        self.ficha_height = 25  # alto de la ficha
        self.ficha_sep = 2  # separación entre fichas
        self.nudge_step = self.max_nudge = 25  # píxeles de coqueo

        # Editor inline
        self._edit_entry = None
        self._edit_entry_var = None
        self._edit_entry_win = None
        self._editing = None  # (zona_idx, ficha_idx, nombre_campo)

        # --- Definición de campos (anchos/valores) ---
        self.default_field_width = 100
        # "resto_fijo": como "resto" pero de ancho fijo (configurable por parámetro,
        # no flexible). Se ajusta en el layout OSF del escenario (Excel).
        self.resto_fijo_width = resto_fijo_width if resto_fijo_width is not None else 100
        self.field_defs = {
            "act":          {"width": 50,  "value": "TAX"},
            "callsign":     {"width": 90,  "value": "IBE1234"},
            "autorizacion": {"width": 20, "value": ""},
            "type":         {"width": 60,  "value": "A320"},
            "wake":         {"width": 50,  "value": "H+"},
            "eobt":         {"width": 70,  "value": "1234"},  # doble uso: eobt o ctot si está registrado (ver _eobt_slot)
            "eldt":         {"width": 70, "value": "1234"},
            "sid":          {"width": 80,  "value": "LEBL7Q"},
            "rules":        {"width": 30,  "value": "I"},
            "rwydep":       {"width": 50,  "value": "24L"},
            "rwydes":       {"width": 50, "value": "24R"},
            "park":         {"width": 50,  "value": "152"},
            "gate":         {"width": 80,  "value": "GT"},
            "campolibre":   {"width": 150, "value": "-libre-"},
            "holdp":        {"width": 80, "value": "HP"},
            "hrls":         {"width": 80, "value": "HRLS"},
            "obstaculo":    {"width": 700, "value": ""},  # ancho de la ventana menos los margenes
            "alerta":       {"width": 30, "value": ""},  # Indicador W/V de alerta (layout LEBL)
            "pista_ent":    {"width": 85, "value": ""},   # Pista ENT/CRU vehiculo (PVH)
            "anotaciones":  {"width": 120, "value": ""},  # Anotaciones PVH vehiculo
            # Campo flexible (sin texto):
            "resto": {"width": "flex", "value": ""},
            # Como "resto" pero de ancho fijo (self.resto_fijo_width, parametrizable):
            "resto_fijo": {"width": self.resto_fijo_width, "value": ""},
        }
        # ---- Campos de la ficha extendida (anchos y valores por defecto) ----
        self.field_defs.update({
            "hacc":     {"width": 120, "value": ""},
            "cssr":     {"width": 70, "value": ""},
            "orig":     {"width": 70, "value": ""},
            "dest":     {"width": 70, "value": ""},
            "eldt":     {"width": 70, "value": "1234"},
            "park":     {"width": 50, "value": "152"},
            "airline":  {"width": 120, "value": ""},
            "vel":      {"width": 60, "value": ""},
            "sid":      {"width": 100, "value": ""},
            "sid_ext":  {"width": 100, "value": ""},
            "cfl":      {"width": 60, "value": ""},
            "qnh":      {"width": 80, "value": ""},
            "hrls":     {"width": 80, "value": "HRLS"},
            "holdp":    {"width": 80, "value": "HP"},
            # Campo flexible (sin texto):
            "resto": {"width": "flex", "value": ""},
            # Como "resto" pero de ancho fijo (self.resto_fijo_width, parametrizable):
            "resto_fijo": {"width": self.resto_fijo_width, "value": ""},
        })

        # --- Zonas (cada zona contiene sus fichas) ---
        self.zonas = [
            {
                "colors": [self.color_des_noasum],  # paleta para texto de campos
                "fichas": [],                       # lista de fichas (cada una define su lista ordenada de campos)
                "scroll_offset": 0
            }
            for _ in range(self.zonas_count)
        ]

        # Registro de layouts por (bahia_type, rol) donde rol ∈ {"dep_local", "des_local", "default"}
        # Fuente principal: hoja OSF_Layout del escenario (FIR). Los diccionarios
        # a continuacion son el fallback y solo se usan si la hoja falta o no
        # cubre alguna combinacion (ver merge con self.fir.osf_layouts mas abajo).
        _default_layouts = {
            # OR=GND, arribadas
            ("GND", "des_local"): ["act", "callsign", "type", "wake", "rwydes", "park", "campolibre", "gate", "resto", "rules"],  # OK
            # OR=GND, salidas
            ("GND", "dep_local"): ["act", "callsign", "autorizacion", "type", "wake", "eobt", "rwydep", "park", "gate", "campolibre", "resto", "rules"],  # OK
            # OR=GND, default
            ("GND", "default"): ["act", "callsign", "type", "wake", "rwy", "park", "sid", "resto", "rules"],

            # OR=LCL, arribadas
            ("LCL", "des_local"): ["act", "callsign", "type", "wake", "eldt", "rwydes", "park", "campolibre", "resto", "rules"],  # OK
            # OR=LCL, salidas
            ("LCL", "dep_local"): ["act", "callsign", "autorizacion", "type", "wake", "eobt", "rwydep", "holdp", "sid", "hrls", "resto", "rules"],  # OK
            # OR=LCL, default
            ("LCL", "default"): ["act", "callsign", "type", "wake", "rwy", "park", "sid", "resto", "rules"],

            # OR=CLR, salidas locales (CLR solo tiene salidas)
            ("CLR", "dep_local"): ["act", "callsign", "autorizacion", "type", "wake", "eobt", "rwy", "park", "resto", "rules"],

            # OR=CLR+GND, salidas
            # ("GND+CLR", "dep_local"): ["act", "callsign", "autorizacion", "type", "wake", "eobt", "rwydep", "park", "gate", "campolibre", "resto", "rules"],

            ("GND+LCL", "dep_local"): ["act", "callsign", "autorizacion", "type", "wake", "eobt", "rwydep", "park", "gate", "campolibre", "resto", "rules"],  # OK
            ("GND+LCL", "des_local"): ["act", "callsign", "type", "wake", "eldt", "rwydes", "park", "campolibre", "resto", "rules"],  # OK
            ("GND+LCL", "default"): ["act", "callsign", "type", "wake", "rwy", "park", "sid", "rules", "resto"],
        }

        # Layouts de FICHA EXTENDIDA por bahía y rol
        _default_ext_layouts = {
            # OR=GND, arribadas
            ("GND", "des_local"): ["hacc", "eldt", "resto"],  # OK
            # OR=GND, salidas
            ("GND", "dep_local"): ["hacc", "cssr", "dest", "vel", "cfl", "eobt", "holdp", "sid", "hrls", "resto"],  # OK
            # OR=GND, default
            ("GND", "default"): ["hacc", "resto"],

            # OR=LCL, arribadas
            ("LCL", "des_local"): ["hacc", "cssr", "orig", "dest", "vel", "resto"],  # OK
            # OR=LCL, salidas
            ("LCL", "dep_local"): ["hacc", "cssr", "dest", "vel", "cfl", "eobt", "park", "resto"],  # OK
            # OR=LCL, default
            ("LCL", "default"): ["hacc", "resto"],

            # OR=CLR+GND, salidas
            # ("GND+CLR", "dep_local"): ["hacc", "cssr", "dest", "vel", "cfl", "eobt", "holdp", "sid", "hrls", "resto"],

            ("GND+LCL", "dep_local"): ["hacc", "cssr", "dest", "vel", "cfl", "eobt", "holdp", "sid", "hrls", "resto"],  # OK
            ("GND+LCL", "des_local"): ["hacc", "cssr", "orig", "dest", "vel", "resto"],  # OK
            ("GND+LCL", "default"): ["hacc", "cssr", "orig", "dest", "airline", "vel", "sid_ext", "cfl", "qnh"],
        }

        # Merge con la hoja OSF_Layout del escenario: sobreescribe los defaults
        # solo para las combinaciones (bahia, rol) que la hoja define.
        _fir_layouts = getattr(self.fir, "osf_layouts", {}) or {}
        _fir_ext_layouts = getattr(self.fir, "osf_ext_layouts", {}) or {}

        self.layouts = dict(_default_layouts)
        self.layouts.update(_fir_layouts)
        self.ext_layouts = dict(_default_ext_layouts)
        self.ext_layouts.update(_fir_ext_layouts)

        # Asegura que existe el campo flex
        self.field_defs.setdefault("resto", {"width": "flex", "value": ""})
        self.field_defs.setdefault("resto_fijo", {"width": self.resto_fijo_width, "value": ""})

        # --- Alturas relativas de las zonas ---
        self.zona_heights = [1.0 / self.zonas_count for _ in range(self.zonas_count)]

        # Inicialización de layout
        self.update_zona_heights()
        self.draw_zonas()

    def show(self):
        try:
            self.root.deiconify()
            self.showed = True
        except tk.TclError:
            pass

    def hide(self):
        try:
            self.root.withdraw()
            self.showed = False
        except tk.TclError:
            pass

    def conmuta(self, e=None):
        if self.showed:
            self.hide()
        else:
            self.show()

    def update(self):
        """
        Inserta nuevas fichas desde self.radisplay.flights,
        aplicando filtros básicos y eliminando las fichas cuyos
        vuelos ya no existen en la lista de flights.
        Además, borra automáticamente las fichas que lleven
        2 minutos en la última zona (en tiempo de simulación),
        excepto si están en MAP o GA.
        """
        flights = list(getattr(self.radisplay, "flights", []) or [])
        t = getattr(self.radisplay, "t", None)

        # Aseguramos la estructura de tiempos de última zona
        if not hasattr(self, "fs_last_zone_entry"):
            self.fs_last_zone_entry = {}

        # ===============================
        # 1) Borrar fichas de vuelos que HAN DESAPARECIDO
        # ===============================
        current_cs = set()
        for f in flights:
            cs = getattr(f, "callsign", None)
            if cs:
                current_cs.add(cs)

        to_remove = [cs for cs in self.fs_processed
                     if (cs not in current_cs) and (cs not in self.fs_deleted)]

        for cs in to_remove:
            borrado = self._delete_ficha_by_callsign(cs, refresh=False)
            if borrado:
                # Lo marcamos como eliminado definitivo
                self.fs_deleted.add(cs)
                # Por si tenía timers activos
                self.fs_last_zone_entry.pop(cs, None)
                self.fs_airborne_t.pop(cs, None)

        if to_remove:
            self.draw_zonas()

        # ===============================
        # 2) Insertar nuevas fichas para vuelos que aún no tenga
        # ===============================
        pl = []
        for f in flights:
            cs = getattr(f, "callsign", None)
            if not cs:
                continue

            # Si ya fue procesado o está marcado como borrado, saltamos
            if cs in self.fs_processed or cs in self.fs_deleted:
                continue

            # Vehiculos: solo tienen ficha si el controlador les ha creado un PVH
            if getattr(f, "fr", None) == "VEH" and not getattr(f, "has_pvh", False):
                continue

            # Si está TERMINATED, borramos (si existiera) y lo marcamos como eliminado
            if getattr(f, "OSF_pof", None) == getattr(Aircraft, "TERMINATED", None):
                if cs not in self.fs_deleted:
                    borrado = self._delete_ficha_by_callsign(cs, refresh=False)
                    if borrado:
                        self.fs_deleted.add(cs)
                        self.fs_processed.add(cs)
                        self.fs_last_zone_entry.pop(cs, None)
                        self.fs_airborne_t.pop(cs, None)
                continue

            # Condición LLZ (igual que tenías)
            fs_print_t = getattr(f, "fs_print_t", {}) or {}
            if t is not None:
                if ("_LLZ" in fs_print_t) and not (fs_print_t["_LLZ"] < t):
                    continue

            pl.append(f)

        for f in pl:
            # insert_fs ya se encarga de actualizar timers de última zona
            self.insert_fs(f)

        # ===============================
        # 2b) Mover despegues AIRBORNE a última zona tras 15 segundos
        # ===============================
        AIRBORNE_TO_LAST_ZONE_DELAY = 15.0
        if t is not None and self.zonas and hasattr(self, "fs_airborne_t"):
            last_idx = self.zonas_count - 1
            move_cs = []
            for cs, enter_t in list(self.fs_airborne_t.items()):
                elapsed = 0.0
                try:
                    delta = t - enter_t
                    elapsed = delta.days * 86400 + delta.seconds
                except Exception:
                    try:
                        elapsed = float(t) - float(enter_t)
                    except Exception:
                        elapsed = 0.0
                if elapsed >= AIRBORNE_TO_LAST_ZONE_DELAY:
                    move_cs.append(cs)

            for cs in move_cs:
                found = self._find_ficha_by_callsign(cs)
                if found:
                    zi, fi, ficha = found
                    if zi != last_idx:
                        # Mover ficha principal de zona actual a última zona
                        self.zonas[zi]["fichas"].pop(fi)
                        self.zonas[last_idx]["fichas"].append(ficha)
                        # Mover también ficha extendida si existe
                        ext = self._find_extended_for_callsign(cs)
                        if ext:
                            ezi, efi = ext
                            ext_ficha = self.zonas[ezi]["fichas"].pop(efi)
                            self.zonas[last_idx]["fichas"].append(ext_ficha)
                        # Iniciar timer de borrado de 2 minutos
                        self.fs_last_zone_entry[cs] = t
                # Ya se movió o no existe: limpiar timer AIRBORNE
                self.fs_airborne_t.pop(cs, None)

            if move_cs:
                self.draw_zonas()

        # ===============================
        # 3) Borrado automático tras 2 minutos en la última zona (tiempo simulado)
        # ===============================
        if t is not None and self.zonas:
            # Índice de la última zona (0-based)
            last_idx = self.zonas_count - 1

            auto_remove_cs = set()

            for zi, zona in enumerate(self.zonas):
                if zi != last_idx:
                    continue  # Solo miramos la última zona

                for ficha in zona["fichas"]:
                    vals = ficha.get("values", {})
                    cs = vals.get("callsign", "")
                    if not cs:
                        continue

                    # Miramos el vuelo real para ver OSF_pof
                    flight = self._find_flight_by_callsign(cs)
                    pof = getattr(flight, "OSF_pof", None) if flight else None

                    # No aplicar borrado automático a MAP o GA
                    if pof in (getattr(Aircraft, "MAP", None),
                               getattr(Aircraft, "GA", None)):
                        # Por si acaso, limpiamos cualquier timer previo
                        self.fs_last_zone_entry.pop(cs, None)
                        continue

                    enter_t = self.fs_last_zone_entry.get(cs)

                    if enter_t is None:
                        # Primera vez que vemos este callsign en la última zona: marcamos hora de entrada
                        self.fs_last_zone_entry[cs] = t
                        continue

                    # Calculamos el tiempo transcurrido en segundos.
                    # Caso habitual: t y enter_t son datetime
                    elapsed = 0.0
                    try:
                        delta = t - enter_t
                        elapsed = delta.days * 86400 + delta.seconds
                    except Exception:
                        # Si no son datetime sino números (p.ej. segundos simulados)
                        try:
                            elapsed = float(t) - float(enter_t)
                        except Exception:
                            elapsed = 0.0

                    if elapsed >= 120.0:  # 2 minutos
                        auto_remove_cs.add(cs)

            # Borrar las fichas que hayan excedido los 2 minutos
            for cs in auto_remove_cs:
                if cs not in self.fs_deleted:
                    if self._delete_ficha_by_callsign(cs, refresh=False):
                        self.fs_deleted.add(cs)
                        self.fs_processed.add(cs)
                        self.fs_last_zone_entry.pop(cs, None)
                        self.fs_airborne_t.pop(cs, None)

            if auto_remove_cs:
                self.draw_zonas()
                return

        # ===============================
        # 4) Alertas aeroportuarias: redibujar solo si cambia el estado de alertas
        #    (alitas W/V). Sin alertas en el escenario el estado es siempre {}.
        # ===============================
        current_alert_state = {}
        for f in flights:
            sev = getattr(f, 'max_alert_severity', 0)
            if sev > 0:
                cs = getattr(f, 'callsign', None)
                if cs:
                    current_alert_state[cs] = sev
        if current_alert_state != getattr(self, '_last_alert_state', {}):
            # No redibujar con un campo en edicion ni durante un arrastre
            if self._edit_entry is not None and self._edit_entry_var is not None:
                return
            if self.dragging is not None or self.dragging_line is not None:
                return
            self._last_alert_state = current_alert_state
            self.draw_zonas()

    def update_strip(self, f, keep_position=True, refresh=True):
        """
        Reconstruye la ficha principal del vuelo 'f' y, si estaba extendida,
        recrea también la extendida debajo (con datos actualizados).
        """
        callsign = getattr(f, "callsign", None)
        if not callsign:
            return False

        # --- 1) Localizar ficha principal y extendida (si existe) ---
        found = self._find_ficha_by_callsign(callsign)
        prev_zona_idx, prev_ficha_idx = None, None
        prev_x_offset = 0
        if found:
            prev_zona_idx, prev_ficha_idx, prev_ficha = found
            try:
                prev_x_offset = int(prev_ficha.get("x_offset", 0))
            except Exception:
                prev_x_offset = 0

        ext_pos = None
        had_extended = False
        try:
            ext_pos = self._find_extended_for_callsign(callsign)  # (zi, fi) o None
            had_extended = bool(ext_pos)
        except Exception:
            ext_pos = None
            had_extended = False

        # --- 2) Eliminar ficha principal y extendida (si existían) ---
        to_delete = []
        if prev_zona_idx is not None:
            to_delete.append((prev_zona_idx, prev_ficha_idx))
        if ext_pos:
            to_delete.append(ext_pos)

        # Borrar empezando por índices mayores (para no descolocar)
        for zi, fi in sorted(to_delete, key=lambda x: (x[0], x[1]), reverse=True):
            try:
                zona = self.zonas[zi]
                if 0 <= fi < len(zona["fichas"]):
                    zona["fichas"].pop(fi)
            except Exception:
                pass

        # Si la selección apuntaba a esa ficha, límpiala (opcional pero recomendable)
        try:
            if self.selected_line and prev_zona_idx is not None:
                if self.selected_line == (prev_zona_idx, prev_ficha_idx):
                    self.selected_line = None
        except Exception:
            pass

        # --- 3) Insertar de nuevo la ficha principal con los valores actuales ---
        # IMPORTANTE: pasamos old_zona_idx para la excepción de "mantener zona"
        self.insert_fs(f, old_zona_idx=prev_zona_idx, x_offset=prev_x_offset)

        # --- 4) Mantener posición si procede (misma zona) ---
        new_found = self._find_ficha_by_callsign(callsign)
        if not new_found:
            if refresh:
                self.draw_zonas()
            return False

        new_zona_idx, new_ficha_idx, _ = new_found

        if keep_position and (prev_zona_idx is not None) and (new_zona_idx == prev_zona_idx):
            zona = self.zonas[new_zona_idx]
            try:
                # Sacamos la ficha de donde haya caído
                ficha_nueva = zona["fichas"].pop(new_ficha_idx)
                insert_idx = min(prev_ficha_idx, len(zona["fichas"]))
                zona["fichas"].insert(insert_idx, ficha_nueva)
            except Exception:
                pass

        # --- 5) Si antes había ficha extendida, recrearla debajo de la principal ---
        if had_extended:
            final_found = self._find_ficha_by_callsign(callsign)
            if final_found:
                zi_final, fi_final, _ = final_found
                try:
                    # Como ya la borramos, _toggle_extended aquí DEBE crearla.
                    self._toggle_extended(zi_final, fi_final)
                except Exception as e:
                    try:
                        print("Error recreando ficha extendida:", e)
                    except Exception:
                        pass

        # --- 6) Redibujar si procede ---
        if refresh:
            self.draw_zonas()

        return True

    def update_valores_ficha(self, callsign, nuevos_valores, refresh=True):
        found = self._find_ficha_by_callsign(callsign)
        if not found:
            return False

        zi, fi, ficha = found
        fields = set(ficha.get("fields", []))
        values = ficha.setdefault("values", {})

        changed = False
        for k, v in (nuevos_valores or {}).items():
            if k in fields:
                nv = "" if v is None else str(v)
                if values.get(k) != nv:
                    values[k] = nv
                    changed = True

        if changed and refresh:
            self.draw_zonas()
        return changed

    def _delete_ficha_by_callsign(self, callsign, refresh=True):
        """
        Elimina la ficha principal cuyo callsign coincide y, además,
        cualquier ficha extendida asociada (is_extended=True y parent_callsign=callsign).
        Devuelve True si ha borrado algo, False si no la ha encontrado.
        """
        found = self._find_ficha_by_callsign(callsign)
        if not found:
            return False

        zi, fi, _ = found

        # Borrar la ficha principal
        try:
            self.zonas[zi]["fichas"].pop(fi)
        except Exception:
            return False

        # Limpiar selección / dragging
        if self.selected_line == (zi, fi):
            self.selected_line = None
        if self.dragging_line == (zi, fi):
            self.dragging_line = None

        # Borrar fichas extendidas asociadas en esa zona
        try:
            zona = self.zonas[zi]
            nuevas = []
            for ficha in zona["fichas"]:
                if ficha.get("is_extended") and ficha.get("parent_callsign") == callsign:
                    continue
                nuevas.append(ficha)
            zona["fichas"] = nuevas
        except Exception:
            pass

        # Limpiar timers
        if hasattr(self, "fs_last_zone_entry"):
            self.fs_last_zone_entry.pop(callsign, None)
        if hasattr(self, "fs_airborne_t"):
            self.fs_airborne_t.pop(callsign, None)

        if refresh:
            self.draw_zonas()

        return True

    def _find_ficha_by_callsign(self, callsign):
        if not callsign:
            return None
        for zi, zona in enumerate(self.zonas):
            for fi, ficha in enumerate(zona.get("fichas", [])):
                if ficha.get("values", {}).get("callsign") == callsign:
                    return zi, fi, ficha
        return None

    def _find_extended_for_callsign(self, callsign):
        """
        Busca en todas las zonas si existe una ficha extendida asociada a 'callsign'.
        Devuelve (zona_idx, ficha_idx) o None.
        """
        for zi, zona in enumerate(self.zonas):
            for fi, ficha in enumerate(zona["fichas"]):
                if ficha.get("is_extended") and ficha.get("parent_callsign") == callsign:
                    return zi, fi
        return None

    def set_status(self, to_be_assumed, assumed, released):
        if assumed and not released:
            status = 'ASUM'
        elif assumed and released:
            status = 'LIB'
        elif to_be_assumed and not released:
            status = 'ENT_NO_LIB'
        elif to_be_assumed and released:
            status = 'ENT_LIB'
        else:
            status = ''
        return status

    def select_panel(self, OSF_pof, to_be_assumed, assumed, released, old_zone_str=None):
        """
        Devuelve el string de zona ('zone1', 'zone2', ...) para este estado.
        old_zone_str es la zona anterior (string) si se conoce.
        """
        status = self.set_status(to_be_assumed, assumed, released)
        if status == '':
            return ''

        # --- Excepción: mantener en su zona actual (solo si no está liberada) ---
        last_zone_str = 'zone%d' % self.zonas_count
        if OSF_pof == getattr(Aircraft, "TERMINATED", None):
            return last_zone_str
        if OSF_pof in (
            Aircraft.STARTREQ, Aircraft.STICEREQ, Aircraft.REAREQ,
            Aircraft.PUSHREQ,  Aircraft.TAXIREQ,  Aircraft.DEPREQ,
            Aircraft.LDGREQ,   Aircraft.MAP,      Aircraft.GA, Aircraft.ABORT
        ) and self.bahia_type != 'CLR':
            # Para GA/MAP liberadas ya en la última zona: no mantener (deben volver a zona de llegadas)
            if OSF_pof in (Aircraft.GA, Aircraft.MAP) and released and old_zone_str == last_zone_str:
                pass  # continuar con la lógica normal de state_to_bahia
            elif old_zone_str:
                return old_zone_str
            # Si no lo conocemos, seguimos con la lógica normal

        action = OSF_pof
        key_list = (self.bahia_type, status, action)

        # # Caso especial bahía CLR
        # if self.bahia_type == 'CLR':
        #     if OSF_pof in (Aircraft.PREPARING, Aircraft.STARTREQ, Aircraft.REAREQ):
        #         return 'zone1'
        #     else:
        #         return ''

        # Resto de casos
        if OSF_pof in (Aircraft.PREPARING, Aircraft.AUTHORIZATION):
            return ''
        else:
            try:
                panel = self.state_to_bahia[key_list]
                return panel
            except Exception:
                # GA y MAP no tienen entradas en el Excel
                if OSF_pof in (Aircraft.GA, Aircraft.MAP):
                    if released:
                        return last_zone_str
                    # Asumido: buscar zona de llegadas via LANDING o INCOMING
                    for fallback_action in (Aircraft.LANDING, Aircraft.INCOMING):
                        fallback_key = (self.bahia_type, status, fallback_action)
                        if fallback_key in self.state_to_bahia:
                            return self.state_to_bahia[fallback_key]
                    if old_zone_str:
                        return old_zone_str
                # Cruce/entrada a pista (CRR, CRU, ENR, ENT, LIB): si la hoja OSF no los
                # recoge, la ficha se queda en su zona; si no se conoce, zona segun el estado
                if OSF_pof in (Aircraft.CRUREQ, Aircraft.CROSSING, Aircraft.ENTREQ,
                               Aircraft.ENTERING, Aircraft.LIB):
                    if old_zone_str:
                        return old_zone_str
                    if status == 'LIB':
                        return last_zone_str
                    if status == 'ENT_NO_LIB':
                        return 'zone1'
                    return 'zone%d' % max(1, self.zonas_count - 1)
                print("Unable to find OSF zone: " + str(key_list))
                return ''

    def panel_to_index(self, panel_id):
        """
        Convierte un identificador de panel ('zone1', 'zone2', ... o int)
        en índice 0-based. Si no es válido, devuelve -1.
        """
        # Si ya viene como índice:
        if isinstance(panel_id, int):
            if 0 <= panel_id < self.zonas_count:
                return panel_id
            return -1

        # Map 1-based 'zoneN' a índice N-1
        mapping = {
            'zone1': 0,
            'zone2': 1,
            'zone3': 2,
            'zone4': 3,
            'zone5': 4,
            'zone6': 5,
            '': -1,
            None: -1,
        }
        return mapping.get(panel_id, -1)

    def choose_zona(self, f, old_zona_idx=None):
        """
        Devuelve índice de zona (0-based) para el vuelo f.
        old_zona_idx: índice de zona anterior si se conoce (o None).
        """
        sector = self.sector or ""
        to_be_assumed = (f.next_atc_sector is not None and
                         sector.find(f.next_atc_sector) >= 0)
        assumed = (f.atc_sector is not None and
                   sector.find(f.atc_sector) >= 0)
        released = bool(f.trans_atc_pos or f.release_atc_pos)

        # Convertir old_zona_idx -> old_zone_str ("zone1"...)
        if old_zona_idx is not None and old_zona_idx >= 0:
            old_zone_str = "zone%d" % (old_zona_idx + 1)
        else:
            old_zone_str = None

        zona_str = self.select_panel(f.OSF_pof, to_be_assumed, assumed, released, old_zone_str=old_zone_str)
        zona_idx = self.panel_to_index(zona_str)

        return zona_idx

    # Alias de nombres de campo aceptados en la hoja OSF_Layout del escenario
    # (el usuario que edita el Excel tiende a usar la etiqueta visible "HP"
    # en vez de la clave interna real "holdp").
    _FIELD_NAME_ALIASES = {"hp": "holdp"}

    def _pushback_rule(self, f):
        """Regla de retroceso (push-back) del stand del vuelo, para todos los escenarios:
        - 'stand': la hoja RetrocesosOSF tiene datos y el stand admite retroceso
          (fir.pushbacks[stand] = direcciones permitidas)
        - 'none': la hoja tiene datos y el stand NO admite retroceso (sale rodando: S/U -> TAX)
        - 'default': no hay hoja o esta vacia -> regla general (antes solo LEBB):
          S/U -> SOLICITUD P/B, AUTORIZACION P/W, AUTORIZACION P/E."""
        pushbacks = getattr(self.fir, "pushbacks", None)
        if not isinstance(pushbacks, dict) or not pushbacks:
            return 'default'
        return 'stand' if getattr(f, "park", None) in pushbacks else 'none'

    def _pvh_enabled(self):
        """Planes de vehiculo (PVH) y cruce/entrada a pista: parametro de escenario 'pvh'."""
        try:
            return bool(self.fir.param('pvh', False))
        except AttributeError:
            return False

    def _resolve_field_names(self, bahia_type, zona_idx, local_dep, local_des, is_veh=False):
        if is_veh:
            return ["act", "callsign", "pista_ent", "anotaciones", "resto"]
        if local_dep:
            key = (bahia_type, "dep_local")
        elif local_des:
            key = (bahia_type, "des_local")
        else:
            key = (bahia_type, "default")
        fields = self.layouts.get(key)
        if not fields:
            return ["callsign", "resto", "rules"]
        return [self._FIELD_NAME_ALIASES.get(c, c) for c in fields]

    def _resolve_ext_fields(self, bahia_type, zona_idx, local_dep, local_des):
        if local_dep:
            key = (bahia_type, "dep_local")
        elif local_des:
            key = (bahia_type, "des_local")
        else:
            key = (bahia_type, "default")
        fields = self.ext_layouts.get(key)
        if not fields:
            return ["airline", "resto", "qnh"]
        return [self._FIELD_NAME_ALIASES.get(c, c) for c in fields]

    # ============================
    # Inserts de fichas y obstaculo
    # ============================
    def insert_fs(self, f, old_zona_idx=None, x_offset=None):
        # 1) Zona destino
        zona_idx = self.choose_zona(f, old_zona_idx=old_zona_idx)
        if zona_idx < 0:
            return

        cs = getattr(f, "callsign", None)
        saved_x_offset = 0
        if x_offset is not None:
            try:
                saved_x_offset = int(x_offset)
            except Exception:
                saved_x_offset = 0
        elif cs:
            prev = self._find_ficha_by_callsign(cs)
            if prev:
                try:
                    saved_x_offset = int(prev[2].get("x_offset", 0))
                except Exception:
                    saved_x_offset = 0

        # --- Gestión de temporizador de última zona (usar tiempo simulado) ---
        t_sim = getattr(self.radisplay, "t", None)

        if cs and t_sim is not None:
            # Sí entra en la última zona
            if zona_idx == self.last_zona_idx:
                # Si antes no estaba en la última zona → empieza el contador
                if old_zona_idx != self.last_zona_idx:
                    self.fs_last_zone_entry[cs] = t_sim
            else:
                # Si sale de la última zona → borrar timer
                self.fs_last_zone_entry.pop(cs, None)

        # 2) Flags local_dep / local_des
        local_dep = False
        local_des = False
        sector_list = (self.sector or "").split(",")
        first_sector = sector_list[0] if sector_list else ""
        ads_set = (self.fir.local_ads.get(first_sector, set())
                   if getattr(self.fir, "local_ads", None) else set())
        if getattr(f, "adep", None) in ads_set:
            local_dep = True
        elif getattr(f, "ades", None) in ads_set:
            local_des = True

        # --- Registro de instante AIRBORNE para despegues locales ---
        if cs and t_sim is not None and local_dep:
            pof = getattr(f, "OSF_pof", None)
            if pof == Aircraft.AIRBORNE and cs not in self.fs_airborne_t:
                self.fs_airborne_t[cs] = t_sim
            elif pof != Aircraft.AIRBORNE:
                self.fs_airborne_t.pop(cs, None)

        # 3) Campos a mostrar
        is_veh = (getattr(f, "fr", None) == "VEH" and getattr(f, "has_pvh", False))
        field_names = self._resolve_field_names(self.bahia_type, zona_idx, local_dep, local_des, is_veh=is_veh)

        def S(x):
            return "" if x is None else str(x)

        act_txt, act_color = self._act_text_color(f)
        # Prediccion CATC: color morado en la fase (indicador visual, no alerta)
        if getattr(f, 'catc_pred', False):
            act_color = "#CC33FF"
        cs_txt, cs_color = self._callsign_text_color(
            f,
            zona_idx,
            warning=bool(getattr(f, "OSF_warning", False))
        )
        wake_color = self._wake_text_color(f)

        hp_val = S(getattr(f, "holdp", "HP"))
        hrls_enabled = bool(getattr(f, "hrls", False))
        hrls_txt = "RLS" if hrls_enabled else "HRLS"
        # cfl: nivel de vuelo autorizado (cfl_c almacenado en FL, e.g. 60.0 = FL060)
        cfl_val = getattr(f, "cfl_c", None)
        cfl_txt = "%03d" % int(round(cfl_val)) if cfl_val is not None else ""
        eobt_txt, eobt_is_ctot = self._eobt_slot(f)

        values = {
            "act": act_txt,
            "callsign": cs_txt,
            "type": S(getattr(f, "type", None)),
            "wake": S(getattr(f, "wake", "")),
            "eobt": eobt_txt,
            "rwydep": S(getattr(f, "deprwy", None)),
            "rwydes": S(getattr(f, "desrwy", None)),
            "park": S(getattr(f, "park", None)),
            "sid": S(getattr(f, "stand_sid_atc", "SID")),
            "campolibre": S(getattr(f, "rutrod", "-libre-")),
            "gate": S(getattr(f, "gate", "GT")),
            "holdp": hp_val,
            "hrls": hrls_txt,
            "cfl": cfl_txt,
            "rules": S(getattr(f, "fr", ""))[:1],
            "resto": "",
            "resto_fijo": "",
        }

        if is_veh:
            osf_pof_v = getattr(f, "OSF_pof", None)
            if osf_pof_v in (Aircraft.CRUREQ, Aircraft.CROSSING):
                values["pista_ent"] = S(getattr(f, "cru_runway", ""))
            else:
                values["pista_ent"] = S(getattr(f, "ent_runway", ""))
            values["anotaciones"] = S(getattr(f, "pvh_notes", ""))

        atc_status = getattr(f, "ATC_status", None) or "ATC_MISSING"
        img_file_str = "img/" + atc_status
        img_abs_path = os.path.join(conf.common_dir, img_file_str)

        # Start flashing fields
        if atc_status == Aircraft.ATC_MISSING:
            self.start_blink_by_callsign(cs_txt, "autorizacion", period_ms=400)
        else:
            self.stop_blink_by_callsign(cs_txt, "autorizacion")

        # Parpadeo selectivo: solo si este sector esta involucrado
        should_blink_cs = False
        if f.pedir_trf or f.trans_atc_pos:
            sector_list = (self.sector or "").split(",")
            should_blink_cs = any(s == f.atc_sector or s == f.next_atc_sector for s in sector_list)
        if should_blink_cs:
            self.start_blink_by_callsign(cs_txt, "callsign", period_ms=500)
        else:
            self.stop_blink_by_callsign(cs_txt, "callsign")
        # End flashing fields

        field_colors = {
            "act": act_color,
            "callsign": cs_color,
            "wake": wake_color,
        }
        if not hrls_enabled:
            field_colors["hrls"] = "red"

        if is_veh:
            # Vehiculo con PVH: campos en azul; callsign en blanco en la ultima zona o transferido
            blue = "#5599FF"
            field_colors["callsign"] = "white" if (zona_idx == self.last_zona_idx or should_blink_cs) else blue
            field_colors["pista_ent"] = blue
            field_colors["anotaciones"] = blue

        ficha = {
            "fields": field_names,
            "values": values,
            "local_dep": local_dep,
            "local_des": local_des,
            "field_colors": field_colors,
            "eobt_mode": ("ctot" if eobt_is_ctot else "eobt"),  # para resaltes del slot eobt/ctot
            # Resalte CTOT: fondo blanco (color de fuente sin cambios); no se toca en modo eobt.
            "field_bg": ({"eobt": "white"} if eobt_is_ctot else {}),
            "images": {  # << NUEVO: mapa de imágenes por campo
                "autorizacion": img_abs_path
            },
            "x_offset": saved_x_offset,  # mantener coqueo previo
            "is_veh": is_veh,          # True si es vehiculo con PVH
        }

        # IMPORTANTE: Si la ficha ya existe en esta zona, actualizarla en lugar de duplicar
        existing_found = None
        if cs:
            for idx, existing_ficha in enumerate(self.zonas[zona_idx]["fichas"]):
                existing_cs = existing_ficha.get("values", {}).get("callsign")
                if existing_cs == cs_txt:
                    existing_found = idx
                    break
        
        if existing_found is not None:
            # Actualizar ficha existente preservando campos extendidos
            existing_ficha = self.zonas[zona_idx]["fichas"][existing_found]
            existing_x_offset = existing_ficha.get("x_offset", saved_x_offset)
            existing_ficha.update(ficha)
            existing_ficha["x_offset"] = existing_x_offset
        else:
            # Nueva ficha
            self.zonas[zona_idx]["fichas"].append(ficha)

        cs = getattr(f, "callsign", None)
        if cs:
            self.fs_processed.add(cs)

        cs = getattr(f, "callsign", None)
        if cs:
            self.fs_processed.add(cs)

            # --- gestión de timer de última zona ---
            # índice de la última zona (interno 0-based)
            last_idx = max(0, min(self.zonas_count - 1,
                                  getattr(self, "last_zona", self.zonas_count) - 1))

            if zona_idx == last_idx and getattr(f, "OSF_pof", None) not in (Aircraft.MAP, Aircraft.GA):
                # entra (o está) en última zona y NO es MAP/GA → arrancar / actualizar timer
                t_now = getattr(self.radisplay, "t", None)
                if t_now is not None:
                    self.fs_last_zone_entry[cs] = t_now
            else:
                # está en otra zona o es MAP/GA → eliminar timer si lo hubiera
                if cs in self.fs_last_zone_entry:
                    del self.fs_last_zone_entry[cs]

        # Redibujar para mostrar la nueva ficha
        self.draw_zonas()

    def _add_obstaculo_strip(self):
        """
        Crea una ficha 'obstáculo' local (sin GTA) en la zona 2 (índice 1).
        """
        zona_idx = 1 if self.zonas_count > 1 else 0

        ficha = {
            # "fields": ["resto", "obstaculo", "resto"],
            "fields": ["obstaculo"],
            "values": {"obstaculo": ""},
            "local_dep": False,
            "local_des": False,
            "field_bg": {"obstaculo": "#ffffff"},  # fondo blanco por defecto
            "x_offset": 0,
            # meta para próximas fases (color editable, etc.)
            "is_obstaculo": True,
        }

        self.zonas[zona_idx]["fichas"].append(ficha)
        self.draw_zonas()

    def receive_transferred_obstaculo(self, obstaculo_texto, obstaculo_color):
        """
        Recibe un obstáculo transferido desde otro sector.
        Lo inserta arriba del todo (zona 0, posición 0).
        """
        zona_idx = 0  # Zona superior (arriba del todo)
        
        ficha = {
            "fields": ["obstaculo"],
            "values": {"obstaculo": obstaculo_texto},
            "local_dep": False,
            "local_des": False,
            "field_bg": {"obstaculo": obstaculo_color},
            "x_offset": 0,
            "is_obstaculo": True,
        }
        
        # Insertar al inicio (arriba del todo)
        self.zonas[zona_idx]["fichas"].insert(0, ficha)
        self.draw_zonas()
        
        print("Obstáculo recibido y añadido arriba del todo: '%s'" % obstaculo_texto)

    # ============================
    # Boton Obstaculos
    # ============================
    def _status_image_path(self, atc_status):
        """Devuelve la ruta absoluta del GIF de estado ATC o None si no procede."""
        if not atc_status:
            return None
        img_file_str = "img/%s" % atc_status
        return os.path.join(conf.common_dir, img_file_str)

    def _get_status_photo(self, atc_status):
        """
        Carga (y cachea) un tk.PhotoImage para el estado dado.
        Devuelve None si no existe o hay error.
        """
        path = self._status_image_path(atc_status)
        if not path or not os.path.exists(path):
            return None

        if not hasattr(self, "_photo_cache"):
            self._photo_cache = {}

        photo = self._photo_cache.get(path)
        if photo:
            return photo

        try:
            photo = tk.PhotoImage(file=path)  # GIF
            self._photo_cache[path] = photo
            return photo
        except Exception:
            return None

    # ============================
    # Helpers de campos
    # ============================
    def _field_width(self, name):
        w = self.field_defs.get(name, {}).get("width", self.default_field_width)
        try:
            return float(w)
        except:
            return float(self.default_field_width)

    def _is_flex(self, name):
        w = str(self.field_defs.get(name, {}).get("width", "")).lower()
        return w in ("flex", "auto", "*")

    def _field_value(self, name):
        v = self.field_defs.get(name, {}).get("value", "")
        return "" if v is None else str(v)

    def _find_flight_by_callsign(self, callsign):
        """
        Devuelve el objeto vuelo (f) cuyo callsign coincide, o None si no está.
        """
        if not callsign:
            return None
        for f in getattr(self.radisplay, "flights", []):
            if getattr(f, "callsign", None) == callsign:
                return f
        return None

    # ============================
    # Gestión de alturas de zonas
    # ============================
    def update_zona_heights(self):
        total = sum(self.zona_heights)
        if total != 1:
            self.zona_heights = [h / total for h in self.zona_heights]

    # ============================
    # Parpadeo de campos (texto/imagen)
    # ============================
    def _ensure_blink_structs(self):
        if not hasattr(self, "_blink_tasks"):
            self._blink_tasks = {}  # key=("cs", callsign, field_name) -> {"after_id":..., "visible":bool, "period":int}

    def _field_index(self, zona_idx, ficha_idx, field_name):
        try:
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        except Exception:
            return None
        try:
            return ficha.get("fields", []).index(field_name)
        except ValueError:
            return None

    def _field_tag_base(self, zona_idx, ficha_idx, field_name):
        fi = self._field_index(zona_idx, ficha_idx, field_name)
        if fi is None:
            return None
        return "field_%d_%d_%d" % (zona_idx, ficha_idx, fi)

    def start_blink_by_callsign(self, callsign, field_name, period_ms=400):
        if not callsign or not field_name:
            return
        self._ensure_blink_structs()
        key = ("cs", callsign, field_name)

        # reinicia si ya existe
        self.stop_blink_by_callsign(callsign, field_name)

        self._blink_tasks[key] = {
            "visible": True,
            "period": int(period_ms),
            "after_id": None,
        }
        self._blink_tick(key)

    def stop_blink_by_callsign(self, callsign, field_name):
        if not hasattr(self, "_blink_tasks"):
            return
        key = ("cs", callsign, field_name)
        task = self._blink_tasks.get(key)
        if not task:
            return

        after_id = task.get("after_id")
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass

        # forzar visible solo del CONTENIDO
        found = self._find_ficha_by_callsign(callsign)
        if found:
            zi, fi, _ = found
            base = self._field_tag_base(zi, fi, field_name)
            if base:
                content_tag = base + "_content"
                try:
                    self.canvas.itemconfigure(content_tag, state="normal")
                except Exception:
                    pass

        self._blink_tasks.pop(key, None)

    def _blink_tick(self, key):
        task = self._blink_tasks.get(key)
        if not task:
            return

        _, callsign, field_name = key
        found = self._find_ficha_by_callsign(callsign)
        content_tag = None
        if found:
            zi, fi, _ = found
            base = self._field_tag_base(zi, fi, field_name)
            if base:
                content_tag = base + "_content"

        if content_tag:
            try:
                if task["visible"]:
                    # ocultar SOLO el contenido (texto/imagen)
                    self.canvas.itemconfigure(content_tag, state="hidden")
                    task["visible"] = False
                else:
                    self.canvas.itemconfigure(content_tag, state="normal")
                    task["visible"] = True
            except Exception:
                pass

        try:
            task["after_id"] = self.root.after(task["period"], lambda k=key: self._blink_tick(k))
        except Exception:
            self._blink_tasks.pop(key, None)

    def warning_toggle(self):
        """
        Alterna OSF_warning del vuelo de la ficha seleccionada y reconstruye la ficha.
        El color rojo del callsign se aplicará en insert_fs/_callsign_text_color.
        """
        if not getattr(self, "selected_line", None):
            return

        zi, fi = self.selected_line
        if not (0 <= zi < len(self.zonas)) or not (0 <= fi < len(self.zonas[zi]["fichas"])):
            return

        ficha = self.zonas[zi]["fichas"][fi]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        # Alternar flag
        f.OSF_warning = not bool(getattr(f, "OSF_warning", False))

        # Notificar al GTA
        try:
            self.radisplay.sendMessage({
                "message": "set_osf_warning",
                "cs": f.callsign,
                "osf_warning": f.OSF_warning
            })
        except Exception:
            pass

    # ============================
    # Eventos
    # ============================
    def on_resize(self, event):
        self.draw_zonas()

    def _nudge_ficha(self, zona_idx, ficha_idx, direction):
        """
        Coqueo.
        Mueve visualmente la ficha a izq/der dentro de su misma zona.
        direction: -1 (izquierda) o +1 (derecha)
        """
        try:
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        except Exception:
            return

        curr = int(ficha.get("x_offset", 0))
        step = self.nudge_step if direction >= 0 else -self.nudge_step
        new_off = curr + step

        # Limitar desplazamiento acumulado
        if new_off > self.max_nudge:
            new_off = self.max_nudge
        if new_off < -self.max_nudge:
            new_off = -self.max_nudge

        if new_off != curr:
            ficha["x_offset"] = new_off
            self.draw_zonas()

    def on_click(self, event):
        canvas_height = self.canvas.winfo_height()
        y_positions = [0]
        cumulative = 0
        for height in self.zona_heights[:-1]:
            cumulative += height
            y_positions.append(int(cumulative * canvas_height))
        click_y = event.y
        tolerance = 6
        for i, y in enumerate(y_positions[1:], 1):
            if abs(click_y - y) < tolerance:
                self.dragging = i
                return

        # --- Clic en bandas negras: coqueo izquierda/derecha ---
        cw = self.canvas.winfo_width()
        m = self.margin

        # ¿qué fila (ficha) hay a esta altura?
        pos = self.get_line_at(event.x, event.y)
        if pos:
            zi, fi = pos
            # Izquierda: dentro de la banda negra izquierda
            if event.x < m:
                self._nudge_ficha(zi, fi, direction=-1)
                return
            # Derecha: banda negra derecha, evitando la zona del scrollbar (últimos 15px)
            if (cw - m) <= event.x <= (cw - 15):
                self._nudge_ficha(zi, fi, direction=+1)
                return

        if event.x > self.canvas.winfo_width() - 15:
            for i, (y0, y1, has_scroll, thumb_y0, thumb_y1) in enumerate(self.scrollbar_positions):
                if has_scroll and y0 <= event.y <= y1:
                    if thumb_y0 <= event.y <= thumb_y1:
                        self.active_scroll = {
                            "zona": i,
                            "start_y": event.y,
                            "orig_offset": self.zonas[i]["scroll_offset"]
                        }
                        return
                    else:
                        delta = 0
                        if thumb_y0 >= event.y:
                            delta = 1
                        elif event.y >= thumb_y1:
                            delta = -1
                        total = len(self.zonas[i]["fichas"])
                        visible = int((y1 - y0) / 27)
                        max_offset = total - visible
                        if max_offset > 0:
                            self.zonas[i]["scroll_offset"] = max(
                                0, min(max_offset, self.zonas[i]["scroll_offset"] + delta)
                            )
                            self.draw_zonas()
                        return

    def on_drag(self, event):
        if self.dragging is not None:
            canvas_height = self.canvas.winfo_height()
            new_y = max(50, min(event.y, canvas_height - 50))
            prev_y = sum(self.zona_heights[:self.dragging - 1]) * canvas_height
            next_y = sum(self.zona_heights[:self.dragging + 1]) * canvas_height
            new_height_prev = (new_y - prev_y) / float(canvas_height)
            new_height_next = (next_y - new_y) / float(canvas_height)
            if new_height_prev > 0.1 and new_height_next > 0.1:
                self.zona_heights[self.dragging - 1] = new_height_prev
                self.zona_heights[self.dragging] = new_height_next
                self.update_zona_heights()
                self.draw_zonas()
        elif self.active_scroll:
            i = self.active_scroll["zona"]
            y0, y1, has_scroll, thumb_y0, thumb_y1 = self.scrollbar_positions[i]
            total = len(self.zonas[i]["fichas"])
            visible = int((y1 - y0) / 27)
            max_offset = total - visible
            if max_offset > 0:
                delta = event.y - self.active_scroll["start_y"]
                scroll_area = y1 - y0 - 40
                new_offset = self.active_scroll["orig_offset"] - int(delta * max_offset / float(scroll_area))
                self.zonas[i]["scroll_offset"] = max(0, min(max_offset, new_offset))
                self.draw_zonas()

    def on_release(self, event):
        self.dragging = None
        self.active_scroll = None

    def on_motion(self, event):
        self.active_scroll = None
        canvas_height = self.canvas.winfo_height()
        y_positions = [0]
        cumulative = 0
        for height in self.zona_heights[:-1]:
            cumulative += height
            y_positions.append(int(cumulative * canvas_height))
        mouse_y = event.y
        tolerance = 6
        for y in y_positions[1:]:
            if abs(mouse_y - y) < tolerance:
                self.canvas.config(cursor="sb_v_double_arrow")
                return
        self.canvas.config(cursor="")

    def on_mousewheel(self, event):
        if self.scrollbar_positions:
            for i, (y0, y1, has_scroll, _, _) in enumerate(self.scrollbar_positions):
                if has_scroll and y0 <= self.canvas.winfo_pointery() - self.canvas.winfo_rooty() <= y1:
                    delta = 1 if event.delta > 0 else -1
                    total = len(self.zonas[i]["fichas"])
                    visible = int((y1 - y0) / 27)
                    max_offset = total - visible
                    if max_offset > 0:
                        self.zonas[i]["scroll_offset"] = max(
                            0, min(max_offset, self.zonas[i]["scroll_offset"] + delta)
                        )
                        self.draw_zonas()
                    break

    # ============================
    # Seleccion de fichas e interccion con etiqueta raster
    # TODO: Parece que no va fino. Repasar
    # ============================
    def on_middle_click(self, event):
        # Saber qué ficha está bajo el puntero
        pos = self.get_line_at(event.x, event.y)
        self._drag_started = False  # aún no sabemos si habrá arrastre

        if pos is None:
            # Nada bajo el clic → si había selección, NO la cambies.
            self.dragging_line = None
            self.draw_zonas()  # necesario?
            return

        zi, fi = pos
        zona_idx, ficha_idx = pos
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]

        # Si se ha clicado la ficha extendida, redirigir a la ficha madre
        if ficha.get("is_extended"):
            parent_cs = ficha.get("parent_callsign", "")
            if parent_cs:
                parent_found = self._find_ficha_by_callsign(parent_cs)
                if parent_found:
                    zi, fi = parent_found[0], parent_found[1]
                    zona_idx, ficha_idx = zi, fi
                    ficha = self.zonas[zi]["fichas"][fi]

        cs = ficha.get("values", {}).get("callsign", "")
        f = self._find_flight_by_callsign(cs)
        if f:
            try:
                self.radisplay.toggle_select(f, True)
            except Exception as e:
                print("Error en toggle_select:", e)

        # Toggle de selección:
        if not self.selected_line:
            # No había ninguna seleccionada → selecciona esta
            self.selected_line = (zi, fi)
        else:
            if self.selected_line == (zi, fi):
                # Clic sobre la misma → deseleccionar
                self.selected_line = None
            else:
                # Había otra seleccionada → cambiar selección a esta
                self.selected_line = (zi, fi)

        # Preparar posible arrastre con el mismo clic central
        self.dragging_line = (zi, fi)
        self.draw_zonas()

    def on_middle_drag(self, event):
        if self.dragging_line:
            src_zona_idx, src_line_idx = self.dragging_line
            dst = self.get_line_position(event.x, event.y)
            if dst:
                dst_zona_idx, dst_line_idx = dst
                if 0 <= src_line_idx < len(self.zonas[src_zona_idx]["fichas"]):
                    ficha = self.zonas[src_zona_idx]["fichas"][src_line_idx]
                    cs = ficha.get("values", {}).get("callsign", "")

                    # Buscar ficha extendida antes de hacer ningún pop
                    ext_pos = None
                    if not ficha.get("is_extended") and cs:
                        ext_pos = self._find_extended_for_callsign(cs)

                    # Pop ficha principal
                    self.zonas[src_zona_idx]["fichas"].pop(src_line_idx)

                    # Pop ficha extendida (si existe), ajustando índice si hace falta
                    ext_ficha = None
                    if ext_pos:
                        ezi, efi = ext_pos
                        if ezi == src_zona_idx and efi > src_line_idx:
                            efi -= 1  # el pop anterior desplazó los índices
                        ext_ficha = self.zonas[ezi]["fichas"].pop(efi)

                    dst_fichas = self.zonas[dst_zona_idx]["fichas"]
                    dst_line_idx = max(0, min(dst_line_idx, len(dst_fichas)))
                    dst_fichas.insert(dst_line_idx, ficha)

                    if ext_ficha is not None:
                        # Insertar extendida en la misma posición → queda debajo de la madre
                        dst_fichas.insert(dst_line_idx, ext_ficha)
                        # La ficha madre quedó desplazada +1
                        self.dragging_line = (dst_zona_idx, dst_line_idx + 1)
                    else:
                        self.dragging_line = (dst_zona_idx, dst_line_idx)

                    self._drag_started = True

                    # --- actualizar timer de última zona por DnD ---
                    if cs:
                        last_idx = max(0, min(self.zonas_count - 1,
                                              getattr(self, "last_zona", self.zonas_count) - 1))
                        # buscamos el vuelo real por si necesitamos OSF_pof
                        f = self._find_flight_by_callsign(cs)
                        if dst_zona_idx == last_idx and (not f or getattr(f, "OSF_pof", None) not in (Aircraft.MAP, Aircraft.GA)):
                            t_now = getattr(self.radisplay, "t", None)
                            if t_now is not None:
                                self.fs_last_zone_entry[cs] = t_now
                        else:
                            self.fs_last_zone_entry.pop(cs, None)

        self.draw_zonas()

    def on_middle_release(self, event):
        if self.dragging_line and self._drag_started:
            self.selected_line = self.dragging_line

        # Reset de estados de arrastre
        self.dragging_line = None
        self._drag_started = False
        self.draw_zonas()

    # seleccion/deseleccion desde el raster
    def clicklabel(self, callsign, raster_call=False):
        """
        Selección desde fuera (raster):
          - Busca la ficha por callsign.
          - Si no había selección, la crea.
          - Si había otra, la reemplaza por esta.
        """
        found = self._find_ficha_by_callsign(callsign)
        if not found:
            # No encontrada: no cambia estado; opcionalmente log
            try:
                print("clicklabel: callsign no encontrado:", callsign)
            except Exception:
                pass
            return

        zi, fi, _ = found

        # Toggle selection:
        if not self.selected_line:
            # No había ninguna seleccionada → selecciona esta
            self.selected_line = (zi, fi)
        else:
            if self.selected_line == (zi, fi):
                # la misma → deseleccionar
                self.selected_line = None
            else:
                # Había otra seleccionada → cambiar selección a esta
                self.selected_line = (zi, fi)

        # Asegura que no quede “arrastre” previo activo
        self.dragging_line = None
        self._drag_started = False

        # Redibuja para mostrar el recuadro blanco
        self.draw_zonas()

    # ============================
    # Helpers de selección de ficha (línea)
    # ============================
    def get_line_at(self, x, y):
        canvas_height = self.canvas.winfo_height()
        y_start = 0
        line_height = self.ficha_height + self.ficha_sep
        for i, zona in enumerate(self.zonas):
            zona_height = self.zona_heights[i] * canvas_height
            y_end = y_start + zona_height
            total = len(zona["fichas"])
            for line_idx in range(total):
                line_bottom = y_end - line_idx * line_height - self.ficha_sep
                line_top = line_bottom - self.ficha_height
                if line_top <= y <= line_bottom:
                    return (i, line_idx)
            y_start = y_end
        return None

    def get_line_position(self, x, y):
        canvas_height = self.canvas.winfo_height()
        y_start = 0
        line_height = self.ficha_height + self.ficha_sep
        for i, zona in enumerate(self.zonas):
            zona_height = self.zona_heights[i] * canvas_height
            y_end = y_start + zona_height
            if y_start <= y <= y_end:
                relative_y = y_end - y
                idx = int(relative_y / line_height)
                return (i, idx)
            y_start = y_end
        return None

    # ============================
    # Dibujo
    # ============================
    def _color_for_ficha(self, ficha, zona_idx):
        local_dep = ficha.get("local_dep", False)
        local_des = ficha.get("local_des", False)

        if local_dep:
            if self.bahia_type != 'CLR' and zona_idx == 0:
                return self.color_dep_noasum
            else:
                return self.color_dep_asum
        elif local_des:
            if zona_idx == 0:
                return self.color_des_noasum
            else:
                return self.color_des_asum
        return self.color_des_asum

    def _eobt_slot(self, f):
        """
        Slot único eobt/ctot: muestra el CTOT del ejercicio (f.ctot) si está
        registrado; si no, el EOBT habitual (con su fallback a etd/time).
        Devuelve (texto "HHMM", is_ctot).
        """
        ctot = getattr(f, "ctot", None) if f else None
        if ctot:
            return "%02d%02d" % (ctot.hour, ctot.minute), True

        eobt = getattr(f, "eobt", None) if f else None
        if eobt:
            return "%02d%02d" % (eobt.hour, eobt.minute), False
        fallback = getattr(f, "etd", None) or getattr(f, "time", None) or ""
        return ("" if fallback is None else str(fallback)), False

    def _act_text_color(self, f):
        pof = getattr(f, "OSF_pof", None)
        txt = "%3s" % (pof or "")

        if pof in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
            txt = "TAX"
        elif pof in (Aircraft.INCOMING, Aircraft.PREPARING):
            txt = "---"
        elif pof == Aircraft.LANDED:
            txt = "LDG"
        elif pof == Aircraft.AIRBORNE:
            txt = "DEP"
        elif pof == Aircraft.STARTREQ:
            txt = "S/U"
        elif pof == Aircraft.PUSHREQ:
            txt = "P/B"
        elif pof == Aircraft.TAXIREQ:
            txt = "TAX"
        elif pof == Aircraft.DEPREQ:
            txt = "DEP"
        elif pof == Aircraft.LDGREQ:
            txt = "LDG"
        # Cruce / entrada a pista (Fase 4 bloque 2)
        elif pof in (Aircraft.CRUREQ, Aircraft.CROSSING):
            txt = "CRU"
        elif pof in (Aircraft.ENTERING, Aircraft.ENTREQ):
            txt = "ENT"
        elif pof == Aircraft.LIB:
            txt = "LIB"

        if pof == Aircraft.INCOMING:
            col = "orange"
        elif pof in (Aircraft.LANDED, Aircraft.AIRBORNE, Aircraft.PARKED, Aircraft.SALIDA, Aircraft.LIB):
            col = "grey"
        elif pof in (Aircraft.STARTREQ, Aircraft.STICEREQ, Aircraft.REAREQ,
                     Aircraft.PUSHREQ, Aircraft.TAXIREQ, Aircraft.DEPREQ, Aircraft.LDGREQ, Aircraft.TGLREQ,
                     Aircraft.CRUREQ, Aircraft.ENTREQ):
            col = "yellow"
        elif pof in (Aircraft.MAP, Aircraft.GA, Aircraft.ABORT):
            col = "red"
        else:
            col = self.color_dep_asum

        return txt, col

    def _callsign_text_color(self, f, zona_idx, warning=False):
        cs_txt = getattr(f, "callsign", "") or ""
        
        # Si está transferido (release_atc_pos), SIEMPRE blanco (prioridad máxima)
        if getattr(f, "release_atc_pos", False):
            return cs_txt, 'white'
        
        # Si tiene warning y NO está transferido, rojo
        if warning:
            return cs_txt, "red"

        sector_list = (self.sector or "").split(",")
        local_ads = getattr(self.fir, "local_ads", {}) or {}
        cs_color = 'white'

        for sector in sector_list:
            ads = local_ads.get(sector, set())
            if getattr(f, "adep", None) in ads:
                cs_color = self.color_dep_noasum if (self.bahia_type != "CLR" and zona_idx == 0) else self.color_dep_asum
                break
            elif getattr(f, "ades", None) in ads:
                cs_color = self.color_des_noasum if (zona_idx == 0) else self.color_des_asum
                break

        return cs_txt, cs_color

    def _wake_text_color(self, f):
        sector_list = (self.sector or "").split(",")
        local_ads = getattr(self.fir, "local_ads", {}) or {}
        wake_color = 'white'

        for sector in sector_list:
            ads = local_ads.get(sector, set())
            if getattr(f, "adep", None) in ads:
                wake_color = self.color_dep_noasum if (self.bahia_type != "CLR") else self.color_dep_asum
                if f.wake in ('H', 'H-', 'H+', 'J'):
                    wake_color = 'yellow'
                elif f.wake in ('L', 'L+'):
                    wake_color = 'white'
                break
            elif getattr(f, "ades", None) in ads:
                wake_color = self.color_des_noasum if (self.bahia_type != "CLR") else self.color_des_asum
                if f.wake in ('H', 'H-', 'H+', 'J'):
                    wake_color = 'yellow'
                elif f.wake in ('L', 'L+'):
                    wake_color = 'white'
                break

        return wake_color

    def _draw_autorizacion(self, x0, y0, x1, y1, ficha, tags):
        cs = ficha.get("values", {}).get("callsign", "")
        f = self._find_flight_by_callsign(cs)
        img = None
        if f:
            img_name = "img/" + str(getattr(f, "ATC_status", "ATC_MISSING"))
            img_path = os.path.join(conf.common_dir, img_name)
            try:
                img = tk.PhotoImage(file=img_path)
            except Exception:
                img = None

        # Guarda referencia para que no la recoja el GC
        if not hasattr(self, "_img_cache"):
            self._img_cache = {}
        if img:
            self._img_cache[(cs, img_name)] = img

        # centro del campo
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0

        if img:
            self.canvas.create_image(cx, cy, image=img, tags=tags)
        else:
            # fallback: un texto placeholder como contenido (también con la tag de contenido)
            self.canvas.create_text(cx, cy, text="?", fill="#ccc", font=self.font_style, tags=tags)

    def draw_zonas(self):
        # No redibujar mientras hay un campo en edicion (Entry inline): el redibujado
        # periodico movia o tapaba el campo y hacia perder lo escrito. Al cerrar la
        # edicion (guardar o cancelar) se limpia _edit_entry y se redibuja.
        if self._edit_entry is not None and self._edit_entry_var is not None:
            try:
                if self._edit_entry.winfo_exists():
                    return
            except Exception:
                pass
            # El Entry ya no existe: limpiar el estado de edicion
            self._edit_entry = None
            self._edit_entry_var = None
        try:
            if not self.canvas.winfo_exists():
                return
        except Exception:
            return
        self.canvas.delete("all")
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        margin = self.margin
        usable_width = canvas_width - 2 * margin
        self._field_positions = {}  # (zona_idx, ficha_idx, nombre_campo) -> (x0, y0, x1, y1)

        y_start = 0
        self.scrollbar_positions = []

        ficha_h = self.ficha_height
        sep_h = self.ficha_sep
        line_height = ficha_h + sep_h

        for i, zona in enumerate(self.zonas):
            zona_height = self.zona_heights[i] * canvas_height
            y_end = y_start + zona_height

            self.canvas.create_rectangle(0, y_start, margin, y_end, fill="black", outline="")
            self.canvas.create_rectangle(canvas_width - margin, y_start, canvas_width, y_end, fill="black", outline="")

            total = len(zona["fichas"])
            visible = int(zona_height / line_height)
            offset = zona["scroll_offset"]
            max_offset = max(0, total - visible)
            offset = min(offset, max_offset)
            zona["scroll_offset"] = offset

            for line_idx in range(visible):
                actual_idx = offset + line_idx
                if actual_idx >= total:
                    break

                ficha = zona["fichas"][actual_idx]
                nombres_campos = ficha.get("fields", [])

                line_bottom = y_end - line_idx * line_height - sep_h
                line_top = line_bottom - ficha_h

                # Alertas aeroportuarias: alitas W/V en los margenes negros (fuera de la
                # ficha gris), leyendo la severidad del vuelo actual
                ficha_cs = ficha.get("values", {}).get("callsign", "")
                live_flight = self._find_flight_by_callsign(ficha_cs) if ficha_cs else None
                live_sev = getattr(live_flight, 'max_alert_severity', 0) if live_flight else 0
                if live_sev >= 1:
                    a_txt, a_col = ("V", "red") if live_sev >= 2 else ("W", "yellow")
                    alita_font = ("Helvetica", 9, "bold")
                    self.canvas.create_rectangle(
                        1, line_top, margin - 1, line_bottom,
                        fill=a_col, outline="", tags="alita")
                    self.canvas.create_text(
                        margin / 2, (line_top + line_bottom) / 2,
                        text=a_txt, fill="black", font=alita_font,
                        anchor="center", tags="alita")
                    self.canvas.create_rectangle(
                        canvas_width - margin + 1, line_top,
                        canvas_width - 1, line_bottom,
                        fill=a_col, outline="", tags="alita")
                    self.canvas.create_text(
                        canvas_width - margin / 2, (line_top + line_bottom) / 2,
                        text=a_txt, fill="black", font=alita_font,
                        anchor="center", tags="alita")

                fixed_total = 0.0
                flex_count = 0
                for nm in nombres_campos:
                    if self._is_flex(nm):
                        flex_count += 1
                    else:
                        fixed_total += self._field_width(nm)

                remaining = max(0.0, usable_width - fixed_total)
                flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

                row_offset = ficha.get("x_offset", 0)
                x_cursor = margin + row_offset
                x_max = margin + usable_width + row_offset

                base_color = self._color_for_ficha(ficha, i)
                field_colors = ficha.get("field_colors", {})

                for field_idx, name in enumerate(nombres_campos):
                    w = (flex_each if self._is_flex(name) else self._field_width(name))

                    x_start = x_cursor
                    x_end = x_cursor + w

                    if x_start >= x_max:
                        break
                    if x_end > x_max:
                        x_end = x_max

                    # bg_color = self.ficha_bg
                    field_bg_overrides = ficha.get("field_bg", {})  # dict opcional {nombre_campo: color}
                    bg_color = field_bg_overrides.get(name, self.ficha_bg)

                    # Texto negro si es campo 'obstaculo'
                    if name == "obstaculo":
                        text_color = "#000000"
                    else:
                        text_color = field_colors.get(name, base_color)

                    field_tag = "field_%d_%d_%d" % (i, actual_idx, field_idx)
                    rect_tag = field_tag + "_rect"
                    content_tag = field_tag + "_content"

                    # Guarda la caja del campo para poder poner el Entry encima al editar
                    self._field_positions[(i, actual_idx, name)] = (x_start, line_top, x_end, line_bottom)

                    self.canvas.create_rectangle(
                        x_start, line_top, x_end, line_bottom,
                        fill=bg_color, outline="", tags=field_tag
                    )

                    if name == "autorizacion":
                        # Dibuja la imagen con la tag de contenido
                        self._draw_autorizacion(x_start, line_top, x_end, line_bottom, ficha,
                                                tags=(field_tag, content_tag))
                    else:
                        # Texto normal (contenido que parpadea)
                        if not self._is_flex(name):
                            valor_campo = ficha.get("values", {}).get(name, self._field_value(name))
                            self.canvas.create_text(
                                (x_start + x_end) / 2,
                                (line_top + line_bottom) / 2,
                                text=valor_campo,
                                fill=text_color,
                                font=self.font_style,
                                tags=(field_tag, content_tag)
                            )

                    self.canvas.tag_bind(
                        field_tag, "<Button-1>",
                        (lambda z=i, f=actual_idx, fi=field_idx, t=name:
                         (lambda e: self.left_clicked(e, z, f, fi, t)))()
                    )
                    self.canvas.tag_bind(
                        field_tag, "<Button-3>",
                        (lambda z=i, f=actual_idx, fi=field_idx, t=name:
                         (lambda e: self.right_clicked(e, z, f, fi, t)))()
                    )

                    if field_idx > 0:
                        x_sep = int(round(x_start))
                        self.canvas.create_line(
                            x_sep, line_top, x_sep, line_bottom,
                            fill="#111111", width=1, tags=(field_tag, "relief")
                        )
                        self.canvas.create_line(
                            x_sep + 1, line_top, x_sep + 1, line_bottom,
                            fill="#333333", width=1, tags=(field_tag, "relief")
                        )
                        self.canvas.tag_raise(field_tag)

                    x_cursor = x_end
                    if x_cursor >= x_max:
                        break

                _hl = (self.dragging_line == (i, actual_idx)) or (self.selected_line == (i, actual_idx))
                if not _hl and ficha.get("is_extended"):
                    # Resaltar ficha extendida si su madre está seleccionada/arrastrando
                    _parent_cs = ficha.get("parent_callsign", "")
                    for _ref in (self.selected_line, self.dragging_line):
                        if _ref and _ref[0] == i:
                            _rfi = _ref[1]
                            if 0 <= _rfi < len(self.zonas[i]["fichas"]):
                                _rf = self.zonas[i]["fichas"][_rfi]
                                if not _rf.get("is_extended") and _rf.get("values", {}).get("callsign") == _parent_cs:
                                    _hl = True
                                    break
                if _hl:
                    self.canvas.create_rectangle(
                        margin, line_top, margin + usable_width, line_bottom,
                        outline="white", width=2
                    )

            has_scroll = total > visible
            thumb_y0 = thumb_y1 = 0
            if has_scroll:
                scroll_x = canvas_width - 15
                scroll_y0 = y_start + 10
                scroll_y1 = y_end - 10
                self.canvas.create_rectangle(scroll_x, scroll_y0, scroll_x + 10, scroll_y1,
                                             fill="#cccccc", outline="black")

                scroll_area = scroll_y1 - scroll_y0 - 20
                thumb_height = max(20, scroll_area * visible / float(total)) if total > 0 else 20
                thumb_pos = (scroll_area * offset / float(total)) if total > 0 else 0
                thumb_y1 = scroll_y1 - 10 - thumb_pos
                thumb_y0 = thumb_y1 - thumb_height
                self.canvas.create_rectangle(scroll_x + 1, thumb_y0, scroll_x + 9, thumb_y1,
                                             fill="#888888", outline="black")

                self.canvas.create_polygon(scroll_x + 5, scroll_y0,
                                           scroll_x + 10, scroll_y0 + 10,
                                           scroll_x, scroll_y0 + 10,
                                           fill="black")
                self.canvas.create_polygon(scroll_x + 5, scroll_y1,
                                           scroll_x + 10, scroll_y1 - 10,
                                           scroll_x, scroll_y1 - 10,
                                           fill="black")

            self.scrollbar_positions.append((y_start, y_end, has_scroll, thumb_y0, thumb_y1))
            y_start = y_end

            if i < len(self.zonas) - 1:
                sep_y = y_end
                self.canvas.create_line(0, sep_y + 1, canvas_width, sep_y + 1, fill="#777777", width=3, tags='sep')
                self.canvas.create_line(0, sep_y + 3, canvas_width, sep_y + 3, fill="#ffffff", width=1, tags='sep')
                self.canvas.create_line(0, sep_y + 6, canvas_width, sep_y + 6, fill="#777777", width=5, tags='sep')
                self.canvas.create_line(0, sep_y + 9, canvas_width, sep_y + 9, fill="#000000", width=1, tags='sep')
                self.canvas.create_line(0, sep_y + 11, canvas_width, sep_y + 11, fill="#777777", width=3, tags='sep')

        self.canvas.tag_raise('sep')

    # ============================
    # Callbacks de clic sobre campos
    # ============================
    def _on_act_click(self, zona_idx, ficha_idx):
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        # Cerrar extendida (si la hay) ANTES de cambiar estado/zona
        self._close_extended_by_callsign(callsign)

        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        sector = self.sector or ""
        if f.atc_sector is None or sector.find(f.atc_sector) < 0 or getattr(f, 'release_atc_pos', False):
            try:
                self.radisplay.sendMessage({"message": "assume", "sector": sector, "cs": callsign, "assumed": True})
            except Exception:
                pass
            f.atc_sector = sector

        local_dep = ficha.get("local_dep", False)
        local_des = ficha.get("local_des", False)

        pof_anterior = getattr(f, "OSF_pof", None)
        
        # BLOQUEO: No permitir cambio de estado con click izquierdo si está en REAREQ
        if pof_anterior == Aircraft.REAREQ:
            return
        
        pof_nuevo = pof_anterior
        backpark_seq = list(getattr(Aircraft, "OSF_BACKPARKSEQ", []))
        if not hasattr(self, "_backpark_callsigns"):
            self._backpark_callsigns = set()
        # Si el vuelo salió del flujo backpark por una accion externa, limpiamos marca.
        if callsign in self._backpark_callsigns and pof_anterior not in backpark_seq:
            self._backpark_callsigns.discard(callsign)

        # Flujo de vuelta al parking (solo para salidas marcadas en ABORT).
        if local_dep and callsign in self._backpark_callsigns and pof_anterior in backpark_seq:
            try:
                idx = backpark_seq.index(pof_anterior)
                if idx + 1 < len(backpark_seq):
                    pof_nuevo = backpark_seq[idx + 1]
                    print("[BACKPARK][ACT] %s: %s -> %s" % (callsign, pof_anterior, pof_nuevo))
            except ValueError:
                pass

        # Requests. La siguiente accion es siempre la autorizacion
        elif pof_anterior == "TXR":
            pof_nuevo = Aircraft.TAXIING_OUT if local_dep else Aircraft.TAXIING_IN
        elif pof_anterior == "PBR":
            pof_nuevo = Aircraft.PUSH
        elif pof_anterior == "LDR":
            pof_nuevo = Aircraft.LANDING
        elif pof_anterior == "SUR":
            pof_nuevo = Aircraft.STARTING
        elif pof_anterior == "DPR":
            pof_nuevo = Aircraft.DEPARTING
        elif pof_anterior == "TGL":
            pof_nuevo = Aircraft.LANDING

        # Flujo ENT request: ENR -> abre dialogo pista (que envia authorize_ent -> ENT)
        elif pof_anterior == Aircraft.ENTREQ:
            self.open_pista_entrada(callsign)
            return

        # Flujo CRU: CRR -> CRU -> LIB -> TAX (restaurar fase previa)
        elif pof_anterior == Aircraft.CRUREQ:
            pof_nuevo = Aircraft.CROSSING
        elif pof_anterior == Aircraft.CROSSING:
            pof_nuevo = Aircraft.LIB
        # Flujo ENT (vehiculos): ENT -> LIB -> TAX
        elif pof_anterior == Aircraft.ENTERING:
            pof_nuevo = Aircraft.LIB
        elif pof_anterior == Aircraft.LIB:
            pof_nuevo = getattr(f, 'pre_cru_pof', None) or getattr(f, 'pre_ent_pof', None) or Aircraft.TAXIING_OUT

        # Para MAP o GA lo siguiente natural es volver a la secuencia de llegadas
        elif pof_anterior in ("MAP", "GA"):
            pof_nuevo = Aircraft.OSF_ARRSEQ[0]

        elif local_dep and getattr(f, 'fr', None) != 'VEH' and pof_anterior in getattr(Aircraft, "PUSH_LIST", []):
            pof_nuevo = Aircraft.TAXIING_OUT

        elif (local_dep and getattr(f, 'fr', None) != 'VEH' and pof_anterior == Aircraft.STARTING
              and self._pushback_rule(f) == 'none'):
            # Stand sin retroceso en la hoja RetrocesosOSF: S/U -> TAX
            pof_nuevo = Aircraft.TAXIING_OUT

        elif local_dep and getattr(f, 'fr', None) != 'VEH' and pof_anterior in getattr(Aircraft, "OSF_DEPSEQ", []):
            seq = list(Aircraft.OSF_DEPSEQ)
            try:
                idx = seq.index(pof_anterior)
                if not (self.bahia_type == 'GND' and pof_anterior == Aircraft.TAXIING_OUT):
                    # Bloqueo HRLS: no permitir avanzar de L/U a DEP cuando HRLS no esta activo.
                    if pof_anterior == Aircraft.LININGUP and not bool(getattr(f, "hrls", False)):
                        pof_nuevo = pof_anterior
                    elif idx + 1 < len(seq):
                        pof_nuevo = seq[idx + 1]
            except ValueError:
                pass
        elif local_des and getattr(f, 'fr', None) != 'VEH' and pof_anterior in getattr(Aircraft, "OSF_ARRSEQ", []):
            seq = list(Aircraft.OSF_ARRSEQ)
            try:
                idx = seq.index(pof_anterior)
                if idx + 1 < len(seq):
                    pof_nuevo = seq[idx + 1]
            except ValueError:
                pass

        if pof_nuevo == pof_anterior:
            return

        if pof_nuevo == getattr(Aircraft, "TERMINATED", None):
            print("[BACKPARK][END] %s: reached TERMINATED" % callsign)
            self._backpark_callsigns.discard(callsign)

        f.OSF_pof = pof_nuevo
        try:
            self.radisplay.sendMessage({
                "message": "set_osf_pof",
                "cs": callsign,
                "osf_pof": pof_nuevo,
                "hacc": self._update_hacc(f)
            })
        except Exception:
            pass

        # self._update_hacc_and_send(f)

        act_txt, act_color = self._act_text_color(f)
        ficha.setdefault("values", {})["act"] = act_txt
        ficha.setdefault("field_colors", {})["act"] = act_color

        nueva_zona_idx = self.choose_zona(f, old_zona_idx=zona_idx)
        if pof_nuevo == getattr(Aircraft, "TERMINATED", None):
            # Al terminar backpark, fijar siempre la ultima zona de la bahia.
            nueva_zona_idx = max(0, self.zonas_count - 1)
        if nueva_zona_idx != zona_idx:
            if 0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"]):
                self.zonas[zona_idx]["fichas"].pop(ficha_idx)
                self.zonas[nueva_zona_idx]["fichas"].append(ficha)

        # --- actualizar timer de última zona por cambio de ACT ---
        cs = ficha.get("values", {}).get("callsign", "")
        if cs:
            last_idx = max(0, min(self.zonas_count - 1,
                                  getattr(self, "last_zona", self.zonas_count) - 1))
            if nueva_zona_idx == last_idx and getattr(f, "OSF_pof", None) not in (Aircraft.MAP, Aircraft.GA):
                t_now = getattr(self.radisplay, "t", None)
                if t_now is not None:
                    self.fs_last_zone_entry[cs] = t_now
            else:
                self.fs_last_zone_entry.pop(cs, None)

        # self.draw_zonas()

    def _get_ctx_flight(self):
        """
        Devuelve el objeto vuelo 'f' asociado al popup de ACCIONES (self._act_popup_ctx)
        o, en su defecto, a la línea seleccionada (self.selected_line).
        """
        zi = fi = None
        ctx = getattr(self, "_act_popup_ctx", None)
        if ctx and isinstance(ctx, tuple) and len(ctx) == 2:
            zi, fi = ctx
        elif getattr(self, "selected_line", None):
            zi, fi = self.selected_line
        else:
            return None

        try:
            ficha = self.zonas[zi]["fichas"][fi]
        except Exception:
            return None

        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return None

        return self._find_flight_by_callsign(callsign)

    def _show_act_popup(self, at_x=None, at_y=None):
        """
        Popup 'ACCIONES' con dos zonas:
          - Zona 1: opciones dinámicas según si el vuelo es salida local o llegada local
          - Zona 2: fija
        """
        # Cerrar si ya hay uno
        if hasattr(self, "_act_popup") and self._act_popup and self._act_popup.winfo_exists():
            try:
                self._act_popup.destroy()
            except:
                pass

        # --- Identificar la ficha/vuelo sobre el que se abre el popup ---
        zi = fi = None
        f = None
        if hasattr(self, "_act_popup_ctx") and self._act_popup_ctx:
            try:
                zi, fi = self._act_popup_ctx
                ficha = self.zonas[zi]["fichas"][fi]
                cs = ficha.get("values", {}).get("callsign", "")
                if cs:
                    f = self._find_flight_by_callsign(cs)
            except Exception:
                f = None

        # Determinar si es salida local o llegada local
        is_dep_local = False
        is_arr_local = False
        if f:
            try:
                sector_list = (self.sector or "").split(",")
                local_ads = getattr(self.fir, "local_ads", {}) or {}
                for sec in sector_list:
                    ads = local_ads.get(sec, set())
                    if getattr(f, "adep", None) in ads:
                        is_dep_local = True
                        break
                    if getattr(f, "ades", None) in ads:
                        is_arr_local = True
                        break
            except Exception:
                pass

            # Fallback por si no se detectó local: si no tenemos nada, usa heurística básica
            if not (is_dep_local or is_arr_local):
                if getattr(f, "adep", None):
                    is_dep_local = True
                elif getattr(f, "ades", None):
                    is_arr_local = True

        top = tk.Toplevel(self.root)
        self._act_popup = top
        try:
            top.wm_overrideredirect(1)
            top.wm_attributes("-topmost", 1)
        except:
            pass

        # Tamaño del popup
        popup_w, popup_h = 300, 400
        if at_x is None or at_y is None:
            at_x = self.root.winfo_rootx() + 30
            at_y = self.root.winfo_rooty() + 30
        top.geometry("%dx%d+%d+%d" % (popup_w, popup_h, int(at_x), int(at_y)))



        # Colores (ajustados al tema popup)
        bg_panel = self.body_popup
        bg_hdr = self.cabecera_popup
        fg_txt = "white"

        container = tk.Frame(top, bg=bg_panel, bd=1, relief="solid")
        container.pack(fill="both", expand=True)

        # Cabecera
        hdr = tk.Label(container, text="ACCIONES", bg=bg_hdr, fg=fg_txt,
                       font=('Lucida Sans Typewriter', 9, 'bold'))
        hdr.pack(side="top", fill="x")

        # Helper para filas
        def add_row(parent, r, text, on_click):
            btn = tk.Button(
                parent,
                width=1, height=0,
                bg=self.fondo_btn_popup,
                fg="white",
                relief="raised",
                bd=1,
                padx=0, pady=0,
                command=on_click
            )
            btn.grid(row=r, column=0, sticky="w", padx=1, pady=1, ipadx=1, ipady=0)
            btn.configure(font=("Lucida Sans Typewriter", 6))

            lbl = tk.Label(
                parent,
                text=text,
                bg=bg_panel,
                fg=fg_txt,
                font=('Lucida Sans Typewriter', 9),
                anchor="w"
            )
            lbl.grid(row=r, column=1, sticky="w", padx=6, pady=1)

            lbl.config(cursor="hand2")

            # ---> NUEVO: hacer clic también sobre el texto
            lbl.bind("<Button-1>", lambda e: on_click())

        # ===== ZONA 1 (dinámica) =====
        body1 = tk.Frame(container, bg=bg_panel)
        body1.pack(side="top", fill="x", padx=6, pady=(4, 2))

        is_veh = f and getattr(f, 'fr', None) == 'VEH' and getattr(f, 'has_pvh', False)
        cru_enabled = self._pvh_enabled()  # parametro de escenario 'pvh'

        if is_veh:
            veh_actions = []
            osf_pof = getattr(f, "OSF_pof", None) if f else None
            if osf_pof in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
                veh_actions.append("SOLICITUD ENT")
                veh_actions.append("AUTORIZACION ENT")
                veh_actions.append("SOLICITUD CRU")
            elif osf_pof == Aircraft.ENTREQ:
                veh_actions.append("AUTORIZACION ENT")
            if osf_pof in (Aircraft.CROSSING, Aircraft.ENTERING):
                veh_actions.append("ANOTACION RWY LIBRE")
            if osf_pof == Aircraft.LIB:
                veh_actions.append("AUTORIZACION TAX")
            veh_actions.append("TERMINAR PVH")
            veh_actions.append("ELIMINAR PVH")
            for i, label in enumerate(veh_actions):
                add_row(body1, i, label, lambda l=label: self._acciones_click(l))

        elif is_dep_local and not is_arr_local:
            # Construcción dinámica para SALIDAS
            actions_list = []

            osf_pof = getattr(f, "OSF_pof", None) if f else None
            if f and osf_pof in (Aircraft.STARTING, Aircraft.PUSHREQ):
                try:
                    fir = getattr(self, "fir", None)
                    park = getattr(f, "park", None)
                    pb_rule = self._pushback_rule(f)
                    if pb_rule == 'stand':
                        # 1) P/B encabezando: autorización si estamos en PUSHREQ, si no solicitud
                        if osf_pof == Aircraft.PUSHREQ:
                            actions_list.append("AUTORIZACION P/B")
                        else:
                            actions_list.append("SOLICITUD P/B")
                        # 2) Direcciones disponibles según fir.pushbacks[park]
                        dirs = fir.pushbacks.get(park) or ""
                        # Orden W, E, S, N
                        if "W" in dirs:
                            actions_list.append("AUTORIZACION P/W")
                        if "E" in dirs:
                            actions_list.append("AUTORIZACION P/E")
                        if "S" in dirs:
                            actions_list.append("AUTORIZACION P/S")
                        if "N" in dirs:
                            actions_list.append("AUTORIZACION P/N")
                    elif pb_rule == 'none':
                        # Stand sin retroceso (hoja RetrocesosOSF): sale rodando
                        if osf_pof == Aircraft.STARTING:
                            actions_list.append("SOLICITUD TAX")
                        else:
                            actions_list.append("AUTORIZACION P/B")
                    elif osf_pof == Aircraft.STARTING:
                        # Sin hoja RetrocesosOSF (o vacia): regla general, antes fija para LEBB
                        actions_list.append("SOLICITUD P/B")
                        actions_list.append("AUTORIZACION P/W")
                        actions_list.append("AUTORIZACION P/E")
                    elif osf_pof == Aircraft.PUSHREQ:
                        actions_list.append("AUTORIZACION P/B")
                    actions_list.append("AUTORIZACION TAX")
                except Exception:
                    pass

            # Fallback si no hay nada dinámico
            if not actions_list:
                actions_list = [
                    "SOLICITUD S/U",
                    "SOLICITUD P/B",
                    "SOLICITUD TAX",
                    "AUTORIZACION S/U",
                    "AUTORIZACION P/B",
                    "AUTORIZACION TAX",
                    "AUTORIZACION L/U",
                    "AUTORIZACION DEP"
                ]

            if cru_enabled:
                # CRU para aviones (no VEH) en fase taxi
                if f and getattr(f, 'fr', None) != 'VEH' and osf_pof in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
                    actions_list.append("SOLICITUD CRU")
                # RWY LIBRE para aviones en CROSSING/ENTERING
                if f and osf_pof in (Aircraft.CROSSING, Aircraft.ENTERING):
                    actions_list.append("ANOTACION RWY LIBRE")

            # Siempre añadimos "OTROS" al final (abre subpopup)
            actions_list.append("OTROS")

            # Pintar filas SALIDAS
            for i, label in enumerate(actions_list):
                if label == "OTROS":
                    add_row(body1, i, label, lambda l=label, ax=at_x, ay=at_y: self._acciones_click(l))
                else:
                    add_row(body1, i, label, lambda l=label: self._acciones_click(l))

        else:
            # LLEGADAS (lista base fija)
            arr_rows = [
                ("SOLICITUD LDG", lambda: self._acciones_click("SOLICITUD LDG")),
                ("SOLICITUD TAX", lambda: self._acciones_click("SOLICITUD TAX")),
                ("SOLICITUD TGL", lambda: self._acciones_click("SOLICITUD TGL")),
                ("AUTORIZACION LDG", lambda: self._acciones_click("AUTORIZACION LDG")),
                ("AUTORIZACION TAX", lambda: self._acciones_click("AUTORIZACION TAX")),
                ("AUTORIZACION TGL", lambda: self._acciones_click("AUTORIZACION TGL")),
                ("AUTORIZACION MAP", lambda: self._acciones_click("AUTORIZACION MAP")),
                ("AUTORIZACION GA", lambda: self._acciones_click("AUTORIZACION GA")),
                ("ANOTACION TOMA", lambda: self._acciones_click("ANOTACION TOMA")),
            ]
            if cru_enabled:
                # CRU para aviones (no VEH) en fase taxi
                if f and getattr(f, 'fr', None) != 'VEH' and getattr(f, 'OSF_pof', None) in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
                    arr_rows.append(("SOLICITUD CRU", lambda: self._acciones_click("SOLICITUD CRU")))
                # RWY LIBRE para aviones en CROSSING/ENTERING
                if f and getattr(f, 'OSF_pof', None) in (Aircraft.CROSSING, Aircraft.ENTERING):
                    arr_rows.append(("ANOTACION RWY LIBRE", lambda: self._acciones_click("ANOTACION RWY LIBRE")))
            arr_rows.append(("OTROS", lambda: self._acciones_click("OTROS")))
            for idx, (txt, cb) in enumerate(arr_rows):
                add_row(body1, idx, txt, cb)

        # Separador
        sep = tk.Frame(container, bg="#444444", height=1)
        sep.pack(side="top", fill="x", padx=6, pady=(4, 2))

        # ===== ZONA 2 (fija) =====
        body2 = tk.Frame(container, bg=bg_panel)
        body2.pack(side="top", fill="x", padx=6, pady=(2, 6))

        add_row(body2, 0, "EDITAR OBSERVACIONES", lambda: self._acciones_click("EDITAR_OBSERVACIONES"))
        add_row(body2, 1, "TRANSFERIR", lambda: self._acciones_click("TRANSFERIR"))
        add_row(body2, 2, "REVOCAR", lambda: self._acciones_click("REVOCAR"))
        
        # Marcar que el popup se acaba de abrir para evitar cerrarlo inmediatamente
        self._popup_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_popup_just_opened", False))

        # Cerrar con ESC
        top.bind("<Escape>", lambda e: top.destroy())

    def _show_secondary_popup(self, kind, at_x=None, at_y=None):
        # inicializa lista de subpopups si no existe
        if not hasattr(self, "_sub_popups"):
            self._sub_popups = []

        top = tk.Toplevel(self.root)
        # guardamos referencia por si quisieras cerrarlos en lote después
        self._sub_popups.append(top)
        try:
            top.wm_overrideredirect(1)  # sin marco/cabecera
            top.wm_attributes("-topmost", 1)
        except:
            pass

        # tamaño y posición
        if kind == "OTROS":
            popup_w, popup_h = 200, 350
            if at_x is None or at_y is None:
                at_x = self.root.winfo_rootx() + 60
                at_y = self.root.winfo_rooty() + 60
            top.geometry("%dx%d+%d+%d" % (popup_w, popup_h, int(at_x), int(at_y)))
        else:
            popup_w, popup_h = 150, 150
            if at_x is None or at_y is None:
                at_x = self.root.winfo_rootx() + 60
                at_y = self.root.winfo_rooty() + 60
            top.geometry("%dx%d+%d+%d" % (popup_w, popup_h, int(at_x), int(at_y)))
        bg_panel = self.body_popup
        fg_txt = "white"

        container = tk.Frame(top, bg=bg_panel, bd=1, relief="solid")
        container.pack(fill="both", expand=True)

        def add_row(parent, r, text, on_click):
            btn = tk.Button(
                parent,
                width=1, height=0,
                bg=self.fondo_btn_popup,
                fg="white",
                relief="raised",
                bd=1,
                padx=0, pady=0,
                command=on_click
            )
            btn.grid(row=r, column=0, sticky="w", padx=1, pady=1, ipadx=1, ipady=0)
            btn.configure(font=("Lucida Sans Typewriter", 6))

            lbl = tk.Label(parent, text=text, bg=bg_panel, fg=fg_txt,
                           font=('Lucida Sans Typewriter', 9), anchor="w")
            lbl.grid(row=r, column=1, sticky="w", padx=6, pady=1)

        body = tk.Frame(container, bg=bg_panel)
        body.pack(side="top", fill="x", padx=6, pady=6)

        if kind == "OTROS":
            add_row(body, 0, "SOLICITUD REA", lambda: self._secondary_click(kind, "SOLICITUD_REA"))
            add_row(body, 1, "SOLICITUD TGL", lambda: self._secondary_click(kind, "SOLICITUD_TGL"))
            add_row(body, 2, "AUTORIZACION TGL", lambda: self._secondary_click(kind, "AUTORIZACION_TGL"))
            add_row(body, 0, "SOLICITUD P/B", lambda: self._secondary_click(kind, "SOLICITUD_P/B"))
            add_row(body, 0, "SOLICITUD TAX", lambda: self._secondary_click(kind, "SOLICITUD_TAX"))
            add_row(body, 3, "AUTORIZACION LOW APP", lambda: self._secondary_click(kind, "AUTORIZACION_LOW_APP"))
            add_row(body, 4, "ASIGNAR PTO ESPERA", lambda: self._secondary_click(kind, "ASIGNAR_PTO_ESPERA"))
            add_row(body, 5, "ANOTACION ABO", lambda: self._secondary_click(kind, "ANOTACION_ABO"))
            add_row(body, 6, "VOLVER A PARKING", lambda: self._secondary_click(kind, "VOLVER_A_PARKING"))
            add_row(body, 7, "VOLVER A PTO ESPERA", lambda: self._secondary_click(kind, "VOLVER_A_PTO_ESPERA"))
            add_row(body, 8, "PUSH&HOLD", lambda: self._secondary_click(kind, "PUSH_AND_HOLD"))
            add_row(body, 9, "MODIFICAR STAND", lambda: self._secondary_click(kind, "MODIFICAR_PISTA/SID"))
            add_row(body, 10, "MODIFICAR PISTA/SID", lambda: self._secondary_click(kind, "MODIFICAR_PISTA_SID"))
            add_row(body, 12, "ANOTACION ESTACIONADO", lambda: self._secondary_click(kind, "ANOTACION_ESTACIONADO"))
            add_row(body, 13, "MODIFICAR STAND", lambda: self._secondary_click(kind, "MODIFICAR_STAND"))
        elif kind == "TRANSFERIR":
            sectores_disponibles = [s for s in self.fir.sectors if s != self.sector]
            for idx, sec in enumerate(sectores_disponibles):
                add_row(body, idx, sec, lambda s=sec: self._secondary_click(kind, s))

        else:
            # fallback genérico
            add_row(body, 0, "OPCION 1", lambda: self._secondary_click(kind, "OPT1"))
            add_row(body, 1, "OPCION 2", lambda: self._secondary_click(kind, "OPT2"))

        # Cerrar este subpopup con ESC
        top.bind("<Escape>", lambda e, w=top: w.destroy())

    def _acciones_click(self, key):
        """
        Gestiona una acción del popup 'ACCIONES'.
        - Para entradas que abren submenús (OTROS/TRANSFERIR), delega y no toca el vuelo.
        - Para acciones de estado, resuelve 'f', cambia f.OSF_pof y notifica al GTA.
        """
        # Submenús: abrir y salir sin cerrar el popup principal
        try:
            at_x = self.root.winfo_pointerx() + 10
            at_y = self.root.winfo_pointery() + 10
        except:
            at_x = self.root.winfo_rootx() + 40
            at_y = self.root.winfo_rooty() + 40

        if key in ("OTROS", "TRANSFERIR"):
            try:
                # Abre el subpopup; no cierres el principal
                self._show_secondary_popup(kind=key, at_x=at_x, at_y=at_y)
            except Exception:
                pass
            return

        # Resolver el vuelo en contexto
        f = self._get_ctx_flight()
        if not f:
            # Si no hay vuelo, cerrar popups y salir
            self._close_act_popups()
            return

        # # REVOCAR
        if key == "REVOCAR":
            try:
                self.revocar(getattr(f, "callsign", None))
                self._close_act_popups()
            except Exception:
                pass
            return

        # --- Vehiculos (PVH) y cruce/entrada a pista (CRU/ENT), Fase 4 bloque 2 ---
        is_veh_pvh = getattr(f, 'fr', None) == 'VEH' and getattr(f, 'has_pvh', False)

        # EDITAR OBSERVACIONES de un vehiculo con PVH: edita pvh_notes
        if key == "EDITAR_OBSERVACIONES" and is_veh_pvh:
            self._close_act_popups()
            self._open_edit_pvh_notes(getattr(f, "callsign", ""))
            return

        # ELIMINAR PVH (vehiculos)
        if key == "ELIMINAR PVH":
            try:
                self.radisplay.sendMessage({"message": "delete_pvh", "cs": getattr(f, "callsign", "")})
            except Exception:
                pass
            self._close_act_popups()
            return

        # SOLICITUD ENT (vehiculos) -> dialogo de cabecera, paso intermedio ENR amarillo
        if key == "SOLICITUD ENT":
            self._close_act_popups()
            self._open_pista_solicitud(getattr(f, "callsign", ""), mode='ENT')
            return

        # AUTORIZACION ENT (vehiculos) -> dialogo de pista
        if key == "AUTORIZACION ENT":
            self._close_act_popups()
            self.open_pista_entrada(getattr(f, "callsign", ""))
            return

        # SOLICITUD CRU (aviones y vehiculos) -> dialogo de pista de cruce
        if key == "SOLICITUD CRU":
            self._close_act_popups()
            self._open_pista_cruce(getattr(f, "callsign", ""))
            return

        # ANOTACION RWY LIBRE -> transicion explicita CROSSING/ENTERING -> LIB
        if key == "ANOTACION RWY LIBRE":
            cs = getattr(f, "callsign", "")
            try:
                self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": Aircraft.LIB})
            except Exception:
                pass
            self._close_act_popups()
            return

        # AUTORIZACION TAX de un vehiculo (en LIB) -> TOU
        if key == "AUTORIZACION TAX" and getattr(f, 'fr', None) == 'VEH':
            cs = getattr(f, "callsign", "")
            try:
                self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": Aircraft.TAXIING_OUT})
            except Exception:
                pass
            self._close_act_popups()
            return

        # TERMINAR PVH (vehiculos) -> fase TERMINATED
        if key == "TERMINAR PVH":
            cs = getattr(f, "callsign", "")
            try:
                self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs,
                                            "osf_pof": getattr(Aircraft, "TERMINATED", "###")})
            except Exception:
                pass
            self._close_act_popups()
            return

        # Mapeo de acciones → nuevo estado OSF
        target_by_key = {
            "SOLICITUD S/U": getattr(Aircraft, "STARTREQ", None),
            "SOLICITUD P/B": getattr(Aircraft, "PUSHREQ", None),
            "SOLICITUD TAX": getattr(Aircraft, "TAXIREQ", None),
            "AUTORIZACION S/U": getattr(Aircraft, "STARTING", None),
            "AUTORIZACION P/B": getattr(Aircraft, "PUSH", None),
            "AUTORIZACION P/N": getattr(Aircraft, "PUSH_N", None),
            "AUTORIZACION P/S": getattr(Aircraft, "PUSH_S", None),
            "AUTORIZACION P/E": getattr(Aircraft, "PUSH_E", None),
            "AUTORIZACION P/W": getattr(Aircraft, "PUSH_W", None),
            "AUTORIZACION TAX": getattr(Aircraft, "TAXIING_OUT", None),
            "AUTORIZACION L/U": getattr(Aircraft, "LININGUP", None),
            "AUTORIZACION DEP": getattr(Aircraft, "DEPARTING", None),
            "SOLICITUD LDG": getattr(Aircraft, "LDGREQ", None),
            "AUTORIZACION LDG": getattr(Aircraft, "LANDING", None),
            "AUTORIZACION MAP": getattr(Aircraft, "MAP", None),
            "AUTORIZACION GA": getattr(Aircraft, "GA", None),
        }

        new_state = target_by_key.get(key)
        if new_state is None:
            # Acción no mapeada: cerrar popups y salir
            self._close_act_popups()
            return

        # Aplicar, notificar y refrescar
        try:
            if getattr(f, "OSF_pof", None) != new_state:
                f.OSF_pof = new_state
                try:
                    self.radisplay.sendMessage({
                        "message": "set_osf_pof",
                        "cs": getattr(f, "callsign", ""),
                        "osf_pof": f.OSF_pof,
                        "hacc": self._update_hacc(f)
                    })
                except Exception:
                    pass

                # self._update_hacc_and_send(f)

                # Puede cambiar de zona → reconstruir tira
                # self.update_strip(f, keep_position=True, refresh=True)
            else:
                # Aun así, refrescar por si hay efectos visuales
                self.draw_zonas()
        finally:
            # Cerrar todos los popups de acciones
            self._close_act_popups()

    def _secondary_click(self, kind, code):
        """
        Maneja el click en una opción de sub-popup.
        - Para TRANSFERIR: toma la ficha (desde el contexto del popup o la selección),
          cambia f.next_atc_sector, actualiza la UI y envía el mensaje al GTA.
        - Para el resto: placeholder + cierre de popups.
        """
        # 1) Resolver qué ficha/flight está en contexto
        zi = fi = None
        # Si _show_act_popup guardó el contexto:
        ctx = getattr(self, "_act_popup_ctx", None)
        if ctx and isinstance(ctx, tuple) and len(ctx) == 2:
            zi, fi = ctx
        elif getattr(self, "selected_line", None):
            zi, fi = self.selected_line

        if kind == "TRANSFERIR":
            # Validación de posición
            if zi is None or fi is None:
                # No hay ficha en contexto ni seleccionada
                self._close_act_popups()
                return
            if not (0 <= zi < len(self.zonas)) or not (0 <= fi < len(self.zonas[zi]["fichas"])):
                self._close_act_popups()
                return

            ficha = self.zonas[zi]["fichas"][fi]
            callsign = ficha.get("values", {}).get("callsign", "")
            if not callsign:
                self._close_act_popups()
                return

            f = self._find_flight_by_callsign(callsign)
            if not f:
                self._close_act_popups()
                return

            # 2) Cambiar el parámetro next_atc_sector según la opción elegida
            next_atc_sector = code
            try:
                setattr(f, "next_atc_sector", next_atc_sector)
            except Exception:
                pass

            # # 3) Actualizar la ficha en local (puede mover de zona según choose_zona)
            # try:
            #     self.update_strip(f, keep_position=False, refresh=True)
            # except Exception:
            #     # fallback: al menos redibujar
            #     self.draw_zonas()

            # 4) Mandar mensaje al GTA
            try:
                self.radisplay.sendMessage({
                    "message": "transfer",
                    "sector": next_atc_sector,
                    "cs": callsign
                })
            except Exception:
                pass

            # Cerrar todos los popups después de ejecutar
            self._close_act_popups()
            return

        # Vale. Ahora funciona. Parametrizar para el resto dentro de "OTROS"...
        if kind == "OTROS":
            # Validar contexto de ficha
            if zi is None or fi is None:
                self._close_act_popups()
                return
            if not (0 <= zi < len(self.zonas)) or not (0 <= fi < len(self.zonas[zi]["fichas"])):
                self._close_act_popups()
                return
            ficha = self.zonas[zi]["fichas"][fi]
            local_dep = bool(ficha.get("local_dep", False))

            # Mapeo de código OTROS → nuevo estado OSF
            otros_target = {
                "ANOTACION_ESTACIONADO": getattr(Aircraft, "PARKED", None),
                "SOLICITUD_REA": getattr(Aircraft, "REAREQ", None),
                "SOLICITUD_TGL": getattr(Aircraft, "TGLREQ", None),
                "AUTORIZACION_TGL": getattr(Aircraft, "LANDING", None),
                "SOLICITUD_P/B": getattr(Aircraft, "PUSHREQ", None),
                "SOLICITUD_TAX": getattr(Aircraft, "TAXIREQ", None),
            }

            if code in ("VOLVER_A_PARKING", "ANOTACION_ABO"):
                # Solo salidas: para llegadas no aplica ningun cambio.
                if not local_dep:
                    self._close_act_popups()
                    return
                pof_nuevo = Aircraft.ABORT
            else:
                pof_nuevo = otros_target.get(code)
                if pof_nuevo is None:
                    # Código no mapeado a estado (acciones UI-only)
                    self._close_act_popups()
                    return

            callsign = ficha.get("values", {}).get("callsign", "")
            if not callsign:
                self._close_act_popups()
                return

            f = self._find_flight_by_callsign(callsign)
            if not f:
                self._close_act_popups()
                return

            # Aplicar localmente ANTES de enviar (igual que _acciones_click)
            if getattr(f, "OSF_pof", None) != pof_nuevo:
                f.OSF_pof = pof_nuevo

            if not hasattr(self, "_backpark_callsigns"):
                self._backpark_callsigns = set()

            try:
                if code in ("VOLVER_A_PARKING", "ANOTACION_ABO"):
                    f.OSF_pof = Aircraft.ABORT
                    self._backpark_callsigns.add(callsign)
                    print("[BACKPARK][START] %s: set to %s" % (callsign, Aircraft.ABORT))
                elif callsign in self._backpark_callsigns and pof_nuevo != getattr(Aircraft, "ABORT", None):
                    self._backpark_callsigns.discard(callsign)
                self.radisplay.sendMessage({
                    "message": "set_osf_pof",
                    "cs": callsign,
                    "osf_pof": pof_nuevo,
                    "hacc": self._update_hacc(f)
                })
            except Exception:
                pass

            self._close_act_popups()
            return

        self._close_act_popups()

    def _close_act_popups(self):
        """Cierra el popup principal de ACCIONES y todos los sub-popups si existen.
        Tb cuando haces click fuera de los popups.
        """
        # principal
        if hasattr(self, "_act_popup") and self._act_popup and self._act_popup.winfo_exists():
            try:
                self._act_popup.destroy()
            except:
                pass
        self._act_popup = None

        # secundarios
        if hasattr(self, "_sub_popups") and self._sub_popups:
            for w in list(self._sub_popups):
                try:
                    if w and w.winfo_exists():
                        w.destroy()
                except:
                    pass
            self._sub_popups = []

    def change_action_from_label(self, callsign):
        """
        Cambia el estado (campo ACT) de la ficha cuyo 'callsign' coincide,
        se llama desde RaElemnts.py
        """
        if not callsign:
            return

        # Buscar la ficha por callsign
        found = self._find_ficha_by_callsign(callsign)
        if not found:
            print("change_action_from_label: no se ha encontrado la ficha con callsign", callsign)
            return

        zona_idx, ficha_idx, _ = found

        # Reutilizar la lógica ya implementada
        try:
            self._on_act_click(zona_idx, ficha_idx)
        except Exception as e:
            print("Error en change_action_from_label:", e)

    def _update_hacc(self, f):
        """
        Calcula hacc a partir de radisplay.t, lo guarda en f.hacc
        y envía un mensaje 'set_hacc' al GTA.

        Formato de hacc: 'HH:MM:SS'
        """
        t_sim = getattr(self.radisplay, "t", None)
        if t_sim is None:
            return  # no hay tiempo de simulación, no hacemos nada

        # Formatear hacc
        try:
            hacc = t_sim.strftime("%H:%M:%S")
        except Exception:
            hacc = str(t_sim)

        # Guardar en el vuelo
        try:
            f.hacc = hacc
        except Exception:
            pass

        return hacc

    def _on_callsign_click(self, zona_idx, ficha_idx):
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        # Cerrar extendida (si la hay) ANTES de cambiar estado/zona
        self._close_extended_by_callsign(callsign)

        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        try:
            sector = self.sector
            self.radisplay.sendMessage({
                "message": "assume",
                "sector": sector,
                "cs": f.callsign,
                "assumed": True
            })
        except Exception:
            pass

    def _on_holdp_click(self, zona_idx, ficha_idx, field_idx):
        """
        Selector de HOLDP (similar a _on_gate_click pero para 'holdp').

        - Usa la pista del vuelo (deprwy / desrwy) para filtrar la lista de HP.
        - Estilo visual coherente con el resto de popups (gate, acciones, etc.).
        """
        # 1) ficha y vuelo
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]

        # callsign normal
        callsign = ficha.get("values", {}).get("callsign", "")

        # si es ficha extendida, puede venir solo en parent_callsign
        if (not callsign) and ficha.get("is_extended"):
            callsign = ficha.get("parent_callsign", "")

        if not callsign:
            return

        # Buscar el vuelo real
        f = None
        for vf in getattr(self.radisplay, "flights", []):
            if getattr(vf, "callsign", None) == callsign:
                f = vf
                break
        if not f:
            return

        # 2) Determinar pista del vuelo usando lógica local_dep / local_des
        rwy = ""
        try:
            sector_list = (self.sector or "").split(",")
            fir = getattr(self, "fir", None)
            local_ads = getattr(fir, "local_ads", {}) or {}
        except Exception:
            sector_list = []
            local_ads = {}

        is_dep_local = False
        is_arr_local = False

        # ¿Es salida local o llegada local?
        for sec in sector_list:
            ads = local_ads.get(sec, set())
            if getattr(f, "adep", None) in ads:
                is_dep_local = True
                break
            if getattr(f, "ades", None) in ads:
                is_arr_local = True
                break

        if is_dep_local:
            # Salida local → usamos deprwy preferente
            rwy = getattr(f, "deprwy", None) or getattr(f, "rwy", None)
        elif is_arr_local:
            # Llegada local → usamos desrwy preferente
            rwy = getattr(f, "desrwy", None) or getattr(f, "rwy", None)
        else:
            # Fallback genérico si no se considera local
            rwy = (getattr(f, "deprwy", None)
                   or getattr(f, "desrwy", None)
                   or ficha.get("values", {}).get("rwy", ""))

        if rwy is None:
            rwy = ""
        else:
            rwy = str(rwy)

        # 3) Obtener lista de HPs desde fir.login filtrada por pista
        hp_by_rwy = getattr(self, "hp_by_rwy", {}) or {}
        items = list(hp_by_rwy.get(rwy, []))

        if not items:
            # si quieres, aquí podrías hacer un fallback a todos los HPs
            return

        # 4) Crear popup con estilo coherente y topmost
        # Cerrar uno anterior si existe
        if hasattr(self, "_holdp_popup") and self._holdp_popup and self._holdp_popup.winfo_exists():
            try:
                self._holdp_popup.destroy()
            except:
                pass

        popup = tk.Toplevel(self.root)
        self._holdp_popup = popup

        try:
            popup.wm_overrideredirect(1)   # sin marco, como otros popups
        except:
            pass
        try:
            popup.wm_attributes("-topmost", 1)
        except:
            pass

        # Posición: cerca del ratón
        try:
            mx = self.root.winfo_pointerx()
            my = self.root.winfo_pointery()
            popup.geometry("+%d+%d" % (mx + 8, my + 8))
        except Exception:
            pass

        # Frame contenedor con estilo oscuro (similar a _on_gate_click)
        frame = tk.Frame(popup, bd=1, relief="solid", bg="#222222")
        frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(frame, orient="vertical")
        lb = tk.Listbox(frame,
                        height=min(10, max(4, len(items))),
                        width=8,
                        exportselection=False,
                        activestyle="dotbox")

        # Estilos del listbox
        try:
            lb.configure(background="#333333", foreground="#ffffff",
                         selectbackground="#555555", selectforeground="#ffffff",
                         relief="flat", borderwidth=0)
        except:
            pass

        sb.config(command=lb.yview)
        lb.config(yscrollcommand=sb.set)

        for s in items:
            lb.insert(tk.END, s)

        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        # Preseleccionar si ya hay un holdp asignado en la ficha
        current_val = ficha.get("values", {}).get("holdp", "")
        if current_val:
            try:
                idx = items.index(current_val)
                lb.selection_set(idx)
                lb.see(idx)
            except ValueError:
                pass

        def _close(event=None):
            try:
                popup.destroy()
            except:
                pass

        def _commit(event=None):
            sel = lb.curselection()
            if not sel:
                _close()
                return
            value = lb.get(int(sel[0]))

            # 5) Actualizar el objeto Flight
            if f:
                setattr(f, "holdp", value)
                
                # 6) Actualizar TODAS las fichas con este callsign (principal y extendida)
                for zi, zona in enumerate(self.zonas):
                    for fi, ficha in enumerate(zona.get("fichas", [])):
                        # Actualizar ficha principal (tiene callsign en values)
                        if ficha.get("values", {}).get("callsign") == f.callsign:
                            if "holdp" in ficha.get("fields", []):
                                ficha.setdefault("values", {})["holdp"] = value
                        # Actualizar ficha extendida (tiene parent_callsign)
                        elif ficha.get("is_extended") and ficha.get("parent_callsign") == f.callsign:
                            if "holdp" in ficha.get("fields", []):
                                ficha.setdefault("values", {})["holdp"] = value
                
                # 7) mandar al GTA
                try:
                    self.radisplay.sendMessage({
                        "message": "set_holdp",
                        "cs": f.callsign,
                        "holdp": value
                    })
                except Exception:
                    pass

            # 8) Cerrar popup y redibujar
            _close()
            self.draw_zonas()
            
            # Asegurar que el canvas tiene el foco para permitir nuevos clicks
            try:
                self.canvas.focus_set()
            except:
                pass

        # Clic izquierdo confirma
        lb.bind("<ButtonRelease-1>", _commit)
        # ESC cancela
        popup.bind("<Escape>", _close)
        
        # Marcar que el popup se acaba de abrir para evitar cerrarlo inmediatamente
        self._popup_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_popup_just_opened", False))

    def _on_gate_click(self, zona_idx, ficha_idx, field_idx):
        """
        Popup de lista de gates junto al campo 'gate'.
        BI -> aplica y cierra.
        ESC -> cierra sin cambios.
        """
        # --- 0) Validaciones / datos base ---
        zona = self.zonas[zona_idx]
        ficha = zona["fichas"][ficha_idx]
        nombres_campos = ficha.get("fields", [])
        if field_idx >= len(nombres_campos) or nombres_campos[field_idx] != "gate":
            return

        # --- 1) Calcular rect del campo 'gate' (igual que en draw_zonas) ---
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        margin = 50
        usable_width = canvas_width - 2 * margin

        ficha_h = 25
        sep_h = 2
        line_h = ficha_h + sep_h

        y_start = sum(self.zona_heights[:zona_idx]) * canvas_height
        y_end = y_start + self.zona_heights[zona_idx] * canvas_height

        offset = zona.get("scroll_offset", 0)
        visible_idx = ficha_idx - offset
        if visible_idx < 0:
            visible_idx = 0

        line_bottom = y_end - visible_idx * line_h - sep_h
        line_top = line_bottom - ficha_h

        # anchos por campo
        fixed_total = 0.0
        flex_count = 0
        for nm in nombres_campos:
            if self._is_flex(nm):
                flex_count += 1
            else:
                fixed_total += self._field_width(nm)
        remaining = max(0.0, usable_width - fixed_total)
        flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

        x_cursor = margin
        x_max = margin + usable_width
        x_start = x_end = None

        for idx, name in enumerate(nombres_campos):
            w = (flex_each if self._is_flex(name) else self._field_width(name))
            xs = x_cursor
            xe = x_cursor + w
            if idx == field_idx:
                x_start = xs
                x_end = xe if xe <= x_max else x_max
                break
            x_cursor = xe

        if x_start is None:
            return

        # --- 2) Crear popup (2.7-safe) ---
        # Cerrar el anterior si existe
        if hasattr(self, "_gate_popup") and self._gate_popup and self._gate_popup.winfo_exists():
            try:
                self._gate_popup.destroy()
            except:
                pass

        popup = tk.Toplevel(self.root)
        self._gate_popup = popup  # mantener referencia viva

        try:
            popup.wm_overrideredirect(1)  # sin marco (2.7)
        except:
            pass
        try:
            popup.wm_attributes("-topmost", 1)
        except:
            pass

        # Posición absoluta, justo debajo del campo
        abs_x = int(self.canvas.winfo_rootx() + x_start)
        abs_y = int(self.canvas.winfo_rooty() + line_bottom)
        popup.geometry("+%d+%d" % (abs_x, abs_y))

        frame = tk.Frame(popup, bd=1, relief="solid", bg="#222222")
        frame.pack(fill="both", expand=True)

        sb = tk.Scrollbar(frame, orient="vertical")
        lb = tk.Listbox(frame,
                        height=min(10, max(4, len(getattr(self, "gates", [])))),
                        width=6,  # <<< ajusta el ancho en caracteres
                        exportselection=False,
                        activestyle="dotbox")

        # Estilos sencillos
        try:
            lb.configure(background="#333333", foreground="#ffffff",
                         selectbackground="#555555", selectforeground="#ffffff")
        except:
            pass

        sb.config(command=lb.yview)
        lb.config(yscrollcommand=sb.set)

        # 2.7: asegúrate de tener la lista de gates
        gates = list(getattr(self, "gates", []))
        for g in gates:
            lb.insert(tk.END, str(g))

        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)

        # Preselección si la ficha ya tenía gate
        current_val = ficha.get("values", {}).get("gate", "")
        if current_val:
            try:
                idx = gates.index(current_val)
                lb.selection_set(idx)
                lb.see(idx)
            except ValueError:
                pass

        # --- 3) Callbacks commit/cerrar ---
        def _close(event=None):
            try:
                popup.destroy()
            except:
                pass

        def _commit(event=None):
            sel = lb.curselection()
            if not sel:
                _close()
                return
            new_gate = lb.get(int(sel[0]))
            
            # Actualiza ficha - ANTES de redibujar
            # Validar índices antes de acceder
            if 0 <= zona_idx < len(self.zonas) and 0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"]):
                ficha_actual = self.zonas[zona_idx]["fichas"][ficha_idx]
                ficha_actual.setdefault("values", {})["gate"] = new_gate
            
            # Reflejo en el vuelo (opcional)
            f = self._find_flight_by_callsign(ficha.get("values", {}).get("callsign", ""))
            if f:
                try:
                    setattr(f, "gate", new_gate)
                    self.radisplay.sendMessage({"message": "set_gate", "cs": f.callsign, "gate": new_gate})
                except:
                    pass
            
            # Cerrar PRIMERO, luego redibujar
            _close()
            self.draw_zonas()
            
            # Asegurar que el canvas tiene el foco para permitir nuevos clicks
            try:
                self.canvas.focus_set()
            except:
                pass

        # Binds (2.7-safe)
        lb.bind("<ButtonRelease-1>", _commit)
        # lb.bind("<Return>", _commit)
        popup.bind("<Escape>", _close)

        # Dar foco para que el teclado funcione
        #try:
        #    popup.focus_set()
        #    lb.focus_set()
        #except:
        #    pass
        
        # Marcar que el popup se acaba de abrir para evitar cerrarlo inmediatamente
        self._popup_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_popup_just_opened", False))

    def _on_campolibre_click(self, zona_idx, ficha_idx):
        """
        Click en el campo 'campolibre': abre un Entry para introducir texto libre (máx 10 caracteres).
        Todo en mayúsculas mientras se escribe.
        """
        # IMPORTANTE: Cerrar cualquier edición activa ANTES de abrir una nueva
        self._close_any_active_edit()
        
        # Validar que los índices sean válidos antes de acceder
        if zona_idx < 0 or zona_idx >= len(self.zonas):
            return
        if ficha_idx < 0 or ficha_idx >= len(self.zonas[zona_idx]["fichas"]):
            return
        
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        # En la ficha extendida no hay clave "callsign" en values (no forma parte
        # de su layout); el vuelo se identifica por "parent_callsign".
        callsign = ficha.get("values", {}).get("callsign", "") or ficha.get("parent_callsign", "")
        if not callsign:
            return

        # Coordenadas del campo en pantalla
        nombres_campos = ficha.get("fields", [])
        if "campolibre" not in nombres_campos:
            return
        field_idx = nombres_campos.index("campolibre")

        margin = 50
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        usable_width = canvas_width - 2 * margin
        offset = self.zonas[zona_idx]["scroll_offset"]

        ficha_h = 25
        sep_h = 2
        line_height = ficha_h + sep_h

        # Posición vertical
        line_idx = ficha_idx - offset
        y_end = (sum(self.zona_heights[:zona_idx + 1]) * canvas_height)
        line_bottom = y_end - line_idx * line_height - sep_h
        line_top = line_bottom - ficha_h

        # Cálculo horizontal hasta llegar al campo
        fixed_total, flex_count = 0.0, 0
        for nm in nombres_campos:
            if self._is_flex(nm):
                flex_count += 1
            else:
                fixed_total += self._field_width(nm)
        remaining = max(0.0, usable_width - fixed_total)
        flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

        x_cursor = margin
        for idx, nm in enumerate(nombres_campos):
            w = flex_each if self._is_flex(nm) else self._field_width(nm)
            if idx == field_idx:
                x_start, x_end = x_cursor, x_cursor + w
                break
            x_cursor += w
        else:
            return  # no encontrado

        # Entry temporal
        valor_actual = ficha.get("values", {}).get("campolibre", "")
        #self._edit_entry_var = tk.StringVar(value=valor_actual) Cuando se da foco se elimina -- si habia antes y si no se termina escribiendo nada vuelve a --
        if valor_actual == "--":
            valor_actual = ""
        self._edit_entry_var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(self.canvas, textvariable=self._edit_entry_var,
                         font=self.font_style, justify="center")
        entry.place(x=x_start, y=line_top, width=(x_end - x_start), height=(line_bottom - line_top))

        # Forzar mayúsculas mientras escribe
        def _norm_var(*args):
            v = self._edit_entry_var.get()
            if len(v) > 10:
                v = v[:10]
            if v != v.upper():
                v = v.upper()
            if v != self._edit_entry_var.get():
                self._edit_entry_var.set(v)

        self._edit_entry_var.trace("w", _norm_var)

        def _commit_campolibre_changes(event=None):
            # Evitar doble ejecución: verificar si ya fue limpiado
            if self._edit_entry_var is None or self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            
            # Capturar valor ANTES de limpiar
            nuevo_valor = self._edit_entry_var.get().upper()[:10]
            if nuevo_valor == "":
                nuevo_valor = "--"
            ficha.setdefault("values", {})["campolibre"] = nuevo_valor
            
            # Limpiar PRIMERO las variables de control
            self._edit_entry = None
            self._edit_entry_var = None
            self._campolibre_edit_active = False
            
            # Destruir entry
            try:
                entry.destroy()
            except Exception:
                pass

            # Redibujar
            self.draw_zonas()

            # Enviar mensaje al GTA
            cs_flight = ficha.get("values", {}).get("callsign", "") or ficha.get("parent_callsign", "")
            f = self._find_flight_by_callsign(cs_flight)
            if f:
                try:
                    self.radisplay.sendMessage({
                        "message": "set_rutrod",
                        "cs": f.callsign,
                        "rutrod": nuevo_valor
                    })
                except:
                    pass

        def _cancel_and_close(event=None):
            # Evitar doble ejecución: verificar si ya fue limpiado
            if self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            
            # Limpiar variables PRIMERO
            self._edit_entry = None
            self._edit_entry_var = None
            self._campolibre_edit_active = False
            
            # Destruir entry
            try:
                entry.destroy()
            except Exception:
                pass
            
            # Redibujar
            self.draw_zonas()

        entry.bind("<Return>", _commit_campolibre_changes)
        entry.bind("<Escape>", _cancel_and_close)
        # BUGFIX: Confirmar automáticamente al perder el foco
        entry.bind("<FocusOut>", _commit_campolibre_changes)
        entry.focus_set()

        # --- NUEVO: datos para el click global ---
        self._edit_entry = entry
        self._campolibre_edit_active = True
        self._campolibre_rect = (x_start, x_end, y_top, y_bottom) = (x_start, x_end, line_top, line_bottom)
        self._campolibre_original = valor_actual
        self._campolibre_cancel_cb = _cancel_and_close
        self._campolibre_ficha = ficha  # Almacenar referencia a la ficha para guardar desde global click
        self._campolibre_callsign = callsign
        
        # Marcar que el campo se acaba de abrir para evitar cerrarlo inmediatamente
        self._edit_just_opened = True
        # Limpiar el flag después de un momento para permitir clicks fuera
        self.canvas.after(100, lambda: setattr(self, "_edit_just_opened", False))


    def _on_park_click(self, zona_idx, ficha_idx):
        """
        Click en el campo 'park': abre un Entry inline.
        Todo en mayusculas mientras se escribe y commit con ENTER o FocusOut.
        """
        self._close_any_active_edit()

        if zona_idx < 0 or zona_idx >= len(self.zonas):
            return
        if ficha_idx < 0 or ficha_idx >= len(self.zonas[zona_idx]["fichas"]):
            return

        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        nombres_campos = ficha.get("fields", [])
        if "park" not in nombres_campos:
            return
        field_idx = nombres_campos.index("park")

        margin = 50
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        usable_width = canvas_width - 2 * margin
        offset = self.zonas[zona_idx]["scroll_offset"]

        ficha_h = 25
        sep_h = 2
        line_height = ficha_h + sep_h

        line_idx = ficha_idx - offset
        y_end = (sum(self.zona_heights[:zona_idx + 1]) * canvas_height)
        line_bottom = y_end - line_idx * line_height - sep_h
        line_top = line_bottom - ficha_h

        fixed_total, flex_count = 0.0, 0
        for nm in nombres_campos:
            if self._is_flex(nm):
                flex_count += 1
            else:
                fixed_total += self._field_width(nm)
        remaining = max(0.0, usable_width - fixed_total)
        flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

        x_cursor = margin
        for idx, nm in enumerate(nombres_campos):
            w = flex_each if self._is_flex(nm) else self._field_width(nm)
            if idx == field_idx:
                x_start, x_end = x_cursor, x_cursor + w
                break
            x_cursor += w
        else:
            return

        valor_actual = ficha.get("values", {}).get("park", "")
        self._edit_entry_var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(self.canvas, textvariable=self._edit_entry_var,
                         font=self.font_style, justify="center")
        entry.place(x=x_start, y=line_top, width=(x_end - x_start), height=(line_bottom - line_top))

        def _norm_var(*args):
            v = self._edit_entry_var.get()
            if len(v) > 10:
                v = v[:10]
            v = v.upper()
            if v != self._edit_entry_var.get():
                self._edit_entry_var.set(v)

        self._edit_entry_var.trace("w", _norm_var)

        def _commit_park_changes(event=None):
            if self._edit_entry_var is None or self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return

            nuevo_valor = self._edit_entry_var.get().upper()[:10]
            ficha.setdefault("values", {})["park"] = nuevo_valor

            self._edit_entry = None
            self._edit_entry_var = None
            self._park_edit_active = False
            self._park_ficha = None
            self._park_callsign = None

            try:
                entry.destroy()
            except Exception:
                pass

            self.draw_zonas()

            f = self._find_flight_by_callsign(callsign)
            if f:
                try:
                    f.park = nuevo_valor
                except Exception:
                    pass
                try:
                    self.radisplay.sendMessage({
                        "message": "set_park",
                        "cs": f.callsign,
                        "park": nuevo_valor
                    })
                except Exception:
                    pass

        def _cancel_and_close(event=None):
            if self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return

            self._edit_entry = None
            self._edit_entry_var = None
            self._park_edit_active = False
            self._park_ficha = None
            self._park_callsign = None

            try:
                entry.destroy()
            except Exception:
                pass

            self.draw_zonas()

        entry.bind("<Return>", _commit_park_changes)
        entry.bind("<Escape>", _cancel_and_close)
        entry.bind("<FocusOut>", _commit_park_changes)
        entry.focus_set()

        self._edit_entry = entry
        self._park_edit_active = True
        self._park_ficha = ficha
        self._park_callsign = callsign

        self._edit_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_edit_just_opened", False))


    def _close_any_active_edit(self):
        """
        Cierra y guarda cualquier campo de edición activo (campolibre u obstáculo).
        Esto previene que se pierda el contenido cuando se hace click en otro campo.
        """
        if not self._edit_entry or not self._edit_entry_var:
            return
        
        try:
            if not hasattr(self._edit_entry, 'winfo_exists') or not self._edit_entry.winfo_exists():
                # El entry ya no existe, limpiar referencias
                self._edit_entry = None
                self._edit_entry_var = None
                self._edit_ctx = None
                self._campolibre_edit_active = False
                self._park_edit_active = False
                return
            
            # Determinar qué tipo de campo es
            ctx = getattr(self, "_edit_ctx", None)
            
            if ctx and ctx.get("field") == "obstaculo":
                # Es un obstáculo: guardar
                zona_idx = ctx.get("zona_idx")
                ficha_idx = ctx.get("ficha_idx")
                if zona_idx is not None and ficha_idx is not None:
                    # Validar índices antes de acceder
                    if 0 <= zona_idx < len(self.zonas) and 0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"]):
                        nuevo_valor = self._edit_entry_var.get().upper()[:20]
                        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
                        ficha.setdefault("values", {})["obstaculo"] = nuevo_valor
            
            elif self._campolibre_edit_active:
                # Es un campolibre: guardar
                nuevo_valor = self._edit_entry_var.get().upper()[:10]
                ficha = getattr(self, "_campolibre_ficha", None)
                callsign = getattr(self, "_campolibre_callsign", "")
                
                if ficha:
                    ficha.setdefault("values", {})["campolibre"] = nuevo_valor
                
                # Enviar mensaje al GTA
                if callsign:
                    f = self._find_flight_by_callsign(callsign)
                    if f:
                        try:
                            self.radisplay.sendMessage({
                                "message": "set_rutrod",
                                "cs": f.callsign,
                                "rutrod": nuevo_valor
                            })
                        except:
                            pass

            elif self._park_edit_active:
                nuevo_valor = self._edit_entry_var.get().upper()[:10]
                ficha = getattr(self, "_park_ficha", None)
                callsign = getattr(self, "_park_callsign", "")

                if ficha:
                    ficha.setdefault("values", {})["park"] = nuevo_valor

                if callsign:
                    f = self._find_flight_by_callsign(callsign)
                    if f:
                        try:
                            f.park = nuevo_valor
                        except Exception:
                            pass
                        try:
                            self.radisplay.sendMessage({
                                "message": "set_park",
                                "cs": f.callsign,
                                "park": nuevo_valor
                            })
                        except Exception:
                            pass
            
            # Destruir el entry
            entry_to_destroy = self._edit_entry
            self._edit_entry = None
            self._edit_entry_var = None
            self._edit_ctx = None
            self._campolibre_edit_active = False
            self._park_edit_active = False
            self._campolibre_ficha = None
            self._campolibre_callsign = None
            self._park_ficha = None
            self._park_callsign = None
            
            try:
                entry_to_destroy.destroy()
            except:
                pass
            
            # NO redibujar aquí - dejar que el nuevo campo se abra inmediatamente
            # self.draw_zonas() se llamará desde el nuevo campo
            
        except Exception as e:
            logging.debug("Error cerrando campo activo: %s" % str(e))
            # Limpiar referencias en caso de error
            self._edit_entry = None
            self._edit_entry_var = None
            self._edit_ctx = None
            self._campolibre_edit_active = False
            self._park_edit_active = False

    def _close_all_popups(self):
        """
        Cierra todos los popups abiertos (ACCIONES, TRANSFERIR, gates, holdp, obstaculo).
        """
        # Cerrar popups de acciones
        self._close_act_popups()
        
        # Cerrar popup de holdp si existe
        if hasattr(self, "_holdp_popup") and self._holdp_popup:
            try:
                if self._holdp_popup.winfo_exists():
                    self._holdp_popup.destroy()
            except:
                pass
            self._holdp_popup = None
        
        # Cerrar popup de gate si existe
        if hasattr(self, "_gate_popup") and self._gate_popup:
            try:
                if self._gate_popup.winfo_exists():
                    self._gate_popup.destroy()
            except:
                pass
            self._gate_popup = None

    def _campolibre_global_click(self, event):
        """
        Maneja clicks en el canvas:
        1. Si hay campo activo (campolibre u obstáculo) y click fuera -> guarda y cierra
        2. Si no hay campo activo -> cierra popups
        """
        # IMPORTANTE: No procesar si el campo se acaba de abrir (evitar cerrar inmediatamente)
        if getattr(self, "_edit_just_opened", False):
            return
        
        # IMPORTANTE: No cerrar popups si se acaban de abrir (para GATE, HOLDP, etc.)
        if getattr(self, "_popup_just_opened", False):
            return
        
        # Verificar si hay CUALQUIER campo activo (campolibre o obstáculo)
        has_active_field = (self._edit_entry is not None and self._edit_entry_var is not None)
        
        if not has_active_field:
            # No hay campo activo, solo cerrar popups
            self._close_all_popups()
            return

        # HAY un campo activo - verificar si el click está fuera
        try:
            if not hasattr(self._edit_entry, 'winfo_exists') or not self._edit_entry.winfo_exists():
                # El entry ya no existe, limpiar
                self._edit_entry = None
                self._edit_entry_var = None
                self._edit_ctx = None
                self._campolibre_edit_active = False
                self._park_edit_active = False
                self._close_all_popups()
                return
            
            # Obtener posición del Entry
            entry_x = self._edit_entry.winfo_x()
            entry_y = self._edit_entry.winfo_y()
            entry_width = self._edit_entry.winfo_width()
            entry_height = self._edit_entry.winfo_height()
            
            # Si el click está DENTRO del Entry, no hacer nada
            if (entry_x <= event.x <= entry_x + entry_width and 
                entry_y <= event.y <= entry_y + entry_height):
                return
            
            # Click está FUERA del Entry -> GUARDAR y cerrar
            # Usar _close_any_active_edit que ya guarda correctamente
            self._close_any_active_edit()
            # Redibujar para mostrar el cambio guardado
            self.draw_zonas()
            
        except Exception as e:
            logging.debug("Error en _campolibre_global_click: %s" % str(e))
        
        # Cerrar popups al hacer click fuera
        self._close_all_popups()

    def _on_autorizacion_click(self, zona_idx, ficha_idx):
        """
        Click izq. sobre el campo 'autorizacion':
          - Detecta si el vuelo es salida local (adep ∈ local_ads[sector]).
          - Si es local_dep: alterna ATC_status entre ATC_OK y ATC_PENDING.
          - Envía mensaje 'set_atc_status'.
          - Refresca la imagen del campo y redibuja.
        """
        # --- 0) Ficha y vuelo ---
        zona = self.zonas[zona_idx]
        ficha = zona["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        # Buscar el vuelo real
        f = None
        for vf in getattr(self.radisplay, "flights", []):
            if getattr(vf, "callsign", None) == callsign:
                f = vf
                break
        if not f:
            return

        # --- 1) ¿Salida local? ---
        fir = self.fir
        sector_list = (self.sector or "").split(",")
        local_dep = False
        local_ads = getattr(fir, "local_ads", {}) or {}
        for sector_aux in sector_list:
            ads = local_ads.get(sector_aux, set())
            if getattr(f, "adep", None) in ads:
                local_dep = True
                break

        # --- 2) Alternar estado si es salida local ---
        if local_dep:
            if f.ATC_status == Aircraft.ATC_OK:
                f.ATC_status = Aircraft.ATC_PENDING
            else:
                f.ATC_status = Aircraft.ATC_OK

            # Notificar al GTA
            try:
                self.radisplay.sendMessage({
                    "message": "set_atc_status",
                    "cs": callsign,
                    "atc_status": f.ATC_status
                })
            except Exception:
                pass

        # --- 3) Refrescar imagen del campo 'autorizacion' según f.ATC_status ---
        atc_status = getattr(f, "ATC_status", None) or "ATC_MISSING"
        img_file_str = "img/" + atc_status
        img_abs_path = os.path.join(conf.common_dir, img_file_str)

        ficha.setdefault("images", {})["autorizacion"] = img_abs_path

        # Limpiar caché de esa imagen si ha cambiado (opcional)
        if hasattr(self, "_img_cache"):
            old = self._img_cache.get(img_abs_path)
            if old is None:
                try:
                    self._img_cache[img_abs_path] = tk.PhotoImage(file=img_abs_path)
                except Exception:
                    self._img_cache[img_abs_path] = None

        # --- 4) Redibujar ---
        self.draw_zonas()

    # ============================
    # Ficha OBSTACULO
    # ============================
    def _on_obstaculo_click(self, zona_idx, ficha_idx):
        """
        Click en el campo 'obstaculo': Entry inline (máx 20 chars, MAYÚSCULAS, texto preseleccionado).
        ENTER confirma, ESC cancela.
        """
        # IMPORTANTE: Cerrar cualquier edición activa ANTES de abrir una nueva
        self._close_any_active_edit()
        
        # Validar que los índices sean válidos antes de acceder
        if zona_idx < 0 or zona_idx >= len(self.zonas):
            return
        if ficha_idx < 0 or ficha_idx >= len(self.zonas[zona_idx]["fichas"]):
            return
        
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]

        # Asegura que este strip tiene el campo obstaculo
        nombres_campos = ficha.get("fields", [])
        if "obstaculo" not in nombres_campos:
            return
        field_idx = nombres_campos.index("obstaculo")

        # Geometría de la celda (igual que en campolibre)
        margin = 50
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        usable_width = canvas_width - 2 * margin

        ficha_h = 25
        sep_h = 2
        line_height = ficha_h + sep_h

        # Vertical
        offset = self.zonas[zona_idx].get("scroll_offset", 0)
        visible_idx = ficha_idx - offset
        if visible_idx < 0:
            return
        y_end = sum(self.zona_heights[:zona_idx + 1]) * canvas_height
        line_bottom = y_end - visible_idx * line_height - sep_h
        line_top = line_bottom - ficha_h

        # Horizontal
        fixed_total, flex_count = 0.0, 0
        for nm in nombres_campos:
            if self._is_flex(nm):
                flex_count += 1
            else:
                fixed_total += self._field_width(nm)
        remaining = max(0.0, usable_width - fixed_total)
        flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

        x_cursor = margin
        x_start = x_end = None
        for idx, nm in enumerate(nombres_campos):
            w = flex_each if self._is_flex(nm) else self._field_width(nm)
            xs, xe = x_cursor, x_cursor + w
            if idx == field_idx:
                x_start, x_end = xs, min(xe, margin + usable_width)
                break
            x_cursor = xe
        if x_start is None:
            return

        # Entry inline
        valor_actual = ficha.get("values", {}).get("obstaculo", "")
        self._edit_entry_var = tk.StringVar()
        self._edit_entry_var.set(valor_actual)

        entry = tk.Entry(self.canvas, textvariable=self._edit_entry_var,
                         font=self.font_style, justify="center",
                         bg=self.ficha_bg, fg="white", insertbackground="white",
                         highlightthickness=0, relief="flat")
        entry.place(x=int(x_start), y=int(line_top), width=int(x_end - x_start), height=int(line_bottom - line_top))

        # Guardar referencias para cerrar luego
        self._edit_entry = entry
        self._edit_ctx = {"zona_idx": zona_idx, "ficha_idx": ficha_idx, "field": "obstaculo"}

        # MAYÚSCULAS + límite 10
        def _norm_var(*_):
            v = self._edit_entry_var.get()
            v2 = (v[:20]).upper()
            if v != v2:
                try:
                    self._edit_entry_var.trace_vdelete("w", norm_trid[0])
                except Exception:
                    pass
                self._edit_entry_var.set(v2)
                norm_trid[0] = self._edit_entry_var.trace("w", _norm_var)

        norm_trid = [self._edit_entry_var.trace("w", _norm_var)]

        # Seleccionar todo y enfocar
        try:
            entry.focus_set()
            entry.selection_range(0, tk.END)
            entry.icursor(tk.END)
        except:
            pass

        # Confirmar / cancelar
        def _confirm(event=None):
            # Evitar doble ejecución: verificar si ya fue limpiado
            if self._edit_entry_var is None or self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            
            # Capturar valor ANTES de limpiar
            nuevo_valor = self._edit_entry_var.get().upper()[:20]
            ficha.setdefault("values", {})["obstaculo"] = nuevo_valor
            
            # Limpiar PRIMERO las variables de control
            self._edit_entry = None
            self._edit_entry_var = None
            self._edit_ctx = None
            
            # Destruir entry
            try:
                entry.destroy()
            except:
                pass
            
            # Redibujar
            self.draw_zonas()

        def _cancel(event=None):
            # Evitar doble ejecución: verificar si ya fue limpiado
            if self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            
            # Limpiar variables PRIMERO
            self._edit_entry = None
            self._edit_entry_var = None
            self._edit_ctx = None
            
            # Destruir entry
            try:
                entry.destroy()
            except:
                pass
            
            # Redibujar
            self.draw_zonas()

        entry.bind("<Return>", _confirm)
        entry.bind("<Escape>", _cancel)
        # BUGFIX: Confirmar automáticamente al perder el foco
        entry.bind("<FocusOut>", _confirm)
        
        # Marcar que el campo se acaba de abrir para evitar cerrarlo inmediatamente
        self._edit_just_opened = True
        # Limpiar el flag después de un momento para permitir clicks fuera
        self.canvas.after(100, lambda: setattr(self, "_edit_just_opened", False))

    def _on_obstaculo_right_click(self, zona_idx, ficha_idx, event=None):
        """
        Menú contextual en el campo 'obstaculo' para cambiar color de fondo
        y transferir a otros sectores.
        """
        try:
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        except Exception:
            return

        # Asegura el dict de fondos por campo
        field_bg = ficha.setdefault("field_bg", {})

        # Colores disponibles
        opciones = [
            ("Azul", "#0066ff"),
            ("Rojo", "#ff3333"),
            ("Amarillo", "#ffd800"),
        ]

        menu = tk.Menu(self.root, tearoff=0)

        def _set_color(color_hex):
            field_bg["obstaculo"] = color_hex
            self.draw_zonas()

        # Opciones de color
        for label, color_hex in opciones:
            menu.add_command(label=label, command=lambda c=color_hex: _set_color(c))
        
        # Separador
        menu.add_separator()
        
        # Submenú de Transferir
        submenu_transferir = tk.Menu(menu, tearoff=0)
        
        # Lista de sectores disponibles
        sectores_disponibles = [s for s in self.fir.sectors if s != self.sector]
        
        def _transferir_obstaculo(sector_destino):
            """Transfiere la ficha de obstaculo al sector seleccionado"""
            import time
    
            # Prevenir envío múltiple (solo enviar si pasaron más de 200ms)
            now = time.time()
            last_time = getattr(self, "_last_obst_transfer", 0)
            
            if now - last_time < 0.2:  # 200ms de ventana
                logging.debug("Transfer de obstaculo ignorado (duplicado)")
                return
            
            self._last_obst_transfer = now
            try:
                # Obtener datos de la ficha antes de eliminarla
                if not (0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"])):
                    return

                ficha_a_transferir = self.zonas[zona_idx]["fichas"][ficha_idx]

                # Extraer información del obstaculo
                obstaculo_texto = ficha_a_transferir.get("values", {}).get("obstaculo", "")
                obstaculo_color = ficha_a_transferir.get("field_bg", {}).get("obstaculo", "#ffffff")

                # Enviar mensaje al GTA para notificar al sector destino
                self.radisplay.sendMessage({
                    "message": "transfer_obstaculo",
                    "sector_origen": self.sector,
                    "sector_destino": sector_destino,
                    "obstaculo_texto": obstaculo_texto,
                    "obstaculo_color": obstaculo_color
                })

                # Eliminar de zona actual
                self.zonas[zona_idx]["fichas"].pop(ficha_idx)
                # Redibujar
                self.draw_zonas()
            except Exception as e:
                print("Error al enviar mensaje de transferencia de obstáculo:", e)
            #finally:
            #    # Resetear flag después de un pequeño delay
            #    self.root.after(100, lambda: setattr(self, '_transfer_in_progress', False))
                
        
        for sector in sectores_disponibles:
            submenu_transferir.add_command(
                label=sector,
                command=lambda s=sector: _transferir_obstaculo(s)
            )
        
        menu.add_cascade(label="Transferir", menu=submenu_transferir)

        # Mostrar el menú en la posición del cursor
        try:
            if event is not None:
                menu.tk_popup(event.x_root, event.y_root)
            else:
                # fallback: centro de la ventana
                x = self.root.winfo_rootx() + self.root.winfo_width() // 2
                y = self.root.winfo_rooty() + self.root.winfo_height() // 2
                menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except:
                pass

    def _handle_fm_button(self):
        """Botón F/M de la barra superior. Sin funcionalidad asignada todavía."""
        pass

    # ============================
    # Plan de Vehiculo (PVH)
    # ============================

    def _handle_veh_button(self):
        """Abre dialogo CREAR PLAN DE VEHICULO (estilo SACTA)."""
        # Si ya hay uno abierto, cerrarlo
        if self._pvh_dialog and self._pvh_dialog.winfo_exists():
            try:
                self._pvh_dialog.destroy()
            except:
                pass
            self._pvh_dialog = None
            self._pvh_cs_var = None
            return

        pop = tk.Toplevel(self.root)
        self._pvh_dialog = pop

        try:
            pop.wm_overrideredirect(1)
        except:
            pass
        pop.transient(self.root)
        pop.lift()
        try:
            pop.wm_attributes("-topmost", 1)
        except:
            pass

        # Posicionar junto al boton VEH
        #JOSERRA: Mejor cerca del puntero del raton
        try:
            #bx = self.btn_veh.winfo_rootx() JOSERRA: Mejor cerca del puntero del raton
            #by = self.btn_veh.winfo_rooty() JOSERRA: Mejor cerca del puntero del raton
            bx, by = self.root.winfo_pointerxy()
            bh = self.btn_veh.winfo_height()
            #pop.geometry("+%d+%d" % (bx, by + bh + 4))
            pop.geometry("+%d+%d" % (bx, by))
        except:
            pop.geometry("+%d+%d" % (self.root.winfo_rootx() + 100, self.root.winfo_rooty() + 40))

        frame = tk.Frame(pop, bd=1, relief="solid", bg="#333333")
        frame.pack(fill="both", expand=True)

        # Cabecera rosa arrastrable
        header_frame = tk.Frame(frame, bg="#CC3399")
        header_frame.pack(side=tk.TOP, fill=tk.X)

        header_label = tk.Label(
            header_frame, text="CREAR PLAN DE VEHICULO",
            bg="#CC3399", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            pady=4
        )
        header_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Button(
            header_frame, text="X", bg="#555555", fg="white",
            font=('Lucida Sans Typewriter', 8, 'bold'),
            bd=1, width=2,
            command=lambda: self._close_pvh_dialog()
        ).pack(side=tk.RIGHT, padx=2, pady=2)

        # Arrastre - vincular tanto al frame como al label para que funcione en toda la barra
        def start_drag(e):
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        def do_drag(e):
            dx = e.x_root - pop._drag_x
            dy = e.y_root - pop._drag_y
            x = pop.winfo_x() + dx
            y = pop.winfo_y() + dy
            pop.geometry("+%d+%d" % (x, y))
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        for w in (header_frame, header_label):
            w.bind("<Button-1>", start_drag)
            w.bind("<B1-Motion>", do_drag)

        # Titulo
        tk.Label(
            frame, text="CREAR PLAN DE VEHICULO",
            bg="#333333", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            pady=4
        ).pack(side=tk.TOP, fill=tk.X, padx=6, pady=(4, 2))

        # Campos con grid
        body = tk.Frame(frame, bg="#333333")
        body.pack(fill=tk.X, padx=6, pady=4)

        tk.Label(body, text="INDICATIVO", bg="#333333", fg="white",
                 font=('Lucida Sans Typewriter', 9)).grid(row=0, column=0, sticky="w", padx=(0, 6))
        tk.Label(body, text="ANOTACIONES", bg="#333333", fg="white",
                 font=('Lucida Sans Typewriter', 9)).grid(row=0, column=1, sticky="w", padx=(6, 0))

        cs_var = tk.StringVar()
        notes_var = tk.StringVar()
        self._pvh_cs_var = cs_var

        # Auto-uppercase
        def _upper_cs(*args):
            val = cs_var.get()
            upper = val.upper()
            if val != upper:
                cs_var.set(upper)
        cs_var.trace('w', _upper_cs)

        def _upper_notes(*args):
            val = notes_var.get()
            upper = val.upper()
            if val != upper:
                notes_var.set(upper)
        notes_var.trace('w', _upper_notes)

        e_cs = tk.Entry(body, textvariable=cs_var, width=12, bg="#222222", fg="white",
                        font=('Lucida Sans Typewriter', 10), insertbackground="white")
        e_cs.grid(row=1, column=0, padx=(0, 6), pady=2)

        e_notes = tk.Entry(body, textvariable=notes_var, width=16, bg="#222222", fg="white",
                           font=('Lucida Sans Typewriter', 10), insertbackground="white")
        e_notes.grid(row=1, column=1, padx=(6, 0), pady=2)

        # Botones
        btn_frame = tk.Frame(frame, bg="#333333")
        btn_frame.pack(fill=tk.X, padx=6, pady=(4, 6))

        def _ejecutar():
            cs = cs_var.get().strip()
            notes = notes_var.get().strip()
            if not cs:
                return
            msg = {"message": "create_pvh", "cs": cs, "notes": notes, "sector": self.sector}
            try:
                self.radisplay.sendMessage(msg)
            except Exception:
                logging.warning("PVH: error enviando create_pvh", exc_info=True)
            self._close_pvh_dialog()

        tk.Button(
            btn_frame, text="EJECUTAR", bg="#444444", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            relief="raised", bd=1, padx=6, pady=6,
            command=_ejecutar
        ).pack(side=tk.LEFT, padx=(0, 4))

        tk.Button(
            btn_frame, text="CANCELAR", bg="#444444", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            relief="raised", bd=1, padx=6, pady=6,
            command=lambda: self._close_pvh_dialog()
        ).pack(side=tk.LEFT, padx=(4, 0))

        pop.bind("<Escape>", lambda e: self._close_pvh_dialog())
        e_cs.focus_set()

    def _close_pvh_dialog(self):
        if self._pvh_dialog and self._pvh_dialog.winfo_exists():
            try:
                self._pvh_dialog.destroy()
            except:
                pass
        self._pvh_dialog = None
        self._pvh_cs_var = None

    def _open_edit_pvh_notes(self, callsign):
        """Abre dialogo para editar las observaciones (pvh_notes) de un vehiculo."""
        if hasattr(self, '_edit_notes_pop') and self._edit_notes_pop and self._edit_notes_pop.winfo_exists():
            try:
                self._edit_notes_pop.destroy()
            except:
                pass

        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        pop = tk.Toplevel(self.root)
        self._edit_notes_pop = pop
        try:
            pop.wm_overrideredirect(1)
            pop.wm_attributes("-topmost", 1)
        except:
            pass
        pop.transient(self.root)
        pop.lift()

        try:
            rx = self.root.winfo_rootx() + self.root.winfo_width() // 2 - 80
            ry = self.root.winfo_rooty() + self.root.winfo_height() // 3
            pop.geometry("+%d+%d" % (rx, ry))
        except:
            pop.geometry("+200+200")

        frame = tk.Frame(pop, bd=1, relief="solid", bg="#333333")
        frame.pack(fill="both", expand=True)

        header = tk.Label(frame, text="OBSERVACIONES %s" % callsign,
                          bg="#CC3399", fg="white",
                          font=('Lucida Sans Typewriter', 9, 'bold'), pady=4)
        header.pack(side=tk.TOP, fill=tk.X)

        notes_var = tk.StringVar(value=getattr(f, 'pvh_notes', '') or '')

        def _upper(name, idx, mode):
            val = notes_var.get()
            upper = val.upper()
            if val != upper:
                notes_var.set(upper)
        notes_var.trace('w', _upper)

        body = tk.Frame(frame, bg="#333333")
        body.pack(fill=tk.X, padx=6, pady=6)

        entry = tk.Entry(body, textvariable=notes_var, width=24, bg="#222222", fg="white",
                         font=('Lucida Sans Typewriter', 10), insertbackground="white")
        entry.pack(fill=tk.X)

        btn_frame = tk.Frame(frame, bg="#333333")
        btn_frame.pack(fill=tk.X, padx=6, pady=(2, 6))

        def _guardar():
            new_notes = notes_var.get().strip()
            try:
                self.radisplay.sendMessage({
                    "message": "set_pvh_notes", "cs": callsign, "notes": new_notes
                })
            except Exception:
                pass
            pop.destroy()

        tk.Button(btn_frame, text="GUARDAR", bg="#444444", fg="white",
                  font=('Lucida Sans Typewriter', 9, 'bold'),
                  relief="raised", bd=1, padx=6, pady=4,
                  command=_guardar).pack(side=tk.LEFT, padx=(0, 4))
        tk.Button(btn_frame, text="CANCELAR", bg="#444444", fg="white",
                  font=('Lucida Sans Typewriter', 9, 'bold'),
                  relief="raised", bd=1, padx=6, pady=4,
                  command=lambda: pop.destroy()).pack(side=tk.LEFT)

        pop.bind("<Escape>", lambda e: pop.destroy())
        entry.focus_set()

    def open_pista_entrada(self, callsign):
        """Abre dialogo PISTA ENTRADA para autorizar vehiculo a entrar en pista."""
        # Cerrar si existe
        if hasattr(self, '_ent_popup') and self._ent_popup and self._ent_popup.winfo_exists():
            try:
                self._ent_popup.destroy()
            except:
                pass

        pop = tk.Toplevel(self.root)
        self._ent_popup = pop

        try:
            pop.wm_overrideredirect(1)
        except:
            pass
        pop.transient(self.root)
        pop.lift()
        try:
            pop.wm_attributes("-topmost", 1)
        except:
            pass

        # Posicionar en centro de la ventana OSF
        try:
            rx = self.root.winfo_rootx() + self.root.winfo_width() // 2 - 60
            ry = self.root.winfo_rooty() + self.root.winfo_height() // 3
            pop.geometry("+%d+%d" % (rx, ry))
        except:
            pop.geometry("+200+200")

        frame = tk.Frame(pop, bd=1, relief="solid", bg="#333333")
        frame.pack(fill="both", expand=True)

        # Cabecera rosa arrastrable
        header_frame = tk.Frame(frame, bg="#CC3399")
        header_frame.pack(side=tk.TOP, fill=tk.X)

        header_label = tk.Label(
            header_frame, text="PISTA ENTRADA",
            bg="#CC3399", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            pady=4
        )
        header_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Button(
            header_frame, text="X", bg="#555555", fg="white",
            font=('Lucida Sans Typewriter', 8, 'bold'),
            bd=1, width=2,
            command=lambda: pop.destroy()
        ).pack(side=tk.RIGHT, padx=2, pady=2)

        # Arrastre - vincular tanto al frame como al label
        def start_drag(e):
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        def do_drag(e):
            dx = e.x_root - pop._drag_x
            dy = e.y_root - pop._drag_y
            x = pop.winfo_x() + dx
            y = pop.winfo_y() + dy
            pop.geometry("+%d+%d" % (x, y))
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        for w in (header_frame, header_label):
            w.bind("<Button-1>", start_drag)
            w.bind("<B1-Motion>", do_drag)

        # Obtener cabeceras del aerodromo
        rwys = []
        try:
            f = self._find_flight_by_callsign(callsign)
            ad_code = getattr(f, 'adep', None) or getattr(f, 'ades', None)
            if ad_code and ad_code in self.fir.aerodromes:
                rwys = [rwy.txt_desig for rwy in self.fir.aerodromes[ad_code].rwy_direction_list]
        except Exception:
            pass
        if not rwys:
            rwys = self._all_runways()

        # Lista vertical de cabeceras
        body = tk.Frame(frame, bg="#333333")
        body.pack(fill=tk.X, padx=6, pady=4)

        for rwy in rwys:
            lbl = tk.Label(
                body, text="  %s  " % rwy,
                bg="#444444", fg="white",
                font=('Lucida Sans Typewriter', 10, 'bold'),
                pady=4, anchor="w", cursor="hand2"
            )
            lbl.pack(fill=tk.X, pady=1)

            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="white", fg="#333333"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="#444444", fg="white"))
            lbl.bind("<Button-1>", lambda e, r=rwy: self._select_ent_runway(callsign, r, pop))

        pop.bind("<Escape>", lambda e: pop.destroy())

    def _select_ent_runway(self, callsign, runway, popup):
        """Envia authorize_ent y cierra popup PISTA ENTRADA."""
        try:
            self.radisplay.sendMessage({
                "message": "authorize_ent", "cs": callsign, "runway": runway
            })
        except Exception:
            pass
        try:
            popup.destroy()
        except:
            pass

    def _get_runway_pairs(self, ad_code):
        """Obtiene pares de pistas fisicas (ej: '06L/24R') de un aerodromo."""
        if ad_code not in self.fir.aerodromes:
            return []
        ad = self.fir.aerodromes[ad_code]
        desigs = [rwy.txt_desig for rwy in ad.rwy_direction_list]
        paired = set()
        pairs = []
        for d in desigs:
            if d in paired:
                continue
            num = int(d[:2])
            suffix = d[2:] if len(d) > 2 else ''
            recip_num = (num + 18) % 36
            if recip_num == 0:
                recip_num = 36
            recip_suffix = {'L': 'R', 'R': 'L', 'C': 'C'}.get(suffix, '')
            recip = '%02d%s' % (recip_num, recip_suffix)
            if recip in desigs:
                pairs.append('%s/%s' % (d, recip))
                paired.add(d)
                paired.add(recip)
            else:
                pairs.append(d)
                paired.add(d)
        return pairs

    def _open_pista_solicitud(self, callsign, mode='CRU'):
        """Abre dialogo de seleccion de cabecera de pista (individual).
        mode='CRU' para solicitud de cruce, mode='ENT' para solicitud de entrada."""
        if hasattr(self, '_cru_popup') and self._cru_popup and self._cru_popup.winfo_exists():
            try:
                self._cru_popup.destroy()
            except:
                pass

        pop = tk.Toplevel(self.root)
        self._cru_popup = pop

        try:
            pop.wm_overrideredirect(1)
        except:
            pass
        pop.transient(self.root)
        pop.lift()
        try:
            pop.wm_attributes("-topmost", 1)
        except:
            pass

        try:
            rx = self.root.winfo_rootx() + self.root.winfo_width() // 2 - 60
            ry = self.root.winfo_rooty() + self.root.winfo_height() // 3
            pop.geometry("+%d+%d" % (rx, ry))
        except:
            pop.geometry("+200+200")

        title = "PISTA CRUCE" if mode == 'CRU' else "PISTA ENTRADA"

        frame = tk.Frame(pop, bd=1, relief="solid", bg="#333333")
        frame.pack(fill="both", expand=True)

        header_frame = tk.Frame(frame, bg="#CC3399")
        header_frame.pack(side=tk.TOP, fill=tk.X)

        header_label = tk.Label(
            header_frame, text=title,
            bg="#CC3399", fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            pady=4
        )
        header_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        tk.Button(
            header_frame, text="X", bg="#555555", fg="white",
            font=('Lucida Sans Typewriter', 8, 'bold'),
            bd=1, width=2,
            command=lambda: pop.destroy()
        ).pack(side=tk.RIGHT, padx=2, pady=2)

        def start_drag(e):
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        def do_drag(e):
            dx = e.x_root - pop._drag_x
            dy = e.y_root - pop._drag_y
            x = pop.winfo_x() + dx
            y = pop.winfo_y() + dy
            pop.geometry("+%d+%d" % (x, y))
            pop._drag_x = e.x_root
            pop._drag_y = e.y_root
        for w in (header_frame, header_label):
            w.bind("<Button-1>", start_drag)
            w.bind("<B1-Motion>", do_drag)

        # Obtener cabeceras individuales del aerodromo
        rwys = []
        try:
            f = self._find_flight_by_callsign(callsign)
            ad_code = getattr(f, 'adep', None) or getattr(f, 'ades', None)
            if ad_code and ad_code in self.fir.aerodromes:
                rwys = [rwy.txt_desig for rwy in self.fir.aerodromes[ad_code].rwy_direction_list]
        except Exception:
            pass
        if not rwys:
            rwys = self._all_runways()

        body = tk.Frame(frame, bg="#333333")
        body.pack(fill=tk.X, padx=6, pady=4)

        msg_type = "request_cru" if mode == 'CRU' else "request_ent"
        for rwy in rwys:
            lbl = tk.Label(
                body, text="  %s  " % rwy,
                bg="#444444", fg="white",
                font=('Lucida Sans Typewriter', 10, 'bold'),
                pady=4, anchor="w", cursor="hand2"
            )
            lbl.pack(fill=tk.X, pady=1)

            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="white", fg="#333333"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="#444444", fg="white"))
            lbl.bind("<Button-1>", lambda e, r=rwy, m=msg_type: self._select_solicitud_runway(callsign, r, m, pop))

        pop.bind("<Escape>", lambda e: pop.destroy())

    def _open_pista_cruce(self, callsign):
        """Abre dialogo PISTA CRUCE (cabeceras individuales)."""
        self._open_pista_solicitud(callsign, mode='CRU')

    def _select_solicitud_runway(self, callsign, runway, msg_type, popup):
        """Envia request_cru o request_ent con la cabecera seleccionada y cierra popup."""
        try:
            self.radisplay.sendMessage({
                "message": msg_type, "cs": callsign, "runway": runway
            })
        except Exception:
            pass
        try:
            popup.destroy()
        except:
            pass

    def _all_runways(self):
        """Cabeceras de todos los aerodromos del escenario (respaldo si el movil no tiene aerodromo)."""
        rwys = []
        try:
            for ad in self.fir.aerodromes.values():
                for rwy in getattr(ad, 'rwy_direction_list', []):
                    if rwy.txt_desig not in rwys:
                        rwys.append(rwy.txt_desig)
        except Exception:
            pass
        return rwys

    def _on_anotaciones_click(self, zona_idx, ficha_idx):
        """Click en campo 'anotaciones' de ficha VEH: abre Entry inline para editar notas PVH."""
        self._close_any_active_edit()

        if zona_idx < 0 or zona_idx >= len(self.zonas):
            return
        if ficha_idx < 0 or ficha_idx >= len(self.zonas[zona_idx]["fichas"]):
            return

        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        nombres_campos = ficha.get("fields", [])
        if "anotaciones" not in nombres_campos:
            return
        field_idx = nombres_campos.index("anotaciones")

        margin = getattr(self, "margin", 50)
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        usable_width = canvas_width - 2 * margin
        offset = self.zonas[zona_idx]["scroll_offset"]

        ficha_h = 25
        sep_h = 2
        line_height = ficha_h + sep_h

        line_idx = ficha_idx - offset
        y_end = (sum(self.zona_heights[:zona_idx + 1]) * canvas_height)
        line_bottom = y_end - line_idx * line_height - sep_h
        line_top = line_bottom - ficha_h

        fixed_total, flex_count = 0.0, 0
        for nm in nombres_campos:
            if self._is_flex(nm):
                flex_count += 1
            else:
                fixed_total += self._field_width(nm)
        remaining = max(0.0, usable_width - fixed_total)
        flex_each = (remaining / flex_count) if flex_count > 0 else 0.0

        x_cursor = margin
        for idx, nm in enumerate(nombres_campos):
            w = flex_each if self._is_flex(nm) else self._field_width(nm)
            if idx == field_idx:
                x_start, x_end = x_cursor, x_cursor + w
                break
            x_cursor += w
        else:
            return

        valor_actual = ficha.get("values", {}).get("anotaciones", "")
        self._edit_entry_var = tk.StringVar(value=valor_actual)
        entry = tk.Entry(self.canvas, textvariable=self._edit_entry_var,
                         font=self.font_style, justify="center")
        entry.place(x=x_start, y=line_top, width=(x_end - x_start), height=(line_bottom - line_top))

        def _norm_var(*args):
            v = self._edit_entry_var.get()
            if len(v) > 20:
                v = v[:20]
            if v != v.upper():
                v = v.upper()
            if v != self._edit_entry_var.get():
                self._edit_entry_var.set(v)

        self._edit_entry_var.trace("w", _norm_var)

        def _commit(event=None):
            if self._edit_entry_var is None or self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            nuevo_valor = self._edit_entry_var.get().upper()[:20]
            ficha.setdefault("values", {})["anotaciones"] = nuevo_valor

            self._edit_entry = None
            self._edit_entry_var = None
            self._campolibre_edit_active = False
            try:
                entry.destroy()
            except Exception:
                pass
            self.draw_zonas()

            f = self._find_flight_by_callsign(callsign)
            if f:
                try:
                    # Antes enviaba 'create_pvh' (reiniciaba la fase del vehiculo); ahora solo las notas
                    self.radisplay.sendMessage({
                        "message": "set_pvh_notes", "cs": callsign, "notes": nuevo_valor
                    })
                except Exception:
                    pass

        def _cancel(event=None):
            if self._edit_entry is None:
                return
            if not hasattr(entry, 'winfo_exists') or not entry.winfo_exists():
                return
            self._edit_entry = None
            self._edit_entry_var = None
            self._campolibre_edit_active = False
            try:
                entry.destroy()
            except Exception:
                pass
            self.draw_zonas()

        entry.bind("<Return>", _commit)
        entry.bind("<Escape>", _cancel)
        entry.bind("<FocusOut>", _commit)
        entry.focus_set()

        self._edit_entry = entry
        self._campolibre_edit_active = True
        self._campolibre_rect = (x_start, x_end, line_top, line_bottom)
        self._campolibre_original = valor_actual
        self._campolibre_cancel_cb = _cancel
        self._campolibre_ficha = ficha
        self._campolibre_callsign = callsign

        self._edit_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_edit_just_opened", False))

    def _handle_obst_button(self):
        """
        Si hay un obstáculo seleccionado, muestra popup BORRAR/ANULAR.
        Si no, crea un obstáculo nuevo (comportamiento anterior).
        """
        if self.selected_line:
            zi, fi = self.selected_line
            if 0 <= zi < len(self.zonas) and 0 <= fi < len(self.zonas[zi]["fichas"]):
                ficha = self.zonas[zi]["fichas"][fi]
                if ficha.get("is_obstaculo"):
                    self._open_obst_delete_popup(zi, fi)
                    return
        # si no hay obstáculo seleccionado, comportamiento original:
        self._add_obstaculo_strip()

    def _open_obst_delete_popup(self, zona_idx, ficha_idx):
        # Cierra uno anterior si quedara abierto
        if hasattr(self, "_obst_popup") and self._obst_popup and self._obst_popup.winfo_exists():
            try:
                self._obst_popup.destroy()
            except:
                pass

        pop = tk.Toplevel(self.root)
        self._obst_popup = pop

        # Estética y comportamiento tipo proyecto
        try:
            pop.wm_overrideredirect(1)  # sin marco
        except:
            pass
        pop.transient(self.root)
        pop.lift()
        try:
            pop.wm_attributes("-topmost", 1)
        except:
            pass

        # Posicionar junto al botón OBST
        try:
            bx = self.btn_obst.winfo_rootx()
            by = self.btn_obst.winfo_rooty()
            bw = self.btn_obst.winfo_width()
            pop.geometry("+%d+%d" % (bx + bw + 6, by))
        except:
            pop.geometry("+%d+%d" % (self.topbar.winfo_rootx() + self.topbar.winfo_width() - 120,
                                     self.topbar.winfo_rooty() + 2))

        frame = tk.Frame(pop, bd=1, relief="solid", bg="#333333")
        frame.pack(fill="both", expand=True)

        # === Cabecera ===
        header = tk.Label(
            frame,
            text="BORRAR FICHA OBSTÁCULO",
            bg="#333333",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            pady=4
        )
        header.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(4, 2))

        # === Botón BORRAR ===
        btn_borrar = tk.Button(
            frame,
            text="BORRAR",
            bg="#444444",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            relief="raised",
            bd=1,
            width=10,
            command=lambda: self._delete_obstaculo(zona_idx, ficha_idx, pop)
        )
        btn_borrar.pack(side=tk.LEFT, padx=6, pady=6)

        # === Botón ANULAR ===
        btn_anular = tk.Button(
            frame,
            text="ANULAR",
            bg="#444444",
            fg="white",
            font=('Lucida Sans Typewriter', 9, 'bold'),
            relief="raised",
            bd=1,
            width=10,
            command=lambda: self._close_obst_popup(pop)
        )
        btn_anular.pack(side=tk.LEFT, padx=6, pady=6)

        # Escape cierra el popup
        pop.bind("<Escape>", lambda e: self._close_obst_popup(pop))

    def _close_obst_popup(self, pop=None):
        try:
            (pop or getattr(self, "_obst_popup", None)).destroy()
        except:
            pass
        self._obst_popup = None

    def _delete_obstaculo(self, zona_idx, ficha_idx, pop=None):
        # Validaciones
        if not (0 <= zona_idx < len(self.zonas)):
            self._close_obst_popup(pop)
            return
        fichas = self.zonas[zona_idx]["fichas"]
        if not (0 <= ficha_idx < len(fichas)):
            self._close_obst_popup(pop)
            return

        ficha = fichas[ficha_idx]
        if not ficha.get("is_obstaculo"):
            # Si por lo que sea no es obstáculo, no hacemos nada
            self._close_obst_popup(pop)
            return

        # Borrar la ficha
        fichas.pop(ficha_idx)

        # Limpiar selección si apuntaba a ella
        if self.selected_line == (zona_idx, ficha_idx):
            self.selected_line = None

        self._close_obst_popup(pop)
        self.draw_zonas()

    def _on_hrls_click(self, zona_idx, ficha_idx):
        """
        Toggle de HRLS en la ficha EXTENDIDA:
          - Invierte f.hrls
          - Envía mensaje al GTA
          - Actualiza texto ('RLS' / 'HRLS') y color (normal / rojo) del campo en la misma ficha
        """
        # 1) Localiza la ficha
        try:
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        except Exception:
            return

        # Sólo tiene sentido en fichas extendidas
        # if not ficha.get("is_extended", False):
        #     return

        # 2) Callsign del vuelo asociado (puede venir en 'callsign' o en 'parent_callsign')
        cs = ficha.get("values", {}).get("callsign") or ficha.get("parent_callsign")
        if not cs:
            return

        # 3) Obtener el vuelo
        f = self._find_flight_by_callsign(cs)
        if not f:
            return

        # 4) Invertir flag y notificar al GTA
        f.hrls = not bool(getattr(f, "hrls", False))
        try:
            self.radisplay.sendMessage({
                "message": "set_hrls",
                "cs": f.callsign,
                "hrls_status": f.hrls
            })
        except Exception:
            pass

        # 5) Actualizar el campo en la propia ficha extendida
        txt = "RLS" if f.hrls else "HRLS"
        ficha.setdefault("values", {})["hrls"] = txt
        fc = ficha.setdefault("field_colors", {})
        if f.hrls:
            # RLS → color normal heredado: quitamos override rojo
            fc.pop("hrls", None)
        else:
            # HRLS → forzar rojo
            fc["hrls"] = "red"

        # 6) Redibujar
        self.draw_zonas()

    def _on_sid_click(self, zona_idx, ficha_idx, event=None):
        print("Left click on SID field")
        # self._toggle_extended(zona_idx, ficha_idx) # artificio para actualizar la extendida. No funciona.

        # 1) Localiza la ficha
        try:
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        except Exception:
            return

        # Solo tiene sentido en fichas extendidas
        if not ficha.get("is_extended", False):
            return

        # 2) Callsign del vuelo asociado (puede venir en 'callsign' o en 'parent_callsign')
        cs = ficha.get("values", {}).get("callsign") or ficha.get("parent_callsign")
        if not cs:
            return

        # 3) Obtener el vuelo
        f = self._find_flight_by_callsign(cs)
        if not f:
            return

        self.radisplay.sid_dialog(f, event)

    # ============================
    # Ficha Extendida
    # ============================
    def _toggle_extended(self, zona_idx, ficha_idx):
        """
        Muestra/oculta una 'Ficha Extendida' justo DEBAJO (visual) de la ficha madre.
        - Renderizas de abajo a arriba, así que para que quede debajo hay que insertar en ficha_idx.
        - Si ya existe una extendida del mismo callsign en la zona, se elimina (toggle off).
        """
        # 0) Validaciones
        if not (0 <= zona_idx < len(self.zonas)):
            return
        zona = self.zonas[zona_idx]
        if not (0 <= ficha_idx < len(zona["fichas"])):
            return

        ficha_madre = zona["fichas"][ficha_idx]
        cs = ficha_madre.get("values", {}).get("callsign", "")
        if not cs:
            return

        # 1) ¿Hay ya alguna extendida de este CS en la zona? -> Elimínala (toggle OFF) y sal.
        to_del = [idx for idx, fx in enumerate(zona["fichas"])
                  if fx is not ficha_madre and fx.get("is_extended") and fx.get("parent_callsign") == cs]

        if to_del:
            for idx in reversed(to_del):
                zona["fichas"].pop(idx)
                if self.selected_line and self.selected_line == (zona_idx, idx):
                    self.selected_line = None
            self.draw_zonas()
            return  # toggle OFF completado

        # 2) Toggle ON: crear la extendida y colocarla DEBAJO (visual) de la madre
        #    Como dibujas de abajo hacia arriba, insertar en ficha_idx pone la extendida debajo.
        f = self._find_flight_by_callsign(cs)

        local_dep = bool(ficha_madre.get("local_dep"))
        local_des = bool(ficha_madre.get("local_des"))

        # Layout para extendida (usa tu resolutor si existe; si no, fallback)
        try:
            ext_fields = self._resolve_ext_fields(self.bahia_type, zona_idx, local_dep, local_des)
        except AttributeError:
            ext_fields = ["hacc", "resto", "qnh"]

        # Valores del vuelo
        hacc = getattr(f, "hacc", "") if f else ""
        squawk = getattr(f, "squawk", None) if f else None
        cssr = str(squawk) if squawk is not None else ""
        orig = str(getattr(f, "adep", "") or "") if f else ""
        dest = str(getattr(f, "ades", "") or "") if f else ""
        # airline: usar radio_callsign (nombre de compañía) derivado del callsign
        airline = str(getattr(f, "radio_callsign", "") or "") if f else ""
        # vel: velocidad de crucero asignada al tipo de aeronave, tabla "Velocidades"
        # del escenario Excel (fir.vel_cruz: tipo -> velocidad). No es la IAS en
        # tiempo real (con la aeronave parada/rodando esa era siempre 0 y el campo
        # aparecia en blanco).
        type_val = str(getattr(f, "type", "") or "") if f else ""
        vel_cruz = getattr(self.fir, "vel_cruz", {}) or {}
        vel = str(vel_cruz.get(type_val, "") or "")
        sid = str(getattr(f, "stand_sid_atc", "") or "") if f else ""
        # cfl: nivel de vuelo autorizado (cfl_c almacenado en FL, e.g. 60.0 = FL060)
        cfl_val = getattr(f, "cfl_c", None) if f else None
        cfl = "%03d" % int(round(cfl_val)) if cfl_val is not None else ""

        hrls_bool = bool(getattr(f, "hrls", False)) if f else False
        hrls = "RLS" if hrls_bool else "HRLS"

        # QNH: propiedad global de la atmósfera en GTA, accesible via radisplay.giw.qnh
        try:
            qnh_float = self.radisplay.giw.qnh
            qnh = "Q%04d" % int(round(qnh_float))
        except Exception:
            qnh = ""

        # Valores editables que pueden cambiar desde fichas extendidas
        holdp_val = str(getattr(f, "holdp", "HP") or "HP") if f else "HP"
        gate_val = str(getattr(f, "gate", "GT") or "GT") if f else "GT"

        # eobt/ctot para layouts extendidos que lo incluyen (mismo slot único que la ficha normal)
        eobt_ext, _eobt_ext_is_ctot = self._eobt_slot(f)

        # eldt y park para layouts extendidos
        eldt_raw = getattr(f, "eldt", None) if f else None
        eldt_ext = str(eldt_raw) if eldt_raw is not None else ""
        park_ext = str(getattr(f, "park", "") or "") if f else ""

        # campolibre: misma fuente de verdad que la ficha normal (f.rutrod)
        rutrod_raw = getattr(f, "rutrod", "-libre-") if f else "-libre-"
        campolibre_ext = "" if rutrod_raw is None else str(rutrod_raw)

        ext_values_full = {
            "hacc": hacc,
            "cssr": cssr,
            "orig": orig,
            "dest": dest,
            "airline": airline,
            "vel": vel,
            "sid": sid,
            "sid_ext": sid,  # sid_ext = mismo SID autorizado (stand_sid_atc)
            "cfl": cfl,
            "hrls": hrls,
            "qnh": qnh,
            "holdp": holdp_val,
            "gate": gate_val,
            "eobt": eobt_ext,
            "eldt": eldt_ext,
            "park": park_ext,
            "campolibre": campolibre_ext,
        }

        ext_values = {k: ext_values_full.get(k, self._field_value(k)) for k in ext_fields}
        ext_field_colors = dict(ficha_madre.get("field_colors", {}))
        if not hrls_bool:
            ext_field_colors["hrls"] = "red"

        ext_ficha = {
            "fields": ext_fields,
            "values": ext_values,
            "local_dep": local_dep,
            "local_des": local_des,
            "field_colors": ext_field_colors,
            "eobt_mode": ficha_madre.get("eobt_mode", "eobt"),
            "field_bg": dict(ficha_madre.get("field_bg", {})),  # hereda el resalte CTOT (fondo blanco)
            "x_offset": ficha_madre.get("x_offset", 0),
            "is_extended": True,
            "parent_callsign": cs,
        }

        # Insertar en ficha_idx -> queda POR DEBAJO visualmente
        zona["fichas"].insert(ficha_idx, ext_ficha)

        # Si tenías seleccionada la madre y la quieres mantener, puede que su índice suba en +1
        if self.selected_line and self.selected_line == (zona_idx, ficha_idx):
            self.selected_line = (zona_idx, ficha_idx + 1)

        self.draw_zonas()

    def _close_extended_by_callsign(self, callsign):
        """Elimina la ficha extendida asociada al callsign (si existe) y
        limpia el flag en la ficha madre."""
        if not callsign:
            return
        for zi, zona in enumerate(self.zonas):
            fichas = zona.get("fichas", [])
            idx_to_del = None
            for idx, ficha in enumerate(fichas):
                if ficha.get("is_extended") and ficha.get("parent_callsign") == callsign:
                    idx_to_del = idx
                    break
            if idx_to_del is not None:
                # borrar extendida
                fichas.pop(idx_to_del)
                # limpiar flag en la madre (si la encontramos en esta zona)
                for f2 in fichas:
                    if f2.get("values", {}).get("callsign") == callsign:
                        try:
                            f2["extended_open"] = False
                        except Exception:
                            pass
                        break
                # si solo puede existir una extendida por callsign, ya podemos salir
                break

    # ============================
    # Eventos de raton en fichas
    # ============================
    def left_clicked(self, event, zona_idx, ficha_idx, field_idx, campo_nombre):
        if campo_nombre == "act":
            self._on_act_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "callsign":
            self._on_callsign_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "campolibre":
            self._on_campolibre_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "park":
            self._on_park_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "gate":
            self._on_gate_click(zona_idx, ficha_idx, field_idx)
            return
        elif campo_nombre == "holdp":
            self._on_holdp_click(zona_idx, ficha_idx, field_idx)
            return
        elif campo_nombre == "autorizacion":
            self._on_autorizacion_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "anotaciones":
            self._on_anotaciones_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "obstaculo":
            self._on_obstaculo_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "hrls":
            self._on_hrls_click(zona_idx, ficha_idx)
            return
        elif campo_nombre == "sid":
            self._on_sid_click(zona_idx, ficha_idx, event)
            return
        else:
            print("Left click → Zona:%d Ficha:%d Campo:%s (idx:%d)" %
                  (zona_idx, ficha_idx, campo_nombre, field_idx))

    def right_clicked(self, event, zona_idx, ficha_idx, field_idx, campo_nombre):
        print("Right click → Zona:%d Ficha:%d Campo:%s (idx:%d)" %
              (zona_idx, ficha_idx, campo_nombre, field_idx))
        if campo_nombre == "obstaculo":
            self._on_obstaculo_right_click(zona_idx, ficha_idx, event)
            return
        elif campo_nombre == "callsign":
            # VEH con PVH no tienen ficha extendida
            ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
            if ficha.get("is_veh"):
                return
            # Toggle de ficha extendida
            self._toggle_extended(zona_idx, ficha_idx)
            return
        # Si haces clic derecho sobre el campo "act", abrimos el popup de acciones
        elif campo_nombre == "act":
            self._act_popup_ctx = (zona_idx, ficha_idx)
            try:
                at_x = event.x_root
                at_y = event.y_root
                self._show_act_popup(at_x, at_y)
            except Exception as e:
                print("Error al abrir popup ACCIONES:", e)
            return
        else:
            print("Right click → Zona:%d Ficha:%d Campo:%s (idx:%d)" %
                  (zona_idx, ficha_idx, campo_nombre, field_idx))

    def rightclicked_from_label_act(self, callsign, event):
        ficha = self._find_ficha_by_callsign(callsign)
        zona_idx = ficha[0]
        ficha_idx = ficha[1]
        self._act_popup_ctx = (zona_idx, ficha_idx)
        try:
            at_x = event.x_root
            at_y = event.y_root
            self._show_act_popup(at_x, at_y)
        except Exception as e:
            print("Error al abrir popup ACCIONES:", e)

    # ============================
    # Opcion REVOCAR
    # ============================
    def revocar(self, callsign):
        """
        Paso atrás en la secuencia OSF del vuelo indicado por 'callsign'.
        - Si es salida local: usa Aircraft.OSF_DEPSEQ
        - Si es llegada local: usa Aircraft.OSF_ARRSEQ
        - Si es sobrevuelo: usa Aircraft.OSF_OVFSEQ
        Reconstruye la ficha tras el cambio.
        """
        if not callsign:
            return False

        cs = callsign.strip()
        # 1) localizar vuelo
        f = self._find_flight_by_callsign(cs)
        if not f:
            # Fallback: buscar en la lista cruda por si aún no hay ficha creada
            try:
                f = next(v for v in getattr(self.radisplay, "flights", []) if getattr(v, "callsign", None) == cs)
            except StopIteration:
                return False

        # 2) ámbito local (sector)
        sector = (self.sector or "").split(",")[0]
        local_ads = getattr(self.fir, "local_ads", {}) or {}
        ads_set = local_ads.get(sector, set())

        is_dep_local = getattr(f, "adep", None) in ads_set
        is_arr_local = getattr(f, "ades", None) in ads_set

        # 3) escoger secuencia
        seq = None
        if is_dep_local and hasattr(Aircraft, "OSF_DEPSEQ"):
            seq = list(Aircraft.OSF_DEPSEQ)
        elif is_arr_local and hasattr(Aircraft, "OSF_ARRSEQ"):
            seq = list(Aircraft.OSF_ARRSEQ)
        else:
            if hasattr(Aircraft, "OSF_OVFSEQ"):
                seq = list(Aircraft.OSF_OVFSEQ)

        if not seq:
            # No hay secuencia válida para retroceder
            return False

        # 3.5) Si el estado actual es una solicitud, volver al estado de autorización anterior
        current_pof = getattr(f, "OSF_pof", None)

        # VEH: revocar fases ENR/ENT/LIB/CRR/CRU del flujo de entrada/cruce de pista
        if getattr(f, 'fr', None) == 'VEH':
            veh_new = None
            if current_pof in (Aircraft.ENTREQ, Aircraft.ENTERING):
                veh_new = Aircraft.TAXIING_OUT
            elif current_pof in (Aircraft.CRUREQ, Aircraft.CROSSING):
                veh_new = getattr(f, 'pre_cru_pof', None) or Aircraft.TAXIING_OUT
            elif current_pof == Aircraft.LIB:
                # LIB -> ENT o CRU (revocar liberacion, volver a la fase anterior)
                veh_new = Aircraft.CROSSING if getattr(f, 'pre_cru_pof', None) else Aircraft.ENTERING
            if veh_new is not None:
                f.OSF_pof = veh_new
                if veh_new in (Aircraft.TAXIING_OUT, Aircraft.TAXIING_IN):
                    f.ent_runway = None
                    f.pre_ent_pof = None
                    f.cru_runway = None
                    f.pre_cru_pof = None
                try:
                    self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": veh_new})
                except Exception:
                    pass
                return True
            # VEH en TOU u otra fase base: no hay nada que revocar
            return False

        # Aviones: revocar el flujo de cruce de pista (CRR/CRU/LIB)
        cru_prev = None
        if current_pof == Aircraft.CRUREQ:
            cru_prev = getattr(f, 'pre_cru_pof', None) or Aircraft.TAXIING_OUT  # CRR -> fase previa
        elif current_pof == Aircraft.CROSSING:
            cru_prev = Aircraft.CRUREQ  # CRU -> CRR
        elif current_pof == Aircraft.ENTERING and getattr(f, 'pre_ent_pof', None):
            cru_prev = f.pre_ent_pof
        elif current_pof == Aircraft.LIB:
            if getattr(f, 'pre_cru_pof', None):
                cru_prev = Aircraft.CROSSING
            elif getattr(f, 'pre_ent_pof', None):
                cru_prev = Aircraft.ENTERING
            else:
                cru_prev = Aircraft.TAXIING_OUT
        if cru_prev is not None:
            f.OSF_pof = cru_prev
            try:
                if current_pof == Aircraft.CRUREQ:
                    self.radisplay.sendMessage({"message": "cancel_cru", "cs": cs})
                else:
                    self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": cru_prev})
            except Exception:
                pass
            return True

        request_prev = {
            Aircraft.STARTREQ:  Aircraft.PREPARING,   # SUR → PRE
            Aircraft.PUSHREQ:   Aircraft.STARTING,    # PBR → S/U
            Aircraft.DEPREQ:    Aircraft.LININGUP,    # DPR → L/U
            Aircraft.LDGREQ:    Aircraft.INCOMING,     # LDR → INC
            Aircraft.TGLREQ:    Aircraft.INCOMING,     # TGL → INC
            Aircraft.STICEREQ:  Aircraft.INCOMING,     # SIR → INC
            Aircraft.REAREQ:    Aircraft.INCOMING,     # REA → INC
        }
        if current_pof == Aircraft.TAXIREQ:
            # TXR: vuelve a P/B, salvo stand sin retroceso en la hoja RetrocesosOSF (vuelve a S/U)
            new_pof = Aircraft.STARTING if self._pushback_rule(f) == 'none' else Aircraft.PUSH
            f.OSF_pof = new_pof
            try:
                self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": new_pof})
            except Exception:
                pass
            return True
        elif current_pof in request_prev:
            new_pof = request_prev[current_pof]
            f.OSF_pof = new_pof
            try:
                self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": new_pof})
            except Exception:
                pass
            return True

        # 4) retroceder un paso si es posible
        try:
            idx = seq.index(current_pof)
        except ValueError:
            # estado actual no está en la secuencia
            return False

        if idx <= 0:
            # ya está en el primer estado; nada que revocar
            return False

        # No revocar a PREPARING: select_panel() devuelve '' → la ficha desaparece
        if seq[idx - 1] == Aircraft.PREPARING:
            return False

        new_pof = seq[idx - 1]
        # TAX de un stand sin retroceso (hoja RetrocesosOSF): vuelve a S/U, no a P/B
        if seq[idx] == Aircraft.TAXIING_OUT and new_pof == Aircraft.PUSH and self._pushback_rule(f) == 'none':
            new_pof = Aircraft.STARTING
        f.OSF_pof = new_pof

        # 5) notificar al GTA
        try:
            self.radisplay.sendMessage({"message": "set_osf_pof", "cs": cs, "osf_pof": new_pof})
            # self._update_hacc_and_send(f)
        except Exception:
            pass

        # # 6) reconstruir la ficha (permite que cambie de zona si procede)
        # self.update_strip(f, keep_position=False, refresh=True)  # Accion en local. Probar si conflicto con retorno GTA
        return True

