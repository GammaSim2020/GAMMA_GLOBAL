#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: Exercise.py 2256 2006-05-01 19:27:15Z toledo $
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
"""Classes useful for dealing with Exercise files"""

import logging
import os
import re
from stat import *
import cPickle
import zlib
import ConfMgr
from ConfigParser import ConfigParser
from openpyxl import load_workbook, Workbook

# CONSTANTS
CACHE_VERSION = 9
MAPPING_FILE_NAME = "exercises-passes.dat"
conf = ConfMgr.GammaConfig()


class Exercise:
    """All data representing a single exercise"""
    def __init__(self, file=None):
        if file:
            if file[-4:] == '.eje':
                self.load(file)
            else:
                self.load_excel(file)
            return
        self.file = self.fir = self.sector = self.start_time = self.shift = self.metar = self.rwys = ""
        self.sector_list = []
        self.da = self.usu = self.ejer = self.course = self.phase = self.day = self.pass_no = None
        self.wind_azimuth = self.wind_knots = 0
        self.oldcomment = self.comment = ""        
        
        self.flights = {}

    def delete_space(self, string):
        return (string.strip())

    def normalize_transp(self, value):
        """Normalize the transponder code read from the exercise file.

        Numeric cells come back from openpyxl as int/float (losing leading
        zeros and possibly gaining a trailing '.0'), so we rebuild a 4-digit
        string and validate that every digit is octal (0-7).
        Returns 'None' (the sentinel GTA expects) when the cell is empty or
        the value is invalid, so that a random squawk gets assigned."""
        if value is None:
            return 'None'
        if isinstance(value, float) and value == int(value):
            value = int(value)
        transp = str(value).strip()
        if not transp or transp == 'None':
            return 'None'
        transp = transp.zfill(4)
        if len(transp) != 4 or not all(c in '01234567' for c in transp):
            logging.warning('Invalid transponder code %r in exercise, a random squawk will be assigned' % (transp,))
            return 'None'
        return transp

    def sacta_time(self, value):
        """Calculate a flight time from a SACTA-style cell of the exercise.

        Exact same treatment for every flight time column (HoraSacta, CTOT):
        if the cell text is longer than 4 chars it is an absolute time
        ('HH:MM:SS'); otherwise it is a number of minutes to add to the
        exercise start time. Returns (hour_string, minute_string,
        second_string)."""
        if len(self.delete_space(value)) > 4:
            hour_string = self.delete_space(str(value))[0:2]
            minute_string = self.delete_space(str(value))[3:5]
            second_string = self.delete_space(str(value))[6:8]
        else:
            # second_ini = int(self.start_time[6:8])
            minute_ini = int(self.start_time[3:5])
            hour_ini = int(self.start_time[0:2])
            minute_add = int(value)
            hour_final, minute_final = self.total_time(minute_ini, hour_ini, minute_add)
            hour_string = str(hour_final).zfill(2)
            minute_string = str(minute_final).zfill(2)
            second_string = self.delete_space(str(value))[6:8]
        return hour_string, minute_string, second_string

    def total_time(self, minute_ini, hour_ini, minute_add):
        minute_addTotal = minute_ini + minute_add
        hours = abs(minute_addTotal / 60)
        minute_final = abs(minute_addTotal % 60)

        if minute_add >= 0:
            if hour_ini + hours < 24:
                hour_final = hour_ini + hours
            else:
                hour_final = (hour_ini + hours) - 24

        else:
            if hour_ini - hours > 0:
                hour_final = hour_ini - hours
            else:
                hour_final = 24 - abs(hour_ini - hours)

        return hour_final, minute_final

    def load_excel(self, file):
        import re

        book = load_workbook(filename=file, read_only=True)
        self.currentTime_start = False
        flight_rows = False
        self.flights = {}
        i_flight = 0
        self.auto_taxi = False
        for row in book['Ejercicio'].rows:
            if not flight_rows:
                if row[0].value is None:
                    pass
                elif self.delete_space(row[0].value) == 'Escenario':
                    try:
                        self.fir = (self.delete_space(str(row[1].value))).split(',')
                    except:
                        logging.warning('No FIR found for exercise %s' % file)
                elif self.delete_space(row[0].value) == 'Posicion':
                    try:
                        self.sector = self.delete_space(str(row[1].value))
                        self.sector_list = [self.sector]
                    except:
                        logging.warning('No Sector found for exercise %s' % file)

                elif self.delete_space(row[0].value) == 'Inicio':
                    try:
                        self.start_time = self.delete_space(str(row[1].value))
                    except:
                        logging.warning('Invalid Start time found for exercise %s' % file)

                elif self.delete_space(row[0].value) == 'Autotaxi':
                    self.auto_taxi = self.delete_space(str(row[1].value))
                elif self.delete_space(row[0].value) == 'METAR':
                    self.metar = self.delete_space(str(row[1].value))
                    self.qnh_ini = None
                    try:
                        patronQNH = re.compile('Q[0-9]{3,4}')
                        findQNH = patronQNH.search(self.metar)
                        self.qnh_ini = findQNH.group()
                        self.qnh_ini = self.qnh_ini.replace('Q', '')
                    except:
                        logging.warning('Invalid QNH data found for exercise %s' % file)
                    try:
                        patronWIND = re.compile('[0-9]{5,}KT')
                        findWIND = patronWIND.search(self.metar)
                        self.wind = findWIND.group()
                        self.wind = self.wind.replace('KT', '')
                        self.wind_azimuth = long(self.wind[0:3])
                        self.wind_knots = long(self.wind[3:])
                    except:
                        logging.warning('Invalid Wind data found for exercise %s' % file)

                elif self.delete_space(row[0].value) == 'Indicativo':
                    flight_rows = True
            else:
                if row[0].value is None:
                    break
                try:
                    adep = str(self.delete_space(row[4].value)[:4])
                    rdep = str(self.delete_space(row[4].value)[4:])
                    ades = str(self.delete_space(row[5].value)[:4])
                    rdes = str(self.delete_space(row[5].value)[4:])

                    data = str(self.delete_space(row[1].value)) + ',' + self.delete_space(row[2].value) + ',' + self.delete_space(row[
                        3].value) + ',' + adep + ',' + ades + ',' + rdep + ',' + rdes + \
                           ',' + self.delete_space(str(row[8].value)) + ',' + self.delete_space(str(row[10].value)) + ',' + self.delete_space(str(row[13].value))

                    # Calculate start time flights in exercise (sacta_time) ###########################################
                    hour_string, minute_string, second_string = self.sacta_time(row[12].value)
                    # fin calculo start time for all flights in exercise ###############################################

                    hfv_str = 'H' + hour_string + minute_string + second_string + 'F' + self.delete_space(str(
                        row[9].value)).zfill(3) + 'V' + self.delete_space(str(row[7].value))

                    ruta_csv = (self.delete_space(row[6].value)).replace(' ', ',')
                    fijo = self.delete_space(str(row[11].value))

                    if adep in self.fir and ades in self.fir and self.delete_space(row[3].value) != 'VEH':
                        if fijo == 'EOBT':
                            ruta = hfv_str + ',' + ruta_csv
                            fijo = self.delete_space(str(row[13].value))  # fijo = parking
                        elif fijo == 'TOMA':
                            ruta = ruta_csv + ',_LLZ,' + hfv_str
                            fijo = '_LLZ'
                        else:
                            index = ruta_csv.find(row[11].value)+len(row[11].value)
                            if index >= 0:
                                ruta = ruta_csv+','+hfv_str

                    elif adep in self.fir:
                        ruta = hfv_str + ',' + ruta_csv
                        if fijo == 'EOBT':
                            fijo = self.delete_space(str(row[13].value))  # fijo = parking

                    elif ades in self.fir:
                        if fijo == 'TOMA':
                            ruta = ruta_csv + ',_LLZ,'+hfv_str
                            fijo = '_LLZ'
                        elif fijo[0] == '>':
                            ruta = ruta_csv + ',' + fijo + ',' + hfv_str
                        else:
                            index = ruta_csv.find(row[11].value)+len(row[11].value)
                            if index >= 0:
                                ruta = ruta_csv+','+hfv_str

                    elif adep not in self.fir and ades not in self.fir:  # Sobrevuelo
                        ruta = hfv_str + ',' + ruta_csv

                    data = str(data + ',' + ruta)
                    callsign = self.delete_space(str(row[0].value))
                    transp = self.normalize_transp(row[14].value)
                    self.flights[i_flight] = Flight(callsign, data, fijo, transp, escenario=self.fir)
                    # CTOT (columna P): mismo tratamiento que la HoraSacta
                    # (columna M) via sacta_time() -> string 'HHMMSS', o ''
                    # si esta vacia. Un CTOT invalido no debe descartar el
                    # vuelo entero.
                    ctot = ''
                    ctot_cell = row[15].value if len(row) > 15 else None
                    if ctot_cell is not None:
                        try:
                            ctot_h, ctot_m, ctot_s = self.sacta_time(ctot_cell)
                            ctot = (ctot_h + ctot_m + ctot_s).ljust(6, '0')
                        except:
                            # logging.warning('Invalid CTOT %r for flight %s, ignored' % (ctot_cell, callsign))
                            ctot = ''
                    self.flights[i_flight].ctot = ctot
                    i_flight += 1
                except:
                    logging.warning("Unable to read flight "+row[0].value+" from "+str(file))
                    logging.debug("Exception data follows", exc_info=True)
        book._archive.close()

    def load(self, file):
        import re

        self.file = file
        self.auto_taxi = False
        exc = ConfigParser()
        exc.readfp(open(file, "r"))
        self.fir = exc.get('datos', 'fir')
        self.sector = exc.get('datos', 'sector')
        self.sector_list = [self.sector]
        self.start_time = exc.get('datos', 'hora_inicio')
        try: (self.wind_azimuth, self.wind_knots) = [int(x) for x in exc.get('datos', 'viento').split(",")]
        except: self.wind_azimuth, self.wind_knots = 0, 0
        try: (self.metar) = exc.get('datos', 'metar')
        except: self.metar = ""
        try: (self.rwys) = exc.get('datos', 'rwys')
        except: self.rwys = ""

        # The old comment format was in fact used to present exercises
        # in the old MainMenu.py, so we need to maintain it
        # It actually has more information than a real comment
        try:
            self.oldcomment = exc.get('datos', 'comentario')
        except:
            self.oldcomment = os.path.basename(file)
        # If the file doesn't have an actual new comment attr yet, use the old one.
        try:
            self.comment = exc.get('datos', 'comment')
        except:
            self.comment = self.oldcomment
        
        self.load_flights(exc)
        
    def load_flights(self, exc):
        """Load flights from exercise config parser instance exc"""
        file = self.file
        flightops = ()
        try:
            self.n_flights = len(exc.options('vuelos'))        
            flightopts = exc.options('vuelos')
        except:
            logging.warning("Unable to read any flights from "+file)
        self.flights = {}
        i = 0
        for flightopt in flightopts:
            try:
                self.flights[i] = Flight(flightopt, exc.get('vuelos', flightopt), escenario=self.fir)
                self.flights[i].ctot = ''  # el formato .eje no tiene CTOT
                i += 1
            except:
                logging.warning("Unable to read flight "+str(flightopt).upper()+" from "+str(file))
                logging.debug("Exception data follows", exc_info=True)
                
    def reload_flights(self):
        """Make sure flights are loaded fresh from the exercise file"""
        try:
            del(self.flights)
        except:
            pass
        try:
            exc = ConfigParser()
            exc.readfp(open(self.file, "r"))
            self.load_flights(exc)
        except:
            self.flights = {}
            logging.exception("Unable to reload flights for exercise")

    def add_flight(self, f):
        next = self.next_flight_id()
        self.flights[next] = f

    def next_flight_id(self):
        try:
            return max(self.flights.keys())+1
        except:
            return 0

    def save(self, file):
        self.file = file
        try:
            exc = ConfigParser()
            exc.readfp(open(self.file, "r"))
        except:
            logging.info("Unable to open exercise for reading prior to saving")
        
        try:
            exc.add_section('datos')
        except:
            pass
        for field in ("fir", "sector", "shift", "da", "usu", "ejer", "course", "phase", "day", "pass_no", "comment"):
            exc.set('datos', field, getattr(self, field))
        # Old field formats
        exc.set('datos', 'comentario', self.oldcomment)
        exc.set('datos', 'hora_inicio', self.start_time)
        exc.set('datos', 'viento', "%03d" % self.wind_azimuth+","+"%02d" % self.wind_knots)
        exc.set('datos', 'metar',self.metar)
        exc.set('datos', 'rwys', self.rwys)
        
        try:
            exc.add_section('vuelos')
        except:
            pass
        for f in self.flights.values():
            exc.set('vuelos', f.callsign, f.get_config_string())

        exc.write(open(self.file, "w"))
            
    def copy(self):
        e = Exercise()
        e.__dict__ = self.__dict__.copy()
        e.flights = self.flights.copy()
        for f in e.flights.keys():
            e.flights[f] = e.flights[f].copy()
        return e

    def __eq__(self, other):
        try:
            for (sa, sv) in self.__dict__.items():
                if sa == 'flights':
                    continue
                if getattr(other, sa) != sv:
                    logging.debug(sa+" differs when comparing exercises ( "+str(sv)+" "+str(type(sv))+" != "+str(getattr(other, sa))+" "+str(type(getattr(other, sa)))+" )")
                    return False
            for f in self.flights.values():
                f2 = [f2 for f2 in other.flights.values() if f2.callsign == f.callsign][0]
                if f != f2:
                    return False
            for f2 in other.flights.values():
                f = [f for f in self.flights.values() if f.callsign == f2.callsign][0]
                if f != f2:
                    return False
        except:
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

