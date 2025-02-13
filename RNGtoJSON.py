import os
from collections import defaultdict
import PATH
import json
import glob

def is_json(text):
  try:
    json.loads(text)
    return True
  except json.JSONDecodeError:
    return False
def remove_path_before_folder(path, folder_name):
    """Removes the path before the specified folder in a given path.

    Args:
        path: The original path string.
        folder_name: The name of the folder to keep, along with any subsequent path elements.

    Returns:
        The path string starting from the specified folder, or an empty string if the folder is not found.
    """
    index = path.find(folder_name)
    if index != -1:
        return path[index:]
    else:
        return ""
def number_to_action(number):
   if number == '0' or 0:
      return 'Fold'
   elif number == '1' or 1:
      return 'Call'
   elif number == '3' or 3:
      return 'ALLIN'
   elif number == '5' or 5:
      return "Min"
   else:
      a = number.split('00')
      return ('Raise '+str(a[-1]+'%'))
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
def file_print(name_node, dict):
   with open(name_node,'a') as file:
      file.write(dict)

raise_size = 0
hands = [
    "AA", "AKs", "AQs", "AJs", "ATs", "A9s", "A8s", "A7s", "A6s", "A5s", "A4s", "A3s", "A2s",
    "AKo", "KK", "KQs", "KJs", "KTs", "K9s", "K8s", "K7s", "K6s", "K5s", "K4s", "K3s", "K2s",
    "AQo", "KQo", "QQ", "QJs", "QTs", "Q9s", "Q8s", "Q7s", "Q6s", "Q5s", "Q4s", "Q3s", "Q2s",
    "AJo", "KJo", "QJo", "JJ", "JTs", "J9s", "J8s", "J7s", "J6s", "J5s", "J4s", "J3s", "J2s",
    "ATo", "KTo", "QTo", "JTo", "TT", "T9s", "T8s", "T7s", "T6s", "T5s", "T4s", "T3s", "T2s",
    "A9o", "K9o", "Q9o", "J9o", "T9o", "99", "98s", "97s", "96s", "95s", "94s", "93s", "92s",
    "A8o", "K8o", "Q8o", "J8o", "T8o", "98o", "88", "87s", "86s", "85s", "84s", "83s", "82s",
    "A7o", "K7o", "Q7o", "J7o", "T7o", "97o", "87o", "77", "76s", "75s", "74s", "73s", "72s",
    "A6o", "K6o", "Q6o", "J6o", "T6o", "96o", "86o", "76o", "66", "65s", "64s", "63s", "62s",
    "A5o", "K5o", "Q5o", "J5o", "T5o", "95o", "85o", "75o", "65o", "55", "54s", "53s", "52s",
    "A4o", "K4o", "Q4o", "J4o", "T4o", "94o", "84o", "74o", "64o", "54o", "44", "43s", "42s",
    "A3o", "K3o", "Q3o", "J3o", "T3o", "93o", "83o", "73o", "63o", "53o", "43o", "33", "32s",
    "A2o", "K2o", "Q2o", "J2o", "T2o", "92o", "82o", "72o", "62o", "52o", "42o", "32o", "22"
]  # Your full hand list here    
number_converter = {0: "Fold", 1: "Call", 5: "Min", 3: "ALLIN", 4: "Raise "+str(raise_size)+"%"} #5.0.0.0.40075.0 meant raise 75% pot
folder_path = PATH.folder_path
all_files = glob.glob(os.path.join(folder_path, "*.rng"))
players = os.path.basename(folder_path).split("_")
num_players = len(players)

output_dir = os.path.basename(folder_path)
if not os.path.isdir(output_dir):
    os.mkdir(output_dir)

node_list = []
node_count = {}
node_dict = {}
string_node = []
print(players)
alive_players = len(players)
num_actions = 0

#create node groups and append each rng file as a strategy
for file_path in all_files:
   line = os.path.basename(file_path[:-4]).split(".")
   node = line[:-1]
   if name_node(node) in node_count.keys():
      node_count[name_node(node)] += 1
   else:
      node_count[name_node(node)] =0
   action = line[-1]
   if node not in node_list:
      node_list.append(node)
   action_dict = {}
   action_dict[action] = rngtodict(file_path) #creates dict {'AA':[1.0, 500],...}
   #print(is_json(str(json.dumps(action_dict))))
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'),'a') as file:
         if node_count[name_node(node)] == 0:
            file.write('[\n')
         file.write(str(json.dumps(action_dict))+','+'\n')

for node in node_list:
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'),'r') as file:
         data = file.read()[:-2]
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'), 'w') as file:
      file.write(data+'\n]')
      #print(is_json(data+'\n]'))
      if is_json(data+'\n]') == False:
         print(str(node)+' is false')
         break
