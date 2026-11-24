import Tix as tix
import os
from openpyxl import load_workbook, Workbook


class Escenario:

    def __init__(self, fir_file):

        self.book = load_workbook(filename=fir_file, read_only=True)

        self.dibujo = {'Linea costa': 'gray', 'Punto': 'gray25', 'VORDME': 'gray25', 'DVORDME': 'gray25','NDB': 'gray25', 'DME': 'gray25', 'TMA': 'yellow', 'CTA': 'yellow', 'Sector': 'orange'}
        for row in self.book['Escenario'].rows:
            if row[1].value not in self.dibujo.keys():
                self.dibujo[row[1].value] = ['gray']

        self.x0 = self.book['Escenario']['C2'].value
        self.y0 = self.book['Escenario']['D2'].value
        self.Cx0 = self.book['Escenario']['E2'].value
        self.Cy0 = self.book['Escenario']['F2'].value

        self.escenario = {}
        self.aeropuerto = []

        self.escenario['Linea costa'] = {}
        for row in self.book['Linea costa'].rows:
            if row[0].value not in self.escenario['Linea costa'].keys():
                self.escenario['Linea costa'][row[0].value] = []
            self.escenario['Linea costa'][row[0].value].append([row[1].value, row[2].value])

        for row in self.book['Lado tierra'].rows:
            if row[0].value not in self.escenario.keys():
                self.escenario[row[0].value] = {}
            if row[1].value not in self.escenario[row[0].value].keys():
                self.escenario[row[0].value][row[1].value] = []
            self.escenario[row[0].value][row[1].value].append([row[2].value, row[3].value])

        for row in self.book['Stands'].rows:
            if row[0].value not in self.escenario.keys():
                self.escenario[row[0].value] = {}
            if row[1].value not in self.escenario[row[0].value].keys():
                self.escenario[row[0].value][row[1].value] = []
            self.escenario[row[0].value][row[1].value].append([row[2].value, row[3].value])

        for row in self.book['Lado aire'].rows:
            if row[0].value not in self.escenario.keys():
                self.escenario[row[0].value] = {}
            if row[1].value not in self.escenario[row[0].value].keys():
                self.escenario[row[0].value][row[1].value] = []
            self.escenario[row[0].value][row[1].value].append([row[2].value, row[3].value])

        for row in self.book['SACTA'].rows:
            if row[0].value not in self.escenario.keys():
                self.escenario[row[0].value] = {}
            if row[1].value not in self.escenario[row[0].value].keys():
                self.escenario[row[0].value][row[1].value] = []
            self.escenario[row[0].value][row[1].value].append([row[2].value, row[3].value])

        self.puntosrod = {}
        self.calles = {}

        for row in self.book['Puntos rodaje'].rows:
            if row[0].value not in self.calles.keys():
                self.calles[row[0].value] = {}
            if row[1].value not in self.calles[row[0].value]:
                self.calles[row[0].value][row[1].value] = []
            self.calles[row[0].value][row[1].value].append(row[2].value)

            if row[0].value not in self.puntosrod.keys():
                self.puntosrod[row[0].value] = {}
            if row[1].value not in self.puntosrod[row[0].value].keys():
                self.puntosrod[row[0].value][row[1].value] = {}
            if row[2].value not in self.puntosrod[row[0].value][row[1].value].keys():
                self.puntosrod[row[0].value][row[1].value][row[2].value] = {}
            if row[3].value not in self.puntosrod[row[0].value][row[1].value][row[2].value].keys():
                self.puntosrod[row[0].value][row[1].value][row[2].value][row[3].value] = []
            self.puntosrod[row[0].value][row[1].value][row[2].value][row[3].value].append([row[4].value, row[5].value])

        self.procedures = {}
        for row in self.book['Rodaje'].rows:
            if row[0].value not in self.procedures.keys():
                self.procedures[row[0].value] = {}
            if row[1].value not in self.procedures[row[0].value].keys():
                self.procedures[row[0].value][row[1].value] = {}
            if row[2].value not in self.procedures[row[0].value][row[1].value].keys():
                self.procedures[row[0].value][row[1].value][row[2].value] = {}
            for p in str(row[4].value).split(','):
                if 'DEP' in str(row[2].value).split('_'):
                    rutarod = [p] + str(row[5].value).split(',') + [row[1].value]
                    self.procedures[row[0].value][row[1].value][row[2].value][p] = []
                    self.procedures[row[0].value][row[1].value][row[2].value][p].extend(
                        self.puntosrod[row[0].value][p]['Dep']['p'])
                else:
                    rutarod = [row[1].value] + str(row[5].value).split(',') + [p]
                    self.procedures[row[0].value][row[1].value][row[2].value][p] = []
                for c in range(1, len(rutarod) - 1):
                    ini = self.calles[row[0].value][rutarod[c]].index(rutarod[c - 1])
                    fin = self.calles[row[0].value][rutarod[c]].index(rutarod[c + 1])
                    pas = 1 if ini < fin else -1
                    if 'c' in self.puntosrod[row[0].value][rutarod[c]][
                        self.calles[row[0].value][rutarod[c]][ini]].keys():
                        self.procedures[row[0].value][row[1].value][row[2].value][p].extend(
                            self.puntosrod[row[0].value][rutarod[c]][self.calles[row[0].value][rutarod[c]][ini]]['c'])
                    for pto in range(ini, fin, pas):
                        if 'p' in self.puntosrod[row[0].value][rutarod[c]][self.calles[row[0].value][rutarod[c]][pto]].keys():
                            self.procedures[row[0].value][row[1].value][row[2].value][p].extend(self.puntosrod[row[0].value][rutarod[c]][self.calles[row[0].value][rutarod[c]][pto]]['p'])
                if 'LND' in str(row[2].value).split('_'):
                    self.procedures[row[0].value][row[1].value][row[2].value][p].extend(
                        self.puntosrod[row[0].value][p]['Lnd']['p'])

        for row in self.book['Procedimientos'].rows:
            if row[0].value not in self.procedures.keys():
                self.procedures[row[0].value] = {}
            if row[1].value not in self.procedures[row[0].value].keys():
                self.procedures[row[0].value][row[1].value] = {}
            if row[2].value not in self.procedures[row[0].value][row[1].value].keys():
                self.procedures[row[0].value][row[1].value][row[2].value] = {}
            if row[3].value not in self.procedures[row[0].value][row[1].value][row[2].value].keys():
                self.procedures[row[0].value][row[1].value][row[2].value][row[3].value] = []
            self.procedures[row[0].value][row[1].value][row[2].value][row[3].value].append([row[4].value, row[5].value])


