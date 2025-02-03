import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import PATH

# Directory containing the files
data_dir = PATH.file_path

# Dictionary to store strategy data
hand_dict = {}

# Read all files in the directory
for filename in os.listdir(data_dir):
    if filename == "0.rng":  # Fold file
        strategy = "Fold"
        print('0 found')
    elif filename == "5.rng":  # Min file
        strategy = "Min"
    else:
        continue  # Skip files that don't match

    file_path = os.path.join(data_dir, filename)
    
    # Read file and extract EV data (replace this with actual parsing logic)
    with open(file_path, "r") as f:
        for line in f:
            parts = line.strip().split()  # Adjust if your file format is different
            if len(parts) >= 2:
                hand = parts[0]  # Example: "AA", "AKs"
                ev = float(parts[1])  # Example: 3.2

                if hand not in hand_dict:
                    hand_dict[hand] = {"Fold": None, "Min": None, "strategy": 0.5}  # Default strategy fraction
                
                hand_dict[hand][strategy] = ev  # Store EV under correct strategy

# Set up the plot
fig, ax = plt.subplots(figsize=(6, 6))
ax.set_xlim(0, 13)
ax.set_ylim(0, 13)

# Create tooltip annotation
tooltip = ax.annotate("", xy=(0, 0), xytext=(10, 10),
                      textcoords="offset points", ha="center",
                      bbox=dict(boxstyle="round", fc="w"),
                      fontsize=10, visible=False)

# Draw the 13x13 grid
cell_size = 1
for i, (hand, data) in enumerate(hand_dict.items()):
    row = i // 13
    col = i % 13
    fraction = data["strategy"]
    
    fill_rect = patches.Rectangle((col, 12 - row), cell_size * fraction, cell_size, 
                                  linewidth=0, facecolor='lightcoral', edgecolor='black')
    ax.add_patch(fill_rect)

    # Store EV values in the rectangle patch
    fill_rect.ev_fold = data["Fold"] if data["Fold"] is not None else "N/A"
    fill_rect.ev_min = data["Min"] if data["Min"] is not None else "N/A"

# Function to update tooltip on mouseover
def on_hover(event):
    for patch in ax.patches:
        if patch.contains(event)[0]:  # Check if mouse is over a cell
            tooltip.set_text(f"EV (Fold): {patch.ev_fold}\nEV (Min): {patch.ev_min}")
            tooltip.set_position((event.xdata, event.ydata))
            tooltip.set_visible(True)
            fig.canvas.draw_idle()
            return
    tooltip.set_visible(False)
    fig.canvas.draw_idle()

# Connect hover event
fig.canvas.mpl_connect("motion_notify_event", on_hover)

plt.show()