class Flight(object):
    """All data related to a specific flight within an Exercise"""
    def __init__(self, callsign=None, data=None, fijo=None, transp='None', escenario = None):
        """Construct a flight instance
        
        Instantiation arguments:
        callsign -- Flight code (eg: IBE231)
        data -- The flight data as is on the Exercise file
        """
        if callsign and data:
            self.callsign = callsign.upper()
            self._data = data
            self.adep = self.adep()
            self.ades = self.ades()
            self.rdep = self.rdep()
            self.rdes = self.rdes()
            self.park = self.park()
            self.fr = self.fr()
            self.route, self.sid_desig, self.star_desig = self.route()
            self.eto, self.firstlevel, self.tas = self.fix_eto_firstlevel_tas()
            self.fix = fijo
            self.wtc = self.wtc()
            self.rfl = self.rfl()
            self.cfl = self.cfl()
            self.type = self.type()
            self.transp = transp
            self.model_file = self.model_file(escenario=escenario)
        else:
            self.callsign = ""
            self.adep = ""
            self.rdep = ""
            self.ades = ""
            self.rdes = ""
            self.park = ""
            self.fr = ""
            self.route = ""
            self.sid_desig = ""
            self.star_desig = ""
            self.fix = ""
            self.eto = ""
            self.wtc = ""
            self.tas = ""
            self.rfl = ""
            self.firstlevel = ""
            self.cfl = ""
            self.type = ""
            self.transp = 'None'
            self.ctot = ''


    def copy(self):
        n = Flight()
        n.__dict__ = self.__dict__.copy()
        return n

    def fr(self):
        """Return the destination aerodrome"""
        data = self._data.split(',')
        return data[2]
        
    def adep(self):
        """Return the departing aerodrome"""
        data = self._data.split(',')
        return data[3]
        
    def ades(self):
        """Return the destination aerodrome"""
        data = self._data.split(',')
        return data[4]

    def rdep(self):
        """Return the departing rwy"""
        data = self._data.split(',')
        return data[5]

    def rdes(self):
        """Return the destination aerodrome"""
        data = self._data.split(',')
        return data[6]

    def park(self):
        """Return the parking"""
        data = self._data.split(',')
        return data[9]
        
    def route(self):
        data = self._data.split(',')
        route = ''
        sid_desig = ''
        star_desig = ''
        if data[3] == data[4]:  # Entra y sale del mismo sitio
            if len(data[10]) > 8:  # DEFINIDO EOBT
                for fix in data[11:]:
                    p = re.compile('[1-9][a-zA-Z]')
                    m = p.match(fix[-2:])
                    if m:  # Se ha introducido sid / star
                        route = route + fix[:-2].upper() + ','

                        if fix == data[11]:
                            sid_desig = fix.upper()
                        else:
                            star_desig = fix.upper()

                    else:
                        if fix.upper() != '_LLZ' and fix[0] != '>':
                            route = route + fix.upper() + ','

            else:   # DEFINIDO TOMA:
                for fix in data[10:-1]:
                    p = re.compile('[1-9][a-zA-Z]')
                    m = p.match(fix[-2:])
                    if m:  # Se ha introducido sid / star
                        route = route + fix[:-2].upper() + ','

                        if fix == data[-2] and fix.upper() != '_LLZ':
                            star_desig = fix.upper()
                        else:
                            sid_desig = fix.upper()

                    else:
                        if fix.upper() != '_LLZ' and fix[0] != '>':
                            route = route + fix.upper() + ','

        else:  # O HACE TOMA O HACE EOBT
            if len(data[10]) > 8:
                for fix in data[11:]:
                    # Check if one of the points specifies a SID or STAR procedure (ending with number and letter)
                    p = re.compile('[1-9][a-zA-Z]')
                    m = p.match(fix[-2:])
                    if m:  # Se ha introducido sid / star
                        route = route + fix[:-2].upper() + ','
                        sid_desig = fix.upper()

                    else:  # Se ha introducido nombre del fijo
                        if fix.upper() != '_LLZ' and fix[0]!='>':
                            route = route + fix.upper() + ','
            else:
                for fix in data[10:-1]:
                    # Check if one of the points specifies a SID or STAR procedure (ending with number and letter)
                    p = re.compile('[1-9][a-zA-Z]')
                    m = p.match(fix[-2:])
                    if m:  # Se ha introducido sid / star
                        route = route + fix[:-2].upper() + ','
                        star_desig = fix.upper()

                    else:  # Se ha introducido nombre del fijo
                        if fix.upper() != '_LLZ' and fix[0] != '>':
                            route = route + fix.upper() + ','

        # remove the last ","
        route = route[:-1]
        return route, sid_desig, star_desig

    def fix_eto_firstlevel_tas(self):
        """Return the fix for which the eto is valid"""
        import re
        data = self._data.split(',')
        route = data[10:]
        for fix, i in zip(route, range(len(route))):
            m = re.match(r"H(\d+)F(\d+)V(\d+)", route[i])
            if m:
                break
        try:
            eto = m.group(1).ljust(6, "0")  # Make sure it's six chars long, and right pad with zeroes
            firstlevel = m.group(2).rjust(3, "0")
            tas = m.group(3).rjust(3, "0")
        except:
            logging.warning("Unable to extract HFV field in '"+self._data+"'")
            raise

        return eto, firstlevel, tas
        
    def wtc(self):
        """Return the wake turbulence cat"""
        data = self._data.split(',')
        return data[1]

    def model_file(self, escenario=None):
        """Return the file containing the 3Dmodel"""
        if escenario in ['Almeria', 'Granada']:
            model_dir = os.path.join(conf.common_dir, 'models')
            lista = os.listdir(model_dir)
            m_file = self.callsign[:3] + '_' + self.type + '.glb'
            if not m_file in lista:
                m_file = self.callsign[:3] + '_' + self.type + '.gltf'
                if not m_file in lista:
                    m_file = self.type + '.glb'
                    if not m_file in lista:
                        m_file = self.type + '.gltf'
                        if not m_file in lista:
                            m_file = self.wtc + '.glb'
                            if not m_file in lista:
                                m_file = self.wtc + '.gltf'
        else:
            self.fr = self.fr.strip()
            if self.fr != 'IFR':
                m_file = self.type + '.glb'
            else:
                m_file = self.callsign[:3] + '_' + self.type + '.glb'
        # m_file = os.path.join(model_dir,m_file)
        return m_file
        
    def rfl(self):
        """Return the RFL"""
        data = self._data.split(',')
        return data[7]
        
    def cfl(self):
        """Return the CFL"""
        data = self._data.split(',')
        return data[8]
        
    def type(self):
        """Return the type"""
        data = self._data.split(',')
        return data[0]
    
    def get_config_string(self):
        try:
            s = self.type+","+self.wtc+","+self.fr+","+self.adep+","+self.ades+","+"%03d" % (int(self.rfl))+","+"%03d" % (int(self.cfl))+","+self.park
            for f in self.route.split(","):
                s += ","+f
                if f == self.fix:
                    s += ",H"+self.eto+"F"+"%03d" % (int(self.firstlevel))+"V"+"%03d" % (int(self.tas))
            return s
        except:
            logging.error("Failure to create config string for "+str(self.callsign))
            raise
    
    def __eq__(self, other):
        try:
            for (sa, sv) in self.__dict__.items():
                if getattr(other, sa) != sv:
                    logging.debug(sa+" differs when comparing flights ( "+str(sv)+" != "+str(getattr(other, sa))+" )")
                    return False
        except:
            return False
        return True
                
    def __ne__(self, other):
        return not self.__eq__(other)

    def __setattr__(self, name, value):
        """Capture attribute setting so as to force formatting"""
        object.__setattr__(self, name, value)  # This actually sets the attributes
        if name == "eto" and len(value) == 4:
            object.__setattr__(self, name, value+"00")


