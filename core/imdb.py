from requests import Session
from os import environ
import logging
from core.util import tp_split, mapdict, dict_walk, dict_walk_tuple, dict_walk_positive
from functools import cache
import re
from core.web import buildSoup, get_text, WEB, find_by_text
from core.wiki import WIKI
from typing import NamedTuple, Optional
from core.dblite import DB, dict_factory, gW
from core.country import to_alpha_3


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
    duration: Optional[int] = None


class IMDBApi:
    def __init__(self):
        key = environ['OMDBAPI_KEY']
        self.__omdbapi = f"http://www.omdbapi.com/?apikey={key}&i="
        self.__imdb = "https://www.imdb.com/es-es/title/"
        self.__omdbapi_activate = True
        self.__s = Session()

    @cache
    def __get_from_omdbapi(self, id: str):
        r = self.__s.get(self.__omdbapi+id)
        js = r.json()
        return js

    def get(self, *ids: str):
        obj: dict[str, IMDBInfo] = dict()
        for row in DB.select(f'''
            select
                  m.id,
                  m.type,
                  m.year,
                  m.duration,
                  m.rating,
                  m.votes,
                  e.filmaffinity,
                  e.wikipedia,
                  e.countries
            from
                  movie m left join extra e on e.movie=m.id
            where
                  id {gW(ids)}
        ''', *ids, row_factory=dict_factory):
            obj[row['id']] = IMDBInfo(
                id=row['id'],
                title=None,
                director=None,
                actor=None,
                rating=row['rating'],
                votes=row['votes'],
                year=row['year'],
                countries=tp_split(" ", row['countries']),
                wiki=row['wikipedia'],
                duration=row['duration'],
                awards=None,
                typ=row['type'],
                genres=tuple(),
                img=None,
                filmaffinity=row['filmaffinity']
            )
        countries: dict[str, tuple] = dict()
        need_info = set(ids).difference(obj.keys())
        for v in obj.values():
            if not v.countries:
                need_info.add(v.id)
        for i in sorted(need_info):
            data = self.__get_basic(i)
            countries[i] = to_alpha_3(dict_walk(data, 'Country', instanceof=(list, type(None))))
            if i in obj:
                continue
            obj[i] = IMDBInfo(
                id=i,
                title=dict_walk(data, 'Title', instanceof=(str, type(None))),
                director=dict_walk_tuple(data, 'Director'),
                actor=dict_walk_tuple(data, 'Actors'),
                rating=dict_walk_positive(data, 'imdbRating'),
                votes=dict_walk_positive(data, 'imdbVotes'),
                year=dict_walk_positive(data, 'Year'),
                awards=dict_walk(data, 'Awards', instanceof=(str, type(None))),
                typ=dict_walk(data, 'Type', instanceof=(str, type(None))),
                genres=dict_walk_tuple(data, 'Genre'),
                img=dict_walk(data, 'Poster', instanceof=(str, type(None))),
                countries=None,
                wiki=None,
                filmaffinity=None,
            )
        need_countries = []
        need_wikipedia = []
        need_filmaffinity = []
        for i in obj.values():
            if i.filmaffinity is None:
                need_filmaffinity.append(i.id)
            if i.wiki is None:
                need_wikipedia.append(i.id)
            if not i.countries:
                need_countries.append(i.id)
        for k, v in WIKI.get_wiki_url(*need_wikipedia).items():
            obj[k] = obj[k]._replace(wiki=v)
        for k, v in WIKI.get_filmaffinity(*need_filmaffinity).items():
            obj[k] = obj[k]._replace(filmaffinity=v)
        for k, c2 in WIKI.get_countries(*need_countries).items():
            c1 = countries.get(i)
            obj[k] = obj[k]._replace(countries=self.__merge(c1, tp_split(" ", c2)))
        for k, c1 in countries.items():
            if not obj[k].countries:
                obj[k] = obj[k]._replace(countries=c1)
        return obj

    def __merge(self, countries1: tuple[str, ...], countries2: tuple[str, ...]):
        if not countries1:
            return countries2 or tuple()
        if not countries2:
            return countries1 or tuple()
        merge = tuple(set(countries1).intersection(countries2))
        if not merge:
            return countries2 or tuple()
        return merge

    @cache
    def __get_basic(self, id: str):
        if self.__omdbapi_activate is False or id in (None, ""):
            return None
        if not isinstance(id, str):
            raise ValueError(id)
        js = self.__get_from_omdbapi(id)
        js = mapdict(_clean_js, js, compact=True)
        isError = js.get("Error")
        response = js.get("Response")
        if isError:
            logger.warning(f"IMDBApi: {id} = {js['Error']}")
            if js['Error'] == "Request limit reached!":
                self.__omdbapi_activate = False
        elif response is not True:
            logger.warning(f"IMDBApi: {id} Response = {response}")
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
        for k in ('Response', ):
            if k in js:
                del js[k]
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

    @cache
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
            js['Type'] = 'tvEpisode'
        if find_by_text(soup, "li", "Película de TV"):
            js['Type'] = 'tvMovie'

        js = {k: v for k, v in js.items() if v is not None}
        if len(js) == 0:
            return None
        return js

    def __get_html(self, url):
        soup = WEB.get_cached_soup(url)
        return str(soup)


IMDB = IMDBApi()

if __name__ == "__main__":
    import sys
    r = IMDB.get(sys.argv[1])
    print(*r.values(), end="\n")
