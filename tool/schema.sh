#!/bin/bash
jsonschema --out rec/schema.efilm.json rec/efilm/items.json
jsonschema --out rec/schema.efilm.ficha.json rec/efilm/ficha/*.json
jsonschema --out rec/schema.rtve.json rec/rtve/ficha/*.json