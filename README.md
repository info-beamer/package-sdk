# info-beamer hosted package SDK

In this repository you'll find useful files that help
you develop info-beamer hosted packages.

## hosted.py

[hosted.py](hosted.py) can be used as part of an
[info-beamer hosted service](https://info-beamer.com/doc/package-services).
Add this file to your package. Inside your python
based service import some of the utility objects
provided. Example:

```python
from hosted import CONFIG, NODE, DEVICE
```

There are more functions that you can call from your
service that allow you to, for example, turn the
connected screen on/off or reboot the device:

```python
DEVICE.turn_screen_off()
```

You can access all configuration made by the user
in the `CONFIG` object like this:

```python
print(CONFIG['timezone'])
```

You can automatically restart your service by calling

```python
CONFIG.restart_on_update()
```

once. If the system detects that the configuration
file changed, your service will be terminated and
restarted so it can use the new settings.

## hosted.lua

[hosted.lua](hosted.lua) can be use in an info-beamer
node that needs easier access to the configurations
made by the user. In your `node.lua` file, call

```lua
util.init_hosted()
```

once at the top of your script. info-beamer will
look for `hosted.lua`, `node.json` and `package.json`
and will automatically parse `config.json` for you.

You can then access the configuration in the global
`CONFIG` value:

```lua
print(CONIFG.timezone)
```

## hosted.js

The mockup `hosted.js` allows you to develop
[custom ui pages](https://info-beamer.com/doc/package-reference#customconfigurationinterface)
without pushing your package to info-beamer hosted.
Instead you can create a mockup environment to test
your code locally. See the linked documentation for
more information how all of that works together.
