"""Network Manager — WiFi, IP, ping, connectivity for JARVIS MK-X."""

import logging
import socket
import subprocess

logger = logging.getLogger("jarvis.actions.network_manager")


def network_action(action: str, parameters: dict, **kwargs) -> str:
    handlers = {
        "status": _network_status,
        "ip": _get_ip,
        "wifi_scan": _wifi_scan,
        "wifi_connect": _wifi_connect,
        "wifi_disconnect": _wifi_disconnect,
        "ping": _ping,
        "dns": _dns_lookup,
        "speed_test": _speed_test,
        "interfaces": _list_interfaces,
        "firewall_status": _firewall_status,
    }
    handler = handlers.get(action)
    if not handler:
        return f"Unknown network action: {action}"
    try:
        return handler(parameters)
    except Exception as e:
        logger.error("Network action '%s' failed: %s", action, e)
        return f"Network operation failed: {e}"


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=30,
        )
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _cmd(cmd: str) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout.strip()
    except Exception as e:
        return f"Error: {e}"


def _network_status(params: dict) -> str:
    parts = []
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        parts.append(f"Hostname: {hostname}")
        parts.append(f"Local IP: {ip}")
    except Exception:
        pass

    # Check internet connectivity
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        parts.append("Internet: Connected")
    except Exception:
        parts.append("Internet: Disconnected")

    # WiFi info
    wifi = _ps("(netsh wlan show interfaces) 2>$null")
    if wifi:
        for line in wifi.split("\n"):
            line = line.strip()
            if any(k in line.lower() for k in ["ssid", "signal", "state", "channel"]):
                parts.append(line)

    return "\n".join(parts) if parts else "Network info unavailable"


def _get_ip(params: dict) -> str:
    public = params.get("public", False)
    if public:
        try:
            from core.http_pool import fetch
            ip = fetch("https://api.ipify.org", timeout=5)
            if ip:
                return f"Public IP: {ip.strip()}"
            return "Could not get public IP"
        except Exception:
            return "Could not get public IP"
    else:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        return f"Local IP: {ip}"


def _wifi_scan(params: dict) -> str:
    out = _ps("netsh wlan show networks mode=bssid")
    return out if out else "No WiFi networks found"


def _wifi_connect(params: dict) -> str:
    ssid = params.get("ssid", "")
    password = params.get("password", "")
    if not ssid:
        return "Provide an SSID"
    if password:
        _ps(f'netsh wlan connect name="{ssid}"')
        return f"Connecting to {ssid}..."
    _ps(f'netsh wlan connect name="{ssid}"')
    return f"Connecting to {ssid}..."


def _wifi_disconnect(params: dict) -> str:
    _ps("netsh wlan disconnect")
    return "Disconnected from WiFi"


def _ping(params: dict) -> str:
    target = params.get("host", "8.8.8.8")
    count = params.get("count", 4)
    out = _cmd(f"ping -n {count} {target}")
    return out if out else f"Ping to {target} failed"


def _dns_lookup(params: dict) -> str:
    host = params.get("host", "")
    if not host:
        return "Provide a hostname"
    try:
        ips = socket.getaddrinfo(host, None)
        unique = set(ip[4][0] for ip in ips)
        return f"DNS for {host}:\n" + "\n".join(f"  {ip}" for ip in unique)
    except Exception as e:
        return f"DNS lookup failed: {e}"


def _speed_test(params: dict) -> str:
    try:
        from core.http_pool import get_client
        client = get_client()
        import time
        url = "http://speedtest.tele2.net/1MB.zip"
        start = time.time()
        if client is not None:
            client.get(url, timeout=15)
        else:
            import urllib.request
            urllib.request.urlopen(url, timeout=15).read()
        elapsed = time.time() - start
        speed = (1 / elapsed) * 8  # Mbps
        return f"Download speed: ~{speed:.1f} Mbps"
    except Exception:
        return "Speed test failed (try: pip install speedtest-cli)"


def _list_interfaces(params: dict) -> str:
    out = _ps("Get-NetAdapter | Select-Object Name, InterfaceDescription, Status, LinkSpeed | Format-Table -AutoSize")
    return out if out else "No network adapters found"


def _firewall_status(params: dict) -> str:
    out = _ps("Get-NetFirewallProfile | Select-Object Name, Enabled | Format-Table -AutoSize")
    return out if out else "Firewall status unavailable"
