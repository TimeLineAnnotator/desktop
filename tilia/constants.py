import re
from importlib import metadata
from pathlib import Path

if (toml := Path(__file__).parent.parent / "pyproject.toml").exists():
    import sys

    if sys.version_info >= (3, 11):
        from tomllib import load
    else:
        from tomli import load

    with open(toml, "rb") as f:
        setupcfg = load(f).get("project", {})
    AUTHORS = [a.get("name", "") for a in setupcfg.get("authors", [{"name": ""}])]
    AUTHOR = ", ".join(a for a in AUTHORS if a)
    EMAIL = setupcfg.get("authors", [{"email": ""}])[0]["email"]

else:
    try:
        setupcfg = metadata.metadata("TiLiA").json.copy()

        AUTHOR = re.search(r'"(.*?)"', setupcfg.get("author_email", "")).group(1)
        EMAIL = re.search(r"<(.*?)>", setupcfg.get("author_email", "")).group(1)
        if "urls" not in setupcfg:
            setupcfg["urls"] = {}
        for url in setupcfg.get("project_url", {}):
            k, _, v = url.partition(", ")
            setupcfg["urls"][k] = v
        setupcfg["description"] = setupcfg.get("summary", "")
    except metadata.PackageNotFoundError:
        setupcfg = {}
        AUTHOR = ""
        EMAIL = ""

APP_NAME = setupcfg.get("name", "")
VERSION = setupcfg.get("version", "0.0.0")

YEAR = "2022-2026"
FILE_EXTENSION = "tla"
EMAIL_URL = "mailto:" + EMAIL

GITHUB_URL = setupcfg.get("urls", {}).get("Repository", "")
WEBSITE_URL = setupcfg.get("urls", {}).get("Homepage", "")
YOUTUBE_URL_REGEX = r"^((?:https?:)?\/\/)?((?:www|m)\.)?((?:youtube(-nocookie)?\.com|youtu.be))(\/(?:[\w\-]+\?v=|embed\/|v\/)?)([\w\-]+)(\S+)?$"
NOTICE = f"""
{APP_NAME}, {setupcfg.get("description", "") if AUTHOR else ""}
GNU General Public License v3 — {YEAR} {AUTHOR}

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""

with open(Path(__file__).parents[1] / "LICENSE", encoding="utf-8") as f:
    LICENSE_TEXT = f.read()
LICENSE = re.split("How to Apply These Terms to Your New Programs", LICENSE_TEXT)[0]
