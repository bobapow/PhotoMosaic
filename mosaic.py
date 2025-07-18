#-*- coding: utf-8 -*-

# Licensed under the MIT License.
# See https://opensource.org/licenses/MIT or License.txt for license text.

# Create a mosaic of the input image by placing small images (tiles)
# that closely colour match the regions of the input image. This colour
# matching is done using the colour table created by catalog.py.
#
# The input image to be mosaicked is resized so that each RGB pixel
# is used to find the closest matching tile from the colour table.
#
# When the colour table has been created by splitting the tiles
# into dim*dim squares of RGB values, matching a single pixel from
# the input image is instead done by matching dim*dim pixels from
# the original image. The Euclidean distance from each dim*dim sqaure
# is calculated and summed and again the tile with the smallest total
# distance is chosen.
#
# The input image is traversed in a spiral starting at the centre of
# the image. The idea is to place tiles in the centre of the image
# first since this is assumed to be of more interest compared to the
# edges of the image. Depending on the command line options used,
# a tile may only be used once when mosaicking, so it is best to
# place it in the centre of the original image.
#
# The spiral algorithm was taken from:
#
# https://stackoverflow.com/questions/398299/looping-in-a-spiral
#


import colorsys
from datetime import datetime
import math
import os
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import sys


# Set to True to include debugging messages
MOSAIC_DEBUG = False

# Set to False to remove the banner placedin the margin
INCLUDE_BANNER = True


# THE FOLLOWING CONSTANTS ARE RECOMMENEDED.

# Use a square thumb image size that is divisable by many optional dimension sizes.
# 840 is divisable by the numbers 2-8. This is the same value as found in prepare.py
THUMB_SIZE = 840

# Recommended DPI value. This should be pixels per inch not dots per inch?
DPI = 300

# The number of mm in an inch. Used to calculate the DPI of the output image.
INCHES2MM = 25.4

# The environment variable indicating the font to use for the border text.
ENV_MOSAIC_FONT = "MOSAIC_FONT"

# The pixel height of the font.
BANNER_FONT_HEIGHT = 40

# The text spacing for the banner.
BANNER_SPACING = 15

# Number of pixels between the mosaic and the banner description.
# 12mm converted to pixels.
BANNER_BUFFER = round(12 * DPI / INCHES2MM)

# Standard output sizes in mm.
PAGE_SIZES = {'A1':(594,841),'A0':(841,1189),'B1':(707,1000),'B0':(1000,1414)}

# RGB values range from 0-255.
# Dividing an RGB value by 255 will convert it to range from 0 to 1: [0,1]
RGB_NORMALISE = 255

# The index reference into the colour table that doesn't exist! Used to indicate that the original
# image is being used as tile, not a tile from the archive as described in the colour table.
MOSAIC_ORIGINAL_TILE_INDEX = -1

# A label to indicate the original tile being mosaicked has been included in the mosaic,
# not a tile from the archive as described in the colour table.
MOSAIC_ORIGINAL_TILE_NAME = "<original>"

# Remember this setting since it is set to None below.
MY_MAX_IMAGE_PIXELS = Image.MAX_IMAGE_PIXELS

# Setting this to avoid the following runtime warning:
#       DecompressionBombWarning: Image size (... pixels) exceeds limit of ... pixels,
#       could be decompression bomb DOS attack.
Image.MAX_IMAGE_PIXELS = None

# The distance to use when placing the original image as a tile.
# Set to zero - won't impact the result.
MOSAIC_ORIGINAL_TILE_DISTANCE = 0.0


# Read the colour table created by catalog.py.
# Each line in the catalog contains the file name of the square tiles followed by
# the RGB triples for each of the dim*dim squares of the tile. This means there
# are dim*dim*3 integers following the tile file name.
# The ctable returned is a list with elements of:
#   filename
#   the dim*dim colours of RGB values as separate lists for R, G and B
# Note the colour table RGB triples are stored from upper left to bottom right
# and increasing by height then width. So for dimension 2, the triples are stored:
#
#   RGB1    RGB3
#   RGB2    RGB4
#

