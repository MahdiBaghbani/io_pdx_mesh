import json
import os
import re
from pathlib import Path


TEXTURE_SLOTS = ("diff", "n", "spec")


class RemapRule(object):
    def __init__(self, slot, pattern, replace):
        self.slot = slot
        self.pattern = pattern
        self.replace = replace


class RemapConfig(object):
    def __init__(self, exact, rules):
        self.exact = exact
        self.rules = rules


class RemapChange(object):
    def __init__(self, material_index, slot, old_basename, new_basename, method):
        self.material_index = material_index
        self.slot = slot
        self.old_basename = old_basename
        self.new_basename = new_basename
        self.method = method
        self.applied = False


class RemapIssue(object):
    def __init__(self, material_index, slot, old_basename, new_basename, message):
        self.material_index = material_index
        self.slot = slot
        self.old_basename = old_basename
        self.new_basename = new_basename
        self.message = message


class RemapReport(object):
    def __init__(self):
        self.material_count = 0
        self.changes = []
        self.warnings = []
        self.errors = []

    @property
    def changed(self):
        return bool(self.changes)

    @property
    def can_apply(self):
        return not self.errors


def _basename_only(value):
    return str(value).replace("\\", "/").rsplit("/", 1)[-1]


def _read_attribute_string(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return ""
        return str(value[0])
    return str(value)


def _validate_slot(slot):
    if slot not in TEXTURE_SLOTS:
        raise ValueError(
            "Unsupported texture slot '{}' in remap config. "
            "Expected one of: {}.".format(slot, ", ".join(TEXTURE_SLOTS))
        )


def _ensure_latin1(value):
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as err:
        raise ValueError(
            "Remapped texture name '{}' is not Latin-1 encodable.".format(value)
        ) from err


def _target_exists(basename, search_roots, recursive):
    for root in search_roots:
        root = Path(root)
        if not root.exists() or not root.is_dir():
            continue

        direct_match = root / basename
        if direct_match.is_file():
            return True

        if not recursive:
            continue

        for current_root, dirnames, filenames in os.walk(str(root)):
            dirnames.sort()
            filenames.sort()
            if basename in filenames:
                return True

    return False


def load_remap_config(path):
    with Path(path).open("rt", encoding="utf-8") as fp:
        payload = json.load(fp)

    if not isinstance(payload, dict):
        raise ValueError("Remap config must contain a top-level JSON object.")

    version = payload.get("version")
    if version != 1:
        raise ValueError(
            "Unsupported remap config version '{}'. Expected version 1.".format(
                version
            )
        )

    exact_payload = payload.get("exact", {})
    if not isinstance(exact_payload, dict):
        raise ValueError("'exact' must be a JSON object.")

    exact = {}
    for raw_key, raw_value in exact_payload.items():
        if not isinstance(raw_key, str):
            raise ValueError("Exact remap keys must be strings.")
        if not isinstance(raw_value, str):
            raise ValueError(
                "Exact remap value for '{}' must be a string.".format(raw_key)
            )
        if "|" not in raw_key:
            raise ValueError(
                "Exact remap key '{}' must use the format 'slot|basename'.".format(
                    raw_key
                )
            )

        slot, old_basename = raw_key.split("|", 1)
        _validate_slot(slot)

        normalized_key = (slot, _basename_only(old_basename))
        if normalized_key in exact:
            raise ValueError(
                "Duplicate exact remap key after basename normalization: "
                "'{}|{}'.".format(normalized_key[0], normalized_key[1])
            )

        exact[normalized_key] = raw_value

    rules_payload = payload.get("rules", [])
    if not isinstance(rules_payload, list):
        raise ValueError("'rules' must be a JSON array.")

    rules = []
    for index, raw_rule in enumerate(rules_payload):
        if not isinstance(raw_rule, dict):
            raise ValueError("Rule {} must be a JSON object.".format(index))

        slot = raw_rule.get("slot")
        match = raw_rule.get("match")
        replace = raw_rule.get("replace")

        if not isinstance(slot, str):
            raise ValueError("Rule {} is missing a string 'slot'.".format(index))
        if not isinstance(match, str):
            raise ValueError("Rule {} is missing a string 'match'.".format(index))
        if not isinstance(replace, str):
            raise ValueError(
                "Rule {} is missing a string 'replace'.".format(index)
            )

        _validate_slot(slot)

        try:
            pattern = re.compile(match)
        except re.error as err:
            raise ValueError(
                "Rule {} has an invalid regex '{}': {}.".format(
                    index, match, err
                )
            ) from err

        rules.append(RemapRule(slot, pattern, replace))

    return RemapConfig(exact=exact, rules=rules)


def remap_basename(slot, old_basename, config):
    _validate_slot(slot)
    normalized_old = _basename_only(old_basename)

    exact_key = (slot, normalized_old)
    if exact_key in config.exact:
        return _basename_only(config.exact[exact_key]), "exact"

    for rule in config.rules:
        if rule.slot != slot:
            continue
        if rule.pattern.search(normalized_old):
            remapped = rule.pattern.sub(rule.replace, normalized_old)
            return _basename_only(remapped), "rule"

    return normalized_old, "unchanged"


def remap_mesh_tree(
    root_xml,
    config,
    *,
    search_roots,
    recursive=False,
    allow_missing_targets=False
):
    report = RemapReport()
    search_roots = [Path(root) for root in search_roots]

    materials = list(root_xml.iter("material"))
    report.material_count = len(materials)

    planned_changes = []

    for material_index, material_xml in enumerate(materials):
        for slot in TEXTURE_SLOTS:
            current_attr = material_xml.get(slot)
            if current_attr is None:
                continue

            current_value = _read_attribute_string(current_attr)
            if current_value is None:
                continue

            old_basename = _basename_only(current_value)
            new_basename, method = remap_basename(slot, old_basename, config)
            if method == "unchanged" or new_basename == old_basename:
                continue

            change = RemapChange(
                material_index=material_index,
                slot=slot,
                old_basename=old_basename,
                new_basename=new_basename,
                method=method,
            )
            report.changes.append(change)
            planned_changes.append((material_xml, change))

            if not new_basename:
                report.errors.append(
                    RemapIssue(
                        material_index,
                        slot,
                        old_basename,
                        new_basename,
                        "Remapped texture name is empty after basename normalization.",
                    )
                )
                continue

            try:
                _ensure_latin1(new_basename)
            except ValueError as err:
                report.errors.append(
                    RemapIssue(
                        material_index,
                        slot,
                        old_basename,
                        new_basename,
                        str(err),
                    )
                )
                continue

            if not _target_exists(new_basename, search_roots, recursive):
                search_root_text = ", ".join(str(root) for root in search_roots)
                issue = RemapIssue(
                    material_index,
                    slot,
                    old_basename,
                    new_basename,
                    "Remapped target '{}' was not found under search roots: {}.".format(
                        new_basename,
                        search_root_text,
                    ),
                )
                if allow_missing_targets:
                    report.warnings.append(issue)
                else:
                    report.errors.append(issue)

    if report.errors:
        return report

    for material_xml, change in planned_changes:
        material_xml.set(change.slot, [change.new_basename])
        change.applied = True

    return report


def collect_mesh_files(inpath):
    inpath = Path(inpath)
    if not inpath.exists():
        raise ValueError("Input path does not exist: '{}'.".format(inpath))

    if inpath.is_file():
        if inpath.suffix.lower() != ".mesh":
            raise ValueError(
                "Input file must be a .mesh file: '{}'.".format(inpath)
            )
        return [inpath]

    mesh_files = [path for path in inpath.rglob("*.mesh") if path.is_file()]
    return sorted(mesh_files, key=lambda path: path.as_posix())
