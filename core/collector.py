from core.rtve import Rtve, Video as RtveVideo
from core.efilm import EFilm, Video as EFilmVideo
from core.imdb import IMDB, IMDBInfo
from core.film import Film


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
    eflim = EFilm().get_videos()
    info_imdb = IMDB.get(*get_imdb(*rtve, *eflim))
    for r in rtve:
        imdb = info_imdb.get(r.idImdb)
        arr.append(Film(
            source="rtve",
            id=r.id,
            url=r.url,
            img=get_rtve_img(r, imdb)
        ))


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