import webbrowser
import subprocess
import sys

def open_url(url: str):
    if not url.startswith(("https://", "http://")):
        raise ValueError("Only HTTP(S) URLs are allowed.")
    webbrowser.open(url)
    return {"opened": url}

def launch_application(command: list[str], confirmed: bool = False):
    from app.automation.safety import require_confirmation
    require_confirmation("launch application", confirmed)
    if not command or not all(isinstance(part, str) for part in command):
        raise ValueError("Invalid application command.")
    subprocess.Popen(command, shell=False)
    return {"launched": command[0]}
