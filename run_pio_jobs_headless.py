import os
import sys
import json
import time
import glob
import subprocess
from datetime import datetime, timezone
from typing import Optional, IO

# Load .env so AZURE_STORAGE_CONNECTION_STRING etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from azure.storage.filedatalake import DataLakeServiceClient  # pip install azure-storage-file-datalake

# ---------- CONFIG ----------

# Path to text-mode solver exe (adjust for your install/version)
PIO_EXE = os.getenv("PIO_EXE", r"C:\PioSOLVER\PioSOLVER2-edge.exe")

# Where your Save-current-parameters .txt files live
TREEBUILD_DIR = os.getenv("PIO_TREEBUILD_DIR", r"C:\PioSOLVER\TreeBuilding")

# Where you want .cfr / dump_tree files to go (relative to Pio dir)
# We'll actually use a *relative* path "Solved/<board>.cfr" from Pio's cwd.
CFR_SUBDIR = os.getenv("PIO_CFR_SUBDIR", "Solved")

# Folder where the watcher drops job JSONs
JOBS_DIR = os.getenv("PIO_JOBS_DIR", r"C:\PioJobs")

# ADLS config (same as watcher)
CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "onlinerangedata")
ADLS_SOLUTION_PREFIX = os.getenv("PIO_SOLUTION_PREFIX", "piosolutions")  # root folder for solution JSONs in ADLS

POLL_JOBS_EVERY = 2.0  # seconds

END_MARK = "END"  # we’ll set set_end_string END


# ---------- LOGGING ----------

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{ts()}] {msg}", flush=True)


# ---------- ADLS HELPER ----------

def get_fs_client():
    if not CONN_STR:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING not set")
    dls = DataLakeServiceClient.from_connection_string(CONN_STR)
    return dls.get_file_system_client(CONTAINER)


def upload_solution_json(fs, board: str, payload: dict) -> str:
    """Upload JSON solution summary to ADLS."""
    # e.g. piosolutions/2025/11/21/Td7h2c.json
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    path = f"{ADLS_SOLUTION_PREFIX}/{today}/{board}.json"

    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    file_client = fs.get_file_client(path)

    try:
        file_client.create_file()
    except Exception:
        # if it already exists we’ll overwrite
        pass

    file_client.upload_data(data, overwrite=True)
    log(f"  -> Uploaded solution JSON to ADLS: {path}")
    return path


# ---------- PIO UPI CLIENT ----------

