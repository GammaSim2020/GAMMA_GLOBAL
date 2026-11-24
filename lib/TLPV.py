#!/usr/bin/python
#-*- coding:iso8859-15 -*-
# $Id: TLPV.py 2355 2007-03-02 20:33:30Z rodrigo $
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
"""Tratamiento Local de Planes de Vuelo / Local Flight Plan Processing"""
import logging
import random
import datetime

import Route
import MathUtil
#import StripSeries
import Aircraft  # To use the callsign database

#random.seed(0)  # So that we can replicate the squawks created

# Constants
PENDING     = 0  # Pending
COORDINATED = 1  # Coordinated
PREACTIVE   = 2  # Preactive
ACTIVE      = 3  # Active
fir         = None  # GTA will set the proper FIR data


def sector_intersections(route):
    ## JRAR: Adding points is causing trouble with the approach, return route untouched
    # return route
    """Given a fp, add waypoints in the intersections of the route with
    the FIR sectors"""
    # rte_orig = route[:]

    # Remove previous TLPV waypoints
    # for wp in (wp for wp in rte_orig[:] if wp.type==Route.TLPV):
    #    rte_orig.remove(wp)
    # JRAR: the code above was removing the wrong point if it was too close
    initialised = False
    for i in range(len(route)):
        wp = route[i]
        if wp.type != Route.TLPV:
            if initialised:
                rte_orig = rte_orig + Route.Route([wp])
            else:
                rte_orig = Route.Route([wp])
                initialised = True

    ep_found = False
    for i in range(len(rte_orig) - 1):
        xpoints = []
        for name, boundary in fir.boundaries.items():
            xp_list = MathUtil.get_entry_exit_points(rte_orig[i].pos(), rte_orig[i + 1].pos(), boundary)
            for xp in xp_list: xp.append(name)
            xpoints += xp_list

        xpoints.sort(lambda x, y: cmp(x[2], y[2]))  # Sort according to distance to the first waypoint
        for xp in xpoints:
            ep_found = True
            if xp[0] == MathUtil.ENTRY:
                if rte_orig[i + 1].sector_entry:
                    rte_orig[i + 1].sector_entry.append(xp[3])
                else:
                    rte_orig[i + 1].sector_entry = [xp[3]]
            else:
                if rte_orig[i + 1].sector_exit:
                    rte_orig[i + 1].sector_exit.append(xp[3])
                else:
                    rte_orig[i + 1].sector_exit = [xp[3]]

    # If the first point in the route is within a known sector, make sure we note it.
    for sector, boundary in fir.boundaries.items():
        # if MathUtil.point_within_polygon(route[0].pos(), boundary):
        #    route[0].sector_entry = sector
        # JRAR: working internally with rte_orig
        # JRAR: the point could be inside two sectors if they intersect or one is inside the other
        if MathUtil.point_within_polygon(rte_orig[0].pos(), boundary):
            if rte_orig[0].sector_entry:
                rte_orig[0].sector_entry.append(sector)
            else:
                rte_orig[0].sector_entry = [sector]
            # No added point
            # n_added += 1

   # if not ep_found:
   #     logging.info("No sector entry points found in route")

    # return route  # Eliminates redundancy
    # JRAR: working internally with rte_orig
    return rte_orig


def get_exit_ades(flight):
    """Given an Aircraft or a flight plan returns either a the first three letters of the last waypoint
    local to the FIR, or the last two letters of the adep local to the FIR"""
    if flight.ades in fir.aerodromes.keys():
        return "TW" + flight.ades[-2:] + "_"
    # Else
    fet = None
    # If it's a TLPV flight plan and fir_exit_t is already calculated:
    if hasattr(flight, 'fir_exit_t') and flight.fir_exit_t: fet = flight.fir_exit_t
    else:
        try:    fet = max([wp.eto for wp in flight.route if wp.sector_exit])
        except: fir_exit_t = None
    #################################### To put the name of the runway "32L/32R/36L/36R" in the "echo" field##########################################
    # if flight.adep in ('LEMD','LEME','LEBL'):
    #     return ''
    # if flight.ades in ('LEMD','LEME','LEBL'):
    #     return flight.park[0:]
    #######################################################################################################################
    if fet:
        exit_wp = [wp for wp in flight.route if wp.eto >= fet and wp.type==Route.WAYPOINT][0]
        if exit_wp.fix in fir.coords.keys():
            return exit_wp.fix[:3]
        else:
            return flight.route[-1].fix[:3]

    else:
        logging.debug("Unable to find exit or ades for %s"%flight.callsign)
        return flight.campo_eco

