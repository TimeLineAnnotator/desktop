from __future__ import annotations

from enum import Enum


class InOrOut(Enum):
    IN = 1
    OUT = -1


class UpOrDown(Enum):
    UP = 1
    DOWN = -1


class Side:
    LEFT = "LEFT"
    RIGHT = "RIGHT"
