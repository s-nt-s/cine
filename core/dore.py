from .web import Web, refind, get_text
from .cache import TupleCache
from typing import Set, List, Dict
from functools import cached_property, cache
import logging
from .event import Event, Place, Session, Category

logger = logging.getLogger(__name__)


class DoreException(Exception):
    pass


class Dore(Web):
    URL = "https://entradasfilmoteca.gob.es/"
    PRICE = 3

    def get(self, url, auth=None, parser="lxml", **kvargs):
        kys = ('__EVENTTARGET', '__EVENTARGUMENT')
        if len(kvargs) and len(set(kys).difference(kvargs.keys())) == 0:
            msg = str(url) + '?' + "&".join(map(lambda k: f"{k}={kvargs[k]}", kys))
            logger.debug(msg)
        else:
            logger.debug(url)
        return super().get(url, auth, parser, **kvargs)

    @cached_property
    def calendar(self):
        ids: Set[int] = set()
        self.get(Dore.URL)
        while True:
            cal = self.soup.select_one("#CalendarioBusqueda")
            days = refind(cal, "td a", r"\d+")
            if len(days) == 0:
                return tuple(sorted(ids))
            for a in days:
                href = a.attrs["href"]
                id = href.split("'")[-2]
                ids.add(int(id))
            nxt = refind(cal, "a", r">")
            if len(nxt) < 1:
                return tuple(sorted(ids))
            action, data = self.prepare_submit("#ctl01")
            data['__EVENTTARGET'] = "ctl00$CalendarioBusqueda"
            data['__EVENTARGUMENT'] = nxt[0].attrs['href'].split("'")[-2]
            data['ctl00$TBusqueda'] = ""
            self.get(action, **data)

    @cache
    def get_links(self):
        urls: Set[str] = set()
        self.get(Dore.URL)
        action, data = self.prepare_submit("#ctl01")
        data['__EVENTTARGET'] = "ctl00$CalendarioBusqueda"
        data['ctl00$TBusqueda'] = ""
        for cal in self.calendar:
            data['__EVENTARGUMENT'] = str(cal)
            self.get(action, **data)
            for a in self.soup.select("div.thumPelicula a.linkPelicula"):
                urls.add(a.attrs["href"])
        return tuple(sorted(urls))

    @property
    @TupleCache("rec/dore.json", builder=Event.build)
    def events(self):
        events: Set[Event] = set()
        for url in self.get_links():
            events.add(self.__url_to_event(url))
        events = self.__clean_events(events)
        return tuple(events)

    def __clean_events(self, all_events: Set[Event]):
        data: Dict[str, Set[Event]] = {}
        for e in all_events:
            if e.title not in data:
                data[e.title] = set()
            data[e.title].add(e)
        vnts: Set[Event] = set()
        for arr in map(sorted, data.values()):
            if len(arr) == 1:
                vnts.add(arr[0])
                continue
            sessions: Set[Session] = set()
            for e in arr:
                for s in e.sessions:
                    sessions.add(s.merge(url=(s.url or e.url)))
            vnts.add(e.merge(sessions=tuple(sorted(sessions))))
        events: Set[Event] = set()
        for e in vnts:
            surl = set(s.url for s in e.sessions if s.url)
            if len(surl) > 0:
                if len(surl) > 1:
                    e = e.merge(url='')
                else:
                    e = e.merge(
                        url=surl.pop(),
                        sessions=tuple(sorted(s.merge(url=None) for s in e.sessions))
                    )
            events.add(e)
        return tuple(sorted(events))

    def __url_to_event(self, url):
        self.get(url)
        return Event(
            id='fm'+url.split("=")[-1],
            url=url,
            name=get_text(self.soup.select_one("div.row h1")),
            category=self.__find_category(),
            img=self.soup.select_one("div.item.active img").attrs["src"],
            place=self.__find_place(),
            sessions=self.__find_sessions(),
            price=Dore.PRICE
        )

    def __find_sessions(self):
        sessions: Set[Session] = set()
        for tr in self.soup.select("#ContentPlaceHolderMain_grvEventos tr"):
            tds = tuple(map(get_text, tr.findAll("td")))
            d, m, y = map(int, tds[1].split("/"))
            h, mm = map(int, tds[2].split(":"))
            sessions.add(Session(
                date=f"{y}-{m:02d}-{d:02d} {h:02d}:{mm:02d}"
            ))
        return tuple(sorted(sessions))

    def __find_category(self):
        n = self.select_one("#ContentPlaceHolderMain_h2Categoria")
        for br in n.findAll("br"):
            br.replace_with("\n\n")
        txt = get_text(n).split()[0].lower()
        if txt == "cine":
            return Category.CINEMA
        raise DoreException("Unknown category: "+txt)

    def __find_place(self):
        place = get_text(self.select_one("#lateralFicha h4")).lower()
        if place == "cine doré":
            return Place(
                name="Cine Doré",
                address="C. de Santa Isabel, 3, Centro, 28012 Madrid"
            )
        raise DoreException("Unknown place: "+place)


if __name__ == "__main__":
    from .log import config_log
    config_log("log/dore.log", log_level=(logging.DEBUG))
    print(Dore().events)
