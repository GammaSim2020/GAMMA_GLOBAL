# !/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id:
#
# FIR.py 2324 2006-05-21 14:56:27Z toledo $
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
"""Information regarding a Flight Information Region"""


import os
import re


# Application imports
from MathUtil import *
import Route
import math
import random
from openpyxl import load_workbook
from ConfigParser import ConfigParser


# TODO the whole FIR object should be rewritten
# The file format should probably be switched to an XML file that more closely follows
# the internal structure of the information, and the FIR model should structure
# its information using more ideas from the Aeronautical Information Conceptual Model
# See http://www.eurocontrol.int/ais/aixm/aicm40/
# We might even want to consider whether we want to implement AIXM fully,
# although AIXM does not support ATC procedures, which we need to save

CALLSIGN_FILE = "Callsigns.txt"

# Normalizacion de nombres de sector:
_SECTOR_ALIASES = {'TWR': 'LCL',
                   'TORRE': 'LCL',
                   'GMC': 'GND',
                   'CLD': 'CLR',
                   'APROXIMACION': 'APP',
                   'TMA': 'APP',
                   'LEST TMA': 'APP',
                   'LEBB APP': 'APP'}
# Orden de aplicacion determinista: alias mas largos primero (p.ej. 'LEST TMA' antes que 'TMA').
_SECTOR_ALIAS_ORDER = sorted(_SECTOR_ALIASES.keys(), key=lambda a: (-len(a), a))

def _normalize_sector(name):
    """Reemplaza aliases (TWR/GMC/CLD) por nombres canónicos (LCL/GND/CLR) en un nombre de sector."""
    if name is None:
        return name
    s = str(name)
    # El orden de un dict en Python 2.7 no esta garantizado: antes 'LEST TMA' podia
    # quedar 'APP' o 'LEST APP' segun la iteracion. Se aplica en orden fijo y se
    # repite hasta que no haya cambios (p.ej. 'LEBB TMA' -> 'LEBB APP' -> 'APP').
    for _ in range(len(_SECTOR_ALIASES)):
        prev = s
        for alias in _SECTOR_ALIAS_ORDER:
            s = s.replace(alias, _SECTOR_ALIASES[alias])
        if s == prev:
            break
    return s


# ---------------------------------------------------------------------------
# Parametros de escenario (unificacion, Fase 3)
# Filas de la hoja 'Escenario': columna A = clave, columna B = valor.
# En las claves "por elemento" (_PARAM_MAP) la columna B es el aerodromo, sector
# o fijo y la columna C el valor. Si una clave no aparece en el Excel se usa el
# valor por defecto de _default_params(), que reproduce lo que el codigo hacia
# antes para ese escenario (los antiguos "if fir.name == 'LEMD'...").
# ---------------------------------------------------------------------------
_PARAM_BOOL = ('stca', 'separar_etiquetas', 'tabulares_aux', 'tabulares_aux_actualizar',
               'prevdesp_actualizar_ficha', 'sob_tabular', 'osf_lcl_por_sector',
               'pp_arrastre_pantalla', 'pp_asumir_arranca')
_PARAM_NUM = ('preimpresion_arr', 'preimpresion_dep', 'tfl_dep_local', 'tfl_defecto')
_PARAM_LIST = ('orientaciones', 'pp_asumir_rodaje_salvo', 'activacion_manual_ads', 'ads_sin_fichas_fijo')
_PARAM_STR = ('smr_ad',)
_PARAM_MAP = ('decel_aterrizaje', 'acel_despegue', 'min_alt_visible', 'tfl_fijo',
              'alias_ads', 'ficha_pistas_config')
# Parte 2: bahia de fichas (ATCBahia) de las posiciones no OSF
_PARAM_BOOL += ('ficha_freq_teclado',)
_PARAM_LIST += ('bahia_torre_ads', 'ficha_borde_salida_ads', 'uso_pistas')
_PARAM_MAP += ('mapas_pista_cerrada',)
_PARAM_BOOL += ('editor_mapas_reducidos',)
# Fase 4: alertas aeroportuarias INCW/CMAC/CATC (solo si el Excel trae las hojas)
_PARAM_BOOL += ('alertas',)
# Fase 4 bloque 2: planes de vehiculo (PVH) y cruce/entrada a pista (CRU/ENT/LIB)
_PARAM_BOOL += ('pvh',)
# Fase 4 bloque 3: refresco del radar de los moviles en vuelo (s); 0 = como el resto
_PARAM_NUM += ('refresco_aire',)
_PARAM_KEYS = _PARAM_BOOL + _PARAM_NUM + _PARAM_LIST + _PARAM_STR + _PARAM_MAP


def _default_params(name, aps, sectors, ads=None):
    """Valores por defecto: reproducen el comportamiento previo a la Fase 3.
    ads: aerodromos del escenario (fir.aerodromes, incluye los de escenarios anadidos con Add_fir)."""
    ap0 = aps[0] if aps else ''
    if ads is None:
        ads = aps
    p = {}
    p['stca'] = name not in ('LEMD', 'LEBL')
    p['separar_etiquetas'] = name not in ('LEMD', 'LEBL')
    p['tabulares_aux'] = ap0 not in ('LEMD', 'LEBL')
    p['tabulares_aux_actualizar'] = ap0 != 'LEMD'
    p['prevdesp_actualizar_ficha'] = ap0 not in ('LEMD', 'LEBL')
    p['sob_tabular'] = 'LEPA' in ads
    p['smr_ad'] = 'LEST' if 'LEST' in ads else ''
    p['osf_lcl_por_sector'] = (name == 'LEPA')
    p['pp_arrastre_pantalla'] = (name != 'LEMD')
    p['pp_asumir_arranca'] = name in ('LEMD', 'LEBL')
    p['pp_asumir_rodaje_salvo'] = ['GND ES', 'GND EN'] if name == 'LEMD' else []
    if name == 'LEMD':
        p['orientaciones'] = ['FIELD', 'NORTH', 'EAST', 'SOUTH', 'WEST']
    else:
        p['orientaciones'] = ['NORTH', 'FIELD']
    if name in ('LEMD', 'LEBL', 'BarcelonaTWR'):
        p['preimpresion_arr'] = 10
        p['preimpresion_dep'] = 2
    else:
        p['preimpresion_arr'] = 30
        p['preimpresion_dep'] = 30
    p['tfl_dep_local'] = 240
    p['tfl_defecto'] = 250
    p['tfl_fijo'] = {'PEKOP': (130, 150)}  # (salida local, resto)
    p['decel_aterrizaje'] = {'*': 7.0, 'LESO': 8.0, 'LEBL': 4.0}  # kt/s por encima de 50 kt
    p['acel_despegue'] = {'*': 5.0, 'GEML': 9.0, 'LESO': 8.0}  # kt/s
    p['min_alt_visible'] = {'LEGR': 50.0}  # por sector, en cientos de pies
    if sectors and sectors[0] == 'GRANADA':
        p['activacion_manual_ads'] = ['LEGR']
    else:
        p['activacion_manual_ads'] = []
    p['ads_sin_fichas_fijo'] = ['LEAM', 'LEGR']
    # --- Bahia de fichas (ATCBahia), Fase 3 parte 2 ---
    # Bahia de torre: solo fichas de estos aerodromos (vacio = todas). Antes se aplicaba
    # 'solo LEST' en TODOS los escenarios (las torres de LEGR, LEAM... no veian fichas).
    p['bahia_torre_ads'] = ['LEST'] if name in ('LEST', 'LECO', 'LEVX') else []
    p['alias_ads'] = {}  # aerodromo mostrado en la ficha (vacio = el del plan de vuelo)
    # Borde azul (salida) para estos aerodromos aunque no sean locales y teclado en el campo
    # frecuencia: estaban condicionados a fir.name == 'LECG', que no existe (el escenario se llama LEST).
    p['ficha_borde_salida_ads'] = ['LPPR'] if name == 'LECG' else []
    p['ficha_freq_teclado'] = (name == 'LECG')
    # Pista mostrada en la ficha segun la configuracion: 'AD CONFIG' -> (salidas, llegadas)
    if name == 'Barcelona':
        p['ficha_pistas_config'] = {'LEBL WRL': ('25L', '25R'), 'LEBL ELR': ('07R', '07L'),
                                    'LEBL WLL': ('25L', '25L'), 'LEBL ENR': ('07R', '02')}
    else:
        p['ficha_pistas_config'] = {}
    # Ventana USO PISTAS (UCS): pares de pistas y mapas de pista cerrada (antes fijos de LEBL)
    p['uso_pistas'] = ['13/31', '02/20', '06L/24R', '06R/24L']
    p['mapas_pista_cerrada'] = {'02': ['02_CLSD'], '20': ['02_CLSD'],
                                '06L': ['06L_CLSD', '06_CLSD'], '24R': ['06L_CLSD', '06_CLSD'],
                                '24L': ['24_CLSD'], '06R': ['24_CLSD']}
    # Editor: sin rutas/puntos/sectores por defecto y sin botones de fijos (antes fir.name == 'LECB')
    p['editor_mapas_reducidos'] = (name == 'LECB')
    # Alertas aeroportuarias: se activan si el Excel trae las hojas INCW*/CMAC*/CATC*;
    # con 'alertas' = 0 se desactivan aunque esten las hojas
    p['alertas'] = True
    # Planes de vehiculo (boton VEH, PVH) y cruce/entrada a pista CRU/ENT/LIB en OSF:
    # solo existian en la version de LEBL
    p['pvh'] = (name == 'LEBL')
    # Refresco (s) de las etiquetas de los moviles en vuelo en el radar del controlador.
    # 0 = se refrescan con el resto (comportamiento anterior en GAMMA_GLOBAL)
    p['refresco_aire'] = 0
    return p


# ---------------------------------------------------------------------------
# Fijos de la bahia de fichas (ATCBahia, posiciones no OSF)
# Hoja opcional 'BahiaFijos' (si existe sustituye a los de por defecto). Fila 1 = cabecera:
#   A posicion  texto contenido en el sector de la posicion (APP, LCL...); vacio = cualquiera.
#               Se usa el primer filtro que aparezca en el sector; si ninguno, las filas sin filtro.
#   B tipo      TEXTO | TEXTOLIBRE | IMAGEN | IMAGENES
#   C texto     TEXTO: texto mostrado; IMAGEN: fichero; IMAGENES: carpeta con Fijo<n>.jpg
#               En rutas: {img} = carpeta img, {sector} = sector de la posicion,
#               {config} = configuracion de pistas en uso del aerodromo principal (minusculas)
#   D x         posicion horizontal del texto (opcional, 180 por defecto)
#   E id        identificador (opcional, por defecto el texto)
# ---------------------------------------------------------------------------
def _fijo(pos, tipo, texto='', x=180, ident=None, ruta=''):
    return {'pos': pos, 'tipo': tipo, 'texto': texto, 'x': x,
            'id': ident if ident is not None else texto, 'ruta': ruta}


def _default_bahia_fijos(name):
    """Fijos que antes estaban escritos en ATCBahia.update_fijos para cada escenario."""
    T = 'TEXTO'
    if name == 'LEAM':
        return [_fijo('', T, 'RWY 25', 190), _fijo('', T, 'RWY 07', 190), _fijo('', T, 'PISTA OCUPADA', 150)]
    if name == 'LEGR':
        return [_fijo('', 'IMAGENES', ruta='{img}/LEGR')]
    if name == 'LEMH':
        return [_fijo('', T, 'BOMBEROS', 190), _fijo('', T, u'SE\xd1ALERO', 190, 'SENALERO'),
                _fijo('', T, 'PISTA 01', 190, 'PISTA01'), _fijo('', T, 'PISTA 19', 190, 'PISTA19'),
                _fijo('', T, ' ', 190)]
    if name in ('LEST', 'LEVX', 'LECO'):
        fs = [_fijo('APP', T, ad) for ad in ('LEST', 'LECO', 'LEVX', 'LPPR')]
        fs += [_fijo('APP', 'TEXTOLIBRE') for i in range(5)]
        fs += [_fijo('LCL', T, 'LEST'), _fijo('LCL', T, 'PISTA OCUPADA')]
        fs += [_fijo('LCL', 'TEXTOLIBRE') for i in range(5)]
        return fs
    if name == 'Lleida':
        return [_fijo('', T, 'RWY 13'), _fijo('', T, 'RWY 31')]
    if name == 'Malaga':
        return [_fijo('', T, 'RWY 12/30'), _fijo('', T, 'RWY 13/31')]
    if name == 'LEMD':
        return [_fijo('', 'IMAGENES', ruta='{img}/LEMD/{sector}/NOR')]
    return []


