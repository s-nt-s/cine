from requests import Session
from os import environ
import logging
from core.util import tp_split, re_or, mapdict, dict_walk, dict_walk_tuple, dict_walk_positive
from core.cache import Cache
from functools import cache
import re
from core.db import DBCache, DB
from core.web import buildSoup, get_text, WEB, find_by_text
from core.wiki import WIKI
from typing import NamedTuple, Optional


logger = logging.getLogger(__name__)


def _clean_js(k: str, obj):
    if isinstance(obj, str):
        obj = obj.strip()
        if obj in ("", "N/A"):
            return None
        if obj in ("True", "False"):
            return obj == "True"
        nums = tuple(map(int, re.findall(r"\d+", obj)))
        if k == 'Year' and len(nums) == 1 and nums[0] > 1900:
            return nums[0]
        if obj.isdigit() and k in ('Year', "imdbRating", "totalSeasons"):
            return int(obj)
        if k in ("Director", "Writer", "Actors", "Genre", "Country"):
            return list(tp_split(r",", obj))
        if re.match(r"^\d+\.\d+$", obj) and k in ("imdbRating", ):
            return float(obj)
        if re.match(r"^\d+[\.\d,]*$", obj) and k in ("imdbVotes", ):
            return int(obj.replace(",", ""))
        return obj
    if isinstance(obj, (int, float)) and obj < 0 and k in ("imdbRating", "imdbVotes"):
        return None
    return obj


def get_positive(data: dict, field: str):
    val = dict_walk(data, field, instanceof=(int, float, type(None)))
    if val is None or val < 0:
        return None
    i = int(val)
    return i if i == val else val


class DBIMDBWikiCache(DBCache):
    def __init__(self, field):
        super().__init__(
            select=f"select {field} from IMDB_WIKI where id = %s",
            insert=f"insert into IMDB_WIKI (id, {field}) values (%s, %s) ON CONFLICT (id) DO UPDATE SET {field} = EXCLUDED.{field}, updated=now()"
        )

    def read(self, *args):
        val = super().read(*args)
        if isinstance(val, list):
            return tuple(val)
        return val

    def save(self, data, *args):
        if isinstance(data, (list, tuple)) and len(data) == 0:
            return
        if isinstance(data, tuple):
            data = list(data)
        return DB.execute(self.insert, args + (data, ))


class IMDBInfo(NamedTuple):
    id: str
    title: Optional[str] = None
    director: Optional[tuple[str, ...]] = tuple()
    actor: Optional[tuple[str, ...]] = tuple()
    rating: Optional[float] = None
    votes: Optional[int] = None
    year: Optional[int] = None
    countries: Optional[tuple[str, ...]] = tuple()
    wiki: Optional[str] = None
    awards: Optional[str] = None
    typ: Optional[str] = None
    genres: Optional[tuple[str, ...]] = tuple()
    img: Optional[str] = None
    filmaffinity: Optional[int] = None


