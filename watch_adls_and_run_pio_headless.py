import os
import sys
import json
import time
import re
from datetime import datetime, timezone
from typing import List, Tuple, Set, Optional, IO, Any, Dict
import subprocess
import math

# --- Azure Data Lake (Gen2) ---
from azure.storage.filedatalake import DataLakeServiceClient

# --- Windows UI automation & clipboard ---
from pywinauto import Application, keyboard, findwindows
from pywinauto.mouse import click
from pywinauto.timings import Timings
import pyperclip

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
END_MARK = "END"  # Pio UPI end marker

# =========================
# Config / Environment
# =========================
CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "onlinerangedata")
BASE_PREFIX = "gametrees"
WATCH_TODAY_ONLY = True

PIO_TITLE_RE = os.getenv("PIO_TITLE_RE", r"(?i).*PioViewer.*")

# Pio console exe (headless solver)
PIO_EXE = os.getenv("PIO_EXE", r"C:\PioSOLVER\PioSOLVER2-edge.exe")

# Where Save current parameters writes the scripts
TREEBUILD_DIR = os.getenv("PIO_TREEBUILD_DIR", r"C:\PioSOLVER\TreeBuilding")

# Name of the tree script file Pio saves (without .txt) – now fixed "temp"
TREE_SCRIPT_BASENAME = os.getenv("PIO_TREE_SCRIPT_BASENAME", "temp")

# Where we want .cfr files (subdir under Pio dir)
CFR_SUBDIR = os.getenv("PIO_CFR_SUBDIR", "Solved")

# Accuracy (in % exploitability, e.g. 0.5 means solve until ~0.5% exploit)
ACCURACY = float(os.getenv("PIO_ACCURACY", "0.05"))

# pyosolver Pio dir (where PioSOLVER2-edge.exe lives)
PIO_DIR_FOR_PYOSOLVER = os.getenv("PIO_DIR_FOR_PYOSOLVER", r"C:\PioSOLVER")

# Optional local JSON dump dir for debugging / inspection
TEMP_JSON_DIR = os.getenv("PIO_TEMP_JSON_DIR", r"C:\PioSOLVER\TempJson")
if TEMP_JSON_DIR:
    os.makedirs(TEMP_JSON_DIR, exist_ok=True)


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


def list_new_json(
    fs, seen: Set[str], prefix_base: str, only_today: bool
) -> List[Tuple[str, str, str]]:
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


def node_id_to_suffix(node_id: Optional[str], fallback: str = "root") -> str:
    """
    Turn a pyosolver node_id like 'r:0:1' into a safe suffix 'r.0.1'
    for filenames / URLs. If node_id is None, use fallback.
    """
    if not node_id:
        return fallback
    return node_id.replace(":", ".")


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
            log("    [ioc] Special-casing 'Save current parameters' -> click_input only")
            if hasattr(ctrl, "click_input"):
                try:
                    ctrl.click_input(button="left", double=False)  # type: ignore[attr-defined]
                    dt = perf_counter() - t0
                    log(f"    [ioc] click_input() for 'Save current parameters' in {dt:.3f}s")
                    return True
                except Exception as e:
                    log(f"    [ioc] click_input() for 'Save current parameters' raised: {e}")
                    return False
            else:
                log("    [ioc] ctrl has no click_input for 'Save current parameters'")
                return False

        if hasattr(ctrl, "invoke"):
            try:
                ctrl.invoke()  # type: ignore[attr-defined]
                dt = perf_counter() - t0
                log(f"    [ioc] invoke() for '{label}' succeeded in {dt:.3f}s")
                return True
            except Exception as e:
                log(f"    [ioc] invoke() for '{label}' raised: {e}")

        if hasattr(ctrl, "click_input"):
            try:
                ctrl.click_input(button="left", double=False)  # type: ignore[attr-defined]
                dt = perf_counter() - t0
                log(f"    [ioc] click_input() for '{label}' succeeded in {dt:.3f}s")
                return True
            except Exception as e:
                log(f"    [ioc] click_input() for '{label}' raised: {e}")

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


