# tilia-core

The part of [TiLiA](https://tilia-app.com) that works on `.tla` files and folders of them without a user interface. It is used by TiLiA, by TiLiA Library and by scripts, and it never needs Qt.

This package is under development and nothing is stable yet.

```
pip install tilia-core
```

The package installs the `tilia` command. Other installed packages add subcommands to it; `tilia ui` starts TiLiA when TiLiA is installed.

## Bars and beats

`tilia_core.timemap` says where a time lies in bars and beats, from a beat timeline. It computes all of it when it's asked for: nothing is stored, and no file is written.

Say `document` is a `tla.Document` whose beat timeline has a beat every second from 0 s, three to a bar, and bars 1 and 2 are played twice. Then 7.5 s is in bar 1, the second time through, halfway between beats 2 and 3, and a unit from there to 10 s ends in bar 2:

```pycon
>>> from tilia_core.timemap import time_map_of
>>> time_map = time_map_of(document)
>>> place = time_map.positions(7.5, 10.0)
>>> place.bar, place.pass_, place.beat, place.end_bar
(1, 2, 2.5, 2)
```

`time_map_of` uses the beat timeline whose role is `time_map`, else the first one, and gives `None` when there is none or it can't give a time map. `find_time_map` says why it can't.

## License

GNU General Public License, version 3 or later. Source: <https://github.com/TimeLineAnnotator/desktop>
