import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import Cursor
import os
import PATH

# Folder containing the .rng files
folder_path = PATH.folder_path
file_suffixes = {"0.rng": "Fold", "5.rng": "Min", "2.rng": "ALLIN", "1.rng": "Call"}  # Labeling strategies
file_paths = {suffix: os.path.join(folder_path, suffix) for suffix in file_suffixes}

# Initialize the hand dictionary
hand_dict = {hand: {} for hand in [
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
]}

# Read each file and store strategy & EV data
for file, label in file_suffixes.items():
    if os.path.exists(file_paths[file]):
        with open(file_paths[file], "r") as f:
            lines = f.read().strip().split("\n")
            for i in range(0, len(lines), 2):
                hand = lines[i].strip()
                strategy, ev = map(float, lines[i + 1].split(";"))
                ev = ev/2000
                if hand in hand_dict:
                    hand_dict[hand][label] = {"strategy": strategy, "EV": ev}

# Create the 13x13 grid visualization
fig, ax = plt.subplots(figsize=(8, 8))
ax.set_xlim(0, 13)
ax.set_ylim(0, 13)
ax.set_xticks([])
ax.set_yticks([])
ax.set_frame_on(True)

# Colors for different strategies
colors = {"Fold": "lightblue", "Min": "lightcoral"}

# Tooltip storage
tooltip_texts = {}

for i in range(13):
    for j in range(13):
        hand = list(hand_dict.keys())[i * 13 + j]
        strategy_data = hand_dict.get(hand, {})
        x_offset = 0  # Start filling from left
        
        tooltip_texts[(j, 12 - i)] = ""
        
        for label, data in strategy_data.items():
            strategy = data.get("strategy", 0)
            ev = data.get("EV", 0)
            if strategy > 0:
                rect = patches.Rectangle(
                    (j + x_offset, 12 - i), strategy, 1, linewidth=0, facecolor=colors[label]
                )
                ax.add_patch(rect)
                x_offset += strategy
            tooltip_texts[(j, 12 - i)] += f"{label}: EV {ev:.2f}\n"
        
        # Draw grid outline
        outline_rect = patches.Rectangle((j, 12 - i), 1, 1, linewidth=0.5, edgecolor="black", facecolor="none")
        ax.add_patch(outline_rect)
        ax.text(j + 0.5, 12 - i + 0.5, hand, ha='center', va='center', fontsize=8, weight='bold')

# Mouseover tooltip event
annot = ax.annotate("", xy=(0,0), xytext=(10,10), textcoords="offset points",
                    bbox=dict(boxstyle="round", fc="w"), arrowprops=dict(arrowstyle="->"))
annot.set_visible(False)

def update_tooltip(event):
    if event.inaxes == ax:
        x, y = int(event.xdata), int(event.ydata)
        if (x, y) in tooltip_texts:
            annot.set_text(tooltip_texts[(x, y)])
            annot.xy = (x + 0.5, y + 0.5)
            annot.set_visible(True)
            fig.canvas.draw_idle()
        else:
            annot.set_visible(False)
            fig.canvas.draw_idle()

fig.canvas.mpl_connect("motion_notify_event", update_tooltip)
plt.show()
