#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PhotoLightSaber (PLS) is a script for organizing your photos.

It is intended to be used with CoW File Systems like btrfs, xfs. PLS will try to use reflinks for importing the files.
Leveraging reflinks it will allow for more space efficient storage of the duplicated files.


Folders
 - hash-lib -- Folder for all files ordered after sha256 hash
 - by-time -- Photos linked after the Year and time
 - by-camera -- Photos sorted after the camera model.
 - by-import -- Photos bz import run - contains the original file names
 - log -- Output for logfiles

"""

import os
import sys
import os.path
import logging
import enum
import datetime
from pathlib import Path
from PIL.ExifTags import TAGS

#TODO: import multiprocessing # use parallel processing

# was passiert wenn ein file schon im has ist aber geändert wurde. wie ist dann der löschen / umschreiben
# Idee nicht umschreiben, da bei erneutem imort die datei wieder auftaucht.

starttime = datetime.datetime.now()


class Folders(enum.Enum):
    LOG = "log"
    HASH_LIB = "hash-lib"
    BY_CAMERA = "by-camera"
    BY_IMPORT = "by-import"
    BY_TIME = "by-time"

class MetaInfo(enum.Enum):
    DATETIME_ORG = "DateTimeOriginal"
    DATETIME_CREATED = "CreateDate"
    DATETIME_GPS = "GPSDateTime"
    DATETIME_FILE_MODIFY = "FileModifyDate"


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


def extensions(self):
    #return ('.heic') # for testing
    return ('.ras', '.xwd', '.bmp', '.jpe', '.jpg', '.jpeg', '.xpm',
            '.ief', '.pbm', '.tif', '.gif', '.ppm', '.xbm',
            '.tiff', '.rgb', '.pgm', '.png', '.pnm', '.heic', '.heif')


def get_copy_cmd():
    import platform
    if platform.system() == "Darwin":
        return ["cp", "-c"]
    elif platform.system() == "Windows":
        return [""] # Windows Use Junctions or Links?
    else:
        return ["cp", "--reflink=auto"]


class PhotoLightSaber:
    def __init__(self, base_path, copy_cmd=None):
        self.base_path = base_path

        if copy_cmd is not None:
            self.copy_cmd = copy_cmd
        else:
            self.copy_cmd = get_copy_cmd()


    def import_files(self, import_path):
        for root, dirs, files in os.walk(import_path):
            for file in files:
                if file.endswith(".txt"):
                    print(os.path.join(root, file))

    def bootstrap_directory_structure(self):
        if not os.path.exists(self.base_path):
            os.mkdir(self.base_path)

        for f in Folders:
            path = os.path.join(self.base_path, f.value)
            if not os.path.exists(path):
                logging.info("Creating path: %s ", path)
                os.mkdir(path)

        for f in "0123456789abcdef":
            path = os.path.join(self.base_path, Folders.HASH_LIB.value, f)
            if not os.path.exists(path):
                logging.info("Creating path: %s ", path)
                os.mkdir(path)

    def import_files2(self, import_path):

        count_imported = 0
        count_existed = 0

        for ext in extensions():
            for filename in Path(import_path).rglob('*' + ext):
                if filename.is_file():
                    print("reading file %s" % filename)
                    newfile = self.copyfile(filename)
                    if newfile != "":
                        count_imported += 1

                        self.extract_metadata2(newfile)
                    else:
                        count_existed += 1
        print("found files: %s, cloned files: %s, already existed: %s  "
              % (count_imported+count_existed, count_imported, count_existed) )
        logging.info("found files: %s, cloned files: %s, already existed: %s  "
                     , count_imported+count_existed, count_imported, count_existed)

    def check_call2(self, args, shell=False):
        cmd_str = " ".join(args)
        print(cmd_str)


    def check_call(self, args, shell=False):
        cmd_str = " ".join(args)
        logging.info("Execute command: '%s' ", cmd_str)
        import subprocess
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=shell,
            text=True)
        stdout, stderr = p.communicate()
        if stdout:
            logging.debug(stdout)
        if stderr:
            logging.debug(stderr)
        if p.returncode != 0:
            raise RuntimeError("failed %s" % cmd_str)
        return stdout  # return the content

    def getHashFilename(self, filename):
        filehash = hashfile(filename)
        file, fileext = os.path.splitext(filename)
        return os.path.join(self.base_path, Folders.HASH_LIB.value, filehash[0:1], filehash + fileext)


    def copyfile(self, base_path, filename):
        newfile = self.getHashFilename(filename)
        if not os.path.exists(newfile):
            args = self.copy_cmd + [str(filename), newfile]
            self.check_call(args)
            return newfile
        else:
            return ""

    def link_datetime(self, base_path, filename, date_time_str):
        if date_time_str is not None or date_time_str != "":
            # date_time = datetime.datetime.strptime(date_time_str, "%Y:%m:%d %H:%M:%S")
            root, ext = os.path.splitext(filename)
            head, tail = os.path.split(filename)
            path = os.path.join(base_path, Folders.BY_TIME.value, date_time_str[0:4], date_time_str[5:7])
            #print("create path: %s" % path)
            os.makedirs(path, exist_ok=True)

            link_name = os.path.join(path, date_time_str.replace(":", "-") + "_" + tail[0:8] + ext)
            if not os.path.exists(link_name):
                os.symlink(filename, link_name) # os.link alternative

    def getexif(self, filename):
        args = ["exiftool", "-a", "-s", "-n", "-t", filename]
        mstring = self.check_call(args)
        exif = {}
        for line in mstring.splitlines():
            a, b = line.split('\t', 1)
            print("a,b -> %s, %s" % (a, b))
            exif[a] = b
        return exif

    def extract_date(self, exif):
        if MetaInfo.DATETIME_CREATED.value in exif:
            return exif[MetaInfo.DATETIME_CREATED.value]
        elif MetaInfo.DATETIME_ORG.value in exif:
            return exif[MetaInfo.DATETIME_ORG.value]
        elif MetaInfo.DATETIME_GPS.value in exif:
            return exif[MetaInfo.DATETIME_GPS.value]
        else:
            return exif[MetaInfo.DATETIME_FILE_MODIFY.value]

    def extract_metadata2(self, filename):
        exif = self.getexif(filename)
        self.link_datetime(filename, self.extract_date(exif))

    def extract_metadata(self, base_path, filename):
        from PIL import Image, UnidentifiedImageError
        try:

            with Image.open(filename) as im:
                exif = im.getexif()
                if exif is not None:

                    if 306 in exif:
                        datetimestr = exif[306]
                        print("DateTimeString: %s" % datetimestr)  # looks like 2016:08:15 10:18:47
                        self.link_datetime(base_path, filename, datetimestr)
                    else:
                        labeled = self.get_labeled_exif(exif)


                    #print("Camera: %s %s" %( exif[271], exif[272] ))

                else:
                    t = os.path.getmtime(filename)
                    self.link_datetime(base_path, filename, datetime.datetime.strftime("%Y:%m:%d %H:%M:%S"))

        except UnidentifiedImageError as err:
            logging.info('unable to read image file', err)


    def get_labeled_exif(self, exif):
        labeled = {}
        for (key, val) in exif.items():
            labeled[TAGS.get(key)] = val
            print("{0}.{1} -> {2} ".format(TAGS.get(key), key, val))

        return labeled
        # Interesting label - DateTimeOriginal, Make (271) and Model (272),


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
        photolisa = PhotoLightSaber(pa.base_path)

        photolisa.import_files2(pa.base_path, pa.import_path)


if "__main__" == __name__:
    sys.exit(main(sys.argv))
