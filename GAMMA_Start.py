# -*- coding: iso8859-15 -*-
"""Arranque de GammaSim: comprueba si hay version nueva en la carpeta de red,
la copia sobre la instalacion local y lanza GAMMA.py.

Version unificada (Fase 5):
- La carpeta de red se lee de GAMMA.ini ([Global] update_dir / update_dir_alt);
  si no esta, se usan las de GAMMA_GLOBAL.
- La carpeta local es la de este script (antes fija C:/GAMMA_TWRAPS, C:/GAMMA...).
- No se copian ficheros propios de cada puesto (configuracion de usuario, logs...).
- Sin red/VPN (o sin GAMMA.ini remoto) se arranca la version local.
"""
import logging
import os
import sys

# Trabajar siempre en la carpeta del programa (rutas relativas: img/, lib/, GAMMA.ini...)
DST_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(DST_DIR)
sys.path.append(os.path.join(DST_DIR, "lib"))

import Tkinter as tk
from PIL import Image, ImageTk

try:
    import ConfMgr
except Exception:
    logging.exception("Error loading program modules")
    sys.exit(1)

# Ficheros y carpetas que NO se copian al actualizar (son de cada puesto o se regeneran)
EXCLUDE_FILES = ('gamma_settings.json', 'gamma_settings.json.tmp', 'Thumbs.db', 'desktop.ini')
EXCLUDE_EXT = ('.pyc', '.pyo', '.log', '.bak', '.tmp')
EXCLUDE_DIRS = ('log', '.git', '.idea', '.vscode', '.claude', '__pycache__')


def say(msg):
    print(msg)
    sys.stdout.flush()


def check_dir():
    """Primera carpeta de red accesible de las configuradas en GAMMA.ini (o None)."""
    for d in ConfMgr.update_dirs():
        try:
            if d and os.path.isdir(d):
                return d
        except Exception:
            pass
    return None


def ver_num(v):
    try:
        return int(str(v).strip().replace('.', ''))
    except ValueError:
        return None


def excluded(rel_path):
    parts = rel_path.replace('\\', '/').split('/')
    if any(p in EXCLUDE_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    return name in EXCLUDE_FILES or os.path.splitext(name)[1].lower() in EXCLUDE_EXT


def update():
    import shutil
    all_files = []
    for dirpath, dirnames, filenames in os.walk(scr_dir):
        # No entrar en carpetas excluidas
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            src_file = os.path.join(dirpath, filename)
            if not excluded(os.path.relpath(src_file, scr_dir)):
                all_files.append(src_file)
    total = len(all_files) or 1
    for i, src_file in enumerate(all_files):
        rel = os.path.relpath(src_file, scr_dir)
        dst_file = os.path.join(DST_DIR, rel)
        dst_folder = os.path.dirname(dst_file)
        try:
            if not os.path.exists(dst_folder):
                os.makedirs(dst_folder)
            shutil.copy2(src_file, dst_file)
        except Exception:
            logging.exception("No se ha podido copiar %s" % rel)
            say("ERROR copiando " + rel)
        say("Actualizando... " + str(int((i + 1) * 100.0 / total)) + "%  " + rel)


# --- Comprobacion de version ---
conf = ConfMgr.GammaConfig()
crr_ver = conf.ver
scr_dir = check_dir()
new_ver = ""
if scr_dir:
    new_ver = ConfMgr.GammaConfNew(os.path.join(scr_dir, "GAMMA.ini")).ver

say("Directorio de origen (PRODUCCION): " + str(scr_dir))
say("Directorio local GAMMA: " + str(DST_DIR))
say("Searching for updates...")
say("System GammaSim version: " + str(new_ver))
say("Current GammaSim version: " + str(crr_ver))

flag = False
if not scr_dir or ver_num(new_ver) is None:
    say("Carpeta de red no disponible o sin version: se arranca la version local")
elif ver_num(new_ver) != ver_num(crr_ver):
    say("New version exists: " + str(new_ver))
    say("Updating... " + str(new_ver))
    flag = True
else:
    say("System updated")

# --- Ventana de arranque ---
root = tk.Tk()
x_window = 800
y_window = 400
x_screen = (root.winfo_screenwidth() / 2) - (x_window / 2)
y_screen = (root.winfo_screenheight() / 2) - (y_window / 2)
root.geometry(str(x_window) + "x" + str(y_window) + "+" + str(x_screen) + "+" + str(y_screen))
root.overrideredirect(True)


def img(name):
    return ImageTk.PhotoImage(Image.open(os.path.join(DST_DIR, "img", name)))


fondo11 = img("background_sup_1.png")
fondo12 = img("background_sup_2.png")
fondo13 = img("background_sup_3.png")
fondo21 = img("background_med_1.png")
fondo221 = img("background_med_2.png")    # Searching for updates
fondo222 = img("background_med_2_2.png")  # No updates available
fondo223 = img("background_med_2_3.png")  # System updated
fondo224 = img("background_med_2_4.png")  # Starting GAMMA
fondo225 = img("background_med_2_5.png")  # System update available
fondo226 = img("background_med_2_6.png")  # Updating. Please, wait
fondo23 = img("background_med_3.png")
fondo31 = img("background_bajo_1.png")
fondo32 = img("background_bajo_2.png")
fondo33 = img("background_bajo_3.png")
tk.Label(root, image=fondo11, borderwidth=0).place(x=0, y=0)
tk.Label(root, image=fondo12, borderwidth=0).place(x=150, y=0)
tk.Label(root, image=fondo13, borderwidth=0).place(x=650, y=0)
tk.Label(root, image=fondo21, borderwidth=0).place(x=0, y=300)
tk.Label(root, image=fondo23, borderwidth=0).place(x=650, y=300)
tk.Label(root, image=fondo31, borderwidth=0).place(x=0, y=329)
tk.Label(root, image=fondo32, borderwidth=0).place(x=150, y=329)
tk.Label(root, image=fondo33, borderwidth=0).place(x=650, y=329)

# Images list selection, update and start GAMMA.py
yes_list = [fondo221, fondo225, fondo226, fondo224]
not_list = [fondo221, fondo223, fondo224]
count = 0


def start_gamma():
    root.destroy()
    os.chdir(DST_DIR)
    os.system('GAMMA.py')


def img_not():
    global count
    if count < 3:
        tk.Label(root, image=not_list[count], borderwidth=0).place(x=150, y=300)
        count += 1
        root.after(3000, img_not)
    else:
        start_gamma()


def img_yes():
    global count
    if count < 4:
        tk.Label(root, image=yes_list[count], borderwidth=0).place(x=150, y=300)
        count += 1
        if count == 3:
            root.after(3000, img_yes)
            update()  # Copia la carpeta de red sobre la instalacion local
            say("System updated")
        else:
            root.after(3000, img_yes)
    else:
        start_gamma()


def main():
    if flag:
        img_yes()
    else:
        img_not()


main()
root.mainloop()