def readcolourtable(colourtablename, dim):
    table = open(colourtablename)
    line = table.readline()
    ctable = []

    while line:
        cols = line.split()
        name = cols[0]
        redval = []
        greenval = []
        blueval = []

        offset = 1

        for d in range(dim*dim):
            red = int(cols[offset])
            green = int(cols[offset + 1])
            blue = int(cols[offset + 2])
            offset += 3
            redval.append(red)
            greenval.append(green)
            blueval.append(blue)
        colours = (redval, greenval, blueval)
        ctable.append((name, colours))
        line = table.readline()

    return ctable


# The margin is expressed in mm but needs to be converted to pixels.
# When doing this, there may be extra pixels needed to make it fit.
# This is done for both width and height, so "i" (as in pagei and imagei)
# is generic for the image axis.

def checkFill(pagei, imagei, dpi):
    idiff = pagei - imagei
    # the border on both sides
    ib = int(idiff / 2)
    ie = 0
    # check for possible extra space needed
    if idiff % 2 != 0:
        ie += 1
    if MOSAIC_DEBUG:
        print("Fill result: {} {}".format(ib, ie))

    # convert to pixels
    ibp = round(ib * dpi / INCHES2MM)
    iep = round(ie * dpi / INCHES2MM)

    return (ibp, iep)


# Convert the input image into a square thumbnail. Used for placing the input
# image being mosaicked as the tile on the bottom left of the image. Also used
# when optionally blending the original image section being tiled.
# When cropping, need to check for portrait or landscape orientation.
# Note the image coordinates go from (left,top) to (right,bottom): (0,0) -> (width,height)
# A null op if the image is already square.

def crop(image):
    crop = None
    if image != None:
        (width, height) = image.size
        crop = image
        if width < height:
            side = width
            offset = int((height - width) / 2)
            (left, top) = (0, offset)
            (right, bottom) = (side, offset+side)
            crop = image.crop((left, top, right, bottom))
        elif width > height:
            side = height
            offset = int((width - height) / 2)
            (left, top) = (offset, 0)
            (right, bottom) = (offset+side, side)
            crop = image.crop((left, top, right, bottom))

    return crop


# The Euclidean distance is the length of the straight line between two points.

def distance(dim, r1, g1, b1, r2, g2, b2):
    dist = 0.0
    for p in range(dim*dim):
        reddist = abs(r1[p] - r2[p])
        greendist = abs(g1[p] - g2[p])
        bluedist = abs(b1[p] - b2[p])
        d = math.sqrt(reddist*reddist + greendist*greendist + bluedist*bluedist)
        dist += d

    return dist


# Find the best tile from the colour table that matches the section of the
# input image at the row, col location, checking if duplicates allowed.
# Note that the image width is the x dimension which is the column and
# the image height is the y dimension which is the row.
# The getpixel function uses (x,y) which is the (col,row).

def findBestTile(inimage, allowDups, placedTiles, table, dim, row, col):
    found = False
    bestDistance = None
    bestTileIndex = None

    # extract pixels from original image for comparison
    
    (r, g, b) = ([], [], [])
    for fx in range(dim):
        for fy in range(dim):
            (rp, gp, bp) = inimage.getpixel((col*dim+fx,row*dim+fy))
            r.append(rp)
            g.append(gp)
            b.append(bp)

    # find the tile to use at this location, checking if can use duplicates
    for i in range(len(table)):
        if allowDups or i not in placedTiles:
            (name, colours) = table[i]
            (tr, tg, tb) = colours

            # call the distance function
            dist = distance(dim, r, g, b, tr, tg, tb)

            # use average distance to factor the dimension used
            dist = dist / (dim*dim)

            if not found or dist < bestDistance:
                (bestTileIndex, bestDistance) = (i, dist)
                found = True

    assert found

    if MOSAIC_DEBUG:
        print(row,col,r,g,b,table[bestTileIndex][1])

    return (bestTileIndex, bestDistance)


