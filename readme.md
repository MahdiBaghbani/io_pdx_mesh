# IO PDX MESH

![GitHub last commit](https://img.shields.io/github/last-commit/MahdiBaghbani/io_pdx_mesh.svg)
![Github All Releases](https://img.shields.io/github/downloads/MahdiBaghbani/io_pdx_mesh/total.svg)

Maintainer: This is the maintained
[`MahdiBaghbani/io_pdx_mesh`](https://github.com/MahdiBaghbani/io_pdx_mesh)
fork. Please file bugs and feature requests in the
[GitHub issue tracker](https://github.com/MahdiBaghbani/io_pdx_mesh/issues).

This project aims to allow editing of mesh and animation files used in the
various [Clausewitz Engine games](https://en.wikipedia.org/wiki/Paradox_Development_Studio#List_of_games_developed)
created by [Paradox Development Studios](https://www.paradoxplaza.com).

It's designed to run in _both_ Maya (2018+) and Blender (3.6.4+).

## Download

Click here to view the [latest
release](https://github.com/MahdiBaghbani/io_pdx_mesh/releases/latest) and
download the **_io_pdx_mesh.zip_** file (this works with both Maya and
Blender).

## Screenshots and docs

See the [project wiki](https://github.com/MahdiBaghbani/io_pdx_mesh/wiki)
for screenshots, setup notes, and other documentation.

## Installation

### Setup for Maya (2018+)

- Go to your Maya user scripts path. (eg on Windows:
  `C:\Users\...\Documents\maya\scripts`)
- Extract the contents of the zip file directly into this path.
- PyMEL is required for Maya. Do not run `pip install pymel`.
- Instead, use the repo vendor scripts to download PyMEL into
  `vendor/pymel_root`:
  - Windows: run `scripts\vendor\install_pymel_vendor.bat`
  - Linux/macOS: run `sh scripts/vendor/install_pymel_vendor.sh`
- `scripts/vendor/vendor.env` stores the pinned default owner, repo, and
  version, and you can override them if needed.
- Start Maya and change the `Command Line` to Python by clicking the label.
- Then use this Python 3 command to launch the tool:

  ```python
  import importlib
  import io_pdx_mesh
  importlib.reload(io_pdx_mesh)
  ```

- You can highlight this command and use the middle-mouse button to drag it
  into a shelf button to save it.
- The tool window will now open.

### Setup for Blender (3.6.4+)

- Start Blender and open the `User Preferences` panel
  (`Edit > Preferences...`).
- Version 4.2.0+
  - Switch to the `Get Extensions` category and select `Install from Disk...`
    from the dropdown corner menu. Pick the zip file you have downloaded.
- Version 3.6.4+
  - Switch to the `Add-ons` category and select `Install...`. Pick the zip
    file you have downloaded.
- Tick the checkbox to enable the add-on and you should see a new tab in the
  `Sidebar` of the `3D Viewport`. (`View > Sidebar` if you have it closed)
- The `Sidebar` will now have a `PDX Blender Tools` tab.

### Workflow notes

- Issue #15: the exporter writes meshes from the tool's PDX
  material/shader property workflow, not arbitrary Blender materials.
- Issue #112: `Unknown file header` usually means the file is not a supported
  PDX mesh or animation file. Verify the file source first.

---

### Supporters

El Tyranos, creator of CK3's [Community Flavor Pack](https://communityflavorpack.com/)

Kindly provided a PyCharm license from JetBrains for [Open Source
projects](https://jb.gg/OpenSourceSupport).

![PyCharm logo.](https://resources.jetbrains.com/storage/products/company/brand/logos/PyCharm_icon.png)
