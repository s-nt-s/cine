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
from genson import SchemaBuilder
import re

logger = logging.getLogger(__name__)


def myex(e, msg):
    largs = list(e.args)
    if len(largs) == 1 and isinstance(largs, str):
        largs[0] = largs[0]+' '+msg
    else:
        largs.append(msg)
    e.args = tuple(largs)
    return e


def _complete_schema(schema: dict, obj: list, threshold=60):
    if not isinstance(obj, list):
        return schema
    obj = [o for o in obj if o is not None]
    if len(obj) == 0:
        return schema
    schema_type = schema['type']
    typ = None
    hasNull = None
    if isinstance(schema_type, str):
        typ = schema_type
        hasNull = False
    elif isinstance(schema_type, list):
        st = tuple(sorted((s for s in schema_type if s not in ("null", None))))
        hasNull = len(st) < len(schema_type)
        if len(st) == 1:
            typ = st[0]
    if typ == 'object':
        for k, v in list(schema['properties'].items()):
            schema['properties'][k] = _complete_schema(v, [o.get(k) for o in obj], threshold=threshold)
        return schema
    if typ == 'array':
        lns: set[int] = set()
        arr = []
        for i in obj:
            lns.add(len(i))
            arr = arr + i
        schema['items'] = _complete_schema(schema['items'], arr, threshold=threshold)
        schema['minItems'] = min(lns)
        schema['maxItems'] = max(lns)
        return schema
    if typ not in ('string', 'integer'):
        return schema
    vals = sorted(set(obj))
    if len(vals) <= threshold:
        if hasNull:
            vals.insert(0, None)
        schema['enum'] = vals
        return schema
    if typ == 'integer':
        schema['minimum'] = vals[0]
        schema['maximum'] = vals[-1]
    if typ == 'string':
        lvls = sorted(map(len, vals))
        schema['minLength'] = lvls[0]
        schema['maxLength'] = lvls[-1]
        pattern = _guess_pattern(vals)
        if pattern:
            schema['pattern'] = pattern
    return schema


def _guess_pattern(vals: list[str]):
    prefix = ""
    for tp in zip(*vals):
        if len(set(tp)) > 1:
            break
        prefix = prefix + tp[0]
    if prefix:
        pt = _guess_pattern([v[len(prefix):] for v in vals if v[len(prefix):]])
        if pt:
            return r"^" + re.escape(prefix) + pt[1:-1] + r"$"
        return r"^" + re.escape(prefix) + r".+$"
    for r in (
        r'\d+',
        r"tt\d+",
        r'\d{4}-\d{2}-\d{2}',
        r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}',
        r"\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}",
        r'[a-z]',
        r'[A-Z]',
        r'[a-z0-9]',
        r'[A-Z0-9]',
        r'[a-zA-Z]',
        r'[a-zA-Z0-9]',
        r"https?://\S+"
    ):
        r = r"^" + r + r"$"
        if all(re.match(r, x) for x in vals):
            return r
    letters: set[str] = set()
    for i in vals:
        letters = letters.union(list(i))
    if len(letters) < 20:
        re_letters = "".join(map(re.escape, sorted(letters)))
        return '^['+re_letters+']+$'
    for r in (
        r'\S+',
    ):
        r = r"^" + r + r"$"
        if all(re.match(r, x) for x in vals):
            return r


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

    def dump_json(self, file, obj, *args, indent=2, mk_schema=False, **kwargs):
        with open(file, "w") as f:
            json.dump(self.__parse(obj), f, *args, indent=indent, **kwargs)
        if mk_schema:
            schema_file = str(file).rsplit(".", 1)[0]+'.schema.json'
            self.dump_json_schema(schema_file, file, indent=indent)

    def mk_json_schema(self, file: str, out: str = None):
        obj = self.load(file)
        schema_file = out or str(file).rsplit(".", 1)[0]+'.schema.json'
        self.dump_json_schema(schema_file, obj)

    def dump_json_schema(self, file, obj, indent=2):
        obj = self.get_schema(obj)
        self.dump(file, obj, indent=indent)

    def get_schema(self, obj):
        builder = SchemaBuilder()
        if not isinstance(obj, (list, tuple)):
            obj = [obj]
        for o in obj:
            builder.add_object(o)
        schema = builder.to_schema()
        _complete_schema(schema, obj)
        return schema

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