def _read_bahia_fijos_sheet(ws):
    fijos = []
    for i, row in enumerate(ws.rows):
        if i == 0:
            continue  # cabecera
        vals = [cell.value for cell in row[:5]]
        vals += [None] * (5 - len(vals))
        if vals[1] is None:
            continue
        tipo = str(vals[1]).strip().upper()
        if tipo not in ('TEXTO', 'TEXTOLIBRE', 'IMAGEN', 'IMAGENES'):
            logging.error("Unable to read row in 'BahiaFijos' sheet. Values: %s", vals)
            continue
        pos = _normalize_sector(str(vals[0]).strip().upper()) if vals[0] is not None else ''
        texto = vals[2] if vals[2] is not None else ''
        if not isinstance(texto, basestring):
            texto = str(texto)
        try:
            x = int(float(vals[3])) if vals[3] is not None else 180
        except:
            x = 180
        ident = str(vals[4]).strip() if vals[4] is not None else None
        if tipo in ('IMAGEN', 'IMAGENES'):
            fijos.append(_fijo(pos, tipo, '', x, ident, texto))
        else:
            fijos.append(_fijo(pos, tipo, texto, x, ident))
    return fijos


def select_bahia_fijos(fijos, sector):
    """Fijos que corresponden a la posicion 'sector' (ver hoja 'BahiaFijos')."""
    s = str(sector).upper() if sector else ''
    filtros = []
    for f in fijos:
        if f['pos'] and f['pos'] not in filtros:
            filtros.append(f['pos'])
    for flt in filtros:
        if flt in s:
            return [f for f in fijos if f['pos'] == flt]
    return [f for f in fijos if not f['pos']]


def _to_bool(v):
    if v is None:
        return False
    if isinstance(v, (int, long, float)):
        return v != 0
    return str(v).strip().upper() in ('1', '1.0', 'SI', 'S', 'TRUE', 'YES', 'Y', 'ON', 'X')


def _apply_param_rows(params, raw):
    """Aplica sobre params las filas leidas de la hoja 'Escenario'."""
    for key, rows in raw.items():
        for vals in rows:
            b, c = vals[0], vals[1]
            try:
                if key in _PARAM_BOOL:
                    params[key] = _to_bool(b)
                elif key in _PARAM_NUM:
                    params[key] = float(b)
                elif key in _PARAM_LIST:
                    items = [x.strip().upper() for x in str(b if b is not None else '').split(',') if x.strip()]
                    if key == 'pp_asumir_rodaje_salvo':
                        items = [_normalize_sector(x) for x in items]
                    params[key] = items
                elif key in _PARAM_STR:
                    params[key] = str(b).strip().upper() if b is not None else ''
                elif key in _PARAM_MAP:
                    d = dict(params.get(key, {}))
                    k = str(b).strip().upper() if b is not None else '*'
                    if k in ('', 'TODOS', 'ALL'):
                        k = '*'
                    if key == 'min_alt_visible':
                        k = _normalize_sector(k)
                    if c is None:
                        d.pop(k, None)  # celda vacia: elimina el valor por defecto
                    elif key == 'alias_ads':
                        d[k] = str(c).strip().upper()
                    elif key == 'mapas_pista_cerrada':
                        d[k] = [x.strip() for x in str(c).split(',') if x.strip()]
                    elif key == 'ficha_pistas_config':
                        k = ' '.join(k.split())  # 'LEBL  WRL' -> 'LEBL WRL'
                        pr = [x.strip().upper() for x in str(c).split(',')]
                        if len(pr) == 1:
                            pr = pr * 2
                        d[k] = (pr[0], pr[1])
                    elif key == 'tfl_fijo':
                        tf = [int(float(x)) for x in str(c).split(',') if x.strip()]
                        if len(tf) == 1:
                            tf = tf * 2
                        d[k] = (tf[0], tf[1])
                    else:
                        d[k] = float(c)
                    params[key] = d
            except:
                logging.error("Unable to read '%s' in 'Escenario' sheet. Values: %s", key, vals)


# ---------------------------------------------------------------------------
# Reglas de secuencia de sectores (antes fijas en GTA.load_flight)
# Hoja opcional 'SectorSequence'. Fila 1 = cabecera; columnas:
#   A aeropuerto (uno o varios separados por coma; vacio = cualquiera)
#   B operacion  DEP (adep) / ARR (ades) / vacio = cualquiera
#   C pista      texto contenido en la pista de salida/llegada (vacio = cualquiera)
#   D posicion   TWR (posicion solo de torre) / APP (resto) / vacio = cualquiera
#   E accion     QUITAR | QUITAR_PRIMERO | AL_FINAL | FIJAR
#   F valor      sector(es) separados por coma
#   G si_escenario (opcional) la regla solo se aplica si el escenario tiene alguno
#                de estos aerodromos (vacio = siempre)
# Si la hoja existe sustituye por completo a _DEFAULT_SECTOR_SEQ_RULES.
# ---------------------------------------------------------------------------
_SEQ_ACTIONS = ('QUITAR', 'QUITAR_PRIMERO', 'AL_FINAL', 'FIJAR')


def _seq_rule(ads, op, pista, pos, accion, valor, si_escenario=None):
    return {'ads': ads, 'op': op, 'pista': pista, 'pos': pos, 'accion': accion, 'valor': valor,
            'si_escenario': si_escenario or []}


_LEBL = ['LEBL']
_CANARIAS = ['GCXO', 'GCTS', 'GCLP']


_DEFAULT_SECTOR_SEQ_RULES = [
    # LEBL ELR: llegadas por la 06L -> fuera el primer GND GN
    _seq_rule(['LEBL'], 'ARR', '06L', '', 'QUITAR_PRIMERO', ['GND GN'], _LEBL),
    # LEBL ENR pista cruzada: salidas por la 06R sin LCL ARR; llegadas por la 02 sin LCL DEP ni primer GND
    _seq_rule(['LEBL'], 'DEP', '06R', '', 'QUITAR', ['LCL ARR'], _LEBL),
    _seq_rule(['LEBL'], 'ARR', '02', '', 'QUITAR', ['LCL DEP'], _LEBL),
    _seq_rule(['LEBL'], 'ARR', '02', '', 'QUITAR_PRIMERO', ['GND'], _LEBL),
    # LECG: en las salidas APP siempre al final
    _seq_rule(['LEST', 'LECO', 'LEVX'], 'DEP', '', '', 'AL_FINAL', ['APP']),
    # Canarias: secuencia fija por tipo de operacion (posicion de torre pura sin APP)
    _seq_rule(['GCXO', 'GCTS', 'GCLP'], 'ARR', '', 'TWR', 'FIJAR', ['LCL', 'GND'], _CANARIAS),
    _seq_rule(['GCXO', 'GCTS', 'GCLP'], 'DEP', '', 'TWR', 'FIJAR', ['GND', 'LCL'], _CANARIAS),
    _seq_rule(['GCXO', 'GCTS'], 'ARR', '', 'APP', 'FIJAR', ['APP', 'LCL', 'GND'], _CANARIAS),
    _seq_rule(['GCXO', 'GCTS'], 'DEP', '', 'APP', 'FIJAR', ['GND', 'LCL', 'APP'], _CANARIAS),
]


def _split_upper(v):
    return [x.strip().upper() for x in str(v if v is not None else '').split(',') if x.strip()]


def _read_sector_seq_sheet(ws):
    rules = []
    for i, row in enumerate(ws.rows):
        if i == 0:
            continue  # cabecera
        vals = [cell.value for cell in row[:7]]
        vals += [None] * (7 - len(vals))
        if vals[4] is None:
            continue
        accion = str(vals[4]).strip().upper()
        op = str(vals[1]).strip().upper() if vals[1] is not None else ''
        pos = str(vals[3]).strip().upper() if vals[3] is not None else ''
        if accion not in _SEQ_ACTIONS or op not in ('', 'DEP', 'ARR') or pos not in ('', 'TWR', 'APP'):
            logging.error("Unable to read rule in 'SectorSequence' sheet. Values: %s", vals)
            continue
        pista = str(vals[2]).strip().upper() if vals[2] is not None else ''
        valor = [_normalize_sector(x) for x in _split_upper(vals[5])]
        rules.append(_seq_rule(_split_upper(vals[0]), op, pista, pos, accion, valor, _split_upper(vals[6])))
    return rules


def apply_sector_seq_rules(rules, a, posicion, fir_ads=()):
    """Devuelve la secuencia de sectores de 'a' tras aplicar las reglas del escenario."""
    seq = list(a.sector_sequence)
    if not seq or not rules:
        return seq
    pos_upper = str(posicion).upper() if posicion else ''
    twr_only = any(k in pos_upper for k in ('LCL', 'GND')) and 'APP' not in pos_upper
    deprwy = str(getattr(a, 'deprwy', '') or '')
    desrwy = str(getattr(a, 'desrwy', '') or '')
    fijado = False
    for r in rules:
        if r.get('si_escenario') and not any(x in fir_ads for x in r['si_escenario']):
            continue
        if r['pos'] == 'TWR' and not twr_only:
            continue
        if r['pos'] == 'APP' and twr_only:
            continue
        match = False
        for op, ad, rwy in (('DEP', a.adep, deprwy), ('ARR', a.ades, desrwy)):
            if r['op'] not in ('', op):
                continue
            if r['ads'] and ad not in r['ads']:
                continue
            if r['pista'] and r['pista'] not in rwy.upper():
                continue
            match = True
            break
        if not match:
            continue
        acc = r['accion']
        if acc == 'FIJAR':
            if not fijado:
                seq = list(r['valor'])
                fijado = True
        elif acc == 'QUITAR':
            for v in r['valor']:
                if v in seq:
                    seq.remove(v)
        elif acc == 'QUITAR_PRIMERO':
            if seq and any(v in seq[0] for v in r['valor']):
                seq.pop(0)
        elif acc == 'AL_FINAL':
            for v in r['valor']:
                if v in seq:
                    seq.remove(v)
                    seq.append(v)
    return seq


