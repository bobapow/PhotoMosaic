#-*- coding: utf-8 -*-

# Licensed under the MIT License.
# See https://opensource.org/licenses/MIT or License.txt for license text.

# Generate small square thumbnails from a collection of images to be used for mosaicking.

# The code makes use of the image EXIF (Exchangeable Image File Format) metadata tags to 
# determine the image orientation. These image tags are made available in a dictionary
# with numeric keys. These numeric keys have string descriptors available in the
# ExifTags.TAGS dictionary. See the function getOrientationExifKey() below for an example
# of how to find the numeric keys from the more understandable string descriptors.
#
# Also, the EXIF metadata is available using the functions _getexif() and getexif().
# I found _getexif() to be more reliable, so use this first and if no values are found,
# then use getexif().


import hashlib
from PIL import Image
from PIL import ExifTags
import imagehash
import os
import shutil
import sys


# Use a square thumb image size that is divisable by many optional dimension sizes
# 840 is divisable by the numbers 2-8

THUMB_SIZE = 840


# Finds the ExifTags key for the string descriptor, or returns None if not found

def findExifKey(descriptor):
    key = None
    for tag in ExifTags.TAGS:
        if ExifTags.TAGS[tag] == descriptor:
            key = tag
            print("Exif attribute {} has index {}".format(descriptor, tag))
            break
    return key


# Find the EXIF Orientation tag
def getOrientationExifKey():
    return findExifKey("Orientation")


# Find the orientation from the image's EXIF info.

def getOrientation(imExif, key):
    orientation = None
    if imExif is not None:
        if key in imExif.keys():
            orientation = imExif[key]
    return orientation


# Find the orientation of the image. First use the function _getexif(),
# if that doesn't work, then use getexif().

def getImageOrientation(im, key):
    orientation = None
    try:
        orientation = getOrientation(im._getexif(), key)
    except:
        orientation = None
    if orientation is None:
        try:
            orientation = getOrientation(im.getexif(), key)
        except:
            orientation = None
    return orientation


# Calculate the md5sum for the given file.
# Note that two images files may have the exact same image, but due to different
# metadata the files will have differing md5sum values.
# See the imagehash library functions for different methods of comparing the images.

def md5sum(fname):
    hash_md5 = hashlib.md5()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


# Open is a "lazy" operation. If not doing some other operation here, eg convert("RGB"),
# then call load() to get the pixel data to ensure the image can be read ok from now on.
# Sometimes an image thumbnail looks fine, but the file is corrupted - load now to 
# throw an exception to ensure subsequent code works ok.

def readImageFile(fname, ext):
    im = None
    try:
        if ext == "gif":
            # Convert to RGB to standardise the image processing ops,
            # notably getpixel to return an RGB tuple.
            im = Image.open(fname).convert("RGB")
        elif ext == "png":
            im = Image.open(fname)
            # Check for and remove the alpha channel.
            if im.mode == "RGBA":
                im = im.convert("RGB")
            else:
                im.load()
        elif ext == "jpg":
            im = Image.open(fname).convert("RGB")
            im.load()
    except:
        print("Error reading file: {}".format(fname))
        im = None

    return im


# Create a square thumbnail image of size THUMB_SIZE x THUMB_SIZE from the provided image.
# The new thumbnail is the square portion in the middle of the provided image, so need
# to check if the original image is portrait or landscape or sqaure. Also check if the
# original image is smaller than the thumbnail being produced, resizing if needed.
# Note the image coordinates go from (left,top) to (right,bottom): (0,0) -> (width,height)

def createThumb(im):
    width, height = im.size
    imcopy = im

    if width < height:
        if width < THUMB_SIZE:
            neww = THUMB_SIZE
            # keep aspect ratio
            newh = int(THUMB_SIZE * height / width)
            imcopy = im.resize((neww, newh))
            (width, height) = (neww, newh)
        side = width
        offset = int((height - width) / 2)
        (left, top) = (0, offset)
        (right, bottom) = (side, offset+side)
    elif width > height:
        if height < THUMB_SIZE:
            # keep aspect ratio
            neww = int(THUMB_SIZE * width / height)
            newh = THUMB_SIZE
            imcopy = im.resize((neww, newh))
            (width, height) = (neww, newh)
        side = height
        offset = int((width - height) / 2)
        (left, top) = (offset, 0)
        (right, bottom) = (offset+side, side)
    else:
        # square
        if width < THUMB_SIZE:
            imcopy = im.resize((THUMB_SIZE, THUMB_SIZE))
            (width, height) = (THUMB_SIZE, THUMB_SIZE)
        (left, top) = (0, 0)
        (right, bottom) = (width, height)

    tile = imcopy.crop((left, top, right, bottom))
    width, height = tile.size
    assert width == height
    thumb = tile.resize((THUMB_SIZE, THUMB_SIZE))

    return thumb


