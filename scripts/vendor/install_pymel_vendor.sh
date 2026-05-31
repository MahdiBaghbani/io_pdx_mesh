#!/usr/bin/env sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
CONFIG_FILE="$SCRIPT_DIR/vendor.env"
VENDOR_ROOT="$REPO_ROOT/vendor"
INSTALL_ROOT="$VENDOR_ROOT/pymel_root"
BACKUP_ROOT="${INSTALL_ROOT}.tmp"
WHEEL_PATH="$VENDOR_ROOT/pymel-wheel-download.tmp"
RESTORE_BACKUP=0
CREATED_INSTALL_ROOT=0

if [ ! -f "$CONFIG_FILE" ]; then
    echo "Missing config file: $CONFIG_FILE" >&2
    exit 1
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
else
    echo "python3 or python is required to extract the PyMEL wheel." >&2
    exit 1
fi

eval "$("$PYTHON_BIN" - "$CONFIG_FILE" <<'PY'
import os
import shlex
import sys

config_file = sys.argv[1]
config = {}

with open(config_file, "r", encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()

for key in ("PYMEL_OWNER", "PYMEL_REPO", "PYMEL_VERSION"):
    value = os.environ.get(key, config.get(key, "")).strip()
    if not value:
        raise SystemExit(f"Missing required value in environment or vendor.env: {key}")
    print(f"{key}={shlex.quote(value)}")
PY
)"

WHEEL_NAME="pymel-${PYMEL_VERSION}-py3-none-any.whl"
DOWNLOAD_URL="https://github.com/${PYMEL_OWNER}/${PYMEL_REPO}/releases/download/${PYMEL_VERSION}/${WHEEL_NAME}"

cleanup() {
    status=$?

    if [ "$status" -ne 0 ]; then
        echo "Install failed. Cleaning partial vendor directory." >&2
        if [ "$CREATED_INSTALL_ROOT" -eq 1 ]; then
            rm -rf "$INSTALL_ROOT"
        fi
        if [ "$RESTORE_BACKUP" -eq 1 ] && [ -d "$BACKUP_ROOT" ]; then
            mv "$BACKUP_ROOT" "$INSTALL_ROOT"
            echo "Restored previous vendor directory." >&2
        fi
    fi

    rm -f "$WHEEL_PATH"
    exit "$status"
}

trap cleanup EXIT INT TERM HUP

mkdir -p "$VENDOR_ROOT"

if [ -e "$BACKUP_ROOT" ]; then
    echo "Backup directory already exists: $BACKUP_ROOT" >&2
    echo "Remove or rename it, then retry." >&2
    exit 1
fi

if [ -e "$INSTALL_ROOT" ]; then
    mv "$INSTALL_ROOT" "$BACKUP_ROOT"
    RESTORE_BACKUP=1
fi

mkdir -p "$INSTALL_ROOT"
CREATED_INSTALL_ROOT=1

if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$DOWNLOAD_URL" -o "$WHEEL_PATH"
elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$WHEEL_PATH" "$DOWNLOAD_URL"
else
    echo "curl or wget is required to download the PyMEL wheel." >&2
    exit 1
fi

"$PYTHON_BIN" - "$WHEEL_PATH" "$INSTALL_ROOT" <<'PY'
import pathlib
import sys
import zipfile

wheel_path = pathlib.Path(sys.argv[1])
install_root = pathlib.Path(sys.argv[2])

with zipfile.ZipFile(wheel_path, "r") as wheel:
    wheel.extractall(install_root)
PY

if [ ! -d "$INSTALL_ROOT/pymel" ]; then
    echo "Install failed: extracted wheel did not contain a pymel package." >&2
    exit 1
fi

if [ "$RESTORE_BACKUP" -eq 1 ] && [ -d "$BACKUP_ROOT" ]; then
    rm -rf "$BACKUP_ROOT"
    RESTORE_BACKUP=0
fi

rm -f "$WHEEL_PATH"
trap - EXIT INT TERM HUP

echo "Vendored PyMEL installed to $INSTALL_ROOT"
