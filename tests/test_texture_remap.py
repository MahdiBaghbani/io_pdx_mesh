"""Texture remapper unit tests.

Run from the repo root with:
python -m unittest discover -s tests -p "test_*.py"
"""

import json
import tempfile
import unittest
import xml.etree.ElementTree as Xml
from pathlib import Path

from texture_remap import (
    collect_mesh_files,
    load_remap_config,
    remap_basename,
    remap_mesh_tree,
)


class TextureRemapTests(unittest.TestCase):
    def _load_config(self, payload):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "remap.json"
            config_path.write_text(json.dumps(payload), encoding="utf-8")
            return load_remap_config(config_path)

    def _build_mesh_tree(self):
        root_xml = Xml.Element("File")
        root_xml.set("pdxasset", [1, 0])

        object_xml = Xml.SubElement(root_xml, "object")
        shape_xml = Xml.SubElement(object_xml, "shape")
        mesh_xml = Xml.SubElement(shape_xml, "mesh")
        mesh_xml.set("p", [1.0, 2.0, 3.0])

        material_xml = Xml.SubElement(mesh_xml, "material")
        material_xml.set("shader", ["pdxmesh_standard"])
        material_xml.set("diff", ["old_diff.dds"])
        material_xml.set("n", ["old_n.dds"])
        material_xml.set("spec", ["old_spec.dds"])

        return root_xml, mesh_xml, material_xml

    def test_exact_mapping_takes_precedence_over_rules(self):
        config = self._load_config(
            {
                "version": 1,
                "exact": {"diff|old_diff.dds": "exact_diff.dds"},
                "rules": [
                    {
                        "slot": "diff",
                        "match": "^old_diff\\.dds$",
                        "replace": "rule_diff.dds",
                    }
                ],
            }
        )

        self.assertEqual(
            remap_basename("diff", "old_diff.dds", config),
            ("exact_diff.dds", "exact"),
        )

    def test_rules_are_applied_in_order(self):
        config = self._load_config(
            {
                "version": 1,
                "exact": {},
                "rules": [
                    {
                        "slot": "diff",
                        "match": "^old_.*\\.dds$",
                        "replace": "first_match.dds",
                    },
                    {
                        "slot": "diff",
                        "match": "^old_.*\\.dds$",
                        "replace": "second_match.dds",
                    },
                ],
            }
        )

        self.assertEqual(
            remap_basename("diff", "old_diff.dds", config),
            ("first_match.dds", "rule"),
        )

    def test_slot_aware_rules_do_not_cross_apply(self):
        config = self._load_config(
            {
                "version": 1,
                "exact": {},
                "rules": [
                    {
                        "slot": "diff",
                        "match": "^old_n\\.dds$",
                        "replace": "wrong_slot.dds",
                    }
                ],
            }
        )

        self.assertEqual(
            remap_basename("n", "old_n.dds", config),
            ("old_n.dds", "unchanged"),
        )

    def test_remap_output_is_forced_to_basename_only(self):
        config = self._load_config(
            {
                "version": 1,
                "exact": {"diff|old_diff.dds": "textures\\ships/new_diff.dds"},
                "rules": [],
            }
        )

        self.assertEqual(
            remap_basename("diff", "old_diff.dds", config),
            ("new_diff.dds", "exact"),
        )

    def test_non_latin1_output_is_reported_and_tree_is_left_unchanged(self):
        root_xml, _, material_xml = self._build_mesh_tree()
        config = self._load_config(
            {
                "version": 1,
                "exact": {"diff|old_diff.dds": "bad_\u2603.dds"},
                "rules": [],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            report = remap_mesh_tree(
                root_xml,
                config,
                search_roots=[tmpdir],
                recursive=False,
                allow_missing_targets=True,
            )

        self.assertFalse(report.can_apply)
        self.assertEqual(material_xml.get("diff"), ["old_diff.dds"])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("Latin-1", report.errors[0].message)

    def test_remap_mesh_tree_updates_only_target_texture_slots(self):
        root_xml, mesh_xml, material_xml = self._build_mesh_tree()
        config = self._load_config(
            {
                "version": 1,
                "exact": {
                    "diff|old_diff.dds": "textures/new_diff.dds",
                },
                "rules": [
                    {
                        "slot": "spec",
                        "match": "^old_spec\\.dds$",
                        "replace": "new_spec.dds",
                    }
                ],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "new_diff.dds").write_bytes(b"diff")
            (tmpdir_path / "new_spec.dds").write_bytes(b"spec")

            report = remap_mesh_tree(
                root_xml,
                config,
                search_roots=[tmpdir_path],
                recursive=False,
                allow_missing_targets=False,
            )

        self.assertTrue(report.can_apply)
        self.assertEqual([change.slot for change in report.changes], ["diff", "spec"])
        self.assertTrue(all(change.applied for change in report.changes))
        self.assertEqual(material_xml.get("shader"), ["pdxmesh_standard"])
        self.assertEqual(material_xml.get("diff"), ["new_diff.dds"])
        self.assertEqual(material_xml.get("n"), ["old_n.dds"])
        self.assertEqual(material_xml.get("spec"), ["new_spec.dds"])
        self.assertEqual(mesh_xml.get("p"), [1.0, 2.0, 3.0])

    def test_missing_target_is_an_error_by_default(self):
        root_xml, _, material_xml = self._build_mesh_tree()
        config = self._load_config(
            {
                "version": 1,
                "exact": {"diff|old_diff.dds": "missing_diff.dds"},
                "rules": [],
            }
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            report = remap_mesh_tree(
                root_xml,
                config,
                search_roots=[tmpdir],
                recursive=False,
                allow_missing_targets=False,
            )

        self.assertFalse(report.can_apply)
        self.assertEqual(material_xml.get("diff"), ["old_diff.dds"])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("missing_diff.dds", report.errors[0].message)


class CollectMeshFilesTests(unittest.TestCase):
    def test_collect_mesh_files_is_sorted_and_recursive(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (tmpdir_path / "b.mesh").write_bytes(b"")
            (tmpdir_path / "a.mesh").write_bytes(b"")
            nested_dir = tmpdir_path / "nested"
            nested_dir.mkdir()
            (nested_dir / "c.mesh").write_bytes(b"")
            (nested_dir / "ignore.anim").write_bytes(b"")

            mesh_files = collect_mesh_files(tmpdir_path)

        self.assertEqual(
            [path.relative_to(tmpdir_path).as_posix() for path in mesh_files],
            ["a.mesh", "b.mesh", "nested/c.mesh"],
        )


if __name__ == "__main__":
    unittest.main()
