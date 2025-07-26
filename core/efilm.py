from typing import Any
from core.cache import Cache
from core.util import mapdict
import requests
from requests.exceptions import JSONDecodeError
from typing import NamedTuple
import logging
import time

logger = logging.getLogger(__name__)


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
    def __init__(self):
        self.__s = requests.Session()

    def get_json(self, url: str) -> list[dict[str, Any]]:
        max_tries = 3
        result = []
        while url:
            r = self.__s.get(url)
            if max_tries > 0 and r.status_code == 500:
                max_tries = max_tries - 1
                time.sleep(5)
                continue
            try:
                js = r.json()
            except JSONDecodeError:
                logger.critical(f"{r.status_code} {url}")
                raise
            result.extend(js['results'])
            url = js['next']
        return result

    @Cache("rec/efilm/items.json")
    def get_items(self) -> list[dict]:
        done: set[int] = set()
        arr = []
        js = self.get_json("https://backend-prod.efilm.online/api/v1/products/products/relevant/?page=1&page_size=9999&skip_chapters=true")
        i: dict
        for i in mapdict(_clean_js, js, compact=True):
            if i['id'] not in done:
                errors = self.__get_errors(i)
                if errors:
                    url = Video.mk_url(i['id'], i.get('slug'))
                    logger.debug(f"[KO] {', '.join(errors)} {url}")
                    continue
                arr.append(i)
                done.add(i['id'])
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
        if duration < 10:
            arr.append(f'duration={duration}')
        #if set(genres).intersection({'Cultura', 'Documental'}):
        #    arr.append(f'genres={genres}')
        #if provider in ('Azteca', ):
        #    arr.append(f'provider={provider}')
        return tuple(arr)

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
            arr.add(v)
        return tuple(sorted(arr, key=lambda v: v.id))


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
