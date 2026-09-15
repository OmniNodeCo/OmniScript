"""Dates and times, without the ceremony.

    let d = date("2026-09-15")
    d.year                  # 2026
    d.weekday               # "Tuesday"
    d.format("%A, %d %B")   # "Tuesday, 15 September"
    d + days(3)             # three days later
    d.diff(date(), "days")  # how far from now

A `Date` is a moment in local time. It compares and sorts with the usual
operators, prints as ISO text, and answers to `.add()`, `.diff()`,
`.start_of()` and `.format()`.
"""

from __future__ import annotations

import calendar as _calendar
import datetime as _dt

from ..errors import OmniRuntimeError, OmniTypeError
from ..values import HostObject, collect_signature, to_string
from .core import as_num, omni

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday")

UNIT_SECONDS = {
    "second": 1.0, "seconds": 1.0, "sec": 1.0, "s": 1.0,
    "minute": 60.0, "minutes": 60.0, "min": 60.0,
    "hour": 3600.0, "hours": 3600.0, "h": 3600.0,
    "day": 86400.0, "days": 86400.0, "d": 86400.0,
    "week": 604800.0, "weeks": 604800.0, "w": 604800.0,
}


# ------------------------------------------------------------------- helpers
def _to_datetime(value, fmt=None) -> _dt.datetime:
    """Accept a Date, a datetime, an epoch number, or text."""
    if isinstance(value, HostObject) and value.type_name == "Date":
        return value.fields["__dt__"]
    if isinstance(value, _dt.datetime):
        return value
    if isinstance(value, _dt.date):
        return _dt.datetime(value.year, value.month, value.day)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _dt.datetime.fromtimestamp(float(value))
    if value is None:
        return _dt.datetime.now()
    text = to_string(value).strip()
    if fmt:
        try:
            return _dt.datetime.strptime(text, to_string(fmt))
        except ValueError as exc:
            raise OmniRuntimeError(f"cannot read `{text}` as `{to_string(fmt)}`",
                                   hint=str(exc)) from None
    for candidate in (text, text.replace("/", "-"), text.replace("T", " ")):
        try:
            parsed = _dt.datetime.fromisoformat(candidate)
            return parsed
        except ValueError:
            continue
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y",
                    "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y",
                    "%Y/%m/%d", "%H:%M:%S", "%H:%M"):
        try:
            return _dt.datetime.strptime(text, pattern)
        except ValueError:
            continue
    raise OmniRuntimeError(f"cannot read `{text}` as a date",
                           hint='try "2026-09-15", "2026-09-15 13:45:00", '
                                'or pass a format: date(text, "%d/%m/%Y")')


