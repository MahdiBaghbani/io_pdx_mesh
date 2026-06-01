import json
import os
import shutil
import tempfile
from pathlib import Path

try:
    import xml.etree.cElementTree as Xml
except ImportError:
    import xml.etree.ElementTree as Xml

# vendored package imports

from .external import click
from .pdx_data import PDXData, PDXDataJSON, read_meshfile, write_meshfile
from .texture_remap import (
    collect_mesh_files,
    load_remap_config,
    remap_mesh_tree,
)


@click.group()
def cli():
    pass


@cli.command()
@click.option("-i", "--inpath", required=True, type=click.Path())
@click.option("-o", "--outpath", required=False, type=click.Path(), default=None)
@click.option("-f", "--format", "out_format", type=click.Choice(["txt", "json", "xml"]), default="")
def convert_to(inpath, outpath, out_format):
    files = []
    out_folder = None

    inpath = Path(inpath)
    # run on single file
    if inpath.is_file():
        try:
            out_filepath = Path(outpath)  # assumes outpath is a file (not folder)
        except TypeError:
            out_filepath = inpath.parent / inpath.name
        out_folder = out_filepath.parent
        files.append([inpath, out_filepath.with_suffix(f".{out_format}")])

    # run on whole directory, recursively
    elif inpath.is_dir():
        try:
            out_folder = Path(outpath)
        except TypeError:
            out_folder = inpath

        for ext in ["*.mesh", "*.anim"]:
            for fullpath in inpath.rglob(ext):
                files.append([fullpath, (out_folder / fullpath.relative_to(inpath)).with_suffix(f".{out_format}")])

    for i, (in_file, out_file) in enumerate(files):
        pdx_Xml = read_meshfile(f"{in_file}")
        pdx_Data = PDXData(pdx_Xml)
        if out_format:
            print(f"{i + 1}/{len(files)} : {in_file.relative_to(inpath.parent)} --> {out_file.relative_to(out_folder)}")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            if out_format == "txt":
                with open(f"{out_file}", "wt") as fp:
                    fp.write(f"{pdx_Data}\n")
            if out_format == "json":
                with open(f"{out_file}", "wt") as fp:
                    json.dump(pdx_Data, fp, indent=2, cls=PDXDataJSON)
            if out_format == "xml":
                tree = Xml.ElementTree(pdx_Xml)
                tree.write(f"{out_file}")
        else:
            print("-" * 120)
            print(f"{i + 1}/{len(files)} : {in_file.relative_to(inpath.parent)}", end="\n")
            print(f"{pdx_Data}")


def _display_mesh_path(mesh_path, inpath):
    if inpath.is_dir():
        return str(mesh_path.relative_to(inpath))
    return str(mesh_path)


def _build_output_path(mesh_path, inpath, outpath):
    if outpath is None:
        return mesh_path

    if inpath.is_dir():
        return outpath / mesh_path.relative_to(inpath)

    return outpath / mesh_path.name


def _build_backup_path(mesh_path, backup_suffix):
    return mesh_path.with_name(f"{mesh_path.name}{backup_suffix}")


def _is_same_or_nested_path(path, root):
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_output_root(inpath, outpath):
    if outpath is None or not inpath.is_dir():
        return

    resolved_inpath = inpath.resolve()
    resolved_outpath = outpath.resolve()
    if _is_same_or_nested_path(resolved_outpath, resolved_inpath):
        raise click.ClickException(
            "Output path must not be the input directory or a nested child when "
            "remapping a directory tree."
        )


def _validate_apply_destination(
    mesh_path,
    inpath,
    outpath,
    backup_suffix,
    force_backup_overwrite,
):
    if outpath is None:
        backup_path = _build_backup_path(mesh_path, backup_suffix)
        if backup_path == mesh_path:
            raise RuntimeError("Backup suffix must not produce the original mesh path.")
        if backup_path.exists() and not force_backup_overwrite:
            raise RuntimeError(
                f"Backup file already exists: {backup_path}. "
                "Use --force-backup-overwrite to replace it."
            )
        return mesh_path

    dest_path = _build_output_path(mesh_path, inpath, outpath)
    if dest_path.resolve() == mesh_path.resolve():
        raise RuntimeError(
            "Output directory mode must not overwrite the original mesh."
        )
    if dest_path.exists():
        raise RuntimeError(
            f"Output file already exists: {dest_path}. "
            "Choose a different --outpath or remove the file."
        )
    return dest_path


