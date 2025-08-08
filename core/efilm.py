from typing import Any
from core.cache import Cache
from core.util import mapdict
import requests
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError
from json.decoder import JSONDecodeError as DecoderJSONDecodeError
from typing import NamedTuple
import logging
import time
from core.util import tp_split
import re
from core.dblite import DB
from core.filemanager import FM, DictFile


logger = logging.getLogger(__name__)
re_sp = re.compile(r"\s+")


def _clean_name(s, year: int):
    if not isinstance(s, str):
        return s
    s = re_sp.sub(" ", s).strip()
    if len(s) == 0:
        return None
    s = re.sub(r" (Gaumont|\(Kurosawa\)|ANT|\(restaurado Archangel\))$", "", s)
    s = re.sub(r"\s*-\s*Castellano$", "", s)
    if isinstance(year, int) and year > 0:
        s = re.sub(r"\s*\(\s*"+str(year)+r"\s*\)$", "", s)
    return s


def _to_tuple(*args, exclude: tuple = None):
    arr = []
    for a in args:
        if a is not None and a not in arr:
            if exclude and a in exclude:
                continue
            arr.append(a)
    return tuple(arr)


class Video(NamedTuple):
    id: int
    name: str
    slug: str
    typ: str
    cover: str
    cover_horizontal: str
    actors: tuple[str, ...]
    duration: int
    year: int
    genres: tuple[str, ...]
    description: str
    covers: tuple[str, ...]
    director: tuple[str, ...]
    banner_main: str
    banner_trailer: str
    provider_slug: str
    provider: str
    gamma: str
    lang: tuple[str, ...]
    subtitle: tuple[str, ...]
    countries: tuple[str, ...]
    created: str
    expire: str
    imdb: str | None

    @staticmethod
    def mk_url(id: int, slug: str):
        return f'https://cinemadrid.efilm.online/audiovisual-detail/{id}/{slug}'

    def get_url(self):
        return Video.mk_url(self.id, self.slug)


def _clean_js(k: str, obj: list | dict | str):
    if isinstance(obj, str):
        obj = obj.strip()
        if obj in ('', 'No hay es un documental'):
            return None
    return obj


def _g_date(dt: str):
    if dt is None:
        return None
    num = tuple(map(int, re.findall(r"\d+", dt)))
    if len(num) == 3:
        return "{0:04d}-{1:02d}-{2:02d}".format(*num)
    return "{0:04d}-{1:02d}-{2:02d} {3:02d}:{4:02d}".format(*num)


