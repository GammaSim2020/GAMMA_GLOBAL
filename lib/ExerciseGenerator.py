#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: GTA.py 2381 2007-05-30 19:32:42Z rodrigo $

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


# System imports
from time import time, sleep
import logging

import cPickle

pickle = cPickle
import random
import os
from MathUtil import *
import ConfMgr

conf = ConfMgr.GammaConfig()

# Application imports
import Timeline
import datetime
import openpyxl
import ttk
import shutil
import GTA
import numpy as np

# Constants
import sys

if sys.version_info[0] == 2:

    import Tix as tix
    import Tkconstants
    import Tkinter as tk

elif sys.version_info.major == 3:
    import tkinter.tix as tix

WINDOW_BG = '#FFFFFF'  # white
STRIP_BG_DEP = 'deepskyblue'
STRIP_BG_NODEP = 'yellow2'
TABLE_BG = 'slateGray1'
TABLE_LABEL = 'NavajoWhite2'


def fill_pvs(self, Hour, Fix, LstPvs):
    FontStyle = 'Arial 8 bold'

    w = 16
    x = 8

    ColorGround = 'gray'
    IniAux = True
    FixAux = Fix

    for pv in LstPvs:

        if self.Fl:  # No Vengo de eliminar/ copiar/ carga inicio

            if not self.c:  # No conflicto
                if FixAux == '':
                    Fix = pv[10]
                FlConf = False
                ColorFont = 'DeepSkyBlue2'
                TypeConf = ''
                TypeSol = ''
                Hour = pv[11]

            else:  # Conflicto
                if IniAux:
                    FlConf = True
                ColorFont = 'navy'
                TypeConf = self.CboxFil_2.get()
                TypeSol = self.CboxFil_5.get()

        else:  # Vengo de eliminar/ copiar/ carga inicio

            Fix = pv[10]
            Hour = pv[11]
            TypeConf = pv[12]
            TypeSol = pv[13]

            if TypeConf != '':
                if IniAux:
                    FlConf = True
                ColorFont = 'navy'


            else:
                FlConf = False
                ColorFont = 'DeepSkyBlue2'

        CellBaseEntry = tix.Entry(self.frame_in, justify=tix.CENTER, width=10, foreground=ColorFont,
                                  selectbackground=ColorGround, highlightcolor=ColorGround,
                                  font=('Arial 14 bold'))

        CellBaseEntry.insert(0, 'PV ' + str(self.Cont))
        CellBaseEntry.grid(row=self.z, column=0, pady=x)

        Entrys = []
        Entrys.append(CellBaseEntry)
        col = 1

        for element in pv:

            if col == 11:
                element = Fix
            if col == 12:
                element = Hour
            if col == 13:
                element = TypeConf
            if col == 14:
                element = TypeSol

            CellBaseEntry = tix.Entry(self.frame_in, justify=tix.CENTER, width=w, foreground=ColorFont,
                                      selectbackground=ColorGround, font=(FontStyle))
            CellBaseEntry.insert(0, element.replace("'", "").replace('"', "").replace("[", "").replace("]", ""))
            CellBaseEntry.grid(row=self.z, column=col, pady=x)

            if col == 6:
                CellBaseEntry.config(width=50)
                CellBaseEntry.bind("<Button-3>", lambda event, i=self.z: self.showLabelRoute(i, x, True))
                CellBaseEntry.bind('<Return>', lambda event, i=self.z: self.showLabelRoute(i, x, False))

            Entrys.append(CellBaseEntry)
            col += 1

        if FlConf:

            FlConf = False
            IniAux = False

        else:

            IniAux = True
            btnSelectRow = tix.Label(self.frame_in, text="Del", bg=TABLE_BG, font=('Helvetica 8'))
            btnSelectRow.grid(row=self.z, column=15, padx=4, pady=x)
            btnSelectRow.bind("<Button-1>", lambda event, i=self.z: self.del_flight(i))

            btnSelectRow = tix.Label(self.frame_in, text="Cpy", bg=TABLE_BG, font=('Helvetica 8'))
            btnSelectRow.grid(row=self.z, column=16, pady=x)
            btnSelectRow.bind("<Button-1>", lambda event, i=self.z: self.copy_flight(i))

        self.Pvs.append(Entrys)
        self.z += 1
        self.Cont += 1

    self.externalcanvas.update_idletasks()
    self.externalcanvas.config(scrollregion=self.externalcanvas.bbox(tix.ALL))

