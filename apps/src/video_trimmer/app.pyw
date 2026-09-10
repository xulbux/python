# pyright: basic
import ctypes
import io
import json
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from contextlib import suppress
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING
import customtkinter as ctk
from PIL import Image

# Make the `_shared` package (apps/src/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Shared; absolute imports during runtime, relative ones during development so the types are linked correctly in the IDE:
from _shared.consts import COLORS, POPEN_FLAGS
from _shared.helpers import get_system_theme, resolve_binary, resolve_mono_font, setup_window_icon
from _shared.widgets import SegmentedButton, SingleLineEntry, SpinnerButton, ToolTip, render_svg_icon

if TYPE_CHECKING:
    from .._shared.consts import COLORS, POPEN_FLAGS  # ruff:ignore[runtime-import-in-type-checking-block]
    from .._shared.helpers import get_system_theme, resolve_binary, resolve_mono_font, setup_window_icon  # ruff:ignore[runtime-import-in-type-checking-block]
    from .._shared.widgets import SegmentedButton, SingleLineEntry, SpinnerButton, ToolTip, render_svg_icon  # ruff:ignore[runtime-import-in-type-checking-block]

from consts import APP_ICON_PNG, VIDEO_FILE_TYPES
from exporter import TrimExporter
from helpers import format_time, frame_to_time, parse_time, time_to_frame
from widgets import TrimTimeline

# Config for the preview thumbnails shown above the timeline:
_THUMB_W: int = 266
_THUMB_H: int = 150  # 16:9 aspect ratio.
_PREVIEW_DEBOUNCE_MS: int = 350
_DEFAULT_FPS: float = 25.0

# Thumbnail strip (low-res in-memory cache for instant scrub feedback):
_STRIP_COUNT: int = 2048
_STRIP_W: int = 320
_STRIP_H: int = 180  # 16:9 aspect ratio.

# Suffix for auto-generated filenames when the user doesn't specify an output path:
_TRIM_SUFFIX: str = "_trim"


class VideoTrimmerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Video Trimmer")
        self.resizable(False, False)

        # Centered fixed-size window:
        ww, wh = 580, 635
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")

        # Set window/taskbar icon:
        self._temp_ico_path: Path | None = setup_window_icon(self, APP_ICON_PNG)

        # Check for FFmpeg / FFprobe:
        self.ffmpeg_path: str | None = resolve_binary("ffmpeg")
        self.ffprobe_path: str | None = resolve_binary("ffprobe")
        self._fps_mode_flag: str = "-fps_mode"

        self.selected_file: str | None = None
        self.duration: float | None = None  # In seconds.
        self.fps: float | None = None
        self.output_path: str | None = None

        self._start_sec: float = 0.0  # Internal start point (always in seconds).
        self._end_sec: float | None = None  # Internal end point; None = end of file.

        self._input_mode: str = "time"  # "time" or "frame".
        self._current_theme: str = get_system_theme()
        self._trimming: bool = False

        self._preview_start_job: str | None = None
        self._preview_end_job: str | None = None
        self._preview_pending_sec: dict[str, float | None] = {"start": None, "end": None}
        self._preview_latest_sec: dict[str, float | None] = {"start": None, "end": None}
        self._preview_last_fire_ms: dict[str, float] = {"start": 0.0, "end": 0.0}
        self._start_preview_image: ctk.CTkImage | None = None
        self._end_preview_image: ctk.CTkImage | None = None
        self._preview_generation: int = 0

        # Low-res thumbnail strip for scrub feedback:
        self._thumb_strip: list[Image.Image] = []
        self._thumb_strip_generation: int = -1
        self._strip_proc: subprocess.Popen[str] | None = None  # In-flight FFmpeg index process.

        # ************************** UI LAYOUT **************************

        PAD: int = 16

        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=PAD, pady=PAD)

        # ********************* SELECT FILE SECTION *********************

        self.sec_file = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.sec_file.pack(fill="x")
        self.sec_file.grid_columnconfigure(1, weight=1)

        self.lbl_section_file = ctk.CTkLabel(self.sec_file, text="Select Video", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_section_file.grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.btn_reset_all = ctk.CTkButton(
            self.sec_file, text="", width=28, height=28, corner_radius=6, border_width=0, command=self.reset_all
        )
        self.btn_reset_all.grid(row=0, column=2, sticky="e", pady=(0, 8))
        ToolTip(self.btn_reset_all, "Reset all fields")

        self.btn_select_file = SpinnerButton(
            self.sec_file,
            text="Select Video File",
            command=self.select_file,
            state="disabled",  # Enabled after `_verify_ffmpeg` confirms.
        )
        self.btn_select_file.grid(row=1, column=0, sticky="w")

        self.lbl_file = ctk.CTkLabel(self.sec_file, text="No file selected", anchor="w")
        self.lbl_file.grid(row=1, column=1, padx=(10, 0), sticky="ew")

        # ********************* TRIM RANGE SECTION **********************

        self.sec_trim = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.sec_trim.pack(fill="x", pady=(PAD, 0))

        # Section header: title + time / frame mode toggle:
        self.trim_header = ctk.CTkFrame(self.sec_trim, fg_color="transparent")
        self.trim_header.pack(fill="x", pady=(0, 8))

        self.lbl_section_trim = ctk.CTkLabel(self.trim_header, text="Trim Range", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_section_trim.pack(side="left")

        self.mode_toggle = SegmentedButton(
            self.trim_header,
            values=["Time", "Frame"],
            command=self._on_mode_change,
            width=120,
            height=24,
            font=ctk.CTkFont(size=12),
            tooltip="Switch between time (HH:MM:SS) and frame-number input mode",
        )
        self.mode_toggle.set("Time")
        self.mode_toggle.pack(side="right")

        # Scrub-strip indexing status (left of the mode toggle):
        self.lbl_strip_status = ctk.CTkLabel(self.trim_header, text="", font=ctk.CTkFont(size=11), justify="right")
        self.lbl_strip_status.pack(side="right", padx=(0, 12))

        # Preview thumbnails: start on left, end on right:
        self.sec_preview = ctk.CTkFrame(self.sec_trim, fg_color="transparent")
        self.sec_preview.pack(fill="x", pady=(0, 6))

        self.frame_start_thumb = ctk.CTkFrame(
            self.sec_preview, width=_THUMB_W + 6, height=_THUMB_H + 6, corner_radius=0, border_width=1
        )
        self.frame_start_thumb.pack(side="left")
        self.frame_start_thumb.pack_propagate(False)
        self.lbl_start_thumb = ctk.CTkLabel(self.frame_start_thumb, text="Start\nframe", font=ctk.CTkFont(size=11))
        self.lbl_start_thumb.place(relx=0.5, rely=0.5, anchor="center")

        self.frame_end_thumb = ctk.CTkFrame(
            self.sec_preview, width=_THUMB_W + 6, height=_THUMB_H + 6, corner_radius=0, border_width=1
        )
        self.frame_end_thumb.pack(side="right")
        self.frame_end_thumb.pack_propagate(False)
        self.lbl_end_thumb = ctk.CTkLabel(self.frame_end_thumb, text="End\nframe", font=ctk.CTkFont(size=11))
        self.lbl_end_thumb.place(relx=0.5, rely=0.5, anchor="center")

        # Timeline bar:
        self.trim_timeline = TrimTimeline(self.sec_trim, height=36)
        self.trim_timeline.pack(fill="x", pady=(16, 32))
        self.trim_timeline.on_change = self._on_timeline_change
        self.trim_timeline.on_commit = self._on_timeline_commit
        self.trim_timeline.set_enabled(False)  # Disabled until a file is loaded.

        # Input row: start / end entries with steppers:
        self.sec_inputs = ctk.CTkFrame(self.sec_trim, fg_color="transparent")
        self.sec_inputs.pack(fill="x")
        self.sec_inputs.grid_columnconfigure(2, weight=1)
        self.sec_inputs.grid_columnconfigure(6, weight=1)

        # Start:
        self.lbl_start = ctk.CTkLabel(self.sec_inputs, text="Start")
        self.lbl_start.grid(row=0, column=0, sticky="w", padx=(0, 6))

        self.btn_start_left = ctk.CTkButton(
            self.sec_inputs,
            text="",
            width=28,
            height=28,
            corner_radius=6,
            border_width=1,
            command=lambda: self._step_time("start", -1),
        )
        self.btn_start_left.grid(row=0, column=1, padx=(0, 2))

        self.entry_start = SingleLineEntry(self.sec_inputs, border_width=1, placeholder_text="00:00")
        self.entry_start.grid(row=0, column=2, sticky="ew")

        self.btn_start_right = ctk.CTkButton(
            self.sec_inputs,
            text="",
            width=28,
            height=28,
            corner_radius=6,
            border_width=1,
            command=lambda: self._step_time("start", +1),
        )
        self.btn_start_right.grid(row=0, column=3, padx=(2, 0))

        # End:
        self.lbl_end = ctk.CTkLabel(self.sec_inputs, text="End")
        self.lbl_end.grid(row=0, column=4, sticky="w", padx=(PAD, 6))

        self.btn_end_left = ctk.CTkButton(
            self.sec_inputs,
            text="",
            width=28,
            height=28,
            corner_radius=6,
            border_width=1,
            command=lambda: self._step_time("end", -1),
        )
        self.btn_end_left.grid(row=0, column=5, padx=(0, 2))

        self.entry_end = SingleLineEntry(self.sec_inputs, border_width=1, placeholder_text="end of file")
        self.entry_end.grid(row=0, column=6, sticky="ew")

        self.btn_end_right = ctk.CTkButton(
            self.sec_inputs,
            text="",
            width=28,
            height=28,
            corner_radius=6,
            border_width=1,
            command=lambda: self._step_time("end", +1),
        )
        self.btn_end_right.grid(row=0, column=7, padx=(2, 0))

        # Hint text:
        self.lbl_hint = ctk.CTkLabel(
            self.sec_trim,
            text="Format: SS, MM:SS or HH:MM:SS  (decimals allowed, e.g., 1:23.5)",
            font=ctk.CTkFont(size=11),
        )
        self.lbl_hint.pack(anchor="w", pady=(6, 0))

        # *********************** OUTPUT SECTION ************************

        self.sec_out = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.sec_out.pack(fill="x", pady=(PAD, 0))
        self.sec_out.grid_columnconfigure(1, weight=1)

        self.lbl_section_out = ctk.CTkLabel(self.sec_out, text="Output", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_section_out.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.btn_select_out = ctk.CTkButton(
            self.sec_out,
            text="Choose Output\u2026",
            command=self.select_output,
            border_width=1,
            state="disabled",  # Enabled after `_verify_ffmpeg` confirms.
        )
        self.btn_select_out.grid(row=1, column=0, sticky="w")

        self.lbl_out = ctk.CTkLabel(self.sec_out, text=f'(auto: same folder, suffix "{_TRIM_SUFFIX}")', anchor="w")
        self.lbl_out.grid(row=1, column=1, padx=(10, 0), sticky="ew")

        # ********** APPLY BUTTON -OR- FFmpeg NOT FOUND BANNER **********
        if self.ffmpeg_path and self.ffprobe_path:
            self._apply_bottom = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            self._apply_bottom.pack(fill="x", side="bottom", pady=(PAD, 0))
            self._apply_bottom.grid_columnconfigure(0, weight=1)
            self.btn_apply = SpinnerButton(self._apply_bottom, text="Trim Video", command=self.apply_trim, height=40)
            self.btn_apply.grid(row=1, column=0, sticky="ew")
            self.progress_bar = ctk.CTkProgressBar(self._apply_bottom, height=4, corner_radius=4)
            self.progress_bar.grid(row=0, column=0, pady=(0, 10), sticky="ew")
            self.progress_bar.set(0)
            self.progress_bar.grid_remove()
            self._progress_anim_id: str | None = None
            self._progress_anim_current: float = 0.0
        else:
            self.btn_apply = None
            self._banner_labels: list[tuple[ctk.CTkLabel, str]] = []  # (widget, color_key)
            self._banner = ctk.CTkFrame(self.main_frame, border_width=1, corner_radius=8)
            self._banner.pack(fill="x", side="bottom", pady=(PAD, 0))
            lbl_title = ctk.CTkLabel(
                self._banner,
                text="FFmpeg is not installed or not in PATH",
                font=ctk.CTkFont(size=13, weight="bold"),
                wraplength=ww - 2 * PAD - 20,
                justify="left",
            )
            lbl_title.pack(anchor="w", padx=10, pady=(2, 0))
            self._banner_labels.append((lbl_title, "destructive_foreground"))
            lbl_desc = ctk.CTkLabel(
                self._banner,
                text="FFmpeg (and FFprobe) are required to trim video files. Please install them and restart the app.",
                wraplength=ww - 2 * PAD - 20,
                justify="left",
            )
            lbl_desc.pack(anchor="w", padx=10, pady=(4, 0))
            self._banner_labels.append((lbl_desc, "destructive_muted"))
            lbl_cmd = ctk.CTkLabel(self._banner, text="ffmpeg.org", font=resolve_mono_font(12), cursor="hand2")
            lbl_cmd.pack(anchor="w", padx=10, pady=(4, 8))
            lbl_cmd.bind("<Button-1>", lambda _: webbrowser.open("https://ffmpeg.org"))
            self._banner_labels.append((lbl_cmd, "link"))

        # Bind entry commit events:
        for entry, which in ((self.entry_start, "start"), (self.entry_end, "end")):
            entry.bind("<FocusOut>", lambda event, w=which: self._on_entry_commit(w))
            entry.bind("<Return>", lambda event, w=which: self._on_entry_commit(w))
            entry.bind("<KP_Enter>", lambda event, w=which: self._on_entry_commit(w))

        self._apply_theme()
        self.after(2000, self._poll_theme)

        # Verify FFmpeg in the background so the UI is fully rendered first:
        if self.ffmpeg_path and self.ffprobe_path and self.btn_apply:
            self.btn_apply.start(COLORS[self._current_theme]["primary_foreground"])
            threading.Thread(target=self._verify_ffmpeg, daemon=True).start()

        # Kill any in-flight index process before teardown so temp dirs can clean up:
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        # Bump generation so the strip thread's loop notices and bails:
        self._preview_generation += 1

        if (proc := self._strip_proc) is not None and proc.poll() is None:
            with suppress(Exception):
                proc.kill()
                proc.wait(timeout=2)

        self.destroy()

    # *********************** FILE SELECTION ************************

    def select_file(self) -> None:
        if not (filename := filedialog.askopenfilename(title="Select Video File", filetypes=VIDEO_FILE_TYPES)):
            return

        self.selected_file = filename
        self.duration = None
        self.fps = None
        self._start_sec = 0.0
        self._end_sec = None
        self._preview_generation += 1
        self._thumb_strip = []

        theme_colors = COLORS[self._current_theme]
        self.lbl_file.configure(text=Path(filename).name, text_color=theme_colors["foreground"])
        self.btn_select_file.start(COLORS[self._current_theme]["card_foreground"])

        # Reset previews and timeline:
        self._cancel_preview_jobs()
        self._set_preview("start", None)
        self._set_preview("end", None)
        self.lbl_strip_status.configure(text="")
        self.trim_timeline.set_range(0.0, 1.0)
        self.trim_timeline.set_enabled(False)

        threading.Thread(target=self._probe_duration, args=(filename,), daemon=True).start()

    def _probe_duration(self, filename: str) -> None:
        """Probe the file's duration and FPS via FFprobe; called in a background thread."""

        if not self.ffprobe_path:
            return

        cmd = [self.ffprobe_path, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", filename]
        duration: float | None = None
        fps: float | None = None

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, **POPEN_FLAGS)
            data = json.loads(res.stdout or "{}")

            if dur_str := data.get("format", {}).get("duration"):
                duration = float(dur_str)

            for st in data.get("streams", []):
                if st.get("codec_type") == "video":
                    if duration is None and (dur_str := st.get("duration")):
                        duration = float(dur_str)

                    # parse `r_frame_rate` or `avg_frame_rate` (format: num/den):
                    for key in {"r_frame_rate", "avg_frame_rate"}:
                        if (fr := st.get(key)) and "/" in fr:
                            with suppress(ValueError, ZeroDivisionError):
                                num, den = fr.split("/", 1)
                                candidate = float(num) / float(den)

                                if 1.0 < candidate < 500.0:
                                    fps = candidate
                                    break

                    break

        except Exception:
            duration = None

        def _done() -> None:
            self.duration = duration
            self.fps = fps
            theme_colors = COLORS[self._current_theme]

            if duration is not None:
                self._start_sec = 0.0
                self._end_sec = None
                self.trim_timeline.set_range(0.0, 1.0)
                self.trim_timeline.set_enabled(True)
                self._sync_entries()
                self._update_hint()
                self._schedule_preview("start", 0.0)
                self._schedule_preview("end", duration)
                # Kick off low-res scrub strip in background:
                gen = self._preview_generation
                threading.Thread(target=self._build_thumb_strip, args=(filename, duration, gen), daemon=True).start()
            else:
                self.lbl_file.configure(text_color=theme_colors["destructive_label"])
            self.btn_select_file.stop(state="normal")

        self.after(0, _done)

    # *********************** FRAME PREVIEWS ************************

    def _cancel_preview_jobs(self) -> None:
        for attr in {"_preview_start_job", "_preview_end_job"}:
            if job := getattr(self, attr):
                self.after_cancel(job)
                setattr(self, attr, None)
        self._preview_pending_sec = {"start": None, "end": None}
        self._preview_latest_sec = {"start": None, "end": None}

    def _schedule_preview(self, which: str, sec: float) -> None:
        """Show instant low-res strip preview, then throttle high-quality extraction."""

        if not self.selected_file or not self.ffmpeg_path:
            return

        # Cap to just before EOF; FFmpeg returns nothing if seek position >= duration:
        if self.duration is not None:
            sec = min(sec, max(0.0, self.duration - 1.0 / (self.fps or _DEFAULT_FPS)))

        # [1] Instant feedback from in-memory strip (if available):
        if (strip_img := self._strip_image_at(sec)) is not None:
            self._set_preview(which, strip_img)

        # [2] Always record the latest target so stale HD results can be discarded:
        self._preview_pending_sec[which] = sec
        self._preview_latest_sec[which] = sec

        # If a job is already scheduled, it will pick up the updated `sec` on fire:
        if getattr(self, f"_preview_{which}_job") is not None:
            return

        elapsed_ms = (time.monotonic() * 1000.0) - self._preview_last_fire_ms[which]
        delay = 0 if elapsed_ms >= _PREVIEW_DEBOUNCE_MS else int(_PREVIEW_DEBOUNCE_MS - elapsed_ms)

        setattr(self, f"_preview_{which}_job", self.after(delay, lambda: self._fire_preview(which)))

    def _fire_preview(self, which: str) -> None:
        setattr(self, f"_preview_{which}_job", None)
        sec = self._preview_pending_sec.get(which)
        if sec is None or not self.selected_file or not self.ffmpeg_path:
            return
        self._preview_pending_sec[which] = None
        self._preview_last_fire_ms[which] = time.monotonic() * 1000.0
        self._load_preview_async(which, sec, self.selected_file)

    def _load_preview_async(self, which: str, sec: float, video_path: str) -> None:
        generation = self._preview_generation

        def _worker() -> None:
            img = self._extract_frame(video_path, sec)

            def _apply() -> None:
                # Discard if file changed or user has scrubbed to a new position since:
                if self._preview_generation != generation:
                    return
                if self._preview_latest_sec.get(which) != sec:
                    return
                if img is not None:
                    self._set_preview(which, img)

            self.after(0, _apply)

        threading.Thread(target=_worker, daemon=True).start()

    def _extract_frame(self, video_path: str, sec: float) -> Image.Image | None:
        """Extract a single video frame at `sec` seconds; returns PIL Image or None."""

        if not self.ffmpeg_path:
            return None

        cmd = [
            self.ffmpeg_path,
            "-ss",
            f"{max(0.0, sec):.6f}",
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-vf",
            (
                f"scale={_THUMB_W}:{_THUMB_H}:force_original_aspect_ratio=decrease:flags=lanczos,"
                f"pad={_THUMB_W}:{_THUMB_H}:({_THUMB_W}-iw)/2:({_THUMB_H}-ih)/2"
            ),
            "-f",
            "image2pipe",
            "-vcodec",
            "mjpeg",
            "pipe:1",
        ]

        with suppress(Exception):
            res = subprocess.run(cmd, capture_output=True, timeout=10, **POPEN_FLAGS)
            if res.returncode == 0 and res.stdout:
                return Image.open(io.BytesIO(res.stdout)).copy()

        return None

    # ************************* SCRUB STRIP *************************

    def _build_thumb_strip(self, video_path: str, duration: float, generation: int) -> None:
        """Background: extract `_STRIP_COUNT` evenly-spaced low-res frames in a single ffmpeg pass."""

        if not self.ffmpeg_path or duration <= 0:
            return

        count = max(2, _STRIP_COUNT)
        rate = count / duration  # Frames per second to sample.

        self.after(0, lambda: self._set_strip_status("indexing", 0.0, generation))

        with tempfile.TemporaryDirectory(prefix="vt_strip_", ignore_cleanup_errors=True) as td:
            cmd = [
                self.ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-i",
                video_path,
                "-vf",
                (
                    f"fps={rate:.6f},"
                    f"scale={_STRIP_W}:{_STRIP_H}:force_original_aspect_ratio=decrease:flags=fast_bilinear,"
                    f"pad={_STRIP_W}:{_STRIP_H}:({_STRIP_W}-iw)/2:({_STRIP_H}-ih)/2"
                ),
                self._fps_mode_flag,
                "vfr",
                "-q:v",
                "6",
                "-frames:v",
                str(count),
                str(Path(td) / "f%05d.jpg"),
            ]

            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **POPEN_FLAGS,
                )
                self._strip_proc = proc
            except Exception:
                self.after(0, lambda: self._set_strip_status("error", 0.0, generation))
                return

            assert proc.stdout is not None
            for line in proc.stdout:
                if self._preview_generation != generation:
                    proc.kill()
                    self._strip_proc = None
                    return
                if "=" not in (line := line.strip()):
                    continue
                key, _, val = line.partition("=")
                if key == "out_time_us" and val.lstrip("-").isdigit():
                    elapsed = max(0, int(val)) / 1_000_000.0
                    frac = max(0.0, min(0.99, elapsed / duration))
                    self.after(0, lambda progress_frac=frac: self._set_strip_status("indexing", progress_frac, generation))

            proc.wait()
            self._strip_proc = None

            # Abort if user already switched files:
            if self._preview_generation != generation:
                return

            strip: list[Image.Image] = []
            for frame_file in sorted(Path(td).glob("f*.jpg")):
                with suppress(Exception), Image.open(frame_file) as im:
                    strip.append(im.copy())

        if not strip:
            self.after(0, lambda: self._set_strip_status("error", 0.0, generation))
            return

        def _apply() -> None:
            if self._preview_generation != generation:
                return
            self._thumb_strip = strip
            self._thumb_strip_generation = generation
            self._set_strip_status("ready", 1.0, generation)

        self.after(0, _apply)

    def _set_strip_status(self, state: str, frac: float, generation: int) -> None:
        """Update the small indexing indicator. `state` is 'idle' | 'indexing' | 'ready' | 'error'."""

        if generation != self._preview_generation:
            return

        theme_colors = COLORS[self._current_theme]
        if state == "indexing":
            self.lbl_strip_status.configure(
                text=f"Indexing\u2026 {int(frac * 100)}%",
                text_color=theme_colors["placeholder_foreground"],
            )
        elif state == "ready":
            self.lbl_strip_status.configure(text="Ready", text_color=theme_colors["placeholder_foreground"])
        elif state == "error":
            self.lbl_strip_status.configure(text="Index failed", text_color=theme_colors["destructive_label"])
        else:
            self.lbl_strip_status.configure(text="", text_color=theme_colors["placeholder_foreground"])

    def _strip_image_at(self, sec: float) -> Image.Image | None:
        """Return the nearest low-res strip thumbnail for `sec`, upscaled to display size."""

        if not self._thumb_strip or self.duration is None or self.duration <= 0:
            return None
        if self._thumb_strip_generation != self._preview_generation:
            return None

        n = len(self._thumb_strip)
        idx = int(sec / self.duration * n)
        idx = max(0, min(n - 1, idx))

        return self._thumb_strip[idx].resize((_THUMB_W, _THUMB_H), Image.Resampling.BILINEAR)

    def _set_preview(self, which: str, img: Image.Image | None) -> None:
        """Update a thumbnail widget; `which` is 'start' or 'end'."""

        lbl = self.lbl_start_thumb if which == "start" else self.lbl_end_thumb
        theme_colors = COLORS[self._current_theme]

        if img is None:
            setattr(self, f"_{which}_preview_image", None)
            # Clear the underlying `tk.Label` image first to prevent `TclError` from stale `PhotoImage` refs:
            with suppress(Exception):
                lbl._label.configure(image="")
            lbl.configure(
                image=None,
                text="Start\nframe" if which == "start" else "End\nframe",
                text_color=theme_colors["placeholder_foreground"],
            )
            return

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        setattr(self, f"_{'start' if which == 'start' else 'end'}_preview_image", ctk_img)
        lbl.configure(image=ctk_img, text="")
        lbl.place(relx=0.5, rely=0.5, anchor="center")

    # ******************** TIMELINE INTERACTIONS ********************

    def _on_timeline_change(self, start_frac: float, end_frac: float) -> None:
        """Called continuously while the timeline handle is being dragged."""

        if self.duration is None:
            return

        prev_start = self._start_sec
        prev_end = self._end_sec if self._end_sec is not None else self.duration

        self._start_sec = start_frac * self.duration
        new_end = end_frac * self.duration
        self._end_sec = new_end if new_end < self.duration - 0.05 else None

        self._sync_entries()

        # Live-update previews while dragging (debounced in `_schedule_preview`):
        cur_end = self._end_sec if self._end_sec is not None else self.duration
        if self._start_sec != prev_start:
            self._schedule_preview("start", self._start_sec)
        if cur_end != prev_end:
            self._schedule_preview("end", cur_end)

    def _on_timeline_commit(self, start_frac: float, end_frac: float) -> None:
        """Called once when the timeline handle is released."""

        if self.duration is None:
            return

        self._start_sec = start_frac * self.duration
        new_end = end_frac * self.duration
        self._end_sec = new_end if new_end < self.duration - 0.05 else None

        self._sync_entries()
        self._schedule_preview("start", self._start_sec)
        self._schedule_preview("end", self._end_sec if self._end_sec is not None else self.duration)

    # ********************* ENTRY INTERACTIONS **********************

    def _on_entry_commit(self, which: str) -> None:
        """Parse the entry and update internal state; revert on invalid input."""

        entry = self.entry_start if which == "start" else self.entry_end
        val = entry.get().strip()

        if not val:
            if which == "start":
                self._start_sec = 0.0
            else:
                self._end_sec = None
            self._sync_entries()
            self._sync_timeline()
            return

        sec: float | None = None
        if self._input_mode == "frame":
            fps = self.fps or _DEFAULT_FPS
            with suppress(ValueError):
                sec = frame_to_time(int(val), fps)
        else:
            sec = parse_time(val)

        if sec is None:
            self._sync_entries()  # Revert to last valid value.
            return

        sec = max(0.0, sec)
        if self.duration is not None:
            sec = min(sec, self.duration)

        if which == "start":
            self._start_sec = sec
        else:
            self._end_sec = sec if (self.duration is None or sec < self.duration - 0.05) else None

        self._sync_entries()
        self._sync_timeline()
        self._schedule_preview(which, sec)

    def _step_time(self, which: str, direction: int) -> None:
        """Increment or decrement the start or end by exactly one frame."""

        if not self.selected_file:
            return

        fps = self.fps or _DEFAULT_FPS
        step = 1.0 / fps

        current = (
            self._start_sec if which == "start" else (self._end_sec if self._end_sec is not None else (self.duration or 0.0))
        )

        new_sec = max(0.0, current + direction * step)
        if self.duration is not None:
            new_sec = min(new_sec, self.duration)

        if which == "start":
            self._start_sec = new_sec
            if self._end_sec is not None and self._start_sec >= self._end_sec:
                self._start_sec = max(0.0, self._end_sec - step)
        else:
            self._end_sec = new_sec if (self.duration is None or new_sec < self.duration - step * 0.5) else None
            if self._end_sec is not None and self._end_sec <= self._start_sec:
                self._end_sec = self._start_sec + step

        self._sync_entries()
        self._sync_timeline()
        self._schedule_preview(which, new_sec)

    def _on_mode_change(self, value: str) -> None:
        self._input_mode = "frame" if value == "Frame" else "time"
        self._update_hint()
        self._sync_entries()

    # ************************* STATE SYNC **************************

    def _sync_entries(self) -> None:
        """Repopulate the entry widgets from `_start_sec` / `_end_sec`."""

        if not self.selected_file:
            return

        fps = self.fps or _DEFAULT_FPS
        effective_end = self._end_sec if self._end_sec is not None else self.duration

        if self._input_mode == "frame":
            start_text = str(time_to_frame(self._start_sec, fps)) if self.selected_file else ""
            end_text = str(time_to_frame(effective_end, fps)) if effective_end is not None else ""
        else:
            start_text = format_time(self._start_sec) if self.selected_file else ""
            end_text = format_time(effective_end) if effective_end is not None else ""

        for entry, text in ((self.entry_start, start_text), (self.entry_end, end_text)):
            entry.delete(0, "end")
            if text:
                entry.insert(0, text)

    def _sync_timeline(self) -> None:
        """Update the timeline widget from `_start_sec` / `_end_sec`."""

        if self.duration:
            start_frac = self._start_sec / self.duration
            end_frac = (self._end_sec / self.duration) if self._end_sec is not None else 1.0
            self.trim_timeline.set_range(start_frac, end_frac)

    def _update_hint(self) -> None:
        if self._input_mode == "frame":
            if self.fps:
                hint = f"Frame number  (at {self.fps:.3f} fps)"
            else:
                hint = f"Frame number  (FPS unknown, assuming {_DEFAULT_FPS:.0f})"

            self.entry_start.configure(placeholder_text="0")
            self.entry_end.configure(placeholder_text="last frame")

        else:
            hint = "Format: SS, MM:SS or HH:MM:SS  (decimals allowed, e.g., 1:23.5)"
            self.entry_start.configure(placeholder_text="00:00")
            self.entry_end.configure(placeholder_text="end of file")

        self.lbl_hint.configure(text=hint)

    # *********************** OUTPUT & RESET ************************

    def select_output(self) -> None:
        initial_dir: str | None = None
        initial_file: str | None = None

        if self.selected_file:
            file_path = Path(self.selected_file)
            initial_dir = str(file_path.parent)
            initial_file = f"{file_path.stem}{_TRIM_SUFFIX}{file_path.suffix}"

        path = filedialog.asksaveasfilename(
            title="Save Trimmed Video As",
            initialdir=initial_dir,
            initialfile=initial_file,
            defaultextension=Path(self.selected_file).suffix if self.selected_file else ".mp4",
            filetypes=VIDEO_FILE_TYPES,
        )
        if not path:
            return

        self.output_path = path
        theme_colors = COLORS[self._current_theme]
        self.lbl_out.configure(text=Path(path).name, text_color=theme_colors["foreground"])

    def reset_all(self) -> None:
        """Clear all fields and return the UI to its initial state."""

        self._start_sec = 0.0
        self._end_sec = None
        self.selected_file = None
        self.duration = None
        self.fps = None
        self.output_path = None

        self._preview_generation += 1
        self._thumb_strip = []
        self._cancel_preview_jobs()

        self.entry_start.delete(0, "end")
        self.entry_end.delete(0, "end")

        theme_colors = COLORS[self._current_theme]
        self.lbl_file.configure(text="No file selected", text_color=theme_colors["placeholder_foreground"])
        self.btn_select_file.stop(state="normal")
        self.lbl_out.configure(
            text=f'(auto: same folder, suffix "{_TRIM_SUFFIX}")', text_color=theme_colors["placeholder_foreground"]
        )

        self._set_preview("start", None)
        self._set_preview("end", None)
        self.lbl_strip_status.configure(text="")
        self.trim_timeline.set_range(0.0, 1.0)
        self.trim_timeline.set_enabled(False)

    # *************************** THEMING ***************************

    def _apply_theme(self) -> None:
        self._current_theme = get_system_theme()
        theme_colors: dict[str, str] = dict(COLORS[self._current_theme])

        ctk.set_appearance_mode(self._current_theme)
        self.configure(fg_color=theme_colors["background"])

        self.main_frame.configure(fg_color=theme_colors["background"])
        self.sec_file.configure(fg_color=theme_colors["background"])
        self.sec_trim.configure(fg_color=theme_colors["background"])
        self.trim_header.configure(fg_color=theme_colors["background"])
        self.sec_preview.configure(fg_color=theme_colors["background"])
        self.sec_inputs.configure(fg_color=theme_colors["background"])
        self.sec_out.configure(fg_color=theme_colors["background"])

        self.lbl_section_file.configure(text_color=theme_colors["foreground"])
        self.lbl_section_trim.configure(text_color=theme_colors["foreground"])
        self.lbl_section_out.configure(text_color=theme_colors["foreground"])

        self.lbl_start.configure(text_color=theme_colors["muted_foreground"])
        self.lbl_end.configure(text_color=theme_colors["muted_foreground"])
        self.lbl_hint.configure(text_color=theme_colors["muted_foreground"])

        self.lbl_file.configure(
            text_color=theme_colors["foreground"] if self.selected_file else theme_colors["placeholder_foreground"]
        )
        self.lbl_out.configure(
            text_color=theme_colors["foreground"] if self.output_path else theme_colors["placeholder_foreground"]
        )

        # Preview thumbnails:
        for frame in (self.frame_start_thumb, self.frame_end_thumb):
            frame.configure(fg_color=theme_colors["background"], border_color=theme_colors["border"])
        for lbl in (self.lbl_start_thumb, self.lbl_end_thumb):
            lbl.configure(text_color=theme_colors["placeholder_foreground"], fg_color="transparent")

        # Mode toggle:
        self.mode_toggle.configure(
            fg_color=theme_colors["background"],
            border_color=theme_colors["secondary_border"],
            selected_color=theme_colors["primary"],
            selected_hover_color=theme_colors["primary_hover"],
            selected_text_color=theme_colors["primary_foreground"],
            unselected_color=theme_colors["background"],
            unselected_hover_color=theme_colors["secondary_hover"],
            text_color=theme_colors["foreground"],
        )

        # Timeline:
        self.trim_timeline.apply_colors(theme_colors)

        # Stepper buttons:
        chevron_left = render_svg_icon("chevron-left", 14, theme_colors["muted_foreground"])
        chevron_right = render_svg_icon("chevron-right", 14, theme_colors["muted_foreground"])
        for btn, icon in (
            (self.btn_start_left, chevron_left),
            (self.btn_start_right, chevron_right),
            (self.btn_end_left, chevron_left),
            (self.btn_end_right, chevron_right),
        ):
            btn.configure(
                fg_color=theme_colors["secondary"],
                hover_color=theme_colors["secondary_hover"],
                border_color=theme_colors["secondary_border"],
                text_color=theme_colors["muted_foreground"],
                image=icon,
            )

        self.btn_select_file.configure(
            fg_color=theme_colors["card"], hover_color=theme_colors["card_hover"], text_color=theme_colors["card_foreground"]
        )
        self.btn_select_out.configure(
            fg_color=theme_colors["secondary"],
            hover_color=theme_colors["secondary_hover"],
            border_color=theme_colors["secondary_border"],
            text_color=theme_colors["secondary_foreground"],
        )
        self.btn_reset_all.configure(
            width=28,
            height=28,
            image=render_svg_icon("refresh-ccw", 16, theme_colors["muted_foreground"]),
            fg_color="transparent",
            hover_color=theme_colors["secondary_hover"],
        )

        for entry in (self.entry_start, self.entry_end):
            entry.configure(
                fg_color=theme_colors["background"],
                border_color=theme_colors["secondary_border"],
                text_color=theme_colors["foreground"],
                placeholder_text_color=theme_colors["placeholder_foreground"],
            )

        if self.btn_apply:
            self.btn_apply.configure(
                fg_color=theme_colors["primary"],
                hover_color=theme_colors["primary_hover"],
                text_color=theme_colors["primary_foreground"],
            )
        if hasattr(self, "progress_bar"):
            self.progress_bar.configure(
                fg_color=theme_colors["secondary_hover"], progress_color=theme_colors["placeholder_foreground"]
            )

        if hasattr(self, "_banner"):
            self._banner.configure(fg_color=theme_colors["destructive"], border_color=theme_colors["destructive_border"])
            for lbl, key in self._banner_labels:
                lbl.configure(text_color=theme_colors[key])

    def _verify_ffmpeg(self) -> None:
        """Verify FFmpeg and FFprobe run; called in a background thread."""

        ok = False
        fps_mode_flag = "-fps_mode"
        if self.ffmpeg_path and self.ffprobe_path:
            try:
                subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, timeout=5, check=True, **POPEN_FLAGS)
                subprocess.run([self.ffprobe_path, "-version"], capture_output=True, timeout=5, check=True, **POPEN_FLAGS)
                ok = True
            except Exception:
                ok = False

        if ok and self.ffmpeg_path:
            with suppress(Exception):
                res = subprocess.run([self.ffmpeg_path, "-fps_mode"], capture_output=True, text=True, timeout=5, **POPEN_FLAGS)
                if "Unrecognized option 'fps_mode'" in res.stderr:
                    fps_mode_flag = "-vsync"

        def _done() -> None:
            if not ok:
                self.ffmpeg_path = None
                self.ffprobe_path = None
            else:
                self._fps_mode_flag = fps_mode_flag

            state = "normal" if ok else "disabled"
            self.btn_select_file.configure(state=state)
            self.btn_select_out.configure(state=state)

            if self.btn_apply:
                self.btn_apply.stop(state=state)

        self.after(0, _done)

    def _poll_theme(self) -> None:
        if get_system_theme() != self._current_theme:
            self._apply_theme()
        self.after(2000, self._poll_theme)

    # ************************** TRIMMING ***************************

    def _animate_progress_to(self, target: float) -> None:
        """Ease-out animate the progress bar toward `target` at ~60 fps."""

        if not hasattr(self, "progress_bar"):
            return
        if self._progress_anim_id:
            self.after_cancel(self._progress_anim_id)
            self._progress_anim_id = None

        STEP_MS: int = 16
        EASE: float = 0.25
        SNAP: float = 0.005

        def _step() -> None:
            if abs(remaining := target - self._progress_anim_current) < SNAP:
                self.progress_bar.set(target)
                self._progress_anim_current = target
                self._progress_anim_id = None
                return

            self._progress_anim_current += remaining * EASE
            self.progress_bar.set(self._progress_anim_current)
            self._progress_anim_id = self.after(STEP_MS, _step)

        _step()

    def apply_trim(self) -> None:  # ruff:ignore[complex-structure]
        if not self.ffmpeg_path:
            return
        if not self.selected_file:
            messagebox.showwarning("No File", "Please select a video file first.")
            return
        if self._trimming:
            return

        # Parse current entry values (handles uncommitted changes):
        start_str = self.entry_start.get().strip()
        end_str = self.entry_end.get().strip()

        start_s: float = 0.0
        if start_str:
            if self._input_mode == "frame":
                fps = self.fps or _DEFAULT_FPS
                try:
                    start_s = frame_to_time(int(start_str), fps)
                except (ValueError, TypeError):
                    messagebox.showerror("Invalid Start", f'Cannot parse start frame: "{start_str}"')
                    return
            else:
                if (parsed := parse_time(start_str)) is None:
                    messagebox.showerror("Invalid Start", f'Cannot parse start time: "{start_str}"')
                    return
                start_s = parsed

        end_s: float | None = None
        if end_str:
            if self._input_mode == "frame":
                fps = self.fps or _DEFAULT_FPS
                try:
                    end_s = frame_to_time(int(end_str), fps)
                except (ValueError, TypeError):
                    messagebox.showerror("Invalid End", f'Cannot parse end frame: "{end_str}"')
                    return
            else:
                if (parsed := parse_time(end_str)) is None:
                    messagebox.showerror("Invalid End", f'Cannot parse end time: "{end_str}"')
                    return
                end_s = parsed

        if end_s is not None and end_s <= start_s:
            messagebox.showerror("Invalid Range", "End time must be greater than start time.")
            return

        if self.duration is not None:
            if start_s >= self.duration:
                messagebox.showerror("Invalid Range", "Start time is past the end of the file.")
                return
            if end_s is not None and end_s > self.duration + 0.5:
                messagebox.showerror("Invalid Range", "End time is past the end of the file.")
                return

        # Resolve output path:
        if self.output_path:
            out_path = self.output_path
        else:
            file_path = Path(self.selected_file)
            out_path = str(file_path.with_name(f"{file_path.stem}{_TRIM_SUFFIX}{file_path.suffix}"))

        if Path(out_path).resolve() == Path(self.selected_file).resolve():
            messagebox.showerror("Invalid Output", "Output path must differ from the input file.")
            return

        if Path(out_path).exists() and not messagebox.askokcancel(
            "Overwrite?",
            f'"{Path(out_path).name}" already exists.\n\nOverwrite this file?',
            icon="warning",
        ):
            return

        clip_total: float | None = None
        if end_s is not None:
            clip_total = end_s - start_s
        elif self.duration is not None:
            clip_total = self.duration - start_s

        self._trimming = True

        if self.btn_apply:
            self.btn_apply.start(COLORS[self._current_theme]["primary_foreground"])

        if hasattr(self, "progress_bar"):
            if self._progress_anim_id:
                self.after_cancel(self._progress_anim_id)
            self._progress_anim_id = None
            self._progress_anim_current = 0.0
            self.progress_bar.set(0)
            self.progress_bar.grid()

        def _on_progress(frac: float) -> None:
            self.after(0, lambda progress_frac=frac: self._animate_progress_to(progress_frac))

        def _on_done(ok: bool, err: str | None) -> None:

            def _apply() -> None:
                self._trimming = False
                if self.btn_apply:
                    self.btn_apply.stop(state="normal")
                if hasattr(self, "progress_bar"):
                    if self._progress_anim_id:
                        self.after_cancel(self._progress_anim_id)
                        self._progress_anim_id = None
                    self.progress_bar.grid_remove()
                if ok:
                    messagebox.showinfo("Success", f"Saved trimmed video to:\n{out_path}")
                else:
                    messagebox.showerror("FFmpeg Error", f"Failed to trim video:\n{err or 'Unknown error'}")

            self.after(0, _apply)

        TrimExporter(self.ffmpeg_path, self.ffprobe_path).export(
            src=self.selected_file,
            dst=out_path,
            start_s=start_s,
            end_s=end_s,
            clip_total=clip_total,
            on_progress=_on_progress,
            on_done=_on_done,
        )


if __name__ == "__main__":
    ctk.set_appearance_mode(get_system_theme())
    ctk.set_default_color_theme("blue")

    # On Windows, set the app user model ID before creating the window so the
    # taskbar groups the app under its own icon rather than the Python interpreter:
    if sys.platform == "win32":
        with suppress(Exception):
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VideoTrimmer.app")

    app = VideoTrimmerApp()

    try:
        app.mainloop()
    except KeyboardInterrupt:
        app.destroy()

    # Clean up temp files:
    if app._temp_ico_path and app._temp_ico_path.exists():
        app._temp_ico_path.unlink()
