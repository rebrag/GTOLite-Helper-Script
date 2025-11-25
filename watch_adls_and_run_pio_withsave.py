# watch_adls_and_run_pio.py
# Fast ADLS watcher that pastes TreeBuilding text into PioViewer,
# clicks "Save current parameters", types the flop as filename, hits Enter,
# then triggers Build & Go.

import os
import sys
import json
import time
import re
from datetime import datetime, timezone
from typing import List, Tuple, Set, Optional
import pathlib
import json as _json

# --- Azure Data Lake (Gen2) ---
from azure.storage.filedatalake import DataLakeServiceClient

# --- Windows UI automation & clipboard ---
from pywinauto import Application, keyboard, findwindows
from pywinauto.mouse import click
from pywinauto.timings import Timings
import pyperclip

JOBS_DIR = r"C:\PioJobs"  # create this folder once
os.makedirs(JOBS_DIR, exist_ok=True)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from pywinauto.base_wrapper import BaseWrapper  # type: ignore
except Exception:
    BaseWrapper = object  # fallback


# =========================
# Speed knobs
# =========================
try:
    Timings.fast()
except Exception:
    pass


def _set_timing(name: str, value: float):
    if hasattr(Timings, name):
        setattr(Timings, name, value)


_set_timing("after_clickinput_wait", 0.05)
_set_timing("after_setfocus_wait", 0.05)
_set_timing("after_sendkeys_key_wait", 0.05)
_set_timing("wait_between_actions", 0.05)

POLL_SECS = float(os.getenv("POLL_SECS", "0.6"))
TINY = 0.02

# =========================
# Config / Environment
# =========================
CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "onlinerangedata")
BASE_PREFIX = "gametrees"
WATCH_TODAY_ONLY = True

PIO_TITLE_RE = os.getenv("PIO_TITLE_RE", r"(?i).*PioViewer.*")


# =========================
# Logging
# =========================
def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


def today_subpath_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y/%m/%d")


# =========================
# Azure helpers
# =========================
def get_fs_client():
    if not CONN_STR:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING env var not set")
    dls = DataLakeServiceClient.from_connection_string(CONN_STR)
    return dls.get_file_system_client(CONTAINER)


def list_existing_json(fs, prefix_base: str, only_today: bool) -> Set[str]:
    seen: Set[str] = set()
    base = prefix_base.rstrip("/")
    want_prefix = f"{base}/{today_subpath_utc()}/" if only_today else f"{base}/"
    try:
        for p in fs.get_paths(path=base, recursive=True):
            if p.is_directory:
                continue
            if not p.name.endswith(".json"):
                continue
            if not p.name.startswith(want_prefix):
                continue
            seen.add(p.name)
    except Exception as e:
        log(f"[seed] error: {e}")
    return seen


def list_new_json(fs, seen: Set[str], prefix_base: str, only_today: bool) -> List[Tuple[str, str, str]]:
    results: List[Tuple[str, str, str]] = []
    base = prefix_base.rstrip("/")
    want_prefix = f"{base}/{today_subpath_utc()}/" if only_today else f"{base}/"
    try:
        for p in fs.get_paths(path=base, recursive=True):
            if p.is_directory:
                continue
            if not p.name.endswith(".json"):
                continue
            if not p.name.startswith(want_prefix):
                continue
            if p.name in seen:
                continue
            lm = (p.last_modified or datetime.now(timezone.utc)).isoformat()
            fname = p.name.rsplit("/", 1)[-1]
            results.append((p.name, fname, lm))
    except Exception as e:
        log(f"[list] error: {e}")
        return []
    results.sort(key=lambda t: t[2])
    return results


def download_text(fs, full_path: str) -> Optional[str]:
    try:
        file_client = fs.get_file_client(full_path)
        data = file_client.download_file().readall()
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        log(f"[download] error for {full_path}: {e}")
        return None


