# zzz-character-fbx-extract 한곳 실행기. 인자 없이 돌리면 메뉴가 나온다 (zzz-character-fbx-extract.bat 더블클릭).
#   python zx.py setup                  설정 만들기 (게임·Blender·도구 위치 찾기, 훅 빌드)
#   python zx.py extract <이름> [옵션]   찾기 + 뽑기 (지도가 없거나 오래되면 먼저 만든다)
#       옵션: --code <코드명>  --clips <동작 이름 앞부분 정규식, 예: "Idle_Loop|Evade">  --with-facial  --model-only
#   python zx.py check <코드명>          대표 동작 3개만 따로 뽑아 실제로 움직이는지 Blender로 확인
#   python zx.py dump <코드명> [덤프 폴더 이름]   ZZMI 덤프 팔레트 번호 → 뼈 이름 표
#   python zx.py map                    검색 지도 다시 만들기 (게임 업데이트 뒤, 약 7분)
#   python zx.py list                   뽑아 둔 캐릭터 목록
import argparse
import json
import os
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    except Exception:
        pass
import zx_common as Z  # noqa: E402
import zx_extract  # noqa: E402
import zx_find  # noqa: E402

GAME_SUB = Path("ZenlessZoneZero Game") / "ZenlessZoneZero_Data" / "StreamingAssets" / "Blocks"
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
ADDON = HERE.parent / "blender_addon" / "zzz_character_fbx_tools.py"
LINKS = {
    "AnimeStudioUltimate 1.8.1": "https://github.com/LegionInstaller/AnimeStudioUltimate/releases",
    ".NET 10 런타임 (Windows x64 zip)": "https://dotnet.microsoft.com/download/dotnet/10.0",
    "Blender": "https://www.blender.org/download/",
}


def ask(q, default=""):
    try:
        a = input(f"{q}{f' [{default}]' if default else ''}: ").strip().strip('"')
    except EOFError:
        a = ""
    return a or default


def yes(q, default=True):
    a = ask(q + (" (Y/n)" if default else " (y/N)")).lower()
    return default if not a else a in ("y", "yes", "예", "ㅇ", "네")


def run_py(script, *args):
    return subprocess.run([sys.executable, "-X", "utf8", str(HERE / script), *map(str, args)]).returncode


# ---------- setup ----------
def drives():
    return [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]


