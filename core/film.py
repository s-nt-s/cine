from dataclasses import dataclass, asdict


@dataclass(frozen=True, order=True)
class Film:
    id: str
    url: str
    title: str
    img: str

    def merge(self, **kwargs):
        return Film(**{**asdict(self), **kwargs})