# Find the best tile in the colour table for the location row/col in the
# input image and place this tile into the tileLocations dictionary.

def placeBestTile(originalRow, originalCol, cnt, nTiles, inimage, allowDups, tileLocations, placedTiles, table, dim, row, col):
    # for the bottom left tile, use the original image as the output tile
    if row == originalRow and col == originalCol:
        # Note using an invalid colour table index (MOSAIC_ORIGINAL_TILE_INDEX) to note using the originalTile here
        # and the bestDistance is not relevant so set to MOSAIC_ORIGINAL_TILE_DISTANCE
        (bestTileIndex, bestDistance) = (MOSAIC_ORIGINAL_TILE_INDEX, MOSAIC_ORIGINAL_TILE_DISTANCE)
        if MOSAIC_DEBUG:
            print("Using the original image for the tile")
        tileName = MOSAIC_ORIGINAL_TILE_NAME
    else:
        (bestTileIndex, bestDistance) = findBestTile(inimage, allowDups, placedTiles, table, dim, row, col)
        tileName = table[bestTileIndex][0]

    # remember the image
    tileLocations[(row, col)] = (bestTileIndex, bestDistance)
    placedTiles.add(bestTileIndex)

    if MOSAIC_DEBUG:
        # Note cnt starts at 0 so increment by 1 when reporting
        print("Tile# {}/{}: row {} column {} => distance: {} index: {} tile: {}".format(cnt+1, nTiles, row, col, bestDistance, bestTileIndex, tileName))
        sys.stdout.flush()
    
    return (tileLocations, placedTiles)


# Determine the tile locations using a sprial traversal of the image to find
# the best tile. This can fail if not enough tiles and duplicates not allowed.
# Return a dictionary indicating the (row,column) locations of the tile via
# an index into the colour table along with the distance the tile was.
# Use index of MOSAIC_ORIGINAL_TILE_INDEX when placing the originalTile.

def placeSpiral(inimage, originalRow, originalCol, XD, YD, table, dim, allowDups):
    # Remember where tiles have been placed to create this mosaic.
    # Use (row,col) as key and remember the tile colour table index and distance.
    tileLocations = dict()

    # Remember which tiles have been placed. Use the colour table index to reference the tiles used.
    placedTiles = set()

    # this is the spiral image walk
    ic = int((XD-1)/2)
    jc = int((YD-1)/2)
    x = y = 0
    cnt = 0
    dx = 0
    dy = -1
    for i in range(max(XD, YD)**2):
        if (-XD/2 < x <= XD/2) and (-YD/2 < y <= YD/2):
            # Note: im_j = row and im_i = col
            # using these variables since that's what the original spiral algorithm calls them
            im_i = ic+x
            im_j = jc+y

            (tileLocations, placedTiles) = placeBestTile(originalRow, originalCol, cnt, XD*YD, inimage, allowDups, tileLocations, placedTiles, table, dim, im_j, im_i)
            
            cnt += 1

        if x == y or (x < 0 and x == -y) or (x > 0 and x == 1-y):
            dx, dy = -dy, dx
        x, y = x+dx, y+dy

    return (tileLocations, len(placedTiles))


# Compare the generated image with the original pixel by pixel.
# Will need to resize the original to be the same as the mosiac.

def metric(original, mosaic):
    (oWidth, oHeight) = original.size
    (mWidth, mHeight) = mosaic.size

    if MOSAIC_DEBUG:
        print("Original image size: {} {}".format(oWidth, oHeight))
        print("Mosaic image size:   {} {}".format(mWidth, mHeight))

    assert oWidth <= mWidth
    assert oHeight <= mHeight

    oImage = original.resize((mWidth, mHeight))
    mImage = mosaic

    # normalise the colour space metric
    factor = math.sqrt(3 * 256*256)

    dist = 0.0
    same = 0
    max = 0.0
    cnt = 0
    for x in range(mWidth):
        for y in range(mHeight):
            (r1, g1, b1) = oImage.getpixel((x,y))
            (r2, g2, b2) = mImage.getpixel((x,y))
            rdist = abs(r1 - r2)
            gdist = abs(g1 - g2)
            bdist = abs(b1 - b2)
            d = math.sqrt(rdist*rdist + gdist*gdist + bdist*bdist)

            cnt += 1
            if d == 0.0:
                same += 1
            else:
                normD = (d / factor)
                dist += normD
                if normD > max:
                    max = normD

    avg = dist/cnt

    return avg


