# State of Decay 2 Maps for Project Zomboid

Four hand-authored, SoD2-inspired regions:

```text
Meagher Valley     650 cells
Drucker County     650 cells
Cascade Hills      650 cells
Providence Ridge   650 cells
```

Each region has five named bases/landmarks and compound-yard rooms. This repo
contains the mod metadata, manifest and generator source.

## Install

The compiled maps are distributed as a Workshop/local mod folder, not as Git
binaries:

```bash
rm -rf ~/Zomboid/mods/sod2-expansion
cp -a dist/sod2-expansion ~/Zomboid/mods/
```

Requires the `OmskExpansion` map pack. Enable both in a new save.

## Build from source

```bash
python3 tools/build_sod2_region.py --map "Meagher Valley"
python3 tools/build_sod2_region.py --map "Drucker County"
python3 tools/build_sod2_region.py --map "Cascade Hills"
python3 tools/build_sod2_region.py --map "Providence Ridge"
```

Outputs go to `dist/sod2-expansion/common/media/maps`.

## Layout

```text
x=139
Meagher y=0
Drucker y=26
Cascade y=52
Providence y=78
```

The 3.9 GB compiled pack is intentionally not committed to Git.
Map data and layouts are manual reconstructions; no copyrighted game assets.
