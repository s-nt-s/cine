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

logger = logging.getLogger(__name__)

PAGE_URL = environ['PAGE_URL']
OWNER_MAIL = environ['OWNER_MAIL']


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
        r = self.__s.get(
            "https://query.wikidata.org/sparql",
            params={"query": dedent(query).strip()}
        )
        r.raise_for_status()
        return r.json()

    def query_bindings(self, query: str) -> list[dict[str, Any]]:
        data = self.query_sparql(query)
        bindings = dict_walk(data, 'results/bindings', instanceof=list)
        return bindings

    @cache
    def query_str(self, path: str, query: str) -> list[dict[str, Any]]:
        count = dict()
        while True:
            dt = self.query_bindings(query)
            i = dict_walk(dt, path, instanceof=(str, type(None)))
            count[i] = count.get(i, 1) + 1
            if count[i] > 2:
                return i
            if i is None:
                sleep(0.2)
                continue
            sleep(0.1)

    @cache
    def __get_json(self, url: str):
        r = self.__s.get(url)
        r.raise_for_status()
        return r.json()

    @cache
    def info_from_imdb(self, imdb_id: str):
        count = dict()
        while True:
            i = self.__info_from_imdb(imdb_id)
            count[i] = count.get(i, 1) + 1
            if count[i] > 2:
                return i
            if i is None:
                sleep(0.2)
                continue
            if i.filmaffinity:
                return i
            sleep(0.5)

    def __info_from_imdb(self, imdb_id: str):
        if imdb_id is None:
            return None
        query = """
            SELECT ?item ?itemLabel ?country ?countryLabel ?filmaffinity ?article WHERE {
              ?item wdt:P345 "%s".     # IMDb ID
              OPTIONAL {
                ?item wdt:P495 ?country.       # País/es de origen o producción
              }
              OPTIONAL {
                ?item wdt:P480 ?filmaffinity. # URL FilmAffinity
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
            v = vals[f]
            if len(v) != 1:
                if len(v) > 1:
                    logger.warning(f"{f} ambiguo para {imdb_id}: {v}")
                vals[f] = None
                continue
            v = v.pop()
            if isinstance(v, str) and v.isdigit():
                v = int(v)
            vals[f] = v
        url = vals['article/value']
        if url is None:
            url = self.query_str(
                '0/article/value',
                """
                SELECT ?article WHERE {
                    ?item wdt:P345 "%s".
                    ?article schema:about ?item ; schema:isPartOf ?wikiSite .
                    FILTER(STRSTARTS(STR(?wikiSite), "https://"))
                }
                LIMIT 1
                """ % imdb_id
            )
        return WikiInfo(
            url=url,
            country=self.__parse_countries(vals['countryLabel/value']),
            filmaffinity=vals['filmaffinity/value']
        )

    def parse_url(self, url: str):
        if url is None:
            return None
        lang = url.split("://", 1)[-1].split(".", 1)[0]
        label = self.query_str(
            '0/langItemLabel/value',
            """
            SELECT ?langItem ?langItemLabel WHERE {
            {
                ?langItem wdt:P424 "%s".
            }
            SERVICE wikibase:label { bd:serviceParam wikibase:language "es,en". }
            }
            LIMIT 1
            """ % lang
        )
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
            if c in (None, ""):
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