class EFilm:
    def __init__(self, origin: str, min_duration=50):
        self.__cache = DictFile("cache/efilm.dct.txt")
        self.__s = requests.Session()
        self.__min_duration = min_duration
        self.__origin = origin
        self.__s.headers.update({
            'Accept-Language': 'es',
            'localization': '{"codeCountry":"ES","city":"Madrid"}',
            'Origin': self.__origin,
            'Referer': self.__origin,
        })

    def get_json(self, url: str):
        max_tries = 3
        logger.debug(url)
        while True:
            r = self.__s.get(url)
            if max_tries > 0 and r.status_code == 500:
                max_tries = max_tries - 1
                time.sleep(5)
                continue
            try:
                return r.json()
            except (DecoderJSONDecodeError, RequestsJSONDecodeError):
                logger.critical(f"{r.status_code} {url}")
                raise

    def get_list(self, url: str) -> list[dict[str, Any]]:
        prc = url.split("://")[0]
        result = []
        while url:
            url = f"{prc}://" + url.split("://", 1)[1]
            js = self.get_json(url)
            if isinstance(js, list) and len(js) == 1:
                js = js[0]
            result.extend(js['results'])
            url = js['next']
        return result

    def get_audiovisual(self):
        "https://backend-prod.efilm.online/api/v1/videos/audiovisuals/audiovisual_type/?audiovisual_type=Pel%C3%ADculas"

    @Cache("rec/efilm/items.json")
    def get_items(self) -> list[dict]:
        root = f"https://backend-prod.efilm.online/api/v1/products/products/relevant/?duration_gte={self.__min_duration}&page=1&page_size=1000&product_type=audiovisual&skip_chapters=true"
        done: set[int] = set()
        arr = []
        i: dict
        for query in (
            "&languages=1",
            "&subtitles=1"
        ):
            js = self.get_list(
                #"https://backend-prod.efilm.online/api/v1/videos/audiovisuals/audiovisual_type/?audiovisual_type=Pel%C3%ADculas"
                root+query
            )
            for i in mapdict(_clean_js, js, compact=True):
                if i['id'] not in done:
                    done.add(i['id'])
                    errors = self.__get_errors(i)
                    if errors:
                        url = Video.mk_url(i['id'], i.get('slug'))
                        logger.debug(f"[KO] {', '.join(errors)} {url}")
                        continue
                    arr.append(i)
        return arr

    def __get_errors(self, i: dict):
        arr: list[str] = []
        typ = i.get('type')
        provider = (i.get('provider') or {}).get('name')
        genres = tuple(x['name'] for x in (i.get('genres') or []))
        gamma = (i.get('gamma') or {}).get('name_show')
        duration = i.get('duration', 999999)
        director_name = i.get('director_name')
        year = i['year']
        if typ in ('game', ):
            arr.append(f'type={typ}')
        if gamma in ('Azul', ):
            arr.append(f'gamma={gamma}')
        if director_name in (None, ""):
            arr.append("director=None")
        if year > 1960 and duration < self.__min_duration:
            arr.append(f'year={year} duration={duration}')
        #if set(genres).intersection({'Cultura', 'Documental'}):
        #    arr.append(f'genres={genres}')
        if provider in ('Mondo', "Miguel Rodríguez arias"): #'Azteca', "Alex Quiroga"):
            arr.append(f'provider={provider}')
        return tuple(arr)

    @Cache("rec/efilm/ficha/{}.json")
    def get_ficha(self, id: int):
        url = f"https://backend-prod.efilm.online/api/v1/videos/audiovisuals/{id}/"
        js = self.get_json(url)
        js = mapdict(_clean_js, js, compact=True)
        return js

    def get_videos(self):
        arr: set[Video] = set()
        for i in self.get_items():
            ficha = self.get_ficha(i['id'])
            lang = []
            subt = []
            coun = []
            for ln in (ficha.get('languages') or []):
                if not isinstance(ln, dict):
                    raise ValueError(ln)
                lang.append((ln.get('language') or {}).get('code_iso3'))
                lang.append((ln.get('subtitle') or {}).get('code_iso3'))
            for ct in (ficha.get('countries') or []):
                if not isinstance(ct, dict):
                    raise ValueError(ct)
                coun.append(ct.get('code'))
            year = i['year']
            v = Video(
                id=i['id'],
                name=_clean_name(i.get('name'), year),
                slug=i['slug'],
                typ=i['type'],
                cover=i.get('cover'),
                cover_horizontal=i.get('cover_horizontal'),
                actors=tuple(i.get('actors') or []),
                duration=i['duration'],
                year=year,
                genres=tuple(x['name'] for x in (i.get('genres') or [])),
                description=i.get('description'),
                covers=tuple(x['cover'] for x in (i.get('covers') or [])),
                director=tp_split("/", i.get('director_name')),
                banner_main=i.get('banner_main'),
                banner_trailer=i.get('banner_trailer'),
                provider_slug=i.get('provider_slug'),
                provider=(i.get('provider') or {}).get('name'),
                gamma=(i.get('gamma') or {}).get('name_show'),
                lang=_to_tuple(*lang, exclude=('mud','mis')),
                subtitle=_to_tuple(*subt, exclude=('mis', )),
                countries=_to_tuple(*coun),
                created=ficha.get('created'),
                expire=ficha.get('expire'),
                imdb=self.__cache.get(i['id'])
            )
            if (v.lang or v.subtitle) and 'spa' not in v.lang and 'spa' not in v.subtitle:
                logger.debug(f"[KO] NO_SPA {v.lang} {v.subtitle} {v.get_url()}")
                continue
            if v.imdb is None:
                imdb = DB.search_imdb_id(v.name, v.year, v.director, v.duration)
                if imdb:
                    v = v._replace(imdb=imdb)
                    self.__cache.set(v.id, imdb)
            arr.add(v)
        self.__cache.dump()
        logger.info(f"{len(arr)} recuperados de efilm")
        return tuple(sorted(arr, key=lambda v: v.id))


if __name__ == "__main__":
    from core.log import config_log
    from core.filemanager import FM
    config_log("log/efilm.log")
    e = EFilm()
    for v in e.get_videos():
        if v.genres == ('Documental', ):
            print(v.get_url())
    #sys.exit()
    e.get_items()
