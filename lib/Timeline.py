
import Tix as tix

import datetime
import ttk
from openpyxl import load_workbook
from openpyxl.chart.axis import DateAxis
from openpyxl.chart import (
    LineChart,
    Reference,
)
import subprocess
import numpy as np
import Tkinter as tk
import matplotlib.pyplot as plt

#from ExenGenSV import Gen_Exercise_1204, EditExercise_1204
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class Timeline(object):

    def __init__(variable, self, gta):

        variable.gta = gta
        variable.exe_file = variable.gta.exercise_file
        variable.sectores_fir = []
        variable.camps_ejerc = self.Etiq
        variable.flag_init = True

        #variable.sector = variable.gta.sector  # Sector definido en ejercicio -> Campo posicion
        sectores_fir = variable.gta.fir.sectors # Contiene_sectores fir [ZML,ZMM,ZMU,CJL,CJU,TER,ZGZ,TLL,TLU]
        for sector in sectores_fir:
            variable.sectores_fir.append(sector[0:2])

        sectores = np.unique(variable.sectores_fir)
        variable.sectores_fir = []
        for string in sectores:
            variable.sectores_fir.append(string)

        try:
            time_str = self.EntryH_Ini.get()
        except:
            time_str = str(self.EntryH_Ini)

        time_inicio = datetime.datetime.strptime(time_str, '%H:%M:%S').time()
        variable.tday = datetime.datetime.today()

        variable.datetime_inicio = datetime.datetime.combine(variable.tday.date(), time_inicio)

        variable.dragging_bgcolor = 'grey'
        variable.bgcolor = 'white'
        variable.bdcolor = 'gray'
        variable.selected_bdcolor = 'blue'
        variable.text_color = 'black'
        variable.text_color_etq = 'black'

        variable.pnts_sector = self.Fijos

        variable.win = self.win
        variable.w = self.w
        variable.h = self.h

        variable.init_x = 8
        variable.init_y = 15
        variable.delta_x = 0.5  # pixels per second
        variable.delta_y = 25   # spacing inbetween rows
        variable.delta_callsign = 57
        variable.w_etq = 60
        variable.delta_conf = 50
        variable.button_color = 'grey'

        variable.win.protocol("WM_DELETE_WINDOW", variable.hide)
        variable.win.bind('<Right>', variable.rightKey)
        variable.win.bind('<Control-Right>', variable.CtrlrightKey)
        variable.win.bind('<Left>', variable.leftKey)
        variable.win.bind('<Control-Left>', variable.CtrlleftKey)


        variable.window = tix.Frame(variable.win, width=variable.w, height=variable.h / 2)
        variable.window.pack(side=tix.TOP)

        variable.window.update_idletasks()

        variable._build()

    def _build(variable, **kw):

        variable.ficha_width = variable.w - 20
        variable.ficha_height = 30
        variable.time_exer = []
        delta = datetime.timedelta(minutes=1)
        tim = variable.datetime_inicio
        ############
        for t in range(4, 65, 1):

            inc = tim.time()
            # To add a 0 before minute, when minute < 10
            if inc.minute in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] and inc.hour not in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]:

                variable.time_exer.append(str(inc.hour) + ':0' + str(inc.minute))

            elif inc.minute not in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] and inc.hour in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]:

                variable.time_exer.append('0' + str(inc.hour) + ':' + str(inc.minute))

            elif inc.minute in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] and inc.hour in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]:

                variable.time_exer.append('0' + str(inc.hour) + ':0' + str(inc.minute))

            else:
                variable.time_exer.append(str(inc.hour) + ':' + str(inc.minute))

            tim = tim + delta

        variable.Button_save = tix.Button(variable.window, text='Exportar Ejercicio', relief=tix.GROOVE, bg=variable.button_color,
                                          command=variable.solv_conflict)
        variable.Button_save.pack(side=tix.TOP, fill=tix.X)
        variable.Button_save = tix.Button(variable.window, text='Actualizar Timeline', relief=tix.GROOVE, bg=variable.button_color,
                                          command=variable.actualizar_timeline)
        variable.Button_save.pack(side=tix.TOP, fill=tix.X)

        variable.frame_check = tix.Frame(variable.window)
        variable.frame_check.pack(side=tix.TOP, fill=tix.BOTH)

        variable.frame_check_Left = tix.Frame(variable.frame_check)
        variable.frame_check_Left.pack(side=tix.LEFT, fill=tix.BOTH)
        variable.frame_check_Right = tix.Frame(variable.frame_check)
        variable.frame_check_Right.pack(side=tix.RIGHT, fill=tix.BOTH)

        variable.lst_var_sect = []
        i = 50
        for sector in variable.sectores_fir:
            var = tk.IntVar()
            Sector_Check = tk.Checkbutton(variable.frame_check_Left, text=sector, variable=var).grid(row=0, column=i)
            variable.lst_var_sect.append(var)
            var.set(1)
            i += 1


        i = 50
        j = 1
        variable.radio_var = tk.StringVar()
        for sector in variable.sectores_fir:
            Sector_Radio = tk.Radiobutton(variable.frame_check_Left, text=sector, variable=variable.radio_var, value=sector, command=variable.sel_sector).grid(row=1, column=i)
            i += 1
            j += 1
        variable.radio_var.set(variable.sectores_fir[-1])
        label_graphs = tk.Label(variable.frame_check_Left, text='Graficas de los sectores: ', font="Georgia 8 bold").grid(row=0, column=20)
        label_timeline = tk.Label(variable.frame_check_Left, text='Timeline del sector: ', font="Georgia 8 bold").grid(row=1, column=20)

        variable.Button_graphs = tix.Button(variable.frame_check_Right, text='Visualizar', relief=tix.GROOVE,
                                          bg=variable.button_color, command=variable.actualizar_graph)
        variable.Button_graphs.pack(side=tix.TOP, fill=tix.X)

        variable.panel_time = tix.Frame(variable.window)
        variable.panel_time.pack(side=tix.TOP, fill=tix.X)

        canvas = tix.Canvas(variable.panel_time, bg=variable.bgcolor, bd=0, highlightthickness=0, takefocus=0,
                            width=variable.ficha_width,
                            height=variable.ficha_height)

        canvas.grid(row=0, column=0, sticky=tix.NW)

        i = 0
        for x_entry in range(0, variable.ficha_width, 30):


            canvas.verticalBorder = canvas.create_line(x_entry + variable.delta_callsign, 0,
                                                       x_entry + variable.delta_callsign,
                                                       variable.ficha_height - 1, fill='grey', width=1)

            canvas.create_text(x_entry + 16 + variable.delta_callsign, variable.init_y, text=variable.time_exer[i],
                               font="Courier 7 bold", fill=variable.text_color)

            if variable.time_exer[i] == variable.time_exer[-1]:
                canvas.verticalBorder = canvas.create_line(x_entry + variable.delta_callsign, 0,
                                                           x_entry + variable.delta_callsign,
                                                           variable.ficha_height - 1, fill='grey', width=1)
                break
            else:
                i += 1


        variable.panel_top = tix.Frame(variable.window, width=variable.w, height=variable.h / 2, bg='gray', highlightcolor='black', highlightthickness=1)
        variable.panel_top.pack(side=tix.TOP)

        variable.panel_bot = tix.Frame(variable.window, width=variable.w, height=variable.h / 2, bg='gray', highlightcolor='black', highlightthickness=1)
        variable.panel_bot.pack(side=tix.TOP)

        #####Add a scrollbar in each pannel. An external canvas is required to do it
        yscrollbar = tix.Scrollbar(variable.panel_top, orient=tix.VERTICAL)
        yscrollbar.pack(side=tix.RIGHT, fill=tix.Y)

        variable.external_canvas = tix.Canvas(variable.panel_top, width=variable.w, height=variable.h / 2, bg='gray')
        variable.external_canvas.pack(side=tix.TOP)


        yscrollbar.config(command=variable.external_canvas.yview)
        variable.external_canvas.config(yscrollcommand=yscrollbar.set)

        ###########
        ###########

        variable.framein = tix.Frame(variable.external_canvas, bg='gray')
        variable.framein.grid(row=0, column=0, sticky=tix.NW)

        ###########
        ###########

        variable.external_canvas.create_window(0, variable.h / 2, window=variable.framein, anchor=tix.NW)
        variable.external_canvas.update_idletasks()
        variable.external_canvas.config(scrollregion=variable.external_canvas.bbox(tix.ALL))
        # Init Timeline -> Default values
        variable.estados = map((lambda var: var.get()), variable.lst_var_sect)
        variable.sector_select = str(variable.radio_var.get())
        ################################### Call function to create Times
        variable.crear_timeline()
        ################################### Call function to create Graphics
        variable.crear_grafico()

    def actualizar_graph(variable):

        variable.estados = map((lambda var: var.get()), variable.lst_var_sect)
        variable.crear_timeline()

       # if variable.flag_init == True:
            ################################### Call function to create Graphics
        variable.crear_grafico()
        #    variable.flag_init = False
        #else:
        #    pass

    def sel_sector(variable):

        variable.estados = map((lambda var: var.get()), variable.lst_var_sect)
        variable.sector_select = str(variable.radio_var.get())
        variable.ver_timeline()

    def hide(variable):
        variable.win.destroy()
        return

    def actualizar_timeline(variable):

        '''

        Open exercise sheet from excel file, rewrite update pv data for each change pv canvas timeline,
        delete all child canvas timeline and reload data pvs and visualize new canvas timeline.

        :return: None
        '''

        try:
            variable.p
            subprocess.Popen("taskkill /F /IM EXCEL.EXE", shell=True)
        except:
            pass

        wb = load_workbook(filename=variable.exe_file)
        ws = wb['Ejercicio']

        gsize = variable.framein.grid_size()
        nrows = gsize[1]

        for irow in range(0, nrows):

            c = variable.framein.grid_slaves(row=irow, column=0)[1]
            timeline_info = c.timeline_info
            route = timeline_info['route']
            callsign = timeline_info['callsign']
            hora = timeline_info['Hora']
            fijo = timeline_info['Fijo']

            pos_param_hora = variable.camps_ejerc.index('Hora')

            for i in range(1, ws.max_row):

                # Search row for pv
                if ws.cell(row=i, column=1).value == callsign:

                    # Modifica la estimada
                    for wp in route:

                        if wp.fix == fijo:
                            ws.cell(row=i, column=pos_param_hora+1).value = str(hora.time())
                            break
                    continue

        wb.save(variable.exe_file)

        for child in variable.framein.winfo_children():
            child.destroy()

       ##################### Call function to reload data pvs exercise
        variable.gta.reload_exercise()
        variable.gta.confl(variable.gta.flights)
        ################################### Call function to create Timeline
        variable.crear_timeline()
        ################################### Call function to create Graphics
        variable.crear_grafico()

    def rightKey(variable, event):

        '''

        Advance 1 minute in selected canvas timeline.

        :return: None
        '''
        variable.move_selected_timelines(60)

    def CtrlrightKey(variable, event):

        '''

        Advance 1 second in selected canvas timeline.

        :return: None
        '''

        variable.move_selected_timelines(1)

    def leftKey(variable, event):

        '''

        1 minute in selected canvas timeline.

        :return: None
        '''

        variable.move_selected_timelines(-60)

    def CtrlleftKey(variable, event):

        '''

        1 second in selected canvas timeline.

        :return: None
        '''

        variable.move_selected_timelines(-1)

    def move_selected_timelines(variable, delta):
        '''

        Update data time for route pv selected and rewrite it.

        :param {int} delta: contains the time increment or decrement
        :return: None
        '''

        gsize = variable.framein.grid_size()
        nrows = gsize[1]
        variable.Timeline_Graph = []
        variable.cont_pvs = 0

        for irow in range(0, nrows):

            c = variable.framein.grid_slaves(row=irow, column=0)[1]
            if c.timeline_info['selected']:

                # Mover conflictos juntos aunque no esten seleccionados ambos (Cuando son conflictos definidos No reales)
                if c.timeline_info['Color_Sector'] == 'green':
                    if irow == 0:
                        c1 = None
                        c2 = variable.framein.grid_slaves(row=irow + 1, column=0)[1]
                    elif irow == nrows:
                        c1 = variable.framein.grid_slaves(row=irow - 1, column=0)[1]
                        c2 = None
                    else:
                        c1 = variable.framein.grid_slaves(row=irow - 1, column=0)[1]
                        c2 = variable.framein.grid_slaves(row=irow + 1, column=0)[1]

                    if c1 != None and c1.timeline_info['Color_Sector'] == 'green':

                        timeline_info = c1.timeline_info

                        c1.timeline_info['Hora'] = c1.timeline_info['Hora'] + datetime.timedelta(seconds=delta)
                        route = timeline_info['route']

                        # Update each time from route way-points
                        for wp in route:
                            wp.eto = wp.eto + datetime.timedelta(seconds=delta)

                        c1.grid_forget()
                        variable.insertar_timeline(insert_row=irow-1, **timeline_info)

                    elif c2 != None and c2.timeline_info['Color_Sector'] == 'green':

                        timeline_info = c2.timeline_info

                        c2.timeline_info['Hora'] = c2.timeline_info['Hora'] + datetime.timedelta(seconds=delta)
                        route = timeline_info['route']

                        # Update each time from route way-points
                        for wp in route:
                            wp.eto = wp.eto + datetime.timedelta(seconds=delta)

                        c2.grid_forget()
                        variable.insertar_timeline(insert_row=irow+1, **timeline_info)
                    else:
                        pass
                # Mover conflictos juntos aunque no esten seleccionados ambos (Cuando son conflictos definidos Reales)
                if c.timeline_info['Color_Sector'] == 'tomato':
                    if irow == 0:
                        c1 = None
                        c2 = variable.framein.grid_slaves(row=irow + 1, column=0)[1]
                    elif irow == nrows:
                        c1 = variable.framein.grid_slaves(row=irow - 1, column=0)[1]
                        c2 = None
                    else:
                        c1 = variable.framein.grid_slaves(row=irow - 1, column=0)[1]
                        c2 = variable.framein.grid_slaves(row=irow + 1, column=0)[1]

                    if c1 != None and c1.timeline_info['Color_Sector'] == 'tomato':

                        timeline_info = c1.timeline_info

                        c1.timeline_info['Hora'] = c1.timeline_info['Hora'] + datetime.timedelta(seconds=delta)
                        route = timeline_info['route']

                        # Update each time from route way-points
                        for wp in route:
                            wp.eto = wp.eto + datetime.timedelta(seconds=delta)

                        c1.grid_forget()
                        variable.insertar_timeline(insert_row=irow - 1, **timeline_info)

                    elif c2 != None and c2.timeline_info['Color_Sector'] == 'tomato':

                        timeline_info = c2.timeline_info

                        c2.timeline_info['Hora'] = c2.timeline_info['Hora'] + datetime.timedelta(seconds=delta)
                        route = timeline_info['route']

                        # Update each time from route way-points
                        for wp in route:
                            wp.eto = wp.eto + datetime.timedelta(seconds=delta)

                        c2.grid_forget()
                        variable.insertar_timeline(insert_row=irow + 1, **timeline_info)
                    else:
                        pass

                timeline_info = c.timeline_info
                c.timeline_info['Hora'] = c.timeline_info['Hora'] + datetime.timedelta(seconds=delta)
                route = timeline_info['route']

                # Update each time from route way-points
                for wp in route:
                    wp.eto = wp.eto + datetime.timedelta(seconds=delta)

                c.grid_forget()

                    ################################### Call function to insert each canvas timeline
                variable.insertar_timeline(insert_row=irow, **timeline_info)

    def select_flight(variable, event, canvas):

        '''

        To identify if a canvas from timeline is select.

        :param {event} event: Data event object
        :param {canvas} canvas: Data canvas object
        :return: None
        '''

        canvas.timeline_info['selected'] = not canvas.timeline_info['selected']

        if canvas.timeline_info['selected']: #or canvas_etq.timeline_info['selected']:

            canvas.itemconfig(canvas.myborder, outline=variable.selected_bdcolor)

        else:

            canvas.itemconfig(canvas.myborder, outline=variable.bdcolor)

    def ver_timeline(variable):

        '''
        Load each pv data from gta and visualize on a canvas timeline.

        :param {dict} timeline_info: Contains some necessary data from each pv to create canvas timeline
        :return: None

        '''


        variable.datos_sectores = {}
        timeline_info = {}

        variable.PVs_Timeline = []
        variable.conflict = []
        variable.conflict = variable.gta.t_alerts

        insert_row = 0
        variable.cont_pvs = 0

        # Open Work load Sheet
        wb = load_workbook(variable.exe_file)
        ws = wb['Ejercicio']

        for i in range(10, ws.max_row):
            if ws.cell(row=i, column=1).value == None:
                break

            PV = []

            for j in range(1, len(variable.camps_ejerc) + 1):
                PV.append(ws.cell(row=i, column=j).value)

            variable.PVs_Timeline.append(PV)


        for e in range(len(variable.estados)):
            timeline_info_otro = {}
            variable.callsign = []
            variable.Timeline_Graph = []
            variable.Timeline_Graph_conf = []
            variable.Timeline_Graph_Tot = []

            estado = variable.estados[e]
            sector = variable.sectores_fir[e]
            if estado == 1:

                if sector == variable.sector_select:

                 # Se pinta el timeline del sector seleccionado y se almacenan los datos. ########################
                    for f in variable.gta.flights:

                        timeline_info['callsign'] = f.callsign
                        variable.callsign.append(f.callsign)

                        for fl in variable.PVs_Timeline:

                            if f.callsign == fl[0]:
                                timeline_info['Conflicto'] = fl[variable.camps_ejerc.index('Conflicto')]
                                timeline_info['Solucion'] = fl[variable.camps_ejerc.index('Solucion')]
                                timeline_info['Fijo'] = fl[variable.camps_ejerc.index('Fijo')]

                                time_inicio = datetime.datetime.strptime(str(fl[variable.camps_ejerc.index('Hora')]), '%H:%M:%S').time()
                                date_time = datetime.datetime.combine(variable.tday.date(), time_inicio)
                                timeline_info['Hora'] = date_time
                                break

                        if len(f.log) == 0 and len(f.route) != 0:  # Only f.route

                            timeline_info['route'] = f.route

                        elif len(f.log) != 0 and len(f.route) != 0:  # f.route and f.log

                            timeline_info['route'] = f.log + f.route


                        else:
                            timeline_info['route'] = f.log  # Only f.log

                        timeline_info['selected'] = False
                        timeline_info['ifl'] = f.ifl
                        timeline_info['cfl'] = f.cfl

                        ################################### Call function to insert each canvas timeline
                        variable.insertar_timeline(insert_row=insert_row, **timeline_info)
                        variable.cont_pvs += 1
                        # Update scroll bar
                        insert_row += 1


                    variable.external_canvas.update_idletasks()
                    variable.external_canvas.config(scrollregion=variable.external_canvas.bbox(tix.ALL))

                else:
                    pass

    def crear_timeline(variable):

        '''
        Load each pv data from gta and visualize on a canvas timeline.

        :param {dict} timeline_info: Contains some necessary data from each pv to create canvas timeline
        :return: None

        '''


        variable.datos_sectores = {}
        timeline_info = {}

        variable.PVs_Timeline = []
        variable.conflict = []
        variable.conflict = variable.gta.t_alerts

        insert_row = 0
        variable.cont_pvs = 0

        # Open Work load Sheet
        wb = load_workbook(variable.exe_file)
        ws = wb['Ejercicio']

        for i in range(10, ws.max_row):
            if ws.cell(row=i, column=1).value == None:
                break

            PV = []

            for j in range(1, len(variable.camps_ejerc) + 1):
                PV.append(ws.cell(row=i, column=j).value)

            variable.PVs_Timeline.append(PV)


        for e in range(len(variable.estados)):
            timeline_info_otro = {}
            variable.callsign = []
            variable.Timeline_Graph = []
            variable.Timeline_Graph_conf = []
            variable.Timeline_Graph_Tot = []

            estado = variable.estados[e]
            sector = variable.sectores_fir[e]
            if estado == 1:

                if sector == variable.sector_select:

                 # Se pinta el timeline del sector seleccionado y se almacenan los datos. ########################
                    for f in variable.gta.flights:

                        timeline_info['callsign'] = f.callsign
                        variable.callsign.append(f.callsign)

                        for fl in variable.PVs_Timeline:

                            if f.callsign == fl[0]:
                                timeline_info['Conflicto'] = fl[variable.camps_ejerc.index('Conflicto')]
                                timeline_info['Solucion'] = fl[variable.camps_ejerc.index('Solucion')]
                                timeline_info['Fijo'] = fl[variable.camps_ejerc.index('Fijo')]

                                time_inicio = datetime.datetime.strptime(str(fl[variable.camps_ejerc.index('Hora')]), '%H:%M:%S').time()
                                date_time = datetime.datetime.combine(variable.tday.date(), time_inicio)
                                timeline_info['Hora'] = date_time
                                break

                        if len(f.log) == 0 and len(f.route) != 0:  # Only f.route

                            timeline_info['route'] = f.route

                        elif len(f.log) != 0 and len(f.route) != 0:  # f.route and f.log

                            timeline_info['route'] = f.log + f.route


                        else:
                            timeline_info['route'] = f.log  # Only f.log

                        timeline_info['selected'] = False
                        timeline_info['ifl'] = f.ifl
                        timeline_info['cfl'] = f.cfl

                        ################################### Call function to insert each canvas timeline
                        variable.insertar_timeline(insert_row=insert_row, **timeline_info)
                        variable.cont_pvs += 1
                        # Update scroll bar
                        insert_row += 1


                    variable.external_canvas.update_idletasks()
                    variable.external_canvas.config(scrollregion=variable.external_canvas.bbox(tix.ALL))

                    variable.datos_sectores[sector] = {}
                    variable.datos_sectores[sector]['Timeline'] = {}
                    variable.datos_sectores[sector]['Timeline'] = variable.Timeline_Graph_Tot
                    variable.gen_datos_graph(sector)
                    print()

                else:

                # Se almacenan los datos del timeline y del graph. ########################
                    for f in variable.gta.flights:

                        timeline_info_otro['callsign'] = f.callsign
                        variable.callsign.append(f.callsign)

                        for fl in variable.PVs_Timeline:

                            if f.callsign == fl[0]:
                                timeline_info_otro['Conflicto'] = fl[variable.camps_ejerc.index('Conflicto')]
                                timeline_info_otro['Solucion'] = fl[variable.camps_ejerc.index('Solucion')]
                                timeline_info_otro['Fijo'] = fl[variable.camps_ejerc.index('Fijo')]

                                time_inicio = datetime.datetime.strptime(str(fl[variable.camps_ejerc.index('Hora')]),
                                                                         '%H:%M:%S').time()
                                date_time = datetime.datetime.combine(variable.tday.date(), time_inicio)
                                timeline_info_otro['Hora'] = date_time
                                break

                        if len(f.log) == 0 and len(f.route) != 0:  # Only f.route

                            timeline_info_otro['route'] = f.route

                        elif len(f.log) != 0 and len(f.route) != 0:  # f.route and f.log

                            timeline_info_otro['route'] = f.log + f.route


                        else:
                            timeline_info_otro['route'] = f.log  # Only f.log

                        timeline_info_otro['selected'] = False
                        timeline_info_otro['ifl'] = f.ifl
                        timeline_info_otro['cfl'] = f.cfl

                        ################################### Call function to insert each canvas timeline
                        for el in variable.gta.fir.sectors:

                            if el[0:2] == sector:
                                sect = el[0:2]
                        variable.Datos_Timeline(sect, **timeline_info_otro)
                        variable.cont_pvs += 1
                    variable.datos_sectores[sector] = {}
                    variable.datos_sectores[sector]['Timeline'] = {}
                    variable.datos_sectores[sector]['Timeline'] = variable.Timeline_Graph_Tot
                    variable.gen_datos_graph(sector)
                    print()

    def insertar_timeline(variable, insert_row=0, **timeline_info):

        '''

        Create each canvas pv timeline with callsign, way-points, conflicts and times data,
        visualize a line while pv is in selected sector.

        :param {int} insert_row: Count variable to identifier each pv canvas
        :param {dict} timeline_info: Contains some necessary data from each pv to create canvas timeline
        :return: None

        '''

        fijo = str(timeline_info['Fijo'])
        hora = timeline_info['Hora']
        tipo_conf = str(timeline_info['Conflicto'])
        sol_conf = str(timeline_info['Solucion'])

        callsign = timeline_info['callsign']
        route = timeline_info['route']
        selected = timeline_info['selected']
        ifl = str(int(timeline_info['ifl']))
        cfl = str(int(timeline_info['cfl']))
        color_in_sector = 'dodger blue'

        ###########
        ###############

        canvas = tix.Canvas(variable.framein, bg=variable.bgcolor, bd=0, highlightthickness=0, takefocus=0,
                            width=variable.ficha_width,
                            height=variable.ficha_height)

        canvas.grid(row=insert_row, column=0)

        if tipo_conf != 'None':
            for c in variable.conflict:
                if callsign in c:
                    fijo_conf = fijo
                    variable.Timeline_Graph_conf.append((callsign, fijo, str(hora.time()), tipo_conf, sol_conf))
                    color_in_sector = 'tomato'

            if color_in_sector != 'tomato':
                fijo_conf = fijo
                variable.Timeline_Graph_conf.append((callsign, fijo, str(hora.time()), tipo_conf, sol_conf))
                color_in_sector = 'green'

        else:
            for c in variable.conflict:
                if callsign in c:
                    fijo_conf = fijo
                    color_in_sector = 'DarkOrchid2'
                    break

                else:
                    color_in_sector = 'dodger blue'

        timeline_info['Color_Sector'] = color_in_sector
        canvas_etq = tix.Canvas(variable.framein, bg=variable.bgcolor, bd=0, highlightthickness=0, takefocus=0, width=variable.w_etq,
                                height=variable.ficha_height)
        canvas_etq.grid(row=insert_row, column=0, sticky=tix.NW)

        canvas.myborder = canvas.create_rectangle(0, 0, variable.ficha_width - 2, variable.ficha_height - 2,
                                                  outline=variable.bdcolor, width=1)

        for x_entry in range(0, variable.ficha_width, 30):

            canvas.verticalBorder = canvas.create_line(x_entry + variable.delta_callsign, 0,
                                                       x_entry + variable.delta_callsign,
                                                       variable.ficha_height - 1, fill='grey', width=1)

        canvas_etq.create_text(variable.init_x, 2, anchor="nw", text=callsign, font="Courier 7 bold", fill=variable.text_color_etq)
        canvas_etq.create_text(variable.init_x, variable.ficha_height - 2, anchor="sw", text=ifl + ' ' + cfl,
                               font="Courier 7 bold", fill=variable.text_color_etq)

        canvas_etq.create_rectangle(0, 0, variable.delta_callsign, variable.ficha_height - 2,
                                    outline=color_in_sector, width=2)
        if selected:
            canvas.itemconfig(canvas.myborder, outline=variable.selected_bdcolor)

        canvas.bind("<Button-1>", lambda event, canvas=canvas: variable.select_flight(event, canvas))

        delta_time_entry = 0
        delta_time_exit = int(variable.ficha_width - (variable.init_x + variable.delta_callsign) / variable.delta_x)

        variable.Timeline_Graph = []
        puntos = []
        Horas = []
        Times_canvas = []
        Text_Color = []

        for wp in route:

            fix = wp.fix
            eto = wp.eto
            eto_str = str(eto)[11:16]
            delta_time = int((wp.eto - variable.datetime_inicio).total_seconds())
            flg = 0

            if wp == route[-1] and len(variable.Timeline_Graph) >= 1 and 'In' in variable.Timeline_Graph[-1]:
                variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))
                flg = 1
                delta_time_exit = delta_time
                fix = fix

            if wp.sector_entry and (all(x[0:2] in variable.sector_select for x in wp.sector_entry)):

                if len(variable.Timeline_Graph) >= 1 and 'In' in variable.Timeline_Graph[-1] and flg == 1:
                    pass
                else:
                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'In'))

                    if delta_time_entry == 0:
                        delta_time_entry = delta_time
                    else:
                        pass

                    fix = fix

            elif wp.sector_exit and (all(x[0:2] in variable.sector_select for x in wp.sector_exit)):

                if 'Out' in variable.Timeline_Graph[-1]:

                    del variable.Timeline_Graph[-1]
                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))

                else:

                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))

                delta_time_exit = delta_time
                fix = fix

            elif fix == fijo:
                fix = fix

            elif not wp.sector_entry and not wp.sector_exit and flg == 1:
                pass
            else:
                continue

            if delta_time >= 0:

                if tipo_conf != 'None' and fix == str(fijo_conf):
                    variable.text_color = 'red3'

                else:
                    variable.text_color = 'black'
                for c in variable.conflict:

                    if callsign in c[1]:

                        Etq = canvas.create_text(variable.init_x + variable.delta_callsign + variable.delta_x + variable.w_etq,
                                           variable.init_y, anchor="s", text='C_' + c[2], font="Courier 8 bold", fill=color_in_sector)
                        canvas.tag_lower(Etq)

                        Lev = canvas.create_text(variable.init_x + variable.delta_callsign + variable.delta_x + variable.w_etq,
                                           variable.init_y + 12, anchor="s", text=c[0], font="Courier 8 bold", fill=color_in_sector)
                        canvas.tag_lower(Lev)

                    elif callsign in c[2]:

                        Etq = canvas.create_text(variable.init_x + variable.delta_callsign + variable.delta_x + variable.w_etq,
                                           variable.init_y, anchor="s", text='C_' + c[1], font="Courier 8 bold", fill=color_in_sector)
                        canvas.tag_lower(Etq)

                        Lev = canvas.create_text(variable.init_x + variable.delta_callsign + variable.delta_x + variable.w_etq,
                                           variable.init_y + 12, anchor="s", text=c[0], font="Courier 8 bold", fill=color_in_sector)
                        canvas.tag_lower(Lev)

                    else:
                        pass

                if (all(x in fix for x in ['X-', 'Y-', '.'])) or (all(x in fix for x in ['X', 'Y', '.'])):

                    if len(variable.Timeline_Graph) >= 1 and variable.Timeline_Graph[-1][3] == 'Out':

                        fix = 'Exit_Sector'
                    else:
                        fix = 'Entry_Sector'

                    if fix not in puntos and eto_str not in Horas:

                        Horas.append(eto_str)
                        puntos.append(fix)
                        Times_canvas.append(delta_time)
                        Text_Color.append(variable.text_color)

                    else: pass

                else:
                    if fix not in puntos and eto_str not in Horas or fix == fijo:

                        Horas.append(eto_str)
                        puntos.append(fix)
                        Times_canvas.append(delta_time)
                        Text_Color.append(variable.text_color)

                    else: pass

        variable.Rell_Timeline(Times_canvas, Horas, puntos, Text_Color, fijo, canvas, callsign, fix, color_in_sector)
        canvas.timeline_info = timeline_info

    def Rell_Timeline(variable, Times_canvas, Horas, puntos, Text_Color, fijo, canvas, callsign, fix, color_in_sector):

        if len(Times_canvas) < 2:
            pass
        elif len(Times_canvas) == 2 and fijo in puntos:

            x_entry = variable.init_x + variable.delta_callsign + Times_canvas[0] * variable.delta_x
            x_exit = variable.init_x + variable.delta_callsign + Times_canvas[-1] * variable.delta_x

            Line = canvas.create_line(x_entry, variable.init_y, x_exit, variable.init_y, fill=color_in_sector,
                                      width=variable.ficha_width / 2, stipple='gray25')

        elif len(Times_canvas) == 3:

            if puntos[-1] == fijo and puntos[-2]=='Exit_Sector' or puntos[0]==fijo and puntos[1]=='Entry_Sector':
                if 'Entry_Sector' in puntos and 'Exit_Sector' not in puntos:
                    ent = puntos.index('Entry_Sector')
                    sal = -1
                elif 'Entry_Sector' not in puntos and 'Exit_Sector' in puntos:
                    ent = 0
                    sal = puntos.index('Exit_Sector')

                elif 'Entry_Sector' in puntos and 'Exit_Sector' in puntos:
                    ent = puntos.index('Entry_Sector')
                    sal = puntos.index('Exit_Sector')
                else:
                    ent = 0
                    sal = -1

                x_entry = variable.init_x + variable.delta_callsign + Times_canvas[ent] * variable.delta_x
                x_exit = variable.init_x + variable.delta_callsign + Times_canvas[sal] * variable.delta_x

                Line = canvas.create_line(x_entry, variable.init_y, x_exit, variable.init_y, fill=color_in_sector,
                                          width=variable.ficha_width / 2, stipple='gray25')
            else:
                x_entry = variable.init_x + variable.delta_callsign + Times_canvas[0] * variable.delta_x
                x_exit = variable.init_x + variable.delta_callsign + Times_canvas[-1] * variable.delta_x

                Line = canvas.create_line(x_entry, variable.init_y, x_exit, variable.init_y, fill=color_in_sector,
                                          width=variable.ficha_width / 2, stipple='gray25')
        else:
            if 'Entry_Sector' in puntos and 'Exit_Sector' in puntos:
                ent = puntos.index('Entry_Sector')
                sal = puntos.index('Exit_Sector')
                x_entry = variable.init_x + variable.delta_callsign + Times_canvas[ent] * variable.delta_x
                x_exit = variable.init_x + variable.delta_callsign + Times_canvas[sal] * variable.delta_x
            else:
                x_entry = variable.init_x + variable.delta_callsign + Times_canvas[0] * variable.delta_x
                x_exit = variable.init_x + variable.delta_callsign + Times_canvas[-1] * variable.delta_x

            Line = canvas.create_line(x_entry, variable.init_y, x_exit, variable.init_y, fill=color_in_sector,
                                      width=variable.ficha_width / 2, stipple='gray25')


        if not variable.Timeline_Graph:
            variable.Timeline_Graph_Tot.append(((callsign, fix, None, 'In'), (callsign, fix, None, 'Out')))
        else:
            variable.Timeline_Graph_Tot.append((variable.Timeline_Graph[0], variable.Timeline_Graph[-1]))


        for i in range(len(Times_canvas)):

                Pnt = canvas.create_text(variable.init_x + variable.delta_callsign + Times_canvas[i] * variable.delta_x,
                                                             variable.init_y, anchor="s", text=puntos[i], font="Georgia 8 bold", fill=Text_Color[i])

                Hour = canvas.create_text(variable.init_x + variable.delta_callsign + Times_canvas[i] * variable.delta_x,
                                                             variable.init_y, anchor="n", text=Horas[i], font="Georgia 8 bold", fill=Text_Color[i])

    def Datos_Timeline(variable, sector_datos, **timeline_info_otro):

        '''

        Create each canvas pv timeline with callsign, way-points, conflicts and times data,
        visualize a line while pv is in selected sector.

        :param {int} insert_row: Count variable to identifier each pv canvas
        :param {dict} timeline_info: Contains some necessary data from each pv to create canvas timeline
        :return: None

        '''

        fijo = str(timeline_info_otro['Fijo'])
        hora = timeline_info_otro['Hora']
        tipo_conf = str(timeline_info_otro['Conflicto'])
        sol_conf = str(timeline_info_otro['Solucion'])

        callsign = timeline_info_otro['callsign']
        route = timeline_info_otro['route']
        color_in_sector = ''
        ###########
        ###############

        if tipo_conf != 'None':
            for c in variable.conflict:
                if callsign in c:
                    fijo_conf = fijo
                    variable.Timeline_Graph_conf.append((callsign, fijo, str(hora.time()), tipo_conf, sol_conf))
                    color_in_sector = 'red'

            if color_in_sector != 'red':
                fijo_conf = fijo
                variable.Timeline_Graph_conf.append((callsign, fijo, str(hora.time()), tipo_conf, sol_conf))
                color_in_sector = 'green'

        else:
            for c in variable.conflict:
                if callsign in c:
                    fijo_conf = fijo
                    color_in_sector = 'dark orchid'
                    break

                else:
                    color_in_sector = 'blue'


        delta_time_entry = 0

        variable.Timeline_Graph = []


        for wp in route:

            fix = wp.fix
            eto = wp.eto
            eto_str = str(eto)[11:19]
            delta_time = int((wp.eto - variable.datetime_inicio).total_seconds())
            flg = 0

            if wp == route[-1] and len(variable.Timeline_Graph) >= 1 and 'In' in variable.Timeline_Graph[-1]:
                variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))
                flg = 1
                fix = fix

            if wp.sector_entry and (all(x[0:2] in sector_datos for x in wp.sector_entry)): # and (variable.sector[0] in wp.sector_entry or variable.sector[1] in wp.sector_entry or variable.sector[2] in wp.sector_entry):

                if len(variable.Timeline_Graph) >= 1 and 'In' in variable.Timeline_Graph[-1] and flg == 1:
                    pass
                else:
                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'In'))

                    if delta_time_entry == 0:
                        delta_time_entry = delta_time
                    else:
                        pass

                    fix = fix

            elif wp.sector_exit and (all(x[0:2] in sector_datos for x in wp.sector_exit)):# and (variable.sector[0] in wp.sector_exit or variable.sector[1] in wp.sector_exit or variable.sector[2] in wp.sector_exit):

                if 'Out' in variable.Timeline_Graph[-1]:

                    del variable.Timeline_Graph[-1]
                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))

                else:

                    variable.Timeline_Graph.append((callsign, fix, eto_str, 'Out'))

                fix = fix

            elif fix == fijo:
                fix = fix

            elif not wp.sector_entry and not wp.sector_exit and flg == 1:
                pass
            else:
                continue

        if not variable.Timeline_Graph:
            variable.Timeline_Graph_Tot.append(((callsign, fix, None, 'In'), (callsign, fix, None, 'Out')))
        else:
            variable.Timeline_Graph_Tot.append((variable.Timeline_Graph[0], variable.Timeline_Graph[-1]))

    def gen_datos_graph(variable, sector_actual):

        '''

        :return:
        '''

        variable.data_graph = []
        variable.data_excel = []
        variable.Timeline_Graph_ConfGrp = []

        variable.data_graph_Noadj = []
        variable.data_graph_total = []


        exe_file = variable.gta.exercise_file
        wb = load_workbook(filename=exe_file)
        ws = wb['Valores']

        try:
            variable.Timeline_Graph_conf
            for n in range(0, len(variable.Timeline_Graph_conf), 2):
                    variable.Timeline_Graph_ConfGrp.append((variable.Timeline_Graph_conf[n], variable.Timeline_Graph_conf[n + 1]))
        except:
            pass

        # Sheet -> Timeline Sheet
        for i in range(50, 50 + 100):

            # Search column -> PROBLEM IDENTIFIER -> CONFLICTING TRACKS
            if ws.cell(row=i, column=2).value == 'SAME':
                Conf_Code1 = int(ws.cell(row=i, column=4).value)
                Conf_CodeStr1 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'RECIP':
                Conf_Code2 = int(ws.cell(row=i, column=4).value)
                Conf_CodeStr2 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'SPEED':
                Conf_Code3 = int(ws.cell(row=i, column=4).value)
                Conf_CodeStr3 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'CROSS':
                Conf_Code4 = int(ws.cell(row=i, column=4).value)
                Conf_CodeStr4 = str(ws.cell(row=i, column=2).value)

            if ws.cell(row=i, column=2).value == 'C_D':
                Sol_Code1 = int(ws.cell(row=i, column=4).value)
                Sol_CodeStr1 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'VEC':
                Sol_Code2 = int(ws.cell(row=i, column=4).value)
                Sol_CodeStr2 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'SEQ':
                Sol_Code3 = int(ws.cell(row=i, column=4).value)
                Sol_CodeStr3 = str(ws.cell(row=i, column=2).value)

            elif ws.cell(row=i, column=2).value == 'SPD':
                Sol_Code4 = int(ws.cell(row=i, column=4).value)
                Sol_CodeStr4 = str(ws.cell(row=i, column=2).value)

        i = 0
        for pv in variable.gta.flights:

            # Sector entry and exit times

            entry_time1 = variable.Timeline_Graph_Tot[i][0][2]
            exit_time1 = variable.Timeline_Graph_Tot[i][1][2]

            # pos_ini1 and pos_end1 -> time pos in variable.time_exer

            if entry_time1==None or entry_time1[0:5] not in variable.time_exer  and exit_time1==None or exit_time1[0:5] not in variable.time_exer:
                pos_ini1 = 'NA'
                pos_end1 = 'NA'

            elif entry_time1[0:5] in variable.time_exer and exit_time1[0:5] not in variable.time_exer:
                exit_time1 = variable.time_exer[-1]
                pos_ini1 = variable.time_exer.index(entry_time1[0:5])
                pos_end1 = variable.time_exer.index(exit_time1[0:5])

            elif entry_time1[0:5] not in variable.time_exer and exit_time1[0:5] in variable.time_exer:
                pos_ini1 = 0
                pos_end1 = variable.time_exer.index(exit_time1[0:5])
            else:
                pos_ini1 = variable.time_exer.index(entry_time1[0:5])
                pos_end1 = variable.time_exer.index(exit_time1[0:5])

            # Conf parameters (CONF TYPE -- SOL CONF)
            # Format ---> variable.Timeline_Graph_ConfGrp =  ((callsign1, time, type conf, sol conf)(callsign2, time, type conf, sol conf))
            for c in variable.Timeline_Graph_ConfGrp:

                if pv.callsign in c[0]:

                    conf_callsign = c[1][0]
                    conf_time = c[1][2]

                    p = 0
                    for pv in variable.Timeline_Graph_Tot:

                        if pv[0][0] == conf_callsign:
                            entry_time2 = variable.Timeline_Graph_Tot[p][0][2]
                            exit_time2 = variable.Timeline_Graph_Tot[p][1][2]
                            break

                        else: pass

                        p += 1
                    # El conflicto se produce fuera del tiempo dentro del sector (en otro sector)
                    if entry_time2==None or (int(entry_time2[0:2]) == int(conf_time[0:2]) and int(entry_time2[3:5]) > int(conf_time[3:5]) or int(entry_time2[0:2]) > int(conf_time[0:2])):
                        conf_pos_ini = 'NA'
                        conf_pos_end = 'NA'
                        sol_pos_ini = 'NA'
                        sol_pos_end = 'NA'
                        break

                    elif exit_time2==None or (int(exit_time2[0:2]) == int(conf_time[0:2]) and int(exit_time2[3:5]) < int(conf_time[3:5]) or int(exit_time2[0:2]) < int(conf_time[0:2])):
                        conf_pos_ini = 'NA'
                        conf_pos_end = 'NA'
                        sol_pos_ini = 'NA'
                        sol_pos_end = 'NA'
                        break

                    elif entry_time2==None or entry_time2[0:5] not in variable.time_exer  and exit_time2==None or exit_time2[0:5] not in variable.time_exer:
                        pos_ini2 = 'NA'
                        pos_end2 = 'NA'

                    elif entry_time2[0:5] in variable.time_exer and exit_time2[0:5] not in variable.time_exer:
                        pos_ini2 = variable.time_exer.index(entry_time2[0:5])
                        pos_end2 = variable.time_exer.index(variable.time_exer[-1])

                    elif entry_time2[0:5] not in variable.time_exer and exit_time2[0:5] in variable.time_exer:
                        pos_ini2 = 0
                        pos_end2 = variable.time_exer.index(exit_time2[0:5])

                    else:
                        pos_ini2 = variable.time_exer.index(entry_time2[0:5])
                        pos_end2 = variable.time_exer.index(exit_time2[0:5])

                    if pos_ini1 > pos_ini2:
                        conf_pos_ini = pos_ini1
                    elif pos_ini1 < pos_ini2:
                        conf_pos_ini = pos_ini2
                    else:
                        conf_pos_ini = pos_ini1

                    time_conf = c[0][2]
                    conf_pos_end = variable.time_exer.index(time_conf[0:5])
                    sol_pos = variable.time_exer.index(time_conf[0:5])

                    type_conf = c[0][3]
                    sol_conf = c[0][4]

                    if sol_conf == 'C_D':
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    elif sol_conf == 'VEC':

                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    elif sol_conf == 'SEQ':
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    else:
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 5
                    break

                elif pv.callsign in c[1]:
                    conf_callsign = c[0][0]

                    p = 0
                    for pv in variable.Timeline_Graph_Tot:

                        if pv[0][0] == conf_callsign:
                            entry_time2 = variable.Timeline_Graph_Tot[p][0][2]
                            exit_time2 = variable.Timeline_Graph_Tot[p][1][2]
                            break

                        else:
                            pass
                        p += 1

                    # El conflicto se produce fuera del tiempo dentro del sector (en otro sector)
                    if entry_time2==None or (int(entry_time2[0:2]) == int(conf_time[0:2]) and int(entry_time2[3:5]) > int(
                            conf_time[3:5]) or int(entry_time2[0:2]) > int(conf_time[0:2])):

                        conf_pos_ini = 'NA'
                        conf_pos_end = 'NA'
                        sol_pos_ini = 'NA'
                        sol_pos_end = 'NA'
                        break

                    elif exit_time2==None or (int(exit_time2[0:2]) == int(conf_time[0:2]) and int(exit_time2[3:5]) < int(
                            conf_time[3:5]) or int(exit_time2[0:2]) < int(conf_time[0:2])):

                        conf_pos_ini = 'NA'
                        conf_pos_end = 'NA'
                        sol_pos_ini = 'NA'
                        sol_pos_end = 'NA'
                        break
                    elif entry_time2==None or entry_time2[0:5] not in variable.time_exer  and exit_time2==None or exit_time2[0:5] not in variable.time_exer:
                        pos_ini2 = 'NA'
                        pos_end2 = 'NA'

                    elif entry_time2[0:5] in variable.time_exer and exit_time2[0:5] not in variable.time_exer:
                        pos_ini2 = variable.time_exer.index(entry_time2[0:5])
                        pos_end2 = variable.time_exer.index(variable.time_exer[-1])

                    elif entry_time2[0:5] not in variable.time_exer and exit_time2[0:5] in variable.time_exer:
                        pos_ini2 = 0
                        pos_end2 = variable.time_exer.index(exit_time2[0:5])

                    else:
                        pos_ini2 = variable.time_exer.index(entry_time2[0:5])
                        pos_end2 = variable.time_exer.index(exit_time2[0:5])


                    if pos_ini1 > pos_ini2:
                        conf_pos_ini = pos_ini1
                    elif pos_ini1 < pos_ini2:
                        conf_pos_ini = pos_ini2
                    else:
                        conf_pos_ini = pos_ini1

                    time_conf = c[1][2]
                    conf_pos_end = variable.time_exer.index(time_conf[0:5])
                    sol_pos = variable.time_exer.index(time_conf[0:5])

                    type_conf = c[1][3]
                    sol_conf = c[1][4]

                    if sol_conf == 'C_D':
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    elif sol_conf == 'VEC':

                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    elif sol_conf == 'SEQ':
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 2
                    else:
                        sol_pos_ini = sol_pos - 5
                        sol_pos_end = sol_pos + 5
                    break
                else:
                    conf_pos_ini = 'NA'
                    conf_pos_end = 'NA'
                    sol_pos_ini = 'NA'
                    sol_pos_end = 'NA'

            if len(variable.Timeline_Graph_ConfGrp) == 0:
                conf_pos_ini = 'NA'
                conf_pos_end = 'NA'
                sol_pos_ini = 'NA'
                sol_pos_end = 'NA'

            pv_data = []
            pv_data_exc = []
            for t in variable.time_exer:
                pos = variable.time_exer.index(t[0:5])

                ##### TIEMPO QUE PERMANECE EL VUELO EN SECTOR
                if pos >= pos_ini1 and pos <= pos_end1:
                    sector = 2
                    sector_str = 'SSR'
                else:
                    sector = 0
                    sector_str = None


                if conf_pos_ini == 'NA' and conf_pos_end == 'NA':
                    sol = 0
                    confl = 0
                    conf_str = None
                    sol_str = None
                else:
                    ##### TIEMPO QUE SUMA CONFLICTO
                    if pos >= conf_pos_ini and pos <= conf_pos_end:

                        if type_conf == 'SAME':
                            confl = Conf_Code1
                            conf_str = Conf_CodeStr1
                        elif type_conf == 'RECIP':
                            confl = Conf_Code2
                            conf_str = Conf_CodeStr2
                        elif type_conf == 'SPEED':
                            confl = Conf_Code3
                            conf_str = Conf_CodeStr3
                        else:
                            confl = Conf_Code4
                            conf_str = Conf_CodeStr4
                    else:

                        confl = 0
                        conf_str = None

                        ##### TIEMPO QUE SUMA SOLUCION
                    if pos >= sol_pos_ini and pos <= sol_pos_end:

                        if type_conf == 'C_D':
                            sol = Sol_Code1
                            sol_str = Sol_CodeStr1

                        elif type_conf == 'VEC':
                            sol = Sol_Code2
                            sol_str = Sol_CodeStr2

                        elif type_conf == 'SEQ':
                            sol = Sol_Code3
                            sol_str = Sol_CodeStr3

                        else:
                            sol = Sol_Code4
                            sol_str = Sol_CodeStr4

                    else:
                        sol = 0
                        sol_str = None

                pv_data.append(sector+confl+sol)

                if sector_str != None and conf_str == None and sol_str == None:
                    pv_data_exc.append('=' + sector_str)

                elif sector_str != None and conf_str != None and sol_str == None:
                    pv_data_exc.append('=' + sector_str + '+' + conf_str)

                elif sector_str != None and conf_str == None and sol_str != None:
                    pv_data_exc.append('=' + sector_str + '+' + sol_str)

                elif sector_str != None and conf_str != None and sol_str != None:
                    pv_data_exc.append('=' + sector_str + '+' + conf_str + '+' + sol_str)

                elif sector_str == None and conf_str == None and sol_str != None:
                    pv_data_exc.append('=' + sol_str)

                else:
                    pv_data_exc.append('')

            i += 1

            variable.data_excel.append(pv_data_exc)
            variable.data_graph.append(pv_data)

        for i in range(len(variable.time_exer)): #fila
            tot = 0
            contador = 0
            for j in range(len(variable.data_graph)): #columna
                tot += variable.data_graph[j][i]
                if variable.data_graph[j][i] != 0:
                    contador += 1
            ajuste = tot + 300*contador/25
            #self.num_pvs_min(contador)
            variable.data_graph_Noadj.append(ajuste)

        for i in range(len(variable.data_graph_Noadj)):

            if i == 0 or i == len(variable.data_graph_Noadj)-1:

                variable.data_graph_total.append(float(variable.data_graph_Noadj[i]))
            else:
                x = (float(variable.data_graph_Noadj[i] + variable.data_graph_Noadj[i + 1]) - (2 * variable.data_graph_Noadj[i - 1]))
                op = round(float(variable.data_graph_Noadj[i - 1]) + x / 3, 1)
                variable.data_graph_total.append(op)


        variable.datos_sectores[sector_actual]['Excel'] = variable.data_excel
        variable.datos_sectores[sector_actual]['Graph'] = variable.data_graph_total

    def crear_grafico(variable):

        for child in variable.panel_bot.winfo_children():
            child.destroy()

        lst = []
        variable.time_exer_lab = []

        for i in range(len(variable.time_exer)):
            lst.append(i)
            if i == 0:
                variable.time_exer_lab.append(variable.time_exer[i])
            elif i % 10 == 0:
                variable.time_exer_lab.append(variable.time_exer[i])
            else:
                variable.time_exer_lab.append(variable.time_exer[i][3:5])

        variable.fig, variable.x1 = plt.subplots(figsize=(30, 8))


        variable.x1.grid(color='black', linestyle='-', linewidth=1)
        variable.x1.set_ylabel('Pv')
        variable.x1.set_xlabel('Tiempo')
        #self.x1.set_xlim(41300, 73000)
        variable.x1.set_xticks(np.arange(0, len(variable.time_exer), 1))
        variable.x1.set_xticklabels(variable.time_exer_lab, rotation=0, fontsize=8)


        variable.x1.set_yticks(np.arange(1, 201, 5))
        variable.x1.set_yticklabels(range(0, 200, 5))
        #self.x1.invert_yaxis()


        variable.x1.minorticks_on()

        # Customize the major grid
        # x1.grid(which='major', linestyle='.', linewidth='0.1', color='gray')
        # Customize the minor grid
        variable.x1.grid(which='minor', linestyle='-', linewidth='0.1', color='black')

        for sector in variable.datos_sectores:
            puntuacion = variable.datos_sectores[sector]['Graph']
            variable.x1.plot(lst, puntuacion, lw=3, label=sector)

        variable.x1.legend()
        canvas = FigureCanvasTkAgg(variable.fig, variable.panel_bot)
        canvas.get_tk_widget().pack(side=tix.BOTTOM, fill=tix.BOTH, expand=True)

    def solv_conflict(variable):

        '''
        Open exercise sheet from excel file, load all data pvs on a list,
        add conflict data and a code solution by each one.

        :param {list} ExerPVList: Contains all pvs from exercise sheet
        :return: None
        '''

        exe_file = variable.gta.exercise_file
        wb = load_workbook(filename=exe_file)
        sheet = wb['Ejercicio']

        variable.ExerPVList_conf = []
        variable.ExerPVList = []

        for i in range(10, sheet.max_row + 1):

            if sheet.cell(row=i, column=1).value == None:
                break

            if sheet.cell(row=i, column=len(variable.camps_ejerc)-1).value != None:

                PV = []
                for j in range(1, len(variable.camps_ejerc)+1):

                    PV.append(str(sheet.cell(row=i, column=j).value))
                variable.ExerPVList_conf.append(PV)
                variable.ExerPVList.append(PV)
            else:

                PV = []
                for j in range(1, len(variable.camps_ejerc)+1):
                    PV.append(str(sheet.cell(row=i, column=j).value))

                variable.ExerPVList.append(PV)

        ################################### Call function to create conflict visualize pop up
        variable.Create_Timeline_Graph()

    def Create_Timeline_Graph(variable):

        '''

        Open excel timeline sheet from exercise excel file, add all pvs data from the exercise to create the work
        load graph by each code from work load points definition.

        :param {list} time_exer: Exercise duration (inc, minute by minute)
        :param {list}
        :return: None
        '''

        exe_file = variable.gta.exercise_file

        try:
            variable.p
            subprocess.Popen("taskkill /F /IM EXCEL.EXE", shell=True)
        except:
            pass

        wb = load_workbook(filename=exe_file)
        sect_cont = 0
        hojas = []

        sheet = wb['Ejercicio']
        sheet_conf = wb['Conflictos']

        for ws in wb.worksheets:
            if ws.title == 'Graphs':
                wb.remove(ws)

        for e in range(len(variable.estados)):

            estado = variable.estados[e]
            sector = variable.sectores_fir[e]

            if estado == 1:

                for ws in wb.worksheets:

                    if ws.title != 'Ejercicio' and ws.title != 'Difficulty' and ws.title != 'Conflictos' and ws.title != 'Tabla' and ws.title != 'Valores' and ws.title not in hojas:

                        hojas.append(str(ws.title))
                        ws.title = sector
                        hojas.append(str(ws.title))
                        data_excel = variable.datos_sectores[sector]['Excel']
                        sect_cont +=1
                        j = 0

                        variable.sol_conf_cont = 0
                        variable.conf_cont = 0

                        # Exercise Time
                        for t in range(4, 64, 1):
                            # Delete values (Time)
                            ws.cell(row=5, column=t).value = None
                            # Insert new values (Time)
                            ws.cell(row=5, column=t).value = variable.time_exer[t-4][0:5]

                        # To add on y_axis table each callsign from the exercise pvs
                        for i in range(7, 7 + 40):
                            # Del values (Callsign)
                            ws.cell(row=i, column=2).value = None
                            ws.cell(row=i, column=3).value = None

                            for c in range(4, 65):
                                # Del Grid values (Sum of parameters: SSR + CONF + SOL)
                                ws.cell(row=i, column=c).value = None

                        # Exercise Callsign
                        for i in range(7, 7 + len(variable.callsign)):
                            # Insert new values (Callsign)
                            ws.cell(row=i, column=2).value = variable.callsign[j]
                            j += 1

                        # Exercise Grid values (Sum of parameters: SSR + CONF + SOL)
                        for i in range(len(data_excel)):
                            for j in range(len(data_excel[i])):
                                if str(data_excel[i][j]) == '':
                                    pass
                                else:
                                    # Insert new values (Sum of parameters: SSR + CONF + SOL)
                                    ws.cell(row=i + 7, column=j + 4).value = str(data_excel[i][j])

                        break




        ws_grp = wb.create_sheet('Graphs')
        cols = []
        row = []
        row.append('Time')
        cols.append(variable.time_exer)
        for e in range(len(variable.estados)):

            estado = variable.estados[e]
            sector = variable.sectores_fir[e]

            if estado == 1:
                cols.append(variable.datos_sectores[sector]['Graph'])
                row.append(sector)

        r = len(cols)
        c = len(cols[0])
        rows = [[cols[j][i] for j in xrange(r)] for i in range(c)]

        ws_grp.append(row)
        for row in rows:
            ws_grp.append(row)

        c1 = LineChart()
        c1.title = "Carga de Trabajo"
        c1.y_axis.title = 'Puntuacion'
        c1.x_axis.title = 'Tiempo'

        c1.height = 20  # default is 7.5
        c1.width = 40  # default is 15

        data = Reference(ws_grp, min_col=1, min_row=1, max_col=len(row), max_row=len(rows))
        c1.add_data(data, titles_from_data=True)


        ws_grp.add_chart(c1, "H6")
        wb.save(exe_file)

        first_excel_row = 10

        # Delete flights values (Sheet -> Ejercicio)
        for i in range(first_excel_row, sheet.max_row):
            for c in range(1, len(variable.camps_ejerc)+1):
                sheet.cell(row=i, column=c).value = None

        row_cont = 0

        # Insert new values (Flights)
        for f in variable.Timeline_Graph_Tot:
            for pv in variable.ExerPVList:
                # Callsign
                if f[0][0] == pv[0]:
                    column_cont = 1
                    for element in pv:

                        if element == 'None':
                            element = ''

                        sheet.cell(row=row_cont + first_excel_row, column=column_cont).value = element
                        column_cont += 1

                    row_cont += 1

        wb.save(exe_file)

        row_cont = 0

        # Delete Conf values (Sheet -> Conflictos)
        for i in range(1, sheet_conf.max_row):
            for c in range(1, len(variable.camps_ejerc)+1):
                sheet_conf.cell(row=i, column=c).value = None

        # Insert new values (Conf)
        for c in variable.ExerPVList_conf:
            column_cont = 1
            for element in c:
                sheet_conf.cell(row=row_cont + first_excel_row, column=column_cont).value = element
                column_cont += 1

            row_cont += 1

        wb.save(exe_file)
        # Open excel file
        variable.p = subprocess.Popen([r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE", exe_file])

    def det_sect(variable, n, entry_time, exit_time, wb):

        '''

        Add points to excel sheet while each pv is in the sector.

        :param {int} n: Number of pv in timeline
        :param {list} time_exer: Exercise duration (inc, minute by minute)
        :param {str} entry_time: Entry sector time (Format->Hour:minutes:seconds)
        :param {str} exit_time: Exit sector time (Format->Hour:minutes:seconds)
        :param {worksheet} ws: Timeline Sheet from excel exercise
        :return: None

        '''
        ws = wb['Timeline Sheet']
        i = 0
        #for i in range(50, 50 + 100):
            # Search column -> PROBLEM IDENTIFIER -> AIRCRAFT
            #if ws.cell(row=i, column=2).value == 'SSR':

                #Sect_Code = ws.cell(row=i, column=4).value

        if entry_time[0:5] not in variable.time_exer and exit_time[0:5] not in variable.time_exer:

            pass

        elif entry_time[0:5] not in variable.time_exer or exit_time[0:5] not in variable.time_exer:

            incremento_entry = 0

            if entry_time[0:5] not in variable.time_exer:

                pos_ini = 4

            else:

                pos_ini = variable.time_exer.index(entry_time[0:5]) + 4

            if exit_time[0:5] not in variable.time_exer:

                pos_end = 64
                incremento_exit = 0

            else:

                pos_end = variable.time_exer.index(exit_time[0:5]) + 4

                if exit_time[6:] >= '30':

                    incremento_exit = 2

                else:

                    incremento_exit = 1

            for z in range(pos_ini + incremento_entry, pos_end + incremento_exit):

                if ws.cell(row=7 + n, column=z).value != None:

                    val_ant = ws.cell(row=7 + n, column=z).value
                    ws.cell(row=7 + n, column=z).value = val_ant + '+SSR'

                else:

                    ws.cell(row=7 + n, column=z).value = '=SSR'
        else:

            incremento_entry = 0
            pos_ini = variable.time_exer.index(entry_time[0:5]) + 4
            pos_end = variable.time_exer.index(exit_time[0:5]) + 4

            if exit_time[6:] >= '30':

                incremento_exit = 2

            else:

                incremento_exit = 1

            for z in range(pos_ini + incremento_entry, pos_end + incremento_exit):

                if ws.cell(row=7 + n, column=z).value != None:

                    val_ant = ws.cell(row=7 + n, column=z).value
                    ws.cell(row=7 + n, column=z).value = val_ant + '+SSR'

                else:

                    ws.cell(row=7 + n, column=z).value = '=SSR'

    def det_conf(variable, n, entry_time, exit_time, wb):

        '''

        Find callsigns in conflict data, calculate entry and exit conflict times(entry_conf, exit_conf),
        add points to excel sheet.

        :param {int} n: Number of pv in timeline
        :param {list} time_exer: Exercise duration (inc, minute by minute)
        :param {str} entry_time: Entry sector time (Format->Hour:minutes:seconds)
        :param {str} exit_time: Exit sector time (Format->Hour:minutes:seconds)
        :param {worksheet} ws: Timeline Sheet from excel exercise
        :return: None

        '''
        ws = wb['Timeline Sheet']
       # self.conflict_exc = []
       # for c in range(0, len(self.conflict), 2):
       #     self.conflict_exc.append((self.conflict[c], self.conflict[c+1]))


        for c in range(0, len(variable.conflict), 2):#(tipo, callsign, eto_str, tipo_conf, sol_conf)

            if variable.callsign[n] == variable.conflict[c]:  # and self.callsign[n] != call and conf not in aux_c

                for pv in variable.Timeline_Graph_Tot:
                    if variable.conflict[c][1] in pv[0]:
                        entry_time_pv1 = pv[0][2]
                        exit_time_pv1 = pv[1][2]

                    if variable.conflict[c + 1][1] in pv[0]:
                        entry_time_pv2 = pv[0][2]
                        exit_time_pv2 = pv[1][2]


                if entry_time_pv1 > entry_time_pv2:
                    entry_conf = entry_time_pv1
                else:
                    entry_conf = entry_time_pv2

                #if exit_time_pv1 > exit_time_pv2:
                #    exit_conf = exit_time_pv2
                #else:
                #    exit_conf = exit_time_pv1

                #for cp in self.ExerPVList_conf:

                  #  c = cp[0]


                #HSacta = conflic[2]

                #if conflic[0] != HSacta:

                exit_conf = variable.conflict[c][2]

                #varconf = self.lst_conf_val[self.conf_cont][0]
                #var = varconf.get()
                #for c in range(len(self.conflict)):
                var = variable.conflict[c][3]#var.upper()


                if entry_time[0:5] not in variable.time_exer and exit_time[0:5] not in variable.time_exer:

                    continue

                elif entry_conf[0:5] not in variable.time_exer or exit_conf[0:5] not in variable.time_exer:

                    if entry_conf[0:5] not in variable.time_exer:

                        pos_ini = 4

                    else:

                        pos_ini = variable.time_exer.index(entry_conf[0:5]) + 8

                    if exit_conf[0:5] not in variable.time_exer:

                        pos_end = 64

                    else:

                        pos_end = variable.time_exer.index(exit_conf[0:5]) + 4


                    for z in range(pos_ini, pos_end + 1):

                        ws.cell(row=7 + n, column=z).value = '=' + var

                    variable.conf_cont += 1

                    ################################### Call solution conflict function

                    variable.sol_conflic(n, ws, wb, exit_time_pv1, exit_time_pv2, c)


                else:

                    pos_ini = variable.time_exer.index(entry_conf[0:5]) + 4
                    pos_end = variable.time_exer.index(exit_conf[0:5]) + 4

                    if exit_conf[6:] >= '30':
                        incremento_exit = 2
                    else:
                        incremento_exit = 1

                    for z in range(pos_ini, pos_end + incremento_exit):

                        ws.cell(row=7 + n, column=z).value = '=' + var

                    variable.conf_cont += 1

                    ################################### Call solution conflict function
                    variable.sol_conflic(n, ws, wb, exit_time_pv1, exit_time_pv2, c)

    def sol_conflic(variable, n, ws, wb, exit_time_pv1, exit_time_pv2, c):

        '''

        Read solution conflict code for pv, add points to excel sheet.

        :param {int} n: Number of pv in timeline
        :param {list} time_exer: Exercise duration (inc, minute by minute)
        :param {worksheet} ws: Timeline Sheet from excel exercise
        :param {int} pos_call: Number of pv in ExerPVList->(contains all pvs from exercise)
        :return: None

        '''
        #varsol = self.lst_conf_val[self.sol_conf_cont][1]
        #var = varsol.get()
        var = variable.conflict[c][4]#var.upper()
        #position = pos_call

        # Open Work load Sheet
        ws_criterios = wb['Tabla']

        if var == 'VEC':
            for i in range(1, 50):
                v = str(ws_criterios.cell(row=i, column=1).value)
                 #Search column -> PROBLEM IDENTIFIER -> VECTORING
                if v == 'VEC':

                    crit_ant = str(ws_criterios.cell(row=i, column=4).value)
                    crit_post = str(ws_criterios.cell(row=i, column=5).value)

        elif var == 'SEQ':

            for i in range(1, 50):
                v = str(ws_criterios.cell(row=i, column=1).value)
                if v == 'SEQ':

                    crit_ant = str(ws_criterios.cell(row=i, column=4).value)
                    crit_post = str(ws_criterios.cell(row=i, column=5).value)

        elif var == 'SPD':

            for i in range(1, 50):
                v = str(ws_criterios.cell(row=i, column=1).value)
                if v == 'SPD':

                    crit_ant = str(ws_criterios.cell(row=i, column=4).value)
                    crit_post = str(ws_criterios.cell(row=i, column=5).value)

        else:
            pass

        entry_sol = variable.conflict[c][2]
        exit_sol = variable.conflict[c][2]

        if variable.time_exer.index(entry_sol[0:5]) + 4 < 7:

            pos_ini = 4

        else:
            crit_ant = crit_ant.split()
            pos_ini = variable.time_exer.index(entry_sol[0:5]) + 4 - int(crit_ant[-1])

       # if var == 'SPD':
        #    pos_end = time_exer.index(crit_post[0:5]) + 4
        #else:
            if crit_post == 'T_OUT2':

                if exit_time_pv1[0:2] in exit_time_pv2[0:2]:
                    if exit_time_pv1[3:5] in exit_time_pv2[3:5]:
                        crit_post = exit_time_pv1[0:5]
                    elif int(exit_time_pv1[3:5]) > int(exit_time_pv2[3:5]):
                       crit_post = exit_time_pv1[0:5]
                    elif int(exit_time_pv1[3:5]) < int(exit_time_pv2[3:5]):
                       crit_post = exit_time_pv2[0:5]
                    else:
                        pass

                elif int(exit_time_pv1[0:2]) > int(exit_time_pv2[0:2]):
                    crit_post = exit_time_pv1[0:5]

                else:
                    crit_post = exit_time_pv2[0:5]

                pos_end = variable.time_exer.index(crit_post[0:5]) + 4

            else:
                crit_post = crit_post.split()
                pos_end = variable.time_exer.index(exit_sol[0:5]) + 4 + int(crit_post[-1])


        for z in range(pos_ini, pos_end + 1):

            if ws.cell(row=7 + n, column=z).value != None:

                val_ant = ws.cell(row=7 + n, column=z).value

                ws.cell(row=7 + n, column=z).value = val_ant + '+' + var

            else:

                ws.cell(row=7 + n, column=z).value = '=' + var

        variable.sol_conf_cont += 1





