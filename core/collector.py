from core.rtve import Rtve, Video as RtveVideo
from core.efilm import EFilm, Video as EFilmVideo
from core.imdb import IMDB, IMDBInfo
from core.film import Film, IMDb
from core.wiki import WIKI
from core.util import re_or, get_first, tp_uniq
from core.country import to_countries
from core.genres import fix_genres
from collections import defaultdict
from core.filemanager import FM
import re
import logging

logger = logging.getLogger(__name__)


def get_imdb(*args: RtveVideo | EFilmVideo):
    ids: set[str] = set()
    for a in args:
        if isinstance(a, RtveVideo) and a.idImdb:
            ids.add(a.idImdb)
        if isinstance(a, EFilmVideo) and a.imdb:
            ids.add(a.imdb)
    return tuple(sorted(ids))


def get_films():
    arr: list[Film] = []
    for source, imdb, v in iter_films():
        if not isinstance(v.imdb, IMDb) or not isinstance(v.imdb.id, str):
            v = v._replace(imdb=None)
        ko = is_ko(source, imdb)
        if ko:
            logger.debug(f"{v.url} descartado por {ko}")
            continue
        imdbId = v.imdb.id if v.imdb else None
        v = complete_film(v)
        v = v._replace(genres=fix_genres(v.genres, imdbId))
        arr.append(v)
    films: list[Film] = []
    imdb_film: dict[str, set[Film]] = defaultdict(set)
    for f in arr:
        if f.imdb is None:
            films.append(f)
        else:
            imdb_film[f.imdb.id].add(f)
    for fls in imdb_film.values():
        if len(fls) == 1:
            films.append(fls.pop())
            continue
        alt = sorted(fls, key=_sort_dup_films)
        f = alt[0]._replace(alt=tuple(alt[1:]))
        films.append(f)
    return tuple(films)


def _sort_dup_films(f: Film):
    arr = []
    arr.append(-int(f.provider == "rtve"))
    arr.append(-int("spa" in f.audio))
    arr.append(-int("spa" in f.subtitle))
    arr.append(-len(f.audio))
    arr.append(-len(f.subtitle))
    arr.append(f.title)
    return tuple(arr)


def complete_film(v: Film):
    if v is None:
        return v
    v = v._replace(
        casting=tp_uniq(v.casting),
        director=tp_uniq(v.director),
        genres=tp_uniq(v.genres)
    )
    if v.imdb is None or v.imdb.id is None:
        logger.debug(f"NO_IMDB {v.url}")
        return v._replace(imdb=None)
    if v.casting and v.director and v.genres:
        return v
    x = IMDB.get_from_omdbapi(v.imdb.id, autocomplete=False)
    if not isinstance(x, dict):
        return v
    if not v.casting:
        v = v._replace(casting=tp_uniq(x.get('Actors')))
    if not v.director:
        v = v._replace(director=tp_uniq(x.get('Director')))
    if not v.genres:
        v = v._replace(genres=tp_uniq(x.get('Genre')))
    return v


def get_filmaffinity_cache(name: str) -> dict[int, int]:
    file = FM.resolve_path(f"cache/filmaffinity/{name}.dct.txt")
    if not file.is_file():
        return {}
    obj = FM.load(file)
    if not isinstance(obj, dict):
        return {}
    r = {}
    for k, v in obj.items():
        nums = set(map(int, re.findall(r"\d+", v)))
        if len(nums) == 1:
            r[k] = int(nums.pop())
    return r


