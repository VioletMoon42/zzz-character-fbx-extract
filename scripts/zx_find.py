# 캐릭터 이름으로 게임 속 이름(코드명)·모델·메시·동작이 든 게임 파일(.blk)을 찾아 plan.json을 만든다 (읽기만)
#   python -X utf8 zx_find.py <이름>                 예: Astra, Phoenix(→ Pheony), Claret
#   python -X utf8 zx_find.py <이름> --code <코드명>  후보가 여럿일 때 코드명을 직접 고른다
# 결과: <ROOT>\characters\<코드명>\plan.json. 못 찾으면 후보를 출력한다.
import argparse
import collections
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from zx_common import ROOT, char_dir, game_version, load_map  # noqa: E402

ALIASES_FILE = ROOT / "aliases.json"   # 표시 이름 → 게임 코드명 (예: Phoenix → Pheony). 확정될 때마다 쌓는다.
MODEL_RX = re.compile(r"^Avatar_(?:Female|Male)_Size\d+_([A-Za-z0-9_]+?)_Model$")   # 스킨은 Astra_Chandelier처럼 밑줄 포함


def model_codes(rows):
    """지도에서 캐릭터 모델 Animator를 모아 {코드명: {Animator 이름}}"""
    codes = collections.defaultdict(set)
    for n, t, _ in rows:
        if t == "Animator":
            m = MODEL_RX.match(n)
            if m:
                codes[m.group(1)].add(n)
    return codes


def is_own_mesh(name, code, others):
    """메시 이름이 이 코드명의 것인지. 같은 접두어의 다른 모델(Pheony_Youth, Pheony_Weapon 등)과 LOD는 뺀다."""
    if not name.startswith(code + "_") or re.search(r"_LOD\d+$", name):
        return False
    return not any(name.startswith(o + "_") or name == o for o in others)


def candidates(name, codes):
    part = sorted(c for c in codes if name.lower() in c.lower())
    close = difflib.get_close_matches(name, list(codes), n=8, cutoff=0.5)
    return list(dict.fromkeys(part + close))


def load_aliases():
    return json.loads(ALIASES_FILE.read_text(encoding="utf-8")) if ALIASES_FILE.exists() else {}


def resolve(name, codes, code=None):
    """코드명을 정한다: --code > 별명 > 대소문자 무시 일치. 못 정하면 None."""
    if code:
        return code
    al = load_aliases()
    code = al.get(name) or {k.lower(): v for k, v in al.items()}.get(name.lower())
    if code in codes:
        return code
    return next((c for c in codes if c.lower() == name.lower()), None)


def make_plan(rows, codes, code, name):
    model = sorted(codes[code])[0]
    by_blk = collections.defaultdict(set)
    for n, t, b in rows:
        if t in ("Animator", "Avatar") and n in (model, model + "Avatar"):
            by_blk[b].add((n, t))
    model_blks = sorted(b for b, s in by_blk.items() if (model, "Animator") in s)
    with_avatar = [b for b in model_blks if (model + "Avatar", "Avatar") in by_blk[b]]   # 모델 Avatar가 같이 든 파일 우선
    model_blks = with_avatar or model_blks
    others = [c for c in codes if c != code and c.startswith(code + "_")]
    meshes = collections.defaultdict(set)
    for n, t, b in rows:
        if t == "Mesh" and is_own_mesh(n, code, others):
            meshes[n].add(b)
    clip_rx = re.compile(rf"^Avatar_(?:Female|Male)_Size\d+_{re.escape(code)}_Ani_")
    clips = collections.defaultdict(set)
    for n, t, b in rows:
        if t == "AnimationClip" and clip_rx.match(n):
            clips[b].add(n)
    all_clips = {n for s in clips.values() for n in s}
    return {
        "input_name": name, "code": code, "model_animator": model, "game_version": game_version(),
        "model_blks": model_blks, "mesh_blks": sorted({b for s in meshes.values() for b in s}), "meshes": sorted(meshes),
        "clip_blks": sorted(clips), "body_clip_count": sum("Facial" not in n for n in all_clips),
        "facial_clip_count": sum("Facial" in n for n in all_clips),
        "body_clips": sorted(n for n in all_clips if "Facial" not in n),
        "other_models_same_code_prefix": sorted(others),
    }


def find(name, code=None):
    """찾으면 {"found": True, "plan": ...}(plan.json도 씀), 못 찾으면 {"found": False, "candidates": [...]}"""
    rows = load_map()
    codes = model_codes(rows)
    code = resolve(name, codes, code)
    if code is None:
        return {"found": False, "name": name, "candidates": candidates(name, codes)}
    if code not in codes:
        raise SystemExit(f"코드명 {code}의 모델(Avatar_*_{code}_Model)이 지도에 없습니다. 후보: {', '.join(candidates(code, codes)) or '없음'}")
    plan = make_plan(rows, codes, code, name)
    out = char_dir(code)
    out.mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    if name.lower() != code.lower():
        al = load_aliases()
        al[name] = code
        ALIASES_FILE.write_text(json.dumps(al, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"found": True, "plan": plan}


def main():
    ap = argparse.ArgumentParser(description="캐릭터 이름으로 게임 속 코드명과 필요한 게임 파일을 찾는다")
    ap.add_argument("name", help="캐릭터 이름 (영어, 예: Astra, Phoenix)")
    ap.add_argument("--code", help="게임 속 코드명을 직접 지정 (후보 중에서)")
    a = ap.parse_args()
    r = find(a.name, a.code)
    if not r["found"]:
        print(json.dumps({"찾음": False, "이름": a.name, "후보": r["candidates"],
                          "안내": "후보 중 하나를 --code로 다시 돌리세요."}, ensure_ascii=False, indent=1))
        sys.exit(2)
    short = {k: v for k, v in r["plan"].items() if k != "body_clips"}
    print(json.dumps(short, ensure_ascii=False, indent=1))
    print(f"plan: {char_dir(r['plan']['code']) / 'plan.json'}")


if __name__ == "__main__":
    main()
