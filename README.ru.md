# rtwi

![Python 3.14+](https://img.shields.io/badge/Python-3.14%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen)
![Coverage](https://img.shields.io/badge/Coverage-%3E94%25-brightgreen)
![macOS aarch64](https://img.shields.io/badge/macOS-aarch64-lightgrey)

[English](README.md) · **Русский**

Автоматическая авторизация в коммерческом Wi-Fi **«Ростелеком»**
(портал [auth.wifi.rt.ru](https://auth.wifi.rt.ru)) с опциональным
**сбросом MAC-адреса** для обнуления лимита при блокировке устройства.
Небольшой CLI для macOS, сделанный по образцу
[openrot](https://github.com/vispar-tech/openrot).

## Зачем

Пользовался Wi-Fi в аэропортах и поездах — «Ростелеком» постоянно просит
авторизоваться заново, а при исчерпании лимита отвечает `FORBIDDEN`, пока
не сменишь MAC-адрес. rtwi заменяет ручной танец с браузером одной командой:
проверяет портал, авторизует, подтверждает по SMS или обратному звонку и
автоматически меняет MAC, если портал блокирует доступ.

## Быстрая установка

**Готовый бинарник** (macOS arm64) — скачивает собранный релиз и ставит
`rtwi` в `~/.local/bin`:

```bash
curl -fsSL https://raw.githubusercontent.com/vispar-tech/rtwi/main/install.sh | bash
```

Закрепить конкретную версию можно через `RTWI_VERSION`:

```bash
RTWI_VERSION=v0.1.0 curl -fsSL https://raw.githubusercontent.com/vispar-tech/rtwi/main/install.sh | bash
```

## Использование

```
rtwi status       # состояние Wi-Fi и портала
rtwi fix          # авторизация, при блокировке — авто-сброс MAC
rtwi sms 1234     # подтверждение SMS-кодом
rtwi roll         # сброс MAC-адреса адаптера (нужны права root)
rtwi config       # открыть ~/.config/rtwi/config.yaml в $EDITOR
```

Портал позвонит вам обратно (по умолчанию `method: call`), подтвердите:

```bash
rtwi fix --sudo
```

`fix` авторизует, а при ответе портала `FORBIDDEN` меняет MAC-адрес
(при `--sudo` самостоятельно повышает права через sudo) и повторяет попытку
до `max_rolls` раз.

Коды выхода:

| код | значение |
|-----|----------|
| 0   | успех |
| 1   | ошибка |
| 2   | требуется SMS-код |
| 3   | звонок не дождались |
| 4   | запрещено (лимит исчерпан) |
| 5   | офлайн |

## Конфигурация

`~/.config/rtwi/config.yaml` создаётся автоматически при первом запуске.
Любой параметр можно переопределить переменной окружения.

| параметр          | по умолч. | env               |
|-------------------|-----------|-------------------|
| `phone`           | (пусто)   | `RTWI_PHONE`      |
| `interface`       | `auto`    | `RTWI_INTERFACE`  |
| `method`          | `call`    | `RTWI_METHOD`     |
| `network`         | `Rostelecom`| `RTWI_NETWORK`   |
| `auto_roll`       | `true`    | `RTWI_AUTO_ROLL`  |
| `max_rolls`       | `3`       | `RTWI_MAX_ROLLS`  |
| `request_timeout` | `5`       | `RTWI_TIMEOUT`    |
| `poll_interval`   | `5`       | —                 |
| `max_call_polls`  | `10`      | —                 |

Достаточно минимума для старта:

```yaml
phone: +79110000000
method: call
auto_roll: true
```

## Сборка из исходников

Нужны Python 3.14+ и [Poetry](https://python-poetry.org):

```bash
make install   # установка зависимостей
make check     # ruff + mypy + pytest (покрытие ≥ 75%)
make package   # бинарник onedir + dist/rtwi-darwin-aarch64.tar.gz
```

## Лицензия

[MIT](LICENSE)