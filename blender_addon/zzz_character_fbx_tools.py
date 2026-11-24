# ZZZ Character FBX Tools — zzz-character-fbx-extract의 Blender 애드온 (한 파일)
# 설치: Blender → Edit → Preferences → Add-ons → (오른쪽 위 ▼) Install from Disk… → 이 파일
# 사용: 3D 뷰 오른쪽 사이드바(N) → "ZZZ FBX" 탭
#   1. 게임 캐릭터 불러오기: 뽑은 결과의 .blend(model\ 또는 anim\)를 지금 파일로 가져온다. 동작 이름표·프레임 범위·60 fps까지.
#   2. 선택한 메시를 게임 뼈대에: 내 모드 메시(XXMI/ZZMI로 가져온 것 등)의 사본을 만들어 게임 뼈대에 붙인다.
#      - 버텍스 그룹이 번호(0, 1, 2…)면 palette_to_bone.json(메뉴 4번 결과)으로 뼈 이름을 붙인다. 모드 웨이트가 그대로 쓰인다.
#      - 표가 없으면 게임 몸 메시에서 가장 가까운 웨이트를 옮겨 온다(Data Transfer).
#      - 위치·크기·좌우 반전은 게임 몸 메시에 가장 잘 겹치는 쪽으로 자동으로 맞춘다.
#      원본 메시는 건드리지 않는다. 사본은 "게임 뼈대 시험" 컬렉션에 생긴다.
import json
import re
from itertools import permutations, product
from pathlib import Path

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector
from mathutils.kdtree import KDTree

