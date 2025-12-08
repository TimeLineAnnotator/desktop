from importlib import metadata
from pathlib import Path
import re

if (toml := Path(__file__).parent.parent / "pyproject.toml").exists():
    from sys import version_info

    if version_info >= (3, 11):
        from tomllib import load
    else:
        from tomli import load

    with open(toml, "rb") as f:
        setupcfg = load(f).get("project", {})
    AUTHOR = setupcfg.get("authors", [{"name": ""}])[0]["name"]
    EMAIL = setupcfg.get("authors", [{"email": ""}])[0]["email"]

else:
    setupcfg = metadata.metadata("TiLiA").json.copy()

    AUTHOR = re.search(r'"(.*?)"', setupcfg.get("author_email", "")).group(1)
    EMAIL = re.search(r"<(.*?)>", setupcfg.get("author_email", "")).group(1)
    if "urls" not in setupcfg:
        setupcfg["urls"] = {}
    for url in setupcfg.get("project_url", {}):
        k, _, v = url.partition(", ")
        setupcfg["urls"][k] = v
    setupcfg["description"] = setupcfg.get("summary", "")

APP_NAME = setupcfg.get("name", "")
VERSION = setupcfg.get("version", "0.0.0")

YEAR = "2022-2025"
FILE_EXTENSION = "tla"
EMAIL_URL = "mailto:" + EMAIL

GITHUB_URL = setupcfg.get("urls", {}).get("Repository", "")
WEBSITE_URL = setupcfg.get("urls", {}).get("Homepage", "")
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
NOTICE = f"""
{APP_NAME}, {setupcfg.get("description", "") if AUTHOR else ""}
Copyright © {YEAR} {AUTHOR}

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""
