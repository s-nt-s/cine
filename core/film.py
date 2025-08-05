from typing import NamedTuple, Optional
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
    wiki: WikiUrl
    filmaffinity: str | None
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]
    imdb: Optional[IMDb] = None
    provider: str = None

    def get_provider(self):
        if self.source.lower() == "rtve":
            return "rtve"
        if self.provider is None:
            return self.source
        if self.source is None:
            return self.provider
        if self.source.lower() == self.provider.lower():
            return self.provider
        return f"{self.source} - {self.provider}"