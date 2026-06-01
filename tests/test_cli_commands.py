"""CLI command registration tests.

Run from the repo root with:
python -m unittest discover -s tests -p "test_*.py"
"""

import importlib
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as Xml
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO_ROOT.parent

if str(PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_PARENT))

cli_main = importlib.import_module("io_pdx_mesh.__main__")
CliRunner = importlib.import_module("io_pdx_mesh.external.click.testing").CliRunner


class CliCommandRegistrationTests(unittest.TestCase):
    def test_help_lists_texture_remap_command_with_underscore_and_dash(self):
        result = subprocess.run(
            [sys.executable, "-m", "io_pdx_mesh", "--help"],
            cwd=PACKAGE_PARENT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("remap_textures", result.stdout)
        self.assertIn("remap-textures", result.stdout)

    def test_underscore_texture_remap_command_is_invokable(self):
        result = subprocess.run(
            [sys.executable, "-m", "io_pdx_mesh", "remap_textures", "--help"],
            cwd=PACKAGE_PARENT,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("--config", result.stdout)
        self.assertIn("--search-root", result.stdout)
        self.assertIn("--best-effort", result.stdout)
        normalized_help = " ".join(result.stdout.split())
        self.assertIn(
            "Write remapped meshes instead of running a dry run.",
            normalized_help,
        )
        self.assertIn("partial output may remain", normalized_help)
        self.assertIn("overwrite an existing backup file", normalized_help)
        self.assertIn("Warn instead of failing", normalized_help)
        self.assertIn("Extra directory to search", normalized_help)
        self.assertIn("Search each texture root recursively", normalized_help)


class TextureRemapCliIntegrationTests(unittest.TestCase):
    def _write_config(self, root, payload):
        config_path = root / "remap.json"
        config_path.write_text(json.dumps(payload), encoding="utf-8")
        return config_path

    def _build_mesh_tree(self, slot, basename):
        root_xml = Xml.Element("File")
        object_xml = Xml.SubElement(root_xml, "object")
        shape_xml = Xml.SubElement(object_xml, "shape")
        mesh_xml = Xml.SubElement(shape_xml, "mesh")
        material_xml = Xml.SubElement(mesh_xml, "material")
        material_xml.set("shader", ["pdxmesh_standard"])
        material_xml.set(slot, [basename])
        return root_xml

    def _make_read_stub(self, mesh_specs, read_calls):
        def stub(mesh_path):
            mesh_path = Path(mesh_path)
            read_calls.append(mesh_path.name)
            slot, basename = mesh_specs[mesh_path.name]
            return self._build_mesh_tree(slot, basename)

        return stub

    def _make_write_stub(self, write_calls):
        def stub(outpath, root_xml):
            outpath = Path(outpath)
            material_xml = next(root_xml.iter("material"))
            slot_values = {
                slot: material_xml.get(slot)
                for slot in ("diff", "n", "spec")
                if material_xml.get(slot) is not None
            }
            write_calls.append(outpath)
            outpath.write_bytes(
                b"stub:"
                + json.dumps(slot_values, sort_keys=True).encode("utf-8")
            )

        return stub

    def _write_mesh_state(self, mesh_path, slot, basename):
        mesh_path.write_text(
            json.dumps({"slot": slot, "basename": basename}),
            encoding="utf-8",
        )

    def _read_mesh_state(self, mesh_path):
        return json.loads(mesh_path.read_text(encoding="utf-8"))

    def _make_stateful_read_stub(self, read_calls):
        def stub(mesh_path):
            mesh_path = Path(mesh_path)
            read_calls.append(mesh_path.name)
            state = self._read_mesh_state(mesh_path)
            return self._build_mesh_tree(state["slot"], state["basename"])

        return stub

    def _make_stateful_write_stub(self, write_calls, fail_on_call=None):
        def stub(outpath, root_xml):
            outpath = Path(outpath)
            write_calls.append(outpath)
            if fail_on_call is not None and len(write_calls) == fail_on_call:
                raise RuntimeError("forced write failure")

            material_xml = next(root_xml.iter("material"))
            for slot in ("diff", "n", "spec"):
                value = material_xml.get(slot)
                if value is None:
                    continue

                if isinstance(value, (list, tuple)):
                    basename = value[0]
                else:
                    basename = value

                self._write_mesh_state(outpath, slot, basename)
                return

            raise AssertionError("Expected at least one texture slot on material.")

        return stub

    def test_remap_apply_is_all_or_nothing_by_default(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            mesh_root.mkdir()
            good_mesh = mesh_root / "a.mesh"
            bad_mesh = mesh_root / "b.mesh"
            good_mesh.write_bytes(b"good-original")
            bad_mesh.write_bytes(b"bad-original")
            (mesh_root / "new_diff.dds").write_bytes(b"diff")
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {
                        "diff|old_diff.dds": "new_diff.dds",
                        "spec|old_spec.dds": "missing_spec.dds",
                    },
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []
            mesh_specs = {
                "a.mesh": ("diff", "old_diff.dds"),
                "b.mesh": ("spec", "old_spec.dds"),
            }

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_read_stub(mesh_specs, read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_write_stub(write_calls),
            ):
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--apply",
                    ],
                )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn(
                "ABORT no mesh files were written because preflight found blocking errors.",
                result.output,
            )
            self.assertEqual(read_calls, ["a.mesh", "b.mesh"])
            self.assertEqual(write_calls, [])
            self.assertEqual(good_mesh.read_bytes(), b"good-original")
            self.assertEqual(bad_mesh.read_bytes(), b"bad-original")
            self.assertFalse((mesh_root / "a.mesh.bak").exists())
            self.assertFalse((mesh_root / "b.mesh.bak").exists())

    def test_remap_apply_rolls_back_on_write_time_failure_by_default(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            mesh_root.mkdir()
            first_mesh = mesh_root / "a.mesh"
            second_mesh = mesh_root / "b.mesh"
            self._write_mesh_state(first_mesh, "diff", "old_diff.dds")
            self._write_mesh_state(second_mesh, "spec", "old_spec.dds")
            original_first = first_mesh.read_bytes()
            original_second = second_mesh.read_bytes()
            (mesh_root / "new_diff.dds").write_bytes(b"diff")
            (mesh_root / "new_spec.dds").write_bytes(b"spec")
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {
                        "diff|old_diff.dds": "new_diff.dds",
                        "spec|old_spec.dds": "new_spec.dds",
                    },
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_stateful_read_stub(read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_stateful_write_stub(
                    write_calls,
                    fail_on_call=2,
                ),
            ):
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--apply",
                    ],
                )

            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(read_calls, ["a.mesh", "b.mesh"])
            self.assertEqual(len(write_calls), 2)
            self.assertEqual([path.parent for path in write_calls], [mesh_root, mesh_root])
            self.assertTrue(write_calls[0].name.startswith("a.mesh."))
            self.assertTrue(write_calls[1].name.startswith("b.mesh."))
            self.assertIn(
                "ABORT rolled back earlier writes after a write-time failure.",
                result.output,
            )
            self.assertIn("written=0", result.output)
            self.assertEqual(first_mesh.read_bytes(), original_first)
            self.assertEqual(second_mesh.read_bytes(), original_second)
            self.assertFalse((mesh_root / "a.mesh.bak").exists())
            self.assertFalse((mesh_root / "b.mesh.bak").exists())

    def test_remap_apply_is_idempotent_when_already_remapped(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_path = tmpdir_path / "ship.mesh"
            self._write_mesh_state(mesh_path, "diff", "old_diff.dds")
            original_mesh = mesh_path.read_bytes()
            (tmpdir_path / "new_diff.dds").write_bytes(b"diff")
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {"diff|old_diff.dds": "new_diff.dds"},
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_stateful_read_stub(read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_stateful_write_stub(write_calls),
            ):
                first_result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_path),
                        "--config",
                        str(config_path),
                        "--apply",
                    ],
                )
                second_result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_path),
                        "--config",
                        str(config_path),
                        "--apply",
                    ],
                )

            backup_path = tmpdir_path / "ship.mesh.bak"
            self.assertEqual(first_result.exit_code, 0, msg=first_result.output)
            self.assertEqual(second_result.exit_code, 0, msg=second_result.output)
            self.assertEqual(read_calls, ["ship.mesh", "ship.mesh"])
            self.assertEqual(len(write_calls), 1)
            self.assertIn("written=1", first_result.output)
            self.assertIn("written=0", second_result.output)
            self.assertEqual(self._read_mesh_state(mesh_path)["basename"], "new_diff.dds")
            self.assertTrue(backup_path.exists())
            self.assertEqual(backup_path.read_bytes(), original_mesh)

    def test_remap_rejects_nested_output_directory(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            mesh_root.mkdir()
            (mesh_root / "ship.mesh").write_bytes(b"mesh")
            config_path = self._write_config(
                tmpdir_path,
                {"version": 1, "exact": {}, "rules": []},
            )

            with mock.patch.object(cli_main, "read_meshfile") as read_meshfile:
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--outpath",
                        str(mesh_root / "generated"),
                        "--apply",
                    ],
                )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn(
                "Output path must not be the input directory or a nested child",
                result.output,
            )
            read_meshfile.assert_not_called()

    def test_remap_outpath_rejects_preexisting_destination_before_writing(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            mesh_root.mkdir()
            first_mesh = mesh_root / "a.mesh"
            second_mesh = mesh_root / "b.mesh"
            first_mesh.write_bytes(b"first-original")
            second_mesh.write_bytes(b"second-original")
            (mesh_root / "new_diff.dds").write_bytes(b"diff")
            (mesh_root / "new_spec.dds").write_bytes(b"spec")
            out_root = tmpdir_path / "outputs"
            out_root.mkdir()
            existing_output = out_root / "a.mesh"
            existing_output.write_bytes(b"existing-output")
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {
                        "diff|old_diff.dds": "new_diff.dds",
                        "spec|old_spec.dds": "new_spec.dds",
                    },
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []
            mesh_specs = {
                "a.mesh": ("diff", "old_diff.dds"),
                "b.mesh": ("spec", "old_spec.dds"),
            }

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_read_stub(mesh_specs, read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_write_stub(write_calls),
            ):
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--outpath",
                        str(out_root),
                        "--apply",
                    ],
                )

            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(read_calls, ["a.mesh", "b.mesh"])
            self.assertEqual(write_calls, [])
            self.assertIn("Output file already exists", result.output)
            self.assertIn(
                "ABORT no mesh files were written because preflight found blocking errors.",
                result.output,
            )
            self.assertEqual(existing_output.read_bytes(), b"existing-output")
            self.assertFalse((out_root / "b.mesh").exists())

    def test_remap_outpath_rolls_back_on_write_time_failure_by_default(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            mesh_root.mkdir()
            first_mesh = mesh_root / "a.mesh"
            second_mesh = mesh_root / "b.mesh"
            self._write_mesh_state(first_mesh, "diff", "old_diff.dds")
            self._write_mesh_state(second_mesh, "spec", "old_spec.dds")
            (mesh_root / "new_diff.dds").write_bytes(b"diff")
            (mesh_root / "new_spec.dds").write_bytes(b"spec")
            out_root = tmpdir_path / "outputs"
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {
                        "diff|old_diff.dds": "new_diff.dds",
                        "spec|old_spec.dds": "new_spec.dds",
                    },
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_stateful_read_stub(read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_stateful_write_stub(
                    write_calls,
                    fail_on_call=2,
                ),
            ):
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--outpath",
                        str(out_root),
                        "--apply",
                    ],
                )

            first_output = out_root / "a.mesh"
            second_output = out_root / "b.mesh"
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(read_calls, ["a.mesh", "b.mesh"])
            self.assertEqual(len(write_calls), 2)
            self.assertEqual([path.parent for path in write_calls], [out_root, out_root])
            self.assertTrue(write_calls[0].name.startswith(f"{first_output.name}."))
            self.assertTrue(write_calls[1].name.startswith(f"{second_output.name}."))
            self.assertIn(
                "ABORT rolled back earlier writes after a write-time failure.",
                result.output,
            )
            self.assertIn("written=0", result.output)
            self.assertEqual(self._read_mesh_state(first_mesh)["basename"], "old_diff.dds")
            self.assertEqual(self._read_mesh_state(second_mesh)["basename"], "old_spec.dds")
            self.assertFalse(first_output.exists())
            self.assertFalse(second_output.exists())

    def test_force_backup_overwrite_controls_existing_backup_behavior(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_path = tmpdir_path / "ship.mesh"
            mesh_path.write_bytes(b"original-mesh")
            backup_path = tmpdir_path / "ship.mesh.bak"
            backup_path.write_bytes(b"existing-backup")
            (tmpdir_path / "new_diff.dds").write_bytes(b"diff")
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {"diff|old_diff.dds": "new_diff.dds"},
                    "rules": [],
                },
            )

            mesh_specs = {"ship.mesh": ("diff", "old_diff.dds")}

            blocked_reads = []
            blocked_writes = []
            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_read_stub(mesh_specs, blocked_reads),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_write_stub(blocked_writes),
            ):
                blocked_result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_path),
                        "--config",
                        str(config_path),
                        "--apply",
                    ],
                )

            self.assertNotEqual(blocked_result.exit_code, 0)
            self.assertIn("Backup file already exists", blocked_result.output)
            self.assertEqual(blocked_reads, ["ship.mesh"])
            self.assertEqual(blocked_writes, [])
            self.assertEqual(mesh_path.read_bytes(), b"original-mesh")
            self.assertEqual(backup_path.read_bytes(), b"existing-backup")

            forced_reads = []
            forced_writes = []
            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_read_stub(mesh_specs, forced_reads),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_write_stub(forced_writes),
            ):
                forced_result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_path),
                        "--config",
                        str(config_path),
                        "--apply",
                        "--force-backup-overwrite",
                    ],
                )

            self.assertEqual(forced_result.exit_code, 0, msg=forced_result.output)
            self.assertEqual(forced_reads, ["ship.mesh"])
            self.assertEqual(len(forced_writes), 1)
            self.assertTrue(mesh_path.read_bytes().startswith(b"stub:"))
            self.assertEqual(backup_path.read_bytes(), b"original-mesh")

    def test_remap_creates_missing_output_parent_directories(self):
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            mesh_root = tmpdir_path / "meshes"
            nested_root = mesh_root / "nested"
            nested_root.mkdir(parents=True)
            mesh_path = nested_root / "ship.mesh"
            mesh_path.write_bytes(b"original-mesh")
            (nested_root / "new_diff.dds").write_bytes(b"diff")
            out_root = tmpdir_path / "outputs"
            config_path = self._write_config(
                tmpdir_path,
                {
                    "version": 1,
                    "exact": {"diff|old_diff.dds": "new_diff.dds"},
                    "rules": [],
                },
            )

            read_calls = []
            write_calls = []
            mesh_specs = {"ship.mesh": ("diff", "old_diff.dds")}

            with mock.patch.object(
                cli_main,
                "read_meshfile",
                side_effect=self._make_read_stub(mesh_specs, read_calls),
            ), mock.patch.object(
                cli_main,
                "write_meshfile",
                side_effect=self._make_write_stub(write_calls),
            ):
                result = runner.invoke(
                    cli_main.cli,
                    [
                        "remap_textures",
                        "--inpath",
                        str(mesh_root),
                        "--config",
                        str(config_path),
                        "--outpath",
                        str(out_root),
                        "--apply",
                    ],
                )

            written_mesh = out_root / "nested" / "ship.mesh"
            self.assertEqual(result.exit_code, 0, msg=result.output)
            self.assertEqual(read_calls, ["ship.mesh"])
            self.assertEqual(len(write_calls), 1)
            self.assertEqual(write_calls[0].parent, written_mesh.parent)
            self.assertTrue(write_calls[0].name.startswith(f"{written_mesh.name}."))
            self.assertTrue(written_mesh.exists())
            self.assertTrue(written_mesh.read_bytes().startswith(b"stub:"))


if __name__ == "__main__":
    unittest.main()
