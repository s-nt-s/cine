from functools import cached_property
from core.web import Web, buildSoup, get_text
from requests.exceptions import TooManyRedirects
import json
from collections import defaultdict
from typing import NamedTuple, Any
from bs4 import Tag
from core.filemanager import FM
import logging
from core.cache import Cache
from core.util import dict_walk, trim, re_or
from core.film import Film
import re

logger = logging.getLogger(__name__)


def _clean_js(obj: list | dict | str, k: str = None):
    if isinstance(obj, str):
        obj = obj.strip()
        if len(obj) == 0:
            return None
        if isinstance(k, str) and k.startswith("id") and obj.isdigit():
            return int(obj)
        return obj
    if isinstance(obj, list):
        return [_clean_js(i) for i in obj]
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            obj[k] = _clean_js(v, k=k)
    return obj


def _to_json(n: Tag, attr: str):
    if n is None:
        return None
    val = n.attrs.get(attr)
    if not isinstance(val, str):
        return None
    val = val.strip()
    if len(val) == 0:
        return None
    obj = json.loads(val)
    return _clean_js(obj)


class Rtve(Web):
    @cached_property
    def urls(self):
        urls: set[str] = set()
        urls.add("https://www.rtve.es/play/cine/")
        self.get("https://www.rtve.es/play/cine/")
        for a in self.soup.select("div[data-feed^='/play/modulos/']"):
            urls.add("https://www.rtve.es"+a.attrs["data-feed"])
        return tuple(urls)

    def get_films(self, url: str) -> tuple[Film, ...]:
        try:
            self.get(url)
        except TooManyRedirects:
            return ()
        films: set[Film] = set()
        for li in self.soup.select("*[data-setup]"):
            js = _to_json(li, "data-setup")
            if not isinstance(js, dict):
                continue
            idAsset = js.get("idAsset")
            if idAsset is None or js.get("tipo") != "video":
                continue
            ficha = self.get_ficha(idAsset)
            type_name: str = dict_walk(ficha, 'type/name', instanceof=str)
            sbty_name: str = dict_walk(ficha, 'subType/name', instanceof=(str, type(None)))
            title: str = dict_walk(js, 'title', instanceof=str)
            if type_name in ('Avance', 'Fragmento'):
                logger.warning(f"{idAsset} {title} descartado por {type_name} {sbty_name or ''}".strip())
                continue
            mainTopic: str = dict_walk(ficha, 'mainTopic', instanceof=str)
            if mainTopic.startswith("Televisión/Programas de TVE/"):
                tp_mainTopic = mainTopic.split("/")[2:]
                if not set(tp_mainTopic).intersection(('Cine', 'Documentales')):#, 'Cinema en català')):
                    logger.warning(f"{idAsset} {title} descartado por {mainTopic}".strip())
                    continue
            if "'" not in title:
                title = title.replace('"', "'")
            duration = dict_walk(ficha, 'duration', instanceof=int)
            if isinstance(duration, int):
                duration = int(duration/(60*1000))
            year: int = dict_walk(ficha, 'productionDate', instanceof=(int, type(None)))
            director: str = dict_walk(ficha, 'director', instanceof=(str, type(None))) or ''
            casting: str = dict_walk(ficha, 'casting', instanceof=(str, type(None))) or ''
            genres = self.__get_genres(ficha)
            if "Playz joven" in genres:
                logger.warning(f"{idAsset} {title} descartado por genero {', '.join(genres)}".strip())
                continue

            def _g_date(k: str):
                s = dict_walk(ficha, k, instanceof=(str, type(None)))
                if s is None:
                    return None
                num = tuple(map(int, re.findall(r"\d+", s)))
                return "{2:04d}-{1:02d}-{0:02d}".format(*num[:3])

            url = dict_walk(ficha, 'htmlUrl', instanceof=str)
            films.add(Film(
                source="rtve",
                id=idAsset,
                title=title,
                url=url,
                img=self.__get_img(li, ficha),
                program=dict_walk(ficha, 'programInfo/title', instanceof=(str, type(None))),
                lang=dict_walk(ficha, 'language', instanceof=str),
                country=dict_walk(ficha, 'country', instanceof=str),
                description=self.__get_description(url, ficha),
                year=year,
                expiration=_g_date('expirationDate'),
                publication=_g_date('publicationDate'),
                duration=duration,
                director=tuple(i for i in map(trim, director.split(" | ")) if i),
                casting=tuple(i for i in map(trim, casting.split(" | ")) if i),
                genres=genres
            ))
        return tuple(films)

    def __get_img(self, li: Tag, ficha: dict) -> str:
        for img in li.select("img[data-src*=vertical]"):
            src = img.attrs["data-src"]
            if src:
                return src
        for k in (
            'previews/vertical',
            'previews/vertical2',
            'previews/horizontal',
            'previews/horizontal2'
            'previews/square',
            'previews/square2',
            'imageSEO'
        ):
            v = dict_walk(ficha, k, instanceof=(str, type(None)))
            if isinstance(v, str):
                return v
        qualities = dict_walk(ficha, 'qualities', instanceof=(list, type(None)))
        for q in reversed(qualities or []):
            if isinstance(q, dict):
                img = q.get('previewPath')
                if isinstance(img, str):
                    return img

    def __get_genres(self, ficha: dict):
        genres: set[str] = set()
        for g in (ficha.get("generos") or []):
            for k in ('generoInf', 'subGeneroInf'):
                v = trim(g.get(k))
                if v in (None, "Cine"):
                    continue
                if v in ("Documentales", "Biografías", "Historia"):
                    v = "Documental"
                genres.add(v)
        return tuple(genres)

    def __get_description(self, url: str, ficha: dict):
        arr = [i for i in map(
                lambda x: dict_walk(ficha, x, instanceof=(str, type(None))), (
                    'description',
                    'shortDescription',
                    'promoDesc'
                )
            ) if i is not None]
        if len(arr) == 0:
            return None
        description = arr[0]
        if description[0]+description[-1] != "<>":
            return description
        soup = buildSoup(url, description, parser="html.parser")
        for n in soup.select("strong, p"):
            txt = get_text(n)
            if not txt:
                n.extract()
                continue
            if re_or(txt, "^Dirigida por", "^Contenido disponible"):
                n.extract()
        return str(soup)

    @cached_property
    def films(self):
        dct_films: dict[Film, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for url in self.urls:
            for f in self.get_films(url):
                k = f._replace(
                    img=None,
                    program=None
                )
                for field in ("img", "program"):
                    val = f._asdict()[field]
                    if val is not None:
                        dct_films[k][field].add(val)
        films: set[Film] = set()
        for f, set_values in dct_films.items():
            for k, v in set_values.items():
                if k == "img":
                    best = [i for i in v if "/?h=" in i]
                    if len(best) > 0:
                        v = best
                v = tuple(sorted(v))
                if len(v) > 1:
                    logger.warning(f"{f.id} {f.title} {f.url} tiene varios {k} = {v}")
                if len(v) > 0:
                    if k == "img":
                        img = v[0]
                        if img.endswith("?h=400"):
                            img = img.rsplit("?", 1)[0]+"?w=150"
                        f = f._replace(**{k: img})
                    else:
                        f = f._replace(**{k: ", ".join(v)})
            films.add(f)
        return tuple(sorted(films, key=lambda x: (x.title, x.id)))

    @Cache("rec/rtve/{}.json")
    def get_ficha(self, id: int) -> dict[str, Any]:
        js = self.json(f"https://api.rtve.es/api/videos/{id}.json")
        return _clean_js(js['page']['items'][0])


if __name__ == "__main__":
    r = Rtve()
    x = r.films  # r.get_ids("https://www.rtve.es/play/modulos/collection/3557/?skin=rtve-play-tematicas&pos=10&home=true&noLabels=false&distribution=slide")
    print(len(r.films), "resultados")
    FM.dump("rec/rtve.json", r.films)