class InterfaceCommElements(object):

    def __init__(self):
        '''

            Init variables from database and Ais designators files

        '''

        self.AvailablePvListAux = []   # Lista Auxiliar para almacenar pvs del databasefile.txt
        self.AvailablePvList = []      # Lista vuelos de la base de datos
        self.FilteredPvList = []       # Lista vuelos que cumplen filtros del usuario
        self.LabAux = []              # Lista Auxiliar para almacenar etiquetas del databasefile.txt
        self.Departure = []            # Lista Filtrada con todos los puntos de origen disponibles en la base de datos
        self.Destination = []          # Lista Filtrada con todos los puntos de destino disponibles en la base de datos
        self.Routes = []               # Lista con todas las rutas disponibles en la base de datos filtradas con los puntos
                                       # actualizados del Aisfile.xlsx
        self.Fixes = []                # Lista Filtrada con todos los fijos disponibles en las rutas de la base de datos
        self.Pvs = []                  # Lista en la que se añaden planes de vuelo del ejercicio
        self.z = 0
        self.Cont = 1
        self.c = False

        with open('C:\GAMMA\Datos de Adaptacion AIS\Aisfile.txt', 'r') as filehandle:
            i = True
            for line in filehandle.readlines():
                if i: i = False
                else: self.DateData = str(line)

        filehandle.close()

        with open('C:\GAMMA\Bases de Datos\databasefile.txt', 'r') as filehandle:
            i = True
            for line in filehandle.readlines():
                if i:
                    self.LabAux.append((line.split(',')))
                    i = False
                else:
                    self.AvailablePvListAux.append((line.split(',')))

        filehandle.close()

        self.Lab = [self.LabAux[0][i].replace("'", "").replace('"', "").replace("[", "").replace("]", "").rstrip() for
                    i in
                    range(len(self.LabAux[0]))]

        for i in range(len(self.AvailablePvListAux)):
            pv = []
            for j in range(len(self.AvailablePvListAux[0])):
                pv.append(self.AvailablePvListAux[i][j].replace("'", "").replace('"', "").replace("[", "").replace("]",
                                                                                                                   "").rstrip())

            self.AvailablePvList.append(pv)

        LstDeparture = []
        LstDestination = []
        LstRoutes = []
        LstFixesAux = []
        LstFixes = []
        DelChar = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']

        for i in range(len(self.AvailablePvList)):
            LstDeparture.append((self.AvailablePvList[i][3]).replace("'", ""))
            LstDestination.append((self.AvailablePvList[i][4]).replace("'", ""))
            LstRoutes.append((self.AvailablePvList[i][5]).replace("'", ""))
            ruta = self.AvailablePvList[i][5].split()

            for p in ruta:
                p = p.replace("'", "")
                p = p.replace('"', "")
                if p not in LstFixes:
                    LstFixesAux.append(p)

        for p in LstFixesAux:
            for x in DelChar:
                if x in p:
                    break
                else:
                    if x == DelChar[-1]:
                        if p not in LstFixes:
                            LstFixes.append(p.replace("'", ""))

        Departure = np.unique(LstDeparture)
        Destination = np.unique(LstDestination)
        Routes = np.unique(LstRoutes)
        LstFixes.sort()
        self.Fixes = LstFixes

        for string in Departure:
            self.Departure.append(string)
        for string in Destination:
            self.Destination.append(string)
        for string in Routes:
            self.Routes.append(string)

    def pp_window(self):

        '''

            Create pp window

        :return: None
        '''

        self.window = tix.Toplevel()
        self.window.wm_state('zoomed')
        self.window.update_idletasks()

        self.h = self.window.winfo_height()
        self.w = self.window.winfo_width()

        img_dir = os.path.join(conf.common_dir, 'img')
        ico_file = os.path.join(img_dir, 'GAMMASIM.ico')
        self.window.iconbitmap(ico_file)
        self.window.title('Flights selection')

    def pp_frames(self):

        '''

            Include all frames in the interface

        :return:
        '''

        color_text = 'navy'

        self.upperFrame = tix.Frame(self.window, bd=0, highlightthickness=0, width=self.w, height=self.h)
        self.upperFrame.pack(side=tix.TOP, padx=15, pady=10)

        ###
        self.frame_header1 = tix.Frame(self.upperFrame, bd=0, highlightthickness=0, width=self.w,
                                       height=(1 / 2) * self.h / 10)
        self.frame_header1.pack(side=tix.TOP)

        self.frame_header1_1 = tix.Frame(self.frame_header1, bd=0, highlightthickness=0, width=self.w,
                                         height=(1 / 2) * self.h)
        self.frame_header1_1.pack(side=tix.TOP)

        self.frame_header1_2 = tix.Frame(self.frame_header1, bd=0, highlightthickness=0, width=self.w,
                                         height=(1 / 2) * self.h)
        self.frame_header1_2.pack(side=tix.BOTTOM)

        self.frame_header1_2LEFT = tix.Frame(self.frame_header1_2, bd=0, highlightthickness=0,
                                             width=(1 / 2) * self.w,
                                             height=(1 / 2) * self.h)
        self.frame_header1_2LEFT.pack(side=tix.LEFT)

        self.frame_header1_2RIGHT = tix.Frame(self.frame_header1_2, bd=0, highlightthickness=0,
                                              width=(1 / 2) * self.w,
                                              height=(1 / 2) * self.h)
        self.frame_header1_2RIGHT.pack(side=tix.RIGHT)

        self.frame_header2 = tix.Frame(self.upperFrame, bd=0, highlightthickness=0, width=self.w,
                                       height=(1 / 2) * self.h / 10)
        self.frame_header2.pack(side=tix.TOP, fill=tix.X)

        self.frame_header2_1 = tix.Frame(self.frame_header2, bd=0, highlightthickness=0, width=self.w / 2,
                                         height=self.h)
        self.frame_header2_1.pack(side=tix.LEFT)

        self.frame_header2_2 = tix.Frame(self.frame_header2, bd=0, highlightthickness=0, width=self.w / 2,
                                         height=self.h)
        self.frame_header2_2.pack(side=tix.LEFT)

        self.frame_header3 = tix.Frame(self.upperFrame, bd=0, highlightthickness=0, width=self.w,
                                       height=self.h / 10)
        self.frame_header3.pack(side=tix.TOP, fill=tix.X)

        self.frame_header3_1 = tix.Frame(self.frame_header3, bd=0, highlightthickness=0, width=self.w / 2,
                                         height=self.h,
                                         borderwidth=1, relief=tix.SUNKEN)
        self.frame_header3_1.pack(side=tix.LEFT)

        self.frame_header3_11 = tix.Frame(self.frame_header3_1, bd=0, highlightthickness=0, width=self.w / 2,
                                          height=self.h, borderwidth=1)
        self.frame_header3_11.pack(side=tix.TOP, fill=tix.X)

        self.frame_header3_12 = tix.Frame(self.frame_header3_1, bd=0, highlightthickness=0, width=self.w / 2,
                                          height=self.h, borderwidth=1)
        self.frame_header3_12.pack(side=tix.BOTTOM, fill=tix.X)

        self.frame_header3_2 = tix.Frame(self.frame_header3, bd=0, highlightthickness=0, width=self.w / 2,
                                         height=self.h,
                                         borderwidth=1, relief=tix.SUNKEN)
        self.frame_header3_2.pack(side=tix.LEFT, fill=tix.X)

        self.frame_header3_21 = tix.Frame(self.frame_header3_2, bd=0, highlightthickness=0, width=self.w / 2,
                                          height=self.h,
                                          borderwidth=1)
        self.frame_header3_21.pack(side=tix.TOP, fill=tix.X)

        self.frame_header3_22 = tix.Frame(self.frame_header3_2, bd=0, highlightthickness=0, width=self.w / 2,
                                          height=self.h,
                                          borderwidth=1)
        self.frame_header3_22.pack(side=tix.BOTTOM, fill=tix.X)

        self.frame_header4 = tix.Frame(self.upperFrame, bd=0, highlightthickness=0, width=self.w,
                                       height=self.h / 10)
        self.frame_header4.pack(side=tix.TOP)

        self.frame_header4_1 = tix.Frame(self.frame_header4, bd=0, highlightthickness=0, width=self.w,
                                         height=1 * self.h / 3)
        self.frame_header4_1.pack(side=tix.TOP)

        self.frame_header4_2 = tix.Frame(self.frame_header4, bd=0, highlightthickness=0, width=self.w,
                                         height=2 * self.h / 3)
        self.frame_header4_2.pack(side=tix.TOP)

        self.frame_body = tix.Frame(self.upperFrame, bd=0, highlightthickness=0, width=self.w,
                                    height=7 * self.h / 10)
        self.frame_body.pack(side=tix.TOP)

        title = tix.Label(self.frame_header1_1, text='GENERACION DEL EJERCICIO', fg=color_text, bd=0,
                          font=('Helvetica 14 bold'))
        title.pack(side=tix.TOP, pady=10)

    def pp_elements(self):

        '''

            Include all elements in the interface: labels, entry widgets, buttons and combobox

        :return:
        '''

        ColorText = 'navy'
        w = 10
        r = 1
        r_ent = 1
        Font = ('Helvetica 12 bold')

        ##############################################################################################################
        ############################## INTERFACE WIDGETS -> GENERACIÓN DE CONFLICTO ################################
        ##############################################################################################################

        LabelFil_1 = tix.Label(self.frame_header2_1, text='Especificaciones del Conflicto: ', fg=ColorText, bd=0,
                               font=('Helvetica 14 bold'))
        LabelFil_1.pack(side=tix.LEFT, pady=15)

        LabelFil_2 = tix.Label(self.frame_header3_11, text='Tipo de Conflicto: ', fg=ColorText, bd=0, font=Font)
        LabelFil_2.grid(row=r, column=2, padx=2, pady=5)

        self.CboxFil_2 = ttk.Combobox(self.frame_header3_11, state="readonly", justify=tix.CENTER, width=w, font=Font)
        self.CboxFil_2.grid(row=r, column=3, padx=2, pady=5)
        self.CboxFil_2["values"] = ['CROSS', 'SAME', 'SPEED']


        LabelFil_5 = tix.Label(self.frame_header3_11, text='Solucion: ', fg=ColorText, bd=0, font=Font)
        LabelFil_5.grid(row=r, column=4, padx=2, pady=5)

        self.CboxFil_5 = ttk.Combobox(self.frame_header3_11, state="readonly", justify=tix.CENTER, width=w,
                                      font=Font)
        self.CboxFil_5.grid(row=r, column=5, padx=2, pady=5)
        self.CboxFil_5["values"] = ['VEC', 'SPD', 'SEQ', 'C_D']


        LabelFil_6 = tix.Label(self.frame_header3_11, text='Niveles: ', fg=ColorText, bd=0, font=Font)
        LabelFil_6.grid(row=r, column=6, padx=2, pady=5)

        self.CboxFil_6 = ttk.Combobox(self.frame_header3_11, state="readonly", justify=tix.CENTER, width=w,
                                      font=Font)
        self.CboxFil_6.grid(row=r, column=7, padx=2, pady=5)
        self.CboxFil_6["values"] = ['PARES', 'IMPARES']


        LabelFil_3 = tix.Label(self.frame_header3_11, text='Fijo: ', fg=ColorText, bd=0, font=Font)
        LabelFil_3.grid(row=r, column=8, padx=2, pady=5)

        self.CboxFil_3 = ttk.Combobox(self.frame_header3_11, state="normal", justify=tix.CENTER, width=w, font=Font)
        self.CboxFil_3.grid(row=r, column=9, padx=2, pady=5)
        self.CboxFil_3["values"] = self.Fixes
        self.CboxFil_3.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 4))

        LabelFil_4 = tix.Label(self.frame_header3_12, text='Hora: ', fg=ColorText, bd=0, font=Font)
        LabelFil_4.grid(row=r_ent, column=1, padx=2, pady=5)

        self.EntryFil_4H = tix.Entry(self.frame_header3_12, width=3, font=Font)
        self.EntryFil_4H.grid(row=r_ent, column=2, padx=2, pady=5)
        self.EntryFil_4H.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))
        LabelFil_4PUNT = tix.Label(self.frame_header3_12, text=':', fg=ColorText, bd=0, font=Font)
        LabelFil_4PUNT.grid(row=r_ent, column=3, padx=2, pady=5)
        self.EntryFil_4M = tix.Entry(self.frame_header3_12, width=3, font=Font)
        self.EntryFil_4M.grid(row=r_ent, column=4, padx=2, pady=5)
        self.EntryFil_4M.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        Labelspace1 = tix.Label(self.frame_header3_11)
        Labelspace1.grid(row=0, column=0)
        Labelspace2 = tix.Label(self.frame_header3_11)
        Labelspace2.grid(row=2, column=0)
        Labelspace3 = tix.Label(self.frame_header3_12)
        Labelspace3.grid(row=2, column=0)

        ##############################################################################################################
        ####################### INTERFACE WIDGETS -> GENERACIÓN DE PLANES DE VUELO RELLENO #########################
        ##############################################################################################################

        title_R = tix.Label(self.frame_header2_2, text='Especificaciones Planes de Vuelo: ', fg=ColorText, bd=0,
                            font=('Helvetica 14 bold'))
        title_R.pack(side=tix.LEFT, padx=540, pady=16)

        LabelFil_1R = tix.Label(self.frame_header3_21, text='Origen: ', fg=ColorText, bd=0, font=Font)
        LabelFil_1R.grid(row=r, column=1, padx=2, pady=5)

        self.cmbFil_1R = ttk.Combobox(self.frame_header3_21, state="normal", justify=tix.CENTER, width=w, font=Font)
        self.cmbFil_1R.grid(row=r, column=2, padx=2, pady=5)
        self.cmbFil_1R["values"] = self.Departure
        self.cmbFil_1R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 1))

        LabelFil_2R = tix.Label(self.frame_header3_21, text='Destino: ', fg=ColorText, bd=0, font=Font)
        LabelFil_2R.grid(row=r, column=3, padx=2, pady=5)

        self.cmbFil_2R = ttk.Combobox(self.frame_header3_21, state="normal", justify=tix.CENTER, width=w, font=Font)
        self.cmbFil_2R.grid(row=r, column=4, padx=2, pady=5)
        self.cmbFil_2R["values"] = self.Destination
        self.cmbFil_2R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 2))

        LabelFil_4R = tix.Label(self.frame_header3_21, text='Fijo: ', fg=ColorText, bd=0, font=Font)
        LabelFil_4R.grid(row=r, column=5, padx=1, pady=5)

        self.cmbFil_4R = ttk.Combobox(self.frame_header3_21, state="normal", justify=tix.CENTER, width=w, font=Font)
        self.cmbFil_4R.grid(row=r, column=6, padx=2, pady=5)
        self.cmbFil_4R["values"] = self.Fixes
        self.cmbFil_4R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 4))

        LabelFil_5R = tix.Label(self.frame_header3_21, text='Hora: ', fg=ColorText, bd=0, font=Font)
        LabelFil_5R.grid(row=r, column=7, padx=2, pady=5)

        self.EntryFil_5RH = tix.Entry(self.frame_header3_21, width=3, font=Font)
        self.EntryFil_5RH.grid(row=r, column=8, padx=2, pady=5)
        self.EntryFil_5RH.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        LabelFil_5PUNT = tix.Label(self.frame_header3_21, text=':', fg=ColorText, bd=0, font=Font)
        LabelFil_5PUNT.grid(row=r, column=9, padx=2, pady=5)

        self.EntryFil_5RM = tix.Entry(self.frame_header3_21, width=3, font=Font)
        self.EntryFil_5RM.grid(row=r, column=10, padx=2, pady=5)
        self.EntryFil_5RM.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        LabelFil_6R = tix.Label(self.frame_header3_21, text='Número de Vuelos: ', fg=ColorText, bd=0, font=Font)
        LabelFil_6R.grid(row=r, column=11, padx=2, pady=5)

        self.EntryFil_6R = tix.Entry(self.frame_header3_21, width=w, font=Font)
        self.EntryFil_6R.grid(row=r, column=12, padx=2, pady=5)
        self.EntryFil_6R.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        LabelFil_3R = tix.Label(self.frame_header3_22, text='Ruta: ', fg=ColorText, bd=0, font=Font)
        LabelFil_3R.grid(row=r_ent, column=1, padx=2, pady=5)

        self.cmbFil_3R = ttk.Combobox(self.frame_header3_22, state="normal", justify=tix.CENTER, width=95,
                                      font=Font)
        self.cmbFil_3R.grid(row=r_ent, column=2, padx=2, pady=5)
        self.cmbFil_3R["values"] = self.Routes

        self.cmbFil_3R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 3))

        Labelspace1 = tix.Label(self.frame_header3_21)
        Labelspace1.grid(row=0, column=0)
        Labelspace2 = tix.Label(self.frame_header3_21)
        Labelspace2.grid(row=2, column=0)
        Labelspace3 = tix.Label(self.frame_header3_22)
        Labelspace3.grid(row=2, column=0)

        ##############################################################################################################
        ############################################# INTERFACE WIDGETS -> BUTTON ####################################
        ##############################################################################################################


        self.EntryAis = tix.Entry(self.frame_header1_2LEFT, width=50, justify=tix.CENTER, fg='dark green', font=('Helvetica 12 bold'))
        self.EntryAis.pack(side=tix.LEFT, padx=5, pady=10)
        self.EntryAis.insert(0, self.DateData)
        self.EntryAis.config(state='readonly')

        self.LabelH_Ini = tix.Label(self.frame_header1_2LEFT, text='Hora Inicio: ', fg=ColorText, bd=0,
                                    font=('Helvetica 12 bold'))
        self.LabelH_Ini.pack(side=tix.LEFT, padx=5, pady=10)

        self.EntryH_IniH = tix.Entry(self.frame_header1_2LEFT, width=3, justify=tix.CENTER, font=('Helvetica 12 bold'))
        self.EntryH_IniH.pack(side=tix.LEFT, padx=5, pady=10)
        self.EntryH_IniH.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        self.LabelH_IniPUNT = tix.Label(self.frame_header1_2LEFT, text=':', fg=ColorText, bd=0, font=('Helvetica 12 bold'))
        self.LabelH_IniPUNT.pack(side=tix.LEFT, padx=5, pady=10)

        self.EntryH_IniM = tix.Entry(self.frame_header1_2LEFT, width=3, justify=tix.CENTER, font=('Helvetica 12 bold'))
        self.EntryH_IniM.pack(side=tix.LEFT, padx=5, pady=10)
        self.EntryH_IniM.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        self.LabelH_Dur = tix.Label(self.frame_header1_2LEFT, text='Duracion(mm): ', fg=ColorText, bd=0,
                                    font=('Helvetica 12 bold'))
        self.LabelH_Dur.pack(side=tix.LEFT, padx=5, pady=10)

        self.EntryH_Dur = tix.Entry(self.frame_header1_2LEFT, width=5, justify=tix.CENTER, font=('Helvetica 12 bold'))
        self.EntryH_Dur.pack(side=tix.LEFT, padx=5, pady=10)

        self.EntryH_Dur.insert(0, '60')
        self.EntryH_Dur.config(state='readonly')

        self.button_gen_conf = tix.Button(self.frame_header1_2LEFT, text='Generar Conflicto', font=('Helvetica 11 bold'),
                                          fg=ColorText, bg='SlateGray2', width=15, height=1, relief=tix.GROOVE)
        self.button_gen_conf.pack(side=tix.LEFT, padx=5, pady=10)
        self.button_gen_conf.bind('<Button-1>', lambda event: self.filter_conf(event))

        self.button_gen_pv = tix.Button(self.frame_header1_2LEFT, text='Generar Planes de Vuelo', font=('Helvetica 11 bold'),
                                        fg=ColorText, bg='SlateGray2', width=20, height=1, relief=tix.GROOVE)
        self.button_gen_pv.pack(side=tix.LEFT, padx=5, pady=10)
        self.button_gen_pv.bind('<Button-1>', lambda event: self.filter_fill_pvs(event))

        self.button_save = tix.Button(self.frame_header1_2LEFT, text='Guardar Ejercicio', font=('Helvetica 11 bold'),
                                      fg=ColorText, bg='SlateGray2', width=15, height=1, relief=tix.GROOVE)
        self.button_save.pack(side=tix.LEFT, padx=5, pady=10)
        self.button_save.bind('<Button-1>', lambda event: self.generate_exercise(event))

        self.button_Timeline = tix.Button(self.frame_header1_2RIGHT, text='Cargar Timeline', font=('Helvetica 11 bold'),
                                          fg=ColorText, bg='SlateGray2', width=15, height=1, relief=tix.GROOVE)
        self.button_Timeline.pack(side=tix.RIGHT, padx=5, pady=10)
        self.button_Timeline.bind('<Button-1>', lambda event: self.load_timeline(event))

        # self.button_ord = tix.Button(self.frame_header1_2RIGHT, text='Reordenar Ejercicio', font=('Helvetica 10 bold'),
        #                             fg=color_text, bg='SlateGray2', width=20, height=1, relief=tix.GROOVE)
        # self.button_ord.pack(side=tix.RIGHT, padx=5, pady=10)
        # self.button_ord.bind('<Button-1>', lambda event: self.Ord_Exer(event))

    def pp_elements_init_values(self):

        '''

            Include all elements in the interface

        :return:
        '''

        ##############################################################################################################
        ################################ INTERFACE WIDGETS -> GENERACIÓN DE CONFLICTO ################################
        ##############################################################################################################

        self.CboxFil_2["values"] = ['CROSS', 'SAME', 'SPEED']


        self.CboxFil_5["values"] = ['VEC', 'SPD', 'SEQ', 'C_D']


        self.CboxFil_6["values"] = ['PARES', 'IMPARES']


        self.CboxFil_3["values"] = self.Fixes
        self.CboxFil_3.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 4))


        self.EntryFil_4H.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        self.EntryFil_4M.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))


        ##############################################################################################################
        ####################### INTERFACE WIDGETS -> GENERACIÓN DE PLANES DE VUELO RELLENO #########################
        ##############################################################################################################

        self.cmbFil_1R["values"] = self.Departure
        self.cmbFil_1R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 1))

        self.cmbFil_2R["values"] = self.Destination
        self.cmbFil_2R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 2))

        self.cmbFil_4R["values"] = self.Fixes
        self.cmbFil_4R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 4))


        self.EntryFil_5RH.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))


        self.EntryFil_5RM.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))


        self.EntryFil_6R.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))


        self.cmbFil_3R["values"] = self.Routes
        self.cmbFil_3R.bind("<KeyRelease>", lambda event: self.filter_pvs(event, 3))


        ##############################################################################################################
        ############################################# INTERFACE WIDGETS -> BUTTON ####################################
        ##############################################################################################################


        self.EntryAis.insert(0, self.DateData)
        self.EntryAis.config(state='readonly')


        self.EntryH_IniH.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))

        self.EntryH_IniM.bind("<KeyRelease>", lambda event: self.limite_char_entry(event))


        self.EntryH_Dur.insert(0, '60')
        self.EntryH_Dur.config(state='readonly')


        self.button_gen_conf.bind('<Button-1>', lambda event: self.filter_conf(event))


        self.button_gen_pv.bind('<Button-1>', lambda event: self.filter_fill_pvs(event))


        self.button_save.bind('<Button-1>', lambda event: self.generate_exercise(event))


        self.button_Timeline.bind('<Button-1>', lambda event: self.load_timeline(event))

        # self.button_ord = tix.Button(self.frame_header1_2RIGHT, text='Reordenar Ejercicio', font=('Helvetica 10 bold'),
        #                             fg=color_text, bg='SlateGray2', width=20, height=1, relief=tix.GROOVE)
        # self.button_ord.pack(side=tix.RIGHT, padx=5, pady=10)
        # self.button_ord.bind('<Button-1>', lambda event: self.Ord_Exer(event))

    def labels(self):

        '''

        Create a row on window with the labels of each pv data.

        :var {list} Etiq: Contains pv Labels
        :return: None

        '''
        self.Label_space = tix.Label(self.frame_header4_1)
        self.Label_space.pack(side=tix.TOP)

        for i in range(0, len(self.Lab)):
            if i == 5:
                w = 50  # Route File Length
            else:
                w = 16

            Labels = tix.Entry(self.frame_header4_2, justify=tix.CENTER, width=w, font=('Arial 8 bold'),
                               relief=tix.FLAT, selectbackground='gray')
            Labels.insert(0, self.Lab[i])
            Labels.grid(row=0, column=i + 1, pady=5)

    def scroll(self):

        '''

            Include scroll code -> Y axis

        :return:
        '''

        yscrollbar = tix.Scrollbar(self.frame_body, orient=tix.VERTICAL)
        yscrollbar.pack(side=tix.RIGHT, fill=tix.Y)

        self.externalcanvas = tix.Canvas(self.frame_body, width=self.w, height=9 * self.h / 10, bg=WINDOW_BG)
        self.externalcanvas.pack(side=tix.TOP)
        yscrollbar.config(command=self.externalcanvas.yview)
        self.externalcanvas.config(yscrollcommand=yscrollbar.set)

        self.frame_in = tix.Frame(self.externalcanvas, width=self.w, height=self.h, bg=WINDOW_BG)
        self.frame_in.pack(side=tix.TOP, padx=10)
        self.externalcanvas.create_window(0, self.h, window=self.frame_in, anchor=tix.N)
        self.externalcanvas.update_idletasks()
        self.externalcanvas.config(scrollregion=self.externalcanvas.bbox(tix.ALL))

    def limite_char_entry(self, eventObject):

        '''

            Limit to introduce a max of 2 characters on widget entry: hour, minute and number of pvs

        :param eventObject: Char -> Number
        :return:
        '''

        value = eventObject.widget.get()
        if len(value) < 3:
            pass
        else:
            eventObject.widget.delete(0, 'end')
            eventObject.widget.insert(0, value[0:2])

    def filter_pvs(self, eventObject, IndList):

        '''

            List to filter

        :var {str} Points: Capitalize Entry user word
        :param eventObject: Entry user string
        :param {int} IndList: Number to select list data to filter
        :return:
        '''

        Points = (eventObject.widget.get()).upper()

        if IndList == 1:
            List = self.Departure
        elif IndList == 2:
            List = self.Destination
        elif IndList == 3:
            List = self.Routes
        elif IndList == 4:
            List = self.Fixes

        filtList = [(r, r.index(Points)) for r in List if Points in r]
        filtList.sort(key=lambda tup: tup[1])
        filtList = [r for r, i in filtList]
        eventObject.widget["values"] = filtList
        
    def filter_conf(self, eventObject):

        try:
            self.timer_object
            self.window.after_cancel(self.timer_object)
        except:
            pass

        Hora = self.EntryFil_4H.get()
        Min = self.EntryFil_4M.get()

        if Hora == '':
            Time = '----'
        else:
            Time = str(Hora) + ':' + str(Min) + ':00'

        Niveles = self.CboxFil_6.get()
        fix = (self.CboxFil_3.get()).upper()
        t_conf = (self.CboxFil_2.get()).upper()

        pv_aux = ['', '', '', '', '', '', '', '', '', '', '', '', '', '']

        # pos_param_indicativo =  self.Etiq.index('Indicativo')
        # pos_param_ruta =    self.Etiq.index('RutaSACTA')
        # pos_param_nivel =   self.Etiq.index('NivelCrucero')
        # pos_param_vel =     self.Etiq.index('VelCrucero')

        pos_param_indicativo = 0
        pos_param_ruta = 5
        pos_param_vel = 6
        pos_param_nivel = 7

        list_pv_filt = random.sample(self.AvailablePvList, int(2000))  # Planes de vuelo aleatorios sel.1 pv del conflct
        for i in range(0, 5):
            lst_conf = []
            for pv1 in list_pv_filt:  # Select 1 pv

                route1 = pv1[pos_param_ruta].split()

                if Niveles == 'PARES':
                    operacion = 0
                else:
                    operacion = 1

                if int(pv1[pos_param_nivel][0:2]) % 2 == operacion and fix in route1:
                    pv1_conf = pv1
                    vel1 = int(pv1[pos_param_vel])
                    lst_conf.append(pv1_conf)
                    break
                else:
                    pv1_conf = None

            if pv1_conf == None:
                break

            for pv2 in list_pv_filt:  # Select 2 pv

                route2 = pv2[pos_param_ruta].split()
                vel2 = int(pv2[pos_param_vel])

                if int(pv2[pos_param_nivel][0:2]) % 2 == operacion and pv1_conf[pos_param_indicativo] != pv2[
                    pos_param_indicativo] and fix in route2:

                    ind1 = route1.index(fix)
                    ind2 = route2.index(fix)
                    len1 = route1.index(route1[-1])
                    len2 = route2.index(route2[-1])

                    # punto ant al fijo en el que se quiere tener el conflicto para ambos pvs
                    if ind1 != 0 and ind2 != 0:
                        fix_ant1 = route1[ind1 - 1]
                        fix_ant2 = route2[ind2 - 1]
                    elif ind1 != 0 and ind2 == 0:
                        fix_ant1 = route1[ind1 - 1]
                        fix_ant2 = route2[ind2]
                    elif ind1 == 0 and ind2 != 0:
                        fix_ant1 = route1[ind1]
                        fix_ant2 = route2[ind2]
                    else:
                        fix_ant1 = route1[ind1]
                        fix_ant2 = route2[ind2]

                    # punto post al fijo en el que se quiere tener el conflicto para ambos pvs
                    if ind1 != len1 and ind2 != len2:
                        fix_post1 = route1[ind1 + 1]
                        fix_post2 = route2[ind2 + 1]
                    elif ind1 != len1 and ind2 == len2:
                        fix_post1 = route1[ind1 + 1]
                        fix_post2 = route2[ind2]
                    elif ind1 == len1 and ind2 != len2:
                        fix_post1 = route1[ind1]
                        fix_post2 = route2[ind2 + 1]
                    else:
                        fix_post1 = route1[ind1]
                        fix_post2 = route2[ind2]

                    if fix_ant1 != fix_ant2 and fix_post1 != fix_post2:
                        if t_conf == 'CROSS':
                            pv2_conf = pv2
                            lst_conf.append(pv2_conf)
                            break

                    elif fix_ant1 != fix_ant2 and fix_post1 == fix_post2:
                        if t_conf == 'SAME':
                            pv2_conf = pv2
                            lst_conf.append(pv2_conf)
                            break


                    elif fix_ant1 == fix_ant2 and fix_post1 == fix_post2 and (vel1 > vel2 + 10 or vel2 > vel1 + 10):
                        if t_conf == 'SPEED':
                            pv2_conf = pv2
                            lst_conf.append(pv2_conf)
                            break
                    else:
                        pass

                else:

                    if pv2[pos_param_indicativo] in list_pv_filt[-1] and len(lst_conf) % 2 != 0:
                        lst_conf.append(pv_aux)
                        break
            if lst_conf[1][0] == '':
                pass
            else:
                break

        if len(lst_conf) < 1:
            self.Label_space = tix.Label(self.frame_header4_1,
                                         text='No se Encuentran Planes de Vuelo con estas Características en la Base de Datos',
                                         fg='IndianRed3', bd=0, font=('Helvetica 12 bold'))
            self.Label_space.pack(side=tix.TOP, pady=8)
        else:

            try:
                self.Label_space
                self.Label_space.destroy()
            except:
                pass
            self.c = True
            self.Fl = True
            fill_pvs(self, Time, fix, lst_conf)


            self.EntryFil_4H.delete(0, 'end')
            self.EntryFil_4M.delete(0, 'end')

    def filter_fill_pvs(self, eventObject):

        '''

        To filter pvs available list from entrys widget.

        :param {event} eventObject:
        :param {str} Departure: Contains entry adep data
        :param {str} Destination: Contains entry ades data
        :param {str} Route: Contains entry route data
        :param {str} Fix: Contains entry fix data
        :var {list} FilterFiles: Contains all entry data
        :var {int} Fl: To specify type filter data
        :return: None
        '''

        try:
            self.timer_object
            self.window.after_cancel(self.timer_object)
        except:
            pass

        FilterFiles = []
        FilterFlags = []
        self.FilteredPvsList = []
        Fl = 0

        Departure = (self.cmbFil_1R.get()).upper()
        Destino = (self.cmbFil_2R.get()).upper()
        Route = (self.cmbFil_3R.get()).upper()
        Fix = (self.cmbFil_4R.get()).upper()

        Hour = self.EntryFil_5RH.get()
        Min = self.EntryFil_5RM.get()

        NumPvs = self.EntryFil_6R.get()

        if NumPvs == '':
            NumPvs = 1

        if Departure != 'Origen' and Destino == 'Destino' and Route == 'Ruta' and Fix == 'Fijo':

            Fl = 3
            FilterFiles.append(Departure)

        elif Destino != 'Destino' and Departure == 'Origen' and Route == 'Ruta' and Fix == 'Fijo':

            Fl = 4
            FilterFiles.append(Destino)

        elif Route != 'Ruta' and Departure == 'Origen' and Destino == 'Destino' and Fix == 'Fijo':

            Fl = 5
            FilterFiles.append(Route)

        elif Fix != 'Fijo' and Departure == 'Origen' and Destino == 'Destino':

            Fl = 5
            FilterFiles.append(Fix)

        else:

            if Departure != 'Origen':
                FilterFiles.append(Departure)
                FilterFlags.append(3)

            if Destino != 'Destino':
                FilterFiles.append(Destino)
                FilterFlags.append(4)

            if Route != 'Ruta':
                FilterFiles.append(Route)
                FilterFlags.append(5)

            if Fix != 'Fijo':
                FilterFiles.append(Fix)
                FilterFlags.append(5)

        if Fl == 0:  # Si el filtrado es con varios campo

            for i in range(1, (len(self.AvailablePvList))):

                cont = 0

                for n in range(len(FilterFiles)):

                    f = FilterFlags[n]
                    if FilterFiles[n] in self.AvailablePvList[i][f]:
                        cont += 1

                if cont == len(FilterFiles):
                    self.FilteredPvList.append(self.AvailablePvList[i])

        else:  # Si el filtrado es con un unico campo

            for i in range(1, (len(self.AvailablePvList))):

                if FilterFiles[0] in self.AvailablePvList[i][Fl]:
                    self.FilteredPvList.append(self.AvailablePvList[i])

        if int(NumPvs) > len(self.FilteredPvList) and len(self.FilteredPvList) != 0:
            try:
                self.Label_space
                self.Label_space.destroy()


            except:
                pass

            self.Label_space = tix.Label(self.frame_header4_1,
                                         text='No se Encuentran Suficientes Planes de Vuelo con estas Características en la Base de Datos',
                                         fg='IndianRed3', bd=0, font=('Helvetica 12 bold'))
            self.Label_space.pack(side=tix.TOP, pady=8)



        elif len(self.FilteredPvList) == 0:

            try:
                self.Label_space
                self.Label_space.destroy()

            except:
                pass
            self.Label_space = tix.Label(self.frame_header4_1,
                                         text='No se Encuentran Planes de Vuelo con estas Características en la Base de Datos',
                                         fg='IndianRed3', bd=0, font=('Helvetica 12 bold'))
            self.Label_space.pack(side=tix.TOP, pady=8)

            self.EntryFil_5RH.delete(0, 'end')
            self.EntryFil_5RM.delete(0, 'end')


        else:

            try:
                self.Label_space
                self.Label_space.destroy()
                self.Label_space = tix.Label(self.frame_header4_1)
                self.Label_space.pack(side=tix.TOP)

            except:
                pass

            PVsSelected = random.sample(self.FilteredPvList, int(NumPvs))

            ################################### Call function to fill pp window
            self.c = False
            self.Fl = True

            for pv in PVsSelected:

                if Fix == '':
                    R = pv[5].split()
                    pv[10] = R[random.randrange(len(R))]

                if Hour == '' or Min == '':
                    pv[11] = '----'
                else:
                    if pv == PVsSelected[0]:
                        pv[11] = str(Hour) + ':' + str(Min) + ':00'
                    else:
                        NMin = str(random.randrange(int(Min), 60, 5))
                        if len(NMin) == 1: NMin = '0' + NMin
                        Time = str(Hour) + ':' + NMin + ':00'
                        pv[11] = Time

            fill_pvs(self, False, Fix, PVsSelected)

            self.EntryFil_5RH.delete(0, 'end')
            self.EntryFil_5RM.delete(0, 'end')

    def show_label_route(self, i, x, Option):
        # type: (object, object, object) -> object
        FontStyle = 'Arial 9'

        if Option:

            PvLst = []
            for pv in self.Pvs:
                paux = []
                for element in pv:
                    paux.append(element.get())
                PvLst.append(paux)

            self.Label_Route = ttk.Label(self.frame_in, text=PvLst[i][6], anchor=tix.CENTER, width=150,
                                         font=(FontStyle))
            self.Label_Route.bind("<Button-1>", self.del_entry)
            self.Label_Route.grid(row=i, column=6, pady=x)

        else:
            self.Label_Route.destroy()

    def del_entry(self, eventObject):
        self.Label_Route.destroy()

    def del_flight(self, i):

        '''

        Delete a pv on SelectPvList if user press del button.

        :param {list} SelectPvList: Contains pvs selected to create a new exercise
        :param {int} i: Position on SelectPVList
        :return: None
        '''

        try:
            self.timer_object
            self.window.after_cancel(self.timer_object)
        except:
            pass

        try:
            self.Pvs
            Row = self.Pvs[i]
            Type = Row[13].get()
            if Type != '':

                self.Pvs.pop(i)
                self.Pvs.pop(i - 1)
            else:
                self.Pvs.pop(i)

            PvList = []
            for pv in self.Pvs:
                paux = []
                for element in pv:
                    paux.append(element.get())
                paux.pop(0)
                PvList.append(paux)

        except:
            pass

        for child in self.frame_in.winfo_children():
            child.destroy()

        self.Pvs = []
        self.z = 0

        self.Cont = 1
        self.Fl = False
        fill_pvs(self, False, False, PvList)

    def copy_flight(self, i):

        '''

        Copy a pv on PVs if user press copy button.

        :param {list} Pvs: Contains pvs selected to create a new exercise
        :param {int} i: Position on PVs
        :return: None
        '''

        try:
            self.timer_object
            self.window.after_cancel(self.timer_object)
        except:
            pass

        try:
            self.Pvs
            row1 = self.Pvs[i]
            fix1 = row1[11].get()
            tipo1 = row1[13].get()
            sol1 = row1[14].get()

            if tipo1 != '':  # Seleccion de pv definido como conflicto

                fl2 = False
                fl3 = False

                if self.Pvs[i] != self.Pvs[-1]:
                    row2 = self.Pvs[i + 1]
                    tipo2 = row2[13].get()
                    fl2 = True

                if self.Pvs[i] != self.Pvs[0]:
                    row3 = self.Pvs[i - 1]
                    fl3 = True

                if fl2 and fl3:  # self.PVs[i] Plan de vuelo de conflicto intermedio
                    fix2 = row2[11].get()
                    sol2 = row2[14].get()

                    if fix1 == fix2 and tipo1 == tipo2 and sol1 == sol2:
                        self.Pvs.insert(i + 1, row2)
                        self.Pvs.insert(i + 2, row1)
                    else:
                        self.Pvs.insert(i + 1, row3)
                        self.Pvs.insert(i + 2, row1)

                elif fl2 and not fl3:  # self.PVs[i] Plan de vuelo de conflicto i = 0

                    self.Pvs.insert(i + 1, row2)
                    self.Pvs.insert(i + 2, row1)
                elif fl3 and not fl2:  # self.PVs[i] Plan de vuelo de conflicto i = -1

                    self.Pvs.insert(i + 1, row3)
                    self.Pvs.insert(i + 2, row1)

            else:

                self.Pvs.insert(i + 1, row1)

            pv_lst = []
            for pv in self.Pvs:
                paux = []
                for element in pv:
                    paux.append(element.get())
                paux.pop(0)
                pv_lst.append(paux)

        except:
            pass

        for child in self.frame_in.winfo_children():
            child.destroy()

        self.Pvs = []
        self.z = 0

        self.cont = 1
        self.Fl = False
        fill_pvs(self, False, False, pv_lst)

    def guardar_cambios(self, eventObject):

        try:
            self.Pvs
            Cont = 0
            for cf in self.Pvs:
                self.Pvs[Cont] = (cf[0], cf[1], cf[2],
                                   cf[3], cf[4], cf[5],
                                   cf[6], cf[7], cf[8],
                                   cf[9], cf[10], cf[11],
                                   cf[12], cf[13], cf[14])
                Cont += 1

        except:
            pass

    def revisar(self):

        self.Rev = False

        # Comprobar si hay algún vuelo que este duplicado
        for i in range(len(self.Pvs)):
            Callsign = self.Pvs[i][1].get()
            for pv in self.Pvs[i + 1::]:
                if Callsign == pv[1].get():
                    self.Pvs[i][1].config(foreground='red')
                    pv[1].config(foreground='red')
                    self.Rev = True
                    break
                else:
                    Conf = self.Pvs[i][13].get()
                    if Conf != '':
                        self.Pvs[i][1].config(foreground='navy')
                    else:
                        self.Pvs[i][1].config(foreground='DeepSkyBlue2')

        # Comprobar si los niveles en los conflictos son iguales
        for i in range(0, len(self.Pvs)):
            if len(self.Pvs) > 3:

                if self.Pvs[i] != self.Pvs[-1] and self.Pvs[i] != self.Pvs[0]:  # i intermedio

                    Conf1 = self.Pvs[i - 1][13].get()
                    Conf2 = self.Pvs[i][13].get()
                    Conf3 = self.Pvs[i + 1][13].get()

                    if Conf1 != '' and Conf2 != '' and Conf3 != '':  # Plan de vuelo en conf entre 2 planes de vuelo en conf

                        Fl2 = False
                        Fl3 = False

                        if self.Pvs[i] != self.Pvs[-1]:
                            Fl2 = True

                        if self.Pvs[i] != self.Pvs[0]:
                            Fl3 = True

                        PvConf1 = self.Pvs[i - 1]
                        PvConf2 = self.Pvs[i]
                        PvConf3 = self.Pvs[i + 1]

                        if Fl2 and Fl3:  # self.PVs[i] Plan de vuelo de conflicto intermedio

                            if PvConf1[11].get() == PvConf2[11].get() and PvConf1[12].get() == PvConf2[12].get():
                                # Conflicto entre actual y ant
                                # Compruebo fijo y hora
                                if PvConf1[10].get() != PvConf2[10].get():

                                    PvConf1[10].config(foreground='red')
                                    PvConf2[10].config(foreground='red')
                                    self.Rev = True
                                else:
                                    PvConf1[10].config(foreground='navy')
                                    PvConf2[10].config(foreground='navy')
                            else:
                                if PvConf2[10].get() != PvConf3[10].get():  # Conflicto entre actual y posterior

                                    PvConf2[10].config(foreground='red')
                                    PvConf3[10].config(foreground='red')
                                    self.Rev = True
                                else:
                                    PvConf2[10].config(foreground='navy')
                                    PvConf3[10].config(foreground='navy')

                        elif Fl2 and not Fl3:  # self.PVs[i] Plan de vuelo de conflicto i = 0 (actual(primero) y posterior)

                            if PvConf2[10].get() != PvConf3[10].get():  # Conflicto entre actual y posterior

                                PvConf2[10].config(foreground='red')
                                PvConf3[10].config(foreground='red')
                                self.Rev = True
                            else:
                                PvConf2[10].config(foreground='navy')
                                PvConf3[10].config(foreground='navy')

                        elif Fl3 and not Fl2:  # self.PVs[i] Plan de vuelo de conflicto i = -1 (actual y anterior)

                            if PvConf1[10].get() != PvConf2[10].get():

                                PvConf1[10].config(foreground='red')
                                PvConf2[10].config(foreground='red')
                                self.Rev = True
                            else:
                                PvConf1[10].config(foreground='navy')
                                PvConf2[10].config(foreground='navy')

                elif self.Pvs[i] == self.Pvs[0]:
                    PvConf2 = self.Pvs[i]
                    PvConf3 = self.Pvs[i + 1]

                    if PvConf2[13].get() != '' and PvConf3[13].get() != '':
                        if PvConf2[10].get() != PvConf3[10].get():  # Conflicto entre actual y posterior

                            PvConf2[10].config(foreground='red')
                            PvConf3[10].config(foreground='red')
                            self.Rev = True
                        else:
                            PvConf2[10].config(foreground='navy')
                            PvConf3[10].config(foreground='navy')

                elif self.Pvs[i] == self.Pvs[-1]:
                    PvConf1 = self.Pvs[i - 1]
                    PvConf2 = self.Pvs[i]

                    if PvConf1[13].get() != '' and PvConf2[13].get() != '':
                        if PvConf1[10].get() != PvConf2[10].get():

                            PvConf1[10].config(foreground='red')
                            PvConf2[10].config(foreground='red')
                            self.Rev = True
                        else:
                            PvConf1[10].config(foreground='navy')
                            PvConf2[10].config(foreground='navy')

        # Comprobar si se ha introducido Hora de inicio del ejercicio
        if self.EntryH_IniH.get() == '' or self.EntryH_IniM.get() == '':
            self.LabelH_Ini.config(fg='red')
            self.Rev = True
        else:
            self.LabelH_Ini.config(fg='navy')

        # Comprobar si se ha introducido duracion del ejercicio
        if self.EntryH_Dur.get() == '' or self.EntryH_Dur.get() == '':
            self.LabelH_Dur.config(fg='red')
            self.Rev = True
        else:
            self.LabelH_Dur.config(fg='navy')

        # Comprobar si se ha introducido Hora en los pvs
        for i in range(len(self.Pvs)):
            hora = self.Pvs[i][12].get()
            if hora == '----':
                self.Pvs[i][12].config(foreground='red')
                self.Rev = True
            else:
                Conf = self.Pvs[i][13].get()
                if Conf != '':
                    self.Pvs[i][12].config(foreground='navy')
                else:
                    self.Pvs[i][12].config(foreground='DeepSkyBlue2')

        # Comprobar si se ha introducido Fijo en los pvs
        for i in range(len(self.Pvs)):
            Fix = self.Pvs[i][11].get()
            if Fix == 'None':
                self.Pvs[i][11].config(foreground='red')
                self.Rev = True
            else:
                Conf = self.Pvs[i][13].get()
                if Conf != '':
                    self.Pvs[i][11].config(foreground='navy')
                else:
                    self.Pvs[i][11].config(foreground='DeepSkyBlue2')

    def named_exercise(self):

        ColorText = 'navy'
        Fuente = ('Helvetica 12 bold')

        self.popname = tix.Toplevel()

        ImgDir = os.path.join(conf.common_dir, 'img')
        IcoFile = os.path.join(ImgDir, 'GAMMASIM.ico')
        self.popname.iconbitmap(IcoFile)
        self.popname.title('Exercise Name')
        self.popname.geometry('300x200')

        Frame_label = tix.Frame(self.popname)
        Frame_label.pack(side=tix.TOP)

        Label_name = tix.Label(Frame_label, text='Introduzca Nombre del Ejercicio: ', fg=ColorText, bd=0, font=Fuente)
        Label_name.pack(side=tix.TOP, padx=2, pady=10)

        self.Entry_Name = tix.Entry(Frame_label, fg=ColorText, bd=0, font=Fuente, width=20)
        self.Entry_Name.pack(side=tix.TOP, padx=2, pady=10)

        Button_name = tix.Button(Frame_label, text='Guardar', font=('Helvetica 11 bold'),
                                 fg=ColorText, bg='SlateGray2', width=15, height=1, relief=tix.GROOVE)
        Button_name.pack(side=tix.TOP, padx=2, pady=10)
        Button_name.bind('<Button-1>', lambda event: self.save_exercise(event))

    def save_exercise(self, eventObject):

        self.WorkbookNameBase = 'C:\GAMMA\MuestraBase.xlsx'
        Name = self.Entry_Name.get()
        self.WorkbookName = 'C:\GAMMA\\' + str(Name) + '.xlsx'

        shutil.copy(self.WorkbookNameBase, self.WorkbookName)
        Workbook = openpyxl.load_workbook(self.WorkbookNameBase)
        Sheet = Workbook['Ejercicio']

        FirstExcelRow = 10
        RowCont = 0
        Sheet.cell(row=1, column=1).value = self.EntryAis.get()
        Sheet.cell(row=4, column=2).value = self.EntryH_IniH.get() + ':' + self.EntryH_IniM.get() + ':00'
        Sheet.cell(row=4, column=4).value = self.EntryH_Dur.get()

        for row in self.Pvs:

            ColumnCont = 0

            for element in row[1::]:
                Sheet.cell(row=RowCont + FirstExcelRow, column=ColumnCont + 1).value = str(element.get()).lstrip()
                ColumnCont += 1

            RowCont += 1

        Workbook.save(self.WorkbookName)

        self.popname.destroy()
        self.button_Timeline.config(state=tix.NORMAL)

    def generate_exercise(self, eventObject):

        self.revisar()

        if self.Rev == True:
            pass
        else:
            self.guardar_cambios(None)
            self.named_exercise()

    def load_timeline(self, eventObject):

        self.revisar()

        if self.Rev == True:

            pass

        else:
            Label_space = tix.Label(self.frame_header4_1, text='Cargando Timeline...', fg='navy', bd=0,
                                    font=('Helvetica 12 bold'))
            Label_space.pack(side=tix.TOP, pady=8)
            try:
                self.WorkbookName
                self.FileExercise = self.WorkbookName
            except:
                pass

            global gta
            logging.debug("Creating GTA object")
            if 'gta' not in globals():
                gta = GTA.GTA(conf)
            logging.info("Loading scenario and exercise")
            gta.load(self.FileExercise)
            gta.confl(gta.flights)
            logging.debug("Starting GTA thread")

            try:
                self.wint
                for child in self.win.winfo_children():
                    child.destroy()
            except:
                self.wint = tix.Toplevel()
                self.w = self.wint.winfo_screenwidth()
                self.h = self.wint.winfo_screenheight()
                self.wint.title('TIMELINE ' + self.FileExercise)
                img_dir = os.path.join(conf.common_dir, 'img')
                ico_file = os.path.join(img_dir, 'GAMMASIM.ico')
                self.wint.iconbitmap(ico_file)
                self.wint.state('zoomed')

            Label_space.destroy()
            Timeline.Timeline(self, gta)

            # self.update_window()



