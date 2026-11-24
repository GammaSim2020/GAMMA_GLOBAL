#!/usr/bin/python
# -*- coding:iso8859-15 -*-
"""Building elements of a radar display"""


import datetime
import logging
import sys
import Aircraft

if sys.version_info[0] == 2:
    import Tix as tix
    import tkFont
elif sys.version_info.major == 3:
    import tkinter.tix as tix
import Tkinter as tk

from twisted.internet import reactor

from FIR import *
import os
import re
from MathUtil import *

import ConfMgr
conf = ConfMgr.GammaConfig()
from PIL import Image, ImageTk


# Globals
# Definition of fields in the OSF
C_ACTION = 1
C_CALLSIGN = 2


_radialogs = {}  # List of all dialogs, to avoid duplicates

# Because tkinter will not free the command for the binding when removing
# binding canvas elements, we have to keep track of every binding to make sure
# the the unbind is properly handled, including the funcid
_tag_binds = []
_binds = []

# Constants
IMGDIR = './img/'
CHANGE_WIDTH = 13

VOR = 'VOR'
NDB = 'NDB'
FIX = 'FIX'
AD = 'AD'
TA = 60  # Transition altitude (/100), used to generate Transition Level (tlevel)
SMALL_CIRCLE = 'SMALL_CIRCLE'
BIG_CIRCLE = 'BIG_CIRCLE'


def ra_bind(object, widget, sequence, callback):
    """Creates a TK binding and stores information for later deletion"""
    funcid = widget.bind(sequence, callback)
    _binds.append((object, widget, sequence, funcid),)


def ra_unbind(object, widget, sequence):
    for (o, w, s, f) in [(o, w, s, f) for (o, w, s, f) in _binds if (o == object and w == widget and sequence == s)]:
        w.unbind(s, f)
        _binds.remove((o, w, s, f))


def ra_clearbinds(object):
    for (o, w, s) in [(o, w, s) for (o, w, s, f) in _binds if (o == object)]:
        ra_unbind(o, w, s)


def ra_tag_bind(canvas, tag_or_id, sequence, func):
    """Creates a tag binding and stores information for later deletion"""
    if tag_or_id is None:
        return
    funcid = canvas.tag_bind(tag_or_id, sequence, func, add=True)
    _tag_binds.append((canvas, tag_or_id, sequence, funcid))


def ra_tag_unbind(canvas_remove, tag_remove, sequence_remove):
    for b in _tag_binds[:]:
        [canvas, tag, seq, funcid] = b
        if (tag == tag_remove) and (canvas == canvas_remove) and (sequence_remove == seq):
            canvas.tag_unbind(tag, seq, funcid)
            _tag_binds.remove(b)


def ra_cleartagbinds(tag_to_remove, canvas_to_remove=None):
    # Because we are messing with the list within the iterator,
    # we iterate over a copy of the list (that's what _tag_binds[:] is, a copy)
    for b in _tag_binds[:]:
        [canvas, tag, seq, funcid] = b
        #if tag == tag_to_remove:
        if tag == tag_to_remove and (canvas_to_remove is None or canvas == canvas_to_remove):#
            try:
                canvas.tag_unbind(tag, seq, funcid)
            except:
                logging.debug('tag_unbind failed with '+str(tag)+','+str(seq)+','+str(funcid))
            _tag_binds.remove(b)


class RaFrame(object):
    """A moveable window inside a radar display"""
    def __init__(self, master, **kw):
        """Construct a moveable, titled frame inside the parent radar display.

        Instantiation arguments:
        master -- parent master
        Options:
            label -- text to use on the window title
            closebutton -- Boolean (default True)
            dockbutton -- Boolean (default True)
            closebuttonhides -- Boolean (default False)
        """

        self._master = master
        self._kw = kw  # We need to save it for rebuilding in toggle_windowed
        self._closebutton = self._label = None
        self.bd, self.bg, self.fg = 'gray50', 'Black', 'White'
        self._bindings = []
        self._x, self._y = (0, 0)
        self.showed = True

        # Build the frame
        self._build(master, windowed=False, **kw)
        # Place it
        self._place()

    def _build(self, master=None, windowed=False, **kw):
        """Build the GUI elements, either as a canvas element, or as a toplevel"""
        if not windowed:
            # Build a frame as a tix.Canvas element
            # if kw.has_key('anchor') and kw['anchor'] != '':
            #    kw2 ={anchor:tix.NW}
            #    kw2['anchor'] = kw['anchor']
            self.container = tix.Frame(master, background=self.bd, borderwidth = 1)

            self.top_bar = tix.Frame(self.container, background='magenta', borderwidth=1, relief=tix.FLAT, height=10)
            self.top_bar.pack(fill=tix.X, padx=0, pady=0)
            self.windowtitle = tix.Frame(self.container, background=self.bd, borderwidth=0, relief=tix.FLAT)
            self.windowtitle.pack(fill=tix.X)
            self.contents = tix.Frame(self.container, background=self.bg)
            self.contents.pack(fill=tix.BOTH, expand=1)

            def bring_foreground(e=None):
                self.container.tkraise()

            if kw.has_key('label') and kw['label'] != '':
                self._label = tix.Label(self.windowtitle, text=kw['label'], bg=self.bd, foreground=self.fg, font=("Arial", "8", "bold"))
                self._label.pack(side=tix.LEFT, ipadx=2)
                i = self._label.bind('<Button-1>', bring_foreground, add="+")
                self._bindings.append((self._label, i, "<Button-1>"),)

            if not kw.has_key('closebutton') or kw['closebutton']:
                self._closebutton = tix.Label(self.top_bar, text='X', background='gray80', foreground=self.fg, width=2, font=("Arial", "5", "bold"))
                self._closebutton.pack(side=tix.RIGHT, padx=0, pady=0)
#                self._closebutton.place(anchor=tix.E)
                if (self._kw.has_key('closebuttonhides')
                    and self._kw['closebuttonhides']):
                    i = self._closebutton.bind('<Button-1>', self.hide)
                else:
                    i = self._closebutton.bind('<Button-1>', self.close)
                self._bindings.append((self._closebutton, i, "<Button-1>"),)
            else:
                self.top_bar.grid_propagate(0)
            # TODO
            # This is causing problems because it's really not well implemented
            # Better not to have to avoid the crashes it creates until it's
            # properly done.
            # if not kw.has_key('dockbutton') or kw['dockbutton']:
            #    self._undockbutton=tix.Label(self.container,text='O',bg=self.bd,fg='Black')
            #    self._undockbutton.pack(side=tix.RIGHT)
            #    i=self._undockbutton.bind('<Button-1>',self.toggle_windowed)
            #    self._bindings.append((self._undockbutton,i,'<Button-1>'),)

            # Frame dragging
            # self.top_bar.grid(row=1,column=0,padx=2,pady=2,sticky=N+E+S)
            # self.windowtitle.grid(row=2,column=0,padx=2,pady=2,sticky=N+S+W)
            # self.contents.grid(row=3,column = 0,padx=2,pady=2,sticky=N+E+S+W)

            def drag_frame(e=None):
                """Move the frame as many pixels as the mouse has moved"""
                self._master.move(self._master_ident, e.x_root-self._x, e.y_root-self._y)
                self._x = e.x_root
                self._y = e.y_root

            def drag_select(e=None):
                # if self._label is not None:
                #    i=self._label.bind('<Motion>',drag_frame)
                #    self._bindings.append((self._label,i,'<Motion>'),)
                i = self.top_bar.bind('<Motion>', drag_frame)
                self._bindings.append((self.top_bar, i, '<Motion>'),)
                self._x = e.x_root
                self._y = e.y_root
                self.top_bar.lift()

            def drag_unselect(e=None):
                # if self._label is not None:
                #    self._label.unbind('<Motion>')
                self.top_bar.unbind('<Motion>')
                self.check_limits()

            # if self._label is not None:
            #    i=self._label.bind('<Button-2>',drag_select)
            #    j=self._label.bind('<ButtonRelease-2>',drag_unselect)
            #    self._bindings.append((self._label,i,'<Button-2>'),)
            #    self._bindings.append((self._label,j,'<ButtonRelease-2>'),)

            g = self.windowtitle.bind('<Button-1>', bring_foreground, add="+")
            h = self.top_bar.bind('<Button-1>', bring_foreground, add="+")
            i = self.top_bar.bind('<Button-1>', drag_select, add="+")
            j = self.top_bar.bind('<ButtonRelease-1>', drag_unselect)
            self._bindings.append((self.windowtitle, g, '<Button-1>'),)
            self._bindings.append((self.top_bar, h, '<Button-1>'),)
            self._bindings.append((self.top_bar, i, '<Button-1>'),)
            self._bindings.append((self.top_bar, j, '<ButtonRelease-1>'),)
            self.windowed = False
        else:
            # Build a frame as a transient toplevel
            t = tix.Toplevel(bg=self.bg)
            t.transient(master)
            t.resizable(0, 0)
            if kw.has_key('label'):
                t.title(kw['label'])
            t.protocol('WM_DELETE_WINDOW', self.toggle_windowed)

            self.contents = tix.Frame(t, bg=self.bg)
            self.contents.grid(padx=1, pady=1)
            self.container = t
            self.windowed = True

    def check_limits(self):
        x_max = self._master.winfo_width()
        y_max = self._master.winfo_height()

        # Make two iterations to garantee complete window recovery
        for i in (0, 1):

            if self.container.winfo_x() < 0:
                self._x = 1
                self._y = self.container.winfo_y()
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_x() > (x_max-self.container.winfo_width()):
                self._x = x_max-self.container.winfo_width()
                self._y = self.container.winfo_y()
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_y() < 0:
                self._x = self.container.winfo_x()
                self._y = 1
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_y() > y_max-self.container.winfo_height():
                self._x = self.container.winfo_x()
                self._y = y_max - self.container.winfo_height()
                self._place()
                self.container.update_idletasks()

    def _place(self):
        # If we are not given any position info, just use 0,0

        if not self._kw.has_key('position'):
            pos = (0, 0)
        else:
            pos = self._kw['position']
        if not self._kw.has_key('anchor'):
            anchor = tix.NW
        else:
            anchor = self._kw['anchor']

        # We reset x and y only if this is the first time we are placing the
        # frame. If the user moved it himself, then use the last known position.
        if self._x == 0 and self._y == 0:
            (self._x, self._y) = pos

        # Currently the master must be a canvas if not windowed
        try:
            if not self.windowed:
                self._master_ident = self._master.create_window((self._x, self._y), window=self.container, anchor=anchor)
        except AttributeError:
            logging.debug('RaFrame has no windowed attribute')

    def configure(self, **ckw):
        if ckw.has_key('position'):
            x, y = ckw['position']
            self._master.coords(self._master_ident, x, y)

    def bind(self, event, callback):
        """bind a callback to the RaFrame"""
        def bind_children(wid, event, callback):
            i = wid.bind(event, callback)
            self._bindings.append((wid, i, event),)
            for w in wid.winfo_children():
                bind_children(w, event, callback)
        bind_children(self.contents, event, callback)

    def show(self, e=None):
        """Show the RaFrame (to be used after having been hidden)"""
        if self.windowed:
            self.container.deiconify
        else:
            self._master_ident = self._master.create_window((self._x, self._y),
                window=self.container)
        self._place()
        self.check_limits()
        self.container.lift()
        self.showed=True

    def close(self, e=None):
        """Close the RaFrame and completely delete it"""
        logging.debug("Raframe.close")
        if (self._kw.has_key('closebuttonhides')
            and self._kw['closebuttonhides']):
            self.hide()
            return

        for t, i, ev in self._bindings:
            t.unbind(ev, i)
        self._bindings = []

        if not self.windowed:
            self._master.delete(self._master_ident)
        self.contents.destroy()
        if self.windowed:
            self.container.destroy()

    def hide(self, e=None):
        """Hide the RaFrame, but don't destroy the contents"""
        self._x = self.container.winfo_x()
        self._y = self.container.winfo_y()
        logging.debug("RaFrame.hide")
        if self.windowed:
            self.container.withdraw()
        else:
            self._master.delete(self._master_ident)
        self.showed = False

    def toggle_windowed(self, e=None):
        self.close()
        self.windowed = not self.windowed
        self._build(master=self._master, windowed=self.windowed, **self._kw)
        self._place()

    def conmuta(self, e=None):
        if self.showed:
            self.hide()
        else:
            self.show()

    def info_w_h(self, e=None):
        """Returns width and heigth of the container in pixels"""
        x1 = self.container.winfo_width()
        y1 = self.container.winfo_height()
        return (x1, y1)

    def __del__(self):
        # Print a message to make sure we are freing the memory
        logging.debug("RaFrame.__del__")


class RaCanvas(object):
    """A moveable window inside a radar display"""
    def __init__(self, master, **kw):
        """Construct a moveable, titled frame inside the parent radar display.

        Instantiation arguments:
        master -- parent master
        Options:
            label -- text to use on the window title
            closebutton -- Boolean (default True)
            dockbutton -- Boolean (default True)
            closebuttonhides -- Boolean (default False)
        """

        self._master = master
        self._kw = kw  # We need to save it for rebuilding in toggle_windowed
        self._closebutton = self._label = None
        self.bd, self.bg, self.fg = 'gray50', 'Black', 'White'
        self._bindings = []
        self._x, self._y = (0, 0)
        self.showed = True

        # Build the frame
        self._build(master, windowed=False, **kw)
        # Place it
        self._place()

    def _build(self, master=None, windowed=False, **kw):
        """Build the GUI elements, either as a canvas element, or as a toplevel"""
        if not windowed:
            # Build a frame as a tix.Canvas element
            # if kw.has_key('anchor') and kw['anchor'] != '':
            #    kw2 ={anchor:tix.NW}
            #    kw2['anchor'] = kw['anchor']
            self.container = tix.Frame(master, background=self.bd, borderwidth=1)

            self.top_bar = tix.Frame(self.container, background='magenta', borderwidth=1, relief=tix.FLAT, height=10)
            self.top_bar.pack(fill=tix.X, padx=0, pady=0)
            self.windowtitle = tix.Frame(self.container, background=self.bd, borderwidth=0, relief=tix.FLAT)
            self.windowtitle.pack(fill=tix.X)
            self.contents = tix.Canvas(self.container, background='blue')
            self.contents.pack(fill=tix.Frame, expand=1)
            # self.contents.create_oval(50,50,100,100,outline="yellow",fill="",tags="wind_dir")

            def bring_foreground(e=None):
                self.container.tkraise()

            if kw.has_key('label') and kw['label'] != '':
                self._label = tix.Label(self.windowtitle, text=kw['label'], bg=self.bd, foreground=self.fg, font=("Arial", "8", "bold"))
                self._label.pack(side=tix.LEFT, ipadx=2)
                i = self._label.bind('<Button-1>', bring_foreground, add="+")
                self._bindings.append((self._label, i, "<Button-1>"),)

            if not kw.has_key('closebutton') or kw['closebutton']:
                self._closebutton = tix.Label(self.top_bar, text='X', background='gray80', foreground=self.fg, width=2, font=("Arial", "5", "bold"))
                self._closebutton.pack(side=tix.RIGHT, padx=0, pady=0)
#                self._closebutton.place(anchor=tix.E)
                if (self._kw.has_key('closebuttonhides')
                    and self._kw['closebuttonhides']):
                    i = self._closebutton.bind('<Button-1>', self.hide)
                else:
                    i = self._closebutton.bind('<Button-1>', self.close)
                self._bindings.append((self._closebutton, i, "<Button-1>"),)
            else:
                self.top_bar.grid_propagate(0)
            # TODO
            # This is causing problems because it's really not well implemented
            # Better not to have to avoid the crashes it creates until it's
            # properly done.
            # if not kw.has_key('dockbutton') or kw['dockbutton']:
            #    self._undockbutton=tix.Label(self.container,text='O',bg=self.bd,fg='Black')
            #    self._undockbutton.pack(side=tix.RIGHT)
            #    i=self._undockbutton.bind('<Button-1>',self.toggle_windowed)
            #    self._bindings.append((self._undockbutton,i,'<Button-1>'),)

            # Frame dragging
            # self.top_bar.grid(row=1,column=0,padx=2,pady=2,sticky=N+E+S)
            # self.windowtitle.grid(row=2,column=0,padx=2,pady=2,sticky=N+S+W)
            # self.contents.grid(row=3,column = 0,padx=2,pady=2,sticky=N+E+S+W)

            def drag_frame(e=None):
                """Move the frame as many pixels as the mouse has moved"""
                self._master.move(self._master_ident, e.x_root-self._x, e.y_root-self._y)
                self._x = e.x_root
                self._y = e.y_root

            def drag_select(e=None):
                # if self._label is not None:
                #    i=self._label.bind('<Motion>',drag_frame)
                #    self._bindings.append((self._label,i,'<Motion>'),)
                i = self.top_bar.bind('<Motion>', drag_frame)
                self._bindings.append((self.top_bar, i, '<Motion>'),)
                self._x = e.x_root
                self._y = e.y_root
                self.top_bar.lift()

            def drag_unselect(e=None):
                # if self._labe lis not None:
                #    self._label.unbind('<Motion>')
                self.top_bar.unbind('<Motion>')
                self.check_limits()
            # if self._label is not None:
            #    i=self._label.bind('<Button-2>',drag_select)
            #    j=self._label.bind('<ButtonRelease-2>',drag_unselect)
            #    self._bindings.append((self._label,i,'<Button-2>'),)
            #    self._bindings.append((self._label,j,'<ButtonRelease-2>'),)

            g = self.windowtitle.bind('<Button-1>', bring_foreground, add="+")
            h = self.top_bar.bind('<Button-1>', bring_foreground, add="+")
            i = self.top_bar.bind('<Button-1>', drag_select, add="+")
            j = self.top_bar.bind('<ButtonRelease-1>', drag_unselect)
            self._bindings.append((self.windowtitle, g, '<Button-1>'),)
            self._bindings.append((self.top_bar, h, '<Button-1>'),)
            self._bindings.append((self.top_bar, i, '<Button-1>'),)
            self._bindings.append((self.top_bar, j, '<ButtonRelease-1>'),)
            self.windowed = False
        else:
            # Build a frame as a transient toplevel
            t = tix.Toplevel(bg=self.bg)
            t.transient(master)
            t.resizable(0, 0)
            if kw.has_key('label'):
                t.title(kw['label'])
            t.protocol('WM_DELETE_WINDOW', self.toggle_windowed)

            self.contents = tix.Canvas(t, bg=self.bg)
            self.contents.grid(padx=1, pady=1)
            self.container = t
            self.windowed = True

    def check_limits(self):
        x_max = self._master.winfo_width()
        y_max = self._master.winfo_height()

        # Make two iterations to garantee complete window recovery
        for i in (0, 1):

            if self.container.winfo_x() < 0:
                self._x = 1
                self._y = self.container.winfo_y()
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_x() > (x_max-self.container.winfo_width()):
                self._x = x_max-self.container.winfo_width()
                self._y = self.container.winfo_y()
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_y() < 0:
                self._x = self.container.winfo_x()
                self._y = 1
                self._place()
                self.container.update_idletasks()
            if self.container.winfo_y() > y_max-self.container.winfo_height():
                self._x = self.container.winfo_x()
                self._y = y_max - self.container.winfo_height()
                self._place()
                self.container.update_idletasks()

    def _place(self):
        # If we are not given any position info, just use 0,0

        if not self._kw.has_key('position'):
            pos = (0, 0)
        else:
            pos = self._kw['position']
        if not self._kw.has_key('anchor'):
            anchor = tix.NW
        else:
            anchor = self._kw['anchor']

        # We reset x and y only if this is the first time we are placing the
        # frame. If the user moved it himself, then use the last known position.
        if self._x == 0 and self._y == 0:
            (self._x, self._y) = pos

        # Currently the master must be a canvas if not windowed
        try:
            if not self.windowed:
                self._master_ident = self._master.create_window((self._x, self._y), window=self.container, anchor=anchor)
        except AttributeError:
            logging.debug('RaFrame has no windowed attribute')

    def configure(self, **ckw):
        if ckw.has_key('position'):
            x, y = ckw['position']
            self._master.coords(self._master_ident, x, y)

    def bind(self, event, callback):
        """bind a callback to the RaFrame"""
        def bind_children(wid, event, callback):
            i = wid.bind(event, callback)
            self._bindings.append((wid, i, event),)
            for w in wid.winfo_children():
                bind_children(w, event, callback)
        bind_children(self.contents, event, callback)

    def show(self, e=None):
        """Show the RaFrame (to be used after having been hidden)"""
        if self.windowed:
            self.container.deiconify
        else:
            self._master_ident = self._master.create_window((self._x, self._y), window=self.container)
        self._place()
        self.check_limits()
        self.container.lift()
        self.showed = True

    def close(self, e=None):
        """Close the RaFrame and completely delete it"""
        logging.debug("Raframe.close")
        if (self._kw.has_key('closebuttonhides')
            and self._kw['closebuttonhides']):
            self.hide()
            return

        for t, i, ev in self._bindings:
            t.unbind(ev, i)
        self._bindings = []

        if not self.windowed:
            self._master.delete(self._master_ident)
        self.contents.destroy()
        if self.windowed:
            self.container.destroy()

    def hide(self, e=None):
        """Hide the RaFrame, but don't destroy the contents"""
        self._x = self.container.winfo_x()
        self._y = self.container.winfo_y()
        logging.debug("RaFrame.hide")
        if self.windowed:
            self.container.withdraw()
        else:
            self._master.delete(self._master_ident)
        self.showed = False

    def toggle_windowed(self, e=None):
        self.close()
        self.windowed = not self.windowed
        self._build(master=self._master, windowed=self.windowed, **self._kw)
        self._place()

    def conmuta(self, e=None):
        if self.showed:
            self.hide()
        else:
            self.show()

    def info_w_h(self, e=None):
        """Returns width and heigth of the container in pixels"""
        x1 = self.container.winfo_width()
        y1 = self.container.winfo_height()
        return (x1, y1)

    def __del__(self):
        # Print a message to make sure we are freing the memory
        logging.debug("RaCanvas.__del__")


class RaDialog(RaFrame):
    """A frame whith OK and Cancel buttons and optional entries"""

    def __init__(self, master, **kw):
        """Create a frame and associate OK and Cancel bindings

        Options
            ok_callback -- If defined, a global binding is defined
                to call this function when enter is pressed
            esc_closes -- If True, a global binding is defined
                to close the frame when escape is pressed. Default True
            type -- if 'command' the frame is positioned on the bottom left corner
        """
        logging.debug("RaDialog.__init__ "+str(kw))

        self.container = None

        RaFrame.__init__(self, master, **kw)

    def _build(self, master=None, windowed=False, **kw):
        """Build the RaDialog GUI elements

        The dialog need not not know whether it will be built as a canvas
        element or as a toplevel, since it build on top of self.contents
        """

        # If there is already a dialog with the same label
        # close the existing one
        if _radialogs.has_key(kw['label']):
            _radialogs[kw['label']].close()
            return
        self._dialog_label = kw['label']
        _radialogs[kw['label']] = self

        RaFrame._build(self, master=master, windowed=windowed, **kw)

        # Dialog colors
        self._frame_colors = {'background': self.bd,
                            'highlightbackground': self.bg,
                            'highlightcolor': 'Black'}
        self._label_colors = {'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': 'Black',
                            'foreground': self.bg,
                            'activebackground': self.bd,
                            'activeforeground': self.fg,
                            'disabledforeground': ''}
        self._button_colors = {'background': self.bd,
                            'highlightbackground': self.bg,
                            'highlightcolor': self.bd,
                            'foreground': self.fg,
                            'activebackground': self.bg,
                            'activeforeground': self.fg,
                            'disabledforeground': ''}
        self._entry_colors = {'background': self.fg,
                            'highlightbackground': self.bg,
                            'highlightcolor': 'Black',
                            'foreground': self.bg,
                            'selectbackground': self.bg,
                            'selectforeground': self.fg,
                            'insertbackground': self.bd,
                            'insertwidth': 5,
                            'relief': tix.FLAT,
                            'borderwidth': 0,
                            'insertborderwidth': 0}

        # Dialog elements
        self.contents.configure(**self._frame_colors)
        f0 = tix.Frame(self.contents, **self._frame_colors)  # Text
        f0.pack(side=tix.TOP, pady=1, fill=tix.BOTH)
        f1 = tix.Frame(self.contents, **self._frame_colors)  # Dialog contents
        f1.pack(side=tix.TOP, pady=1, fill=tix.BOTH)
        # f2a = tix.Frame(self.contents, **self._frame_colors) # aux frame
        # f2a.pack(side=tix.BOTTOM, fill=tix.BOTH)

        # f2 = tix.Frame(f2a, **self._frame_colors) # Default dialog buttons
        # f2.pack(side=tix.RIGHT, fill=tix.BOTH)
        self.botom_bar = tix.Frame(self.container, background=self.bd, borderwidth=1, relief=tix.FLAT)
        self.botom_bar.pack(fill=tix.BOTH, side=tix.BOTTOM)
        f2 = self.botom_bar

        if kw.has_key('text'):
            l = tix.Label(f0, text=kw['text'], **self._label_colors)
            l.pack(side=tix.LEFT)
        but_accept = tix.Button(f2, text="ACEPTAR", font=("Arial", "6", "bold"), width=9, height=1, default='active', **self._button_colors)

        but_accept['command'] = self.accept
        if kw.has_key('ok_callback'):
            # Label(f2,text=' ', **self._label_colors).pack(side=tix.LEFT)
            but_cancel = tix.Button(f2, text="CANCELAR", font=("Arial", "6", "bold"), width=9, height=1, **self._button_colors)
            but_cancel.pack(side=tix.RIGHT)
            but_cancel['command'] = self.close
        but_accept.pack(side=tix.RIGHT, ipady=1)
        # Dialog entries
        if kw.has_key('entries'):
            self.entries = {}
            first = None
            spacer = None
            for i in kw['entries']:
                e = i.copy()  # Otherwise next time we get here we would have
                            # modified the entry and we would not have a label,for instance.
                e_label = e['label']
                entry = None
                tix.Label(f1, text=e_label, **self._label_colors).pack(side=tix.LEFT)
                del e['label']
                if e.has_key('def_value'):
                    def_value = e['def_value']
                    del e['def_value']
                else:
                    def_value = ''
                if e.has_key('values'):
                    entry = tix.ComboBox(f1, editable=True)
                    maxwidth = 0
                    for i in e['values']:
                        if len(i) > maxwidth: maxwidth = len(i)
                        entry.append_history(i)
                    entry.entry['width'] = maxwidth+5
                    entry.slistbox.listbox.configure(width=maxwidth+5,
                                                     # height=len(e['values']),
                                                     height=10,
                                                     bg=self.bg,
                                                     fg=self.fg)
                    # We need the master since we can't set the color of the
                    # frame containing the entry and the arrow
                    entry.entry.master['bg'] = self.bg
                    entry.label.configure(**self._label_colors)
                    entry.entry.configure(**self._entry_colors)
                    entry.slistbox.configure(**self._frame_colors)
                    entry.arrow.configure(**self._button_colors)
                    entry['value'] = def_value
                else:
                    e.update(self._entry_colors)
                    entry = tix.Entry(f1, **e)
                    entry.insert(tix.END, def_value)
                entry.pack(side=tix.LEFT)
                if first is None:
                    first = entry
                if entry:  # Store the entry widgets to make them available
                    self.entries[e_label] = entry
                spacer = tix.Label(f1, text=' ', **self._label_colors)
                spacer.pack(side=tix.LEFT)
            first.focus_set()  # Place the focus on the first entry
            spacer.destroy()  # The last spacer is unnecesary
        else:
            self.entries = None

        # Global bindings
        self._ok_callback = self._esc_closes = False
        i = self._master.bind_all("<Return>", self.accept)
        j = self._master.bind_all("<KP_Enter>", self.accept)
        self._bindings.append((self._master, i, '<Return>'),)
        self._bindings.append((self._master, j, '<KP_Enter>'),)
        if kw.has_key('ok_callback'):
            self._ok_callback = kw['ok_callback']

        if not kw.has_key('esc_closes') or kw['esc_closes']:
            i = self._master.bind_all("<Escape>", self.close)
            self._bindings.append((self._master, i, '<Escape>'),)
            self._esc_closes = True

    def _place(self):
        """Place the dialog on the lower left corner or the master"""
        RaFrame._place(self)
        if self._kw.has_key('position') or (self._x != 0 and self._y != 0):
            # If the user already defined a position or has previously moved
            # this frame, don't go any further
            return
        x_padding, y_padding = 20, 40
        self.container.update_idletasks()  # The geometry manager must be called before we know the size of the widget
        x = x_padding
        y = self._master.winfo_height()-self.container.winfo_height()-y_padding
        self.configure(position=(x, y))

    def accept(self, e=None):
        """Call the callback and check for results

        The callback function should returns False
        if the dialog has not validated correctly
        """
        if self._ok_callback and self.entries:
            # If entries were created we send them as an
            # argument to allow for validation
            if self._ok_callback(entries=self.entries)==False:
                return
        elif self._ok_callback:
            self._ok_callback()
        self.close()

    def close(self, e=None):
        # Por la etiqueta con que se registro (si el texto del titulo cambia, 'del' fallaba)
        _radialogs.pop(getattr(self, '_dialog_label', self._label['text']), None)
        RaFrame.close(self, e)


class RaWindRose(RaFrame):
    """An closeable, moveable frame with a wind rose inside"""

    def __init__(self, master, **kw):
        """Create an closable canvas displaying the wind rose

        SPECIFIC OPTIONS
        wind speed-- a text string to display
        wind dir-- to display on the wind rose
        """
        def_opt = {'position': (5, 5)}
        def_opt.update(kw)
        self.wind = (0, 0)
        self._w_dir = "180"
        self.metar = ""
        # The frame constructor method will call _build
        RaFrame.__init__(self, master=master, closebuttonhides=True, **def_opt)

    def _build(self, master=None, windowed=False, **kw):
        if windowed:
            def_opt = {'label': 'Wind'}
            def_opt.update(kw)
        else:
            def_opt = kw
        RaFrame._build(self, master=master, windowed=windowed, **def_opt)
        # dir_h = self._wind_dir.winfo_reqheight()
        padding = 20
        rose_r = 80
        circle_r = 5
        size = 2*(rose_r+circle_r)
        wind_h = size
        spd_h = 30
        metar_h = 60
        (x0, y0) = (rose_r+circle_r+padding, rose_r+circle_r+padding)
        self._wind_dir = tix.Canvas(self.contents, background='black', width=size, height=size+metar_h)
        self._wind_dir.grid(ipadx=padding, ipady=padding)
        (tx, ty) = pr((rose_r+circle_r, 0))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='N', anchor=tix.S)
        (tx, ty) = pr((rose_r+circle_r, 180))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='S', anchor=tix.N)
        (tx, ty) = pr((rose_r+circle_r, 90))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='E', anchor=tix.W)
        (tx, ty) = pr((rose_r+circle_r, 270))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='W', anchor=tix.E)
        (tx, ty) = pr((rose_r+circle_r, 30))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='03', anchor=tix.SW)
        (tx, ty) = pr((rose_r+circle_r, 60))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='06', anchor=tix.SW)
        (tx, ty) = pr((rose_r+circle_r, 120))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='12', anchor=tix.NW)
        (tx, ty) = pr((rose_r+circle_r, 150))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='15', anchor=tix.NW)
        (tx, ty) = pr((rose_r+circle_r, 210))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='21', anchor=tix.NE)
        (tx, ty) = pr((rose_r+circle_r, 240))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='24', anchor=tix.NE)
        (tx, ty) = pr((rose_r+circle_r, 300))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='30', anchor=tix.SE)
        (tx, ty) = pr((rose_r+circle_r, 330))
        self._wind_dir.create_text(x0+tx, y0-ty, fill="white", text='33', anchor=tix.SE)

        for i in range(0, 360, 10):
            (dx, dy) = pr((rose_r, i))
            cx = x0 + dx
            cy = y0 - dy
            self._wind_dir.create_oval(cx-circle_r, cy-circle_r, cx+circle_r, cy+circle_r, outline="white", fill="", tags="wind_dir"+str(i))
        self._wind_spd = tix.Label(self.contents,
                    font=('Courier', '40', 'bold'),
                    foreground="red",    # Very yellowed orange color
                    background='black',
                    text="%d" % floor(self.wind[0]))
        self._wind_spd.place(relx=0.5, y=0.5*(wind_h-spd_h), anchor=tix.N)
        self._metar = tix.Label(self.contents,
                    font=('Courier', '12', 'bold'),
                    foreground="black",
                    background='white',
                    text=self.metar,
                    anchor=tix.NW, justify=tix.LEFT, wraplength=size+2*padding)
        self._metar.place(relx=0.0, rely=1.0, relwidth=1.0, height=metar_h, anchor=tix.SW)

    def configure(self, **options):
        RaFrame.configure(self, **options)
        if options.has_key('wind_spd'):
            self._wind_spd['text'] = options['wind_spd']
        if options.has_key('wind_dir'):
            self._wind_dir.itemconfigure("wind_dir"+self._w_dir, fill='')
            w_dir = str(10*int(round(options['wind_dir']/10, 0)))
            self._wind_dir.itemconfigure("wind_dir"+w_dir, fill='red')
            self._w_dir = w_dir
        if options.has_key('metar'):
            self._metar['text'] = options['metar']


class RaClock(RaFrame):
    """An uncloseable, moveable frame with adjustable text inside"""

    def __init__(self, master, **kw):
        """Create an unclosable frame displaying the clock time

        SPECIFIC OPTIONS
        time -- a text string to display
        """
        def_opt = {'position': (5, 5), 'closebutton': False, 'undockbutton': False}
        def_opt.update(kw)
        # The frame constructor method will call _build
        RaFrame.__init__(self, master, **def_opt)

    def _build(self, master=None, windowed=False, **kw):
        if windowed:
            def_opt = {'label': 'Reloj'}
            def_opt.update(kw)
        else:
            def_opt = kw
        RaFrame._build(self, master=master, windowed=windowed, **def_opt)

        self._time = tix.Button(self.contents,
                    font=('Courier', '20', 'bold'),
                    foreground="#%04x%04x%04x" % (63736, 46774, 7453),    # Very yellowed orange color
                    background='black')
        self._time.grid(padx=5, pady=5)

    def configure(self, **options):
        RaFrame.configure(self, **options)
        if options.has_key('time'):
            self._time['text'] = options['time']


class FlashableAtcLabelImage(tix.Label):
    def flash(self):
        if self.img_file_str == "img/"+Aircraft.ATC_MISSING:
            img_file_str = "img/"+Aircraft.ATC_NA
        elif self.img_file_str == "img/"+Aircraft.ATC_NA:
            img_file_str = "img/"+Aircraft.ATC_MISSING
        else:
            return
        img_file = os.path.join(conf.common_dir, img_file_str)
        aut_img = tix.PhotoImage(file=img_file)
        self.configure(image=aut_img)
        self.image = aut_img
        self.img_file_str = img_file_str
        self.after(500, self.flash)  # tkinter delayed call mechanism


class FlashableAtcLabelText(tix.Label):
    def flash(self):
        if self.cget("background") != self.cget("foreground"):
            self.fg = self.cget("foreground")
            self.configure(foreground=self.cget("background"))
        else:
            self.configure(foreground=self.fg)
        self.after(500, self.flash)  # tkinter delayed call mechanism


