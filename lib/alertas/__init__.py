# -*- coding: iso8859-15 -*-
"""Paquete de alertas aeroportuarias (INCW, CMAC, CATC)."""

from alertas.alert_types import Alert, SEVERITY_NONE, SEVERITY_WNG, SEVERITY_VIO
from alertas.alert_types import ALERT_INCW, ALERT_CMAC, ALERT_CATC, PRIORITY_ORDER
from alertas.incw_engine import INCWEngine
from alertas.cmac_engine import CMACEngine
from alertas.catc_engine import CATCEngine

import logging


class AlertManager(object):
    """Orquesta los motores de alertas y gestiona el ciclo de evaluacion."""

    def __init__(self, fir):
        self.fir = fir
        # Parametro de escenario 'alertas' (por defecto 1): con 0 se desactivan aunque el
        # Excel traiga las hojas INCW/CMAC/CATC.
        enabled = True
        try:
            enabled = bool(fir.param('alertas', True))
        except AttributeError:
            pass
        if not enabled or not getattr(fir, 'incw_zones', {}):
            self.incw = self.cmac = self.catc = None
            self.available = False
            if not enabled:
                logging.info("AlertManager: desactivado por el parametro de escenario 'alertas'")
            else:
                logging.info("AlertManager: sin zonas INCW, alertas desactivadas")
            return
        self.incw = INCWEngine(fir)
        self.cmac = CMACEngine(fir) if getattr(fir, 'cmac_params', {}) else None
        self.catc = CATCEngine(fir) if getattr(fir, 'catc_subtypes', []) else None
        self.available = True
        logging.info("AlertManager: activo con %d zonas INCW", len(fir.incw_zones))
        if self.cmac is not None:
            logging.info("AlertManager: CMAC activo con %d subtipos", len(fir.cmac_subtypes))
        if self.catc is not None:
            logging.info("AlertManager: CATC activo con %d subtipos", len(fir.catc_subtypes))

    def evaluate(self, flights, pistas_config):
        """Evalua alertas para todos los vuelos. Llamado cada segundo desde GTA.timer().

        Args:
            flights: lista de Aircraft activos
            pistas_config: lista de dicts con config de pistas del controlador
        """
        if not self.available:
            return

        # Evaluar INCW primero
        self.incw.evaluate(flights, pistas_config)

        # Evaluar CMAC segundo (re-sort incluye alertas de ambos motores)
        if self.cmac is not None:
            self.cmac.evaluate(flights, pistas_config)

        # Evaluar CATC tercero (re-sort incluye alertas de los tres motores)
        if self.catc is not None:
            self.catc.evaluate(flights, pistas_config)
