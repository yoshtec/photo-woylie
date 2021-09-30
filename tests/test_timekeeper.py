# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from woylie.timekeeper import TimeKeeper


class TestTimeKeeper:
    def test_something(self):
        testdata = {
            "FileModifyDate": "2016:02:28 17:34:29+01:00",
            "FileAccessDate": "2020:01:06 21:37:05+01:00",
            "FileInodeChangeDate": "2020:01:06 21:37:03+01:00",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

        # 2016:02:28 17:34:29+01:00
        assert tk.as_iso_time() == "2016-02-28T17:34:29+01:00"
        assert tk.as_utc_normalized() == "2016-02-28T16:34:29+00:00"

    def test_something2(self):
        testdata = {
            "SonyDateTime2": "2016:01:24 13:06:05",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

    def test_something3(self):
        testdata = {
            "SonyDateTime": "2016:01:24 13:06:05",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

    def test_microseconds(self):
        testdata = {
            "SonyDateTime": "2016:01:24 13:06:05.55",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

        assert tk.as_utc_normalized() == "2016-01-24T12:06:05.550000+00:00"

    def test_timezone(self):
        testdata = {
            "SonyDateTime": "2016:01:24 13:06:05Z",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

        assert tk.as_utc_normalized() == "2016-01-24T12:06:05+00:00"

    def test_no_time(self):
        testdata = {
            "xyz": "2016:01:24 13:06:05Z",
        }

        tk = TimeKeeper()
        tk.add_all(testdata)

        assert tk.as_iso_time() is None
        assert tk.as_utc_normalized() is None
