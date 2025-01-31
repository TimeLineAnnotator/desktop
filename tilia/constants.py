import configparser
from pathlib import Path

setupcfg = configparser.ConfigParser()
setupcfg.read("setup.cfg")

APP_NAME = "TiLiA"
try:
    VERSION = setupcfg["metadata"]["version"]
except KeyError:
    VERSION = "test"
APP_ICON_PATH = Path("ui", "img", "main_icon.png")
FILE_EXTENSION = "tla"
GITHUB_URL = "https://github.com/TimeLineAnnotator/desktop"
WEBSITE_URL = "https://tilia-app.com/"
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
