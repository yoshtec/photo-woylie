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
    BY_LOCATION = "by-location"


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
    URL = 'https://nominatim.openstreetmap.org/reverse?format=jsonv2&zoom=12&lat=%s&lon=%s'

    def __init__(self, file_name):
        print("Geo data provided by OpenStreetmap:")
        print("-|> © OpenStreetMap contributors")
        print("-|> url: https://www.openstreetmap.org/copyright")

        self.file_name = file_name
        if file_name is not None and os.path.exists(file_name):
            file = open(file_name, 'r')
            self.cache = json.load(file)
            file.close()
        else:
            self.cache = []

    def _resolve_cache(self, lat, lon):

        # TODO: this could be a lot smarter
        for item in self.cache:

            x = item['boundingbox']
            # print("lat, lon, array", lat, lon, x)
            # 'boundingbox': ['28.4793827', '28.6129197', '77.2054109', '77.346601']
            # south Latitude, north Latitude, west Longitude, east Longitude

            if float(x[0]) < float(lat) < float(x[1]) and float(x[2]) < float(lon) < float(x[3]):
                return item

        return None

    def resolve(self, lat, lon):
        if lat is not None and lon is not None:
            # https://operations.osmfoundation.org/policies/nominatim/
            js = self._resolve_cache(lat, lon)

            # Cache miss
            if js is None:
                url = self.URL % (lat, lon)
                r = requests.get(url)

                if r.status_code == 200:
                    js = r.json()
                    self.cache.append(js)

            return js

    def resolve_name(self, lat, lon):
        osmjs = self.resolve(lat, lon)
        #print(osmjs)

        if osmjs:
            if 'address' in osmjs and 'country' in osmjs['address']:
                if 'city' in osmjs['address']:
                    return os.path.join(osmjs['address']['country'], osmjs['address']['city'])
                elif 'town' in osmjs['address']:
                    return os.path.join(osmjs['address']['country'], osmjs['address']['town'])
                elif 'state' in osmjs['address']:
                    return os.path.join(osmjs['address']['country'], osmjs['address']['state'])
                elif 'county' in osmjs:
                    return os.path.join(osmjs['address']['country'], osmjs['address']['county'])
                else:
                    os.path.join(osmjs['address']['country'])
            elif 'display_name' in osmjs:
                return os.path.join(osmjs['display_name'])

        print(osmjs)
        return os.path.join("Unknown")

    def cache_write(self):
        file = open(self.file_name, "w")
        json.dump(self.cache, file, indent=4)
        file.close()


class PhotoWoylie:

    def __init__(self, base_path, copy_cmd=None, hardlink=True, dump_exif=False):
        self.base_path = base_path

        self.copy_cmd = copy_cmd if copy_cmd else get_copy_cmd()

        self.start_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        if dump_exif:
            self.exif_dump = []
        self.dump_exif = dump_exif

        self.hardlink = hardlink

        self.bootstrap_directory_structure()

        self.osm = OSMResolver(os.path.join(self.base_path, Folders.DATA.value, "osm-cache.json"))

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
                        fi = self.FileImporter(
                            self.base_path, filename,
                            copy_cmd=self.copy_cmd,
                            start_time=self.start_time,
                            hardlink=self.hardlink)

                        if fi.imported:
                            count_imported += 1

                            import_trace.write("%s\t%s\n" % (os.path.abspath(filename), fi.full_path))

                            fi.link_import()
                            fi.link_gps(self.osm)
                            fi.link_datetime()
                            fi.link_camera()

                            if self.dump_exif:
                                self.exif_dump.append(fi.get_exif())

                            print("✅  Imported: ", fi.flags)

                        else:
                            count_existed += 1
                            print("♻️  Existed ")
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

        self.osm.cache_write()

    class FileImporter:

        def __init__(self, base_path, filename, copy_cmd, start_time, hardlink=True):
            self.flags = []

            self.base_path = base_path
            self.start_time = start_time

            self.old_file_path = filename
            head, self.old_file_name = os.path.split(filename)
            file, self.ext = os.path.splitext(filename)
            self.file_hash = hashfile(filename)

            self.link_function = os.link if hardlink else os.symlink
            self.copy_cmd = copy_cmd if copy_cmd else get_copy_cmd()

            self.full_path = os.path.abspath(
                os.path.join(
                    self.base_path, Folders.HASH_LIB.value, self.file_hash[0:1], self.file_hash + self.ext
                )
            )

            if not os.path.exists(self.full_path):
                check_call(self.copy_cmd + [str(self.old_file_path), self.full_path])

                self.flags.append("#")
                mstring = check_call(["exiftool", "-json", "-n", self.full_path])
                self.exif = json.loads(mstring)[0]
                self.datetime_filename = \
                    extract_date(self.exif).replace(":", "-").replace(" ", "_") + "_" + self.file_hash[0:8] + self.ext

                self.imported = True
            else:
                self.imported = False

        def link_import(self):
            path = os.path.join(self.base_path, Folders.BY_IMPORT.value, self.start_time)
            os.makedirs(path, exist_ok=True)
            self.link_function(self.full_path, os.path.join(path, self.old_file_name))
            self.flags.append("💾")

        def link_datetime(self):
            path = os.path.join(
                self.base_path, Folders.BY_TIME.value, self.datetime_filename[0:4], self.datetime_filename[5:7])
            os.makedirs(path, exist_ok=True)
            self.link_function(self.full_path, os.path.join(path, self.datetime_filename))
            self.flags.append("🕘")

        def get_exif(self):
            return self.exif

        def link_gps(self, osm: OSMResolver):
            lat = None
            lon = None
            if "GPSLatitude" in self.exif and "GPSLongitude" in self.exif:
                lat = self.exif["GPSLatitude"]
                lon = self.exif["GPSLongitude"]
            elif "GPSPosition" in self.exif:
                gpspos = self.exif["GPSPosition"].split()
                lat = gpspos[0]
                lon = gpspos[1]

            if lat is not None and lon is not None:
                osmpath = osm.resolve_name(lat, lon)
                path = os.path.join(self.base_path, Folders.BY_LOCATION.value, osmpath)
                os.makedirs(path, exist_ok=True)
                self.link_function(self.full_path, os.path.join(path, self.datetime_filename))
                self.flags.append("🌍")

        def link_camera(self):
            name = ""

            if 'Comment' in self.exif and self.exif['Comment'] == "Screenshot":
                name = "Screenshot"

            if 'Make' in self.exif:
                name = self.exif['Make']

            if 'Model' in self.exif:
                name += " " + self.exif['Model']

            print(name)
            if name != "":
                path = os.path.join(self.base_path, Folders.BY_CAMERA.value, name)
                os.makedirs(path, exist_ok=True)
                self.link_function(self.full_path, os.path.join(path, self.datetime_filename))
                self.flags.append("📸")

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