def get_stand_sid(flight):
    if flight.adep in fir.aerodromes.keys() and flight.sid is not None:
        return flight.sid.txt_desig
    elif flight.ades in fir.aerodromes.keys():

        return flight.park #Joserra OSF LEMD
    else:
        return flight.sid_desig #Joserra OSF LEMD

def get_rwy(flight):
    if flight.ades in fir.aerodromes.keys():
            return flight.rdes
    elif flight.adep in fir.aerodromes.keys():
        return flight.rdep
    else:
        return flight.lrwy

class TLPV:
    """Keeps track of flight plans in the system"""
    # TODO in order to keep the implementation simple there cannot be two
    # flightplans sharing the same callsign
    
    def __init__(self, exercise_name=''):
        self.squawks = []  # List of xpndr codes already assigned
        self.flightplans = []  # List of known flightplans
        self.exercise_name = exercise_name
        self.fir = fir
        # Minutos de preimpresion: parametros de escenario preimpresion_arr / preimpresion_dep
        # (por defecto 30/30; LEMD, LEBL y BarcelonaTWR 10/2)
        self.preprint_mins_arr = self.fir.param('preimpresion_arr', 30)
        self.preprint_mins_dep = self.fir.param('preimpresion_dep', 30)
        pass
    
    def create_fp(self, callsign, type, fr, adep, ades, rfl, ecl, rte, sid_desig, star_desig, park,
                 eobt=None, next_wp=None, next_wp_eto=None, init=True):
        """Creates a new flight plan
        Either the eobt or (next_wp and eto) are mandatory in order to calculate estimates"""

        fp = FlightPlan(callsign, type, fr, adep, ades, rfl, ecl, rte, sid_desig, star_desig, park,
                        eobt=eobt, next_wp=next_wp, next_wp_eto=next_wp_eto)
        self.flightplans.append(fp)
        
        # Assign a squawk code
        fp.squawk = self.get_squawk(fr)
        
        # Calculate intersections with sectors
        # fp.route = sector_intersections(fp.route)
        
        # Save sector entry times for each flight plan
        fp.sector_sequence = []

        # DCM: prueba CLD para LEBL. Homogeneizar si funciona
        # if fp.adep in ('LEBL'):
        #     fp.sector_sequence.append('CLD')

        for wp in fp.route:
            initial_wp = fp.route[0]  # Get the initial wp to obtain the sector that contains all the sectors
            if wp.eto != None:
                last_eto = wp.eto
            if wp.sector_entry:
                for sector_entry in wp.sector_entry:
                    # Check: Si estoy dentro del sector en altitud comparando wp.elvl con fir.lvl_max and fir.lvl_min
                    lvl_max = fir.lvl_max[sector_entry]
                    lvl_min = fir.lvl_min[sector_entry]
                    if not wp.elvl:
                        wp.elvl = 0.0
                    if wp.elvl <= lvl_max and wp.elvl >= lvl_min:
                        if sector_entry not in fp.sector_entry_t.keys():
                            # JRAR: For local arrivals there are no estimates after the IAF
                            if wp.eto != None:
                                fp.sector_entry_t[sector_entry] = wp.eto
                                fp.sector_sequence.append(sector_entry)
                                # Done at the beginning
                                # last_eto = wp.eto
                            else:
                                fp.sector_entry_t[sector_entry] = last_eto
                                fp.sector_sequence.append(sector_entry)

                            if fp.adep in self.fir.local_ads[sector_entry]:
                                fp.fs_print_t[sector_entry] = fp.eobt-datetime.timedelta(minutes=self.preprint_mins_dep)
                            else:
                                fp.fs_print_t[sector_entry] = fp.sector_entry_t[sector_entry]-datetime.timedelta(minutes=self.preprint_mins_arr)
                                #JOSERRA: _LLZ print time used for arrivals in OSF
                                if wp.fix == "_LLZ":
                                    fp.fs_print_t["_LLZ"] = fp.sector_entry_t[sector_entry] - datetime.timedelta(
                                        minutes=self.preprint_mins_arr)
            if wp.sector_exit:
                for sector_entry in wp.sector_exit:
                    ## Check: Si estoy dentro del sector en altitud comparando wp.elvl con fir.lvl_max and fir.lvl_min
                    lvl_max = fir.lvl_max[sector_entry]
                    lvl_min = fir.lvl_min[sector_entry]

                    if wp.elvl <= lvl_max and wp.elvl >= lvl_min:
                        if sector_entry not in fp.sector_entry_t.keys():
                            # JRAR: For local arrivals there are no estimates after the IAF
                            if wp.eto != None:
                                fp.sector_entry_t[sector_entry] = wp.eto
                                fp.sector_sequence.append(sector_entry)
                                # Done at the beginning
                                # last_eto = wp.eto
                            else:
                                fp.sector_entry_t[sector_entry]=last_eto
                                fp.sector_sequence.append(sector_entry)

                            if fp.adep in self.fir.local_ads[sector_entry]:
                                fp.fs_print_t[sector_entry] = fp.eobt-datetime.timedelta(minutes=self.preprint_mins_dep)
                            else:
                                fp.fs_print_t[sector_entry] = fp.sector_entry_t[sector_entry]-datetime.timedelta(minutes=self.preprint_mins_arr)
