from textwrap import dedent
import logging
from typing import Any, NamedTuple
from functools import cache
import re
from time import sleep
from functools import wraps
from core.git import G
from core.req import R
from collections import defaultdict
from urllib.parse import urlencode
from datetime import datetime, timedelta
from core.util import iter_chunk
from urllib.error import HTTPError


logger = logging.getLogger(__name__)
re_sp = re.compile(r"\s+")
LANGS = ('es', 'en', 'ca', 'gl', 'it', 'fr')


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



class WikiError(Exception):
    def __init__(self, msg: str, query: str, http_code: int):
        super().__init__(f"{msg}\n{query}")
        self.__query = query
        self.__msg = msg
        self.__http_code = http_code

    @property
    def msg(self):
        return self.__msg

    @property
    def http_code(self):
        return self.__http_code

    @property
    def query(self):
        return self.__query


def retry_fetch(chunk_size=5000):
    def decorator(func):

        @wraps(func)
        def wrapper(self: "WikiApi", *args, **kwargs):
            if len(args) == 0:
                return {}
            args = sorted(set(args))

            def _log_line(rgs: tuple, kw: dict, ck: int):
                rgs = sorted(set(rgs))
                line = ", ".join(
                    [f"{len(rgs)} ids [{rgs[0]} - {rgs[-1]}]"] +
                    [f"{k}={v}" for k, v in kw.items()] +
                    [f"chunk_size={ck}"]
                )
                return f"{func.__name__}({line})"

            error_query = {}
            result = dict()
            ko = set(args)
            count = 0
            tries = 0
            until = datetime.now() + timedelta(seconds=60*5)
            cur_chunk_size = int(chunk_size)
            while ko and (tries == 0 or (datetime.now() < until and tries < 3)):
                error_query = {}
                tries = tries + 1
                if tries > 1:
                    cur_chunk_size = cur_chunk_size // 3
                    sleep(5)
                logger.info(_log_line(ko, kwargs, cur_chunk_size))
                for chunk in iter_chunk(cur_chunk_size, list(ko)):
                    count += 1
                    fetched: dict = None
                    try:
                        fetched = func(self, *chunk, **kwargs) or {}
                        fetched = {k: v for k, v in fetched.items() if v}
                    except WikiError as e:
                        logger.warning(f"└ [KO] {e.msg}")
                        if e.http_code == 429:
                            sleep(60)
                        elif e.http_code is not None:
                            last_error = error_query.get(e.http_code)
                            if last_error is None or len(last_error) > len(e.query):
                                error_query[e.http_code] = str(e.query)
                    if not fetched:
                        continue
                    for k, v in fetched.items():
                        ko.remove(k)
                        result[k] = v
                    logger.debug(f"└ [{count}] [{chunk[0]} - {chunk[-1]}] = {len(fetched)} items")

            logger.info(f"{_log_line(args, kwargs, chunk_size)} = {len(result)} items")
            for c, q in error_query.items():
                logger.debug(f"STATUS_CODE {c} for:\n{q}")
            return result

        return wrapper
    return decorator


