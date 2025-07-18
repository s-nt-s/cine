import pycountry
from babel import Locale
import logging
from typing import NamedTuple
from pycountry.db import Country as DBCountry
from pycountry import countries as DBCountries


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


def search_country(name):
    c: DBCountry = DBCountries.get(name=name)
    if c is not None:
        return c
    lw_name = name.lower()
    for c in DBCountries:
        for f in ("name", "official_name", "common_name"):
            if hasattr(c, f):
                value = getattr(c, f)
                if value and lw_name == value.lower():
                    return c
    alias = {
        "russia": "Russian Federation",
        "turkey": "Türkiye"
    }.get(lw_name)
    if alias:
        return search_country(alias)
    return None


def to_country(s: str):
    if s == "West Germany":
        return to_country("Germany")._replace(
            eng=s,
            spa="Alemania Occidental"
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
