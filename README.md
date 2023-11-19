# ⏱️ Arbeitszeit

*Track your worktime.*

## Motivation

I wrote this CLI tool to track my worktime
and make it easy to enter it in [Workday](https://www.workday.com/).

## Installation

```sh
pipx install arbeitszeit
# or
pip install --user arbeitszeit
```

## Usage

**For all time values, the app uses `24:00` format.**

### Optional: Set the storage file path

By default the app will use `$HOME/.config/arbeitszeit/arbeitszeit.txt`.

```
arbeitszeit config path path/to/your/arbeitszeit.txt
```

### Optional: Set your daily worktime

By default the app will assume 8 hours.

```sh
arbeitszeit config worktime 06:00
```

### Optional: Edit your config

You can edit your `config.yaml` with your default `$EDITOR`.

```sh
arbeitszeit config edit
```

### Record the start of your worktime

By default the app will use the current time.

```sh
arbeitszeit start
# or
arbeitszeit start 09:00
```

### Record the end of your worktime

By default the app will use the current time.

```sh
arbeitszeit stop
# or
arbeitszeit stop 09:00
```

### Edit your worktime records

You can edit your `arbeitszeit.txt` with your default `$EDITOR`.

```sh
arbeitszeit edit
```

The entries have the following format:

```txt
Day YYYY-MM-DD HH:MM HH:MM 
```

If a time value is undefined, it will show `--:--`.

### Show your worktime records

Aggregate all worktime records in an overview by week and day:

```sh
arbeitszeit log
```

The output will have the following format:

```txt
2023W46: 15:00 [-01:00]
  Thu 2023-11-16: 08:15 [+00:15]
  Fri 2023-11-17: 06:45 [-01:15]
```
