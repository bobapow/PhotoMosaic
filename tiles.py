#-*- coding: utf-8 -*-

# Licensed under the MIT License.
# See https://opensource.org/licenses/MIT or License.txt for license text.

# This script generates synthetic tiles of random colours to demonstrate the
# photomosaic process.
#
# Originally authored with assistance from ChatGPT (OpenAI).


import os
import random
from PIL import Image, ImageDraw

# Parameters
output_folder = "synthetic_tiles"
tile_size = (32, 32)  # Width x Height
num_tiles = 30000     # Total number of images to generate

# Create output directory
os.makedirs(output_folder, exist_ok=True)

def random_color():
    return tuple(random.randint(0, 255) for _ in range(3))

def draw_shape(draw, size):
    w, h = size
    padding = 1
    draw.rectangle([padding, padding, w-padding, h-padding], fill=random_color())

# Generate images
for i in range(num_tiles):
    img = Image.new("RGB", tile_size, color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw_shape(draw, tile_size)
    
    # Save image
    img.save(os.path.join(output_folder, f"tile_{i:06d}.png"))

print(f"Generated {num_tiles} synthetic tiles in '{output_folder}' folder.")

