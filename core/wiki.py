import requests
from textwrap import dedent
from core.util import dict_walk
import logging
from typing import NamedTuple, Any
from functools import cache
from os import environ
import re
from time import sleep
from functools import wraps
from requests import JSONDecodeError


logger = logging.getLogger(__name__)

PAGE_URL = environ['PAGE_URL']
OWNER_MAIL = environ['OWNER_MAIL']


def _is_empty(x: Any):
    if x is None:
        return True
    if isinstance(x, (dict, list, tuple, set, str)):
        return len(x) == 0
    return False


def retry_until_stable(func):
    def __sort_kv(kv: tuple[Any, int]):
        k, v = kv
        arr = []
        arr.append(int(k is None))
        arr.append(-len(k) if isinstance(k, tuple) else 0)
        arr.append(-v)
        return tuple(arr)

    @wraps(func)
    def wrapper(*args, **kwargs):
        count = dict()
        while True:
            value = func(*args, **kwargs)
            count[value] = count.get(value, 1) + 1
            if count[value] > (2 + int(_is_empty(value))):
                return sorted(count.items(), key=__sort_kv)[0][0]
            if value is None:
                sleep(0.5 * count[value])
                continue
            sleep(0.1 * count[value])
    return wrapper


def log_if_empty(method):
    @wraps(method)
    def wrapper(self: "WikiApi", *args, **kwargs):
        val = method(self, *args, **kwargs)
        if _is_empty(val):
            logger.debug("Empty query:\n"+self.last_query)
        return val
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


class WikiApi:
    def __init__(self):
        self.__s = requests.Session()
        # https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
        self.__s.headers.update({
            "Accept": "application/sparql-results+json",
            'User-Agent': f'CineBoot/0.0 ({PAGE_URL}; {OWNER_MAIL})'
        })
        self.__last_query: str | None = None

    @property
    def last_query(self):
        return self.__last_query

    def query_sparql(self, query: str):
        # https://query.wikidata.org/
        query = dedent(query).strip()
        query = re.sub(r"\n(\s*\n)+", "\n", query)
        self.__last_query = query
        r = self.__s.get(
            "https://query.wikidata.org/sparql",
            params={"query": query}
        )
        try:
            r.raise_for_status()
        except Exception:
            logger.critical(f"Error ({r.status_code}) querying:\n"+query)
            raise
        try:
            return r.json()
        except JSONDecodeError:
            logger.critical("Error (no JSON format) querying:\n"+query)
            raise

    def query_bindings(self, query: str) -> list[dict[str, Any]]:
        data = self.query_sparql(query)
        bindings = dict_walk(data, 'results/bindings', instanceof=list)
        return bindings

    @cache
    @log_if_empty
    @retry_until_stable
    def get_one(self, query: str, instanceof=None, order_by: str = None):
        if not isinstance(instanceof, (tuple, type(None))):
            instanceof = (instanceof, type(None))
        full_query = "SELECT ?field WHERE {\n"+dedent(query)+"\n}"
        if order_by:
            full_query += f"\nORDER BY ?{order_by} STR(?field)"
        dt = self.query_bindings(full_query+"\nLIMIT 1")
        if dt:
            return dict_walk(dt, '0/field/value', instanceof=instanceof)

    @cache
    @log_if_empty
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
        if dt:
            return dict_walk(dt, '0/fieldLabel/value', instanceof=str)

    @cache
    @log_if_empty
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

    def query_str(self, query: str, order_by: str = None) -> str | None:
        return self.get_one(query, instanceof=str, order_by=order_by)

    def query_int(self, query: str, order_by: str = None) -> int | None:
        return self.get_one(query, instanceof=int, order_by=order_by)

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
    def get_filmaffinity_from_imdb(self, imdb_id: str):
        return self.query_int(
            """
            ?item wdt:P345 "%s".
            OPTIONAL { ?item wdt:P480 ?field . }
            """ % imdb_id
        )

    @cache
    def get_wiki_url_from_imdb(self, imdb_id: str):
        return self.query_str(
            """
            ?item wdt:P345 "%s".
            ?field schema:about ?item ; schema:isPartOf ?wikiSite .
            FILTER(STRSTARTS(STR(?wikiSite), "https://"))

            BIND(REPLACE(STR(?wikiSite), "https://", "") AS ?domain)
            BIND(STRBEFORE(?domain, ".wikipedia.org") AS ?lang)

            OPTIONAL {
                VALUES (?prioLang ?priority) {
                ("es" 1)
                ("en" 2)
                ("ca" 3)
                ("gl" 4)
                ("it" 5)
                ("fr" 6)
                }
                FILTER(?lang = ?prioLang)
            }

            BIND(COALESCE(?priority, 99) AS ?langPriority)
            """ % imdb_id,
            order_by="langPriority"
        )

    @cache
    @retry_until_stable
    def get_countries_from_imdb(self, imdb_id: str):
        query = """
            SELECT ?country ?countryLabel WHERE {
              ?item wdt:P345 "%s".
              OPTIONAL {
                ?item wdt:P495 ?country.
              }
              SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
            }
        """ % imdb_id
        countries: list[str] = []
        bindings = self.query_bindings(query)
        for b in bindings:
            c = dict_walk(b, 'countryLabel/value', instanceof=(str, type(None)))
            if not isinstance(c, str):
                continue
            c = c.strip()
            if c and re.match(r'^Q\d+$', c):
                js = self.__get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{c}.json")
                c = js['entities'][c]['labels']['en']['value']
            if c and c not in countries:
                countries.append(c)
        return tuple(countries)

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