# =========================
# PioViewer attach & actions
# =========================
def attach_pioviewer(title_re: str) -> Optional[Application]:
    try:
        hwnds = findwindows.find_windows(title_re=title_re)
    except Exception:
        hwnds = []
    if not hwnds:
        log("  -> No PioViewer windows found")
        return None
    try:
        app = Application(backend="uia").connect(handle=hwnds[0])
        log(f"  -> Attached to PioViewer via handle {hwnds[0]}")
        app.top_window().set_focus()
        return app
    except Exception as e:
        log(f"  -> Failed to attach by handle: {e}")
        try:
            app = Application(backend="uia").connect(title_re=title_re, timeout=0.4)
            log("  -> Attached to PioViewer via title regex")
            app.top_window().set_focus()
            return app
        except Exception as e2:
            log(f"  -> Failed to attach by title regex: {e2}")
            return None


def focus_window_center(win):
    try:
        r = win.rectangle()
        cx, cy = (r.left + r.right) // 2, (r.top + r.bottom) // 2
        click(coords=(cx, cy))
        log(f"  -> Focused window center at ({cx}, {cy})")
    except Exception as e:
        log(f"  -> focus_window_center failed: {e}")


def _invoke_or_click(btn_spec, label: str = "(unknown)") -> bool:
    from time import perf_counter

    t0 = perf_counter()
    log(f"    [ioc] Trying '{label}'...")

    try:
        if hasattr(btn_spec, "exists"):
            try:
                if not btn_spec.exists(timeout=0.5):
                    log("    [ioc] btn_spec.exists(timeout=0.5) -> False")
                    return False
                else:
                    log("    [ioc] btn_spec.exists(timeout=0.5) -> True")
            except Exception as e:
                log(f"    [ioc] exists() check raised: {e}")

        ctrl = btn_spec.wrapper_object()  # type: ignore[assignment]
        try:
            txt = ctrl.window_text()
        except Exception:
            txt = "<no-text>"
        try:
            cname = ctrl.friendly_class_name()
        except Exception:
            cname = type(ctrl).__name__

        log(f"    [ioc] wrapper_object: class='{cname}', text='{txt}'")

        label_l = (label or "").lower()
        txt_l = (txt or "").lower()
        is_save_params = "save current parameters" in label_l or "save current parameters" in txt_l

        # For Save current parameters, only click_input to avoid blocking invoke()
        if is_save_params:
            log("    [ioc] Special-casing 'Save current parameters' -> click_input only (no invoke)")
            if hasattr(ctrl, "click_input"):
                try:
                    ctrl.click_input(button="left", double=False)  # type: ignore[attr-defined]
                    dt = perf_counter() - t0
                    log(f"    [ioc] ctrl.click_input() for 'Save current parameters' succeeded in {dt:.3f}s")
                    return True
                except Exception as e:
                    log(f"    [ioc] ctrl.click_input() for 'Save current parameters' raised: {e}")
                    return False
            else:
                log("    [ioc] ctrl has no click_input for 'Save current parameters'")
                return False

        if hasattr(ctrl, "invoke"):
            try:
                ctrl.invoke()  # type: ignore[attr-defined]
                dt = perf_counter() - t0
                log(f"    [ioc] ctrl.invoke() for '{label}' succeeded in {dt:.3f}s")
                return True
            except Exception as e:
                log(f"    [ioc] ctrl.invoke() for '{label}' raised: {e}")

        if hasattr(ctrl, "click_input"):
            try:
                ctrl.click_input(button="left", double=False)  # type: ignore[attr-defined]
                dt = perf_counter() - t0
                log(f"    [ioc] ctrl.click_input() for '{label}' succeeded in {dt:.3f}s")
                return True
            except Exception as e:
                log(f"    [ioc] ctrl.click_input() for '{label}' raised: {e}")

    except Exception as e:
        dt = perf_counter() - t0
        log(f"    [ioc] _invoke_or_click('{label}') failed in {dt:.3f}s: {e!r}")
        return False

    dt = perf_counter() - t0
    log(f"    [ioc] _invoke_or_click('{label}') finished with no action in {dt:.3f}s")
    return False


