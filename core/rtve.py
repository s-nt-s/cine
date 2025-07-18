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
    d = "{2:04d}-{1:02d}-{0:02d} {3:02d}:{4:02d}:{5:02d}".format(*num)
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
            title: str = dict_walk(js, 'title', instanceof=str)
            title = re_sp.sub(" ", title).strip()
            if "'" not in title:
                title = title.replace('"', "'")
            title = re.sub(r"\s*\(\s*[Cc]ortometraje\s*\)\s*$", "", title)

            is_ko = self.__is_ko(ficha, None)
            if is_ko:
                logger.warning(f"{idAsset} {title} descartado por "+is_ko)
                continue

            year: int = dict_walk(ficha, 'productionDate', instanceof=(int, type(None)))
            idImdb = IMDB.get_id(title, year) or \
                     dict_walk(ficha, 'idImdb', instanceof=(str, type(None)))
            imdb_info = IMDB.get(idImdb)

            is_ko = self.__is_ko(ficha, imdb_info)
            if is_ko:
                logger.warning(f"{idAsset} {title} descartado por "+is_ko)
                continue

            genres = self.__get_genres(ficha, imdb_info)
            img = self.__get_img(li, ficha, imdb_info)
            director: list[str] = dict_walk(ficha, 'director', instanceof=(list, type(None))) or \
                                  list(imdb_info.director) or \
                                  list()
            casting: list[str] = dict_walk(ficha, 'casting', instanceof=(list, type(None))) or \
                                 list(imdb_info.actor) or \
                                 list()
            imdbRate: float = dict_walk_positive(ficha, 'imdbRate') or \
                              imdb_info.rating
            duration = dict_walk(ficha, 'duration', instanceof=int)
            if isinstance(duration, int):
                duration = int(duration/(60*1000))
            if year is None:
                year: int = imdb_info.year

            url = dict_walk(ficha, 'htmlUrl', instanceof=str)
            f = Film(
                source="rtve",
                id=idAsset,
                title=title,
                url=url,
                img=img,
                program=dict_walk(ficha, 'programInfo/title', instanceof=(str, type(None))),
                lang=dict_walk(ficha, 'language', instanceof=str),
                description=self.__get_description(url, ficha),
                year=year,
                expiration=_g_date(ficha, 'expirationDate'),
                publication=_g_date(ficha, 'publicationDate'),
                duration=duration,
                director=tuple(director),
                casting=tuple(casting),
                genres=tuple(genres),
                imdb=IMDb(
                    id=idImdb,
                    rate=to_int_float(imdbRate),
                    votes=imdb_info.votes if imdb_info else None
                ) if idImdb else None,
                wiki=WIKI.parse_url(imdb_info.wiki or dict_walk(ficha, 'idWiki', instanceof=(str, type(None)))),	
                country=tuple(set(map(to_country, imdb_info.countries))),
                filmaffinity=imdb_info.filmaffinity
            )
            films.add(f)
        return tuple(films)

    def __is_ko(self, ficha: dict, info_imdb: IMDBInfo):
        if info_imdb is None:
            info_imdb = IMDBInfo(id=None)
        type_name: str = dict_walk(ficha, 'type/name', instanceof=str)
        sbty_name: str = dict_walk(ficha, 'subType/name', instanceof=(str, type(None)))
        if type_name in ('Avance', 'Fragmento'):
            return f"type/name={type_name} subType/name={sbty_name}"
        mainTopic: str = dict_walk(ficha, 'mainTopic', instanceof=str)
        if self.__is_ko_mainTopic(mainTopic):
            return f"mainTopic={mainTopic}"
        genres = self.__get_genres(ficha, None)
        if "Playz joven" in genres:
            return f"genero={', '.join(genres)}"
        if ficha.get("temporadas"):
            return "temporadas!=null"
        programType = dict_walk(ficha, 'programInfo/programType', instanceof=(str, type(None)))
        if programType in ("Entrevistas", ):
            return f"programType={programType}"
        if info_imdb.awards is None and 'Spain' not in info_imdb.countries and "Documental" not in genres:
            if info_imdb.typ in ("tvmovie", "episode", "series"):
                return "Type="+info_imdb.typ
            if "TV Movies" in genres:
                return "Genero=TV Movies"
        for t in (info_imdb.title, ficha.get('title')):
            if re_or(t, "^Ein Sommer (an|auf)", r"^Corazón roto\. ", flags=re.I):
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

    def __get_img(self, li: Tag, ficha: dict, imdb_info: IMDBInfo) -> str:
        for img in li.select("img[data-src*=vertical]"):
            src = img.attrs["data-src"]
            if src:
                return src
        ficha['__poster'] = imdb_info.img
        for k in (
            'previews/vertical',
            'previews/vertical2',
            '__poster',
            'previews/horizontal',
            'previews/horizontal2'
            'previews/square',
            'previews/square2',
            'imageSEO',
            'thumbnail'
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

    def __get_genres(self, ficha: dict, imdb_info: IMDBInfo):
        if imdb_info is None:
            imdb_info = IMDBInfo(id=None)
        mainTopic = dict_walk(ficha, 'mainTopic', instanceof=(str, type(None)))
        longTitle = dict_walk(ficha, 'longTitle', instanceof=(str, type(None)))
        ecort_content = dict_walk(ficha, 'escort/content', instanceof=(str, type(None)))
        programType = dict_walk(ficha, 'programInfo/programType', instanceof=(str, type(None)))
        if re_or(longTitle, r"^Cine [iI]nfantil"):
            return ("Infantil", )
        if re_or(longTitle, r"^Somos [dD]documentales"):
            return ("Documental", )
        if re_or(mainTopic, r"[Pp]el[íi]culas [Dd]ocumentales"):
            return ("Documental", )
        if re_or(mainTopic, r"[Cc]omedia negra"):
            return ("Comedia", )
        #if re_or(ecort_content, r"[Nn]o [Ff]icci[oó]n[\-\-\s]*[Ii]nformaci[óo]n"):
        #    return ("Documental", )
        if re_or(programType, r"[dD]ocumental"):
            return ("Documental", )
        if re_or(mainTopic, r"Thriller"):
            return ("Suspense", )
        if re_or(ecort_content, r"Thriller"):
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
        for g in (ficha.get("generos") or []):
            v = trim(g.get('subGeneroInf')) or trim(g.get('generoInf'))
            if v in (None, "Cine", "Cultura"):
                continue
            v = {
                "Documentales": "Documental",
                "Biografías": "Biográfico",
                "Música": "Musical",
                "Policíaca y suspense": "Suspense",
                "Acción y aventuras": "Aventuras",
                "Historia": "Histórico"
            }.get(v, v)
            genres.add(v)
        if len(genres):
            return tuple(genres)
        if re_or(ecort_content, "[dD]rama"):
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
        return mapdict(_clean_js, js['page']['items'][0], compact=True)


if __name__ == "__main__":
    r = Rtve()
    x = r.films  # r.get_ids("https://www.rtve.es/play/modulos/collection/3557/?skin=rtve-play-tematicas&pos=10&home=true&noLabels=false&distribution=slide")
    print(len(r.films), "resultados")
    FM.dump("rec/rtve.json", r.films)
