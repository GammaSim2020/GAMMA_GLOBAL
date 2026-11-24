import atexit
import logging
import datetime
import time
import os
from shutil import copy

# Trabajar siempre en la carpeta del programa: GAMMA.log, log/, img/, lib/,
# gamma_settings.json... se buscan aqui aunque se arranque desde otra carpeta
os.chdir(os.path.dirname(os.path.abspath(__file__)))

LOG_DIR ='log/'
LOG_FILENAME = 'GAMMA.log'
LOG_TIME_LIMIT = 30  # days

def setup_logging():
    # Full logging goes to 'LOG_FILENAME'
    logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(message)s',
                    filename=LOG_FILENAME,
                    filemode='w')
    l = logging.getLogger()
    # Important log messages go to the console as well
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('%(levelname)-6s %(message)s'))
    l.addHandler(console)

def save_log():
    if os.stat(LOG_FILENAME).st_size == 0:
        print('log file is empty. Unsaved...')
    else:
        limit = time.time() - LOG_TIME_LIMIT * 86400
        count = 0
        if not os.path.isdir(LOG_DIR):
            try:
                os.makedirs(LOG_DIR)
            except OSError:
                pass
        for f in os.listdir(LOG_DIR):
            pathFile = os.path.join(LOG_DIR, f)
            if os.path.isfile(pathFile) and os.stat(pathFile).st_mtime < limit:
                try:
                    os.remove(pathFile)
                    count += 1
                except:
                    pass
        print(count, "old log files erased")
        try:
            log_saved_filename = datetime.datetime.now().strftime("%d%m%Y_%H%M.log")
            copy(LOG_FILENAME, LOG_DIR + log_saved_filename)
            print('New log file saved:', log_saved_filename)
        except:
            print("Failed to create log file")


if __name__=="__main__":
    setup_logging()

# Import system modules
import sys
#sys.path.append("//nacl0400.na.aena.es/INTERREGIONAL/GAMMA/LEBL/lib")
sys.path.append("lib")  # Off-line option
import locale
import os

# Import libraries
try:
    # from twisted.internet import gtk2reactor # for gtk-2.0
    # gtk2reactor.install()
    from twisted.internet import reactor, tksupport, threads
    # The label separation code is run within it's own thread
    from twisted.python import threadable
    threadable.init()
except:
    logging.exception("Unable to load Twisted library")

# Import program modules
try:
    if sys.version_info[0]==2:
        import Tix as tix
        import Tkconstants
        import tkFileDialog as filedg
    elif sys.version_info.major==3:
        import tkinter.tix as tix
        from tkinter import constants
        import filedialog as filedg
    from Exercise import *
    from FIR import *
    import BADA  # To load aircraft types
    import ConfMgr
    from Pantalla import Editor
    conf = ConfMgr.GammaConfig()
    from GTA import GTA
    import Timeline
    from ExerciseGenerator import NewExercise, EditExercise
    import Timeline
    from RemoteClient import RemoteClient, GTA_Client_Protocol
    from RemoteClient import PSEUDOPILOT, ATC
except:
    logging.exception("Error loading program modules")
    sys.exit(1)

# TODO this works as it is, but it's probably not the best way to do it.
if sys.platform == "win32": encoding = locale.getpreferredencoding()
else: encoding = "cp1252"
utf8conv = lambda x : unicode(x, encoding).encode('utf8')

_remote_client = None  # active RemoteClient instance (client mode)


def _save_all_displays():
    """Save config state from all active displays and flush to disk.

    Called from every exit path so the JSON is always written regardless of
    how the program is closed (aspa ventana, cierre CMD, servidor termina,
    perdida de conexion TCP).
    """
    global _remote_client
    rc = _remote_client
    _remote_client = None  # prevent double-save if called again
    if rc is not None:
        for d in rc.display:
            if d is not None:
                try:
                    d.save_state()
                except Exception:
                    logging.error("Failed to save display state", exc_info=True)
    try:
        conf.save()
    except Exception:
        logging.error("Failed to save config", exc_info=True)


atexit.register(_save_all_displays)


def NewFile():
    return

def Launch():
    global gta
# Build a list of tuples for each file type the file dialog should display
    my_filetypes = [('all files', '.*'),('GAMMASIM Excel exercise files', '.XLSX'),
                    ('GAMMASIM plain text exercise files', '.eje')]
# Ask the user to select a single file name.
    exc_file = filedg.askopenfilename(parent=root,
                                initialdir=os.getcwd(),
                                title="Please select a file:",
                                filetypes=my_filetypes)
    print(exc_file)
    logging.debug("Creating GTA object")

    if 'gta' not in globals():
        gta = GTA(conf)
    # logging.info("Loading scenario and exercise", exc_file)
    gta.load(exc_file)
    # logging.debug("Starting GTA thread")
    reactor.callInThread(gta.start)

    if not reactor.running: reactor.run()
    launchmenu.entryconfig("Launch exercise",state="disabled")
    launchmenu.entryconfig("Stop exercise",state="normal")

def Stop():
    logging.debug("Stopping GTA thread")
    gta.stop()
    launchmenu.entryconfig("Launch exercise",state="normal")
    launchmenu.entryconfig("Stop exercise",state="disabled")
    #logging.debug("Stopping reactor")
    #if reactor.running: reactor.stop()
    save_log()

