import os
import PATH
import json
import glob
from tkinter import Tk
from tkinter.filedialog import askdirectory
import re

def is_json(text):
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False

def number_to_action(number):
    if number == '0':
        return "Fold"
    elif number == '1':
        return "Call"
    elif number == '3':
        return "ALLIN"
    elif number == '5':
        return "Min"
    elif number == '15':
        return "Raise 2bb"
    elif number == '14':
        return "Raise 1.5bb"
    elif number == '19':
        return "Raise 4bb"
    elif number == '21':
        return "Raise 5bb"
    elif number.startswith("40"):
        percentage = number[3:]
        return f"Raise {percentage}%"
    else:
        a = number.split('00')
        return str(number)

def rngtodict(file_path):
    d = {}
    with open(file_path, 'r') as f:
        lines = f.read().strip().split('\n')
        for i in range(0, len(lines), 2):
            handXX = lines[i]  # The key (e.g., 'AA', 'KK', 'QQ')
            value = lines[i + 1]
            parts = value.split(';')
            strategy = float(parts[0].strip())  # First part is always present
            ev = float(parts[1].strip()) if len(parts) > 1 else 0  # Default to 0 if no second part
            d[handXX] = [float(strategy), round(float(ev)/2000, 2)]
    return d

def name_node(node):
    if len(node) > 0:
        return '.'.join(node)
    else:
        return 'root'

def parse_position_bb(s: str):
    # """
    # Splits a string like "14.5HJ" into ("HJ", 14.5)
    # or "UTG1" into ("UTG1", <number>).
    # """
    m = re.match(r'^(\d+(?:\.\d+)?)([A-Za-z]+\d?)$', s)
    if not m:
        raise ValueError(f"Invalid format: {s}")
    bb_val = float(m.group(1))
    pos    = m.group(2)
    return pos, bb_val


def get_active_player(node, players):
    alive = players[:]      # copy of ["14.5HJ", "25.5CO", …]
    idx   = 0               # start at dealer (root)
    
    for action in node:
        if not alive:
            break
        act = int(action)
        if act == 0:
            del alive[idx]
            if alive and idx >= len(alive):
                idx = 0
        else:
            idx = (idx + 1) % len(alive)

    if not alive:
        return ""
    # now alive[idx] is something like "14.5HJ"
    pos_str = alive[idx]
    pos, _  = parse_position_bb(pos_str)
    return pos

# Select folder using a dialog box.
folder_path = askdirectory(title='Select Folder')
print(folder_path)
all_files = glob.glob(os.path.join(folder_path, "*.rng"))

# Determine output directory name.
output_dir = os.path.basename(folder_path)
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)

# Get metadata name from user, showing the original folder name.
metadata_name = input(f"Give name metadata for {os.path.basename(folder_path)}: ")

# Calculate ante based on the number of players.
players = os.path.basename(folder_path).split("_")
ante = 0.125 * len(players)

# Prompt user for ICM values.
icm_input = input("Enter ICM values (either 'none' or comma separated numbers): ")
if icm_input.strip().lower() in ["", "none"]:
    icm = "none"
else:
    try:
        icm = [float(x.strip()) for x in icm_input.split(',') if x.strip() != '']
    except ValueError:
        print("Invalid ICM values entered. Setting ICM to 'none'.")
        icm = "none"

# Create metadata dictionary and write to metadata.json in output folder.
metadata = {"name": metadata_name, "ante": ante, "icm": icm}
metadata_path = os.path.join(r'C:\\PythonStuff\\MonkerPythonGUI\\' + output_dir, "metadata.json")
with open(metadata_path, 'w') as meta_file:
    json.dump(metadata, meta_file)

raise_size = 0
number_converter = {0: "Fold", 1: "Call", 5: "Min", 3: "ALLIN", 4: "Raise "+str(raise_size)+"%", 2: "Raise X", 14: "Raise 1.5bb", 15: "Raise 2bb"}
# Example: file "5.0.0.0.40075.0" meant raise 75% pot.

node_list = []
node_count = {}
# Create node groups and append each RNG file as a strategy.
for file_path in all_files:
    players = os.path.basename(folder_path).split("_")
    num_players = len(players)
    line = os.path.basename(file_path[:-4]).split(".")
    node = line[:-1]  # list of actions as strings
    # Determine the position and big blind based on the next player's data.
    positionS = players[len(node) % len(players)]
    position, bb = parse_position_bb(positionS)
    # Update node count (used for determining file header writes).
    if name_node(node) in node_count.keys():
        node_count[name_node(node)] += 1
    else:
        node_count[name_node(node)] = 0
    action = line[-1]
    if node not in node_list:
        node_list.append(node)
    # Get the active player based on the simulated betting progression.
    active_player = get_active_player(list(map(int, node)), players)
    with open(os.path.join(r'C:\\PythonStuff\\MonkerPythonGUI\\' + output_dir, name_node(node) + '.json'), 'a') as file:
        if node_count[name_node(node)] == 0:
            file.write('{"Position":' + json.dumps(active_player) + ',"bb":' + str(bb) + ",")
        file.write('"' + str(number_to_action(action)) + '":' + json.dumps(rngtodict(file_path)) + ',')
        
print('entering node list')
print('output directory: ' + output_dir)
for node in node_list:
    json_path = os.path.join(r'C:\\PythonStuff\\MonkerPythonGUI\\' + output_dir, name_node(node) + '.json')
    with open(json_path, 'r') as file:
        data = file.read()[:-1]
    with open(json_path, 'w') as file:
        file.write(data + "}")
        if not is_json(data + "}"):
            print(str(node) + ' is false')
            break

print("RNGtoJSON Complete.")
