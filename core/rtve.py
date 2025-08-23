from functools import cached_property
from core.web import Web, buildSoup, get_text
from requests.exceptions import TooManyRedirects
import json
from collections import defaultdict
from typing import Any
from bs4 import Tag
import logging
from core.cache import Cache
from core.util import dict_walk, trim, re_or, mapdict, tp_split, dict_walk_positive
import re
from functools import cache
from typing import NamedTuple
from core.filemanager import DictFile, FM
from core.dblite import DB
from types import MappingProxyType


logger = logging.getLogger(__name__)
re_sp = re.compile(r"\s+")


def _clean_js(k: str, obj: list | dict | str):
    if isinstance(obj, str):
        obj = obj.strip()
        if len(obj) == 0:
            return None
        if obj.isdigit() and (k in ("duration", "productionDate", "imdbRate") or k.startswith("id")):
            return int(obj)
        if k in ("director", "casting", "producedBy"):
            return list(tp_split("|", obj))
        if re.match(r"^\d+\.\d+$", obj) and k in ("imdbRate", ):
            return float(obj)
        return obj
    if isinstance(obj, (int, float)) and obj < 0 and k in ("imdbRate", ):
        return None
    return obj


def _g_date(ficha: dict, k: str):
    s = dict_walk(ficha, k, instanceof=(str, type(None)))
    if s is None:
        return None
    num = tuple(map(int, re.findall(r"\d+", s)))
    d = "{2:04d}-{1:02d}-{0:02d} {3:02d}:{4:02d}".format(*num)
    return d


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
    return mapdict(_clean_js, obj, compact=True)


def clean_title(title: str):
    if title is None:
        return None
    title = re_sp.sub(" ", title).strip()
    if "'" not in title:
        title = title.replace('"', "'")
    title = re.sub(r"\s*\(\s*[Cc]ortometraje\s*\)\s*$", "", title)
    if len(title) == 0:
        return None
    return title


def get_attr(n: Tag, slc: str, attr: str):
    if n is None:
        return tuple()
    arr = list()
    for n in n.select(slc):
        val = n.attrs[attr]
        if isinstance(val, str):
            val = val.strip()
        if val not in ([None, ""]+arr):
            arr.append(val)
    return tuple(arr)


class Video(NamedTuple):
    id: str
    typeName: str
    subTypeName: str
    title: str
    img_vertical: tuple[str, ...]
    img_horizontal: tuple[str, ...]
    img_others: tuple[str, ...]
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]
    productionDate: int
    idImdb: str | None
    imdbRate: float
    duration: int
    url: str
    mainTopic: str
    longTitle: str
    ecortContent: str
    programType: str
    programTitle: str
    language: str
    idWiki: str
    expirationDate: str
    publicationDate: str
    description: str