def save_current_parameters_simple(main_win, script_basename: str) -> bool:
    """
    Click 'Save current parameters', then type script_basename in the Save dialog and press Enter.
    This controls the name of the TreeBuilding .txt file (e.g. temp.txt).
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

    time.sleep(0.5)

    try:
        seq1 = "^a{BACKSPACE}"
        seq2 = script_basename
        seq3 = "{ENTER}"
        log(f"  [save] keyboard.send_keys({seq1!r}), then {seq2!r}, then {seq3!r}")
        keyboard.send_keys(seq1, pause=0.02)
        keyboard.send_keys(seq2, pause=0.02, with_spaces=False)
        keyboard.send_keys(seq3, pause=0.02)
        log(f"  [save] Typed '{script_basename}' and pressed Enter in Save dialog")
        time.sleep(0.4)
        return True
    except Exception as e:
        log(f"  [save] Error sending keys to Save dialog: {e}")
        return False


# =========================
# Pio console (UPI) client
# =========================
class PioClient:
    """
    Simple wrapper around a PioSOLVER console process using UPI.
    Now used as a context manager so each instance is short-lived.
    """

    def __init__(self, exe_path: str):
        pio_dir = os.path.dirname(exe_path) or "."
        self.pio_dir = os.path.abspath(pio_dir)

        log(f"Starting PioSOLVER process: {exe_path} (cwd={self.pio_dir})")

        self.proc = subprocess.Popen(
            [exe_path],
            cwd=self.pio_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
        )

        stdin = self.proc.stdin
        stdout = self.proc.stdout
        if stdin is None or stdout is None:
            raise RuntimeError("Failed to get stdin/stdout for PioSOLVER process")

        self._stdin: IO[str] = stdin
        self._stdout: IO[str] = stdout

        # set end marker
        _ = self.send_cmd(f"set_end_string {END_MARK}", log_cmd=False)
        log("PioSOLVER started and END marker set")

    def __enter__(self) -> "PioClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def send_cmd(self, cmd: str, log_cmd: bool = True) -> str:
        """Send one UPI command and read until END line."""
        if not self.is_alive():
            raise RuntimeError("PioSOLVER process is not running")

        if log_cmd:
            log(f"  [UPI] >> {cmd}")

        try:
            self._stdin.write(cmd + "\n")
            self._stdin.flush()
        except OSError as e:
            raise RuntimeError(f"Failed to send command '{cmd}' to PioSOLVER: {e}") from e

        lines: list[str] = []
        for line in self._stdout:
            line = line.rstrip("\r\n")
            if line == END_MARK:
                break
            lines.append(line)

        resp = "\n".join(lines)
        if resp:
            last = resp.splitlines()[-1]
            log(f"  [UPI] << {last}")
        return resp

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def close(self):
        """
        Try very hard to shut down the PioSOLVER process so we don't leave
        licensed processes hanging around.
        """
        if not self.is_alive():
            return

        log("Shutting down PioSOLVER process...")
        try:
            # polite exit via UPI
            try:
                self.send_cmd("exit", log_cmd=False)
            except Exception as e:
                log(f"  [close] error sending 'exit': {e}")

            # then wait a bit
            try:
                self.proc.wait(timeout=10.0)
                log("  [close] PioSOLVER exited cleanly.")
                return
            except subprocess.TimeoutExpired:
                log("  [close] PioSOLVER did not exit in time; terminating...")
        except Exception as e:
            log(f"  [close] unexpected error during exit: {e}")

        # fallback: terminate/kill
        try:
            self.proc.terminate()
        except Exception as e:
            log(f"  [close] terminate() failed: {e}")

        try:
            self.proc.wait(timeout=5.0)
            log("  [close] PioSOLVER terminated.")
        except subprocess.TimeoutExpired:
            log("  [close] terminate timed out; killing...")
            try:
                self.proc.kill()
                log("  [close] PioSOLVER killed.")
            except Exception as e:
                log(f"  [close] kill() failed: {e}")


# =========================
# Helper: parse wait_for_solver output
# =========================
def parse_wait_stats(wait_output: str) -> Dict[str, Optional[float]]:
    """
    Extract EV OOP / EV IP / Exploitable from wait_for_solver text.
    Returns a dict with keys: ev_oop, ev_ip, exploitable (floats or None).
    """
    ev_oop = ev_ip = exploitable = None

    m_oop = re.search(r"EV OOP:\s*([-\d\.]+)", wait_output)
    m_ip = re.search(r"EV IP:\s*([-\d\.]+)", wait_output)
    m_expl = re.search(r"Exploitable for:\s*([-\d\.]+)", wait_output)

    if m_oop:
        try:
            ev_oop = float(m_oop.group(1))
        except ValueError:
            pass
    if m_ip:
        try:
            ev_ip = float(m_ip.group(1))
        except ValueError:
            pass
    if m_expl:
        try:
            exploitable = float(m_expl.group(1))
        except ValueError:
            pass

    return {
        "ev_oop": ev_oop,
        "ev_ip": ev_ip,
        "exploitable": exploitable,
    }


def parse_stacks_and_hero_bb(stacks_str: Optional[str], node_name: Optional[str]) -> tuple[Dict[str, int], Optional[int], Optional[str]]:
    """
    Parse something like '25LJ_25HJ_25CO_6BTN_25SB_13BB' into a mapping:
      { 'LJ': 25, 'HJ': 25, 'CO': 25, 'BTN': 6, 'SB': 25, 'BB': 13 }
    and try to infer the hero seat & stack from '..._pos=BB_...' in node_name.
    """
    stacks_map: Dict[str, int] = {}
    hero_bb: Optional[int] = None
    hero_pos: Optional[str] = None

    if stacks_str:
        for token in stacks_str.split("_"):
            m = re.match(r"(\d+)([A-Za-z0-9]+)", token)
            if not m:
                continue
            bb_val = int(m.group(1))
            pos_code = m.group(2)
            stacks_map[pos_code] = bb_val

    if node_name:
        m2 = re.search(r"_pos=([^_]+)", node_name)
        if m2:
            hero_pos = m2.group(1)

    if hero_pos and stacks_map:
        hero_bb = stacks_map.get(hero_pos)

    return stacks_map, hero_bb, hero_pos


# =========================
# Solve + dump_tree + wait for CFR
# =========================
def solve_tree_to_cfr(
    pio: PioClient, tree_script_path: str, board: str
) -> Tuple[str, str, Dict[str, Optional[float]]]:
    """
    Given a TreeBuilding .txt (from Save current parameters),
    build & solve headless and dump_tree to a .cfr file.
    Returns:
      (cfr_full_path, wait_output_text, stats_dict)
    """
    tree_script_path = os.path.abspath(tree_script_path)
    if not os.path.isfile(tree_script_path):
        raise FileNotFoundError(tree_script_path)

    log(f"Solving tree for board {board} using script: {tree_script_path}")

    # sanity check
    resp_present = pio.send_cmd("is_tree_present", log_cmd=False)
    log(f"  [UPI] is_tree_present before load_script_silent: {resp_present}")

    # set accuracy
    pio.send_cmd(f"set_accuracy {ACCURACY}")

    # load script
    pio.send_cmd(f'load_script_silent "{tree_script_path}"')

    # solve
    pio.send_cmd("go")
    wait_resp = pio.send_cmd("wait_for_solver")
    log(f"  [UPI] wait_for_solver response:\n{wait_resp}")

    stats = parse_wait_stats(wait_resp)

    # make sure solver is stopped
    pio.send_cmd("stop", log_cmd=False)

    # construct CFR path
    cfr_dir_full = os.path.join(pio.pio_dir, CFR_SUBDIR)
    os.makedirs(cfr_dir_full, exist_ok=True)
    cfr_full = os.path.abspath(os.path.join(cfr_dir_full, f"{board}.cfr"))
    log(f"  [UPI] Target CFR path: {cfr_full}")

    # request dump_tree
    dump_cmd = f'dump_tree "{cfr_full}" full'
    dump_resp = pio.send_cmd(dump_cmd)
    log(f"  [UPI] dump_tree full response:\n{dump_resp if dump_resp else '(no output)'}")

    # actively wait for CFR file to appear on disk
    max_wait = float(os.getenv("PIO_CFR_WAIT_SECS", "600"))  # default: 10 minutes
    poll = 2.0  # seconds
    deadline = time.time() + max_wait
    told_waiting = False
    last_size = -1

    while time.time() < deadline:
        if os.path.exists(cfr_full):
            size = os.path.getsize(cfr_full)
            if last_size < 0:
                log(f"  -> CFR file detected: {cfr_full} (size={size} bytes)")
            elif size != last_size:
                log(f"  -> CFR file size updated: {size} bytes")
            last_size = size
            if size > 0:
                log(f"  -> dump_tree appears complete: {cfr_full}")
                break
        else:
            if not told_waiting:
                log(
                    f"  -> CFR file not present yet; waiting up to {max_wait:.0f}s "
                    f"for Pio to finish writing..."
                )
                told_waiting = True

        time.sleep(poll)
    else:
        log(
            f"  -> WARNING: CFR file still not found after waiting "
            f"{max_wait:.0f}s: {cfr_full}"
        )

    return cfr_full, wait_resp, stats


# =========================
# pyosolver helpers (root + check)
# =========================
def safe_show_tree_info(solver) -> Dict[str, Any]:
    """
    Safer version of show_tree_info that parses the raw output from
    `show_tree_info` ourselves.
    """
    raw = solver._run("show_tree_info")  # type: ignore[attr-defined]
    info: Dict[str, Any] = {}

    if not raw:
        return info

    for line in raw.splitlines():
        line = line.strip()
        if not line or "#" not in line:
            continue
        parts = line.split("#")
        if len(parts) < 3:
            continue
        _, key, value = parts[0], parts[1], "#".join(parts[2:])
        info[key.strip()] = value.strip()

    return info


def extract_root_and_check_summary(cfr_path: str) -> Optional[Dict[str, Any]]:
    """
    Use PYOSolver to extract:
      - tree_info (EV OOP, EV IP, Exploitable, etc. as strings)
      - hand_order (1326 combo order)
      - root node ("r:0") basic info + ranges + strategy + EVs
      - node after root -> check (if any) same as above

    Returns JSON-serializable dict or None on failure.
    """
    try:
        from pyosolver import PYOSolver  # type: ignore[import]
    except Exception as e:
        log(f"  [PYOSolver] Not available (install 'pyosolver'): {e}")
        return None

    if not os.path.exists(cfr_path):
        log(f"  [PYOSolver] CFR not found: {cfr_path}")
        return None

    solver = PYOSolver(PIO_DIR_FOR_PYOSOLVER, "PioSOLVER2-edge.exe", debug=False)

    try:
        # Load the CFR
        solver.load_tree(cfr_path)

        # Robust tree info (using safe_show_tree_info)
        tree_info = safe_show_tree_info(solver)
        hand_order = solver.show_hand_order()

        root_id = "r:0"
        root_node = solver.show_node(root_id)
        root_pos = root_node.get_position() if root_node is not None else None

        def safe_range(position: str, node_id: str) -> Optional[List[float]]:
            r = solver.show_range(position, node_id)
            if r is None:
                return None
            return list(r)

        def safe_strategy(node_id: str) -> Optional[List[List[float]]]:
            try:
                s = solver.show_strategy(node_id)
                return [list(row) for row in s]
            except Exception:
                return None

        def safe_ev(position: str, node_id: str) -> Optional[List[float]]:
            """
            Per-combo EVs for the given position at this node, using calc_ev.
            """
            try:
                evs, _matchups = solver.calc_ev(position, node_id)
            except Exception:
                return None
            if evs is None:
                return None
            return list(evs)

        def safe_matchups(position: str, node_id: str) -> Optional[List[float]]:
            """
            Per-combo 'matchups' vector from calc_ev (can be used for equity-like calcs).
            """
            try:
                _evs, matchups = solver.calc_ev(position, node_id)
            except Exception:
                return None
            if matchups is None:
                return None
            return list(matchups)

        # Root view
        root_view: Dict[str, Any] = {
            "node_id": root_id,
            "position": root_pos,
            "board": list(root_node.board) if root_node is not None else None,
            "pot": list(root_node.pot) if root_node is not None else None,
            "flags": list(root_node.flags) if root_node is not None else None,
            "ranges": {
                "oop": safe_range("OOP", root_id),
                "ip": safe_range("IP", root_id),
            },
            "strategy": safe_strategy(root_id),
            "evs": {
                "oop": safe_ev("OOP", root_id),
                "ip": safe_ev("IP", root_id),
            },
            "matchups": {
                "oop": safe_matchups("OOP", root_id),
                "ip": safe_matchups("IP", root_id),
            },
        }

        # Children from root
        children = solver.show_children(root_id) or []
        actions = solver.show_children_actions(root_id) or []
        root_view["actions"] = actions

        check_idx: Optional[int] = None
        for i, act in enumerate(actions):
            a = (act or "").lower().strip()
            if a in ("x", "check", "c"):
                check_idx = i
                break

        check_view: Optional[Dict[str, Any]] = None
        if check_idx is not None and 0 <= check_idx < len(children):
            child = children[check_idx]
            cid = child.node_id

            # Actions *from* the check-node to its children
            check_children_actions = solver.show_children_actions(cid) or []

            check_view = {
                "node_id": cid,
                "position": child.get_position(),
                "board": list(child.board),
                "pot": list(child.pot),
                "flags": list(child.flags),
                "action_label": actions[check_idx],
                "actions": check_children_actions,
                "ranges": {
                    "oop": safe_range("OOP", cid),
                    "ip": safe_range("IP", cid),
                },
                "strategy": safe_strategy(cid),
                "evs": {
                    "oop": safe_ev("OOP", cid),
                    "ip": safe_ev("IP", cid),
                },
                "matchups": {
                    "oop": safe_matchups("OOP", cid),
                    "ip": safe_matchups("IP", cid),
                },
            }

        summary: Dict[str, Any] = {
            "tree_info": tree_info,
            "hand_order": hand_order,
            "root": root_view,
            "root_check": check_view,
        }
        return summary
    finally:
        # If PYOSolver has any cleanup, you could add it here
        try:
            close_fn = getattr(solver, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass


# =========================
# 1326 -> 169 aggregation helpers
# =========================
RANKS = "AKQJT98765432"
RANK_INDEX = {r: i for i, r in enumerate(RANKS)}  # A highest, 2 lowest


def combo_to_hand_class(hand: str) -> str:
    """
    Convert a specific combo like 'AhKd' or 'AsAd' to a 169-class:
      - 'AA', 'KK', ...
      - 'AKs', 'AKo', etc.
    Assumes hand is exactly 4 chars, RankSuitRankSuit.
    """
    r1, s1, r2, s2 = hand[0], hand[1], hand[2], hand[3]

    # Pairs -> 'AA', 'KK', etc. (rank repeated once)
    if r1 == r2:
        return r1 + r2

    # Order ranks highest-first for canonical representation (AK, KQ, etc.)
    if RANK_INDEX[r1] < RANK_INDEX[r2]:
        hi, lo = r1, r2
        suited = (s1 == s2)
    else:
        hi, lo = r2, r1
        suited = (s1 == s2)

    return f"{hi}{lo}{'s' if suited else 'o'}"


def hand_class_sort_key(cls: str) -> tuple:
    """
    Sort pairs first (AA, KK...), then suited, then offsuit, high-card-first.
    """
    if len(cls) == 2:  # pair
        return (0, RANK_INDEX[cls[0]])
    hi, lo, suited_char = cls[0], cls[1], cls[2]
    suited = (suited_char == "s")
    return (1, RANK_INDEX[hi], RANK_INDEX[lo], 0 if suited else 1)


def aggregate_1326_to_169(
    hand_order: List[str],
    values_1326: List[float],
) -> Dict[str, float]:
    """
    Aggregate a 1326-length vector into 169 hand classes by simple average.
    Returns a dict like { 'AA': ev, 'AKs': ev, ... }.
    """
    from collections import defaultdict

    buckets: Dict[str, List[float]] = defaultdict(list)
    for hand, v in zip(hand_order, values_1326):
        cls = combo_to_hand_class(hand)
        buckets[cls].append(v)

    out: Dict[str, float] = {}
    for cls, vals in buckets.items():
        if vals:
            out[cls] = sum(vals) / len(vals)
    return out


def aggregate_strategy_1326_to_169(
    hand_order: List[str],
    strategy: List[List[float]],
) -> Tuple[List[str], List[List[float]]]:
    """
    Aggregate a 1326xActions strategy matrix into 169xActions.

    strategy is [actions][1326].
    Returns (hand_classes, matrix_169) where
      - hand_classes is a sorted list of 169 keys (AA, AKo, AKs, ...)
      - matrix_169 is [actions][169].
    """
    from collections import defaultdict

    if not strategy or not hand_order:
        return [], []

    n_actions = len(strategy)
    n_combos = len(hand_order)

    # sanity: each row length should match hand_order
    for row in strategy:
        if len(row) != n_combos:
            log("  [agg] Warning: strategy row length != hand_order length")
            return [], []

    sum_by_class: Dict[str, List[float]] = {}
    count_by_class: Dict[str, int] = defaultdict(int)

    for idx, hand in enumerate(hand_order):
        cls = combo_to_hand_class(hand)
        if cls not in sum_by_class:
            sum_by_class[cls] = [0.0] * n_actions
        for a in range(n_actions):
            sum_by_class[cls][a] += strategy[a][idx]
        count_by_class[cls] += 1

    # Order the classes canonically
    hand_classes = sorted(sum_by_class.keys(), key=hand_class_sort_key)

    # Build matrix_169[action][class_index]
    matrix_169: List[List[float]] = []
    for a in range(n_actions):
        row: List[float] = []
        for cls in hand_classes:
            cnt = count_by_class[cls]
            if cnt <= 0:
                row.append(0.0)
            else:
                row.append(sum_by_class[cls][a] / cnt)
        matrix_169.append(row)

    return hand_classes, matrix_169


# =========================
# Build Plate-style JSON & upload to ADLS
# =========================
def sanitize_float(x: Optional[float]) -> Optional[float]:
    """
    Convert NaN / +/-inf to None so the JSON is valid and parsable.
    """
    if x is None:
        return None
    if isinstance(x, (int, float)) and math.isfinite(x):
        return float(x)
    return None


def build_solution_doc(
    board: str,
    cfr_path: str,
    wait_output: str,
    stats: Dict[str, Optional[float]],
    py_summary: Dict[str, Any],
    src_gametree_path: str,
    focus: str = "auto",  # "root", "check", or "auto"
    alive_positions: Optional[List[str]] = None,
    acting_pos: Optional[str] = None,
) -> Dict[str, Any]:

    """
    Build a JSON doc in a preflop-like shape, focusing on either:
      - the root node ("r:0"), or
      - the node after an OOP check (root_check), if requested.
    The doc will include:
      - node_id: e.g. "r:0" or "r:0:1"
      - node_suffix: e.g. "r.0" or "r.0.1" (safe for filenames/URLs)
    """
    hand_order = py_summary.get("hand_order", [])
    root = py_summary.get("root") or {}
    root_check = py_summary.get("root_check")

    # Decide which node to focus on
    focus_node_type = "root"
    if focus == "root":
        focus_node = root
        focus_node_type = "root"
        log("  [doc] focus=root (root node).")
    elif focus == "check":
        if root_check is not None:
            focus_node = root_check
            focus_node_type = "check"
            log("  [doc] focus=check – using root_check node (after OOP checks).")
        else:
            focus_node = root
            focus_node_type = "root"
            log("  [doc] focus=check but no root_check; falling back to root.")
    else:  # "auto"
        if root_check is not None:
            focus_node = root_check
            focus_node_type = "check"
            log("  [doc] Using root_check as focus node (after OOP checks).")
        else:
            focus_node = root
            focus_node_type = "root"
            log("  [doc] No root_check found; using root as focus node.")

    node_actions = focus_node.get("actions") or []
    node_evs = focus_node.get("evs", {}) or {}
    node_matchups = focus_node.get("matchups", {}) or {}
    node_strategy = focus_node.get("strategy")

    oop_evs_1326 = node_evs.get("oop")
    ip_evs_1326 = node_evs.get("ip")
    oop_mu_1326 = node_matchups.get("oop")
    ip_mu_1326 = node_matchups.get("ip")

    # Extract stacks/node info from src_gametree_path
    stacks = None
    node_name = None
    yyyy = mm = dd = None

    if src_gametree_path.startswith(BASE_PREFIX + "/"):
        rel_after_base = src_gametree_path[len(BASE_PREFIX) + 1 :]
    else:
        rel_after_base = src_gametree_path

    parts = rel_after_base.split("/")
    if len(parts) >= 3:
        yyyy, mm, dd = parts[0], parts[1], parts[2]

    for p in parts:
        if p.startswith("folder="):
            stacks = p[len("folder=") :]
            break

    node_file = parts[-1] if parts else ""
    if node_file.endswith(".json"):
        node_name = node_file[:-5]
    else:
        node_name = node_file

    # Parse stacks string + hero bb / hero position like BB/HJ/etc.
    stacks_map, hero_bb, hero_pos = parse_stacks_and_hero_bb(stacks, node_name)

    # Prefer acting_pos from the upload over filename-derived hero_pos
    if acting_pos:
        hero_pos = acting_pos

    villain_pos: Optional[str] = None
    alive_positions_clean: Optional[List[str]] = None

    if alive_positions and isinstance(alive_positions, list):
        # Make sure they're strings
        alive_positions_clean = [str(p) for p in alive_positions if p]
        if hero_pos and hero_pos in alive_positions_clean and len(alive_positions_clean) == 2:
            # The "other" seat is villain
            a, b = alive_positions_clean
            villain_pos = b if a == hero_pos else a
        elif len(alive_positions_clean) == 2 and not hero_pos:
            # Fallback: treat first as hero, second as villain
            hero_pos = alive_positions_clean[0]
            villain_pos = alive_positions_clean[1]
    else:
        alive_positions_clean = None

    # Defaults for 169-level aggregates
    hand_classes_169: List[str] = []
    strat_matrix_169: List[List[float]] = []
    ev_oop_169_list: Optional[List[Optional[float]]] = None
    ev_ip_169_list: Optional[List[Optional[float]]] = None

    # Only aggregate if everything lines up to 1326
    if (
        isinstance(hand_order, list)
        and len(hand_order) == 1326
        and isinstance(node_strategy, list)
        and node_strategy
    ):
        log("  [agg] Aggregating 1326->169 for focus node strategy/EVs...")
        hand_classes_169, strat_matrix_169 = aggregate_strategy_1326_to_169(
            hand_order, node_strategy
        )

        # EV aggregation to 169 and sanitize
        if isinstance(oop_evs_1326, list) and len(oop_evs_1326) == 1326:
            ev_oop_map_169 = aggregate_1326_to_169(hand_order, oop_evs_1326)
            ev_oop_169_list = [sanitize_float(ev_oop_map_169.get(cls)) for cls in hand_classes_169]
        if isinstance(ip_evs_1326, list) and len(ip_evs_1326) == 1326:
            ev_ip_map_169 = aggregate_1326_to_169(hand_order, ip_evs_1326)
            ev_ip_169_list = [sanitize_float(ev_ip_map_169.get(cls)) for cls in hand_classes_169]
    else:
        log("  [agg] Skipping 1326->169 aggregation (hand_order/strategy not 1326)")

    # Decide whose EV we care about for the per-hand tuples: the side to act.
    node_position = (focus_node.get("position") or "").upper()  # "IP" or "OOP"
    hero_ev_list: Optional[List[Optional[float]]] = None
    if node_position == "IP" and isinstance(ev_ip_169_list, list):
        hero_ev_list = ev_ip_169_list
    elif node_position == "OOP" and isinstance(ev_oop_169_list, list):
        hero_ev_list = ev_oop_169_list

    # Build preflop-like "actions" dict:
    actions_payload: Dict[str, Dict[str, List[Optional[float]]]] = {}

    if hand_classes_169 and strat_matrix_169:
        for action_index, action_label in enumerate(node_actions):
            row: List[float] = []
            if 0 <= action_index < len(strat_matrix_169):
                row = strat_matrix_169[action_index]

            hand_map: Dict[str, List[Optional[float]]] = {}
            for idx, hand_cls in enumerate(hand_classes_169):
                freq = row[idx] if idx < len(row) else 0.0
                hero_ev = None
                if hero_ev_list and idx < len(hero_ev_list):
                    hero_ev = hero_ev_list[idx]
                hero_ev = sanitize_float(hero_ev)

                hand_map[hand_cls] = [float(freq), hero_ev]

            actions_payload[action_label] = hand_map
    else:
        log("  [doc] No 169-level aggregation available; actions will be empty.")

    # Rebuild root_169 so your existing postflop parser keeps working.
    root_169 = {
        "hand_classes": hand_classes_169,
        "strategy": {
            "actions": node_actions,
            "matrix": strat_matrix_169,
        },
        "ev": {
            "oop": ev_oop_169_list,
            "ip": ev_ip_169_list,
        },
    }

    # Sanitize summary EVs as well
    summary_ev_oop = sanitize_float(stats.get("ev_oop"))
    summary_ev_ip = sanitize_float(stats.get("ev_ip"))
    summary_expl = sanitize_float(stats.get("exploitable"))

    # Node identity (pyosolver-style)
    focus_node_id = focus_node.get("node_id") or ("r:0" if focus_node_type == "root" else None)
    node_suffix = node_id_to_suffix(focus_node_id, fallback=focus_node_type)

    # Final doc
    doc: Dict[str, Any] = {
        "board": board,
        "cfr_path": cfr_path,
        "created_utc": datetime.now(timezone.utc).isoformat(),

        # Pio roles + seat mapping
        "position": node_position,      # "IP" or "OOP" (side to act at this node)
        "hero_pos": hero_pos,           # e.g. "UTG1" or "BB"
        "villain_pos": villain_pos,     # the other alive seat, if known
        "alive_positions": alive_positions_clean,  # ["UTG1","BB"], from frontend
        "bb": hero_bb,                  # hero stack in BB if stacks_map known

        "node_type": focus_node_type,   # "root" or "check"
        "node_id": focus_node_id,       # e.g. "r:0" or "r:0:1"
        "node_suffix": node_suffix,     # e.g. "r.0" or "r.0.1"

        "summary": {
            "ev_oop": summary_ev_oop,
            "ev_ip": summary_ev_ip,
            "exploitable": summary_expl,
        },
        "tree_info": py_summary.get("tree_info"),
        "source": {
            "gametree_path": src_gametree_path,
            "stacks": stacks,
            "stacks_map": stacks_map,
            "node": node_name,
            "acting_pos": acting_pos,
            "alive_positions": alive_positions_clean,
            "date": {
                "year": yyyy,
                "month": mm,
                "day": dd,
            },
        },
        "actions": actions_payload,
        "root_169": root_169,
    }

    return doc


def upload_solution_json_to_adls(fs, doc: Dict[str, Any]) -> None:
    board = doc.get("board") or "unknown_board"
    src = doc.get("source") or {}
    stacks = src.get("stacks") or "nostacks"
    node_name = src.get("node") or "nonode"
    date_info = src.get("date") or {}
    yyyy = date_info.get("year") or datetime.now(timezone.utc).strftime("%Y")
    mm = date_info.get("month") or datetime.now(timezone.utc).strftime("%m")
    dd = date_info.get("day") or datetime.now(timezone.utc).strftime("%d")

    node_suffix = doc.get("node_suffix") or doc.get("node_type") or "root"

    # File name now includes node suffix: {board}-{node_suffix}.json
    filename = f"{board}-{node_suffix}.json"

    # piosolutions/{stacks}/{node_name}/{board}-{node_suffix}.json
    rel_path = f"piosolutions/{stacks}/{node_name}/{filename}"

    json_text = json.dumps(doc, separators=(",", ":"), ensure_ascii=False)

    log(f"  [upload] Starting JSON upload for board '{board}' ({node_suffix}) -> {rel_path}")
    try:
        file_client = fs.get_file_client(rel_path)
        file_client.upload_data(json_text, overwrite=True)
        log(
            f"  [upload] Completed JSON upload: {rel_path} "
            f"(size={len(json_text)} bytes)"
        )
    except Exception as e:
        log(f"  [upload] ERROR uploading solution JSON to ADLS '{rel_path}': {e}")

    if TEMP_JSON_DIR:
        try:
            local_path = os.path.join(TEMP_JSON_DIR, filename)
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(json_text)
            log(f"  [upload] Wrote local solution JSON: {local_path}")
        except Exception as e:
            log(f"  [upload] ERROR writing local JSON: {e}")


# =========================
# Per-file processing helper
# =========================
def process_gametree_json(
    fs,
    full_path: str,
    name: str,
    lm: str,
    pio: PioClient,
) -> None:
    log(f"[NEW] {full_path}  (last_modified={lm})")

    raw = download_text(fs, full_path)
    if raw is None:
        return

    # Accept raw or JSON { "Text": "...", "AlivePositions": [...], ... }
    alive_positions: Optional[list[str]] = None
    acting_pos: Optional[str] = None

    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            text = obj.get("Text") or raw
            alive_positions = obj.get("AlivePositions")
            acting_pos = obj.get("ActingPos")
        else:
            text = raw
        if not isinstance(text, str) or not text.strip():
            text = raw
    except Exception:
        text = raw
        alive_positions = None
        acting_pos = None

    pyperclip.copy(text)
    log(f"  -> Copied {len(text.encode('utf-8', 'ignore'))} bytes to clipboard")

    app = attach_pioviewer(PIO_TITLE_RE)
    if not app:
        log("  -> PioViewer window not found.")
        return

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

    # Parse board name from text (still used for CFR + JSON)
    board_name = get_board_name(text, name)

    # Save current parameters, but now ALWAYS using fixed "temp" script name
    log(
        f"  -> Calling save_current_parameters_simple with script_basename="
        f"'{TREE_SCRIPT_BASENAME}' (board='{board_name}')"
    )
    if not save_current_parameters_simple(win, TREE_SCRIPT_BASENAME):
        log("  -> WARNING: SaveCurrentParameters failed; skipping headless solve")
        return

    # TreeBuilding script path (fixed temp)
    tree_script_path = os.path.join(
        TREEBUILD_DIR, f"{TREE_SCRIPT_BASENAME}.txt"
    )
    if not os.path.isfile(tree_script_path):
        log(
            "  -> WARNING: Expected TreeBuilding script not found: "
            f"{tree_script_path}"
        )
        return

    # Headless solve via Pio console (this uses the passed-in `pio`)
    cfr_path, wait_output, stats = solve_tree_to_cfr(
        pio, tree_script_path, board_name
    )

    log(
        f"  -> Stats: EV_OOP={stats.get('ev_oop')}, "
        f"EV_IP={stats.get('ev_ip')}, exploitable={stats.get('exploitable')}"
    )

    # pyosolver summary -> JSON docs -> ADLS
    log("  -> Running pyosolver summary + JSON build...")
    py_summary = extract_root_and_check_summary(cfr_path)
    if py_summary is None:
        log("  -> pyosolver summary unavailable; skipping JSON upload")
        return

    # Always upload a JSON for the ROOT node
    doc_root = build_solution_doc(
        board=board_name,
        cfr_path=cfr_path,
        wait_output=wait_output,
        stats=stats,
        py_summary=py_summary,
        src_gametree_path=full_path,
        focus="root",
        alive_positions=alive_positions,
        acting_pos=acting_pos,
    )
    upload_solution_json_to_adls(fs, doc_root)

    # If we actually have a root_check node, also upload a JSON for it
    if py_summary.get("root_check") is not None:
        doc_check = build_solution_doc(
            board=board_name,
            cfr_path=cfr_path,
            wait_output=wait_output,
            stats=stats,
            py_summary=py_summary,
            src_gametree_path=full_path,
            focus="check",
            alive_positions=alive_positions,
            acting_pos=acting_pos,
        )
        upload_solution_json_to_adls(fs, doc_check)
    else:
        log("  -> No root_check node found; only root JSON uploaded.")


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
    log(f"Pio console exe: {PIO_EXE}")
    log(f"TreeBuilding dir: {TREEBUILD_DIR}")
    log(f"CFR subdir: {CFR_SUBDIR}")
    log(f"Tree script basename (Save current parameters): {TREE_SCRIPT_BASENAME}")
    log(f"Poll: {POLL_SECS:.1f}s\n")

    seen = list_existing_json(fs, BASE_PREFIX, WATCH_TODAY_ONLY)
    if seen:
        log(f"Seeded with {len(seen)} existing file(s).")
    else:
        log("No existing files under prefix; starting fresh.")

    try:
        while True:
            new_items = list_new_json(fs, seen, BASE_PREFIX, WATCH_TODAY_ONLY)
            if new_items:
                for full_path, name, lm in new_items:
                    seen.add(full_path)

                    # Fresh Pio process per file – guarantees shutdown after CFR
                    with PioClient(PIO_EXE) as pio:
                        try:
                            process_gametree_json(fs, full_path, name, lm, pio)
                        except Exception as e:
                            log(f"  -> ERROR processing {full_path}: {e}")

            time.sleep(POLL_SECS)
    except KeyboardInterrupt:
        log("Exiting on Ctrl+C")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