def click_paste_button(win) -> bool:
    patterns = [r"(?i)^Paste$"]
    for pat in patterns:
        try:
            btn_spec = win.child_window(title_re=pat, control_type="Button")
            if _invoke_or_click(btn_spec, label="Paste"):
                log("  -> Clicked 'Paste' button")
                return True
        except Exception as e:
            log(f"  -> Error locating Paste button with pattern '{pat}': {e}")
            continue
    log("  -> Paste button not found / not clicked")
    return False


def optimistic_build_and_go(win, max_wait_ms: int = 100) -> str:
    from time import perf_counter, sleep

    tried: List[str] = []
    log("  -> Attempting Build & Go")

    def try_once(tag: str) -> bool:
        try:
            btn_spec = win.child_window(title_re=r"(?i)^Build and Go$", control_type="Button")
            if _invoke_or_click(btn_spec, label=f"Build and Go ({tag})"):
                tried.append(tag + ":enabled")
                return True
        except Exception as e:
            log(f"    [build] Error locating Build and Go button ({tag}): {e}")
        try:
            keyboard.send_keys("{ENTER}", pause=0.0)
            tried.append(tag + ":ENTER")
            log(f"    [build] Sent ENTER for Build and Go ({tag})")
            return False
        except Exception as e:
            tried.append(tag + ":enter_fail")
            log(f"    [build] ENTER send failed ({tag}): {e}")
            return False

    if try_once("immediate"):
        return "BuildAndGo:immediate_enabled"

    deadline = perf_counter() + (max_wait_ms / 1000.0)
    while perf_counter() < deadline:
        if try_once("retry"):
            return "BuildAndGo:retry_enabled"
        sleep(0.025)

    try:
        btn_spec = win.child_window(
            title_re=r"(?i).*Build.*Go.*|.*Build.*|.*Run.*|.*Solve.*",
            control_type="Button",
        )
        if _invoke_or_click(btn_spec, label="Build/Run/Solve loose"):
            return "BuildAndGo:loose_match"
    except Exception as e:
        log(f"    [build] Loose match search failed: {e}")

    return "BuildAndGo:best_effort(" + ",".join(tried) + ")"


# =========================
# Board parsing + Save parameters
# =========================
def get_board_name(text: str, fallback_name: str) -> str:
    """Parse '#Board#4h Jh 5s' -> '4hJh5s'; else use filename stem."""
    m = re.search(r"#Board#([2-9TJQKA][shdc]\s+[2-9TJQKA][shdc]\s+[2-9TJQKA][shdc])", text)
    if m:
        board = m.group(1).replace(" ", "")
        log(f"  -> Parsed board '{board}' from text")
        return board
    stem = fallback_name.rsplit(".", 1)[0]
    log(f"  -> No board found in text, using fallback filename stem '{stem}'")
    return stem


def save_current_parameters_simple(main_win, board_name: str) -> bool:
    """
    VERY SIMPLE STRATEGY (what you requested):

      1. Click 'Save current parameters' on the main Pio window.
      2. Wait a short moment for the Save As dialog to appear (it grabs focus).
      3. Send Ctrl+A, Backspace, board_name, Enter via global keyboard.

    Assumes:
      - The Save As window is focused by default.
      - The File name field is focused by default.
    """
    try:
        btn_spec = main_win.child_window(
            title_re=r"(?i)save current parameters",
            control_type="Button",
        )
        clicked = _invoke_or_click(btn_spec, label="Save current parameters")
        log(f"  [save] _invoke_or_click('Save current parameters') returned {clicked}")
        if not clicked:
            log("  [save] Failed to click 'Save current parameters'")
            return False
        log("  -> Clicked 'Save current parameters'")
    except Exception as e:
        log(f"  [save] Error locating/clicking 'Save current parameters' button: {e}")
        return False

    # Give Windows/Pio a moment to show the Save As dialog & focus File name box
    time.sleep(0.5)

    try:
        seq1 = "^a{BACKSPACE}"
        seq2 = board_name
        seq3 = "{ENTER}"
        log(f"  [save] keyboard.send_keys({seq1!r}), then {seq2!r}, then {seq3!r}")
        keyboard.send_keys(seq1, pause=0.02)
        keyboard.send_keys(seq2, pause=0.02, with_spaces=False)
        keyboard.send_keys(seq3, pause=0.02)
        log(f"  [save] Typed '{board_name}' and pressed Enter in Save dialog")
        # tiny extra wait for dialog to close
        time.sleep(0.4)
        return True
    except Exception as e:
        log(f"  [save] Error sending keys to Save dialog: {e}")
        return False


