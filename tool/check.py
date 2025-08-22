from core.dblite import DB, dict_factory
from core.filemanager import DictFile
from types import MappingProxyType
from core.j2 import Jnj2
from core.filmaffinity import FilmM
from typing import NamedTuple
from core.rtve import Rtve as RtveApi
from core.efilm import EFilm as EfilmApi
from core.imdb import IMDB
from core.util import get_first


class Item(NamedTuple):
    url: str
    poster: str
    year: int
    title: tuple[str, ...]


class Row(NamedTuple):
    source: str
    id: int
    imdb: str
    items: tuple[Item, ...]


def load_dct(*files: str, ok_file: str = None):
    ok = set()
    if ok_file:
        obj = DictFile(ok_file)
        ok = set(obj.keys())
        obj.dump()
    data: dict[int, str] = {}
    for file in files:
        obj = DictFile(file)
        for k, v in list(obj.items()):
            if k in data or k in ok:
                obj.discard(k)
            else:
                data[k] = v
        obj.dump()
    return MappingProxyType(data)


rtve = load_dct(
    "cache/rtve.log.dct.txt",
    ok="cache/rtve.dct.txt",
)
efilm = load_dct(
    "cache/efilm.dct.txt",
    "cache/efilm.new.dct.txt",
)
imdb_ids = tuple(sorted(set(efilm.values()).union(set(rtve.values()))))
imdb: dict[str, dict] = {r['id']: r for r in DB.to_tuple(f"""
    select
        *
    from
        movie
    where
        id in {imdb_ids}
""", row_factory=dict_factory)}
imdb_title = DB.get_dict_set(f"select movie, title from title where movie in {imdb_ids}")
imdb_film = DB.get_dict(f"select movie, filmaffinity from extra where movie in {imdb_ids}")


RTVE = RtveApi()
EFFILM = EfilmApi()
arr_data: list[Row] = []

for r_id, i_id in rtve.items():
    id_film = imdb_film.get(i_id)
    f = FilmM.get(id_film)
    r = RTVE.get_video(r_id)
    i = IMDB.get_from_omdbapi(i_id, autocomplete=False)
    items: list[Item] = []
    items.append(Item(
        url=r.url,
        poster=get_first(*r.img_vertical, *r.img_horizontal, *r.img_others),
        year=r.productionDate,
        title=(r.title, )
    ))
    items.append(Item(
        url=f"https://www.imdb.com/es-es/title/{i_id}/",
        poster=i.get('Poster'),
        year=imdb[i_id].get('year') or i['Year'],
        title=tuple(imdb_title.get(i_id, set())) or (i['Title'], ),
    ))
    items.append(Item(
        url=f"https://www.filmaffinity.com/es/film{id_film}.html",
        poster=f.poster if f else None,
        year=f.year if f else None,
        title=(f.title, ) if f else ()
    ))
    arr_data.append(Row(
        source="rtve",
        id=r_id,
        imdb=i_id,
        items=tuple(items)
    ))


for e_id, i_id in efilm.items():
    id_film = imdb_film.get(i_id)
    f = FilmM.get(id_film)
    e = EFFILM.get_video(e_id)
    i = IMDB.get_from_omdbapi(i_id, autocomplete=False)
    items: list[Item] = []
    items.append(Item(
        url=f"https://efilm.online/audiovisual-detail/{e_id}/x",
        poster=get_first(e.cover, *e.covers, e.cover_horizontal, e.banner_main, e.banner_trailer),
        year=e.year,
        title=(e.name, )
    ))
    items.append(Item(
        url=f"https://www.imdb.com/es-es/title/{i_id}/",
        poster=i.get('Poster'),
        year=imdb[i_id].get('year') or i['Year'],
        title=tuple(imdb_title.get(i_id, set())) or (i['Title'], ),
    ))
    items.append(Item(
        url=f"https://www.filmaffinity.com/es/film{id_film}.html",
        poster=f.poster if f else None,
        year=f.year if f else None,
        title=(f.title, ) if f else ()
    ))
    arr_data.append(Row(
        source="efilm",
        id=e_id,
        imdb=i_id,
        items=tuple(items)
    ))

j = Jnj2(
    "template/",
    "out/",
    favicon="📽",
)

j.save(
    "check.html",
    rows=arr_data
)