def steam_libraries():
    libs = []
    for base in [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam",
                 Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Steam"]:
        vdf = base / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            libs.append(base)
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                libs.append(Path(m.group(1).replace("\\\\", "\\")))
    for d in drives():
        libs.append(d / "SteamLibrary")
    return libs


def find_game():
    cands = [lib / "steamapps" / "common" / "Zenless Zone Zero" / "games" for lib in steam_libraries()]
    for d in drives():
        for p in ["Program Files/HoYoPlay/games", "HoYoPlay/games", "Program Files/miHoYo Launcher/games",
                  "Program Files/Zenless Zone Zero", "Zenless Zone Zero", "Games/Zenless Zone Zero"]:
            cands.append(d / p)
    for c in cands:
        if (c / GAME_SUB).is_dir():
            return c / GAME_SUB
    return None


def find_blender():
    w = shutil.which("blender")
    if w:
        return Path(w)
    pats = []
    for d in drives():
        pats += [(d / "Program Files" / "Blender Foundation", "*/blender.exe")]
    pats += [(lib / "steamapps" / "common" / "Blender", "blender.exe") for lib in steam_libraries()]
    found = []
    for base, pat in pats:
        if base.is_dir():
            found += list(base.glob(pat))
    return sorted(found)[-1] if found else None


def find_under(root, name, need=None):
    if not root.is_dir():
        return None
    for p in sorted(root.rglob(name)):
        if need is None or need(p):
            return p
    return None


def dotnet10_ok(p):
    return any(p.parent.glob("shared/Microsoft.NETCore.App/10.*"))


def setup():
    print(f"작업 폴더: {Z.ROOT}  (바꾸려면 환경 변수 ZX_ROOT를 정하고 다시 실행)")
    tools = Z.ROOT / "tools"; tools.mkdir(parents=True, exist_ok=True)
    cfgp = Z.ROOT / "config.json"
    old = json.loads(cfgp.read_text(encoding="utf-8")) if cfgp.exists() else {}
    c = dict(Z.TEMPLATE); c.update(old)

    def keep(key, check):
        v = old.get(key)
        return v if v and "<" not in v and check(Path(v)) else None

    g = keep("game_blocks", Path.is_dir) or find_game()
    if not g:
        print("\n게임 폴더를 못 찾았습니다. 'ZenlessZoneZero Game' 폴더가 든 게임 설치 폴더를 알려 주세요.")
        while True:
            p = Path(ask("게임 설치 폴더"))
            for q in (p / GAME_SUB, p / "games" / GAME_SUB, p / GAME_SUB.relative_to("ZenlessZoneZero Game"), p):
                if q.name == "Blocks" and q.is_dir():
                    g = q; break
            if g:
                break
            print("  그 안에서 ...\\ZenlessZoneZero_Data\\StreamingAssets\\Blocks를 못 찾았습니다.")
    c["game_blocks"] = str(g); print(f"✓ 게임: {g}")

    cli = keep("tool_app", lambda p: (p / "AnimeStudio.CLI.exe").exists())
    if not cli:
        exe = find_under(tools, "AnimeStudio.CLI.exe")
        cli = str(exe.parent) if exe else None
    dn = keep("dotnet_root", lambda p: dotnet10_ok(p / "dotnet.exe"))
    if not dn:
        exe = find_under(tools, "dotnet.exe", dotnet10_ok)
        dn = str(exe.parent) if exe else None
    missing = [k for k, v in (("AnimeStudioUltimate 1.8.1", cli), (".NET 10 런타임 (Windows x64 zip)", dn)) if not v]
    if missing:
        print(f"\n아래 도구를 받아 {tools} 안에 압축을 풀어 주세요 (폴더 이름은 자유):")
        for k in missing:
            print(f"  - {k}: {LINKS[k]}")
        print("다 풀었으면 setup을 다시 실행하세요.")
        cfgp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
        return False
    c["tool_app"], c["dotnet_root"] = cli, dn
    print(f"✓ AnimeStudio CLI: {cli}\n✓ .NET 10: {dn}")

    hook = Path(c["hook_dll"])
    if "<" in str(hook):
        hook = tools / "hook" / "ExtractHook.dll"
    src = HERE / "ExtractHook.cs"
    if not hook.exists() or hook.stat().st_mtime < src.stat().st_mtime:   # 없거나 소스가 더 새것이면 다시 빌드
        hook.parent.mkdir(parents=True, exist_ok=True)
        if not CSC.exists():
            print(f"훅을 빌드할 csc.exe가 없습니다: {CSC} (.NET Framework 4.x가 필요합니다)"); return False
        r = subprocess.run([str(CSC), "-nologo", "-target:library", f"-out:{hook}", str(src)],
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0 or not hook.exists():
            print("훅 빌드 실패:\n" + r.stdout + r.stderr); return False
    c["hook_dll"] = str(hook); print(f"✓ 훅: {hook}")

    b = keep("blender", Path.is_file) or find_blender()
    if not b:
        print(f"\nBlender를 못 찾았습니다 ({LINKS['Blender']}). 동작 확인·덤프 대조에만 필요합니다.")
        b = ask("blender.exe 경로 (없으면 Enter)") or ""
    c["blender"] = str(b) if b else "(없음)"
    print(f"{'✓' if b else '-'} Blender: {c['blender']}")

    d = old.get("dump_root", "")
    if not d or "<" in d:
        print("\n(선택) ZZ-Model-Importer-Assets의 PlayerCharacterData 폴더. 팔레트 → 뼈 이름 대조에만 필요합니다.")
        d = ask("폴더 경로 (없으면 Enter)") or "(없음)"
    c["dump_root"] = d
    c["map_file"] = old.get("map_file") if old.get("map_file") and "<" not in old["map_file"] else str(Z.ROOT / "map" / "zzz_map_compact.tsv")
    cfgp.write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n설정 저장: {cfgp}")
    try:
        import numpy, scipy  # noqa: F401
    except ImportError:
        print("덤프 대조에는 numpy, scipy가 필요합니다:  python -m pip install numpy scipy")
    print("준비 끝. 이제 extract <캐릭터 이름>으로 뽑을 수 있습니다.")
    return True


def need_cfg():
    try:
        return Z.cfg()
    except SystemExit as e:
        raise SystemExit(f"{e.code}\n먼저 setup(메뉴 1번)을 실행해 주세요.")


# ---------- map / extract ----------
def map_status():
    info = Path(need_cfg()["map_file"]).parent / "map_info.json"
    if not info.exists() or not Path(need_cfg()["map_file"]).exists():
        return "없음"
    v = json.loads(info.read_text(encoding="utf-8")).get("game_version")
    gv = Z.game_version()
    return "최신" if (gv is None or v == gv) else f"오래됨 (지도 {v}, 게임 {gv})"


def ensure_map():
    st = map_status()
    if st == "최신":
        return True
    print(f"검색 지도: {st}. 지도를 만들어야 합니다 (약 7분, 빈 디스크 공간 약 5 GB).")
    if not yes("지금 만들까요?"):
        return False
    return run_py("zx_build_map.py") == 0


def print_plan(name, pl):
    files = len(set(pl["model_blks"] + pl["mesh_blks"] + pl["clip_blks"]))
    print(f"찾음: {name} → 게임 속 이름 {pl['code']}\n  모델 {pl['model_animator']}\n"
          f"  몸 동작 {pl['body_clip_count']}개, 얼굴 동작 {pl['facial_clip_count']}개, 게임 파일 {files}개")
    others = pl["other_models_same_code_prefix"]
    wpn = [m for m in others if m.endswith("_Weapon")]
    rest = [m for m in others if m not in wpn]
    if wpn:
        print(f"  무기: {', '.join(wpn)} → 같은 동작으로 함께 뽑아 .blend에 넣습니다 (빼려면 --no-weapon)")
    if rest:
        print(f"  (다른 모습: {', '.join(rest)} → 이 이름으로 extract하면 따로 뽑힙니다)")


def extract(a):
    need_cfg()
    name = a.name or ask("캐릭터 이름 (영어, 예: Astra, Phoenix)")
    if not name or not ensure_map():
        return 1
    r = zx_find.find(name, a.code)
    if not r["found"]:
        cands = r["candidates"]
        if not cands:
            print(f"'{name}'와 비슷한 캐릭터가 없습니다. 인게임 영어 이름으로 다시 해 보세요.")
            return 1
        print(f"'{name}'를 바로 못 찾았습니다. 게임 속 이름 후보:")
        for i, cnd in enumerate(cands, 1):
            print(f"  {i}. {cnd}")
        k = ask("번호 (그만두려면 Enter)")
        if not k.isdigit() or not 1 <= int(k) <= len(cands):
            return 1
        r = zx_find.find(name, cands[int(k) - 1])
    pl = r["plan"]
    print_plan(name, pl)
    xa = [pl["code"]] + (["--clips", a.clips] if a.clips else []) + (["--with-facial"] if a.with_facial else []) \
        + (["--model-only"] if a.model_only else []) + (["--no-weapon"] if getattr(a, "no_weapon", False) else [])
    rc = run_py("zx_extract.py", *xa)
    if rc == 0:
        print(f"\n완료: {Z.char_dir(pl['code'])}\n  model\\ 모델 FBX" + ("" if a.model_only else ", anim\\ 모델 + 동작 FBX"))
        print(f"동작이 제대로 움직이는지 보려면: check {pl['code']}")
    return rc


# ---------- check ----------
CHECK_CLIPS = ("Idle_Loop", "Attack_Normal_01", "Evade_Front_01")


def check(a):
    c = need_cfg()
    code = a.code or ask("게임 속 이름 (extract 결과에 나온 이름)")
    plan = Z.load_plan(code)
    Z.optional_path(c, "blender", "동작 확인")
    have = {b.split("_Ani_", 1)[1] for b in plan["body_clips"]}
    want = [x for x in CHECK_CLIPS if x in have] or sorted(have)[:3]
    if not want:
        print(f"{code}에는 몸 동작이 없습니다.")
        return 1
    base = Z.char_dir(code)
    out, n = base / "anim_check", 2
    while out.exists() and any(out.iterdir()):
        out, n = base / f"anim_check_{n}", n + 1
    pre = re.escape(plan["model_animator"][:-len("_Model")]) + "_Ani_"
    print(f"동작 {', '.join(want)}만 따로 뽑는 중...")
    _, lst = zx_extract.gather_input(plan, False, c)
    r = zx_extract.export(plan, c, lst, out.name, "^" + pre + "(" + "|".join(map(re.escape, want)) + ")$")
    rep = out / "anim_check.json"
    Z.run_blender("zx_check_anim_blender.py", [r["fbx"][0], rep], base / f"log_{out.name}_blender.txt")
    j = json.loads(rep.read_text(encoding="utf-8"))
    print(f"\n뼈 {j['bones']}개. 동작별 최대 움직임 (키 대비. 대기는 작고, 공격·회피는 앞으로 나가는 만큼 큼):")
    still = []
    for act in j["actions"]:
        m = max(act["max_move_rel"].values(), default=0)
        name = act["name"].split("|")[1]
        if m <= 0.02:
            still.append(name)
        print(f"  {name:<50} {m:.2f}")
    if not j["actions"]:
        print("→ FBX에 동작이 없습니다.")
        return 1
    print("→ 동작이 실제로 움직입니다." if not still else f"→ 거의 안 움직이는 동작: {', '.join(still)}")
    return 0 if not still else 1


# ---------- dump / list ----------
def dump(a):
    c = need_cfg()
    root = Z.optional_path(c, "dump_root", "덤프 대조")
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError:
        print("덤프 대조에는 numpy, scipy가 필요합니다:  python -m pip install numpy scipy")
        return 1
    code = a.code or ask("게임 속 이름")
    Z.load_plan(code)
    folder = a.dump
    if not folder:
        names = sorted(p.name for p in root.iterdir() if p.is_dir())
        guess = [nm for nm in names if nm.lower().startswith(code.lower()[:4])]
        print("덤프 폴더 후보:", ", ".join(guess or names[:20]))
        folder = ask("덤프 폴더 이름", guess[0] if guess else "")
    print("대조 중 (처음에는 Blender로 모델을 읽느라 1~2분 걸립니다)...")
    r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "zx_map_dump.py"), code, folder],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = Z.char_dir(code) / "dump_map" / Path(folder).name
    rep = out / "dump_map_report.json"
    if r.returncode != 0 or not rep.exists():
        print(r.stdout + r.stderr)
        return 1
    print("\n부위별 결과 (웨이트 차이가 0에 가까우면 표가 맞습니다):")
    bad = 0
    for comp, v in json.loads(rep.read_text(encoding="utf-8"))["components"].items():
        if "skip" in v:
            print(f"  -  {comp:<28} 건너뜀: {v['skip']}")
            continue
        m = v.get("check_weight_L1", {}).get("max", 1.0)
        ok = m < 0.01 and not v.get("unmapped")
        bad += not ok
        print(f"  {'✓' if ok else '✗'}  {comp:<28} → {v.get('fbx_mesh')}, 뼈 {v.get('palette_mapped')}/{v.get('palette_used')}개, "
              f"웨이트 차이 최대 {m:.4f}")
    print(f"\n표: {out}\\<부위>_palette_to_bone.json")
    if bad:
        print("✗ 부위는 표가 정확하지 않을 수 있습니다. dump_map_report.json을 확인하세요.")
    return 0


