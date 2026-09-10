#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/src/film_credits_tagger/app.pyw" &
disown
