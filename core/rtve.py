from functools import cached_property
from core.web import Web
from requests.exceptions import TooManyRedirects
import json
from core.film import Film
from collections import defaultdict


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
            # info = json.loads(self.soup.select_one(f'[data-idasset="{idAsset}"][data-share]').attrs["data-share"])
            a = li.select_one("a[href]")
            img = li.select_one("img[data-src*=vertical]")
            idAsset = int(idAsset)
            films.add(Film(
                id=f"rtve{idAsset}",
                title=js['title'],
                url=a.attrs["href"],
                img=img.attrs["data-src"] if img else None
            ))
        return tuple(films)

    @cached_property
    def films(self):
        dct_films: dict[Film, set[str]] = defaultdict(set)
        for url in self.urls:
            for f in self.get_films(url):
                dct_films[f.merge(img=None)].add(f.img)
        films: set[Film] = set()
        for f, imgs in dct_films.items():
            if len(imgs) > 1 and None in imgs:
                imgs.remove(None)
            films.add(f.merge(img=imgs.pop() or "#"))
        return tuple(sorted(films))


if __name__ == "__main__":
    r = Rtve()
    x = r.films#r.get_ids("https://www.rtve.es/play/modulos/collection/3557/?skin=rtve-play-tematicas&pos=10&home=true&noLabels=false&distribution=slide")
    print(*x, sep="\n")