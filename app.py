import os
import sys
import json
import re
import socket
import subprocess
import ctypes
import shutil
import io
import time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, abort, Response

try:
    import qrcode
except Exception:
    qrcode = None

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "buttons.json"
PAGE_COLORS_FILE = BASE_DIR / "page_colors.json"
THEME_FILE = BASE_DIR / "theme.json"
BACKUPS_DIR = BASE_DIR / "backups"
SOUNDS_DIR = BASE_DIR / "sounds"
ICONS_DIR = BASE_DIR / "static" / "icons"
ALLOWED_SOUND_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
ALLOWED_ICON_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
DEFAULT_PAGE = "Main"
BACKUP_LIMIT = 30
RUN_TYPES = {"open", "url", "command", "sound", "volume_toggle", "volume_mute", "volume_unmute", "volume_up", "volume_down"}
BUTTON_TYPES = RUN_TYPES | {"macro"}
STARTER_PAGES = ["Main", "Streaming", "Dev", "Music", "System"]
DEFAULT_ACCENT = "#2fb7ff"
DEFAULT_PAGE_COLORS = {
    "All": "#2fb7ff",
    "Main": "#2fb7ff",
    "Streaming": "#ff5c7a",
    "Dev": "#33d17a",
    "Music": "#ffd166",
    "System": "#9b8cff",
}
THEME_PRESETS = {
    "neon": {"id": "neon", "name": "Neon Dark", "accent": "#2fb7ff"},
    "studio": {"id": "studio", "name": "Studio", "accent": "#ffb86b"},
    "minimal": {"id": "minimal", "name": "Minimal", "accent": "#7dd3fc"},
    "ios": {"id": "ios", "name": "iOS Glass", "accent": "#8b5cf6"},
}
DEFAULT_THEME = "neon"
APP_ALIASES = {
    "chrome": {
        "darwin": "Google Chrome",
        "win32": "chrome",
        "linux": "google-chrome",
    },
    "google chrome": {
        "darwin": "Google Chrome",
        "win32": "chrome",
        "linux": "google-chrome",
    },
    "calculator": {
        "darwin": "Calculator",
        "win32": "calc",
        "linux": "gnome-calculator",
    },
    "calc": {
        "darwin": "Calculator",
        "win32": "calc",
        "linux": "gnome-calculator",
    },
    "terminal": {
        "darwin": "Terminal",
        "win32": "wt",
        "linux": "x-terminal-emulator",
    },
    "powershell": {
        "darwin": "Terminal",
        "win32": "powershell",
        "linux": "x-terminal-emulator",
    },
    "cmd": {
        "darwin": "Terminal",
        "win32": "cmd",
        "linux": "x-terminal-emulator",
    },
    "visual studio code": {
        "darwin": "Visual Studio Code",
        "win32": "code",
        "linux": "code",
    },
    "vscode": {
        "darwin": "Visual Studio Code",
        "win32": "code",
        "linux": "code",
    },
    "finder": {
        "darwin": "Finder",
        "win32": "explorer",
        "linux": "xdg-open .",
    },
    "explorer": {
        "darwin": "Finder",
        "win32": "explorer",
        "linux": "xdg-open .",
    },
    "notepad": {
        "darwin": "TextEdit",
        "win32": "notepad",
        "linux": "gedit",
    },
}
HOST = os.environ.get("WEB_DECK_HOST", "0.0.0.0")
PORT = int(os.environ.get("WEB_DECK_PORT", "5001"))
TOKEN = os.environ.get("WEB_DECK_TOKEN", "1234")

