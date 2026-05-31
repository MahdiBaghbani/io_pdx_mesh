"""
IO PDX Mesh Python module.
This is designed to allow tools to check if they are out of date or not and supply a download link to the latest.

author : ross-g
"""

import json
import logging
from datetime import date, datetime
from os.path import splitext
from time import perf_counter
from urllib.request import Request, URLError, urlopen

from . import IO_PDX_INFO, IO_PDX_SETTINGS

UPDATER_LOG = logging.getLogger("io_pdx.updater")


""" ====================================================================================================================
    Helper functions.
==================================================================================================================== """


class Github_API(object):
    """
    Handles connection to Githubs API to get some data on releases for this repository.
    """

    API_URL = "https://api.github.com"

    def __init__(self, owner, repo):
        self.api = self.API_URL
        self.owner = owner
        self.repo = repo
        self.args = {"owner": self.owner, "repo": self.repo, "api": self.api}

        self.AT_LATEST = True
        self.CURRENT_VERSION = IO_PDX_INFO["current_git_tag"]
        self.LATEST_VERSION = self.CURRENT_VERSION
        self.LATEST_RELEASE = "https://github.com/{owner}/{repo}/releases/latest".format(**self.args)
        self.LATEST_RELEASE_DATA = {}
        self.LATEST_NOTES = ""
        self.LATEST_URL = {}
        self.refresh()

    @staticmethod
    def get_data(url, time=1.0):
        req = Request(url)
        result = urlopen(req, timeout=time)
        result_str = result.read()
        result.close()

        return json.JSONDecoder().decode(result_str.decode())

    @staticmethod
    def _coerce_latest_url(value):
        if not isinstance(value, dict):
            return {}

        return {str(key): url.strip() for key, url in value.items() if isinstance(url, str) and url.strip()}

    @staticmethod
    def _coerce_latest_notes(value):
        return value if isinstance(value, str) else ""

    @staticmethod
    def _version_key(value):
        if value in (None, ""):
            return ()

        version = str(value).strip().lstrip("vV").split("-", 1)[0]
        if not version:
            return ()

        parts = []
        for part in version.split("."):
            if not part.isdigit():
                return ()
            parts.append(int(part))

        while len(parts) > 1 and parts[-1] == 0:
            parts.pop()

        return tuple(parts)

    def _load_cached_release(self):
        cached_version = IO_PDX_SETTINGS.github_latest_version
        self.LATEST_VERSION = self.CURRENT_VERSION if cached_version in (None, "") else cached_version
        self.LATEST_URL = self._coerce_latest_url(IO_PDX_SETTINGS.github_latest_url)
        self.LATEST_NOTES = self._coerce_latest_notes(IO_PDX_SETTINGS.github_latest_notes)
        self.LATEST_RELEASE_DATA = {}

    def _clear_cached_release(self):
        self.LATEST_VERSION = self.CURRENT_VERSION
        self.LATEST_URL = {}
        self.LATEST_NOTES = ""
        self.LATEST_RELEASE_DATA = {}

        IO_PDX_SETTINGS.github_latest_version = self.LATEST_VERSION
        IO_PDX_SETTINGS.github_latest_url = {}
        IO_PDX_SETTINGS.github_latest_notes = ""
        IO_PDX_SETTINGS.last_update_check = f"{date.today()}"

    def _apply_latest_release(self, latest):
        self.LATEST_RELEASE_DATA = latest if isinstance(latest, dict) else {}
        latest_tag = latest.get("tag_name")
        self.LATEST_VERSION = self.CURRENT_VERSION if latest_tag in (None, "") else latest_tag
        assets = latest.get("assets")
        if not isinstance(assets, list):
            assets = []
        self.LATEST_URL = self._coerce_latest_url(
            {
                splitext(asset["name"])[0].split("-")[0]: asset["browser_download_url"]
                for asset in assets
                if isinstance(asset, dict)
                and isinstance(asset.get("name"), str)
                and isinstance(asset.get("browser_download_url"), str)
            }
        )

        published_at = latest.get("published_at", "")
        release_date = published_at.split("T")[0] if isinstance(published_at, str) and published_at else ""
        release_notes = [f"Release version: {self.LATEST_VERSION}"]
        if release_date:
            release_notes.insert(0, release_date)

        body = latest.get("body")
        if isinstance(body, str) and body:
            release_notes.append(body)

        self.LATEST_NOTES = "\r\n".join(release_notes)

    def _update_at_latest(self):
        current_key = self._version_key(self.CURRENT_VERSION)
        latest_key = self._version_key(self.LATEST_VERSION)

        if not latest_key:
            self.AT_LATEST = True
        elif current_key and latest_key:
            self.AT_LATEST = current_key == latest_key
        else:
            self.AT_LATEST = str(self.CURRENT_VERSION) == str(self.LATEST_VERSION)

    def get_download_url(self, app_name):
        app_key = app_name.strip() if isinstance(app_name, str) else ""
        generic_key = self.repo.strip() if isinstance(self.repo, str) else ""

        if isinstance(self.LATEST_URL, dict):
            for key in [app_key, generic_key]:
                if not key:
                    continue

                url = self.LATEST_URL.get(key)
                if isinstance(url, str):
                    url = url.strip()
                    if url:
                        return url

        release_url = self.LATEST_RELEASE.strip() if isinstance(self.LATEST_RELEASE, str) else ""
        return release_url

    def refresh(self, force=False):
        recheck = True

        # only check for updates once per day
        last_check_date = IO_PDX_SETTINGS.last_update_check
        if last_check_date is not None:
            try:
                recheck = date.today() > datetime.strptime(last_check_date, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                recheck = True

        if recheck or force:
            start = perf_counter()

            # get latest release data
            releases_url = "{api}/repos/{owner}/{repo}/releases".format(**self.args)

            try:
                release_list = self.get_data(releases_url)
                if release_list:
                    latest = release_list[0]
                    self._apply_latest_release(latest)

                    # cache data to settings
                    IO_PDX_SETTINGS.github_latest_version = self.LATEST_VERSION
                    IO_PDX_SETTINGS.github_latest_url = self.LATEST_URL
                    IO_PDX_SETTINGS.github_latest_notes = self.LATEST_NOTES
                    IO_PDX_SETTINGS.last_update_check = f"{date.today()}"
                    UPDATER_LOG.info(f"Checked for update. ({perf_counter() - start:0.4f} sec)")
                else:
                    UPDATER_LOG.warning("Found no releases during update check.")
                    self._clear_cached_release()
            except URLError as err:
                UPDATER_LOG.warning(f"Unable to check for update. ({err.reason})")
                self._load_cached_release()
            except Exception as err:
                UPDATER_LOG.error(f"Failed during update check. ({err})")
                self._load_cached_release()

        else:
            # used cached release data in settings
            self._load_cached_release()
            UPDATER_LOG.info("Skipped update check. (already ran today)")

        self._update_at_latest()


github = Github_API(owner=IO_PDX_INFO["maintainer"], repo=IO_PDX_INFO["id"])
