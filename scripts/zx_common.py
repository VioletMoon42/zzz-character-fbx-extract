# zzz-game-extract 공용 설정·도우미
# 작업 폴더(ROOT): 환경 변수 ZX_ROOT, 없으면 사용자 폴더의 ZZZ_GameExtract
# 설정 파일: <ROOT>\config.json. 없으면 틀을 만들고 멈춘다. 경로를 채운 뒤 다시 돌린다 (또는 zx.py setup).
import ctypes
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(os.environ.get("ZX_ROOT", str(Path.home() / "ZZZ_GameExtract")))
TEMPLATE = {
    "game_blocks": r"<게임 설치 폴더>\ZenlessZoneZero Game\ZenlessZoneZero_Data\StreamingAssets\Blocks",
    "tool_app": str(ROOT / "tools" / "AnimeStudioUltimate-1.8.1" / "app"),
    "dotnet_root": str(ROOT / "tools" / "dotnet-runtime-10"),
    "hook_dll": str(ROOT / "tools" / "hook" / "ExtractHook.dll"),
    "blender": shutil.which("blender") or r"<blender.exe 경로>",
    "dump_root": r"<ZZ-Model-Importer-Assets 폴더>\PlayerCharacterData",
    "map_file": str(ROOT / "map" / "zzz_map_compact.tsv"),
}
OPTIONAL = {"blender", "dump_root"}   # 비워 둬도 되는 항목 (동작 확인·덤프 대조에만 필요)
NONE = "(없음)"


def cfg():
    p = ROOT / "config.json"
    if not p.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=1), encoding="utf-8")
        raise SystemExit(f"설정 파일을 만들었습니다: {p}\n"
                         "zx.py setup을 돌리거나, <...> 부분을 내 PC 경로로 채운 뒤 다시 돌리세요.")
    c = dict(TEMPLATE)
    c.update(json.loads(p.read_text(encoding="utf-8")))
    bad = [k for k, v in c.items() if "<" in str(v) and k not in OPTIONAL]
    if bad:
        raise SystemExit(f"{p}에서 아직 안 채운 경로: {', '.join(bad)} (zx.py setup으로 채울 수 있습니다)")
    return c


def optional_path(c, key, what):
    """선택 항목(blender, dump_root) 경로를 돌려준다. 없으면 무엇에 필요한지 알려 주고 멈춘다."""
    v = c.get(key, "")
    if not v or v == NONE or "<" in v or not Path(v).exists():
        raise SystemExit(f"{what}에는 설정의 {key}가 필요합니다 (지금 값: {v or '비어 있음'}). zx.py setup을 다시 돌리세요.")
    return Path(v)


def decode_console(raw):
    """CLI 콘솔 출력 바이트를 글자로. UTF-8이 아니면 윈도우 OEM 코드 페이지(한국어 윈도우는 cp949)로 읽는다."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            cp = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
        except (AttributeError, OSError):
            cp = "cp949"
        return raw.decode(cp, errors="replace")


def run_cli(args, env_extra=None, log=None):
    """AnimeStudio.CLI.exe를 휴대용 .NET 10으로 직접 실행한다 (dotnet exec로 돌리면 FBX DLL을 못 찾음).
    돌려주는 값: (종료 코드, 출력 글자). log를 주면 출력을 그 파일에도 쓴다."""
    c = cfg()
    exe = Path(c["tool_app"]) / "AnimeStudio.CLI.exe"
    if not exe.exists():
        raise SystemExit(f"AnimeStudio.CLI.exe가 없습니다: {exe} (zx.py setup을 다시 돌리세요)")
    env = dict(os.environ, DOTNET_ROOT=c["dotnet_root"])
    env.update(env_extra or {})
    r = subprocess.run([str(exe)] + [str(a) for a in args], cwd=c["tool_app"], env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    text = decode_console(r.stdout)
    if log:
        Path(log).write_text(text, encoding="utf-8", errors="replace")
    return r.returncode, text


def hook_env(c, list_file, out_dir, model_animator, clips_regex):
    """ExtractHook.dll에 넘길 환경 변수. model_animator는 정확한 이름, clips_regex는 동작 이름 정규식."""
    return {"DOTNET_STARTUP_HOOKS": c["hook_dll"], "ZX_LIST": str(list_file), "ZX_OUT": str(out_dir),
            "ZX_MODEL": "^" + re.escape(model_animator) + "$", "ZX_CLIPS": clips_regex}


def run_blender(script, args, log):
    """Blender를 배경 모드로 돌려 scripts\\<script>를 실행한다. 실패하면 로그 위치를 알려 주고 멈춘다."""
    blender = optional_path(cfg(), "blender", "Blender 작업")
    r = subprocess.run([str(blender), "-b", "--factory-startup", "--python", str(Path(__file__).parent / script),
                        "--"] + [str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    Path(log).write_text(r.stdout.decode("utf-8", errors="replace"), encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit(f"Blender 실행 실패 (종료 코드 {r.returncode}). 로그: {log}")


def game_version():
    """게임 폴더 config.ini의 game_version (지도·plan이 최신인지 비교할 때 쓴다). 못 읽으면 None."""
    ini = Path(cfg()["game_blocks"]).parents[2] / "config.ini"
    if ini.exists():
        for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("game_version="):
                return line.split("=", 1)[1].strip()
    return None


def load_map():
    """간추린 지도: 줄마다 이름\t종류\t파일(.blk 이름)"""
    p = Path(cfg()["map_file"])
    if not p.exists():
        raise SystemExit(f"검색 지도가 없습니다: {p} (zx_build_map.py 또는 zx.py map으로 먼저 만드세요)")
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 3:
                rows.append(tuple(parts))
    return rows


def char_dir(code):
    return ROOT / "characters" / code


def load_plan(code):
    p = char_dir(code) / "plan.json"
    if not p.exists():
        raise SystemExit(f"{code}의 plan.json이 없습니다: {p} (먼저 zx_find.py {code}로 찾으세요)")
    return json.loads(p.read_text(encoding="utf-8"))


def copy_if_changed(src, dst):
    """게임 파일을 작업 폴더로 복사한다. 이미 있어도 크기나 수정 시각이 다르면(게임 업데이트) 새로 복사한다.
    돌려주는 값: 복사했으면 True."""
    src, dst = Path(src), Path(dst)
    s = src.stat()
    if dst.exists():
        d = dst.stat()
        if d.st_size == s.st_size and int(d.st_mtime) == int(s.st_mtime):
            return False
    shutil.copy2(src, dst)
    return True


def free_gb(path):
    p = Path(path)
    while not p.exists():
        p = p.parent
    return shutil.disk_usage(p).free / 1e9
