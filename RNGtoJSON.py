import os
import PATH
import json
import glob

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
   # elif number == '15':
   #    return ""
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

raise_size = 0
number_converter = {0: "Fold", 1: "Call", 5: "Min", 3: "ALLIN", 4: "Raise "+str(raise_size)+"%", 2: "Raise X"} #5.0.0.0.40075.0 meant raise 75% pot
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
            file.write('{')
         file.write('"'+str(number_to_action(action))+'"'+":"+str(json.dumps(rngtodict(file_path)))+ ',')

print(node_list)
for node in node_list:
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'),'r') as file:
      data = file.read()[:-1]
   with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\'+output_dir,name_node(node)+'.json'), 'w') as file:
      file.write(data+"}")
      if is_json(data+"}") == False:
         print(str(node)+' is false')
         break
