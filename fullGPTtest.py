import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

# Directory containing .rng files
directory = r"C:\\Users\\John\\MonkerSolver\\ranges\\Hold'em\\6-way\\1bbAnte 2xOpen\\g.) 8SB 20HJ"

# Identify files to group by tree level
base_files = ["0.rng", "5.rng"]
additional_files = sorted([f for f in os.listdir(directory) if f.startswith("0.") and f.endswith(".rng")])

def load_hand_data(files):
    hand_data = {}
    colors = ["lightblue", "lightcoral", "lightgreen", "lightyellow", "lightpink", "lightgray"]
    
    for file, color in zip(files, colors):
        file_path = os.path.join(directory, file)
        with open(file_path, "r") as f:
            lines = f.read().strip().split("\n")
        
        for i in range(0, len(lines), 2):
            hand = lines[i].strip()
            strategy, ev = map(float, lines[i + 1].split(";"))
            
            if hand not in hand_data:
                hand_data[hand] = {"strategies": [], "EVs": []}
            
            hand_data[hand]["strategies"].append((strategy, color))
            hand_data[hand]["EVs"].append(ev)
    
    return hand_data

hands = [  # Standard 13x13 hand order
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
]

def plot_grid(ax, hand_data, title):
    for i in range(13):
        for j in range(13):
            hand = hands[i * 13 + j]
            strategies = hand_data.get(hand, {}).get("strategies", [])
            
            x_offset = 0  # Track filled fraction
            for strategy, color in strategies:
                if strategy > 0:
                    rect = patches.Rectangle(
                        (j + x_offset, 12 - i), strategy, 1, linewidth=0, facecolor=color
                    )
                    ax.add_patch(rect)
                    x_offset += strategy
            
            ax.text(j + 0.5, 12 - i + 0.5, hand, ha='center', va='center', fontsize=8, weight='bold')
            outline_rect = patches.Rectangle((j, 12 - i), 1, 1, linewidth=0.5, edgecolor="black", facecolor="none")
            ax.add_patch(outline_rect)
    
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 13)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(True)
    ax.set_title(title)

# Plot multiple grids
fig, axes = plt.subplots(1 + len(additional_files), 1, figsize=(8, 8 * (1 + len(additional_files))))
if len(additional_files) == 0:
    axes = [axes]  # Ensure axes is iterable when there's only one grid

# First grid for base files
base_hand_data = load_hand_data(base_files)
plot_grid(axes[0], base_hand_data, "Base Grid: 0.rng & 5.rng")

# Additional grids
for idx, file in enumerate(additional_files):
    hand_data = load_hand_data([file])
    plot_grid(axes[idx + 1], hand_data, f"Grid for {file}")

plt.tight_layout()
plt.show()