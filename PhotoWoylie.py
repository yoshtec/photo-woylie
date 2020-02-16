#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

"""
PhotoWoylie (short woylie) is a script for organizing your photos.

It works best with CoW File Systems like btrfs, xfs, apfs. Woylie will try to use reflinks for
importing photos and movies.

Folders:
 - hash-lib - Folder for all files ordered after sha256 hash
 - data -- general data needed by woylie, e.g. OpenStreetMap cache.
 - log - Output for logfiles
  Photos will be sorted into:
 - by-time - Photos linked after the Year and time
 - by-camera - Photos sorted after the camera model.
 - by-import - Photos by import run - contains the original file names

woylie depends on exiftool for reading metadata: check out https://exiftool.org/#supported

OpenStreetMap Nominatim is used for resolving locations from GPS metadata.
https://nominatim.org/release-docs/develop/api/Reverse/

"""

import os
import sys
import logging
import enum
import datetime
import json
import requests
import subprocess
from pathlib import Path

# TODO: import multiprocessing # and use parallel processing

STOP_FILE = ".woylie_stop"

EXTENSIONS_PIC = ['.ras', '.xwd', '.bmp', '.jpe', '.jpg', '.jpeg', '.xpm', '.ief', '.pbm', '.tif', '.tiff', '.gif',
                  '.ppm', '.xbm', '.rgb', '.pgm', '.png', '.pnm', '.heic', '.heif']
EXTENSIONS_MOV = ['.mov', '.mts', '.mp4', '.m4v']
EXTENSIONS_RAW = ['.raw', '.arw']

IGNORE_PATH = ['.AppleDouble', '.git', '.hg', '.svn', '.bzr']


class Folders(enum.Enum):
    LOG = "log"
    DATA = "data"
    HASH_LIB = "hash-lib"
    BY_CAMERA = "by-camera"
    BY_IMPORT = "by-import"
    BY_TIME = "by-time"
    BY_LOCATION = "by-location"


class ExifDateTime(enum.Enum):
    DATETIME_ORG = "DateTimeOriginal"
    DATETIME_CREATED = "CreateDate"
    DATETIME_GPS = "GPSDateTime"
    DATETIME_MOD = "ModifyDate"
    DATETIME_SONY = "SonyDateTime"
    DATETIME_FILE_MODIFY = "FileModifyDate"


def hash_file(filename):
    """
    Reads a File and returns the sha256 hex digest of the file
    """

    import hashlib
    buffer = 65536
    file_hash = hashlib.sha256()

    with open(filename, 'r+b') as f:
        while True:
            data = f.read(buffer)
            if not data:
                break
            file_hash.update(data)
    return file_hash.hexdigest()


def check_call(args, ignore_return_code=False):
    cmd_str = " ".join(args)
    logging.info("Execute command: '%s' ", cmd_str)
    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True)
    stdout, stderr = p.communicate()
    if stdout:
        logging.debug(stdout)
    if stderr:
        logging.debug(stderr)
    if not ignore_return_code and p.returncode != 0:
        raise RuntimeError("failed to run '%s'" % cmd_str)
    return stdout


def get_copy_cmd():
    import platform
    if platform.system() == "Darwin":
        return ["cp", "-c"]
    elif platform.system() == "Windows":
        print("WARN: Windows Support currently not implemented")
        return ["copy"]  # Windows Use Junctions or Links?
    else:
        return ["cp", "--reflink=auto"]


