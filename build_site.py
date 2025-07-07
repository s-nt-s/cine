#!/usr/bin/env python3

from core.rtve import Rtve
from core.log import config_log
from core.j2 import Jnj2
import logging
from datetime import datetime


config_log("log/build_site.log")
logger = logging.getLogger(__name__)

NOW = datetime.now()

films = tuple(Rtve().films)

print("Resultado final:", len(films))

print("Generando web")

j = Jnj2("template/", "out/", favicon="📽")
j.save(
    "index.html",
    fl=films,
    NOW=NOW,
    count=len(films)
)

print("Fin")