app = Flask(__name__)
SOUNDS_DIR.mkdir(exist_ok=True)
ICONS_DIR.mkdir(exist_ok=True)
BACKUPS_DIR.mkdir(exist_ok=True)


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def default_buttons():
    return [
        {"id": "mute_toggle", "title": "ปิด/เปิดเสียง", "icon": "🔇", "type": "volume_toggle", "page": "System"},
        {"id": "sound_on", "title": "เปิดเสียง", "icon": "🔊", "type": "volume_unmute", "page": "System"},
        {"id": "sound_off", "title": "ปิดเสียง", "icon": "🔈", "type": "volume_mute", "page": "System"},
        {"id": "volume_up", "title": "เพิ่มเสียง", "icon": "➕", "type": "volume_up", "step": 4, "page": "System"},
        {"id": "volume_down", "title": "ลดเสียง", "icon": "➖", "type": "volume_down", "step": 4, "page": "System"},
        {"id": "chrome", "title": "Chrome", "icon": "🌐", "type": "open", "target": "app:Google Chrome", "page": "Dev"},
        {"id": "calculator", "title": "Calculator", "icon": "🧮", "type": "open", "target": "app:Calculator", "page": "System"},
        {"id": "terminal", "title": "Terminal", "icon": "⌨️", "type": "open", "target": "app:Terminal", "page": "Dev"},
        {"id": "vscode", "title": "VS Code", "icon": "💻", "type": "open", "target": "app:Visual Studio Code", "page": "Dev"},
        {"id": "finder", "title": "Finder", "icon": "📁", "type": "open", "target": "app:Finder", "page": "System"},
        {"id": "google", "title": "Google", "icon": "🔎", "type": "url", "target": "https://google.com", "page": "Main"},
        {"id": "play_alert", "title": "เล่นเสียง Alert", "icon": "🔔", "type": "sound", "target": "alert.wav", "page": "Music"},
        {"id": "run_yolo", "title": "Start YOLO", "icon": "🤖", "type": "command", "target": "python3 /Users/yourname/project/yolo/main.py", "page": "Dev"}
    ]


def clean_page(value):
    page = str(value or DEFAULT_PAGE).strip()
    return page[:40] or DEFAULT_PAGE


def clean_color(value, fallback=""):
    color = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color.lower()
    return fallback


def normalize_buttons(buttons):
    normalized = []
    for button in buttons:
        if not isinstance(button, dict):
            continue
        item = button.copy()
        item["page"] = clean_page(item.get("page"))
        if item.get("color"):
            item["color"] = clean_color(item.get("color"))
        normalized.append(item)
    return normalized


def read_json_file(path, fallback):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def prune_backups(limit=BACKUP_LIMIT):
    backups = sorted(BACKUPS_DIR.glob("backup-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_backup in backups[limit:]:
        try:
            old_backup.unlink()
        except OSError:
            pass


def backup_config(reason="auto"):
    if not CONFIG_FILE.exists() and not PAGE_COLORS_FILE.exists() and not THEME_FILE.exists():
        return None
    BACKUPS_DIR.mkdir(exist_ok=True)
    clean_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(reason or "auto")).strip("_") or "auto"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_file = BACKUPS_DIR / f"backup-{timestamp}-{clean_reason[:32]}.json"
    data = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": clean_reason,
        "buttons": read_json_file(CONFIG_FILE, []),
        "page_colors": read_json_file(PAGE_COLORS_FILE, {}),
        "theme": read_json_file(THEME_FILE, {"theme": DEFAULT_THEME}),
    }
    backup_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_backups()
    return backup_file


def load_buttons():
    if not CONFIG_FILE.exists():
        save_buttons(default_buttons(), make_backup=False)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        return normalize_buttons(data) if isinstance(data, list) else default_buttons()
    except Exception:
        return default_buttons()


def save_buttons(buttons, make_backup=True):
    if make_backup:
        backup_config("buttons")
    CONFIG_FILE.write_text(json.dumps(buttons, ensure_ascii=False, indent=2), encoding="utf-8")


