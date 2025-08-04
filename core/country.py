from babel import Locale
import logging
from typing import NamedTuple
from pycountry.db import Country as DBCountry
from pycountry import countries as DBCountries, historic_countries


logger = logging.getLogger(__name__)
LOCALE = Locale('es')


class Country(NamedTuple):
    spa: str
    cod: str
    eng: str = None
    ico: str = None

    def to_html(self):
        if self.ico:
            return f'<abbr class="pais pais_{self.cod}" title="{self.spa}">{self.ico}</abbr>'
        return f'<img class="pais pais_{self.cod}" title="{self.spa}" src="https://flagcdn.com/{self.cod}.svg"/>'


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
        for f in ("name", "official_name", "common_name"):
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
        "yugoslavia": "Yugoslavia, (Socialist) Federal Republic of"
    }.get(lw_name)
    if alias:
        return search_country(alias)
    return None


def to_country(s: str) -> Country:
    if s == "West Germany":
        return to_country("Germany")._replace(
            eng=s,
            spa="Alemania Occidental"
        )
    if s in ("SUN", "Soviet Union", "Unión soviética", "URSS"):
        return Country(
            cod="SUN",
            spa="Unión soviética",
            eng="Soviet Union",
            ico="🇨🇳"
        )
    c = search_country(name=s)
    if c is None:
        raise ValueError(f"País no encontrado: {s}")
    cod: str = c.alpha_2
    name = LOCALE.territories.get(cod)
    return Country(
        cod=cod.lower(),
        spa=name,
        eng=s,
        ico=c.flag
    )


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
