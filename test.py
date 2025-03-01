
import json
import os

def abctodict(insidefile):
    return

def is_json(text):
  try:
    json.loads(text)
    return True
  except json.JSONDecodeError:
    return False

a = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
b = ['a', 'b', 'c', 'd', 'e']
z = {(1, 2), (3, 4), (5, 6)}
ab = ["0", "Fold", "1", "Call", "5", "Min", "3", "ALLIN"]
dict = {'AA':{'strategy': 1.0, 'EV': 0.07},'KK':{'strategy': 0.8, 'EV': 0.07},'QQ':{'strategy': 0.9, 'EV': 0.05}}
abc = "AA\n1.00;5.3143\nKK\n0.90;5914.3\nQQ\n0.80;531.43\n"
root = {'root': ""}
h = [1,2,3,4]
#dict = {a: b}
reverse = list(a.items())[::-1]
for x,y in reverse:
    print(x,y)
    #print(value)
z = []
empty = {}
#print(z)
line_counter = 0
hand_dict = {}
lines = abc.strip().split('\n')
for i in range(0,len(lines),2):
    handXX = lines[i]  # The key (e.g., 'AA', 'KK', 'QQ')
    strategy, ev = lines[i + 1].split(';')
    hand_dict[handXX] = [float(strategy), round(float(ev)/2000, 2)]

#print(hand_dict)

#root['root'] = hand_dict

#print(root)

empty[0] = 'test'
empty[1] = 'frugal'
outer = {}
outer['polly'] = empty
print(outer)

print(len(h))
# print(is_json(str(json.dumps(outer))))
# with open(os.path.join('C:\PythonStuff\MonkerPythonGUI\\test','testtest.txt'),'a') as file:
#       file.write(str(json.dumps(outer))+'\n')