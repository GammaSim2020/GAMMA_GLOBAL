#!/usr/bin/python
# -*- coding:iso8859-15 -*-
"""Management of user preferences stored in gamma_settings.json (JSON format).

Replaces the old ConfigParser/GAMMA.ini approach.
Migration from GAMMA.ini happens automatically on first run.
"""

import json
import os
import logging

# Rutas siempre junto al programa (carpeta padre de lib/), no en la carpeta desde la
# que se lanza: asi la configuracion no se pierde si se arranca desde otro sitio.
_script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_config_file = os.path.join(_script_dir, "gamma_settings.json")
_ini_file = os.path.join(_script_dir, "GAMMA.ini")

# Carpeta de red de actualizacion por defecto (GAMMA.ini [Global] update_dir / update_dir_alt)
_DEFAULT_UPDATE_DIRS = (r"\\nacl0400\INTERREGIONAL\GAMMA\08 GAMMA PRODUCCION\GAMMA_GLOBAL",
                        r"\\nacl0400.nav.es\INTERREGIONAL\GAMMA\08 GAMMA PRODUCCION\GAMMA_GLOBAL")


def _read_local_ini(option, default=None):
    """Lee una opcion de [Global] del GAMMA.ini local."""
    try:
        import ConfigParser
        cp = ConfigParser.RawConfigParser()
        cp.read(_ini_file)
        return cp.get('Global', option)
    except Exception:
        return default


def update_dirs():
    """Carpetas de red de actualizacion, en orden de preferencia."""
    dirs = []
    for opt, default in (('update_dir', _DEFAULT_UPDATE_DIRS[0]), ('update_dir_alt', _DEFAULT_UPDATE_DIRS[1])):
        d = _read_local_ini(opt, default)
        if d and d.strip() and d.strip() not in dirs:
            dirs.append(d.strip())
    return dirs


def _new_config_path():
    for d in update_dirs():
        p = os.path.join(d, "GAMMA.ini")
        try:
            if os.path.exists(p):
                return p
        except Exception:
            pass
    return os.path.join(update_dirs()[0], "GAMMA.ini") if update_dirs() else ""

# Sections that always live at the top level of the JSON, never nested under a scenario.
_TOP_LEVEL_SECTIONS = {"Global"}


def _load_json():
    """Load JSON config from disk. Returns empty dict on any failure.
    Si el fichero principal falta o esta danado, usa la copia temporal del ultimo guardado."""
    for path in (_config_file, _config_file + ".tmp"):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                logging.warning("Failed to parse %s" % path)
    return {}


def _coerce(value):
    """Convert a string read from INI to its natural Python type."""
    if isinstance(value, bool):
        return value
    s = str(value).strip()
    # GAMMA.ini antiguos (version LEBL) guardaban listas de un elemento: "['2']" -> "2"
    if len(s) >= 4 and s[0] == '[' and s[-1] == ']' and s[1] in "'\"" and s[-2] == s[1] and s.count(s[1]) == 2:
        s = s[2:-2].strip()
    if s.lower() == 'true':
        return True
    if s.lower() == 'false':
        return False
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


class GammaConfNew(object):
    """Reads the remote GAMMA.ini to check for version updates."""

    def __init__(self, path=None):
        self.ver = ""
        try:
            import ConfigParser
            cp = ConfigParser.RawConfigParser()
            cp.read(path or _new_config_path())
            self.ver = cp.get('Global', 'ver')
        except Exception:
            logging.warning("Failed to read remote version.")

    def read_option(self, section, name):
        try:
            return _load_json().get(section, {}).get(name.lower(), "")
        except Exception:
            return ""


