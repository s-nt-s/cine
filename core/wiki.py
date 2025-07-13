import requests
from textwrap import dedent
from core.util import dict_walk
from collections import defaultdict
import logging
from typing import NamedTuple, Any
from functools import cache
from os import environ

logger = logging.getLogger(__name__)

PAGE_URL = environ['PAGE_URL']
OWNER_MAIL = environ['OWNER_MAIL']


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
        endpoint = "https://query.wikidata.org/sparql"

        r = self.__s.get(endpoint, params={"query": query})
        r.raise_for_status()
        return r.json()

    @cache
    def info_from_imdb(self, imdb_id: str):
        if imdb_id is None:
            return None
        query = dedent("""
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
        """).strip() % imdb_id
        js = self.query_sparql(query)
        bindings = dict_walk(js, 'results/bindings', instanceof=(list, type(None)))
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

        return WikiInfo(
            url=vals['article/value'],
            country=tuple(vals['countryLabel/value']),
            filmaffinity=vals['filmaffinity/value']
        )


WIKI = WikiApi()

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Uso: python wiki_api.py <imdb_id>")
        sys.exit(1)

    imdb_id = sys.argv[1]
    api = WikiApi()
    result = api.info_from_imdb(imdb_id)
    print(result._asdict())
