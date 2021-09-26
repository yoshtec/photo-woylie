# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT

from woylie.timekeeper import TimeKeeper

TESTDATA1 = {
    "FileModifyDate": "2016:02:28 17:34:29+01:00",
    "FileAccessDate": "2020:01:06 21:37:05+01:00",
    "FileInodeChangeDate": "2020:01:06 21:37:03+01:00",
}

TESTDATA2 = {
    "SonyDateTime2": "2016:01:24 13:06:05",
}

TESTDATA3 = {
    "SonyDateTime": "2016:01:24 13:06:05",
}

TESTDATA4 = {
    "SonyDateTime": "2016:01:24 13:06:05",
}


class TestTimeKeeper:

    def test_something(self):
        tk = TimeKeeper()
        tk.add_all(TESTDATA1)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

    def test_something2(self):
        tk = TimeKeeper()
        tk.add_all(TESTDATA2)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

    def test_something3(self):
        tk = TimeKeeper()
        tk.add_all(TESTDATA3)

        print(tk.as_iso_time())
        print(tk.as_utc_normalized())