class IMDBApi:
    def __init__(self):
        key = environ['OMDBAPI_KEY']
        self.__omdbapi = f"http://www.omdbapi.com/?apikey={key}&i="
        self.__imdb = "https://www.imdb.com/es-es/title/"
        self.__s = Session()

    @DBCache(
        select="select json from OMBDAPI where id = %s and updated > NOW() - INTERVAL '30 days'",
        insert="insert into OMBDAPI (id, json) values (%s, %s) ON CONFLICT (id) DO UPDATE SET json = EXCLUDED.json, updated=now()"
    )
    def __get_from_omdbapi(self, id: str):
        r = self.__s.get(self.__omdbapi+id)
        js = r.json()
        return js

    def get(self, id: str):
        if id is None:
            return IMDBInfo(id=None)
        data = self.__get(id)
        if data is None:
            return IMDBInfo(id=id)
        return IMDBInfo(
            id=id,
            title=dict_walk(data, 'Title', instanceof=(str, type(None))),
            director=dict_walk_tuple(data, 'Director'),
            actor=dict_walk_tuple(data, 'Actors'),
            rating=dict_walk_positive(data, 'imdbRating'),
            votes=dict_walk_positive(data, 'imdbVotes'),
            year=dict_walk_positive(data, 'Year'),
            countries=tuple(self.__merge(
                dict_walk(data, 'Country', instanceof=(list, type(None))),
                dict_walk(data, 'wiki_countries', instanceof=(list, tuple, type(None)))
            )),
            wiki=self.__get_wiki_from_imdb(id), #dict_walk(data, 'wiki', instanceof=(str, type(None))),
            awards=dict_walk(data, 'Awards', instanceof=(str, type(None))),
            typ=dict_walk(data, 'Type', instanceof=(str, type(None))),
            genres=dict_walk_tuple(data, 'Genre'),
            img=dict_walk(data, 'Poster', instanceof=(str, type(None))),
            filmaffinity=dict_walk(data, 'filmaffinity', instanceof=(int, type(None))),
        )

    def __merge(self, countries1: list[str], countries2: list[str]):
        if not countries1:
            return countries2 or list()
        if not countries2:
            return countries1 or list()
        merge = list(set(countries1).intersection(countries2))
        if not merge:
            return countries2 or list()
        return merge

    @cache
    @Cache("rec/imdb/{}.json")
    def __get(self, id: str):
        data = self.__get_basic(id) or {}
        for k in ('Response', ):
            if k in data:
                del data[k]
        data['filmaffinity'] = self.__get_filmaffinity_from_imdb(id)
        data['wiki'] = self.__get_wiki_from_imdb(id)
        data['wiki_countries'] = self.__get_countries_from_imdb(id)
        data = {k: v for k, v in data.items() if v is not None}
        if len(data) == 0:
            return None
        return data

    @cache
    @DBIMDBWikiCache("filmaffinity")
    def __get_filmaffinity_from_imdb(self, imdb_id: str):
        return WIKI.get_filmaffinity_from_imdb(imdb_id)

    @cache
    @DBIMDBWikiCache("wiki")
    def __get_wiki_from_imdb(self, imdb_id: str):
        return WIKI.get_wiki_url_from_imdb(imdb_id)

    @cache
    @DBIMDBWikiCache("countries")
    def __get_countries_from_imdb(self, imdb_id: str):
        return WIKI.get_countries_from_imdb(imdb_id)

    def __get_basic(self, id: str):
        if id in (None, ""):
            return None
        js = self.__get_from_omdbapi(id)
        js = mapdict(_clean_js, js, compact=True)
        isError = js.get("Error")
        if isError:
            logger.warning(f"IMDBApi: {id} = {js['Error']}")
        if self.__need_info(js):
            soup_js = self.__get_from_imdb(id)
            if isError:
                return soup_js
            if soup_js is None:
                return js
            for k, v in soup_js.items():
                val = js.get(k)
                if k in ('Type', ) or (val is None or (isinstance(v, (int, float)) and isinstance(val, (int, float)) and val<v)):
                    js[k] = v
        return js

    def __need_info(self, js: dict):
        if js.get("Error"):
            return True
        if not isinstance(js.get('imdbRating'), (float, int)):
            return True
        if not isinstance(js.get("imdbVotes"), (int, float)):
            return True
        if set(('France', 'Germany', 'Australia')).intersection(js.get('Country', set())):
            return True
        if js.get('Type') not in ("episode", "series"):
            return True
        return False

    def __get_from_imdb(self, id: str):
        js = dict()
        url = f"{self.__imdb}{id}"
        soup = buildSoup(url, self.__get_html(url))
        votes = get_text(soup.select_one('a[aria-label="Ver puntuaciones de usuarios"]'))
        if votes is not None:
            votes = votes.replace("/10", " ")
            votes = re.sub(r" mil$", "000", votes)
            votes = re.sub(r" M$", "000000", votes)
            spl = votes.split()
            if len(spl) != 2:
                raise ValueError(f"{url} = {spl}")
            imdbRating, imdbVotes = spl
            js["imdbRating"] = float(imdbRating.replace(",", "."))
            js["imdbVotes"] = int(imdbVotes.replace(",", ""))
        if find_by_text(soup, "a", "Todos los episodios"):
            js['Type'] = 'episode'
        if find_by_text(soup, "li", "Película de TV"):
            js['Type'] = 'tvmovie'

        js = {k: v for k, v in js.items() if v is not None}
        if len(js) == 0:
            return None
        return js

    @DBCache(
        select="select txt from URL_TXT where url = %s and updated > NOW() - INTERVAL '10 days'",
        insert="insert into URL_TXT (url, txt) values (%s, %s) ON CONFLICT (url) DO UPDATE SET txt = EXCLUDED.txt, updated=now()"
    )
    def __get_html(self, url):
        soup = WEB.get_cached_soup(url)
        return str(soup)

    def get_id(self, title: str, year: int):
        if re_or(title, "^Almodóvar, todo sobre ellas", flags=re.I):
            return "tt6095626"
        if re_or(title, "^De Salamanca a ninguna parte", flags=re.I):
            return "tt0336249"
        if re_or(title, "^Los comuneros$", flags=re.I) and year == 1978:
            return "tt0573534"
        if re_or(title, "^Fernando Méndez Leite. La memoria del cine", "La memoria del cine: una película sobre Fernando Méndez-Leite", flags=re.I):
            return "tt26812553"
        if re_or(title, "^Spanish Western", flags=re.I):
            return "tt6728914"
        if re_or(title, "^La primera mirada", flags=re.I):
            return "tt32897831"
        if re_or(title, "^Los habitantes de la casa deshabitada", flags=re.I):
            return "tt7534332"
        if re_or(title, "^Bolívar. El hombre de las dificultades", flags=re.I):
            return "tt3104336"
        if re_or(title, "^MAMA$", flags=re.I) and year == 2021:
            return "tt12725124"
        if re_or(title, "^El techo amarillo", flags=re.I) and year == 2022:
            return "tt20112674"
        if re_or(title, "^Historias de nuestro cine", flags=re.I) and year == 2019:
            return "tt11128736"
        if re_or(title, "^Mujeres sin censura", flags=re.I) and year == 2021:
            return "tt15787982"
        if re_or(title, "^Para profesor vale cualquiera", flags=re.I) and year == 2022:
            return "tt18718108"
        if re_or(title, r"^\¡Upsss 2\! \¿Y ahora dónde está Noé", flags=re.I):
            return "tt12615474"
        if re_or(title, r"^El asombroso Mauricio", flags=re.I) and year == 2022:
            return "tt10473036"
        if re_or(title, r"^Mi pequeño amor", flags=re.I) and year == 2020:
            return "tt12546872"
        if re_or(title, r"^Un cuento de Navidad", flags=re.I) and year == 2008:
            return "tt0993789"
        if re_or(title, r"^Hanna y los monstruos", flags=re.I) and year == 2022:
            return "tt2903136"
        if re_or(title, r"^La buena vida", flags=re.I) and year == 2008:
            return "tt1327798"
        if re_or(title, r"^Alguien que cuide de mí", flags=re.I) and year == 2023:
            return "tt19382276"
        if re_or(title, r"^Bardem, la metamorfosis", flags=re.I) and year in (2023, 2020):
            return "tt31647570"
        if re_or(title, r"^Indomable, Ava Gardner", flags=re.I) and year in (2018, 2016):
            return "tt8610760"
        if re_or(title, r"^Los ángeles exterminados", flags=re.I) and year == 1968:
            return "tt37384074"
        if re_or(title, r"^El traje", flags=re.I) and year == 2002:
            return "tt0340407"
        if re_or(title, r"^Corazón roto. Fuga a Italia", flags=re.I) and year == 2023:
            return "tt33992356"


IMDB = IMDBApi()

if __name__ == "__main__":
    import sys
    r = IMDB.get(sys.argv[1])
    print(r)
