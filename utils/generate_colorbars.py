"""
Colorbar image generation utility

CLI tool to export matplotlib colormaps as PNG images for making colorbars. We use this to make the matplotlib colormaps
used by the backend available as static assets for the UI.

Args:
    colormap (str): Name of the matplotlib colormap (e.g., "viridis").
    dimensions (tuple): Width and height in pixels (e.g., (200, 20)).
    filename (str): Name of the output file (e.g., "colorbar.png").
"""

import matplotlib.pyplot as plt
import numpy as np
import argparse

def export_colormap(colormap, dimensions, filename):
    try:
        # Create a figure and axis
        width, height = dimensions
        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)

        # Create a gradient and plot it
        gradient = np.linspace(0, 1, 256).reshape(1, -1)  # Gradient from 0 to 1
        ax.imshow(gradient, aspect="auto", cmap=colormap)

        # Remove axes
        ax.set_axis_off()

        # Save the colormap as an image
        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)  # Remove all padding
        plt.savefig(filename, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        print(f"Colormap '{colormap}' exported successfully to {filename}.")

    except ValueError as e:
        print(f"Error: '{colormap}' is not a valid matplotlib colormap. Details: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export matplotlib colormap to PNG")
    parser.add_argument("colormap", type=str, help="A valid matplotlib colormap name (e.g., 'viridis')")
    parser.add_argument("width", type=int, help="Width of the output image in pixels")
    parser.add_argument("height", type=int, help="Height of the output image in pixels")
    parser.add_argument("filename", type=str, help="Name of the output PNG file (e.g., 'colorbar.png')")

    args = parser.parse_args()

    export_colormap(args.colormap, (args.width, args.height), args.filename)