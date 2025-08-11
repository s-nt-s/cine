from core.imdb import IMDB
from functools import cache
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
    "policíaco": "suspense",
    "policiaco": "suspense",
    "intriga": "suspense",
    "biografía": "biográfico",
    "fantasía": "fantástico",
    "familiar": "infantil",
    "familia": "infantil"
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
    'cultura'
)


ORDER = {k: i for i, k in enumerate((
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
))}


def _standarize(*genres: str):
    known = set(RM_GENRE).union(STANDARDIZATION.keys()).union(STANDARDIZATION.values())
    arr: list[str] = []
    for g in genres:
        g = re_sp.sub(" ", g).strip().lower()
        g = STANDARDIZATION.get(g, g)
        if g not in known:
            logger.warning(f"Genero desconocido {g}")
        if g not in RM_GENRE and g not in arr:
            arr.append(g)
    return tuple(arr)


@cache
def _get_from_omdb(imdb: str):
    obj = IMDB.get_from_omdbapi(imdb, autocomplete=False) or {}
    gnr = obj.get('Genre') or []
    gnr = _standarize(*gnr)
    gnr = set(_standarize(*gnr)).intersection(STANDARDIZATION.values())
    return tuple(sorted(gnr))


def fix_genres(genres: tuple[str, ...], imdb: str = None):
    gnr: set[str] = set(_get_from_omdb(imdb))
    nrm: set[str] = set(_standarize(*genres))

    if ("documental" in nrm and len(gnr) == 0) or "documental" in gnr:
        return ("Documental", )
    nrm.discard("documental")

    hasGen: dict[str, bool] = {}
    for g in ("acción", "drama", "infantil"):
        hasGen[g] = (g in nrm) or (g in gnr)
        gnr.discard(g)
        nrm.discard(g)

    for k, dup in {
        "biográfico": ("histórico", )
    }.items():
        if k in nrm:
            nrm = nrm.difference(dup)
        if k in gnr:
            gnr = gnr.difference(dup)

    if len(nrm) == 0:
        nrm = gnr
    elif gnr:
        nrm = set(nrm).intersection(gnr) or gnr
    if len(nrm) == 0:
        for k, b in hasGen.items():
            if b is True:
                return (k.capitalize(), )

    genres = sorted(nrm, key=lambda g: (ORDER.get(g, len(ORDER)), g))
    return tuple(map(str.capitalize, genres))
