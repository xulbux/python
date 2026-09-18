#!/usr/bin/env python3
# x-cmds:file[update]

"""
Get detailed hardware information about your PC.
"""

import platform
import re
import subprocess
import sys
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypedDict
import xulbux as xx
from xulbux import ArgumentParser, S

# Make the `_shared` package (commands/_shared) importable when running this script directly:
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _shared.helpers import format_size

if TYPE_CHECKING:
    from ._shared.helpers import format_size  # ruff:ignore[runtime-import-in-type-checking-block]

    import psutil
    from xulbux.ansi import Renderable

# Check if psutil is available (may fail on Python 3.14):
try:
    import psutil

    PSUTIL_AVAILABLE: bool = True
    PSUTIL_ERROR: str | None = None

except (ImportError, ModuleNotFoundError) as exc:
    PSUTIL_AVAILABLE: bool = False  # pyright:ignore[reportConstantRedefinition]
    PSUTIL_ERROR: str | None = str(exc)  # pyright:ignore[reportConstantRedefinition]


class AdapterInfo(TypedDict):
    name: str
    is_up: bool
    speed: str | None
    mac: str | None


class HardwareInfo:
    def __init__(self) -> None:
        self.system: dict[str, Any] = {}
        self.cpu: dict[str, Any] = {}
        self.memory: dict[str, Any] = {}
        self.disk: dict[str, Any] = {}
        self.gpu: dict[str, Any] = {}
        self.network: dict[str, Any] = {}
        self.battery: dict[str, Any] = {}

    def _get_system_info(self) -> dict[str, Any]:
        """Get basic system information."""

        info: dict[str, Any] = {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "platform": platform.platform(),
        }
        return info

    def _get_cpu_info(self) -> dict[str, Any]:
        """Get CPU information."""

        info: dict[str, Any] = {
            "processor": platform.processor(),
            "physical_cores": None,
            "logical_cores": None,
            "frequency": None,
            "max_frequency": None,
            "cpu_usage": None,
        }

        if PSUTIL_AVAILABLE:
            info["physical_cores"] = psutil.cpu_count(logical=False)
            info["logical_cores"] = psutil.cpu_count(logical=True)

            cpu_freq = psutil.cpu_freq()
            if cpu_freq:
                info["frequency"] = f"{cpu_freq.current:.2f} MHz"
                info["max_frequency"] = f"{cpu_freq.max:.2f} MHz"

            info["cpu_usage"] = f"{psutil.cpu_percent(interval=1)}%"
            info["per_core_usage"] = [f"{x}%" for x in psutil.cpu_percent(interval=1, percpu=True)]

        return info

    def _get_memory_info(self) -> dict[str, Any]:
        """Get memory information."""

        info: dict[str, Any] = {"total": None, "available": None, "used": None, "usage_percent": None}

        if PSUTIL_AVAILABLE:
            mem = psutil.virtual_memory()
            info["total"] = format_size(mem.total)
            info["available"] = format_size(mem.available)
            info["used"] = format_size(mem.used)
            info["usage_percent"] = f"{mem.percent}%"

            swap = psutil.swap_memory()
            info["swap_total"] = format_size(swap.total)
            info["swap_used"] = format_size(swap.used)
            info["swap_percent"] = f"{swap.percent}%"

        return info

    def _get_disk_info(self) -> dict[str, Any]:
        """Get disk information."""

        info: dict[str, Any] = {"partitions": [], "total_size": None, "total_used": None, "total_free": None}

        if PSUTIL_AVAILABLE:
            partitions = psutil.disk_partitions()

            total_size = 0
            total_used = 0
            total_free = 0

            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    partition_info = {
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "filesystem": partition.fstype,
                        "total": format_size(usage.total),
                        "used": format_size(usage.used),
                        "free": format_size(usage.free),
                        "usage_percent": f"{usage.percent}%",
                    }

                    total_size += usage.total
                    total_used += usage.used
                    total_free += usage.free

                    info["partitions"].append(partition_info)
                except (PermissionError, OSError):
                    continue

            info["total_size"] = format_size(total_size)
            info["total_used"] = format_size(total_used)
            info["total_free"] = format_size(total_free)

        return info

    def _get_gpu_info(self) -> dict[str, Any]:  # ruff:ignore[complex-structure]
        """Get GPU information."""

        info: dict[str, Any] = {"gpus": []}

        system = platform.system()

        if system == "Windows":
            with suppress(Exception):
                result = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")[1:]
                    for line in lines:
                        gpu_name = line.strip()
                        if gpu_name:
                            info["gpus"].append({"name": gpu_name})

        elif system == "Linux":
            with suppress(Exception):
                # Try `lspci` for GPU info:
                result = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split("\n"):
                        if "VGA" in line or "3D" in line or "Display" in line:
                            match = re.search(r": (.+)$", line)
                            if match:
                                info["gpus"].append({"name": match.group(1).strip()})

        elif system == "Darwin":  # macOS
            with suppress(Exception):
                result = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.split("\n")
                    for line in lines:
                        if "Chipset Model:" in line:
                            gpu_name = line.split(":", 1)[1].strip()
                            info["gpus"].append({"name": gpu_name})

        return info

    def _get_network_info(self) -> dict[str, Any]:
        """Get network adapter information."""

        info: dict[str, Any] = {"adapters": []}

        if PSUTIL_AVAILABLE:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            for interface_name in stats:
                if interface_name in addrs:
                    adapter_info: AdapterInfo = {
                        "name": interface_name,
                        "is_up": stats[interface_name].isup,
                        "speed": f"{stats[interface_name].speed} Mbps" if stats[interface_name].speed > 0 else "Unknown",
                        "mac": None,
                    }

                    # Get MAC address:
                    for addr in addrs[interface_name]:
                        if addr.family.name == "AF_LINK" or addr.family.name == "AF_PACKET":  # pyright:ignore[reportUnnecessaryComparison]
                            adapter_info["mac"] = addr.address
                            break

                    info["adapters"].append(adapter_info)

        return info

    def _get_battery_info(self) -> dict[str, Any]:
        """Get battery information (for laptops)."""

        info: dict[str, Any] = {"has_battery": False, "percent": None, "power_plugged": None, "time_left": None}

        if PSUTIL_AVAILABLE:
            with suppress(AttributeError):
                if battery := psutil.sensors_battery():  # pyright:ignore[reportUnknownMemberType,reportUnknownVariableType]
                    info["has_battery"] = True
                    info["percent"] = f"{battery.percent}%"  # pyright:ignore[reportUnknownMemberType]
                    info["power_plugged"] = battery.power_plugged  # pyright:ignore[reportUnknownMemberType]
                    if battery.secsleft != psutil.POWER_TIME_UNLIMITED and battery.secsleft > 0:  # pyright:ignore[reportUnknownMemberType]
                        hours = battery.secsleft // 3600  # pyright:ignore[reportUnknownMemberType,reportUnknownVariableType]
                        minutes = (battery.secsleft % 3600) // 60  # pyright:ignore[reportUnknownMemberType,reportUnknownVariableType]
                        info["time_left"] = f"{hours}h {minutes}m"

        return info

    def gather_info(self) -> None:
        """Gather all hardware information."""

        if not PSUTIL_AVAILABLE:
            S(
                "\n",
                (S.BOLD | S.BR.YELLOW)("⚠ Library psutil failed to initialize - some hardware info will be missing!"),
                "\n  ",
                S.DIM("This is likely due to incompatibility with your Python version."),
                "\n",
            ).print()

        xx.console.info("Gathering hardware information...", start="\n")

        self.system = self._get_system_info()
        self.cpu = self._get_cpu_info()
        self.memory = self._get_memory_info()
        self.disk = self._get_disk_info()
        self.gpu = self._get_gpu_info()
        self.network = self._get_network_info()
        self.battery = self._get_battery_info()

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Convert hardware info to dictionary."""

        result: dict[str, dict[str, Any]] = {}
        if self.system:
            result["system"] = self.system
        if self.cpu:
            result["cpu"] = self.cpu
        if self.memory:
            result["memory"] = self.memory
        if self.disk:
            result["disk"] = self.disk
        if self.gpu:
            result["gpu"] = self.gpu
        if self.network:
            result["network"] = self.network
        if self.battery and self.battery.get("has_battery"):
            result["battery"] = self.battery
        return result

    def display(self) -> None:  # ruff:ignore[complex-structure]
        """Display hardware information in formatted output."""

        print()

        # System info:
        if self.system:
            (S.BOLD | S.BR.GREEN)("\nSystem Information").print()
            system_text: list[Renderable] = []
            if self.system.get("os"):
                system_text.append(
                    S(S.BOLD("          OS"), " : ", S.BR.WHITE(f"{self.system['os']} {self.system.get('os_release', '')}"))
                )
            if self.system.get("os_version"):
                system_text.append(S(S.BOLD("     Version"), " : ", S.BR.WHITE(str(self.system["os_version"]))))
            if self.system.get("architecture"):
                system_text.append(S(S.BOLD("Architecture"), " : ", S.BR.WHITE(str(self.system["architecture"]))))
            if self.system.get("hostname"):
                system_text.append(S(S.BOLD("    Hostname"), " : ", S.BR.WHITE(str(self.system["hostname"]))))
            xx.console.box(*system_text, border_style=S.BR.GREEN)

        # CPU info:
        if self.cpu:
            (S.BOLD | S.BR.CYAN)("\nCPU Information").print()
            cpu_text: list[Renderable] = []
            if self.cpu.get("processor"):
                prefix = "     " if PSUTIL_AVAILABLE else ""
                cpu_text.append(S(S.BOLD(f"{prefix}Processor"), " : ", S.BR.WHITE(str(self.cpu["processor"]))))
            if self.cpu.get("physical_cores"):
                cpu_text.append(S(S.BOLD("Physical Cores"), " : ", S.BR.WHITE(str(self.cpu["physical_cores"]))))
            if self.cpu.get("logical_cores"):
                cpu_text.append(S(S.BOLD(" Logical Cores"), " : ", S.BR.WHITE(str(self.cpu["logical_cores"]))))
            if self.cpu.get("frequency"):
                cpu_text.append(S(S.BOLD("     Frequency"), " : ", S.BR.WHITE(str(self.cpu["frequency"]))))
            if self.cpu.get("max_frequency"):
                cpu_text.append(S(S.BOLD(" Max Frequency"), " : ", S.BR.WHITE(str(self.cpu["max_frequency"]))))
            if self.cpu.get("cpu_usage"):
                cpu_text.append(S(S.BOLD("     CPU Usage"), " : ", S.BR.WHITE(str(self.cpu["cpu_usage"]))))
            if self.cpu.get("per_core_usage"):
                cpu_text.append("{hr}")
                cores = self.cpu["per_core_usage"]
                formatted_cores: list[Renderable] = [
                    S.BR.WHITE(", ".join(cores[i : i + 10])) for i in range(0, len(cores), 10)
                ]
                cpu_text.append(S((S.BOLD | S.BR.CYAN)("Per-Core Usage\n"), S("\n").join(formatted_cores)))
            xx.console.box(*cpu_text, border_style=S.BR.CYAN)

        # GPU info:
        if self.gpu and self.gpu.get("gpus"):
            (S.BOLD | S.BR.BLUE)("\nGPU Information").print()
            gpu_text: list[Renderable] = []
            for i, gpu in enumerate(self.gpu["gpus"]):
                if i > 0:
                    gpu_text.append("{hr}")
                gpu_text.append(S(S.BOLD(f"GPU {i + 1}"), " : ", S.BR.WHITE(str(gpu["name"]))))
            xx.console.box(*gpu_text, border_style=S.BR.BLUE)

        # Memory info:
        if self.memory:
            (S.BOLD | S.MAGENTA)("\nMemory Information").print()
            mem_text: list[Renderable] = []
            if self.memory.get("total"):
                mem_text.append(S(S.BOLD("     Total"), " : ", S.BR.WHITE(str(self.memory["total"]))))
            if self.memory.get("available"):
                mem_text.append(S(S.BOLD(" Available"), " : ", S.BR.WHITE(str(self.memory["available"]))))
            if self.memory.get("used"):
                mem_text.append(S(S.BOLD("      Used"), " : ", S.BR.WHITE(str(self.memory["used"]))))
            if self.memory.get("usage_percent"):
                mem_text.append(S(S.BOLD("     Usage"), " : ", S.BR.WHITE(str(self.memory["usage_percent"]))))
            if self.memory.get("swap_total"):
                mem_text.append(S(S.BOLD("Swap Total"), " : ", S.BR.WHITE(str(self.memory["swap_total"]))))
            if self.memory.get("swap_used"):
                mem_text.append(S(S.BOLD(" Swap Used"), " : ", S.BR.WHITE(str(self.memory["swap_used"]))))
            if self.memory.get("swap_percent"):
                mem_text.append(S(S.BOLD("Swap Usage"), " : ", S.BR.WHITE(str(self.memory["swap_percent"]))))
            xx.console.box(*mem_text, border_style=S.MAGENTA)

        # Disk info:
        if self.disk:
            (S.BOLD | S.BR.MAGENTA)("\nDisk Information").print()
            disk_text: list[Renderable] = []
            if self.disk.get("total_size"):
                disk_text.append(S(S.BOLD("Total Size"), " : ", S.BR.WHITE(str(self.disk["total_size"]))))
            if self.disk.get("total_used"):
                disk_text.append(S(S.BOLD("Total Used"), " : ", S.BR.WHITE(str(self.disk["total_used"]))))
            if self.disk.get("total_free"):
                disk_text.append(S(S.BOLD("Total Free"), " : ", S.BR.WHITE(str(self.disk["total_free"]))))

            if self.disk.get("partitions"):
                for partition in self.disk["partitions"]:
                    disk_text.append("{hr}")
                    disk_text.append((S.BOLD | S.BR.MAGENTA)(str(partition["device"])))
                    disk_text.append(S(S.BOLD("     Mount"), " : ", S.BR.WHITE(str(partition["mountpoint"]))))
                    disk_text.append(S(S.BOLD("Filesystem"), " : ", S.BR.WHITE(str(partition["filesystem"]))))
                    disk_text.append(S(S.BOLD("     Total"), " : ", S.BR.WHITE(str(partition["total"]))))
                    disk_text.append(S(S.BOLD("      Used"), " : ", S.BR.WHITE(str(partition["used"]))))
                    disk_text.append(S(S.BOLD("      Free"), " : ", S.BR.WHITE(str(partition["free"]))))
                    disk_text.append(S(S.BOLD("     Usage"), " : ", S.BR.WHITE(str(partition["usage_percent"]))))

            xx.console.box(*disk_text, border_style=S.BR.MAGENTA)

        # Network info:
        if self.network and self.network.get("adapters"):
            (S.BOLD | S.BR.RED)("\nNetwork Adapters").print()
            net_text: list[Renderable] = []
            for i, adapter in enumerate(self.network["adapters"]):
                if i > 0:
                    net_text.append("{hr}")
                status = (
                    (S.ITALIC | S.GREEN)("Connected") if adapter["is_up"] else (S.ITALIC | S.DIM | S.WHITE)("Disconnected")
                )
                net_text.append(S((S.BOLD | S.BR.RED)(str(adapter["name"])), " ", status))
                if adapter.get("mac"):
                    net_text.append(S(S.BOLD("  MAC"), " : ", S.BR.WHITE(str(adapter["mac"]))))
                if adapter.get("speed"):
                    net_text.append(S(S.BOLD("Speed"), " : ", S.BR.WHITE(str(adapter["speed"]))))
            xx.console.box(*net_text, border_style=S.BR.RED)

        # Battery info:
        if self.battery and self.battery.get("has_battery"):
            (S.BOLD | S.BR.WHITE)("\nBattery Information").print()
            battery_text: list[Renderable] = []
            time_left = self.battery.get("time_left")
            prefix = "        " if time_left else ""
            if self.battery.get("percent"):
                battery_text.append(S(S.BOLD(f"{prefix}Charge"), " : ", S.BR.WHITE(str(self.battery["percent"]))))
            if self.battery.get("power_plugged") is not None:
                status = S.GREEN("Plugged In") if self.battery["power_plugged"] else (S.ITALIC | S.YELLOW)("On Battery")
                battery_text.append(S(S.BOLD(f"{prefix}Status"), " : ", status))
            if time_left:
                battery_text.append(S(S.BOLD("Time Remaining"), " : ", S.BR.WHITE(str(time_left))))
            xx.console.box(*battery_text, border_style=S.BR.WHITE)

        print()


def main() -> None:
    hw_info = HardwareInfo()

    try:
        hw_info.gather_info()
    except Exception as exc:
        xx.console.fail(f"Error gathering hardware information: {exc}", end="\n\n", exit_code=1)

    if ARGS.json_output.exists:
        S("\n", xx.data.render(hw_info.as_dict(), indent=2, as_json=True, syntax_highlighting=True), "\n").print()
    else:
        hw_info.display()


if __name__ == "__main__":
    args = ArgumentParser(
        title="Hardware Info",
        subtitle="Get detailed hardware information about your PC",
        examples=[
            ("{cmd}", "Show summary hardware information"),
            ("{cmd} --json", "Output hardware information as JSON"),
        ],
    )

    args.add_opt({"-j", "--json"}, "json_output", help="Output hardware information as JSON")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)
