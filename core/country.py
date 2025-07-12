
import pycountry
from babel import Locale
import logging
from typing import NamedTuple
from pycountry.db import Country as DBCountry

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
        return f'<img class="pais pais_{self.cod}" title="{self.spa}" src="python/{self.cod}.svg"/>'


def search_country(name):
    c = pycountry.countries.get(name=name)
    if c is not None:
        return c
    for country in pycountry.countries:
        if country.name.lower() == name.lower():
            return country
        if hasattr(country, 'official_name') and country.official_name.lower() == name.lower():
            return country
    alias = {
        "russia": "Russian Federation",
        "usa": "United States",
        "uk": "United Kingdom",
        "south korea": "Korea, Republic of",
        "north korea": "Korea, Democratic People's Republic of",
        "iran": "Iran, Islamic Republic of",
        "syria": "Syrian Arab Republic",
        "czech republic": "Czechia",
        "west germany": "Germany",
    }.get(name.lower())
    if alias:
        return search_country(alias)
    return None


def to_country(s: str):
    if s == "Venezuela":
        return Country(
            cod="ve",
            spa="Venezuela",
        )
    if s == "Bolivia":
        return Country(
            cod="ko",
            spa="Bolivia",
        )
    if s == "Turkey":
        return Country(
            cod="tr",
            spa="Turquía",
        )
    c = search_country(name=s)
    cod: str = c.alpha_2
    name = LOCALE.territories.get(cod)
    return Country(
        cod=cod.lower(),
        spa=name,
        eng=s,
        ico=c.flag
    )