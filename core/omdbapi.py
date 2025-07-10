from requests import Session
from os import environ
import logging
from core.util import tp_split, re_or
from core.cache import Cache
import re

logger = logging.getLogger(__name__)

def _clean_js(obj: list | dict | str, k: str = None):
    if isinstance(obj, str):
        obj = obj.strip()
        if obj in ("", "N/A"):
            return None
        if obj in ("True", "False"):
            return obj == "True"
        if isinstance(k, str):
            if obj.isdigit() and k in ('Year', "imdbRating"):
                return int(obj)
            if k in ("Director", "Writer", "Actors", "Genre"):
                return list(tp_split(r",", obj))
            if re.match(r"^\d+\.\d+$", obj) and k in ("imdbRating", ):
                return float(obj)
        return obj
    if isinstance(obj, list):
        return [_clean_js(i) for i in obj]
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            v = _clean_js(v, k=k)
            if k in ("imdbRating", ) and isinstance(v, (int, float)) and v<0:
                v = None
            obj[k] = v
    return obj

class OmdbApi:
    def __init__(self):
        key = environ['OMDBAPI_KEY']
        self.__url = f"http://www.omdbapi.com/?apikey={key}&i="
        self.__s = Session()

    @Cache("rec/omdbapi/{}.json")
    def get(self, id: str):
        if id in (None, ""):
            return None
        r = self.__s.get(self.__url+id)
        js = r.json()
        js = _clean_js(js)
        if js.get("Error"):
            logger.warning(f"OmdbApi: {id} = {js['Error']}")
            return None
        return js

    def get_id(self, title: str, year: int):
        if re_or(title, "^Almodóvar, todo sobre ellas", flags=re.I):
            return "tt6095626"
        if re_or(title, "^De Salamanca a ninguna parte", flags=re.I):
            return "tt0336249"
        if re_or(title, "^Los comuneros$", flags=re.I) and year == 1978:
            return "tt0573534"
        if re_or(title, "^Fernando Méndez Leite. La memoria del cine", "La memoria del cine: una película sobre Fernando Méndez-Leite", flags=re.I):
            return "tt26812553"
        if re_or(title, "^Spanish Western", flags=re.I):
            return "tt6728914"
        if re_or(title, "^La primera mirada", flags=re.I):
            return "tt32897831"


OMDB = OmdbApi()

if __name__ == "__main__":
    import sys
    r = OMDB.get(sys.argv[1])
    print(r)
