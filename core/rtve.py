from functools import cached_property
from core.web import Web
from requests.exceptions import TooManyRedirects
import json
from core.film import Film
from bs4 import Tag


def _get_id_from_url(prefix: str, url: str):
    if url is None:
        return None
    if not url.startswith(prefix):
        return None
    url = url.rstrip("/")
    id_url = url.split("/")[-1]
    if id_url.isdigit():
        return int(id_url)


class Rtve(Web):
    @cached_property
    def urls(self):
        urls: set[str] = set()
        urls.add("https://www.rtve.es/play/cine/")
        self.get("https://www.rtve.es/play/cine/")
        for a in self.soup.select("div[data-feed^='/play/modulos/']"):
            urls.add("https://www.rtve.es"+a.attrs["data-feed"])
        return tuple(urls)

    def get_films(self, url: str):
        try:
            self.get(url)
        except TooManyRedirects:
            return ()
        films: set[Film] = set()
        for li in self.soup.select("*[data-setup]"):
            js = json.loads(li.attrs["data-setup"])
            if not isinstance(js, dict):
                continue
            idAsset = js.get("idAsset")
            if idAsset is None or js.get("tipo") != "video":
                continue
            a = li.select_one("a[href]")
            img = self.first_select_one(li, "img.poster[data-src]", "img.poster[src]", "img[data-src]", "img[src]")
            idAsset = int(idAsset)
            films.add(Film(
                id=f"rtve{idAsset}",
                name=js['title'],
                url=a.attrs["href"],
                img=img.attrs.get("data-src") or img.attrs.get("src")
            ))
        return tuple(films)

    def first_select_one(self, node: Tag, *args):
        for a in args:
            n = node.select_one(a)
            if n:
                return n

    @cached_property
    def films(self):
        films: set[int] = set()
        for url in self.urls:
            films = films.union(self.get_films(url))
        return tuple(sorted(films))


if __name__ == "__main__":
    r = Rtve()
    x = r.films#r.get_ids("https://www.rtve.es/play/modulos/collection/3557/?skin=rtve-play-tematicas&pos=10&home=true&noLabels=false&distribution=slide")
    print(*x, sep="\n")