class ATCBahia(tix.Toplevel):
    def __init__(self, radisplay):
        self.radisplay = radisplay
        self.showed = True
        self.elements = tix.IntVar()
        self.entry = None
        self.min_width = 0
        self.max_width = 0
        self.min_height = 0
        self.max_height = 0
        self.papelera_width = 96
        self.panel_width = 593
        # Divisiones en el ancho de la ficha
        self.ficha_w1 = 110
        self.ficha_w2 = 160
        self.ficha_w3 = 210
        self.ficha_w4 = 235
        self.ficha_w5 = 260
        self.ficha_w6 = 285
        self.ficha_w7 = 310
        self.ficha_w8 = 335
        self.ficha_w9 = 360
        self.ficha_w10 = 430
        self.ficha_w11 = 500
        self.ficha_width = 538
        self.panel_pad = int(0.5*(self.panel_width-self.ficha_width))
        # Divisiones en el alto de la ficha
        self.ficha_h1 = 20
        self.ficha_h2 = 30
        self.ficha_h3 = 45
        self.ficha_h4 = 60
        self.ficha_height = 75
        self.coqueo_left = False
        self.coqueo_right = False
        self.npanels = 3
        tix.Toplevel.__init__(self)
        self._build()
        self.update_fijos()

    def _build(self, **kw):
        self.title('BAHIA DE FICHAS')
        self.window = tix.Frame(self)
        self.window.pack(fill=tix.BOTH, expand=True)
        self.window.update_idletasks()
        # self.w = self.radisplay.screen_width
        self.h = self.radisplay.screen_height

        ############
        self.left_panel = tix.Frame(self.window, width=self.panel_width, height=self.h, bg='gray', highlightcolor='black', highlightthickness=1)
        self.left_panel.pack(side=tix.LEFT, fill=tix.BOTH, expand=True)
        self.centre_panel = tix.Frame(self.window, width=self.panel_width, height=self.h, bg='gray', highlightcolor='black', highlightthickness=1)
        self.centre_panel.pack(side=tix.LEFT, fill=tix.BOTH, expand=True)
        self.right_panel = tix.Frame(self.window, width=self.panel_width, height=self.h, bg='gray', highlightcolor='black', highlightthickness=1)
        self.right_panel.pack(side=tix.LEFT, fill=tix.BOTH, expand=True)

        # Add a scrollbar in each pannel
        # left
        self.canvas_left = tix.Canvas(self.left_panel, width=self.panel_width, height=self.h, bg='gray')
        yscrollbar = tix.Scrollbar(self.left_panel, orient=tix.VERTICAL)
        yscrollbar.pack(side=tix.RIGHT, fill=tix.Y)
        yscrollbar.config(command=self.canvas_left.yview)
        self.canvas_left.config(yscrollcommand=yscrollbar.set)
        self.canvas_left.pack(side=tix.BOTTOM)
        self.framein_left = tix.Frame(self.canvas_left, width=self.panel_width, height=self.h, bg='gray')
        self.framein_left.pack(side=tix.BOTTOM)
        self.canvas_left.create_window(0, self.h, window=self.framein_left, anchor=tix.S)
        self.canvas_left.update_idletasks()
        self.canvas_left.config(scrollregion=self.canvas_left.bbox(tix.ALL))
        frame = self.framein_left
        ra_bind(self.radisplay, frame, "<Button-1>", lambda event: self.coquear(event))

        # centre
        self.canvas_centre = tix.Canvas(self.centre_panel, width=self.panel_width, height=self.h, bg='gray')
        yscrollbar = tix.Scrollbar(self.centre_panel, orient=tix.VERTICAL)
        yscrollbar.pack(side=tix.RIGHT, fill=tix.Y)
        yscrollbar.config(command=self.canvas_centre.yview)
        self.canvas_centre.config(yscrollcommand=yscrollbar.set)
        self.canvas_centre.pack(side=tix.BOTTOM)
        self.framein_centre = tix.Frame(self.canvas_centre, width=self.panel_width, height=self.h, bg='gray')
        self.framein_centre.pack(side=tix.BOTTOM)
        self.canvas_centre.create_window(0, self.h, window=self.framein_centre, anchor=tix.S)
        self.canvas_centre.update_idletasks()
        self.canvas_centre.config(scrollregion=self.canvas_centre.bbox(tix.ALL))
        frame = self.framein_centre
        ra_bind(self.radisplay, frame, "<Button-1>", lambda event: self.coquear(event))

        # right
        self.canvas_right = tix.Canvas(self.right_panel, width=self.panel_width, height=self.h, bg='gray')
        yscrollbar = tix.Scrollbar(self.right_panel, orient=tix.VERTICAL)
        yscrollbar.pack(side=tix.RIGHT, fill=tix.Y)
        yscrollbar.config(command=self.canvas_right.yview)
        self.canvas_right.config(yscrollcommand=yscrollbar.set)
        self.canvas_right.pack(side=tix.BOTTOM)
        self.framein_right = tix.Frame(self.canvas_right, width=self.panel_width, height=self.h, bg='gray')
        self.framein_right.pack(side=tix.BOTTOM)
        self.canvas_right.create_window(0, self.h, window=self.framein_right, anchor=tix.S)
        self.canvas_right.update_idletasks()
        self.canvas_right.config(scrollregion=self.canvas_right.bbox(tix.ALL))
        frame = self.framein_right
        ra_bind(self.radisplay, frame, "<Button-1>", lambda event: self.coquear(event))

        self.delete_frame = tix.Frame(self.window, width=self.papelera_width, height=self.h, bg='red', highlightcolor='black', highlightthickness=1)
        self.delete_frame.pack(side=tix.LEFT, fill=tix.BOTH, expand=True)
        ############
        canvas_delete = tix.Canvas(self.delete_frame, width=self.papelera_width, height=self.h, bg='red')
        canvas_delete.pack(fill=tix.BOTH)
        img_dir = os.path.join(conf.common_dir, 'img')
        img_papelera = os.path.join(img_dir, 'papelera_edited.GIF')
        photo = tix.PhotoImage(file=img_papelera)
        label = tix.Label(canvas_delete, image=photo)
        label.image = photo
        label.pack(side=tix.TOP, fill=tix.BOTH, expand=True)

        self.protocol("WM_DELETE_WINDOW", self.hide)

        self.fs_added = []
        self.fs_removed = []
        self.sector_list = []
        self.fijos_added = []


    def coquear(self, event):
        def coqueo_left(canvas, zone_str, row):
            callsign = canvas.callsign
            try:
                name = canvas.name
            except:
                name = 'ficha'
            if callsign is not None and name == 'ficha':
                for track in self.radisplay.tracks:
                    if track.cs == callsign:
                        vt = track
                f = self.radisplay._tracks_flights[vt]
                if canvas.right:
                    canvas.right = False
                    canvas.left = False
                else:
                    canvas.right = False
                    canvas.left = True
                self.insertar_ficha(f, zone_str=zone_str, insert_row=row, dragged_canvas=canvas)

        def coqueo_right(canvas, zone_str, row):
            # print('Coqueo right')
            callsign = canvas.callsign
            try:
                name = canvas.name
            except:
                name = 'ficha'
            if callsign is not None and name == 'ficha':
                for track in self.radisplay.tracks:
                    if track.cs == callsign:
                        vt = track
                f = self.radisplay._tracks_flights[vt]
                if canvas.left:
                    canvas.right = False
                    canvas.left = False
                else:
                    canvas.right = True
                    canvas.left = False
                self.insertar_ficha(f, zone_str=zone_str, insert_row=row, dragged_canvas=canvas)
        # Identificar el vuelo que se est? coqueando
        canvas_coqueado, zone_str, row = self.canvas_by_coords(event.x_root, event.y_root)
        try:
            name = canvas_coqueado.name
        except:
            name = 'ficha'
        if name == 'ficha' and ((event.x >= 0 and event.x <= self.panel_pad) or (event.x >= self.panel_pad + self.ficha_width and event.x <= self.panel_width)):
            # Borrar el vuelo solo si es una ficha
            if zone_str == 'left':
                zone = self.framein_left
            elif zone_str == 'centre':
                zone = self.framein_centre
            elif zone_str == 'right':
                zone = self.framein_right
            canvas = zone.grid_slaves(row=row, column=0)[0]
            canvas.grid_forget()
            gsize = zone.grid_size()
            nrows = gsize[1]
            for irow in range(row+1, nrows):
                canvas = zone.grid_slaves(row=irow, column=0)[0]
                canvas.grid(row=irow-1, column=0, sticky=tix.NSEW)
            # Insertar el vuelo coqueado a derecha o a izquierda
            if event.x >= 0 and event.x <= self.panel_pad:
                coqueo_left(canvas=canvas_coqueado, zone_str=zone_str, row=row)
            elif event.x >= self.panel_pad + self.ficha_width and event.x <= self.panel_width:
                coqueo_right(canvas=canvas_coqueado, zone_str=zone_str, row=row)

    def update_cfl(self, callsign, cfl):
        irow_found = None
        zone_str = None
        radisp = self.radisplay
        for track in radisp.tracks:
            if track.cs == callsign:
                vt = track
        f = radisp._tracks_flights[vt]
        f.atc_cfl = cfl
        callsign = '%9s' % (f.callsign)
        # Busqueda por los paneles del canvas asociado a ese vuelo, la zona y la fila
        for i in range(self.npanels):
            if i == 0:
                zone = self.framein_left
                zone_str = 'left'
            elif i == 1:
                zone = self.framein_centre
                zone_str = 'centre'
            elif i == 2:
                zone = self.framein_right
                zone_str = 'right'

            gsize = zone.grid_size()
            nrows = gsize[1]
            for irow in range(nrows):
                canvas = zone.grid_slaves(row=irow, column=0)[0]
                if canvas.callsign.strip() == callsign.strip():
                    irow_found = irow
                    break
            if irow_found is not None:
                break
        self.remove_fs(f)
        self.insertar_ficha(f, zone_str=zone_str, insert_row=irow_found, dragged_canvas=canvas)

    def show(self):
        self.deiconify()
        self.showed = True
        return

    def hide(self):
        self.withdraw()
        self.showed = False
        return

    def conmuta(self, e=None):
        if self.showed:
            self.hide()
        else:
            self.show()

        #######################################
    def update(self):
        # Add to tabular after printing time and delete after 30 minutes, if not printed yet
        sector = self.radisplay.sector
        sector_list = sector.split(",")
        # Comprueba constantemente si se ha cambiado de sector para reescribir los fijos en la bahía
        # Esto ya no es necesario porque se hace desde RaDisplay
        # if sector not in self.sector_list: #Since I have changed the sector, I have to load the new strips
        #    borrar TODAS las fichas antiguas, en la lista de fichas
        #    for f in self.fijos_added:
        #        self.remove_fijo(f)
        #        self.fijos_added.remove(f)
        #    self.sector_list.append(sector)
        #    for txt in self.fijos_added:
        #        self.remove_fijo(txt)
        #    self.update_fijos()

        t = self.radisplay.t
        pl = []
        for f in self.radisplay.flights:
            if not f.callsign in self.fs_added and not f.callsign in self.fs_removed and f.fr != 'VEH':
                for sect in sector_list:
                    # Antes se consultaba 'sector' (la posicion completa) en vez de cada 'sect':
                    # con posiciones multisector ('A,B') no se insertaba ninguna ficha
                    if f.fs_print_t.has_key(sect) and f.fs_print_t[sect] < t:
                        pl.append(f)
                        break
        #pl.sort(lambda p, q: -cmp(p.fs_print_t[sector], q.fs_print_t[sector]))
        # Bahia de torre: solo fichas de los aerodromos del parametro 'bahia_torre_ads'
        # (por defecto LEST en los escenarios de LECG; vacio = todas). Antes el filtro
        # 'solo LEST' se aplicaba a las torres de todos los escenarios.
        torre_ads = self.radisplay.fir.param('bahia_torre_ads', [])
        for f in pl:
            if torre_ads and ('LCL' in sector or 'TWR' in sector):
                if f.ades in torre_ads or f.adep in torre_ads:
                    self.insertar_ficha(f)
            else:
                self.insertar_ficha(f)
        # self.radisplay.set_active_sectors(self.sector_list)

    def remove_fijo(self, f):
        sector = self.radisplay.sector
        fir = self.radisplay.fir
        txt = f
        try:
            callsign = self.dragged_canvas.callsign
        except:
            callsign = txt
        irow_found = None
        for i in range(self.npanels):
            if i == 0:
                zone = self.framein_left
                external_canvas = self.canvas_left
                zone_str = 'left'
            elif i == 1:
                zone = self.framein_centre
                external_canvas = self.canvas_centre
                zone_str = 'centre'
            elif i == 2:
                zone = self.framein_right
                external_canvas = self.canvas_right
                zone_str = 'right'

            gsize = zone.grid_size()
            nrows = gsize[1]
            ncols = gsize[0]
            for irow in range(nrows):
                canvas = zone.grid_slaves(row=irow, column=0)[0]
                if canvas.callsign.strip() == callsign.strip():
                    irow_found = irow
                    canvas.grid_forget()
                    break
            if irow_found is not None:
                break
        # JRAR: Move up remaining strips
        if irow_found is None:
            return zone_str, irow_found
        for irow in range(irow_found+1, nrows):
            canvas = zone.grid_slaves(row=irow, column=0)[0]
            canvas.grid(row=irow-1, column=0, sticky=tix.NSEW)

        external_canvas.config(scrollregion=external_canvas.bbox(tix.ALL))
        return zone_str, irow_found

    # ------------------------------------------------------------------
    # Ayudas de la bahia de fichas para parametros de escenario (Fase 3 parte 2)
    # ------------------------------------------------------------------
    def _local_ads(self):
        """Aerodromos locales de la posicion; con posiciones multisector ('A,B') se unen
        los de cada sector (antes fir.local_ads[sector] daba KeyError)."""
        fir = self.radisplay.fir
        sector = self.radisplay.sector
        if sector in fir.local_ads:
            return fir.local_ads[sector]
        ads = []
        for s in str(sector).split(','):
            for ad in fir.local_ads.get(s.strip(), []):
                if ad not in ads:
                    ads.append(ad)
        return ads

    def _alias_ad(self, ad):
        return self.radisplay.fir.param('alias_ads', {}).get(ad, ad)

    def _rwy_txt_config(self, ad, rwy_txt, idx):
        """Pista mostrada en la ficha segun la configuracion en uso (parametro 'ficha_pistas_config')."""
        cfg = self.radisplay.fir.param('ficha_pistas_config', {})
        if not cfg:
            return rwy_txt
        try:
            key = '%s %s' % (ad, self.radisplay.fir.aerodromes[ad].rwy_in_use.txt_desig)
        except:
            return rwy_txt
        if key.upper() in cfg:
            return cfg[key.upper()][idx]
        return rwy_txt

    # ------------------------------------------------------------------
    # Fijos de la bahia (Fase 3 parte 2): definidos en fir.bahia_fijos (hoja
    # 'BahiaFijos' del escenario o FIR._default_bahia_fijos), en lugar de un
    # bloque de codigo por escenario.
    # ------------------------------------------------------------------
    def _fijo_path(self, ruta):
        fir = self.radisplay.fir
        sector = self.radisplay.sector
        sector_dir = str(sector).replace('/', '_').replace(' ', '_')
        config = ''
        try:
            config = fir.aerodromes[fir.ap[0]].rwy_in_use.txt_desig.lower()
        except:
            pass
        ruta = ruta.replace('{img}', os.path.join(conf.common_dir, 'img'))
        ruta = ruta.replace('{sector}', sector_dir).replace('{config}', config)
        ruta = ruta.replace('\\', os.sep).replace('/', os.sep)
        return os.path.normpath(ruta)

    def _expand_fijos(self):
        """Lista de fijos (dict) de la posicion actual, con las carpetas IMAGENES expandidas."""
        fir = self.radisplay.fir
        fijos = select_bahia_fijos(getattr(fir, 'bahia_fijos', []), self.radisplay.sector)
        out = []
        n_libre = 0
        for spec in fijos:
            tipo = spec['tipo']
            if tipo == 'IMAGENES':
                carpeta = self._fijo_path(spec['ruta'])
                try:
                    nombres = os.listdir(carpeta)
                except:
                    logging.warning("Bahia de fichas: no existe la carpeta de fijos %s", carpeta)
                    continue
                numerados = []
                for nombre in nombres:
                    m = re.match(r'^fijo(\d+)\.jpe?g$', nombre, re.IGNORECASE)
                    if m and os.path.isfile(os.path.join(carpeta, nombre)):
                        numerados.append((int(m.group(1)), nombre))
                numerados.sort()
                for num, nombre in numerados:
                    s = dict(spec)
                    s['tipo'] = 'IMAGEN'
                    s['id'] = 'Fijo%d' % num
                    s['img_file'] = os.path.join(carpeta, nombre)
                    out.append(s)
            elif tipo == 'IMAGEN':
                s = dict(spec)
                s['img_file'] = self._fijo_path(spec['ruta'])
                if not s.get('id'):
                    s['id'] = os.path.splitext(os.path.basename(s['img_file']))[0]
                out.append(s)
            elif tipo == 'TEXTOLIBRE':
                n_libre += 1
                s = dict(spec)
                s['id'] = 'TEXTOLIBRE%d' % n_libre
                out.append(s)
            else:
                out.append(dict(spec))
        return out

    def _crear_fijo(self, zone, row, spec, color='white', zone_str='', textolibre=''):
        """Crea en 'zone' (fila 'row') el canvas de un fijo descrito por 'spec'."""
        callsign = None
        canvas = tix.Canvas(zone, bg=color, bd=0, highlightthickness=0, takefocus=0,
                            width=self.ficha_width, height=self.ficha_height)
        canvas.grid(row=row, column=0, sticky=tix.S)
        if zone_str in ['left', 'centre']:
            canvas.grid_configure(padx=self.panel_pad)
        canvas.name = 'fijo'
        canvas.callsign = spec['id']
        canvas.txt = spec['id']
        canvas.fijo_spec = spec
        canvas.escenario = self.radisplay.fir.name
        canvas.left = False
        canvas.right = False
        target = canvas
        if spec['tipo'] == 'TEXTOLIBRE':
            text = tix.StringVar()
            text.set(textolibre)
            entry = tix.Entry(canvas, font=("Courier", 28), textvariable=text)
            entry.grid(row=0, column=0, padx=45, pady=18)
            canvas.textolibre = text.get()
            canvas.text_variable = text
            text.trace('w', lambda name, index, mode, c=canvas, v=text: setattr(c, 'textolibre', v.get()))
        elif spec['tipo'] == 'IMAGEN':
            try:
                photo = ImageTk.PhotoImage(Image.open(spec['img_file']))
            except:
                logging.warning("Bahia de fichas: no se puede abrir %s", spec.get('img_file'))
                photo = None
            if photo is not None:
                label = tix.Label(canvas, image=photo, width=self.ficha_width, height=self.ficha_height)
                label.image = photo
                label.pack(fill=tix.BOTH, expand=True)
                target = label
            else:
                canvas.create_text(spec.get('x', 180), 15, anchor="nw", text=spec['id'], font="Courier 28")
        else:
            canvas.create_text(spec.get('x', 180), 15, anchor="nw", text=spec['texto'], font="Courier 28")
        canvas.update_idletasks()
        w_canvas, h_canvas = canvas.winfo_width(), canvas.winfo_height()
        canvas.myborder = canvas.create_rectangle(0, 0, w_canvas-2, h_canvas-2, outline='red', width=3)
        ra_bind(self.radisplay, target, "<Button-1>",
                lambda event, callsign=callsign, canvas=canvas: self.rightclicked(event, callsign, canvas))
        ra_bind(self.radisplay, target, "<B1-Motion>", self.drag)
        ra_bind(self.radisplay, target, "<ButtonRelease-1>", self.drop)
        return canvas

    def _zone_by_str(self, zone_str):
        if zone_str == 'left':
            return self.framein_left, self.canvas_left
        elif zone_str == 'centre':
            return self.framein_centre, self.canvas_centre
        return self.framein_right, self.canvas_right

    def insert_fijo(self, f, zone_str='', insert_row=0, color='white'):
        if insert_row is None:
            insert_row = 0
        dragged = self.dragged_canvas
        zone, external_canvas = self._zone_by_str(zone_str)
        spec = getattr(dragged, 'fijo_spec', None)
        if spec is None:
            spec = {'pos': '', 'tipo': 'TEXTO', 'texto': dragged.txt, 'x': 180, 'id': dragged.txt, 'ruta': ''}
        # Move all labels one row down
        gsize = zone.grid_size()
        nrows = gsize[1]
        for irow in range(nrows, insert_row, -1):
            canvas = zone.grid_slaves(row=irow-1, column=0)[0]
            canvas.grid(row=irow, column=0, sticky=tix.S)
        self._crear_fijo(zone, insert_row, spec, color=color, zone_str=zone_str,
                         textolibre=getattr(dragged, 'textolibre', ''))
        external_canvas.config(scrollregion=external_canvas.bbox(tix.ALL))

    def update_fijos(self, zone_str='', insert_row=0):
        zone, external_canvas = self._zone_by_str(zone_str)
        for i, spec in enumerate(self._expand_fijos()):
            canvas = self._crear_fijo(zone, insert_row + i, spec, color='white')
            self.fijos_added.append(canvas.txt)
        external_canvas.config(scrollregion=external_canvas.bbox(tix.ALL))

    def update_strip(self, f):
        # Add to tabular after printing time and delete after 30 minutes, if not printed yet
        sector = self.radisplay.sector
        t = self.radisplay.t
        # Insert updated flight strip
        if f.callsign not in self.fs_added:
            self.insertar_ficha(f)

    def remove_fs(self, f):
        sector = self.radisplay.sector
        fir = self.radisplay.fir
        callsign = '%9s' % (f.callsign)
        irow_found = None
        for i in range(self.npanels):
            if i == 0:
                zone = self.framein_left
                external_canvas = self.canvas_left
                zone_str = 'left'
            elif i == 1:
                zone = self.framein_centre
                external_canvas = self.canvas_centre
                zone_str = 'centre'
            elif i == 2:
                zone = self.framein_right
                external_canvas = self.canvas_right
                zone_str = 'right'

            # zone.pack_configure(side=tix.BOTTOM)
            gsize = zone.grid_size()
            nrows = gsize[1]
            ncols = gsize[0]
            for irow in range(nrows):
                canvas = zone.grid_slaves(row=irow, column=0)[0]
                if canvas.callsign.strip() == callsign.strip():
                    irow_found = irow
                    canvas.grid_forget()
                    break
            if irow_found is not None:
                break

        # JRAR: Move up remaining strips
        if irow_found is None: return zone_str, irow_found
        for irow in range(irow_found+1, nrows):
            canvas = zone.grid_slaves(row=irow, column=0)[0]
            try:
                if canvas.left:
                    canvas.grid(row=irow-1, column=0, sticky=tix.W)
                    canvas.grid_configure(padx=0)
                elif canvas.right:
                    canvas.grid(row=irow-1, column=0, sticky=tix.E)
                    canvas.grid_configure(padx=0)
                else:
                    canvas.grid(row=irow-1, column=0, sticky=tix.S)
                    canvas.grid_configure(padx=self.panel_pad)
            except:
                canvas.grid(row=irow - 1, column=0, sticky=tix.S)
                canvas.grid_configure(padx=self.panel_pad)
        self.fs_added.remove(f.callsign)
        self.fs_removed.append(f.callsign)

        external_canvas.config(scrollregion=external_canvas.bbox(tix.ALL))
        return zone_str, irow_found

    def insertar_ficha(self, f, zone_str='', insert_row=0, color='white', dragged_canvas=None):
        radisp = self.radisplay
        sector = radisp.sector
        fir = radisp.fir
        print_time = radisp.t.strftime("%H:%M")
        print_time_txt = print_time[11:16]
        time = '%10s' % (self.radisplay.t)
        minute = time[14:16]
        hour = time[11:13]
        if dragged_canvas is None:
            estimated_t = 0
            if f.ades in self._local_ads():
                iaf = f.iaf
                for i in range(0, len(f.route)):
                    if f.route[i].fix == iaf:
                        try:
                            estimated_t = '%02d:%02d'%(f.route[i].eto.hour, f.route[i].eto.minute)
                            f.estimated_t = estimated_t
                        except:
                            f.estimated_t = ''
            qnh_check = False
            rwy_check = False
            minute_check = False
            minute2_check = False
            minute3_check = False
            minute4_check = False
            minute5_check = False
            minute6_check = False
            minute7_check = False
            minute8_check = False
            minute9_check = False
            emergency_check = False
            trasponder_check = False
            Bcheck = False
            freeText=''
            ils_check = False
            freq_check = False
            hour_check = False
            hour2_check = False
            left_coqueo = False
            right_coqueo = False
            cfl_leave_check = False
        else:
            qnh_check = dragged_canvas.qnh
            rwy_check = dragged_canvas.rwy
            minute_check = dragged_canvas.minute
            minute2_check = dragged_canvas.minute2
            minute3_check = dragged_canvas.minute3
            minute4_check = dragged_canvas.minute4
            minute5_check = dragged_canvas.minute5
            minute6_check = dragged_canvas.minute6
            minute7_check = dragged_canvas.minute7
            minute8_check = dragged_canvas.minute8
            minute9_check = dragged_canvas.minute9
            emergency_check = dragged_canvas.emergency
            trasponder_check = dragged_canvas.trasponder
            Bcheck = dragged_canvas.Bcheck
            freeText = dragged_canvas.freeText
            ils_check = dragged_canvas.ils
            freq_check = dragged_canvas.freq
            hour_check = dragged_canvas.hour
            hour2_check = dragged_canvas.hour2
            left_coqueo = dragged_canvas.left
            right_coqueo = dragged_canvas.right
            cfl_leave_check = dragged_canvas.cfl_leave
            try:
                estimated_t = f.estimated_t
            except:
                estimated_t = ''
        if zone_str == '':
            zone = self.framein_right
            external_canvas = self.canvas_right
        elif zone_str == 'left':
            zone = self.framein_left
            external_canvas = self.canvas_left
        elif zone_str == 'centre':
            zone = self.framein_centre
            external_canvas = self.canvas_centre
        elif zone_str == 'right':
            zone = self.framein_right
            external_canvas = self.canvas_right
        callsign = '%9s' % f.callsign
        callsign = callsign.strip()
        ecl = '%3s' % int(f.ecl)
        park = '%5s' % f.park
        type_txt = f.type
        # CFL
        try:
            for track in radisp.tracks:
                if track.cs == callsign:
                    vt = track
            f = radisp._tracks_flights[vt]
            cfl = f.atc_cfl
        except:
            cfl = int(f.cfl)

        if f.adep in self._local_ads():
            rwy_txt = f.deprwy
            rwy_txt = self._rwy_txt_config(f.adep, rwy_txt, 0)  # parametro 'ficha_pistas_config' (antes Barcelona)
        elif f.ades in self._local_ads():
            rwy_txt = f.desrwy
            rwy_txt = self._rwy_txt_config(f.ades, rwy_txt, 1)  # parametro 'ficha_pistas_config' (antes Barcelona)
        else:
            rwy_txt = f.desrwy
        # Move all strips one row down
        gsize = zone.grid_size()
        nrows = gsize[1]
        for irow in range(nrows, insert_row, -1):
            canvas = zone.grid_slaves(row=irow-1, column=0)[0]
            try:
                if canvas.left:
                    canvas.grid(row=irow, column=0, sticky=tix.W)
                    canvas.grid_configure(padx=0)
                elif canvas.right:
                    canvas.grid(row=irow, column=0, sticky=tix.E)
                    canvas.grid_configure(padx=0)
                else:
                    canvas.grid(row=irow, column=0, sticky=tix.S)
                    canvas.grid_configure(padx=self.panel_pad)
            except:
                canvas.grid(row=irow, column=0, sticky=tix.S)
                canvas.grid_configure(padx=self.panel_pad)
        # Add new strip in row 0
        irow = insert_row
        canvas = tix.Canvas(zone, bg=color, bd=0, highlightthickness=0, takefocus=0, width=self.ficha_width, height=self.ficha_height)
        ########################
        if zone_str in ['centre', 'left', 'right']:
            if left_coqueo:
                canvas.grid(row=irow, column=0, sticky=tix.W)
                canvas.grid_configure(padx=0)
                canvas.left = left_coqueo
                canvas.right = right_coqueo
            elif right_coqueo:
                canvas.grid(row=irow, column=0, sticky=tix.E)
                canvas.grid_configure(padx=0)
                canvas.left = left_coqueo
                canvas.right = right_coqueo
            else:
                canvas.grid(row=irow, column=0, sticky=tix.S)
                canvas.grid_configure(padx=self.panel_pad)
                canvas.left = left_coqueo
                canvas.right = right_coqueo
        else:
            canvas.grid(row=irow, column=0, sticky=tix.S)
            # canvas.grid_configure(padx=self.panel_pad)
            canvas.left = left_coqueo
            canvas.right = right_coqueo
        ########################
        canvas.row = irow
        canvas.freq_click = 0
        try:
            canvas.minute1_value = dragged_canvas.minute1_value
        except:
            canvas.minute1_value = ''
        try:
            canvas.minute2_value = dragged_canvas.minute2_value
        except:
            canvas.minute2_value = ''
        try:
            canvas.minute3_value = dragged_canvas.minute3_value
        except:
            canvas.minute3_value = ''
        try:
            canvas.minute4_value = dragged_canvas.minute4_value
        except:
            canvas.minute4_value = ''
        try:
            canvas.minute5_value = dragged_canvas.minute5_value
        except:
            canvas.minute5_value = ''
        try:
            canvas.minute6_value = dragged_canvas.minute6_value
        except:
            canvas.minute6_value = ''
        try:
            canvas.minute7_value = dragged_canvas.minute7_value
        except:
            canvas.minute7_value = ''
        try:
            canvas.minute8_value = dragged_canvas.minute8_value
        except:
            canvas.minute8_value = ''
        try:
            canvas.minute9_value = dragged_canvas.minute9_value
        except:
            canvas.minute9_value = ''
        # Draw the strip
        canvas.create_line(0, 30, 360, 30)
        canvas.create_line(0, 60, 700, 60)
        canvas.create_line(160, 0, 160, 60)
        canvas.create_line(110, 30, 110, 60)
        canvas.create_line(210, 0, 210, 60)
        canvas.create_line(260, 0, 260, 60)
        canvas.create_line(310, 0, 310, 60)
        canvas.create_line(360, 0, 360, 60)
        # canvas.create_line(160, 45, 160, 45)
        canvas.create_line(235, 30, 235, 60)
        canvas.create_line(285, 30, 285, 60)
        canvas.create_line(335, 30, 335, 60)
        canvas.create_line(160, 45, 210, 45)
        canvas.create_line(500, 0, 500, 20)
        canvas.create_line(500, 20, 700, 20)
        # Insert the text
        canvas.callsign = callsign
        canvas.zone = zone
        canvas.create_text(4, 6, anchor="nw", text=callsign, font="Courier 16")
        canvas.create_text(4, 6, anchor="nw", text=callsign, font="Courier 16")
        canvas.create_text(4, 6, anchor="nw", text=callsign, font="Courier 16")
        canvas.create_text(4, 30, anchor="nw", text=type_txt, font="Courier 10")
        adep = f.adep
        adep = self._alias_ad(adep)  # parametro 'alias_ads'
        ades = f.ades
        ades = self._alias_ad(ades)  # parametro 'alias_ads'
        if f.adep in self._local_ads():
            eobt = '%02d:%02d' % (f.eobt.hour, f.eobt.minute)
            canvas.create_text(4, 45, anchor="nw", text=adep + '/' + eobt + ' ' + ades + '/' + ecl, font="Courier 7")
        else:
            canvas.create_text(4, 45, anchor="nw", text=adep+'/     ' + ades + '/'+ecl, font="Courier 7")
        canvas.create_text(4, 60, anchor="nw", text=f.fp_route, font="Courier 10")
        canvas.create_text(168, 45, anchor="nw", text=f.squawk, font="Courier 10")
        if f.ades in self._local_ads():
            canvas.create_text(200, 6, anchor="nw", text=park, font="Courier 12")
        elif f.adep in self._local_ads():  # Se incluye tambien el parking en los vuelos que sean salidas (Peticion de LEMH)
            canvas.create_text(200, 6, anchor="nw", text=park, font="Courier 12")
        canvas.create_text(480, 60, anchor="nw", text=print_time_txt, font="Courier 10")
        canvas.create_text(450, 6, anchor="nw",text=cfl, font="Courier 10")
        if f.adep in self._local_ads():
            canvas.create_text(364, 6, anchor="nw", text=f.stand_sid_atc, font="Courier 10")
        elif f.ades in self._local_ads():
            canvas.create_text(263, 6, anchor="nw", text=f.iaf, font="Courier 10")
            canvas.create_text(263, 36, anchor="nw", text=estimated_t, font="Courier 12")
            try:
                # May fail for a traffic returning to the field
                canvas.create_text(364, 6, anchor="nw", text=f.star.txt_desig, font="Courier 10")
            except:
                pass
        self.fs_added.append(f.callsign)
        # Leaving CFL
        canvas.cfl = cfl
        canvas.cfl_leave = cfl_leave_check
        if cfl_leave_check:
            cfl_leave = self.cfl_leaved
            canvas.create_rectangle(450, 20, 480, 40, fill='white', outline='white')
            canvas.create_text(450, 20, anchor="nw", text=cfl_leave, font="Courier 10")
            canvas.create_line(450, 28, 470, 28)
        # Create the windows of action in each label
        # Bcheck
        canvas.Bcheck = Bcheck
        if Bcheck:
            canvas.create_text(420, 6, anchor="nw", text='B', font="Courier 16", fill="red")
        else:
            canvas.create_rectangle(419, 2, 450, 25, fill=color, outline=color)
        canvas.freeText = freeText
        canvas.delete('freeText')
        canvas.create_text(self.ficha_w10 + 2, self.ficha_h2 + 2, anchor="nw", text=canvas.freeText, font="Courier 15",
                           tag='freeText')
        # TRASPONDEDOR
        canvas.trasponder = trasponder_check
        if trasponder_check:
            canvas.create_line(199, 52, 203, 58, fill='black', width=2)
            canvas.create_line(203, 58, 209, 46, fill='black', width=2)
        else:
            canvas.create_rectangle(199, 46, 209, 58, fill=color, outline=color)
            # QNH
        qnh = int(self.radisplay.giw._qnh)
        canvas.qnh = qnh_check
        if qnh_check:
            canvas.create_text(163, 6, anchor="nw", text=qnh, font="Courier 12")
        else:
            canvas.create_text(163, 6, anchor="nw", text='', font="Courier 12")
        # RWY
        canvas.rwy = rwy_check
        if rwy_check:
            canvas.create_text(114, 6, anchor="nw", text='RWY'+rwy_txt, font="Courier 10")
        else:
            canvas.create_text(114, 6, anchor="nw", text='', font="Courier 12")
            # MINUTE 1
        canvas.minute = minute_check
        if minute_check:
            canvas.create_text(120, 36, anchor="nw", text=dragged_canvas.minute1_value,font="Courier 12")
        else:
            canvas.create_text(120, 36, anchor="nw", text='', font="Courier 12")
            # MINUTE 2
        canvas.minute2 = minute2_check
        if minute2_check:
            canvas.create_text(335, 6, anchor="nw", text=dragged_canvas.minute2_value, font="Courier 12")
        else:
            canvas.create_text(335, 6, anchor="nw", text='', font="Courier 12")
            # MINUTE 3
        canvas.minute3 = minute3_check
        if minute3_check:
            canvas.create_text(210, 36, anchor="nw", text=dragged_canvas.minute3_value, font="Courier 12")
        else:
            canvas.create_text(210, 36, anchor="nw", text='', font="Courier 12")
            # MINUTE 4
        canvas.minute4 = minute4_check
        if minute4_check:
            canvas.create_text(235, 36, anchor="nw", text=dragged_canvas.minute4_value, font="Courier 12")
        else:
            canvas.create_text(235, 36, anchor="nw", text='', font="Courier 12")
            # MINUTE 5
        canvas.minute5 = minute5_check
        if minute5_check:
            canvas.create_text(501, 4, anchor="nw", text=dragged_canvas.minute5_value, font="Courier 12")
        else:
            canvas.create_text(501, 4, anchor="nw", text='', font="Courier 12")
            # MINUTE 6
        canvas.minute6 = minute6_check
        if minute6_check:
            canvas.create_text(285, 36, anchor="nw", text=dragged_canvas.minute6_value, font="Courier 12")
        else:
            canvas.create_text(285, 36, anchor="nw", text='', font="Courier 12")
            # MINUTE 7
        canvas.minute7 = minute7_check
        if minute7_check:
            canvas.create_text(310, 36, anchor="nw", text=dragged_canvas.minute7_value, font="Courier 12")
        else:
            canvas.create_text(310, 36, anchor="nw", text='', font="Courier 12")
            # MINUTE 8
        canvas.minute8 = minute8_check
        if minute8_check:
            canvas.create_text(335, 36, anchor="nw", text=dragged_canvas.minute8_value, font="Courier 12")
        else:
            canvas.create_text(335, 36, anchor="nw", text='', font="Courier 12")
            # HOUR
        canvas.hour = hour_check
        if hour_check:
            canvas.create_text(310, 6, anchor="nw", text=hour, font="Courier 12")
        else:
            canvas.create_text(310, 6, anchor="nw", text='', font="Courier 12")
            # MINUTE 9
        canvas.minute9 = minute9_check
        if minute9_check:
            canvas.create_text(235, 6, anchor="nw", text=dragged_canvas.minute9_value, font="Courier 12")
        else:
            canvas.create_text(235, 6, anchor="nw", text='', font="Courier 12")
            # HOUR 2
        canvas.hour2 = hour2_check
        if hour2_check:
            canvas.create_text(210, 6, anchor="nw", text=hour, font="Courier 12")
        else:
            canvas.create_text(210, 6, anchor="nw", text='', font="Courier 12")
            # EMERGENCY
        canvas.emergency = emergency_check
        if emergency_check:
            canvas.create_text(450, 30, anchor="nw", text='W', font="Courier 18", fill="red")
        else:
            canvas.create_text(450, 30, anchor="nw", text=' ', font="Courier 18")
            # ILS
        canvas.ils = ils_check
        if ils_check:
            canvas.create_text(500, 20, anchor="nw", text='ILS', font="Courier 10")
        else:
            canvas.create_text(500, 20, anchor="nw", text='', font="Courier 10")
            # FREQUENCY
        canvas.freq = freq_check
        frequency_sequence = []
        for i in range(len(f.sector_sequence)):
            frequency = fir.frequency[f.sector_sequence[i]]
            frequency_sequence.append(frequency)
        if freq_check:
            canvas.freq_click += 1
            try:
                canvas.create_text(480, 40, anchor="nw", text=frequency_sequence[canvas.freq_click], font="Courier 10")
            except:
                canvas.create_text(480, 40, anchor="nw", text=frequency_sequence[len(f.sector_sequence)-1], font="Courier 10")
        else:
            canvas.create_text(480, 40, anchor="nw", text='', font="Courier 10")
        # Add a border deppending on departure/arrival colors
        canvas.update_idletasks()
        w_canvas, h_canvas = canvas.winfo_width(), canvas.winfo_height()
        if f.adep in self._local_ads():
            canvas.myborder = canvas.create_rectangle(0, 0, w_canvas-2, h_canvas-2, outline='blue', width=3)
        else:
            canvas.myborder = canvas.create_rectangle(0, 0, w_canvas-2, h_canvas-2, outline='yellow', width=3)
        # Se pone azul el borde de los despegues de Oporto para el escenario de LECG
        # (parametro 'ficha_borde_salida_ads'; antes condicionado a fir.name == 'LECG', que no existe)
        if f.adep in self.radisplay.fir.param('ficha_borde_salida_ads', []):
            canvas.myborder = canvas.create_rectangle(0, 0, w_canvas-2, h_canvas-2, outline='blue', width=3)
        # Detect click and functions
        ra_bind(self.radisplay, canvas, "<Button-3>", lambda event, callsign=callsign, canvas=canvas: self.rightclicked(event, callsign, canvas))
        ra_bind(self.radisplay, canvas, "<Button-1>", lambda event, f=f, canvas=canvas: self.leftclicked(event, f, canvas))

        external_canvas.config(scrollregion=external_canvas.bbox(tix.ALL))


    def leftclicked(self, event, f, canvas):
        radisp = self.radisplay
        sector = radisp.sector
        fir = radisp.fir
        callsign = '%9s' % (f.callsign)
        callsign = callsign.strip()
        try:
            for track in radisp.tracks:
                if track.cs == callsign: vt = track
            f=radisp._tracks_flights[vt]
            cfl = f.atc_cfl
        except: cfl = int(f.cfl)
        if f.adep in self._local_ads():
            rwy_txt = f.deprwy
            rwy_txt = self._rwy_txt_config(f.adep, rwy_txt, 0)  # parametro 'ficha_pistas_config' (antes Barcelona)
        elif f.ades in self._local_ads():
            rwy_txt = f.desrwy
            rwy_txt = self._rwy_txt_config(f.ades, rwy_txt, 1)  # parametro 'ficha_pistas_config' (antes Barcelona)
        else:
            rwy_txt = f.desrwy
        qnh = int(self.radisplay.giw._qnh)
        x = event.x
        y = event.y
        time = '%10s' % (self.radisplay.t)
        minute = time[14:16]
        hour = time[11:13]
        second = time[17:19]
        if int(second) > 29:
            minute = '%02d' % (int(minute)+1)
            if int(minute) > 59:
                minute = '00'
                hour = '%02d' % (int(hour)+1)
                if int(hour) > 23:
                    hour = '00'
        if x >= 110 and x <= 160 and y >= 0 and y <= 30:  # rwy region
            if canvas.rwy:
                canvas.create_rectangle(114, 6, 158, 28, fill='white', outline='white')
                canvas.rwy = False
            else:
                canvas.rwy = True
                canvas.create_rectangle(114, 6, 158, 28, fill='white', outline='white')
                canvas.create_text(114, 6, anchor="nw", text='RWY'+rwy_txt, font="Courier 10")
        elif x >= 425 and x <= 500 and y >= 0 and y <= 30:  # cfl region
            self.openkeyboard(canvas, event)
        elif x >= 400 and x <= 450 and y >= 30:  # free text region
            self.openFreeTextKeyboard(canvas, event)
        elif x >= 350 and x <= 420 and y >= 0 and y <= 30:  # B trasponder check
            if not canvas.Bcheck:
                canvas.Bcheck = True
                canvas.create_text(420, 3, anchor="nw", text='B', font="Courier 16", fill="red")
            else:
                canvas.Bcheck = False
                canvas.create_rectangle(419, 2, 450, 25, fill='white', outline='white')
        elif x >= 160 and x <= 210 and y >= 0 and y <= 30:  # qnh region
            if canvas.qnh:
                canvas.create_rectangle(163, 6, 208, 28, fill='white', outline='white')
                canvas.qnh = False
            else:
                canvas.qnh = True
                canvas.create_rectangle(163, 6, 208, 28, fill='white', outline='white')
                canvas.create_text(163, 6, anchor="nw", text=qnh, font="Courier 12")
        elif x >= 160 and x <= 210 and y >= 45 and y <= 60:
            if canvas.trasponder:
                canvas.create_rectangle(199, 46, 209, 58, fill='white', outline='white')
                canvas.trasponder = False
            else:
                canvas.create_line(199, 52, 203, 58, fill='black', width=2)
                canvas.create_line(203, 58, 209, 46, fill='black', width=2)
                canvas.trasponder = True

        elif x >= 110 and x <= 160 and y <= 60 and y >= 30:  # minute_1
            if canvas.minute:
                canvas.create_rectangle(120, 36, 150, 50, fill='white', outline='white')
                canvas.minute = False
            else:
                canvas.minute = True
                try:
                    canvas.minute1_value = minute
                except:
                    canvas.minute1_value = ''
                canvas.create_rectangle(120, 36, 150, 50, fill='white', outline='white')
                canvas.create_text(120, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 335 and x <= 360 and y >= 0 and y <= 30:  # minute_2
            if canvas.minute2:
                canvas.create_rectangle(336, 6, 358, 28, fill='white', outline='white')
                canvas.minute2 = False
            else:
                canvas.minute2 = True
                canvas.minute2_value = minute
                canvas.create_rectangle(336, 6, 350, 28, fill='white', outline='white')
                canvas.create_text(336, 6, anchor="nw", text=minute, font="Courier 12")
        elif x >= 210 and x <= 235 and y >= 30 and y <= 60:  # minute_3
            if canvas.minute3:
                canvas.create_rectangle(211, 36, 230, 58, fill='white', outline='white')
                canvas.minute3 = False
            else:
                canvas.minute3 = True
                canvas.minute3_value = minute
                canvas.create_text(211, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 235 and x <= 260 and y >= 30 and y <= 60:  # minute_4
            if canvas.minute4:
                canvas.create_rectangle(236, 36, 258, 58, fill='white', outline='white')
                canvas.minute4 = False
            else:
                canvas.minute4 = True
                canvas.minute4_value = minute
                canvas.create_text(236, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 500 and x <= 560 and y >= 0 and y <= 20:  # minute_5
            if canvas.minute5:
                canvas.create_rectangle(501, 4, 520, 18, fill='white', outline='white')
                canvas.minute5 = False
            else:
                canvas.minute5 = True
                canvas.minute5_value = minute
                canvas.create_text(501, 4, anchor="nw", text=minute, font="Courier 12")
        elif x >= 285 and x <= 310 and y >= 30 and y <= 60:  # minute_6
            if canvas.minute6:
                canvas.create_rectangle(286, 36, 308, 58, fill='white', outline='white')
                canvas.minute6 = False
            else:
                canvas.minute6 = True
                canvas.minute6_value = minute
                canvas.create_text(286, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 310 and x <= 335 and y >= 30 and y <= 60:  # minute_7
            if canvas.minute7:
                canvas.create_rectangle(311, 36, 333, 58, fill='white', outline='white')
                canvas.minute7 = False
            else:
                canvas.minute7 = True
                canvas.minute7_value = minute
                canvas.create_text(310, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 335 and x <= 360 and y >= 30 and y <= 60:  # minute_8
            if canvas.minute8:
                canvas.create_rectangle(336, 37, 358, 58, fill='white', outline='white')
                canvas.minute8 = False
            else:
                canvas.minute8 = True
                canvas.minute8_value = minute
                canvas.create_text(335, 36, anchor="nw", text=minute, font="Courier 12")
        elif x >= 310 and x <= 335 and y >= 0 and y <= 30:  # hour
            if canvas.hour:
                canvas.create_rectangle(311, 6, 333, 28, fill='white', outline='white')
                canvas.hour = False
            else:
                canvas.hour = True
                canvas.create_text(311, 6, anchor="nw", text=hour, font="Courier 12")
        elif x >= 235 and x <= 260 and y >= 0 and y <= 30:  # minute_9
            if canvas.minute9:
                canvas.create_rectangle(236, 6, 258, 28, fill='white', outline='white')
                canvas.minute9 = False
            else:
                canvas.minute9 = True
                canvas.minute9_value = minute
                canvas.create_text(236, 6, anchor="nw", text=minute, font="Courier 12")
        elif x >= 210 and x <= 235 and y >= 0 and y <= 30:  # hour_2
            if canvas.hour2:
                canvas.create_rectangle(211, 6, 233, 28, fill='white', outline='white')
                canvas.hour2 = False
            else:
                canvas.hour2 = True
                canvas.create_text(211, 6, anchor="nw", text=hour, font="Courier 12")
        elif x >= 500 and x <= 560 and y >= 20 and y <= 40:  # ILS
            if f.ades in self._local_ads() and f.adep != 'LPPR':
                canvas.ils = True
                canvas.create_text(500, 20, anchor="nw", text='ILS', font="Courier 10")
        elif x >= 450 and x <= 500 and y >= 30 and y <= 60:  # emergency
            if not canvas.emergency:
                canvas.emergency = True
                canvas.create_text(450, 30, anchor="nw", text='W', font="Courier 18", fill="red")
            else:
                canvas.emergency = False
                canvas.create_rectangle(450, 30, 480, 50, fill='white', outline='white')
        elif x >= 500 and x <= 560 and y >= 40 and y <= 60:  # frequency
            if not fir.param('ficha_freq_teclado', False):  # antes escenario != 'LECG'
                canvas.create_rectangle(480, 40, 534, 59, fill='white', outline='white')
                frequency_sequence = []
                for i in range(len(f.sector_sequence)):
                    frequency = fir.frequency[f.sector_sequence[i]]
                    frequency_sequence.append(frequency)
                canvas.freq = True
                canvas.freq_click += 1
                try:
                    canvas.create_text(480, 40, anchor="nw", text=frequency_sequence[canvas.freq_click], font="Courier 10")
                except:
                    canvas.create_text(480, 40, anchor="nw", text=frequency_sequence[len(f.sector_sequence)-1], font="Courier 10")
            else:
                self.openkeyboard_frequency(canvas=canvas, event=event)
        elif x >= 0 and x <= 110 and y >= 0 and y <= 60:
            self.rightclicked(event, callsign, canvas)
            ra_bind(self.radisplay, canvas, "<B1-Motion>", self.drag)
            ra_bind(self.radisplay, canvas, "<ButtonRelease-1>", self.drop)

    def openkeyboard_frequency(self, canvas, event):
        def write0(frequency_text):
            frequency_text.set(frequency_text.get()+'0')

        def write1(frequency_text):
            frequency_text.set(frequency_text.get()+'1')

        def write2(frequency_text):
            frequency_text.set(frequency_text.get()+'2')

        def write3(frequency_text):
            frequency_text.set(frequency_text.get()+'3')

        def write4(frequency_text):
            frequency_text.set(frequency_text.get()+'4')

        def write5(frequency_text):
            frequency_text.set(frequency_text.get()+'5')

        def write6(frequency_text):
            frequency_text.set(frequency_text.get()+'6')

        def write7(frequency_text):
            frequency_text.set(frequency_text.get()+'7')

        def write8(frequency_text):
            frequency_text.set(frequency_text.get()+'8')

        def write9(frequency_text):
            frequency_text.set(frequency_text.get()+'9')

        def writedot(frequency_text):
            frequency_text.set(frequency_text.get()+'.')

        def insert_frequency(frequency_text):
            frequency_text = frequency_text.get()
            root.destroy()
            canvas.create_rectangle(480, 40, 534, 59, fill='white', outline='white')
            canvas.create_text(480, 40, anchor="nw", text=frequency_text, font="Courier 10")

        def delete(frequency_text):
            i = len(frequency_text.get())
            frequency_text.set(frequency_text.get()[0:i-1])
        frequency_text = tix.StringVar()
        frequency_text.set('')
        root = tix.Toplevel()
        root.configure(background='gray36')
        root.title(canvas.callsign + 'Keyboard')
        root.geometry('%dx%d+%d+%d' % (244, 267, event.x_root-244, event.y_root-267))
        button_dot = tix.Button(root, text='.', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: writedot(frequency_text))
        button_dot.grid(column=2, row=4)
        button_enter = tix.Button(root, text='Enter', font="Courier 10", fg='white', bg='gray36', pady=40, padx=10, command=lambda: insert_frequency(frequency_text))
        button_enter.grid(column=3, row=3, rowspan=2)
        button_delete = tix.Button(root, text='Delete', font="Courier 10", fg='white', bg='gray36', pady=40, padx=5, command=lambda: delete(frequency_text))
        button_delete.grid(column=3, row=1, rowspan=2)
        button0 = tix.Button(root, text='0', font="Courier 20", fg='white', bg='gray36', padx=39, command=lambda: write0(frequency_text))
        button0.grid(columnspan=2, row=4)
        button1 = tix.Button(root, text='1', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write1(frequency_text))
        button1.grid(column=0, row=3)
        button2 = tix.Button(root, text='2', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write2(frequency_text))
        button2.grid(column=1, row=3)
        button3 = tix.Button(root, text='3', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write3(frequency_text))
        button3.grid(column=2, row=3)
        button4 = tix.Button(root, text='4', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write4(frequency_text))
        button4.grid(column=0, row=2)
        button5 = tix.Button(root, text='5', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write5(frequency_text))
        button5.grid(column=1, row=2)
        button6 = tix.Button(root, text='6', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write6(frequency_text))
        button6.grid(column=2, row=2)
        button7 = tix.Button(root, text='7', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write7(frequency_text))
        button7.grid(column=0, row=1)
        button8 = tix.Button(root, text='8', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write8(frequency_text))
        button8.grid(column=1, row=1)
        button9 = tix.Button(root, text='9', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write9(frequency_text))
        button9.grid(column=2, row=1)
        screen = tix.Entry(root, textvariable=frequency_text, width=15, font='Courier20')
        screen.grid(columnspan=4, row=0)
    #############################################################################################################

    def openkeyboard(self, canvas, event):

        def write0(cfl_text):
            cfl_text.set(cfl_text.get()+'0')

        def write1(cfl_text):
            cfl_text.set(cfl_text.get()+'1')

        def write2(cfl_text):
            cfl_text.set(cfl_text.get()+'2')

        def write3(cfl_text):
            cfl_text.set(cfl_text.get()+'3')

        def write4(cfl_text):
            cfl_text.set(cfl_text.get()+'4')

        def write5(cfl_text):
            cfl_text.set(cfl_text.get()+'5')

        def write6(cfl_text):
            cfl_text.set(cfl_text.get()+'6')

        def write7(cfl_text):
            cfl_text.set(cfl_text.get()+'7')

        def write8(cfl_text):
            cfl_text.set(cfl_text.get()+'8')

        def write9(cfl_text):
            cfl_text.set(cfl_text.get()+'9')

        def writedot(cfl_text):
            cfl_text.set(cfl_text.get()+'.')

        def insert_cfl(cfl_text):
            cfl_text = cfl_text.get()
            root.destroy()
            self.update_cfl(callsign=canvas.callsign, cfl=cfl_text)

        def delete(cfl_text):
            i = len(cfl_text.get())
            cfl_text.set(cfl_text.get()[0:i-1])

        def leave_cfl(cfl_text):
            root.destroy()
            canvas.create_rectangle(450, 20, 480, 40, fill='white', outline='white')
            canvas.create_text(450, 20, anchor="nw", text=cfl_text.get(), font="Courier 10")
            canvas.create_line(450, 28, 470, 28)
            self.cfl_leaved = cfl_text.get()
            canvas.cfl_leave = True
            self.update_cfl(callsign=canvas.callsign, cfl=canvas.cfl)
        cfl_text = tix.StringVar()
        cfl_text.set('')
        root = tix.Toplevel()
        root.configure(background='gray36')
        root.title(canvas.callsign + 'Keyboard')
        root.geometry('%dx%d+%d+%d' % (244, 267, event.x_root-244, event.y_root-267))
        button_dot = tix.Button(root, text='.', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: writedot(cfl_text))
        button_dot.grid(column=2, row=4)
        button_enter = tix.Button(root, text='Clear', font="Courier 10", fg='white', bg='gray36', pady=40, padx=10, command=lambda: insert_cfl(cfl_text))
        button_enter.grid(column=3, row=3, rowspan=2)
        button_leaving = tix.Button(root, text='Leaving', font="Courier 10", fg='white', bg='gray36', pady=40, command=lambda: leave_cfl(cfl_text))
        button_leaving.grid(column=3, row=1, rowspan=2)
        button_delete = tix.Button(root, text='Delete', font="Courier 10", fg='white', bg='gray36', pady=15, padx=5, command=lambda: delete(cfl_text))
        button_delete.grid(column=3, row=0)
        button0 = tix.Button(root, text='0', font="Courier 20", fg='white', bg='gray36', padx=39, command=lambda: write0(cfl_text))
        button0.grid(columnspan=2, row=4)
        button1 = tix.Button(root, text='1', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write1(cfl_text))
        button1.grid(column=0, row=3)
        button2 = tix.Button(root, text='2', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write2(cfl_text))
        button2.grid(column=1, row=3)
        button3 = tix.Button(root, text='3', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write3(cfl_text))
        button3.grid(column=2, row=3)
        button4 = tix.Button(root, text='4', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write4(cfl_text))
        button4.grid(column=0, row=2)
        button5 = tix.Button(root, text='5', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write5(cfl_text))
        button5.grid(column=1, row=2)
        button6 = tix.Button(root, text='6', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write6(cfl_text))
        button6.grid(column=2, row=2)
        button7 = tix.Button(root, text='7', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write7(cfl_text))
        button7.grid(column=0, row=1)
        button8 = tix.Button(root, text='8', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write8(cfl_text))
        button8.grid(column=1, row=1)
        button9 = tix.Button(root, text='9', font="Courier 20", fg='white', bg='gray36', padx=10, command=lambda: write9(cfl_text))
        button9.grid(column=2, row=1)
        screen = tix.Entry(root, textvariable=cfl_text, width=15, font='Courier20')
        screen.grid(columnspan=3, row=0)

    def openFreeTextKeyboard(self, canvas, event):
        myKeys = ['1234567890<>',
                  'QWERTYUIOP+-',
                  'ASDFGHJKL\/',
                  'ZXCVBNM,.']
        # kb = tix.Toplevel()
        kb = tix.Toplevel()
        kb.configure(background='gray10')
        kb.title(canvas.callsign + 'Keyboard')
        kb.geometry('+%d+%d' % (event.x_root - 244, event.y_root - 267))
        kbEntry = tix.Entry(kb, font='Courier20')
        kbEntry.grid(columnspan=14, row=0)
        kbEntry.insert(0, canvas.freeText)
        varRow = 0
        for myLine in myKeys:
            varRow += 1
            varColumn = 0
            for myKey in myLine:
                command = lambda x=myKey: select(x)
                tix.Button(kb, text=myKey, width=4, bg="white", fg="black",
                        activebackground="black", activeforeground="white", relief='raised', padx=1,
                        pady=1, bd=1, command=command).grid(row=varRow, column=varColumn)
                varColumn += 1
        command = lambda x=myKey: select('Espacio')
        tix.Button(kb, text='', width=4, bg="white", fg="black",
                activebackground="black", activeforeground="white", relief='raised', padx=1,
                pady=1, bd=1, command=command).grid(row=6, column=3, columnspan=6, sticky=tix.W+tix.E+tix.N+tix.S)
        command = lambda x=myKey: select('Supr')
        tix.Button(kb, text='Supr', width=4, bg="white", fg="black",
                activebackground="black", activeforeground="white", relief='raised', padx=1,
                pady=1, bd=1, command=command).grid(row=1, column=12, columnspan=2, sticky=tix.W+tix.E+tix.N+tix.S)
        command = lambda x=myKey: select('Borrar')
        tix.Button(kb, text='Borrar', width=4, bg="white", fg="black",
                activebackground="black", activeforeground="white", relief='raised', padx=1,
                pady=1, bd=1, command=command).grid(row=2, column=12, columnspan=2, sticky=tix.W+tix.E+tix.N+tix.S)
        command = lambda x=myKey: select('Entrar')
        tix.Button(kb, text='Entrar', width=4, bg="white", fg="black",
                activebackground="black", activeforeground="white", relief='raised', padx=1,
                pady=1, bd=1, command=command).grid(row=3, column=11, rowspan=2, columnspan=3, sticky=tix.W+tix.E+tix.N+tix.S)

        def select(value):
            curIndex = kbEntry.index(tix.INSERT)
            if value == 'Entrar':
                canvas.freeText = kbEntry.get()
                canvas.delete('freeText')
                canvas.create_text(self.ficha_w9+2, self.ficha_h2+2, anchor="nw", text=canvas.freeText, font="Courier 15", tag='freeText')
                kb.destroy()
            elif value == 'Borrar':
                kbEntry.delete(curIndex-1, curIndex)
            elif value == 'Supr':
                kbEntry.delete(curIndex, curIndex+1)
            elif value == 'Espacio':
                kbEntry.insert(curIndex, ' ')
            else:
                kbEntry.insert(curIndex, value)

    def rightclicked(self, event, callsign, canvas):
        ra_bind(self.radisplay, canvas, "<B3-Motion>", self.drag)
        ra_bind(self.radisplay, canvas, "<ButtonRelease-3>", self.drop)
        if callsign is not None:
            radisp = self.radisplay
            for track in radisp.tracks:
                if track.cs == callsign:
                    vt = track
            f = radisp._tracks_flights[vt]
            self.dragged_canvas = canvas
            self.dropping_canvas = None
            self.dragged_f = f

            color = 'gray'
            canvas, zone_str, row = self.canvas_by_coords(event.x_root, event.y_root)
            if canvas is not None and canvas != self.dropping_canvas:
                f = self.dragged_f
                if f != 'fijo':
                    self.remove_fs(f)
                    self.insertar_ficha(f, zone_str=zone_str, insert_row=row, color=color, dragged_canvas=canvas)
        else:
            f = canvas.name
            self.dragged_canvas = canvas  # We are removing an obstacle strip
            self.dropping_canvas = None
            self.dragged_f = f

    def drag(self, event):
        color = 'gray'
        canvas, zone_str, row = self.canvas_by_coords(event.x_root, event.y_root)
        if canvas is not None and canvas != self.dropping_canvas:
            self.dropping_canvas = canvas
            f = self.dragged_f
            if f != 'fijo':
                self.remove_fs(f)
                self.insertar_ficha(f, zone_str=zone_str, insert_row=row, color=color, dragged_canvas=self.dragged_canvas)
            else:
                self.remove_fijo(f)
                self.insert_fijo(f, zone_str=zone_str, insert_row=row, color=color)

    def drop(self, event):
        canvas, zone_str, row = self.canvas_by_coords(event.x_root, event.y_root)
        if canvas is not None and canvas != self.dragged_canvas:
            # remove dragged frame from previous position and insert in the corresponding zone and row
            f = self.dragged_f
            if f != 'fijo':   # Si se trata de la fiha de un vuelo y no de un fijo
                self.remove_fs(f)
                dragged_canvas = self.dragged_canvas
                if zone_str != 'delete':
                    self.insertar_ficha(f, zone_str=zone_str, insert_row=row, dragged_canvas=dragged_canvas)
            else:  # Si se trata de un fijo y no de la ficha de un vuelo
                self.remove_fijo(f)
                if zone_str != 'delete':
                    self.insert_fijo(f, zone_str=zone_str, insert_row=row)
                else:
                    self.fijos_added.remove(f)

        elif canvas is None:
            f = self.dragged_f
            if f != 'fijo':
                self.remove_fs(f)
                dragged_canvas = self.dragged_canvas
                if zone_str != 'delete':
                    self.insertar_ficha(f, zone_str=zone_str, insert_row=0, dragged_canvas=dragged_canvas)
            else:
                self.remove_fijo(f)
                if zone_str != 'delete':
                    self.insert_fijo(f, zone_str=zone_str, insert_row=row)

    def canvas_by_coords(self, x_root, y_root):
        irow_found = None
        zone = None
        x_root = x_root-self.winfo_x()
        y_root = y_root-self.winfo_y()
        x1 = self.left_panel.winfo_width()
        x2 = x1 + self.centre_panel.winfo_width()
        x3 = x2 + self.right_panel.winfo_width()
        if x_root <= x1:
            zone = self.framein_left
            zone_str = 'left'
        elif x_root > x1 and x_root <= x2:
            zone = self.framein_centre
            zone_str = 'centre'
        elif x_root > x2 and x_root <= x3:
            zone = self.framein_right
            zone_str = 'right'
        elif x_root > x3:
            zone = self.delete_frame
            zone_str = 'delete'
        gsize = zone.grid_size()
        nrows = gsize[1]
        ncols = gsize[0]
        for irow in range(nrows):
            canvas = zone.grid_slaves(row=irow, column=0)[0]
            if y_root > canvas.winfo_rooty() - self.winfo_y() and y_root < canvas.winfo_rooty() - self.winfo_y() + canvas.winfo_height():
                irow_found = irow
                break
            # if irow_found is not None: break
        if irow_found is None:
            canvas = None
        return canvas, zone_str, irow_found


class RaTabular(RaFrame):
    """Generic frame containing tabular info"""

    def __init__(self, master, **kw):
        def_opt = {'position': (500, 222), }
        def_opt.update(kw)
        self._items = []  # We need to make a copy of the items to rebuild
                        # the list
        # The frame constructor method will call _build
        self.elements = tix.IntVar()
        self.entry = None
        self.min_width = 0
        self.max_width = 0
        self.min_height = 0
        self.max_height = 0
        RaFrame.__init__(self, master=master, **def_opt)

    def _build(self, master=None, windowed=False, **kw):
        # import Tix
        RaFrame._build(self, master=master, windowed=windowed, **kw)
        self.n_elementos = tix.Label(self.windowtitle, bg=self.bd, foreground=self.fg, font=("Arial", "12", "bold"), textvariable=self.elements, relief=tix.GROOVE, borderwidth=2)
        self.n_elementos.pack(side=tix.RIGHT, padx=0, ipadx=4)
        self.legend = tix.Label(self.contents, font="Courier 12", bg=self.bg, fg=self.fg, height=0)
        self.legend.pack(padx=7, side=tix.TOP, anchor=tix.NW)

        self._slist = tix.ScrolledListBox(self.contents, relief=tix.FLAT, borderwidth=0, highlightthickness=0)
        self._list_colors = {'background': self.bg,
                            'highlightbackground': self.bg,
                            'highlightcolor': self.bg,
                            'foreground': '#bdbdbd',
                            'selectbackground': self.bg,
                            'selectforeground': 'green'}
        # The widget listbox is "encapsulated" by ScrolledListBox
        self.list = self._slist.listbox
        self.list.configure(**self._list_colors)
        self.list.configure(relief=tix.FLAT,)
        # self.list.configure(height=6, width=30)
        self._scroll_bar_configuration = {'activebackground': self.bd,
                                        'borderwidth': 0,
                                        'width': 10,
                                        'activerelief': tix.FLAT,
                                        'troughcolor': self.bd,
                                        'elementborderwidth': 0,
                                        'background': self.bg}
        self._slist.hsb.configure(**self._scroll_bar_configuration)
        self._slist.vsb.configure(**self._scroll_bar_configuration)
        for i, elements in enumerate(self._items):
            self.list.insert(i, *elements)

        self._slist.pack(fill=tix.BOTH, expand=1, padx=5, pady=5)
        j=self.n_elementos.bind('<Button-1>', self.set_visible_rows, add="+")
        self._bindings.append((self.n_elementos, j, '<Button-1>'),)
        self.adjust()

    def set_visible_rows(self, e=None):
        """Show a dialog to allow the user to set the number of visible rows"""
        n_rows = tix.StringVar()
        frame_colors = {'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': self.bd}
        label_colors = {'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': self.bd,
                            'foreground': 'yellow',
                            'activebackground': self.bd,
                            'activeforeground': self.bd,
                            'activeforeground': self.bd,
                            'disabledforeground': '',
                            'anchor': tix.SE}
        button_colors = {'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': self.bd,
                            'foreground': self.fg,
                            'activebackground': self.bd,
                            'activeforeground': self.fg,
                            'disabledforeground': ''}
        entry_colors = {'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': self.bd,
                            'foreground': 'yellow',
                            'selectbackground': self.bd,
                            'selectforeground': 'yellow'}

        def set_rows(e=None, entries=None):
            try:
                self.max_height = int(n_rows.get())
                self.adjust(max_height=self.max_height)
            except:
                pass
            # self.visible_rows=int(n_rows.get())

        if self.entry is None:
            self.entry = tix.ComboBox(self.windowtitle, editable=True)
            self.entry.configure(bg=self.bd,
                                 relief=tix.GROOVE, borderwidth=0,
                                 height=5,
                                 width=6,
                                 command=set_rows)
            e_entry = self.entry.subwidget_list['entry']
            e_entry.configure(bg=self.bd,
                                   foreground=self.fg,
                                   font=("Arial", "7", "bold"),
                                   relief=tix.FLAT, width=2,
                                   bd=0,
                                   textvariable=n_rows,
                                   justify=tix.RIGHT)
            e_list = self.entry.subwidget_list['slistbox']
            e_list.configure(bg=self.bd,
                                   relief=tix.FLAT,width=3)
            scroll_bar_configuration = {'activebackground': self.bd,
                                'borderwidth': 0,
                                'width': 6,
                                'activerelief': tix.FLAT,
                                'bg': self.bd}
            e_list.vsb.configure(**self._scroll_bar_configuration)
            e_arrow = self.entry.subwidget_list['arrow']
            e_arrow.configure(bg=self.bd, bd=0, fg=self.fg, height=10)
            e_frame = self.entry.children['frame']
            e_frame.configure(bg=self.bd, bd=0)
            e_shell = self.entry.children['shell']
            e_shell.configure(bg=self.bd, bd=0)
            n_rows.set(str(self.max_height))

            for i in range(0, 21):
                self.entry.add_history(str(i))

            self.entry.entry.master['bg'] = self.bd
            self.entry.label.configure(**label_colors)
            self.entry.entry.configure(**entry_colors)
            self.entry.slistbox.configure(**frame_colors)
            self.entry.arrow.configure(**button_colors)
            self.entry.label.configure(font=(("Arial","7",)))
            self.entry.label.configure(text="MAX:")
            self.entry.pack(side=tix.RIGHT)

        else:
            self.entry.destroy()
            self.entry = None


        # self.entry_rows=tix.Entry(self.windowtitle,bg=self.bd,
        # x1=self.container.winfo_x()+self.container.winfo_width()/2
        # y1=self.container.winfo_y()+self.container.winfo_height()/2
        # entries=[]
        # entries.append({'label':'','width':5,'def_value':self.visible_rows})
        # RaDialog(self.canvas,position=(x1,y1),label='FILAS',ok_callback=set_rows,entries=entries)

    def insert(self, index, *elements):
        """Insert a list item (use text='text to show')"""
        self.list.insert(index, *elements)
        # TODO we should deal with more Tk constants here.
        if index == tix.END:
            index = len(self._items)
        self._items.insert(index, elements)
        self.elements.set(self.list.size())

    def delete(self, index):
        """Delete a list item"""
        self.list.delete(index)
        self.elements.set(self.list.size())


    def adjust(self,min_height=-1, min_width=-1, max_height=-1, max_width=-1):
        """Reduce the size of the list to the minimum that fits
        or whatever is given as parameters
        max_height = 0 means unlimited"""
        if min_height == -1:min_height = self.min_height
        else: self.min_height = min_height
        if min_width == -1:min_width = self.min_width
        else: self.min_width = min_width
        if max_height == -1:max_height = self.max_height
        else: self.max_height = max_height
        if max_width == -1: max_width = self.max_width
        else: self.max_width = max_width


        self.elements.set(self.list.size())
        items = self.list.get(0,tix.END)
        max_item_size = max([len(i) for i in items]+[0])
        if self.min_width == 0: mw = max_item_size
        else: mw = max(self.min_width, max_item_size)
        if self.min_height == 0: mh = self.list.size()
        else: mh = max(self.min_height, len(i))

        # mw = max((min([len(i) for i in items]+[0]),self.min_width))
        # mh = max((self.list.size(), self.min_height))
        if self.max_width != 0:
            if mw > self.max_width: mw = self.max_width

        if self.max_height != 0:
            if mh > self.max_height: mh = self.max_height
        # if mw>self.max_width and self.max_width != 0: mw = self.max_width
        # if mh>self.max_height and self.max_height != 0: mh= self.max_height
        self.list.configure(height=mh, width=mw)

    def close(self):
        RaTabular.conmuta()


class DepTabular(RaTabular):
    """A tabular window showing departure aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='DESPEGUES', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'PARK'+'  '+'ORIG'+' '+'DEST'+'  '+'EOBT '+' '+'CTOT'+'  '+'TIPO '+'SID     '+' CSSR'
        ra_bind(radisplay, self.list, "<Button-1>", self.clicked)
        ra_bind(radisplay, self.legend, "<Button-1>", self.legend_clicked)
        self.cs_ordered = True
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        self.deps = []

    def legend_clicked(self, e=None):
        self.cs_ordered = not self.cs_ordered
        self.update()

    def update(self):
        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        fir = self.master.fir

        self.deps = [f for f in self.master.flights
                     if f.pof == Aircraft.GROUND and not f.fr == 'VEH'
                     and (f.eobt-self.master.t) < datetime.timedelta(minutes=10)]
        if self.cs_ordered:
            self.deps.sort(lambda p, q: cmp(p.callsign, q.callsign))
        else:
            self.deps.sort(lambda p, q: cmp(p.eobt, q.eobt))

        i = 0
        for f in self.deps:
            eobt = '%02d:%02d'%(f.eobt.hour, f.eobt.minute)
            park = '%3s' % (f.park)
            try: sid = '%7s' % (f.sid.txt_desig)
            except: sid = '       '
            try: ctot = '%02d:%02d'%(f.ctot.hour, f.ctot.minute)
            except: ctot = '     '
            t =  ' '+f.callsign.ljust(9)+park.ljust(5)+' '+f.adep.ljust(4)+' '+f.ades.ljust(4)+' '+\
                ' '+eobt+' '+ctot+' '+f.type.ljust(4)+' '+sid.ljust(8)+' '+f.squawk.ljust(4)
            self.insert(i, t)
            # if self.mode == 'pp' and f.eobt < self.master.t and not f.auto_depart:
            if self.mode == 'pp' and f.eobt < self.master.t:
                self.list.itemconfig(i, background='green', foreground='black')
            else:
                track = self.master._flights_tracks[f]
                if self.mode == 'pp' and track.assumed:
                    self.list.itemconfig(i, foreground=track.color.get())
            i += 1

        if self.showed: self.adjust()

    def clicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        f = self.deps[index]
        # Change code to allow to override autodeparture and also depart before eobt
        # if dep.eobt < self.master.t and not dep.auto_depart and self.mode == 'pp':
        if self.mode == 'pp':
                x1 = self.container.winfo_x()+self.container.winfo_width()/2
                y1 = self.container.winfo_y()+self.container.winfo_height()/2
                self.depart_dialog(f)

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y<lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.deps[index]
        vt = self.master._flights_tracks[f]

        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            try: radisp.selected_track.selected = not radisp.selected_track.selected
            except: logging.debug("Unselecting previous selected track failed")
            if radisp.selected_track == vt:
                radisp.selected_track = None
                vt.selected = False
            else:
                radisp.selected_track = vt
                vt.selected = True

    def depart_dialog(self, dep):
        """Show a dialog to allow the user to define sid and initial level"""
        def depart(e=None, entries=None):
            ent_sid = entries['SID:']
            ent_cfl = entries['CFL:']
            sid = ent_sid['value']
            cfl = ent_cfl.get()
            fallo = False
            if cfl.isdigit():
                cfl = float(cfl)
            else:
                ent_cfl['bg'] = 'red'
                ent_cfl.focus_set()
                fallo = True
            # TODO this should really test the SID, and should show a
            # dropdown, but I'm leaving it like it is until
            # the aircraft object is redesigned
            if fallo:
                return False  # Validation failed

            self.master.sendMessage({"message": "depart",
                                "cs": dep.callsign, "sid": sid, "cfl": cfl, "pista": ad.rwy_in_use.txt_desig})

        # Build the GUI Dialog
        entries = []
        try:
            dep_sid = dep.sid.txt_desig
            ad = self.master.fir.aerodromes[dep.adep]
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig == dep.rdep:
                    rwy_in_use = rwy
            # sids = [ad.rwy_in_use.txt_desig]
            sids = [sid.txt_desig for sid in rwy_in_use.sid_dict.values()]


        except:
            logging.warning("No SIDs found for %s departing from %s" % (dep.callsign, dep.adep))
            sids = ''
            dep_sid = ''
        entries.append({'label': 'SID:', 'width': 5, 'values': sids, 'def_value': dep_sid})
        entries.append({'label': 'CFL:', 'width': 3,'def_value': int(dep.cfl)})
        x1 = self.container.winfo_x()+self.container.winfo_width()/2
        y1 = self.container.winfo_y()+self.container.winfo_height()/2
        RaDialog(self.canvas, label=dep.callsign+': Change SID',
                    ok_callback=depart, entries=entries, position=(x1, y1))


class CoorTabular(RaTabular):
    """A tabular window showing departure aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='DESPEGUES', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.sacta_mode = radisplay.fir.sacta_mode[radisplay.sector.split(',')[0]]
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'ORIG'+' '+'DEST'+' '+'EOBT '+' '+'CTOT'+'  '+'SID     '+' CSSR'
        ra_bind(radisplay, self.list, "<Button-1>", self.clicked)
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        self.deps = []

    def update(self):
        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        self.deps = [f for f in self.master.flights
                 if f.pof == Aircraft.GROUND and not f.fr == 'VEH'
                 and not f.preact and not f.act and not f.correlado
                 and (f.eobt-self.master.t) < datetime.timedelta(minutes=10)]

        self.deps.sort(lambda p, q: cmp(p.eobt, q.eobt))

        i = 0
        for f in self.deps:
            eobt = '%02d:%02d'%(f.eobt.hour, f.eobt.minute)
            try: sid = '%7s' % f.sid.txt_desig
            except: sid = '       '
            try:
                ctot = '%02d:%02d' % (f.ctot.hour, f.ctot.minute)
            except:
                ctot = '    '

            t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+\
                    f.ades.ljust(4)+' '+eobt+' '+ctot+' '+sid.ljust(8)+' '+f.squawk.ljust(5)
            self.insert(i, t)

            track = self.master._flights_tracks[f]
            if self.sacta_mode == 'UCS':
                if track.assumed:
                    self.list.itemconfig(i, foreground=track.color.get())
            else:
                self.list.itemconfig(i, foreground=track.color.get())

            i += 1

        if self.showed:
            self.adjust()

    def clicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        f = self.deps[index]
        if self.sacta_mode == 'UCS' and self.master.smrOn:
            f.correlado = True
            self.master.sendMessage({"message": "correlado", "cs": f.callsign, "correlado": f.correlado})
        else:
            f.preact = True
            self.master.sendMessage({"message": "preact", "cs": f.callsign, "preact": f.preact})

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.deps[index]

        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            radisp.toggle_select(f)


class PreactTabular(RaTabular):
    """A tabular window showing departure aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='PREACTIVOS', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.sacta_mode = radisplay.fir.sacta_mode[radisplay.sector.split(',')[0]]
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'ORIG'+' '+'DEST'+' '+'EOBT '+' '+'CTOT'+'  '+'SID    '+' '+'CSSR'
        ra_bind(radisplay, self.list, "<Button-1>", self.clicked)
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        self.deps = []

    def update(self):
        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        fir = self.master.fir

        if fir.param('activacion_manual_ads', []):  # parametro de escenario (por defecto LEGR en GRANADA)
            self.deps = [f for f in self.master.flights
                         if f.preact]
        else:
            self.deps = [f for f in self.master.flights
                         if f.pof == Aircraft.GROUND
                         and f.preact
                         and (f.eobt-self.master.t) < datetime.timedelta(minutes=10)]
        self.deps.sort(lambda p, q: cmp(p.eobt, q.eobt))

        i = 0
        for f in self.deps:
            eobt = '%02d:%02d'%(f.eobt.hour, f.eobt.minute)
            try: sid = '%7s' % f.sid.txt_desig
            except: sid = '       '
            try: ctot = '%02d:%02d' % (f.ctot.hour, f.ctot.minute)
            except: ctot = '    '
            t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+\
                    f.ades.ljust(4)+' '+eobt+' '+ctot+' '+sid.ljust(7)+' '+f.squawk.ljust(5)
            self.insert(i, t)

            track = self.master._flights_tracks[f]
            if self.sacta_mode == 'UCS':
                if track.assumed:
                    self.list.itemconfig(i, foreground=track.color.get())
            else:
                self.list.itemconfig(i, foreground=track.color.get())

            if self.mode == 'pp' and f.eobt < self.master.t:
                self.list.itemconfig(i, background='green', foreground='black')

            i += 1

        if self.showed: self.adjust()

    def clicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        f = self.deps[index]

        f.preact = False
        self.master.sendMessage({"message": "preact", "cs": f.callsign, "preact": f.preact})
        f.act = True
        self.master.sendMessage({"message": "act", "cs": f.callsign, "act": f.act})

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.deps[index]
        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            radisp.toggle_select(f)


class AlarmNoCorrTabular(RaTabular):
    """A tabular window showing alarm no correlated aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='atc', **kw):
        RaTabular.__init__(self, canvas, label='NO CORRELADOS', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.sacta_mode = radisplay.fir.sacta_mode[radisplay.sector.split(',')[0]]
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'C'+' '+'INDICATIV'+' '+'PREV'+' '+'ASIG'+'  '
        ra_bind(radisplay, self.list, "<Button-1>", self.clicked)
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        self.noCorr = []
        self.noCorrPass = []

    def update(self):
        self.list.delete(0, self.list.size())
        fir = self.master.fir
        if fir.sectors[0] in ('LEST TWR', 'LEST TMA'):
            self.noCorr = [f for f in self.master.flights
                           if f.pof == Aircraft.GROUND
                           and f.correlado and f not in self.noCorrPass]
        self.noCorr.sort(lambda p, q: cmp(p.eobt, q.eobt))
        i = 0
        for f in self.noCorr:
            t = '   '+f.callsign.ljust(9)+'     '+f.squawk
            self.insert(i, t)
            track = self.master._flights_tracks[f]
            if self.sacta_mode == 'UCS':
                if track.assumed:
                    self.list.itemconfig(i, foreground=track.color.get())
            else:
                self.list.itemconfig(i, foreground=track.color.get())
            i += 1
        if self.showed: self.adjust()

    def clicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y)<0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item

        # Se elimina el vuelo del tabular No Correlados cd hace el update
        f = self.noCorr[index]
        self.noCorrPass.append(f)

        f.preact = True
        self.master.sendMessage({"message": "preact", "cs": f.callsign, "preact": f.preact})


class ActTabular(RaTabular):
    """A tabular window showing departure aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='ACTIVOS', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.var1 = tix.IntVar()
        self.var2 = tix.IntVar()
        self.var3 = tix.IntVar()

        self.Sob_Checkbutton = tix.Checkbutton(self.windowtitle, text='SOB', bg=self.bd, fg=self.fg,
                                               selectcolor='#a8a240', borderwidth=0, highlightthickness=0, variable=self.var1)
        self.Arr_Checkbutton = tix.Checkbutton(self.windowtitle, text='ARR', bg=self.bd, fg=self.fg,
                                               selectcolor='#a8a240', borderwidth=0, highlightthickness=0, variable=self.var2)
        self.Des_Checkbutton = tix.Checkbutton(self.windowtitle, text='DEP', bg=self.bd, fg=self.fg,
                                               selectcolor='#a8a240', borderwidth=0, highlightthickness=0, variable=self.var3)

        self.Arr_Checkbutton.pack(side=tix.RIGHT)
        self.Des_Checkbutton.pack(side=tix.RIGHT)
        self.Sob_Checkbutton.pack(side=tix.RIGHT)

        self.var1.set(1)
        self.var2.set(1)
        self.var3.set(1)

        self.Sob_Checkbutton.bind("<Button-1>", self.Sob_Checkbutton.toggle())
        self.Des_Checkbutton.bind("<Button-1>", self.Des_Checkbutton.toggle())
        self.Arr_Checkbutton.bind("<Button-1>", self.Arr_Checkbutton.toggle())

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.sacta_mode = radisplay.fir.sacta_mode[radisplay.sector.split(',')[0]]
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'ORIG'+' '+'DEST'+' '+'HORA'+' '+'STAR/SID'+'  CSSR'
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        ra_bind(radisplay, self.legend, "<Button-1>", self.legend_clicked)
        self.cs_ordered = True
        ra_bind(radisplay, self.list, "<Button-1>", self.clicked)
        self.act = []

    def aircraft_type_filter(self, e=None):
        act_lst = []
        Sob = self.var1.get()
        Arr = self.var2.get()
        Dep = self.var3.get()
        f = False
        if Sob:
            type_lst = [f for f in self.act
                        if f.adep not in self.master.fir.aerodromes.keys() and f.ades not in self.master.fir.aerodromes.keys()]
            act_lst.append(type_lst)
            f = True
        if Dep:
            type_lst = [f for f in self.act if f.adep in self.master.fir.aerodromes.keys()]
            act_lst.append(type_lst)
            f = True
        if Arr:
            type_lst = [f for f in self.act if f.ades in self.master.fir.aerodromes.keys()]
            act_lst.append(type_lst)
            f = True

        if f:
            self.act = [f for lst in act_lst for f in lst]

    def legend_clicked(self, e=None):
        self.cs_ordered = not self.cs_ordered
        self.update()

    def update(self):
        def tryconvert(ptime, qtime):
            try:
                ord = cmp(ptime, qtime)
                return ord
            except:
                if ptime is None:
                    return -1
                else:
                    return 1

        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        fir = self.master.fir
        # Flights from LEGR have to be activated manually to simulate lack of radar coverage
        # (parametro de escenario 'activacion_manual_ads', por defecto LEGR en el escenario GRANADA)
        if fir.param('activacion_manual_ads', []):
            self.act = [f for f in self.master.flights
                        if f.act or f.adep not in fir.param('activacion_manual_ads', [])]
        else:
            if self.mode == 'pp':
                self.act = [f for f in self.master.flights
                             if f.pof in (Aircraft.FLYING, Aircraft.TAKEOFF)]
            else:
                self.act = [f for f in self.master.flights
                             if f.pof in (Aircraft.FLYING, Aircraft.LANDED, Aircraft.TAKEOFF) or (f.act and f.pof == Aircraft.GROUND)]

        if self.cs_ordered:
            self.act.sort(lambda p, q: cmp(p.callsign, q.callsign))
        else:
            self.act.sort(lambda p, q: tryconvert(p.hora, q.hora))

        self.aircraft_type_filter()

        if len(self.act) == 0:
            pass
        else:
            i = 0
            for f in self.act:

                try: proced = '%7s' % f.star.txt_desig
                except:
                    try: proced = '%7s' % f.sid.txt_desig
                    except:
                        proced = '       '

                if f.hora == '':
                    hora = '     '
                else:
                    hora = '%02d:%02d' % (f.hora.hour, f.hora.minute)

                t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+\
                    f.ades.ljust(4)+' '+hora+' '+proced.ljust(8)+' '+f.squawk.ljust(5)
                self.insert(i, t)

                track = self.master._flights_tracks[f]
                if self.mode == 'pp' and track.assumed:
                    self.list.itemconfig(i, foreground=track.color.get())
                elif self.mode in ['atc', 'atc-nocorrel']:
                    if self.sacta_mode == 'UCS':
                        if track.assumed:
                            self.list.itemconfig(i, foreground=track.color.get())
                    else:
                        self.list.itemconfig(i, foreground=track.color.get())
                else:
                    pass

                i += 1

        if self.showed: self.adjust()

    def clicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y<lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        act = self.act[index]
        # Change code to allow to override autodeparture and also depart before eobt
        # if dep.eobt < self.master.t and not dep.auto_depart and self.mode == 'pp':
        if self.mode == 'pp' and act.star is not None:
                x1 = self.container.winfo_x()+self.container.winfo_width()/2
                y1 = self.container.winfo_y()+self.container.winfo_height()/2
                self.star_dialog(act, index)

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.act[index]

        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            radisp.toggle_select(f)

    def star_dialog(self, act, index):
        # Show a dialog to allow the user change star
        def change_star(e=None, entries=None):
            ent_star = entries['STAR:']
            star = ent_star['value']
            self.master.sendMessage({"message":"change_star",
                                "cs":act.callsign, "star": star, "pista": rwy_in_use.txt_desig})
        # Build the GUI Dialog
        entries = []
        try:
            act_star = act.star.txt_desig
            ad = self.master.fir.aerodromes[act.ades]
            for rwy in ad.rwy_direction_list:
                if rwy.txt_desig == act.rdes:
                    rwy_in_use = rwy
            stars = [star.txt_desig for star in rwy_in_use.star_dict.values()]

        except:
            logging.warning("No STARs found for %s destination %s" % (act.callsign, act.ades))
            stars = ''
            act_star = ''
        entries.append({'label': 'STAR:', 'width': 5, 'values': stars, 'def_value': act_star})
        x1 = self.container.winfo_x()+self.container.winfo_width()/2
        y1 = self.container.winfo_y()+self.container.winfo_height()/2
        RaDialog(self.canvas, label=act.callsign+': Change STAR',
                    ok_callback=change_star, entries=entries, position=(x1, y1))


class SobTabular(RaTabular):
    """A tabular window showing departure aircraft"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='PREV SOBREVUELO', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.sacta_mode = radisplay.fir.sacta_mode[radisplay.sector.split(',')[0]]
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'ORIG'+' '+'DEST'+' '+'CSSR'
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        ra_bind(radisplay, self.legend, "<Button-1>", self.legend_clicked)
        self.cs_ordered = True
        self.sob = []

    def legend_clicked(self, e=None):
        self.cs_ordered = not self.cs_ordered
        self.update()

    def update(self):

        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        fir = self.master.fir

        self.sob = [f for f in self.master.flights if f.adep not in self.master.fir.aerodromes.keys() and f.ades not in self.master.fir.aerodromes.keys()
                         and f.pof == Aircraft.FLYING]


        if self.cs_ordered:
            self.sob.sort(lambda p, q: cmp(p.callsign, q.callsign))
        else:
            self.sob.sort(lambda p, q: cmp(p.hora, q.hora))

        if len(self.sob) == 0:
            pass
        else:
            i = 0
            for f in self.sob:

                t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+ f.ades.ljust(4)+' '+f.squawk.ljust(5)
                self.insert(i, t)

                track = self.master._flights_tracks[f]
                self.list.itemconfig(i, foreground=track.color.get())

                i += 1

        if self.showed: self.adjust()

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.sob[index]

        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            radisp.toggle_select(f)


class ArrTabular(RaTabular):
    """A tabular window showing arrivals"""
    def __init__(self, radisplay, canvas=None, flights=None, mode='pp', **kw):
        """Create a tabular showing aircraft reports and requests"""
        RaTabular.__init__(self, canvas, label='LLEGADAS', closebuttonhides=True,
                           anchor=tix.NW, **kw)

        self.canvas = canvas
        self.master = radisplay
        self.mode = mode
        self.list.configure(font="Courier 12", selectmode=tix.SINGLE)
        self.legend['text'] = 'INDICATIV'+' '+'ORIG'+' '+'DEST'+' '+'STAR    '+' CSSR'
        ra_bind(radisplay, self.legend, "<Button-1>", self.legend_clicked)
        self.cs_ordered = True
        ra_bind(radisplay, self.list, "<Button-2>", self.centerclicked)
        self.arr = []

    def legend_clicked(self, e=None):
        self.cs_ordered = not self.cs_ordered
        self.update()

    def update(self):
        """Update the tabular using the given departure list"""
        self.list.delete(0, self.list.size())
        fir = self.master.fir

        self.arr = [f for f in self.master.flights if f.pof == Aircraft.LANDED]
        if self.cs_ordered:
            self.arr.sort(lambda p, q: cmp(p.callsign, q.callsign))
        else:
            self.arr.sort(lambda p, q: cmp(p.eobt, q.eobt))

        i = 0
        for f in self.arr:
            if not self.arr[i].star:
                t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+\
                    f.ades.ljust(4)+' '+f.squawk.ljust(5)
            else:
                star = '%7s' % f.star.txt_desig
                t = ' '+f.callsign.ljust(9)+f.adep.ljust(4)+' '+\
                    f.ades.ljust(4)+' '+star.ljust(8)+' '+f.squawk.ljust(5)
            self.insert(i, t)
            track = self.master._flights_tracks[f]
            self.list.itemconfig(i, foreground=track.color.get())

            i += 1

        if self.showed: self.adjust()

    def centerclicked(self, e=None):
        lb = self.list
        if lb.nearest(e.y) < 0:  # No items
            return
        index = lb.nearest(e.y)
        if e.y < lb.bbox(index)[1] or e.y > (lb.bbox(index)[3]+lb.bbox(index)[1]):
            return  # Not really clicked within the item
        radisp = self.master
        f = self.arr[index]
        vt = self.master._flights_tracks[f]

        if self.mode == 'pp':
            radisp.show_hide_way_point(f)
        else:
            try: radisp.selected_track.selected = not radisp.selected_track.selected
            except: logging.debug("Unselecting previous selected track failed")
            if radisp.selected_track == vt:
                radisp.selected_track = None
                vt.selected = False
            else:
                radisp.selected_track = vt
                vt.selected = True


class GeneralInformationWindow(RaFrame):
    """A window containing generic information related to the position"""
    def __init__(self, radisplay, sectors, activesectors, **kw):
        """RaFrame containing info such as the QNH and the active sectors
        """
        def_opt = {'position': (5, 5), 'anchor': tix.NW, 'closebutton': False, 'undockbutton': False}
        def_opt.update(kw)
        self.radisplay = radisplay
        master = radisplay.c
        self._qnh = 0000
        self.tlevel = 70
        # The frame constructor method will call _build
        RaFrame.__init__(self, master, **def_opt)

        # Sector selection window
        if self.radisplay.disp_number == 1:
            self.sector_vars = {}
            self.sector_win = sw = RaFrame(master, position=(500, 500), closebuttonhides=True)
            swc = sw.contents
            font = ('Arial', '9', 'bold')
            fg = 'gray90'
            bg = 'black'
            l = tix.Label(swc, text='ORS', font=font, fg=fg, bg=bg)
            l.pack(side=tix.TOP)
            for s in sectors:
                v = self.sector_vars[s] = tix.IntVar()
                if s in activesectors: v.set(1)
                l = tix.Checkbutton(swc, text=s, font=font, fg=fg, bg=bg, selectcolor=bg, variable=v, command=self.sector_set)
                l.pack(side=tix.TOP, anchor=tix.W)
            self.sector_win.hide()
        
    def _build(self, master=None, windowed=False, **kw):
        if windowed:
            def_opt = {'label': 'Reloj'}
            def_opt.update(kw)
        else:
            def_opt = kw
        RaFrame._build(self, master=master, windowed=windowed, **def_opt)
        font = ('Arial', '9', 'bold')
        fg = 'gray90'
        bg = 'black'
        self.qnh_b = tix.Button(self.contents, font=font, foreground='green', background=bg, text="QNH: %d"%floor(self._qnh))
        self.tl_b = tix.Button(self.contents, font=font, fg=fg, bg=bg, text="TL: %d"%self.tlevel, state=tix.DISABLED)
        self.mr_b = tix.Button(self.contents, font=font, fg=fg, bg=bg, text='MULTIRAD', state=tix.DISABLED)
        self.vid_b = tix.Button(self.contents, font=font, fg=fg, bg=bg, text='SIN VIDEO', state=tix.DISABLED)
        self.ac_b = tix.Button(self.contents, font=font, fg='green', bg=bg, text='AC', command=self.toggle_pac)
        self.mode_b = tix.Button(self.contents, font=font, fg='green', bg=bg, text='AUTONOMO', state=tix.DISABLED)
        self.sect_b = tix.Button(self.contents, font=font, fg=fg, bg=bg, text='SECT', command=self.toggle_sectors_window)
        
        self.qnh_b.pack(side=tix.LEFT, padx=1, pady=1)
        self.tl_b.pack(side=tix.LEFT, padx=1, pady=1)
        # self.mr_b.pack(side=tix.LEFT, padx = 1, pady=1)
        # self.vid_b.pack(side=tix.LEFT, padx = 1, pady=1)
        self.ac_b.pack(side=tix.LEFT, padx=1, pady=1)
        # self.mode_b.pack(side=tix.LEFT, padx = 1, pady=1)
        self.sect_b.pack(side=tix.LEFT, padx=1, pady=1)
        
    
    def toggle_sectors_window(self):
        if self.radisplay.disp_number == 1:
            self.sector_win.conmuta()
            # self.sector_win.configure(position=self.sect_b.winfo_pointerxy())
            # JRAR pointer method was giving problems in multi-display
            self.sector_win.configure(position=(370,30))
    
    def toggle_pac(self):
        # Boton AC de 3 estados (de GAMMA): verde = PAC y VAC, amarillo = solo VAC,
        # rojo = sin avisos de conflicto. Antes solo alternaba PAC (verde/rojo).
        if self.ac_b['fg'] == 'green':
            self.ac_b['fg'] = 'yellow'
            self.radisplay.pac = False
            self.radisplay.vac = True
        elif self.ac_b['fg'] == 'yellow':
            self.ac_b['fg'] = 'red'
            self.radisplay.pac = False
            self.radisplay.vac = False
        else:
            self.ac_b['fg'] = 'green'
            self.radisplay.pac = True
            self.radisplay.vac = True
        
    def sector_set(self):
        """Method called whenever sector checkboxes are modified"""
        #self.radisplay.set_active_sectors([s for s, v in self.sector_vars.items() if v.get()])
        for radisp in self.radisplay.master.display:
            try:
                radisp.set_active_sectors([s for s, v in self.sector_vars.items() if v.get()])
            except AttributeError:
                continue
    def set_tlevel(self, qnh):
        if qnh > 1013.2:
            tlevel = TA+10
        elif qnh <= 1013.2 and qnh >= 995.1:
            tlevel = TA+15
        elif qnh < 995.1 and qnh >= 977.2:
            tlevel = TA+20
        elif qnh < 977.2 and qnh >= 959.5:
            tlevel = TA+25
        elif qnh <959.5:
            tlevel = TA+30
        else:
            tlevel = 00
        try:
            self.tl_b['text'] = "TL: %d" % tlevel
        except AttributeError:
            pass
            
    def get_qnh(self):
        return self._qnh
    
    def set_qnh(self, value):
        self._qnh = value
        self.set_tlevel(self._qnh)
        try:
            self.qnh_b['text'] = "QNH: %d" % floor(self._qnh)
        except AttributeError:
            pass
    qnh = property(get_qnh, set_qnh)
    
    def configure(self, **options):
        RaFrame.configure(self, **options)
        
    def exit(self):
        del self.radisplay
    

class SmartColor(object):
    """Given a color string and a brightness factor calculates the output color"""
    
    # TODO this should probably be rewritten using properties as the VisTrack
    
    winfo_rgb       = None  # This function will be set when Tkinter is initialized
    known_values    = {}    # We keep a cache of calculations
    
    def __init__(self, color='white', intensity=1.0):
        object.__setattr__(self, 'color', color)  # displayed  color
        object.__setattr__(self, 'basecolor', color)  # master color
        self.intensity = intensity  # Item color intensity
        self.set_intensity(intensity)
            
    def get(self): return self.color
    
    def set(self, c):
        self.basecolor = c
        self.set_intensity(self.intensity)
        
    def get_basecolor(self): return self.basecolor
                 
    def set_intensity(self, factor):
        """Returns a color object with the intensisty changed and string representation"""
        self.intensity = factor
        color = self.basecolor
        
        if color == '' or factor == 1:
            self.color = self.basecolor
            return  # If no correction or transparent, simply set the base color
        
        if self.known_values.has_key((color, factor)):
            self.color = self.known_values[(color, factor)]
            return
    
        (red, green, blue) = self.winfo_rgb(color)
        
        rgb1 = [red, green, blue]
        hsv = self.RGBtoHSV(rgb1, 65535)
        v = hsv[2]*factor
        if v > 1.0:
            v = 1.0
        hsv[2] = v
        rgb2 = self.HSVtoRGB(hsv, 65535)
        
        r1 = int(rgb2[0])
        g1 = int(rgb2[1])
        b1 = int(rgb2[2])
    
        self.color = self.rgb_to_string((r1, g1, b1))
        self.known_values[(color, factor)] = self.color

    def RGBtoHSV(self, rgb, factor=1):
        """Returns HSV components from rgb (R,G,B)"""
        r1 = float(rgb[0])/factor
        g1 = float(rgb[1])/factor
        b1 = float(rgb[2])/factor
        rgb1 = [r1, g1, b1]
    
        max_c = max(rgb1)
        min_c = min(rgb1)
        delta = max_c - min_c
        v = max_c
    
        if delta == 0.0:
            s = 0.0
            h = 0.0
            return [h, s, v]
        else:
            s = delta / max_c
            del_R = (((max_c - r1) / 6.0) + (delta / 2.0)) / delta
            del_G = (((max_c - g1) / 6.0) + (delta / 2.0)) / delta
            del_B = (((max_c - b1) / 6.0) + (delta / 2.0)) / delta
        if r1 == max_c:
            h = del_B - del_G
        elif g1 == max_c:
            h = (1.0/3.0)+del_R - del_B
        elif b1 == max_c:
            h = (2.0/3.0)+del_G - del_R
            
        if h < 0.0:
            h += 1.0
        if h > 1.0:
            h -= 1.0
        
        return [h, s, v]
    
    def HSVtoRGB(self, hsv, factor=1):
        """Returns RGB components scaled by factor, from hsv"""
        [h, s, v] = hsv
        if s == 0:
            var_r = v
            var_g = v
            var_b = v
    
        else:
            var_h = h*6.0
            if var_h == 6.0: var_h = 0
            var_i = floor(var_h)
            var_1 = v * (1 - s)
            var_2 = v * (1 - s * (var_h - var_i))
            var_3 = v * (1 - s * (1 - (var_h - var_i)))
            
            if var_i == 0.0:
                var_r = v
                var_g = var_3
                var_b = var_1
            elif var_i == 1.0:
                var_r = var_2
                var_g = v
                var_b = var_1
            elif var_i == 2.0:
                var_r = var_1
                var_g = v
                var_b = var_3
            elif var_i == 3.0:
                var_r = var_1
                var_g = var_2
                var_b = v
            elif var_i == 4.0:
                var_r = var_3
                var_g = var_1
                var_b = v
            else:
                var_r = v
                var_g = var_1
                var_b = var_2
            
        var_r = var_r * factor
        var_g = var_g * factor
        var_b = var_b * factor
            
        return [var_r, var_g, var_b]
        
    def rgb_to_string(self, rgb):
        """Returns a string representing de RGB color passed in rgb"""
        return "#%04x%04x%04x" % rgb
   

class RaBrightness(RaFrame):
    """Brightness control frame"""
    def __init__(self, master, callback, intensity, **kw):
        # def_opt={'position':(512,575)}
        # def_opt.update(kw)
        self.callback = callback
        self.intensity = intensity
        self.master = master
        # The frame constructor method will call _build
        RaFrame.__init__(self, master=master, closebuttonhides=True, **kw)

        
    def _build(self, master=None, windowed=False, **kw):
        A = (1.0-0.35)/25
        B = 1.0

        RaFrame._build(self, master=master, windowed=windowed,  **kw)

        gvar = tix.DoubleVar()  # General
        gvar.set((self.intensity['GLOBAL'] - B) / A)
        tvar = tix.DoubleVar()  # Tracks
        tvar.set((self.intensity['TRACKS'] - B) / A)
        mvar = tix.DoubleVar()  # Maps
        mvar.set((self.intensity['MAP'] - B) / A)
        lvar = tix.DoubleVar()  # LADs
        lvar.set((self.intensity['LADS'] - B) / A)

        self.scale_colors={'background': self.bd,
                            'highlightbackground': self.bd,
                            'highlightcolor': self.bd,
                            'foreground': self.fg,
                            'troughcolor': self.bd}

        cb = self.callback

        def changed(*args):
            A = (1.0-0.35)/25
            B = 1.0
            cb({"GLOBAL": A*gvar.get()+B, "TRACKS": A*tvar.get()+B,
                      "MAP": A*mvar.get()+B, "LADS": A*lvar.get()+B})

        for t, v in (("G", gvar), ("P", tvar), ("M", mvar), ("L", lvar)):
            f = tix.Frame(self.contents, background=self.bd)
            l = tix.Label(f, text=t, background=self.bd, fg=self.fg)
            v.set(v.get())
            v.trace("w", changed)
            w = tix.Scale(f)
            l.pack(side=tix.TOP)
            w.pack(side=tix.BOTTOM, fill=tix.BOTH)
            f.pack(side=tix.LEFT)
            w.configure(**self.scale_colors)
            w.configure(showvalue=1, sliderlength=20, from_=50, to=-25, resolution=1, variable=v)
        del(self.callback)
    
    
class VisTrack(object):  # ensure a new style class
    """Visual representation of a radar track on either a pseudopilot display
    or a controller display"""
    
    allitems = ['cs', 'alt', 'rate', 'cfl', 'tfl', 'rfl', 'gs', 'mach', 'wake', 'lrwy', 'ltype', 'spc', 'echo', 'rutrod', 'holdp', 'emg',
                'stand_sid', 'stand', 'hdg', 'dir', 'fhdg', 'pac', 'vac', 'trans', 'to_do', 'thr_nm', 'thr_min', 'tfto', 'colat', 'rules', 'adep',
                'ades', 'r_speed', 'r_head', 'r_rate', 'osf_act', 'sidok', 'pvh_notes']
    timer_id = None  # Whenever there are timer based callbacks pending, this is set
    timer_callbacks = []  # List of timer based callbacks and args
    ON, OFF = True, False  
    timer_state = ON  # Toggles when there are timers set between ON and OFF
    ASSUMED_COLOR_UCS_OverFlight = INCOMING_COLOR = '#bdbdbd' # light grey
    NONASSUMED_COLOR_UCS = '#99DD99' # Light green
    ASSUMED_COLOR_UCS = 'green' # Dark green
    ASSUMED_COLOR_PICT = 'orange'
    ASSUMED_COLOR_UCS_DEP = ASSUMED_COLOR_PICT_DEP = 'green'
    ASSUMED_COLOR_PICT_OverFlight = 'cyan'
    NONASSUMED_COLOR = 'white'
    VEHICLE_COLOR = '#99DD99'
    VEHICLE_PVH_COLOR = '#5599FF'  # Vehiculo con Plan de Vehiculo (PVH)
    OSF_NOT_ASSUMED_ARRIVAL = 'orange4'
    OSF_ASSUMED_ARRIVAL = 'orange'
    OSF_NOT_ASSUMED_DEP = 'green4'
    OSF_ASSUMED_DEP = 'green'
    OSF_WARNING = 'red'

    def __init__(self, radisplay, message_handler, do_scale, undo_scale, intensity=1.0):
        """Construct a radar track inside the parent display.
        
        Instantiation arguments:
        canvas -- parent canvas
        message_handler -- function that will deal with events generated by the track
        do_scale -- scaling function
        undo_scale -- unscaling function """
        
        self.id = 'track'+str(id(self))
        self.rd             = radisplay
        canvas              = radisplay.c
        self._c             = canvas
        self._message_handler = message_handler
        self.do_scale       = do_scale
        self.undo_scale     = undo_scale

        # Defaults
        
        # Track attributes
        self._item_refresh_list = []  # List of label items that need to be refreshed
        # Set the default but don't trigger a redraw
        self._visible       = False
        self._sacta_mode    = ''
        self._mode          = ''
        self._label_format  = ''
        self._selected      = False
        self._assumed       = False  # Para que sea compatible con la version SACTA de la TORRE, que tiene naranja para las llegadas en modo asumido y no asumido
        self._app_autorized = False
        self._initialized   = False
        self.line_onoff     = [True, True, True, True, True, True]

        self._plot_only     = False
        self._pac           = False
        self._vac           = False
        self._emg           = False
        self.local_dep      = False
        self.local_des      = False
        
        # object.__setattr__(self,'x',0)  # Screen coords
        # Can't set x directly until we also have a y
        self._x             = 0.  # X screen coordinate
        self._y             = 0.  # Y screen coordinate
        self._wx            = 0.  # X world coordinate
        self._wy            = 0.  # Y world coordinate
        self._intensity     = intensity  # Color intensity
        self.future_pos = []  # List of future positions. Used for STCA calculations
        self.cs             = 'ABC1234'  # Callsign
        self.mach           = .82
        self.gs             = 250
        self.thr_nm         = 10.5
        self.thr_min        = 2.5
        self.tfto           = 2.0
        self.t_takeoff      = None
        self.ias            = 200
        self.ias_max        = 340
        self.ias_min        = 100
        self.wake           = 'H'
        self.lrwy           = '36L'
        self.echo           = 'KOTEX'
        self.rutrod         = '-'  # Controller input free text (max 7 letters)
        self.gate           = 'GT'
        self.holdp          = 'HP'
        self.sidok          = 'O'  # Ok SID tick only LEMD
        self.stand_sid      = 'KOTEX1A'
        self.stand          = ''
        self.trans          = '2000'
        self.to_do          = 'fpr'
        self.hdg            = 200
        self.track          = 200  # Magnetic track
        self.fhdg           = 200   # Target (future) heading
        self.r_speed        = 250
        self.r_head         = 200
        self.r_rate         = 1500
        self.dir            = '>'
        self.opc            = 'ECON'
        self.draw_fhdg      = False  # Whether or not to draw the future hdg
        self.alt            = 150
        self.draw_cfl       = False  # Whether or not to draw the current cfl
        self.cfl            = 250
        self.ecl            = 350
        self.tfl            = 350
        self.remove_tfl     = False  # DCM: doble click on tfl label and remove it
        self.arrow          = 250
        self.rate           = 0  # Vertical rate of climb or descent 2000
        self.adep           = 'LEMD'
        self.ades           = 'LEBB'
        self.type           = 'B737'
        self.ltype           = 'B737'
        self.radio_cs       = 'IBERIA'
        self.rfl            = 330
        self.colat          = 'SAL_'
        self.rules          = 'VFR'
        self.adep           = 'LEMD'
        self.ades           = 'LEBL'
        self.eclfix         = 'CEGAM'
        self.osf_act        = '---'
        self.pvh_notes      = ''
        self.OSF_pof        = '---'
        self._has_pvh       = False
        self.AirportElev = 0.0
        self.lvl_blocked = False

        self.color          = SmartColor(self.INCOMING_COLOR)
        self.selected_border_color = SmartColor('yellow')
        
        self._last_t = datetime.datetime.today() - datetime.timedelta(days=1)  # Last time the radar was updated
        
        # Plot attributes
        self.plotsize = 3
        self._pitem = None
        
        # Plot history
        self._h = []  # List of previous positions in real coord (not screen), and the associated canvas rectangle
        
        # Label
        self._l                     = self.Label(self)
        self._l_font_size           = 12
        _font_family = "Courier Prime" if "Courier Prime" in tkFont.families() else "Helvetica"
        self._l_font                = tkFont.Font(family=_font_family, size=self.l_font_size)
        self.label_heading          = 120  # Label heading 120
        self.label_radius           = 30  # Label radius 30
        # lxo and lyo are the offsets of the label with respect to the plot
        self.label_xo               = self.label_radius * sin(radians(self.label_heading))
        self.label_yo               = self.label_radius * cos(radians(self.label_heading))
        # lx and ly are the actual screen coord of the label
        self.label_x                = self.x + self.label_xo
        self.label_y                = self.y + self.label_yo
        self.label_width            = 0
        self.label_height           = 0
        # Alternative versions of the label screen coordinates to try them out
        # while performing label separation
        self.label_x_alt            = self.label_x
        self.label_y_alt            = self.label_y
        self.label_heading_alt      = self.label_heading
        # Find the end of the leader line (it starts in the plot)
        self._ldr_x                 = self.label_x
        self._ldr_y                 = self.label_y + 10
        self._lineid                = None
        self._widelineid            = None
        self._flashing              = False
        self._release_atc_pos       = False
        self._OSF_warning           = False
        # Alertas aeroportuarias (INCW, CMAC, CATC)
        self._alert_severity        = 0     # 0=none, 1=WNG, 2=VIO
        self._alert_text_obj        = None  # Alerta mas prioritaria (Alert object)
        self._alert_item            = None  # Canvas item ID del texto de alerta
        self._alert_blink_on        = True  # Estado actual del parpadeo de alerta
        self._alert_blinking        = False # Si el parpadeo esta activo
        self._active_alerts         = []    # Lista completa de Alert objects para ventana
        self.catc_pred              = False # Flag prediccion CATC (indicador visual morado)
        self._alert_frame_item      = None  # Canvas item ID del marco rojo VIO
        self.auto_separation        = True
        self.last_rotation          = 0  # Keeps the serial number of the last rotation event
                                         # so that auto rotation will try to move the last manually moved label last.
        # Speed vector
        self.speed_vector           = (0, 0)  # Final position of the speed vector in screen coords
        self._speed_vector_length   = 0.  # Length in minutes

        self.redraw()

    def configure(self, **kw):
        """Configure track options"""
        if kw.has_key('position'):
            x, y = kw['position']
            self.coords(x, y)
            
    def coords(self, x, y, t):
        """Reposition the track using screen coordinates"""
        
        if not self.visible:
            return
            
        st = self.id
        dx, dy = x-self.x, y-self.y  # Calculate delta
        # Store the position in history if there has been a radar
        # update since the last one (more than five seconds ago)
        # TODO: The last radar update should be stored in a future radar
        # display class, rather than here.
        # if t is not None and t>self.rd.t+datetime.timedelta(seconds=self.rd.refresco):
        if t is not None:
            while len(self._h) >= 6:
                (pos, rect_id) = self._h.pop()
                self._c.delete(rect_id)
            rx, ry = self.undo_scale((x, y))
            rect_id = self.draw_h_plot((rx, ry))
            self._h.insert(0, [(rx, ry), rect_id])
        #    self._last_t=t
            
        self.x, self.y = x, y  # New position
        
        # Label items refresh
        for i in self._item_refresh_list:
            self._l.refresh(i)
        self._item_refresh_list = []
        # Move moveable elements        
        self._c.move(st, dx, dy)
        # Update position variables:
        self.label_x += dx
        self.label_y += dy
        self._ldr_x += dx
        self._ldr_y += dy

        # Reposition history points
        for (rpos, rect_id) in self._h:
            (x, y) = self.do_scale(rpos)
            self._c.coords(rect_id, x, y, x+1, y+1)

        # Same with speed vector
        speed_vector = s((self.wx, self.wy), pr((self.speed_vector_length * self.gs, self.track)))
        sx, sy = self.do_scale(speed_vector)
        self._c.coords(st+'speedvector', self.x, self.y, sx, sy)

    def delete(self):
        """Delete the visual track and unbind all bindings"""
        # Parar parpadeo de alerta antes de borrar: si no, blink() recrea el texto
        # de alerta aunque la etiqueta este oculta (filtro FGND...)
        self._stop_alert_blink()
        self.delete_p()
        self.delete_h()
        self.delete_sv()
        self.delete_l()
        
    def redraw(self):
        """Draw the visual track with the current options"""
        
        if not self.visible:
            return
            
        self.redraw_h()  # History
        self.redraw_sv()  # Speed vector
        # Leader and label
        if self.plot_only:
            self.delete_l()
        else:
            try:
                self.redraw_l()
            except:
                logging.warning("Error redrawing label for %s" % self.cs, exc_info=True)
        self.redraw_p()  # Plot

    def refresh(self):
        """Reconfigure VisTrack items with current options
        Redrawing is expensive, particularly the label text
        because of everything related to fonts.
        Refreshing updates things like color"""

        if not self.visible:
            return

        # Detectar etiqueta perdida: si visible y no plot_only pero cs.i es None,
        # la etiqueta fue eliminada por un error previo. Recuperar con redraw_l.
        if not self.plot_only and self._l.cs.i is None:
            try:
                self.redraw_l()
            except:
                logging.warning("Error recovering label for %s" % self.cs, exc_info=True)
            return

        for i_name in self.allitems:
            self._l.refresh(i_name)


    def delete_p(self):
        """Delete the visual plot and unbind bindings"""
        if self._pitem:  # Delete old plot
            # Remove bindings
            ra_cleartagbinds(self._pitem, self._c)
            # Delete the canvas item
        self._c.delete(self._pitem)
        
    def redraw_p(self):
        """Draw the visual plot with the current options"""
        self.delete_p()
        size = self.plotsize
        x, y = self.x, self.y
        s = self.id
        color = SmartColor(self.color.get_basecolor(), self._intensity).get()
        sacta_mode = self.rd.fir.sacta_mode[self.rd.sector.split(",")[0]]
        if sacta_mode == 'UCS':
            if self.assumed:
                size = size + 1
                self._pitem = self._c.create_polygon(x - size, y, x, y - size, x + size, y, x, y + size, x - size, y,
                                                     outline=color, fill='',
                                                     tags=(s, s + 'plot', 'track', 'plot'))
            else:
                self._pitem = self._c.create_polygon(x - size, y, x, y - size, x + size, y, x, y + size, x - size, y,
                                                     outline=color, fill='',
                                                     tags=(s, s + 'plot', 'track', 'plot'))
        else:
            if self.assumed:
                size = size + 1  # Assumed plots are a litle bigger to appear the same size
                self._pitem = self._c.create_polygon(x - size, y, x, y - size, x + size, y, x, y + size, x - size, y,
                                                     outline=color, fill='',
                                                     tags=(s, s + 'plot', 'track', 'plot'))
            else:
                self._pitem = self._c.create_polygon(x - size, y - size, x - size, y + size, x + size, y + size,
                                                     x + size, y - size, x - size,
                                                     y - size, outline=color, fill='',
                                                     tags=(s, s + 'plot', 'track', 'plot'))

        def plot_b1(e=None):
            self._message_handler(self, 'plot', '<Button-1>', None, e)

        def plot_b3(e=None):
            # La pantalla puede tratar el clic (vehiculos con PVH); si no, alterna solo plot
            if not self._message_handler(self, 'plot', '<Button-3>', None, e):
                self.plot_only = not self.plot_only

        def plot_b2(e=None):
            if not self._message_handler(self, 'plot', '<Button-2>', None, e):
                self.plot_only = not self.plot_only

            # (Re)Do the bindings
        ra_tag_bind(self._c, self._pitem, '<Button-1>', plot_b1)
        # Boton 2 del plot: salidas del aerodromo con SMR (parametro 'smr_ad', antes fijo LEST)
        # y escenarios con planes de vehiculo (parametro 'pvh')
        try:
            _fir = self.rd.fir
            _b2 = (self.adep and self.adep == _fir.param('smr_ad', '')) or bool(_fir.param('pvh', False))
        except AttributeError:
            _b2 = (self.adep == 'LEST')
        if _b2:
            ra_tag_bind(self._c, self._pitem, '<Button-2>', plot_b2)
        ra_tag_bind(self._c, self._pitem, '<Button-3>', plot_b3)

    def flash_p(self, count):
        if self.timer_state:
            self._c.itemconfig(self._pitem, outline='green')
        else:
            self._c.itemconfig(self._pitem, outline='black')
        # self.redraw_p()
        if count < 10:
            count += 1
            self.add_timer_callback(self.flash_p, count)
        else:
            self.redraw_p()
        #  self.after(500,self.flash_p) Tkinter delayed call
        # reactor.callLater(0.5,self.flash_p) Twisted reactor delayed call

    def delete_h(self):
        """Delete this track's history plots"""
        self._c.delete(self.id+'hist')

    def redraw_h(self):
        """Draw the history with the current options"""
        self.delete_h()
        for i in range(len(self._h)):
            (rx, ry), rect_id = self._h[i]
            (h0, h1) = self.do_scale((rx, ry))
            rect_id = self.draw_h_plot((rx, ry))
            self._h[i][1] = rect_id

    def draw_h_plot(self, (h0, h1)):
        s = self.id
        color = SmartColor(self.color.get_basecolor(), self._intensity).get()
        sacta_mode = self.rd.fir.sacta_mode[self.rd.sector.split(",")[0]]
        if self.mode in ['atc', 'atc-nocorrel']:
            if sacta_mode == 'UCS':
                if self.assumed and self.rules != 'VEH':
                    item = self._c.create_rectangle(h0, h1, h0+1, h1+1, outline=color,
                                             tags=(s, s+'hist', 'track'))
                else:
                    item = self._c.create_rectangle(h0, h1, h0+1, h1+1, outline=self.INCOMING_COLOR,
                                             tags=(s, s+'hist', 'track'))
            else:
                if self.rules != 'VEH':
                    item = self._c.create_rectangle(h0, h1, h0 + 1, h1 + 1, outline=color,
                                                tags=(s, s + 'hist', 'track'))
                else:
                    item = self._c.create_rectangle(h0, h1, h0 + 1, h1 + 1, outline=self.INCOMING_COLOR,
                                                    tags=(s, s + 'hist', 'track'))
        else:
            item = self._c.create_rectangle(h0, h1, h0 + 1, h1 + 1, outline=color,
                                            tags=(s, s + 'hist', 'track'))

        return item
            
    def delete_sv(self):
        """Delete the track's speed vector"""
        # Speed vector
        s = self.id
        self._c.delete(s+'speedvector')

    def redraw_sv(self):
        """Redraw this track's speed vector"""
        self.delete_sv()
        if not self.visible: return
        st = self.id
        speed_vector = s((self.wx, self.wy), pr((self.speed_vector_length * self.gs, self.track)))
        screen_sv = self.do_scale(speed_vector)
        (sx, sy) = screen_sv
        color = SmartColor(self.color.get_basecolor(), self._intensity).get()
        sacta_mode = self.rd.fir.sacta_mode[self.rd.sector.split(",")[0]]
        if self.mode in ['atc', 'atc-nocorrel']:
            if sacta_mode == 'UCS':
                if self.assumed and self.rules != 'VEH':
                    self._c.create_line(self.x, self.y, sx, sy, fill=color, tags=(st, st+'speedvector', 'track'))
                else:
                    self._c.create_line(self.x, self.y, sx, sy, fill=self.INCOMING_COLOR, tags=(st, st+'speedvector', 'track'))
            else:
                if self.rules != 'VEH':
                    self._c.create_line(self.x, self.y, sx, sy, fill=color, tags=(st, st+'speedvector', 'track'))
                else:
                    self._c.create_line(self.x, self.y, sx, sy, fill=self.INCOMING_COLOR,
                                        tags=(st, st + 'speedvector', 'track'))
        else:
            self._c.create_line(self.x, self.y, sx, sy, fill=color, tags=(st, st + 'speedvector', 'track'))


    def delete_l(self):
        c = self._c
        s = self.id
        
        if (self._lineid):
            ra_cleartagbinds(self._lineid, c)
        self._lineid = None
        if (self._widelineid):
            ra_cleartagbinds(self._widelineid, c)
        self._widelineid = None
        # Delete old label, leader and selection box
        c.delete(s+'selection_box')
        c.delete(s+'leader')
        c.delete(s + 'wideleader')
        c.delete(s+'alert')
        self._alert_item = None
        c.delete(s+'alertframe')
        self._alert_frame_item = None
        self._l.delete()
        
    def redraw_l(self):
        """Draw the leader and label of the track using current options"""
        # Delete old label, leader and selection box
        self.delete_l()
        
        if not self.visible:
            return

        self._l.redraw()
        # Selection box
        self.selected_box()
        # Leader line
        self.leader_line()
        # Recrear texto de alerta si hay alerta activa
        if self._alert_severity > 0:
            self._update_alert_display()

    def refresh_leader(self):
        """Draw the leader and label of the track using current options"""
        if not self.visible:
            return
        # Helper variables
        c = self._c
        s = self.id

        if self._lineid:
            ra_cleartagbinds(self._lineid, c)
        self._lineid = None
        if self._widelineid:
            ra_cleartagbinds(self._widelineid, c)
        self._widelineid = None
        # Delete old label, leader and selection box
        c.delete(s + 'selection_box')
        c.delete(s + 'leader')
        c.delete(s + 'leadewider')

        # Leader and label
        if not self.plot_only:
            # Selection box
            self.selected_box()
            # Leader line
            self.leader_line()

    def leader_line(self):
        # Helper variables
        c = self._c
        s = self.id
        # Leader line
        color = SmartColor(self.color.get_basecolor(), self._intensity).get()
        sacta_mode = self.rd.fir.sacta_mode[self.rd.sector.split(",")[0]]
        if self.mode in ['atc', 'atc-nocorrel']:
            if sacta_mode == 'OSF':
                if self.local_dep and self.rules != 'VEH':
                    id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                       tags=(s, s + 'leader', 'track'))
                elif self.local_des and self.rules != 'VEH':
                    id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                       tags=(s, s + 'leader', 'track'))
                else:
                    if not self.assumed:
                        color = SmartColor(self.INCOMING_COLOR, self._intensity).get()
                    id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                       tags=(s, s + 'leader', 'track'))
            else:
                if sacta_mode == 'UCS':
                    id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                       tags=(s, s + 'leader', 'track'))
                else:
                    if self.rules != 'VEH':
                        id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                           tags=(s, s + 'leader', 'track'))
                    else:
                        color = SmartColor(self.INCOMING_COLOR, self._intensity).get()
                        id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                                           tags=(s, s + 'leader', 'track'))
        else:
            id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill=color,
                               tags=(s, s + 'leader', 'track'))

        self._lineid = id
        ra_tag_bind(c, self._lineid, "<Button-1>", self.rotate_label)
        ra_tag_bind(c, self._lineid, "<Button-3>", self.counter_rotate_label)

        id = c.create_line(self.x, self.y, self._ldr_x, self._ldr_y, fill='',width=20,
                           tags=(s, s + 'wideleader', 'track')) #Linea invisible gorda debajo de leader
        c.tag_lower(id) #Mueve linea gorda al fondo
        self._widelineid = id
        ra_tag_bind(c, self._widelineid, "<Button-1>", self.rotate_label)
        ra_tag_bind(c, self._widelineid, "<Button-3>", self.counter_rotate_label)

    def selected_box(self):
        # Helper variables
        c = self._c
        s = self.id
        # Label text
        new_label_x = self.x + self.label_radius * sin(radians(self.label_heading))
        new_label_y = self.y + self.label_radius * cos(radians(self.label_heading))
        self.reposition_label(new_label_x, new_label_y)
        lw = self.label_width
        lh = self.label_height
        lx = self.label_x
        ly = self.label_y

        # Selection box
        if self.selected:
            color = SmartColor(self.selected_border_color.get(), self._intensity).get()
            c.create_rectangle(lx, ly, lx + lw, ly + lh, outline=color,
                               tags=(s, s + 'label', s + 'selection_box', 'track'))


    def rotate_label(self, e=None):
        [x, y] = (self.x, self.y)
        self.auto_separation = False
        self.label_heading += 90.0
        self.label_radius = self.l_font_size*3
        new_label_x = x + self.label_radius * sin(radians(self.label_heading))
        new_label_y = y + self.label_radius * cos(radians(self.label_heading))
        self.reposition_label(new_label_x, new_label_y)
        try:  # In case this function was not called by a gui event
            self.last_rotation = e.serial
            self._message_handler(self, 'leader', '<Button-1>', None, e)
        except: pass
        
    def counter_rotate_label(self, e=None):
        # if e is not None:
        #        self.last_lad = e.serial
        [x, y] = (self.x, self.y)
        self.auto_separation = False
        self.label_heading -= 90.0
        self.label_radius = self.l_font_size*3
        new_label_x = x + self.label_radius * sin(radians(self.label_heading))
        new_label_y = y + self.label_radius * cos(radians(self.label_heading))
        self.reposition_label(new_label_x, new_label_y)
        try:  # In case this function was not called by a gui event
            self.last_rotation = e.serial
            self._message_handler(self, 'leader', '<Button-3>', None, e)
        except: pass
     
    def label_coords(self, newx, newy):
        """Repositions the label given new screen coordinates"""
        dx = newx - self.label_x
        dy = newy - self.label_y
        self.label_x += dx
        self.label_y += dy
        self.label_xo += dx
        self.label_yo += dy
        self._c.move(self.id+'label', dx, dy)
        # Leader line
        self._ldr_y = self.label_y + 10
        if (self.label_x - self.x) > 0:
            self._ldr_x = self.label_x
        else:
            self._ldr_x = self.label_x + self.label_width
        ldr_x_offset, ldr_y_offset = self._ldr_x-self.x, self._ldr_y-self.y
        self.label_heading = 90.0-degrees(atan2(ldr_y_offset, ldr_x_offset))
        self._c.coords(self.id+'leader', self.x, self.y, self._ldr_x, self._ldr_y)
        self._c.coords(self.id + 'wideleader', self.x, self.y, self._ldr_x, self._ldr_y)

    def reposition_label(self, newx, newy):
        """Repositions the label based on the new end of the leader line"""
        # self._l.reformat()  # Make sure we have the current width
        (x, y) = self.x, self.y
        ldr_x_offset = newx - x
        ldr_y_offset = newy - y
        # l_xo and lyo are the offsets of the label with respect to the plot
        if ldr_x_offset > 0.:  
            new_l_x = x+ldr_x_offset
            new_l_y = y+ldr_y_offset - 10
        else:
            new_l_x = x+ldr_x_offset - self.label_width
            new_l_y = y+ldr_y_offset - 10
        self.label_heading = 90.0-degrees(atan2(ldr_y_offset, ldr_x_offset))
        self.label_radius = sqrt(ldr_y_offset**2+ldr_x_offset**2)
        self._c.coords(self.id+'leader', self.x, self.y, newx, newy)
        self._c.coords(self.id + 'wideleader', self.x, self.y, newx, newy)

        dx = new_l_x-self.label_x
        dy = new_l_y-self.label_y
        self.label_x += dx
        self.label_y += dy
        self.label_xo += dx
        self.label_yo += dy
        self._c.move(self.id+'label', dx, dy)
        
        (self._ldr_x, self._ldr_y) = (newx, newy)
        
    def add_timer_callback(self, f, *kw):
        """Callbacks passed as arguments will be called within the next 500ms"""
        VisTrack.timer_callbacks.append((f, kw))
        
        def timer():
            """Calls each of the callbacks that have been set for this event"""
            tc = self.timer_callbacks
            # Reset the timer so that the callbacks may set up new timer
            # callbacks if required
            VisTrack.timer_callbacks = []
            VisTrack.timer_id = None
            VisTrack.timer_state = not VisTrack.timer_state
            
            if self.timer_state == VisTrack.OFF:
                # Force execution of the timer to make sure
                # VisTrack.timer_state will end up in state ON 
                self.add_timer_callback(lambda: True)
                
            # Call callbacks            
            for f, kw in tc:
                try: f(*kw)
                except:
                    logging.debug("Error while executing timer", exc_info=True)
        
        if not VisTrack.timer_id:
            VisTrack.timer_id = reactor.callLater(0.5, timer)
            
    def reset_timer(self):
        if VisTrack.timer_id:
            self.timer_id.cancel()
        VisTrack.timer_callbacks = []                    
    
    # Getters and setters. This gives much better perfomance than
    # using the __setattr__ method
    def update_item_color(self, item, basecolor):
        if item.color.get_basecolor() == basecolor:
            pass
        else:
            item.color.set(basecolor)

    def _veh_color(self):
        return self.VEHICLE_PVH_COLOR if getattr(self, '_has_pvh', False) else self.VEHICLE_COLOR

    def reconfigure(self):
        # Sets label_format and color settings
        sacta_mode = self.rd.fir.sacta_mode[self.rd.sector.split(",")[0]]
        # Vehiculos con Plan de Vehiculo (parametro de escenario 'pvh'): formato y color propios
        try:
            pvh_on = bool(self.rd.fir.param('pvh', False))
        except AttributeError:
            pvh_on = False
        _veh_fmt = 'atc-veh-pvh' if getattr(self, '_has_pvh', False) else 'atc-veh'
        if self.mode == 'atc':
            if sacta_mode == 'UCS':
                if self._assumed:
                    if self.rules == 'VEH':
                        self.label_format = _veh_fmt
                    else:
                        self.label_format = 'atc-ucs'
                    if self.local_dep and self.rules != 'VEH':
                        self.color.set(self.ASSUMED_COLOR_UCS_DEP)
                    elif self.local_des and self.rules != 'VEH':
                        self.color.set(self.ASSUMED_COLOR_UCS)
                    elif self.rules == 'VEH' and pvh_on:
                        self.color.set(self._veh_color())
                    else:
                        # self.color.set(self.INCOMING_COLOR)
                        self.color.set(self.ASSUMED_COLOR_UCS)  # DCM. LEST
                else:
                    if self.rules == 'VEH':
                        self.label_format = _veh_fmt
                        if pvh_on:
                            self.color.set(self._veh_color())
                    else:
                        self.label_format = 'atc-na'
                        self.color.set(self.NONASSUMED_COLOR_UCS)

            elif sacta_mode == 'OSF':
                if self.rules == 'VEH':
                    self.label_format = _veh_fmt
                else:
                    if self.local_des:
                        self.label_format = 'atc-osf-llegadas'
                    else:
                        self.label_format = 'atc-osf'
                if self.rules == 'VEH' and pvh_on:
                    self.color.set(self._veh_color())
                elif self.local_dep and self.rules != 'VEH':
                    if not self.assumed:
                        self.color.set(self.OSF_NOT_ASSUMED_DEP)
                    else:
                        self.color.set(self.OSF_ASSUMED_DEP)
                    # self.color.set(self.ASSUMED_COLOR_PICT_DEP)
                elif self.local_des and self.rules != 'VEH':
                    if not self.assumed:
                        self.color.set(self.OSF_NOT_ASSUMED_ARRIVAL)
                    else:
                        self.color.set(self.OSF_ASSUMED_ARRIVAL)
                    # self.color.set(self.ASSUMED_COLOR_PICT)
                else:
                    # self.color.set(self.INCOMING_COLOR)
                    if not self.assumed:
                        self.color.set(self.INCOMING_COLOR)
                    else:
                        self.color.set(self.OSF_ASSUMED_ARRIVAL)

            else:
                self.label_format = 'atc-pict'
                if self.rules == 'VEH' and pvh_on:
                    self.label_format = _veh_fmt
                    self.color.set(self._veh_color())
                elif self.local_dep and self.rules == 'VEH':
                    self.label_format = 'atc-veh'
                    self.color.set(self.INCOMING_COLOR)
                elif self.assumed:
                    self.color.set(self.ASSUMED_COLOR_UCS)
                else:
                    self.color.set(self.NONASSUMED_COLOR_UCS)

        elif self.mode in ['pp', 'pp-mach']:
            if self.rules == 'VEH':
                self.label_format = 'pp-veh'
            else:
                self.label_format = self.mode
            if self._assumed:
                if self.local_dep and self.rules != 'VEH':
                    self.color.set(self.ASSUMED_COLOR_PICT_DEP)
                elif self.local_des and self.rules != 'VEH':
                    self.color.set(self.ASSUMED_COLOR_PICT)
                elif self.rules == 'VEH':
                    self.color.set(self._veh_color())
                else:
                    self.color.set(self.ASSUMED_COLOR_PICT_OverFlight)
            else:
                if self._initialized:
                    self.color.set(self.NONASSUMED_COLOR)
                else:
                    self.color.set(self.INCOMING_COLOR)

        elif self.mode == 'atc-nocorrel':
            self.label_format = 'atc-nocorrel'
            self.color.set(self.INCOMING_COLOR)

            if self.rd.smrOn:
                self.label_format = 'atc-smr'
                if self.local_dep and self.rules != 'VEH':
                    self.color.set(self.ASSUMED_COLOR_PICT_DEP)
                elif self.local_des and self.rules != 'VEH':
                    self.color.set(self.ASSUMED_COLOR_PICT)
                else:
                    self.color.set(self.INCOMING_COLOR)

        #self._l.cs.color.set(self.color.get_basecolor()) hacemos comprobaciones para que el color de cs sea blanco o rojo en caso de release atc pos o warning respectivamente, y no se vea afectado por el cambio de modo
        if self._release_atc_pos:
            self._l.cs.color.set('white')
        elif self._OSF_warning:
            self._l.cs.color.set('red')
        else:
            self._l.cs.color.set(self.color.get_basecolor())

        self._l.osf_act.color.set(self.color.get_basecolor())
        # Prediccion CATC: color morado en fase (indicador visual, no alerta)
        if getattr(self, 'catc_pred', False):
            self._l.osf_act.color.set('#CC33FF')
        self._l.to_do.color.set(self.color.get_basecolor())
        self._l.alt.color.set(self.color.get_basecolor())
        self._l.rate.color.set(self.color.get_basecolor())
        self._l.cfl.color.set(self.color.get_basecolor())
        self._l.hdg.color.set(self.color.get_basecolor())
        self._l.stand_sid.color.set(self.color.get_basecolor())
        self._l.stand.color.set(self.color.get_basecolor())
        self._l.echo.color.set(self.color.get_basecolor())
        self._l.rutrod.color.set(self.color.get_basecolor())
        self._l.pvh_notes.color.set(self.color.get_basecolor())
        self._l.gate.color.set(self.color.get_basecolor())
        self._l.holdp.color.set(self.color.get_basecolor())
        self._l.sidok.color.set(self.color.get_basecolor())
        self._l.lrwy.color.set(self.color.get_basecolor())
        # VEH con PVH: pista en azul
        if self.rules == 'VEH' and self.lrwy and getattr(self, '_has_pvh', False):
            self._l.lrwy.color.set('#5599FF')
        self._l.spc.color.set(self.color.get_basecolor())
        self._l.ltype.color.set(self.color.get_basecolor())
        self._l.trans.color.set(self.color.get_basecolor())
        self._l.mach.color.set(self.color.get_basecolor())
        self._l.gs.color.set(self.color.get_basecolor())
        # if self._l.wake.vt.assumed and self._l.wake.vt.wake in ('H', 'J'):
        if self._l.wake.vt.wake in ('H', 'H-', 'H+', 'J'):
            self._l.wake.color.set('yellow')
        # elif self._l.wake.vt.assumed and self._l.wake.vt.wake in ('L'):
        elif self._l.wake.vt.wake in ('L', 'L+'):
            self._l.wake.color.set('white')
        else:
            self._l.wake.color.set(self.color.get_basecolor())
        self._l.thr_nm.color.set(self.color.get_basecolor())
        self._l.thr_min.color.set(self.color.get_basecolor())
        self._l.tfto.color.set(self.color.get_basecolor())
        if self.visible:
            self.redraw()

    def color_change(self):
        # Respetar color rojo de WARNING
        if self._OSF_warning:
            self._l.cs.color.set('red')
        else:
            self._l.cs.color.set(self.color.get_basecolor())
        self._l.osf_act.color.set(self.color.get_basecolor())
        if getattr(self, 'catc_pred', False):
            self._l.osf_act.color.set('#CC33FF')
        self._l.to_do.color.set(self.color.get_basecolor())
        self._l.hdg.color.set(self.color.get_basecolor())
        self._l.alt.color.set(self.color.get_basecolor())
        self._l.rate.color.set(self.color.get_basecolor())
        self._l.cfl.color.set(self.color.get_basecolor())
        self._l.stand_sid.color.set(self.color.get_basecolor())
        self._l.stand.color.set(self.color.get_basecolor())
        self._l.echo.color.set(self.color.get_basecolor())
        self._l.rutrod.color.set(self.color.get_basecolor())
        self._l.pvh_notes.color.set(self.color.get_basecolor())
        self._l.gate.color.set(self.color.get_basecolor())
        self._l.holdp.color.set(self.color.get_basecolor())
        self._l.sidok.color.set(self.color.get_basecolor())
        self._l.lrwy.color.set(self.color.get_basecolor())
        # VEH con PVH: pista en azul
        if self.rules == 'VEH' and self.lrwy and getattr(self, '_has_pvh', False):
            self._l.lrwy.color.set('#5599FF')
        self._l.spc.color.set(self.color.get_basecolor())
        self._l.ltype.color.set(self.color.get_basecolor())
        self._l.trans.color.set(self.color.get_basecolor())
        self._l.mach.color.set(self.color.get_basecolor())
        self._l.gs.color.set(self.color.get_basecolor())
        # if self._l.wake.vt.assumed and self._l.wake.vt.wake in ('H', 'J'):
        if self._l.wake.vt.wake in ('H', 'H-', 'H+', 'J'):
            self._l.wake.color.set('yellow')
        # elif self._l.wake.vt.assumed and self._l.wake.vt.wake in ('L'):
        elif self._l.wake.vt.wake in ('L', 'L+'):
            self._l.wake.color.set('white')
        else:
            self._l.wake.color.set(self.color.get_basecolor())
        self._l.thr_nm.color.set(self.color.get_basecolor())
        self._l.thr_min.color.set(self.color.get_basecolor())
        self._l.tfto.color.set(self.color.get_basecolor())
        self.refresh_leader()
        self.redraw_h()  # History
        self.redraw_sv()  # Speed vector
        self.redraw_p()

    def get_visible(self): return self._visible

    def set_visible(self, value):
        if value == self._visible:
            return
        self._visible = value
        if value:
            self.redraw()
        else:
            self.delete()
    visible = property(get_visible, set_visible)
    
    def get_mode(self): return self._mode

    def set_mode(self, value):
        if value == self._mode:
            return
        self._mode = value
        self.reconfigure()
    mode = property(get_mode, set_mode)
    
    def get_label_format(self): return self._label_format

    def set_label_format(self, value):
        self._label_format = self._l.format = value
    label_format = property(get_label_format, set_label_format)
    
    def get_selected(self): return self._selected

    def set_selected(self, value):
        if value == self._selected:
            return
        self._selected = value
        if self.visible:
            self.redraw_l()
    selected = property(get_selected, set_selected)
    
    def get_assumed(self): return self._assumed

    def set_assumed(self, value):
        if value == self._assumed:
            return
        self._assumed = value
        # Keep information that the traffic has been assumed to know that is not still incoming
        if self._assumed:
            self._initialized = True
        self.reconfigure()
    assumed = property(get_assumed, set_assumed)

    def get_plot_only(self): return self._plot_only

    def set_plot_only(self, value):
        if value == self._plot_only:
            return
        self._plot_only = value
        self.redraw()
    plot_only = property(get_plot_only, set_plot_only)
        
    def get_pac(self): return self._pac

    def set_pac(self, value):
        if value == self._pac:
            return
        self._pac = value
        if self.visible:
            self._item_refresh_list.append('pac')
            self.redraw_l()
            if value and self.plot_only:
                self.plot_only = False
    pac = property(get_pac, set_pac)
        
    def get_vac(self): return self._vac

    def set_vac(self, value):
        if value == self._vac:
            return
        self._vac = value
        if self.visible:
            self._item_refresh_list.append('vac')
            self.redraw_l()
            if value and self.plot_only:
                self.plot_only = False
    vac = property(get_vac, set_vac)

    def get_x(self): return self._x

    def set_x(self, value):
        if value == self._x:
            return
        self._x = value
        (self._wx, self._wy) = self.undo_scale((self.x, self.y))
    x = property(get_x, set_x)
        
    def get_y(self): return self._y

    def set_y(self, value):
        if value == self._y:
            return
        self._y = value
        (self._wx, self._wy) = self.undo_scale((self.x, self.y))
    y = property(get_y, set_y)

    def get_wx(self): return self._wx

    def set_wx(self, value):
        if value == self._wx:
            return
        self._wx = value
        (self._x, self._y) = self.do_scale((self.wx, self.wy))
    wx = property(get_wx, get_wx)
    
    def get_wy(self): return self._wy

    def set_wy(self, value):
        if value == self._wy:
            return
        self._wy = value
        (self._x, self._y) = self.do_scale((self.wx, self.wy))
    wy = property(get_wy, get_wy)
    
    def get_intensity(self): return self._intensity

    def set_intensity(self, value):
        # TODO setting the intensity should not force a full redraw.
        if value == self._intensity:
            return
        self._intensity = value
        # refresh Label items
        self._l.cs.color.set_intensity(value)
        self._l.osf_act.color.set_intensity(value)
        self._l.to_do.color.set_intensity(value)
        self._l.alt.color.set_intensity(value)
        self._l.rate.color.set_intensity(value)
        self._l.cfl.color.set_intensity(value)
        self._l.stand_sid.color.set_intensity(value)
        self._l.stand.color.set_intensity(value)
        self._l.echo.color.set_intensity(value)
        self._l.rutrod.color.set_intensity(value)
        self._l.pvh_notes.color.set_intensity(value)
        self._l.gate.color.set_intensity(value)
        self._l.holdp.color.set_intensity(value)
        self._l.sidok.color.set_intensity(value)
        self._l.lrwy.color.set_intensity(value)
        self._l.spc.color.set_intensity(value)
        self._l.ltype.color.set_intensity(value)
        self._l.trans.color.set_intensity(value)
        self._l.mach.color.set_intensity(value)
        self._l.gs.color.set_intensity(value)
        self._l.wake.color.set_intensity(value)
        self._l.thr_nm.color.set_intensity(value)
        self._l.thr_min.color.set_intensity(value)
        self._l.tfto.color.set_intensity(value)
        self._l.hdg.color.set_intensity(value)
        # refresh leader label
        self.refresh_leader()
        # Redraw plot, speed vector and history points
        self.redraw_h()
        self.redraw_sv()
        self.redraw_p()

    intensity = property(get_intensity, set_intensity)
   
    def get_l_font_size(self): return self._l_font_size

    def set_l_font_size(self, value):
        if value == self._l_font_size:
            return
        self._l_font_size = value
        if self.auto_separation:
            self.label_radius = value*3
        # self.redraw_l()
        self._l.reformat()
    l_font_size = property(get_l_font_size, set_l_font_size)
   
    def get_flashing(self): return self._flashing

    def set_flashing(self, value):
        if value == self._flashing:
            return
        self._flashing = value

        def flash_timer():
            if self.timer_state:
                # Si está transferido, siempre parpadea en BLANCO (ignorando warning u otros estados)
                if self.release_atc_pos:
                    self._l.cs.color.set('white')
                elif self.alt == 'GND':
                    self._l.cs.color.set(self.ASSUMED_COLOR_PICT_DEP)
                else:
                    self._l.cs.color.set(self.NONASSUMED_COLOR)
            else:
                self._l.cs.color.set('black')
            if self.flashing:
                self.add_timer_callback(flash_timer)
            else:
                # Al dejar de parpadear, restaurar color según estado
                if self.release_atc_pos:
                    self._l.cs.color.set('white')
                elif self.OSF_warning:
                    self._l.cs.color.set('red')
                else:
                    self._l.cs.color.set(self.color.get_basecolor())
            self._l.refresh('cs')
        if value:
            self.add_timer_callback(flash_timer)
        else:
            self.plot_only = False
    flashing = property(get_flashing, set_flashing)

    def get_release_atc_pos(self): return self._release_atc_pos

    def set_release_atc_pos(self, value):
        if value == self._release_atc_pos:
            return
        self._release_atc_pos = value
        if value:
            # Cuando se transfiere, poner en blanco (el flashing ya manejará el parpadeo)
            self._l.cs.color.set('white')
        else:
            # Cuando se asume, restaurar color según estado
            if self.OSF_warning:
                self._l.cs.color.set('red')  # Si tiene warning, ponerlo en rojo
            else:
                self._l.cs.color.set(self.color.get_basecolor())
        self._l.refresh('cs')
    release_atc_pos = property(get_release_atc_pos, set_release_atc_pos)

    def get_OSF_warning(self): return self._OSF_warning

    def set_OSF_warning(self, value):
        if value == self._OSF_warning:
            return
        self._OSF_warning = value
        if value:
            # Si está transferido, NO cambiar a rojo (seguir en blanco parpadeando)
            if not self.release_atc_pos:
                self._l.cs.color.set('red')
        else:
            # Si ya no tiene warning, restaurar color base (si no está transferido)
            if not self.release_atc_pos:
                self._l.cs.color.set(self.color.get_basecolor())
        self._l.refresh('cs')
    OSF_warning = property(get_OSF_warning, set_OSF_warning)

    def get_alert_severity(self): return self._alert_severity

    def set_alert_severity(self, value):
        if value == self._alert_severity:
            return
        self._alert_severity = value
        self._update_alert_display()
    alert_severity = property(get_alert_severity, set_alert_severity)

    def get_alert_text(self): return self._alert_text_obj

    def set_alert_text(self, value):
        self._alert_text_obj = value
        self._update_alert_display()
    alert_text = property(get_alert_text, set_alert_text)

    def set_active_alerts(self, alerts):
        """Actualiza la lista completa de alertas activas (para ventana de alertas)."""
        self._active_alerts = alerts if alerts else []
        # Si todas reconocidas, parar parpadeo
        if self._active_alerts and all(a.acknowledged for a in self._active_alerts):
            self._stop_alert_blink()
            self._update_alert_display()

    def _update_alert_display(self):
        """Crea, actualiza o elimina el texto de alerta encima de la etiqueta.

        Comportamiento SACTA:
        - Solo el campo OG ALERTAS lleva color de severidad (rojo VIO / amarillo WNG).
        - Click BI sobre el texto = asumir (acknowledge). Click BD = abrir ventana individual.
        - Al asumir: texto pasa al color de la etiqueta, parpadeo para, marco rojo desaparece.
        - Marco rojo rectangular alrededor de la etiqueta solo para VIO no asumido.
        - El texto solo desaparece cuando la alerta se resuelve.
        """
        # Defensa: si la etiqueta no esta visible (filtro FGND u otro), no
        # recrear items en el canvas y parar el parpadeo. El callback blink()
        # ya quedo cortado en delete(), pero puede quedar una tick encolada
        # en VisTrack.timer_callbacks; este check evita que esa tick
        # ultima genere texto huerfano sobre el canvas.
        if not self.visible:
            self._stop_alert_blink()
            return

        c = self._c
        severity = self._alert_severity
        alert = self._alert_text_obj

        if severity == 0 or alert is None:
            # Sin alerta: borrar item, marco y parar parpadeo
            if self._alert_item is not None:
                c.delete(self._alert_item)
                self._alert_item = None
            if self._alert_frame_item is not None:
                c.delete(self._alert_frame_item)
                self._alert_frame_item = None
            self._stop_alert_blink()
            return

        # Determinar texto y color
        if severity >= 2:  # VIO
            text = 'VIO'
            sev_color = 'red'
        else:  # WNG
            text = 'WNG'
            sev_color = 'yellow'

        acknowledged = getattr(alert, 'acknowledged', False)

        if acknowledged:
            # Asumida: color de la etiqueta (no severidad), sin parpadeo
            color = self.color.get()
        elif not self._alert_blink_on:
            color = 'black'  # Fase "off" del parpadeo
        else:
            color = sev_color

        # Posicion: encima de la etiqueta
        lf = self._l_font
        line_h = lf.metrics('ascent') if lf else 12
        ax = self.label_x + 2
        ay = self.label_y - line_h - 2

        if self._alert_item is not None:
            try:
                c.coords(self._alert_item, ax, ay)
                c.itemconfig(self._alert_item, text=text, fill=color)
            except Exception:
                self._alert_item = None

        if self._alert_item is None:
            try:
                self._alert_item = c.create_text(
                    ax, ay, text=text, fill=color,
                    anchor='nw', font=lf,
                    tags=(self.id, self.id + 'alert', self.id + 'label', 'track'))
                # Bind clic izquierdo para asumir alerta, derecho para ventana
                ra_tag_bind(c, self._alert_item, '<Button-1>', self._acknowledge_alert)
                ra_tag_bind(c, self._alert_item, '<Button-3>', self.show_alert_window)
            except Exception:
                pass

        # Marco rojo rectangular: solo para VIO no asumido
        show_frame = (severity >= 2 and not acknowledged)
        if show_frame:
            # Calcular bbox de la etiqueta completa
            try:
                bbox = c.bbox(self.id + 'label')
                if bbox:
                    fx1, fy1, fx2, fy2 = bbox
                    pad = 2
                    if self._alert_frame_item is not None:
                        c.coords(self._alert_frame_item,
                                 fx1 - pad, fy1 - pad, fx2 + pad, fy2 + pad)
                        c.itemconfig(self._alert_frame_item, outline='red')
                    else:
                        self._alert_frame_item = c.create_rectangle(
                            fx1 - pad, fy1 - pad, fx2 + pad, fy2 + pad,
                            outline='red', width=2, fill='',
                            tags=(self.id, self.id + 'alertframe', 'track'))
            except Exception:
                pass
        else:
            if self._alert_frame_item is not None:
                c.delete(self._alert_frame_item)
                self._alert_frame_item = None

        # Iniciar parpadeo si no reconocida
        if not acknowledged and not self._alert_blinking:
            self._start_alert_blink()

    def _start_alert_blink(self):
        """Inicia parpadeo del texto de alerta."""
        if self._alert_blinking:
            return
        self._alert_blinking = True
        self._alert_blink_on = True

        def blink():
            if not self._alert_blinking:
                return
            self._alert_blink_on = not self._alert_blink_on
            self._update_alert_display()
            if self._alert_blinking:
                self.add_timer_callback(blink)
        self.add_timer_callback(blink)

    def _stop_alert_blink(self):
        """Para el parpadeo del texto de alerta."""
        self._alert_blinking = False
        self._alert_blink_on = True

    def _acknowledge_alert(self, e=None):
        """Asume todas las alertas activas de este movil.

        Envia mensaje al GTA para que la asuncion sea global (todos los UCS la ven).
        Tambien aplica localmente para respuesta inmediata.
        """
        # Aplicar localmente para respuesta visual inmediata
        for a in self._active_alerts:
            a.acknowledged = True
        self._stop_alert_blink()
        self._update_alert_display()
        # Enviar al GTA para asuncion global
        try:
            self.rd.sendMessage({"message": "ack_alert", "cs": self.cs})
        except Exception:
            pass

    def show_alert_window(self, e=None):
        """Ventana pequena de alertas estilo SACTA.

        Primera fila: fondo rosa con callsign + boton expandir (abre tabular global).
        Debajo: max 5 filas de descripciones cortas en color de severidad, scroll si mas.
        """
        alerts = self._active_alerts
        if not alerts:
            return

        win = tix.Toplevel()
        win.configure(bg='black')
        win.overrideredirect(True)
        win.attributes('-topmost', True)

        if e:
            win.geometry("+%d+%d" % (e.x_root + 10, e.y_root + 10))

        row_font = ('Helvetica', 9)
        hdr_font = ('Helvetica', 9, 'bold')

        # Hacer la ventana draggable desde la cabecera
        win._drag_x = 0
        win._drag_y = 0

        def start_drag(evt):
            win._drag_x = evt.x
            win._drag_y = evt.y

        def do_drag(evt):
            x = win.winfo_x() + evt.x - win._drag_x
            y = win.winfo_y() + evt.y - win._drag_y
            win.geometry("+%d+%d" % (x, y))

        # Fila 1: fondo rosa con callsign + boton expandir + X cerrar
        hdr = tix.Frame(win, bg='#CC6688', bd=0)
        hdr.pack(fill='x')
        hdr.bind('<Button-1>', start_drag)
        hdr.bind('<B1-Motion>', do_drag)
        hdr_lbl = tix.Label(hdr, text=self.cs, bg='#CC6688', fg='white',
                  font=hdr_font, anchor='w', padx=4, pady=1)
        hdr_lbl.pack(side='left', fill='x', expand=True)
        hdr_lbl.bind('<Button-1>', start_drag)
        hdr_lbl.bind('<B1-Motion>', do_drag)

        def open_tabular():
            win.destroy()
            self._show_alert_tabular()

        tix.Button(hdr, text=u'\u25B2', command=open_tabular,
                   bg='#CC6688', fg='white', font=('Helvetica', 7),
                   bd=0, padx=3, pady=0, highlightthickness=0
                   ).pack(side='right')
        tix.Button(hdr, text='X', command=win.destroy,
                   bg='#AA4466', fg='white', font=('Helvetica', 7, 'bold'),
                   bd=0, padx=4, pady=0, highlightthickness=0
                   ).pack(side='right')

        # Filas de descripcion de alertas (max 5 visibles, scroll si mas)
        list_frame = tix.Frame(win, bg='black')
        list_frame.pack(fill='both', expand=True)

        sorted_alerts = sorted(alerts, key=lambda x: x.priority_key())

        if len(sorted_alerts) > 5:
            canvas = tix.Canvas(list_frame, bg='black', highlightthickness=0,
                                width=180, height=5 * 16)
            scrollbar = tix.Scrollbar(list_frame, orient='vertical',
                                      command=canvas.yview)
            inner = tix.Frame(canvas, bg='black')
            canvas.create_window((0, 0), window=inner, anchor='nw')
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')

            def on_configure(evt):
                canvas.configure(scrollregion=canvas.bbox('all'))
            inner.bind('<Configure>', on_configure)
            target = inner
        else:
            target = list_frame

        def _popup_action(a):
            """Texto de accion para popup: N+auth o WRWY_rwy."""
            sub = a.subtype or ''
            if a.alert_type == 'INCW':
                if sub.startswith('MULT_'):
                    sub = sub[5:]
                if sub == 'L/U':
                    return 'NL/U'
                if sub.startswith('DEP'):
                    return 'NDEP'
                if sub.startswith('ARR'):
                    return 'NLDG'
                if sub == 'CROSS':
                    return 'NCRU'
                if sub == 'VEH':
                    return 'NVEH'
                return sub
            elif a.alert_type == 'CMAC':
                if sub.endswith('_PI'):
                    return 'WRWY_%s' % (a.runway or '')
                if sub == 'ALIN_NA':
                    return 'NALIN'
                if sub == 'DEP_NA':
                    return 'NDEP'
                if sub == 'ARR_NA':
                    return 'NLDG'
                if sub == 'CRU_NA':
                    return 'NCRU'
                if sub == 'ENT_NA':
                    return 'NENT'
                if sub == 'NO_CONTACTO':
                    return 'NCTC'
                if sub.startswith('AUT_CERR'):
                    return 'NCERR'
                return sub
            return ''

        for a in sorted_alerts:
            sev_color = 'red' if a.severity >= 2 else 'yellow'
            sev_txt = 'VIO' if a.severity >= 2 else 'WNG'
            rwy = a.runway or ''
            if a.alert_type in ('INCW', 'CMAC'):
                action = _popup_action(a)
                desc = '%s %s RWY %s %s' % (a.alert_type, sev_txt, rwy, action)
            elif a.alert_type == 'CATC':
                sub = a.subtype or ''
                if sub.startswith('CCMAC'):
                    tag = 'CCMAC'
                elif sub.startswith('CINCW'):
                    tag = 'CINCW'
                else:
                    tag = 'CATC'
                rel = (' vs %s' % a.related_cs) if a.related_cs else ''
                desc = '%s %s RWY %s%s' % (tag, sev_txt, rwy, rel)
            else:
                desc = '%s %s %s' % (a.alert_type, sev_txt, a.description)
            tix.Label(target, text=desc, bg='black', fg=sev_color,
                      font=row_font, anchor='w', padx=4, pady=1
                      ).pack(fill='x')

        win.bind('<Escape>', lambda ev: win.destroy())
        win.bind('<FocusOut>', lambda ev: win.destroy())
        win.focus_set()

    def _show_alert_tabular(self):
        """Ventana grande tabular de alertas estilo SACTA.

        Muestra TODAS las alertas activas de todos los moviles, organizadas
        en secciones RW, AS, CMAC, CATC. Se actualiza cada segundo.
        Contenido ocupa todo el ancho. Texto de datos en blanco.
        Formato fila: V/VEH  CALLSIGN  DESCRIPCION  FASE  PISTA
        Draggable y redimensionable.
        """
        rd = self.rd
        if hasattr(rd, '_alert_tabular_win') and rd._alert_tabular_win is not None:
            try:
                rd._alert_tabular_win.lift()
                return
            except Exception:
                rd._alert_tabular_win = None

        win = tix.Toplevel()
        win.configure(bg='black')
        win.attributes('-topmost', True)
        win.title('')
        win.geometry("380x340")
        win.minsize(250, 200)
        rd._alert_tabular_win = win

        row_font = ('Helvetica', 9)
        hdr_font = ('Helvetica', 9, 'bold')
        section_bg = '#555555'
        section_fg = 'white'
        data_bg = 'black'
        data_fg = 'white'
        title_bg = '#AAAAAA'

        # Seccion -> tipo de alerta
        SECTION_MAP = {
            'RW': 'INCW',
            'AS': 'SAPW',
            'CMAC': 'CMAC',
            'CATC': 'CATC',
        }
        SECTIONS = ['RW', 'AS', 'CMAC', 'CATC']

        # Fila titulo: gris claro con X a la derecha
        title_bar = tix.Frame(win, bg=title_bg, bd=0)
        title_bar.pack(fill='x', side='top')
        tix.Label(title_bar, text='', bg=title_bg,
                  font=hdr_font).pack(side='left', fill='x', expand=True)

        def close_tabular():
            rd._alert_tabular_win = None
            win.destroy()

        tix.Button(title_bar, text='X', command=close_tabular,
                   bg=title_bg, fg='black', font=('Helvetica', 8, 'bold'),
                   bd=0, padx=5, pady=1, highlightthickness=0
                   ).pack(side='right')

        # Contenedor principal que ocupa todo el espacio restante
        # pack_propagate(False) impide que el contenido hijo agrande la ventana
        main = tix.Frame(win, bg=data_bg)
        main.pack(fill='both', expand=True, side='top')
        main.pack_propagate(False)

        # Crear frames fijos para cada seccion (header + area de datos)
        sec_frames = {}
        for sec_name in SECTIONS:
            # Cabecera de seccion
            hdr = tix.Label(main, text=sec_name, bg=section_bg, fg=section_fg,
                            font=hdr_font, anchor='w', padx=6, pady=2)
            hdr.pack(fill='x', side='top')

            # Area de datos: se expande para llenar espacio
            data_area = tix.Frame(main, bg=data_bg)
            data_area.pack(fill='both', expand=True, side='top')
            sec_frames[sec_name] = data_area

        def refresh():
            if rd._alert_tabular_win is None:
                return
            try:
                win.winfo_exists()
            except Exception:
                rd._alert_tabular_win = None
                return

            # Preservar solo la posicion (no el tamano) antes de actualizar contenido
            saved_x = win.winfo_x()
            saved_y = win.winfo_y()

            # Mapeo de fases internas a lenguaje de controlador
            _PHASE_MAP = {
                'TOU': 'TAX', 'TIN': 'TAX', 'TXR': 'TAX',
                'LND': 'LDG', 'LDR': 'LDG',
                'AIR': 'DEP', 'DPR': 'DEP',
                'INC': '---', 'PRE': '---',
                'SUR': 'S/U', 'PBR': 'P/B',
                'CRR': 'CRU', 'LIB': 'LIB', 'ENT': 'ENT', 'ENR': 'ENT',
            }

            def _phase_txt(raw):
                return _PHASE_MAP.get(raw, raw) if raw else ''

            def _rw_cmac_action(a):
                """Texto de accion para RW/CMAC: N+auth o WRWY_rwy."""
                sub = a.subtype or ''
                if a.alert_type == 'INCW':
                    if sub.startswith('MULT_'):
                        sub = sub[5:]
                    if sub == 'L/U':
                        return 'NL/U'
                    if sub.startswith('DEP'):
                        return 'NDEP'
                    if sub.startswith('ARR'):
                        return 'NLDG'
                    if sub == 'CROSS':
                        return 'NCRU'
                    if sub == 'VEH':
                        return 'NVEH'
                    return sub
                elif a.alert_type == 'CMAC':
                    if sub.endswith('_PI'):
                        return 'WRWY_%s' % (a.runway or '')
                    if sub == 'ALIN_NA':
                        return 'NALIN'
                    if sub == 'DEP_NA':
                        return 'NDEP'
                    if sub == 'ARR_NA':
                        return 'NLDG'
                    if sub == 'CRU_NA':
                        return 'NCRU'
                    if sub == 'ENT_NA':
                        return 'NENT'
                    if sub == 'NO_CONTACTO':
                        return 'NCTC'
                    if sub.startswith('AUT_CERR'):
                        return 'NCERR'
                    return sub
                return ''

            def _catc_subtype_short(sub):
                """Texto corto de subtipo CATC."""
                if not sub:
                    return ''
                if sub.startswith('CCMAC'):
                    return 'CCMAC'
                if sub.startswith('CINCW'):
                    return 'CINCW'
                if sub.startswith('MISMA'):
                    return 'MISMA'
                if sub.startswith('OPUEST'):
                    return 'OPUES'
                if sub.startswith('CRUZAD'):
                    return 'CRUZA'
                if sub.startswith('CONVER'):
                    return 'CONV'
                return sub[:6]

            # Lookup de fase y pista por callsign (para filas pareadas CATC)
            cs_phase = {}
            cs_catc_rwy = {}
            cs_is_veh = {}
            for vt in rd.tracks:
                cs_phase[vt.cs] = getattr(vt, '_osf_act', '')
                cs_is_veh[vt.cs] = (getattr(vt, 'rules', '') == 'VEH')
                for a in getattr(vt, '_active_alerts', []):
                    if a.alert_type == 'CATC' and a.related_cs:
                        cs_catc_rwy.setdefault(vt.cs, {})[a.related_cs] = a.runway

            # Recopilar alertas de todos los tracks
            all_alerts = []
            seen_pairs = set()
            for vt in rd.tracks:
                for a in getattr(vt, '_active_alerts', []):
                    is_veh = getattr(vt, 'rules', '') == 'VEH'
                    osf_pof = getattr(vt, '_osf_act', '---')
                    if a.related_cs:
                        pair_key = frozenset([vt.cs, a.related_cs, a.subtype or ''])
                        if pair_key in seen_pairs:
                            continue
                        seen_pairs.add(pair_key)
                    all_alerts.append((vt.cs, a, is_veh, osf_pof))

            # Agrupar por seccion
            sections = {}
            for s in SECTIONS:
                sections[s] = []
            for cs, a, is_veh, osf_pof in all_alerts:
                for sec_name, atype in SECTION_MAP.items():
                    if a.alert_type == atype:
                        sections[sec_name].append((cs, a, is_veh, osf_pof))
                        break

            # Actualizar cada seccion
            for sec_name in SECTIONS:
                area = sec_frames[sec_name]
                for w in area.winfo_children():
                    w.destroy()

                for cs, a, is_veh, osf_pof in sorted(
                        sections[sec_name],
                        key=lambda x: x[1].priority_key()):
                    tipo = 'VEH' if is_veh else 'V'
                    runway = a.runway if a.runway else ''
                    phase = _phase_txt(osf_pof)

                    if sec_name in ('RW', 'CMAC'):
                        # RW/CMAC: 3a columna = accion (NLDG, NDEP, WRWY_24R...)
                        action = _rw_cmac_action(a)
                        if a.related_cs:
                            text = ' %-4s %-8s %-10s %-5s %s' % (
                                tipo, cs, action, runway, a.related_cs)
                        else:
                            text = ' %-4s %-8s %-10s %s' % (
                                tipo, cs, action, runway)
                        lbl = tix.Label(area, text=text, bg=data_bg, fg=data_fg,
                                        font=row_font, anchor='w', padx=2, pady=0)
                        lbl.pack(fill='x', side='top')

                    elif sec_name == 'CATC':
                        # CATC: 5 columnas - tipo | cs | subtipo | fase | pista
                        sub_short = _catc_subtype_short(a.subtype)
                        text = ' %-4s %-8s %-6s %-5s %s' % (
                            tipo, cs, sub_short, phase, runway)
                        lbl = tix.Label(area, text=text, bg=data_bg, fg=data_fg,
                                        font=row_font, anchor='w', padx=2, pady=0)
                        lbl.pack(fill='x', side='top')
                        # Segunda fila: movil par (sin tipo, sin subtipo)
                        if a.related_cs:
                            rel_osf = cs_phase.get(a.related_cs, '')
                            rel_phase = _phase_txt(rel_osf)
                            rel_rwy = cs_catc_rwy.get(a.related_cs, {}).get(cs, runway)
                            text2 = ' %-4s %-8s %-6s %-5s %s' % (
                                '', a.related_cs, '', rel_phase, rel_rwy)
                            lbl2 = tix.Label(area, text=text2, bg=data_bg, fg=data_fg,
                                             font=row_font, anchor='w', padx=2, pady=0)
                            lbl2.pack(fill='x', side='top')

                    else:
                        # AS/SAPW y otros
                        if a.related_cs:
                            text = ' %-4s %-8s vs %-8s %-5s %s' % (
                                tipo, cs, a.related_cs, phase, runway)
                        else:
                            text = ' %-4s %-8s %-10s %-5s %s' % (
                                tipo, cs, phase, runway, '')
                        lbl = tix.Label(area, text=text, bg=data_bg, fg=data_fg,
                                        font=row_font, anchor='w', padx=2, pady=0)
                        lbl.pack(fill='x', side='top')

            # Restaurar solo la posicion tras actualizar contenido (el tamano lo
            # gestiona el geometry manager con el tamano fijo de 380x340)
            try:
                win.geometry("+%d+%d" % (saved_x, saved_y))
            except Exception:
                pass

            try:
                win.after(1000, refresh)
            except Exception:
                rd._alert_tabular_win = None

        refresh()
        win.protocol('WM_DELETE_WINDOW', close_tabular)
        win.bind('<Escape>', lambda ev: close_tabular())

    def set_flashing_t(self, value):
        if value == self._flashing:
            return
        self._flashing = value

        def flash_timer():
            if self.timer_state:
                self.update_item_color(self._l.trans, 'red')
            else:
                self.update_item_color(self._l.trans, 'black')
            if self.flashing_t:
                self.add_timer_callback(flash_timer)
            else:
                self.update_item_color(self._l.trans,self.color.get_basecolor())
            self._l.refresh('trans')
        if value:
            self.add_timer_callback(flash_timer)
        else:
            self.plot_only = False
    flashing_t = property(get_flashing, set_flashing_t)
   
    def get_speed_vector_length(self): return self._speed_vector_length

    def set_speed_vector_length(self, value):
        if value == self._speed_vector_length:
            return
        self._speed_vector_length = value
        self.redraw_sv()
    speed_vector_length = property(get_speed_vector_length, set_speed_vector_length)

    def get_label_item(self, item): return getattr(self, '_'+item)

    def set_label_item(self, item, value):
        try:
            if value == getattr(self, '_'+item):
                return
        except: pass  # This is to account for the first time it is set
        setattr(self, '_'+item, value)
        if self.visible:
            self._item_refresh_list.append(item)
            if item == 'alt':
                self._item_refresh_list.append('cfl')
            if item == 'cfl':
                self.draw_cfl = True
            if item == 'hdg':
                self._item_refresh_list.append('fhdg')
                self._item_refresh_list.append('dir')


    cs = property(lambda s: s.get_label_item('cs'), lambda s, v: s.set_label_item('cs', v))
    alt = property(lambda s: s.get_label_item('alt'), lambda s, v: s.set_label_item('alt', v))
    rate = property(lambda s: s.get_label_item('rate'), lambda s, v: s.set_label_item('rate', v))
    cfl = property(lambda s: s.get_label_item('cfl'), lambda s, v: s.set_label_item('cfl', v))
    tfl = property(lambda s: s.get_label_item('tfl'), lambda s, v: s.set_label_item('tfl', v))
    rfl = property(lambda s: s.get_label_item('rfl'), lambda s, v: s.set_label_item('rfl', v))
    gs = property(lambda s: s.get_label_item('gs'), lambda s, v: s.set_label_item('gs', v))
    mach = property(lambda s: s.get_label_item('mach'), lambda s, v: s.set_label_item('mach', v))
    wake = property(lambda s: s.get_label_item('wake'), lambda s, v: s.set_label_item('wake', v))
    ltype = property(lambda s: s.get_label_item('ltype'), lambda s, v: s.set_label_item('ltype', v))
    spc = property(lambda s: s.get_label_item('spc'), lambda s, v: s.set_label_item('spc', v))
    echo = property(lambda s: s.get_label_item('echo'), lambda s, v: s.set_label_item('echo', v))
    rutrod = property(lambda s: s.get_label_item('rutrod'), lambda s, v: s.set_label_item('rutrod', v))
    pvh_notes = property(lambda s: s.get_label_item('pvh_notes'), lambda s, v: s.set_label_item('pvh_notes', v))
    gate = property(lambda s: s.get_label_item('gate'), lambda s, v: s.set_label_item('gate', v))
    holdp = property(lambda s: s.get_label_item('holdp'), lambda s, v: s.set_label_item('holdp', v))
    sidok = property(lambda s: s.get_label_item('sidok'), lambda s, v: s.set_label_item('sidok', v))
    emg = property(lambda s: s.get_label_item('emg'), lambda s, v: s.set_label_item('emg', v))
    lrwy = property(lambda s: s.get_label_item('lrwy'), lambda s, v: s.set_label_item('lrwy', v))
    stand_sid = property(lambda s: s.get_label_item('stand_sid'), lambda s, v: s.set_label_item('stand_sid', v))
    stand = property(lambda s: s.get_label_item('stand'), lambda s, v: s.set_label_item('stand', v))
    trans = property(lambda s: s.get_label_item('trans'), lambda s, v: s.set_label_item('trans', v))
    hdg = property(lambda s: s.get_label_item('hdg'), lambda s, v: s.set_label_item('hdg', v))
    fhdg = property(lambda s: s.get_label_item('fhdg'), lambda s, v: s.set_label_item('fhdg', v))
    dir = property(lambda s: s.get_label_item('dir'), lambda s, v: s.set_label_item('dir', v))
    to_do = property(lambda s: s.get_label_item('to_do'), lambda s, v: s.set_label_item('to_do', v))
    thr_nm = property(lambda s: s.get_label_item('thr_nm'), lambda s, v: s.set_label_item('thr_nm', v))
    thr_min = property(lambda s: s.get_label_item('thr_min'), lambda s, v: s.set_label_item('thr_min', v))
    tfto = property(lambda s: s.get_label_item('tfto'), lambda s, v: s.set_label_item('tfto', v))
    rules = property(lambda s: s.get_label_item('rules'), lambda s, v: s.set_label_item('rules', v))
    colat = property(lambda s: s.get_label_item('colat'), lambda s, v: s.set_label_item('colat', v))
    colat_app = property(lambda s: s.get_label_item('colat_app'), lambda s, v: s.set_label_item('colat_app', v))
    adep = property(lambda s: s.get_label_item('adep'), lambda s, v: s.set_label_item('adep', v))
    ades = property(lambda s: s.get_label_item('ades'), lambda s, v: s.set_label_item('ades', v))
    r_speed = property(lambda s: s.get_label_item('r_speed'), lambda s, v: s.set_label_item('r_speed', v))
    r_head = property(lambda s: s.get_label_item('r_head'), lambda s, v: s.set_label_item('r_head', v))
    r_rate = property(lambda s: s.get_label_item('r_rate'), lambda s, v: s.set_label_item('r_rate', v))
    osf_act = property(lambda s: s.get_label_item('osf_act'), lambda s, v: s.set_label_item('osf_act', v))

    def destroy(self):
        self.delete()
        self._l.destroy()
        del(self._message_handler)
        del(self.do_scale)
        del(self.undo_scale)
        
    def __del__(self):
        logging.debug("VisTrack.__del__ %s" % self.cs)
            
    class Label(object):
        """Contains the information regarding label formatting"""
        formats = {'pp': {-1:['pac', 'vac', 'emg', 'to_do'],
                            0:['cs', 'spc', 'stand_sid'],
                            1:['ltype', 'wake', 'spc', 'lrwy', 'spc', 'echo'],
                            2:['gs', 'spc', 'alt', 'rate', 'cfl', 'spc', 'trans'],
                            3:['hdg', 'dir', 'fhdg'],
                            4:['thr_nm', 'spc', 'thr_min']},
                'pp-ground': {-1:['pac', 'vac', 'emg', 'to_do'],
                            0:['cs', 'spc', 'stand_sid'],
                            1:['ltype', 'wake', 'spc', 'lrwy', 'spc', 'echo'],
                            2:['gs', 'spc', 'alt', 'rate', 'cfl', 'spc', 'trans'],
                            3:['hdg', 'dir', 'fhdg'],
                            4:['thr_nm', 'spc', 'thr_min']},
                'pp-mach': {-1:['pac', 'vac', 'emg', 'to_do'],
                            0:['cs', 'spc', 'stand_sid'],
                            1:['ltype', 'wake', 'spc', 'lrwy', 'spc', 'echo'],
                            2:['mach', 'spc', 'alt', 'rate', 'cfl', 'spc', 'trans'],
                            3:['hdg', 'dir', 'fhdg'],
                            4:['thr_nm', 'spc', 'thr_min']},
                'atc-nocorrel': {-1:['pac', 'vac', 'emg'],
                            0:['trans'],
                            1:['spc', 'spc', 'echo'],
                            2:['gs', 'spc', 'alt', 'rate', 'cfl'],
                            3:['thr_nm', 'spc', 'thr_min']},
                'atc-pict': {-1:['pac', 'vac', 'emg'],
                            0:['cs'],
                            1: ['alt', 'rate', 'cfl'],
                            2:['gs', 'wake', 'spc', 'echo'],
                            3:['thr_nm', 'spc', 'thr_min', 'trans']},
                'atc-smr':  {-1: ['pac', 'vac', 'emg'],
                            0: ['cs', 'spc'],
                            1: ['alt', 'rate', 'cfl'],
                            2: ['gs', 'wake', 'spc', 'echo'],
                            3: ['thr_nm', 'spc', 'thr_min']},
                'pp-veh':   {-1:[],
                            0: ['cs'],
                            1: ['gs', 'spc', 'alt']},
                # DCM: Etiqueta para LEBL
                'atc-osf-llegadas': {-1:['pac', 'vac', 'emg'],
                            0:['cs', 'spc', 'spc', 'stand_sid', 'spc', 'stand', 'spc', 'osf_act'],
                            1:['ltype', 'wake', 'spc', 'lrwy', 'spc', 'gate', 'spc', 'spc', 'spc', 'spc', 'spc', 'spc', 'spc', 'rutrod'],
                            2:['gs', 'spc', 'alt', 'cfl'],
                            3:['thr_nm', 'spc', 'thr_min', 'tfto']},
               'atc-osf': {-1: ['pac', 'vac', 'emg'],
                           0: ['cs', 'spc', 'spc', 'stand_sid', 'spc', 'stand', 'spc', 'osf_act'],
                           1: ['ltype', 'wake', 'spc', 'lrwy', 'spc', 'gate', 'spc', 'spc', 'spc', 'spc', 'spc',
                               'spc', 'spc', 'holdp', 'spc', 'spc', 'spc', 'spc', 'spc', 'spc', 'rutrod'],
                           2: ['gs', 'spc', 'alt', 'cfl'],
                           3: ['thr_nm', 'spc', 'thr_min', 'tfto']},
                # Etiqueta para LECG. No la usan
                # 'atc-osf': {-1: ['pac', 'vac', 'emg'],
                #             0: ['cs', 'spc', 'spc', 'stand_sid', 'spc', 'osf_act'],
                #             1: ['ltype', 'wake', 'spc', 'lrwy', 'spc', 'stand', 'spc', 'gate', 'spc', 'spc', 'spc',
                #                 'spc', 'spc', 'spc', 'spc',
                #                 'rutrod', 'spc', 'spc', 'spc', 'spc', 'spc', 'spc', 'holdp'],
                #             2: ['gs', 'spc', 'alt', 'cfl'],
                #             3: ['thr_nm', 'spc', 'thr_min']},
                'atc-veh': {-1:[],
                             0: ['cs']},
                # Vehiculo con Plan de Vehiculo (PVH): fase, pista de entrada/cruce y anotaciones
                'atc-veh-pvh': {-1:[],
                             0: ['cs', 'spc', 'osf_act', 'spc', 'lrwy'],
                             1: ['pvh_notes']},
                'atc-ucs': {-1: ['pac', 'vac', 'emg'],
                            0: ['cs'],
                            1: ['alt', 'rate', 'cfl'],
                            2: ['gs', 'wake', 'spc', 'tfl', 'spc', 'echo'],
                            3: ['thr_nm', 'spc', 'thr_min', 'trans']},
                'atc-na': {-1: ['pac', 'vac', 'emg'],
                            0: ['cs'],
                            1: ['alt', 'rate', 'cfl'],
                            2: ['gs', 'wake', 'spc', 'echo'],
                            3:['thr_nm', 'spc', 'thr_min', 'trans']},
                'atc-app': {-1: ['pac', 'vac', 'emg'],
                            0: ['cs'],
                            1: ['alt', 'rate', 'tfl', 'spc', 'colat_app'],
                            2: ['gs', 'wake', 'spc', 'echo'],
                            3:['thr_nm', 'spc', 'thr_min', 'trans']},
                'atc-extend': {-1:['pac', 'vac', 'emg'],
                            0:['cs'],
                            1:['alt', 'rate', 'cfl', 'spc', 'tfl', 'spc', 'colat'],
                            2:['gs', 'wake', 'spc', 'echo'],
                            3:['ltype', 'spc', 'rfl''spc', 'rules', 'spc', 'adep', 'spc', 'ades', 'spc'],
                            4:['thr_nm', 'spc', 'thr_min', 'trans']}}


        # The __getitem__ function allows us access this class' attributes
        # as if it were a dictionary
        def __getitem__(self, key): return self.__dict__[key]


        class LabelItem(object):
            """Contains the attributes of a label item"""
            def __init__(self, master_track):
                self.vt = vt = master_track
                self.color = master_track.color
                self.t = ""  # Item text
                self.w = 0  # Width in pixels
                self.x = 0  # Hor screen coord
                self.y = 0  # Ver screen coord
                self.i = None  # tix.Canvas item id
                self._prev_text = None
                self._prev_fill = None

            #def __del__(self):
            #    logging.debug("LabelItem.__del__")
                
        def __init__(self, master_track):
            self.vt = vt = master_track
            self.fir = vt.rd.fir
            self.c = self.vt._c  # tix.Canvas
            self.cs = self.LabelItem(vt)
            self.cs.color = SmartColor(vt.color.get_basecolor())
            self.alt = self.LabelItem(vt)
            self.alt.color = SmartColor(vt.color.get_basecolor())
            self.rate = self.LabelItem(vt)
            self.rate.color = SmartColor(vt.color.get_basecolor())
            self.cfl = self.LabelItem(vt)
            self.cfl.color = SmartColor(vt.color.get_basecolor())
            self.osf_act = self.LabelItem(vt)
            self.osf_act.t = '---'
            self.osf_act.color = SmartColor(vt.color.get_basecolor())
            self.tfl = self.LabelItem(vt)
            self.rfl = self.LabelItem(vt)
            self.colat = self.LabelItem(vt)
            self.colat_app = self.LabelItem(vt)
            self.rules = self.LabelItem(vt)
            self.adep = self.LabelItem(vt)
            self.ades = self.LabelItem(vt)
            self.r_speed = self.LabelItem(vt)
            self.r_head = self.LabelItem(vt)
            self.r_rate = self.LabelItem(vt)
            self.gs = self.LabelItem(vt)
            self.gs.color = SmartColor(vt.color.get_basecolor())
            self.thr_nm = self.LabelItem(vt)
            self.thr_nm.color = SmartColor(vt.color.get_basecolor())
            self.thr_min = self.LabelItem(vt)
            self.thr_min.color = SmartColor(vt.color.get_basecolor())
            self.tfto = self.LabelItem(vt)  # Time from takeoff
            self.tfto.color = SmartColor(vt.color.get_basecolor())
            self.mach = self.LabelItem(vt)
            self.mach.color = SmartColor(vt.color.get_basecolor())
            self.echo = self.LabelItem(vt)
            self.echo.t = '     '
            self.echo.color = SmartColor(vt.color.get_basecolor())

            self.rutrod = self.LabelItem(vt)
            self.rutrod.t = '-'
            self.rutrod.color = SmartColor(vt.color.get_basecolor())

            self.pvh_notes = self.LabelItem(vt)
            self.pvh_notes.t = ''
            self.pvh_notes.color = SmartColor(vt.color.get_basecolor())

            self.gates = []
            self.gate = self.LabelItem(vt)
            self.gate.t = '-'
            self.gate.color = SmartColor(vt.color.get_basecolor())

            self.holdp = self.LabelItem(vt)
            self.holdp.t = '-'
            self.holdp.color = SmartColor(vt.color.get_basecolor())

            self.sidok = self.LabelItem(vt)
            self.sidok.t = 'Ok'
            self.sidok.color = SmartColor(vt.color.get_basecolor())

            self.stand_sid = self.LabelItem(vt)
            self.stand_sid.t = ' '
            self.stand_sid.color = SmartColor(vt.color.get_basecolor())
            self.stand = self.LabelItem(vt)
            self.stand.t = ' '
            self.stand.color = SmartColor(vt.color.get_basecolor())
            self.trans = self.LabelItem(vt)
            self.trans.t = '    '
            self.trans.color = SmartColor(vt.color.get_basecolor())

            self.lrwy = self.LabelItem(vt)
            self.lrwy.color = SmartColor(vt.color.get_basecolor())

            self.ltype = self.LabelItem(vt)
            self.ltype.color = SmartColor(vt.color.get_basecolor())

            self.wake = self.LabelItem(vt)

            # self.wake.color = SmartColor('')
            self.wake.color = SmartColor(vt.color.get_basecolor())
            self.to_do = self.LabelItem(vt)
            self.to_do.t = '   '
            self.to_do.color = SmartColor(vt.color.get_basecolor())
            self.hdg = self.LabelItem(vt)
            self.hdg.color = SmartColor(vt.color.get_basecolor())
            self.dir = self.LabelItem(vt)
            self.spc = self.LabelItem(vt)
            self.spc.t = ' '
            self.spc.color = SmartColor(vt.color.get_basecolor())
            self.opc = self.LabelItem(vt)
            self.fhdg = self.LabelItem(vt)

            self.emg = self.LabelItem(vt)
            self.emg.t = 'EMG'
            self.emg.color = SmartColor('')

            self.pac = self.LabelItem(vt)     
            self.pac.t = 'PAC'
            self.pac.color = SmartColor('')
            
            self.vac = self.LabelItem(vt)
            self.vac.t = 'VAC'
            self.vac.color = SmartColor('')
            
            self._old_font_size = 0
                        
            self.format = self.vt.label_format  # By default, 'pp'
            self.items = []  # They are calculated at reformat time

            self.color_engine = 'black'
            self.color_sup = 'black'


        def delete(self):
            """Delete old tag and remove old bindings"""
            c = self.vt._c  # tix.Canvas
            s = self.vt.id
            
            for i in self.items:
                ra_cleartagbinds(self[i].i, c)
                self[i].i = None
            c.delete(s+'labelitem')
            self.items = []
            
        def destroy(self):
            self.delete()
            for i in self.vt.allitems:
                item = getattr(self, i)
                delattr(item, 'vt')
                delattr(item, 'color')
                delattr(self, i)
            del(self.vt)
            
        def redraw(self):
            """Redraw the label and reset bindings"""
            c = self.vt._c  # tix.Canvas
            s = self.vt.id
            lf = self.vt._l_font
            self.format = self.vt.label_format
            
            # Delete old tag and remove old bindings
            self.delete()
            
            if not self.vt.visible: return
            
            # Create new label
            self.reformat()
            for i_name in self.items:
                i = self[i_name]  # i is an instance of the LabelItem class
                i.i = c.create_text(i.x, i.y, text=i.t, fill=i.color.get(), tag=s+i_name, anchor=tix.NW, font=lf)
                c.itemconfig(i.i, tags=(s, s+'labelitem', s+'label', 'track'))
                    
            # Create bindings
            # Common bindings
            ra_tag_bind(self.c, self.cs.i, "<Button-1>", self.cs_b1)
            ra_tag_bind(self.c, self.cs.i, "<Button-2>", self.cs_b2)
            ra_tag_bind(self.c, self.cs.i, "<Button-3>", self.cs_b3)
            ra_tag_bind(self.c, self.echo.i, "<Button-1>", self.echo_b1)
            ra_tag_bind(self.c, self.alt.i, "<Button-1>", self.change_altitude)
            ra_tag_bind(self.c, self.trans.i, "<Button-1>", self.change_trans)
            ra_tag_bind(self.c, self.trans.i, "<Button-2>", self.trans_b2)
            ra_tag_bind(self.c, self.stand_sid.i, "<Button-1>", self.change_sid)
            ra_tag_bind(self.c, self.stand_sid.i, "<Button-2>", self.stand_sid_b2)
            ra_tag_bind(self.c, self.lrwy.i, "<Button-1>", self.change_sid)

            # PP bindings
            if self.vt.mode in ['pp', 'pp-mach']:
                ra_tag_bind(self.c, self.gs.i, "<Button-2>", self.gs_b2)
                ra_tag_bind(self.c, self.mach.i, "<Button-2>", self.mach_b2)
                ra_tag_bind(self.c, self.ltype.i, "<Button-2>", self.ltype_b2)
                ra_tag_bind(self.c, self.cfl.i, "<Button-1>", self.change_rate)
                ra_tag_bind(self.c, self.gs.i, "<Button-1>", self.change_speed)
                ra_tag_bind(self.c, self.mach.i, "<Button-1>", self.change_speed)
                ra_tag_bind(self.c, self.hdg.i, "<Button-1>", self.change_heading)

            # ATC bindings
            elif self.vt.mode == 'atc':
                ra_tag_bind(self.c, self.cfl.i, "<Button-1>", self.change_altitude)
                ra_tag_bind(self.c, self.tfl.i, "<Double-Button-1>", self.tfl_db1)
                ra_tag_bind(self.c, self.osf_act.i, "<Button-3>", self.change_action)
                ra_tag_bind(self.c, self.osf_act.i, "<Button-1>", self.change_action_sequence)
                ra_tag_bind(self.c, self.colat.i, "<Button-1>", self.circunflejo)
                ra_tag_bind(self.c, self.rutrod.i, "<Double-Button-1>", self.change_rutrod)
                ra_tag_bind(self.c, self.gate.i, "<Button-1>", self.change_gate)
                ra_tag_bind(self.c, self.holdp.i, "<Button-1>", self.change_holdp)
                ra_tag_bind(self.c, self.sidok.i, "<Button-1>", self.change_sidok)

        def reformat(self):
            """Recalculates the text for the label items, and the new label geometry"""
            vt = self.vt  # Parent track object
            lf = vt._l_font  # Label font
            if vt.l_font_size != self._old_font_size:
                lf.configure(size=vt.l_font_size)
                self._old_font_size = vt.l_font_size
                
            # Refresh items text and color
            for i_name in vt.allitems:
                self.refresh(i_name)
                
            # Label geometry
            lw = mlw = 40  # Label Width initially Minimum label width
            lh = 4  # Initial label height
            line_height = lf.metrics('ascent')
            for line_no, items in self.formats[self.format].items():
                if not vt.line_onoff[line_no+1]: continue
                line_width = 4
                x_offset = vt.label_x+2  # Left click on callsign to move labels
                for item in items:
                    self[item].w = lf.measure(self[item].t)
                    line_width += self[item].w
                    self[item].x = x_offset
                    x_offset += self[item].w
                    self[item].y = vt.label_y + line_no * line_height
                    self.items.append(item)
                lw = max(lw, line_width)
                lh = lh + line_height
            vt.label_width = lw
            # We are assumming here that all label formats
            # have a -1 line to contain pac and vac
            # TODO This is NOT CORRECT
            vt.label_height = lh - line_height
                
            # Update label items position
            for i in self.items:
                if self[i].i is not None:
                    vt._c.coords(self[i].i, self[i].x, self[i].y)
                    
        def update_item_color(self, item, basecolor):
            if item.color.get_basecolor() == basecolor:
                pass
            else:

                item.color.set(basecolor)

        def refresh(self, i):
            """Change text and color of a specific label item"""
            vt = self.vt  # Parent track object
            lf = vt._l_font  # Label font
            # Text
            if i == 'cs':
                self.cs.t = vt.cs
            elif i == 'to_do':
                if vt.to_do == 'hld':
                    self.to_do.t = 'HLD'
                elif vt.to_do == 'orbit':
                    self.to_do.t = 'ORB'
                elif vt.to_do == 'app':
                    self.to_do.t = 'APP'
                else:
                    self.to_do.t = ''
            elif i == 'mach':
                self.mach.t = '.'+str(int(round(vt.mach*100)))
            elif i == 'gs':
                self.vt.label_format = self.format
                self.gs.t = "%02d" % round(vt.gs/10)

            elif i == 'wake':
                self.wake.t = vt.wake

            elif i == 'lrwy':
                self.lrwy.t = vt.lrwy
            elif i == 'ltype':
                self.ltype.t = vt.ltype
            elif i == 'colat':
                if self.colat.t == 'SAL^':
                    self.colat.t = self.colat.t
                else:
                    self.colat.t = vt.colat
            elif i == 'colat_app':
                if self.colat.t == 'SAL^':
                    self.colat.t = self.colat.t
                else:
                    self.colat.t = vt.colat_app
            elif i == 'rules':
                self.rules.t = vt.rules
            elif i == 'adep':
                self.adep.t = vt.adep
            elif i == 'ades':
                self.ades.t = vt.ades
            elif i == 'r_speed':
                # self.r_speed.t = vt.r_speed
                self.r_speed.t =''
            elif i == 'r_head':
                # self.r_head.t = vt.r_head
                self.r_head.t = ''
            elif i == 'r_rate':
                # self.r_rate.t = vt.r_rate
                self.r_rate.t = ''
            elif i=='hdg':
                if vt.to_do == 'hdg':
                    self.update_item_color(self.hdg, 'white')
                else:
                    self.update_item_color(self.hdg, vt.color.get_basecolor())
                self.hdg.t='%03d'%(int(vt.hdg))
                if vt.draw_fhdg:
                    if (vt.hdg-vt.fhdg)>2.:
                        self.fhdg.t='%03d'%(int(vt.fhdg))
                    elif (vt.hdg-vt.fhdg)<-2.:
                        self.fhdg.t='%03d'%(int(vt.fhdg))
                    else:
                        vt.draw_fhdg = False
                        self.fhdg.t = '   '
                else:
                    self.fhdg.t = '   '
            elif i == 'dir':
                if self.opc == 'ECON':
                    if vt.draw_fhdg:
                        if (vt.hdg-vt.fhdg) > 2.:
                            if abs(vt.hdg-vt.fhdg) < 180:
                                self.dir.t='<'
                            else:
                                self.dir.t = '>'
                        elif (vt.hdg-vt.fhdg) < -2.:
                            if abs(vt.hdg-vt.fhdg) < 180:
                                self.dir.t = '>'
                            else:
                                self.dir.t = '<'
                        else:
                            self.dir.t = '  ' # Two spaces, as wide as the >, so that a reformat is not necessary
                    else:
                        self.dir.t = '  '
                elif self.opc == 'DCHA':
                    if vt.draw_fhdg:
                        self.dir.t = '>'
                    else:
                        self.dir.t = '  '
                elif self.opc == 'IZDA':
                    if vt.draw_fhdg:
                        self.dir.t = '<'
                    else:
                        self.dir.t = '  '
                else:
                    self.dir.t = '  '
            elif i == 'fhdg':
                self.fhdg.t = '%03d' % (int(vt.fhdg))
                if vt.draw_fhdg:
                    if vt.to_do != 'hdg':
                        vt.draw_fhdg = False
                        self.fhdg.t = '   '
                    elif (vt.hdg-vt.fhdg)>2.:
                        self.fhdg.t = '%03d' % (int(vt.fhdg))
                    elif (vt.hdg-vt.fhdg)<-2.:
                        if self.fhdg.t == '360' and self.hdg.t == '000': # HDG is never 360,
                            vt.draw_fhdg = False                         # changes to 000
                            self.fhdg.t = '   '
                            self.dir.t = '  '
                        else:
                            self.fhdg.t='%03d'%(int(vt.fhdg))
                    else:
                        vt.draw_fhdg = False
                        self.fhdg.t = '   '
                else:
                    self.fhdg.t = '   '
            elif i == 'alt':
                if vt.alt == 'GND':
                    self.alt.t = vt.alt
                else:
                    if vt.lvl_blocked:
                        self.update_item_color(self.alt, 'white')
                    else:
                        self.update_item_color(self.alt, vt.color.get_basecolor())
                    self.alt.t = '%03d' % (int(vt.alt+0.5))
            elif i == 'thr_nm':
                if vt.thr_nm != '':
                    self.thr_nm.t = '%4.1f' % vt.thr_nm
                else:
                    self.thr_nm.t = ''
            elif i == 'thr_min':
                if vt.thr_min != '':
                    self.thr_min.t = ('%4.1f' % vt.thr_min).replace('.', '\'')
                else:
                    self.thr_min.t = ''
            elif i == 'tfto':
                self.tfto.t = vt.tfto
            elif i == 'rate':
                if vt.alt != 'GND' and vt.alt < vt.arrow:
                    self.rate.t = unichr(8593)  # symbol
                elif vt.alt != 'GND' and vt.alt > vt.arrow:
                    self.rate.t = unichr(8595)  # symbol
                else:
                    self.rate.t = '  '  # Two spaces, as wide as the arrow, so that a reformat is not necessary
            elif i == 'osf_act':
                self.osf_act.t = self.vt.osf_act
                # Edit the text field and the color
                if self.osf_act.t in ['FIN', 'ABO', 'SAL', 'LND', 'AIR']:
                    self.osf_act.color.set('grey')
                elif self.osf_act.t in ['SUR', 'SIR', 'REA', 'PBR', 'TXR', 'DPR', 'LDR', 'CRR', 'ENR']:
                    self.osf_act.color.set('yellow')
                elif self.osf_act.t in ['INC', 'PRE']:
                    self.osf_act.color.set('orange')
                elif self.osf_act.t in ['MAP', "GA"]:
                    self.osf_act.color.set('red')
                else:
                    self.osf_act.color.set('green')
                # Prediccion CATC: override a morado si hay prediccion what-if
                if getattr(self.vt, 'catc_pred', False):
                    self.osf_act.color.set('#CC33FF')
                if self.osf_act.t in ['TOU', 'TIN']:
                    self.osf_act.t = 'TAX'
                elif self.osf_act.t in ['INC', 'PRE']:
                    self.osf_act.t = '---'
                elif self.osf_act.t == 'AIR':
                    self.osf_act.t = 'DEP'
                elif self.osf_act.t in ['LND', 'LDR']:
                    self.osf_act.t = 'LDG'
                elif self.osf_act.t == 'SUR':
                    self.osf_act.t = 'S/U'
                elif self.osf_act.t == 'PBR':
                    self.osf_act.t = 'P/B'
                elif self.osf_act.t == 'TXR':
                    self.osf_act.t = 'TAX'
                elif self.osf_act.t == 'DPR':
                    self.osf_act.t = 'DEP'
                elif self.osf_act.t == 'CRR':
                    self.osf_act.t = 'CRU'
                elif self.osf_act.t == 'ENR':
                    self.osf_act.t = 'ENT'

                # DCM: Cuidado con las vueltas al campo..
                if vt.tfto != '':
                    self.osf_act.t = 'DEP'
                    self.osf_act.color.set('grey')

            elif i == 'cfl':
                if vt.draw_cfl:
                    if vt.alt != 'GND' and vt.cfl != vt.AirportElev:
                        if vt.cfl-vt.alt > 2.:
                            self.cfl.t = '%03d' % (int(vt.cfl+0.5))  # Vertical direction
                        elif vt.cfl-vt.alt < -2.:
                            self.cfl.t = '%03d' % (int(vt.cfl+0.5))
                        else:
                            # vt.draw_cfl = False
                            self.cfl.t = '-'
                    else:
                        # vt.draw_cfl = False
                        self.cfl.t = '-'
                else:
                    self.cfl.t = '-'
            elif i == 'tfl':
                if vt.label_format == 'atc-ucs':
                    if vt.cfl - vt.tfl > 2.:
                        self.tfl.t = '%03d' % (int(vt.tfl+0.5))
                    elif vt.cfl - vt.tfl < -2.:
                        self.tfl.t = '%03d' % (int(vt.tfl+0.5))
                    else:
                        self.tfl.t = '%03d' % (int(vt.tfl+0.5))
                    if vt.remove_tfl:  # DCM: doble click on tfl label and remove it
                        self.tfl.t = '   '
                elif vt.label_format == 'atc-na':
                    if vt.cfl - vt.tfl > 2.:
                        self.tfl.t = '%02d-' % (int(0.1*vt.tfl+0.5))  # Vertical direction
                    elif vt.cfl - vt.tfl < -2.:
                        self.tfl.t = '%02d-' % (int(0.1*vt.tfl+0.5))
                    else:
                        self.tfl.t = ''
            elif i == 'rfl':
                self.rfl.t='%03d'%(int(vt.rfl+0.5))

            elif i == 'echo':
                if self.echo.t == u'^':
                    self.echo.t = self.echo.t
                else:
                    self.echo.t = vt.echo

            elif i == 'rutrod':
                self.rutrod.t = vt.rutrod

            elif i == 'pvh_notes':
                self.pvh_notes.t = vt.pvh_notes

            elif i == 'gate':
                self.gate.t = vt.gate

            elif i == 'holdp':
                self.holdp.t = vt.holdp

            ###############################################
            # DCM: Ver posibilidad de img en lugar de texto
            # Aircraft -> self.sid_check = False
            elif i == 'sidok':
                self.sidok.t = vt.sidok
            ###############################################

            elif i == 'stand_sid':
                self.stand_sid.t = vt.stand_sid

            elif i == 'stand':
                self.stand.t = vt.stand

            elif i == 'trans':
                if vt.trans in ('SEC', 'COM', 'EMG', ' SEC', ' COM', ' EMG'):
                    self.emg.color.set('red')
                    self.emg.t = vt.trans.strip()
                    if self.vt.timer_state:
                        self.emg.color.set('red')
                    else:
                        self.emg.color.set('')
                    self.vt.add_timer_callback(self.refresh, i)
                    self.vt.add_timer_callback(self.refresh, 'emg')
                else:
                    self.emg.t = '   '
                    self.trans.t = vt.trans

            elif i == 'pac':
                if vt.pac and not vt.vac:
                    self.pac.t = "PAC"
                else:
                    self.pac.t = ""
            elif i == 'vac':
                if vt.vac:
                    self.vac.t = "VAC"
                else:
                    self.vac.t = ""
                
            item = self[i]
            if i == 'pac':
                if vt.pac and not vt.vac:
                    if self.vt.timer_state:
                        self.update_item_color(self.pac, 'red')
                    else:
                        self.update_item_color(self.pac, '')
                    self.vt.add_timer_callback(self.refresh, i)
                else:
                    self.update_item_color(self.pac, '')
            if i == 'vac':
                if vt.vac:
                    if self.vt.timer_state:
                        self.update_item_color(self.vac, 'red')
                    else:
                        self.update_item_color(self.vac, '')
                    self.vt.add_timer_callback(self.refresh, i)
                else:
                    self.update_item_color(self.vac, '')

                # Refresh the item
            #if item.i is not None:
            #    vt._c.itemconfig(item.i, text=item.t, fill=item.color.get())

            # Refresh the item only if the text or the color has changed, to avoid unnecessary redraws
            if item.i is not None:
                new_text = item.t
                new_fill = item.color.get()
                if new_text != item._prev_text or new_fill != item._prev_fill:
                    vt._c.itemconfig(item.i, text=new_text, fill=new_fill)
                    item._prev_text = new_text
                    item._prev_fill = new_fill
                
        def cs_moved(self,  e):
            self.vt.reposition_label(e.x, e.y)
            self.vt.auto_separation = False
            # self.vt._message_handler(self.vt,'cs','<Motion>',None,e)

        def cs_released(self, e):
                ra_tag_unbind(self.c, self.cs.i, "<Motion>")
                ra_tag_unbind(self.c, self.cs.i, "<ButtonRelease-2>")
                ra_tag_bind(self.c, self.cs.i, "<Button-2>", self.cs_b2)
                self.vt._message_handler(self.vt, 'cs', '<ButtonRelease-2>', None, e)

        def trans_released(self, e):
                ra_tag_unbind(self.c, self.trans.i, "<Motion>")
                ra_tag_unbind(self.c, self.trans.i, "<ButtonRelease-2>")
                ra_tag_bind(self.c, self.trans.i, "<Button-2>", self.trans_b2)
                self.vt._message_handler(self.vt, 'trans', '<ButtonRelease-2>', None, e)

        def stand_sid_released(self, e):
                ra_tag_unbind(self.c, self.stand_sid.i, "<Motion>")
                ra_tag_unbind(self.c, self.stand_sid.i, "<ButtonRelease-2>")
                ra_tag_bind(self.c, self.stand_sid.i, "<Button-2>", self.stand_sid_b2)
                self.vt._message_handler(self.vt, 'stand_sid', '<ButtonRelease-2>', None, e)

        def ltype_released(self, e):
                ra_tag_unbind(self.c, self.ltype.i, "<Motion>")
                ra_tag_unbind(self.c, self.ltype.i, "<ButtonRelease-2>")
                ra_tag_bind(self.c, self.ltype.i, "<Button-2>", self.ltype_b2)
                self.vt._message_handler(self.vt, 'ltype', '<ButtonRelease-2>', None, e)

        def cs_b2(self, e):
            ra_tag_unbind(self.c, self.cs.i, "<Button-2>")
            ra_tag_bind(self.c, self.cs.i, "<Motion>", self.cs_moved)
            ra_tag_bind(self.c, self.cs.i, "<ButtonRelease-2>", self.cs_released)
            self.vt._message_handler(self.vt, 'cs', '<Button-2>', None, e)
            # self.reformat()  # We redraw the text to reset the width

        def trans_b2(self, e):
             ra_tag_unbind(self.c, self.trans.i, "<Button-2>")
             ra_tag_bind(self.c, self.trans.i, "<Motion>", self.cs_moved)
             ra_tag_bind(self.c, self.trans.i, "<ButtonRelease-2>", self.trans_released)
             self.vt._message_handler(self.vt, 'trans', '<Button-2>', None, e)
             # self.reformat()  # We redraw the text to reset the width

        def stand_sid_b2(self, e):
             ra_tag_unbind(self.c, self.stand_sid.i, "<Button-2>")
             ra_tag_bind(self.c, self.stand_sid.i, "<Motion>", self.cs_moved)
             ra_tag_bind(self.c, self.stand_sid.i, "<ButtonRelease-2>", self.stand_sid_released)
             self.vt._message_handler(self.vt, 'stand_sid', '<Button-2>', None, e)

        def ltype_b2(self, e):
             ra_tag_unbind(self.c, self.ltype.i, "<Button-2>")
             ra_tag_bind(self.c, self.ltype.i, "<Motion>", self.cs_moved)
             ra_tag_bind(self.c, self.ltype.i, "<ButtonRelease-2>", self.ltype_released)
             self.vt._message_handler(self.vt, 'ltype', '<Button-2>', None, e)

        def cs_b1(self, e):
            self.vt._message_handler(self.vt, 'cs', '<Button-1>', None, e)
            if self.vt.mode in ['pp', 'pp-mach']:
                if self.vt._assumed:
                    self.desplegar_appbutton(e, self.vt)

        def cs_b3(self, e):
            # Si hay alertas activas, mostrar ventana de alertas
            if self.vt._active_alerts:
                self.vt.show_alert_window(e)
                return
            self.vt._message_handler(self.vt, 'cs', '<Button-3>', None, e)
