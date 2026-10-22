# ODEJOI X91 firmware

Documentation of the ODEJOI X91 MP3 player's stock firmware, as far as it has been worked out, and of the code that
changes it: the stage builders that turn the stock image into the **Graphite** interface, the program patches, the
new code written in C, and the tools that dump and flash the player.

The player is a 1.8-inch button player on an Actions ATJ2157. Nothing here comes from vendor documentation;
addresses and formats were read from the firmware itself, with a partial SDK of the predecessor chip as a guide.

```{figure} ../design/themes-preview.png
:alt: The Graphite design in its four accent colours
:width: 640px

The Graphite design in the four accent colours (Amber, Mint, Ice, Berry).
```

## Where to start

- New here: {doc}`overview`, then {doc}`quickstart`.
- Changing the firmware: {doc}`code/build-system`, {doc}`code/patches` and {doc}`code/new-code`.
- Looking something up: {doc}`firmware/index`.

```{toctree}
:caption: Introduction
:maxdepth: 2

overview
quickstart
project-layout
```

```{toctree}
:caption: Firmware reference
:maxdepth: 2

firmware/index
firmware/hardware
firmware/image-format
firmware/programs
firmware/resources
firmware/display-driver
firmware/shared-code
firmware/music
firmware/other-programs
firmware/flashing
```

```{toctree}
:caption: Graphite design
:maxdepth: 2

design/index
design/stages
```

```{toctree}
:caption: Code reference
:maxdepth: 2

code/build-system
code/patches
code/new-code
code/tools
```

```{toctree}
:caption: Project
:maxdepth: 2

project/history
project/todo
project/sources
glossary
```
