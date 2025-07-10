from requests import Session
from os import environ
import logging
from core.util import tp_split, re_or
from core.cache import Cache
from functools import cache
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
            if obj.isdigit() and k in ('Year', "imdbRating", ):
                return int(obj)
            if k in ("Director", "Writer", "Actors", "Genre"):
                return list(tp_split(r",", obj))
            if re.match(r"^\d+\.\d+$", obj) and k in ("imdbRating", ):
                return float(obj)
            if re.match(r"^\d+[\.\d,]*$", obj) and k in ("imdbVotes", ):
                return int(obj.replace(",", ""))
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

    @cache
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
        if re_or(title, "^Los habitantes de la casa deshabitada", flags=re.I):
            return "tt7534332"
        if re_or(title, "^Bolívar. El hombre de las dificultades", flags=re.I):
            return "tt3104336"
        if re_or(title, "^MAMA$", flags=re.I) and year == 2021:
            return "tt12725124"
        if re_or(title, "^El techo amarillo", flags=re.I) and year == 2022:
            return "tt20112674"
        if re_or(title, "^Historias de nuestro cine", flags=re.I) and year == 2019:
            return "tt11128736"
        if re_or(title, "^Mujeres sin censura", flags=re.I) and year == 2021:
            return "tt15787982"
        if re_or(title, "^Para profesor vale cualquiera", flags=re.I) and year == 2022:
            return "tt18718108"
        if re_or(title, r"^\¡Upsss 2\! \¿Y ahora dónde está Noé", flags=re.I):
            return "tt12615474"
        if re_or(title, r"^El asombroso Mauricio", flags=re.I) and year == 2022:
            return "tt10473036"
        if re_or(title, r"^Mi pequeño amor", flags=re.I) and year == 2020:
            return "tt12546872"
        if re_or(title, r"^Un cuento de Navidad", flags=re.I) and year == 2008:
            return "tt0993789"
        if re_or(title, r"^Hanna y los monstruos", flags=re.I) and year == 2022:
            return "tt2903136"
        if re_or(title, r"^La buena vida", flags=re.I) and year == 2008:
            return "tt1327798"
        if re_or(title, r"^Alguien que cuide de mí", flags=re.I) and year == 2023:
            return "tt19382276"
        if re_or(title, r"^Bardem, la metamorfosis", flags=re.I) and year in (2023, 2020):
            return "tt31647570"
        if re_or(title, r"^Indomable, Ava Gardner", flags=re.I) and year in (2018, 2016):
            return "tt31647570"
        if re_or(title, r"^Los ángeles exterminados", flags=re.I) and year == 1968:
            return "tt37384074"
        if re_or(title, r"^El traje", flags=re.I) and year == 2002:
            return "tt0340407"


OMDB = OmdbApi()

if __name__ == "__main__":
    import sys
    r = OMDB.get(sys.argv[1])
    print(r)