class RouteDB:
    """A database of routes that are known for a specific FIR"""
    
    def __init__(self):
        self._routes = {}
        
    def append(self, route, adep, ades):
        """Append a route together with the adep and ades to the DB of routes"""
        route = route.strip().replace(" ", ",")
        if route not in self._routes.keys():
          # We add the route to the database, with a frequency of one, and
          # adding the first pair of adep and ades
            self._routes[route] = (1, [adep+ades])
            # logging.debug("New route: "+route)
        else:
          # If the route already exists, we increment the frequency for the route
          # and if the orig_dest pair is new, add it to the list.
            (frequency, orig_dest_list) = self._routes[route]
            frequency = frequency+1
            if (adep+ades) not in orig_dest_list:
                orig_dest_list.append(adep+ades)
            self._routes[route] = (frequency, orig_dest_list)
            
    def size(self):
        """Return the number of known routes"""
        len(self._routes)
        
    def matching_routes(self, fix_list, adep, ades):
        """Given a list of points, and optional adep and ades airports, return
        a sorted list of possible matching routes"""
        match_routes = self._routes.copy()
        potential_discards = []
        # Routes must contain the given fixes in the same order
        for route in match_routes.keys():
            i = 0
            rs = route.split(',')
            for f in rs:
                if f == fix_list[i]:
                    i = i+1
                    if i == len(fix_list):
                        break
            # If we have given a list of fixes, and we did not find them all in order,
            # remove the route. But it's OK if the list was empty to begin with
            # (meaning that we DO want to see all the available options).
            if i < len(fix_list) and fix_list[0] != '':
                del match_routes[route]
                continue
            
            # Remove the route if it has the origin AD as the first route point
            if adep == route.split(",")[0]:
                del match_routes[route]
                continue

            # Mark for discarding routes that neither begin nor end on the
            # given adep and ades
            (f, orig_dest_list) = match_routes[route]
            if adep != '' or ades != '':
                for od in orig_dest_list:
                    if not (adep == '' or adep == od[0:4]) and not (ades == '' or ades == od[4:8]):
                        if route not in potential_discards:
                            potential_discards.append(route)
                        break
                            
        # Only discard routes based on adep and ades when it doesn't remove
        # all of our options
        if len(potential_discards) < len(match_routes):
            for d in potential_discards:
                del match_routes[d]
                
        # Out of the remaining routes, we need to sort them first according to whether
        # it is appropriate for the adep-ades pair, and then frequency 
        sorted_routes = []
        for (route, (frequency, orig_dest_list)) in match_routes.items():
            if (adep+ades) in orig_dest_list:
                # Both origin and ades matches gives the highest score
                matches_orig_dest = 2
            else:
                # No matching whatsoever gives the lowest score
                matches_orig_dest = 0
                for od in orig_dest_list:
                    if (adep == od[0:4]) or (ades == od[4:8]):
                        # But if either the adep or ades matched we get partial score
                        matches_orig_dest = 1
            sorted_routes.append([matches_orig_dest, frequency, route])
        sorted_routes.sort(reverse=True)
        logging.debug(sorted_routes)
        for i in range(len(sorted_routes)):
            sorted_routes[i] = sorted_routes[i][2]
        return sorted_routes        