def load_page_colors():
    colors = DEFAULT_PAGE_COLORS.copy()
    if PAGE_COLORS_FILE.exists():
        try:
            data = json.loads(PAGE_COLORS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for page, color in data.items():
                    clean_name = "All" if str(page).strip() == "All" else clean_page(page)
                    colors[clean_name] = clean_color(color, colors.get(clean_name, DEFAULT_ACCENT))
        except Exception:
            pass
    return colors


def save_page_colors(colors, make_backup=True):
    if make_backup:
        backup_config("page-colors")
    PAGE_COLORS_FILE.write_text(json.dumps(colors, ensure_ascii=False, indent=2), encoding="utf-8")


def load_theme():
    data = read_json_file(THEME_FILE, {"theme": DEFAULT_THEME})
    theme_id = str(data.get("theme", DEFAULT_THEME)).strip()
    return theme_id if theme_id in THEME_PRESETS else DEFAULT_THEME


def save_theme(theme_id, make_backup=True):
    theme_id = str(theme_id or "").strip()
    if theme_id not in THEME_PRESETS:
        raise ValueError("Theme ไม่ถูกต้อง")
    if make_backup:
        backup_config("theme")
    THEME_FILE.write_text(json.dumps({"theme": theme_id}, ensure_ascii=False, indent=2), encoding="utf-8")
    return theme_id


def theme_payload():
    current = load_theme()
    return {
        "current_theme": current,
        "theme_class": f"theme-{current}",
        "theme_name": THEME_PRESETS[current]["name"],
        "themes": list(THEME_PRESETS.values()),
    }


def check_token():
    token = request.args.get("token") or request.headers.get("X-Web-Deck-Token")
    if token != TOKEN:
        abort(403)


def slugify(text):
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", str(text).strip().lower()).strip("_")
    return base or "button"


def unique_id(buttons, title):
    base = slugify(title)
    ids = {b.get("id") for b in buttons}
    if base not in ids:
        return base
    i = 2
    while f"{base}_{i}" in ids:
        i += 1
    return f"{base}_{i}"


def clean_step(value, default=4):
    try:
        return max(1, min(int(value or default), 20))
    except (TypeError, ValueError):
        return default


def clean_delay(value):
    try:
        delay = float(value or 0)
    except (TypeError, ValueError):
        delay = 0
    return max(0, min(delay, 30))


def validate_macro_actions(actions):
    if not isinstance(actions, list) or not actions:
        raise ValueError("Macro ต้องมี actions อย่างน้อย 1 รายการ")
    if len(actions) > 20:
        raise ValueError("Macro ใส่ actions ได้สูงสุด 20 รายการ")

    cleaned = []
    for index, action in enumerate(actions, start=1):
        if not isinstance(action, dict):
            raise ValueError(f"Macro action #{index} ต้องเป็น object")
        action_type = str(action.get("type", "")).strip()
        delay = clean_delay(action.get("delay"))

        if action_type == "delay" or (not action_type and delay):
            cleaned.append({"type": "delay", "delay": delay})
            continue

        if action_type not in RUN_TYPES:
            raise ValueError(f"Macro action #{index} มี type ไม่ถูกต้อง")

        item = {"type": action_type}
        if action_type in {"open", "url", "command", "sound"}:
            target = str(action.get("target", "")).strip()
            if not target:
                raise ValueError(f"Macro action #{index} ต้องใส่ target")
            item["target"] = target
        if action_type in {"volume_up", "volume_down"}:
            item["step"] = clean_step(action.get("step"))
        if delay:
            item["delay"] = delay
        cleaned.append(item)

    return cleaned


def validate_button(payload, existing=None):
    title = str(payload.get("title", "")).strip()
    icon = str(payload.get("icon", "🔘")).strip() or "🔘"
    page = clean_page(payload.get("page") or (existing or {}).get("page"))
    color = clean_color(payload.get("color") or (existing or {}).get("color") or "")
    action_type = str(payload.get("type", "open")).strip()
    target = str(payload.get("target", "")).strip()
    step = clean_step(payload.get("step"))

    if not title:
        raise ValueError("กรุณาใส่ชื่อปุ่ม")
    if action_type not in BUTTON_TYPES:
        raise ValueError("ประเภทปุ่มไม่ถูกต้อง")
    if action_type in {"open", "url", "command", "sound"} and not target:
        raise ValueError("ปุ่มประเภทนี้ต้องใส่ Target")
    actions = validate_macro_actions(payload.get("actions")) if action_type == "macro" else []

    button = existing.copy() if existing else {}
    button.update({"title": title, "icon": icon, "page": page, "type": action_type})
    if color:
        button["color"] = color
    else:
        button.pop("color", None)

    if action_type in {"open", "url", "command", "sound"}:
        button["target"] = target
    else:
        button.pop("target", None)

    if action_type in {"volume_up", "volume_down"}:
        button["step"] = step
    else:
        button.pop("step", None)

    if action_type == "macro":
        button["actions"] = actions
    else:
        button.pop("actions", None)

    return button


def page_counts(buttons, page_colors=None):
    page_colors = page_colors or load_page_colors()
    counts = {}
    for page in STARTER_PAGES:
        counts[page] = 0
    for button in buttons:
        page = clean_page(button.get("page"))
        counts[page] = counts.get(page, 0) + 1
    return [{"name": name, "count": count, "color": page_colors.get(name, DEFAULT_ACCENT)} for name, count in counts.items()]


def selected_page(buttons, requested):
    if str(requested or "").strip() == "All":
        return "All"
    pages = [p["name"] for p in page_counts(buttons)]
    page = clean_page(requested)
    return page if page in pages else pages[0]


def request_port():
    host = request.host or f"127.0.0.1:{PORT}"
    if ":" in host and not host.startswith("["):
        return host.rsplit(":", 1)[1]
    return str(PORT)


def deck_links():
    port = request_port()
    local_url = f"http://127.0.0.1:{port}/?token={TOKEN}"
    lan_url = f"http://{get_lan_ip()}:{port}/?token={TOKEN}"
    current_url = request.url_root.rstrip("/") + f"/?token={TOKEN}"
    return {"local": local_url, "lan": lan_url, "current": current_url}


def win_press_vk(vk_code, times=1):
    KEYEVENTF_KEYUP = 0x0002
    user32 = ctypes.windll.user32
    for _ in range(max(1, int(times))):
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def run_command(command):
    subprocess.Popen(command, shell=True)


def platform_key():
    if sys.platform.startswith("win"):
        return "win32"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def resolve_app_alias(name):
    app_name = str(name or "").strip()
    alias = APP_ALIASES.get(app_name.lower())
    if alias:
        return alias.get(platform_key()) or app_name
    return app_name


def open_target(target):
    target = str(target).strip()

    if sys.platform.startswith("win"):
        resolved = resolve_app_alias(target[4:] if target.startswith("app:") else target)
        if resolved.startswith("shell:"):
            subprocess.Popen(["explorer", resolved])
            return
        startfile = getattr(os, "startfile", None)
        try:
            if startfile:
                startfile(resolved)
            else:
                raise FileNotFoundError(resolved)
        except (FileNotFoundError, OSError):
            run_command(f'start "" "{resolved}"')
        return

    if sys.platform == "darwin":
        if target.startswith("app:"):
            subprocess.Popen(["open", "-a", resolve_app_alias(target[4:])])
        elif target.startswith("/") or target.endswith(".app") or target.startswith("http"):
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["open", "-a", resolve_app_alias(target)])
        return

    if target.startswith("app:"):
        run_command(resolve_app_alias(target[4:]))
    else:
        subprocess.Popen(["xdg-open", target])


def powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def win_audio_command(action_type, step):
    endpoint_policy = "Add-Type -TypeDefinition @'\nusing System;\nusing System.Runtime.InteropServices;\n[Guid(\"5CDF2C82-841E-4546-9722-0CF74078229A\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IAudioEndpointVolume { int NotImpl1(); int NotImpl2(); int GetChannelCount(out uint channelCount); int SetMasterVolumeLevel(float level, Guid eventContext); int SetMasterVolumeLevelScalar(float level, Guid eventContext); int GetMasterVolumeLevel(out float level); int GetMasterVolumeLevelScalar(out float level); int SetChannelVolumeLevel(uint channelNumber, float level, Guid eventContext); int SetChannelVolumeLevelScalar(uint channelNumber, float level, Guid eventContext); int GetChannelVolumeLevel(uint channelNumber, out float level); int GetChannelVolumeLevelScalar(uint channelNumber, out float level); int SetMute([MarshalAs(UnmanagedType.Bool)] bool isMuted, Guid eventContext); int GetMute(out bool isMuted); }\n[Guid(\"D666063F-1587-4E43-81F1-B948E807363F\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IMMDevice { int Activate(ref Guid id, int clsCtx, IntPtr activationParams, out IAudioEndpointVolume endpointVolume); }\n[Guid(\"A95664D2-9614-4F35-A746-DE8DB63617E6\"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)] public interface IMMDeviceEnumerator { int NotImpl1(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); }\n[ComImport, Guid(\"BCDE0395-E52F-467C-8E3D-C4579291692E\")] public class MMDeviceEnumeratorComObject { }\npublic class Audio { public static IAudioEndpointVolume Volume() { IMMDeviceEnumerator enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject()); IMMDevice device; Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0, 1, out device)); Guid id = typeof(IAudioEndpointVolume).GUID; IAudioEndpointVolume volume; Marshal.ThrowExceptionForHR(device.Activate(ref id, 23, IntPtr.Zero, out volume)); return volume; } }\n'@;"
    if action_type == "volume_mute":
        action = "[Audio]::Volume().SetMute($true, [Guid]::Empty)"
    elif action_type == "volume_unmute":
        action = "[Audio]::Volume().SetMute($false, [Guid]::Empty)"
    elif action_type == "volume_toggle":
        action = "$v=[Audio]::Volume(); $m=$false; $v.GetMute([ref]$m); $v.SetMute(-not $m, [Guid]::Empty)"
    else:
        delta = max(1, min(int(step or 3), 20)) * 0.05
        op = "+" if action_type == "volume_up" else "-"
        action = f"$v=[Audio]::Volume(); $level=0.0; $v.GetMasterVolumeLevelScalar([ref]$level); $next=[Math]::Max(0,[Math]::Min(1,$level {op} {delta})); $v.SetMasterVolumeLevelScalar($next,[Guid]::Empty)"
    return endpoint_policy + action