# Put a description of the mosaic in the border of the output image.
# This is placed at the bottom left of the image. When rotated,
# adjust where the banner is placed accordingly.

def includeBanner(bigimage, rotated, margin, XD, YD, nTiles, dim, tilemm, allowDups, alpha, nTilesUsed, leftOffset, topOffset, tilesize, actualw):
    # Write a banner describing the mosaic generated.
    (bXD, bYD) = (XD, YD)

    # The banner includes a description of the mosaic undertaken, including the number of rows and cols used etc.
    # These numbers need to be adjusted when the image is rotated - in this case the image is printed as portrait
    # but each tile is rotated so that it is hung as landscape - therefore we need to swap the following:
    if rotated:
        (bXD, bYD) = (YD, XD)

    banner = "Mosaic consists of {:,} tiles (width {} and height {}) ".format(bXD*bYD, bXD, bYD)

    banner = banner + "from archive of {:,} photos. ".format(nTiles)

    banner = banner + "Colour table dimension {}. Tile size {}mm. ".format(dim, tilemm)

    banner = banner + "Duplicate tiles"
    if not allowDups:
        banner = banner + " not"
    banner = banner + " allowed."
    if alpha > 0:
        banner = banner + " Tile blending set at {}%.".format(alpha)
    else:
        banner = banner + " Tile blending not used."

    banner = banner + " Resolution {} dpi.".format(DPI)
    if allowDups:
        banner = banner + " Total unique tiles used {:,}.".format(nTilesUsed)

    date = datetime.today().strftime('%Y-%m-%d')
    banner = banner + " Generated on " + date + "."

    print(banner)

    # get the font to use
    myfont = ImageFont.load_default()
    fontName = os.getenv(ENV_MOSAIC_FONT)
    if fontName is None:
        print("Using the default font!")
    else:
        try:
            myfont = ImageFont.truetype(fontName, BANNER_FONT_HEIGHT)
        except:
            print("Font {} not found. Using the default.".format(fontName))

    # Put the banner below the picture on the left.
    txt = ImageDraw.Draw(bigimage)
    txtLeft = int(leftOffset*1.5)
    txtTop = int(topOffset+tilesize*YD+BANNER_BUFFER)
    txt.text((txtLeft, txtTop), banner, fill=(0, 0, 0), font=myfont, spacing=BANNER_SPACING)

    if rotated:
        # Cut the text out, rotate it 180 degrees and paste it back.
        bannerTxt = bigimage.crop((0, txtTop, actualw, txtTop + BANNER_FONT_HEIGHT))
        # Don't really need to do this, but am...
        bigimage.paste((255,255,255), (0, txtTop, actualw, txtTop + BANNER_FONT_HEIGHT))
        rotatedTxt = bannerTxt.rotate(180, expand=1)
        bigimage.paste(rotatedTxt, (0, txtTop, actualw, txtTop + BANNER_FONT_HEIGHT))

    return bigimage


# Create a mosaic of "newImage" (which may be rotated from Landscape to Portrait).
# The originalImage is the non-rotated image.

