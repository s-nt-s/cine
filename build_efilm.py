#!/usr/bin/env python3

from core.efilm import EFilm
from core.log import config_log
from core.j2 import Jnj2
import logging
from datetime import datetime
from typing import Callable, Any
from core.film import Film
from core.filemanager import FM
import re
from datetime import date


config_log("log/build_efilm.log")
logger = logging.getLogger(__name__)

NOW = datetime.now()

films = tuple(EFilm(
    origin='https://cinemadrid.efilm.online',
    min_duration=0
).films)

print("Películas:", len(films))


def sort_ids(fnc: Callable[[Film], Any], reverse=False):
    arr = sorted(films, key=fnc, reverse=reverse)
    return tuple(map(lambda x: f"{x.source}{x.id}", arr))


def mk_date(s: str):
    num = tuple(map(int, re.findall(r"\d+", s)))
    d = date(num[0], num[1], num[2])
    return d


def get_expiration(fmls: tuple[Film]):
    fmls = [f for f in fmls if f.expiration]
    if len(fmls) == 0:
        return None
    exp: dict[str, Any] = dict()
    min_exp = mk_date(min(f.expiration for f in fmls))
    exp['__min__'] = min_exp
    for f in fmls:
        delta = (mk_date(f.expiration) - min_exp)
        exp[f"{f.source}{f.id}"] = delta.days
    return exp


print("Generando web")
order = dict()
order['publicacion'] = sort_ids(lambda f: f.publication or '', reverse=True)
order['expiracion'] = sort_ids(lambda f: (int(f.expiration is None), f.expiration or ''))
order['duracion'] = sort_ids(lambda f: f.duration or 0)
order['estreno'] = sort_ids(lambda f: f.year or 0, reverse=True)
order['genero'] = sort_ids(lambda f: f.genres)
order['titulo'] = sort_ids(lambda f: f.title)
order['director'] = sort_ids(lambda f: f.director)


j = Jnj2(
    "template/",
    "out/efilm/",
    favicon="📽",
)
j.create_script(
    "info.js",
    ORDER=order,
    EXPIRATION=get_expiration(films),
    replace=True
)
j.save(
    "efilm.html",
    "index.html",
    fl=films,
    NOW=NOW,
    count=len(films)
)

FM.dump("out/efilm/films.json", films)

print("Fin")
