#!/usr/bin/python
# -*- coding:iso8859-15 -*-
# $Id: RemoteClient.py 2381 2007-05-30 19:32:42Z rodrigo $
#
#
# Sys imports
import sys

sys.path.append("lib")
import cPickle

pickle = cPickle
if not (sys.version_info[0] == 2 and sys.version_info[1] < 7):
    import dill
import logging
import zlib
import Tix

# Twisted imports
from twisted.internet import reactor, defer
from twisted.internet.protocol import ClientCreator
from twisted.protocols.basic import NetstringReceiver

# Program imports
from Pseudopilot import PpDisplay
from UCS import UCS
from FIR import *
# from StripSeries import StripSeries
import Route  # In order to set the fir object
from copy import deepcopy

# Constants
PSEUDOPILOT = "pseudopilot"
ATC = "ATC"


class GTA_Client_Protocol(NetstringReceiver):

    def __init__(self):
        self.command_no = 0
        self.defer_list = {}
        self.MAX_LENGTH = 10000000  # The Twisted NetstringReceiver drops the connection for messages longer than this.
        self._message_queue = []              
        self._processing_message = False     
        
    """
    def stringReceived(self, line):
        line = zlib.decompress(line)
        try:
            if sys.version_info[0] == 2 and sys.version_info[1] < 7:
                m = pickle.loads(line)
            else:
                m = dill.loads(line)
        except:
            logging.critical("Unable to unpickle")
            return

        # If the received message was a reply to a previous
        # command, fire the callback for it.
        if m['message'] == 'reply':
            self.defer_list[m['command_no']].callback(m['data'])
            return

        try:
            self.client.process_message(m)
        except:
            logging.error("Unable to process server message %s" % m, exc_info=True)

    """

    def stringReceived(self, line):
        from twisted.internet import threads
        
        def deserialize_in_thread(compressed_line):
            decompressed = zlib.decompress(compressed_line)
            if sys.version_info[0] == 2 and sys.version_info[1] < 7:
                return pickle.loads(decompressed)
            else:
                return dill.loads(decompressed)
        
        def process_next_message():
            if not self._message_queue or self._processing_message:
                return
            
            self._processing_message = True
            m = self._message_queue.pop(0)
            
            if m['message'] == 'reply':
                self.defer_list[m['command_no']].callback(m['data'])
            else:
                try:
                    self.client.process_message(m)
                except:
                    logging.error("Unable to process server message %s" % m, exc_info=True)
            
            self._processing_message = False
            process_next_message()  # Procesar siguiente
        
        def on_deserialized(m):
            self._message_queue.append(m)
            process_next_message()
        
        d = threads.deferToThread(deserialize_in_thread, line)
        d.addCallback(on_deserialized)
        d.addErrback(lambda failure: logging.critical("Unable to unpickle %s" % failure))
    
    def sendMessage(self, object):
        object = {"command_no": self.command_no, "data": object}
        if sys.version_info[0] == 2 and sys.version_info[1] < 7:
            line = pickle.dumps(object, protocol=-1)
        else:
            line = dill.dumps(object)
        zline = zlib.compress(line)
        self.sendString(zline)
        d = defer.Deferred()
        self.defer_list[self.command_no] = d
        reactor.callLater(5, self.replyTimeout, d, self.command_no)
        self.command_no += 1
        return d

    def replyTimeout(self, d, command_no):
        """Deletes the reference to the command deferred if no reply was received"""
        del self.defer_list[command_no]

    def connectionLost(self, reason):
        logging.info("Connection to server lost")
        logging.debug(reason)
        try:
            self.connectionLostCB()
        except:
            pass

    def __del__(self):
        logging.debug("GTA_Client_Protocol.__del__")


class RemoteClient:

    def __init__(self, conf):
        self.conf = conf
        self.initialising = False
        self.display = []
        self.display_osf = []

    def connect(self, ip, port, type, n_disp, connectionLost=None):
        self.n_disp = n_disp
        d = self.d = defer.Deferred()
        logging.info("Connecting " + ip + ", port " + str(port))
        c = ClientCreator(reactor, GTA_Client_Protocol)
        c.connectTCP(ip, port).addCallback(self.gotProtocol).addErrback(self.failed_connection)
        self.connectionLost = connectionLost
        self.type = type
        return d

    def gotProtocol(self, p):
        logging.info("Connection established")
        if self.connectionLost:
            p.connectionLostCB = self.connectionLost
        p.client = self
        self.protocol = p

    def failed_connection(self, p):
        logging.critical("Error while connecting")
        self.d.errback(False)

    def process_message(self, m):
        if self.initialising and m['message'] != 'init': return
        if m['message'] == 'hello':
            self.protocol.sendMessage({'message': 'hello', 'client_type': self.type})
            return
        elif m['message'] == 'init':
            self.initialising = True
            logging.debug("Init message received")
            fir = m['fir']
            tlpv = m['tlpv']
            Route.fir = fir
            sector = m['sector']
            flights = m['flights']

            exc_file = self.exc_file = m['exercise_file']
            window_name = exc_file + " (" + str(sector) + ")"
            scenario_key = fir.ap[0] if getattr(fir, 'ap', None) else "default"
            self.conf.set_scenario(scenario_key)
            for i in range(self.n_disp):
                if self.type == PSEUDOPILOT:
                    logging.debug("Creating PpDisplay object")

                    d = PpDisplay(self.conf, window_name, './img/GAMMA.ico', fir, tlpv, sector, deepcopy(flights),
                                  i + 1,
                                  mode='pp')
                elif self.type == ATC:
                    logging.debug("Creating UCS object")
                    d = UCS(self.conf, window_name, './img/GAMMA.ico', fir, tlpv, sector, deepcopy(flights), i + 1,
                            mode='atc', display_remote=self.display_osf)
                self.display.append(d)
                d.sendMessage = self.protocol.sendMessage
                try:
                    d.pos_number = m['pos_number']
                    d.master = self
                except:
                    logging.warning("Unable to set pos_number")
                try:
                    self.display[i].top_level.protocol("WM_DELETE_WINDOW", lambda: reactor.callLater(0, self.exit))
                except AttributeError:
                    continue
            self.initialising = False
            # Informar al GTA del sector real de este cliente
            if self.display:
                real_sector = getattr(self.display[0], 'sector', sector)
                self.protocol.sendMessage({'message': 'set_client_sector', 'sector': real_sector})
            return

        elif m['message'] == 'stop':
            for i in range(len(self.display)):
                self.display[i].exit()
            for i in range(len(self.display_osf)):
                self.display_osf[i].exit()
            self.display = []
            self.display_osf = []

        elif m['message'] == 'save_state':
            for radisp in self.display:
                radisp.save_state()

        elif m['message'] == 'flightstrips':
            for i in range(len(self.display)):
                try:
                    self.display[i].fs_list = fs_list = m['fs_list']
                except AttributeError:
                    continue
        try:
            for i in range(len(self.display)):
                try:
                    self.display[i].process_message(m)
                except AttributeError:
                    continue
        except:
            logging.warning("Processing message %s failed" % m, exc_info=True)

        
        
    def exit(self):
        p = self.protocol
        p.transport.loseConnection()
        p.client = None
        for i in range(self.n_disp):
            self.display[i].exit()
            self.display[i] = None
        for i in range(len(self.display_osf)):
            self.display_osf[i].exit()
        self.d.callback(True)

    def __del__(self):
        logging.debug("RemoteClient.__del__")