class Rtve(Web):
    CONSOLIDATED: MappingProxyType[int, str] = MappingProxyType(FM.load("cache/rtve.dct.txt"))
    JSONS = (
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-peliculas&contentType=video&size=999',
    )
    BAN_IDS = (
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-series&size=999',
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-programas&size=999',
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-informativos&size=999',
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-deportes&size=999',
        'https://recomsys.rtve.es/recommendation/tops?source=apps&recoId=tve-playz&size=999'
    )

    def __init__(self, *args, **kwargv):
        self.__new = DictFile("cache/rtve.new.dct.txt")
        super().__init__(*args, **kwargv)

    @cached_property
    def urls(self):
        urls: set[str] = set()
        for u in Rtve.JSONS:
            urls.add(u)
        urls.add("https://www.rtve.es/play/cine/")
        self.get("https://www.rtve.es/play/cine/")
        for a in self.soup.select("div[data-feed^='/play/modulos/']"):
            urls.add("https://www.rtve.es"+a.attrs["data-feed"])
        return tuple(urls)

    @cache
    def __get_ids(self, *urls):
        ids: set[int] = set()
        for u in urls:
            js = self.json(u)
            for i in js['page']['items']:
                if isinstance(i, dict):
                    ficha_id = i.get('id')
                    if isinstance(ficha_id, str) and ficha_id.isdigit():
                        ficha_id = int(ficha_id)
                    if isinstance(ficha_id, int):
                        ids.add(ficha_id)
        ids = tuple(sorted(ids))
        return ids

    @cache
    def get_videos(self, *urls: str):
        if len(urls) == 0:
            urls = tuple(self.urls)
        id_li: dict[int, Tag] = dict()
        ids: set[int] = set()
        col: dict[id, set[Video]] = defaultdict(set)
        set_urls = set(urls)
        js_urls = set_urls.intersection(Rtve.JSONS)
        ids = ids.union(self.__get_ids(*js_urls))
        for u in set_urls.difference(js_urls):
            try:
                self.get(u)
            except TooManyRedirects:
                continue
            for li in self.soup.select("*[data-setup]"):
                js = _to_json(li, "data-setup")
                if not isinstance(js, dict):
                    continue
                ficha_id = js.get("idAsset")
                if ficha_id and js.get('tipo') == 'video':
                    ids.add(ficha_id)
                    id_li[ficha_id] = li
        ids_ko = self.__get_ids(*Rtve.BAN_IDS)
        for ficha_id in sorted(ids):
            if ficha_id not in ids_ko:
                v = self.get_video(ficha_id, id_li.get(ficha_id))
                if v is None:
                    continue
                if v.idImdb is None:
                    v = v._replace(
                        idImdb=DB.search_imdb_id(v.title, v.productionDate, v.director, v.duration)
                    )
                    self.__new.set(v.id, v.idImdb)
                col[v.id].add(v)
        arr: set[Video] = set()
        for v in col.values():
            arr.add(self.__merge(v))
        videos = tuple(sorted(arr, key=lambda r: r.id))
        for k in Rtve.CONSOLIDATED.keys():
            self.__new.discard(k)
        self.__new.dump()
        logger.info(f"{len(videos)} recuperados de rtve")
        return videos

    def __merge(self, videos: set[Video]):
        if len(videos) == 0:
            raise ValueError(videos)
        if len(videos) == 1:
            return videos.pop()
        v1 = videos.pop()._asdict()
        while videos:
            for k, new in videos.pop()._asdict().items():
                if new in (None, tuple(), ''):
                    continue
                old = v1[k]
                if old in (None, tuple(), ''):
                    v1[k] = new
                    continue
                if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old < new:
                    v1[k] = new
                    continue
                if type(old) is not type(new):
                    continue
                if isinstance(old, tuple):
                    old = list(old)
                    for x in new:
                        if x not in old:
                            old.append(x)
                    v1[k] = tuple(old)
        return Video(**v1)

    def get_video(self, ficha_id: int, li: Tag = None):
        ficha = self.get_ficha(ficha_id)
        idAsset = dict_walk(ficha, 'id', instanceof=(int, type(None)))
        if idAsset != ficha_id:
            raise ValueError(ficha)
        ficha_idImdb = dict_walk(ficha, 'idImdb', instanceof=(str, type(None)))
        self.__new.set(idAsset, ficha_idImdb)

        img_vertical, img_horizontal, img_others = self.__get_imgs_from_ficha(ficha, li)

        url = dict_walk(ficha, 'htmlUrl', instanceof=str)
        duration = dict_walk(ficha, 'duration', instanceof=(int, type(None)))
        if duration is not None:
            duration = int(duration/(60*1000))

        v = Video(
            id=idAsset,
            url=url,
            title=clean_title(dict_walk(ficha, 'title', instanceof=str)),
            img_vertical=img_vertical,
            img_horizontal=img_horizontal,
            img_others=img_others,
            productionDate=dict_walk(ficha, 'productionDate', instanceof=(int, type(None))),
            idImdb=Rtve.CONSOLIDATED.get(idAsset, ficha_idImdb),
            typeName=dict_walk(ficha, 'type/name', instanceof=(str, type(None))),
            subTypeName=dict_walk(ficha, 'subType/name', instanceof=(str, type(None))),
            director=tuple(dict_walk(ficha, 'director', instanceof=(list, type(None))) or []),
            casting=tuple(dict_walk(ficha, 'casting', instanceof=(list, type(None))) or []),
            imdbRate=dict_walk_positive(ficha, 'imdbRate'),
            mainTopic=dict_walk(ficha, 'mainTopic', instanceof=str),
            longTitle=dict_walk(ficha, 'longTitle', instanceof=(str, type(None))),
            ecortContent=dict_walk(ficha, 'escort/content', instanceof=(str, type(None))),
            programType=dict_walk(ficha, 'programInfo/programType', instanceof=(str, type(None))),
            programTitle=dict_walk(ficha, 'programInfo/title', instanceof=(str, type(None))),
            language=dict_walk(ficha, 'language', instanceof=str),
            idWiki=dict_walk(ficha, 'idWiki', instanceof=(str, type(None))),
            expirationDate=_g_date(ficha, 'expirationDate'),
            publicationDate=_g_date(ficha, 'publicationDate'),
            duration=duration,
            genres=self.__get_genres_from_ficha(ficha),
            description=self.__get_description(url, ficha),
        )
        if self.__is_ko(v):
            return None
        return v

    def __get_genres_from_ficha(self, ficha: dict):
        genres: list[str] = list()
        for g in (ficha.get("generos") or []):
            v = trim(g.get('subGeneroInf')) or trim(g.get('generoInf'))
            if v not in ([None, ""]+genres):
                genres.append(v)
        return tuple(genres)

    def __get_imgs_from_ficha(self, ficha: dict, li: Tag):
        img_done = set({None, ""})
        img_vertical: list[str] = list(get_attr(li, "img[data-src*=vertical]", "data-src"))
        img_horizontal: list[str] = list(get_attr(li, "img[data-src*=horizontal]", "data-src"))
        img_others: list[str] = list()
        for k in (
            'previews/vertical',
            'previews/vertical2',
        ):
            val = dict_walk(ficha, k, instanceof=(str, type(None)))
            if val not in img_done:
                img_vertical.append(val)
                img_done.add(val)
        for k in (
            'previews/horizontal',
            'previews/horizontal2',
        ):
            val = dict_walk(ficha, k, instanceof=(str, type(None)))
            if val not in img_done:
                img_horizontal.append(val)
                img_done.add(val)
        for k in (
            'previews/square',
            'previews/square2',
            'imageSEO',
            'thumbnail'
        ):
            val = dict_walk(ficha, k, instanceof=(str, type(None)))
            if val not in img_done:
                img_others.append(val)
                img_done.add(val)

        qualities = dict_walk(ficha, 'qualities', instanceof=(list, type(None)))
        for q in reversed(qualities or []):
            if isinstance(q, dict):
                val = q.get('previewPath')
                if isinstance(val, str) and val not in img_done:
                    img_others.append(val)
                    img_done.add(val)
        return tuple(map(tuple, (
            img_vertical,
            img_horizontal,
            img_others,
        )))

    def __is_ko(self, v: Video):
        if v.typeName in ('Avance', 'Fragmento'):
            return f"type={v.typeName} subType={v.subTypeName}"
        if self.__is_ko_mainTopic(v.mainTopic):
            return f"mainTopic={v.mainTopic}"
        if "Playz joven" in v.genres:
            return f"genero={', '.join(v.genres)}"
        if v.programType in ("Entrevistas", ):
            return f"programType={v.programType}"
        return None

    def __is_ko_mainTopic(self, mainTopic: str):
        if mainTopic.startswith("Televisión/Programas de TVE/"):
            tp_mainTopic = mainTopic.split("/")[2:]
            if not set(tp_mainTopic).intersection(('Cine', 'Documentales')):#, 'Cinema en català')):
                return True
        if mainTopic.startswith('PLAYZ/Series/'):
            return True
        return False

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
            if re_or(txt, "^(Película )?[Dd]irigida( y guionizada)? por", "^Contenido disponible", "^Este contenido está disponible"):
                n.extract()
        return str(soup)

    @Cache("rec/rtve/ficha/{}.json")
    def get_ficha(self, id: int) -> dict[str, Any]:
        js = self.json(f"https://api.rtve.es/api/videos/{id}.json")
        return mapdict(_clean_js, js['page']['items'][0], compact=True)


if __name__ == "__main__":
    r = Rtve()
    v = r.get_videos(*r.urls)
