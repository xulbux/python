# Apps

This directory contains lots of small, useful desktop apps built with [**Python**](https://www.python.org) and [**CustomTkinter**](https://customtkinter.tomschimansky.com).

✔️  All apps run on **Windows**, **macOS**, and **Linux**.<br>
✨  All apps use a consistent, modern design language.<br>
🔆  All apps follow the system **light/dark theme**.<br>

### Apps in this collection

-   [**Film Credits Tagger**](#film-credits-tagger)
-   [**Video Trimmer**](#video-trimmer)

### General requirements

-   Python 3.12+
-   Python packages:

    ```bash
    pip install customtkinter reportlab pymupdf pillow svglib
    ```

-   (*Other app-specific requirements noted in each app's section below.*)

### Launching an app

-   On **Windows**, double-click the app's `.vbs` file (*e.g.,* `video-trimmer.vbs`).
-   On **macOS/Linux**, run the app's `.sh` file (*e.g.,* `video-trimmer.sh`) in a terminal (*or double-click it if your system allows*).
-   (*Or manually run the app's* `src/<app_name>/app.pyw` *with Python.*)

<br>
<br>
<br>

# Film Credits Tagger<a href="#film-credits-tagger"><img src="./src/film_credits_tagger/assets/img/film-credits-tagger.svg" height="36" align="right" /></a>

A small desktop app for tagging film credits and metadata into video files – powered by [**ExifTool**](https://exiftool.org).

### Features

-   **Write metadata** into `.mp4`, `.mov`, `.m4v`, `.m4a`, `.3gp`, and `.3g2` files.
-   **Batch processing** – Select multiple files and apply the same tags to all at once.
-   **Editable fields** – Edit various properties covering general info, credits, and descriptions.
-   **Cover art** – Select an image, preview it in-app, and embed it as front-cover art.
-   **JSON templates** – Save the current field values to a `.json` file and reload them later.
-   **Load from video** – Reads existing metadata and cover art back out of a file and populates the fields.
-   **Clear-empty toggle** – When enabled, fields left blank actively *delete* the corresponding tags<br>
    from the file instead of leaving them untouched.
-   **Cross-platform tags** – Writes both iTunes/QuickTime atoms (*recognized by macOS, VLC, mpv*)<br>
    and Windows-specific tags (*recognized by Windows Explorer and WMP*) simultaneously.

### Requires

-   [**ExifTool**](https://exiftool.org) installed and available on `PATH`
    <!-- winget install -e --id OliverBetz.ExifTool -->

<br>
<br>
<br>

# Video Trimmer<a href="#video-trimmer"><img src="./src/video_trimmer/assets/img/video-trimmer.svg" height="36" align="right" /></a>

A small desktop app for trimming the start and end off a video file – powered by [**FFmpeg**](https://ffmpeg.org).


### Features

-   **Lossless trimming** – Uses FFmpeg's stream-copy mode (`-c copy`), so trimming is fast<br>
    and doesn't re-encode or recompress the video or audio.
-   **Flexible time format** – Accepts `SS`, `MM:SS`, or `HH:MM:SS` (decimals allowed, e.g., `1:23.5`).
-   **Frame-number mode** – Toggle between time and frame-number input for precise, frame-accurate trim points.
-   **Optional bounds** – Leave start blank to trim from the beginning; leave end blank to trim to the end of the file.
-   **Interactive timeline** – Drag the start/end handles or use the stepper buttons to adjust trim points.
-   **Frame previews** – Live thumbnails show the exact start and end frames as you adjust the trim points.
-   **Smart output path** – Defaults to the input file's folder with a `_trim` suffix; or pick your own.

### Requires

-   [**FFmpeg**](https://ffmpeg.org) (`ffmpeg` and `ffprobe`) installed and available on `PATH`
    <!-- winget install -e --id Gyan.FFmpeg -->

<br>
<br>
<br>
