from core.imdb import IMDB
from core.util import safe_index
from functools import cache
from core.film import Film
from core.filmaffinity import FilmM
from core.util import re_or
import logging
import re

logger = logging.getLogger(__name__)
re_sp = re.compile(r"\s+")


STANDARDIZATION = {
    # Inglés → Español
    "action": "acción",
    "adventure": "acción",
    "animation": "animación",
    "anime": "animación",
    "biography": "biográfico",
    "biopic": "biográfico",
    "comedy": "comedia",
    "crime": "suspense",
    "documentary": "documental",
    "family": "familiar",
    "fantasy": "fantástico",
    "history": "histórico",
    "horror": "terror",
    "mystery": "suspense",
    "romance": "romántico",
    "sci-fi": "ciencia ficción",
    "science fiction": "ciencia ficción",
    "short": "cortometraje",
    "thriller": "suspense",
    "war": "bélico",
    "western": "oeste",
    "music": "musical",
    "slasher": "terror",
    "sport": "deportes",
    "film-noir": "suspense",
    "spaghetti western": "oeste",

    # Español variantes → forma preferida
    "romántica": "romántico",
    "criminal": "suspense",
    "cine negro": "suspense",
    "cine bélico": "bélico",
    "ficción realista": "drama",
    "social y político": "social",
    "occidental": "oeste",
    "misterio": "suspense",
    "crimen": "suspense",
    "aventuras": "acción",
    "artes marciales": "acción",
    "policíaco": "suspense",
    "policiaco": "suspense",
    "intriga": "suspense",
    "biografía": "biográfico",
    "fantasía": "fantástico",
    "familiar": "infantil",
    "familia": "infantil",
    "cine familiar": "infantil",
    'película de culto': 'película de culto',
    'serie b': 'serie b',
    'teatro': 'teatro',
}

RM_GENRE = (
    'luchando',
    'clásicos',
    'cortometraje',
    'deportes',
    'periodismo',
    'tv movies',
    'familiar',
    'cine español',
    'cine europeo',
    'cine internacional',
    'social',
    'cultura',
    'arte',
    'película de culto',
    'serie b'
)


ORDER = (
    "documental",
    "oeste",
    "comedia",
    "terror",
    "romántico",
    "suspense",
    "musical",
    "bélico",
    "biográfico",
    "histórico",
    "ciencia ficción",
    "fantástico",
    "acción",
    "drama",
    "animación",
    'teatro'
)


def _standarize(*genres: str, url: str = None) -> tuple[str, ...]:
    known = set(RM_GENRE).union(STANDARDIZATION.keys()).union(STANDARDIZATION.values())
    arr: list[str] = []
    for g in genres:
        g = re_sp.sub(" ", g).strip().lower()
        g = STANDARDIZATION.get(g, g)
        if g not in known:
            logger.warning(f"Genero desconocido {g} en {url}")
        if g not in RM_GENRE and g not in arr:
            arr.append(g)
    return tuple(arr)


@cache
def _get_from_omdb(imdb: str):
    obj = IMDB.get_from_omdbapi(imdb, autocomplete=False)
    if not isinstance(obj, dict):
        return tuple()
    gnr = obj.get('Genre') or []
    gnr = _standarize(*gnr, url=f"https://www.imdb.com/es-es/title/{imdb}")
    gnr = set(gnr).intersection(STANDARDIZATION.values())
    return tuple(sorted(gnr))


def _get_from_filmaffinity(id: int):
    if id is None:
        return tuple()
    film = FilmM.get(id)
    if film is None or not film.genres:
        return tuple()
    known = set(RM_GENRE).union(STANDARDIZATION.keys()).union(STANDARDIZATION.values())
    gnr: set[str] = set()
    for g in map(str.lower, film.genres):
        if g in known:
            gnr.add(g)
            continue
        if re_or(g, "^comedia"):
            gnr.add("comedia")
        if re_or(g, "^documental"):
            gnr.add("documental")
        if re_or(g, "animación"):
            gnr.add("animación")
        if re_or(g, "^drama", 'melodrama'):
            gnr.add("drama")
        if re_or(g, "thriller"):
            gnr.add("suspense")
    gnr = _standarize(*gnr, url=f"https://www.filmaffinity.com/es/film{id}.html")
    gnr = set(gnr).intersection(STANDARDIZATION.values())
    return tuple(sorted(gnr))


def fix_genres(f: Film):
    film: set[str] = set(_get_from_filmaffinity(f.filmaffinity.id if f.filmaffinity else None))
    imdb: set[str] = set(_get_from_omdb(f.imdb.id if f.imdb else None))
    main: set[str] = set(_standarize(*f.genres, url=f.url))

    fml_mdb = film.union(imdb)
    if "documental" in fml_mdb or (len(fml_mdb) == 0 and "documental" in main):
        return ("Documental", )
    main.discard("documental")

    hasGen: dict[str, bool] = {}
    for g in ("infantil", "teatro"):  # "acción", "drama"
        hasGen[g] = (g in main) or (g in imdb) or (g in film)
        imdb.discard(g)
        main.discard(g)
        film.discard(g)

    for k, dup in {
        "biográfico": ("histórico", "drama"),
        "suspense": ("drama", "acción"),
        "oeste": ("drama", "acción", "histórico"),
        "acción": ("drama", ),
        "bélico": ("drama", "acción"),
        "histórico": ("drama", "acción"),
        "terror": ("drama", "acción"),
        "ciencia ficción": ("fantástico", )
    }.items():
        for st in (main, imdb, film):
            if k in st:
                st.difference_update(dup)
    if len(film) > 0:
        main = film
    elif len(main) == 0:
        main = imdb
    elif imdb:
        main = set(main).intersection(imdb) or imdb
    if len(main) == 0:
        for k, b in hasGen.items():
            if b is True:
                return (k.capitalize(), )

    def_index = len(ORDER)
    genres = sorted(main, key=lambda g: (safe_index(ORDER, g, def_index), g))
    return tuple(map(str.capitalize, genres))
