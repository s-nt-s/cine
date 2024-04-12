from .web import Web, refind, get_text
from .cache import TupleCache
from typing import Set, Dict, List
from functools import cached_property, cache
import logging
from .event import Event, Place, Session, Category
import re
from bs4 import Tag
from datetime import datetime, timedelta
from .util import plain_text
import json


logger = logging.getLogger(__name__)
NOW = datetime.now()

class AcademiaCineExpecption(Exception):
    pass


class AcademiaCine(Web):
    URL = "https://entradas.aliro.academiadecine.com/"

    def get(self, url, auth=None, parser="lxml", **kvargs):
        if url == self.url:
            return self.soup
        logger.debug(url)
        return super().get(url, auth, parser, **kvargs)

    @cached_property
    def calendar(self):
        urls: Set[str] = set()
        self.get(AcademiaCine.URL)
        for a in self.soup.select("div.activities-wrapper a"):
            urls.add((a.attrs["href"], a.find("img").attrs["src"]))
        return tuple(sorted(urls))

    @property
    @TupleCache("rec/academiacine.json", builder=Event.build)
    def events(self):
        events: Set[Event] = set()
        for url, img in self.calendar:
            events.add(self.__url_to_event(url, img))
        if None in events:
            events.remove(None)
        return tuple(sorted(events))

    def __url_to_event(self, url: str, img: str):
        self.get(url)
        return Event(
            id="ac"+url.split("/")[-1],
            url=url,
            name=get_text(self.select_one("div.fs-1")),
            img=img,
            price=self.__find_price(),
            category=self.__find_category(),
            duration=self.__find_duration(),
            sessions=tuple((Session(
                url=url,
                date=self.__find_session()
            ),)),
            place=Place(
                name="Academia de cine",
                address="Calle de Zurbano, 3, Chamberí, 28010 Madrid"
            )
        )

    def __find_session(self):
        months = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
        txt = get_text(self.select_one("div.fs-5"))
        dat = txt.split("|")[0].lower()
        match = re.search(r"(\d+) de (" + "|".join(months) + r")\S+ de (\d+) a las (\d+):(\d+)", dat)
        if match is None:
            raise AcademiaCineExpecption("NOT FOUND DATE: " + dat)
        d, month, y, h, mm = match.groups()
        m = months.index(month) + 1
        d, y, h, mm = map(int, (d, y, h, mm))
        return f"{y}-{m:02d}-{d:02d} {h:02d}:{mm:02d}"

    def __find_price(self):
        prices = set()
        for p in map(get_text, self.soup.select("div.session-info div")):
            prices = prices.union(map(lambda x: float(x.replace(",", ".")), re.findall(r"([\d,.]+)\s+euro\(s\)", p)))
        if len(prices) == 0:
            raise AcademiaCineExpecption("NOT FOUND PRICE in "+self.url)
        return max(prices)

    def __find_duration(self):
        td = self.soup.find("td", string=re.compile(r"^\s*\d+\s+minutos\s*$"))
        if td is None:
            logger.warning("NO DURATION in "+self.url)
            return 0
        txt = get_text(td)
        return int(txt.split()[0])

    def __find_category(self):
        tds = tuple(map(plain_text, self.soup.select("th")))
        if len(set({"duracion", "idioma", "formato"}).difference(tds)) == 0:
            return Category.CINEMA
        txt = get_text(self.select_one("div.fs-5"))
        cat = plain_text(txt.split("|")[-1]).lower()
        if cat in ("la academia preestrena", "aniversarios de cine"):
            return Category.CINEMA
        if re.search(r"libros?", cat):
            logger.warning(self.url+" OTHERS: "+cat)
            return Category.OTHERS
        if re.search(r"podcast?", cat):
            logger.warning(self.url+" OTHERS: "+cat)
            return Category.OTHERS
        raise AcademiaCineExpecption("Unknown category: " + txt)

if __name__ == "__main__":
    from .log import config_log
    config_log("log/academiacine.log", log_level=(logging.DEBUG))
    print(AcademiaCine().events)