def mosaic(originalImage, newImage, rotated, table, tilemm, outname, canvas, dim, allowDups, margin, alpha):
    imgFormat = outname[-3:]

    # The canvas is the physical output dimensions, ie the width/height size of the "paper"
    # being printed to in mm, always in portrait apsect ratio.
    # Pagesize is picture size: the canvas cropped to include the margin, again in mm
    assert canvas[0] < canvas[1]
    pagesize = (canvas[0] - 2*margin, canvas[1] - 2*margin)

    if MOSAIC_DEBUG:
        print("canvas size: {} {}".format(canvas[0], canvas[1]))
        print("pagesize: {} {}".format(pagesize[0], pagesize[1]))

    # Work out upper limit of how many tiles in the X and Y dimensions and the aspect ratio
    (outX, outY) = (pagesize[0]/tilemm, pagesize[1]/tilemm)
    outRatio = outX/outY
    if MOSAIC_DEBUG:
        print("max portrait ntiles {}, {} -- ratio {:5f}".format(outX, outY, outRatio))

    # Create a tile of the original image for the bottom left of the output image.
    originalTile = crop(originalImage)

    # Aspect ratio of the image being mosaicked.
    (origX, origY) = newImage.size
    origRatio = origX/origY
    if MOSAIC_DEBUG:
        print("original image portrait size: {}, {} -- ratio {:5f}".format(origX, origY, origRatio))

    # So far we know the maximum number of tiles that can fit into the pagesize, but we need
    # to maintain the aspect ratio of the original image being mosaicked.
    # The apsect ratio is the width/height
    if origRatio < outRatio:
        # the height is ok, need to adjust the number of tiles for the width
        # using the aspect ratio of the original image
        XD = int(outY*origRatio)
        YD = int(outY)
    else:
        # the width is ok, need to adjust the number of tiles for the height
        # using the aspect ratio of the original image
        XD = int(outX)
        YD = int(outX/origRatio)

    ratio = XD/YD
    if MOSAIC_DEBUG:
        print("ntiles: {}, {} -- ratio {:5f}".format(XD, YD, ratio))

    (X, Y) = (dim*XD, dim*YD)
    inimage = newImage.resize((X,Y))

    tilesize = THUMB_SIZE

    # work out what the tilesize should be to maintain the DPI value
    targetTilesize = round(DPI * tilemm / INCHES2MM)
    if MOSAIC_DEBUG:
        print("targetTilesize = {}".format(targetTilesize))
    if targetTilesize < tilesize:
        if MOSAIC_DEBUG:
            print("Adjusting the tilesize from {} to: {}".format(tilesize, targetTilesize))
        tilesize = targetTilesize
    else:
        if MOSAIC_DEBUG:
            print("Can increase tilesize to be size: {}".format(targetTilesize))

    # cross check the targetTilesize

    if MOSAIC_DEBUG:
        print("Original image size {} -- type {} -- ratio {:5f}".format(newImage.size, newImage.mode, (newImage.size[0]/newImage.size[1])))
        print("Reduced image size {} -- type {} -- ratio {:5f}".format(inimage.size, inimage.mode, (inimage.size[0]/inimage.size[1])))
    print("Need to place {} images".format(XD*YD))

    if XD*YD > len(table) and not allowDups:
        print("ERROR: not enough images in the photo archive ({:,} images) to create mosaic".format(len(table)))
        return

    # this is for the image being created - measured in pixels
    bigwidth = tilesize * XD
    bigheight = tilesize * YD

    if MOSAIC_DEBUG:
        print("Initial image size (in pixels): {} {}".format(bigwidth, bigheight))

    # check for max image size
    maxPixels = MY_MAX_IMAGE_PIXELS
    if MOSAIC_DEBUG:
        print("maxPixels = {}".format(maxPixels))
    if bigwidth > maxPixels or bigheight > maxPixels:
        if bigwidth > bigheight:
            newtilesize = int(maxPixels / XD)
        else:
            newtilesize = int(maxPixels / YD)
        print("MAX PIXELS: adjusting tilesize from {} to: {}".format(tilesize, newtilesize))
        tilesize = newtilesize
        bigwidth = tilesize * XD
        bigheight = tilesize * YD

    if MOSAIC_DEBUG:
        print("Initial big image size (in pixels): {} {}".format(bigwidth, bigheight))

    # Adjust the image to include the optional white border (margin)
    pixelIndent = int((2 * margin * DPI / INCHES2MM))
    actualw = bigwidth + pixelIndent
    actualh = bigheight + pixelIndent

    if MOSAIC_DEBUG:
        print("Initial actual width and height: {} {} (with pixelIndent {})".format(actualw, actualh, pixelIndent))

    # A tile is placed using pixel coordinates - need to work out the (left, top)
    # pixel offsets of where the image starts on the canvas (the actual page being
    # printed on). Makes use of the DPI for this.
    (leftOffset, topOffset) = (0, 0)
    xmm = int(bigwidth * INCHES2MM / DPI)
    ymm = int(bigheight * INCHES2MM / DPI)
    if MOSAIC_DEBUG:
        print("Image physical mm dimension (includes margins): {} {}".format(xmm, ymm))
        print("Cross check: maximum dimensions: {} {}".format(canvas[0], canvas[1]))

    assert xmm <= canvas[0]
    assert ymm <= canvas[1]

    # check border fill in pixels allowing for possible "extra" pixels
    (widthFillPixels, widthExtraPixels) = checkFill(canvas[0], xmm, DPI)
    (heightFillPixels, heightExtraPixels) = checkFill(canvas[1], ymm, DPI)

    actualw = bigwidth + widthFillPixels * 2 + widthExtraPixels
    actualh = bigheight + heightFillPixels * 2 + heightExtraPixels
    if MOSAIC_DEBUG:
        print("Final image pixel dimensions: {} {}".format(actualw, actualh))

    # set offsets from the left, top corner
    (leftOffset, topOffset) = (widthFillPixels, heightFillPixels)
    if MOSAIC_DEBUG:
        print("left/top offset: {} {}".format(leftOffset, topOffset))

    actualxmm = int(round(actualw * INCHES2MM / DPI))
    actualymm = int(round(actualh * INCHES2MM / DPI))
    print("Final image physical mm dimension: {} {}".format(actualxmm, actualymm))

    if MOSAIC_DEBUG:
        print("Creating image size : {} {}".format(actualw, actualh))
    sys.stdout.flush()

    # Create the output image and fill it to be all white
    bigimage = Image.new("RGB", (actualw, actualh))
    bigimage.paste((255,255,255), (0, 0, actualw, actualh))

    # The row/column tile position to place a tile of the original image being mosaicked
    originalRow = YD-1
    originalCol = 0
    if rotated:
        originalRow = YD-1
        originalCol = XD-1

    (tileLocations, nTilesUsed) = placeSpiral(inimage, originalRow, originalCol, XD, YD, table, dim, allowDups)

    # Now place the tiles into the bigimage, applying alpha to the tiles as needed.
    if alpha > 0:
        # Resize the input image to align with the tiles and dimensions
        # ready for mosaicking
        originalBig = newImage.resize((bigwidth, bigheight))

    total = 0.0
    cnt = 0
    for key in tileLocations.keys():
        (row, col) = key
        (index, distance) = tileLocations[key]

        if index == MOSAIC_ORIGINAL_TILE_INDEX:
            tileName = MOSAIC_ORIGINAL_TILE_NAME
            tile = originalTile
        else:
            tileName = table[index][0]
            tile = Image.open(tileName)

        total += distance

        tile = tile.resize((tilesize, tilesize))

        if rotated:
            tile = tile.rotate(90, expand=True)

        left = col * tilesize
        right = left + tilesize
        top = row * tilesize
        bottom = top + tilesize

        # optionally blend the tile with the original image bit
        if alpha > 0:
            ocrop = originalBig.crop((left, top, right, bottom))
            if rotated:
                ocrop = ocrop.rotate(90, expand=True)
            if MOSAIC_DEBUG:
                print("index: {} name: {}".format(index, tileName))
            blend = Image.blend(tile, ocrop, round(alpha/100.0,2))
        else:
            blend = tile

        bigimage.paste(blend, (leftOffset+left, topOffset+top, leftOffset+right, topOffset+bottom))
        tile.close()
        if alpha > 0:
            blend.close()

        cnt += 1

    if alpha > 0:
        originalBig.close()

    # include the banner if we have a margin to put it in
    if margin == 0 or not INCLUDE_BANNER:
        print("Skipping banner")
    else:
        bigimage = includeBanner(bigimage, rotated, margin, XD, YD, len(table), dim, tilemm, allowDups, alpha, nTilesUsed, leftOffset, topOffset, tilesize, actualw)

    sys.stdout.flush()

    bigimage.save(outname, dpi=(DPI,DPI))

    # When comparing images using the metric function, only compare the actual
    # mosaic image - not the white/blank border or the text banner!
    # Do this by cropping the mosaic portion from the bigimage
    justMosaic = bigimage.crop((leftOffset, topOffset, leftOffset+(XD*tilesize), topOffset+(YD*tilesize)))

    # Can now close the result image.
    bigimage.close()

    metricAvg = metric(newImage, justMosaic)

    percent = (1 - metricAvg) * 100.0

    print("metric percentage: {}".format(round(percent,2)))


