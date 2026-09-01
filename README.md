# rtwi

![Python 3.14+](https://img.shields.io/badge/Python-3.14%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-%3E94%25-brightgreen)
![macOS aarch64](https://img.shields.io/badge/macOS-aarch64-lightgrey)

**English** · [Русский](README.ru.md)

Automatic authorization on the **Rostelecom commercial Wi-Fi** captive portal
([auth.wifi.rt.ru](https://auth.wifi.rt.ru)) plus **MAC roll** to reset usage
limits when the portal blocks your device. A small macOS CLI, built like
[openrot](https://github.com/vispar-tech/openrot).

## Why

Flying on Wi-Fi at airports and trains, the Rostelecom portal keeps asking you
to sign back in, and once your usage limit is hit it answers `FORBIDDEN` until
you come up with a new MAC address. rtwi replaces the manual browser dance with
a single command: check the portal, sign in, confirm via SMS or callback, and
automatically roll the MAC when the portal blocks you.

## Quick install

**Standalone binary** (macOS arm64) — downloads the prebuilt release and
installs `rtwi` into `~/.local/lib/rtwi` (symlink in `~/.local/bin`):

```bash
curl -fsSL https://raw.githubusercontent.com/vispar-tech/rtwi/main/install.sh | bash
```

Pin an exact version with `RTWI_VERSION`:

```bash
RTWI_VERSION=v0.1.0 curl -fsSL https://raw.githubusercontent.com/vispar-tech/rtwi/main/install.sh | bash
```

## Usage

```
rtwi status       # Wi-Fi + portal state
rtwi fix          # authorize on the portal, auto-rolling the MAC when blocked
rtwi sms 1234     # submit an SMS confirmation code
rtwi roll         # roll the MAC (change Wi-Fi adapter MAC; needs root)
rtwi config       # open ~/.config/rtwi/config.yaml in $EDITOR
rtwi watch        # background daemon: monitor + auto-authorize
```

Let the portal phone you back (default `method: call`) and confirm with

```bash
rtwi fix --sudo
```

`fix` signs in, and if the portal answers `FORBIDDEN` it rolls the MAC
(self-elevates via sudo when `--sudo` is given) and retries, up to
`max_rolls` times.

### Background daemon

`rtwi watch` polls the portal on a loop and auto-authorizes whenever needed:

```bash
rtwi watch --interval 60       # check every 60 s
rtwi watch -i 30 --sudo        # allow MAC rolls, check every 30 s
```

Ctrl-C stops the daemon gracefully.

### Exit codes

| code | meaning |
|------|---------|
| 0    | success |
| 1    | failed / error |
| 2    | SMS code required |
| 3    | call-timed out |
| 4    | forbidden (limit reached) |
| 5    | offline |
| 6    | network disabled by schedule |

## Configuration

`~/.config/rtwi/config.yaml` is created automatically on first run. Every
setting can be overridden with an environment variable.

| key               | default     | env              |
|-------------------|-------------|------------------|
| `phone`           | (empty)     | `RTWI_PHONE`     |
| `interface`       | `auto`      | `RTWI_INTERFACE` |
| `method`          | `call`      | `RTWI_METHOD`    |
| `network`         | `Rostelecom`| `RTWI_NETWORK`   |
| `auto_roll`       | `true`      | `RTWI_AUTO_ROLL` |
| `max_rolls`       | `3`         | `RTWI_MAX_ROLLS` |
| `request_timeout` | `5`         | `RTWI_TIMEOUT`   |
| `poll_interval`   | `5`         | —                |
| `max_call_polls`  | `10`        | —                |

### Schedule

When the portal is disabled by schedule (e.g. "Сеть отключена по расписанию
предприятия"), rtwi detects this automatically and **does not roll the MAC**
(uselessly).  You can also configure your own working hours so rtwi skips
authorization outside the allowed window:

```yaml
phone: +79110000000
method: call
schedule:
  enabled: true
  start: "09:00"
  end: "18:00"
  days: [0, 1, 2, 3, 4]   # Mon-Fri
```

| key            | default     | description |
|----------------|-------------|-------------|
| `enabled`      | `false`     | enable schedule check |
| `start`        | `08:00`     | start of allowed window (HH:MM) |
| `end`          | `22:00`     | end of allowed window (HH:MM) |
| `days`         | `[0,1,2,3,4]` | allowed weekdays (0=Mon .. 6=Sun) |

Days: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun.

The window can wrap past midnight (e.g. `start: "22:00"`, `end: "06:00"`).

Set enough to get started:

```yaml
phone: +79110000000
method: call
auto_roll: true
```

## Build from source

Requires Python 3.14+ and [Poetry](https://python-poetry.org):

```bash
make install   # install dependencies
make check     # ruff + mypy + pytest (coverage ≥ 75%)
make package   # standalone onedir build + dist/rtwi-darwin-aarch64.tar.gz
```

## License

[MIT](LICENSE)