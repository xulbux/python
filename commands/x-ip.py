#!/usr/bin/env python3
# x-cmds:file[update]

"""
Get local and public IP addresses with optional geolocation information.
"""

import json
import re
import socket
import subprocess
from contextlib import suppress
from typing import TYPE_CHECKING, Any
import xulbux as xx
from xulbux import ArgumentParser, S

if TYPE_CHECKING:
    from xulbux.ansi import Renderable


class IPInfo:
    def __init__(self) -> None:
        self.local_ipv4: str | None = None
        self.local_ipv6: str | None = None
        self.public_ipv4: str | None = None
        self.public_ipv6: str | None = None
        self.all_interfaces: dict[str, dict[str, str]] = {}
        self.geo_info: dict[str, Any] | None = None

    def _get_local_ip(self) -> str | None:
        """Get primary local IPv4 address."""

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return None

    def _get_local_ipv6(self) -> str | None:
        """Get local IPv6 address."""

        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect(("2001:4860:4860::8888", 80))  # Google DNS IPv6.
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return None

    def _get_all_interfaces(self) -> dict[str, dict[str, str]]:
        """Get all network interfaces and their IPs."""

        interfaces: dict[str, dict[str, str]] = {}

        try:
            import netifaces

            for interface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(interface)
                interface_info = {}
                # IPv4:
                if netifaces.AF_INET in addrs:
                    ipv4_info = addrs[netifaces.AF_INET][0]
                    interface_info["ipv4"] = ipv4_info.get("addr", "N/A")
                    if "netmask" in ipv4_info:
                        interface_info["subnet_mask"] = ipv4_info["netmask"]
                # IPv6:
                if netifaces.AF_INET6 in addrs:
                    ipv6_info = addrs[netifaces.AF_INET6][0]
                    ipv6_addr = ipv6_info.get("addr", "N/A")
                    ipv6_addr = ipv6_addr.split("%")[0]
                    interface_info["ipv6"] = ipv6_addr

                # Get gateway information:
                with suppress(Exception):
                    gateways = netifaces.gateways()
                    if "default" in gateways and netifaces.AF_INET in gateways["default"]:
                        default_gateway_info = gateways["default"][netifaces.AF_INET]
                        if len(default_gateway_info) >= 2 and default_gateway_info[1] == interface:
                            interface_info["gateway"] = default_gateway_info[0]

                if interface_info:
                    interfaces[interface] = interface_info

            return interfaces

        except ImportError:
            return self._get_interfaces_fallback()

    def _get_interfaces_fallback(self) -> dict[str, dict[str, str]]:  # ruff:ignore[complex-structure]
        """Fallback method to get interfaces using system commands."""

        interfaces: dict[str, dict[str, str]] = {}

        with suppress(Exception):
            result = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                current_interface = None
                for line in result.stdout.split("\n"):
                    line = line.strip()

                    # Check if this line defines a new interface:
                    if ("adapter" in line or "configuration" in line) and line.endswith(":"):
                        interface_name = line.rstrip(":")
                        interface_name = re.sub(
                            r"^(Ethernet adapter|Wireless LAN adapter|Unknown adapter)\s*", "", interface_name
                        )
                        if interface_name and interface_name != "Windows IP Configuration":
                            current_interface = interface_name
                            interfaces[current_interface] = {}

                    # Extract IPv4 address:
                    elif "IPv4 Address" in line and current_interface:
                        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            interfaces[current_interface]["ipv4"] = match.group(1)

                    # Extract subnet mask:
                    elif "Subnet Mask" in line and current_interface:
                        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            interfaces[current_interface]["subnet_mask"] = match.group(1)

                    # Extract default gateway:
                    elif "Default Gateway" in line and current_interface:
                        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                        if match:
                            interfaces[current_interface]["gateway"] = match.group(1)

                    # Extract DNS suffix:
                    elif "Connection-specific DNS Suffix" in line and current_interface:
                        match = re.search(r":\s+(.+)", line)
                        if match:
                            dns_suffix = match.group(1).strip()
                            if dns_suffix:
                                interfaces[current_interface]["dns_suffix"] = dns_suffix

                    # Extract IPv6 address:
                    elif ("IPv6 Address" in line or "Link-local IPv6 Address" in line) and current_interface:
                        match = re.search(r":\s+([0-9a-fA-F:]+)", line)
                        if match:
                            ipv6_addr = match.group(1).split("%")[0]
                            if ":" in ipv6_addr and len(ipv6_addr) > 5:
                                interfaces[current_interface]["ipv6"] = ipv6_addr

                    # Extract media state (for disconnected interfaces):
                    elif "Media State" in line and current_interface:
                        if "disconnected" in line.lower():
                            interfaces[current_interface]["status"] = "Disconnected"

                # Set status to connected for interfaces with IP addresses:
                for _, interface_data in interfaces.items():
                    if "status" not in interface_data and any(key in interface_data for key in ["ipv4", "ipv6"]):
                        interface_data["status"] = "Connected"

                # Remove interfaces with no IP addresses (but keep disconnected ones for status info):
                interfaces = {
                    name: addrs
                    for name, addrs in interfaces.items()
                    if addrs and (any(key in addrs for key in ["ipv4", "ipv6"]) or "status" in addrs)
                }

        return interfaces

    def _get_public_ip(self, provider: str = "ipify", ipv6: bool = False) -> str | None:
        """Get public IP address from various providers."""

        providers = {
            "ipify": f"https://api{'64' if ipv6 else ''}.ipify.org?format=text",
            "icanhazip": f"https://{'ipv6.' if ipv6 else ''}icanhazip.com",
            "ipapi": "https://ipapi.co/ip/",
        }

        url = providers.get(provider.lower(), providers["ipify"])

        try:
            import urllib.request

            with urllib.request.urlopen(url, timeout=5) as response:
                ip = response.read().decode("utf-8").strip()
                return ip if ip else None
        except Exception:
            return None

    def _get_geolocation(self, ip: str) -> dict[str, Any] | None:
        """Get geolocation information for an IP address."""

        try:
            import urllib.request

            url = f"https://ipapi.co/{ip}/json/"

            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                if "error" in data:
                    return None
                return {
                    "ip": data.get("ip"),
                    "city": data.get("city"),
                    "region": data.get("region"),
                    "country": data.get("country_name"),
                    "country_code": data.get("country_code"),
                    "postal": data.get("postal"),
                    "lat": data.get("lat"),
                    "lng": data.get("lng"),
                    "timezone": data.get("timezone"),
                    "org": data.get("org"),
                    "asn": data.get("asn"),
                }
        except Exception:
            return None

    def gather_info(self, provider: str | None) -> None:
        """Gather all IP information."""

        xx.console.info("Gathering IP information...", start="\n")

        provider = provider or "ipify"

        self.local_ipv4 = self._get_local_ip()
        self.local_ipv6 = self._get_local_ipv6()
        self.public_ipv4 = self._get_public_ip(provider, ipv6=False)
        self.public_ipv6 = self._get_public_ip(provider, ipv6=True)
        self.all_interfaces = self._get_all_interfaces()

        if self.public_ipv4:
            self.geo_info = self._get_geolocation(self.public_ipv4)

    def as_dict(self) -> dict[str, dict[str, Any]]:
        """Convert IP info to dictionary."""

        result: dict[str, dict[str, Any]] = {"local": {}, "public": {}}

        if self.local_ipv4:
            result["local"]["ipv4"] = self.local_ipv4
        if self.local_ipv6:
            result["local"]["ipv6"] = self.local_ipv6
        if self.public_ipv4:
            result["public"]["ipv4"] = self.public_ipv4
        if self.public_ipv6:
            result["public"]["ipv6"] = self.public_ipv6
        if self.all_interfaces:
            result["interfaces"] = self.all_interfaces
        if self.geo_info:
            result["geolocation"] = self.geo_info

        return result

    def display(self) -> None:  # ruff:ignore[complex-structure]
        """Display IP information in formatted output."""

        print()

        (S.BOLD | S.GREEN)("\nLocal IP Addresses").print()
        local_ips_text: list[Renderable] = []

        if self.local_ipv4:
            local_ips_text.append(S(S.BOLD("IPv4"), " : ", S.WHITE(self.local_ipv4)))
        else:
            local_ips_text.append(S(S.BOLD("IPv4"), " : ", (S.ITALIC | S.DIM | S.WHITE)("Not Found")))
        if self.local_ipv6:
            local_ips_text.append(S(S.BOLD("IPv6"), " : ", S.WHITE(self.local_ipv6)))
        else:
            local_ips_text.append(S(S.BOLD("IPv6"), " : ", (S.ITALIC | S.DIM | S.WHITE)("Not Found")))

        xx.console.box(*local_ips_text, border_style=S.GREEN)

        (S.BOLD | S.CYAN)("\nPublic IP Addresses").print()
        public_ips_text: list[Renderable] = []

        if self.public_ipv4:
            public_ips_text.append(S(S.BOLD("IPv4"), " : ", S.WHITE(self.public_ipv4)))
        else:
            public_ips_text.append(S(S.BOLD("IPv4"), " : ", (S.ITALIC | S.DIM | S.WHITE)("Not Found")))
        if self.public_ipv6:
            public_ips_text.append(S(S.BOLD("IPv6"), " : ", S.WHITE(self.public_ipv6)))
        else:
            public_ips_text.append(S(S.BOLD("IPv6"), " : ", (S.ITALIC | S.DIM | S.WHITE)("Not Found")))

        xx.console.box(*public_ips_text, border_style=S.CYAN)

        if self.all_interfaces:
            (S.BOLD | S.BLUE)("\nAll Network Interfaces").print()
            interfaces_text: list[Renderable] = []

            for i, (interface, addrs) in enumerate(self.all_interfaces.items()):
                if i > 0:
                    interfaces_text.append("{hr}")

                status = (
                    S(
                        " ",
                        (S.ITALIC | S.GREEN)(addrs["status"])
                        if addrs["status"].lower() == "connected"
                        else (S.ITALIC | S.DIM | S.WHITE)(addrs["status"]),
                    )
                    if "status" in addrs
                    else ""
                )

                interfaces_text.append(S((S.BOLD | S.BLUE)(interface), status))
                p = "   " if "dns_suffix" in addrs else ""

                # IPv4 info:
                if "ipv4" in addrs:
                    interfaces_text.append(S(S.BOLD(f"{p}   IPv4"), " : ", S.WHITE(str(addrs["ipv4"]))))
                    if "subnet_mask" in addrs:
                        interfaces_text.append(S(S.BOLD(f"{p} Subnet"), " : ", S.WHITE(str(addrs["subnet_mask"]))))
                    if "gateway" in addrs:
                        interfaces_text.append(S(S.BOLD(f"{p}Gateway"), " : ", S.WHITE(str(addrs["gateway"]))))

                # IPv6 info:
                if "ipv6" in addrs:
                    interfaces_text.append(S(S.BOLD(f"{p}   IPv6"), " : ", S.WHITE(str(addrs["ipv6"]))))

                # DNS suffix:
                if "dns_suffix" in addrs:
                    interfaces_text.append(S(S.BOLD("DNS Suffix"), " : ", S.WHITE(str(addrs["dns_suffix"]))))

            xx.console.box(*interfaces_text, border_style=S.BLUE)

        if self.geo_info:
            (S.BOLD | S.MAGENTA)("\nGeolocation Information").print()
            geo = self.geo_info
            geo_text: list[Renderable] = []
            has_coords = geo.get("lat") is not None and geo.get("lng") is not None
            p = "   " if has_coords else ""

            if geo.get("city") or geo.get("region"):
                location = f"{geo.get('city', '')}, {geo.get('region', '')}".strip(", ")
                geo_text.append(S(S.BOLD(f"{p}Location"), " : ", S.WHITE(location)))
            if geo.get("country"):
                geo_text.append(S(S.BOLD(f"{p} Country"), " : ", S.WHITE(f"{geo['country']} ({geo.get('country_code', '')})")))
            if geo.get("postal"):
                geo_text.append(S(S.BOLD(f"{p}  Postal"), " : ", S.WHITE(str(geo["postal"]))))
            if geo.get("timezone"):
                geo_text.append(S(S.BOLD(f"{p}Timezone"), " : ", S.WHITE(str(geo["timezone"]))))
            if has_coords:
                geo_text.append(S(S.BOLD("Coordinates"), " : ", S.WHITE(f"{geo['lat']}, {geo['lng']}")))
            if geo.get("org"):
                geo_text.append(S(S.BOLD(f"{p}     ISP"), " : ", S.WHITE(str(geo["org"]))))
            if geo.get("asn"):
                geo_text.append(S(S.BOLD(f"{p}     ASN"), " : ", S.WHITE(str(geo["asn"]))))

            xx.console.box(*geo_text, border_style=S.MAGENTA)

        print()