class PioClient:
    """
    Simple wrapper around a long-lived PioSOLVER console process using UPI.
    """

    def __init__(self, exe_path: str):
        # Ensure we use the Pio directory as working directory
        pio_dir = os.path.dirname(exe_path) or "."
        self.pio_dir = os.path.abspath(pio_dir)

        log(f"Starting PioSOLVER process: {exe_path} (cwd={self.pio_dir})")

        self.proc = subprocess.Popen(
            [exe_path],
            cwd=self.pio_dir,  # IMPORTANT: run in Pio directory
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

        # Set the END marker so we know where each response finishes
        resp = self.send_cmd(f"set_end_string {END_MARK}")
        log("PioSOLVER started and END marker set")

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
            # Log the last line as a summary (avoid dumping huge outputs)
            last = resp.splitlines()[-1]
            log(f"  [UPI] << {last}")
        return resp

    def is_alive(self) -> bool:
        return self.proc.poll() is None

    def close(self):
        try:
            self.send_cmd("exit", log_cmd=False)
        except Exception:
            pass
        try:
            self.proc.terminate()
        except Exception:
            pass


# ---------- HIGH-LEVEL SOLVE PIPELINE ----------

def solve_tree_to_cfr(pio: PioClient, tree_script_path: str, board: str) -> str:
    """
    Given a TreeBuilding .txt (from Save current parameters),
    build & solve headless and dump_tree to a .cfr file.
    Returns the full local .cfr path.

    This version:
      * uses an absolute path for the CFR file
      * explicitly asks for a FULL save
      * logs full dump_tree and show_save_version responses
    """
    tree_script_path = os.path.abspath(tree_script_path)
    if not os.path.isfile(tree_script_path):
        raise FileNotFoundError(tree_script_path)

    log(f"Solving tree for board {board} using script: {tree_script_path}")

    # Optional sanity: check if there was a previous tree
    resp_is_present = pio.send_cmd("is_tree_present", log_cmd=False)
    log(f"  [UPI] is_tree_present before load_script_silent: {resp_is_present}")

    # Load the script created by Save current parameters
    pio.send_cmd(f'load_script_silent "{tree_script_path}"')

    # You can tweak accuracy/algorithm here if you want, e.g.:
    # pio.send_cmd("set_accuracy 0.5")

    # Start solver and wait until it's done
    pio.send_cmd("go")
    wait_resp = pio.send_cmd("wait_for_solver")
    log(f"  [UPI] wait_for_solver response:\n{wait_resp}")

    # Construct absolute CFR path on disk, under <pio_dir>\Solved\<board>.cfr
    cfr_dir_full = os.path.join(pio.pio_dir, CFR_SUBDIR)
    os.makedirs(cfr_dir_full, exist_ok=True)

    cfr_full = os.path.abspath(os.path.join(cfr_dir_full, f"{board}.cfr"))
    log(f"  [UPI] Target CFR path: {cfr_full}")

    # IMPORTANT: use absolute path and 'full' flag
    dump_cmd = f'dump_tree "{cfr_full}" full'
    dump_resp = pio.send_cmd(dump_cmd)
    log(f"  [UPI] dump_tree full response:\n{dump_resp if dump_resp else '(no output)'}")

    # Give the OS/solver a tiny moment just in case
    time.sleep(0.5)

    if os.path.exists(cfr_full):
        size = os.path.getsize(cfr_full)
        log(f"  -> dump_tree wrote: {cfr_full} (size={size} bytes)")
    else:
        log(f"  -> WARNING: dump_tree finished but file not found: {cfr_full}")
        # Ask Pio what it thinks about this file path
        try:
            md_resp = pio.send_cmd(f'show_save_version "{cfr_full}"')
            log(f"  [UPI] show_save_version response for missing CFR:\n{md_resp}")
        except Exception as e:
            log(f"  [UPI] show_save_version raised: {e!r}")

    return cfr_full



def build_solution_json_from_cfr(cfr_path: str, board: str) -> dict:
    """
    Minimal "real" payload: confirm CFR exists and has nonzero size.

    TODO: replace this with actual extraction of ranges/EVs using either:
      * Pious / pyosolver to load the CFR file, or
      * additional UPI commands (showing node strategy, root EVs, etc.).
    """
    exists = os.path.exists(cfr_path)
    size = os.path.getsize(cfr_path) if exists else 0

    return {
        "board": board,
        "cfr_path": cfr_path,
        "cfr_exists": exists,
        "cfr_size_bytes": size,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "note": "TODO: replace this stub with real node/range data extracted from the CFR file.",
    }


# ---------- JOB LOOP ----------

def load_next_job() -> Optional[str]:
    os.makedirs(JOBS_DIR, exist_ok=True)
    jobs = sorted(glob.glob(os.path.join(JOBS_DIR, "*.job.json")))
    return jobs[0] if jobs else None


def process_job(job_path: str, pio: PioClient, fs) -> None:
    log(f"Processing job: {job_path}")
    with open(job_path, "r", encoding="utf-8") as f:
        job = json.load(f)

    board = job["board"]
    tree_file = job["tree_file"]

    # 1) Solve & dump CFR
    cfr_path = solve_tree_to_cfr(pio, tree_file, board)

    # 2) Build JSON summary (for now: board + CFR existence/size)
    payload = build_solution_json_from_cfr(cfr_path, board)

    # 3) Upload JSON to ADLS
    upload_solution_json(fs, board, payload)

    # 4) Mark job as done
    os.remove(job_path)
    log(f"Job finished and deleted: {job_path}")


def main():
    if not CONN_STR:
        raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING not set")

    fs = get_fs_client()
    pio = PioClient(PIO_EXE)

    try:
        while True:
            job_path = load_next_job()
            if job_path:
                process_job(job_path, pio, fs)
            else:
                time.sleep(POLL_JOBS_EVERY)
    except KeyboardInterrupt:
        log("Exiting on Ctrl+C")
    finally:
        pio.close()


if __name__ == "__main__":
    main()
