import tomllib
from pathlib import Path

with open(Path(__file__).parent.parent / "pyproject.toml", "rb") as f:
    setupcfg = tomllib.load(f).get("project", {})

APP_NAME = setupcfg.get("name", "")
AUTHOR = setupcfg.get("authors", [{"name": ""}])[0]["name"]
VERSION = setupcfg.get("version", "beta")

YEAR = "2022-2025"
FILE_EXTENSION = "tla"
EMAIL_URL = "mailto:" + setupcfg.get("authors", [{"email": ""}])[0]["email"]

GITHUB_URL = setupcfg.get("urls", {}).get("Repository", "")
WEBSITE_URL = setupcfg.get("urls", {}).get("Homepage", "")
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
NOTICE = f"""
{APP_NAME}, {setupcfg.get("description", "") if AUTHOR else ""}
Copyright © {YEAR} {AUTHOR}

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""
