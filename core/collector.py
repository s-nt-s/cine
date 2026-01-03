from core.rtve import Rtve, Video as RtveVideo
from core.efilm import EFilm, Video as EFilmVideo
from core.imdb import IMDB, IMDBInfo
from core.film import Film, IMDb, FilmAffinity
from core.wiki import WIKI
from core.util import re_or, get_first, tp_uniq
from core.country import CF
from core.genres import fix_genres
from collections import defaultdict
from core.filemanager import FM, DictFile
import re
import logging
from datetime import date
from core.filmaffinity import FilmM
from core.git import G
from core.req import R

logger = logging.getLogger(__name__)
TODAY = date.today()


def _sort_dup_films(f: Film):
    arr = []
    arr.append(-int(f.provider == "rtve"))
    arr.append(-int("spa" in f.audio))
    arr.append(-int("spa" in f.subtitle))
    arr.append(-len(f.audio))
    arr.append(-len(f.subtitle))
    arr.append(f.title)
    return tuple(arr)


class Collector:
    def __init__(self):
        self.__rtve_filmaffinity = self.get_filmaffinity_cache("rtve")
        self.__efilm_filmaffinity = self.get_filmaffinity_cache("efilm")
        self.__publication = self.__get_dict_file("publication.json")

    def __get_dict_file(self, path: str):
        obj = R.safe_get_dict(f"{G.page}/{path}")
        file = DictFile(f"out/{path}")
        for k, v in obj.items():
            file.set(k, v)
        return file

    def __get_imdb(self, *args: RtveVideo | EFilmVideo):
        ids: set[str] = set()
        for a in args:
            if isinstance(a, RtveVideo) and a.idImdb:
                ids.add(a.idImdb)
            if isinstance(a, EFilmVideo) and a.imdb:
                ids.add(a.imdb)
        return tuple(sorted(ids))

    def get_films(self):
        ban: tuple[str, ...] = FM.load("cache/ban.qw.txt")
        arr: list[Film] = []
        for source, imdb, v in self.iter_films():
            if imdb and imdb.id in ban:
                logger.debug(f"{v.url} descartado por ban")
                continue
            if f"{v.source}{v.id}".lower() in ban:
                logger.debug(f"{v.url} descartado por ban")
                continue
            if not isinstance(v.imdb, IMDb) or not isinstance(v.imdb.id, str):
                v = v._replace(imdb=None)
            ko = self.__is_ko(source, imdb, v)
            if ko:
                logger.debug(f"{v.url} descartado por {ko}")
                continue
            v = self.__complete_film(v)
            v = v._replace(genres=fix_genres(v))
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
        films = tuple(films)
        self.__publication.dump()
        return films

    def __complete_film(self, v: Film):
        if v is None:
            return v
        k_film = f"{v.source}_{v.id}"
        old_publication = self.__publication.get(k_film)
        if old_publication is not None and (v.publication is None or old_publication<v.publication):
            v = v._replace(publication=old_publication)
        self.__publication.set(k_film, v.publication)

        if len(v.country) != 1 and v.filmaffinity and v.filmaffinity.id:
            flm = FilmM.get(v.filmaffinity.id)
            ct = CF.to_country(flm.country if flm else None)
            if ct:
                v = v._replace(country=(ct, ))
        v = v._replace(
            casting=tp_uniq(v.casting),
            director=tp_uniq(v.director),
            genres=tp_uniq(v.genres)
        )
        if v.expiration and date(*map(int, re.findall(r"\d+", v.expiration)[:3])) < TODAY:
            logger.debug(f"{v.expiration} eliminada por incongruente, {v.url}")
            v = v._replace(expiration=None)
        if v.imdb is None or v.imdb.id is None:
            logger.debug(f"NO_IMDB {v.url}")
            v = v._replace(imdb=None)
        if v.imdb is not None and v.filmaffinity is None:
            logger.debug(f"NO_FILMAFFINITY https://www.imdb.com/es-es/title/{v.imdb.id}")
        if v.imdb is None:
            return v
        if v.id not in {
            "rtve": Rtve.CONSOLIDATED,
            "eFilm": EFilm.CONSOLIDATED
        }.get(v.source, {}):
            return v
        imdb_obj = IMDB.get_from_omdbapi(v.imdb.id, autocomplete=False)
        film_obj = FilmM.get(v.filmaffinity.id if v.filmaffinity else None)
        if not isinstance(imdb_obj, dict) and not isinstance(film_obj, FilmAffinity):
            return v
        if imdb_obj is None:
            imdb_obj = {}
        if not v.casting:
            v = v._replace(casting=tp_uniq(imdb_obj.get('Actors')))
        if not v.director:
            v = v._replace(director=tp_uniq(imdb_obj.get('Director')))
        if not v.genres:
            v = v._replace(genres=tp_uniq(imdb_obj.get('Genre')))
        if film_obj:
            v = v._replace(year=film_obj.year or v.year)
            v = v._replace(title=film_obj.title or v.title)
            if v.source == "eFilm" and film_obj.poster:
                v = v._replace(fallback=v.img)
                v = v._replace(img=film_obj.poster)
        elif imdb_obj:
            v = v._replace(year=imdb_obj.get("Year") or v.year)
        return v

    def get_filmaffinity_cache(self, name: str) -> dict[int, int]:
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

    def __get_filmaffinity(self, id: int):
        if not isinstance(id, int):
            return None
        fm = FilmM.get(id)
        if fm is None:
            return FilmAffinity(id=id)
        return FilmAffinity(
            id=id,
            reviews=fm.reviews,
            votes=fm.votes,
            rate=fm.rate
        )._fix()

    def iter_films(self):
        rtve = Rtve().get_videos()
        eflim = EFilm(
            origin='https://cinemadrid.efilm.online',
            min_duration=50,
            exclude_topis=(
                "chile en teatrix",
                "méxico en teatrix",
                "perú en teatrix",
                "carnaval en teatrix",
                "el mejor teatro en tiempo de tango",
                "originales teatrix",
                "cómicos y stand-up",
                "santiago doria - filipinas",
                "unipersonales",
                "entre el telón y el divan",
                'memoria artística',
                'documental sobre religión',
                'documental marino',
                'Teatro para disfrutar con los peques'
            )
        ).get_videos()
        info_imdb = IMDB.get(*self.__get_imdb(*rtve, *eflim))
        for v in rtve:
            imdb = info_imdb.get(v.idImdb) or IMDBInfo(
                id=v.idImdb,
                rating=v.imdbRate
            )
            img = self.__get_rtve_img(v, imdb)
            if img:
                img = img.replace("?h=400", "?w=150")
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
                country=CF.to_country_uniq_tp(imdb.countries),
                description=v.description,
                year=v.productionDate or imdb.year,
                expiration=v.expirationDate,
                publication=v.publicationDate,
                duration=v.duration or imdb.duration,
                imdb=IMDb(
                    id=imdb.id,
                    rate=imdbRate,
                    votes=imdb.votes
                )._fix(),
                wiki=WIKI.parse_url(imdb.wiki),
                filmaffinity=self.__get_filmaffinity(
                    self.__rtve_filmaffinity.get(v.id) or imdb.filmaffinity
                ),
                director=v.director,
                casting=v.casting,
                genres=self.__get_rtve_genres(v, imdb),
                provider="rtve"
            )
        for v in eflim:
            imdb = info_imdb.get(v.imdb) or IMDBInfo(
                id=v.imdb,
            )
            f = Film(
                source="eFilm",
                id=v.id,
                url=v.get_url(),
                title=v.name,
                img=get_first(v.cover, *v.covers, v.cover_horizontal, v.banner_main, v.banner_trailer),
                audio=tuple(v.lang or []),
                subtitle=tuple(v.subtitle or []),
                country=CF.to_country_uniq_tp(imdb.countries or v.countries),
                description=v.description,
                year=v.year or imdb.year,
                expiration=v.expire,
                publication=v.created,
                duration=v.duration or imdb.duration,
                imdb=IMDb(
                    id=imdb.id,
                    rate=imdb.rating,
                    votes=imdb.votes
                )._fix(),
                wiki=WIKI.parse_url(imdb.wiki),
                filmaffinity=self.__get_filmaffinity(
                    self.__efilm_filmaffinity.get(v.id) or imdb.filmaffinity
                ),
                director=v.director,
                casting=v.actors,
                genres=v.genres,
                provider=v.provider
            )
            yield v, imdb, f

    def __is_ko(self, source, i: IMDBInfo, v: Film):
        if i is not None:
            if not isinstance(i, IMDBInfo):
                raise ValueError(i)
            banIfTv = False
            if isinstance(source, RtveVideo):
                banIfTv = re_or(source.longTitle, "Sesión de tarde", flags=re.I) and re_or(source.mainTopic, "Cine internacional", flags=re.I)
            if not banIfTv:
                banIfTv = not i.awards and i.countries and "ESP" not in i.countries
            if i.typ in ('tvEpisode', 'tvSeries', 'tvMiniSeries'):
                return f"imdb_type={i.typ}"
            rate = v.get_rate() or 0
            if banIfTv and rate < 5 and i.typ in ('tvMovie', 'tvSpecial', 'tvShort', 'tvPilot'):
                return f"imdb_type={i.typ}"
        if self.__is_too_bad(v):
            return f"rate={v.get_rate()}"

    def __is_too_bad(self, v: Film):
        rate = v.get_rate() or 999
        min_rate = 4
        if v.source == "eFilm":
            min_rate = min_rate + 0.5
        gnrs = set({
            "Documental",
            "Oeste",
            "Biográfico",
            "Romántico",
            "Teatro",
            "Terror",
            "Animación"
        })
        cnts = set({
            "ARG",
            "DEU",
            "FRG",  # Alemana del oeste
            "AUS",
            "BOL",
            "BRA",
            "CAN",
            "CHL",
            "COL",
            "ESP",
            "USA",
            "GTM",
            "MEX",
            "GBR",
            "RUS",
            "URY",
            "VEN"
        })
        if rate >= (min_rate + 1):
            return False
        fm = self.__get_filmaffinity_data(v)
        if fm:
            if set(fm.genres).intersection(("Serie B", "Película de culto")):
                return False
            if gnrs.intersection(fm.genres) or fm.country in cnts:
                min_rate = min_rate + 1
        elif gnrs.intersection(v.genres) and cnts.intersection(v.country):
            min_rate = min_rate + 1
        return rate < min_rate

    def __get_filmaffinity_data(self, v: Film):
        if v is None or v.filmaffinity is None or v.filmaffinity.id is None:
            return tuple()
        fm = FilmM.get(v.filmaffinity.id)
        return fm

    def __get_rtve_img(self, v: RtveVideo, imdb_info: IMDBInfo) -> str:
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

    def __get_rtve_genres(self, v: RtveVideo, imdb_info: IMDBInfo):
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