class NewExercise(InterfaceCommElements):

    def __init__(self):
        InterfaceCommElements.__init__(self)
        InterfaceCommElements.pp_window(self)
        InterfaceCommElements.pp_frames(self)
        InterfaceCommElements.pp_elements(self)
        InterfaceCommElements.pp_elements_init_values(self)
        self.button_Timeline.config(state=tix.DISABLED)

        ################################### Call function to fill pp window labels
        InterfaceCommElements.labels(self)
        ################################### Call function to create scrollbar
        InterfaceCommElements.scroll(self)



class EditExercise(InterfaceCommElements):

    def __init__(self, exercise):

        exercise
        self.FileExercise = exercise

        InterfaceCommElements.__init__(self)
        self.edit()

    def edit(self):

        workbook = openpyxl.load_workbook(self.FileExercise)
        sheet = workbook['Ejercicio']
        first_excel_row = 10
        PVs_Ini = []

        for row in range(0, sheet.max_row):

            if (sheet.cell(row=row + first_excel_row, column=1).value) == None:
                break

            pv = []
            for j in range(1, len(self.Lab) + 1):
                if sheet.cell(row=row + first_excel_row, column=j).value == 'None':
                    value = ''
                else:
                    value = str(sheet.cell(row=row + first_excel_row, column=j).value)
                pv.append(value)

            PVs_Ini.append(pv)

        self.Time = sheet.cell(row=4, column=2).value
        self.Dur = sheet.cell(row=4, column=4).value

        InterfaceCommElements.pp_window(self)
        InterfaceCommElements.pp_frames(self)
        InterfaceCommElements.pp_elements(self)
        InterfaceCommElements.pp_elements_init_values(self)

        ################################### Call function to fill pp window labels
        InterfaceCommElements.labels(self)
        ################################### Call function to create scrollbar
        InterfaceCommElements.scroll(self)

        self.EntryAis.insert(0, str(sheet.cell(row=1, column=1).value))
        self.EntryH_IniH.insert(0, str(self.Time[0:2]))
        self.EntryH_IniM.insert(0, str(self.Time[3:5]))
        self.EntryH_Dur.insert(0, '60')
        self.button_Timeline.config(state=tix.NORMAL)

        self.Fl = False
        fill_pvs(self, False, False, PVs_Ini)