class OSMResolver:
    URL = 'https://nominatim.openstreetmap.org/reverse'

    def __init__(self, file_name: Path, lang=None):
        print("🗺️  Geo data provided by OpenStreetmap:")
        print("🗺️ -|> © OpenStreetMap contributors")
        print("🗺️ -|> url: https://www.openstreetmap.org/copyright")

        self.lang = lang
        self.file_name = file_name.with_suffix("." + lang + ".json") if lang else file_name
        if file_name is not None and file_name.exists():
            file = file_name.open('r')
            self.cache = json.load(file)
            file.close()
        else:
            self.cache = []

    def _resolve_cache(self, lat, lon):
        # TODO: this could be a lot smarter
        for item in self.cache:
            if 'boundingbox' in item:
                x = item['boundingbox']
                if float(x[0]) < float(lat) < float(x[1]) and float(x[2]) < float(lon) < float(x[3]):
                    return item
        return None

    def resolve(self, lat, lon):
        if lat is not None and lon is not None:
            # https://operations.osmfoundation.org/policies/nominatim/
            js = self._resolve_cache(lat, lon)

            # Cache miss
            if js is None:
                # https://nominatim.org/release-docs/develop/api/Reverse/
                params = {'format': 'jsonv2', 'zoom': 12, 'lat': lat, 'lon': lon}
                if self.lang:
                    params['accept-language'] = self.lang

                r = requests.get(self.URL, params)

                if r.status_code == 200:
                    js = r.json()
                    self.cache.append(js)

            return js

    def resolve_name(self, lat, lon):
        osmjs = self.resolve(lat, lon)

        if osmjs:
            if 'address' in osmjs and 'country' in osmjs['address']:
                if 'city' in osmjs['address']:
                    return Path(osmjs['address']['country'], osmjs['address']['city'])
                elif 'town' in osmjs['address']:
                    return Path(osmjs['address']['country'], osmjs['address']['town'])
                elif 'state' in osmjs['address']:
                    return Path(osmjs['address']['country'], osmjs['address']['state'])
                elif 'county' in osmjs['address']:
                    return Path(osmjs['address']['country'], osmjs['address']['county'])
                else:
                    Path(osmjs['address']['country'])
            elif 'display_name' in osmjs:
                return Path(osmjs['display_name'])

        print("🗺️  Result for OpenStreetMap: lat, lon ", lat, lon)
        print("🗺️  Query result: ", osmjs)
        return Path("Unknown")

    def cache_write(self):
        file = self.file_name.open("w")
        json.dump(self.cache, file, indent=4)
        file.close()


class ExifTool:
    """ minimal wrapper for exiftool
    always returns -json strings
    """
    ENC = "utf-8"

    def __init__(self):
        cmd = ['exiftool', '-stay_open', 'True', '-@', '-', "-common_args", "-json", "-n"]
        self._xt = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=self.ENC)

    def __del__(self):
        self.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute(self, file):
        end = b"{ready}"

        self._xt.stdin.write("\n" + str(file) + "\n-execute\n")
        self._xt.stdin.flush()

        result = b""
        stdout = self._xt.stdout.fileno()
        while not result[-10:].strip().endswith(end):
            result += os.read(stdout, 4096)
        return result.strip()[:-len(end)].decode(self.ENC)

    def close(self):
        if self._xt is not None:
            self._xt.stdin.write("-stay_open\nFalse\n")
            self._xt.stdin.flush()
            self._xt.communicate()
            del self._xt