def _emit_remap_report(label, report):
    if report.errors:
        click.echo(
            f"ERROR {label} materials={report.material_count} "
            f"changes={len(report.changes)}"
        )
    elif report.changed:
        click.echo(
            f"REMAPPED {label} materials={report.material_count} "
            f"changes={len(report.changes)}"
        )
    else:
        click.echo(
            f"UNCHANGED {label} materials={report.material_count} changes=0"
        )

    for change in report.changes:
        click.echo(
            f"  {change.slot}: {change.old_basename} -> "
            f"{change.new_basename} ({change.method})"
        )

    for warning in report.warnings:
        click.echo(f"  warning: {warning.message}")

    for error in report.errors:
        click.echo(f"  error: {error.message}")


def _write_mesh_atomically(outpath, root_xml):
    outpath.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        dir=str(outpath.parent),
        prefix=f"{outpath.name}.",
        suffix=".tmp",
    )
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        write_meshfile(f"{temp_path}", root_xml)
        temp_path.replace(outpath)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_mesh_with_backup(mesh_path, root_xml, backup_suffix, force_backup_overwrite):
    backup_path = _build_backup_path(mesh_path, backup_suffix)
    backup_preexisting = backup_path.exists()
    if backup_path == mesh_path:
        raise RuntimeError("Backup suffix must not produce the original mesh path.")
    if backup_preexisting and not force_backup_overwrite:
        raise RuntimeError(
            f"Backup file already exists: {backup_path}. "
            "Use --force-backup-overwrite to replace it."
        )

    shutil.copy2(mesh_path, backup_path)
    try:
        _write_mesh_atomically(mesh_path, root_xml)
    except Exception:
        if backup_path.exists():
            shutil.copy2(backup_path, mesh_path)
        if not backup_preexisting and backup_path.exists():
            backup_path.unlink()
        raise

    return {
        "mode": "inplace",
        "mesh_path": mesh_path,
        "backup_path": backup_path,
        "backup_preexisting": backup_preexisting,
    }


def _write_mesh_to_output(dest_path, root_xml):
    dest_preexisting = dest_path.exists()
    try:
        _write_mesh_atomically(dest_path, root_xml)
    except Exception:
        if not dest_preexisting and dest_path.exists():
            dest_path.unlink()
        raise

    return {
        "mode": "outpath",
        "dest_path": dest_path,
        "dest_preexisting": dest_preexisting,
    }


def _rollback_completed_writes(completed_writes):
    rollback_errors = []

    for write_info in reversed(completed_writes):
        try:
            if write_info["mode"] == "inplace":
                backup_path = write_info["backup_path"]
                if backup_path.exists():
                    shutil.copy2(backup_path, write_info["mesh_path"])
                if not write_info["backup_preexisting"] and backup_path.exists():
                    backup_path.unlink()
                continue

            dest_path = write_info["dest_path"]
            if not write_info["dest_preexisting"] and dest_path.exists():
                dest_path.unlink()
        except Exception as err:  # noqa: BLE001
            rollback_errors.append((write_info, err))

    return rollback_errors


