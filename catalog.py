#-*- coding: utf-8 -*-

# Licensed under the MIT License.
# See https://opensource.org/licenses/MIT or License.txt for license text.

# Create the catalog - the Red/Green/Blue (RGB) colour summary of the
# input images to be used for mosaicking.

# The input images are the square thumbnails generated from prepare.py.
# The colour summary is the average RGB values for each pixel in
# the image. These averages can be made for the whole image or for regular
# square subdivisions of the image as indicated by the "dim" parameter.
#
# The dim (dimension) parameter indicates how many subdivisions are made
# on the x and y axes of the image to make the colour summary. A dim of
# 1 means a single subdivision on each axis (ie no subdivision) and the result
# will be three integer values for the average RGB colours of the image.
# Note the RGB integers are values from 0 - 255 inclusive.
#
# When the dim is 2, the image is split into 4 squares and the RGB averages
# for each square are calculated, resulting in 4 * 3 (4 squares and 3 RGB
# values for each square) as the image colour summary.
#
# In general, for dim d there wil be d*d*3 values in the image colour summary.


from PIL import Image
import os
import sys


# Return the colour summary of the input image subdividing into dim*dim squares.
# Note the getpixel function references the image using x,y coordinates where
# x is the width of the image and y is the height.

def colours(im, dim):
    width, height = im.size
    redval = []
    greenval = []
    blueval = []

    for r in range(dim * dim):
        redval.append(0)
        greenval.append(0)
        blueval.append(0)

    section = 0
    count = 0
    for x in range(dim):
        iOffset = int(x * width / dim)
        for y in range(dim):
            jOffset = int(y * height / dim)
            for i in range(int(width/dim)):
                iLoc = i + iOffset
                for j in range(int(height/dim)):
                    jLoc = j + jOffset
                    r, g, b = im.getpixel((iLoc, jLoc))
                    redval[section] = redval[section] + r
                    greenval[section] = greenval[section] + g
                    blueval[section] = blueval[section] + b
                    count = count + 1
            redval[section] = round(redval[section] / count)
            greenval[section] = round(greenval[section] / count)
            blueval[section] = round(blueval[section] / count)
            section = section + 1
            count = 0
    return (redval, greenval, blueval)


# For each file in the directory (and sub directories) calculate the RGB
# colour values and note them along with the file name in the outputfile.
# Assumes all files in the directory tree structure are images.

def main(directory, outfilename, dim):
    outfile = open(outfilename, "w")
    tot = 0

    for root, dirs, files in os.walk(directory):
        for file in files:
            imagename = root + os.sep + file
            if not os.path.isfile(imagename):
                continue
            tot += 1
            im = Image.open(imagename).convert("RGB")
            outfile.write("{}".format(imagename))
            # write out the colours for dimension dim
            c = colours(im, dim)
            for p in range(dim*dim):
                outfile.write(" {} {} {}".format(c[0][p], c[1][p], c[2][p]))
            outfile.write("\n")
            outfile.flush()
        print("Done dir {}. Progress: files {}.".format(root, tot))
        sys.stdout.flush()

    print("Num files:      {}".format(tot))
    print("Dim:            {}".format(dim))
    outfile.close()


# Command line options are:
#
#   directory  - top level directory containing image files
#   outputfile - the colour catalog text file produced
#   dim        - the subdivisions on the x and y axes to split the image into

if __name__ == '__main__':
    if len(sys.argv) != 4:
        print("Usage: {} directory outputfile dim".format(sys.argv[0]))
    else:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