bl_info = {
    "name": "ZZZ Character FBX Tools",
    "author": "VioletMoon42",
    "version": (1, 2, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > ZZZ FBX",
    "description": "zzz-character-fbx-extract 결과를 불러오고, 모드 메시를 게임 뼈대에 붙여 게임 동작으로 시험한다",
    "category": "Animation",
}

TAG = "zzz_fbx_source"          # 불러온 게임 오브젝트 표시 (값 = 원본 .blend 경로)
TEST_COLL = "게임 뼈대 시험"
# 자료끼리 단위 차이는 100배(cm↔m)뿐이다. 0.1·10을 넣으면 작게 줄인 사본이 몸 점들 사이에 묻혀 거리가 짧게 나와 잘못 고른다
SCALES = (1.0, 0.01, 100.0)


def game_objects(context):
    return [o for o in context.scene.objects if TAG in o]


def game_armature(context):
    arms = [o for o in game_objects(context) if o.type == "ARMATURE"]
    return arms[0] if arms else None


def rest_points(meshes, limit=60000):
    """메시의 rest(변형 전) 정점 위치, 월드 좌표"""
    pts = []
    for m in meshes:
        mw = m.matrix_world
        vs = m.data.vertices
        step = max(1, len(vs) * len(meshes) // limit)
        pts += [mw @ v.co for v in list(vs)[::step]]
    return pts


def top_group(v, names):
    """정점의 가장 큰 웨이트 그룹 이름 (없으면 None)"""
    best = max(v.groups, key=lambda g: g.weight, default=None)
    return names.get(best.group) if best and best.weight > 0 else None


def game_bone_tree(body, xf):
    """게임 메시 rest 정점 → 그 정점의 주 뼈 이름. 모드 웨이트가 맞는지 대조하는 기준"""
    pts, bones = [], []
    for b in body:
        names = {g.index: g.name for g in b.vertex_groups}
        mw = xf @ b.matrix_world
        for v in b.data.vertices:
            n = top_group(v, names)
            if n:
                pts.append(mw @ v.co)
                bones.append(n)
    t = KDTree(len(pts))
    for i, p in enumerate(pts):
        t.insert(p, i)
    t.balance()
    return t, bones


def nearest_bones(c, gtree, gbones, mw, k=8, limit=20000):
    """사본 정점마다 (주 그룹 이름, 가장 가까운 게임 정점의 주 뼈, 가까운 게임 정점 k개의 주 뼈들)"""
    names = {g.index: g.name for g in c.vertex_groups}
    vs = list(c.data.vertices)
    out = []
    for v in vs[:: max(1, len(vs) // limit)]:
        n = top_group(v, names)
        if n is not None:
            near = gtree.find_n(mw @ v.co, k)
            out.append((n, gbones[near[0][1]], {gbones[i] for _, i, _ in near}))
    return out


def agreement(pairs, mapping):
    """모드 그룹 → 뼈 이름 표를 썼을 때 주 뼈가 가까운 게임 정점들의 주 뼈 중 하나인 정점 비율.
    (모드 몸 모양이 원본과 조금 달라 경계에서 이웃 뼈가 이기는 것은 맞은 것으로 본다. 틀린 표는 신발 → 쇄골처럼 동떨어진다)"""
    return sum(mapping.get(n) in gs for n, _, gs in pairs) / max(1, len(pairs))


def median_err(M, src_pts, tree, height):
    sample = src_pts[:: max(1, len(src_pts) // 1500)]
    d = sorted(tree.find(M @ p)[2] for p in sample)
    return d[len(d) // 2] / height


def common_shift(objs, tree, height, rounds=4):
    """선택한 메시 전체를 함께 옮겨 맞출 위치 차이. 게임 자료의 원점이 모드와 몇 cm 다를 때(나히다 glb 등)만 쓰인다.
    메시마다 따로 옮기면 한쪽에만 있는 조각(어깨 장식 등)이 몸 안으로 끌려 들어가므로 전체를 한 번에,
    그리고 전체 오차가 키의 1%를 넘고 옮겨서 25% 넘게 나아질 때만 쓴다."""
    pts = []
    for o in objs:
        src = rest_points([o], limit=20000)
        M = best_fit(src, tree, height)[0][0]
        pts += [M @ p for p in src[:: max(1, len(src) // 1500)]]
    def err(s):
        d = sorted(tree.find(p + s)[2] for p in pts)
        return d[len(d) // 2] / height
    e0 = err(Vector())
    if e0 <= 0.01:
        return Vector()
    s = Vector()
    for _ in range(rounds):
        ds = [tree.find(p + s)[0] - (p + s) for p in pts]
        s += Vector([sorted(d[i] for d in ds)[len(ds) // 2] for i in range(3)])
    return s if err(s) < e0 * 0.75 else Vector()


def vote_mapping(pairs):
    """그룹마다 그 그룹이 주 그룹인 정점들의 '가까운 게임 뼈' 다수결"""
    from collections import Counter, defaultdict
    votes = defaultdict(Counter)
    for n, g, _ in pairs:
        votes[n][g] += 1
    return {n: cnt.most_common(1)[0][0] for n, cnt in votes.items()}


def link_leftovers(c, gtree, gbones, bones, mw):
    """이름을 붙인 뒤에도 뼈 이름이 아닌 그룹(표·다수결에서 빠진, 늘 보조 웨이트로만 쓰이는 번호 등)을
    그 그룹 정점들 자리의 게임 뼈(웨이트 합 다수결)로 연결한다. 그대로 두면 그 몫만큼 정점이 제자리에 남아 길게 늘어난다."""
    from collections import Counter, defaultdict
    left = {g.index: g.name for g in c.vertex_groups if g.name not in bones}
    if not left:
        return 0
    votes = defaultdict(Counter)
    for v in c.data.vertices:
        hit = [(g.group, g.weight) for g in v.groups if g.group in left and g.weight > 0]
        if hit:
            b = gbones[gtree.find(mw @ v.co)[1]]
            for gi, w in hit:
                votes[left[gi]][b] += w
    rename_groups(c, {n: cnt.most_common(1)[0][0] for n, cnt in votes.items()})
    return len(votes)


def rename_groups(c, mapping):
    """그룹 이름을 바꾼다. 같은 뼈로 모이는 그룹은 웨이트를 더해 하나로 합친다"""
    old = {g.index: g.name for g in c.vertex_groups}
    per = {}
    for v in c.data.vertices:
        for g in v.groups:
            if g.weight > 0:
                n = old[g.group]
                n = mapping.get(n, n)
                d = per.setdefault(v.index, {})
                d[n] = d.get(n, 0.0) + g.weight
    c.vertex_groups.clear()
    groups = {}
    for vi, d in per.items():
        for n, w in d.items():
            vg = groups.get(n) or groups.setdefault(n, c.vertex_groups.new(name=n))
            vg.add([vi], min(1.0, w), "REPLACE")


def candidate_matrices():
    for perm in permutations(range(3)):
        for signs in product((1, -1), repeat=3):
            m = Matrix.Identity(3)
            for r in range(3):
                for c in range(3):
                    m[r][c] = signs[r] if perm[r] == c else 0
            for s in SCALES:
                yield (m * s).to_4x4()


def best_fit(src_pts, tree, height):
    """src 점들을 게임 몸에 겹치게 하는 축 바꿈·반전·크기 후보 (원점 기준). [(행렬, 중앙 거리 / 키)] 가까운 순"""
    sample = src_pts[:: max(1, len(src_pts) // 1500)]
    out = []
    for M in candidate_matrices():
        d = sorted(tree.find(M @ p)[2] for p in sample)
        out.append((M, d[len(d) // 2] / height))
    out.sort(key=lambda x: x[1])
    return out


def find_palette(src_blend, obj):
    """원본 .blend 옆 dump_map\\**\\<부위>_palette_to_bone.json 중 이 메시의 부위에 맞는 것.
    모드 불러오기로 만든 메시는 부위 단어(zzz_component, 예: Body)로, 그 밖에는 이름이 부위 이름으로 시작하는지로 찾는다."""
    if not src_blend:
        return None
    root = Path(src_blend).parents[1] / "dump_map"
    if not root.exists():
        return None
    comp = str(obj.get("zzz_component", "")).lower()
    base = re.split(r"[-.=]", obj.name)[0].lower()
    best = None
    for f in root.rglob("*_palette_to_bone.json"):
        part = f.name[: -len("_palette_to_bone.json")].lower()
        ok = part.endswith(comp) if comp else base.startswith(part)
        if ok and (best is None or len(part) > len(best[0])):
            best = (part, f)
    return best[1] if best else None


def all_palettes(src_blend):
    if not src_blend:
        return []
    root = Path(src_blend).parents[1] / "dump_map"
    return sorted(root.rglob("*_palette_to_bone.json")) if root.exists() else []


def parse_mod_ini(path):
    """ZZMI 모드 ini에서 (버퍼, 그리기 범위)를 읽는다.
    돌려주는 값: 부위 목록 [{"component", "ib", "position", "blend", "draws": [(이름, 개수, 시작)]}]"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    res, sections = {}, []
    cur = None
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^\[(.+)\]$", s)
        if m:
            cur = {"name": m.group(1), "lines": []}
            sections.append(cur)
        elif cur is not None:
            cur["lines"].append(s)
    for sec in sections:
        if sec["name"].startswith("Resource"):
            kv = dict(re.match(r"^(\w+)\s*=\s*(.*)$", ln).groups() for ln in sec["lines"] if re.match(r"^\w+\s*=", ln))
            if "filename" in kv:
                res[sec["name"]] = {"file": Path(path).parent / kv["filename"].strip(), "stride": int(kv.get("stride", 0) or 0)}
    stems = {n[: -len("Position")] for n in res if n.endswith("Position")}
    parts = []
    for sec in sections:
        ib = next((ln.split("=", 1)[1].strip() for ln in sec["lines"] if re.match(r"^ib\s*=", ln)), None)
        if not ib or ib not in res:
            continue
        stem = max((s for s in stems if ib.startswith(s)), key=len, default=None)
        if stem is None:
            continue
        draws, label, seen = [], None, set()
        for ln in sec["lines"]:
            if ln.startswith(";"):
                label = ln.lstrip("; ").strip()
            m = re.match(r"^drawindexed\s*=\s*(\d+)\s*,\s*(\d+)", ln)
            if m and (m.group(1), m.group(2)) not in seen:
                seen.add((m.group(1), m.group(2)))
                draws.append((label or f"{int(m.group(2))}", int(m.group(1)), int(m.group(2))))
        word = re.search(r"([A-Z][a-z]+)$", stem.split("_")[-1])
        parts.append({"section": sec["name"].replace("TextureOverride", ""), "component": word.group(1) if word else stem,
                      "ib": res[ib], "position": res.get(stem + "Position"), "blend": res.get(stem + "Blend"), "draws": draws})
    return parts


def build_mod_mesh(name, part, count, start):
    """한 그리기 범위를 메시 오브젝트로 (XXMI ZZZ 가져오기와 같은 좌우 반전, 번호 버텍스 그룹)"""
    import numpy as np
    cache = part.setdefault("_cache", {})   # 같은 부위의 그리기 범위끼리 버퍼를 한 번만 읽는다
    if "ib" not in cache:
        cache["ib"] = np.fromfile(part["ib"]["file"], dtype=np.uint32)
        ps = part["position"]["stride"] or 40
        cache["pos"] = np.fromfile(part["position"]["file"], dtype=np.uint8).reshape(-1, ps)[:, :12].copy().view(np.float32)
        if part.get("blend") and part["blend"]["file"].exists():
            bs = part["blend"]["stride"] or 32
            cache["blend"] = np.fromfile(part["blend"]["file"], dtype=np.uint8).reshape(-1, bs)
    ib = cache["ib"][start:start + count]
    pos = cache["pos"]
    used, inv = np.unique(ib, return_inverse=True)
    co = pos[used].astype(np.float32)
    co[:, 0] *= -1                                   # x 반전 (XXMI ZZZ 프리셋과 같게)
    tris = inv.reshape(-1, 3)[:, ::-1]               # 반전했으니 면 방향도 뒤집는다
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(tris.size)
    me.loops.foreach_set("vertex_index", tris.ravel().astype(np.int32))
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", np.arange(0, tris.size, 3, dtype=np.int32))
    me.update(calc_edges=True)
    ob = bpy.data.objects.new(name, me)
    if "blend" in cache:
        raw = cache["blend"][used]
        w = raw[:, :16].copy().view(np.float32)       # BLENDWEIGHTS 4개
        idx = raw[:, 16:32].copy().view(np.uint32)    # BLENDINDICES 4개
        # 같은 (그룹, 웨이트) 정점을 한 번에 넣는다 (정점마다 넣으면 수십만 정점에서 몇십 분 걸림)
        vi = np.repeat(np.arange(len(used)), 4)
        gi = idx.ravel()
        wq = np.round(w.ravel() * 4096).astype(np.int64)   # 1/4096 단위 (모드 웨이트는 보통 8비트라 손실 없음)
        keep = wq > 0
        vi, gi, wq = vi[keep], gi[keep], wq[keep]
        order = np.lexsort((wq, gi))
        vi, gi, wq = vi[order], gi[order], wq[order]
        cut = np.nonzero((np.diff(gi) != 0) | (np.diff(wq) != 0))[0] + 1
        vgs = {}
        for s, e in zip(np.r_[0, cut], np.r_[cut, len(vi)]):
            g = int(gi[s])
            vg = vgs.get(g) or vgs.setdefault(g, ob.vertex_groups.new(name=str(g)))
            vg.add(vi[s:e].tolist(), float(wq[s]) / 4096.0, "ADD")
        # 이름순(숫자)으로 그룹 순서 정리는 하지 않는다: 이름이 곧 팔레트 번호다
    return ob


class ZZZFBX_OT_import_mod(bpy.types.Operator, ImportHelper):
    """ZZMI 모드(ini + .ib/.buf)를 메시로 가져온다. 그리기 범위(토글 부분)마다 따로 나눈다"""
    bl_idname = "zzz_fbx.import_mod"
    bl_label = "모드 불러오기 (ZZMI)"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".ini"
    filter_glob: StringProperty(default="*.ini", options={"HIDDEN"})

    def execute(self, context):
        parts = parse_mod_ini(self.filepath)
        parts = [p for p in parts if p["position"] and p["position"]["file"].exists() and p["ib"]["file"].exists()]
        if not parts:
            self.report({"ERROR"}, "이 ini에서 메시 버퍼(Position/IB)를 못 찾았습니다")
            return {"CANCELLED"}
        coll = bpy.data.collections.new("모드 " + Path(self.filepath).stem)
        context.scene.collection.children.link(coll)
        n = 0
        for p in parts:
            sub = bpy.data.collections.new(p["section"])
            coll.children.link(sub)
            for label, count, start in p["draws"]:
                ob = build_mod_mesh(label[:60], p, count, start)
                ob["zzz_component"] = p["component"]
                sub.objects.link(ob)
                n += 1
        self.report({"INFO"}, f"모드 메시 {n}개를 '{coll.name}' 컬렉션에 가져왔습니다 (토글 부분이 겹쳐 보일 수 있습니다)")
        return {"FINISHED"}


class ZZZFBX_OT_load(bpy.types.Operator, ImportHelper):
    """뽑은 결과의 .blend에서 게임 캐릭터(뼈대·메시·동작)를 지금 파일로 가져온다"""
    bl_idname = "zzz_fbx.load_character"
    bl_label = "게임 캐릭터 불러오기"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".blend"
    filter_glob: StringProperty(default="*.blend", options={"HIDDEN"})

    def execute(self, context):
        path = self.filepath
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.scenes = src.scenes[:1]
        if not dst.scenes:
            self.report({"ERROR"}, "장면이 없는 파일입니다")
            return {"CANCELLED"}
        s = dst.scenes[0]
        coll = bpy.data.collections.new(Path(path).stem)
        context.scene.collection.children.link(coll)
        objs = list(s.objects)
        for o in objs:
            coll.objects.link(o)
            o[TAG] = path
        sc = context.scene
        sc.render.fps, sc.render.fps_base = s.render.fps, s.render.fps_base
        sc.frame_start, sc.frame_end = s.frame_start, s.frame_end
        for m in s.timeline_markers:
            if m.name not in sc.timeline_markers:
                sc.timeline_markers.new(m.name, frame=m.frame)
        bpy.data.scenes.remove(s)
        arm = game_armature(context)
        self.report({"INFO"}, f"불러옴: 오브젝트 {len(objs)}개, 뼈대 {arm.name if arm else '없음'}, 동작 이름표 {len(sc.timeline_markers)}개")
        return {"FINISHED"}


class ZZZFBX_OT_bind(bpy.types.Operator):
    """선택한 메시의 사본을 만들어 게임 뼈대에 붙인다 (원본은 그대로)"""
    bl_idname = "zzz_fbx.bind_selected"
    bl_label = "선택한 메시를 게임 뼈대에"
    bl_options = {"REGISTER", "UNDO"}

    palette: StringProperty(name="팔레트 표", subtype="FILE_PATH",
                            description="palette_to_bone.json (비우면 불러온 캐릭터의 dump_map에서 이름으로 찾는다)")

    def execute(self, context):
        arm = game_armature(context)
        if arm is None:
            self.report({"ERROR"}, "먼저 '게임 캐릭터 불러오기'로 게임 캐릭터를 가져오세요")
            return {"CANCELLED"}
        body = [o for o in game_objects(context) if o.type == "MESH"]
        sel = [o for o in context.selected_objects if o.type == "MESH" and TAG not in o]
        if not sel:
            self.report({"ERROR"}, "붙일 내 메시를 선택하세요 (불러온 게임 메시 말고)")
            return {"CANCELLED"}
        # 게임 메시 자신의 좌표(정점 데이터 그대로)에서 맞춘다. 모드 데이터와는 축 바꿈·반전·단위만 다르다.
        # 뼈대 오브젝트 자체가 프레임마다 움직이고 도는 자료(glTF 등)도 이 좌표는 변하지 않는다.
        # 사본은 게임 메시와 같은 부모·변환을 받아 게임 메시와 똑같이 따라간다.
        # 게임 메시에 zzz_rest_matrix(메시 데이터 → 바로 선 게임 좌표)가 있으면 그 좌표에서, 없으면 월드 좌표에서 맞춘다.
        ref = max(body, key=lambda b: len(b.data.vertices))
        W = Matrix(ref["zzz_rest_matrix"]) if "zzz_rest_matrix" in ref else ref.matrix_world.copy()
        ainv = W @ ref.matrix_world.inverted()
        gp = [ainv @ p for p in rest_points(body)]
        tree = KDTree(len(gp))
        for i, p in enumerate(gp):
            tree.insert(p, i)
        tree.balance()
        height = max(max(p[i] for p in gp) - min(p[i] for p in gp) for i in range(3))

        coll = bpy.data.collections.get(TEST_COLL) or bpy.data.collections.new(TEST_COLL)
        if coll.name not in context.scene.collection.children:
            context.scene.collection.children.link(coll)
        src_blend = arm.get(TAG)
        gtree = gbones = None
        shift = None
        lines = []
        for o in sel:
            c = o.copy()
            c.data = o.data.copy()
            c.name = o.name + "_게임뼈대"
            c.parent = ref.parent
            c.parent_type = ref.parent_type
            c.parent_bone = ref.parent_bone
            c.matrix_parent_inverse = ref.matrix_parent_inverse.copy()
            for md in [m for m in c.modifiers if m.type == "ARMATURE"]:
                c.modifiers.remove(md)
            coll.objects.link(c)
            # 1) 위치 맞추기 (후보를 거리순으로; 몸은 거의 좌우 대칭이라 거울상도 거리가 비슷하다)
            base = o.matrix_world.copy()
            src = rest_points([o])
            fits = best_fit(src, tree, height)
            if shift is None:
                shift = common_shift(sel, tree, height)
            if shift.length:
                fits = [(Matrix.Translation(shift) @ Mi, ei) for Mi, ei in fits[:12]]
                fits = sorted(((Mi, median_err(Mi, src, tree, height)) for Mi, _ in fits), key=lambda f: f[1])
            M, err = fits[0]
            c.matrix_basis = ref.matrix_basis @ W.inverted() @ M @ base
            # 2) 웨이트
            names = [g.name for g in c.vertex_groups]
            numeric = names and all(n.isdigit() for n in names)
            bones = set(arm.data.bones.keys())
            if numeric:
                if self.palette:
                    cands = [Path(bpy.path.abspath(self.palette))]
                else:
                    first = find_palette(src_blend, o)
                    cands = ([first] if first else []) + [p for p in all_palettes(src_blend) if p != first]
                cands = [p for p in cands if p.exists()]
                # (표 이름, 표). 파일 표 + 뼈대에 담긴 표(다른 도구가 게임 스킨 순서대로 넣어 둔 것, 속성 zzz_palette_tables)
                tables = [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in cands]
                if not self.palette and arm.get("zzz_palette_tables"):
                    tables += list(json.loads(arm["zzz_palette_tables"]).items())
                tables = [(k, {i: b for i, b in t.items() if b in bones}) for k, t in tables]
                if not tables:
                    lines.append(f"{o.name}: 번호 그룹인데 palette_to_bone.json을 못 찾음 → 게임 몸에서 웨이트를 옮김")
                    self.transfer(context, c, body)
                    how = f"위치 오차 {err * 100:.1f}% (키 대비), 웨이트 옮김"
                else:
                    # 표대로 붙이기 전에, 표가 이 모드에 맞는지 게임 메시와 대조한다.
                    # (모드가 예전 게임 버전에서 만들어졌거나 뼈 번호를 다르게 쓰면 신발이 팔 뼈를 따라가는 식으로 흩어진다)
                    # 이름으로 고른 표가 없거나 안 맞으면 다른 부위 표도 대 보고 가장 잘 맞는 것을 쓴다.
                    # 거리가 비슷한 위치 후보(거울상 등)도 함께 대 보고, 뼈가 가장 잘 맞는 쪽을 고른다(좌우 뒤바뀜 방지).
                    if gtree is None:
                        gtree, gbones = game_bone_tree(body, ainv)
                    best = None
                    for Mi, ei in [f for f in fits if f[1] <= fits[0][1] * 1.15 + 0.0005][:6]:
                        pairs_i = nearest_bones(c, gtree, gbones, Mi @ base)
                        for label, t in tables:
                            ok = agreement(pairs_i, t)
                            if best is None or (ok, -ei) > (best[0], -best[4]):
                                best = (ok, label, t, Mi, ei, pairs_i)
                    ok_table, f, table, M, err, pairs = best
                    c.matrix_basis = ref.matrix_basis @ W.inverted() @ M @ base
                    how = f"위치 오차 {err * 100:.1f}% (키 대비)"
                    voted = vote_mapping(pairs)
                    ok_vote = agreement(pairs, voted)
                    if ok_table >= 0.5:
                        rename_groups(c, table)
                        how += f", 표 {f} (게임 메시와 주 뼈 일치 {ok_table:.0%})"
                    elif ok_vote >= 0.6:
                        rename_groups(c, voted)
                        how += (f", 표가 이 모드와 안 맞음(일치 {ok_table:.0%}) → 그룹마다 가까운 게임 뼈로 다시 연결"
                                f" (일치 {ok_vote:.0%}, 모드 웨이트 모양은 유지)")
                    else:
                        self.transfer(context, c, body)
                        how += f", 표가 이 모드와 안 맞음(일치 {ok_table:.0%}) → 게임 몸에서 웨이트를 옮김"
                    n_left = link_leftovers(c, gtree, gbones, bones, M @ base)
                    if n_left:
                        how += f", 남은 번호 그룹 {n_left}개는 그 자리의 게임 뼈로"
            else:
                how = f"위치 오차 {err * 100:.1f}% (키 대비)"
                if not (set(names) & bones):
                    self.transfer(context, c, body)
                    how += ", 웨이트 옮김"
            # 3) 뼈대에 붙이기. 뼈대 오브젝트 자체가 움직이는 자료(glTF 등)도 따라가게 뼈대의 자식으로(지금 위치 유지)
            md = c.modifiers.new("게임 뼈대", "ARMATURE")
            md.object = arm
            lines.append(f"{c.name}: {how}" + ("  ← 많이 어긋남, 결과를 확인하세요" if err > 0.03 else ""))
        for ln in lines:
            print("[ZZZ FBX]", ln)
        self.report({"INFO"}, " / ".join(lines))
        return {"FINISHED"}

    @staticmethod
    def transfer(context, c, body):
        """게임 메시 전체(rest 자세)를 잠깐 하나로 합쳐 원본으로 삼고, 가장 가까운 면의 웨이트를 옮긴다"""
        import bmesh
        context.view_layer.update()     # 사본의 새 위치(뼈대 기준)를 월드 행렬에 반영
        bm = bmesh.new()
        names = []
        for b in body:
            idx = {g.index: g.name for g in b.vertex_groups}
            me = b.data.copy()
            me.transform(b.matrix_world)
            tmp = bmesh.new()
            tmp.from_mesh(me)
            dl = tmp.verts.layers.deform.verify()
            # 그룹 번호를 이름 기준 공통 번호로 바꿔 담는다
            for v in tmp.verts:
                d = v[dl]
                items = [(idx[k], w) for k, w in d.items() if k in idx]
                d.clear()
                for n, w in items:
                    if n not in names:
                        names.append(n)
                    d[names.index(n)] = w
            tmp.to_mesh(me)
            tmp.free()
            bm.from_mesh(me)
            bpy.data.meshes.remove(me)
        src_me = bpy.data.meshes.new("_zzz_weight_src")
        bm.to_mesh(src_me)
        bm.free()
        src = bpy.data.objects.new("_zzz_weight_src", src_me)
        for n in names:
            src.vertex_groups.new(name=n)
        context.scene.collection.objects.link(src)
        try:
            c.vertex_groups.clear()
            md = c.modifiers.new("웨이트 옮기기", "DATA_TRANSFER")
            md.object = src
            md.use_object_transform = True
            md.use_vert_data = True
            md.data_types_verts = {"VGROUP_WEIGHTS"}
            # 면 없는 게임 메시(점만 있는 자료)는 가까운 점에서 옮긴다
            md.vert_mapping = "POLYINTERP_NEAREST" if len(src_me.polygons) else "NEAREST"
            with context.temp_override(object=c, active_object=c, selected_objects=[c], selected_editable_objects=[c]):
                bpy.ops.object.datalayout_transfer(modifier=md.name)
                bpy.ops.object.modifier_apply(modifier=md.name)
        finally:
            bpy.data.objects.remove(src)
            bpy.data.meshes.remove(src_me)


class ZZZFBX_PT_panel(bpy.types.Panel):
    bl_label = "ZZZ Character FBX"
    bl_idname = "ZZZFBX_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ZZZ FBX"

    def draw(self, context):
        lay = self.layout
        arm = game_armature(context)
        lay.operator(ZZZFBX_OT_load.bl_idname, icon="IMPORT")
        lay.label(text=f"게임 뼈대: {arm.name if arm else '없음'}")
        lay.operator(ZZZFBX_OT_import_mod.bl_idname, icon="MESH_DATA")
        col = lay.column()
        col.enabled = arm is not None
        col.operator(ZZZFBX_OT_bind.bl_idname, icon="ARMATURE_DATA")
        sc = context.scene
        follow = bpy.data.objects.get(FOLLOW)
        on = bool(follow and getattr(context.space_data, "lock_object", None) == follow)
        row = lay.row()
        row.enabled = arm is not None
        row.operator(ZZZFBX_OT_follow.bl_idname, icon="VIEW_CAMERA", depress=on,
                     text="화면이 캐릭터 따라가기: " + ("켜짐" if on else "꺼짐"))
        if sc.timeline_markers:
            box = lay.box()
            box.label(text="동작으로 건너뛰기")
            for m in sorted(sc.timeline_markers, key=lambda m: m.frame)[:400]:
                op = box.operator("zzz_fbx.jump", text=m.name, emboss=False)
                op.frame = m.frame


class ZZZFBX_OT_jump(bpy.types.Operator):
    """이 동작의 처음으로 가고, 이 동작 구간만 반복 재생하도록 미리보기 범위를 잡는다"""
    bl_idname = "zzz_fbx.jump"
    bl_label = "동작으로"
    frame: bpy.props.IntProperty()

    def execute(self, context):
        sc = context.scene
        fs = sorted(m.frame for m in sc.timeline_markers)
        nxt = [f for f in fs if f > self.frame]
        end = (nxt[0] - 1) if nxt else sc.frame_end
        sc.use_preview_range = True
        sc.frame_preview_start, sc.frame_preview_end = self.frame, max(self.frame, end - 10 if nxt else end)
        sc.frame_set(self.frame)
        return {"FINISHED"}


FOLLOW = "화면 따라가기"


class ZZZFBX_OT_follow(bpy.types.Operator):
    """3D 화면이 캐릭터를 따라가게 한다 (다시 누르면 끔).
    공격·회피는 캐릭터가 실제로 수 m~수십 m 이동하는데(루트 모션), 이걸 켜면 캐릭터가 화면 가운데에 머문다.
    Blender의 View Lock(Lock to Object)을 쓰되, 위아래 흔들림 없이 앞뒤·좌우로만 따라가는 빈 오브젝트에 건다.
    카메라(렌더용)도 이 빈 오브젝트의 자식으로 두면 같이 따라간다."""
    bl_idname = "zzz_fbx.follow"
    bl_label = "화면이 캐릭터 따라가기"

    def execute(self, context):
        arm = game_armature(context)
        space = context.space_data
        emp = bpy.data.objects.get(FOLLOW)
        if emp and space.lock_object == emp:
            space.lock_object = None
            return {"FINISHED"}
        if emp is None:
            emp = bpy.data.objects.new(FOLLOW, None)
            emp.empty_display_type = "PLAIN_AXES"
            emp.empty_display_size = 0.1
            emp.hide_render = True
            context.scene.collection.objects.link(emp)
        if arm is not None:
            # 뼈대의 맨 위 뼈(ZZZ는 Bip001)가 루트 모션을 싣는다
            top = next((b.name for b in arm.data.bones if b.parent is None), "")
            con = emp.constraints.get("따라가기") or emp.constraints.new("COPY_LOCATION")
            con.name = "따라가기"
            con.target, con.subtarget = arm, top
            con.use_z = False
            emp.location.z = 0.9   # 허리 높이에서 바라보기
        space.lock_object = emp
        space.lock_bone = ""
        return {"FINISHED"}


CLASSES = (ZZZFBX_OT_load, ZZZFBX_OT_import_mod, ZZZFBX_OT_bind, ZZZFBX_OT_jump, ZZZFBX_OT_follow, ZZZFBX_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
