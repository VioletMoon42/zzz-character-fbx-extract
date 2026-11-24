# 게임 파일 검색 지도를 만든다 (처음 한 번, 그리고 게임 업데이트 뒤). 게임 폴더는 읽기만 한다.
#   python -X utf8 zx_build_map.py               CLI로 전체 지도를 만든 뒤(약 7분) 간추리고, 큰 임시 JSON(약 3.5 GB)은 지운다
#   python -X utf8 zx_build_map.py --from <json>  이미 있는 전체 지도 JSON에서 간추리기만 한다 (그 JSON은 그대로 둔다)
# 간추린 지도에는 Animator, Avatar, Mesh, AnimationClip만 남긴다 (줄마다 이름\t종류\t.blk 이름).
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from zx_common import ROOT, cfg, free_gb, game_version, run_cli  # noqa: E402

KEEP = {"Animator", "Avatar", "Mesh", "AnimationClip"}
NEED_GB = 5   # 전체 지도 JSON 약 3.5 GB + 여유
KV = re.compile(r'^\s*"(\w+)":\s*(.*?),?\s*$')


def compact(src, dst):
    """AnimeStudio 전체 지도 JSON(들여쓰기, 한 줄에 키 하나)을 줄 단위로 읽어 간추린다. 3.5 GB라 json.load는 쓰지 않는다.
    돌려주는 값: 남긴 항목 수."""
    cur, n = {}, 0
    tmp = Path(str(dst) + ".tmp")
    with open(src, encoding="utf-8") as f, open(tmp, "w", encoding="utf-8") as o:
        for line in f:
            s = line.strip()
            if s.startswith("{"):
                cur = {}
            elif s.startswith("}"):
                if cur.get("Type") in KEEP:
                    name = str(cur.get("Name", "")).replace("\t", " ")
                    blk = str(cur.get("Source", "")).replace("/", "\\").rsplit("\\", 1)[-1]
                    o.write(f"{name}\t{cur['Type']}\t{blk}\n")
                    n += 1
                cur = {}
            else:
                m = KV.match(line)
                if m and m.group(1) in ("Name", "Type", "Source"):
                    v = m.group(2)
                    cur[m.group(1)] = json.loads(v) if v.startswith('"') else v
    tmp.replace(dst)
    return n


def main():
    ap = argparse.ArgumentParser(description="게임 파일 검색 지도를 만든다")
    ap.add_argument("--from", dest="src", help="이미 있는 전체 지도 JSON (간추리기만)")
    a = ap.parse_args()
    c = cfg()
    dst = Path(c["map_file"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    if a.src:
        src, delete = Path(a.src), False
    else:
        tmpdir = ROOT / "map" / "full_tmp"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)   # 이 스크립트가 지난번에 끝내지 못하고 남긴 임시 폴더
        if free_gb(ROOT) < NEED_GB:
            raise SystemExit(f"{ROOT}가 있는 드라이브에 빈 공간이 {free_gb(ROOT):.1f} GB뿐입니다. 지도를 만들려면 {NEED_GB} GB쯤 필요합니다.")
        tmpdir.mkdir(parents=True)
        t0 = time.time()
        print("전체 지도를 만드는 중 (약 7분)...", flush=True)
        log = ROOT / "map" / "build_log.txt"
        code, _ = run_cli([c["game_blocks"], str(tmpdir), "--game", "ZZZ", "--map_op", "AssetMap",
                           "--map_type", "JSON", "--map_name", "zzz_full"], log=log)
        print(f"전체 지도: 종료 코드 {code}, {time.time() - t0:.0f}초")
        src, delete = tmpdir / "zzz_full.json", True
        if code != 0 or not src.exists():
            raise SystemExit(f"전체 지도를 못 만들었습니다. 로그: {log}")
    n = compact(src, dst)
    if delete:
        shutil.rmtree(src.parent)   # 이 스크립트가 방금 만든 임시 폴더만 지운다
    info = {"made": time.strftime("%Y-%m-%d %H:%M"), "entries": n, "game_version": game_version()}
    (dst.parent / "map_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"간추린 지도: {dst} ({n}개 항목, {dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