def control_volume(action_type, step=3):
    step = max(1, min(int(step or 3), 20))

    if sys.platform.startswith("win"):
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", win_audio_command(action_type, step)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return action_type

    if sys.platform == "darwin":
        scripts = {
            "volume_mute": "set volume output muted true",
            "volume_unmute": "set volume output muted false",
            "volume_toggle": "set volume output muted not (output muted of (get volume settings))",
            "volume_up": f"set volume output volume ((output volume of (get volume settings)) + {step * 5})",
            "volume_down": f"set volume output volume ((output volume of (get volume settings)) - {step * 5})",
        }
        subprocess.Popen(["osascript", "-e", scripts[action_type]])
        return action_type

    if action_type == "volume_mute":
        subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])
    elif action_type == "volume_unmute":
        subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])
    elif action_type == "volume_toggle":
        subprocess.Popen(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
    elif action_type == "volume_up":
        subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step * 5}%"])
    elif action_type == "volume_down":
        subprocess.Popen(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step * 5}%"])
    return action_type



def list_sounds():
    SOUNDS_DIR.mkdir(exist_ok=True)
    files = []
    for f in SOUNDS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in ALLOWED_SOUND_EXT:
            files.append(f.name)
    return sorted(files, key=str.lower)


def list_icons():
    ICONS_DIR.mkdir(exist_ok=True)
    files = []
    for f in ICONS_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in ALLOWED_ICON_EXT:
            files.append(f"/static/icons/{f.name}")
    return sorted(files, key=str.lower)


def safe_upload_name(filename):
    raw = Path(filename or "").name
    stem = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(raw).stem).strip("_") or "upload"
    return f"{stem[:48]}{Path(raw).suffix.lower()}"


def safe_sound_path(target):
    target = str(target).strip()
    if not target:
        raise ValueError("กรุณาระบุไฟล์เสียง")

    # รองรับทั้งชื่อไฟล์ในโฟลเดอร์ sounds/ และ path เต็มในเครื่อง
    if "/" not in target and "\\" not in target:
        path = SOUNDS_DIR / target
    else:
        path = Path(target).expanduser()

    if path.suffix.lower() not in ALLOWED_SOUND_EXT:
        raise ValueError("รองรับไฟล์เสียง .mp3, .wav, .m4a, .aac, .ogg, .flac")
    if not path.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์เสียง: {path}")
    return path


