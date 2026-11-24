# -*- coding: iso8859-15 -*-

import Tkinter as tk
import os
from lib.osf.OSF import OSF
from lib import ConfMgr
from lib import Aircraft

conf = ConfMgr.GammaConfig()


class PrevDesp(OSF):
    """
    Ventana de previstos de despegue.
    Reutiliza la mecanica de OSF (render, scroll, eventos) con singleton propio.
    """
    _instance = None

    @classmethod
    def get_instance(cls, radisplay=None, bahia_type="CLR"):
        """
        Devuelve la unica instancia de PrevDesp.
        - Si existe y su ventana sigue viva, la reutiliza.
        - Si no existe o la ventana fue destruida, crea una nueva.
        """
        inst = cls._instance

        if inst is not None:
            try:
                if not hasattr(inst, "root") or not inst.root.winfo_exists():
                    inst = None
            except:
                inst = None

        if inst is None:
            if radisplay is None:
                raise ValueError("PrevDesp aun no existe: hay que pasar radisplay la primera vez")
            inst = cls(radisplay, bahia_type)
            cls._instance = inst

        return inst

    def __init__(self, radisplay, bahia_type="CLR"):
        # PrevDesp trabaja sobre CLR por diseno.
        if not bahia_type:
            bahia_type = "CLR"

        OSF.__init__(self, radisplay, bahia_type)

        # --- CONFIGURACION ESPECIFICA DE PREVDESP ---
        
        # Redefinir field_defs con solo los campos que necesitamos
        self.field_defs = {
            "act":       {"width": 70,  "value": "   "},
            "callsign":  {"width": 120,  "value": "IBE1234"},
            "autorizacion": {"width": 30, "value": ""},
            "type":      {"width": 90,  "value": "A320"},
            "wake":      {"width": 40,  "value": "H+"},
            "park":      {"width": 60,  "value": "152"},
            "eobt":      {"width": 70,  "value": "1234"},
            "tobt":      {"width": 70,  "value": "1234"},
            "hopm":      {"width": 70, "value": "1234"},
            "dtot":      {"width": 70, "value": "1234"},
            "ctot":      {"width": 70,  "value": ""},
            "tsat":      {"width": 70,  "value": ""},
            "tsac":      {"width": 70,  "value": "___"},
            "asrt":      {"width": 70,  "value": ""},
            "dest":      {"width": 70,  "value": "LEMD"},
            "rwydep":    {"width": 70,  "value": "24L"},
            "sid":       {"width": 100,  "value": ""},
            "cfl":       {"width": 100,  "value": "050"},
            "cssr":      {"width": 80,  "value": ""},
            "qnh":       {"width": 80,  "value": ""},
            "rules":     {"width": 40,  "value": "I"},
            "resto":     {"width": "flex", "value": ""},
        }
        
        # Redefinir layout para CLR con dep_local
        self.layouts = {
            ("CLR", "dep_local"): ["act", "callsign", "autorizacion", "type", "park", "eobt", "ctot", "hopm",
                                   "dest", "rwydep", "sid", "cfl", "cssr", "rules", "dtot", "qnh", "resto"],
        }
        
        # Títulos personalizados para las columnas (modifica aquí)
        self.column_titles = {
            "act": "ACC",
            "callsign": "INDICATIV",
            "autorizacion": "A",
            "type": "N/TIPO",
            "park": "STND",
            "wake": "E",
            "eobt": "EOBT",
            "tobt": "TOBT",
            "ctot": "CTOT",
            "tsat": "TSAT",
            "hopm": "HOPM",
            "dtot": "DTOT",
            "tsac": "TSAC",
            "asrt": "ASRT",
            "dest": "DEST",
            "rwydep": "PD",
            "sid": "SID",
            "cssr": "CSSR",
            "cfl": "CFL",
            "qnh": "QNH",
            "rules": "R",
            "resto": "",
        }
        
        # Colores de resalte genéricos para varios campos
        self.light_green = "#90EE90"   # Verde claro
        self.green = "#009802"           # Verde
        self.yellow = "yellow"         # Amarillo

        # Identidad visual propia.
        self.root.title("Previstos Despegue")
        self.root.geometry("1200x450")  # anchura y altura por defecto

        # Reemplazamos la barra superior con botones por una con label
        if hasattr(self, 'topbar'):
            self.topbar.pack_forget()
            self.topbar.destroy()

        # Creamos nueva barra con label
        self.topbar = tk.Frame(self.root, bg="#555555", height=30)
        self.topbar.pack(side=tk.TOP, fill=tk.X)

        label_prevdesp = tk.Label(
            self.topbar,
            text="PREVISTOS DESPEGUE",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 8, 'bold'),
            justify=tk.LEFT
        )
        label_prevdesp.pack(side=tk.LEFT, padx=10, pady=5)

        # Label contador de fichas
        self.label_contador = tk.Label(
            self.topbar,
            text="0",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 7, 'bold'),
            width=8,
            relief="raised",
            bd=2
        )
        self.label_contador.pack(side=tk.RIGHT, padx=1, pady=3)

        # Botón Warning en la derecha
        self.btn_warning = tk.Button(
            self.topbar,
            text="W",
            bg="#555555",
            fg="white",
            width=8,
            font=('Lucida Sans Typewriter', 7, 'bold'),
            relief="raised",
            bd=2,
            command=self.warning_toggle
        )
        self.btn_warning.pack(side=tk.RIGHT, padx=1, pady=3)

        # Minibutton SOL S/U en la derecha
        self.sol_su_active = False
        self.btn_sol_su = tk.Button(
            self.topbar,
            text="SOL S/U",
            bg="#555555",
            fg="white",
            font=('Lucida Sans Typewriter', 7, 'bold'),
            width=6,
            relief="raised",
            bd=2,
            padx=5,
            command=self._toggle_sol_su
        )
        self.btn_sol_su.pack(side=tk.RIGHT, padx=5, pady=5)

        # Re-empaquetar el canvas debajo del topbar
        self.canvas.pack_forget()
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind para botón central (selección de ficha)
        self.canvas.bind("<Button-2>", self.on_middle_click)

        # Eliminar márgenes laterales de coqueo
        self.margin = 0

        # Reconfiguracion estructural: una sola zona.
        self._configure_single_zone()
        
        # Timer para recalcular resaltes de EOBT cada minuto
        self._schedule_eobt_refresh()

    def _configure_single_zone(self):
        self.zonas_count = 1
        self.last_zona_idx = 0

        self.zonas = [{
            "colors": [self.color_dep_asum],
            "fichas": [],
            "scroll_offset": 0
        }]

        self.zona_heights = [1.0]
        self.update_zona_heights()
        self.draw_zonas()

    def _toggle_sol_su(self):
        """Toggle del botón SOL S/U: cambia color entre amarillo (activado) y fondo (desactivado)"""
        self.sol_su_active = not self.sol_su_active
        if self.sol_su_active:
            self.btn_sol_su.config(bg="yellow", fg="black")
        else:
            self.btn_sol_su.config(bg="#555555", fg="white")

    def get_line_at(self, x, y):
        """
        Devuelve (zona_idx, ficha_idx) de la ficha bajo la coordenada y.
        Adaptado para PrevDesp que dibuja fichas de arriba a abajo.
        Ahora tiene en cuenta el desplazamiento de la fila de encabezados.
        """
        canvas_height = self.canvas.winfo_height()
        ficha_h = self.ficha_height
        sep_h = self.ficha_sep
        line_height = ficha_h + sep_h
        
        # Desplazamiento por fila de encabezados
        header_height = ficha_h + sep_h
        y_start_fichas = header_height
        
        for i, zona in enumerate(self.zonas):
            zona_height = self.zona_heights[i] * canvas_height
            y_end = y_start_fichas + zona_height
            
            # Si y está dentro de esta zona (después de los encabezados)
            if y_start_fichas <= y < y_end:
                total = len(zona["fichas"])
                visible = int(zona_height / line_height)
                offset = zona.get("scroll_offset", 0)
                
                # Calcular el line_idx desde arriba de las fichas
                relative_y = y - y_start_fichas
                line_idx = int(relative_y / line_height)
                
                # Verificar que está dentro del rango visible y total
                if 0 <= line_idx < visible:
                    actual_idx = offset + line_idx
                    if actual_idx < total:
                        return (i, actual_idx)
            
            y_start_fichas = y_end
        
        return None

    def draw_zonas(self):
        """Override para dibujar fichas sin encabezados"""
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
        self._field_positions = {}
        self.scrollbar_positions = []

        y_start = 0
        ficha_h = self.ficha_height
        sep_h = self.ficha_sep
        line_height = ficha_h + sep_h
        
        # Dibujar fila de encabezados
        y_start_fichas = y_start
        header_top = y_start_fichas
        header_bottom = header_top + ficha_h
        self._draw_headers(header_top, header_bottom, margin, usable_width)
        y_start_fichas = header_bottom + sep_h
        
        for i, zona in enumerate(self.zonas):
            zona_height = self.zona_heights[i] * canvas_height
            y_end = y_start_fichas + zona_height

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

                # Fichas desde la parte ARRIBA hacia abajo
                line_top = y_start_fichas + line_idx * line_height
                line_bottom = line_top + ficha_h

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

                    field_bg_overrides = ficha.get("field_bg", {})
                    bg_color = field_bg_overrides.get(name, self.ficha_bg)

                    text_color = field_colors.get(name, base_color)

                    field_tag = "field_%d_%d_%d" % (i, actual_idx, field_idx)
                    rect_tag = field_tag + "_rect"
                    content_tag = field_tag + "_content"

                    self._field_positions[(i, actual_idx, name)] = (x_start, line_top, x_end, line_bottom)

                    self.canvas.create_rectangle(
                        x_start, line_top, x_end, line_bottom,
                        fill=bg_color, outline="", tags=field_tag
                    )

                    if not self._is_flex(name):
                        if name == "autorizacion":
                            # Dibuja la imagen con la tag de contenido
                            self._draw_autorizacion(x_start, line_top, x_end, line_bottom, ficha,
                                                    tags=(field_tag, content_tag))
                        else:
                            valor_campo = ficha.get("values", {}).get(name, self._field_value(name))
                            # CENTRADO VERTICAL, ALINEADO A LA IZQUIERDA
                            y_text = (line_top + line_bottom) / 2
                            self.canvas.create_text(
                                x_start + 5,
                                y_text,
                                text=valor_campo,
                                fill=text_color,
                                font=self.font_style,
                                anchor="w",
                                tags=(field_tag, content_tag)
                            )

                    # Bind para click en autorizacion, callsign o act
                    if name == "autorizacion":
                        self.canvas.tag_bind(
                            field_tag, "<Button-1>",
                            (lambda z=i, f=actual_idx:
                             (lambda e: self._on_autorizacion_click(z, f)))()
                        )
                        self.canvas.tag_bind(
                            field_tag, "<Button-3>",
                            (lambda z=i, f=actual_idx:
                             (lambda e: self._on_autorizacion_right_click(z, f)))()
                        )
                    elif name == "callsign":
                        self.canvas.tag_bind(
                            field_tag, "<Button-1>",
                            (lambda z=i, f=actual_idx:
                             (lambda e: self._on_callsign_click(z, f)))()
                        )
                    elif name == "act":
                        self.canvas.tag_bind(
                            field_tag, "<Button-1>",
                            (lambda z=i, f=actual_idx:
                             (lambda e: self._on_act_click(z, f)))()
                        )
                        self.canvas.tag_bind(
                            field_tag, "<Button-3>",
                            (lambda z=i, f=actual_idx, e_x=None, e_y=None:
                             (lambda e: self._on_act_right_click(z, f, e)))()
                        )

                    x_cursor += w

                # Dibujar recuadre de selección si la ficha está seleccionada
                if self.selected_line == (i, actual_idx):
                    self.canvas.create_rectangle(
                        margin, line_top, margin + usable_width, line_bottom,
                        outline="white", width=2
                    )
            
            # Dibujar scrollbar para esta zona si hay más fichas de las visibles
            has_scroll = total > visible
            thumb_y0 = thumb_y1 = 0
            if has_scroll:
                scroll_x = canvas_width - 15
                scroll_y0 = y_start_fichas + 10
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
            
            self.scrollbar_positions.append((y_start_fichas, y_end, has_scroll, thumb_y0, thumb_y1))
            y_start_fichas = y_end

    def _draw_autorizacion(self, x0, y0, x1, y1, ficha, tags):
        """Dibuja la imagen de estado ATC (autorizacion) en el campo."""
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

        # Centro del campo
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0

        if img:
            self.canvas.create_image(cx, cy, image=img, tags=tags)
        else:
            # Fallback: un texto placeholder como contenido
            self.canvas.create_text(cx, cy, text="?", fill="#ccc", font=self.font_style, anchor="center", tags=tags)

    def _draw_headers(self, header_top, header_bottom, margin, usable_width):
        """Dibuja la fila de encabezados numerados con fondo negro."""
        canvas_width = self.canvas.winfo_width()
        
        # Obtener nombres de campos del layout
        nombres_campos = self._resolve_field_names("CLR", 0, True, False)
        
        # Calcular ancho de campos fijos y flexibles
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
        
        for col_idx, name in enumerate(nombres_campos):
            w = (flex_each if self._is_flex(name) else self._field_width(name))
            x_start = x_cursor
            x_end = x_cursor + w
            
            if x_start >= x_max:
                break
            if x_end > x_max:
                x_end = x_max
            
            # Dibujar fondo negro del encabezado
            header_tag = "header_%d" % col_idx
            self.canvas.create_rectangle(
                x_start, header_top, x_end, header_bottom,
                fill="black", outline="", tags=header_tag
            )
            
            # Dibujar número centrado
            y_text = (header_top + header_bottom) / 2
            # Obtener título personalizado o usar el nombre en mayúsculas por defecto
            title = self.column_titles.get(name, name.upper())
            self.canvas.create_text(
                x_start + 5,
                y_text,
                text=title,
                fill="white",
                font=self.font_style,
                anchor="w",
                tags=header_tag
            )
            
            # Bind para click en encabezado (ordenar)
            self.canvas.tag_bind(
                header_tag, "<Button-1>",
                (lambda col=col_idx, fname=name:
                 (lambda e: self._sort_by_column(col, fname)))()
            )
            
            x_cursor += w

    def _sort_by_column(self, col_idx, field_name):
        """Ordena las fichas alfabéticamente por la columna especificada."""
        if not self.zonas or not self.zonas[0]["fichas"]:
            return
        
        zona_idx = 0
        fichas = self.zonas[zona_idx]["fichas"]
        
        # Ordenar fichas por el valor del campo
        def get_value(ficha):
            val = ficha.get("values", {}).get(field_name, "")
            return str(val).lower() if val else ""
        
        fichas.sort(key=get_value)
        self.draw_zonas()

    def _on_autorizacion_click(self, zona_idx, ficha_idx):
        """
        Click en el campo 'autorizacion':
          - Detecta si el vuelo es salida local.
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
        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        # --- 1) ¿Salida local? ---
        sector_list = (self.radisplay.sector or "").split(",")
        local_dep = False
        local_ads = getattr(self.fir, "local_ads", {}) or {}
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

        # --- 3) Refrescar imagen del campo 'autorizacion' ---
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

    def _on_autorizacion_right_click(self, zona_idx, ficha_idx):
        """
        Click derecho en el campo 'autorizacion':
          - Cambia la imagen a ATC_REQUEST.gif
          - Notifica al GTA
          - Refresca la imagen del campo
        """
        
        # --- 0) Ficha y vuelo ---
        zona = self.zonas[zona_idx]
        ficha = zona["fichas"][ficha_idx]
        callsign = ficha.get("values", {}).get("callsign", "")
        if not callsign:
            return

        # Buscar el vuelo real
        f = self._find_flight_by_callsign(callsign)
        if not f:
            return

        # --- 1) Cambiar estado a ATC_REQUEST ---
        if hasattr(Aircraft, "ATC_REQUEST"):
            f.ATC_status = Aircraft.ATC_REQUEST

        # --- 2) Refrescar imagen del campo 'autorizacion' ---
        atc_status = getattr(f, "ATC_status", None) or "ATC_MISSING"
        img_file_str = "img/" + atc_status
        img_abs_path = os.path.join(conf.common_dir, img_file_str)

        ficha.setdefault("images", {})["autorizacion"] = img_abs_path

        # Limpiar caché de esa imagen si ha cambiado
        if hasattr(self, "_img_cache"):
            old = self._img_cache.get(img_abs_path)
            if old is None:
                try:
                    self._img_cache[img_abs_path] = tk.PhotoImage(file=img_abs_path)
                except Exception:
                    self._img_cache[img_abs_path] = None

        # --- 3) Redibujar ---
        self.draw_zonas()

    def _on_callsign_click(self, zona_idx, ficha_idx):
        """
        Click izquierdo en el campo 'callsign':
        Funcionalidad removida - el click no realiza ninguna acción.
        """
        return

    def insert_fs(self, f, old_zona_idx=None, x_offset=None):
        """
        Inserta/actualiza una ficha, pero SOLO si es un vuelo de salida local (local_dep=True).
        Filtra según la configuración de PrevDesp.
        """
        import os
        
        cs = getattr(f, "callsign", None)
        if not cs:
            return
        
        # 1) Determinar si es local_dep o local_des
        local_dep = False
        local_des = False
        sector_list = (self.radisplay.sector or "").split(",")
        first_sector = sector_list[0] if sector_list else ""
        ads_set = (self.fir.local_ads.get(first_sector, set())
                   if getattr(self.fir, "local_ads", None) else set())
        if getattr(f, "adep", None) in ads_set:
            local_dep = True
        elif getattr(f, "ades", None) in ads_set:
            local_des = True
        
        # 2) FILTRO: PrevDesp solo muestra salidas locales
        if not local_dep:
            # Si la ficha existe pero ya no es local_dep, eliminarla
            self._delete_ficha_by_callsign(cs, refresh=False)
            return
        
        # 3) Zona destino (PrevDesp solo tiene 1 zona)
        zona_idx = 0
        
        # 4) Obtener valores de campos
        def S(x):
            return "" if x is None else str(x)
        
        act_txt, act_color = self._act_text_color(f)
        cs_txt, cs_color = self._callsign_text_color(f, zona_idx, warning=bool(getattr(f, "OSF_warning", False)))
        wake_color = self._wake_text_color(f)
        
        # Obtener estado ATC para imagen de autorización
        atc_status = getattr(f, "ATC_status", None) or "ATC_MISSING"
        img_file_str = "img/" + atc_status
        img_abs_path = os.path.join(conf.common_dir, img_file_str)

        # cfl: nivel de vuelo autorizado (cfl_c almacenado en FL, e.g. 60.0 = FL060)
        cfl_val = getattr(f, "cfl_c", None)
        cfl_txt = "%03d" % int(round(cfl_val)) if cfl_val is not None else ""

        # QNH: propiedad global de la atmósfera en GTA, accesible via radisplay.giw.qnh
        # Solo visible una vez anotada la autorización (BI sobre 'autorizacion')
        qnh_txt = ""
        if atc_status == Aircraft.ATC_OK:
            try:
                qnh_float = self.radisplay.giw.qnh
                qnh_txt = "Q%04d" % int(round(qnh_float))
            except Exception:
                qnh_txt = ""

        # Construir diccionario de valores con los campos específicos de PrevDesp
        values = {
            "act": act_txt,
            "callsign": cs_txt,
            "autorizacion": "",  # Campo de imagen, no valor de texto
            "type": S(getattr(f, "type", None)),
            "wake": S(getattr(f, "wake", None)),
            "park": S(getattr(f, "park", None)),
            "eobt": ("%02d%02d" % (f.eobt.hour, f.eobt.minute) if getattr(f, "eobt", None) else ""),
            "tobt": ("%02d%02d" % (f.tobt.hour, f.tobt.minute) if getattr(f, "tobt", None) else ""),
            "ctot": ("%02d%02d" % (f.ctot.hour, f.ctot.minute) if getattr(f, "ctot", None) else ""),
            "hopm": ("%02d%02d" % (f.hopm.hour, f.hopm.minute) if getattr(f, "hopm", None) else ""),
            "dtot": ("%02d%02d" % (f.dtot.hour, f.dtot.minute) if getattr(f, "dtot", None) else ""),
            "tsat": ("%02d%02d" % (f.tsat.hour, f.tsat.minute) if getattr(f, "tsat", None) else ""),
            "tsac": ("%02d%02d" % (f.tsac.hour, f.tsac.minute) if getattr(f, "tsac", None) else ""),
            "asrt": ("%02d%02d" % (f.asrt.hour, f.asrt.minute) if getattr(f, "asrt", None) else ""),
            "dest": S(getattr(f, "ades", None)),
            "rwydep": S(getattr(f, "deprwy", None)),
            "sid": S(getattr(f, "stand_sid_atc", "")),
            "cfl": cfl_txt,
            "cssr": S(getattr(f, "squawk", "")),
            "qnh": qnh_txt,
            "rules": S(getattr(f, "fr", ""))[:1] if getattr(f, "fr", None) else "",
            "resto": "",
        }
        
        # Colores de campos
        field_colors = {
            "act": act_color,
            "callsign": cs_color,
        }
        
        # Resaltes para EOBT según la diferencia con HACT
        # HACT: hora actual de simulación (self.radisplay.t)
        try:
            t_sim = getattr(self.radisplay, "t", None)
            if t_sim is None:
                pass  # No hay tiempo, no aplicar resalte
            else:
                eobt = getattr(f, "eobt", None)
                if eobt is not None:
                    # Convertir a minutos para comparación: horas*60 + minutos
                    try:
                        t_sim_minutes = t_sim.hour * 60 + t_sim.minute
                        eobt_minutes = eobt.hour * 60 + eobt.minute
                    except AttributeError:
                        # Si no tienen atributos hour/minute, saltar resalte
                        pass
                    else:
                        diff_minutes = eobt_minutes - t_sim_minutes
                        
                        # Resalte 1 (verde claro): HACT < EOBT - 15min
                        if diff_minutes > 15:
                            field_colors["eobt"] = self.light_green
                        # Resalte 2 (verde): EOBT - 15min <= HACT <= EOBT + 15min
                        elif -15 <= diff_minutes <= 15:
                            field_colors["eobt"] = self.green
                        # Resalte 3 (amarillo): HACT > EOBT + 15min
                        elif diff_minutes < -15:
                            field_colors["eobt"] = self.yellow
        except Exception:
            # Si falla cualquier cosa, continúa sin resaltes
            pass
        
        # Resaltes para TSAT según la diferencia con HACT
        # HACT: hora actual de simulación (self.radisplay.t)
        try:
            t_sim = getattr(self.radisplay, "t", None)
            if t_sim is None:
                pass  # No hay tiempo, no aplicar resalte
            else:
                tsat = getattr(f, "tsat", None)
                if tsat is not None:
                    # Convertir a minutos para comparación: horas*60 + minutos
                    try:
                        t_sim_minutes = t_sim.hour * 60 + t_sim.minute
                        tsat_minutes = tsat.hour * 60 + tsat.minute
                    except AttributeError:
                        # Si no tienen atributos hour/minute, saltar resalte
                        pass
                    else:
                        diff_minutes = tsat_minutes - t_sim_minutes
                        
                        # Resalte 1 (verde claro): HACT < TSAT - 5min
                        if diff_minutes > 5:
                            field_colors["tsat"] = self.light_green
                        # Resalte 2 (verde): TSAT - 5min <= HACT <= TSAT + 5min
                        elif -5 <= diff_minutes <= 5:
                            field_colors["tsat"] = self.green
                        # Resalte 3 (amarillo): HACT > TSAT + 5min
                        elif diff_minutes < -5:
                            field_colors["tsat"] = self.yellow
        except Exception:
            # Si falla cualquier cosa, continúa sin resaltes
            pass
        
        # Parpadeo de autorización si está faltando
        if atc_status == Aircraft.ATC_MISSING:
            self.start_blink_by_callsign(cs_txt, "autorizacion", period_ms=400)
        else:
            self.stop_blink_by_callsign(cs_txt, "autorizacion")
        
        # Campos a mostrar (definidos en layouts)
        field_names = self._resolve_field_names(self.bahia_type, zona_idx, True, False)
        
        # Construir ficha
        saved_x_offset = 0
        if x_offset is not None:
            try:
                saved_x_offset = int(x_offset)
            except Exception:
                saved_x_offset = 0
        else:
            prev = self._find_ficha_by_callsign(cs)
            if prev:
                try:
                    saved_x_offset = int(prev[2].get("x_offset", 0))
                except Exception:
                    saved_x_offset = 0
        
        ficha = {
            "fields": field_names,
            "values": values,
            "local_dep": local_dep,
            "local_des": local_des,
            "field_colors": field_colors,
            "images": {"autorizacion": img_abs_path},
            "x_offset": saved_x_offset,
        }
        
        # 5) Buscar si la ficha ya existe y actualizarla, o crear nueva
        existing_found = None
        for idx, existing_ficha in enumerate(self.zonas[zona_idx]["fichas"]):
            existing_cs = existing_ficha.get("values", {}).get("callsign")
            if existing_cs == cs_txt:
                existing_found = idx
                break
        
        if existing_found is not None:
            # Actualizar ficha existente preservando x_offset
            existing_ficha = self.zonas[zona_idx]["fichas"][existing_found]
            existing_x_offset = existing_ficha.get("x_offset", saved_x_offset)
            existing_ficha.update(ficha)
            existing_ficha["x_offset"] = existing_x_offset
        else:
            # Nueva ficha
            self.zonas[zona_idx]["fichas"].append(ficha)
        
        # Marcar como procesada
        self.fs_processed.add(cs)
        
        # Redibujar
        self.draw_zonas()

    def update(self):
        """
        Actualiza las fichas desde radisplay.flights.
        - Elimina fichas de vuelos que ya no existen
        - Inserta nuevas fichas mediante insert_fs() (que filtra por local_dep)
        """
        
        # Obtener lista actual de vuelos
        flights = list(getattr(self.radisplay, "flights", []) or [])
        t = getattr(self.radisplay, "t", None)
        
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
                self.fs_deleted.add(cs)
                self.fs_last_zone_entry.pop(cs, None)
                self.fs_airborne_t.pop(cs, None)
        
        if to_remove:
            self.draw_zonas()
        
        # ===============================
        # 1.5) Borrar fichas de vuelos que han alcanzado DEPARTING
        # ===============================
        fichas_to_remove = []
        for ficha in self.zonas[0]["fichas"]:
            cs = ficha.get("values", {}).get("callsign", "")
            if cs:
                f = self._find_flight_by_callsign(cs)
                if f:
                    # Si el vuelo ha alcanzado DEPARTING o más allá, eliminarlo
                    if getattr(f, "OSF_pof", None) in [Aircraft.PUSH, Aircraft.TAXIING_OUT, Aircraft.LININGUP,Aircraft.DEPARTING, Aircraft.AIRBORNE]:
                        fichas_to_remove.append(cs)
        
        for cs in fichas_to_remove:
            borrado = self._delete_ficha_by_callsign(cs, refresh=False)
            if borrado:
                self.fs_deleted.add(cs)
                self.fs_processed.add(cs)
                self.fs_last_zone_entry.pop(cs, None)
                self.fs_airborne_t.pop(cs, None)
        
        if fichas_to_remove:
            self.draw_zonas()
        
        # ===============================
        # 2) Insertar nuevas fichas para vuelos que aún no tenga
        # ===============================
        for f in flights:
            cs = getattr(f, "callsign", None)
            if not cs:
                continue
            
            # Si ya fue procesado o está marcado como borrado, saltamos
            if cs in self.fs_processed or cs in self.fs_deleted:
                continue
            
            # Ignorar vehículos
            if getattr(f, "fr", None) == "VEH":
                continue
            
            # Si está TERMINATED, no lo procesamos
            if getattr(f, "OSF_pof", None) == getattr(Aircraft, "TERMINATED", None):
                if cs not in self.fs_deleted:
                    borrado = self._delete_ficha_by_callsign(cs, refresh=False)
                    if borrado:
                        self.fs_deleted.add(cs)
                        self.fs_processed.add(cs)
                        self.fs_last_zone_entry.pop(cs, None)
                        self.fs_airborne_t.pop(cs, None)
                continue

            # Filtro LLZ si existe
            fs_print_t = getattr(f, "fs_print_t", {}) or {}
            if t is not None:
                if ("_LLZ" in fs_print_t) and not (fs_print_t["_LLZ"] < t):
                    continue

            # insert_fs() se encargará de filtrar por local_dep
            self.insert_fs(f)
        
        # ===============================
        # 3) Actualizar contador de fichas en el label
        # ===============================
        total_fichas = len(self.zonas[0]["fichas"]) if self.zonas else 0
        self.label_contador.config(text=str(total_fichas))

    def _schedule_eobt_refresh(self):
        """Programa el recalculado de resaltes de EOBT cada 60 segundos"""
        try:
            if not self.canvas.winfo_exists():
                return
            self._refresh_eobt_colors()
        except Exception:
            pass

    def _refresh_eobt_colors(self):
        """Recalcula colores de EOBT y TSAT para todas las fichas basado en tiempo de simulación"""
        try:
            if not self.canvas.winfo_exists():
                return
            
            t_sim = getattr(self.radisplay, "t", None)
            if t_sim is None:
                # Reprogramar el timer sin hacer nada
                self.canvas.after(60000, self._refresh_eobt_colors)
                return
            
            t_sim_minutes = t_sim.hour * 60 + t_sim.minute
            needs_redraw = False
            
            # Recorrer todas las fichas y actualizar colores de EOBT y TSAT
            for ficha in self.zonas[0]["fichas"]:
                cs = ficha.get("values", {}).get("callsign", "")
                if not cs:
                    continue
                
                f = self._find_flight_by_callsign(cs)
                if not f:
                    continue
                
                field_colors = ficha.setdefault("field_colors", {})
                
                # --- Resaltes EOBT (threshold ±15min) ---
                eobt = getattr(f, "eobt", None)
                if eobt is not None:
                    try:
                        eobt_minutes = eobt.hour * 60 + eobt.minute
                        diff_minutes = eobt_minutes - t_sim_minutes
                        
                        new_color = None
                        if diff_minutes > 15:
                            new_color = self.light_green
                        elif -15 <= diff_minutes <= 15:
                            new_color = self.green
                        elif diff_minutes < -15:
                            new_color = self.yellow
                        
                        # Si el color cambió, marcar para redibujar
                        if new_color is not None and field_colors.get("eobt") != new_color:
                            field_colors["eobt"] = new_color
                            needs_redraw = True
                    except Exception:
                        pass
                
                # --- Resaltes TSAT (threshold ±5min) ---
                tsat = getattr(f, "tsat", None)
                if tsat is not None:
                    try:
                        tsat_minutes = tsat.hour * 60 + tsat.minute
                        diff_minutes = tsat_minutes - t_sim_minutes
                        
                        new_color = None
                        if diff_minutes > 5:
                            new_color = self.light_green
                        elif -5 <= diff_minutes <= 5:
                            new_color = self.green
                        elif diff_minutes < -5:
                            new_color = self.yellow
                        
                        # Si el color cambió, marcar para redibujar
                        if new_color is not None and field_colors.get("tsat") != new_color:
                            field_colors["tsat"] = new_color
                            needs_redraw = True
                    except Exception:
                        pass
            
            # Redibujar si algún color cambió
            if needs_redraw:
                self.draw_zonas()
            
            # Reprogramar el timer
            self.canvas.after(60000, self._refresh_eobt_colors)
        except Exception:
            pass


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

    def on_middle_click(self, event):
        """
        Selecciona/deselecciona una ficha con el botón central del ratón.
        """
        # Saber qué ficha está bajo el puntero
        pos = self.get_line_at(event.x, event.y)

        if pos is None:
            # Nada bajo el clic -> no cambiar la selección
            return

        zi, fi = pos
        zona_idx, ficha_idx = pos
        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        cs = ficha.get("values", {}).get("callsign", "")
        f = self._find_flight_by_callsign(cs)
        if f:
            try:
                self.radisplay.toggle_select(f, True)
            except Exception as e:
                print("Error en toggle_select:", e)

        # Toggle de selección:
        if not self.selected_line:
            # No había ninguna seleccionada -> selecciona esta
            self.selected_line = (zi, fi)
        else:
            if self.selected_line == (zi, fi):
                # Clic sobre la misma -> deseleccionar
                self.selected_line = None
            else:
                # Había otra seleccionada -> cambiar selección a esta
                self.selected_line = (zi, fi)

        self.draw_zonas()

    def _on_act_click(self, zona_idx, ficha_idx):
        """
        Avanza el siguiente estado de departure (POF) en la secuencia de departures.
        Se detiene en TAXIING_OUT: no avanza más allá de ese estado.
        """
        
        if not (0 <= zona_idx < len(self.zonas)) or not (0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"])):
            return

        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        cs = ficha.get("values", {}).get("callsign", "")
        if not cs:
            return

        f = self._find_flight_by_callsign(cs)
        if not f:
            return

        current_pof = getattr(f, "OSF_pof", None)
        
        # BLOQUEO: No permitir cambio de estado con click izquierdo si está en REAREQ
        if current_pof == Aircraft.REAREQ:
            return
        
        new_pof = current_pof
        
        # Si está en STARTREQ, el siguiente es STARTING
        if current_pof == Aircraft.STARTREQ:
            new_pof = Aircraft.STARTING
        else:
            # Obtener la secuencia de departures
            if not hasattr(Aircraft, "OSF_DEPSEQ"):
                return

            seq = list(Aircraft.OSF_DEPSEQ)

            # Insertar paso intermedio "ATC" entre PREPARING y STARTING.
            # Solo para PrevDesp: OSF_DEPSEQ no se toca porque OSF.py lo comparte
            # y no debe mostrar este paso.
            if hasattr(Aircraft, "AUTHORIZATION") and Aircraft.PREPARING in seq:
                prep_idx = seq.index(Aircraft.PREPARING)
                seq.insert(prep_idx + 1, Aircraft.AUTHORIZATION)

            # Encontrar índice actual en la secuencia
            try:
                current_idx = seq.index(current_pof)
            except ValueError:
                # El estado actual no está en la secuencia, ir al primero
                current_idx = -1
            
            # Para PrevDesp, el límite máximo es STARTING (no TAXIING_OUT)
            if not hasattr(Aircraft, "STARTING"):
                return
            
            starting_idx = None
            try:
                starting_idx = seq.index(Aircraft.STARTING)
            except ValueError:
                return
            
            # Calcular el siguiente estado
            next_idx = current_idx + 1
            
            # No avanzar más allá de STARTING (límite máximo para PrevDesp)
            if next_idx > starting_idx:
                return
            
            if next_idx >= len(seq):
                return
            
            new_pof = seq[next_idx]

        # Asumir el vuelo si está en PREPARING
        if current_pof == Aircraft.PREPARING:
            sector = self.radisplay.sector or ""
            if f.atc_sector is None or sector.find(f.atc_sector) < 0 or getattr(f, 'release_atc_pos', False):
                try:
                    self.radisplay.sendMessage({"message": "assume", "sector": sector, "cs": cs, "assumed": True})
                except Exception:
                    pass
                f.atc_sector = sector

        # Actualizar el vuelo y notificar al GTA
        f.OSF_pof = new_pof
        try:
            self.radisplay.sendMessage({
                "message": "set_osf_pof",
                "cs": f.callsign,
                "osf_pof": new_pof
            })
        except Exception:
            pass

        # Redibujar para mostrar el nuevo estado
        self.insert_fs(f)


    def _on_act_right_click(self, zona_idx, ficha_idx, event):
        """
        Click derecho en el campo act: muestra popup con opciones.
        """
        if not (0 <= zona_idx < len(self.zonas)) or not (0 <= ficha_idx < len(self.zonas[zona_idx]["fichas"])):
            return

        ficha = self.zonas[zona_idx]["fichas"][ficha_idx]
        cs = ficha.get("values", {}).get("callsign", "")
        if not cs:
            return

        # Guardar el contexto del popup (zona y ficha índices)
        self._act_popup_ctx = (zona_idx, ficha_idx)
        
        # Mostrar popup en la posición del evento
        self._show_act_popup(at_x=event.x_root, at_y=event.y_root)

    def _show_act_popup(self, at_x=None, at_y=None):
        """
        Popup 'ACCIONES' con tres opciones para PrevDesp.
        Formato similar al de OSF.
        """
        # Cerrar si ya hay uno
        if hasattr(self, "_act_popup") and self._act_popup and self._act_popup.winfo_exists():
            try:
                self._act_popup.destroy()
            except:
                pass

        # Crear ventana Toplevel
        top = tk.Toplevel(self.root)
        self._act_popup = top
        try:
            top.wm_overrideredirect(1)
            top.wm_attributes("-topmost", 1)
        except:
            pass

        # Tamaño del popup
        popup_w, popup_h = 300, 170
        if at_x is None or at_y is None:
            at_x = self.root.winfo_rootx() + 50
            at_y = self.root.winfo_rooty() + 50
        
        # Ajustar si se sale de pantalla
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            if at_x + popup_w > screen_w:
                at_x = screen_w - popup_w - 10
            if at_y + popup_h > screen_h:
                at_y = screen_h - popup_h - 10
        except:
            pass
        
        top.geometry("%dx%d+%d+%d" % (popup_w, popup_h, int(at_x), int(at_y)))

        # Colores (usar los mismos que OSF si existen)
        bg_panel = getattr(self, "body_popup", "#333333")
        bg_hdr = getattr(self, "cabecera_popup", "#222222")
        fg_txt = "white"
        btn_bg = getattr(self, "fondo_btn_popup", "#555555")

        # Contenedor principal
        container = tk.Frame(top, bg=bg_panel, bd=1, relief="solid")
        container.pack(fill="both", expand=True)

        # Cabecera
        hdr = tk.Label(container, text="ACCIONES", bg=bg_hdr, fg=fg_txt,
                       font=('Lucida Sans Typewriter', 9, 'bold'), pady=4)
        hdr.pack(side="top", fill="x")

        # Body con las opciones
        body = tk.Frame(container, bg=bg_panel)
        body.pack(side="top", fill="both", expand=True, padx=4, pady=4)

        # Helper para añadir filas con botón y texto
        def add_row(parent, r, text, on_click):
            btn = tk.Button(
                parent,
                width=1, height=1,
                bg=btn_bg,
                fg="white",
                relief="raised",
                bd=1,
                padx=2, pady=0,
                font=("Lucida Sans Typewriter", 7, 'bold'),
                command=on_click
            )
            btn.grid(row=r, column=0, sticky="w", padx=2, pady=2, ipadx=2, ipady=0)

            lbl = tk.Label(
                parent,
                text=text,
                bg=bg_panel,
                fg=fg_txt,
                font=('Lucida Sans Typewriter', 8),
                anchor="w",
                justify=tk.LEFT,
                # wraplength=200
            )
            lbl.grid(row=r, column=1, sticky="w", padx=6, pady=2)
            lbl.config(cursor="hand2")
            lbl.bind("<Button-1>", lambda e: on_click())

            return btn, lbl

        # Las opciones
        add_row(body, 0, "SOLICITUD DE PUESTA EN MARCHA", 
                lambda: self._on_popup_startup_request())
        add_row(body, 1, "SOLICITUD REA", 
                lambda: self._on_popup_rea_request())
        add_row(body, 2, "AUTORIZACION S/U", 
                lambda: self._on_popup_authorization_su())
        add_row(body, 3, "OTROS", 
                lambda: self._on_popup_others())

        # Cerrar con ESC
        top.bind("<Escape>", lambda e: top.destroy())

        # Marcar popup como abierto
        self._popup_just_opened = True
        self.canvas.after(100, lambda: setattr(self, "_popup_just_opened", False))

    def _on_popup_startup_request(self):
        """Acción para 'SOLICITUD DE PUESTA EN MARCHA': cambia act a 'S/U' en amarillo"""
        
        if hasattr(self, "_act_popup") and self._act_popup:
            try:
                self._act_popup.destroy()
            except:
                pass
        
        # Obtener el vuelo desde el contexto del popup
        ctx = getattr(self, "_act_popup_ctx", None)
        if not ctx or not isinstance(ctx, tuple) or len(ctx) != 2:
            return
        
        try:
            zi, fi = ctx
            ficha = self.zonas[zi]["fichas"][fi]
            cs = ficha.get("values", {}).get("callsign", "")
            if not cs:
                return
            
            f = self._find_flight_by_callsign(cs)
            if not f:
                return
            
            # --- Asumir el vuelo si es necesario (igual que en _on_act_click) ---
            current_pof = getattr(f, "OSF_pof", None)
            if current_pof == Aircraft.PREPARING:
                sector = self.radisplay.sector or ""
                if f.atc_sector is None or sector.find(f.atc_sector) < 0 or getattr(f, 'release_atc_pos', False):
                    try:
                        self.radisplay.sendMessage({"message": "assume", "sector": sector, "cs": cs, "assumed": True})
                    except Exception:
                        pass
                    f.atc_sector = sector
            
            # Cambiar el estado a STARTREQ ("S/U" en amarillo)
            f.OSF_pof = Aircraft.STARTREQ
            
            # Notificar al GTA
            try:
                self.radisplay.sendMessage({
                    "message": "set_osf_pof",
                    "cs": f.callsign,
                    "osf_pof": Aircraft.STARTREQ
                })
            except Exception:
                pass
            
            # Actualizar la ficha y redibujar
            self.insert_fs(f)
        except Exception:
            pass

    def _on_popup_rea_request(self):
        """Acción para 'SOLICITUD REA': cambia act a 'REA' en amarillo"""
        
        if hasattr(self, "_act_popup") and self._act_popup:
            try:
                self._act_popup.destroy()
            except:
                pass
        
        # Obtener el vuelo desde el contexto del popup
        ctx = getattr(self, "_act_popup_ctx", None)
        if not ctx or not isinstance(ctx, tuple) or len(ctx) != 2:
            return
        
        try:
            zi, fi = ctx
            ficha = self.zonas[zi]["fichas"][fi]
            cs = ficha.get("values", {}).get("callsign", "")
            if not cs:
                return
            
            f = self._find_flight_by_callsign(cs)
            if not f:
                return
            
            # --- Asumir el vuelo si es necesario (igual que en _on_act_click) ---
            current_pof = getattr(f, "OSF_pof", None)
            if current_pof == Aircraft.PREPARING:
                sector = self.radisplay.sector or ""
                if f.atc_sector is None or sector.find(f.atc_sector) < 0 or getattr(f, 'release_atc_pos', False):
                    try:
                        self.radisplay.sendMessage({"message": "assume", "sector": sector, "cs": cs, "assumed": True})
                    except Exception:
                        pass
                    f.atc_sector = sector
            
            # Cambiar el estado a REAREQ ("REA" en amarillo)
            f.OSF_pof = Aircraft.REAREQ
            
            # Notificar al GTA
            try:
                self.radisplay.sendMessage({
                    "message": "set_osf_pof",
                    "cs": f.callsign,
                    "osf_pof": Aircraft.REAREQ
                })
            except Exception:
                pass
            
            # Actualizar la ficha y redibujar
            self.insert_fs(f)
        except Exception:
            pass

    def _on_popup_authorization_su(self):
        """Acción para 'AUTORIZACION S/U': cambia act a 'S/U' en amarillo (STARTING)"""
        
        if hasattr(self, "_act_popup") and self._act_popup:
            try:
                self._act_popup.destroy()
            except:
                pass
        
        # Obtener el vuelo desde el contexto del popup
        ctx = getattr(self, "_act_popup_ctx", None)
        if not ctx or not isinstance(ctx, tuple) or len(ctx) != 2:
            return
        
        try:
            zi, fi = ctx
            ficha = self.zonas[zi]["fichas"][fi]
            cs = ficha.get("values", {}).get("callsign", "")
            if not cs:
                return
            
            f = self._find_flight_by_callsign(cs)
            if not f:
                return
            
            # --- Asumir el vuelo si es necesario (igual que en _on_act_click) ---
            current_pof = getattr(f, "OSF_pof", None)
            if current_pof == Aircraft.PREPARING:
                sector = self.radisplay.sector or ""
                if f.atc_sector is None or sector.find(f.atc_sector) < 0 or getattr(f, 'release_atc_pos', False):
                    try:
                        self.radisplay.sendMessage({"message": "assume", "sector": sector, "cs": cs, "assumed": True})
                    except Exception:
                        pass
                    f.atc_sector = sector
            
            # Cambiar el estado a STARTING (autorización de puesta en marcha)
            f.OSF_pof = Aircraft.STARTING
            
            # Notificar al GTA
            try:
                self.radisplay.sendMessage({
                    "message": "set_osf_pof",
                    "cs": f.callsign,
                    "osf_pof": Aircraft.STARTING
                })
            except Exception:
                pass
            
            # Actualizar la ficha y redibujar
            self.insert_fs(f)
        except Exception:
            pass

    def _on_popup_others(self):
        """Acción para 'OTROS'"""
        if hasattr(self, "_act_popup") and self._act_popup:
            try:
                self._act_popup.destroy()
            except:
                pass
        
        # Implementar acción aquí
        print("OTROS")