def blend(a):
    """이미 뽑아 둔 FBX마다 바로 쓰는 .blend를 만든다 (있으면 건너뜀)"""
    c = need_cfg()
    Z.optional_path(c, "blender", "Blender 파일 만들기")
    code = a.code or ask("게임 속 이름")
    base = Z.char_dir(code)
    is_wpn = lambda d: d.name.lower().endswith("weapon")   # 무기 폴더(<동작 폴더>_weapon)는 그 동작 폴더의 .blend에 같이 넣는다

    def weapons_for(folder):
        """<folder>_weapon 또는 무기가 여럿일 때 <folder>_<코드>_Weapon"""
        n = folder + "_"
        ds = [d for d in base.glob(n + "*") if d.is_dir() and is_wpn(d)
              and (d.name == n + "weapon" or d.name[len(n):].count("_") == 1)]
        return sorted(w for d in ds for w in d.glob("*.fbx"))

    fbxs = sorted(f for d in ("model", "anim") for f in (base / d).glob("*.fbx")) + \
        sorted(f for d in base.glob("anim_*") if not is_wpn(d) for f in d.glob("*.fbx"))
    if not fbxs:
        print(f"{base}에 뽑은 FBX가 없습니다. 먼저 캐릭터 뽑기(2번)를 하세요.")
        return 1
    for f in fbxs:
        b = f.with_suffix(".blend")
        if b.exists():
            print(f"  있음: {b.relative_to(base)}")
            continue
        extras = [] if f.parent.name == "model" else weapons_for(f.parent.name)
        print(f"  만드는 중: {b.relative_to(base)}" + (" + 무기" if extras else "") + " (동작이 많으면 몇 분 걸립니다)")
        Z.make_blend(f, base / f"log_{f.parent.name}_blend.txt", extras)
    print(f"\nBlender에서 바로 열면 됩니다. 내 모드 메시를 게임 뼈대에 붙이려면 애드온을 쓰세요: {ADDON}")
    return 0


