# tilia-core

The part of [TiLiA](https://tilia-app.com) that works on `.tla` files and folders of them without a user interface. It is used by TiLiA, by TiLiA Library and by scripts, and it never needs Qt.

This package is under development and nothing is stable yet.

```
pip install tilia-core
```

## Regular expressions

Regular expressions in queries run on Python's `re`, which cannot be stopped once it is running: a pattern that backtracks badly holds the whole process, whatever the time limit of the call. Install the extra to give them a time limit:

```
pip install "tilia-core[regex]"
```

It adds the third-party [`regex`](https://pypi.org/project/regex/) package, which stops a regular expression when the call's `time_limit` runs out. The bound is approximate, not exact. Without the extra, `time_limit` and `cancel` do not cover regular expressions.

## License

GNU General Public License, version 3 or later. Source: <https://github.com/TimeLineAnnotator/desktop>