def main() -> None:
    ip_info = IPInfo()

    try:
        ip_info.gather_info(provider=ARGS.provider.val(default="ipify"))
    except Exception as exc:
        xx.console.fail(f"Error gathering IP information: {exc}", end="\n\n", exit_code=1)

    if ARGS.json_output.exists:
        S("\n", xx.data.render(ip_info.as_dict(), indent=2, as_json=True, syntax_highlighting=True), "\n").print()
    else:
        ip_info.display()


if __name__ == "__main__":
    args = ArgumentParser(
        title="IP Info",
        subtitle="Get local and public IP addresses with geolocation",
        examples=[
            ("{cmd}", "Show basic IP information"),
            ("{cmd} --provider=ipapi", "Use ipapi.co to get public IP"),
            ("{cmd} --json", "Output IP information as JSON"),
        ],
    )

    args.add_opt(
        {"-p", "--provider"},
        "provider",
        expects_value="NAME",
        help=("Use specific IP provider ", S.DIM("(ipify, ipapi, icanhazip)")),
    )
    args.add_opt({"-j", "--json"}, "json_output", help="Output IP information as JSON")

    global ARGS
    ARGS = args.parse()

    try:
        main()
    except KeyboardInterrupt:
        print()
    except Exception as exc:
        xx.console.fail(exc, start="\n", end="\n\n", exit_code=1)