# Remove the trailing directory path separator from the directory name.

def removeTrailingSlash(dirName):
    while dirName[-1] == os.sep:
        dirName = dirName[:-1]

    return dirName


# Create sqaure thumbnail images from jpg, png and gif images found in each of the dirs
# directories. Use the image ExifTags to rotate the original image correctly.
# EXIF is the "Exchangeable Image File Format" and contains metadata about the image.
# Place the created thumbs into a directory structure that is the same as the original, but
# using a different root parent directory of the paramter target.
# Similar images are placed into the dircetory <target>_similar.

def main(target, hash_threshold, format, dirs):
    imageFormats = ('jpg','png','gif')
    (total, md5Dup, hashDup, dist, err) = (0, 0, 0, 0, 0)
    orientationCounters = dict()
    hasExif_Orientation = 0
    orientationMissing = 0
    totals = dict()
    md5s = dict()
    hashes = dict()
    similars = dict()
    for img in imageFormats:
        totals[img] = 0

    orientationExifKey = getOrientationExifKey()

    # Make sure 'target' does not end with the directory path separator
    # This will be added later.
    target = removeTrailingSlash(target)

    targetSimilar = target + "_similar"

    os.mkdir(target)
    os.mkdir(targetSimilar)

    # repeat for each of the dirs directories provided
    for pics in dirs:
        # make sure pics ends with the directory path separator
        if pics[-1] != os.sep:
            pics = pics + os.sep

        print("Starting at: {}".format(pics))
        print("Copying to:  {}".format(target))
        for root, dirs, files in os.walk(pics):
            # this is the directory path to place the found images into under target
            dirname = root[len(pics):]

            counters = dict()
            for img in imageFormats:
                counters[img] = 0
            (dir_total, dir_md5Dup, dir_hashDup, dir_dist, dir_err) = (0, 0, 0, 0, 0)

            for file in files:
                ext = os.path.splitext(file.lower())[1][1:]
                if ext in imageFormats:
                    dir_total += 1
                    counters[ext] += 1

                    # full file path of the image being read
                    root = removeTrailingSlash(root)
                    fullFile = root + os.sep + file

                    # check image md5sum values
                    md5 = md5sum(fullFile)
                    if md5 in md5s.keys():
                        dir_md5Dup += 1
                        print("Duplicate md5: {} with {}".format(fullFile, md5s[md5]))
                    else:
                        # include the md5sum in the dictionary
                        md5s[md5] = fullFile

                        # when doing hash similarity, rotate image first
                        im = readImageFile(fullFile, ext)
                        if im is None:
                            dir_err += 1
                        else:
                            # rotate image as needed
                            orientation = getImageOrientation(im, orientationExifKey)
                            if orientation is not None:
                                hasExif_Orientation += 1
                                if orientation not in orientationCounters.keys():
                                    orientationCounters[orientation] = 0
                                orientationCounters[orientation] += 1
                                if orientation == 3:
                                    im = im.rotate(180, expand=True)
                                elif orientation == 6:
                                    im = im.rotate(270, expand=True)
                                elif orientation == 8:
                                    im = im.rotate(90, expand=True)
                                # otherwise orientation ok as is
                            else:
                                orientationMissing += 1

                            # Now check image hash values.
                            # I originally used the average_hash() function,
                            # but dhash works better. Also explored using
                            # different 'hash_size=...' but the default of 8
                            # works well.
                            hash = None
                            try:
                                hash = imagehash.dhash(im)
                            except:
                                dir_err += 1
                                print("Error with image hash for file: {}".format(fullFile))

                            if hash is not None:
                                found = False
                                similarFile = None
                                hashDiff = -1
                                for key in hashes.keys():
                                    value = hashes[key]
                                    # The threshold for hash value similarity is subjective,
                                    # hence using a command line argument for this.
                                    hashDiff = hash - value
                                    if hashDiff < hash_threshold:
                                        dir_hashDup += 1
                                        found = True
                                        similarFile = key
                                        break
                                if found:
                                    # Save the hash based similar images to the hash dir
                                    # grouping them together. Use the file counter as references
                                    # to the original files to track them down
                                    (fileCount, count) = similars[similarFile]
                                    print("Hash similar #{}, difference {} below threshold {} for new image: {} (#{:05d}) and previous image {} (#{:05d})".format(hashDup+dir_hashDup, hashDiff, hash_threshold, fullFile, total+dir_total, key, fileCount))
                                    if count == 0:
                                        # first time an existing image has been found to be similar with another
                                        firstExt = os.path.splitext(similarFile.lower())[1][1:]
                                        firstSim = "{}{}sim_{:05d}.{}".format(targetSimilar, os.sep, fileCount, firstExt)
                                        shutil.copyfile(similarFile, firstSim)
                                    # now copy the similar file
                                    count += 1
                                    similars[similarFile] = (fileCount, count)
                                    nextExt = os.path.splitext(fullFile.lower())[1][1:]
                                    nextSim = "{}{}sim_{:05d}_{:05d}.{}".format(targetSimilar, os.sep, fileCount, total+dir_total, nextExt)
                                    shutil.copyfile(fullFile, nextSim)
                                else:
                                    # Include this file into the similars dictionary with the given
                                    # counts so we can compare results when using different hash thresholds
                                    similars[fullFile] = (total+dir_total, 0)
                                    dir_dist += 1
                                    hashes[fullFile] = hash

                                    # keep the same directory structure for the thumb image
                                    # note the file number in case need to track down similar files later
                                    targetDirname = "{}{}{}".format(target, os.sep, dirname)
                                    targetDirname = removeTrailingSlash(targetDirname)
                                    if not os.path.exists(targetDirname):
                                        os.makedirs(targetDirname)
                                    filename = os.path.splitext(file)[0]
                                    targetFilename = "{}{}{}.{}".format(targetDirname, os.sep, filename, format)
                                    print("Thumb #{} {} from {}".format(total+dir_total, targetFilename, fullFile))

                                    # create thumb and save it
                                    thumb = createThumb(im)
                                    thumb.save(targetFilename)
                                    thumb.close()
                            im.close()
                    sys.stdout.flush()

            total += dir_total
            md5Dup += dir_md5Dup
            hashDup += dir_hashDup
            dist += dir_dist
            err += dir_err
            for ext in imageFormats:
                totals[ext] += counters[ext]
            if dir_total > 0:
                line = "{} has:".format(root)
                for ext in imageFormats:
                    if counters[ext] > 0:
                        line = "{} {} {}".format(line, counters[ext], ext)
                print("{}. This dir: {} {} {} {}. Totals: {} {} {} {}".format(line, dir_total, dir_dist, dir_md5Dup+dir_hashDup, dir_err, total, dist, md5Dup+hashDup, err))
            sys.stdout.flush()

    print(" total images found: {}".format(total))
    for ext in imageFormats:
        if totals[ext] > 0:
            print("                     {} => {}".format(ext, totals[ext]))
    print("         num errors: {}".format(err))
    print("     hash threshold: {}".format(hash_threshold))
    print("   images processed: {}".format(total-err))
    print("   with orientation: {}".format(hasExif_Orientation))
    print("orientation missing: {}".format(orientationMissing))
    for orientation in orientationCounters.keys():
        print("                     orientation {} => {}".format(orientation, orientationCounters[orientation]))
    print(" duplicates md5sums: {}".format(md5Dup))
    print("  duplicates hashes: {}".format(hashDup))
    print("   duplicates found: {}".format(md5Dup + hashDup))
    print("       unique found: {}".format(dist))
    print("        num md5sums: {}".format(len(md5s)))
    print("         num hashes: {}".format(len(hashes)))
    print("   dups cross check: {} (should be zero!)".format(len(md5s)-(len(hashes)+hashDup)))


# Produces square thumbnail images used for mosaicking from a collection of images
# contained in the provided directories. Duplicate images are checked for using md5sum
# and near duplicates are determined using the imagehash function. The thumb images
# are placed into directories corresponding to the original source directory structure,
# but "rooted" at <target_dir>. The near duplicates are also copied to a new directory
# called <target_dir>_similar so they can be reviewed to check they are indeed near
# duplicates. This can be useful for adjusting the value of <hash_threshold>,
# although a value of 5 is recommended.
#
# Command line options are:
#
#   target_dir     - directory to place the created thumbnails
#   hash_threshold - the hash function threshold indicating duplicate images
#                    if 0, similar images won't be found
#   format         - the output image format to use for the thumbnails: png or jpg
#   photos_dir+    - the top level directories containg the source images 

if __name__ == '__main__':
    formats = ('jpg','png')
    if len(sys.argv) < 5:
        print("usage: {} target_dir hash_threshold format photos_dir+".format(sys.argv[0]))
    else:
        format = sys.argv[3].lower()
        if format in formats:
            main(sys.argv[1], int(sys.argv[2]), format, sys.argv[4:])
        else:
            print("format must be one of {}".format(formats))
