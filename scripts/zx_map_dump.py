# 게임 FBX(모델만)와 ZZ-Model-Importer-Assets 덤프를 맞춰, 부위(Body/Torso/Legs/Hair...)마다
# "덤프 팔레트 번호 → 실제 뼈 이름" 표를 만들고 검산한다.
#   python -X utf8 zx_map_dump.py <코드명> [덤프 폴더 이름 또는 전체 경로]
#   (덤프 폴더를 안 주면 plan의 input_name → dump_root\<이름> 을 시도)
# 모델 FBX는 Blender(zx_read_fbx_blender.py)로 읽어 characters\<코드명>\fbx_data\에 저장해 두고, FBX가 바뀌면 다시 읽는다.
# 결과: characters\<코드명>\dump_map\<덤프 폴더 이름>\<부위>_palette_to_bone.json, dump_map_report.json
import argparse
import collections
import itertools
import json
import re
import sys
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
from zx_common import cfg, char_dir, load_plan, optional_path, run_blender  # noqa: E402

# 덤프 좌표 → FBX 좌표 후보: 축 순서 6 × 부호 8 × 배율 3
AXES = [(p, sg, s) for p in itertools.permutations(range(3)) for sg in itertools.product((1, -1), repeat=3)
        for s in (1.0, 0.01, 100.0)]


def parse_vb(path):
    """ZZMI 덤프 vb0 텍스트를 {의미(POSITION 등): (정점 수, 성분 수) 배열}로 읽는다."""
    data, n = {}, None
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.startswith("vertex count:"):
                n = int(line.split(":")[1])
            m = re.match(r"vb0\[(\d+)\]\+\d+ (\w+): (.*)", line)
            if m:
                if n is None:
                    raise ValueError(f"{path}: 'vertex count:' 줄보다 정점 데이터가 먼저 나옵니다")
                i, s = int(m.group(1)), m.group(2)
                v = [float(x) for x in m.group(3).split(",")]
                if s not in data:
                    data[s] = np.zeros((n, len(v)))
                data[s][i] = v
    return data


def transform(dp, p, sg, s):
    return dp[:, list(p)] * np.array(sg) * s


def best_axis(dp, gp_list):
    """정점 순서가 같다고 보고, 덤프 좌표를 FBX 좌표에 가장 가깝게 맞추는 (거리 중앙값, 축, 부호, 배율, 메시 번호)"""
    best = None
    for p, sg, s in AXES:
        q = transform(dp, p, sg, s)
        for gi, gp in enumerate(gp_list):
            if len(gp) != len(dp):
                continue
            d = float(np.median(np.linalg.norm(q - gp, axis=1)))
            if best is None or d < best[0]:
                best = (d, p, sg, s, gi)
    return best


def best_axis_nearest(dp, tree):
    """정점 순서가 다를 때: 덤프 정점 1/20을 모든 FBX 정점의 KD 트리에 물어 가장 가깝게 맞는 (거리 중앙값, 축, 부호, 배율)"""
    best = None
    for p, sg, s in AXES:
        dd, _ = tree.query(transform(dp, p, sg, s)[::20])
        m = float(np.median(dd))
        if best is None or m < best[0]:
            best = (m, p, sg, s)
    return best


def load_fbx_data(base):
    """모델 FBX를 Blender로 읽은 결과(fbx_data)를 쓴다. 없거나 FBX가 더 새것이면 다시 읽는다."""
    fbx = next(iter(sorted((base / "model").glob("*.fbx"))), None)
    if fbx is None:
        raise SystemExit(f"모델 FBX가 없습니다: {base / 'model'} (먼저 zx_extract.py로 뽑으세요)")
    fd = base / "fbx_data"
    info = fd / "game_fbx_info.json"
    if not info.exists() or info.stat().st_mtime < fbx.stat().st_mtime:
        print("모델 FBX를 Blender로 읽는 중...", flush=True)
        for old in fd.glob("mesh_*.npz"):
            old.unlink()   # 이 스크립트가 만든 캐시만 지운다
        run_blender("zx_read_fbx_blender.py", [fbx, fd], base / "log_read_fbx.txt")
    meshes = {}
    for f in sorted(fd.glob("mesh_*.npz")):
        with np.load(f) as z:
            meshes[f.stem[5:]] = {"co": z["co"], "wi": z["wi"], "ww": z["ww"], "gn": [str(x) for x in z["gnames"]]}
    if not meshes:
        raise SystemExit(f"FBX에서 메시를 못 읽었습니다. 로그: {base / 'log_read_fbx.txt'}")
    return meshes


