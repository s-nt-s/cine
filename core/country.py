from babel import Locale
import logging
from typing import NamedTuple
from pycountry.db import Country as DBCountry
from pycountry import countries as DBCountries, historic_countries
from core.util import get_first

logger = logging.getLogger(__name__)
LOCALE = Locale('es')


class Country(NamedTuple):
    spa: str
    cod: str
    eng: str = None
    ico: str = None
    alpha_3: str = None

    def to_html(self):
        if self.ico:
            return f'<abbr class="pais pais_{self.cod}" title="{self.spa}">{self.ico}</abbr>'
        return f'<img class="pais pais_{self.cod}" title="{self.spa}" src="{self.url_ico}"/>'

    @property
    def url_ico(self):
        if self.alpha_3 == "YUG":
            return "https://upload.wikimedia.org/wikipedia/commons/6/61/Flag_of_Yugoslavia_%281946-1992%29.svg"
        return f"https://flagcdn.com/{self.cod}.svg"

    def _fix(self):
        slf = self
        if slf.spa:
            if slf.spa.startswith("RAE de "):
                slf = slf._replace(spa=slf.spa[7:].strip())
            if slf.spa == "Territorios Palestinos":
                slf = slf._replace(spa="Palestina")
        elif slf.alpha_3 == "SCG":
            slf = slf._replace(spa="Serbia y Montenegro")
        elif slf.alpha_3 == "YUG":
            slf = slf._replace(spa="Yugoslavia")
        else:
            logger.warning(f"País sin nombre: {slf}")
        return slf


def search_country(name: str):
    if name in (None, '', 'N/A'):
        return None
    c: DBCountry = \
        DBCountries.get(name=name) or \
        DBCountries.get(alpha_3=name) or \
        DBCountries.get(alpha_2=name)
    if c is not None:
        return c
    lw_name = name.lower()
    for c in DBCountries:
        for f in ("name", "official_name", "common_name"):
            if hasattr(c, f):
                value = getattr(c, f)
                if not isinstance(value, str):
                    continue
                if lw_name == value.lower():
                    return c
    for c in historic_countries:
        for f in ("name", "official_name", "common_name", "alpha_3"):
            if hasattr(c, f):
                value = getattr(c, f)
                if not isinstance(value, str):
                    continue
                if lw_name == value.lower():
                    return c
    alias = {
        "russia": "Russian Federation",
        "turkey": "Türkiye",
        "uk": "GB",
        "yugoslavia": "Yugoslavia, (Socialist) Federal Republic of",
        "occupied palestinian territory": "PSE"
    }.get(lw_name)
    if alias:
        return search_country(alias)
    return None


def to_country(s: str) -> Country:
    if s == "NED":
        return to_country("NLD")
    if s == "West Germany":
        return to_country("Germany")._replace(
            eng=s,
            spa="Alemania Occidental"
        )._fix()
    if s in ("SUN", "Soviet Union", "Unión soviética", "URSS"):
        return Country(
            cod="SUN",
            spa="Unión soviética",
            eng="Soviet Union",
            ico="🇨🇳"
        )._fix()
    c = search_country(name=s)
    if c is None:
        raise ValueError(f"País no encontrado: {s}")
    cod: str = c.alpha_2
    alpha_3: str = getattr(c, 'alpha_3', None)
    name = LOCALE.territories.get(cod)
    return Country(
        cod=cod.lower(),
        spa=name,
        eng=get_first(*map(lambda x: getattr(c, x, None), ('name', "common_name", "official_name"))),
        ico=getattr(c, "flag", None),
        alpha_3=alpha_3,
    )._fix()


def _to_alpha_3(s: str):
    if s in (None, '', 'N/A'):
        return None
    if s in ("SUN", "Soviet Union", "Unión soviética", "URSS"):
        return "SUN"
    if s == "West Germany":
        return _to_alpha_3("Germany")
    c = search_country(name=s)
    if c is None:
        raise ValueError(f"País no encontrado: {s}")
    return c.alpha_3.upper()


def to_alpha_3(names: tuple[str, ...]):
    if not isinstance(names, (tuple, list)):
        return tuple()
    arr = []
    for n in names:
        try:
            c = _to_alpha_3(n)
            if c is not None and c not in arr:
                arr.append(c)
        except ValueError as e:
            logger.critical(str(e))
    return tuple(arr)


def to_countries(cs: tuple[str, ...]):
    if not isinstance(cs, (tuple, list)):
        return tuple()
    arr: list[Country] = []
    for c in cs:
        try:
            x = to_country(c)
            if x:
                arr.append(x)
        except ValueError as e:
            logger.critical(str(e))
    return tuple(arr)


if __name__ == "__main__":
    import sys
    print(to_country(sys.argv[1]))