# NO SE ESTAN USANDO EN ESTA VERSION
def Ord_Exer(self, eventObject):

    list_pvs_ord = []

    Modo = 0  # self.cmbMode.get()

    if Modo == 'Por Conflicto':

        # if isinstance(self.PVs[0][0], str):

        #    self.PVs.sort(key=lambda x: x[0])
        #    self.fill_desh()
        # else:
        self.PVs.sort(key=lambda x: x[0].get())
        self.fill_ord()

    else:
        # if isinstance(self.PVs[0][0], str):

        #     self.PVs.sort(key=lambda x: x[13])
        #     self.fill_desh()
        # else:
        self.PVs.sort(key=lambda x: x[13].get())
        self.fill_ord()

def fill_ord(self):

    fontstyle = 'Helvetica 8'

    x = 5
    w = 15

    self.list_pvs = []
    self.list_pvs_ord = []
    self.z = 0
    self.cont = 1

    for pv in self.PVs:
        p = pv[13].get()
        if p != '':

            style = "EntryStyle1.TEntry"

        else:
            style = "EntryStyle2.TEntry"

        self.cellBaseEntry0 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style,
                                        font=('Helvetica 10 bold'))
        self.cellBaseEntry0.insert(0, pv[0].get())
        self.cellBaseEntry0.grid(row=self.z, column=0, pady=x)

        self.cellBaseEntry0 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry0.insert(0, pv[1].get())
        self.cellBaseEntry0.grid(row=self.z, column=1, pady=x)

        self.cellBaseEntry1 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry1.insert(0, pv[2].get())
        self.cellBaseEntry1.grid(row=self.z, column=2, pady=x)

        self.cellBaseEntry2 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry2.insert(0, pv[3].get())
        self.cellBaseEntry2.grid(row=self.z, column=3, pady=x)

        self.cellBaseEntry3 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry3.insert(0, pv[4].get())
        self.cellBaseEntry3.grid(row=self.z, column=4, pady=x)

        self.cellBaseEntry4 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry4.insert(0, pv[5].get())
        self.cellBaseEntry4.grid(row=self.z, column=5, pady=x)

        # var5 = tix.StringVar()
        # var5.set(str(LoadPV[i, 5]))
        self.cellBaseEntry5 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=55, style=style, font=(fontstyle))
        self.cellBaseEntry5.insert(0, pv[6].get())
        self.cellBaseEntry5.grid(row=self.z, column=6, pady=x)

        # var6 = tix.StringVar()
        # var6.set(str(LoadPV[i, 6]))
        self.cellBaseEntry6 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry6.insert(0, pv[7].get())
        self.cellBaseEntry6.grid(row=self.z, column=7, pady=x)

        # var7 = tix.StringVar()
        # var7.set(str(LoadPV[i, 7]))
        self.cellBaseEntry7 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry7.insert(0, pv[8].get())
        self.cellBaseEntry7.grid(row=self.z, column=8, pady=x)

        # var8 = tix.StringVar()
        # var8.set(str(LoadPV[i, 8]))
        self.cellBaseEntry8 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry8.insert(0, pv[9].get())
        self.cellBaseEntry8.grid(row=self.z, column=9, pady=x)

        # var9 = tix.StringVar()
        # var9.set(str(LoadPV[i, 9]))
        self.cellBaseEntry9 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry9.insert(0, pv[10].get())
        self.cellBaseEntry9.grid(row=self.z, column=10, pady=x)

        # var10 = tix.StringVar()
        # var10.set(str(LoadPV[i, 10]))
        self.cellBaseEntry10 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry10.insert(0, pv[11].get())
        self.cellBaseEntry10.grid(row=self.z, column=11, pady=x)

        # var11 = tix.StringVar()
        # var11.set(str(LoadPV[i, 11]))
        self.cellBaseEntry11 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry11.insert(0, pv[12].get())
        self.cellBaseEntry11.grid(row=self.z, column=12, pady=x)

        # var12 = tix.StringVar()
        # var12.set(str(LoadPV[i, 12]))
        self.cellBaseEntry12 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry12.insert(0, pv[13].get())  # Hora)
        self.cellBaseEntry12.grid(row=self.z, column=13, pady=x)

        # var13 = tix.StringVar()
        # var13.set(str(LoadPV[i, 13]))
        self.cellBaseEntry13 = ttk.Entry(self.frame_in, justify=tix.CENTER, width=w, style=style, font=(fontstyle))
        self.cellBaseEntry13.insert(0, pv[14].get())
        self.cellBaseEntry13.grid(row=self.z, column=14, pady=x)

        self.list_pvs_ord.append((self.cellBaseEntry, self.cellBaseEntry0, self.cellBaseEntry1,
                                  self.cellBaseEntry2, self.cellBaseEntry3, self.cellBaseEntry4,
                                  self.cellBaseEntry5, self.cellBaseEntry6, self.cellBaseEntry7,
                                  self.cellBaseEntry8, self.cellBaseEntry9, self.cellBaseEntry10,
                                  self.cellBaseEntry11, self.cellBaseEntry12, self.cellBaseEntry13))

        self.z += 1

    self.externalcanvas.update_idletasks()
    self.externalcanvas.config(scrollregion=self.externalcanvas.bbox(tix.ALL))
