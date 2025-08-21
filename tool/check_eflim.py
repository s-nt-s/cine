from core.filemanager import FM
from webbrowser import open_new_tab
from core.dblite import DB
from core.efilm import EFilm


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
    print(f"{abs(i):>4}: {k} -> {v}        ", end='\r')
    ficha: dict = EF.get_ficha(k)
    title: str = ficha['name']
    year: int = ficha['year']
    duration: int = ficha['duration']
    if year in imdb_year.get(v, set()) and duration in imdb_duration.get(v, set()) and title.lower() in imdb_title.get(v, set()):
        continue
    imdb = DB.search_imdb_id(
        title,
        year,
        director=ficha['director']['name'],
        duration=duration,
        year_gap=1,
        full_match=False
    )
    if imdb == v:
        continue

    open_new_tab(f"https://efilm.online/audiovisual-detail/{k}/x")
    open_new_tab(f"https://www.imdb.com/es-es/title/{v}/")
print("")
