from typing import Any
from core.cache import Cache
from core.util import mapdict
import requests


def _clean_js(k: str, obj: list | dict | str):
    if isinstance(obj, str):
        obj = obj.strip()
        if len(obj) == 0:
            return None
    return obj


class EFilm:
    def __init__(self):
        self.__s = requests.Session()

    def get_json(self, url: str) -> list[dict[str, Any]]:
        result = []
        while url:
            r = self.__s.get(url)
            js = r.json()
            url = js['next']
            result.extend(js['results'])
        return result

    @Cache("rec/efilm.json")
    def get_list(self):
        js = self.get_json("https://backend-prod.efilm.online/api/v1/products/products/relevant/?page=1&page_size=9999&skip_chapters=true")
        js = mapdict(_clean_js, js, compact=True)
        return js


if __name__ == "__main__":
    EFilm().get_list()
