import os
import time
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
        "17": "Raise 3bb",
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
        # Monker convention: 40075 → raise 75 % pot
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

def _parse_rng_file(file_path: str) -> tuple[str, str, dict]:
    """
    Helper for parallel processing. This function is now simplified and robust.
    """
    file_name_no_ext = os.path.basename(file_path)[:-4]
    node_parts = file_name_no_ext.split(".")
    action_code = node_parts[-1]
    node_path_list = node_parts[:-1]
    node_key = name_node(node_path_list)
    
    # Return the node key, the RAW action code, and the file data
    # We will convert the action code to its name later
    return node_key, action_code, rng_to_dict(file_path)

def get_active_player(node: List[int], players: List[str]) -> str:
    """
    Determine whose turn it is by simulating the betting round based on
    the action list `node` and initial `players` list with stacks.
    This is more robust than the previous implementation as it accounts
    for players being all-in and unable to act further.
    """
    if not players:
        return ""

    # 1. Initialize player states from strings like '9BTN', '18SB', etc.
    player_states = []
    for p_str in players:
        pos, stack = parse_position_bb(p_str)
        player_states.append({
            "pos": pos, "stack": stack, "bet": 0.0, "is_folded": False, "is_all_in": False
        })

    # 2. Simulate preflop blinds (assuming 0.5/1)
    # This is a simplification but necessary for stack calculations.
    if len(player_states) > 1:
        bb_player = player_states[-1]
        bb_bet = min(1.0, bb_player['stack'])
        bb_player['bet'] = bb_bet
        bb_player['stack'] -= bb_bet

        sb_player = player_states[-2]
        sb_bet = min(0.5, sb_player['stack'])
        sb_player['bet'] = sb_bet
        sb_player['stack'] -= sb_bet
    
    highest_bet = 1.0
    
    # 3. Determine the first player to act.
    # The list `players` is assumed to be in the order of preflop action.
    active_idx = 0
    
    # 4. Process the action sequence from the file path node.
    for act_code in node:
        current_player = player_states[active_idx]
        action_str = number_to_action(str(act_code))

        if action_str == "Fold":
            current_player['is_folded'] = True
        elif action_str == "ALLIN":
            current_player['bet'] += current_player['stack']
            current_player['stack'] = 0
        elif action_str == "Call":
            to_call = highest_bet - current_player['bet']
            actual_call = min(to_call, current_player['stack'])
            current_player['bet'] += actual_call
            current_player['stack'] -= actual_call
        elif "Raise" in action_str and "bb" in action_str:
            # Use re.search for safety, although findall works if pattern is guaranteed
            match = re.search(r'(\d+(?:\.\d+)?)bb', action_str)
            if match:
                total_bet_target = float(match.group(1))
                to_add = total_bet_target - current_player['bet']
                actual_add = min(to_add, current_player['stack'])
                current_player['bet'] += actual_add
                current_player['stack'] -= actual_add
        elif action_str == "Min":
            # Simplified Min-raise logic
            last_raise_size = highest_bet - (player_states[(active_idx - 1 + len(player_states)) % len(player_states)]['bet'])
            min_raise_to = highest_bet + last_raise_size
            to_add = min_raise_to - current_player['bet']
            actual_add = min(to_add, current_player['stack'])
            current_player['bet'] += actual_add
            current_player['stack'] -= actual_add

        # After any action, update the highest bet and check for all-in status.
        highest_bet = max(highest_bet, current_player['bet'])
        if current_player['stack'] <= 0:
            current_player['stack'] = 0
            current_player['is_all_in'] = True

        # 5. Find the next player to act.
        next_player_found = False
        search_idx = active_idx
        for _ in range(len(player_states)):
            search_idx = (search_idx + 1) % len(player_states)
            player_to_check = player_states[search_idx]
            if not player_to_check['is_folded'] and not player_to_check['is_all_in']:
                active_idx = search_idx
                next_player_found = True
                break
        
        if not next_player_found:
            return "" # Action is over

    # 6. After the loop, `active_idx` points to the player whose turn it is now.
    return player_states[active_idx]['pos']


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
        from tqdm import tqdm
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
    # This dictionary will now store raw action codes, e.g., { "5.1": { "17": { ...data... } } }
    node_data_raw: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_parse_rng_file, fp) for fp in files]
        for fut in as_completed(futures):
            node_key, raw_action_code, data = fut.result()
            node_data_raw.setdefault(node_key, {})[raw_action_code] = data
            tick()

    if 'progress' in locals(): progress.close()
    else: print()

    # ---------- add Position / bb and translate action names ----------------
    players = os.path.basename(folder_path).split("_")
    pos_to_bb = dict(parse_position_bb(p) for p in players)

    # This will be the final dictionary with translated action names
    final_node_data: Dict[str, Dict[str, Any]] = {}

    for node_key, actions in node_data_raw.items():
        # Prepare the dictionary for this node
        final_node_data[node_key] = {}
        
        # Add Position and bb information
        node_parts = node_key.split(".") if node_key != "root" else []
        active_player = get_active_player(list(map(int, node_parts)), players)
        final_node_data[node_key]["Position"] = active_player
        final_node_data[node_key]["bb"] = pos_to_bb.get(active_player, 0.0)

        # Translate action codes to names and add the data
        for raw_action_code, data in actions.items():
            action_name = number_to_action(raw_action_code)
            final_node_data[node_key][action_name] = data

    # ---------- single write per node ------------
    os.makedirs(output_dir, exist_ok=True)
    for node_key, payload in final_node_data.items():
        out_path = os.path.join(output_dir, f"{node_key}.json")
        try:
            import orjson as _json
            with open(out_path, "wb") as f:
                f.write(_json.dumps(payload, option=_json.OPT_INDENT_2))
        except ModuleNotFoundError:
            with open(out_path, "w") as f:
                json.dump(payload, f, indent=2)

    elapsed = time.perf_counter() - start
    print(f"✅ Converted {total} files into {len(final_node_data)} nodes in {elapsed:.1f} s.")


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
    # The output directory should be a subdirectory of the script's location
    # to avoid cluttering the source directory.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "output_test", output_dir_name)
    os.makedirs(output_path, exist_ok=True)


    # Launch the conversion in a background thread
    worker = threading.Thread(
        target=convert_rng_folder,
        args=(folder_path, output_path),
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
    with open(os.path.join(output_path, "metadata.json"), "w") as mf:
        json.dump(metadata, mf, indent=2)

    print(f"All done – metadata.json written to '{output_path}'.")


if __name__ == "__main__":
    main()