class Pantalla(Escenario):

    def __init__(self, fir_file):

        Escenario.__init__(self, fir_file)
        self.tl = tix.Toplevel()
        self.tl.wm_title(fir_file)
        self.tl.wm_state('zoomed')
        self.c = tix.Canvas(self.tl, bg='black')
        self.c.pack(expand=1, fill=tix.BOTH)
        self.escala = 500.0
        self.c.bind('<Button-1>', self.move)
        self.c.bind('<B1-Motion>', self.move_move)
        self.tl.bind('<MouseWheel>', self.zoom)

        self.draw_maps()
        self.c.scale('all', self.x0, self.y0, self.Cx0 * self.escala, -self.Cy0 * self.escala)

    def move(self, event):
        self.c.scan_mark(event.x, event.y)

    def move_move(self, event):
        self.c.scan_dragto(event.x, event.y, gain=1)

    def zoom(self, e):
        porcentaje = 0.1
        factorescala = 0
        x = self.c.canvasx(e.x)
        y = self.c.canvasy(e.y)
        if e.delta > 0:
            factorescala = 1 + porcentaje
        elif e.delta < 0:
            factorescala = 1 - porcentaje
        self.c.scale("all", self.x0, self.y0, factorescala, factorescala)
        self.escala = self.escala * factorescala
        self.c.scan_mark(int(x * factorescala), int(y * factorescala))
        self.c.scan_dragto(int(x), int(y), gain=1)

    def draw_maps(self):
        for d in self.dibujo.keys():
            if d in self.escenario.keys():
                for obj in self.escenario[d].keys():
                    if len(self.escenario[d][obj]) == 1:
                        self.c.create_text(self.escenario[d][obj][0], text=obj, font=('helvetica', 8), fill=self.dibujo[d], tag=d, activefill='green', anchor='nw')
                        if d == 'Punto':
                                self.c.create_text(self.escenario[d][obj][0], text='D', font=('symbol', 10), fill='gray25', activefill='yellow')
                        elif d in ('VORDME', 'DVORDME'):
                            self.c.create_text(self.escenario[d][obj][0], text='O', font=('helvetica', 10), fill='gray25', activefill='yellow')
                            self.c.create_text(self.escenario[d][obj][0], text='x', font=('helvetica', 10), fill='gray25', activefill='yellow')
                        elif d == self.aeropuerto:
                            self.c.create_text(self.escenario[d][obj][0], text='O', font=('helvetica', 8), fill='gray25', activefill='yellow')
                    else:
                        self.c.create_line(self.escenario[d][obj], fill=self.dibujo[d], tag=d, activefill='green')

