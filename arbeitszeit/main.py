from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml
from appdirs import user_config_dir, user_data_dir
from isoweek import Week as week
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Annotated


# -- CONSTS --


APP_NAME = "arbeitszeit"
CONFIG_PATH = Path(user_config_dir(APP_NAME)) / "config.yaml"
EDITOR = os.getenv("EDITOR", "open")
DATE_PATTERN = "%Y-%m-%d"
DATE_PATTERN_PREFIX = "%a "
DATE_REGEX = r"[A-z ]{3} [0-9]{4}-[0-9]{2}-[0-9]{2}"
NONE_TIME = "--:--"
TIME_PATTERN = "%H:%M"
TIME_REGEX = "[0-9]{2}:[0-9]{2}|{NONE_TIME}"


# -- CONFIG --


class Config:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._config = self.load()

    def load(self):
        if self.path.is_file():
            with open(self.path, "r", encoding="utf-8") as file:
                return yaml.safe_load(file) or {}
        with open(self.path, mode="wt", encoding="utf-8") as file:
            yaml.dump({}, file)
        if "path" in self._config:
            self._config["path"] = Path(self._config["path"])

    def save(self):
        if "path" in self._config:
            self._config["path"] = str(self._config["path"].resolve())
        with open(self.path, mode="wt", encoding="utf-8") as file:
            yaml.dump(self._config, file)

    @property
    def db_path(self) -> Path:
        if "path" not in self._config:
            return self.path.parent / "arbeitszeit.txt"
        return Path(self._config["path"])

    @db_path.setter
    def db_path(self, path: Path):
        self._config["path"] = path
        self.save()

    @property
    def worktime(self) -> timedelta:
        worktime = self._config.get("worktime", "08:00")
        return text_to_timedelta(worktime)

    @worktime.setter
    def worktime(self, worktime: timedelta):
        self._config["worktime"] = timedelta_to_text(worktime)
        self.save()


# -- UTILS --


def today() -> date:
    return dt.datetime.now().date()


def now() -> time:
    return dt.datetime.now().time()


def is_date(date: str) -> bool:
    return re.match(DATE_REGEX, date)


def is_time(time: str) -> bool:
    return re.match(TIME_REGEX, time)


def is_record(text: str) -> bool:
    return re.match(f"{DATE_REGEX} {TIME_REGEX} {TIME_REGEX}", text)


def text_to_date(text: str) -> dt.date:
    return dt.datetime.strptime(text, DATE_PATTERN)


def date_to_text(date: date) -> str:
    return date.strftime(DATE_PATTERN_PREFIX + DATE_PATTERN)


def text_to_time(text: str) -> time | None:
    if text == NONE_TIME:
        return None
    return dt.datetime.strptime(text, TIME_PATTERN).time()


def time_to_text(time: time | None) -> str:
    if time is None:
        return NONE_TIME
    return time.strftime(TIME_PATTERN)


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
    time = dt.datetime.strptime(text, TIME_PATTERN)
    return dt.timedelta(hours=time.hour, minutes=time.minute)


def sum_timedeltas(timedeltas: list[dt.timedelta]) -> dt.timedelta:
    return sum(timedeltas, dt.timedelta())


# -- MODEL --


class Record(BaseModel):
    day: dt.date = Field(default_factory=today)
    start: Optional[dt.time] = None
    end: Optional[dt.time] = None

    @model_validator(mode="after")
    def check_either_start_or_end(self) -> Record:
        if (self.start, self.end) == (None, None):
            raise ValueError("Either start or end must be set!")
        return self

    @model_validator(mode="after")
    def check_start_before_end(self) -> Record:
        if None in (self.start, self.end):
            return self
        if self.start > self.end:
            raise ValueError("Start must come before end!")
        return self

    @classmethod
    def from_text(cls, text) -> Record:
        assert is_record(text)
        day, start, end = text[4:].split(" ")
        return Record(
            day=text_to_date(day), start=text_to_time(start), end=text_to_time(end)
        )

    @classmethod
    def from_start(cls, start) -> Record:
        assert is_time(start)
        assert start != NONE_TIME
        return Record(day=today(), start=text_to_time(start), end=None)

    @classmethod
    def from_end(cls, end) -> Record:
        assert is_time(start)
        assert end != NONE_TIME
        return Record(day=today(), start=None, end=text_to_time(start))

    @property
    def worktime(self) -> dt.timedelta | None:
        if None in (self.start, self.end):
            return None
        return dt.datetime.combine(self.day, self.end) - dt.datetime.combine(
            self.day, self.start
        )

    @property
    def text(self):
        day = date_to_text(self.day)
        start = time_to_text(self.start)
        end = time_to_text(self.end)
        return f"{day} {start} {end}"

    def __str__(self):
        worktime = timedelta_to_text(self.worktime)
        return f"{self.text} [{worktime}]"