def iter_films():
    rtve = Rtve().get_videos()
    eflim = EFilm(
        origin='https://cinemadrid.efilm.online',
        min_duration=50
    ).get_videos()
    info_imdb = IMDB.get(*get_imdb(*rtve, *eflim))
    rtve_filmaffinity = get_filmaffinity_cache("rtve")
    efilm_filmaffinity = get_filmaffinity_cache("efilm")
    for v in rtve:
        imdb = info_imdb.get(v.idImdb) or IMDBInfo(
            id=v.idImdb,
            rating=v.imdbRate
        )
        img = get_rtve_img(v, imdb)
        if img:
            img.replace("?h=400", "?w=150")
        imdbRate = None
        if (imdb.rating, v.imdbRate) != (None, None):
            imdbRate = max(imdb.rating or 0, v.imdbRate or 0)
        yield v, imdb, Film(
            source="rtve",
            id=v.id,
            url=v.url,
            title=v.title,
            img=img,
            audio=tuple(),
            subtitle=tuple(),
            country=to_countries(imdb.countries),
            description=v.description,
            year=v.productionDate or imdb.year,
            expiration=v.expirationDate,
            publication=v.publicationDate,
            duration=v.duration or imdb.duration,
            imdb=IMDb(
                id=imdb.id,
                rate=imdbRate,
                votes=imdb.votes
            ),
            wiki=WIKI.parse_url(imdb.wiki),
            filmaffinity=rtve_filmaffinity.get(v.id) or imdb.filmaffinity,
            director=v.director,
            casting=v.casting,
            genres=get_rtve_genres(v, imdb),
            provider="rtve"
        )
    for v in eflim:
        imdb = info_imdb.get(v.imdb) or IMDBInfo(
            id=v.imdb,
        )
        yield v, imdb, Film(
            source="eFilm",
            id=v.id,
            url=v.get_url(),
            title=v.name,
            img=get_first(v.cover, *v.covers, v.cover_horizontal, v.banner_main, v.banner_trailer),
            audio=tuple(v.lang or []),
            subtitle=tuple(v.subtitle or []),
            country=to_countries(imdb.countries or v.countries),
            description=v.description,
            year=v.year or imdb.year,
            expiration=v.expire,
            publication=v.created,
            duration=v.duration or imdb.duration,
            imdb=IMDb(
                id=imdb.id,
                rate=imdb.rating,
                votes=imdb.votes
            ),
            wiki=WIKI.parse_url(imdb.wiki),
            filmaffinity=efilm_filmaffinity.get(v.id) or imdb.filmaffinity,
            director=v.director,
            casting=v.actors,
            genres=v.genres,
            provider=v.provider
        )


def is_ko(source, i: IMDBInfo):
    if i is None:
        return None
    if not isinstance(i, IMDBInfo):
        raise ValueError(i)
    banIfTv = False
    if isinstance(source, RtveVideo):
        banIfTv = re_or(source.longTitle, "Sesión de tarde", flags=re.I) and re_or(source.mainTopic, "Cine internacional", flags=re.I)
    if not banIfTv:
        banIfTv = not i.awards and i.countries and "ESP" not in i.countries
    if i.typ in ('tvEpisode', 'tvSeries', 'tvMiniSeries'):
        return f"imdb_type={i.typ}"
    if banIfTv and i.typ in ('tvMovie', 'tvSpecial', 'tvShort', 'tvPilot'):
        return f"imdb_type={i.typ}"


def get_rtve_img(v: RtveVideo, imdb_info: IMDBInfo) -> str:
    if v.img_vertical:
        return v.img_vertical[0]
    if imdb_info and isinstance(imdb_info.id, str):
        info = IMDB.get_from_omdbapi(imdb_info.id)
        if isinstance(info, dict) and isinstance(info.get('Poster'), str):
            poster = info.get("Poster").strip()
            if len(poster):
                return poster
    if v.img_horizontal:
        return v.img_horizontal[0]
    if v.img_others:
        return v.img_others[0]


def get_rtve_genres(v: RtveVideo, imdb_info: IMDBInfo):
    if re_or(v.longTitle, r"^Cine [iI]nfantil"):
        return ("Infantil", )
    if re_or(v.longTitle, r"^Somos [dD]documentales"):
        return ("Documental", )
    if re_or(v.mainTopic, r"[Pp]el[íi]culas [Dd]ocumentales"):
        return ("Documental", )
    if re_or(v.mainTopic, r"[Cc]omedia negra"):
        return ("Comedia", )
    #if re_or(ecort_content, r"[Nn]o [Ff]icci[oó]n[\-\-\s]*[Ii]nformaci[óo]n"):
    #    return ("Documental", )
    if re_or(v.programType, r"[dD]ocumental"):
        return ("Documental", )
    if re_or(v.mainTopic, r"Thriller"):
        return ("Suspense", )
    if re_or(v.ecortContent, r"Thriller"):
        return ("Suspense", )
    genres: set[str] = set()
    for g in v.genres:
        if g in (None, "Cine", "Cultura"):
            continue
        g = {
            "Documentales": "Documental",
            "Biografías": "Biográfico",
            "Música": "Musical",
            "Policíaca y suspense": "Suspense",
            "Acción y aventuras": "Aventuras",
            "Historia": "Histórico"
        }.get(g, g)
        genres.add(g)
    if len(genres):
        return tuple(genres)
    if imdb_info.genres:
        return imdb_info.genres
    if re_or(v.ecortContent, "[dD]rama"):
        return ("Drama", )
    return tuple()
