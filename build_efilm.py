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

films = tuple(EFilm(origin='https://cinemadrid.efilm.online').films)

print("Películas:", len(films))


def sort_ids(fnc: Callable[[Film], Any], reverse=False):
    arr = sorted(films, key=fnc, reverse=reverse)
    return tuple(map(lambda x: f"{x.source}{x.id}", arr))


print("Generando web")
order = dict()
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
