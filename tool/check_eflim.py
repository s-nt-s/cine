from core.filemanager import FM
from webbrowser import open_new_tab
from core.dblite import DB
from core.efilm import EFilm
from time import sleep


EF = EFilm(
    origin='https://cinemadrid.efilm.online',
    min_duration=50
)


def to_dict_set(gap: int, sql: str):
    result: dict[str, set[int]] = {}
    for k, v in DB.get_dict(sql).items():
        result[k] = {x for x in range(v - gap, v + gap + 1)}
    return result


obj: dict[int, str] = FM.load("cache/efilm.dct.txt")
imdbs = tuple(sorted(set(obj.values())))
imdb_year: dict[str, set[int]] = to_dict_set(10, f"select id, year from MOVIE where year is not null and id in {imdbs}")
imdb_duration: dict[str, set[int]] = to_dict_set(1, f"select id, duration from MOVIE where duration is not null and id in {imdbs}")
imdb_title: dict[str, set[str]] = DB.get_dict_set(f"select movie, LOWER(title) from TITLE where title is not null and movie in {imdbs}")

for i, (k, v) in enumerate(obj.items(), start=-len(obj)):
    if abs(i) > 778:
        continue
    print(f"{abs(i):>4}: {k} -> {v}        ", end='\r')
    ficha: dict = EF.get_ficha(k)
    title: str = ficha.get('name')
    year: int = ficha.get('year')
    duration: int = ficha.get('duration')
    if year in imdb_year.get(v, set()) and duration in imdb_duration.get(v, set()) and title.lower() in imdb_title.get(v, set()):
        continue

    open_new_tab(f"https://efilm.online/audiovisual-detail/{k}/x")
    open_new_tab(f"https://www.imdb.com/es-es/title/{v}/")
    sleep(8)
print("")
