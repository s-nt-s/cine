from babel import Locale
import logging
from typing import NamedTuple
from pycountry.db import Country as DBCountry
from pycountry import countries as DBCountries, historic_countries
from core.util import get_first

import re

logger = logging.getLogger(__name__)
LOCALE = Locale('es')
re_sp = re.compile(r"\s+")

CUSTOM_ALIASES = {
    "FRG": ("Alemania Occidental", "West Germany"),
    "DDR": ("Alemania Oriental", "East Germany"),
    "SUN": ("Soviet Union", "Unión soviética", "URSS"),
    "PSE": ("Occupied Palestinian Territory",),
    "YUG": ("Yugoslavia", "Yugoslavia, (Socialist) Federal Republic of"),
    "TUR": ("Turkey", "Türkiye"),
    "RUS": ("Russia", "Russian Federation"),
    "GBR": ("UK", "United Kingdom"),
    "TWN": ("ROC", "TAI", "Taiwán"),
    "DEU": ("GER", "Alemania"),
    "LVA": ("Letonia", ),
    "CSK": ("Checoslovaquia", "Czechoslovakia")
}


class Country(NamedTuple):
    alpha_3: str
    spa: str = None
    eng: str = None
    ico: str = None

    def to_html(self):
        if self.ico not in (None, '☭', '★'):
            return f'<abbr class="pais pais_{self.alpha_3}" title="{self.spa}">{self.ico}</abbr>'
        return f'<img class="pais pais_{self.alpha_3}" title="{self.spa}" src="{self.url_ico}"/>'

    @property
    def url_ico(self):
        url = {
            "YUG": "https://upload.wikimedia.org/wikipedia/commons/6/61/Flag_of_Yugoslavia_%281946-1992%29.svg",
            "SUN": "https://upload.wikimedia.org/wikipedia/commons/a/a9/Flag_of_the_Soviet_Union.svg"
        }.get(self.alpha_3)
        if url:
            return url
        alpha_2 = CF.alpha3_to_alpha2(self.alpha_3)
        if alpha_2:
            return f"https://flagcdn.com/{alpha_2}.svg"

    def _fix(self):
        slf = self
        spa = {
            "FRG": "Alemania del Oeste",
            "DDR": "Alemania del Este",
            "SUN": "Unión Soviética",
            "PSE": "Palestina",
            "YUG": "Yugoslavia",
            "SCG": "Serbia y Montenegro",
            "CSK": "Checoslovaquia"
        }.get(slf.alpha_3)
        alpha_2 = CF.alpha3_to_alpha2(slf.alpha_3)
        ico = {
            "FRG": "🇩🇪",
            "DDR": "🇩🇪",
            "CSK": "🇨🇿",
            "SUN": "☭",
            "YUG": "★",
        }.get(slf.alpha_3)
        if spa:
            slf = slf._replace(spa=spa)
        elif slf.spa is None:
            logger.warning(f"País sin nombre: {slf}")
        elif slf.spa.startswith("RAE de "):
            slf = slf._replace(spa=slf.spa[7:].strip())
        if ico:
            slf = slf._replace(ico=ico)
        elif slf.ico is None and slf.url_ico is None:
            logger.critical(f"País sin icono ni URL: {slf}")
        return slf


