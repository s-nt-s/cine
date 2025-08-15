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
        html = f' <a class="imdb" title="{title}"href="https://www.imdb.com/es-es/title/{self.id}">IMDb'
        if self.rate:
            html += ' <span class="imdbRate"'
            if self.votes:
                html += f' en base a {self.votes} votos'
            html += f'">{self.rate}</span>'
        html += '</a>'
        return html

    def get_title(self) -> str:
        if self.rate is None:
            return "Ficha IMDb"
        if self.votes:
            return f"Ficha IMDb ({self.rate} sobre 10 en base a {self.votes} votos)"
        return f"Ficha IMDb ({self.rate} sobre 10)"


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
    filmaffinity: str | None
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]
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
        if self.source is None:
            return pr
        if self.source.lower() == pr.lower():
            return self.source
        return f"{self.source} - {pr}"
