import matplotlib.pyplot as plt
import matplotlib.patches as patches
import glob
import os
import math
from collections import defaultdict
import PATH
import json

def is_json(text):
  try:
    json.loads(text)
    return True
  except json.JSONDecodeError:
    return False
  
class mydict(dict):
    def __str__(self):
        return json.dumps(self)

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

# Configuration
folder_path = PATH.folder_path
file_suffixes = {"0": "Fold", "1": "Call", "5": "Min", "3": "ALLIN", "4": "Raise"}
base_figsize = 3
colors = {"Fold": "lightblue", "Call": "lightgreen", "Min": "lightcoral", "ALLIN": "red"}

# Get all .rng files and group by node
all_files = glob.glob(os.path.join(folder_path, "*.rng"))
node_groups = defaultdict(dict)

for file_path in all_files:
    filename = os.path.basename(file_path)
    base_name = filename[:-4]  # Remove .rng extension
    rng_file_parts = base_name.split('.')
    # Skip files that don't follow 0-prefixed structure
    is_valid = True
    for p in rng_file_parts[:-1]:  # Check all rng_file_parts except the last (action)
        if p != '0' and len(rng_file_parts) > 1:  # Allow root node actions
            is_valid = False
            break
    if not is_valid:
        continue

    # Group valid files
    if len(rng_file_parts) == 1:
        node_name = "root"
        suffix = rng_file_parts[0]
    else:
        node_name = '.'.join(rng_file_parts[:-1])
        suffix = rng_file_parts[-1]
    
    if suffix in file_suffixes:
        node_groups[node_name][file_suffixes[suffix]] = file_path
        base_file_path = os.path.basename(file_path)
        ss_file_path, ext = os.path.splitext(base_file_path)

json_node = mydict(node_groups)
# Create subplot grid
num_nodes = len(node_groups)
rows = math.ceil(math.sqrt(num_nodes))
cols = math.ceil(num_nodes / rows)
fig, axs = plt.subplots(rows, cols, figsize=(base_figsize*cols, base_figsize*rows))

# Flatten axes array
axs = axs.flatten() if num_nodes > 1 else [axs]

# Store tooltips for each axis
tooltip_dict = defaultdict(dict)

# Flatten axes array
if num_nodes > 1:
    axs = axs.flatten()
else:
    axs = [axs]

# Process nodes in reverse order
reversed_nodes = list(node_groups.items())[::-1]
for ax_idx, (node_name, strategies) in enumerate(reversed_nodes):
    ax = axs[ax_idx]
    node_dict = {hand: {} for hand in hands}
    
    # Load data and precompute tooltips
    for action, file_path in strategies.items():
        with open(file_path, 'r') as f:
            lines = f.read().strip().split("\n")
            line_counter = 0
            
            while line_counter < len(lines):
                hand_line = lines[line_counter].strip()
                line_counter += 1
                if not hand_line:
                    continue
                data_line = lines[line_counter].strip()
                line_counter += 1
                rng_file_parts = data_line.split(";")
                if len(rng_file_parts) != 2:
                    print(f"⚠️ Malformed data line in {file_path}: {data_line}")
                    continue
                try:
                    strategy, nonRoundEv = map(float, rng_file_parts)
                    nonRoundEv /= 2000
                    ev = round(nonRoundEv, 2)
                    if hand_line in node_dict:
                        node_dict[hand_line][action] = {
                            "strategy": strategy,
                            "EV": ev
                        }
                except ValueError as e:
                    print(f"⚠️ Invalid numeric value in {file_path}: {data_line}")
                    continue
    
    # Precompute tooltips for this node
    for row_idx in range(13):
        for col_idx in range(13):
            hand_index = row_idx * 13 + col_idx
            if hand_index >= len(hands):
                continue
            hand = hands[hand_index]
            strategy_data = node_dict.get(hand, {})
            
            # Build tooltip
            tooltip = f"{hand}\n"
            for action in ["Fold", "Call", "Min", "ALLIN"]:
                if action in strategy_data:
                    ev = strategy_data[action]["EV"]
                    tooltip += f"{action}: {ev:.2f}\n"
            
            # Store tooltip
            tooltip_dict[ax][(col_idx, 12 - row_idx)] = tooltip.strip()
    
    # Draw grid for this node - PROPER GRID CREATION
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 13)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"Node: {node_name}" if node_name != "root" else "Root Node", fontsize=8)
    
    # Create 13x13 grid using explicit hand order
    for row_idx in range(13):
        for col_idx in range(13):
            hand_index = row_idx * 13 + col_idx
            if hand_index >= len(hands):
                continue
            hand = hands[hand_index]
            strategy_data = node_dict.get(hand, {})
            x_offset = 0

            # Build tooltip FIRST
            tooltip = f"{hand}\n"
            for action in ["Fold", "Call", "Min", "ALLIN"]:
                if action in strategy_data:
                    ev = strategy_data[action]["EV"]
                    tooltip += f"{action}: {ev:.2f}\n"
            tooltip_dict[ax][(col_idx, 12 - row_idx)] = tooltip.strip()

            # Then draw strategies
            for action in ["Fold", "Call", "Min", "ALLIN"]:
                if action in strategy_data:
                    data = strategy_data[action]
                    strategy = data["strategy"]
                    if strategy > 0:
                        rect = patches.Rectangle(
                            (col_idx + x_offset, 12 - row_idx),
                            strategy, 1,
                            linewidth=0, facecolor=colors[action], alpha=0.7
                        )
                        ax.add_patch(rect)
                        x_offset += strategy

            # Add cell outline
            outline_rect = patches.Rectangle(
                (col_idx, 12 - row_idx), 1, 1,
                linewidth=0, edgecolor="none", facecolor="none"
            )
            ax.add_patch(outline_rect)
            ax.text(col_idx + 0.5, 12 - row_idx + 0.5, hand,
                    ha='center', va='center', fontsize=6, weight='bold', alpha=0.7)

# Tooltip annotation setup
annot = fig.text(0, 0, "", 
                ha='left', va='bottom',
                bbox=dict(boxstyle="round", fc="white", alpha=0.9),
                visible=False,
                zorder=100,
                transform=None)  # Important: use display coordinates

# Store the last cell position
last_cell = (None, None)

def update_tooltip(event):
    global last_cell
    annot.set_visible(False)
    if event.inaxes and event.inaxes in tooltip_dict:
        ax = event.inaxes
        try:
            x = int(event.xdata)
            y = int(event.ydata)
        except (TypeError, ValueError):
            return
        
        # Only update if the cell has changed
        if (x, y) != last_cell:
            last_cell = (x, y)  # Update the last cell position
            
            if (x, y) in tooltip_dict[ax]:
                annot.set_text(tooltip_dict[ax][(x, y)])
                annot.set_position((event.x + 10, event.y + 10))
                annot.set_visible(True)
                fig.canvas.draw_idle()

fig.canvas.mpl_connect('motion_notify_event', update_tooltip)

# Hide empty subplots
for ax in axs[len(node_groups):]:
    ax.axis('off')

plt.tight_layout()
plt.show()