# Do the mosaicking by rotating landscape images to portrait

def main(original_image, tilemm, outname, canvas, colourtable, dim, allowDups, margin, alpha):
    table = readcolourtable(colourtable, dim)

    print("opening file {}".format(original_image))

    # Convert to RGB just to be sure.
    originalImage = Image.open(original_image).convert("RGB")
    (width, height) = originalImage.size
    print("input image size: {}, type {}".format(originalImage.size, originalImage.mode))

    # Rotate the image being mosaicked as needed.
    # Keep in the original image as is since it will be used as a tile.
    rotated = False
    workingImage = originalImage
    if width > height:
        rotated = True
        workingImage = originalImage.rotate(90, expand=True)
        print("rotating image to be portrait")
        (width, height) = workingImage.size
        print("input image size now: {} -- type {}".format(workingImage.size, workingImage.mode))

    mosaic(originalImage, workingImage, rotated, table, tilemm, outname, canvas, dim, allowDups, margin, alpha)


# Command line options:
#
#   originalimage      - The input image to be mosaicked
#   tilemm             - The size in mm of the square tile to be placed into the mosaicked image
#   outputimage        - The output mosaicked image
#   outputpagesize     - Page size to be printed, one of A1, A0, B1, B0 or a custom WidthxHeight (WxH)
#   colourtable        - Colour table file for the tiles to be used for mosaicking
#   dim                - Colour table dimension
#   allowDups          - Allow duplicate tiles in mosiac <True|False>
#   borderMM           - The space to leave around the border in mm
#   alpha              - How much to "blend" the original image with the tile as a percentage.
#                        0 = no blend, 100 = full blend, 50 half blend, etc.

