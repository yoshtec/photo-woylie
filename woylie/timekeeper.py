#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import datetime
from time import strptime

UTC = datetime.timezone(datetime.timedelta(0), name="UTC")

TIMESTR = "%Y:%m:%d %H:%M:%S"


class ExifDateTimeType:
    def __init__(self, name: str, utctime: bool = False, rank: int = 0):
        self.name = name
        self.utctime = utctime
        self.rank = rank

    def better(self, etd: "ExifDateTimeType"):
        return self.rank > etd.rank if etd is not None else True

    def __lt__(self, other: "ExifDateTimeType"):
        return self.rank < other.rank if other is not None else False

    def __gt__(self, other: "ExifDateTimeType"):
        return self.rank > other.rank if other is not None else False

    def __le__(self, other: "ExifDateTimeType"):
        return self.rank <= other.rank if other is not None else False


DATE_TIMES = {
    "FileModifyDate": ExifDateTimeType("FileModifyDate", False, -1),
    "DateTimeOriginal": ExifDateTimeType("DateTimeOriginal", False, 2),
    "CreateDate": ExifDateTimeType("CreateDate", False, 1),
    "GPSDateTime": ExifDateTimeType("GPSDateTime", False, 6),
    "ModifyDate": ExifDateTimeType("ModifyDate", False, 0),
    "SonyDateTime2": ExifDateTimeType("SonyDateTime2", True, 4),
    "SonyDateTime": ExifDateTimeType("SonyDateTime", False, 5),
}


class TimeKeeper:
    """
    keep track of Times out of the Exif Info
    """

    def __init__(
        self,
    ):
        self.datetime: datetime.datetime = None
        self.edt: ExifDateTimeType = None
        self.times = []

    def add_all(self, info: dict):
        for k in info:
            if k in DATE_TIMES:
                self._add(DATE_TIMES[k], info[k])

    def _add(self, etype: ExifDateTimeType, date_time_str: str):
        if etype.better(self.edt) and date_time_str is not None and date_time_str != "":
            try:
                self.edt = etype
                dt = None

                # Prepare for eventualities
                time_format = TIMESTR
                if "." in date_time_str:
                    time_format = time_format + ".%f"
                if "Z" in date_time_str:
                    time_format = time_format + "Z"

                if "+" in date_time_str:
                    ar = date_time_str.split("+")
                    dt = datetime.datetime.strptime(ar[0], time_format)
                    tm = strptime(ar[1], "%H:%M")
                    tz = datetime.timezone(
                        datetime.timedelta(hours=tm.tm_hour, minutes=tm.tm_min)
                    )
                    dt = dt.astimezone(tz)

                elif "-" in date_time_str:
                    ar = date_time_str.split("-")
                    dt = datetime.datetime.strptime(ar[0], time_format)
                    tm = strptime(ar[1], "%H:%M")
                    tz = datetime.timezone(
                        datetime.timedelta(hours=-tm.tm_hour, minutes=-tm.tm_min)
                    )
                    dt = dt.astimezone(tz)

                else:
                    dt = datetime.datetime.strptime(date_time_str, time_format)
                    if etype.utctime:
                        dt = dt.replace(tzinfo=UTC)  # time was already UTC
                    else:
                        dt = dt.astimezone()  # using local current timezone

                self.edt = etype
                self.datetime = dt
            except ValueError as ve:
                print(f"{date_time_str} --> {ve}")
                # raise ValueError

            # print(f"{date_time_str} --> {self.datetime}")

    def add(self, tag: str, date_time_str: str):
        if tag in DATE_TIMES:
            self._add(DATE_TIMES[tag], date_time_str)

    def as_iso_time(self) -> str:
        return self.datetime.isoformat() if self.datetime else None

    def as_utc_normalized(self) -> str:
        return self.datetime.astimezone(UTC).isoformat() if self.datetime else None

    def __str__(self):
        return self.as_iso_time()

    @classmethod
    def check(cls, candidate_datetime: str) -> bool:
        return False