class PhotoWoylie:

    def __init__(self, base_path, copy_cmd=None, hardlink=True, dump_exif=False, lang=None,
                 link_date=True, link_import=True, link_cam=True, link_gps=True):

        self.base_path: Path = Path(base_path)

        self.copy_cmd = copy_cmd if copy_cmd else get_copy_cmd()

        self.start_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        if dump_exif:
            self.exif_dump = []
        self.dump_exif = dump_exif

        self.count_imported = 0
        self.count_existed = 0
        self.count_error = 0
        self.count_scanned = 0
        self.count_deleted = 0

        self.link_import = link_import
        self.link_date = link_date
        self.link_cam = link_cam
        self.link_gps = link_gps

        self.hardlink = hardlink

        self.bootstrap_directory_structure()

        self.osm = OSMResolver(self.base_path / Folders.DATA.value / "osm-cache.json", lang=lang)

        self.ignore_path = IGNORE_PATH
        self.extensions = EXTENSIONS_PIC + EXTENSIONS_RAW + EXTENSIONS_MOV

    def add_extensions(self, exts):
        for e in exts:
            if not e.startswith("."):
                self.extensions.append("." + e.lower())
            else:
                self.extensions.append(e.lower())

    def bootstrap_directory_structure(self):
        if not self.base_path.exists():
            self.base_path.mkdir()

        # create a stop file in the base dir so that the dir is not searched.
        self.stop(self.base_path)

        for f in Folders:
            path = self.base_path / f.value
            if not path.exists():
                logging.info("Creating path: %s ", path)
                path.mkdir()

        for f in "0123456789abcdef":
            path = self.base_path / Folders.HASH_LIB.value / f
            if not path.exists():
                logging.info("Creating path: %s ", path)
                path.mkdir()

    def import_files(self, import_path: os.PathLike, recursive: bool = True):

        import_trace = self.base_path.joinpath(Folders.LOG.value, "import-" + self.start_time + ".log").open("w")

        exiftool = ExifTool()

        try:
            for file in self.file_digger(Path(import_path), recursive):
                self.import_file(file, import_trace, exiftool)
        except Exception:
            raise
        finally:
            print("-->")
            print("ℹ️ scanned files: %s" % (self.count_imported + self.count_existed + self.count_error))
            print("ℹ️ cloned files: %s" % self.count_imported)
            print("ℹ️ already existed: %s" % self.count_existed)
            print("ℹ️ files with errors: %s" % self.count_error)
            logging.info("found files: %s, cloned files: %s, already existed: %s  ",
                         self.count_imported + self.count_existed, self.count_imported, self.count_existed)

            if self.dump_exif:
                json_file = self.base_path.joinpath(Folders.LOG.value, "exif-" + self.start_time + ".json").open("w")
                json.dump(self.exif_dump, json_file, indent=4)

            self.osm.cache_write()
            del exiftool

    def remove_files(self, delete_path: os.PathLike, recursive: bool = True):
        delete_trace = self.base_path.joinpath(Folders.LOG.value, "delete-" + self.start_time + ".log").open("w")

        exiftool = ExifTool()

        try:
            for file in self.file_digger(Path(delete_path), recursive):
                self.remove_file(file, delete_trace, exiftool)
        except Exception:
            raise
        finally:
            print("-->")
            print("ℹ️ scanned files: %s" % self.count_scanned)
            print("ℹ️ removed files: %s" % self.count_deleted)
            print("ℹ️ files with errors: %s" % self.count_error)
            del exiftool

    def rebuild(self):
        # TODO

        # delete by- folders
        for folder in [Folders.BY_CAMERA.value, Folders.BY_TIME.value, Folders.BY_LOCATION.value]:
            f = self.base_path / folder
            f.rmdir()
            f.mkdir()

        exiftool = ExifTool()
        # go through all files in hash-lib
        for h in "0123456789abcdef":
            path = self.base_path / Folders.HASH_LIB.value / h
            for p in path.iterdir():
                self.rebuild_file(0)

    def file_digger(self, path: Path, recursive: bool = True):
        stop_file = path.joinpath(STOP_FILE)  # stop if there is a stop file
        if stop_file.exists():
            print("⏸️ Found a stop-file in: ", stop_file)
        elif path.parts[-1] in self.ignore_path:
            print("⏸️ ignoring path: ", path)
        elif path.exists() and path.is_dir():
            for p in path.iterdir():
                if p.is_file() and p.suffix.lower() in self.extensions:
                    yield p

                if p.is_dir() and recursive:
                    yield from self.file_digger(p, recursive)

    def remove_file(self, filename: Path, trace, exiftool: ExifTool):
        try:
            print("▶️ File:", filename, end=' ')
            trace.write("%s\t" % filename.absolute())

            fi = self.FileImporter(
                self.base_path, filename,
                exiftool=exiftool,
                copy_cmd=self.copy_cmd,
                start_time=self.start_time,
                hardlink=self.hardlink)

            self.count_scanned += 1

            fi.delete_file()

            if fi.deleted:
                self.count_deleted += 1

                trace.write("%s\t" % fi.full_path)

                fi.delete_links()

                trace.write("Removed!\t%s\n" % fi.flags)
                print("  Removed: ", fi.flags)

            else:
                trace.write("\t♻️ not existing\n")
                print("♻️  Existed ")

        except (RuntimeError, PermissionError) as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
        except Exception as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
            raise

    def import_file(self, filename: Path, trace, exiftool: ExifTool):
        try:
            print("▶️ File:", filename, end=' ')
            trace.write("%s\t" % filename.absolute())

            fi = self.FileImporter(
                self.base_path, filename,
                exiftool=exiftool,
                copy_cmd=self.copy_cmd,
                start_time=self.start_time,
                hardlink=self.hardlink)

            self.count_scanned += 1

            fi.import_file()

            if fi.imported:
                self.count_imported += 1

                trace.write("%s\t" % fi.full_path)

                if self.link_import:
                    fi.link_import()
                if self.link_date:
                    fi.link_datetime()
                if self.link_cam:
                    fi.link_camera()
                if self.link_gps:
                    fi.link_gps(self.osm)

                if self.dump_exif:
                    self.exif_dump.append(fi.exif)

                trace.write("✅OK!\t%s\n" % fi.flags)
                print("✅  Imported: ", fi.flags)

            else:
                self.count_existed += 1
                trace.write("\t♻️ Existed\n")
                print("♻️  Existed ")
        except (RuntimeError, PermissionError) as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
        except Exception as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
            raise

    def rebuild_file(self, filename: Path, trace, exiftool: ExifTool):
        try:
            print("▶️ File:", filename, end=' ')
            trace.write("%s\t" % filename.absolute())

            fi = self.FileImporter(
                self.base_path, filename,
                exiftool=exiftool,
                copy_cmd=self.copy_cmd,
                start_time=self.start_time,
                hardlink=self.hardlink)

            self.count_scanned += 1

            fi.load_file()

            trace.write("%s\t" % fi.full_path)

            if self.link_date:
                fi.link_datetime()
            if self.link_cam:
                fi.link_camera()
            if self.link_gps:
                fi.link_gps(self.osm)

            if self.dump_exif:
                self.exif_dump.append(fi.exif)

            trace.write("✅OK!\t%s\n" % fi.flags)
            print("✅  Rebuild: ", fi.flags)

        except (RuntimeError, PermissionError) as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
        except Exception as e:
            trace.write("❌ERROR %s\n\n" % e)
            self.count_error += 1
            print("❌  Error")
            raise

    class FileImporter:
        def __init__(self, base_path: Path, filename: Path, copy_cmd, exiftool: ExifTool, start_time: str, hardlink=True):
            self.flags = []

            self.exiftool = exiftool
            self.base_path = base_path.absolute()
            self.start_time = start_time

            self.old_file_path = filename
            self.old_file_name = filename.name
            self.ext = filename.suffix.lower()  # make the extension lowercase for consistency

            self.file_hash = hash_file(filename)

            self.link_function = os.link if hardlink else os.symlink
            self.copy_cmd = copy_cmd if copy_cmd else get_copy_cmd()

            self.full_path = self.base_path / Folders.HASH_LIB.value / self.file_hash[0:1] / \
                             str(self.file_hash + self.ext)

            # TODO: sanity check
            self.datetime_filename = None
            self.exif = None
            self.imported = False

            self.deleted = False

        def import_file(self):
            if not any(self.full_path.parent.glob(self.file_hash + ".*")):
                check_call(self.copy_cmd + [str(self.old_file_path), str(self.full_path)])

                self.flags.append("#")
                self._load_exif()
                self.imported = True

        def delete_file(self):
            if self.full_path.exists():
                self.flags.append("-")
                self._load_exif()
                self.full_path.unlink()
                self.deleted = True

        def load_file(self):
            if self.full_path.exists():
                self.flags.append("%")
                self._load_exif()

        def _load_exif(self):
            mstring = self.exiftool.execute(self.full_path)
            self.exif = json.loads(mstring)[0]

            self.datetime_filename = self.extract_date().replace(":", "-").replace(" ", "_")[0:19] \
                                     + "_" + self.file_hash[0:8] + self.ext

        def _link(self, link_name: Path):
            if self.deleted:  # essentially unlinking again deleted files
                if link_name.exists():
                    link_name.unlink()
                    return True
                return False
            else:
                link_name.parent.mkdir(parents=True, exist_ok=True)
                if not link_name.exists():
                    self.link_function(self.full_path, link_name)
                    return True
                return False

        def link_import(self):
            p = self.base_path / Folders.BY_IMPORT.value / self.start_time / self.old_file_name
            if not self._link(p):
                p = self.base_path / Folders.BY_IMPORT.value / self.start_time / \
                   Path(self.old_file_path.parts[-1] + self.old_file_name)
                self._link(p)
            self.flags.append("💾")

        def link_datetime(self):
            self._link(self.base_path / Folders.BY_TIME.value / self.datetime_filename[0:4] /
                       self.datetime_filename[5:7] / self.datetime_filename)
            self.flags.append("🕘")

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
                self._link(self.base_path / Folders.BY_LOCATION.value / osmpath / self.datetime_filename)
                self.flags.append("🌍")

        def link_camera(self):
            name = ""
            if 'UserComment' in self.exif and self.exif['UserComment'] == "Screenshot":
                name = "Screenshot"
            if 'Make' in self.exif:
                name = self.exif['Make']
            if 'Model' in self.exif:
                name += " " + self.exif['Model']
            if name != "":
                self._link(self.base_path / Folders.BY_CAMERA.value / name.strip() / self.datetime_filename)
                self.flags.append("📸")

        def extract_date(self):
            for dt in ExifDateTime:
                if dt.value in self.exif:
                    return self.exif[dt.value]

        def delete_links(self):
            for f in Folders:
                if f.value.startswith('by-'):
                    p = self.base_path / f.value
                    for file in p.rglob(self.datetime_filename):
                        #file.unlink()
                        print("would delete: ", file)

    @classmethod
    def stop(cls, path):
        p = Path(path)
        if p.name != STOP_FILE:
            p = p / STOP_FILE
            if not p.exists():
                p.touch(exist_ok=True)
                print("created Stop File:", p)

    @classmethod
    def show_extensions(cls):
        print("The following extensions are build in:")

        print("Pictures:")
        print("* " + " ".join(sorted(EXTENSIONS_PIC)))

        print("Raw Formats:")
        print("* " + " ".join(sorted(EXTENSIONS_RAW)))

        print("Movie Formats:")
        print("* " + " ".join(sorted(EXTENSIONS_MOV)))

        print("Ignoring Paths containing the following parts:")
        print("* " + " ".join(sorted(IGNORE_PATH)))


