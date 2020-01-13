#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""
PhotoWoylie (short woylie) is a script for organizing your photos.

It is intended to be used with CoW File Systems like btrfs, xfs, apfs. Woylie will try to use reflinks for
importing photos and movies.

Rationale:
Leveraging reflinks it will allow for more space efficient storage of the duplicated files. Most users have already
stored Photos on the disk in several locations. Often unable to identify which files have already been imported,
copied, sorted or the like. Woylie will import all files to the hash-lib where files are stored by their hash digest.
duplicate files will thus not be imported, even if they are from different locations (as long as the content hasn't
been changed.


Folders
 - hash-lib -- Folder for all files ordered after sha256 hash
 - by-time -- Photos linked after the Year and time
 - by-camera -- Photos sorted after the camera model.
 - by-import -- Photos by import run - contains the original file names
 - log -- Output for logfiles
 - data -- general data needed by woylie


"""

import os
import sys
import os.path
import logging
import enum
import datetime
import json
import requests
from pathlib import Path

# TODO: import multiprocessing # use parallel processing


class Folders(enum.Enum):
    LOG = "log"
    DATA = "data"
    HASH_LIB = "hash-lib"
    BY_CAMERA = "by-camera"
    BY_IMPORT = "by-import"
    BY_TIME = "by-time"
    BY_COUNTRY = "by-country"


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


def extensions():
    #return ('.heic') # for testing
    return ('.ras', '.xwd', '.bmp', '.jpe', '.jpg', '.jpeg', '.xpm',
            '.ief', '.pbm', '.tif', '.gif', '.ppm', '.xbm',
            '.tiff', '.rgb', '.pgm', '.png', '.pnm', '.heic', '.heif')


def get_copy_cmd():
    import platform
    if platform.system() == "Darwin":
        return ["cp", "-c"]
    elif platform.system() == "Windows":
        print("WARN: Windows Support currently not implemented")
        return ["copy"] # Windows Use Junctions or Links?
    else:
        return ["cp", "--reflink=auto"]


def extract_date(exif):
    if MetaInfo.DATETIME_CREATED.value in exif:
        return exif[MetaInfo.DATETIME_CREATED.value]
    elif MetaInfo.DATETIME_ORG.value in exif:
        return exif[MetaInfo.DATETIME_ORG.value]
    elif MetaInfo.DATETIME_GPS.value in exif:
        return exif[MetaInfo.DATETIME_GPS.value]
    else:
        return exif[MetaInfo.DATETIME_FILE_MODIFY.value]

class OSMResolver:


    def __init__(self, file_name):
        if file_name is not None and file_name.trim != "":
            file = open(file_name, 'r')
            self.cache = json.load(file)
        else:
            self.cache = {}

    def resolve_cache(self, lat, lon):
        for key, val in self.cache.items():
            print(key, val)

            # TODO: this could be a lot smarter
            return None

    def resolve(self, lat, lon, mail):
        if lat is not None and lon is not None:
            # https://operations.osmfoundation.org/policies/nominatim/
            js = self.resolve_cache(lat, lon)

            if js is None:
                url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=12&lat=%s&lon=%s' % (lat, lon)
                r = requests.get(url)

                if r.status_code == 200:
                    js = r.json()
                    self.cache.append(js)

            return js

    def cache_write(self, file_name):
        file = open(file_name, "a")
        json.dump(self.cache, file, indent=4)

class PhotoWoylie:
    def __init__(self, base_path, copy_cmd=None, hardlink=True, dump_exif=False):
        self.base_path = base_path

        if copy_cmd is not None:
            self.copy_cmd = copy_cmd
        else:
            self.copy_cmd = get_copy_cmd()

        self.start_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        if dump_exif:
            self.exif_dump = []
        self.dump_exif = dump_exif

        if hardlink:
            self.link_function = os.link
        else:
            self.link_function = os.symlink

        self.bootstrap_directory_structure()

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

    def import_files(self, import_path):

        import_trace = open(os.path.join(self.base_path, Folders.LOG.value, "import-" + self.start_time + ".log"), "a")

        count_imported = 0
        count_existed = 0

        for ext in extensions():
            for filename in Path(import_path).rglob('*' + ext):
                if filename.is_file():
                    print("Reading file %s" % filename, end=' ')
                    try:
                        newfile = self.copyfile(filename)
                        if newfile != "":
                            count_imported += 1

                            import_trace.write("%s\t%s\n" % (os.path.abspath(filename), newfile))

                            self.link_import(newfile, filename)
                            self.link_exif_metadata(newfile)

                            print("✅  Imported")

                        else:
                            print("♻️  Existed")
                            count_existed += 1
                    except Exception:
                        print("❌  Error")
                        raise

        print("found files: %s, cloned files: %s, already existed: %s  "
              % (count_imported+count_existed, count_imported, count_existed) )
        logging.info("found files: %s, cloned files: %s, already existed: %s  "
                     , count_imported+count_existed, count_imported, count_existed)

        if self.dump_exif:
            json_file = open(os.path.join(self.base_path, Folders.LOG.value, "exif-" + self.start_time + ".json"), "a")
            json.dump(self.exif_dump, json_file, indent=4)

    @staticmethod
    def check_call(args, shell=False):
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
            raise RuntimeError("failed to run '%s'" % cmd_str)
        return stdout

    def link_import(self, filename, import_file):
        path = os.path.join(self.base_path, Folders.BY_IMPORT.value, self.start_time)
        if not os.path.exists(path):
            os.mkdir(path)
        head, tail = os.path.split(import_file)
        self.link_function(filename, os.path.join(path, tail))

    def copyfile(self, filename):
        filehash = hashfile(filename)
        file, ext = os.path.splitext(filename)
        newfile = os.path.join(self.base_path, Folders.HASH_LIB.value, filehash[0:1], filehash + ext)

        if not os.path.exists(newfile):
            args = self.copy_cmd + [str(filename), newfile]
            self.check_call(args)
            return newfile
        else:
            return ""

    def link_datetime(self, filename, date_time_str):
        if date_time_str is not None or date_time_str != "":
            # date_time = datetime.datetime.strptime(date_time_str, "%Y:%m:%d %H:%M:%S")
            root, ext = os.path.splitext(filename)
            head, tail = os.path.split(filename)
            path = os.path.join(self.base_path, Folders.BY_TIME.value, date_time_str[0:4], date_time_str[5:7])
            os.makedirs(path, exist_ok=True)

            link_name = os.path.join(path, date_time_str.replace(":", "-") + "_" + tail[0:8] + ext)
            if not os.path.exists(link_name):
                self.link_function(filename, link_name)

    def get_exif(self, filename):
        args = ["exiftool", "-json", "-n", filename]
        mstring = self.check_call(args)
        exif = json.loads(mstring)[0]
        if self.dump_exif:
            self.exif_dump.append(exif)
        return exif

    def link_exif_metadata(self, filename):
        exif = self.get_exif(filename)
        self.link_datetime(filename, extract_date(exif))

    def link_gps(self, exif):

        lat = None
        lon = None
        if "GPSLatitude" in exif and "GPSLongitude" in exif:
            lat = exif["GPSLatitude"]
            lon = exif["GPSLongitude"]
        elif "GPSPosition" in exif:
            gpspos = exif["GPSPosition"].split()
            lat = gpspos[0]
            lon = gpspos[1]

        if lat is not None and lon is not None:
            # https://operations.osmfoundation.org/policies/nominatim/
            url = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=%s&lon=%s' % (lat, lon)
            r = requests.get(url)

            if r.status_code == 200:
                r.json()


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        description='this is the PhotoWoylie tool')

    parser.add_argument(
        '--base-path', '-p',
        metavar='PATH',
        dest='base_path',
        required=True,
        help='PhotoWoylie base path')

    parser.add_argument(
        '--import-path', '-i',
        metavar='PATH',
        dest='import_path',
        required=True,
        help='Add the Pictures to the PhotoWoylie base Path.'
             'Pictures will only be physically copied if across filesystem '
             'or on non reflink possible fs')

    parser.add_argument(
        '--explain',
        help='Explain what %(prog)s does (and stop)',
        action='store_true')

    parser.add_argument(
        '--verbose', '-v',
        help='verbose output',
        action='store_true')

    parser.add_argument(
        '--dump-exif',
        dest='dump_exif',
        help='safe exif information per import into the log directory',
        action='store_true')

    parser.add_argument(
        '--use-symlinks',
        dest='symlink',
        help='use symlinks instead of hardlinks for linking the pictures in the by-xyz folders',
        action='store_true'
    )

    pa = parser.parse_args(argv[1:])

    # safety net if no arguments are given call for help
    if len(sys.argv[1:]) == 0:
        parser.print_help()
        return 0

    if pa.explain:
        sys.stdout.write(__doc__)
        return 0

    if pa.base_path is not None:
        woylie = PhotoWoylie(
            base_path=pa.base_path,
            hardlink=(pa.symlink is None),
            dump_exif=(pa.dump_exif is not None)
        )

        if pa.import_path is not None:
            woylie.import_files(pa.import_path)


if "__main__" == __name__:
    sys.exit(main(sys.argv))
