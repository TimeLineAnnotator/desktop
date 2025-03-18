import configparser
from pathlib import Path

setupcfg = configparser.ConfigParser()
setupcfg.read(Path(__file__).parent.parent / "setup.cfg")

if setupcfg.has_section("metadata"):
    APP_NAME = setupcfg["metadata"]["name"]
    AUTHOR = setupcfg["metadata"]["author"]
    VERSION = setupcfg["metadata"]["version"]

else:
    APP_NAME = "TiLiA"
    AUTHOR = ""
    VERSION = "beta"

FILE_EXTENSION = "tla"
GITHUB_URL = "https://github.com/TimeLineAnnotator/desktop"
WEBSITE_URL = "https://tilia-app.com/"
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