def listing(a):
    base = Z.ROOT / "characters"
    rows = sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    if not rows:
        print("아직 뽑은 캐릭터가 없습니다.")
    for p in rows:
        pl = json.loads((p / "plan.json").read_text(encoding="utf-8")) if (p / "plan.json").exists() else {}
        has = [t for t, d in (("모델", "model"), ("동작", "anim"), ("덤프대조", "dump_map")) if (p / d).is_dir()]
        print(f"  {p.name:<24} 동작 {pl.get('body_clip_count', '?'):>4}개   {' '.join(has)}")
    return 0


# ---------- 명령·메뉴 ----------
def parser():
    ap = argparse.ArgumentParser(prog="zx.py", description="내 게임 파일에서 ZZZ 캐릭터 뼈대·모델·동작을 FBX로 뽑는다. 인자 없이 돌리면 메뉴.")
    sub = ap.add_subparsers(dest="cmd", metavar="명령")
    sub.add_parser("setup", help="처음 설정 (게임·도구·Blender 찾기, 훅 빌드)")
    e = sub.add_parser("extract", help="캐릭터 찾기 + 뽑기")
    e.add_argument("name", nargs="?", help="캐릭터 이름 (영어)")
    e.add_argument("--code", help="게임 속 이름을 직접 지정")
    e.add_argument("--clips", help="동작 일부만: _Ani_ 다음 이름의 앞부분 정규식, 예: 'Idle_Loop|Attack_Normal_01'")
    e.add_argument("--with-facial", action="store_true", help="얼굴 동작도")
    e.add_argument("--model-only", action="store_true", help="모델만")
    e.add_argument("--no-weapon", action="store_true", help="무기는 빼고 (기본: 무기 모델이 있으면 같은 동작으로 함께 뽑음)")
    ch = sub.add_parser("check", help="대표 동작만 뽑아 Blender로 움직임 확인")
    ch.add_argument("code", nargs="?", help="게임 속 이름")
    d = sub.add_parser("dump", help="ZZMI 덤프 팔레트 번호 → 뼈 이름 표")
    d.add_argument("code", nargs="?", help="게임 속 이름")
    d.add_argument("dump", nargs="?", help="덤프 폴더 이름")
    sub.add_parser("list", help="뽑아 둔 캐릭터 목록")
    sub.add_parser("map", help="검색 지도 다시 만들기 (게임 업데이트 뒤)")
    bl = sub.add_parser("blend", help="이미 뽑은 FBX로 바로 쓰는 .blend 만들기")
    bl.add_argument("code", nargs="?", help="게임 속 이름")
    return ap