class Day(BaseModel):
    day: dt.date
    baseline: dt.timedelta
    records: list[Record]

    @classmethod
    def from_record(cls, record: Record, baseline: dt.timedelta) -> Day:
        return Day(day=record.day, baseline=baseline, records=[record])

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
        return -(self.baseline - worktime)

    @property
    def week(self) -> isoweek.week:
        y, w, _ = self.day.isocalendar()
        return week(y, w)

    def __str__(self) -> str:
        day = date_to_text(self.day)
        worktime = timedelta_to_text(self.worktime)
        delta = signed_timedelta_to_text(self.delta)
        return f"{day}: {worktime} [{delta}]"


class Week(BaseModel):
    week: week
    days: list[Day]

    @classmethod
    def from_day(cls, day: Day) -> Week:
        return Week(week=day.week, days=[day])

    def add_day(self, day: Day):
        assert day.week == self.week, "Day must be in the same week!"
        self.days.append(day)

    @property
    def worktime(self) -> dt.timedelta:
        worktimes = [day.worktime for day in self.days]
        if None in worktimes:
            return None
        return sum_timedeltas(worktimes)

    @property
    def delta(self):
        deltas = [day.delta for day in self.days]
        if None in deltas:
            return None
        return sum_timedeltas(deltas)

    def __str__(self) -> str:
        worktime = timedelta_to_text(self.worktime)
        delta = signed_timedelta_to_text(self.delta)
        return "\n".join(
            [f"{self.week}: {worktime} [{delta}]"] + [f"  {day}" for day in self.days]
        )


# -- DB --


class DB:
    def __init__(self, config: Config):
        self.path = config.db_path
        self.baseline = config.worktime
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
            except:
                raise
                print(f"{self.path}#L{lines.index(line)}: Invalid record '{line}'!")
                exit()
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
                days[record.day] = Day.from_record(record, self.baseline)
            else:
                days[record.day].add_record(record)
        return days.values()

    @property
    def weeks(self) -> list[Week]:
        weeks = {}
        for day in self.days:
            if day.week not in weeks:
                weeks[day.week] = Week.from_day(day)
            else:
                weeks[day.week].add_day(day)
        return weeks.values()

    def start(self, time: str):
        self.records.append(Record(start=time))
        self.save()

    def end(self, time: str):
        if self.empty or self.last.end is not None:
            self.records.append(Record(end=time))
        else:
            self.last.end = time
        self.save()


# -- APP --


app = typer.Typer()
app_config = typer.Typer()
app.add_typer(app_config, name="config")


@app.command()
def start(time: Annotated[Optional[str], typer.Argument()] = None):
    if time is None:
        time = now()
    else:
        assert is_time(time), f"Time string '{time}' is invalid!"
    config = Config(CONFIG_PATH)
    db = DB(config)
    db.start(time)


@app.command()
def end(time: Annotated[Optional[str], typer.Argument()] = None):
    if time is None:
        time = now()
    else:
        assert is_time(time), f"Time string '{time}' is invalid!"
    config = Config(CONFIG_PATH)
    db = DB(config)
    db.end(time)


@app.command()
def log():
    config = Config(CONFIG_PATH)
    db = DB(config)
    for week in db.weeks:
        print(week)


@app.command()
def edit():
    config = Config(CONFIG_PATH)
    subprocess.call([EDITOR, config.db_path])


@app_config.command()
def edit():
    subprocess.call([EDITOR, CONFIG_PATH])


@app_config.command()
def path(path: Path):
    config = Config(CONFIG_PATH)
    config.db_path = path


@app_config.command()
def worktime(worktime: str):
    assert is_time(worktime)
    assert worktime != NONE_TIME
    config = Config(CONFIG_PATH)
    config.worktime = text_to_timedelta(worktime)


if __name__ == "__main__":
    app(prog_name=APP_NAME)
