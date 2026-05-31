"""
IO PDX Mesh Python module.
Collection of shared library functions and constants.

author : ross-g
"""

import functools
import logging
import re

PDX_SHADER = "shader"
PDX_ANIMATION = "animation"
PDX_IGNOREJOINT = "pdxIgnoreJoint"
PDX_MESHINDEX = "meshindex"
PDX_MAXSKININFS = 4
PDX_MAXUVSETS = 4

PDX_DECIMALPTS = 5
PDX_ROUND_ROT = 4
PDX_ROUND_TRANS = 3
PDX_ROUND_SCALE = 2

LOD_PATTERN = r".*_?LOD_?(?P<level>\d)"  # allow LODX or LOD_X, with or without any kind of prefix
LOCATOR_NAME_ALLOWED_CHARS = {"_", "-"}
LOCATOR_NAME_MAX_LENGTH = 63
LOCATOR_NAME_FALLBACK = "locator"


def get_lod_level(*names):
    for name in names:
        lod_match = re.match(LOD_PATTERN, name, re.IGNORECASE)
        if lod_match:
            return int(lod_match.group("level"))


def _is_valid_export_locator_char(char):
    if char == "\x00" or ord(char) > 255:
        return False

    return char.isalnum() or char in LOCATOR_NAME_ALLOWED_CHARS


def _is_valid_export_locator_first_char(char):
    return char == "_" or (ord(char) <= 255 and char.isalpha())


def sanitize_export_locator_name(name, fallback=LOCATOR_NAME_FALLBACK, max_length=LOCATOR_NAME_MAX_LENGTH):
    clean_name = str(name or "").strip()
    clean_name = clean_name.replace(":", "_").replace("|", "_")

    sanitized_chars = []
    for char in clean_name:
        sanitized_chars.append(char if _is_valid_export_locator_char(char) else "_")

    clean_name = re.sub(r"_+", "_", "".join(sanitized_chars))
    if not clean_name or not clean_name.strip("_"):
        clean_name = fallback

    if not _is_valid_export_locator_first_char(clean_name[0]):
        clean_name = f"{fallback}_{clean_name}"

    return clean_name[:max_length]


def deduplicate_export_locator_names(names, fallback=LOCATOR_NAME_FALLBACK, max_length=LOCATOR_NAME_MAX_LENGTH):
    unique_names = []
    used_names = set()

    for name in names:
        base_name = sanitize_export_locator_name(name, fallback=fallback, max_length=max_length)
        unique_name = base_name
        duplicate_index = 1

        while unique_name in used_names:
            suffix = f"-{duplicate_index:03d}"
            suffix_base = base_name[: max_length - len(suffix)]
            unique_name = f"{suffix_base}{suffix}"
            duplicate_index += 1

        used_names.add(unique_name)
        unique_names.append(unique_name)

    return unique_names


def _selfcheck_export_locator_names():
    sanitizer_cases = [
        ("   ", "locator"),
        ("rig:locator", "rig_locator"),
        ("root|locator", "root_locator"),
        ("漢字", "locator"),
        ("1locator", "locator_1locator"),
        ("  ns:bébé|ctrl  ", "ns_bébé_ctrl"),
    ]

    for original_name, expected_name in sanitizer_cases:
        sanitized_name = sanitize_export_locator_name(original_name)
        assert sanitized_name == expected_name, (original_name, sanitized_name, expected_name)

    long_name = "A" * 80
    truncated_name = sanitize_export_locator_name(long_name)
    assert truncated_name == "A" * LOCATOR_NAME_MAX_LENGTH
    assert len(truncated_name) == LOCATOR_NAME_MAX_LENGTH

    duplicate_names = deduplicate_export_locator_names(["漢字", "漢字"])
    assert duplicate_names == ["locator", "locator-001"]
    assert all(len(name) <= LOCATOR_NAME_MAX_LENGTH for name in duplicate_names)

    deduped_long_names = deduplicate_export_locator_names([long_name, long_name])
    assert deduped_long_names[0] == truncated_name
    assert deduped_long_names[1].endswith("-001")
    assert len(deduped_long_names[1]) <= LOCATOR_NAME_MAX_LENGTH


def allow_debug_logging(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        debug_enabled = kwargs.get("debug_mode", False)

        # enabled debug logging level
        if debug_enabled:
            root_level = logging.root.level
            io_pdx_level = logging.getLogger("io_pdx").level
            logging.root.setLevel(logging.DEBUG)
            logging.getLogger("io_pdx").setLevel(logging.DEBUG)

        value = func(*args, **kwargs)

        # restore logging level
        if debug_enabled:
            logging.root.setLevel(root_level)
            logging.getLogger("io_pdx").setLevel(io_pdx_level)

        return value

    return wrapper