CMDS = {"setup": lambda a: 0 if setup() else 1, "extract": extract, "check": check, "dump": dump,
        "list": listing, "map": lambda a: run_py("zx_build_map.py"), "blend": blend}
MENU = [("setup", "처음 설정 (한 번만)"), ("extract", "캐릭터 뽑기 (모델 + 동작 FBX + Blender 파일)"), ("check", "뽑은 동작 확인 (Blender)"),
        ("dump", "ZZMI 덤프와 뼈 이름 대조 (선택)"), ("list", "뽑아 둔 캐릭터 목록"), ("map", "검색 지도 다시 만들기 (게임 업데이트 뒤)"),
        ("blend", "이미 뽑은 결과로 Blender 파일 만들기")]


def menu(ap):
    print("ZZZ Character FBX Extract — 내 게임 파일에서 캐릭터 뼈대·모델·동작 뽑기 (개인 작업용, 결과물 배포 금지)\n")
    while True:
        for i, (_, t) in enumerate(MENU, 1):
            print(f"  {i}. {t}")
        k = ask("\n번호 (끝내려면 Enter)")
        if not k.isdigit() or not 1 <= int(k) <= len(MENU):
            return 0
        cmd = MENU[int(k) - 1][0]
        try:
            CMDS[cmd](ap.parse_args([cmd]))
        except SystemExit as e:
            if e.code not in (None, 0):
                print(e.code)
        print()


def main():
    ap = parser()
    if len(sys.argv) == 1:
        return menu(ap)
    a = ap.parse_args()
    if not a.cmd:
        ap.print_help()
        return 1
    return CMDS[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main() or 0)