#############################PARTE CONFLICTIVA PARA ESCENARIOS QUE NO SEAN LEMG
#            elif wp.sector_entry == None:
#                if wp.sector_exit != None:
#                    try :sector_entry = initial_wp.sector_entry[0] #Sector that contains all the sectors
#                    except: sector_entry = fp.sector_sequence[0]
#                    fp.sector_entry_t[sector_entry]=wp.eto
#                    lvl_max = fir.lvl_max[sector_entry]
#                    lvl_min = fir.lvl_min[sector_entry]
#                    try: lvl = wp.elvl
#                    except: lvl = 0
#                    if int(lvl) <= int(lvl_max) and int(lvl) >= int(lvl_min):
#                        fp.sector_sequence.append(sector_entry)
        # As there is not yet support for a proper FIR boundary in fir.py,
        # we define the first sector entry time as the FIR entry time
        try:    fp.fir_entry_t = min(fp.sector_entry_t.values())
        except: fp.fir_entry_t = None
        if fp.ades not in fir.aerodromes.keys():
            try: fp.fir_exit_t = max([wp.eto for wp in fp.route if wp.sector_exit])
            except: fp.fir_exit_t = None
        else:  # Ades is local
            fp.fir_exit_t = None
                
        return fp

    def get_squawk(self, fr):
        """Returns a random available squawk code"""
        # NOTE In python, the int literal 010 is interpreted in octal,
        # that is, 010 (octal) equals 8 (decimal)
        # TODO this would be inefficient if we had lots of flights,
        # but should do by now considering how little flights we are dealing with
        if fr == 'IFR':
            while True:
                r = int(oct(random.randint(int('0100', 8), int('6777', 8))))  # Between 0100 and 6777 octal
                if r in self.squawks or r in range(2000, 2777):
                    continue
                else:
                    break
        else:
            while True:
                r = int(oct(random.randint(int('7001', 8), int('7777', 8))))  # Between 7001 and 7777 octal
                if r in self.squawks or r in (7500, 7600, 7700):
                    continue
                else:
                    break
        self.squawks.append(r)
        return '%04d' % r

    def register_squawk(self, code):
        """Marks an externally assigned squawk (e.g. from the exercise file)
        as taken so that get_squawk never hands out a duplicate"""
        try:
            code = int(code)
        except (TypeError, ValueError):
            return
        if code not in self.squawks:
            self.squawks.append(code)
    
    def start(self):
        """Initialize TLPV"""
        # Calculate flight strip print times
        pass
        for sector in fir.sectors:
            fpl = [fp for fp in self.flightplans if sector in fp.sector_entry_t.keys()]
            for fp in fpl:
                if fp.adep in self.fir.local_ads[sector]:
                    fp.fs_print_t[sector] = fp.eobt-datetime.timedelta(minutes=10)
                else:
                    fp.fs_print_t[sector] = fp.sector_entry_t[sector]-datetime.timedelta(minutes=10)
                
    def get_sector_flightstrips(self, sector):
        """Returns a list of FlightStripData objects containing all flight strips for the sector"""
                
        fir = self.fir
        name = self.exercise_name
        
        fs_list = []
        
        fpl = [fp for fp in self.flightplans if sector in fp.sector_entry_t.keys()]
        fpl.sort(lambda p,q: cmp(p.fs_print_t[sector], q.fs_print_t[sector]))
        for a in fpl:
                    
            # Flight Strip creation
            
            # First we determine whether this flight will pass any of the
            # primary flight strip printing points. If it doesn't, then
            # it will use the secondary flight strip printing points instead
            current_printing_fixes = fir.fijos_impresion_secundarios[sector]
            at_least_one_strip_printed = False
            for i in range(len(a.route)):
                for fix in fir.fijos_impresion[sector]:
                    if a.route[i].fix==fix:
                        current_printing_fixes = fir.fijos_impresion[sector]
                
            route = ''        
            for wp in [wp for wp in a.route if wp.type == Route.WAYPOINT]:
                if wp.fix[0]!='_' and not wp.is_geo:
                    route += wp.fix+' '
                
            def format_t(t): return '%02d%02d'%(t.hour, t.minute)
            
            # Common data
            cfd=FlightStripData()
            cfd.callsign        = a.callsign
            cfd.exercice_name   = name
            cfd.ciacallsign     = a.radio_callsign
            cfd.model           = a.type
            cfd.wake            = a.wake
            cfd.speed           = "%04d"%a.filed_tas
            cfd.responder       = "C"
            cfd.origin          = a.adep
            cfd.destination     = a.ades
            cfd.fl              = "%d"%a.rfl
            # If the plane departs from a local airport, cfl is not printed
            if a.adep in fir.local_ads[sector]:
                cfd.cfl             = ""
            else:
                cfd.cfl             = "%d"%a.ecl
            
