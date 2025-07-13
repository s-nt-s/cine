from typing import NamedTuple


class Film(NamedTuple):
    source: str
    id: int
    url: str
    title: str
    img: str
    program: str
    lang: str
    country: tuple[tuple[str, str], ...]
    description: str
    year: int
    expiration: str
    publication: str
    duration: int
    imdbId: str
    imdbRate: float
    imdbVotes: int
    wiki: str
    filmaffinity: str | None
    director: tuple[str, ...]
    casting: tuple[str, ...]
    genres: tuple[str, ...]
