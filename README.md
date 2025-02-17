# Poker Strategy Visualizer

This Python project is designed to visualize poker strategies from `.rng` files. The code processes poker strategy data, groups it by nodes, and generates interactive visualizations using `matplotlib`. The visualizations include tooltips that display detailed strategy information for each hand.

## Features

- **File Processing**: Reads `.rng` files containing poker strategy data.
- **Node Grouping**: Groups strategy files by nodes (e.g., decision points in a poker game).
- **Interactive Visualization**: Generates a grid-based visualization of poker strategies for each node.
- **Tooltips**: Displays detailed strategy information (e.g., fold, call, raise, all-in) when hovering over specific hands.
- **JSON Output**: Converts strategy data into JSON format for further analysis or storage.

## Requirements

- Python 3.x
- Libraries:
  - `glob`
  - `os`
  - `collections.defaultdict`
  - `math`
  - `matplotlib.pyplot`
  - `matplotlib.patches`
  - `json`

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/poker-strategy-visualizer.git
   cd poker-strategy-visualizer

2. Install the required libraries:
   ```bash
   pip install -r requirements.txt

## Usage

1. - Set the 'folder_path': update the 'folder_path' variable in the code to point to the directory containing your '.rng' files,
2. groups them by nodes, and generates a visualization.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for improvements or bug fixes 🤩