#            cfd.cssr            = "%04o"%a.squawk
            cfd.cssr            = a.squawk
            cfd.route           = route
            cfd.park            = a.park
            cfd.sid_desig       = a.sid_desig
            cfd.star_desig      = a.star_desig
            cfd.rules           = a.fr
            cfd.fs_print_t      = a.fs_print_t[sector]
            cfd.print_time      = format_t(a.fs_print_t[sector])
            try: cfd.eobt       = format_t(a.eobt)
            except: cfd.eobt    = ''
                        
            # Print a coord flight strip if it's a departure from an AD we have to release
            if a.adep in fir.local_ads[sector] and a.fr != 'VEH':
                fd=cfd.copy()
                fd.fs_type="coord"
                fs_list.append(fd)
                # JRAR: Do not print fix flight strips for local departures in twr role
                # (parametro de escenario 'ads_sin_fichas_fijo', por defecto LEAM,LEGR)
                if a.adep in fir.param('ads_sin_fichas_fijo', []): continue

                
            # Print a flight strip for every route point which is any of the
            # current_printing_fixes
                
            if a.adep in fir.local_ads[sector]:
                prev    = a.adep
                prev_t  = format_t(a.eobt)
            else:
                prev=prev_t=''
            for i in range(len(a.route)):
                if a.route[i-1].eto != None:
                    if i>=1 and a.fir_entry_t and a.route[i-1].eto<a.fir_entry_t:
						if a.route[i].eto != None:
							prev    = 'ENTRAD'
							prev_t  = format_t(a.route[i].eto)
                    elif i>=1 and a.route[i-1].type not in (Route.TLPV, Route.FMS) and a.route[i-1].fix[0]!='_':
                        prev    = a.route[i-1].fix
                        prev_t  = format_t(a.route[i-1].eto)

                if a.route[i].fix in current_printing_fixes:
                  # Main flight strip fix 
                    fijo=a.route[i].fix
                    t = a.route[i].eto
                    try:
                        fijo_t='%02d%02d'%(t.hour, t.minute)
                    except:
                        break
                    # Find next printable waypoint
                    try:
                        j = i+1
                        while True:
                            if a.route[j].type == Route.WAYPOINT and a.route[j].fix[0]!='_':
                                next    = a.route[j].fix
                                next_t  = format_t(a.route[j].eto)
                                break
                            j += 1
                    except:
                        next    = ''
                        next_t  = ''
                    if next == '' and a.ades in fir.local_ads[sector]:
                        # Printing fix is last route point and adep is local
                        next    = a.ades
                        next_t  = ''
                    elif i<len(a.route)-1 and a.fir_exit_t and a.route[i+1].eto>a.fir_exit_t:
                        # Next waypoint marks FIR exit
                        next    = 'SALIDA'
                        next_t  = format_t(a.route[i+1].eto)
                        
                    fd                  = cfd.copy()
                    fd.prev_fix         = prev
                    fd.fix              = fijo
                    fd.next_fix         = next
                    fd.prev_fix_est     = prev_t
                    fd.fix_est          = fijo_t
                    fd.next_fix_est     = next_t
                    fd.ecl              = "%d"%a.ecl
                    fs_list.append(fd)
                    
        return fs_list
        
    def exit(self):
        self.flightplans = []
        self.squawks = []
        
    def __del__(self):
        logging.debug("TLPV.__del__")

