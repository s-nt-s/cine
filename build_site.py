#!/usr/bin/env python3

from core.rtve import Rtve
from core.log import config_log
from core.j2 import Jnj2
import logging
from datetime import datetime
from typing import Callable, Any
from core.film import Film
from core.filemanager import FM


config_log("log/build_site.log")
logger = logging.getLogger(__name__)

NOW = datetime.now()

films = tuple(Rtve().films)
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

j = Jnj2(
    "template/",
    "out/",
    favicon="📽",
)
j.create_script(
    "info.js",
    ORDER=order,
    replace=True
)
j.save(
    "index.html",
    fl=films,
    NOW=NOW,
    count=len(films)
)

FM.dump("out/films.json", films)

print("Fin")
