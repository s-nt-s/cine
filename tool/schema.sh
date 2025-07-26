#!/bin/bash
jsonschema --out rec/schema.efilm.json rec/efilm/fimls.json
jsonschema --out rec/schema.rtve.json rec/rtve/ficha/*.json