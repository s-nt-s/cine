#!/bin/bash
rm -rf imdb.sqlite
curl -Lqs https://s-nt-s.github.io/imdb-sql/imdb.tar.gz | tar -xz 'imdb.sqlite'