class WikiApi:
    def __init__(self):
        # https://foundation.wikimedia.org/wiki/Policy:Wikimedia_Foundation_User-Agent_Policy
        self.__headers = {
            'User-Agent': f'ImdbBoot/0.0 ({G.remote}; {G.mail})',
            'Content-Type': 'application/x-www-form-urlencoded',
            "Accept": "application/sparql-results+json"
        }
        self.__last_query: str | None = None

    @property
    def last_query(self):
        return self.__last_query

    def query_sparql(self, query: str) -> dict:
        # https://query.wikidata.org/
        query = dedent(query).strip()
        query = re.sub(r"\n(\s*\n)+", "\n", query)
        self.__last_query = query
        query = re_sp.sub(" ", query)
        data = urlencode({"query": query}).encode('utf-8')
        try:
            return R.get_json(
                "https://query.wikidata.org/sparql",
                headers=self.__headers,
                data=data,
                wait_if_status={429: 60}
            )
        except Exception as e:
            code = e.code if isinstance(e, HTTPError) else None
            raise WikiError(str(e), self.__last_query, http_code=code) from e

    def query(self, query: str) -> list[dict[str, Any]]:
        data = self.query_sparql(query)
        if not isinstance(data, dict):
            raise WikiError(str(data), self.__last_query)
        result = data.get('results')
        if not isinstance(result, dict):
            raise WikiError(str(data), self.__last_query)
        bindings = result.get('bindings')
        if not isinstance(bindings, list):
            raise WikiError(str(data), self.__last_query)
        for i in bindings:
            if not isinstance(i, dict):
                raise WikiError(str(data), self.__last_query)
            if i.get('subject') and i.get('object'):
                raise WikiError(str(data), self.__last_query)
        return bindings

    def get_filmaffinity(self, *args):
        r: dict[str, int] = dict()
        for k, v in self.get_dict(
            *args,
            key_field='wdt:P345',
            val_field='wdt:P480'
        ).items():
            if len(v) == 1:
                r[k] = v[0]
        return r

    def get_director(self, *args):
        r: dict[str, tuple[str, ...]] = dict()
        for k, v in self.get_dict(
            *args,
            key_field='wdt:P345',
            val_field='wdt:P345',
            by_field='wdt:P57'
        ).items():
            if len(v):
                r[k] = tuple(sorted(v))
        return r

    def get_names(self, *args: str) -> dict[str, str]:
        obj = {}
        for k, v in self.get_label_dict(*args, key_field='wdt:P345').items():
            if len(v) == 1:
                obj[k] = v.pop()
        return obj

    @cache
    @retry_fetch(chunk_size=5000)
    def get_label_dict(self, *args, key_field: str = None, lang: tuple[str] = None) -> dict[str, list[str | int]]:
        if len(args) == 0:
            return {}

        if not lang:
            lang = LANGS

        values = " ".join(f'"{x}"' for x in args)

        lang_priority = {lg: i for i, lg in enumerate(lang, start=1)}
        lang_filter = ", ".join(f'"{lg}"' for lg in lang_priority)

        lang_case = " ".join(
            f'IF(LANG(?v) = "{lg}", {p},' for lg, p in lang_priority.items()
        ) + f"{(len(lang_priority) + 1)})" * len(lang_priority)

        query = dedent("""
            SELECT ?k ?v WHERE {
                VALUES ?k { %s }
                ?item %s ?k ;
                    rdfs:label ?v .
                FILTER(LANG(?v) IN (%s))

                {
                SELECT ?k (MIN(?pri) AS ?minPri) WHERE {
                    VALUES ?k { %s }
                    ?item %s ?k ;
                        rdfs:label ?v .
                    FILTER(LANG(?v) IN (%s))
                    BIND(%s AS ?pri)
                }
                GROUP BY ?k
                }

                BIND(%s AS ?pri)
                FILTER(?pri = ?minPri)
            }
        """).strip() % (
            values,
            key_field,
            lang_filter,
            values,
            key_field,
            lang_filter,
            lang_case,
            lang_case,
        )
        r = defaultdict(set)
        for i in self.query(query):
            k = i['k']['value']
            v = i.get('v', {}).get('value')
            if isinstance(v, str):
                v = v.strip()
            if v is None or (isinstance(v, str) and len(v) == 0):
                continue
            if v.isdigit():
                v = int(v)
            r[k].add(v)
        r = {k: list(v) for k, v in r.items()}
        return r

    @cache
    @retry_fetch(chunk_size=5000)
    def get_dict(self, *args, key_field: str = None, val_field: str = None, by_field: str = None) -> dict[str, list[str | int]]:
        if len(args) == 0:
            return {}
        ids = " ".join(map(lambda x: f'"{x}"', args))
        if by_field:
            query = dedent('''
                SELECT ?k ?v WHERE {
                    VALUES ?k { %s }
                    ?item %s ?k ;
                          %s ?b .
                       ?b %s ?v .
                }
            ''').strip() % (
                ids,
                key_field,
                by_field,
                val_field,
            )
        else:
            query = dedent('''
                SELECT ?k ?v WHERE {
                    VALUES ?k { %s }
                    ?item %s ?k.
                    ?item %s ?v.
                }
            ''').strip() % (
                ids,
                key_field,
                val_field,
            )
        r = defaultdict(set)
        for i in self.query(query):
            k = i['k']['value']
            v = i.get('v', {}).get('value')
            if isinstance(v, str):
                v = v.strip()
            if v is None or (isinstance(v, str) and len(v) == 0):
                continue
            if v.isdigit():
                v = int(v)
            r[k].add(v)
        r = {k: list(v) for k, v in r.items()}
        return r

    @cache
    @retry_fetch(chunk_size=500)
    def get_countries(self, *args: str) -> dict[str, str]:
        r = defaultdict(set)
        ids = " ".join(f'"{x}"' for x in args)
        query = """
        SELECT ?imdb ?alpha3 WHERE {
            VALUES ?imdb { %s }
            ?item wdt:P345 ?imdb ;
                wdt:P495 ?country .
            ?country wdt:P298 ?alpha3 .
        }
        """ % ids
        for row in self.query(query):
            imdb = row["imdb"]["value"]
            alpha3 = row.get("alpha3", {}).get("value")
            if alpha3:
                r[imdb].add(alpha3)
        obj: dict[str, str] = dict()
        for k, v in r.items():
            if v:
                obj[k] = " ".join(sorted(v))
        return obj

    @cache
    @retry_fetch(chunk_size=5000)
    def get_wiki_url(self, *args):
        if len(args) == 0:
            return {}
        ids = " ".join(map(lambda x: f'"{x}"', args))
        order = []
        for i, lang in enumerate(LANGS, start=1):
            order.append(f'IF(CONTAINS(STR(?site), "://{lang}.wikipedia.org"), {i},')
        len_order = len(order)
        order.append(f"{len_order}" + (')' * len_order))
        order_str = " ".join(order)

        bindings = self.query(
            """
                SELECT ?imdb ?article WHERE {
                VALUES ?imdb { %s }

                ?item wdt:P345 ?imdb .
                ?article schema:about ?item ;
                        schema:isPartOf ?site .

                FILTER(CONTAINS(STR(?site), "wikipedia.org"))

                BIND(
                    %s
                    AS ?priority
                )

                {
                    SELECT ?imdb (MIN(?priority) AS ?minPriority) WHERE {
                    VALUES ?imdb { %s }
                    ?item wdt:P345 ?imdb .
                    ?article schema:about ?item ;
                            schema:isPartOf ?site .
                    FILTER(CONTAINS(STR(?site), "wikipedia.org"))
                    BIND(
                        %s
                        AS ?priority
                    )
                    }
                    GROUP BY ?imdb
                }

                FILTER(?priority = ?minPriority)
                }
                ORDER BY ?imdb
            """ % (ids, order_str, ids, order_str)
        )
        obj: dict[str, set[str]] = defaultdict(set)
        for i in bindings:
            k = i['imdb']['value']
            v = i.get('article', {}).get('value')
            if isinstance(v, str):
                v = v.strip()
            if v is None or (isinstance(v, str) and len(v) == 0):
                continue
            obj[k].add(v)
        obj = {k: v.pop() for k, v in obj.items() if len(v) == 1}
        return obj

    @cache
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
        dt = self.query(query)
        if isinstance(dt, list):
            obj = dt[0]
            if isinstance(obj, dict):
                obj = obj.get('fieldLabel')
                if isinstance(obj, dict):
                    return obj.get('value')

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
