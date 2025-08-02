from core.rtve import Rtve, Video as RtveVideo
from core.efilm import EFilm, Video as EFilmVideo
from core.imdb import IMDB, IMDBInfo
from core.film import Film, IMDb
from core.wiki import WIKI
from core.util import re_or, get_first


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
    rtve = Rtve().get_videos()
    eflim = EFilm(
        origin='https://cinemadrid.efilm.online',
        min_duration=0
    ).get_videos()
    info_imdb = IMDB.get(*get_imdb(*rtve, *eflim))
    for v in rtve:
        imdb = info_imdb.get(v.idImdb) or IMDBInfo(
            id=v.idImdb,
            rate=v.imdbRate
        )
        arr.append(Film(
            source="rtve",
            id=v.id,
            url=v.url,
            img=get_rtve_img(v, imdb),
            lang=None,
            country=imdb.countries,
            description=v.description,
            year=v.productionDate or imdb.year,
            expiration=v.expirationDate,
            publication=v.publicationDate,
            duration=v.duration or imdb.duration,
            imdb=IMDb(
                id=imdb.id,
                rate=max(imdb.rating, v.imdbRate or 0),
                votes=imdb.votes
            ),
            wiki=WIKI.parse_url(imdb.wiki),
            filmaffinity=imdb.filmaffinity,
            director=v.director,
            casting=v.casting,
            genres=get_rtve_genres(v, imdb)
        ))
    for v in eflim:
        imdb = info_imdb.get(v.imdb) or IMDBInfo(
            id=v.imdb,
        )
        v.countries
        arr.append(Film(
            source="efilm",
            id=v.id,
            url=v.get_url(),
            img=get_first(v.cover, *v.covers, v.cover_horizontal, v.banner_main, v.banner_trailer, imdb.img),
            lang=v.lang,
            country=imdb.countries or v.countries,
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
            filmaffinity=imdb.filmaffinity,
            director=v.director,
            casting=v.actors,
            genres=get_rtve_genres(v, imdb)
        ))
    return tuple(arr)


def is_ko(i: IMDBInfo):
    if not isinstance(i, IMDBInfo):
        return None
    if i.typ in ('tvEpisode', 'tvSeries', 'tvMiniSeries'):
        return f"imdb_type={i.typ}"
    if not i.awards and i.countries and "ESP" not in i.countries:
        if i.typ in ('tvMovie', 'tvSpecial', 'tvShort', 'tvPilot'):
            return f"imdb_type={i.typ}" 


def get_rtve_img(v: RtveVideo, imdb_info: IMDBInfo) -> str:
    if v.img_vertical:
        return v.img_vertical[0]
    if imdb_info and imdb_info.img:
        return imdb_info.img
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
    if "Biography" in imdb_info.genres:
        return ("Biográfico", )
    if "Thriller" in imdb_info.genres:
        return ("Suspense", )
    if len(set(("Crime", "Mystery")).difference(imdb_info.genres)) == 0:
        return ("Suspense", )
    if "Horror" in imdb_info.genres:
        return ("Terror", )
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
    if re_or(v.ecortContent, "[dD]rama"):
        return ("Drama", )
    return imdb_info.genres