class Editor (Pantalla):

    def __init__(self, fir_file):

        Pantalla.__init__(self, fir_file)
        self.menu = tix.Menu(self.tl)
        self.menu_archivo = tix.Menu(self.tl)
        self.menu_procedimiento = tix.Menu(self.tl)
        self.menu.add_cascade(label='Archivo', menu=self.menu_archivo)
        self.menu_archivo.add_cascade(label='Procedimiento', menu=self.menu_procedimiento)
        self.tl.config(menu=self.menu)
        self.tl.bind('<F1>', self.export)
        for aeropuerto in self.procedures.keys():
            self.menu_aeropuerto = tix.Menu(self.tl)
            self.menu_procedimiento.add_cascade(label=aeropuerto, menu=self.menu_aeropuerto)
            for pista in self.procedures[aeropuerto].keys():
                self.menu_aeropuerto.add_radiobutton(label=pista,command=lambda aeropuerto=aeropuerto, pista=pista: self.edit_proc(aeropuerto, pista))

    def edit_proc(self, aeropuerto, pista):
        tl = tix.Toplevel(height=300, width=300)
        tl.title(aeropuerto + ' ' + pista)
        self.c.delete('procedimiento')

        def editar(tipo, procedimiento):
            if option[tipo][procedimiento].get() == 1:
                self.c.create_line(self.procedures[aeropuerto][pista][tipo][procedimiento], fill='orange',
                                   activefill='red', tags=('procedimiento', tipo + procedimiento))
                self.c.scale(tipo + procedimiento, self.x0, self.y0, self.Cx0 * self.escala, -self.Cy0 * self.escala)
                for punto in range(0, len(self.procedures[aeropuerto][pista][tipo][procedimiento])):
                    self.c.create_text(self.procedures[aeropuerto][pista][tipo][procedimiento][punto], text='+', font=('Helvetica', 12), fill='orange', activefill='red',
                                       tags=('procedimiento', tipo + procedimiento + 'punto',tipo + procedimiento + str(punto)))
                    self.c.scale(tipo + procedimiento + str(punto), self.x0, self.y0, self.Cx0 * self.escala, -self.Cy0 * self.escala)

                    def mover_punto(e, punto=punto):
                        self.c.delete(tipo + procedimiento)
                        self.procedures[aeropuerto][pista][tipo][procedimiento][punto] = [(self.c.canvasx(e.x) - self.x0) / (self.Cx0 * self.escala) + self.x0,
                            -(self.c.canvasy(e.y) - self.y0) / (self.Cy0 * self.escala) + self.y0]
                        self.c.create_line(self.procedures[aeropuerto][pista][tipo][procedimiento], fill='orange', activefill='red',
                                           tags=('procedimiento', tipo + procedimiento))
                        self.c.scale(tipo + procedimiento, self.x0, self.y0, self.Cx0 * self.escala, -self.Cy0 * self.escala)
                        self.c.coords(tipo + procedimiento + str(punto), self.procedures[aeropuerto][pista][tipo][procedimiento][punto][0],
                                      self.procedures[aeropuerto][pista][tipo][procedimiento][punto][1])
                        self.c.scale(tipo + procedimiento + str(punto), self.x0, self.y0, self.Cx0 * self.escala, -self.Cy0 * self.escala)

                    def crear_punto(e, punto=punto, tipo=tipo, procedimiento=procedimiento):
                        self.procedures[aeropuerto][pista][tipo][procedimiento].insert(punto,self.procedures[aeropuerto][pista][tipo][procedimiento][punto])
                        self.c.delete(tipo + procedimiento)
                        self.c.delete(tipo + procedimiento + 'punto')
                        editar(tipo, procedimiento)

                    def eliminar_punto(e, punto=punto, tipo=tipo, procedimiento=procedimiento):
                        self.procedures[aeropuerto][pista][tipo][procedimiento].remove(self.procedures[aeropuerto][pista][tipo][procedimiento][punto])
                        self.c.delete(tipo + procedimiento)
                        self.c.delete(tipo + procedimiento + 'punto')
                        editar(tipo, procedimiento)

                    self.c.tag_bind(tipo + procedimiento + str(punto), '<B3-Motion>', mover_punto)
                    self.c.tag_bind(tipo + procedimiento + str(punto), '<Double-Button-3>', crear_punto)
                    self.c.tag_bind(tipo + procedimiento + str(punto), '<Double-Button-1>', eliminar_punto)
            else:
                self.c.delete(tipo + procedimiento)
                self.c.delete(tipo + procedimiento + 'punto')

        option = {}
        columna = 0
        for tipo in self.procedures[aeropuerto][pista].keys():
            fila = 0
            option[tipo] = {}
            tix.Label(tl, text=tipo).grid(column=columna, row=fila, sticky=tix.W)
            fila += 1
            park = self.procedures[aeropuerto][pista][tipo].keys()
            park.sort()
            for procedimiento in park:
                option[tipo][procedimiento] = tix.IntVar()
                tix.Checkbutton(tl, text=procedimiento, variable=option[tipo][procedimiento],
                                command=lambda tipo=tipo, procedimiento=procedimiento: editar(tipo, procedimiento)) \
                    .grid(column=columna, row=fila, sticky=tix.W)
                fila += 1
                if fila > 30:
                    fila = 1
                    columna += 1
            columna += 1

    def export(self, e):
        book = Workbook()
        salto = 0
        for aeropuerto in self.procedures.keys():
            for pista in self.procedures[aeropuerto].keys():
                for tipo in self.procedures[aeropuerto][pista].keys():
                    for procedimiento in self.procedures[aeropuerto][pista][tipo].keys():
                        for fila in range(len(self.procedures[aeropuerto][pista][tipo][procedimiento])):
                            salto = salto + 1
                            book['Sheet'].cell(row=salto, column=1).value = aeropuerto
                            book['Sheet'].cell(row=salto, column=2).value = pista
                            book['Sheet'].cell(row=salto, column=3).value = tipo
                            book['Sheet'].cell(row=salto, column=4).value = procedimiento
                            book['Sheet'].cell(row=salto, column=5).value = \
                            self.procedures[aeropuerto][pista][tipo][procedimiento][fila][0]
                            book['Sheet'].cell(row=salto, column=6).value = \
                            self.procedures[aeropuerto][pista][tipo][procedimiento][fila][1]
        if not os.path.isdir('Edit'):
            os.makedirs('Edit')  # La carpeta Edit/ no viene en la instalacion
        book.save('Edit/Edit.xlsx')
