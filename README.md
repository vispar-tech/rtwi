# rtwi

Automatic authorization in Rostelecom commercial Wi-Fi (`auth.wifi.rt.ru`) plus
MAC roll to reset expired network limits. CLI for macOS.

```
rtwi status       # current network / MAC / portal status
rtwi auth         # one-shot authorization (call | sms)
rtwi roll         # change MAC address (sudo)
rtwi fix          # full automation: auth -> roll on FORBIDDEN -> re-auth
rtwi config       # open ~/.config/rtwi/config.yaml
```

Documentation (RU): [README.ru.md](README.ru.md)