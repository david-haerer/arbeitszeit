#!/usr/bin/env python3

from __future__ import annotations

import sys
import os
from re import match
import datetime as dt
from pathlib import Path
from typing import Optional


# -- CONSTS --


NONE_TIME = "--:--"

PATTERN_DATE = "%Y-%m-%d"
PATTERN_DAY = "%a"
PATTERN_TIME = "%H:%M"

REGEX_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
REGEX_DAY = r"[A-z ]{3}"
REGEX_TIME = "(" + "|".join(["[0-9]{2}:[0-9]{2}", NONE_TIME]) + ")"


# -- UTILS --


def today() -> dt.date:
    return dt.datetime.now().date()


def now() -> dt.time:
    return dt.datetime.now().time()


def is_date(date: str) -> bool:
    return match(REGEX_DATE, date)


def is_time(time: str) -> bool:
    return match(REGEX_TIME, time)


def is_record(text: str) -> bool:
    pattern = " ".join([REGEX_DAY, REGEX_DATE, REGEX_TIME, REGEX_TIME])
    return match(pattern, text)


def text_to_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, PATTERN_DATE)


def date_to_text(date: dt.date) -> str:
    return date.strftime(f"{PATTERN_DAY} {PATTERN_DATE}")


def text_to_time(text: str) -> dt.time | None:
    if text == NONE_TIME:
        return None
    return dt.datetime.strptime(text, PATTERN_TIME).time()


def time_to_text(time: dt.time | None) -> str:
    if time is None:
        return NONE_TIME
    return time.strftime(PATTERN_TIME)


