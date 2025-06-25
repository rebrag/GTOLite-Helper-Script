import os, time
import json
import glob
import re
import threading
from typing import Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import Tk
from tkinter.filedialog import askdirectory


# ────────────────────────────────────────────
# Utility helpers
# ────────────────────────────────────────────
def is_json(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False
    
# ──────────────────────────────────────────────────
# Progress-aware, timed converter
# ──────────────────────────────────────────────────
def _parse_rng_file(file_path: str) -> tuple[str, str, dict]:
    parts = os.path.basename(file_path[:-4]).split(".")
    node, action_code = parts[:-1], parts[-1]
    node_key = name_node(node)
    return node_key, number_to_action(action_code), rng_to_dict(file_path)

def number_to_action(number: str) -> str:
    """
    Translate Monker-style numeric codes into readable actions.
    Extend the dictionary below if you meet new codes.
    """
    mapping = {
        "0": "Fold",
        "1": "Call",
        "3": "ALLIN",
        "5": "Min",
        "14": "Raise 1.5bb",
        "15": "Raise 2bb",
        "16": "Raise 2.5bb",
        "18": "Raise 3.5bb",
        "19": "Raise 4bb",
        "21": "Raise 5bb",
        "22": "Raise 5.5bb",
        "23": "Raise 6bb",
        "24": "Raise 6.5bb",
        "28": "Raise 8.5bb",
    }

    if number in mapping:
        return mapping[number]
    if number.startswith("40"):
        # Monker convention: 40075 → raise 75 % pot
        percent = int(number[2:])  
        return f"Raise {percent}%"
    # Fallback: keep the raw code
    return number


def rng_to_dict(file_path: str) -> Dict[str, List[float]]:
    """Read one *.rng file into { 'AA': [strategy, EV], … }."""
    result: Dict[str, List[float]] = {}
    with open(file_path, "r") as f:
        lines = f.read().strip().splitlines()
        for i in range(0, len(lines), 2):
            hand = lines[i]
            strategy_str, *ev_part = lines[i + 1].split(";")
            strategy = float(strategy_str.strip())
            ev = float(ev_part[0].strip()) if ev_part else 0.0
            result[hand] = [strategy, round(ev / 2000, 2)]
    return result


def name_node(node: List[str]) -> str:
    """Turn ['5', '0', '0'] into '5.0.0' (or 'root' for [])"""
    return ".".join(node) if node else "root"


def parse_position_bb(s: str) -> Tuple[str, float]:
    """
    Split strings like '14.5HJ' → ('HJ', 14.5)
    or 'UTG1' (no stack given) → ('UTG1', 0)
    """
    m = re.match(r"^(\d+(?:\.\d+)?)([A-Za-z]+\d?)$", s)
    if m:
        return m.group(2), float(m.group(1))
    # if no leading digits, treat the whole thing as position
    return s, 0.0


def get_active_player(node: List[int], players: List[str]) -> str:
    """
    Determine whose turn it is given the action list `node`
    and an initial list like ['25BTN', '12SB', '12BB'].
    """
    alive = players[:]           # shallow copy
    idx = 0                      # dealer starts
    for act_code in node:
        if not alive:
            break
        if act_code == 0:        # Fold → remove that seat
            del alive[idx]
            if alive and idx >= len(alive):
                idx = 0
        else:                    # any non‑fold moves to next seat
            idx = (idx + 1) % len(alive)
    if not alive:
        return ""
    pos_str = alive[idx]
    pos, _ = parse_position_bb(pos_str)
    return pos


# ────────────────────────────────────────────
# Worker thread: heavy lifting
# ────────────────────────────────────────────
def convert_rng_folder(folder_path: str,
                       output_dir: str,
                       workers: int = 8) -> None:

    start = time.perf_counter()

    files: List[str] = glob.glob(os.path.join(folder_path, "*.rng"))
    if not files:
        print("No .rng files found."); return
    total = len(files)

    # ---------- choose progress backend ----------
    try:
        from tqdm import tqdm          # type: ignore
        progress = tqdm(total=total, unit="file", desc="Parsing")
        def tick(n=1): progress.update(n)
    except ModuleNotFoundError:
        processed = 0
        def tick(n=1):
            nonlocal processed
            processed += n
            pct = processed * 100 // total
            print(f"\rParsing: {processed}/{total} ({pct:3d}%)", end="", flush=True)

    # ---------- parallel read & parse ------------
    node_data: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_parse_rng_file, fp) for fp in files]
        for fut in as_completed(futures):
            node_key, act_name, data = fut.result()
            node_data.setdefault(node_key, {})[act_name] = data
            tick()

    if 'progress' in locals(): progress.close()
    else: print()            # finish the in-place line

    # ---------- add Position / bb ----------------
    players = os.path.basename(folder_path).split("_")
    pos_to_bb = dict(parse_position_bb(p) for p in players)

    for node_key in node_data:
        node_parts = node_key.split(".") if node_key != "root" else []
        active = get_active_player(list(map(int, node_parts)), players)
        node_data[node_key] = {
            "Position": active,
            "bb": pos_to_bb.get(active, 0.0),
            **node_data[node_key],
        }

    # ---------- single write per node ------------
    os.makedirs(output_dir, exist_ok=True)
    for node_key, payload in node_data.items():
        out_path = os.path.join(output_dir, f"{node_key}.json")
        try:
            import orjson as _json      # type: ignore # fastest if available
            with open(out_path, "wb") as f:
                f.write(_json.dumps(payload, option=_json.OPT_INDENT_2))
        except ModuleNotFoundError:
            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)

    elapsed = time.perf_counter() - start
    print(f"✅ Converted {total} files into {len(node_data)} nodes in {elapsed:.1f} s.")


# ────────────────────────────────────────────
# Main routine
# ────────────────────────────────────────────
def main() -> None:
    # Hide the empty Tk root window behind askdirectory
    Tk().withdraw()
    folder_path = askdirectory(title="Select folder containing .rng files")
    if not folder_path:
        print("No folder selected – exiting.")
        return

    output_dir_name = os.path.basename(folder_path)
    os.makedirs(output_dir_name, exist_ok=True)

    # Launch the conversion in a background thread
    worker = threading.Thread(
        target=convert_rng_folder,
        args=(folder_path, output_dir_name),
        daemon=True
    )
    worker.start()

    # While the thread works, ask for metadata
    meta_name = input(f"Name/label for this simulation set [{output_dir_name}]: ") or output_dir_name
    players = os.path.basename(folder_path).split("_")
    ante = 0.125 * len(players)

    icm_raw = input("Enter ICM values (comma‑separated) or 'none': ").strip()
    if icm_raw.lower() in {"", "none"}:
        icm: Any = "none"
    else:
        try:
            icm = [float(x) for x in icm_raw.split(",") if x.strip()]
        except ValueError:
            print("Invalid ICM list – defaulting to 'none'.")
            icm = "none"

    metadata = {"name": meta_name, "ante": ante, "icm": icm}

    # Wait until the conversion is finished
    worker.join()

    # Write metadata.json alongside the node files
    with open(os.path.join(output_dir_name, "metadata.json"), "w") as mf:
        json.dump(metadata, mf, indent=2)

    print("All done – metadata.json written.")


if __name__ == "__main__":
    main()