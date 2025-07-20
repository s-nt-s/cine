from functools import cached_property
from core.web import Web, buildSoup, get_text
from requests.exceptions import TooManyRedirects
import json
from collections import defaultdict
from typing import Any
from bs4 import Tag
from core.filemanager import FM
import logging
from core.cache import Cache
from core.util import dict_walk, trim, re_or, mapdict, tp_split, to_int_float, dict_walk_positive
from core.film import Film, IMDb
from core.imdb import IMDB, IMDBInfo
import re
from core.wiki import WIKI
from core.country import to_country
from functools import cache
from typing import NamedTuple


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
    idImdb: str
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
        id_li: dict[int, Tag] = dict()
        ids: set[int] = set()
        arr: set[Video] = set()
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
                ficha = self.get_ficha(ficha_id)
                arr.add(self.__ficha_to_video(ficha, id_li.get(ficha_id)))
        return tuple(sorted(arr, key=lambda r: r.id))

    def __ficha_to_video(self, ficha: dict, li: Tag = None):
        idAsset = dict_walk(ficha, 'id', instanceof=(int, type(None)))
        productionDate = dict_walk(ficha, 'productionDate', instanceof=(int, type(None)))
        title = clean_title(dict_walk(ficha, 'title', instanceof=str))

        img_vertical, img_horizontal, img_others = self.__get_imgs_from_ficha(ficha, li)

        idImdb = IMDB.get_id(title, productionDate) or dict_walk(ficha, 'idImdb', instanceof=(str, type(None)))
        url = dict_walk(ficha, 'htmlUrl', instanceof=str)
        duration = dict_walk(ficha, 'duration', instanceof=(int, type(None)))
        if duration is not None:
            duration = int(duration/(60*1000))

        v = Video(
            id=idAsset,
            url=url,
            title=title,
            img_vertical=img_vertical,
            img_horizontal=img_horizontal,
            img_others=img_others,
            productionDate=productionDate,
            idImdb=idImdb,
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

    def get_films(self, *urls: str) -> tuple[Film, ...]:
        videos = list(self.get_videos(*urls))

        def __filter(_get_imdb_info):
            for i, v in reversed(list(enumerate(videos))):
                is_ko = self.__is_ko(v, _get_imdb_info(v.idImdb))
                if is_ko:
                    logger.warning(f"{v.id} {v.title} descartado por "+is_ko)
                    del videos[i]

        logger.info("Filtro imdb=None")
        __filter(lambda x: None)
        logger.info("Filtro imdb = <completeWithImdb=False, completeWithWiki=False>")
        __filter(lambda x: IMDB.get(x, completeWithImdb=False, completeWithWiki=False))
        logger.info("Filtro imdb = <completeWithImdb=True, completeWithWiki=False>")
        __filter(lambda x: IMDB.get(x, completeWithImdb=True, completeWithWiki=False))
        logger.info("Filtro imdb = <completeWithImdb=True, completeWithWiki=True>")
        __filter(lambda x: IMDB.get(x, completeWithImdb=True, completeWithWiki=True))
        logger.info(f"Resultado filtro {len(videos)}")

        films: set[Film] = set()
        for v in videos:
            imdb_info = IMDB.get(v.idImdb)
            f = Film(
                source="rtve",
                id=v.id,
                title=v.title,
                url=v.url,
                img=self.__get_img(v, imdb_info),
                program=v.programTitle,
                lang=v.language,
                description=v.description,
                year=v.productionDate or imdb_info.year,
                expiration=v.expirationDate,
                publication=v.publicationDate,
                duration=v.duration,
                director=v.director or imdb_info.director or tuple(),
                casting=v.casting or imdb_info.actor or tuple(),
                genres=self.__get_genres(v, imdb_info) or tuple(),
                imdb=IMDb(
                    id=v.idImdb,
                    rate=to_int_float(v.imdbRate or imdb_info.rating),
                    votes=imdb_info.votes if imdb_info else None
                ) if v.idImdb else None,
                wiki=WIKI.parse_url(imdb_info.wiki or v.idWiki),	
                country=tuple(set(map(to_country, imdb_info.countries))),
                filmaffinity=imdb_info.filmaffinity
            )
            films.add(f)
        return tuple(films)

    def __is_ko(self, v: Video, info_imdb: IMDBInfo):
        if info_imdb is None:
            info_imdb = IMDBInfo(id=None)
        if v.typeName in ('Avance', 'Fragmento'):
            return f"type={v.typeName} subType={v.subTypeName}"
        if self.__is_ko_mainTopic(v.mainTopic):
            return f"mainTopic={v.mainTopic}"
        genres = self.__get_genres(v, None)
        if "Playz joven" in genres:
            return f"genero={', '.join(genres)}"
        if v.programType in ("Entrevistas", ):
            return f"programType={v.programType}"
        if info_imdb.awards is None and 'Spain' not in info_imdb.countries and "Documental" not in genres:
            if info_imdb.typ in ("tvmovie", "episode", "series"):
                return "Type="+info_imdb.typ
            if "TV Movies" in genres:
                return "Genero=TV Movies"
        for t in (info_imdb.title, v.title):
            if re_or(t, r"^Ein Sommer (an|auf)", r"^Corazón roto\. ", flags=re.I):
                return "Title="+t
        return None

    def __is_ko_mainTopic(self, mainTopic: str):
        if mainTopic.startswith("Televisión/Programas de TVE/"):
            tp_mainTopic = mainTopic.split("/")[2:]
            if not set(tp_mainTopic).intersection(('Cine', 'Documentales')):#, 'Cinema en català')):
                return True
        if mainTopic.startswith('PLAYZ/Series/'):
            return True
        return False

    def __get_img(self, v: Video, imdb_info: IMDBInfo) -> str:
        if v.img_vertical:
            return v.img_vertical[0]
        if imdb_info and imdb_info.img:
            return imdb_info.img
        if v.img_horizontal:
            return v.img_horizontal[0]
        if v.img_others:
            return v.img_others[0]

    def __get_genres(self, v: Video, imdb_info: IMDBInfo):
        if imdb_info is None:
            imdb_info = IMDBInfo(id=None)
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

    @cached_property
    def films(self):
        dct_films: dict[Film, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for f in self.get_films(*self.urls):
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
        return mapdict(_clean_js, js['page']['items'][0], compact=True)


if __name__ == "__main__":
    r = Rtve()
    x = r.films  # r.get_ids("https://www.rtve.es/play/modulos/collection/3557/?skin=rtve-play-tematicas&pos=10&home=true&noLabels=false&distribution=slide")
    print(len(r.films), "resultados")
    FM.dump("rec/rtve.json", r.films)
