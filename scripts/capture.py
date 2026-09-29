#!/usr/bin/env python3
"""Run the CLI examples on an Android emulator: record what each printed, and
take the screenshots the reference pages show.

A scenario marked verbatim runs exactly the command its page shows, so the
output under it is what that command printed. A screenshot whose command is
not the page's own says which command made it, in its caption.

Emulators only. It changes settings — appearance, orientation, locale,
timezone, the clipboard — and puts each back, but it is not for a phone.

    python3 scripts/capture.py --bin ./mobium --device emulator-5554 [--only app_tap]
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "static/img/shots"
RUNS = ROOT / "data/runs.json"

SETTINGS = "com.android.settings"
APP = "dev.mobium.mobiumapp"


def settings_root():
    return [f"terminate {SETTINGS}", f"launch {SETTINGS}"]


def cleared_shade():
    """The shade emptied first, so a picture of it shows this run's
    notifications and no earlier session's. "?" lets a step fail: with
    nothing in the shade there is no Clear all to tap."""
    return ["notifications --shade open", "?tap 'text=Clear all'", "?notifications --shade close"]


def web_storage():
    return [f"terminate {APP}", f"launch {APP}", "tap testid=webviewhubBtn", "tap testid=webstorageBtn",
            "wait text=Back", "context WEBVIEW_dev.mobium.mobiumapp"]


def gesture(name):
    return app_screen("Gestures") + [f"tap 'text={name}'"]


def app_screen(name):
    return [f"terminate {APP}", f"launch {APP}", f"tap 'text={name}'"]


# Each entry: the tool and the canonical index it runs (or None for a shot
# with a command of its own), what to do first, the command, whether to take
# a screenshot before and after, and what puts the device back.
PLAN = [
    dict(tool="app_devices", i=0),
    dict(tool="app_launch", i=0, setup=[f"terminate {SETTINGS}"], after=True),
    dict(tool="app_map", i=0, setup=settings_root(), after=True),
    dict(tool="app_text", i=0, setup=settings_root(), after=True),
    dict(tool="app_find", i=0, setup=settings_root(), after=True),
    dict(tool="app_current", i=0),
    dict(tool="app_state", i=0),
    dict(tool="app_tap", i=0, setup=settings_root(), before=True, after=True),
    dict(tool="app_scroll_to", i=0, setup=settings_root(), after=True),
    dict(tool="app_swipe", i=0, setup=settings_root(), before=True, after=True),
    dict(tool="app_batch", i=0, setup=settings_root(), files={"steps.json": "steps"}, after=True),
    dict(tool="app_press", i=1, setup=settings_root(), after=True),
    dict(tool="app_press", i=0, setup=settings_root() + ["tap 'text=Network & internet'", "wait text=Internet"],
         before=True, after=True),
    # From the home screen, so what is left behind Settings is the launcher.
    dict(tool="app_terminate", i=0, setup=["press home", f"terminate {SETTINGS}", f"launch {SETTINGS}",
                                           "wait 'text=Network & internet'"], before=True, after=True),
    dict(tool="app_appearance", i=0, setup=settings_root(), after=True, restore=["appearance light"]),
    dict(tool="app_orientation", i=0, setup=settings_root(), after=True, restore=["orientation portrait"]),
    dict(tool="app_screen", i=0),
    dict(tool="app_screen", i=None, cmd="screen small-phone", setup=settings_root(), after=True,
         restore=["screen reset"]),
    dict(tool="app_accessibility", i=0),
    dict(tool="app_accessibility", i=1, setup=settings_root(), after=True,
         restore=["accessibility bold_text off"]),
    dict(tool="app_notifications", i=0, setup=cleared_shade()),
    dict(tool="app_notifications", i=1, after=True, restore=["notifications --shade close"]),
    dict(tool="app_check", i=0, setup=app_screen("Form Demo"), before=True, after=True),
    dict(tool="app_wait_for", i=2, setup=app_screen("Form Demo") + ["check testid=termsCheck"]),
    dict(tool="app_fill", i=None, cmd="fill testid=username mobium", setup=app_screen("Login Demo"), after=True),
    dict(tool="app_keyboard", i=0, setup=app_screen("Login Demo") + ["tap testid=username"], after=True),
    # The keyboard slides in after the tap; the pause lets the picture show it up.
    dict(tool="app_keyboard", i=1, setup=app_screen("Login Demo") + ["tap testid=username", "$sleep 1.5"],
         before=True, after=True),
    dict(tool="app_alert", i=0, setup=app_screen("Dialog Demo") + ["tap 'text=Two-button alert'", "wait 'text=Discard changes?'"], after=True,
         restore=["alert dismiss"]),
    dict(tool="app_alert", i=1, setup=app_screen("Dialog Demo") + ["tap 'text=Two-button alert'", "wait 'text=Discard changes?'"], before=True, after=True),
    dict(tool="app_locale", i=0, after=False,
         restore=["locale org.wikipedia ''"]),
    dict(tool="app_locale", i=None, cmd="launch org.wikipedia",
         setup=["terminate org.wikipedia", "locale org.wikipedia ja-JP"], after=True,
         restore=["locale org.wikipedia ''", "terminate org.wikipedia"]),
    dict(tool="app_screenshot", i=0, setup=settings_root(), shot_from="screen.png"),
    dict(tool="app_clipboard", i=0, setup=settings_root(), after=True, pause=0.5),
    dict(tool="app_clipboard", i=1),
    dict(tool="app_location", i=0, setup=[f"grant {APP} location"] + app_screen("Location Demo"), after=True,
         pause=3.0, restore=[f"reset-permissions {APP}"]),
    dict(tool="app_location", i=1),
    # The Clock app's big digits, not Settings' Date & time: there the zone
    # and the time are grey text, and the two pictures looked the same.
    dict(tool="app_timezone", i=0,
         setup=["terminate com.google.android.deskclock", "launch com.google.android.deskclock", "tap testid=tab_menu_clock",
                "wait 'label=Add city'"],
         before=True, after=True, pause=2.0, restore=["timezone {timezone}", "terminate com.google.android.deskclock"]),
    dict(tool="app_time", i=0),
    dict(tool="app_network", i=0, setup=settings_root() + ["tap 'text=Network & internet'", "wait text=Internet"],
         before=True, after=True, pause=2.0, restore=["network --reset"]),
    dict(tool="app_network", i=1, restore=["network --reset"]),
    dict(tool="app_dialogs", i=0),
    dict(tool="app_dialogs", i=1),
    dict(tool="app_sms", i=0, setup=cleared_shade() + settings_root(), after=True, pause=2.0),
    dict(tool="app_call", i=0, after=True, pause=2.0),
    dict(tool="app_call", i=1),
    dict(tool="app_background", i=0, setup=settings_root()),
    dict(tool="app_shake", i=0),
    # The Pinch and Spread page shows its own scale; it has to have loaded before
    # the first picture, or the pair shows the Gestures list and a blank page.
    dict(tool="app_zoom", i=0, setup=gesture("Pinch and Spread") + ["wait testid=pinchWebview", "$sleep 3"],
         before=True, after=True, pause=2.0),
    dict(tool="app_record", i=0, setup=settings_root()),
    dict(tool="app_record", i=1, setup=["swipe up"]),
    dict(tool="app_list_apps", i=0),
    dict(tool="app_contexts", i=0, setup=app_screen("WebViews") + ["tap 'text=Plain page'", "wait text=Back"],
         after=True),
    # Gestures, each on the MobiumApp screen that reports what it received.
    dict(tool="app_tap", i=None, cmd="double-tap testid=pressTarget", setup=gesture("Tap and Press"),
         before=True, after=True),
    dict(tool="app_long_press", i=None, cmd="long-press testid=pressTarget", setup=gesture("Tap and Press"),
         before=True, after=True),
    dict(tool="app_drag", i=None, cmd="drag 'label=Drag source' 'label=Drop zone'", setup=gesture("Drag"),
         before=True, after=True),
    dict(tool="app_rotate", i=None, cmd="rotate 90", setup=gesture("Rotate") + ["wait text=Back"],
         before=True, after=True, pause=2.0),
    dict(tool="app_press_tap", i=None, cmd="press-tap 'label=Hold zone' 'label=Act zone'",
         setup=gesture("Multi-Touch"), after=True),
    dict(tool="app_press_drag", i=None, cmd="press-drag 'label=Hold zone' 'label=Act zone' 'label=Drag end'",
         setup=gesture("Multi-Touch"), after=True),
    # Reading and writing a field, on the Login Demo.
    dict(tool="app_type", i=None, cmd="type testid=username mobium", setup=app_screen("Login Demo"),
         before=True, after=True),
    dict(tool="app_wait_for", i=None,
         cmd="wait testid=loginError --for text --text 'Incorrect username or password.'",
         setup=app_screen("Login Demo") + ["fill testid=username mobium", "fill testid=password wrongpass1",
                                          "keyboard --hide", "tap testid=loginBtn"], after=True),
    # A WebView's content, on MobiumApp's plain page.
    dict(tool="app_eval", i=None, cmd="eval document.title",
         setup=app_screen("WebViews") + ["tap 'text=Plain page'", "wait text=Back", "context WEBVIEW_dev.mobium.mobiumapp"],
         after=True, restore=["context NATIVE_APP"]),
    # The rest of the WebView tools, on the same page.
    dict(tool="app_context", i=None, cmd="context WEBVIEW_dev.mobium.mobiumapp",
         setup=app_screen("WebViews") + ["tap 'text=Plain page'", "wait text=Back"], after=True,
         restore=["context NATIVE_APP"]),
    dict(tool="app_cookies", i=0,
         setup=app_screen("WebViews") + ["tap 'text=Plain page'", "wait text=Back", "context WEBVIEW_dev.mobium.mobiumapp"],
         after=True, restore=["context NATIVE_APP"]),
    # Web storage, on the page with an origin of its own.
    dict(tool="app_storage", i=0, setup=web_storage() + ["eval \"document.getElementById('saveVisit').click()\""],
         after=True),
    # The page redraws what it holds once a second; the pause lets the cleared
    # state show before the picture of it.
    dict(tool="app_storage", i=1, setup=["storage clear", "$sleep 1.5"], before=True, after=True, pause=1.5,
         restore=["storage clear", "context NATIVE_APP"]),
    # The battery, set by the emulator's console, and the app's own reading.
    dict(tool="app_battery", i=0,
         setup=["$adb emu power ac off", "$adb emu power status discharging", "$adb emu power capacity 42",
                f"terminate {APP}", f"launch {APP}", "tap testid=batteryBtn",
                "wait testid=batteryLevel --for text --text 'level: 42%'"],
         after=True, restore=["$adb emu power ac on", "$adb emu power status charging", "$adb emu power capacity 100"]),
    # A dialog rule, answering the dialog in the way of a later action.
    dict(tool="app_dialogs", i=None, cmd="tap testid=oneButtonBtn",
         setup=app_screen("Dialog Demo") + ["dialogs --clear",
                                            "dialogs --when 'Discard changes' --press 'Keep Editing'",
                                            "tap testid=twoButtonBtn", "$sleep 1.5"],
         before=True, after=True, pause=1.5, restore=["?alert accept", "dialogs --clear"],
         caption="With `mobium dialogs --when \"Discard changes\" --press \"Keep Editing\"` declared, "
                 "`mobium tap testid=oneButtonBtn` met the Discard dialog in its way, pressed Keep Editing, and "
                 "went on — its own alert is up, and the line under the title says what the app received — "
                 "on an Android 15 emulator"),
    dict(tool="app_check", i=None, cmd="uncheck testid=termsCheck",
         setup=app_screen("Form Demo") + ["check testid=termsCheck"], before=True, after=True),
    dict(tool="app_open_url", i=None, cmd="open https://en.wikipedia.org/wiki/Mobile_app",
         setup=["terminate org.wikipedia"], after=True, pause=3.0, restore=["terminate org.wikipedia"]),
    dict(tool="app_session", i=0),
    dict(tool="app_session", i=1),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--device", required=True)
    ap.add_argument("--only", action="append")
    a = ap.parse_args()
    if not a.device.startswith("emulator-"):
        raise SystemExit("capture changes device settings; it runs on an emulator only")
    binary = str(Path(a.bin).resolve())
    canon = json.loads((ROOT / "examples/canonical.json").read_text())
    runs = json.loads(RUNS.read_text()) if RUNS.exists() else {}
    SHOTS.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp())
    env = dict(os.environ, ANDROID_SERIAL=a.device)
    home = str(Path.home())

    def mobium(cmd, check=True):
        r = subprocess.run(f"{shlex.quote(binary)} --device {a.device} {cmd}", shell=True, cwd=work,
                           capture_output=True, text=True, env=env)
        if check and r.returncode:
            raise SystemExit(f"setup `mobium {cmd}` failed: {r.stderr.strip()}")
        return r

    def shot(name):
        png = work / "shot.png"
        mobium(f"screenshot -o {png}")
        return save(png, name)

    def save(png, name):
        out = SHOTS / f"{name}.jpg"
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", "--resampleHeightWidthMax", "800",
                        str(png), "--out", str(out)], capture_output=True, check=True)
        return f"/img/shots/{name}.jpg"

    tz = mobium("--json timezone").stdout
    timezone = json.loads(tz).get("timezone", "") if tz.strip().startswith("{") else ""
    for p in PLAN:
        tool, i = p["tool"], p["i"]
        if a.only and tool not in a.only:
            continue
        key = f"{tool}[{i}]" if i is not None else f"{tool}:{p['cmd']}"
        for s in p.get("setup", []):
            if s.startswith("$"):
                # A step that is not mobium's — the emulator console, which is
                # the only thing that can set a battery.
                subprocess.run(s[1:], shell=True, env=env, capture_output=True, check=True)
            elif s.startswith("?"):
                mobium(s[1:], check=False)
            else:
                mobium(s)
        for fname, what in p.get("files", {}).items():
            (work / fname).write_text(json.dumps(canon[tool][i]["args"][what], indent=2) + "\n")
        entry = {"tool": tool, "index": i}
        stem = f"{tool}-{i}" if i is not None else f"{tool}-{re.sub(r'[^a-z0-9]+', '-', p['cmd'].lower()).strip('-')[:40]}"
        if p.get("before"):
            entry["before"] = shot(f"{stem}-before")
        cmd = p.get("cmd") or canon[tool][i]["cli"]
        shown = cmd if p.get("cmd") is None else "mobium " + cmd
        run = cmd.removeprefix("mobium ") if p.get("cmd") is None else cmd
        time.sleep(0.3)
        r = mobium(run, check=False)
        out = (r.stdout + r.stderr).replace(os.path.realpath(work), "…").replace(str(work), "…")
        out = out.replace(home, "~").rstrip("\n")
        if tool == "app_devices":
            # Only the emulator: this Mac's other devices are its owner's
            # business, and a phone's id is somebody's.
            out = "\n".join(l for l in out.splitlines() if l.startswith("emulator-"))
        entry.update(command=shown, verbatim=p.get("cmd") is None, exit=r.returncode, output=out)
        if p.get("caption"):
            entry["caption"] = p["caption"]
        if p.get("after"):
            time.sleep(p.get("pause", 1.0))
            entry["after"] = shot(f"{stem}-after")
        if p.get("shot_from"):
            entry["after"] = save(work / p["shot_from"], f"{tool}-{i}-after")
        for s in p.get("restore", []):
            if s.startswith("$"):
                subprocess.run(s[1:], shell=True, env=env, capture_output=True)
            else:
                mobium(s.format(timezone=shlex.quote(timezone)), check=False)
        runs[key] = entry
        print(f"{'ok ' if r.returncode == 0 else 'ERR'} {key}: {shown} (exit {r.returncode})")
    RUNS.write_text(json.dumps(runs, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