class FlightPlan:
    def __init__(self, callsign, type, fr, adep, ades, rfl, ecl, rte, sid_desig, star_desig, park,
                 eobt=None, next_wp=None, next_wp_eto=None, init=True):

        if (next_wp and not next_wp_eto) or (not next_wp and next_wp_eto):
            raise("Unable to calculate flight profile, either the next waypoint or the eto for the next waypoint is missing")
        if not next_wp and not next_wp_eto and not eobt:
            raise("Either the EOBT, or the next waypoint and its ETO are mandatory parameters")

        self.callsign       = callsign
        self.radio_callsign = ''
        self.set_callsign(callsign)
        self.adep           = adep
        self.ades           = ades
        self.sid_desig      = sid_desig
        self.star_desig     = star_desig
        self.park           = park
        self.type           = type
        self.fr             = fr
#        self.squawk         = squawk
        self.eobt           = eobt
        self.rfl            = rfl
        self.ecl            = ecl
        self.filed_tas      = None
        self.route          = Route.Route(Route.get_waypoints(rte))
        self.next_wp        = None  # Next WP  (in SACTA terminology this is the Entry Point (Punto de Entrada)
        self.next_wp_eto    = None
        self.squawk         = None
        self.squawk_alt     = None
        self.status         = None  # Pending, Coordinated, Preactive, Active
        self.ucs            = None  # Which UCS is controlling it
        self.track          = None  # If the flight is being tracked through the TDR, this links to the Track
        self.sector_entry_t = {}    # Sector entry times for each of the sectors it traverses
        self.fs_print_t     = {}    # Printing time of the flight strips for each sector
        self.fir_entry_t    = None  # Time it first enters our FIR (local departures do count)
        self.fir_exit_t     = None  # Time it leaves the FIR (if ever)
        
    def set_callsign(self, cs):
        self.callsign = cs = cs.strip().upper()
        self.radio_callsign = Aircraft.get_radio_callsign(cs)
        
    #def __del__(self):
    #    logging.debug("FlightPlan.__del__ %s"%self.callsign)
        
class FlightStripData:
    def __init__(self):
        self.exercice_name   = ""
        self.callsign        = ""
        self.ciacallsign     = ""
        self.model           = ""
        self.wake            = ""
        self.responder       = ""
        self.speed           = ""
        self.cssr            = ""
        self.origin          = ""
        self.eobt            = ""
        self.destination     = ""
        self.fl              = ""
        self.cfl             = ""
        self.route           = ""
        self.rules           = ""
        self.prev_fix        = ""
        self.fix             = ""
        self.next_fix        = ""
        self.prev_fix_est    = ""
        self.fix_est         = ""
        self.next_fix_est    = ""
        self.print_time      = ""
        self.fs_type         = "enroute"

    def copy(self):
        fd = FlightStripData()
        fd.__dict__ = self.__dict__.copy()
        return fd