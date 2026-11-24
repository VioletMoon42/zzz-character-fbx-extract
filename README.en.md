# ZZZ Character FBX Extract

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
| Blender (recommended) | [blender.org](https://www.blender.org/download/) | ready-to-open `.blend` files, the add-on, motion checks, dump matching (tested on 5.2) |
| ZZ-Model-Importer-Assets (optional) | see [ZZ-Model-Importer](https://github.com/leotorrez/ZZ-Model-Importer) | only for palette → bone matching |

## How to use
1. **Download:** get **Source code (zip)** from the [latest release](https://github.com/VioletMoon42/zzz-character-fbx-extract/releases/latest) and unzip it anywhere. It contains no binaries.
2. **First-time setup**
   1. Double-click `zzz-character-fbx-extract.bat` and choose menu **1** (setup).
   2. It creates the work folder `%USERPROFILE%\ZZZ_CharacterFBX` and tells you what to unzip into its `tools` folder.
   3. Unzip AnimeStudioUltimate and the .NET 10 runtime into `tools`; any folder names work.
   4. Choose **1** again. It finds the game, the tools and Blender, saves the config, and builds the hook with the compiler that ships with Windows.
3. **Extract:** choose **2**, then type an English name such as `Astra` or `Phoenix`.
   - The first time, and after game updates, it builds a search map first (~7 min, ~4 GB temporary space).
   - If the name differs from the internal one (Phoenix → Pheony), pick a candidate by number. It remembers your choice.
   - Output goes to `%USERPROFILE%\ZZZ_CharacterFBX\characters\<internal name>\`:
     - `model\`: model-only FBX
     - `anim\`: model + all body clips FBX, plus `.animator.json` (state machine and timing)
     - a ready-to-open `.blend` next to each FBX when Blender is configured
4. **Optional checks**
   - **3:** extracts 2–3 sample clips and checks in Blender that they move.
   - **4:** matches a ZZMI dump and writes a `palette_to_bone.json` per part, with a ✓/✗ summary. The add-on uses it to bind mod meshes.
   - **7:** creates `.blend` files for results extracted earlier.

## Command line
```powershell
.\zzz-character-fbx-extract.bat extract Astra
.\zzz-character-fbx-extract.bat extract Astra --clips "Idle_Loop|Attack_Normal_01"
.\zzz-character-fbx-extract.bat check Astra
.\zzz-character-fbx-extract.bat dump Pheony Pheonix
.\zzz-character-fbx-extract.bat list
.\zzz-character-fbx-extract.bat blend Astra
```
Options:
- `--clips <regex>` extracts only some clips. It matches the start of the clip name after `..._Ani_`; add `$` for an exact name.
- `--with-facial` includes face clips.
- `--model-only` extracts only the model.
- `--code <internal name>` skips the candidate prompt.
- `--no-blend` skips the `.blend`.

Set the `ZX_ROOT` environment variable to use a different work folder.

## Development
- Unit tests (no game files needed): `python -m unittest discover -s tests`
- Every script prints its arguments with `--help`.

## Using the results (Blender)
### Just open it
If Blender is configured, extraction also writes a **`.blend`** next to each FBX. Double-click it.
- Real size (about 1.5–1.7 m tall), 60 fps, and a viewport that shows textures.
- All clips are laid out on one timeline with a marker per clip. Press **Space** to play.
- Attacks and dodges move the character forward (root motion); that is expected.
- For results extracted earlier, menu **7** creates the `.blend`.
- Body textures may be missing (AnimeStudio exports only the textures found in the files it read). Shape and motion are unaffected.

### Add-on: pick clips, bind your mod mesh
Install: Blender → **Edit → Preferences → Add-ons** → ▼ (top right) → **Install from Disk…** → `blender_addon\zzz_character_fbx_tools.py`. Press **N** in the 3D view for the **ZZZ FBX** tab.

- **Pick a clip**: click a clip name in the tab to jump there and loop just that clip.
- **화면이 캐릭터 따라가기** (view follows character): keeps the character centred while attacks and dodges move it tens of metres. It follows forward/back and sideways only, not up and down. Press again to turn it off.
- **모드 불러오기 (ZZMI)** (import ZZMI mod): pick a finished ZZMI mod's `.ini` to bring its meshes, with weights, into Blender. One object per draw call, named from the ini comments. Textures are not imported.
- **Preview clipping with your mod mesh**
  1. Open your mod working file (meshes imported with XXMI Tools), or import a mod with **모드 불러오기 (ZZMI)**.
  2. **게임 캐릭터 불러오기** (load game character) → pick `anim\….blend` from the results. The skeleton, meshes, clips and markers come in.
  3. Select your meshes and press **선택한 메시를 게임 뼈대에** (bind selected to game skeleton).
  4. Copies appear in the `게임 뼈대 시험` collection and follow the game motions. **Your original meshes are untouched.**
  - Position, scale and mirroring are fitted automatically to the game body.
  - Numbered vertex groups (`0`, `1`, `2`…) are renamed with `palette_to_bone.json` from menu 4, so **your mod weights are used as-is**. The table is found by mesh name in the same character folder.
  - Before binding, the table is checked against the game mesh. If the numbers don't match (for example a mod made for an older game version), each group is relinked to the nearest game bone, keeping the mod's weight shapes. The result message shows the match rate.
  - Without a table, or when neither fits, weights are copied from the nearest game mesh.

### Using the FBX directly
- When importing the FBX into Blender yourself, set Scale to **100**; otherwise the character is 1.5 cm tall.
- Only actions starting with the armature's name belong to the armature. `Root|`, `Key|` and `FX_Root|` actions belong to other objects.
- ZZMI dump coordinates → FBX is x-flip × 0.01.

## Credits
- [AnimeStudioUltimate](https://github.com/LegionInstaller/AnimeStudioUltimate) does the actual reading and FBX export; the hook only calls its CLI code.
- [ZZ-Model-Importer (ZZMI)](https://github.com/leotorrez/ZZ-Model-Importer) and ZZ-Model-Importer-Assets.

## License
MIT; see [LICENSE](LICENSE). It covers these scripts only, not game data or anything extracted from it.
