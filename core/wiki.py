import requests
from textwrap import dedent
from core.util import dict_walk
from collections import defaultdict
import logging
from typing import NamedTuple, Any
from functools import cache
from os import environ
import re
from time import sleep
from functools import wraps


logger = logging.getLogger(__name__)

PAGE_URL = environ['PAGE_URL']
OWNER_MAIL = environ['OWNER_MAIL']


def retry_until_stable(func):
    def __sort_kv(kv: tuple[Any, int]):
        k, v = kv
        arr = []
        arr.append(int(k is None))
        arr.append(-v)
        return tuple(arr)

    @wraps(func)
    def wrapper(*args, **kwargs):
        count = dict()
        while True:
            value = func(*args, **kwargs)
            count[value] = count.get(value, 1) + 1
            if count[value] > (2 + int(value is None)):
                return sorted(count.items(), key=__sort_kv)[0][0]
            if value is None:
                sleep(0.5 * count[value])
                continue
            sleep(0.1 * count[value])
    return wrapper


class WikiUrl(NamedTuple):
    url: str
    lang_code: str
    lang_label: str

    def to_html(self) -> str:
        cls = ["wiki"]
        title = "Wikipedia"
        if self.lang_label:
            title += f" en {self.lang_label}"
        elif self.lang_code:
            title += f" ({self.lang_code})"
        if self.lang_code:
            cls.append("wiki_"+self.lang_code)
        cls_str = ' '.join(cls)
        html = f'<a class="{cls_str}" href="{self.url}" title="{title}"'
        if self.lang_code:
            html += f' hreflang="{self.lang_code}"'
        html += '>W</a>'
        return html


class WikiInfo(NamedTuple):
    url: str
    country: tuple[str, ...]
    filmaffinity: str | None


