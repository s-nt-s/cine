import json
import logging
from os import makedirs
from os.path import dirname, realpath
from pathlib import Path
from functools import cache

import requests
from bs4 import BeautifulSoup, Tag
from json.decoder import JSONDecodeError
from dataclasses import is_dataclass, asdict

logger = logging.getLogger(__name__)


def myex(e, msg):
    largs = list(e.args)
    if len(largs) == 1 and isinstance(largs, str):
        largs[0] = largs[0]+' '+msg
    else:
        largs.append(msg)
    e.args = tuple(largs)
    return e


class FileManager:
    """
    Da funcionalidad de lectura (load) y escritura (dump) de ficheros
    """

    def __init__(self, root=None):
        """
        Parameters
        ----------
        root: str | Path
            por defecto es la raiz del proyecto, es decir, el directorio ../.. al de este fichero
            se usa para interpretar que las rutas relativas son relativas a este directorio root
        """
        if root is None:
            root = Path(dirname(realpath(__file__))).parent
        elif isinstance(root, str):
            root = Path(root)

        self.root = root

    def resolve_path(self, file) -> Path:
        """
        Si es una ruta absoluta se devuelve tal cual
        Si es una ruta relativa se devuelve bajo la ruta root
        Si empieza por ~ se expande

        Parameters
        ----------
        file: str | Path
            Ruta a resolver
        """
        if isinstance(file, str):
            file = Path(file)

        if str(file).startswith("~"):
            file = file.expanduser()

        if file.is_absolute():
            return file

        root_file = self.root.joinpath(file)

        return root_file

    def normalize_ext(self, ext) -> str:
        """
        Normaliza extensiones para identificar el tipo de fichero en base a la extension
        """
        ext = ext.lstrip(".")
        ext = ext.lower()
        return {
            "xlsx": "xls",
            "js": "json",
            "sql": "txt",
            "gql": "txt",
            "htm": "html",
            "ics": "txt"
        }.get(ext, ext)

    def load(self, file, *args, **kwargs):
        """
        Lee un fichero en funcion de su extension
        Para que haya soporte para esa extension ha de exisitir una funcion load_extension
        """
        file = self.resolve_path(file)

        ext = self.normalize_ext(file.suffix)

        load_fl = getattr(self, "load_"+ext, None)
        if load_fl is None:
            raise Exception(
                "No existe metodo para leer ficheros {} [{}]".format(ext, file.name))

        return load_fl(file, *args, **kwargs)

    @cache
    def cached_load(self, file, *args, **kwargs):
        return self.load(file, *args, **kwargs)

    def dump(self, file, obj, *args, **kwargs):
        """
        Guarda un fichero en funcion de su extension
        Para que haya soporte para esa extension ha de exisitir una funcion dump_extension
        """
        file = self.resolve_path(file)
        makedirs(file.parent, exist_ok=True)

        ext = self.normalize_ext(file.suffix)

        dump_fl = getattr(self, "dump_"+ext, None)
        if dump_fl is None:
            raise Exception(
                "No existe metodo para guardar ficheros {} [{}]".format(ext, file.name))

        dump_fl(file, obj, *args, **kwargs)

    def dwn(self, file, url, verify=True, overwrite=False, headers=None):
        """
        Descarga un fichero

        Parameters
        ----------
        verify: true
            Indica si se debe verificar el certificado de la web
        overwrite: False
            Indica si se debe sobreescribir en caso de ya existir
        """
        file = self.resolve_path(file)
        ext = self.normalize_ext(file.suffix)

        if overwrite or not file.exists():
            r = requests.get(url, verify=verify, headers=headers)
            makedirs(file.parent, exist_ok=True)
            with open(file, "wb") as f:
                f.write(r.content)

    def load_json(self, file, *args, **kwargs):
        with open(file, "r") as f:
            try:
                return json.load(f, *args, **kwargs)
            except JSONDecodeError as e:
                raise myex(e, str(file))

    def dump_json(self, file, obj, *args, indent=2, **kwargs):
        with open(file, "w") as f:
            json.dump(self.__parse(obj), f, *args, indent=indent, **kwargs)

    def load_html(self, file, *args, parser="lxml", **kwargs):
        with open(file, "r") as f:
            return BeautifulSoup(f.read(), parser)

    def dump_html(self, file, obj, *args, **kwargs):
        if isinstance(obj, (BeautifulSoup, Tag)):
            obj = str(obj)
        with open(file, "w") as f:
            f.write(obj)

    def load_txt(self, file, *args, **kwargs):
        with open(file, "r") as f:
            txt = f.read()
            if args or kwargs:
                txt = txt.format(*args, **kwargs)
            return txt

    def dump_txt(self, file, txt, *args, **kwargs):
        if args or kwargs:
            txt = txt.format(*args, **kwargs)
        with open(file, "w") as f:
            f.write(txt)

    def __parse(self, obj):
        if getattr(obj, "_asdict", None) is not None:
            obj = obj._asdict()
        if is_dataclass(obj):
            obj = asdict(obj)
        if isinstance(obj, (list, tuple, set)):
            return tuple(map(self.__parse, obj))
        if isinstance(obj, dict):
            obj = {k: self.__parse(v) for k, v in obj.items()}
        return obj

    def rm(self, file: str | Path):
        file = self.resolve_path(file)
        if not file.exists():
            return
        if file.is_file():
            file.unlink()
        elif file.is_dir():
            file.rmdir()


# Mejoras dinamicas en la documentacion
for mth in dir(FileManager):
    slp = mth.split("_", 1)
    if len(slp) == 2 and slp[0] in ("load", "dump"):
        key, ext = slp
        mth = getattr(FileManager, mth)
        if mth.__doc__ is None:
            if key == "load":
                mth.__doc__ = "Lee "
            else:
                mth.__doc__ = "Guarda "
            mth.__doc__ = mth.__doc__ + "un fichero de tipo "+ext

FM = FileManager()
