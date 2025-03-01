import os
import PATH
import json
import glob
from tkinter import Tk
from tkinter.filedialog import askdirectory

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
        for i in range(0,len(lines),2):
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
    i = 0
    while i < len(s) and s[i].isdigit():
        i += 1
    if i == 0 or i == len(s):
        raise ValueError(f"Invalid format: {s}")
    bb_val = int(s[:i])
    pos = s[i:]
    pos = ''.join(ch for ch in pos if ch.isalnum())
    return pos, bb_val
def get_active_player(node, players):
    active_indices = [
        i for i in range(len(players))
        if (i < len(node) and node[i] != 0) or (i >= len(node))
    ]
    last_active_index = None
    for i in range(len(node) - 1, -1, -1):
        if node[i] != 0:
            last_active_index = i
            break
    if last_active_index is None:
        return players[active_indices[0]].lstrip("0123456789")
    try:
        pos = active_indices.index(last_active_index)
    except ValueError:
        pos = -1
    next_active_index = active_indices[(pos + 1) % len(active_indices)]
    return players[next_active_index].lstrip("0123456789")


folder_path = askdirectory(title='Select Folder') # shows dialog box and return the path
print(folder_path)
#folder_path = PATH.folder_path
all_files = glob.glob(os.path.join(folder_path, "*.rng"))

raise_size = 0
number_converter = {0: "Fold", 1: "Call", 5: "Min", 3: "ALLIN", 4: "Raise "+str(raise_size)+"%", 2: "Raise X"} #5.0.0.0.40075.0 meant raise 75% pot



output_dir = os.path.basename(folder_path)
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)

node_list = []
node_count = {}
node_dict = {}
string_node = []
#print(players)
#alive_players = len(players)
num_actions = 0
positionS = ""
bb = 0

#create node groups and append each rng file as a strategy
for file_path in all_files:
   players = os.path.basename(folder_path).split("_")
   num_players = len(players)
   line = os.path.basename(file_path[:-4]).split(".")
   node = line[:-1]
   fold_count = node.count(0)
   positionS = players[len(node)%len(players)]
   position, bb = parse_position_bb(positionS)
   if name_node(node) in node_count.keys():
      node_count[name_node(node)] += 1
   else:
      node_count[name_node(node)] =0
   action = line[-1]
   #print(node, action)
   if node not in node_list:
      node_list.append(node)
   action_dict = {}
   action_dict[action] = rngtodict(file_path) #creates dict {'AA':[1.0, 500],...}
   #print(is_json(str(json.dumps(action_dict))))
   metadata = { "position": position, "bb": bb}
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'),'a') as file:
         if node_count[name_node(node)] == 0:
            file.write('{"Position":' + json.dumps(get_active_player(list(map(int, node)), players))+',"bb":'+str(bb)+",")
         file.write('"'+str(number_to_action(action))+'"'+":"+str(json.dumps(rngtodict(file_path)))+ ',')
print('entering node list')
print('output directory: ' + output_dir)
for node in node_list:
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'),'r') as file:
      data = file.read()[:-1]
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'), 'w') as file:
      file.write(data+"}")
      if is_json(data+"}") == False:
         print(str(node)+' is false')
         break
print("RNGtoJSON Complete.")