def _shift_months(dt: _dt.datetime, months: int) -> _dt.datetime:
    total = dt.month - 1 + months
    year = dt.year + total // 12
    month = total % 12 + 1
    day = min(dt.day, _calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def make_date(dt: _dt.datetime) -> HostObject:
    """Build the Date value the language hands back to scripts."""
    iso = dt.date().isoformat()
    fields = {
        "year": float(dt.year), "month": float(dt.month), "day": float(dt.day),
        "hour": float(dt.hour), "minute": float(dt.minute),
        "second": float(dt.second), "millisecond": float(dt.microsecond // 1000),
        "weekday": WEEKDAYS[dt.weekday()], "weekday_num": float(dt.weekday() + 1),
        "weekend": dt.weekday() >= 5,
        "iso": iso,
        "datetime": dt.isoformat(timespec="seconds"),
        "timestamp": dt.timestamp(),
        "day_of_year": float(dt.timetuple().tm_yday),
        "leap_year": _calendar.isleap(dt.year),
        "__dt__": dt,
    }

    def str_(self):
        return self.fields["datetime"] if (self.fields["hour"] or self.fields["minute"]
                                           or self.fields["second"]) else self.fields["iso"]

    def format(self, pattern="%Y-%m-%d"):
        """format("%A, %d %B %Y") -- strftime codes, with a sensible default."""
        return self.fields["__dt__"].strftime(to_string(pattern))

    def add(self, seconds=0.0, minutes=0.0, hours=0.0, days=0.0, weeks=0.0,
            months=0.0, years=0.0):
        """add(days: 3) -- a new Date, this one is never changed."""
        dt = self.fields["__dt__"]
        span = _dt.timedelta(seconds=as_num(seconds, "seconds")
                             + as_num(minutes, "minutes") * 60
                             + as_num(hours, "hours") * 3600
                             + as_num(days, "days") * 86400
                             + as_num(weeks, "weeks") * 604800)
        dt = dt + span
        shift = int(as_num(months, "months")) + int(as_num(years, "years")) * 12
        if shift:
            dt = _shift_months(dt, shift)
        return make_date(dt)

    def diff(self, other, unit="seconds"):
        """diff(other, "days") -- how far apart two dates are."""
        other_dt = _to_datetime(other)
        span = (self.fields["__dt__"] - other_dt).total_seconds()
        name = to_string(unit).lower()
        if name in ("month", "months"):
            mine, theirs = self.fields["__dt__"], other_dt
            whole = (mine.year - theirs.year) * 12 + (mine.month - theirs.month)
            if mine.day < theirs.day:
                whole -= 1
            return float(whole)
        if name in ("year", "years"):
            mine, theirs = self.fields["__dt__"], other_dt
            whole = mine.year - theirs.year
            if (mine.month, mine.day) < (theirs.month, theirs.day):
                whole -= 1
            return float(whole)
        factor = UNIT_SECONDS.get(name)
        if factor is None:
            raise OmniRuntimeError(
                f"`{name}` is not a unit of time",
                hint="try seconds, minutes, hours, days, weeks, months or years")
        return span / factor

    def start_of(self, unit="day"):
        """start_of("day") -- the same date, at midnight."""
        dt = self.fields["__dt__"]
        name = to_string(unit).lower()
        if name in ("day", "days"):
            return make_date(dt.replace(hour=0, minute=0, second=0, microsecond=0))
        if name in ("month", "months"):
            return make_date(dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
        if name in ("year", "years"):
            return make_date(dt.replace(month=1, day=1, hour=0, minute=0,
                                        second=0, microsecond=0))
        if name in ("hour", "hours"):
            return make_date(dt.replace(minute=0, second=0, microsecond=0))
        raise OmniRuntimeError(f"`{name}` is not something a day starts at",
                               hint="try hour, day, month or year")

    def to_map(self):
        """every field at once, as a map"""
        return {k: v for k, v in self.fields.items() if not k.startswith("__")}

    def __add__(self, other):
        return _moved(self, _span_seconds(other))

    def __radd__(self, other):
        return _moved(self, _span_seconds(other))

    def __sub__(self, other):
        if isinstance(other, HostObject) and other.type_name == "Date":
            return (self.fields["__dt__"] - other.fields["__dt__"]).total_seconds()
        return _moved(self, -_span_seconds(other))

    def __eq__(self, other):
        try:
            return self.fields["__dt__"] == _to_datetime(other)
        except OmniRuntimeError:
            return False

    def __lt__(self, other):
        return self.fields["__dt__"] < _to_datetime(other)

    def __le__(self, other):
        return self.fields["__dt__"] <= _to_datetime(other)

    def __gt__(self, other):
        return self.fields["__dt__"] > _to_datetime(other)

    def __ge__(self, other):
        return self.fields["__dt__"] >= _to_datetime(other)

    methods = {}
    for fn in (str_, format, add, diff, start_of, to_map,
               __add__, __radd__, __sub__, __eq__, __lt__, __le__, __gt__, __ge__):
        name = fn.__name__
        if name.endswith("_") and not name.startswith("__"):
            name = name[:-1]        # `str_` is registered as `str`
        methods[name] = collect_signature(fn, name, (fn.__doc__ or "").strip(),
                                          takes_interp=False)
    return HostObject("Date", methods=methods, fields=fields,
                      display=lambda obj: _display(obj))


def _display(obj) -> str:
    dt = obj.fields["__dt__"]
    if (dt.hour, dt.minute, dt.second) == (0, 0, 0):
        return dt.date().isoformat()
    return dt.isoformat(timespec="seconds")


def _moved(date_obj, seconds: float) -> HostObject:
    return make_date(date_obj.fields["__dt__"] + _dt.timedelta(seconds=seconds))


def _span_seconds(value) -> float:
    """`d + days(3)` and `d + 259200` both mean the same thing."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, HostObject) and value.type_name == "Date":
        raise OmniTypeError("subtract two dates to get seconds between them",
                            hint="use `a.diff(b, \"days\")` or `a - b`")
    return as_num(value, "seconds")


# ------------------------------------------------------------------ builtins
@omni("date", alias=("parse_date", "datetime"))
def _date(interp, value=None, format=None):
    """date("2026-09-15") -- a moment in time; date() is right now.

    Accepts ISO dates and datetimes, `15/09/2026`, `September 15, 2026`, an
    epoch number, or any text plus a format: `date(text, "%d/%m/%Y")`.
    """
    return make_date(_to_datetime(value, format))


@omni("days")
def _days(interp, n):
    """days(3) -- that many days, counted in seconds."""
    return as_num(n, "n") * 86400.0


@omni("hours")
def _hours(interp, n):
    """hours(6) -- that many hours, counted in seconds."""
    return as_num(n, "n") * 3600.0


@omni("minutes")
def _minutes(interp, n):
    """minutes(90) -- that many minutes, counted in seconds."""
    return as_num(n, "n") * 60.0


@omni("weeks")
def _weeks(interp, n):
    """weeks(2) -- that many weeks, counted in seconds."""
    return as_num(n, "n") * 604800.0


@omni("date_range")
def _date_range(interp, start, end, step_days=1.0):
    """date_range("2026-01-01", "2026-01-05") -- every day between, inclusive."""
    first = _to_datetime(start)
    last = _to_datetime(end)
    step = max(1, int(as_num(step_days, "step_days")))
    out = []
    cursor = first
    while cursor <= last:
        out.append(make_date(cursor))
        cursor = cursor + _dt.timedelta(days=step)
    return out