def hhmmss_to_hhmm(s):
    """Given a string formated as hhmmss return a string formated to hhmm correctly rounded"""
    import datetime
    dt = datetime.datetime.today()
    dt = dt.replace(hour=int(s[0:2]), minute=int(s[2:4]), second=int(s[4:]))
    dt += datetime.timedelta(seconds=30)
    return dt.strftime("%H%M")


def export_callsigns(el, filename, reload=True):
    """Creates a tab separated value file containing the callsigns of the
    actual flights used in the exercices"""
    if reload:
        for e in el:
            e.reload_flights()
    
    csl = [f.callsign.strip("*")[:3] for e in el for f in e.flights.values()]
    callsigns = {}
    cp = ConfigParser()
    cp.readfp(open("Modelos_avo.txt"))
    for cs in cp.options("indicativos_de_compania"):
        callsigns[cs.upper()] = cp.get('indicativos_de_compania', cs)
    
    csd = {}
    for cs in csl:
        try:
            csd[cs][0] += 1
        except:
            try:
                csd[cs] = [1, callsigns[cs]]
            except:
                csd[cs] = [1, ""]
    
    f = open(filename, "w")
    
    for code, (n, cs) in csd.items():
        f.write(code+"\t"+cs+"\t"+str(n)+"\n")