class WikiApi:
    def __init__(self):
        self.__s = requests.Session()
        # https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
        self.__s.headers.update({
            "Accept": "application/sparql-results+json",
            'User-Agent': f'CineBoot/0.0 ({PAGE_URL}; {OWNER_MAIL})'
        })

    def query_sparql(self, query: str):
        # https://query.wikidata.org/
        query = dedent(query).strip()
        r = self.__s.get(
            "https://query.wikidata.org/sparql",
            params={"query": query}
        )
        r.raise_for_status()
        return r.json()

    def query_bindings(self, query: str) -> list[dict[str, Any]]:
        data = self.query_sparql(query)
        bindings = dict_walk(data, 'results/bindings', instanceof=list)
        return bindings

    @cache
    @retry_until_stable
    def get_one(self, query: str, instanceof=None):
        if not isinstance(instanceof, (tuple, type(None))):
            instanceof = (instanceof, type(None))
        query = "SELECT ?field WHERE {\n%s\n}\nLIMIT 1" % dedent(query)
        dt = self.query_bindings(query)
        return dict_walk(dt, '0/field/value', instanceof=instanceof)

    @cache
    @retry_until_stable
    def get_label(self, field: str, value: str, lang: str) -> str | None:
        arr = []
        arr.append("SELECT ?fieldLabel WHERE {")
        arr.append("{")
        arr.append(f'   ?field {field} "{value}".')
        arr.append("}")
        arr.append('SERVICE wikibase:label { bd:serviceParam wikibase:language "%s". }' % lang)
        arr.append("}")
        arr.append("LIMIT 1")
        query = "\n".join(arr)
        dt = self.query_bindings(query)
        return dict_walk(dt, '0/fieldLabel/value', instanceof=str)

    @cache
    @retry_until_stable
    def get_tuple(self, query: str, instanceof=None):
        if not isinstance(instanceof, (tuple, type(None))):
            instanceof = (instanceof, type(None))
        query = "SELECT ?field WHERE {\n%s\n}" % dedent(query)
        dt = self.query_bindings(query)
        arr = []
        for x in dt:
            i = dict_walk(x, 'field/value', instanceof=instanceof)
            if i is not None and i not in arr:
                arr.append(i)
        return tuple(arr)

    def query_str(self, query: str) -> str | None:
        return self.get_one(query, instanceof=str)

    def query_int(self, query: str) -> int | None:
        return self.get_one(query, instanceof=int)

    def query_tuple_str(self, query: str) -> tuple[str, ...]:
        return self.get_tuple(query, instanceof=str)

    def query_tuple_int(self, query: str) -> tuple[int, ...]:
        return self.get_tuple(query, instanceof=int)

    @cache
    def __get_json(self, url: str):
        r = self.__s.get(url)
        r.raise_for_status()
        return r.json()

    @cache
    def info_from_imdb(self, imdb_id: str):
        def __sort_kv(kv: tuple[WikiInfo, int]):
            k, v = kv
            arr = []
            arr.append(int(k is None))
            arr.append(int(k is not None and k.url is None))
            arr.append(int(k is not None and k.filmaffinity is None))
            arr.append(-len(k.country) if k else 0)
            arr.append(-v)
            return tuple(arr)

        count = dict()
        while True:
            i = self.__info_from_imdb(imdb_id)
            count[i] = count.get(i, 1) + 1
            if count[i] > (2+int(i is None or i.filmaffinity is None)):
                return sorted(count.items(), key=__sort_kv)[0][0]
            if i is None:
                sleep(0.2*count[i])
                continue
            sleep(0.5*count[i])

    def __info_from_imdb(self, imdb_id: str):
        if imdb_id is None:
            return None
        query = """
            SELECT ?item ?itemLabel ?country ?countryLabel ?filmaffinity ?article WHERE {
              ?item wdt:P345 "%s".
              OPTIONAL {
                ?item wdt:P495 ?country.
              }
              OPTIONAL {
                ?item wdt:P480 ?filmaffinity.
              }
              OPTIONAL {
                ?article schema:about ?item ; schema:isPartOf <https://es.wikipedia.org/> .
              }
              OPTIONAL {
                ?article schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> .
              }
              SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            }
        """ % imdb_id
        bindings = self.query_bindings(query)
        if not bindings:
            return None

        vals: dict[str, Any] = defaultdict(set)
        for b in bindings:
            for f in ('countryLabel/value', 'filmaffinity/value', 'article/value'):
                v = dict_walk(b, f, instanceof=(str, type(None)))
                if isinstance(v, str):
                    v = v.strip()
                if v not in (None, ""):
                    vals[f].add(v)
        for f in ('filmaffinity/value', 'article/value'):
            v: set[str | int] = vals[f]
            if len(v) != 1:
                if len(v) > 1:
                    logger.warning(f"{f} ambiguo para {imdb_id}: {v}")
                vals[f] = None
                continue
            v = v.pop()
            if isinstance(v, str) and v.isdigit():
                v = int(v)
            vals[f] = v
        if vals['article/value'] is None:
            vals['article/value'] = self.query_str(
                """
                ?item wdt:P345 "%s".
                ?field schema:about ?item ; schema:isPartOf ?wikiSite .
                FILTER(STRSTARTS(STR(?wikiSite), "https://"))
                """ % imdb_id
            )
        if vals['filmaffinity/value'] is None:
            vals['filmaffinity/value'] = self.query_int(
                """
                ?item wdt:P345 "%s".
                OPTIONAL { ?item wdt:P480 ?field . }
                """ % imdb_id
            )

        return WikiInfo(
            url=vals['article/value'],
            country=self.__parse_countries(vals['countryLabel/value']),
            filmaffinity=vals['filmaffinity/value']
        )

    def parse_url(self, url: str):
        if url is None:
            return None
        lang = url.split("://", 1)[-1].split(".", 1)[0]
        label = self.get_label("wdt:P424", lang, "es,en")
        return WikiUrl(
            url=url,
            lang_code=lang,
            lang_label=label
        )

    def __parse_countries(self, countries: set[str]):
        arr = []
        for c in countries:
            if c and re.match(r'^Q\d+$', c):
                js = self.__get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{c}.json")
                c = js['entities'][c]['labels']['en']['value']
            if c in ([None, ""]+arr):
                continue
            arr.append(c)
        return tuple(arr)


WIKI = WikiApi()

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python wiki_api.py <imdb_id>")
        sys.exit(1)

    imdb_id = sys.argv[1]
    api = WikiApi()
    result = api.info_from_imdb(imdb_id)
    if result:
        print(result._asdict())
