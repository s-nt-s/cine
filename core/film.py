from typing import NamedTuple, Optional
from core.wiki import WikiUrl
from core.country import Country
from core.req import R
from functools import cache
import re


def _parse_num(x):
    if not isinstance(x, float):
        return x
    i = int(x)
    return i if i == x else x


class IMDb(NamedTuple):
    id: str
    rate: float
    votes: int

    def to_html(self) -> str:
        title = self.get_title()
        html = f'<a class="imdb" title="{title}" href="https://www.imdb.com/es-es/title/{self.id}">IMDb'
        #if self.rate:
        #    html += f' <span class="imdbRate">{self.rate}</span>'
        html += '</a>'
        return html

    def get_title(self) -> str:
        if self.rate is None:
            return "Ficha IMDb"
        if self.votes:
            return f"Ficha IMDb ({self.rate} sobre 10 en base a {self.votes} votos)"
        return f"Ficha IMDb ({self.rate} sobre 10)"

    def _fix(self):
        slf = self
        if slf.rate == 0:
            slf = slf._replace(rate=None)
        if slf.votes in (0, None):
            slf = slf._replace(votes=None)
            slf = slf._replace(rate=None)
        return slf


class FilmAffinity(NamedTuple):
    id: int
    rate: float = None
    votes: int = None
    reviews: int = None

    @classmethod
    @cache
    def build(cls, id: int):
        if id is None:
            return None
        obj = R.safe_get_json(f"https://s-nt-s.github.io/imdb-sql/filmaffinity/{id}.json")
        if not isinstance(obj, dict):
            return cls(id=id)

        rate = _parse_num(obj.get("rate"))
        votes = _parse_num(obj.get("votes"))
        reviews = _parse_num(obj.get("reviews"))
        return cls(
            id=id,
            rate=rate if (votes or 0, reviews or 0) != (0, 0) else None,
            votes=votes,
            reviews=reviews
        )._fix()

    def to_html(self) -> str:
        title = self.get_title()
        html = f'<a class="filmaffinity" title="{title}" href="https://www.filmaffinity.com/es/film{self.id}.html">FM'
        #if self.rate:
        #    html += f' <span class="filmaffinityRate">{self.rate}</span>'
        html += '</a>'
        return html

    def get_title(self) -> str:
        if self.rate is None:
            return "Ficha FilmAffinity"
        if self.votes:
            if self.reviews in (None, 0):
                return f"Ficha FilmAffinity ({self.rate} sobre 10 en base a {self.votes} votos)"
            return f"Ficha FilmAffinity ({self.rate} sobre 10 en base a {self.votes} votos y {self.reviews} críticas)"
        return f"Ficha FilmAffinity ({self.rate} sobre 10)"

    def _fix(self):
        slf = self
        if slf.rate == 0:
            slf = slf._replace(rate=None)
        if slf.votes in (0, None) and self.reviews in (0, None):
            slf = slf._replace(votes=None)
            slf = slf._replace(rate=None)
            slf = slf._replace(reviews=None)
        return slf


class Film(NamedTuple):
    source: str
    id: int
    url: str
    title: str
    img: str
    audio: tuple[str, ...]
    subtitle: tuple[str, ...]
    country: tuple[Country, ...]
    description: str
    year: int
    expiration: str
    publication: str
    duration: int
    wiki: WikiUrl
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]
    filmaffinity: Optional[FilmAffinity] = None
    imdb: Optional[IMDb] = None
    provider: str = None
    alt: tuple["Film", ...] = tuple()

    def get_provider(self):
        if self.source.lower() == "rtve":
            return "rtve"
        if self.provider is None:
            return self.source
        pr = str(self.provider)
        if not re.search(r"\d", pr) and pr not in ("MSP", "NYX"):
            pr = pr.title().replace(" Un ", " un ")
        if pr == "Zonaa":
            pr = "Zona A"
        if pr == "Acontracorriente":
            pr = "A Contracorriente"
        if pr == "Rita&Luca":
            pr = "Rita & Luca"
        if self.source is None:
            return pr
        if self.source.lower() == pr.lower():
            return self.source
        return f"{self.source} - {pr}"

    def get_score(self):
        if self.filmaffinity and self.filmaffinity.rate is not None:
            return Score(
                source="FilmAffinity",
                votes=self.filmaffinity.votes,
                rate=self.filmaffinity.rate,
                reviews=self.filmaffinity.reviews,
                original=self.filmaffinity.rate,
            )
        if self.imdb and self.imdb.rate is not None:
            return Score(
                source="IMDb",
                votes=self.imdb.votes,
                rate=_parse_num(round(max(0.5, self.imdb.rate-1), 2)),
                original=self.imdb.rate,
            )
        return Score(
                source="none",
                votes=None,
                rate=None,
                original=None,
            )


class Score(NamedTuple):
    source: str
    votes: int
    rate: float
    original: float
    reviews: int = None

    def to_html(self) -> str:
        title = self.get_title()
        if self.rate is None:
            return f'<span title="{title}" class="score score_{self.source.lower()}">⭐ –</span>'
        i = round(self.rate)
        return f'<span title="{title}" class="score score_{self.source.lower()}">⭐ {i}</span>'

    def get_title(self) -> str:
        if self.rate is None:
            return "No hay puntuación disponible"
        if self.reviews in (None, 0):
            return f"{self.original} en {self.source} en base a {self.votes} votos"
        return f"{self.original} en {self.source} en base a {self.votes} votos y {self.reviews} críticas"