def main(argv):
    import argparse

    parser = argparse.ArgumentParser(
        description='this is the PhotoWoylie tool! Organize your photos with metadata into subfolders')

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument(
        '--base-path', '-b',
        metavar='PATH',
        dest='base_path',
        required=True,
        help='woylie base path: all pictures and data is stored there')

    subparsers = parser.add_subparsers(description="test desc", title="Sub commands", dest="command")
    parser_import = subparsers.add_parser(
        'import', help='import files to to library in base path', parents=[common_parser])
    parser_rebuild = subparsers.add_parser(
        'rebuild',
        help='relink all by-folders (except by-import), this might be helpful if some options where wrongly set')
    parser_remove = subparsers.add_parser(
        'remove',
        help='remove files that are were imported to the woylie lib')
    parser_info = subparsers.add_parser(
        'info',
        help='print information about woylie and its dependencies'
    )

    parser_import.add_argument(
        '--import-path', '-i',
        metavar='PATH',
        dest='import_path',
        nargs='+',
        help='Add the Pictures to the PhotoWoylie base Path.'
             'Pictures will only be physically copied if across filesystem '
             'or on non reflink possible fs')

    parser_import.add_argument(
        '--dump-exif', '-d',
        dest='dump_exif',
        help='save exif information per import into the log directory',
        action='store_true')

    parser_import.add_argument(
        '--use-symlinks', '-s',
        dest='symlink',
        help='use symlinks instead of hardlinks for linking the pictures in the by-XYZ folders',
        action='store_true'
    )

    parser_import.add_argument(
        '--language', '-l',
        dest='lang',
        metavar='LANG',
        help='browser language code for request to OpenStreetMap. Defaults to local language of OSM'
    )

    parser_import.add_argument(
        '--include-extensions', '-e',
        nargs='+',
        dest='add_ext',
        help='add extensions to include',
        metavar='.ext'
    )

    pa = parser.parse_args(argv[1:])

    # safety net if no arguments are given call for help
    if len(sys.argv[1:]) == 0:
        parser.print_help()
        return 0

    if pa.command == 'info':
        sys.stdout.write(__doc__)

        PhotoWoylie.show_extensions()
        print("")
        parser.print_help()
        return 0

    #if pa.stop:
    #    for path in pa.stop:
    #        PhotoWoylie.stop(path)

    if pa.command == 'import':
        if pa.base_path:
            woylie = PhotoWoylie(
                base_path=pa.base_path,
                hardlink=not pa.symlink,
                dump_exif=pa.dump_exif,
                lang=pa.lang
            )
            if pa.add_ext:
                woylie.add_extensions(pa.add_ext)

            for path in pa.import_path:
                woylie.import_files(path)

    if pa.command == 'remove':
        if pa.base_path:
            woylie = PhotoWoylie(
                base_path=pa.base_path,
                hardlink=not pa.symlink,
                dump_exif=pa.dump_exif,
                lang=pa.lang
            )
            for path in pa.remove_path:
                woylie.remove_files(path)

    if pa.rebuild == 'rebuild':
        if pa.base_path:
            woylie = PhotoWoylie(
                base_path=pa.base_path,
                hardlink=not pa.symlink,
                dump_exif=pa.dump_exif,
                lang=pa.lang
            )
            woylie.rebuild()

    return 0


if "__main__" == __name__:
    sys.exit(main(sys.argv))
