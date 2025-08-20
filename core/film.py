from typing import NamedTuple, Optional
from core.wiki import WikiUrl
from core.country import Country
import re


class IMDb(NamedTuple):
    id: str
    rate: float
    votes: int

    def to_html(self) -> str:
        title = self.get_title()
        html = f'<a class="imdb" title="{title}" href="https://www.imdb.com/es-es/title/{self.id}">IMDb'
        if self.rate:
            html += f' <span class="imdbRate">{self.rate}</span>'
        html += '</a>'
        return html

    def get_title(self) -> str:
        if self.rate is None:
            return "Ficha IMDb"
        if self.votes:
            return f"Ficha IMDb ({self.rate} sobre 10 en base a {self.votes} votos)"
        return f"Ficha IMDb ({self.rate} sobre 10)"


class FilmAffinity(NamedTuple):
    id: int
    rate: float
    votes: int
    reviews: int

    def to_html(self) -> str:
        title = self.get_title()
        html = f'<a class="filmaffinity" title="{title}" href="https://www.filmaffinity.com/es/film{self.id}.html">FM'
        if self.rate:
            html += f' <span class="filmaffinityRate">{self.rate}</span>'
        html += '</a>'
        return html

    def get_title(self) -> str:
        if self.rate is None:
            return "Ficha FilmAffinity"
        if self.votes and self.reviews is None:
            return f"Ficha FilmAffinity ({self.rate} sobre 10 en base a {self.votes} votos)"
        if self.votes and self.reviews is not None:
            return f"Ficha FilmAffinity ({self.rate} sobre 10 en base a {self.votes} votos y {self.reviews} críticas)"
        return f"Ficha FilmAffinity ({self.rate} sobre 10)"


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