# =========================
# Main loop
# =========================
def main():
    if not CONN_STR:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING env var not set")

    fs = get_fs_client()
    log("Connected to ADLS filesystem OK.")
    sub_today = today_subpath_utc()
    watch_label = f"{BASE_PREFIX}/{sub_today}" if WATCH_TODAY_ONLY else f"{BASE_PREFIX}/"
    log(f"Watching: {watch_label}/ (UTC)")
    log(f"PioViewer title regex: /{PIO_TITLE_RE}/")
    log(f"Poll: {POLL_SECS:.1f}s\n")

    seen = list_existing_json(fs, BASE_PREFIX, WATCH_TODAY_ONLY)
    if seen:
        log(f"Seeded with {len(seen)} existing file(s).")
    else:
        log("No existing files under prefix; starting fresh.")

    while True:
        new_items = list_new_json(fs, seen, BASE_PREFIX, WATCH_TODAY_ONLY)
        if new_items:
            for full_path, name, lm in new_items:
                seen.add(full_path)
                log(f"[NEW] {full_path}  (last_modified={lm})")

                raw = download_text(fs, full_path)
                if raw is None:
                    continue

                # Accept raw or JSON { "Text": "..." }
                try:
                    obj = json.loads(raw)
                    text = obj.get("Text") if isinstance(obj, dict) else raw
                    if not isinstance(text, str) or not text.strip():
                        text = raw
                except Exception:
                    text = raw

                pyperclip.copy(text)
                log(f"  -> Copied {len(text.encode('utf-8', 'ignore'))} bytes to clipboard")

                app = attach_pioviewer(PIO_TITLE_RE)
                if not app:
                    log("  -> PioViewer window not found (not starting a new one).")
                    continue

                win = app.top_window()
                log(f"  -> Pio top window title before paste: '{win.window_text()}'")
                focus_window_center(win)

                from time import perf_counter
                t0 = perf_counter()
                pasted = click_paste_button(win)
                if not pasted:
                    keyboard.send_keys("^v", pause=TINY)
                    log("  -> Sent Ctrl+V (fallback)")
                t1 = perf_counter()

                # Save current parameters using the flop as filename
                board_name = get_board_name(text, name)
                log(f"  -> Calling save_current_parameters_simple with board_name='{board_name}'")
                if save_current_parameters_simple(win, board_name):
                    log(f"  -> SaveCurrentParameters completed with filename '{board_name}'")
                else:
                    log("  -> WARNING: SaveCurrentParameters failed; continuing anyway")

                # Trigger Build & Go
                action = optimistic_build_and_go(win, max_wait_ms=200)
                t2 = perf_counter()

                # after: board_name = get_board_name(text, name)
                job = {
                    "board": board_name,
                    "tree_file": fr"C:\PioSOLVER\TreeBuilding\{board_name}.txt",
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                }
                job_path = pathlib.Path(JOBS_DIR) / f"{board_name}_{int(time.time())}.job.json"
                with open(job_path, "w", encoding="utf-8") as f:
                    _json.dump(job, f)
                log(f"  -> Enqueued UPI solve job: {job_path}")

                log(f"  -> Triggered via {action}")
                log(f"     timings: paste={(t1 - t0):.3f}s, paste->build={(t2 - t1):.3f}s")

        time.sleep(POLL_SECS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Exiting on Ctrl+C")
        sys.exit(0)