@cli.command()
@click.option(
    "-i",
    "--inpath",
    required=True,
    type=click.Path(exists=True),
)
@click.option(
    "-c",
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "-o",
    "--outpath",
    required=False,
    default=None,
    type=click.Path(file_okay=False),
)
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Write remapped meshes instead of running a dry run.",
)
@click.option(
    "--best-effort",
    is_flag=True,
    default=False,
    help=(
        "Continue writing other meshes after preflight or write-time failures; "
        "partial output may remain."
    ),
)
@click.option("--backup-suffix", default=".bak", show_default=True)
@click.option(
    "--force-backup-overwrite",
    is_flag=True,
    default=False,
    help="Allow in-place apply to overwrite an existing backup file.",
)
@click.option(
    "--allow-missing-targets",
    is_flag=True,
    default=False,
    help="Warn instead of failing when a mapped target texture is missing.",
)
@click.option(
    "--search-root",
    "search_roots",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Extra directory to search for target textures. May be passed multiple times.",
)
@click.option(
    "--search-recursive",
    is_flag=True,
    default=False,
    help="Search each texture root recursively instead of only the top level.",
)
def remap_textures(
    inpath,
    config_path,
    outpath,
    apply,
    best_effort,
    backup_suffix,
    force_backup_overwrite,
    allow_missing_targets,
    search_roots,
    search_recursive,
):
    inpath = Path(inpath)
    outpath = Path(outpath) if outpath is not None else None

    if apply and outpath is None and not backup_suffix:
        raise click.ClickException(
            "Backup suffix must not be empty for in-place writes."
        )

    _validate_output_root(inpath, outpath)

    try:
        config = load_remap_config(config_path)
        mesh_files = collect_mesh_files(inpath)
    except ValueError as err:
        raise click.ClickException(str(err))

    total_changes = 0
    total_warnings = 0
    files_changed = 0
    files_written = 0
    failed_files = []
    rollback_errors = []
    configured_search_roots = [Path(root) for root in search_roots]
    preflight_results = []

    for mesh_path in mesh_files:
        label = _display_mesh_path(mesh_path, inpath)

        try:
            root_xml = read_meshfile(f"{mesh_path}")
            active_search_roots = configured_search_roots
            if not active_search_roots:
                active_search_roots = [mesh_path.parent]

            report = remap_mesh_tree(
                root_xml,
                config,
                search_roots=active_search_roots,
                recursive=search_recursive,
                allow_missing_targets=allow_missing_targets,
            )

            total_warnings += len(report.warnings)
            total_changes += len(report.changes)
            if report.changed:
                files_changed += 1

            _emit_remap_report(label, report)

            dest_path = None
            if apply and report.changed and report.can_apply:
                dest_path = _validate_apply_destination(
                    mesh_path,
                    inpath,
                    outpath,
                    backup_suffix,
                    force_backup_overwrite,
                )

            preflight_results.append((mesh_path, label, root_xml, report, dest_path))

            if report.errors:
                failed_files.append(mesh_path)

        except Exception as err:  # noqa: BLE001
            failed_files.append(mesh_path)
            click.echo(f"ERROR {label}")
            click.echo(f"  error: {err}")

    if apply:
        if failed_files and not best_effort:
            click.echo(
                "ABORT no mesh files were written because preflight found blocking "
                "errors. Re-run with --best-effort to allow partial apply."
            )
        else:
            completed_writes = []
            for mesh_path, label, root_xml, report, dest_path in preflight_results:
                if not report.changed or not report.can_apply:
                    continue

                try:
                    if outpath is None:
                        write_info = _write_mesh_with_backup(
                            mesh_path,
                            root_xml,
                            backup_suffix,
                            force_backup_overwrite,
                        )
                    else:
                        write_info = _write_mesh_to_output(dest_path, root_xml)
                    completed_writes.append(write_info)
                    files_written += 1
                except Exception as err:  # noqa: BLE001
                    failed_files.append(mesh_path)
                    click.echo(f"ERROR {label}")
                    click.echo(f"  error: {err}")
                    if not best_effort:
                        rollback_errors = _rollback_completed_writes(completed_writes)
                        files_written = 0
                        if completed_writes:
                            click.echo(
                                "ABORT rolled back earlier writes after a write-time "
                                "failure."
                            )
                        break

    if not apply:
        mode = "dry-run"
    elif best_effort:
        mode = "apply-best-effort"
    else:
        mode = "apply"
    click.echo(
        f"SUMMARY files={len(mesh_files)} changed={files_changed} "
        f"remaps={total_changes} written={files_written} warnings={total_warnings} "
        f"failed={len(failed_files)} mode={mode}"
    )

    if failed_files:
        if rollback_errors:
            for write_info, err in rollback_errors:
                if write_info["mode"] == "inplace":
                    label = str(write_info["mesh_path"])
                else:
                    label = str(write_info["dest_path"])
                click.echo(f"ROLLBACK ERROR {label}")
                click.echo(f"  error: {err}")
        raise click.ClickException(
            f"Texture remap failed for {len(failed_files)} mesh file(s)."
        )


cli.add_command(remap_textures, name="remap_textures")


if __name__ == "__main__":
    """When called from the command line we can just print the structure and contents of the .mesh or .anim file to
    stdout or write directly to a text file. """
    cli()
