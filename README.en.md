# zzz-game-extract

A tool that exports a Zenless Zone Zero (ZZZ) character's **game skeleton + model + all body animations** into a single FBX, from the game files installed on your own PC. It also builds a **bone palette index → real bone name** table for ZZMI (ZZ-Model-Importer) dumps.

It runs from a double-click menu; no AI is needed. With [Claude Code](https://claude.com/claude-code) you can also install it as a skill and drive it in plain words.

The menu and messages are in Korean. The numbered steps below match the menu.

[한국어 README](README.md)

## Why
For outfit ports and weight painting you often want two things:
- the **real game skeleton** to test weights on, instead of an approximate rig;
- **real in-game motions** (attacks, dodges, ultimates) to check for clipping.

The AnimeStudio CLI reads the game's `.blk` files **one at a time**. In ZZZ, though, body meshes and animations live in different files from the model. With the CLI alone you only get the skeleton and hair.

A small startup hook makes the CLI load all the needed files **at once**, so the model and its animations come out in one FBX. AnimeStudio's own code is called as-is and never patched.

## Results so far
- **Pheony (Phoenix):** 314 bones and 123 body animations. The vertex order matched the ZZMI dump, with zero weight difference on every part.
- **Astra:** idle, attack and dodge motions were confirmed to move in Blender.

## Please note
- **Use it only on your own game files, for personal work.** Do not redistribute extracted models or animations. Extracting game files may conflict with the game's terms of service, much like modding does. Use at your own risk.
- The game folder is only read; needed files are copied into the work folder.
- Existing output folders are never overwritten.
- This repository contains no game data, no extracted output and no tool binaries.

## What you need
| Item | Where | Note |
|---|---|---|
| Zenless Zone Zero | Steam or HoYoPlay | found automatically |
| Python 3.10+ | [python.org](https://www.python.org/downloads/) | tick **"Add python.exe to PATH"** |
| AnimeStudioUltimate 1.8.1 | [GitHub releases](https://github.com/LegionInstaller/AnimeStudioUltimate/releases) | does the actual reading and FBX export (MIT) |
| .NET 10 runtime | [Microsoft](https://dotnet.microsoft.com/download/dotnet/10.0) | the **Windows x64 zip** is enough; no install |
| Blender (optional) | [blender.org](https://www.blender.org/download/) | only for motion checks and dump matching (tested on 4.x) |
| ZZ-Model-Importer-Assets (optional) | see [ZZ-Model-Importer](https://github.com/leotorrez/ZZ-Model-Importer) | only for palette → bone matching |

## How to use
1. **Download:** get **Source code (zip)** from the [latest release](https://github.com/VioletMoon42/zzz-game-extract/releases/latest) and unzip it anywhere. It contains no binaries.
2. **First-time setup**
   1. Double-click `zzz-extract.bat` and choose menu **1** (setup).
   2. It creates the work folder `%USERPROFILE%\ZZZ_GameExtract` and tells you what to unzip into its `tools` folder.
   3. Unzip AnimeStudioUltimate and the .NET 10 runtime into `tools`; any folder names work.
   4. Choose **1** again. It finds the game, the tools and Blender, saves the config, and builds the hook with the compiler that ships with Windows.
3. **Extract:** choose **2**, then type an English name such as `Astra` or `Phoenix`.
   - The first time, and after game updates, it builds a search map first (~7 min, ~4 GB temporary space).
   - If the name differs from the internal one (Phoenix → Pheony), pick a candidate by number. It remembers your choice.
   - Output goes to `%USERPROFILE%\ZZZ_GameExtract\characters\<internal name>\`:
     - `model\`: model-only FBX
     - `anim\`: model + all body clips FBX, plus `.animator.json` (state machine and timing)
4. **Optional checks**
   - **3:** extracts 2–3 sample clips and checks in Blender that they move.
   - **4:** matches a ZZMI dump and writes a `palette_to_bone.json` per part, with a ✓/✗ summary.

## Command line
```powershell
.\zzz-extract.bat extract Astra
.\zzz-extract.bat extract Astra --clips "Idle_Loop|Attack_Normal_01"
.\zzz-extract.bat check Astra
.\zzz-extract.bat dump Pheony Pheonix
.\zzz-extract.bat list
```
Options:
- `--clips <regex>` extracts only some clips. It matches the start of the clip name after `..._Ani_`; add `$` for an exact name.
- `--with-facial` includes face clips.
- `--model-only` extracts only the model.
- `--code <internal name>` skips the candidate prompt.

Set the `ZX_ROOT` environment variable to use a different work folder.

## Development
- Unit tests (no game files needed): `python -m unittest discover -s tests`
- Every script prints its arguments with `--help`.

## In Blender
- The character imports at 1/100 scale. ZZMI dump → FBX is x-flip × 0.01.
- Clips are 60 fps.
- Use only the actions that start with the armature's name. `Root|`, `Key|` and `FX_Root|` actions belong to other objects.

## Credits
- [AnimeStudioUltimate](https://github.com/LegionInstaller/AnimeStudioUltimate) does the actual reading and FBX export; the hook only calls its CLI code.
- [ZZ-Model-Importer (ZZMI)](https://github.com/leotorrez/ZZ-Model-Importer) and ZZ-Model-Importer-Assets.

## License
MIT; see [LICENSE](LICENSE). It covers these scripts only, not game data or anything extracted from it.
