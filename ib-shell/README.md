# A terminal client for your hosted devices

Like SSH, but without key management and the need to configure anything
on your devices. And you can connect to them from anywhere.

On Ubuntu you might have to install the package `python-websocket`
and `python-requests`.

Optionally set the environment variable `API_KEY` to your
[info-beamer hosted API key](https://info-beamer.com/account) and start
the `ib-shell` command like this. If you do not specify `API_KEY` and
OAuth flow will be used and a refresh token is saved in `~/.ib-shell.token`:

```
$ ib-shell $device_id
```

with `$device_id` being the device you want to connect to. The program will open
a new secure connection and log you into your device. `exit` or `Ctrl-D` will
close the connection.
