from core.web import buildSoup
from core.cache import StaticCache
from bs4 import BeautifulSoup, Tag
from core.country import CF
import re
from typing import NamedTuple
import cloudscraper
import logging
from datetime import datetime
from functools import cache
from core.cache import DictCache
from core.git import G


logger = logging.getLogger(__name__)

re_sp = re.compile(r"\s+")

FM_SCRAPER = cloudscraper.create_scraper()


class FilmAffinityError(ValueError):
    pass


@cache
def _get_html(id: int):
    url = f"https://www.filmaffinity.com/es/film{id}.html"
    soup = buildSoup(url, FM_SCRAPER.get(url).text)
    title_none = "not title found"
    txt = get_text(soup.select_one("title")) or title_none
    if txt.lower() in (title_none, "too many request", ):
        raise FilmAffinityError(txt)
    return str(soup)


def get_text(n: Tag | None) -> str | None:
    if not isinstance(n, Tag):
        return None
    txt = re_sp.sub(" ", n.get_text()).strip()
    if len(txt) == 0:
        return None
    return txt


class FilmAffinity(NamedTuple):
    id: int
    title: str
    year: int
    url: str
    reviews: int
    votes: int
    country: str
    genres: tuple[str, ...]
    poster: str = None
    rate: float = None


class FilmAffinityApi:
    ACTIVE = True

    @cache
    def get(self, id: int):
        obj = self.__get(id)
        if not isinstance(obj, dict):
            return None
        poster = obj.get('poster')
        if poster in ("https://www.filmaffinity.com/images/noimglg.jpg", ):
            poster = None
        return FilmAffinity(
            id=id,
            title=obj.get('title'),
            year=obj.get('year'),
            url=obj.get('url'),
            rate=obj.get('rate'),
            votes=obj.get('votes'),
            reviews=obj.get('reviews'),
            country=obj.get('country') or tuple(),
            genres=obj.get('genres') or tuple(),
            poster=poster
        )

    @DictCache(
        "out/filmaffinity/{}.json",
        mirror=(
            "https://s-nt-s.github.io/imdb-sql/filmaffinity/",
            f"{G.page}/filmaffinity/"
        ),
        maxOld=90
    )
    def __get(self, id: int):
        if not FilmAffinityApi.ACTIVE or id is None:
            return None
        try:
            api = FilmAffinityScraper(int(id))
            return dict(
                id=api.id,
                title=api.get_title(),
                year=api.get_year(),
                url=api.url,
                rate=api.get_rate(),
                votes=api.get_votes(),
                reviews=api.get_reviews(),
                country=api.get_country(),
                genres=api.get_genres(),
                poster=api.get_poster()
            )
        except FilmAffinityError as e:
            logger.critical(f"Error fetching film {id}: {e}")
            FilmAffinityApi.ACTIVE = False
            return None


class FilmAffinityScraper:
    def __init__(self, id: int):
        self.__id = id
        html = _get_html(id)
        self.__soup = BeautifulSoup(html, "html.parser")

    @property
    def id(self) -> int:
        return self.__id

    @property
    def url(self) -> str:
        return f"https://www.filmaffinity.com/es/film{self.id}.html"

    def __get_attr(self, slc: str, attr: str) -> str | None:
        n = self.__soup.select_one(slc)
        if n is not None:
            val = re_sp.sub(" ", n.attrs.get(attr) or '')
            if len(val):
                return val
        logger.critical(f"Valor no encontrado: {slc}[{attr}] {self.url}")

    def get_poster(self) -> str:
        return self.__get_attr("#movie-main-image-container img, #main-poster img", "src")

    def get_title(self) -> str:
        return get_text(self.__soup.select_one("h1 span[itemprop='name']"))

    def get_year(self) -> str:
        y = get_text(self.__soup.select_one("dd[itemprop='datePublished'], span[itemprop='datePublished']"))
        if y and y.isdecimal():
            return int(y)

    def get_country(self) -> str | None:
        slc = "dl.movie-info span#country-img img, dl img.nflag"
        src = self.__get_attr(slc, "src")
        alt = self.__get_attr(slc, "alt")
        if src is not None:
            cod = src.split("/")[-1].split(".")[0]
            alpha3 = CF.parse_alpha3(cod, silent=True)
            if alpha3:
                return alpha3
        if isinstance(alt, str):
            alpha3 = CF.to_alpha_3(alt, silent=True)
            if alpha3:
                return alpha3
        logger.critical(f"Código alpha3 de país no encontrado: cod={cod} alt={alt} {self.url}")

    def get_rate(self) -> float | None:
        return self.__get_itemprop("ratingValue", to=float)

    def get_votes(self) -> int:
        v = self.__get_itemprop("ratingCount", to=int)
        if v is None:
            return 0
        return v

    def get_reviews(self) -> int | None:
        txt_reviews = get_text(self.__soup.select_one("#movie-reviews-box"))
        if not isinstance(txt_reviews, str) or not re.match(r"^\d+\s+.*$", txt_reviews):
            return 0
        return int(txt_reviews.split()[0])

    def get_genres(self):
        arr: list[str] = []
        for g in map(get_text, self.__soup.select(f'dd.card-genres a')):
            if g and g not in arr:
                arr.append(g)
        if len(arr) == 0:
            return None
        return tuple(arr)

    def __get_itemprop(self, name: str, to: type):
        n = self.__soup.select_one(f'*[itemprop="{name}"][content]')
        if n is None:
            return None
        c = n.attrs.get('content')
        if c is None:
            return None
        if isinstance(c, str):
            c = re_sp.sub(" ", c).strip()
            if len(c) == 0:
                return None
        return to(c) if to else c


FilmM = FilmAffinityApi()

if __name__ == "__main__":
    import sys
    from core.log import config_log
    config_log("log/filmaffinity.log")

    for film in map(FilmM.get, sys.argv[1:]):
        if film:
            print(film)
