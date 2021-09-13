#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

import datetime
import enum


class ExifDateTimeEn(enum.Enum):
    """
    Date Time options to extract the exact Date and Time of a File
    """

    DATETIME_ORG = "DateTimeOriginal"  # Local DateTime
    DATETIME_CREATED = "CreateDate"  # Local DateTime
    DATETIME_GPS = "GPSDateTime"
    DATETIME_MOD = "ModifyDate"
    DATETIME_SONY = "SonyDateTime"  # Contains local DateTime
    DATETIME_SONY2 = "SonyDateTime2"  # Contains UTC Time
    DATETIME_FILE_MODIFY = "FileModifyDate"


class ExifDateTimeType:
    def __init__(self, name: str, utctime: bool = False):
        self.name = name
        self.utctime = utctime


DATETIMES = [
    ExifDateTimeType("DateTimeOriginal", False),
    ExifDateTimeType("CreateDate", False),
    ExifDateTimeType("GPSDateTime"),
    ExifDateTimeType("ModifyDate"),
    ExifDateTimeType("SonyDateTime2", True),
    ExifDateTimeType("SonyDateTime", False),
]


class TimeKeeper:
    def __init__(
        self,
    ):
        self.best_time: datetime.datetime = None
        self.best_time_tz: datetime.timezone = None
        self.best_time_tag: str = None
        self.times = []

    def add(self, date: str, tag: str):
        self.best_time_tag = tag

    def as_iso_time(self) -> str:
        return self.best_time.isoformat()

    def __str__(self):
        return self.as_iso_time()

    @classmethod
    def check(cls, candidate_datetime: str) -> bool:
        return False