#           JRAR: skip confirmation window
#            def ok():
#                self.vt._message_handler(self.vt,'transfer',None,None,e)
            # Only assumed traffic may be transferred
#            if self.vt.assumed: RaDialog(self.c, label=self.cs.t+": Transferir", ok_callback=ok,
#                                        position=(self.vt.x, self.vt.y))
            if self.vt.assumed: self.vt._message_handler(self.vt, 'transfer', None, None, e)
        def gs_b2(self,e):
            self.vt.mode = 'pp-mach'
            self.vt._message_handler(self.vt, 'gs', '<Button-2>', None, e)
        def mach_b2(self,e):
            self.vt.mode = 'pp'
            self.vt._message_handler(self.vt, 'mach', '<Button-2>', None, e)
        def echo_b1(self, e):
            self.echo.t = u'^'
            self.refresh('echo')

        def tfl_db1(self,e):
            self.vt._message_handler(self.vt, 'tfl', '<Double-Button-1>', self.vt.tfl, e)
            self.reformat()  # We redraw the text to reset the width

        def change_action(self, e):
            # Determinar la ruta de cada una de las "class" que se están usando:
                # (self:Label)self.vt.rd in Label is radisplay in RaBahia(self:RaBahia)
                # self.vt in Label is f in RaBahia
            self.OSF_pof = self.vt.osf_act
            # self.vt.rd.fichas_tabular.rightclicked(self.vt, self.vt._cs, C_ACTION, e)
            f = self.vt.rd._tracks_flights[self.vt]
            try:
                self.vt.rd.fichas_tabular.rightclicked_from_label_act(self.vt._cs, e)
            except:
                pass

        def change_action_sequence(self, e):
            try:
                # print("Click en campo ACT de la etiqueta")
                # self.vt.rd.fichas_tabular.leftclicked_act_label(self.vt, self.vt._cs, C_ACTION)
                self.vt.rd.fichas_tabular.change_action_from_label(self.vt._cs)
            except:
                logging.debug("Unable to change action sequence from label...")
                pass

            # def popup_sid(event):
            #     win = tix.Toplevel()
            #     def close_win():
            #         win.destroy()
            #     x, y = event.x_root, event.y_root
            #     poswindow = "228" + "x" + "50" + "+" + str(x) + "+" + str(y)
            #     win.geometry(poswindow)
            #     win.overrideredirect(True)
            #     text_body = (" " + self.vt.cs + " PVT NO TIENE SID CONFIRMADA ")
            #     lbl_msg = tix.Label(win, text=text_body, bg='blue', fg='white')
            #     but_Acp = tix.Button(win, text="Aceptar", command = close_win)
            #     lbl_msg.grid(row=0, columnspan=2, sticky=tix.W + tix.E)
            #     but_Acp.grid(row=1, column=0, columnspan=2, sticky=tix.W + tix.E)
            #
            # f = self.vt.rd._tracks_flights[self.vt]
            # if self.vt.sidok == " O " and\
            #         ((Aircraft.OSF_DEPSEQ[Aircraft.OSF_DEPSEQ.index(f.OSF_pof)+1]) in (Aircraft.DEPARTING, Aircraft.AIRBORNE)):
            #     popup_sid(e)
            # else:
            #     self.vt.rd.fichas_tabular.leftclicked(self.vt, self.vt._cs, C_ACTION)

        def desplegar_appbutton(self, f, e):
            f = self.vt.rd._tracks_flights[self.vt]
            master = self.vt.rd
            def b_auth_approach():
                if master.fir.AdHasIfrRwys(f.ades):
                    ad = master.fir.aerodromes[f.ades]
                elif master.fir.AdHasIfrRwys(f.adep):
                    ad = master.fir.aerodromes[f.adep]
                else:
                    for a in master.fir.aerodromes:
                        ad = master.fir.aerodromes[a]
                        break
                iaf = ''
                rdes = f.desrwy
                # Get all iafs for wry in use
                iaps = ad.rwy_in_use.iaps.keys()
                # Get all iafs for rest of rwys
                rwys = []
                for rwy in ad.rwy_direction_list:
                    rwys.append(rwy.txt_desig)
                    if rwy.txt_desig != ad.rwy_in_use.txt_desig:
                        iaps = iaps + rwy.iaps.keys()
                # Find a potential iaf
                for i in range(0, len(f.route)):
                    if f.route[i-1].fix == f.iaf:
                        iaf = f.route[i-1].fix
                        break
                if iaf == '':
                    for i in range(0, len(f.route)):
                        if f.route[i-1].fix in ad.rwy_in_use.iaps.keys():
                            iaf = f.iaf = f.route[i-1].fix
                            break
                if iaf == '':
                    for i in range(0, len(f.route)):
                        if f.route[i-1].fix in iaps:
                            iaf = f.iaf = f.route[i-1].fix
                            break
                if iaf == '': iaf = f.iaf
                entries = []
                entries.append({'label': 'Destino:', 'width': 4, 'def_value': ad.code_id})
                entries.append({'label': 'Pista:', 'width': 2, 'values': rwys, 'def_value': rdes})
                entries.append({'label': 'IAF:', 'width': 5, 'values': iaps, 'def_value': iaf})

                def auth_app(e=None, avo=f, entries=None):
                    master.sendMessage({"message": "execute_app", "cs": f.callsign,
                                        "ades": entries['Destino:'].get().upper(),
                                        "rdes": entries['Pista:']['value'],
                                        "iaf": entries['IAF:']['value']})
                RaDialog(self.c, label=f.callsign+': Autorizar a Aproximación',
                         ok_callback=auth_app, entries=entries, position=(self.vt.x, self.vt.y))
                close_win()

            def b_change_rwy():
                if master.fir.AdHasIfrRwys(f.ades):
                    ad = master.fir.aerodromes[f.ades]
                elif master.fir.AdHasIfrRwys(f.adep):
                    ad = master.fir.aerodromes[f.adep]

                rdes = f.desrwy
                # Get all rwys
                rwys = []
                for rwy in ad.rwy_direction_list:
                    rwys.append(rwy.txt_desig)

                entries = []
                entries.append({'label': 'Destino:', 'width': 4, 'def_value': ad.code_id})
                entries.append({'label': 'Pista:', 'width': 2, 'values': rwys, 'def_value': rdes})

                def change_rwy(e=None, avo=f, entries=None):
                    master.sendMessage({"message": "change_app_rwy", "cs": f.callsign,
                                        "ades": entries['Destino:'].get().upper(),
                                        "rdes": entries['Pista:']['value']})

                RaDialog(self.c, label=f.callsign+': Cambio de Pista durante APP',
                         ok_callback=change_rwy, entries=entries, position=(self.vt.x, self.vt.y))
                close_win()

            def b_int_ils():
                master.sendMessage({"message": "int_ils", "cs": f.callsign})
                close_win()

            def b_dir_fin():
                master.sendMessage({"message": "dir_fin", "cs": f.callsign})
                close_win()

            def b_execute_lowpass():
                master.sendMessage({"message": "execute_lowpass", "cs": f.callsign})
                close_win()

            def b_execute_map():
                master.sendMessage({"message": "execute_map", "cs": f.callsign})
                close_win()

            def define_holding():
                close_win()
                entries=[]
                entries.append({'label': 'Fijo Principal:', 'width': 5, 'def_value': f.route[0].fix})
                entries.append({'label': 'Virajes (I/D):', 'width': 1, 'def_value': ''})

                def set_holding(e=None, entries=None):
                    error = False
                    ent_hold = entries['Fijo Principal:']
                    ent_side = entries['Virajes (I/D):']
                    fijo = ent_hold.get().upper()
                    lado = ent_side.get().upper()
                    if not fijo in f.route:
                        ent_hold['bg'] = 'red'
                        ent_hold.focus_set()
                        error = True
                    if lado.upper() == 'I': std_turns = False
                    elif lado.upper() == 'D' or lado.strip() == '': std_turns = True
                    else:
                        ent_side['bg'] = 'red'
                        ent_side.focus_set()
                        error = True
                    if error:
                        return False  # Not validated correctly

                    master.sendMessage({"message":"hold", "cs":f.callsign,
                                        "fix":fijo, "std_turns": std_turns})
                RaDialog(self.c, label=f.callsign+': Poner en espera', ok_callback=set_holding, entries=entries, position=(self.vt.x, self.vt.y))

            def hdg_after_fix():
                close_win()
                entries=[]
                entries.append({'label': 'Fijo:', 'width': 5, 'def_value': str(f.route[0].fix)})
                entries.append({'label': 'Rumbo:', 'width': 3})

                def set_fix_hdg(e=None, entries=None):
                    error = False
                    ent_fix = entries['Fijo:']
                    ent_hdg = entries['Rumbo:']
                    fijo = ent_fix.get().strip().upper()
                    hdg = ent_hdg.get().strip()
                    if fijo not in f.route:
                        ent_fix['bg'] = 'red'
                        ent_fix.focus_set()
                    if not hdg.isdigit():
                        ent_hdg['bg'] = 'red'
                        ent_hdg.focus_set()
                        error = True
                    else:
                        hdg = float(hdg)
                    if error:
                        return False  # Validation failed

                    master.sendMessage({"message": "hdg_after_fix",
                                        "cs": f.callsign,
                                        "fix": fijo,
                                        "hdg": hdg})
                RaDialog(self.c,label=f.callsign+': Rumbo después de fijo',
                    ok_callback=set_fix_hdg, entries=entries, position=(self.vt.x, self.vt.y))

            def int_rdl():
                close_win()
                entries=[]
                entries.append({'label': 'Fijo:', 'width': 5, 'def_value': str(f.route[0].fix)})
                entries.append({'label': 'Radial:', 'width': 3})
                entries.append({'label': 'Desde/Hacia (D/H)', 'width': 1, 'def_value': 'D'})

                def set_rdl(e=None,entries=None):
                    error = True
                    ent_fix=entries['Fijo:']
                    ent_rdl=entries['Radial:']
                    ent_d_h=entries['Desde/Hacia (D/H)']
                    fijo = ent_fix.get().upper()
                    rdl = ent_rdl.get().upper()
                    d_h = ent_d_h.get().upper()
                    for [nombre, coord] in master.fir.coords.items():
                        if nombre == fijo:
                            auxiliar = coord
                            error = False
                            break
                    if error:
                        ent_fix['bg'] = 'red'
                        ent_fix.focus_set()
                    if not rdl.isdigit():
                        ent_rdl['bg'] = 'red'
                        ent_rdl.focus_set()
                        error = True
                    else:
                        rdl = float(rdl)
                    if d_h == 'H':
                        correccion = 180.
                    elif d_h == 'D':
                        correccion = 0.
                    else:
                        ent_d_h['bg'] = 'red'
                        ent_d_h.focus_set()
                        error = True
                    if error:
                        return False  # Validation failed

                    master.sendMessage({"message": "int_rdl",
                                        "cs": f.callsign,
                                        "fix": fijo,
                                        "track": (rdl + correccion)% 360.})

                RaDialog(self.c, label=f.callsign+': Interceptar radial',
                    ok_callback=set_rdl, entries=entries, position=(self.vt.x, self.vt.y))

            def b_orbitar():
                close_win()
                entries = []
                entries.append({'label': 'Orbitar hacia:',
                            'values': ('IZDA', 'DCHA'),
                            'def_value': 'IZDA'})

                def set_orbit(e=None,sel=f,entries=None):
                    side_aux = entries['Orbitar hacia:']['value']
                    if side_aux.upper() == 'IZDA':
                        dir = Aircraft.LEFT  # Constant defined in Aircraft.py
                    else:
                        dir = Aircraft.RIGHT
                    master.sendMessage({"message": "orbit", "cs": sel.callsign, "direction": dir})

                RaDialog(self.c, label=f.callsign+': Orbitar',
                     ok_callback=set_orbit, entries=entries, position=(self.vt.x, self.vt.y))
            win = tix.Frame(self.c, width=10)
            # Botones APP
            lbl_cls = tix.Label(win, text=self.vt.cs, bg='blue', fg='white', width=CHANGE_WIDTH)
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            but_Cer = tix.Button(win, text='x')
            but_Cer.grid(row=0, column=3)
            but_app_proc = tix.Button(win, text='APP PROC.', command=b_auth_approach)
            but_app_proc.grid(column=0, row=1, sticky=tix.E+tix.W)
            but_ils_vec = tix.Button(win, text='Vector Final a LLZ', command=b_int_ils)
            but_ils_vec.grid(column=0, row=2, sticky=tix.E+tix.W)
            but_dir_fin = tix.Button(win, text='Directo a Final', command=b_dir_fin)
            but_dir_fin.grid(column=0, row=3, sticky=tix.E+tix.W)
            but_exe_map = tix.Button(win, text='PASADA BAJA', command=b_execute_lowpass)
            but_exe_map.grid(column=0, row=4, sticky=tix.E+tix.W)
            but_exe_lowpass = tix.Button(win, text='EJECUTAR MAP', command=b_execute_map)
            but_exe_lowpass.grid(column=0, row=5, sticky=tix.E+tix.W)
            # Botones PROCs
            but_esperas = tix.Button(win, text='ESPERAS', command=define_holding)
            but_esperas.grid(column=0, row=6, sticky=tix.E+tix.W)
            but_hdg_fix = tix.Button(win, text='HDG DESPUES FIJO', command=hdg_after_fix)
            but_hdg_fix.grid(column=0, row=7, sticky=tix.E+tix.W)
            but_int_rdl = tix.Button(win, text='INT. RDL', command=int_rdl)
            but_int_rdl.grid(column=0, row=8, sticky=tix.E+tix.W)
            but_orbit = tix.Button(win, text='ORBITAR AQU?', command=b_orbitar)
            but_orbit.grid(column=0, row=9, sticky=tix.E+tix.W)

            if master.fir.AdHasIfrRwys(f.ades):
                ad = master.fir.aerodromes[f.ades]
            elif master.fir.AdHasIfrRwys(f.adep):
                ad = master.fir.aerodromes[f.adep]
            else:
                for a in master.fir.aerodromes:
                    ad = master.fir.aerodromes[a]
                    break
                # Get all rwys
            rwys = []
            for rwy in ad.rwy_direction_list:
                rwys.append(rwy.txt_desig)
            if len(rwys) > 2:
                but_rwy = tix.Button(win, text='SIDE STEP', command=b_change_rwy)
                but_rwy.grid(column=0, row=10, sticky=tix.E + tix.W)
                but_Can = tix.Button(win, text="CANCELAR")
                but_Can.grid(row=11, column=0, columnspan=2, sticky=tix.W + tix.E)  
            #
            else:
                    but_Can = tix.Button(win, text="CANCELAR")
                    but_Can.grid(row=10, column=0, columnspan=2, sticky=tix.W + tix.E)                     
            window_ident = self.c.create_window(min(self.c.winfo_width()-150, e.x), min(self.c.winfo_height()-300, e.y), anchor=tix.NW, window=win)

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)
            but_Can['command'] = close_win
            but_Cer['command'] = close_win
            self.c.bind_all("<Escape>", close_win)

        def change_altitude(self, e=None):
            # Trick to avoid geotabs showing after clicking label elements
            self.vt._message_handler(self.vt, 'alt', 'precall', 0, e)
            win = tix.Frame(self.c)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH-1)
            lbl_CFL = tix.Label(win, text="CFL:")
            ent_CFL = tix.Entry(win, width=3)
            if self.vt.mode == 'atc':
                ent_CFL.insert(0, str(int(self.vt.cfl+0.5)))
            else:
                ent_CFL.insert(0, str(self.vt.cfl))
            ent_CFL.select_range(0, tix.END)
            lbl_TFL = tix.Label(win, text="TFL:")
            ent_TFL = tix.Entry(win, width=3)
            ent_TFL.insert(0, str(int(self.vt.tfl+0.5)))
            but_Auttfl = tix.Button(win, text="AUT")
            lbl_ECL = tix.Label(win, text="ECL:")
            ent_ECL = tix.Entry(win, width=3)
            ent_ECL.insert(0, str(int(self.vt.ecl)))
            but_Autecl = tix.Button(win, text="AUT")
            lbl_ECLFIX = tix.Label(win, text="FIJO:")
            ent_ECLFIX = tix.Entry(win, width=6)
            ent_ECLFIX.insert(0, self.vt.eclfix)
            lbl_RFL = tix.Label(win, text="RFL:")
            ent_RFL = tix.Entry(win, width=3)
            ent_RFL.insert(0, str(int(self.vt.rfl+0.5)))
            but_Acp = tix.Button(win, text="ACP")
            but_Can = tix.Button(win, text="ANLR")
            but_Borr = tix.Button(win, text='x')
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            but_Borr.grid(row=0, column=3)
            lbl_CFL.grid(row=1, column=0)
            ent_CFL.grid(row=1, column=1)
            lbl_TFL.grid(row=2, column=0)
            ent_TFL.grid(row=2, column=1)
            but_Auttfl.grid(row=2, column=2)
            lbl_ECL.grid(row=3, column=0)
            ent_ECL.grid(row=3, column=1)
            but_Autecl.grid(row=3, column=2)
            lbl_ECLFIX.grid(row=4, column=0)
            ent_ECLFIX.grid(row=4, column=1)
            lbl_RFL.grid(row=5, column=0)
            ent_RFL.grid(row=5, column=1)
            but_Acp.grid(row=6, column=0, columnspan=1, sticky=tix.W+tix.E)
            but_Can.grid(row=6, column=1, columnspan=1, sticky=tix.W+tix.E)
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_CFL.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_FLs(cfl, tfl, ecl, eclfix, rfl):

                self.vt.cfl = float(cfl)
                self.vt.tfl = int(tfl)
                self.vt.ecl = int(ecl)
                self.vt.eclfix = eclfix
                self.vt.rfl = int(rfl)
                self.vt._message_handler(self.vt, 'tfl', 'update', tfl, e)
                self.vt._message_handler(self.vt, 'ecl', 'update', ecl, e)
                self.vt._message_handler(self.vt, 'eclfix', 'update', eclfix, e)
                self.vt._message_handler(self.vt, 'rfl', 'update', rfl, e)
                self.vt._message_handler(self.vt, 'cfl_c', 'update', cfl, e)
                d = self.vt._message_handler(self.vt, 'cfl', 'update', cfl, e)

                def result((r, cfl_max)):
                    if r:
                        self.vt.cfl = float(cfl)
                        self.reformat()
                        close_win()
                    else:
                        ent_CFL.delete(0, tix.END)
                        ent_CFL.insert(0, str(abs(int(cfl_max))))
                        ent_CFL['bg'] = 'red'
                        ent_CFL.focus_set()

                if self.vt.mode == 'atc':
                    result((True, None))
                else:
                    d.addCallback(result)

            def aceptar(e=None):
                cfl = ent_CFL.get()
                tfl = ent_TFL.get()
                ecl = ent_ECL.get()
                eclfix = ent_ECLFIX.get()
                rfl = ent_RFL.get()
                try:
                    set_FLs(cfl, tfl, ecl, eclfix, rfl)
                except:
                    logging.debug('invalid literal')
                # Update strip in ATCBahia
                callsign = self.vt.cs
                if self.vt.mode == 'atc':
                    if self.vt.rd.atc_bahia.showed:
                        self.vt.rd.atc_bahia.update_cfl(callsign=callsign, cfl=cfl)

            def autecl(e=None):
                cfl = ent_CFL.get()
                tfl = ent_TFL.get()
                ecl = ent_ECL.get()
                eclfix = ent_ECLFIX.get()
                rfl = ent_RFL.get()
                cfl = ecl
                set_FLs(cfl, tfl, ecl, eclfix, rfl)

            def auttfl(e=None):
                cfl = ent_CFL.get()
                tfl = ent_TFL.get()
                ecl = ent_ECL.get()
                eclfix = ent_ECLFIX.get()
                rfl = ent_RFL.get()
                cfl = tfl
                set_FLs(cfl, tfl, ecl, eclfix, rfl)
            but_Autecl['command'] = autecl
            but_Auttfl['command'] = auttfl
            but_Acp['command'] = aceptar
            but_Can['command'] = close_win
            but_Borr['command'] = close_win
            self.c.bind_all("<Return>", aceptar)
            self.c.bind_all("<KP_Enter>", aceptar)
            self.c.bind_all("<Escape>", close_win)
            self.vt._message_handler(self.vt, 'alt', '<Button-1>', None, e)

        def change_rate(self, e):
            # Trick to avoid geotabs showing after clicking label elements
            self.vt._message_handler(self.vt, 'rate', 'precall', 0, e)
            win = tix.Frame(self.c, width=10)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH-1)
            lbl_rate = tix.Label(win, text="Rate:")
            ent_rate = tix.Entry(win, width=4)
            ent_rate.insert(0, str(abs(int(self.vt.rate))))
            ent_rate.select_range(0, tix.END)
            but_Acp = tix.Button(win, text="Aceptar")
            but_Can = tix.Button(win, text="Cancelar")
            but_Cer = tix.Button(win, text="x")
            but_Std = tix.Button(win, text="Estandar")
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            but_Cer.grid(row=0, column=3)
            lbl_rate.grid(row=1, column=0)
            ent_rate.grid(row=1, column=1)
            but_Acp.grid(row=2, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Can.grid(row=3, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Std.grid(row=4, column=0, columnspan=2, sticky=tix.W+tix.E)
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_rate.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_rate(e=None):
                rate = ent_rate.get()
                if ent_rate['bg'] == 'red':
                    force = True
                else:
                    force = False
                d = self.vt._message_handler(self.vt, 'rate', 'update', (rate, force), e)

                def result((r, max_rate)):
                    if r:
                        self.vt.rate = int(rate)
                        close_win()
                    else:
                        ent_rate.delete(0, tix.END)
                        ent_rate.insert(0, str(abs(int(max_rate))))
                        ent_rate['bg'] = 'red'
                        ent_rate.select_range(0, tix.END)
                        ent_rate.focus_set()
                d.addCallback(result)

            def set_std():
                self.vt._message_handler(self.vt, 'rate', 'update', ('std', None), e)
                close_win()
            but_Acp['command'] = set_rate
            but_Can['command'] = close_win
            but_Cer['command'] = close_win
            but_Std['command'] = set_std
            self.c.bind_all("<Return>", set_rate)
            self.c.bind_all("<KP_Enter>", set_rate)
            self.c.bind_all("<Escape>", close_win)
            
        def circunflejo(self, e):
            #print('Acento circunflejo')
            self.colat.t = 'SAL^'
            i = 'colat'
            self.refresh(i)

        def change_heading(self, e):
            # Trick to avoid geotabs showing after clicking label elements
            self.vt._message_handler(self.vt, 'hdg', 'precall', 0, e)
            win = tix.Frame(self.c, width=10)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH)
            lbl_hdg = tix.Label(win, text="Heading:")
            ent_hdg = tix.Entry(win, width=3)
            ent_hdg.insert(0, str(int(self.vt.hdg)))
            ent_hdg.select_range(0, tix.END)
            ent_side = tix.OptionMenu(win, bg='white', width=20)
            num = 0
            for opc in ['ECON', 'DCHA', 'IZDA']:
                ent_side.add_command(opc)
                num = num+1
            ent_side['value'] = 'ECON'
            but_Acp = tix.Button(win, text="Aceptar")
            but_directoallz = tix.Button(win, text="Vector Final a LLZ")
            but_Can = tix.Button(win, text="Cancelar")
            but_Cer = tix.Button(win, text="x")
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            but_Cer.grid(row=0, column=3)
            lbl_hdg.grid(row=1, column=0)
            ent_hdg.grid(row=1, column=1)
            ent_side.grid(row=5, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Acp.grid(row=2, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_directoallz.grid(row=3, column=0, columnspan=2, sticky=tix.W + tix.E)
            but_Can.grid(row=4, column=0, columnspan=2, sticky=tix.W+tix.E)
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_hdg.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_heading(e=None):
                fhdg = ent_hdg.get()
                self.vt.fhdg = int(fhdg)
                self.vt.draw_fhdg = True
                opt = ent_side.cget('value')
                self.opc = opt
                self.vt._message_handler(self.vt, 'hdg', 'update', (fhdg, opt, False), e)
                close_win()

            def set_heading_DirectoLLZ(e=None):
                fhdg = ent_hdg.get()
                self.vt.fhdg = int(fhdg)
                self.vt.draw_fhdg = True
                opt = ent_side.cget('value')
                self.opc = opt
                self.vt._message_handler(self.vt, 'hdg', 'update', (fhdg, opt, True), e)
                close_win()

            but_Acp['command'] = set_heading
            but_directoallz['command'] = set_heading_DirectoLLZ
            but_Can['command'] = close_win
            but_Cer['command'] = close_win
            self.c.bind_all("<Return>", set_heading)
            self.c.bind_all("<KP_Enter>", set_heading)
            self.c.bind_all("<Escape>", close_win)
            
        def change_speed(self, e):
            # TODO we should look for server reply to confirm value setting
            # in the same way we do for cfl and rate
            # Trick to avoid geotabs showing after clicking label elements
            self.vt._message_handler(self.vt, 'spd', 'precall', 0, e)
            if self.vt.label_format == 'pp-mach':
                win = tix.Frame(self.c)
                lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH-2)
                lbl_spd = tix.Label(win, text="MACH:")
                ent_spd = tix.Entry(win, width=3)
                ent_spd.insert(0, str(int(round(float(self.mach.t)*100.0))))
                ent_spd.select_range(0, tix.END)
            else:
                win = tix.Frame(self.c)
                lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH-2)
                lbl_spd = tix.Label(win, text="IAS:")
                ent_spd = tix.Entry(win, width=3)
                if self.vt.ias < 0.1:
                    # Valores sugeridos desde la hoja 'Escenario' (ifr_taxi_ias / vfr_taxi_ias / ret_ias)
                    vfr_taxi = getattr(self.fir, 'vfr_taxi_ias', None)
                    ifr_taxi = getattr(self.fir, 'ifr_taxi_ias', getattr(self.fir, 'taxi_ias', 15.0))
                    if self.vt.rules == "VFR":
                        taxi_default = str(int(vfr_taxi if vfr_taxi is not None else 6))
                    else:
                        taxi_default = str(int(ifr_taxi))
                    try:
                        aircraft = self.vt.rd._tracks_flights[self.vt]
                        if len(aircraft.route) > 0 and aircraft.route[0].push_back:
                            ent_spd.insert(0, str(int(getattr(self.fir, 'ret_ias', 4))))  # Retroceso
                        else:
                            ent_spd.insert(0, taxi_default)
                    except (KeyError, AttributeError):
                        ent_spd.insert(0, taxi_default)
                else:
                    ent_spd.insert(0, str(int(self.vt.ias)))
                ent_spd.select_range(0, tix.END)
            
            but_Acp = tix.Button(win, text="Aceptar")
            but_Can = tix.Button(win, text="Cancelar")
            but_Cer = tix.Button(win, text="x")
            but_Std = tix.Button(win, text="Estandar")
            but_Sup = tix.Button(win, text="Puesta en marcha", fg=self.color_sup)
            but_Fire = tix.Button(win, text='Fuego motor', fg=self.color_engine)
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            but_Cer.grid(row=0, column=3)
            lbl_spd.grid(row=1, column=0)
            ent_spd.grid(row=1, column=1)
            but_Acp.grid(row=2, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Can.grid(row=3, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Std.grid(row=4, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Sup.grid(row=5, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Fire.grid(row=6, column=0, columnspan=2, sticky=tix.W+tix.E)
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_spd.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_speed(e=None):
                if self.vt.label_format == 'pp-mach':
                    spd = ent_spd.get()
                    spd = spd
                    # If entry was already displaying maximum available, let
                    # the user force the desired speed, forcing whatever speed
                    # he requested.
                    if ent_spd['bg'] == 'red':
                        force_speed = True
                    else:
                        force_speed = False
                    d = self.vt._message_handler(self.vt, 'mach', 'update', (int(spd)/100., force_speed), e)

                    def result((r, mach_max)):
                        if r:
                            close_win()
                        else:
                            ent_spd.delete(0, tix.END)
                            ent_spd.insert(0, str(abs(int(mach_max*100))))
                            ent_spd['bg'] = 'red'
                            ent_spd.focus_set()
                    d.addCallback(result)

                else:
                    spd = ent_spd.get()
                    # If entry was already displaying maximum available, let
                    # the user force the desired speed, forcing whatever speed
                    # he requested.
                    if ent_spd['bg'] == 'red':
                        force_speed = True
                    else:
                        force_speed = False
                    d = self.vt._message_handler(self.vt, 'ias', 'update', (spd, force_speed), e)

                    def result((r, d)):
                        if r:
                            close_win()
                        else:
                            ent_spd.delete(0, tix.END)
                            ent_spd.insert(0, str(abs(int(d))))
                            ent_spd['bg'] = 'red'
                            ent_spd.focus_set()
                    d.addCallback(result)

            def set_std():
                if self.vt.label_format == 'pp-mach':
                    self.vt._message_handler(self.vt, 'mach', 'update', ('std', None), e)
                else:
                    self.vt._message_handler(self.vt, 'ias', 'update', ('std', None), e)
                close_win()

            def start_up():
                if but_Sup['fg'] != 'green':
                    but_Sup.configure(fg='green')
                    but_Sup.grid(row=5, column=0, columnspan=2, sticky=tix.W+tix.E)
                else:
                    but_Sup.configure(fg='black')
                    but_Sup.grid(row=5, column=0, columnspan=2, sticky=tix.W+tix.E)
                self.color_sup = but_Sup['fg']
                self.vt._message_handler(self.vt, 'action', 'start', e)
                close_win()

            def fire_engine():
                if but_Fire['fg'] != 'red':
                    but_Fire.configure(fg='red')
                    but_Fire.grid(row=6, column=0, columnspan=2, sticky=tix.W+tix.E)
                else:
                    but_Fire.configure(fg='black')
                    but_Fire.grid(row=6, column=0, columnspan=2, sticky=tix.W+tix.E)
                self.color_engine = but_Fire['fg']
                self.vt._message_handler(self.vt, 'engine', 'fire', e)
                close_win()

            but_Acp['command'] = set_speed
            but_Can['command'] = close_win
            but_Cer['command'] = close_win
            but_Std['command'] = set_std
            but_Sup['command'] = start_up
            but_Fire['command'] = fire_engine
            self.c.bind_all("<Return>", set_speed)
            self.c.bind_all("<KP_Enter>", set_speed)
            self.c.bind_all("<Escape>", close_win)

        def change_sidok(self, e):
            sid_check = self.vt.sidok
            self.vt._message_handler(self.vt, 'sidok', 'update', sid_check, e)

        def change_holdp(self,e):
            win = tix.Frame(self.c)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white')
            lbl_hp = tix.Label(win, text="P.ESP")
            ent_hp = tix.ScrolledListBox(win, width=40)

            for key in self.fir.hp.keys():
                if key == self.vt.lrwy:
                    for hp in self.fir.hp[key]:
                        ent_hp.listbox.insert(tix.END, hp)

            lbl_cls.grid(row=0, columnspan=2)
            lbl_hp.grid(row=1, column=0)
            ent_hp.grid(row=2, column=0)
            window_ident = self.c.create_window(e.x, e.y, window=win)

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_holdp(event):
                widget = event.widget
                selection = widget.curselection()
                value = widget.get(selection[0])
                print("Set HP: ") + value
                if value != '':
                    self.vt.holdp = value
                else:
                    self.vt.holdp = 'HP'
                self.vt._message_handler(self.vt, 'holdp', 'update', self.vt.holdp, e)
                close_win()

            ent_hp.listbox.bind("<<ListboxSelect>>", set_holdp)
            self.c.bind_all("<Return>", set_holdp)
            self.c.bind_all("<KP_Enter>", set_holdp)
            self.c.bind_all("<Escape>", close_win)

        def change_gate(self,e):
            # Trick to avoid other canvas actions after clicking label elements
            win = tix.Frame(self.c)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white')
            lbl_gate = tix.Label(win, text="PUERTA")
            ent_gate = tix.ScrolledListBox(win, width=50)

            for gate in self.fir.gates:
                ent_gate.listbox.insert(tix.END, gate)

            lbl_cls.grid(row=0, columnspan=2)
            lbl_gate.grid(row=1, column=0)
            ent_gate.grid(row=2, column=0)
            window_ident = self.c.create_window(e.x, e.y, window=win)

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_gate(event):
                widget = event.widget
                selection = widget.curselection()
                value = widget.get(selection[0])
                print("Set GATE: ") + value
                if value != '':
                    self.vt.gate = value
                else:
                    self.vt.gate = '-'
                self.vt._message_handler(self.vt, 'gate', 'update', self.vt.gate, e)
                close_win()

            ent_gate.listbox.bind("<<ListboxSelect>>", set_gate)
            self.c.bind_all("<Return>", set_gate)
            self.c.bind_all("<KP_Enter>", set_gate)
            self.c.bind_all("<Escape>", close_win)

        def change_rutrod(self, e):
            # Frame que actuar? como "ventanita" dentro del canvas
            win = tix.Frame(self.c, bd=1, relief='raised')

            # Cabecera + botón "X"
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white',
                                width=CHANGE_WIDTH - 4)
            but_close = tix.Button(win, text="X", width=2)

            lbl_echo = tix.Label(win, text="MNS:")
            ent_text = tix.Entry(win, width=7)

            try:
                ent_text.insert(0, self.rutrod.t)
            except:
                logging.debug("Unable change label text: %s", self.rutrod.t)

            ent_text.select_range(0, tix.END)

            but_Acp = tix.Button(win, text="Aceptar")
            but_Can = tix.Button(win, text="Cancelar")

            # Distribución en grid
            # Fila 0: título + botón X
            lbl_cls.grid(row=0, column=0, sticky=tix.W + tix.E)
            but_close.grid(row=0, column=1, sticky=tix.E)

            # Fila 1: etiqueta + entry
            lbl_echo.grid(row=1, column=0, sticky=tix.W)
            ent_text.grid(row=1, column=1, sticky=tix.E)

            # Fila 2 y 3: botones ocuparán las 2 columnas
            but_Acp.grid(row=2, column=0, columnspan=2, sticky=tix.W + tix.E)
            but_Can.grid(row=3, column=0, columnspan=2, sticky=tix.W + tix.E)

            # Se crea la "ventanita" dentro del canvas
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_text.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                w.delete(ident)

            def set_text(e=None):
                lb_text = ent_text.get().upper()[:7]
                if lb_text != '':
                    self.vt.rutrod = lb_text
                else:
                    self.vt.rutrod = '-'
                self.vt._message_handler(self.vt, 'rutrod', 'update', self.vt.rutrod, e)
                close_win()

            # Asignación de comandos
            but_Acp['command'] = set_text
            but_Can['command'] = close_win
            but_close['command'] = close_win  # <- el "aspa" cierra la ventanita

            # Bind de teclas
            self.c.bind_all("<Return>", set_text)
            self.c.bind_all("<KP_Enter>", set_text)
            self.c.bind_all("<Escape>", close_win)

        def change_sid(self, e):
            self.vt._message_handler(self.vt, 'sid_star', 'change_procedure', 0, e)

        def change_trans(self, e):
            # Trick to avoid other canvas actions after clicking label elements
            self.vt._message_handler(self.vt, 'trans', 'precall', 0, e)
            win = tix.Frame(self.c)
            lbl_cls = tix.Label(win, text=self.cs.t, bg='blue', fg='white', width=CHANGE_WIDTH-2)
            lbl_trans = tix.Label(win, text="TRANSPONDER CODE:")
            # ent_trans = tix.Entry(win, width=5)
            ent_trans = tix.ComboBox(win,options='listbox.height 6')
            ent_trans.entry['state'] = "normal"
            ent_trans['editable'] = True
            ent_trans.entry['width'] = 5
            ent_trans['listwidth'] = 15
            ent_trans.insert(tix.END, 'EMG')
            ent_trans.insert(tix.END, 'SEC')
            ent_trans.insert(tix.END, 'COM')
            ent_trans.insert(tix.END, 'IDE')
            try:
                # ent_trans.insert(0, self.trans.t)
                ent_trans['selection']=self.trans.t
            except:
                logging.debug("Unable to set trans:" % s, self.trans.t)
            # ent_trans.select_range(0, tix.END)

            but_Acp = tix.Button(win, text="Aceptar")
            but_Can = tix.Button(win, text="Cancelar")
            lbl_cls.grid(row=0, columnspan=2, sticky=tix.W+tix.E)
            lbl_trans.grid(row=1, column=0)
            ent_trans.grid(row=1, column=1)
            but_Acp.grid(row=2, column=0, columnspan=2, sticky=tix.W+tix.E)
            but_Can.grid(row=3, column=0, columnspan=2, sticky=tix.W+tix.E)
            window_ident = self.c.create_window(e.x, e.y, window=win)
            ent_trans.focus_set()

            def close_win(e=None, ident=window_ident, w=self.c):
                w.unbind_all("<Return>")
                w.unbind_all("<KP_Enter>")
                w.unbind_all("<Escape>")
                self.c.delete(ident)

            def set_trans(e=None):
                # trans_in = ent_trans.get().upper()[:4]
                trans_in = ent_trans['selection'].upper()[:4]
                if trans_in == '7500':
                    trans = 'SEC'
                elif trans_in == '7600':
                    trans = 'COM'
                elif trans_in == '7700':
                    trans = 'EMG'
                elif trans_in == 'IDE':
                    trans = 'IDE'
                elif trans_in == '':
                    trans = self.vt.trans
                else:
                    trans = trans_in
                self.vt.trans = trans
                self.vt._message_handler(self.vt, 'set_trans', 'update', trans, e)
                close_win()

            but_Acp['command'] = set_trans
            but_Can['command'] = close_win
            self.c.bind_all("<Return>", set_trans)
            self.c.bind_all("<KP_Enter>", set_trans)
            self.c.bind_all("<Escape>", close_win)

class LAD(object):
    """Línea azimut distance = azimut distance line
    
    A graphical line showing distance, bearing, and if aircraft are involved,
    minimum crossing time, and minimum crossing distance"""
    
    # Color is a class attribute
    lad_color = SmartColor("#%04x%04x%04x" % (150*257, 158*257, 20*257))  # Lighter orange than the 'orange'
    super_lad_color = SmartColor('red')
    
    def __init__(self, radisplay, e):
    
        rd = self.radisplay = radisplay
        c = radisplay.c
        
        # No se estaba definiendo un LAD. Comenzar a definir uno
        self.start = self.get_acft_or_point(e.x, e.y)
        ra_unbind(rd, c, '<Motion>')
        ra_unbind(rd, c, '<Button-2>')
        ra_unbind(rd, c, '<Button-3>')
        ra_bind(rd, c, '<Motion>', self.update_lad_being_defined)
        ra_bind(rd, c, '<Button-2>', self.cancel_def_lad)
        ra_bind(rd, c, '<Button-3>', self.end_def_lad)
        
        self.superlad = False
        self.text_id1 = None
        self.text_id2 = None
        self.text_id3 = None
        self.text_id4 = None
        
    def __del__(self):
        logging.debug("LAD.__del__")



    class fix_point:
        """This class acts as a stationary radar track"""
        def __init__(self, world_pos, screen_pos):
            self.wx, self.wy = world_pos
            self.x, self.y = screen_pos
            self.visible = True
            self.track = 0.01
            self.gs = 0.01

    def get_anchor(self, angulo=0.0):
        if (angulo >= 0.0 and angulo < 90.0) or (angulo == 360.0): return {'anchor':tix.NW}
        if angulo >= 90.0 and angulo < 180.0: return {'anchor':tix.NE}
        if angulo >= 180.0 and angulo < 270.0: return {'anchor':tix.NW}
        if angulo >= 270.0 and angulo < 360.0: return {'anchor':tix.NE}
        
    def get_lad_label_position(self, angulo, lad_center_x, lad_center_y, distance):
        if angulo == 360.0: angulo = 0.0
        if (angulo >= 0.0 and angulo < 90.0) or (angulo >= 180.0 and angulo < 270.0):
            x1 = lad_center_x+distance/sqrt(2.0)
            y1 = lad_center_y+distance/sqrt(2.0)
        
        if (angulo >= 90.0 and angulo < 180.0) or (angulo >= 270.0 and angulo < 360.0):
            x1 = lad_center_x-distance/sqrt(2.0)
            y1 = lad_center_y+distance/sqrt(2.0)
        return (x1, y1)
            
    def get_acft_or_point(self, x, y):
        # Returns the closest acft to (x,y) or otherwise a point
        min_snap_distance = 8.
        closest_track = None
        for track in self.radisplay.tracks:
            if track.visible:
                (x0, y0) = (track.x, track.y)
                dist = sqrt((x - x0)**2 + (y - y0)**2)
                if dist < min_snap_distance:
                    closest_track = track
                    min_snap_distance = dist
        if closest_track is None:
            closest_track = self.fix_point(self.radisplay.undo_scale((x, y)), (x, y))
        return closest_track
        
    def cancel_def_lad(self, e=None):
        rd = self.radisplay
        c = rd.c
        c.delete('lad_defined')
        ra_unbind(rd, c, '<Motion>')
        ra_unbind(rd, c, '<Button-2>')
        ra_unbind(rd, c, '<Button-3>')
        ra_bind(rd, c, '<Button-2>', rd.b2_cb)
        ra_bind(rd, c, '<Button-3>', rd.b3_cb)
        rd.b2_cb(e)
        rd.defining_lad = False
        
    def update_lad_being_defined(self, e=None):
        canvas = self.radisplay.c
        canvas.delete('lad_defined')
        (x0, y0) = self.start.x, self.start.y
        end = self.radisplay.undo_scale((e.x, e.y))
        lad_xsize = end[0] - self.start.wx
        lad_ysize = end[1] - self.start.wy
        angulo = 90.0 - degrees(atan2(lad_ysize, lad_xsize))
        if angulo < 0.0: angulo += 360.0
        dist = self.round_down(sqrt(lad_xsize * lad_xsize + lad_ysize * lad_ysize))
        try:
            time_min = 60.0 * dist / self.start.gs
        except:
            pass
        lad_center_x = (x0 + e.x)/2
        lad_center_y = (y0 + e.y)/2
        canvas.create_line(x0, y0, e.x, e.y, fill=self.lad_color.get(), tags="lad_defined")
        lad_text1 = "A: %03d" % angulo
        lad_text2 = "D: %05.1f" % dist
        # Check if LAD begins in a point or in a plane
        if self.start.gs < 10.:
            lad_text3 = ""
            lad_lines = 2  # LAD will show 2 lines with information (Azimuth, Distance)
        else:
            lad_text3 = "T: %03d" % time_min
            lad_lines = 3  # LAD will show 3 lines with information (Azimuth, Distance and Time to reach)
        label_font = self.radisplay.label_font
        lad_rect_width = self.radisplay.label_font.measure(lad_text1)
        lad_line_height = label_font.metrics('ascent')
        anchor_ = self.get_anchor(angulo)
        lad_text = lad_text1+"\n"+lad_text2
        if lad_text3 != "":lad_text += "\n"+lad_text3
        (lad_x, lad_y) = self.get_lad_label_position(angulo, lad_center_x, lad_center_y, 5)
        canvas.create_text(lad_x, lad_y, text=lad_text, fill=self.lad_color.get(), tags="lad_defined", justify=tix.LEFT, **anchor_)

    def end_def_lad(self, e=None):
        rd = self.radisplay
        c = rd.c
        c.delete('lad_defined')
        ra_unbind(rd, c, '<Motion>')
        ra_unbind(rd, c, '<Button-2>')
        ra_unbind(rd, c, '<Button-3>')
        self.end=self.get_acft_or_point(e.x,e.y)
        self.radisplay.lads.append(self)
        ra_bind(rd, c, '<Button-2>', rd.b2_cb)
        ra_bind(rd, c, '<Button-3>', rd.b3_cb)
        rd.b3_cb(e)
        rd.defining_lad = False
        self.redraw()
        
    def delete(self, e=None):
        canvas = self.radisplay.c
        s = str(self)
        
        if self.text_id1 is not None:
            ra_cleartagbinds(self.text_id1, canvas)
        canvas.delete(s+'lad')
        self.radisplay.lads.remove(self)
        if e is not None:
            self.radisplay.cancel_lad_serial = e.serial
            
    def redraw(self):
        canvas = self.radisplay.c
        do_scale = self.radisplay.do_scale
        label_font = self.radisplay.label_font
        s = str(self)
        
        self.delete()
        
        # Create a new LAD
        self.radisplay.lads.append(self)
        
        (xinitA, yinitA) = (self.start.wx, self.start.wy)
        (xinitB, yinitB) = (self.end.wx, self.end.wy)
        lad_xdif = xinitB - xinitA
        lad_ydif = yinitB - yinitA
        current_azimuth = 90.0 - degrees(atan2(lad_ydif, lad_xdif))
        if current_azimuth < 0.0: current_azimuth += 360.0
        lad_lines = 2  # 2 lines of text if planes won't cross; 4 if they will cross
        text1 = "A: %03d" % current_azimuth
        current_distance = self.round_down(sqrt(lad_xdif*lad_xdif + lad_ydif*lad_ydif))
        text2 = "D: %05.1f" % current_distance
        text_lad = text1+"\n"+text2
        (x0, y0) = do_scale((xinitA, yinitA))
        (x1, y1) = do_scale((xinitB, yinitB))
        if self.superlad:
            color = self.super_lad_color.get()

        else:
            color = self.lad_color.get()
        self.line_id = canvas.create_line(x0, y0, x1, y1, fill=color, tags=(s+'lad', s+'line'))
        xm = (x0+x1) / 2
        ym = (y0+y1) / 2
        min_dist_time = self.compute_mindisttime(xinitA, yinitA, self.start.track, self.start.gs, xinitB, yinitB, self.end.track, self.end.gs)
        # Limit min_dist_time<500 to avoid overflow problems when min_dist_time is too high
        if (min_dist_time is not None) and (min_dist_time > 0.0) and (min_dist_time < 500.0):
            # Flights will cross
            min_dist = self.compute_mindist(xinitA, yinitA, self.start.track, self.start.gs, xinitB, yinitB, self.end.track, self.end.gs)
            lad_lines = 4  # 4 lines of text in LAD square

            text3 = "T: %03d" % min_dist_time
            text4 = "C: %05.1f" % min_dist
            text_lad += "\n"+text3+"\n"+text4
            
        lad_line_height = label_font.metrics('ascent')
        lad_label_anchor = self.get_anchor(current_azimuth)
        (x_lad, y_lad) = self.get_lad_label_position(current_azimuth, xm, ym, 10)
        self.text_id1 = canvas.create_text(x_lad, y_lad, text=text_lad, fill=self.lad_color.get(),
                                           tags=(s+'lad', s+'text'), justify=tix.LEFT, **lad_label_anchor)
            
        ra_tag_bind(canvas, self.text_id1, '<Button-1>', self.toggle_superlad)
        ra_tag_bind(canvas, self.text_id1, '<Button-2>', self.delete)
            
        if self.superlad and (min_dist_time is not None) and (min_dist_time > 0.0):
            # Flights will cross
            size = 2
            (posAx, posAy, posBx, posBy) = self.compute_cross_points(xinitA, yinitA, self.start.track, self.start.gs, xinitB, yinitB, self.end.track, self.end.gs)
            (crossAx, crossAy) = do_scale((posAx, posAy))
            (crossBx, crossBy) = do_scale((posBx, posBy))
            canvas.create_line(x0, y0, crossAx, crossAy, fill=self.super_lad_color.get(), tags=(s+'lad', s+'crosspoint'))
            canvas.create_rectangle(crossAx-size, crossAy-size, crossAx +size, crossAy +size, fill=self.super_lad_color.get(), tags=(s+'lad', s+'crosspoint'))
            canvas.create_line(x1, y1, crossBx, crossBy, fill=self.super_lad_color.get(), tags=(s+'lad', s+'crosspoint'))
            canvas.create_rectangle(crossBx - size, crossBy -size, crossBx + size, crossBy + size, fill=self.super_lad_color.get(), tags=(s+'lad', s+'crosspoint'))
            
        canvas.addtag_withtag('lad', s+'lad')
        canvas.lift('lad')
        canvas.lift('track')
            
    def toggle_superlad(self, e=None):
        self.superlad = not self.superlad
        self.redraw()
        
    def compute_mindisttime(self,xA, yA, headingA, speedA, xB, yB, headingB, speedB):
        # 60.0: miles per minute per knot
        try:
            vxA = speedA/60.0 * sin(radians(headingA))
            vyA = speedA/60.0 * cos(radians(headingA))
            vxB = speedB/60.0 * sin(radians(headingB))
            vyB = speedB/60.0 * cos(radians(headingB))
            t = -((xA-xB)*(vxA-vxB)+(yA-yB)*(vyA-vyB)) / ((vxA-vxB)*(vxA-vxB)+(vyA-vyB)*(vyA-vyB))
            # A veces al dividir entre algo muy pequeño no se obtiene excepción, sino un valor
            # flotante de "NaN" o de "inf" (error del Python). Forzamos excepción en estos casos.
            dummy = int(t)
            return t
        except:
            return None
            
    def compute_cross_points(self,xA, yA, headingA, speedA, xB, yB, headingB, speedB):
        time_to_mindist = self.compute_mindisttime(xA, yA, headingA, speedA, xB, yB, headingB, speedB)
        vxA = speedA/60.0 * sin(radians(headingA))
        vyA = speedA/60.0 * cos(radians(headingA))
        vxB = speedB/60.0 * sin(radians(headingB))
        vyB = speedB/60.0 * cos(radians(headingB))
        posAx = xA + vxA * time_to_mindist
        posAy = yA + vyA * time_to_mindist
        posBx = xB + vxB * time_to_mindist
        posBy = yB + vyB * time_to_mindist
        return (posAx, posAy, posBx, posBy)
        
    def compute_mindist(self,xA, yA, headingA, speedA, xB, yB, headingB, speedB):
        (posAx, posAy, posBx, posBy) = self.compute_cross_points(xA, yA, headingA, speedA, xB, yB, headingB, speedB)
        return self.round_down(sqrt((posAx-posBx)*(posAx-posBx) + (posAy-posBy)*(posAy-posBy)))
    
    def round_down(self,a):
        b = int(10.0*a)
        return b / 10.0

class GEOTAB(object):
    """A graphical tab showing geo coordinates of a point"""
    # Color is a class attribute
    geotab_color = SmartColor("#%04x%04x%04x" % (250*257,158*257,20*257))  #Lighter orange than the 'orange'

    def __init__(self,radisplay,e):
        if e.serial==radisplay.cancel_geotab_serial: return
        self.radisplay=radisplay
        canvas=self.c=radisplay.c
        s=str(self)
        (x,y) = radisplay.undo_scale((e.x, e.y))
        self.coords = (x,y)
        (lat,lon) = radisplay.fir.NM2Geo(x, y)
        geotab_text1 = "Lat: %08.4f" % lat + "Lon: %09.4f" % lon
        geotab_text2 = "X: %08.4f" % x + "Y: %08.4f" % y
        self.geotab_text = geotab_text1+"\n"+geotab_text2
        anchor_= self.get_anchor()
        self.text_id1 = canvas.create_text(e.x, e.y, text=self.geotab_text, fill=self.geotab_color.get(), tags=(s+'geotab',s+'text'),justify=tix.LEFT,**anchor_)
        radisplay.geotabs.append(self)
        ra_tag_bind(canvas,self.text_id1,'<Button-2>',self.delete)

    def __del__(self):
        logging.debug("GEOTAB.__del__")

    def get_anchor(self):
        return {'anchor':tix.NE}

    def redraw(self):
        canvas=self.c
        s=str(self)
        (x,y) = self.radisplay.do_scale(self.coords)
        anchor_= self.get_anchor()
        self.delete()
        self.text_id1 = canvas.create_text(x, y, text=self.geotab_text, fill=self.geotab_color.get(), tags=(s+'geotab',s+'text'),justify=tix.LEFT,**anchor_)
        ra_tag_bind(canvas,self.text_id1,'<Button-2>',self.delete)
        canvas.addtag_withtag('geotab',s+'geotab')
        canvas.lift(s+'geotab')
        self.radisplay.geotabs.append(self)

    def delete(self,e=None):
        canvas=self.c
        s=str(self)

        if self.text_id1 is not None:
            ra_cleartagbinds(self.text_id1, canvas)
        canvas.delete(s+'geotab')
        self.radisplay.geotabs.remove(self)
        if e is not None:
            self.radisplay.cancel_geotab_serial = e.serial
            self.radisplay.cancel_lad_serial = e.serial


class RaMap(object):
    """A static radar map"""
    
    def __init__(self, canvas, do_scale, intensity=1.0):
        self.id                 = 'map'+str(id(self))
        self.canvas             = canvas
        self.do_scale           = do_scale
        self.texts              = {}  # Text items attributes
        self.polylines          = {}  # Polyline items attributes
        self.polygons           = {}  # Polygon items attributes
        self.arcs               = {}  # Arc items attributes
        self.circles            = {}
        self.symbols            = {}  # Symbol items attributes
        self._intensity         = intensity
        self.hidden             = False
    
    def add_text(self, text, pos, color='gray',anchor='sw'):
        c = SmartColor(color, self.intensity).get()
        i = self.canvas.create_text(self.do_scale(pos), text=text, fill=c,
                          tag=(self.id, self.id+'text','map'),anchor=anchor,font='-*-Helvetica-Bold-*--*-9-*-')
        self.texts[i] = (text, pos, color)

    def add_polyline(self, *coords, **kw):
        try: color = kw['color']
        except: color = 'gray'
        c = SmartColor(color, self.intensity).get()
        kw = {"fill": c, 'tag': (self.id, 'map')}
        new_coords = [self.do_scale(p) for p in coords]
        i = self.canvas.create_line(*new_coords, **kw)
        self.polylines[i] = (color, coords)
        
    def add_polygon(self, *coords, **kw):
        try: color = kw['color']
        except: color = 'gray'
        c = SmartColor(color, self.intensity).get()
        kw = {"fill": c, 'tag': (self.id, 'map')}
        new_coords = [self.do_scale(p) for p in coords]
        i = self.canvas.create_polygon(*new_coords, **kw)
        self.polygons[i] = (color, coords)    
        
    def add_arc(self, top_left, bottom_right, start, extent, color='gray'):
        c = SmartColor(color, self.intensity).get()
        tl, br = self.do_scale(top_left), self.do_scale(bottom_right)
        i = self.canvas.create_arc(tl, br, start=start, extent=extent,
                     outline=c, style='arc', tag=(self.id, self.id+'arc','map'))
        self.arcs[i] = (top_left, bottom_right, start, extent, color)

    ##############Para diujar los circulos y rellenarlos
    def add_circle(self, top_left, bottom_right, start, extent, color='gray'):
        c = SmartColor(color, self.intensity).get()
        tl, br = self.do_scale(top_left), self.do_scale(bottom_right)
        i = self.canvas.create_arc(tl, br, start=start, extent=extent,
                     fill = color,  tag=(self.id, self.id+'circle','map')) ##############para rellenar los circulos, le estoy quitando "style='arc'"antes de tag
        self.circles[i] = (top_left, bottom_right, start, extent, color)

    def add_symbol(self, type, pos, color='gray'):
        c = SmartColor(color, self.intensity).get()
        (cx,cy) = self.do_scale(pos)
        tags = [self.id, self.id+'symbol', 'map', 'symbol']
        canvas = self.canvas
        if type == VOR:
            radio = 5.0
            i = canvas.create_oval(cx-radio,cy-radio,cx+radio,cy+radio,outline=c,activeoutline='orange',
                          fill='',width=2)
            tags.append(self.id+'symbol'+str(i))
            tags_outline = tags + [self.id+'symbol'+str(i)+'outline', self.id+'symboloutline']
            canvas.itemconfigure(i, tag=tuple(tags_outline))
            radio = 5.0/1.3
            tags = tuple(tags + [self.id+'symbol'+str(i)+'fill'])
            canvas.create_line(cx+radio,cy-radio,cx-radio,cy+radio,fill=c,tag=tags)
            canvas.create_line(cx-radio,cy-radio,cx+radio,cy+radio,fill=c,tag=tags)
        elif type == NDB:
            radio = 4.5
            i = canvas.create_oval(cx-radio,cy-radio,cx+radio,cy+radio,outline=c,activeoutline='orange',fill='',width=1)
            tags += [self.id+'symbol'+str(i), self.id+'symbol'+str(i)+'outline', self.id+'symboloutline']
            tags = tuple(tags)
            canvas.itemconfigure(i, tag=tags)
        elif type == FIX:
            coord_pol = (cx,cy-3.,cx+3.,cy+2.,cx-3.,cy+2.,cx,cy-3.)
            i = canvas.create_polygon(coord_pol,outline=c,activeoutline='orange',fill='',width=1)
            tags += [self.id+'symbol'+str(i), self.id+'symbol'+str(i)+'outline', self.id+'symboloutline']
            tags = tuple(tags)
            canvas.itemconfigure(i, tag=tags)
        elif type == SMALL_CIRCLE:
            radio = 2
            i = canvas.create_oval(cx-radio,cy-radio,cx+radio,cy+radio,outline=c,fill=c,width=1)
            tags += [self.id+'symbol'+str(i), self.id+'symbol'+str(i)+'outline', self.id+'symboloutline', self.id+'symbol'+str(i)+'fill']
            tags = tuple(tags)
            canvas.itemconfigure(i, tag=tags)
        elif type == BIG_CIRCLE:
            radio = 3
            i = canvas.create_oval(cx-radio,cy-radio,cx+radio,cy+radio,outline=c,fill=c,width=1)
            tags += [self.id+'symbol'+str(i), self.id+'symbol'+str(i)+'outline', self.id+'symboloutline', self.id+'symbol'+str(i)+'fill']
            tags = tuple(tags)
            canvas.itemconfigure(i, tag=tags)
        self.symbols[i]=(type, pos, color, (cx,cy))
        
    def reposition(self):
        """Reset coordinates according to the parent's coordinate system"""
        for item, (color, coords) in self.polylines.items()+self.polygons.items():
            new_coords = [c for p in coords for c in self.do_scale(p)]
            self.canvas.coords(item, *new_coords)
        for item, (type, pos, color, screen_pos) in self.symbols.items():
            new_screen_pos = self.do_scale(pos)
            (dx, dy) = r(new_screen_pos, screen_pos)
            self.canvas.move(self.id+'symbol'+str(item), dx, dy)
            self.symbols[item] = (type, pos, color, new_screen_pos)
        for item, (text, pos, color) in self.texts.items():
            new_coords = [c for c in self.do_scale(pos)]
            self.canvas.coords(item, *new_coords)
        for item, (top_left, bottom_right, start, extent, color) in self.arcs.items():
            new_coords = [c for p in (top_left, bottom_right) for c in self.do_scale(p)]
            self.canvas.coords(item, *new_coords)
        #############################Para dibujar los circulos de relleno----->hacer la escala
        for item, (top_left, bottom_right, start, extent, color) in self.circles.items():
            new_coords = [c for p in (top_left, bottom_right) for c in self.do_scale(p)]
            self.canvas.coords(item, *new_coords)
            
    def hide(self):
        if self.hidden: return()
        for item in self.polylines.keys()+self.polygons.keys()+self.texts.keys():
            self.canvas.itemconfigure(item, fill='')
        self.canvas.itemconfigure(self.id+'symbol', fill='')
        self.canvas.itemconfigure(self.id+'symboloutline', outline='')
        self.canvas.itemconfigure(self.id+'arc', outline = '')
        self.canvas.itemconfigure(self.id+'circle', fill = '') ###################para dejar de ver los circulos de las Barras de Parada
        self.hidden = True
            
    def show(self, force=False):
        if not self.hidden and not force: return
        # For performance reasons we want to group the itemconfig
        # so first we set temporary tags, and then do the itemconfig for each group
        # of items with the same color
        tags = {}  
        self.reposition()
        for item, (color, coords) in self.polylines.items()+self.polygons.items():
            color = SmartColor(color, self.intensity).get()
            tag = 'refill'+color
            self.canvas.addtag_withtag(tag, item)
            tags[tag] = color
        for item, (type, pos, color, screen_pos) in self.symbols.items():
            color = SmartColor(color, self.intensity).get()
            tag = 'refill'+color
            self.canvas.addtag_withtag(tag, self.id+'symbol'+str(item)+'fill')
            tags[tag] = color
            tag = 'reoutline'+color
            self.canvas.addtag_withtag(tag, self.id+'symbol'+str(item)+'outline')
            tags[tag] = color
        for item, (text, pos, color) in self.texts.items():
            color = SmartColor(color, self.intensity).get()
            tag = 'refill'+color
            self.canvas.addtag_withtag(tag, item)
            tags[tag] = color
        for item, (top_left, bottom_right, start, extent, color) in self.arcs.items():
            color = SmartColor(color, self.intensity).get()
            tag = 'reoutline'+color
            self.canvas.addtag_withtag(tag, item)
            tags[tag] = color

############################################################################Para ver los circulos de las Barras de Parada
        for item, (top_left, bottom_right, start, extent, color) in self.circles.items():
            color = SmartColor(color, self.intensity).get()
            tag = 'refill'+color
            self.canvas.addtag_withtag(tag, item)
            tags[tag] = color

        for (tag, color) in tags.items():
            if tag.startswith('refill'):
                self.canvas.itemconfigure(tag, fill=color)
            elif tag.startswith('reoutline'):
                self.canvas.itemconfigure(tag, outline=color)
            else:
                logging.error("Impossible scenario in RaMap.show()")
            self.canvas.dtag(tag, tag)
        self.hidden = False
            
    def toggle(self):
        if self.hidden:
            self.show()
        else:
            self.hide()
            
    def get_intensity(self): return self._intensity

    def set_intensity(self, value):
        self._intensity = value
        if not self.hidden:
            self.show(force=True)
    intensity = property(get_intensity, set_intensity)
        
    def destroy(self):

        self.canvas.delete(self.id)
        del self.canvas
        del self.do_scale    

class Storm(object):
    def __init__(self, radisplay, e):
    
        self.radisplay = radisplay
        #dummy canvas
        canvas = radisplay.c
        
        # Start defining a storm
        self.x, self.y = e.x, e.y
        (self.wx, self.wy) = self.radisplay.undo_scale((e.x, e.y))
        self._motion_id = canvas.bind('<Motion>', self.update_storm_being_defined)
        self._button2_id = canvas.bind('<Button-2>', self.cancel_def_storm)
        self._button3_id = canvas.bind('<Button-3>', self.end_def_storm)
        self.selected = False

    def update_storm_being_defined(self, e=None):
        canvas = self.radisplay.c
        canvas.delete('storm_defined')
        x, y = self.x, self.y
        r = sqrt((x-e.x)**2+(y-e.y)**2)
        x0, x1, y0, y1 = x-r, x+r, y-r, y+r
        canvas.create_oval(x0, y0, x1, y1, fill="", outline="yellow", tags="storm_defined")
        r *= 1.4
        x0, x1, y0, y1 = x-r, x+r, y-r, y+r
        canvas.create_oval(x0, y0, x1, y1, fill="", outline="yellow", tags="storm_defined", dash=(10, 10))
        
    def cancel_def_storm(self, e=None):
        canvas = self.radisplay.c
        canvas.delete('storm_defined')
        canvas.unbind('<Motion>', self._motion_id)
        canvas.unbind('<Button-2>', self._button2_id)
        canvas.unbind('<Button-3>', self._button3_id)
        canvas.bind('<Button-2>', self.radisplay.b2_cb)
        canvas.bind('<Button-3>', self.radisplay.b3_cb)
        self.radisplay.b3_cb(e)

    def end_def_storm(self, e=None):
        canvas = self.radisplay.c
        canvas.delete('storm_defined')
        canvas.unbind('<Motion>', self._motion_id)
        canvas.unbind('<Button-2>', self._button2_id)
        canvas.unbind('<Button-3>', self._button3_id)
        x, y = self.x, self.y
        wx, wy = self.wx, self.wy
        self.wrx, self.wry = self.radisplay.undo_scale((e.x, e.y))
        self.r = sqrt((x-e.x)**2+(y-e.y)**2)
        canvas.bind('<Button-2>', self.radisplay.b2_cb)
        canvas.bind('<Button-3>', self.radisplay.b3_cb)
        self.radisplay.b3_cb(e)
        self.redraw()

    def delete(self):
        try:
            self.radisplay.storms.remove(self)
        except:
            pass
        s=str(self)
        self.radisplay.c.delete(s+'storm')

    def redraw(self):
        canvas = self.radisplay.c
        do_scale = self.radisplay.do_scale
        s = str(self)
        self.delete()
        
        # Create a new storm
        self.radisplay.storms.append(self)

        (x, y) = (self.x, self.y) = do_scale((self.wx, self.wy))
        rx, ry = do_scale((self.wrx, self.wry))
        r = sqrt((x-rx)**2+(y-ry)**2)
        x0, x1, y0, y1 = x-r, x+r, y-r, y+r
        if self.selected:
            ts_color = 'red'
        else:
            ts_color = 'yellow'
        canvas.create_oval(x0, y0, x1, y1, fill="", outline=ts_color, tags=(s+'storm', 'storm'))
        r *= 1.4
        x0, x1, y0, y1 = x-r, x+r, y-r, y+r
        canvas.create_oval(x0, y0, x1, y1, fill="", outline=ts_color, tags=(s+'storm', 'storm'), dash=(10, 10))
        
    def auto_select_storm(self, event=None, min_pixel_distance=50):
        former_selection = self.selected
        distance = sqrt((self.x-event.x)**2+(self.y-event.y)**2)
        if distance < min_pixel_distance:
            self.selected = True
        else:
            self.selected = False
        if former_selection != self.selected:
            self.redraw()
