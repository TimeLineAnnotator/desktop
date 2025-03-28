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

YEAR = "2022-2025"
FILE_EXTENSION = "tla"
EMAIL_URL = "mailto:tilia@tilia-app.com"
GITHUB_URL = "https://github.com/TimeLineAnnotator/desktop"
WEBSITE_URL = "https://tilia-app.com"
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
NOTICE = f"""
{APP_NAME}, {setupcfg["metadata"]["description"] if AUTHOR else ""}
Copyright © {YEAR} {AUTHOR}

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""
