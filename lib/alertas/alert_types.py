# -*- coding: iso8859-15 -*-
"""Tipos y constantes para el sistema de alertas aeroportuarias."""

# Severidades
SEVERITY_NONE = 0
SEVERITY_WNG = 1
SEVERITY_VIO = 2

SEVERITY_MAP = {'VIO': SEVERITY_VIO, 'WNG': SEVERITY_WNG, 'NO': SEVERITY_NONE}

# Tipos de alerta
ALERT_INCW = 'INCW'
ALERT_CMAC = 'CMAC'
ALERT_SAPW = 'SAPW'
ALERT_CATC = 'CATC'

# Orden de prioridad para mostrar en etiqueta (indice menor = mayor prioridad)
PRIORITY_ORDER = [
    (ALERT_CMAC, SEVERITY_VIO),
    (ALERT_INCW, SEVERITY_VIO),
    (ALERT_SAPW, SEVERITY_VIO),
    (ALERT_CATC, SEVERITY_VIO),
    (ALERT_CMAC, SEVERITY_WNG),
    (ALERT_INCW, SEVERITY_WNG),
    (ALERT_SAPW, SEVERITY_WNG),
    (ALERT_CATC, SEVERITY_WNG),
]


class Alert(object):
    """Representa una alerta activa sobre un movil."""

    __slots__ = ['alert_type', 'severity', 'description', 'runway',
                 'related_cs', 'subtype', 'acknowledged']

    def __init__(self, alert_type, severity, description, runway=None,
                 related_cs=None, subtype=None):
        self.alert_type = alert_type      # INCW, CMAC, CATC, SAPW
        self.severity = severity          # SEVERITY_WNG o SEVERITY_VIO
        self.description = description    # Texto descriptivo corto
        self.runway = runway              # Pista involucrada (ej: '06L')
        self.related_cs = related_cs      # Callsign del otro movil (multiples/CATC)
        self.subtype = subtype            # Subtipo especifico
        self.acknowledged = False         # Si el controlador ha reconocido

    def __repr__(self):
        sev = 'VIO' if self.severity == SEVERITY_VIO else 'WNG'
        return '%s %s - %s' % (self.alert_type, sev, self.description)

    def priority_key(self):
        """Retorna tupla para ordenar por prioridad (menor = mas prioritario)."""
        pair = (self.alert_type, self.severity)
        try:
            return PRIORITY_ORDER.index(pair)
        except ValueError:
            return len(PRIORITY_ORDER)


def reciprocal_rwy(des):
    """Pista reciproca: '06L' -> '24R', '02' -> '20', '13' -> '31'."""
    try:
        des = str(des).strip()
        num = ''.join([ch for ch in des if ch.isdigit()])
        suf = des[len(num):].upper()
        rnum = (int(num) + 18) % 36 or 36
        rsuf = {'L': 'R', 'R': 'L'}.get(suf, suf)
        return '%02d%s' % (rnum, rsuf)
    except (ValueError, TypeError):
        return des