class GammaConfig(object):
    """All configuration options for GAMMA.

    Values are kept in memory (self.data). Call save() once at exit to persist
    everything to disk in a single atomic write.
    """

    def __init__(self):
        self.scenario = None  # set via set_scenario() once the FIR is known
        self.data = _load_json()
        if not self.data:
            self._migrate_from_ini()

        g = self.data.get("Global", {})
        mru = g.get("connect_mru", "")
        self.connect_mru = [x for x in str(mru).split(",") if x] if mru else [""]
        self.server_port = int(g.get("server_port", 20123))
        self.cesium_dir = g.get("cesium_dir", "C:\\GAMMA")
        self.common_dir = g.get("common_dir", _script_dir)
        if self.common_dir in (".", "", None):
            self.common_dir = _script_dir
        self.type = g.get("type", "pseudopilot")
        self.n_disp = int(g.get("n_disp", 2))
        #self.printer_sound = bool(g.get("printer_sound", True))
        self.fir_option = g.get("fir_option", "FIR MADRID")
        self.sector_option = g.get("sector_option", "---")
        self.course_option = str(g.get("course_option", "23"))
        self.phase_option = g.get("phase_option", "---")

        # ver is owned exclusively by GAMMA_Start.py / GAMMA.ini
        _v = _read_local_ini('ver', "")
        self.ver = str(_coerce(_v)) if _v else ""

    def _migrate_from_ini(self):
        """Migrate from GAMMA.ini to gamma_settings.json on first run."""
        old_file = _ini_file
        if not os.path.exists(old_file):
            self.data = {}
            return
        try:
            import ConfigParser
            cp = ConfigParser.ConfigParser()
            with open(old_file, "r") as f:
                cp.readfp(f)
            self.data = {}
            for section in cp.sections():
                self.data[section] = {}
                for name, value in cp.items(section):
                    self.data[section][name] = _coerce(value)
            logging.info("Migrated config from GAMMA.ini to gamma_settings.json")
            # Se guarda al salir (save()). Antes se llamaba aqui a save() antes de crear
            # los atributos (connect_mru...) y la migracion fallaba siempre.
        except Exception:
            logging.warning("Migration from GAMMA.ini failed", exc_info=True)
            self.data = {}

    def set_scenario(self, name):
        """Activate the scenario namespace for all subsequent read/write calls."""
        self.scenario = name
        if name not in self.data:
            self.data[name] = {}
        # If this scenario has a remembered role, use it going forward
        scenario_type = self.data[name].get("type")
        if scenario_type:
            self.type = scenario_type
        logging.debug("Config scenario: %s" % name)

    def _section_dict(self, section, create=False):
        """Return the dict where (section) lives, honouring the scenario namespace."""
        if section in _TOP_LEVEL_SECTIONS or self.scenario is None:
            root = self.data
        else:
            root = self.data.setdefault(self.scenario, {})
        if create and section not in root:
            root[section] = {}
        return root

    def read_option(self, section, name, default_value=None, type="string"):
        """Return value for (section, name), converting to the requested type."""
        key = name.lower()
        try:
            v = self._section_dict(section)[section][key]
            if type == "int":
                return int(v)
            elif type == "float":
                return float(v)
            elif type == "bool":
                if isinstance(v, bool):
                    return v
                return str(v).lower() in ("true", "1", "yes")
            else:
                return v if isinstance(v, str) else str(v)
        except Exception:
            logging.debug("Config option not found: [%s] %s" % (section, name))
            return default_value

    def write_option(self, section, name, value):
        """Store value in memory. Call save() to persist to disk."""
        self._section_dict(section, create=True)[section][name.lower()] = value

    def write_options_batch(self, options_dict):
        """Compatibility shim: delegates to write_option for each entry."""
        for section, options in options_dict.items():
            for name, value in options.items():
                self.write_option(section, name, value)

    def save(self):
        """Write the full config to disk in one atomic operation."""
        if "Global" not in self.data:
            self.data["Global"] = {}
        g = self.data["Global"]
        g["connect_mru"] = ",".join(self.connect_mru)
        g["server_port"] = self.server_port
        g["cesium_dir"] = self.cesium_dir
        # La carpeta del programa se guarda como "." para que la configuracion siga
        # valiendo si se mueve la instalacion
        g["common_dir"] = "." if self.common_dir == _script_dir else self.common_dir
        g["type"] = self.type
        g["n_disp"] = self.n_disp
        g["fir_option"] = self.fir_option
        g["sector_option"] = self.sector_option
        g["course_option"] = self.course_option
        g["phase_option"] = self.phase_option
        if self.scenario is not None and self.scenario in self.data:
            self.data[self.scenario]["type"] = self.type
        # Guardado atomico: se escribe en un temporal y luego se sustituye el fichero;
        # si se corta a medias, el fichero anterior (o el temporal completo) sigue valido.
        tmp = _config_file + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(self.data, f, indent=2, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(_config_file):
                os.remove(_config_file)  # en Windows os.rename no sobrescribe
            os.rename(tmp, _config_file)
            logging.debug("Config saved to %s" % _config_file)
        except Exception:
            logging.error("Failed to save %s" % _config_file, exc_info=True)