class CountryFinder:
    def __init__(self):
        self.__error: list[str] = []

    def __log_error(self, msg: str):
        if msg not in self.__error:
            logger.critical(msg)
            self.__error.append(msg)

    def __parse_alpha3(self, cod: str) -> str | None:
        cod = cod.strip()
        if len(cod) == 2 and cod.upper() == cod:
            from_alpha_2 = self.alpha2_to_alpha3(cod)
            if from_alpha_2:
                return from_alpha_2
        cod = cod.upper()
        if DBCountries.get(alpha_3=cod) is not None:
            return cod
        if historic_countries.get(alpha_3=cod) is not None:
            return cod
        return None

    def alpha2_to_alpha3(self, alpha2: str) -> str | None:
        for c in (
            DBCountries.get(alpha_2=alpha2),
            historic_countries.get(alpha_2=alpha2)
        ):
            if c is not None and c.alpha_3:
                return c.alpha_3
        return None

    def alpha3_to_alpha2(self, alpha3: str) -> str | None:
        for c in (
            DBCountries.get(alpha_3=alpha3),
            historic_countries.get(alpha_3=alpha3)
        ):
            if c is not None and c.alpha_2:
                return c.alpha_2
        return None

    def parse_alpha3(self, cod: str, silent: bool = False) -> str | None:
        if cod in (None, '', 'N/A'):
            return None
        if cod in CUSTOM_ALIASES.keys():
            return cod
        for k, v in CUSTOM_ALIASES.items():
            if cod in v:
                return k
        c = self.__parse_alpha3(cod)
        if c is not None:
            return c
        if not silent:
            self.__log_error(f"Código alpha3 de país no encontrado: {cod}")

    def __search_country_by_name(self, name: str):
        c: DBCountry = DBCountries.get(name=name)
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
        return None

    def to_alpha_3(self, s: str):
        if s is None:
            return None
        s = re_sp.sub(" ", s).strip()
        if s in ('', 'N/A'):
            return None
        for k, v in CUSTOM_ALIASES.items():
            if s in v:
                return k
        c = self.__search_country_by_name(name=s)
        if c is not None:
            return c.alpha_3.upper()
        if s == s.upper() and len(s) == 3:
            cod = self.__parse_alpha3(s)
            if cod is not None:
                return cod
        self.__log_error(f"País no encontrado: {s}")
        return None

    @property
    def error(self):
        return tuple(self.__error)

    def __alpha_3_to_country(self, alpha3: str) -> str | None:
        for c in (
            DBCountries.get(alpha_3=alpha3),
            historic_countries.get(alpha_3=alpha3)
        ):
            if c is not None:
                return c
        return None

    def to_country(self, alpha3: str) -> Country:
        if re.match(r"^[A-Z]$", alpha3):
            raise ValueError(f"Código país no válido: {alpha3}")
        if len(alpha3) == 2:
            ap = self.alpha2_to_alpha3(alpha3)
            if ap:
                alpha3 = ap
        if len(alpha3) != 3:
            raise ValueError(f"Código país no válido: {alpha3}")
        if alpha3 == "SUN":
            return Country(
                eng="Soviet Union",
                alpha_3=alpha3,
            )._fix()
        if alpha3 == "FRG":
            return Country(
                eng="West Germany",
                alpha_3=alpha3,
            )._fix()
        c = self.__alpha_3_to_country(alpha3)
        if c is None:
            self.__log_error(f"País no encontrado: {alpha3}")
            return None
        return Country(
            spa=LOCALE.territories.get(c.alpha_2, None),
            eng=get_first(*map(lambda x: getattr(c, x, None), ('name', "common_name", "official_name"))),
            ico=getattr(c, "flag", None),
            alpha_3=alpha3,
        )._fix()

    def to_alpha_3_uniq_tp(self, arr) -> tuple[str, ... ]:
        if arr is None:
            return tuple()
        if not isinstance(arr, (list, tuple)):
            raise ValueError(arr)
        val: list[str] = []
        for v in map(self.to_alpha_3, arr):
            if v is not None and v not in val:
                val.append(v)
        return tuple(val)

    def to_country_uniq_tp(self, arr) -> tuple[str, ... ]:
        if arr is None:
            return tuple()
        if not isinstance(arr, (list, tuple)):
            raise ValueError(arr)
        val: list[str] = []
        for v in map(self.to_country, arr):
            if v is not None and v not in val:
                val.append(v)
        return tuple(val)


CF = CountryFinder()

if __name__ == "__main__":
    import sys
    print(CF.to_country(sys.argv[1]))
