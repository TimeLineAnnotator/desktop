import sys
from pathlib import Path

sys.path[0] = Path(__file__).parents[1].__str__()

from tilia.boot import boot


if __name__ == "__main__":
    boot()
