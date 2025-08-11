#!/usr/bin/env python3

from core.rtve import Rtve
from core.log import config_log
from core.j2 import Jnj2
import logging
from datetime import datetime
from typing import Callable, Any
from core.film import Film
from core.filemanager import FM
import re
from datetime import date
from core.collector import get_films


config_log("log/build_site.log")
logger = logging.getLogger(__name__)

NOW = datetime.now()

films = tuple(get_films())
films = tuple(sorted(films, key=lambda f: f.publication, reverse=True))

print("Películas:", len(films))


def sort_ids(fnc: Callable[[Film], Any], reverse=False):
    arr = sorted(films, key=fnc, reverse=reverse)
    return tuple(map(lambda x: f"{x.source}{x.id}", arr))


print("Generando web")
order = dict()
order['publicacion'] = sort_ids(lambda f: f.publication or '', reverse=True)
order['expiracion'] = sort_ids(lambda f: (int(f.expiration is None), f.expiration or ''))
order['duracion'] = sort_ids(lambda f: f.duration or 0)
order['estreno'] = sort_ids(lambda f: f.year or 0, reverse=True)
order['genero'] = sort_ids(lambda f: f.genres)
order['titulo'] = sort_ids(lambda f: f.title)
order['director'] = sort_ids(lambda f: f.director)
order['imdb'] = sort_ids(lambda f: (-(f.imdb.rate if f.imdb and f.imdb.rate else -1), 0 if f.imdb else 1))


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


def _sort_provider(x: str):
    arr = []
    arr.append(-int(x.lower() == "rtve"))
    tp = tuple(x.split(" - "))
    arr.append(len(tp))
    arr.append(tp)
    return tuple(arr)


providers: dict[str, int] = {}
for f in films:
    providers[f.get_provider()] = providers.get(f.get_provider(), 0) + 1
providers = dict(sorted(providers.items(), key=lambda kv: _sort_provider(kv[0])))

j = Jnj2(
    "template/",
    "out/",
    favicon="📽",
)
j.create_script(
    "info.js",
    ORDER=order,
    EXPIRATION=get_expiration(films),
    replace=True
)
j.save(
    "index.html",
    fl=films,
    providers=providers,
    NOW=NOW,
    count=len(films)
)

FM.dump("out/films.json", films)

gens: dict[tuple[str, ...], int] = {}
for f in films:
    gens[f.genres] = gens.get(f.genres, 0) + 1 
for g, c in sorted(gens.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0])):
    logger.info(f"{c} {g}")

print("Fin")
