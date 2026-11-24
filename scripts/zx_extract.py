# plan.json대로 게임 파일 사본을 모아 FBX를 뽑는다: 모델만(model\) / 모델 + 몸 동작 전체(anim\)
#   python -X utf8 zx_extract.py <코드명> [--clips <동작 이름 정규식>] [--with-facial] [--model-only] [--out <폴더 이름>]
#   --clips는 "_Ani_" 다음 동작 이름의 앞부분에 맞춘다. 예: --clips "Idle_Loop|Attack_Normal_01"
# 게임 폴더는 읽기만 한다(필요한 .blk만 characters\<코드명>\input에 복사, 게임 업데이트로 바뀐 파일은 새로 복사).
# 출력 폴더가 이미 있으면 덮어쓰지 않고 건너뛴다.
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from zx_common import cfg, char_dir, copy_if_changed, game_version, hook_env, load_plan, run_cli  # noqa: E402

NO_CLIPS = r"^ZX_NO_CLIP_MATCHES$"   # 모델만 뽑을 때: 어떤 동작 이름에도 안 맞는 정규식


def clip_regex(plan, names=None, facial=False):
    """훅에 넘길 동작 이름 정규식. 항상 이 모델의 동작(<모델>_Ani_...)만 잡는다.
    같은 게임 파일에 다른 모습(Pheony_Illness 등)의 같은 이름 동작이 섞여 있어서, 앞부분을 고정해야 한다.
    names: '_Ani_' 다음 동작 이름의 앞부분에 맞출 정규식 (예: 'Idle_Loop|Attack_Normal_01'). 없으면 몸 동작 전체."""
    pre = "^" + re.escape(plan["model_animator"][:-len("_Model")]) + "_Ani_"
    if names:
        return pre + "(?:" + names + ")"
    return pre + ("" if facial else "(?!.*Facial)")


def gather_input(plan, model_only, c):
    """필요한 게임 파일을 input\\에 모으고 목록 파일을 쓴다."""
    base = char_dir(plan["code"])
    blks = sorted(set(plan["model_blks"] + plan["mesh_blks"] + ([] if model_only else plan["clip_blks"])))
    src = Path(c["game_blocks"])
    missing = [b for b in blks if not (src / b).exists()]
    if missing:
        raise SystemExit(f"게임 폴더에 없는 파일 {len(missing)}개 (예: {missing[0]}). 게임이 업데이트됐다면 지도와 plan을 다시 만드세요 "
                         "(zx_build_map.py → zx_find.py).")
    inp = base / "input"
    inp.mkdir(parents=True, exist_ok=True)
    fresh = sum(copy_if_changed(src / b, inp / b) for b in blks)
    lst = base / "input_list.txt"
    lst.write_text("\n".join(str(inp / b) for b in blks), encoding="utf-8")
    mb = sum((inp / b).stat().st_size for b in blks) / 1e6
    print(f"게임 파일 {len(blks)}개 ({mb:.0f} MB), 이번에 복사 {fresh}개")
    return blks, lst


def export(plan, c, lst, outname, clip_rx):
    """훅으로 모델(+동작)을 FBX로 내보낸다. 출력 폴더가 이미 차 있으면 건너뛰고 None."""
    base = char_dir(plan["code"])
    out = base / outname
    if out.exists() and any(out.iterdir()):
        print(f"이미 있어서 건너뜀(덮어쓰지 않음): {out}")
        return None
    t0 = time.time()
    log = base / f"log_{outname}.txt"
    code, text = run_cli(["x", "x", "--game", "ZZZ"], env_extra=hook_env(c, lst, out, plan["model_animator"], clip_rx), log=log)
    fbx = sorted(out.glob("*.fbx")) if out.exists() else []
    hook = [ln for ln in text.splitlines() if ln.startswith("[훅") or "SeparateMesh attached" in ln]
    clips = next((int(m.group(1)) for ln in hook for m in [re.match(r"\[훅\] 동작 (\d+)개", ln)] if m), None)
    if code != 0 or not fbx:
        raise SystemExit(f"{outname} 내보내기 실패 (종료 코드 {code}). 로그: {log}")
    r = {"seconds": round(time.time() - t0), "clips": clips, "fbx": [str(f) for f in fbx],
         "fbx_mb": [round(f.stat().st_size / 1e6, 1) for f in fbx]}
    print(f"{outname}: FBX {len(fbx)}개 ({', '.join(f'{m} MB' for m in r['fbx_mb'])}), 동작 {clips if clips is not None else '?'}개, {r['seconds']}초")
    return r


def main():
    ap = argparse.ArgumentParser(description="plan.json대로 모델·동작 FBX를 뽑는다")
    ap.add_argument("code", help="게임 속 코드명 (zx_find.py 결과)")
    ap.add_argument("--clips", help="동작 이름(_Ani_ 다음) 앞부분 정규식, 예: 'Idle_Loop|Attack_Normal_01' (기본: 얼굴 동작을 뺀 몸 동작 전체)")
    ap.add_argument("--with-facial", action="store_true", help="얼굴 동작도 넣는다")
    ap.add_argument("--model-only", action="store_true", help="모델만 뽑는다")
    ap.add_argument("--out", default="anim", help="동작 FBX 출력 폴더 이름 (기본 anim)")
    a = ap.parse_args()
    c = cfg()
    plan = load_plan(a.code)
    gv = game_version()
    if plan.get("game_version") and gv and plan["game_version"] != gv:
        print(f"주의: plan은 게임 {plan['game_version']} 때 만든 것입니다 (지금 {gv}). 실패하면 지도와 plan을 다시 만드세요.")
    clip_rx = clip_regex(plan, a.clips, a.with_facial)
    re.compile(clip_rx)   # 잘못된 정규식이면 여기서 바로 알린다
    blks, lst = gather_input(plan, a.model_only, c)
    rep = {"code": a.code, "game_version": gv, "clips_regex": clip_rx, "blks": blks,
           "model": export(plan, c, lst, "model", NO_CLIPS)}
    if not a.model_only:
        rep[a.out] = export(plan, c, lst, a.out, clip_rx)
    (char_dir(a.code) / "extract_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