def timedelta_to_text(timedelta: dt.timedelta | None) -> str:
    if timedelta is None:
        return NONE_TIME
    hours = timedelta.seconds // 3600
    minutes = (timedelta.seconds // 60) % 60
    return f"{hours:02}:{minutes:02}"


def signed_timedelta_to_text(timedelta: dt.timedelta | None) -> str:
    if timedelta is None:
        return NONE_TIME
    sign = "+"
    if timedelta.days < 0:
        timedelta = dt.timedelta() - timedelta
        sign = "-"
    hours = timedelta.seconds // 3600
    minutes = (timedelta.seconds // 60) % 60
    return f"{sign}{hours:02}:{minutes:02}"


def text_to_timedelta(text: str) -> dt.timedelta | None:
    if text == NONE_TIME:
        return None
    time = dt.datetime.strptime(text, PATTERN_TIME)
    return dt.timedelta(hours=time.hour, minutes=time.minute)


def sum_timedeltas(timedeltas: list[dt.timedelta]) -> dt.timedelta:
    return sum(timedeltas, dt.timedelta())


# -- MODEL --


class Record:
    def __init__(
        self: Record, day: Optional[dt.date] = None, start: Optional[dt.time] = None, stop: Optional[dt.time] = None
    ):
        assert (start, stop) != (None, None), "Either start or stop must be defined!"
        if None not in (start, stop):
            assert start <= stop, "Start must come before stop!"
        self.day = day or today()
        self.start = start
        self.stop = stop

    @classmethod
    def from_text(cls, text) -> Record:
        assert is_record(text)
        day, start, stop = text[4:].split(" ")
        return Record(day=text_to_date(day), start=text_to_time(start), stop=text_to_time(stop))

    @classmethod
    def from_start(cls, start) -> Record:
        assert is_time(start)
        assert start != NONE_TIME
        return Record(day=today(), start=text_to_time(start), stop=None)

    @classmethod
    def from_stop(cls, stop) -> Record:
        assert is_time(start)
        assert stop != NONE_TIME
        return Record(day=today(), start=None, stop=text_to_time(start))

    @property
    def worktime(self) -> dt.timedelta | None:
        if None in (self.start, self.stop):
            return None
        return dt.datetime.combine(self.day, self.stop) - dt.datetime.combine(self.day, self.start)

    @property
    def text(self):
        day = date_to_text(self.day)
        start = time_to_text(self.start)
        stop = time_to_text(self.stop)
        return f"{day} {start} {stop}"

    def __str__(self):
        worktime = timedelta_to_text(self.worktime)
        return f"{self.text} [{worktime}]"


class Day:
    def __init__(self: Day, day: dt.date, worktime_reference: dt.timedelta, records: list[Record]):
        self.day, self.worktime_reference, self.records = day, worktime_reference, records

    @classmethod
    def from_record(cls, record: Record, worktime_reference: dt.timedelta) -> Day:
        return Day(day=record.day, worktime_reference=worktime_reference, records=[record])

    def add_record(self, record: Record):
        assert record.day == self.day, "Record must be from the same day!"
        self.records.append(record)

    @property
    def worktime(self) -> dt.timedelta | None:
        worktimes = [record.worktime for record in self.records]
        if None in worktimes:
            return None
        return sum_timedeltas(worktimes)

    @property
    def delta(self):
        worktime = self.worktime
        if worktime is None:
            return None
        return worktime - self.worktime_reference

    def __str__(self) -> str:
        day = date_to_text(self.day)
        worktime = timedelta_to_text(self.worktime)
        delta = signed_timedelta_to_text(self.delta)
        return f"{day}: {worktime} [{delta}]"


# -- DB --


class DB:
    def __init__(self, path, worktime):
        self.path = path
        self.worktime = worktime
        self.records = self.load()

    def load(self):
        if not self.path.is_file():
            return []
        with open(self.path, "r", encoding="utf-8") as file:
            lines = [line.replace("\n", "") for line in file.readlines()]
        records = []
        for line in lines:
            try:
                records.append(Record.from_text(line))
            except AssertionError as error:
                print(error)
                print(f"{self.path}#L{lines.index(line)}: Invalid record '{line}'!")
                print(f"Edit {self.path} to correct the record.")
                exit(1)
        return records

    def save(self):
        with open(self.path, "w", encoding="utf-8") as file:
            file.write("\n".join(record.text for record in self.records))

    @property
    def empty(self) -> bool:
        return len(self.records) == 0

    @property
    def last(self) -> Record:
        assert not self.empty, "DB is empty, no last record!"
        return self.records[-1]

    @property
    def days(self) -> list[Day]:
        days = {}
        for record in self.records:
            if record.day not in days:
                days[record.day] = Day.from_record(record, self.worktime)
            else:
                days[record.day].add_record(record)
        return days.values()

    def start(self, time: str):
        self.records.append(Record(start=time))
        self.save()

    def stop(self, time: str):
        if self.empty or self.last.stop is not None:
            self.records.append(Record(stop=time))
        else:
            self.last.stop = time
        self.save()


# -- APP --


def start(db: DB, time: Optional[str] = None):
    if time is None:
        time = now()
    else:
        assert is_time(time), f"Time string '{time}' is invalid!"
    db.start(time)


def stop(db: DB, time: Optional[str] = None):
    if time is None:
        time = now()
    else:
        assert is_time(time), f"Time string '{time}' is invalid!"
    db.stop(time)


def log(db: DB):
    days = db.days
    for day in days:
        print(day)
    total_worktime = timedelta_to_text(sum_timedeltas([day.worktime for day in days]))
    total_delta = signed_timedelta_to_text(sum_timedeltas([day.delta for day in days]))
    print(f"\nTotal: {total_worktime} [{total_delta}]")


def usage(name):
    print(f"Usage: [DATA_DIR=./] [WORKTIME=%H:%M] {name} [start | stop [%H:%M]]")


if __name__ == "__main__":
    path = Path(os.getenv("DATA_DIR", ".")) / "arbeitszeit.txt"
    worktime = text_to_timedelta(os.getenv("WORKTIME", "08:00"))
    db = DB(path, worktime)
    args = sys.argv
    if len(args) == 1:
        log(db)
        exit(0)
    if args[1] == "start":
        start(db, args[3] if len(args) > 2 else None)
        exit(0)
    if args[1] == "stop":
        stop(db, args[3] if len(args) > 2 else None)
        exit(0)
    usage(args[0])
    exit(1)
