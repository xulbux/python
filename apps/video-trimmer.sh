#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$DIR/src/video_trimmer/app.pyw" &
disown