def Connect():
    top = tix.Toplevel()
    def ConnectIP():
        if v.get()==1: type = ATC
        else: type = PSEUDOPILOT
        try: s = server_ip.get().strip()
        except: s = ""
        try: (host, port) = s.split(":")
        except: host, port = s, 20123
        n_disp = v_screen.get()
        # Save MRU
        # Keep only previous IP
        conf.type = type
        conf.connect_mru = [s]
        conf.n_disp = n_disp
        conf.save()

        # Launch the client; keep reference so Exit() and atexit can save state
        global _remote_client
        logging.debug("Creating RemoteClient object")
        _remote_client = RemoteClient(conf)
        _remote_client.connect(host, port, type, v_screen.get(),
                               connectionLost=_save_all_displays)
        if not reactor.running: reactor.run()
        top.destroy()
        connectmenu.entryconfig("Connect...",state="disabled")

    top.title("Connect to running exercise")
    v = tix.IntVar()
    if conf.type == PSEUDOPILOT: v.set(2)
    else: v.set(1)
    v_screen = tix.IntVar()
    v_screen.set(conf.n_disp)

    tix.Label(top,
        text="Select a role:",
        justify = tix.LEFT,
        padx = 20).pack()
    tix.Radiobutton(top,
              text="Controller",
              padx = 20,
              variable=v,
              value=1).pack(anchor=tix.W)
    tix.Radiobutton(top,
              text="Pilot",
              padx = 20,
              variable=v,
              value=2).pack(anchor=tix.W)
    tix.Label(top,
        text="Number of screens:",
        justify = tix.LEFT,
        padx = 20).pack()
    tix.Radiobutton(top,
              text="1",
              padx = 20,
              variable=v_screen,
              value=1).pack(anchor=tix.W)
    tix.Radiobutton(top,
              text="2",
              padx = 20,
              variable=v_screen,
              value=2).pack(anchor=tix.W)
    tix.Radiobutton(top,
              text="3",
              padx = 20,
              variable=v_screen,
              value=3).pack(anchor=tix.W)
    tix.Label(top,
        text="Server IP:",
        justify = tix.LEFT,
        padx = 20).pack()
    server_ip = tix.Entry(top)
    server_ip.insert(0,conf.connect_mru[-1])
    server_ip.pack()
    button = tix.Button(top, text="Connect", command=ConnectIP)
    button.pack()
    x = root.winfo_x()
    y = root.winfo_y()
    dx=50
    dy=30
    top.geometry("+%d+%d" % (x + dx, y + dy))

def About():
    return

def OpenScenario():
    my_filetypes = [('GAMMASIM scenario files', '.xlsx'),('all files', '.*')]
    # Ask the user to select a single file name.
    fir_file = filedg.askopenfilename(parent=root,
                                initialdir=os.getcwd(),
                                title="Please select a file:",
                                filetypes=my_filetypes)
    print ("Inicializando editor")
    Editor(fir_file)

def Exit():
    _save_all_displays()
    save_log()
    reactor.stop()
    root.destroy()


root = tix.Tk()
x_window = 800
y_window = 354
x_screen = (root.winfo_screenwidth() / 2) - (x_window / 2)
y_screen = (root.winfo_screenheight() / 2) - (y_window / 2)
poswindow = str(x_window) + "x" + str(y_window) + "+" + str(x_screen) + "+" + str(y_screen)
root.geometry(poswindow)
img_dir=os.path.join(conf.common_dir,'img')
ico_file=os.path.join(img_dir,'GAMMASIM.ico')
root.iconbitmap(ico_file)
root.title('GammaSim GLOBAL '+ conf.ver)
img_file=os.path.join(img_dir,"background.gif")
photo = tix.PhotoImage(file=img_file)
label = tix.Label(root,image=photo)
label.image = photo
label.pack(side=tix.BOTTOM,fill=tix.BOTH, expand=True)

#Configure the main window menu
menu = tix.Menu(root)

global launchmenu
launchmenu = tix.Menu(menu)
menu.add_cascade(label="Launch", menu=launchmenu)
launchmenu.add_command(label="Launch exercise", command=Launch)
launchmenu.add_command(label="Stop exercise", command=Stop, state="disabled")
launchmenu.add_separator()
launchmenu.add_command(label="Exit", command=Exit)

connectmenu = tix.Menu(menu)
menu.add_cascade(label="Connect", menu=connectmenu)
connectmenu.add_command(label="Connect...", command=Connect)

scenmenu = tix.Menu(menu)
menu.add_cascade(label="Scenarios", menu=scenmenu)
# scenmenu.add_command(label="New", command=NewScenario)
scenmenu.add_command(label="Open...", command=OpenScenario)
scenmenu.add_separator()
scenmenu.add_command(label="Exit", command=root.quit)

# exemenu = tix.Menu(menu)
# menu.add_cascade(label="Exercises", menu=exemenu)
# exemenu.add_command(label="DataBase", command=database)
# exemenu.add_command(label="New", command=new_exercise)
# exemenu.add_command(label="Open...", command=open_exercise)

# exemenu.add_separator()
# exemenu.add_command(label="Exit", command=root.quit)

helpmenu = tix.Menu(menu)
menu.add_cascade(label="Help", menu=helpmenu)
helpmenu.add_command(label="Virtual Pilot Guide", command=About)
helpmenu.add_command(label="Controller Guide", command=About)
helpmenu.add_command(label="Instructor Guide", command=About)
helpmenu.add_separator()
helpmenu.add_command(label="About...", command=About)

root.config(menu=menu)

#Start the mainloop using twisted tksupport instead of tkinter's mainloop()
tksupport.install(root)
root.protocol('WM_DELETE_WINDOW', Exit)
reactor.run()