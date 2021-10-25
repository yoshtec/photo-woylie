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
 - by-location - Locations where Pictures where taken

woylie depends on exiftool for reading metadata: check out https://exiftool.org/#supported

OpenStreetMap Nominatim is used for resolving locations from GPS metadata.
https://nominatim.org/release-docs/develop/api/Reverse/

"""
import base64
import fnmatch
import os
import logging
import enum
import datetime
import json
import shutil

import sqlite_utils
import requests
import subprocess
import hashlib
import platform
from pathlib import Path

# TODO: P1: Set initial File Permissions and ownership straight
# TODO: P3: import multiprocessing # use parallel processing
from woylie import timekeeper

ENC = "utf-8"

EXTENSIONS_PIC = [
    ".ras",
    ".xwd",
    ".bmp",
    ".jpe",
    ".jpg",
    ".jpeg",
    ".xpm",
    ".ief",
    ".pbm",
    ".tif",
    ".tiff",
    ".gif",
    ".ppm",
    ".xbm",
    ".rgb",
    ".pgm",
    ".png",
    ".pnm",
    ".heic",
    ".heif",
]
EXTENSIONS_MOV = [".mov", ".mts", ".mp4", ".m4v"]
EXTENSIONS_RAW = [".raw", ".arw"]

IGNORE_PATH = [".AppleDouble", ".git", ".hg", ".svn", ".bzr"]
IGNORE_FILE_PATTERN = ["._*"]

# Ignore the following Tags from exif metadata:
IGNORE_EXIF_TAGS = [
    "PreviewImage",
    "Directory",
    "FileAccessDate",
    "FileInodeChangeDate",
    "FilePermissions",
    "FileTypeExtension",
    "ExifToolVersion",
    "ExifByteOrder",
    "ProfileDescriptionML*",
]


class Folders(enum.Enum):
    """
    Folders of the library
    """

    LOG = "log"
    DATA = "data"
    HASH_LIB = "hash-lib"
    BY_CAMERA = "by-camera"
    BY_IMPORT = "by-import"
    BY_TIME = "by-time"
    BY_LOCATION = "by-location"


class Files(enum.Enum):
    DATABASE = "metadata.db"
    STOP = ".woylie_stop"
    OSM_CACHE = "osm-cache.json"


class Tables(enum.Enum):
    """
    Constants like table names for interaction with the metadata database
    """

    EXIF = "exif"
    FILES = "files"
    DERIVED_GPS = "derived_gps"
    OSM_CACHE = "osm_cache"


class Columns(enum.Enum):
    """
    Constants for Tag and Column Names
    """

    HASH = "file_hash"
    EXTENSION = "extension"
    IMPORTED_AT = "importedAt"
    IMPORTED = "imported"
    IGNORE = "ignore"
    DELETED = "deleted"
    UTC_TIME = "utc_time"
    ORIGIN_FILE = "origin_file"
    OSM_PLACE_ID = "place_id"


def hash_file(filename):
    """
    Reads a File and returns the sha256 hex digest of the file
    """

    buffer = 65536
    file_hash = hashlib.sha256()

    with open(filename, "r+b") as f:
        while True:
            data = f.read(buffer)
            if not data:
                break
            file_hash.update(data)
    return file_hash.hexdigest()


def check_call(args, ignore_return_code=False):
    """
    execute shell call and return the standard-out
    """

    cmd_str = " ".join(args)
    logging.info("Execute command: '%s' ", cmd_str)
    p = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = p.communicate()
    if stdout:
        logging.debug(stdout)
    if stderr:
        logging.debug(stderr)
    if not ignore_return_code and p.returncode != 0:
        raise RuntimeError("failed to run '%s'" % cmd_str)
    return stdout


class MetadataBase:
    """
    Encapsulates the Database
    """
    class Index(enum.Enum):
        EXIF_UTC_TIME = f"CREATE INDEX exif_utc_time ON {Tables.EXIF.value} (utc_time);"
        EXIF_HASH_FILE = f"CREATE UNIQUE INDEX exif_hash_file ON {Tables.EXIF.value} (file_hash);"
        OSM_BOUNDING_BOX = f"CREATE INDEX osm_bounding_box ON {Tables.OSM_CACHE.value} (b0, b1, b2, b3);"

    def __init__(self, path: Path):
        self.db = sqlite_utils.Database(path)
        self.indexes = list()

    def _check_index(self, index: Index):
        if index not in self.indexes:
            self._check_and_create_index(index)

    def _check_and_create_index(self, index: Index):

        check_sql = f"select count(*) from sqlite_master where name = '{index.member.lower()}' and type='index'"

        exists = False
        for x in self.db.query(check_sql):
            exists = True

        if not exists:
            self.db.query(index.value)

        self.indexes.append(index)

    def add_osm(self, js):
        bb = "boundingbox"
        if js and bb in js:
            js["b0"] = float(js[bb][0])
            js["b1"] = float(js[bb][1])
            js["b2"] = float(js[bb][2])
            js["b3"] = float(js[bb][3])

        self.db[Tables.OSM_CACHE.value].insert_all(
            [js], pk=Columns.OSM_PLACE_ID.value, alter=True, upsert=True
        )

    def osm_cache_resolve(self, lat, lon):
        self._check_index(self.Index.OSM_BOUNDING_BOX)

        sql = f"select * from {Tables.OSM_CACHE.value} where {lat} > b0 AND {lat} < b1 AND {lon} > b2 AND {lon} < b3"

        for x in self.db.query(sql):
            if "address" in x:
                temp = json.loads(x["address"])
                x["address"] = temp
            return x

    def add_origin_data(self, d: dict):
        self.db[Tables.FILES.value].insert_all(
            [d], pk=Columns.HASH.value, upsert=True, alter=True
        )

    def add_exif_data(self, exif: dict):

        for k in exif:
            if isinstance(exif[k], str) and exif[k].startswith("base64:"):
                exif[k] = base64.b64decode(exif[k][7:])

        self.db[Tables.EXIF.value].insert_all(
            [exif],
            pk=Columns.HASH.value,
            batch_size=10,
            alter=True,
        )

    def drop_exif(self):
        self.db[Tables.EXIF.value].drop(ignore=True)
        self.indexes = list()

    def check_exist_or_ignore(self, file_hash: str):
        try:
            item = self.db[Tables.FILES.value].get(file_hash)
            if item[Columns.IMPORTED.value]:
                return 1
            if item[Columns.IGNORE.value]:
                return 2
        except sqlite_utils.db.NotFoundError:
            return 0
        return 3

    def calculate_nearest(self):
        self._check_index(self.Index.EXIF_UTC_TIME)
        for row in self.db[Tables.EXIF.value].rows_where("GPSPosition is null"):
            self.calculate_nearest_for(row)

    def calculate_nearest_for(self, exif):
        sql = (
            "select "
            f" min(abs(strftime('%s','{exif[Columns.UTC_TIME.value]}') "
            f" - strftime('%s', {Columns.UTC_TIME.value}))) as delta_sec,"
            f" file_hash, GPSPosition, GPSLatitude, GPSLongitude, {Columns.UTC_TIME.value}"
            f" from {Tables.EXIF.value} where GPSPosition not NULL;"
        )

        for res in self.db.execute(sql=sql):
            d = {
                Columns.HASH.value: exif[Columns.HASH.value],
                Columns.UTC_TIME.value: exif[Columns.UTC_TIME.value],
                Columns.HASH.value + "_origin": res[1],
                Columns.UTC_TIME.value + "_origin": res[5],
                "delta": res[0],
                "GPSPosition": res[2],
                "GPSLatitude": res[3],
                "GPSLongitude": res[4],
            }

            self.db[Tables.DERIVED_GPS.value].insert_all(
                [d], pk=[Columns.HASH.value], upsert=True, alter=True
            )

            return res[1]


class ExifTool:
    """
    minimal wrapper for exiftool always returns -json strings
    """

    def __init__(self, ignore_tags=None):
        if ignore_tags is None:
            ignore_tags = IGNORE_EXIF_TAGS
        cmd = [
            "exiftool",
            "-stay_open",
            "True",
            "-@",
            "-",
            "-common_args",
            "-json",
            "-n",  # No print conversion
            "-b",  # get binary data starts with "base64:" see https://exiftool.org/forum/index.php?topic=5586.0
            # "-u",  # Find unknown tags
            # "-U",  # also find binary unknown tags
        ]
        for tag in ignore_tags:
            cmd.append(f'--"{tag}"')

        self.cmd = cmd
        self.count = 0

        self._xt = None
        self.load()

    def __del__(self):
        self.close()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute(self, file, find_unknown=False):
        end = b"{ready}"
        self.count += 1
        if self.count % 100 == 0:
            self.load()

        if find_unknown:
            self._xt.stdin.write("\n-u\n-U\n")
        self._xt.stdin.write("\n" + str(file) + "\n-execute\n")
        self._xt.stdin.flush()

        result = b""
        stdout = self._xt.stdout.fileno()
        while not result[-10:].strip().endswith(end):
            result += os.read(stdout, 4096)

        return result.strip()[: -len(end)].decode(ENC)

    def close(self):
        if self._xt is not None:
            self._xt.stdin.write("-stay_open\nFalse\n")
            self._xt.stdin.flush()
            self._xt.communicate()
            # del self._xt

    def load(self):
        self.close()
        self._xt = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding=ENC,
        )


class OSMResolver:
    URL = "https://nominatim.openstreetmap.org/reverse"
    HEADERS = {"user-agent": "photo-woylie"}

    def __init__(self, file_name: Path, mdb: MetadataBase, lang=None):
        print("🗺️  Geo data provided by OpenStreetmap:")
        print("🗺️ -|> © OpenStreetMap contributors")
        print("🗺️ -|> url: https://www.openstreetmap.org/copyright")

        self.lang = lang
        self.file_name = file_name.with_suffix(f".{lang}.json") if lang else file_name
        self.mdb = mdb
        if file_name is not None and file_name.exists():
            file = file_name.open("r")
            self.cache = json.load(file)
            file.close()
        else:
            self.cache = []

    def _resolve_cache(self, lat, lon):
        # TODO: this could be a lot smarter
        for item in self.cache:
            if "boundingbox" in item:
                x = item["boundingbox"]
                if float(x[0]) < float(lat) < float(x[1]) and float(x[2]) < float(
                    lon
                ) < float(x[3]):
                    return item
        return None

    def resolve(self, lat, lon):
        if lat is not None and lon is not None:
            # All requests should be cached: https://operations.osmfoundation.org/policies/nominatim/
            #js = self._resolve_cache(lat, lon)
            js = self.mdb.osm_cache_resolve(float(lat), float(lon))

            # Cache miss
            if js is None:
                # Documentation https://nominatim.org/release-docs/develop/api/Reverse/
                params = {"format": "jsonv2", "zoom": 12, "lat": lat, "lon": lon}
                if self.lang:
                    params["accept-language"] = self.lang

                r = requests.get(self.URL, headers=self.HEADERS, params=params)

                if r.status_code == 200:
                    js = r.json()
                    self.cache.append(js)
                    self.mdb.add_osm(js)

            return js

    def resolve_name(self, lat, lon):
        osmjs = self.resolve(lat, lon)

        if not osmjs:
            print(f"🗺️  Result for OpenStreetMap: lat={lat}, lon={lon}")
            print(f"🗺️  Query result: {osmjs}")
            return Path("Unknown") / Path(f"lat_{lat}_lon_{lon}")

        if "address" in osmjs and "country" in osmjs["address"]:
            if "city" in osmjs["address"]:
                return Path(osmjs["address"]["country"], osmjs["address"]["city"])
            elif "village" in osmjs["address"]:
                return Path(osmjs["address"]["country"], osmjs["address"]["village"])
            elif "municipality" in osmjs["address"]:
                return Path(
                    osmjs["address"]["country"], osmjs["address"]["municipality"]
                )
            elif "town" in osmjs["address"]:
                return Path(osmjs["address"]["country"], osmjs["address"]["town"])
            elif "state" in osmjs["address"]:
                return Path(osmjs["address"]["country"], osmjs["address"]["state"])
            elif "county" in osmjs["address"]:
                return Path(osmjs["address"]["country"], osmjs["address"]["county"])
            else:
                print(f"🗺️  Result for OpenStreetMap: lat={lat}, lon={lon}")
                print(f"🗺️  Query result: {osmjs}")
                return Path(osmjs["address"]["country"]) / Path(f"lat_{lat}_lon_{lon}")
        elif "display_name" in osmjs:
            return Path(osmjs["display_name"])

    def cache_write(self):
        file = self.file_name.open("w")
        json.dump(self.cache, file, indent=4)
        file.close()

    def __del__(self):
        self.cache_write()


class FileImporter:
    def __init__(
        self,
        base_path: Path,
        filename: Path,
        exiftool: ExifTool,
        start_time: str,
        hardlink=True,
        file_hash=None,
    ):
        self.flags = []

        self.exiftool = exiftool
        self.base_path = base_path.absolute()
        self.start_time = start_time

        self.old_file_path = filename
        self.old_file_name = filename.name

        # make the extension lowercase for consistency
        self.ext = filename.suffix.lower()
        self.file_hash = hash_file(filename) if file_hash is None else file_hash

        self.link_function = os.link if hardlink else os.symlink

        self.full_path = (
            self.base_path
            / Folders.HASH_LIB.value
            / self.file_hash[0:1]
            / str(self.file_hash + self.ext)
        )

        self.datetime_filename = None

        self.exif = None
        self.imported = False
        self.ignore = False
        self.deleted = False

    def get_origin(self) -> dict:
        origin = dict()
        origin[Columns.HASH.value] = self.file_hash
        origin[Columns.EXTENSION.value] = self.full_path.suffix

        origin[Columns.IMPORTED_AT.value] = self.start_time if self.imported else None

        origin[Columns.IMPORTED.value] = self.imported
        origin[Columns.IGNORE.value] = self.ignore
        origin[Columns.DELETED.value] = self.deleted

        origin[Columns.ORIGIN_FILE.value] = self.old_file_name

        return origin

    def import_file(self):
        def get_copy_cmd(retry=False):
            if platform.system() == "Darwin":
                return ["cp"] if retry else ["cp", "-c"]
            elif platform.system() == "Windows":
                print("WARN: Windows Support currently not implemented")
                return ["copy"]  # Windows Use Junctions or Links?
            else:
                return ["cp", "--reflink=auto"]

        if not any(self.full_path.parent.glob(self.file_hash + ".*")):
            try:
                check_call(
                    get_copy_cmd() + [str(self.old_file_path), str(self.full_path)]
                )
            except RuntimeError as e:
                check_call(
                    get_copy_cmd(retry=True)
                    + [str(self.old_file_path), str(self.full_path)]
                )

        self.flags.append("#")
        self._load_exif()

        self.imported = True

    def delete_file(self):
        if self.full_path.exists():
            self.flags.append("🗑️")
            self._load_exif()
            self.full_path.unlink()
            self.deleted = True
        self.ignore = True

    def ignore_file(self):
        self.ignore = True
        self.flags.append("I")

    def load_file(self):
        if self.full_path.exists():
            self.flags.append("%")
            self._load_exif()

    def _load_exif(self):
        mstring = self.exiftool.execute(self.full_path)
        self.exif = json.loads(mstring)[0]

        # still necessary for deleting exifTool immanent information
        for tag in list(self.exif):
            for tagp in IGNORE_EXIF_TAGS:
                if fnmatch.fnmatch(tag, tagp):
                    del self.exif[tag]

        self.exif[Columns.HASH.value] = self.file_hash

        tk = timekeeper.TimeKeeper()
        tk.add_all(self.exif)
        self.exif[Columns.UTC_TIME.value] = tk.as_utc_normalized()

        if tk.as_utc_normalized():
            self.datetime_filename = (
                tk.as_utc_normalized()[0:19] + "_" + self.file_hash[0:8] + self.ext
            )
        else:
            self.datetime_filename = "0000-00-00_" + self.file_hash[0:8] + self.ext

        self.imported = True

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
        p = (
            self.base_path
            / Folders.BY_IMPORT.value
            / self.start_time
            / self.old_file_name
        )
        if not self._link(p):
            p = (
                self.base_path
                / Folders.BY_IMPORT.value
                / self.start_time
                / Path(self.old_file_path.parts[-1] + self.old_file_name)
            )
            self._link(p)
        self.flags.append("💾")

    def link_datetime(self):
        self._link(
            self.base_path
            / Folders.BY_TIME.value
            / self.datetime_filename[0:4]
            / self.datetime_filename[5:7]
            / self.datetime_filename
        )
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
            self._link(
                self.base_path
                / Folders.BY_LOCATION.value
                / osmpath
                / self.datetime_filename
            )
            self.flags.append("🌍")

    def link_camera(self):
        name = ""

        if "UserComment" in self.exif and self.exif["UserComment"] == "Screenshot":
            name = "Screenshot"

        if "Make" in self.exif:
            name = self.exif["Make"]

        if "Model" in self.exif:
            name += " " + self.exif["Model"]

        if name != "":
            self._link(
                self.base_path
                / Folders.BY_CAMERA.value
                / name.strip()
                / self.datetime_filename
            )
            self.flags.append("📸")

    def delete_links(self):
        for f in Folders:
            if f.value.startswith("by-"):
                p = self.base_path / f.value
                for file in p.rglob(self.datetime_filename):
                    file.unlink()


class PhotoWoylie:
    def __init__(
        self,
        base_path,
        hardlink=True,
        dump_exif=False,
        lang=None,
        link_date=True,
        link_import=True,
        link_cam=True,
        link_gps=True,
    ):

        self.base_path: Path = Path(base_path)

        self.start_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

        self.exif_dump = []
        self.dump_exif = dump_exif

        self.count_imported = 0
        self.count_existed = 0
        self.count_error = 0
        self.count_scanned = 0
        self.count_deleted = 0
        self.count_ignored = 0

        self.link_import = link_import
        self.link_date = link_date
        self.link_cam = link_cam
        self.link_gps = link_gps

        self.hardlink = hardlink

        self.lang = lang

        self.bootstrap_directory_structure()

        self.mdb = MetadataBase(
            self.base_path / Folders.DATA.value / Files.DATABASE.value
        )

        self.osm = OSMResolver(
            self.base_path / Folders.DATA.value / Files.OSM_CACHE.value,
            mdb=self.mdb,
            lang=lang,
        )

        self.ignore_path = IGNORE_PATH
        self.ignore_file_patterns = IGNORE_FILE_PATTERN
        self.extensions = EXTENSIONS_PIC + EXTENSIONS_RAW + EXTENSIONS_MOV

    def bootstrap_directory_structure(self):
        if not self.base_path.exists():
            self.base_path.mkdir()

        # create a stop file in the base dir so that the dir is not searched.
        self.stop(self.base_path)

        for f in Folders:
            path = self.base_path / f.value
            if not path.exists():
                logging.info(f"Creating path: {path}")
                path.mkdir()

        for f in "0123456789abcdef":
            path = self.base_path / Folders.HASH_LIB.value / f
            if not path.exists():
                logging.info(f"Creating path: {path}")
                path.mkdir()

    def add_extensions(self, extensions):
        for e in extensions:
            if not e.startswith("."):
                self.extensions.append("." + e.lower())
            else:
                self.extensions.append(e.lower())

    def import_files(self, import_path: os.PathLike, recursive: bool = True):

        import_trace = self.base_path.joinpath(
            Folders.LOG.value, f"import-{self.start_time}.log"
        ).open("w")

        exiftool = ExifTool()

        try:
            for file in self.file_digger(Path(import_path), recursive):
                self.import_file(file, import_trace, exiftool)

        except Exception:
            raise
        finally:
            print("-->")
            print(f"ℹ️ scanned files: {self.count_scanned}")
            print(f"ℹ️ cloned files: {self.count_imported}")
            print(f"ℹ️ already existed: {self.count_existed}")
            print(f"ℹ️ ignored: {self.count_ignored}")
            print(f"ℹ️ files with errors: {self.count_error}")
            logging.info(
                f"found files: {self.count_scanned}, "
                f"cloned files: { self.count_imported}, "
                f"already existed: {self.count_existed}"
                f"ignored: {self.count_ignored}"
            )

            if self.dump_exif:
                json_file = self.base_path.joinpath(
                    Folders.LOG.value, f"exif-{self.start_time}.json"
                ).open("w")
                json.dump(self.exif_dump, json_file, indent=4)

            self.osm.cache_write()
            del exiftool

    def remove_files(self, delete_path: os.PathLike, recursive: bool = True):
        delete_trace = self.base_path.joinpath(
            Folders.LOG.value, f"delete-{self.start_time}.log"
        ).open("w")

        exiftool = ExifTool()

        try:
            for file in self.file_digger(Path(delete_path), recursive):
                self.remove_file(file, delete_trace, exiftool)
        except Exception:
            raise
        finally:
            print("-->")
            print(f"ℹ️ scanned files: {self.count_scanned}")
            print(f"ℹ️ removed files: {self.count_deleted}")
            print(f"ℹ️ files with errors: {self.count_error}")
            del exiftool

    def rebuild(self, reset=False):
        rebuild_trace = self.base_path.joinpath(
            Folders.LOG.value, f"rebuild-{self.start_time}.log"
        ).open("w")

        # delete by- folders
        for folder in [
            Folders.BY_CAMERA.value,
            Folders.BY_TIME.value,
            Folders.BY_LOCATION.value,
        ]:
            f = self.base_path / folder
            rebuild_trace.write(f"deleting folder: {f}")
            print(f"deleting folder: {f}")
            shutil.rmtree(f, ignore_errors=True)
            f.mkdir()

        if reset:
            dbfile = self.base_path / Folders.DATA.value / Files.DATABASE.value
            dbfile.unlink()
            self.mdb = MetadataBase(dbfile)
            self.osm.mdb = self.mdb
        else:
            rebuild_trace.write(f"dropping table: {Tables.EXIF.value}")
            print(f"dropping table: {Tables.EXIF.value}")
            self.mdb.drop_exif()

        exiftool = ExifTool()
        # go through all files in hash-lib
        for h in "0123456789abcdef":
            path = self.base_path / Folders.HASH_LIB.value / h
            for p in path.iterdir():
                self.rebuild_file(p, exiftool=exiftool, trace=rebuild_trace)

    def file_digger(self, path: Path, recursive: bool = True):
        if not path.exists():
            pass  # ignore nonexisting paths and files
        elif path.is_dir():
            stop_file = path.joinpath(Files.STOP.value)  # stop if there is a stop file
            if stop_file.exists():
                print(f"⏸️ Found a stop-file in: {stop_file}")
            elif path.parts[-1] in self.ignore_path:
                print(f"⏸️ ignoring path: {path}")
            else:
                for p in path.iterdir():
                    yield from self.file_digger(p, recursive)
        elif (
            path.is_file()
            and path.suffix.lower() in self.extensions
            and not self.ignore_file(path.name)
        ):
            yield path

    def ignore_file(self, file: str) -> bool:
        for ignore_pattern in self.ignore_file_patterns:
            if fnmatch.fnmatch(file, ignore_pattern):
                return True
        return False

    def remove_file(self, filename: Path, trace, exiftool: ExifTool):
        try:
            print(f"▶️ File: {filename}", end=" ")
            trace.write("%s\t" % filename.absolute())

            fi = FileImporter(
                self.base_path,
                filename,
                exiftool=exiftool,
                start_time=self.start_time,
                hardlink=self.hardlink,
            )

            self.count_scanned += 1

            fi.delete_file()

            self.mdb.add_origin_data(fi.get_origin())

            if fi.deleted:
                self.count_deleted += 1

                trace.write("%s\t" % fi.full_path)

                fi.delete_links()

                trace.write("🗑️  Removed!\t%s\n" % fi.flags)
                print("🗑️  Removed: ", fi.flags)

            else:
                trace.write("\t🏳️ not existing\n")
                print("🏳️️ not Existed")

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
            print("▶️ File:", filename, end=" ")
            trace.write("%s\t" % filename.absolute())

            fi = FileImporter(
                self.base_path,
                filename,
                exiftool=exiftool,
                start_time=self.start_time,
                hardlink=self.hardlink,
            )

            self.count_scanned += 1

            status = self.mdb.check_exist_or_ignore(fi.file_hash)
            if status == 0:
                fi.import_file()

                # if fi.imported:
                self.count_imported += 1

                trace.write("%s\t" % fi.full_path)

                if self.link_import:
                    fi.link_import()

                self._link_standards(fi)

                self.mdb.add_origin_data(fi.get_origin())

                self._save_exif(fi)

                trace.write("✅OK!\t%s\n" % fi.flags)
                print("✅  Imported: ", fi.flags)

            elif status == 1:
                self.count_existed += 1
                trace.write("\t♻️ Existed\n")
                print("♻️  Existed ")
            else:
                self.count_ignored += 1
                trace.write("\t💤 Ignored\n")
                print("💤 Ignored ")

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
            print("▶️ File:", filename, end=" ")
            trace.write("%s\t" % filename.absolute())

            fi = FileImporter(
                self.base_path,
                filename,
                exiftool=exiftool,
                start_time=self.start_time,
                hardlink=self.hardlink,
                file_hash=filename.stem,
            )

            self.count_scanned += 1

            fi.load_file()

            trace.write("%s\t" % fi.full_path)

            self._link_standards(fi)

            self._save_exif(fi)

            trace.write("✅ OK!\t%s\n" % fi.flags)
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

    def _save_exif(self, fi):
        if self.dump_exif:
            self.exif_dump.append(fi.exif)

        self.mdb.add_exif_data(fi.exif)

    def _link_standards(self, fi):
        if self.link_date:
            fi.link_datetime()
        if self.link_cam:
            fi.link_camera()
        if self.link_gps:
            fi.link_gps(self.osm)

    @classmethod
    def stop(cls, path):
        p = Path(path)
        if p.name != Files.STOP.value:
            p = p / Files.STOP.value
            if not p.exists():
                p.touch(exist_ok=True)
                print(f"created Stop File: {p.absolute()}")

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

    @classmethod
    def check_prerequisites(cls):
        import shutil

        if not shutil.which("exiftool"):
            return False
