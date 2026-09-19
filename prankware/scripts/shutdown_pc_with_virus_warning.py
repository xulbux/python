import subprocess
import sys
import time


def shutdown(message: str = "WARNING: Virus detected. Starting system cleanup process...", delay: int = 5) -> None:
    """Trigger a system shutdown with an alarming warning message across supported operating systems."""

    if sys.platform == "win32":
        subprocess.run(["shutdown", "/s", "/f", "/t", str(delay), "/c", message])
    elif sys.platform in {"darwin", "linux"}:
        subprocess.run(["sudo", "shutdown", "-h", f"+{delay // 60}", message])
    else:
        print(f"Shutdown not supported on this OS: {sys.platform}")
    time.sleep(delay)


if __name__ == "__main__":
    shutdown()