def play_sound(target):
    path = safe_sound_path(target)

    if sys.platform == "darwin":
        subprocess.Popen(["afplay", str(path)])
        return f"playing sound: {path.name}"

    if sys.platform.startswith("win"):
        if path.suffix.lower() == ".wav":
            ps = f'(New-Object Media.SoundPlayer "{str(path)}").PlaySync()'
        else:
            ps = f'Add-Type -AssemblyName presentationCore; $p=New-Object System.Windows.Media.MediaPlayer; $p.Open("{path.as_uri()}"); $p.Play(); Start-Sleep -Seconds 10'
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
        return f"playing sound: {path.name}"

    player = shutil.which("paplay") or shutil.which("aplay") or shutil.which("ffplay")
    if not player:
        raise RuntimeError("ไม่พบโปรแกรมเล่นเสียงบน Linux: ติดตั้ง paplay/aplay/ffplay ก่อน")
    if Path(player).name == "ffplay":
        subprocess.Popen([player, "-nodisp", "-autoexit", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen([player, str(path)])
    return f"playing sound: {path.name}"


def run_macro_actions(actions):
    cleaned_actions = validate_macro_actions(actions)
    completed = 0
    for action in cleaned_actions:
        delay = clean_delay(action.get("delay"))
        if action.get("type") == "delay":
            time.sleep(delay)
            continue
        run_button(action)
        completed += 1
        if delay:
            time.sleep(delay)
    return f"macro completed: {completed} actions"


def run_button(button):
    action_type = button.get("type")
    target = button.get("target", "")
    if action_type == "macro":
        return run_macro_actions(button.get("actions", []))
    if action_type == "url":
        import webbrowser
        webbrowser.open(target)
        return "opened url"
    if action_type == "open":
        open_target(target)
        return "opened app/file"
    if action_type == "command":
        run_command(target)
        return "command started"
    if action_type == "sound":
        return play_sound(target)
    if action_type in {"volume_toggle", "volume_mute", "volume_unmute", "volume_up", "volume_down"}:
        return control_volume(action_type, button.get("step", 3))
    raise ValueError(f"Unknown button type: {action_type}")


@app.route("/")
def index():
    check_token()
    buttons = load_buttons()
    page_colors = load_page_colors()
    base_pages = page_counts(buttons, page_colors)
    pages = [{"name": "All", "count": len(buttons), "color": page_colors.get("All", DEFAULT_ACCENT)}] + base_pages
    current_page = selected_page(buttons, request.args.get("page"))
    page_buttons = buttons if current_page == "All" else [b for b in buttons if clean_page(b.get("page")) == current_page]
    return render_template(
        "index.html",
        buttons=page_buttons,
        pages=pages,
        page_colors=page_colors,
        current_color=page_colors.get(current_page, DEFAULT_ACCENT),
        current_page=current_page,
        total_buttons=len(buttons),
        token=TOKEN,
        **theme_payload(),
    )


@app.route("/settings")
def settings():
    check_token()
    buttons = load_buttons()
    page_colors = load_page_colors()
    pages = page_counts(buttons, page_colors)
    requested = request.args.get("page") or "All"
    current_page = "All" if requested == "All" else selected_page(buttons, requested)
    shown_buttons = buttons if current_page == "All" else [b for b in buttons if clean_page(b.get("page")) == current_page]
    return render_template(
        "settings.html",
        buttons=shown_buttons,
        pages=pages,
        page_colors=page_colors,
        current_color=page_colors.get(current_page, DEFAULT_ACCENT),
        current_page=current_page,
        token=TOKEN,
        sounds=list_sounds(),
        **theme_payload(),
    )


@app.route("/qr")
def qr_page():
    check_token()
    links = deck_links()
    return render_template("qr.html", token=TOKEN, links=links, **theme_payload())


@app.route("/qr.png")
def qr_png():
    check_token()
    if qrcode is None:
        return jsonify({"ok": False, "error": "ไม่ได้ติดตั้ง qrcode package"}), 500
    links = deck_links()
    mode = request.args.get("mode", "lan")
    target = links.get(mode, links["lan"])
    img = qrcode.make(target)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png")


@app.route("/api/buttons", methods=["GET"])
def api_buttons():
    check_token()
    buttons = load_buttons()
    return jsonify({"ok": True, "buttons": buttons, "pages": page_counts(buttons), "page_colors": load_page_colors()})


@app.route("/api/config/export", methods=["GET"])
def api_export_config():
    check_token()
    data = json.dumps(load_buttons(), ensure_ascii=False, indent=2)
    return Response(
        data,
        mimetype="application/json; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=buttons.json"},
    )


@app.route("/api/config/import", methods=["POST"])
def api_import_config():
    check_token()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "กรุณาเลือกไฟล์ buttons.json"}), 400
    try:
        imported = json.loads(file.read().decode("utf-8"))
        if not isinstance(imported, list):
            raise ValueError("ไฟล์ต้องเป็น JSON array")
        normalized = normalize_buttons(imported)
        if not normalized:
            raise ValueError("ไม่พบรายการปุ่มในไฟล์")
        cleaned = []
        seen = set()
        for button in normalized:
            if not button.get("id"):
                button["id"] = unique_id(normalized, button.get("title", "button"))
            if button["id"] in seen:
                button["id"] = unique_id(normalized, button.get("title", "button"))
            seen.add(button["id"])
            validated = validate_button(button, existing=button)
            validated["id"] = button["id"]
            cleaned.append(validated)
        save_buttons(cleaned)
        return jsonify({"ok": True, "buttons": cleaned, "count": len(cleaned)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/page-colors", methods=["GET"])
def api_page_colors():
    check_token()
    return jsonify({"ok": True, "colors": load_page_colors()})


@app.route("/api/page-colors", methods=["POST"])
def api_save_page_color():
    check_token()
    payload = request.get_json(force=True) or {}
    page = str(payload.get("page") or "").strip()
    if page != "All":
        page = clean_page(page)
    color = clean_color(payload.get("color"))
    if not color:
        return jsonify({"ok": False, "error": "สีต้องอยู่ในรูปแบบ #RRGGBB"}), 400
    colors = load_page_colors()
    colors[page] = color
    save_page_colors(colors)
    return jsonify({"ok": True, "page": page, "color": color, "colors": colors})


@app.route("/api/theme", methods=["GET"])
def api_theme():
    check_token()
    return jsonify({"ok": True, **theme_payload()})


@app.route("/api/theme", methods=["POST"])
def api_save_theme():
    check_token()
    payload = request.get_json(force=True) or {}
    try:
        theme_id = save_theme(payload.get("theme"))
        return jsonify({"ok": True, "theme": theme_id, **theme_payload()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/buttons", methods=["POST"])
def api_add_button():
    check_token()
    buttons = load_buttons()
    try:
        button = validate_button(request.get_json(force=True) or {})
        button["id"] = unique_id(buttons, button["title"])
        buttons.append(button)
        save_buttons(buttons)
        return jsonify({"ok": True, "button": button})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/buttons/<button_id>", methods=["PUT"])
def api_update_button(button_id):
    check_token()
    buttons = load_buttons()
    idx = next((i for i, b in enumerate(buttons) if b.get("id") == button_id), None)
    if idx is None:
        return jsonify({"ok": False, "error": "button not found"}), 404
    try:
        buttons[idx] = validate_button(request.get_json(force=True) or {}, existing=buttons[idx])
        buttons[idx]["id"] = button_id
        save_buttons(buttons)
        return jsonify({"ok": True, "button": buttons[idx]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/buttons/<button_id>", methods=["DELETE"])
def api_delete_button(button_id):
    check_token()
    buttons = load_buttons()
    new_buttons = [b for b in buttons if b.get("id") != button_id]
    if len(new_buttons) == len(buttons):
        return jsonify({"ok": False, "error": "button not found"}), 404
    save_buttons(new_buttons)
    return jsonify({"ok": True})


@app.route("/api/buttons/<button_id>/move", methods=["POST"])
def api_move_button(button_id):
    check_token()
    buttons = load_buttons()
    idx = next((i for i, b in enumerate(buttons) if b.get("id") == button_id), None)
    if idx is None:
        return jsonify({"ok": False, "error": "button not found"}), 404
    payload = request.get_json(force=True) or {}
    direction = str(payload.get("direction", "")).strip().lower()
    current_page = str(payload.get("page") or "").strip()
    if current_page == "All":
        move_indexes = list(range(len(buttons)))
    else:
        page = clean_page(current_page or buttons[idx].get("page"))
        move_indexes = [i for i, b in enumerate(buttons) if clean_page(b.get("page")) == page]

    if idx not in move_indexes:
        return jsonify({"ok": False, "error": "button is not in the selected page"}), 400

    move_pos = move_indexes.index(idx)

    if direction == "up":
        new_pos = max(0, move_pos - 1)
    elif direction == "down":
        new_pos = min(len(move_indexes) - 1, move_pos + 1)
    elif direction == "top":
        new_pos = 0
    elif direction == "bottom":
        new_pos = len(move_indexes) - 1
    else:
        return jsonify({"ok": False, "error": "direction must be up, down, top, or bottom"}), 400

    if new_pos != move_pos:
        movable_buttons = [buttons[i] for i in move_indexes]
        item = movable_buttons.pop(move_pos)
        movable_buttons.insert(new_pos, item)
        iterator = iter(movable_buttons)
        move_index_set = set(move_indexes)
        buttons = [next(iterator) if i in move_index_set else b for i, b in enumerate(buttons)]
        save_buttons(buttons)
    return jsonify({"ok": True, "buttons": buttons})


@app.route("/api/buttons/reorder", methods=["POST"])
def api_reorder_buttons():
    check_token()
    buttons = load_buttons()
    payload = request.get_json(force=True) or {}
    ids = payload.get("ids") or []
    if not isinstance(ids, list):
        return jsonify({"ok": False, "error": "ids must be a list"}), 400

    page = payload.get("page")
    by_id = {b.get("id"): b for b in buttons}
    if page and page != "All":
        page = clean_page(page)
        page_buttons = [b for b in buttons if clean_page(b.get("page")) == page]
        ordered = [by_id[i] for i in ids if i in by_id and clean_page(by_id[i].get("page")) == page]
        remaining_page = [b for b in page_buttons if b.get("id") not in set(ids)]
        page_order = iter(ordered + remaining_page)
        buttons = [next(page_order) if clean_page(b.get("page")) == page else b for b in buttons]
    else:
        ordered = [by_id[i] for i in ids if i in by_id]
        remaining = [b for b in buttons if b.get("id") not in set(ids)]
        buttons = ordered + remaining
    save_buttons(buttons)
    return jsonify({"ok": True, "buttons": buttons})



@app.route("/api/sounds", methods=["GET"])
def api_sounds():
    check_token()
    return jsonify({"ok": True, "sounds": list_sounds()})


@app.route("/api/sounds", methods=["POST"])
def api_upload_sound():
    check_token()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "กรุณาเลือกไฟล์เสียง"}), 400
    name = Path(file.filename).name
    if Path(name).suffix.lower() not in ALLOWED_SOUND_EXT:
        return jsonify({"ok": False, "error": "รองรับ .mp3, .wav, .m4a, .aac, .ogg, .flac"}), 400
    dest = SOUNDS_DIR / name
    file.save(dest)
    return jsonify({"ok": True, "filename": name, "sounds": list_sounds()})


@app.route("/api/icons", methods=["GET"])
def api_icons():
    check_token()
    return jsonify({"ok": True, "icons": list_icons()})


@app.route("/api/icons", methods=["POST"])
def api_upload_icon():
    check_token()
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "กรุณาเลือกไฟล์ไอคอน"}), 400
    name = safe_upload_name(file.filename)
    if Path(name).suffix.lower() not in ALLOWED_ICON_EXT:
        return jsonify({"ok": False, "error": "รองรับ .png, .jpg, .jpeg, .gif, .webp, .svg"}), 400
    dest = ICONS_DIR / name
    file.save(dest)
    return jsonify({"ok": True, "icon": f"/static/icons/{name}", "icons": list_icons()})

@app.route("/api/run/<button_id>", methods=["POST"])
def api_run(button_id):
    check_token()
    buttons = load_buttons()
    button = next((b for b in buttons if b.get("id") == button_id), None)
    if not button:
        return jsonify({"ok": False, "error": "button not found"}), 404
    try:
        result = run_button(button)
        return jsonify({"ok": True, "message": result, "button": button.get("title")})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print("=" * 60)
    print("Web Stream Deck Custom is running")
    print(f"Open on this computer: http://127.0.0.1:{PORT}/?token={TOKEN}")
    print(f"Open on phone/tablet: http://{lan_ip}:{PORT}/?token={TOKEN}")
    print(f"Settings page: http://{lan_ip}:{PORT}/settings?token={TOKEN}")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=False)