if __name__ == '__main__':
    if len(sys.argv) != 10:
        print("Usage: {} originalimage tilemm outputimage <{}> colourtable dim allowDups borderMM alpha".format(sys.argv[0], "|".join(sorted(PAGE_SIZES.keys()))))
    else:
        pagesize = sys.argv[4]

        canvas = None
        if pagesize in PAGE_SIZES.keys():
            canvas = PAGE_SIZES[pagesize]
        else:
            if 'x' in pagesize:
                i = pagesize.index('x')
                w = int(pagesize[:i])
                h = int(pagesize[i+1:])
                if w > h:
                    print("Width must be less than or equal to Height for custom pagesize")
                else:
                    canvas = (w,h)
        if canvas == None:
            print("Unknown output page size: {}. Use one of: <{}> or WxH".format(pagesize, PAGE_SIZES.keys()))
        else:
            allowDups = False
            if sys.argv[7].lower() == "true":
                allowDups = True

            alpha = int(sys.argv[9])
            if alpha < 0 or alpha > 100:
                print("Incorrect image blend percentage {}".format(alpha))
            else:
                main(sys.argv[1], int(sys.argv[2]), sys.argv[3], canvas, sys.argv[5], int(sys.argv[6]), allowDups, int(sys.argv[8]), alpha)
