#!/usr/bin/env python3

from core.log import config_log
from core.j2 import Jnj2, simplify
import logging
from datetime import datetime
from typing import Callable, Any
from core.film import Film
from core.filemanager import FM
import re
from datetime import date
from core.collector import get_films
from core.country import Country


config_log("log/build_site.log")
logger = logging.getLogger(__name__)

NOW = datetime.now()

films = tuple(get_films())
films = tuple(sorted(films, key=lambda f: f.publication, reverse=True))

print("Películas:", len(films))


def sort_ids(fnc: Callable[[Film], Any], reverse=False):
    arr = sorted(films, key=fnc, reverse=reverse)
    return tuple(map(lambda x: f"{x.source}{x.id}", arr))


def sort_score(f: Film):
    arr = []
    s = f.get_score()
    arr.append(s.rate if s else None)
    arr.append(s.votes if s else None)
    arr.append(s.reviews if s else None)
    arr.append(int(bool(f.filmaffinity is not None)))
    arr.append(int(bool(f.imdb is not None)))
    return tuple(map(lambda x: 0 if x is None else -x, arr))


print("Generando web")
order: dict[str, tuple[str, ...]] = dict()
order['publicacion'] = sort_ids(lambda f: f.publication or '', reverse=True)
order['expiracion'] = sort_ids(lambda f: (int(f.expiration is None), f.expiration or ''))
order['duracion'] = sort_ids(lambda f: f.duration or 0)
order['estreno'] = sort_ids(lambda f: f.year or 0, reverse=True)
#order['genero'] = sort_ids(lambda f: f.genres)
order['titulo'] = sort_ids(lambda f: f.title)
order['director'] = sort_ids(lambda f: f.director)
order['puntuacion'] = sort_ids(sort_score)
order['imdb'] = sort_ids(lambda f: (
        -(f.imdb.rate if f.imdb and f.imdb.rate else -1),
        -(f.imdb.votes if f.imdb and f.imdb.votes else -1),
        0 if f.imdb else 1
    )
)
order['filmaffinity'] = sort_ids(lambda f: (
        -(f.filmaffinity.rate if f.filmaffinity and f.filmaffinity.rate else -1),
        -(f.filmaffinity.votes if f.filmaffinity and f.filmaffinity.votes else -1),
        0 if f.filmaffinity else 1
    )
)


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
genres: dict[str, int] = {}
for f in films:
    for g in f.genres:
        genres[g] = genres.get(g, 0) + 1
genres = dict(sorted(genres.items()))
countries: dict[Country, int] = {}
for f in films:
    for c in f.country:
        countries[c] = countries.get(c, 0) + 1
countries = dict(sorted(countries.items(), key=lambda kv: kv[0].spa))

genres_unicode = {
    "accion": "💥",        # Acción
    "animacion": "🎨",     # Animación
    "biografico": "👤",    # Biográfico
    "belico": "🎖️",       # Bélico
    "ciencia-ficcion": "👽",  # Ciencia ficción
    "comedia": "😂",       # Comedia
    "documental": "📚",    # Documental
    "drama": "🎭",         # Drama
    "fantastico": "🪄",    # Fantástico
    "historico": "🏛️",     # Histórico
    "infantil": "🧸",      # Infantil
    "musical": "🎵",       # Musical
    "oeste": "🤠",         # Oeste
    "romantico": "❤️",     # Romántico
    "suspense": "🕵️",     # Suspense
    "terror": "👻",         # Terror
    "serie-b": "💾",
    "culto": "💎"
}
for g in map(simplify, genres.keys()):
    if g not in genres_unicode:
        genres_unicode[g] = "🎬"

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
    genres=genres,
    countries=countries,
    NOW=NOW,
    count=len(films),
    genres_unicode=genres_unicode
)

FM.dump("out/films.json", films)


print("Fin")
