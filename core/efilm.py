from typing import Any
from core.cache import Cache
from core.util import mapdict
import requests
from requests.exceptions import JSONDecodeError
from typing import NamedTuple
import logging
import time
from core.util import tp_split
from functools import cached_property
from core.film import Film


logger = logging.getLogger(__name__)


def _get_first(*args):
    for a in args:
        if a is not None:
            return a


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
    director_name: str
    banner_main: str
    banner_trailer: str
    provider_slug: str
    provider: str
    gamma: str

    @staticmethod
    def mk_url(id: int, slug: str):
        return f'https://cinemadrid.efilm.online/audiovisual-detail/{id}/{slug}'

    def get_url(self):
        return Video.mk_url(self.id, self.slug)


def _clean_js(k: str, obj: list | dict | str):
    if isinstance(obj, str):
        obj = obj.strip()
        if len(obj) == 0:
            return None
    return obj


class EFilm:
    def __init__(self, origin: str, min_duration=50):
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
            except JSONDecodeError:
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
        root = f"https://backend-prod.efilm.online/api/v1/products/products/relevant/?duration_gte={self.__min_duration}&page=1&page_size=9999&product_type=audiovisual&skip_chapters=true"
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
        director_name=i.get('director_name')
        if typ in ('game', ):
            arr.append(f'type={typ}')
        if gamma in ('Azul', ):
            arr.append(f'gamma={gamma}')
        if director_name in (None, ""):
            arr.append("director=None")
        if duration < self.__min_duration:
            arr.append(f'duration={duration}')
        #if set(genres).intersection({'Cultura', 'Documental'}):
        #    arr.append(f'genres={genres}')
        #if provider in ('Azteca', ):
        #    arr.append(f'provider={provider}')
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
            v = Video(
                id=i['id'],
                name=i.get('name'),
                slug=i['slug'],
                typ=i['type'],
                cover=i.get('cover'),
                cover_horizontal=i.get('cover_horizontal'),
                actors=tuple(i.get('actors') or []),
                duration=i['duration'],
                year=i['year'],
                genres=tuple(x['name'] for x in (i.get('genres') or [])),
                description=i.get('description'),
                covers=tuple(x['cover'] for x in (i.get('covers') or [])),
                director_name=i.get('director_name'),
                banner_main=i.get('banner_main'),
                banner_trailer=i.get('banner_trailer'),
                provider_slug=i.get('provider_slug'),
                provider=(i.get('provider') or {}).get('name'),
                gamma=(i.get('gamma') or {}).get('name_show')
            )
            self.get_ficha(v.id)
            arr.add(v)
        return tuple(sorted(arr, key=lambda v: v.id))

    @cached_property
    def films(self):
        arr: set[Film] = set()
        for v in self.get_videos():
            if v.gamma != "Verde":
                continue
            v = Film(
                source="efilm",
                id=v.id,
                title=v.name,
                url=v.get_url(),
                img=_get_first(v.cover, *v.covers, v.cover_horizontal, v.banner_main, v.banner_trailer),
                lang=None,
                country=tuple(),
                description=v.description,
                year=v.year,
                expiration=None,
                publication=None,
                duration=v.duration,
                imdb=None,
                wiki=None,
                filmaffinity=None,
                director=tp_split("/", v.director_name),
                casting=v.actors,
                genres=v.genres,
                program=None
            )
            arr.add(v)
        return tuple(sorted(arr, key=lambda x: x.id))


if __name__ == "__main__":
    from core.log import config_log
    import sys
    from core.filemanager import FM
    config_log("log/efilm.log")
    e = EFilm()
    for v in e.get_videos():
        if v.genres == ('Documental', ):
            print(v.get_url())
    #sys.exit()
    e.get_items()