class ESCENARIO:

    def __init__(self, fir_file):
        self.book = load_workbook(filename=fir_file, read_only=True)

        self.x0 = self.book['Escenario']['C2'].value
        self.y0 = self.book['Escenario']['D2'].value
        self.Cx0 = self.book['Escenario']['E2'].value
        self.Cy0 = self.book['Escenario']['F2'].value

        self.ap = []
        self.rwys = []
        self.elevation = 0
        self.field_up = 0
        self.dec_mag = 0
        self.cob_radar_inf = 0
        # Velocidades de rodaje (kt), hoja 'Escenario':
        #   ifr_taxi_ias (o 'taxi_ias', sinonimo por compatibilidad), vfr_taxi_ias, ret_ias.
        # vfr_taxi_ias = None -> los VFR ruedan a ifr_taxi_ias (comportamiento previo).
        self.ifr_taxi_ias = 15.0
        self.vfr_taxi_ias = None
        self.ret_ias = 4.0
        self.auto_map = 0.0  # Frustrada automatica al llegar alto al umbral (0 = desactivada)
        self.auto_map_alt = 200.0  # Pies por encima de la senda que disparan la frustrada
        self.app_max_rod = 0.0  # Limite del rate de descenso en APP, ft/min (0 = sin limite)
        self.gates = []
        self.hp = {}
        self.zonasOSF = {}
        self.params_raw = {}  # Parametros de escenario (ver _PARAM_KEYS)

        for row in self.book['Escenario'].rows:
            if row[0].value == 'pistas':
                rwys = (str(row[1].value)).split(',')
                for rwy in rwys:
                    self.rwys.append(rwy)
            elif row[0].value == 'elevaciones':
                self.elevation = float(row[1].value)
            elif row[0].value == 'aeropuerto':
                self.ap.append(str(row[1].value).upper())
            elif row[0].value == 'field_up':
                self.field_up = float(row[1].value)
            elif row[0].value == 'dec_magnetica':
                self.dec_mag = float(row[1].value)
            elif row[0].value == 'puertas':
                try:
                    gates = (str(row[1].value)).split(',')
                    for gate in gates:
                        self.gates.append(gate)
                except:
                    logging.error("Unable to read 'Puertas' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'hp':
                try:
                    rwy_key = str(row[1].value)
                    if rwy_key not in self.hp.keys():
                        list = (str(row[2].value)).split(',')
                        self.hp[rwy_key] = list
                except:
                    logging.error("Unable to read 'Holding Points' in 'Escenario' sheet. Error: %s", row)

            # elif row[0].value == 'hp':  # DCM: lo hacemos como lista para probar rapido con OSF nueva. Cambiar a dict...
            #     try:
            #         hps = (str(row[1].value)).split(',')
            #         for hp in hps:
            #             self.hp.append(hp)
            #     except:
            #         logging.error("Unable to read 'HPs' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'cob_radar_inf':
                self.cob_radar_inf = float(row[1].value) if row[1].value is not None else 0.0

            elif row[0].value in ('taxi_ias', 'ifr_taxi_ias'):
                try:
                    self.ifr_taxi_ias = float(row[1].value)
                except:
                    logging.error("Unable to read '%s' in 'Escenario' sheet. Error: %s", row[0].value, row)

            elif row[0].value == 'vfr_taxi_ias':
                try:
                    self.vfr_taxi_ias = float(row[1].value)
                except:
                    logging.error("Unable to read 'vfr_taxi_ias' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'ret_ias':
                try:
                    self.ret_ias = float(row[1].value)
                except:
                    logging.error("Unable to read 'ret_ias' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'auto_map':
                try:
                    self.auto_map = float(row[1].value)
                except:
                    logging.error("Unable to read 'auto_map' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'auto_map_alt':
                try:
                    self.auto_map_alt = float(row[1].value)
                except:
                    logging.error("Unable to read 'auto_map_alt' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value == 'app_max_rod':
                try:
                    self.app_max_rod = float(row[1].value)
                except:
                    logging.error("Unable to read 'app_max_rod' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value in ('zonasOSF', 'zonesOSF'):  # 'zonesOSF': nombre usado en LEBL/LEPA/LEMD/LEMG
                try:
                    key = _normalize_sector(row[1].value)
                    if key not in self.zonasOSF.keys():
                        self.zonasOSF[key] = str(row[2].value)
                except:
                    logging.error("Unable to read 'zonasOSF' in 'Escenario' sheet. Error: %s", row)

            elif row[0].value is not None and str(row[0].value).strip() in _PARAM_KEYS:
                vals = [cell.value for cell in row[1:3]]
                vals += [None] * (2 - len(vals))
                self.params_raw.setdefault(str(row[0].value).strip(), []).append(vals)

        self.taxi_ias = self.ifr_taxi_ias  # compatibilidad con codigo que aun lea taxi_ias

        # Fijos de la bahia de fichas (hoja opcional 'BahiaFijos'; None -> los de por defecto)
        self.bahia_fijos = None
        if 'BahiaFijos' in self.book.sheetnames:
            try:
                self.bahia_fijos = _read_bahia_fijos_sheet(self.book['BahiaFijos'])
            except:
                logging.error("Unable to read 'BahiaFijos' sheet", exc_info=True)

        # Reglas de secuencia de sectores (hoja opcional 'SectorSequence'; None -> reglas por defecto)
        self.sector_seq_rules = None
        if 'SectorSequence' in self.book.sheetnames:
            try:
                self.sector_seq_rules = _read_sector_seq_sheet(self.book['SectorSequence'])
            except:
                logging.error("Unable to read 'SectorSequence' sheet", exc_info=True)

        self.line = {}
        self.stands = {}
        self.pushbacks = {}
        self.t_side = {}

        try:
            for row in self.book['Linea costa'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.line.keys():
                    self.line[row[0].value] = []
                    # print row[0].value
                self.line[row[0].value].append([row[1].value, row[2].value])
        except ValueError:
            logging.error("Unable to read 'Linea costa' sheet data. Error: %s", row)

        try:

            for row in self.book['Stands'].rows:
                if row[1].value is None:
                    break
                if row[1].value not in self.stands.keys():
                    self.stands[row[1].value] = []
                self.stands[row[1].value].append([row[2].value, row[3].value])
        except ValueError:
            logging.error("Unable to read 'Stands' sheet data. Error: %s", row)

        try:
            for row in self.book['Lado tierra'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.t_side.keys():
                    self.t_side[row[0].value] = {}
                if row[1].value not in self.t_side[row[0].value].keys():
                    self.t_side[row[0].value][row[1].value] = []
                self.t_side[row[0].value][row[1].value].append([row[2].value, row[3].value])
        except ValueError:
            logging.error("Unable to read 'Lado Tierra' sheet data. Error: %s", row)

        self.air_side = {}
        try:
            for row in self.book['Lado aire'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.air_side.keys():
                    self.air_side[row[0].value] = {}
                if row[1].value not in self.air_side[row[0].value].keys():
                    self.air_side[row[0].value][row[1].value] = []
                self.air_side[row[0].value][row[1].value].append([row[2].value, row[3].value])
        except ValueError:
            logging.error("Unable to read 'Lado Aire' sheet data. Error: %s", row)

        self.rod_points = {}
        self.taxiways = {}

        try:
            for row in self.book['Puntos rodaje'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.taxiways.keys():
                    self.taxiways[row[0].value] = {}
                if row[1].value not in self.taxiways[row[0].value]:
                    self.taxiways[row[0].value][row[1].value] = []
                self.taxiways[row[0].value][row[1].value].append(row[2].value)

                if row[0].value not in self.rod_points.keys():
                    self.rod_points[row[0].value] = {}
                if row[1].value not in self.rod_points[row[0].value].keys():
                    self.rod_points[row[0].value][row[1].value] = {}
                if row[2].value not in self.rod_points[row[0].value][row[1].value].keys():
                    self.rod_points[row[0].value][row[1].value][row[2].value] = {}
                if row[3].value not in self.rod_points[row[0].value][row[1].value][row[2].value].keys():
                    self.rod_points[row[0].value][row[1].value][row[2].value][row[3].value] = []
                try:
                    self.rod_points[row[0].value][row[1].value][row[2].value][row[3].value].append(
                        [row[4].value, row[5].value, row[6].value])
                except IndexError:  # catch the error
                    self.rod_points[row[0].value][row[1].value][row[2].value][row[3].value].append(
                        [row[4].value, row[5].value, None])
        except ValueError:
            logging.error("Unable to read 'Puntos rodaje' sheet data. Error: %s", row)

        self.procedures = {}
        try:
            for row in self.book['Rodaje'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.procedures.keys():
                    self.procedures[row[0].value] = {}
                if row[1].value not in self.procedures[row[0].value].keys():
                    self.procedures[row[0].value][row[1].value] = {}
                if row[2].value not in self.procedures[row[0].value][row[1].value].keys():
                    self.procedures[row[0].value][row[1].value][row[2].value] = {}
                for point in str(row[4].value).split(','):
                    if 'DEP' in str(row[2].value).split('_'):
                        rutarod = [point] + str(row[5].value).split(',') + [row[1].value]
                        self.procedures[row[0].value][row[1].value][row[2].value][point] = []
                        self.procedures[row[0].value][row[1].value][row[2].value][point].extend(
                            self.rod_points[row[0].value][point]['Dep']['p'])
                    else:
                        rutarod = [row[1].value] + str(row[5].value).split(',') + [point]
                        self.procedures[row[0].value][row[1].value][row[2].value][point] = []
                    for c in range(1, len(rutarod) - 1):
                        ini = self.taxiways[row[0].value][rutarod[c]].index(rutarod[c - 1])
                        fin = self.taxiways[row[0].value][rutarod[c]].index(rutarod[c + 1])
                        pas = 1 if ini < fin else -1
                        if 'c' in self.rod_points[row[0].value][rutarod[c]][self.taxiways[row[0].value][rutarod[c]][ini]].keys():
                            self.procedures[row[0].value][row[1].value][row[2].value][point].extend(
                                self.rod_points[row[0].value][rutarod[c]][self.taxiways[row[0].value][rutarod[c]][ini]]['c'])
                        for pto in range(ini, fin, pas):
                            if 'p' in self.rod_points[row[0].value][rutarod[c]][self.taxiways[row[0].value][rutarod[c]][pto]]\
                                    .keys():
                                self.procedures[row[0].value][row[1].value][row[2].value][point].extend(
                                    self.rod_points[row[0].value][rutarod[c]][self.taxiways[row[0].value][rutarod[c]][pto]]['p'])
                    if 'LND' in str(row[2].value).split('_'):
                        self.procedures[row[0].value][row[1].value][row[2].value][point].extend(
                            self.rod_points[row[0].value][point]['Lnd']['p'])
        except ValueError:
            logging.error("Unable to read Rodaje sheet data. Error: %s", row)

        try:
            for row in self.book['Procedimientos'].rows:
                if row[0].value is None:
                    break
                if row[0].value not in self.procedures.keys():
                    self.procedures[row[0].value] = {}
                if row[1].value not in self.procedures[row[0].value].keys():
                    self.procedures[row[0].value][row[1].value] = {}
                if row[2].value not in self.procedures[row[0].value][row[1].value].keys():
                    self.procedures[row[0].value][row[1].value][row[2].value] = {}
                if row[2].value == 'IA':
                    if row[3].value not in self.procedures[row[0].value][row[1].value][row[2].value].keys():
                        self.procedures[row[0].value][row[1].value][row[2].value][row[3].value] = {}
                    if row[8].value not in self.procedures[row[0].value][row[1].value][row[2].value][row[3].value].keys():
                        self.procedures[row[0].value][row[1].value][row[2].value][row[3].value][row[8].value] = []
                    self.procedures[row[0].value][row[1].value][row[2].value][row[3].value][row[8].value]\
                        .append([row[4].value, row[5].value, row[7].value, row[6].value])
                else:
                    if row[3].value not in self.procedures[row[0].value][row[1].value][row[2].value].keys():
                        self.procedures[row[0].value][row[1].value][row[2].value][row[3].value] = []
                    self.procedures[row[0].value][row[1].value][row[2].value][row[3].value]\
                        .append([row[4].value, row[5].value])

            for row in self.book['LLZ']:
                if row[0].value is None:
                    break
                if row[0].value not in self.procedures.keys():
                    self.procedures[row[0].value] = {}
                if row[1].value not in self.procedures[row[0].value].keys():
                    self.procedures[row[0].value][row[1].value] = {}
                if row[2].value not in self.procedures[row[0].value][row[1].value].keys():
                    self.procedures[row[0].value][row[1].value][row[2].value] = {}
                if row[3].value not in self.procedures[row[0].value][row[1].value][row[2].value].keys():
                    self.procedures[row[0].value][row[1].value][row[2].value][row[3].value] = []
                self.procedures[row[0].value][row[1].value][row[2].value][row[3].value].append(
                    [row[4].value, row[5].value, row[6].value, row[7].value, row[8].value, row[9].value])
        except ValueError:
            logging.error("Unable to read 'Procedimientos' sheet data. Error: %s", row)

        self.sacta = {}
        self.sacta_order = []
        try:
            for row in self.book['SACTA'].rows:
                if row[1].value is None:
                    break
                if row[1].value not in self.sacta.keys():
                    self.sacta[row[1].value] = {}
                    self.sacta_order.append(row[1].value)
                if row[2].value not in self.sacta[row[1].value].keys():
                    self.sacta[row[1].value][row[2].value] = {}
                if row[3].value not in self.sacta[row[1].value][row[2].value].keys():
                    try:
                        self.sacta[row[1].value][row[2].value][row[3].value] = [row[6].value]
                    except IndexError:  # catch the error
                        self.sacta[row[1].value][row[2].value][row[3].value] = [None]

                self.sacta[row[1].value][row[2].value][row[3].value].append([row[4].value, row[5].value])
        except ValueError:
            logging.error("Unable to read 'SACTA' sheet data. Error: %s", row)

        self.holdings = {}

        try:
            for row in self.book['Esperas'].rows:
                if row[0].value is None:
                    break
                if row[1].value not in self.holdings.keys():
                    self.holdings[row[1].value] = [float(row[2].value), float(row[3].value), str(row[4].value)]
        except ValueError:
            logging.error("Unable to read 'Esperas' sheet data. Error: %s", row)

        self.sectors = {}

        try:
            for row in self.book['Sector'].rows:
                if row[0].value is None:
                    break
                sector_name = _normalize_sector(row[0].value)
                if sector_name not in self.sectors.keys():
                    self.sectors[sector_name] = {}
                if row[1].value not in self.sectors[sector_name].keys():
                    self.sectors[sector_name][row[1].value] = []
                self.sectors[sector_name][row[1].value].append([row[2].value])
        except ValueError:
            logging.error("Unable to read 'Sector' sheet data. Error: %s", row)

        try:
            self.state_to_bahia = {}
            # La hoja OSF es opcional: los escenarios PICT/UCS no la tienen.
            if 'OSF' not in self.book:
                logging.info("Sheet 'OSF' not found in the workbook (escenario sin OSF).")
            for row in (self.book['OSF'].rows if 'OSF' in self.book else []):
                rol_list = (str(row[0].value)).split(',')
                osf_status_list = (str(row[1].value)).split(',')
                action_list = (str(row[2].value)).split(',')
                zone = 'zone' + str(row[3].value)
                for rol in rol_list:
                    for osf_status in osf_status_list:
                        for action in action_list:
                            rol = _normalize_sector(rol.strip())
                            osf_status = osf_status.strip()
                            action = action.strip()
                            self.state_to_bahia[(rol, osf_status, action)] = zone
            # print(self.state_to_bahia)
        except ValueError:
            logging.error("Unable to read 'OSF' sheet data. Error: %s", row)

        # Hoja OSF_Layout: estructura de fichas OSF/PrevDesp por (bahia, depdes).
        # Si la hoja no existe o falta una combinacion, OSF/PrevDesp caen al
        # layout hardcoded por defecto.
        self.osf_layouts = {}
        self.osf_ext_layouts = {}
        if 'OSF_Layout' not in self.book:
            logging.warning("Sheet 'OSF_Layout' not found in the workbook.")
        else:
            try:
                header_seen = False
                for row in self.book['OSF_Layout'].rows:
                    if not header_seen:
                        header_seen = True
                        continue
                    if row[0].value is None:
                        break
                    bahia = str(row[0].value).strip()
                    depdes = str(row[1].value).strip()
                    normal_raw = row[2].value if len(row) > 2 else None
                    ext_raw = row[3].value if len(row) > 3 else None
                    if normal_raw:
                        self.osf_layouts[(bahia, depdes)] = [
                            c.strip() for c in str(normal_raw).split(',') if c.strip()
                        ]
                    if ext_raw:
                        self.osf_ext_layouts[(bahia, depdes)] = [
                            c.strip() for c in str(ext_raw).split(',') if c.strip()
                        ]
            except ValueError:
                logging.error("Unable to read 'OSF_Layout' sheet data. Error: %s", row)

        try:
            self.vel_cruz = {}
            if 'Velocidades' not in self.book:
                logging.warning("Sheet 'Velocidades' not found in the workbook.")
            else:
                for row in self.book['Velocidades'].rows:
                    key = row[0].value
                    value = row[1].value

                    if key is None or value is None:
                        logging.warning("Skipping row with missing values: %s", row)
                        continue

                    self.vel_cruz[str(key)] = str(value)
        except ValueError:
            logging.error("Error reading 'Velocidades' sheet: %s", row)

        try:
            if 'RetrocesosOSF' not in self.book:
                logging.warning("Sheet 'Retrocesos' not found in the workbook.")
            else:
                for row in self.book['RetrocesosOSF'].rows:
                    if row[1].value is None:
                        break
                    if row[1].value in self.stands.keys() and row[1].value not in self.pushbacks.keys() and row[2].value == 'S':
                        # Direcciones permitidas en las columnas D-G (antes solo D-F: se perdia la
                        # cuarta, p. ej. 'W' en los stands de LEPA con N,S,E,W)
                        self.pushbacks[row[1].value] = [c.value for c in row[3:7]
                                                        if c.value not in (None, '')]
        except ValueError:
            logging.error("Unable to read 'RetrocesosOSF' sheet data. Error: %s", row)

        # Alertas aeroportuarias (INCW/CMAC/CATC): hojas opcionales; sin ellas no se activan
        try:
            self._load_incw_sheets()
        except Exception:
            logging.error("Unable to read INCW/CMAC/CATC alert sheets", exc_info=True)
            self.incw_areas = {}

    def _load_incw_sheets(self):
        """Carga hojas INCW del Excel de escenario (zonas BDAP, parametros pista, pistas cruzadas).

        Hojas esperadas: INCWareaIncur, INCWareaIncurParam, INCWpistasCruzadas.
        Si no existen, las alertas INCW simplemente no se activan.
        Formato: 2 filas de cabecera (fila 0 agrupacion, fila 1 nombres), datos desde fila 2.
        Columnas con offset: Dependencia(0), Aerodromo(1), luego datos especificos.
        """
        self.incw_areas = {}            # {(pista, tipo): [(lat_dms, lon_dms), ...]}
        self.incw_param_pista = {}      # {pista: {campo: valor, ...}}
        self.incw_pistas_cruzadas = []  # [{campo: valor, ...}, ...]

        # Codigos ICAO de este escenario (ej: ['LEBL']) para filtrar filas
        my_airports = [a.upper() for a in self.ap]

        # --- INCWareaIncur: zonas de proteccion (poligonos BDAP) ---
        # Cols: Dependencia(0), Aerodromo(1), Pista(2), Tipo Area(3), orden(4), Latitud(5), Longitud(6)
        if 'INCWareaIncur' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWareaIncur'].rows:
                row_idx += 1
                if row_idx <= 2:  # Saltar 2 filas de cabecera
                    continue
                if row[2].value is None:  # Pista vacia = fin de datos
                    break

                # Filtrar por aerodromo de este escenario
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue

                pista = str(row[2].value).strip()
                tipo_raw = str(row[3].value).strip()
                lat_str = str(row[5].value).strip() if row[5].value else None
                lon_str = str(row[6].value).strip() if row[6].value else None

                if not lat_str or not lon_str:
                    continue

                # Normalizar tipo de area
                if 'Alineamiento' in tipo_raw or tipo_raw == 'ALIN':
                    tipo = 'ALIN'
                elif 'NO-LVP' in tipo_raw or 'NO_LVP' in tipo_raw:
                    tipo = 'NO-LVP'
                elif 'LVP' in tipo_raw:
                    tipo = 'LVP'
                else:
                    tipo = tipo_raw

                # Parsear DMS: quitar sufijo N/S/E/W, convertir a float
                lat_dms = self._parse_dms_value(lat_str)
                lon_dms = self._parse_dms_value(lon_str)
                if lat_dms is None or lon_dms is None:
                    continue

                key = (pista, tipo)
                if key not in self.incw_areas:
                    self.incw_areas[key] = []
                self.incw_areas[key].append((lat_dms, lon_dms))

            logging.info("INCW_Areas: cargadas %d zonas, %d puntos totales",
                         len(self.incw_areas),
                         sum(len(v) for v in self.incw_areas.values()))
        else:
            logging.info("Hoja 'INCWareaIncur' no encontrada, alertas INCW sin zonas BDAP")

        # --- INCWareaIncurParam: parametros por pista ---
        # Cols: Dep(0), Aero(1), Pista(2), PoligCalc(3), Dist.Der(4), Dist.Izq(5),
        #       NoLVP T.Pred(6), NoLVP T.Viol(7), NoLVP Marg.Anch(8), NoLVP Marg.Long(9),
        #       NoLVP T.Cort.Arr(10), LVP T.Pred(11), LVP T.Viol(12),
        #       LVP Marg.Anch(13), LVP Marg.Long(14), LVP T.Cort.Arr(15)
        if 'INCWareaIncurParam' in self.book.sheetnames:
            PARAM_COLS = [
                (4, 'Dist.Der'), (5, 'Dist.Izq'),
                (6, 'NoLVP_T_Pred'), (7, 'NoLVP_T_Viol'),
                (8, 'NoLVP_Marg_Anch'), (9, 'NoLVP_Marg_Long'),
                (10, 'NoLVP_T_Cort_Arr'),
                (11, 'LVP_T_Pred'), (12, 'LVP_T_Viol'),
                (13, 'LVP_Marg_Anch'), (14, 'LVP_Marg_Long'),
                (15, 'LVP_T_Cort_Arr'),
            ]
            row_idx = 0
            for row in self.book['INCWareaIncurParam'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                if row[2].value is None:
                    break

                # Filtrar por aerodromo
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue

                pista = str(row[2].value).strip()
                params = {}
                for col_idx, col_name in PARAM_COLS:
                    if col_idx < len(row) and row[col_idx].value is not None:
                        try:
                            params[col_name] = float(row[col_idx].value)
                        except (ValueError, TypeError):
                            params[col_name] = row[col_idx].value
                self.incw_param_pista[pista] = params

            logging.info("INCW_ParamPista: cargados parametros para %d pistas",
                         len(self.incw_param_pista))

        # --- INCWpistasCruzadas: puntos de cruce entre pistas ---
        # Cols: Dep(0), Aero(1), PuntoCruce(2), P.Cruzada1(3), P.Cruzada2(4),
        #       P1_D1_Arr(5), P1_D2_Arr(6), P1_D3_Arr(7), P1_D4_Desp(8),
        #       P2_D1_Arr(9), P2_D2_Arr(10), P2_D3_Arr(11), P2_D4_Desp(12),
        #       Dist_Min_Sep(13)
        if 'INCWpistasCruzadas' in self.book.sheetnames:
            CRUCE_COLS = [
                (2, 'Punto_Cruce'), (3, 'Pista1'), (4, 'Pista2'),
                (5, 'P1_D1_Arr'), (6, 'P1_D2_Arr'), (7, 'P1_D3_Arr'), (8, 'P1_D4_Desp'),
                (9, 'P2_D1_Arr'), (10, 'P2_D2_Arr'), (11, 'P2_D3_Arr'), (12, 'P2_D4_Desp'),
                (13, 'Dist_Min_Sep'),
            ]
            row_idx = 0
            for row in self.book['INCWpistasCruzadas'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                if row[2].value is None:
                    break

                # Filtrar por aerodromo
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue

                entry = {}
                for col_idx, col_name in CRUCE_COLS:
                    if col_idx < len(row) and row[col_idx].value is not None:
                        val = row[col_idx].value
                        # Pista1 y Pista2 siempre como string (evitar "02" -> 2.0)
                        if col_name in ('Pista1', 'Pista2', 'Punto_Cruce'):
                            entry[col_name] = str(val).strip() if not isinstance(val, float) \
                                else str(int(val)).zfill(2)
                        else:
                            try:
                                entry[col_name] = float(val)
                            except (ValueError, TypeError):
                                entry[col_name] = str(val).strip()
                self.incw_pistas_cruzadas.append(entry)

            logging.info("INCW_PistasCruzadas: cargados %d puntos de cruce: %s",
                         len(self.incw_pistas_cruzadas),
                         [(e.get('Pista1','?'), e.get('Pista2','?')) for e in self.incw_pistas_cruzadas])

        # --- INCWparamt: parametros generales INCW ---
        # Cols: Dep(0), Aero(1), taxi(2), Despegue(3), Desp.Rapi(4), MaxAngCruce(5),
        #       DistSeg(6), DistMaxFiltConfl(7), NivDescDesp(8)
        self.incw_params = {}  # {'taxi': 50, 'despegue': 35, ...}
        if 'INCWparamt' in self.book.sheetnames:
            GPARAM_COLS = [
                (2, 'taxi'), (3, 'despegue'), (4, 'desp_rapido'),
                (5, 'max_ang_cruce'), (6, 'dist_seg'),
                (7, 'dist_max_filt_confl'), (8, 'niv_desc_desp'),
            ]
            row_idx = 0
            for row in self.book['INCWparamt'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                for col_idx, col_name in GPARAM_COLS:
                    if col_idx < len(row) and row[col_idx].value is not None:
                        try:
                            self.incw_params[col_name] = float(row[col_idx].value)
                        except (ValueError, TypeError):
                            self.incw_params[col_name] = row[col_idx].value
                break  # Solo una fila por aerodromo

            logging.info("INCW_Params: %s", self.incw_params)

        # --- Matrices de severidad INCW ---
        # Patron comun: 2 filas cabecera, filtro aerodromo, fases como columnas
        FASES = ['L/U', 'DEP-S/D', 'DEP-F/D', 'ARR-L/F', 'ARR-S/F',
                 'ARR-ApT', 'CROSS', 'VEH', 'Pred.Taxi']

        def _parse_severity(val):
            """Convierte texto de celda a valor de severidad."""
            if val is None:
                return None
            s = str(val).strip()
            if s == 'VIO':
                return 'VIO'
            elif s == 'WNG':
                return 'WNG'
            elif s == '-' or s == '':
                return None  # Combinacion simetrica (ya evaluada al reves)
            elif 'W/V' in s:
                return 'W/V'  # W/V por distancia (requiere calculo especial)
            else:
                return 'NO'  # 'NO alerta' o cualquier otro

        # --- INCWalerInIndividuales: alertas individuales ---
        # Cols: Dep(0), Aero(1), UsoPista(2), Cabecera(3), Datos(4),
        #       L/U(5), DEP-S/D(6), DEP-F/D(7), ARR-L/F(8), ARR-S/F(9),
        #       ARR-ApT(10), CROSS(11), VEH(12), Pred.Taxi(13)
        self.incw_alert_indiv = {}  # {(uso_pista, cabecera): {fase: severidad}}
        if 'INCWalerInIndividuales' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWalerInIndividuales'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break

                uso_pista = str(row[2].value).strip()
                cabecera = str(row[3].value).strip()
                severidades = {}
                for fi, fase in enumerate(FASES):
                    col = 5 + fi
                    if col < len(row):
                        severidades[fase] = _parse_severity(row[col].value)
                self.incw_alert_indiv[(uso_pista, cabecera)] = severidades

            logging.info("INCW_AlertIndiv: %d reglas", len(self.incw_alert_indiv))

        # --- INCWalerInMultENuso: alertas multiples pista EN USO ---
        # Cols: Dep(0), Aero(1), UsoPista(2), FaseA(3), Datos(4),
        #       L/U(5)..Pred.Taxi(13) = severidad para FaseB
        self.incw_mult_en_uso = {}  # {(uso_pista, fase_a): {fase_b: severidad}}
        if 'INCWalerInMultENuso' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWalerInMultENuso'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break

                uso_pista = str(row[2].value).strip()
                fase_a = str(row[3].value).strip()
                severidades = {}
                for fi, fase in enumerate(FASES):
                    col = 5 + fi
                    if col < len(row):
                        severidades[fase] = _parse_severity(row[col].value)
                self.incw_mult_en_uso[(uso_pista, fase_a)] = severidades

            logging.info("INCW_MultEnUso: %d reglas", len(self.incw_mult_en_uso))

        # --- INCWalerInMultNOenUSO: alertas multiples pista NO EN USO ---
        self.incw_mult_no_en_uso = {}  # {(uso_pista, fase_a): {fase_b: severidad}}
        if 'INCWalerInMultNOenUSO' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWalerInMultNOenUSO'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break

                uso_pista = str(row[2].value).strip()
                fase_a = str(row[3].value).strip()
                severidades = {}
                for fi, fase in enumerate(FASES):
                    col = 5 + fi
                    if col < len(row):
                        severidades[fase] = _parse_severity(row[col].value)
                self.incw_mult_no_en_uso[(uso_pista, fase_a)] = severidades

            logging.info("INCW_MultNoEnUso: %d reglas", len(self.incw_mult_no_en_uso))

        # --- INCWalerInMultCERRADA: alertas multiples pista CERRADA ---
        self.incw_mult_cerrada = {}  # {(uso_pista, fase_a): {fase_b: severidad}}
        if 'INCWalerInMultCERRADA' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWalerInMultCERRADA'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break

                uso_pista = str(row[2].value).strip()
                fase_a = str(row[3].value).strip()
                severidades = {}
                for fi, fase in enumerate(FASES):
                    col = 5 + fi
                    if col < len(row):
                        severidades[fase] = _parse_severity(row[col].value)
                self.incw_mult_cerrada[(uso_pista, fase_a)] = severidades

            logging.info("INCW_MultCerrada: %d reglas", len(self.incw_mult_cerrada))

        # --- INCWalerConfMultTraOp: alertas conflicto trafico opuesto ---
        # Cols: Dep(0), Aero(1), UsoPista(2), TipoOpuesta(3), FaseA(4), Datos(5),
        #       L/U(6), DEP-S/D(7), DEP-F/D(8), ARR-L/F(9), ARR-S/F(10), ARR-ApT(11)
        FASES_OPUESTO = ['L/U', 'DEP-S/D', 'DEP-F/D', 'ARR-L/F', 'ARR-S/F', 'ARR-ApT']
        self.incw_conf_opuesto = {}  # {(uso_pista, tipo_opuesta, fase_a): {fase_b: sev}}
        if 'INCWalerConfMultTraOp' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['INCWalerConfMultTraOp'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break

                uso_pista = str(row[2].value).strip()
                tipo_opuesta = str(row[3].value).strip()
                fase_a = str(row[4].value).strip()
                severidades = {}
                for fi, fase in enumerate(FASES_OPUESTO):
                    col = 6 + fi
                    if col < len(row):
                        severidades[fase] = _parse_severity(row[col].value)
                self.incw_conf_opuesto[(uso_pista, tipo_opuesta, fase_a)] = severidades

            logging.info("INCW_ConfOpuesto: %d reglas", len(self.incw_conf_opuesto))

        self._load_cmac_sheets()
        self._load_catc_sheets()

    def _load_catc_sheets(self):
        """Carga hoja CATCsubtipos del Excel de escenario.

        Formato: 2 filas cabecera, datos desde fila 3.
        Cols: Dependencia(0), Aerodromo(1), Categoria(2), Combinacion(3),
              Severidad(4), Condicion_A(5), Condicion_B(6), Condicion_fin(7)
        """
        self.catc_subtypes = []  # [{categoria, combinacion, severidad, ...}]

        my_airports = [a.upper() for a in self.ap]

        if 'CATCsubtipos' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['CATCsubtipos'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break
                self.catc_subtypes.append({
                    'categoria': str(row[2].value).strip(),
                    'combinacion': str(row[3].value).strip() if row[3].value else '',
                    'severidad': str(row[4].value).strip().upper() if row[4].value else 'WNG',
                    'condicion_a': str(row[5].value).strip() if row[5].value else '',
                    'condicion_b': str(row[6].value).strip() if row[6].value else '',
                    'condicion_fin': str(row[7].value).strip() if row[7].value else '',
                })
            logging.info("CATC_subtypes: %d combinaciones cargadas", len(self.catc_subtypes))

    def _load_cmac_sheets(self):
        """Carga hojas CMAC del Excel de escenario (parametros, subtipos, pistas cerradas).

        Hojas esperadas: CMACparamt, CMACsubtipos, CMACpistasCerradas.
        Si no existen, las alertas CMAC simplemente no se activan.
        Formato: 2 filas de cabecera (fila 0 titulo, fila 1 nombres), datos desde fila 2.
        """
        self.cmac_params = {}           # {campo: valor}
        self.cmac_subtypes = {}         # {codigo: {nombre, severidad, aplica_a, fase_movil, condicion_fin}}
        self.cmac_pistas_cerradas = {}  # {(uso_pista, autorizacion): {subtipo, severidad}}

        my_airports = [a.upper() for a in self.ap]

        # --- CMACparamt: parametros generales ---
        # Cols: Dependencia(0), Aerodromo(1), taxi(2), despegue(3), desp_rapido(4),
        #       max_ang_cruce(5), niv_desc_desp(6), tiempo_min_contacto(7)
        if 'CMACparamt' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['CMACparamt'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                param_names = ['taxi', 'despegue', 'desp_rapido', 'max_ang_cruce',
                               'niv_desc_desp', 'tiempo_min_contacto']
                for i, name in enumerate(param_names):
                    col = 2 + i
                    if col < len(row) and row[col].value is not None:
                        try:
                            self.cmac_params[name] = int(row[col].value)
                        except (ValueError, TypeError):
                            self.cmac_params[name] = float(row[col].value)
            logging.info("CMAC_params: %s", self.cmac_params)

        # --- CMACsubtipos: 12 subtipos de alerta ---
        # Cols: Dependencia(0), Aerodromo(1), Codigo(2), Nombre(3), Severidad(4),
        #       Aplica_a(5), Fase_movil(6), Condicion_fin(7)
        if 'CMACsubtipos' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['CMACsubtipos'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break
                codigo = str(row[2].value).strip()
                self.cmac_subtypes[codigo] = {
                    'nombre': str(row[3].value).strip() if row[3].value else '',
                    'severidad': str(row[4].value).strip().upper() if row[4].value else 'WNG',
                    'aplica_a': str(row[5].value).strip().upper() if row[5].value else 'AMBOS',
                    'fase_movil': str(row[6].value).strip() if row[6].value else '',
                    'condicion_fin': str(row[7].value).strip() if row[7].value else '',
                }
            logging.info("CMAC_subtypes: %d subtipos cargados", len(self.cmac_subtypes))

        # --- CMACpistasCerradas: matriz uso_pista x autorizacion ---
        # Cols: Dependencia(0), Aerodromo(1), Uso_pista(2), Autorizacion(3),
        #       Severidad(4), Subtipo_CMAC(5)
        if 'CMACpistasCerradas' in self.book.sheetnames:
            row_idx = 0
            for row in self.book['CMACpistasCerradas'].rows:
                row_idx += 1
                if row_idx <= 2:
                    continue
                aero = str(row[1].value).strip().upper() if row[1].value else ''
                if aero not in my_airports:
                    continue
                if row[2].value is None:
                    break
                uso_pista = str(row[2].value).strip()
                autorizacion = str(row[3].value).strip()
                severidad = str(row[4].value).strip().upper() if row[4].value else 'WNG'
                subtipo = str(row[5].value).strip() if row[5].value else ''
                self.cmac_pistas_cerradas[(uso_pista, autorizacion)] = {
                    'subtipo': subtipo,
                    'severidad': severidad,
                }
            logging.info("CMAC_pistasCerradas: %d reglas", len(self.cmac_pistas_cerradas))

    @staticmethod
    def _parse_dms_value(val):
        """Parsea un valor DMS que puede ser numero o string con sufijo N/S/E/W."""
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if s and s[-1] in ('N', 'S', 'E', 'W', 'n', 's', 'e', 'w'):
            s = s[:-1]
        try:
            return float(s)
        except (ValueError, TypeError):
            return None


    # All fir elements should be turned into classes, just as the Hold is now


class TRANSFORM:
    def __init__(self):
        pass

    def polyline(self, obj, color, geo2NM):

        map_obj = []
        for el in ['polyline', color]:
            map_obj.append(el)
        for point in obj:
            (x, y) = geo2NM(point[1], point[0])
            for el in [x, y]:
                map_obj.append(el)

        return map_obj

    def polygon(self, obj, color, geo2NM):

        map_obj = []
        for el in ['polygon', color]:
            map_obj.append(el)
        for point in obj:
            (x, y) = geo2NM(point[1], point[0])
            for el in [x, y]:
                map_obj.append(el)

        return map_obj

    def circle(self, value, color, geo2NM):

        (x, y) = geo2NM(value[0][1], value[0][0])
        radius = float(value[1][0])

        x0 = x - radius
        y0 = y - radius
        x1 = x + radius
        y1 = y + radius

        map_obj = []
        for el in ['circulo', float(x0), float(y0), float(x1), float(y1), 0.0, float(value[2][0]), color]:
            map_obj.append(el)

        return map_obj

    def text(self, obj, types, color, geo2NM):

        map_obj = []

        (x, y) = geo2NM(obj[0][1], obj[0][0])

        if types[0] != 'Simbolos':
            obj_tp = 'texto'
        else:
            obj_tp = 'simbolo'
        if len(types[1]) == 2:
            lon = 'NDB'
        elif len(types[1]) == 3:
            lon = 'VOR'
        else:
            lon = 'FIX'

        if obj_tp != 'texto':
            for el in [obj_tp, x, y, lon, color]:
                map_obj.append(el)
        else:
            for el in [obj_tp, x, y, types[1], color, 'sw']:
                map_obj.append(el)

        return map_obj

    def arc(self, value, color, geo2NM):

        xypoint = []
        for pnt in value:
            (x, y) = geo2NM(pnt[1], pnt[0])
            xypoint.append((x, y))
        centre = (xypoint[0][0], xypoint[0][1])
        p1 = (xypoint[1][0], xypoint[1][1])
        p2 = (xypoint[2][0], xypoint[2][1])
        (radius, azim1) = rp(r(p1, centre))
        (radius, azim2) = rp(r(p2, centre))
        if azim2 < azim1:
            azim2 += 360.0
        coord_list = []
        coord_azim = s(centre, pr((radius, azim1)))
        coord_list.append(coord_azim[0])
        coord_list.append(coord_azim[1])
        for azim in range(int(azim1) + 1, int(azim2), 10):
            coord_azim = s(centre, pr((radius, azim)))
            coord_list.append(coord_azim[0])
            coord_list.append(coord_azim[1])
        coord_azim = s(centre, pr((radius, azim2)))
        coord_list.append(coord_azim[0])
        coord_list.append(coord_azim[1])
        obj = ['polyline', color]
        for coord in coord_list:
            obj.append(coord)

        return obj

    def circumference(self, value, color, geo2NM):
        (x, y) = geo2NM(value[0][1], value[0][0])
        radius = float(value[1][0])
        centre = (x, y)
        coord_list = []
        for azim in range(0, 370, 10):
            coord_azim = s(centre, pr((radius, float(azim))))
            coord_list.append(coord_azim[0])
            coord_list.append(coord_azim[1])

        obj = ['polyline', color]
        for coord in coord_list:
            obj.append(coord)

        return obj

    def findfix(self, rte, points, geo2NM, i, flag, string):

        ord_wp = []

        if string in ['SID', 'DEP']:
            init_end_rte = [0]
        elif string == 'LND':
            init_end_rte = [len(rte) - 1]
        else:
            init_end_rte = [0, len(rte)-1]

        j = 0

        for p_rte in rte:

            fl = False
            if j in init_end_rte:
                (x, y) = geo2NM(p_rte[1], p_rte[0])
                for key, p_points in points.items():

                    if str(round(p_points[0], 4)) == str(round(x, 4)) \
                            and str(round(p_points[1], 4)) == str(round(y, 4)):
                        fl = True
                        if flag:
                            if p_rte[2] is not None:
                                ord_wp.append(str(key) + str(p_rte[2]))
                                break
                            else:
                                ord_wp.append(str(key))
                                break
                        else:
                            ord_wp.append(str(key))

            if fl:
                pass
            else:
                if flag and p_rte[2] is not None:
                    ord_wp.append('p' + str(i) + str(p_rte[2]))
                else:
                    ord_wp.append('p' + str(i))
                i += 1
            j += 1

        return ord_wp

class FIR:
    """FIR information and processess"""
    def __init__(self, fir_file):
        """Create a FIR instance"""
        datos_escenario = ESCENARIO(fir_file)
        transformation = TRANSFORM()
        self.file = fir_file

        self.pos = self.GetPointCoordinates  # Method alias

        Route.fir = self

        # Following properties added in order to read taxiway files

        self.arpcoords = (0.0, 0.0)  # coordinates of the arp in NM (longitud, latitud)
        self.field_up = 0.0  # Alternate plot up-orientation for surface radar

        self.coords = {}  # Dictionary with point coordinates
        self.rel_points = {}  # Dictionary of points relative to another Format:[RELATIVE_POINT NAME]:[POINT_NAME],
        # [RADIAL],[DISTANCE]
        self.local_maps = {}  # Dictionary of local maps
        self.aerodromes = {}  # Dictionary of AD_HP objects
        self.tramos = {}
        self._sector_sections = {}  # Section name of each sector
        self.boundaries = {}  # List of boundary points for each sector
        self.min_sep = {}  # Minimum radar separation for each sector
        self.ifr_auto_approach = {}  # Whether there are autodepartures for each sector
        self.sacta_mode = {}  # Select sacta_mode for each sector
        self.lvl_min = {}
        self.lvl_max = {}
        self.frequency = {}
        self.fijos_impresion = {}
        self.fijos_impresion_bahia = {}
        self.fijos_impresion_secundarios = {}
        self.local_ads = {}
        self.release_required_ads = {}
        self.iaps = {}  # Instrument Approach Procedures

        self.sectors = []  # List of sector names
        self.holds = []  # List of published holds (See Hold class)
        self.points = []  # List of geo coordinates of points
        self.geo2NMscale = []  # scales to convert from degrees to NM
        self.local_maps_order = []
        self.iafs = []

        # 1 arc-minute in latitude equals 1NM
        # 1 arc-minute in longitude varies with the latitude of the reference point
        self.geo2NMscale = (datos_escenario.Cx0, datos_escenario.Cy0)  # factor de escala
        self.x0 = datos_escenario.x0
        self.y0 = datos_escenario.y0

        self.name = str(os.path.basename(self.file))[0:-5]
        self.field_up = datos_escenario.field_up
        self.dec_mag = radians(datos_escenario.dec_mag)
        self.gates = datos_escenario.gates  # Sheet Escenario: puertas
        self.hp = datos_escenario.hp  # Sheet Escenario: Holding Points
        self.zonasOSF = datos_escenario.zonasOSF  # Sheet Excenario: OSF zonas
        self.state_to_bahia = datos_escenario.state_to_bahia  # Sheet OSF
        self.osf_layouts = datos_escenario.osf_layouts  # Sheet OSF_Layout (fichas normales)
        self.osf_ext_layouts = datos_escenario.osf_ext_layouts  # Sheet OSF_Layout (fichas extendidas)
        self.aps = datos_escenario.ap
        self.ap = datos_escenario.ap
        self.cob_radar_inf = datos_escenario.cob_radar_inf
        self.taxi_ias = datos_escenario.taxi_ias
        self.ifr_taxi_ias = datos_escenario.ifr_taxi_ias
        self.vfr_taxi_ias = datos_escenario.vfr_taxi_ias
        self.ret_ias = datos_escenario.ret_ias
        self.auto_map = datos_escenario.auto_map
        self.auto_map_alt = datos_escenario.auto_map_alt
        self.app_max_rod = datos_escenario.app_max_rod
        self.callsigns = self.load_callsigns()
        self.vel_cruz = datos_escenario.vel_cruz

        self.pushbacks = datos_escenario.pushbacks

        try:
            # Elevaciones
            for airp in datos_escenario.ap:
                self.aerodromes[airp] = ADHP(airp)
                self.aerodromes[airp].val_elev = float(datos_escenario.elevation)
        except ValueError:
            logging.error("Unable to save Aerodrome Elevation")

        try:
            # Published holding patterns
            for fijo, datos in datos_escenario.holdings.items():
                if datos[2] == 'D':
                    std_turns = True
                else:
                    std_turns = False
                self.holds.append(HOLD(fijo.upper(), datos[0], datos[1], std_turns))
        except ValueError:
            logging.error("Unable to save Holdings")


        self.designators(datos_escenario)

        self.localmaps_function(datos_escenario, transformation)

        self.procedures_function(datos_escenario, transformation)

        self.approach_procedures(datos_escenario)

        try:
            self._load_incw_zone_maps(datos_escenario)
        except Exception:
            logging.error("Unable to load INCW zones", exc_info=True)
            self.incw_zones = {}

        self.sector(datos_escenario)

        self.sacta(datos_escenario, transformation)

        # Parametros de escenario: valores por defecto + filas de la hoja 'Escenario'
        self.params_raw = datos_escenario.params_raw
        self.params = _default_params(self.name, self.aps, self.sectors, self.aerodromes.keys())
        _apply_param_rows(self.params, self.params_raw)
        self.sector_seq_from_sheet = datos_escenario.sector_seq_rules is not None
        if self.sector_seq_from_sheet:
            self.sector_seq_rules = datos_escenario.sector_seq_rules
        else:
            self.sector_seq_rules = list(_DEFAULT_SECTOR_SEQ_RULES)
        self.bahia_fijos_from_sheet = datos_escenario.bahia_fijos is not None
        if self.bahia_fijos_from_sheet:
            self.bahia_fijos = datos_escenario.bahia_fijos
        else:
            self.bahia_fijos = _default_bahia_fijos(self.name)
        logging.info("Parametros de escenario %s: %s", self.name, self.params)

    def param(self, key, default=None):
        """Parametro de escenario (ver FIR._PARAM_KEYS); default si no existe."""
        return getattr(self, 'params', {}).get(key, default)

    def load_callsigns(self):
        global callsigns
        cf = ConfigParser()
        try:
            cf.readfp(open(CALLSIGN_FILE, "r"))
        except:
            cf.readfp(open("../" + CALLSIGN_FILE, "r"))
        callsigns = {}
        for cs, rcs in cf.items('Callsigns'):
            callsigns[cs.upper()] = rcs.upper()
        return callsigns

    def designators(self, datos_escenario):
        try:
            # Puntos y stands del FIR
            for key in datos_escenario.air_side.keys():
                if key in ['Punto', 'DVORDME', 'VORDME', 'DME', 'NDB', 'PISTA', 'SECTOR']:
                    for sub_key, value in datos_escenario.air_side[key].items():
                        (x, y) = self.Geo2NM(value[0][1], value[0][0])
                        self.points.append([sub_key.upper(), (x, y)])
                        self.coords[str(sub_key.upper())] = (x, y)
        except ValueError:
            logging.error("Unable to save Designators data")

        try:
            for key, value in datos_escenario.stands.items():
                (x, y) = self.Geo2NM(value[0][1], value[0][0])
                self.points.append([key.upper(), (x, y)])
                self.coords[str(key.upper())] = (x, y)
        except ValueError:
            logging.error("Unable to save 'Stand' data")

    def localmaps_function(self, datos_escenario, transformation):
        try:
            color = 'white'
            map_objects = []
            for key in datos_escenario.line.keys():
                map_objects.append(transformation.polyline(datos_escenario.line[key], color, self.Geo2NM))

            self.local_maps['Linea de Costa'] = map_objects
            self.local_maps_order.append('Linea de Costa')

            map_objects = []

            for k in (datos_escenario.t_side[datos_escenario.ap[0]]).keys():
                map_objects.append(
                    transformation.polyline(datos_escenario.t_side[datos_escenario.ap[0]][k], color, self.Geo2NM))

            self.local_maps['Rodadura' + datos_escenario.ap[0]] = map_objects
            self.local_maps_order.append('Rodadura' + datos_escenario.ap[0])

            for map_section in ['TMA', 'CTA']:
                map_objects = []
                if map_section in datos_escenario.air_side.keys():
                    for key, value in datos_escenario.air_side[map_section].items():
                        map_objects.append(
                            transformation.polyline(datos_escenario.air_side[map_section][key], color, self.Geo2NM))

                    self.local_maps[map_section + datos_escenario.ap[0]] = map_objects
                    self.local_maps_order.append(map_section + datos_escenario.ap[0])
        except ValueError:
            logging.error("Unable to save LocalMaps data")

    def procedures_function(self, datos_escenario, transformation):
        # IFR Runways
        ad = None
        for airp in datos_escenario.ap:
            ad = self.aerodromes[airp.upper()]
        for rwy in datos_escenario.rwys:
            ad.rwy_direction_list.append(RWYDIRECTION(rwy))

        # First runway if the preferential
        ad.rwy_in_use = ad.rwy_direction_list[0]

        # SID and STAR procedures
        for ad, rwy_direction in ((ad, rwy) for ad in self.aerodromes.values() for rwy in
                                  ad.rwy_direction_list):

            # Procedures -> SID
            if 'SI' in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig].keys():
                index = 0

                for (sid_desig, sid_points) in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig]['SI'].\
                        items():
                    index += 1
                    sid_desig = sid_desig.upper()
                    rwy_direction.sid_dict[sid_desig] = SID(sid_desig, sid_points, self.coords,
                                                            transformation, self.Geo2NM, index)

            # Procedures -> STAR
            if 'ST' in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig].keys():
                index = 0

                for (star_desig, star_points) in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig]['ST'].\
                        items():
                    index += 1
                    star_desig = star_desig.upper()
                    rwy_direction.star_dict[star_desig] = STAR(star_desig, star_points, self.coords, transformation,
                                                               self.Geo2NM, index)

            # Procedures -> DEP & LND
            if 'DEP' in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig].keys():
                try:
                    for park, points in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig]['DEP'].items():
                        rwy_direction.dep_dict[park] = DEP(park, points, self.coords, transformation, self.Geo2NM)
                except ValueError:
                    logging.error("Unable to save DEP procedures")

            if 'LND' in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig].keys():
                try:
                    for park, points in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig]['LND'].items():
                        rwy_direction.lnd_dict[park] = LND(park, points, self.coords, transformation, self.Geo2NM)
                except ValueError:
                    logging.error("Unable to save LND procedures")

    def approach_procedures(self, datos_escenario):

        com_points = None
        mis_points = None
        # Instrument Approach Procedures -> APP
        for ad, rwy_direction in ((ad, rwy) for ad in self.aerodromes.values() for rwy in ad.rwy_direction_list):

            # Procedimientos aproximacion: PUNTOS ESPECIFICOS + PUNTOS COMUNES (C)  + LLZ (LLZ) + FRUSTRADA (MIS)
            if 'IA' in datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig].keys():
                apps = datos_escenario.procedures[ad.code_id][rwy_direction.txt_desig]['IA']
                points = apps['LLZ']
                (x, y) = self.Geo2NM(points[0][1], points[0][0])
                llz_points = [(x, y), float(points[0][2]), float(points[0][3]),
                              float(points[0][4]), float(points[0][5])]

                for app_name, phases in apps.items():  # APPROX. & PHASES(MIS, COM
                    if str(app_name) == 'LLZ':
                        pass
                    else:
                        for phase, points in phases.items():
                            if str(phase) == 'C':
                                com_points = points
                            elif str(phase) == 'MIS':
                                mis_points = points
                            else:
                                pass
                        iaps = {}
                        for phase, points in phases.items():
                            if str(phase) in ['C', 'MIS']:
                                pass
                            elif 'VFR' in str(phase) or '_3_' in str(phase) or '_1_' in str(phase):
                                iaps[str(phase).upper()] = points
                            else:
                                iaps[str(phase).upper()] = (points + com_points)
                        i = 100
                        for iap_name, pnts in iaps.items():
                            lst1 = []
                            for point in pnts:
                                if point[3] == 'AGL':
                                    elev = datos_escenario.elevation * 100
                                else:
                                    elev = 0
                                (x, y) = self.Geo2NM(point[1], point[0])
                                fl = False
                                key = None
                                if point == pnts[0]:
                                    for key, p_points in self.coords.items():
                                        if str(round(p_points[0], 4)) == str(round(x, 4)) and str(
                                                round(p_points[1], 4)) == str(round(y, 4)):
                                            if point == pnts[0] and '_1_' not in key and '_3_' not in key:
                                                lst1.append(((x, y), str(key)+'*', '', float(point[2]+elev) if point[2] is not None else None))
                                            else:
                                                lst1.append(((x, y), str(key), '', float(point[2]+elev) if point[2] is not None else None))
                                            fl = True
                                            break
                                    if not fl:
                                        if point == pnts[0] and '_1_' not in key and '_3_' not in key:
                                            lst1.append(((x, y), str(key)+'*', '', float(point[2]+elev) if point[2] is not None else None))
                                        else:
                                            lst1.append(((x, y), str(key), '', float(point[2]+elev) if point[2] is not None else None))
                                else:
                                    lst1.append(((x, y), str(i), '', float(point[2]+elev) if point[2] is not None else None))
                                i += 1

                            lst2 = []
                            for point in mis_points:
                                if point[3] == 'AGL':
                                    elev = datos_escenario.elevation * 100
                                else:
                                    elev = 0
                                (x, y) = self.Geo2NM(point[1], point[0])

                                if point[0] == mis_points[-1][0] and point[1] == mis_points[-1][1]:
                                    fl = False
                                    for key, p_points in self.coords.items():
                                        if str(round(p_points[0], 4)) == str(round(x, 4)) and str(
                                                round(p_points[1], 4)) == str(round(y, 4)):
                                            lst2.append(((x, y), str(key)+'*', '', float(point[2]+elev) if point[2] is not None else None))
                                            fl = True
                                            break
                                    if not fl:
                                        lst2.append(((x, y), str(i)+'*', '', float(point[2]+elev) if point[2] is not None else None))
                                else:
                                    lst2.append(((x, y), str(i), '', float(point[2]+elev) if point[2] is not None else None))
                                    i += 1

                            rwy_direction.iaps[iap_name] = (lst1, llz_points, lst2)
                            self.iafs.append(iap_name.upper())

    def _load_incw_zone_maps(self, datos_escenario):
        """Carga zonas INCW desde datos del Excel de escenario y las registra como capas de mapa.

        Lee datos de datos_escenario.incw_areas (cargados de hoja INCWareaIncur).
        Tres capas: 'INCW NO-LVP' (verde), 'INCW LVP' (amarillo), 'INCW ALIN' (blanco).
        Tambien guarda self.incw_zones para uso en point_within_polygon() en runtime.

        Las zonas LVP y NO-LVP son compartidas por pistas reciprocas (02=20, 06L=24R, etc.)
        Se dibujan una sola vez y las etiquetas se colocan en el centroide de cada zona ALIN
        (que es unica por cabecera y esta cerca del umbral correspondiente).
        """
        self.incw_zones = {}  # {(pista, tipo): [(x_nm, y_nm), ...]} para runtime

        # Propagar datos INCW de ESCENARIO a FIR para uso en alertas (incw_engine)
        self.incw_params = getattr(datos_escenario, 'incw_params', {})
        self.incw_param_pista = getattr(datos_escenario, 'incw_param_pista', {})
        self.incw_pistas_cruzadas = getattr(datos_escenario, 'incw_pistas_cruzadas', [])
        self.incw_alert_indiv = getattr(datos_escenario, 'incw_alert_indiv', {})
        self.incw_mult_en_uso = getattr(datos_escenario, 'incw_mult_en_uso', {})
        self.incw_mult_no_en_uso = getattr(datos_escenario, 'incw_mult_no_en_uso', {})
        self.incw_mult_cerrada = getattr(datos_escenario, 'incw_mult_cerrada', {})
        self.incw_conf_opuesto = getattr(datos_escenario, 'incw_conf_opuesto', {})

        # Propagar datos CMAC de ESCENARIO a FIR para uso en alertas (cmac_engine)
        self.cmac_params = getattr(datos_escenario, 'cmac_params', {})
        self.cmac_subtypes = getattr(datos_escenario, 'cmac_subtypes', {})
        self.cmac_pistas_cerradas = getattr(datos_escenario, 'cmac_pistas_cerradas', {})

        # Propagar datos CATC de ESCENARIO a FIR para uso en alertas (catc_engine)
        self.catc_subtypes = getattr(datos_escenario, 'catc_subtypes', [])

        if not datos_escenario.incw_areas:
            logging.info("INCW: sin zonas de proteccion (hoja INCWareaIncur vacia o ausente)")
            return

        def dms_to_dec(dms_val, is_lon=False):
            """Convierte DDMMSS.sss (lat) o DDDMMSS.sss (lon) a grados decimales."""
            if is_lon:
                d = int(dms_val / 10000)
                remainder = dms_val - d * 10000
            else:
                d = int(dms_val / 10000)
                remainder = dms_val - d * 10000
            m = int(remainder / 100)
            s = remainder - m * 100
            return d + m / 60.0 + s / 3600.0

        def convert_to_nm(pts_dms):
            """Convierte lista de puntos DMS a coordenadas NM."""
            pts_nm = []
            for lat_dms, lon_dms in pts_dms:
                lat_dec = dms_to_dec(lat_dms)
                lon_dec = dms_to_dec(lon_dms, is_lon=True)
                x, y = self.Geo2NM(lat_dec, lon_dec)
                pts_nm.append((x, y))
            return pts_nm

        def make_polyline(pts_nm, color):
            """Crea objeto polyline cerrada para local_maps."""
            coords = []
            for x, y in pts_nm:
                coords.extend([x, y])
            coords.extend([pts_nm[0][0], pts_nm[0][1]])
            return ['polyline', color] + coords

        # Recopilar todas las pistas
        pistas = set()
        for key in datos_escenario.incw_areas:
            pistas.add(key[0])

        # --- Paso 1: Convertir TODAS las zonas a NM y guardar para runtime ---
        zones_nm = {}  # {key: [(x_nm, y_nm), ...]}
        for key, pts_dms in datos_escenario.incw_areas.items():
            if len(pts_dms) >= 3:
                pts_nm = convert_to_nm(pts_dms)
                zones_nm[key] = pts_nm
                self.incw_zones[key] = pts_nm

        # --- Paso 2: Calcular posicion de etiqueta por pista usando centroide ALIN ---
        # Cada pista tiene su propia zona ALIN cerca de su umbral
        label_pos = {}  # {pista: (cx, cy)}
        for pista in pistas:
            alin_pts = zones_nm.get((pista, 'ALIN'))
            if alin_pts:
                cx = sum(p[0] for p in alin_pts) / len(alin_pts)
                cy = sum(p[1] for p in alin_pts) / len(alin_pts)
                label_pos[pista] = (cx, cy)

        # --- Paso 3: Dibujar poligonos y etiquetas ---
        nolvp_objs = []
        lvp_objs = []
        alin_objs = []
        label_objs_nolvp = []
        label_objs_lvp = []
        label_objs_alin = []

        # Para LVP y NO-LVP: evitar dibujar poligonos duplicados (pistas reciprocas
        # comparten las mismas coordenadas). Se registra el primer punto como huella.
        drawn_polygons = {'LVP': set(), 'NO-LVP': set()}

        for pista in sorted(pistas):
            for tipo in ('NO-LVP', 'LVP', 'ALIN'):
                pts_nm = zones_nm.get((pista, tipo))
                if not pts_nm:
                    continue

                if tipo in ('LVP', 'NO-LVP'):
                    # Evitar dibujar el mismo poligono dos veces (ej: 02 y 20 comparten)
                    fingerprint = (pts_nm[0][0], pts_nm[0][1], len(pts_nm))
                    if fingerprint in drawn_polygons[tipo]:
                        # Poligono ya dibujado, pero aun asi poner etiqueta en esta cabecera
                        if pista in label_pos:
                            cx, cy = label_pos[pista]
                            color = 'green' if tipo == 'NO-LVP' else 'yellow'
                            if tipo == 'NO-LVP':
                                label_objs_nolvp.append(['texto', cx, cy, pista, color])
                            else:
                                label_objs_lvp.append(['texto', cx, cy, pista, color])
                        continue
                    drawn_polygons[tipo].add(fingerprint)

                    # Dibujar poligono
                    color = 'green' if tipo == 'NO-LVP' else 'yellow'
                    if tipo == 'NO-LVP':
                        nolvp_objs.append(make_polyline(pts_nm, color))
                    else:
                        lvp_objs.append(make_polyline(pts_nm, color))

                    # Etiqueta en posicion de la cabecera (centroide ALIN)
                    if pista in label_pos:
                        cx, cy = label_pos[pista]
                        if tipo == 'NO-LVP':
                            label_objs_nolvp.append(['texto', cx, cy, pista, color])
                        else:
                            label_objs_lvp.append(['texto', cx, cy, pista, color])

                elif tipo == 'ALIN':
                    alin_objs.append(make_polyline(pts_nm, 'white'))
                    if pista in label_pos:
                        cx, cy = label_pos[pista]
                        label_objs_alin.append(['texto', cx, cy, pista, 'white'])

        if nolvp_objs:
            self.local_maps['INCW NO-LVP'] = nolvp_objs + label_objs_nolvp
            self.local_maps_order.append('INCW NO-LVP')
        if lvp_objs:
            self.local_maps['INCW LVP'] = lvp_objs + label_objs_lvp
            self.local_maps_order.append('INCW LVP')
        if alin_objs:
            self.local_maps['INCW ALIN'] = alin_objs + label_objs_alin
            self.local_maps_order.append('INCW ALIN')

        logging.info("INCW: cargadas %d NO-LVP, %d LVP, %d ALIN zonas (%d poligonos runtime)",
                     len(nolvp_objs), len(lvp_objs), len(alin_objs), len(self.incw_zones))

    def sector(self, datos_escenario):
        try:
            for sector, elements in datos_escenario.sectors.items():
                sector_name = str(sector)
                self.sectors.append(sector_name)
                self.boundaries[sector_name] = []
                self.fijos_impresion[sector_name] = []
                self.fijos_impresion_secundarios[sector_name] = []
                self.local_ads[sector_name] = []
                self.release_required_ads[sector_name] = []

                for section, list_x in elements.items():
                    item = list_x[0][0]
                    if section == 'lvl_min':
                        if item is not None:
                            self.lvl_min[sector] = float(item)
                        else:
                            self.lvl_min[sector] = 0

                    elif section == 'lvl_max':
                        if item is not None:
                            self.lvl_max[sector] = float(item)
                        else:
                            self.lvl_max[sector] = 1000

                    elif section == 'min_sep':
                        if item is not None:
                            self.min_sep[sector] = float(item)
                        else:
                            self.min_sep[sector] = 8.0

                    elif section == 'frequency':
                        if item is not None:
                            self.frequency[sector] = float(item)
                        else:
                            self.frequency[sector] = '000.000'

                    elif section == 'local_ads':
                        if item is not None:
                            for point in list_x:
                                self.local_ads[sector].append((str(point[0])).upper())
                        else:
                            ads = []
                            self.local_ads[sector] = ads

                    elif section == 'release_required_ads':
                        if item is not None:
                            for point in list_x:
                                self.release_required_ads[sector].append((str(point[0])).upper())
                        else:
                            ads = []
                            self.release_required_ads[sector] = ads

                    elif section == 'sacta_mode':
                        if item is not None:
                            self.sacta_mode[sector] = (str(item)).upper()
                        else:
                            self.sacta_mode[sector] = 'PICT'

                    elif section == 'auto_departure':
                        if (str(item)) == 'MANUAL':
                            self.ifr_auto_approach[sector] = False
                        else:
                            self.ifr_auto_approach[sector] = True

                    elif section == 'limites':
                        if list_x[0][0] is not None:
                            for point in list_x:
                                lon, lat = self.coords[(str(point[0])).upper()]

                                self.boundaries[sector].append((lon, lat))
                        else:
                            pass

                    elif section == 'fijos_de_impresion':
                        if item is not None:
                            for point in list_x:
                                self.fijos_impresion[sector].append((str(point[0])).upper())
                        else:
                            pass

                    elif section == 'fijos_de_impresion_secundarios':
                        if item is not None:
                            for point in list_x:
                                self.fijos_impresion_secundarios[sector].append((str(point[0])).upper())
                        else:
                            pass
        except ValueError:
            logging.error("Unable to save Sectors data")

    def sacta(self, datos_escenario, transformation):
        try:
            for dat in datos_escenario.sacta_order:
                self.local_maps_order.append(dat)

            for map_section in datos_escenario.sacta.keys():
                self.local_maps[map_section] = []

                for key, value in datos_escenario.sacta[map_section].items():
                    key = key.lower().title()

                    if key == 'Arcos':
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            self.local_maps[map_section].append(transformation.arc(values[1::], self.set_maps_color(values[0]), self.Geo2NM))

                    elif key in ['Circunferencias', 'Circunferencia']:
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            self.local_maps[map_section].append(transformation.circumference(values[1::], self.set_maps_color(values[0]), self.Geo2NM))

                    elif key in ['Fijos', 'Simbolos', 'Textos']:
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            keys = [key, sub_key]

                            map_objects = transformation.text(values[1::], keys, self.set_maps_color(values[0]), self.Geo2NM)
                            self.local_maps[map_section].append(map_objects)

                    elif key in ['Circulos', 'Circulo', 'Circle', 'Circles']:
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            self.local_maps[map_section].append(transformation.circle(values[1::], self.set_maps_color(values[0]), self.Geo2NM))

                    elif key in ['Poligono', 'Poligonos', 'Polygon', 'Polygons']:
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            self.local_maps[map_section].append(transformation.polygon(values[1::], self.set_maps_color(values[0]), self.Geo2NM))
                    else:
                        for sub_key, values in datos_escenario.sacta[map_section][key].items():
                            map_objects = transformation.polyline(values[1::], self.set_maps_color(values[0]), self.Geo2NM)
                            self.local_maps[map_section].append(map_objects)
        except ValueError:
            logging.error("Unable to save SACTA data")

    def set_maps_color(self, color):
        if color is not None:
            return str(color)
        return 'white'

    def GetPointCoordinates(self, point_name):

        if point_name in self.coords.keys():
            return self.coords[point_name]
        elif re.match(r"X([-+]?(\d+(\.\d*)?|\d*\.\d+))Y([-+]?(\d+(\.\d*)?|\d*\.\d+))", point_name.upper()):
            v = re.match(r"X([-+]?(\d+(\.\d*)?|\d*\.\d+))Y([-+]?(\d+(\.\d*)?|\d*\.\d+))", point_name.upper()).groups()
            return float(v[0]), float(v[3])
        else:
            raise RuntimeError('Point %s not found in %s' % (point_name, self.file))

    def AdHasIfrRwys(self, code_id):
        return code_id in self.aerodromes.keys() \
               and len(self.aerodromes[code_id].rwy_direction_list) > 0

    def MagRotation(self, x, y):
        x_rm = cos(self.dec_mag) * x - sin(self.dec_mag) * y
        y_rm = sin(self.dec_mag) * x + cos(self.dec_mag) * y
        return x_rm, y_rm

    def DesMagRotation(self, x_rm, y_rm):
        x = cos(-(self.dec_mag)) * x_rm - sin(-(self.dec_mag)) * y_rm
        y = sin(-(self.dec_mag)) * x_rm + cos(-(self.dec_mag)) * y_rm
        return x, y

    def Geo2NM(self, lat, lon):
        x = self.arpcoords[0]+(lon-self.x0) * self.geo2NMscale[0]
        y = self.arpcoords[1]+(lat-self.y0) * self.geo2NMscale[1]
        x_rm, y_rm = self.MagRotation(x, y)
        return x_rm, y_rm

    def NM2Geo(self, x_rm, y_rm):
        x, y = self.DesMagRotation(x_rm, y_rm)
        lat = self.y0 + (y - self.arpcoords[1]) / self.geo2NMscale[1]
        lon = self.x0 + (x - self.arpcoords[0]) / self.geo2NMscale[0]
        return lat, lon

def LoadFirs(path, escenario):
    fir = None
    firs = None
    for esc in escenario:

        f = find_fir_file(path, esc + '.xlsx')
        if f is None:
            logging.warning("Unable to find FIR file "+esc+".xlsx starting from "+path)
            continue

        try:
            fir = FIR(f)

        except ValueError:
            logging.warning("Unable to read FIR file"+f, exc_info=True)
            continue

        if firs is None:
            firs = fir
        else:
            firs = Add_fir(firs, fir)

    return firs

def find_fir_file(path, filename):
    # El fichero base de la FIR (p.ej. LEMD.xlsx) puede estar en la carpeta
    # del escenario o en cualquier carpeta ancestro (los ejercicios pueden
    # anidarse en subcarpetas, p.ej. "Ejercicios PROBADOS\VR")
    current = os.path.abspath(path)
    while True:
        candidate = os.path.join(current, filename)
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent

def Add_fir(firs, fir):
    firs.aerodromes = check_len_dict(firs.aerodromes, fir.aerodromes)
    firs.ifr_auto_approach = check_len_dict(firs.ifr_auto_approach, fir.ifr_auto_approach)
    firs.boundaries = check_len_dict(firs.boundaries, fir.boundaries)
    firs.coords = check_len_dict(firs.coords, fir.coords)
    firs.fijos_impresion = check_len_dict(firs.fijos_impresion, fir.fijos_impresion)
    firs.fijos_impresion_bahia = check_len_dict(firs.fijos_impresion_bahia, fir.fijos_impresion_bahia)
    firs.fijos_impresion_secundarios = check_len_dict(firs.fijos_impresion_secundarios, fir.fijos_impresion_secundarios)
    firs.frequency = check_len_dict(firs.frequency, fir.frequency)
    firs.holds = check_len_dict(firs.holds, fir.holds)
    firs.iafs = check_len_dict(firs.iafs, fir.iafs)
    firs.local_ads = check_len_dict(firs.local_ads, fir.local_ads)
    firs.local_maps = check_len_dict(firs.local_maps, fir.local_maps)
    firs.local_maps_order = check_len_dict(firs.local_maps_order, fir.local_maps_order)
    firs.lvl_max = check_len_dict(firs.lvl_max, fir.lvl_max)
    firs.lvl_min = check_len_dict(firs.lvl_min, fir.lvl_min)
    firs.min_sep = check_len_dict(firs.min_sep, fir.min_sep)
    firs.release_required_ads = check_len_dict(firs.release_required_ads, fir.release_required_ads)
    firs.sacta_mode = check_len_dict(firs.sacta_mode, fir.sacta_mode)
    firs.sectors = check_len_dict(firs.sectors, fir.sectors)

    # Parametros de escenario: se recalculan con los aerodromos ya unidos; las filas
    # del Excel principal prevalecen sobre las del anadido.
    try:
        raw = {}
        for src in (getattr(fir, 'params_raw', {}), getattr(firs, 'params_raw', {})):
            for k, v in src.items():
                raw[k] = list(v)
        firs.params = _default_params(firs.name, firs.aps, firs.sectors, firs.aerodromes.keys())
        _apply_param_rows(firs.params, raw)
        if not getattr(firs, 'sector_seq_from_sheet', False) and getattr(fir, 'sector_seq_from_sheet', False):
            firs.sector_seq_rules = fir.sector_seq_rules
            firs.sector_seq_from_sheet = True
        if not getattr(firs, 'bahia_fijos_from_sheet', False) and getattr(fir, 'bahia_fijos_from_sheet', False):
            firs.bahia_fijos = fir.bahia_fijos
            firs.bahia_fijos_from_sheet = True
    except:
        logging.error("Unable to merge scenario parameters", exc_info=True)

    return firs

def check_len_dict(firs_atributte, fir_atributte):

    if len(fir_atributte) == 0:
        pass

    elif isinstance(fir_atributte, dict):

        if len(fir_atributte.keys()) > 1:

            for key, value in fir_atributte.items():
                if key not in firs_atributte.keys():
                    firs_atributte[key] = value
        else:
            firs_atributte[fir_atributte.keys()[0]] = fir_atributte.values()[0]

    elif isinstance(fir_atributte, list):

        for value in fir_atributte:
            if value not in firs_atributte:
                firs_atributte.append(value)

    return firs_atributte


# TODO
# There is currently no support for lat/lon coordinates, so we are using
# the non-standard attribute 'pos' to store the cartesian coordinates of objects,
# rather than the aicm standard geo_lat and geo_lon

class ADHP:  # Aerodrome / Heliport
    def __init__(self, code_id, txt_name='', pos=None, val_elev=0):
        self.code_id = code_id
        self.txt_name = txt_name
        self.pos = pos
        self.val_elev = val_elev
        self.rwy_direction_list = []
        self.rwy_in_use = None

    def get_sid_dep(self, txt_desig, pista, park):
        for rwy in self.rwy_direction_list:
            if rwy.txt_desig == pista:
                for sid in rwy.sid_dict.values():
                    if sid.txt_desig == txt_desig:
                        try:
                            taxi_dep = rwy.dep_dict[park]
                        except:
                            taxi_dep = rwy.dep_dict[random.choice(list(rwy.dep_dict.keys()))]

                        return sid, taxi_dep, rwy.txt_desig
        return None, None, None

    def get_star(self, txt_desig, pista):
        for rwy in self.rwy_direction_list:
            if rwy.txt_desig == pista:
                return [star for star in rwy.star_dict.values()
                        if star.txt_desig == txt_desig][0]


class HOLD:
    # TODO this does not reflect AICM. We need to support the whole
    # procedure_leg in order to do this
    def __init__(self, fix, inbd_track=180, outbd_time=1, std_turns=True, min_FL=000, max_FL=999):
        self.fix = fix         # The fix on which this hold is based
        self.inbd_track = inbd_track  # Inbound track of the holding pattern
        self.outbd_time = outbd_time  # For how long to fly on the outbd track
        self.std_turns = std_turns   # Standard turns are to the right
        self.min_FL = min_FL        # minimun FL at the holding pattern
        self.max_FL = max_FL        # maximun FL at the holding pattern


class RWYDIRECTION:
    def __init__(self, txt_desig):
        self.txt_desig = txt_desig  # TXT_DESIG must have between 2 and 3 characters, of which the first 2 may be any
        # digit between 0 and 9. Examples: 09, 09L, 09R, 09C, 09T, etc..
        self.sid_dict = {}
        self.star_dict = {}
        self.lnd_dict = {}
        self.dep_dict = {}
        self.iap_dict = {}
        self.iaps = {}


class STAR:
    # TODO this only covers basic AICM attributes.
    # We need to support the whole procuedure_leg object in order to
    # to support things like SLP and vertical limitations
    def __init__(self, txt_desig, rte, points, Transformaciones, geo2NM, index=0):

        ord_lst = Transformaciones.findfix(rte, points, geo2NM, 0, False, 'STAR')

        self.txt_desig = txt_desig
        self.rte = Route.Route(Route.get_waypoints(ord_lst))
        i = 0
        for wp in self.rte:
            (x, y) = geo2NM(rte[i][1], rte[i][0])
            wp._pos = (x, y)
            wp.elvl = 0.0
            i += 1
        if len(txt_desig) > 3:
            self.start_fix = txt_desig[:-2]
        else:
            self.start_fix = txt_desig

        self.index = index

    def __str__(self): return self.txt_desig


class SID:
    # TODO this only covers basic AICM attributes.
    # We need to support the whole procuedure_leg object in order to
    # to support things like SLP and vertical limitations
    def __init__(self, txt_desig, rte, points, Transformaciones, geo2NM, index=0):

        ord_lst = Transformaciones.findfix(rte, points, geo2NM, 0, False, 'SID')
        self.txt_desig = txt_desig
        self.rte = Route.Route(Route.get_waypoints(ord_lst))

        i = 0
        for wp in self.rte:

            (x, y) = geo2NM(rte[i][1], rte[i][0])
            i += 1
            wp._pos = (x, y)
            wp.elvl = 0.0

        if len(txt_desig) > 3:
            self.end_fix = txt_desig[:-2]
        else:
            self.end_fix = txt_desig
        self.index = index

    def __str__(self): return self.txt_desig


class LND:
    # TODO this only covers basic AICM attributes.
    # We need to support the whole procuedure_leg object in order to
    # to support things like SLP and vertical limitations
    def __init__(self, txt_desig, rte, points, Transformaciones, geo2NM):

        ord_lst = Transformaciones.findfix(rte, points, geo2NM, 1000, True, 'LND')

        self.txt_desig = txt_desig
        self.rte = Route.Route(Route.get_waypoints(ord_lst))
        i = 0
        for wp in self.rte:
            (x, y) = geo2NM(rte[i][1], rte[i][0])
            wp._pos = (x, y)
            wp.elvl = 0.0
            i += 1

        self.txt_fix = txt_desig

    def __str__(self): return self.txt_desig


class DEP:
    # TODO this only covers basic AICM attributes.
    # We need to support the whole procuedure_leg object in order to
    # to support things like SLP and vertical limitations
    def __init__(self, txt_desig, rte, points, Transformaciones, geo2NM):

        ord_lst = Transformaciones.findfix(rte, points, geo2NM, 1000, True, 'DEP')

        self.txt_desig = txt_desig
        self.rte = Route.Route(Route.get_waypoints(ord_lst))
        i = 0
        for wp in self.rte:
            (x, y) = geo2NM(rte[i][1], rte[i][0])
            wp._pos = (x, y)
            wp.elvl = 0.0
            i += 1

        self.txt_fix = txt_desig

    def __str__(self): return self.txt_desig


if __name__ == "__main__":
    FIR('/temp/radisplay/pasadas/Ruta-Convencional/Ruta-Convencional.fir')