def main():
    ap = argparse.ArgumentParser(description="ZZMI 덤프 팔레트 번호 → 게임 뼈 이름 표를 만든다")
    ap.add_argument("code", help="게임 속 코드명")
    ap.add_argument("dump", nargs="?", help="덤프 폴더 이름(설정의 dump_root 아래) 또는 전체 경로")
    a = ap.parse_args()
    c = cfg()
    base = char_dir(a.code)
    plan = load_plan(a.code)
    if a.dump and Path(a.dump).is_absolute():
        dump = Path(a.dump)
    else:
        dump = optional_path(c, "dump_root", "덤프 대조") / (a.dump or plan["input_name"])
    if not dump.is_dir():
        raise SystemExit(f"덤프 폴더가 없습니다: {dump}")
    meshes = load_fbx_data(base)
    names = list(meshes)
    allco = np.concatenate([meshes[k]["co"] for k in names])
    owner = np.concatenate([np.full(len(meshes[k]["co"]), i) for i, k in enumerate(names)])
    local = np.concatenate([np.arange(len(meshes[k]["co"])) for k in names])
    tree = cKDTree(allco)   # 모든 FBX 정점. 순서가 다른 부위를 짝지을 때 쓰며, 한 번만 만든다
    out = base / "dump_map" / dump.name; out.mkdir(parents=True, exist_ok=True)   # 덤프 폴더마다 따로
    rep = {"dump": str(dump), "components": {}}

    # 덤프 부위: <이름><부위><파트 글자>-vb0=<hash>.txt (파트 A/B/..는 같은 VB) 또는 프레임 덤프식 <이름><부위>-vb0=<hash>.txt
    comps = {}
    for vbf in sorted(dump.glob("*-vb0=*.txt")):
        stem = vbf.name.split("-vb0=")[0]
        m = re.match(r"(.+[a-z0-9])[A-Z]$", stem)
        comp = m.group(1) if m else stem
        comps.setdefault(comp, vbf)
    for comp, vbf in comps.items():
        vb = parse_vb(vbf)
        if "POSITION" not in vb or "BLENDINDICES" not in vb:
            rep["components"][comp] = {"skip": "위치나 웨이트가 없음"}
            continue
        dp, di = vb["POSITION"], vb["BLENDINDICES"].astype(int)
        r = {"verts": len(dp)}
        wkey = next((k for k in ("BLENDWEIGHTS", "BLENDWEIGHT") if k in vb), None)
        if wkey:
            dw = vb[wkey]
            if dw.shape[1] < di.shape[1]:   # 마지막 웨이트가 생략된 형식: 1 - 합
                dw = np.concatenate([dw, 1 - dw.sum(1, keepdims=True)], 1)
        else:   # 웨이트 없이 뼈 번호만 있는 부위(얼굴 등): 첫 번호에 1
            dw = np.zeros(di.shape); dw[:, 0] = 1; r["weights"] = "없음(첫 뼈 번호에 1로 봄)"
        cand = [k for k in names if len(meshes[k]["co"]) == len(dp)]
        if cand:
            b = best_axis(dp, [meshes[k]["co"] for k in cand])
            d, p, sg, s, gi = b
            mk = cand[gi]; G = meshes[mk]
            q = transform(dp, p, sg, s)
            dist = np.linalg.norm(q - G["co"], axis=1)
            r.update({"fbx_mesh": mk, "axis": {"perm": p, "sign": sg, "scale": s}, "same_order_dist_p99": float(np.percentile(dist, 99))})
            order = np.arange(len(dp))
            if np.percentile(dist, 99) > 1e-4:
                order = None
        else:
            order = None
        if order is None:
            # 정점 수가 다르거나 순서가 다름: 모든 메시를 합쳐 가장 가까운 정점으로 짝짓기
            _, p, sg, s = best_axis_nearest(dp, tree)
            dd, ii = tree.query(transform(dp, p, sg, s))
            mk = names[int(np.bincount(owner[ii]).argmax())]; G = meshes[mk]
            order = local[ii]
            r.update({"fbx_mesh": mk, "axis": {"perm": p, "sign": sg, "scale": s}, "match": "가장 가까운 정점",
                      "nearest_median": float(np.median(dd)), "nearest_max": float(dd.max()),
                      "other_mesh_hits": int((owner[ii] != names.index(mk)).sum())})
            if np.median(dd) > 2e-4:   # 0.2 mm보다 멀면 같은 메시가 아님 (무기처럼 모델 FBX에 없는 부위)
                r = {"verts": len(dp), "skip": "모델 FBX에 맞는 메시 없음 (무기·별도 모델일 수 있음)",
                     "nearest_median": float(np.median(dd))}
                rep["components"][comp] = r
                print(comp, json.dumps(r, ensure_ascii=False))
                continue
        # 팔레트 번호 → 뼈 이름 (같은 웨이트 값끼리 투표)
        votes = collections.defaultdict(collections.Counter)
        for v in range(len(dp)):
            g = order[v]
            bb = [(G["ww"][g, k], G["gn"][G["wi"][g, k]]) for k in range(G["wi"].shape[1]) if G["wi"][g, k] >= 0 and G["ww"][g, k] > 1e-4]
            for k in range(di.shape[1]):
                if dw[v, k] > 1e-4:
                    for wb, nb in bb:
                        if abs(dw[v, k] - wb) < 2e-3:
                            votes[int(di[v, k])][nb] += 1
        pal = {i: votes[i].most_common(1)[0][0] for i in sorted(votes)}
        used = sorted(set(int(x) for x in np.unique(di[dw > 1e-4])))
        # 검산
        err = []
        for v in range(len(dp)):
            g = order[v]; A = collections.Counter(); B = collections.Counter()
            for k in range(di.shape[1]):
                if dw[v, k] > 1e-4: A[pal.get(int(di[v, k]), "?")] += dw[v, k]
            for k in range(G["wi"].shape[1]):
                if G["wi"][g, k] >= 0: B[G["gn"][G["wi"][g, k]]] += G["ww"][g, k]
            err.append(sum(abs(A[n] - B[n]) for n in set(A) | set(B)))
        err = np.array(err)
        r.update({"palette_used": len(used), "palette_mapped": len(pal), "unmapped": [i for i in used if i not in pal],
                  "check_weight_L1": {"median": float(np.median(err)), "p99": float(np.percentile(err, 99)),
                                      "max": float(err.max()), "verts_over_0.05": int((err > 0.05).sum())}})
        (out / f"{comp}_palette_to_bone.json").write_text(json.dumps({str(k): v for k, v in pal.items()}, ensure_ascii=False, indent=1), encoding="utf-8")
        rep["components"][comp] = r
        print(comp, json.dumps(r, ensure_ascii=False))
    (out / "dump_map_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
