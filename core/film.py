from typing import NamedTuple
from core.wiki import WikiUrl


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
    lang: tuple[str, ...]
    country: tuple[tuple[str, str], ...]
    description: str
    year: int
    expiration: str
    publication: str
    duration: int
    imdb: IMDb
    wiki: WikiUrl
    filmaffinity: str | None
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]

