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
- Start Maya and change the `Command Line` to Python by clicking the label.
- Then use the command `import io_pdx_mesh;reload(io_pdx_mesh)` to launch the
  tool.
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

---

### Supporters

El Tyranos, creator of CK3's [Community Flavor Pack](https://communityflavorpack.com/)

Kindly provided a PyCharm license from JetBrains for [Open Source
projects](https://jb.gg/OpenSourceSupport).

<img src="https://resources.jetbrains.com/storage/products/company/brand/logos/PyCharm_icon.png" alt="PyCharm logo." width="50" height="50">
