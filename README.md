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
installs `rtwi` into `~/.local/bin`:

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
```

Let the portal phone you back (default `method: call`) and confirm with

```bash
rtwi fix --sudo
```

`fix` signs in, and if the portal answers `FORBIDDEN` it rolls the MAC
(self-elevates via sudo when `--sudo` is given) and retries, up to
`max_rolls` times.

Exit codes:

| code | meaning |
|------|---------|
| 0    | success |
| 1    | failed / error |
| 2    | SMS code required |
| 3    | call-timed out |
| 4    | forbidden (limit reached) |
| 5    | offline |

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