#!/usr/bin/env python3


"""
PhotoLightSaber (PLS) is a script for organizing your photos.

It is intended to be used with CoW File Systems like btrfs, xfs. PLS will try to use reflinks for importing the files.
Leveraging reflinks it will allow for more space efficient storage of the duplicated files.


Folders
 - hashlib -- Folder for all files ordered after sha256 hash
 - by-time -- Photos linked after the Year and time
 - by-camera -- Photos sorted after the camera model.
 - by-import -- Photos bz import run - contains the original file names
 - log -- Output for logfiles

"""

import os
import sys
import os.path
import logging
from PIL.ExifTags import TAGS

#TODO: import multiprocessing # use parallel processing

# was passiert wenn ein file schon im has ist aber geändert wurde. wie ist dann der löschen / umschreiben
# Idee nicht umschreiben, da bei erneutem imort die datai wieder auftaucht.

#class PhotoLightSaber:

def extensions():
    #return ('.heic') # for testing
    return ('.ras', '.xwd', '.bmp', '.jpe', '.jpg', '.jpeg', '.xpm',
            '.ief', '.pbm', '.tif', '.gif', '.ppm', '.xbm',
            '.tiff', '.rgb', '.pgm', '.png', '.pnm', '.heic', '.heif')


def import_files(base_path, import_path):
    for root, dirs, files in os.walk(import_path):
        for file in files:
            if file.endswith(".txt"):
                print(os.path.join(root, file))


def import_files2(base_path, import_path):
    from pathlib import Path

    count_imported = 0
    count_existed = 0

    for ext in extensions():
        for filename in Path(import_path).rglob('*' + ext):
            if filename.is_file():
                print(filename)
                newfile = copyfile(base_path, filename)
                if newfile != "":
                    count_imported += 1
                    # extract_metadata(newfile)
                else:
                    count_existed += 1


def check_call2(args, shell=False):
    cmd_str = " ".join(args)
    print(cmd_str)


def check_call(args, shell=False):
    cmd_str = " ".join(args)
    import subprocess
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=shell)
    stdout, stderr = p.communicate()
    if stdout:
        logging.trace(stdout)
    if stderr:
        logging.trace(stderr)
    if p.returncode != 0:
        raise RuntimeError("failed %s" % cmd_str)
    return stdout  # return the content


def getHashFilename(base_path, filename):
    filehash = hashfile(filename)
    file, fileext = os.path.splitext(filename)
    return os.path.join(base_path, filehash[0:1], filehash + fileext)

def getCopyCmd():
    import platform
    if platform.system() == "Darwin":
        return "cp -c"
    elif platform.system() == "Windows":
        return "" # Windows Use Junctions or Links?
    else:
        return "cp --reflink=auto"



def copyfile(base_path, filename):
    newfile = getHashFilename(base_path, filename)
    if not os.path.exists(newfile):

        args=[getCopyCmd(), str(filename), newfile]

        check_call2(args)

        return newfile
    else:
        return ""


def extract_metadata(filename):
    from PIL import Image, UnidentifiedImageError
    try:

        with Image.open(filename) as im:
            exif = im.getexif()
            labeled = get_labeled_exif(exif)

    except UnidentifiedImageError as err:
        logging.info('unable to read image file', err)


def get_labeled_exif(exif):
    labeled = {}
    for (key, val) in exif.items():
        labeled[TAGS.get(key)] = val
        print("{0} -> {1} ".format( TAGS.get(key), val) )

    return labeled
    # Interesting label - DateTimeOriginal, Make and Model,


def hashfile(filename):
    """
    Reads a File and returns the hex digest of the file
    """
    import hashlib

    buffer = 65536

    hash = hashlib.sha256()

    with open(filename, 'r+b') as f:
        while True:
            data = f.read(buffer)
            if not data:
                break
            hash.update(data)

    return hash.hexdigest()


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        description='this is the PhotoLightSaber tool')

    parser.add_argument(
        '--base-path', '-p',
        metavar='PATH',
        dest='base_path',
        required=True,
        help='Target PhotoLightSaber base path')

    parser.add_argument(
        '--import-path', '-i',
        metavar='PATH',
        dest='import_path',
        required=True,
        help='Add the Pictures to the PhotoLightSaber base Path.'
             'Pictures will only be physically copied if across filesystem '
             'or on non reflink possible fs')

    parser.add_argument(
        '--explain',
        help='Explain what %(prog)s does (and stop)',
        action='store_true')

    parser.add_argument(
        '--verbose', '-v',
        help='Verbose output',
        action='store_true')

    pa = parser.parse_args(argv[1:])

    # safety net if no arguments are given call for help
    if len(sys.argv[1:]) == 0:
        parser.print_help()
        return 0

    if pa.explain:
        sys.stdout.write(__doc__)
        return 0

    if pa.base_path is not None and pa.import_path is not None:
        import_files2(pa.base_path, import_path=pa.import_path)


if "__main__" == __name__:
    sys.exit(main(sys.argv))
