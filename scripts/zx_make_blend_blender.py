# 뽑은 FBX를 바로 쓸 수 있는 .blend로 만든다 (FBX는 읽기만, 같은 폴더에 <이름>.blend)
#   blender -b --factory-startup --python zx_make_blend_blender.py -- <fbx> <출력 .blend>
# - 실제 크기(가져오기 Scale 100: 키 약 1.5 m), 60 fps, 텍스처가 보이는 머티리얼 미리보기
# - 동작이 여러 개면 NLA로 타임라인 하나에 이어 붙이고, 동작마다 이름표(마커)를 단다.
#   뼈대(Bone_Root|), 셰이프 키(Key|), 다른 오브젝트(Root|, FX_Root|)의 같은 동작도 같은 자리에 놓아 함께 움직인다.
# 스크립트 자동 실행이 필요 없는 평범한 .blend다.
import sys
from pathlib import Path

import bpy

GAP = 10   # 동작 사이 빈 프레임

argv = sys.argv[sys.argv.index("--") + 1:]
fbx, out = Path(argv[0]), Path(argv[1])
extras = [Path(p) for p in argv[2:]]      # 같은 동작으로 뽑은 무기 FBX (선택)
if out.exists():
    print(f"ERROR: 이미 있어서 덮어쓰지 않음: {out}")
    sys.exit(1)

def mixed_bind_poses(path):
    """같은 뼈를 메시마다 다른 기준 자세(바인드 포즈)로 묶은 FBX를 찾는다.
    예: Severian은 얼굴·눈썹·앞머리 그림자만 등뼈·목·머리를 21 m 옮긴 자리 기준으로 묶여 있다.
    게임은 메시마다 자기 기준 자세를 쓰지만 Blender 뼈는 하나만 가질 수 있어서, 그대로 가져오면 마지막 값을 쓰고
    같은 뼈를 쓰는 몸이 늘어나 흩어진다.
    돌려주는 값: replace {클러스터 uid: {b'TransformLink': 원소, b'Transform': 원소}} 다수 메시 값으로 바꿀 것,
                 fix {메시 이름: G} 그 메시 정점을 G⁻¹만큼 옮기면 맞는 것(G는 FBX 공간의 고정 변환),
                 canon {뼈 이름: 다수 메시의 기준 자세 위치(FBX 공간)}"""
    import collections
    from io_scene_fbx import parse_fbx
    from io_scene_fbx.fbx_utils import array_to_matrix4
    root, _ = parse_fbx.parse(str(path))
    objs = next(e for e in root.elems if e.id == b"Objects")
    conns = next(e for e in root.elems if e.id == b"Connections")
    nodes = {e.props[0]: e for e in objs.elems}
    up, down = collections.defaultdict(list), collections.defaultdict(list)
    for c in conns.elems:
        if c.props[0] == b"OO":
            up[c.props[1]].append(c.props[2])
            down[c.props[2]].append(c.props[1])

    def name(e):
        return e.props[1].split(b"\x00")[0].decode("utf-8", "replace")

    def child(e, i):
        return next((x for x in e.elems if x.id == i), None)

    def is_(uid, kind):
        return uid in nodes and nodes[uid].id == kind

    size = {}   # 메시 이름 -> 정점 수
    for uid, e in nodes.items():
        if e.id == b"Geometry" and e.props[2] == b"Mesh":
            v = child(e, b"Vertices")
            for m in up[uid]:
                if is_(m, b"Model"):
                    size[name(nodes[m])] = len(v.props[0]) // 3 if v is not None else 0
    by_bone = collections.defaultdict(list)   # 뼈 이름 -> [(클러스터 uid, 메시 이름, L, 원소들, 가중치 합)]
    skin = {}   # 클러스터 uid -> (정점 번호들, 가중치들)
    for uid, e in nodes.items():
        if e.id != b"Deformer" or e.props[2] != b"Cluster":
            continue
        link, tx = child(e, b"TransformLink"), child(e, b"Transform")
        bones = [name(nodes[b]) for b in down[uid] if is_(b, b"Model")]
        meshes = [name(nodes[m]) for s in up[uid] for g in up[s] if is_(g, b"Geometry") for m in up[g] if is_(m, b"Model")]
        if link is None or tx is None or not bones or not meshes:
            continue
        w, ix = child(e, b"Weights"), child(e, b"Indexes")
        weight = float(sum(w.props[0])) if w is not None else 0.0   # 0이면 정점이 하나도 안 묶인 빈 클러스터
        by_bone[bones[0]].append((uid, meshes[0], array_to_matrix4(link.props[0]), {b"TransformLink": link, b"Transform": tx}, weight))
        skin[uid] = (list(ix.props[0]) if ix is not None else [], list(w.props[0]) if w is not None else [])

    def key(m):
        return tuple(round(x, 3) for row in m for x in row)

    def elem(src, m):
        """원소 src의 행렬 값을 m으로 바꾼 새 원소 (FBX 행렬은 열 우선 16개)"""
        return src._replace(props=[[m[r][c] for c in range(4) for r in range(4)]])

    def retarget(el, L, Lc):
        """클러스터의 뼈 기준 자세를 Lc로 바꾸되 메시 자리(TransformLink @ Transform)는 그대로 둔다"""
        T = array_to_matrix4(el[b"Transform"].props[0])
        return {b"TransformLink": elem(el[b"TransformLink"], Lc), b"Transform": elem(el[b"Transform"], Lc.inverted() @ L @ T)}

    def solve(pick):
        """pick {뼈: 기준으로 삼을 L}로 바꿀 클러스터·옮길 메시를 정한다"""
        replace, shifts, canon, minority = {}, collections.defaultdict(list), {}, {}
        corr = collections.defaultdict(list)   # 메시 -> [(클러스터 uid, Lc L⁻¹)] 그 메시가 쓰는 모든 뼈의 보정
        for bone, lst in by_bone.items():
            Lc = pick[bone]
            common = key(Lc)
            canon[bone] = Lc.translation
            for uid, mesh, L, el, wt in lst:
                if wt > 0:
                    corr[mesh].append((uid, Lc @ L.inverted()))
                if key(L) == common:
                    continue
                replace[uid] = retarget(el, L, Lc)   # 뼈 휴지 자세는 기준 값으로
                if wt > 0:
                    shifts[mesh].append(L @ Lc.inverted())
                    minority[uid] = mesh
        # 소수 메시: 한 메시 안에서 차이가 하나의 고정 변환이면 정점을 그만큼 옮겨 정확히 맞춘다(fix).
        # 아니면(뼈마다 조금씩 다른 자세로 묶인 경우) 정점마다 묶인 뼈들의 보정을 가중치대로 섞어 옮긴다(blend):
        # 기준 자세에서는 정확히 맞고, 동작 중에는 섞인 정점에만 차이가 남는다.
        fix = {m: gs[0] for m, gs in shifts.items() if len({key(g) for g in gs}) == 1}
        # 옮길 메시가 다른 메시와 같은 기준 자세로 묶인 뼈도 쓰면, 옮기는 순간 그 부분이 어긋난다 → 그런 메시는 옮기지 않는다
        changed = True
        while changed:
            changed = False
            for bone, lst in by_bone.items():
                used = [t for t in lst if t[4] > 0]
                only_fixed = all(m in fix for _, m, _, _, _ in used) and len({key(fix[m]) for _, m, _, _, _ in used}) == 1
                for uid, m, L, _, _ in used:
                    if m in fix and not only_fixed and uid not in minority:
                        del fix[m]
                        changed = True
                        break
        # 옮길 메시만 쓰는 뼈(얼굴 표정 뼈 등)는 그 메시의 기준 자세만 갖고 있다 → 메시를 옮기는 만큼 뼈 기준 자세도 옮긴다
        for bone, lst in by_bone.items():
            used = [t for t in lst if t[4] > 0]
            if not used or any(m not in fix for _, m, _, _, _ in used) or len({key(fix[m]) for _, m, _, _, _ in used}) != 1:
                continue
            G = fix[used[0][1]]
            L2 = G.inverted() @ used[0][2]
            for uid, _, L, el, _ in lst:
                replace[uid] = retarget(el, L, L2)
            canon[bone] = L2.translation
        blend = {}
        for m in shifts:
            if m in fix:
                continue
            idx, wts, mats = [], [], []
            for uid, C in corr[m]:
                ix, ws = skin[uid]
                idx += ix
                wts += ws
                mats += [C] * len(ix)
            blend[m] = (idx, wts, mats)
        return replace, fix, canon, blend, minority

    # 1차 기준: 그 뼈를 실제로 쓰는(빈 클러스터가 아닌) 메시 중 정점이 가장 많은 메시(보통 몸)의 값
    pick = {}
    for bone, lst in by_bone.items():
        used = [t for t in lst if t[4] > 0] or lst
        pick[bone] = max(used, key=lambda t: size.get(t[1], 0))[2]
    replace, fix, canon, blend, minority = solve(pick)
    # 2차: 통째로 옮겨 맞출 메시가 소수로 끼지 않은 엇갈린 뼈는, 후보 값마다 "그 뼈에 묶인 정점들의 보정이 얼마나 흩어지는지"를 재서
    #      가장 덜 흩어지는 값을 고른다. 한 정점에 묶인 뼈들의 보정이 같으면 동작 중에도 정확하고, 다를수록 어긋난다.
    import numpy as np
    fixed_bones = {b for b, lst in by_bone.items() for uid, m, _, _, _ in lst if uid in minority and m in fix}
    conflict = [b for b, lst in by_bone.items() if b not in fixed_bones and len({key(t[2]) for t in lst if t[4] > 0}) > 1]
    again = False
    if conflict:
        geo_of = {}
        for uid, e in nodes.items():
            if e.id == b"Geometry" and e.props[2] == b"Mesh":
                for m in up[uid]:
                    if is_(m, b"Model"):
                        geo_of[name(nodes[m])] = e
        vmesh = {}   # 메시 -> 바인드 월드 정점 (n,4)
        infl = collections.defaultdict(list)   # 메시 -> [(뼈, 정점 번호들, 가중치들, L)]
        for bone, lst in by_bone.items():
            for uid, m, L, el, wt in lst:
                if wt > 0 and m not in fix:
                    ix, ws = skin[uid]
                    infl[m].append((bone, np.array(ix, int), np.array(ws), L))
        for m in infl:
            v = child(geo_of[m], b"Vertices") if m in geo_of else None
            if v is None:
                continue
            uidT = next(uid for uid, mm in ((u, t[1]) for b in by_bone for t in by_bone[b] for u in [t[0]]) if mm == m)
            el = next(t[3] for b in by_bone for t in by_bone[b] if t[0] == uidT)
            MT = np.array(array_to_matrix4(el[b"TransformLink"].props[0]) @ array_to_matrix4(el[b"Transform"].props[0]))
            vl = np.array(v.props[0]).reshape(-1, 3)
            vmesh[m] = (MT @ np.c_[vl, np.ones(len(vl))].T).T

        def spread(bone_set):
            total = 0.0
            for m, lst in infl.items():
                if m not in vmesh or not any(b in bone_set for b, _, _, _ in lst):
                    continue
                V = vmesh[m]
                n = len(V)
                touch = np.zeros(n, bool)
                for b, ix, ws, L in lst:
                    if b in bone_set:
                        touch[ix[ix < n]] = True
                acc = np.zeros((n, 3)); acc2 = np.zeros(n); wsum = np.zeros(n); pts = []
                for b, ix, ws, L in lst:
                    ok = (ix < n) & touch[np.minimum(ix, n - 1)]
                    ix, ws = ix[ok], ws[ok]
                    if not len(ix):
                        continue
                    C = np.array(pick[b] @ L.inverted())
                    P = (C @ V[ix].T).T[:, :3]
                    pts.append((ix, ws, P))
                    np.add.at(acc, ix, P * ws[:, None]); np.add.at(wsum, ix, ws)
                mean = acc / np.maximum(wsum, 1e-9)[:, None]
                for ix, ws, P in pts:
                    np.add.at(acc2, ix, ws * np.linalg.norm(P - mean[ix], axis=1))
                total += float(acc2.sum())
            return total

        for _ in range(2):
            for bone in conflict:
                cands = {key(t[2]): t[2] for t in by_bone[bone] if t[4] > 0}
                best, best_s = pick[bone], None
                for L in cands.values():
                    old = pick[bone]
                    pick[bone] = L
                    sp = spread({bone})
                    pick[bone] = old
                    if best_s is None or sp < best_s - 1e-9:
                        best, best_s = L, sp
                if key(best) != key(pick[bone]):
                    pick[bone] = best
                    again = True
    if again:
        replace, fix, canon, blend, minority = solve(pick)
    return replace, fix, canon, blend


def import_fbx(path):
    """FBX를 가져온다. 메시마다 기준 자세가 엇갈리면 다수 메시 값으로 통일해 가져오고, 소수 메시는 정점을 옮겨 맞춘다."""
    try:
        replace, fix, canon, blend = mixed_bind_poses(path)
    except Exception as ex:   # 검사에 실패해도 가져오기는 평소대로
        print("WARN 바인드 포즈 검사 실패:", repr(ex))
        replace = {}
    if not replace:
        bpy.ops.import_scene.fbx(filepath=str(path), global_scale=100.0)
        return
    import numpy as np
    from io_scene_fbx import import_fbx as imp
    from mathutils import Matrix
    objs0 = set(bpy.data.objects)
    orig = imp.elem_find_first

    def patched(elem, id_search, default=None):
        if id_search in (b"TransformLink", b"Transform") and getattr(elem, "id", None) == b"Deformer" \
                and elem.props and elem.props[0] in replace:
            return replace[elem.props[0]][id_search]
        return orig(elem, id_search, default)

    imp.elem_find_first = patched
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), global_scale=100.0)
    finally:
        imp.elem_find_first = orig
    new = [o for o in bpy.data.objects if o not in objs0]
    arm_ = next(o for o in new if o.type == "ARMATURE")
    # FBX 공간 → Blender 월드 변환: 뼈 휴지 위치(이제 다수 메시 기준)와 FBX 값을 맞대어 구한다(축 변환·배율이 버전마다 달라도 맞게)
    # 크기 변환이 섞인 뼈는 Blender 뼈 위치가 FBX 값과 달라질 수 있어, 안 맞는 뼈는 빼 가며 다시 맞춘다
    pairs = [(canon[b.name], arm_.matrix_world @ b.head_local) for b in arm_.data.bones if b.name in canon]
    src = np.array([[*p, 1.0] for p, _ in pairs])
    dst = np.array([list(q) for _, q in pairs])
    keep = np.ones(len(src), bool)
    for _ in range(5):
        sol = np.linalg.lstsq(src[keep], dst[keep], rcond=None)[0]
        res = np.linalg.norm(src @ sol - dst, axis=1)
        keep = res < max(0.002, 3 * float(np.median(res)))
    err = float(res[keep].max()) if keep.any() else 1e9
    if err > 0.01 or keep.sum() < 0.5 * len(src):
        print(f"WARN 축 변환을 못 맞춤(오차 {err:.3f} m, 맞은 뼈 {int(keep.sum())}/{len(src)}): 엇갈린 메시는 옮기지 않음")
        return
    conv = Matrix([[*sol[:3, i], sol[3, i]] for i in range(3)] + [[0, 0, 0, 1]])
    for mesh, G in fix.items():
        ob = next((o for o in new if o.type == "MESH" and o.name == mesh), None)
        if ob is None:
            continue
        w = ob.matrix_world.copy()
        ob.data.transform(w.inverted() @ conv @ G.inverted() @ conv.inverted() @ w, shape_keys=True)
    cn = np.array(conv)
    cni = np.linalg.inv(cn)
    for mesh, (idx, wts, mats) in blend.items():
        ob = next((o for o in new if o.type == "MESH" and o.name == mesh), None)
        if ob is None or not idx:
            continue
        me = ob.data
        n = len(me.vertices)
        W = np.array(ob.matrix_world)
        A = cni @ W   # 로컬 → FBX 월드
        B = np.linalg.inv(W) @ cn   # FBX 월드 → 로컬
        acc = np.zeros((n, 4, 4))
        ws = np.zeros(n)
        for i, wv, C in zip(idx, wts, mats):
            if i < n:
                acc[i] += wv * np.array(C)
                ws[i] += wv
        ok = ws > 0
        acc[ok] /= ws[ok][:, None, None]
        acc[~ok] = np.eye(4)
        X = B @ acc @ A   # 정점마다 로컬 공간 보정 행렬
        sets = [me.vertices] + ([k.data for k in me.shape_keys.key_blocks] if me.shape_keys else [])
        for coll in sets:
            co = np.zeros(n * 3)
            coll.foreach_get("co", co)
            co = np.c_[co.reshape(-1, 3), np.ones(n)]
            co = np.einsum("nij,nj->ni", X, co)[:, :3]
            coll.foreach_set("co", co.ravel())
        me.update()
    print(f"BIND {Path(path).name}: 기준 자세 통일, 통째로 옮긴 메시 {', '.join(fix) or '-'}, 정점별로 맞춘 메시 {', '.join(blend) or '-'}")


bpy.ops.wm.read_factory_settings(use_empty=True)
import_fbx(fbx)
sc = bpy.context.scene
sc.render.fps, sc.render.fps_base = 60, 1.0

arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if arm is None:
    print("ERROR: FBX에 뼈대(Armature)가 없습니다:", fbx)
    sys.exit(1)


def split(act):
    """'Bone_Root|Avatar_..._Ani_Idle_Loop|Base Layer' -> ('Bone_Root', 'Avatar_..._Ani_Idle_Loop')"""
    p = act.name.split("|")
    return (p[0], p[1]) if len(p) >= 2 else (None, None)


# 동작을 가진 데이터(오브젝트, 셰이프 키)와 그 앞부분 이름
owners = {}
for idb in list(bpy.data.objects) + list(bpy.data.shape_keys):
    ad = idb.animation_data
    if ad and ad.action:
        pre, _ = split(ad.action)
        if pre:
            owners[pre] = idb
clips = sorted({split(a)[1] for a in bpy.data.actions if split(a)[0] == arm.name})
by_key = {split(a): a for a in bpy.data.actions}


def short(clip):
    return clip.split("_Ani_", 1)[1] if "_Ani_" in clip else clip


# 대기 동작을 맨 앞에
clips.sort(key=lambda c: (not short(c).startswith("Idle"), short(c)))
frame = 1
if len(clips) > 1:
    tracks = {}
    for pre, idb in owners.items():
        idb.animation_data.action = None
        tracks[pre] = idb.animation_data.nla_tracks.new()
        tracks[pre].name = "동작"
    for clip in clips:
        length = 1
        for pre, idb in owners.items():
            act = by_key.get((pre, clip))
            if act is None:
                continue
            s = tracks[pre].strips.new(short(clip), frame, act)
            if hasattr(s, "action_slot") and getattr(act, "slots", None):
                try:
                    s.action_slot = act.slots[0]
                except Exception:
                    pass
            length = max(length, int(round(act.frame_range[1] - act.frame_range[0])) + 1)
        sc.timeline_markers.new(short(clip), frame=frame)
        frame += length + GAP
    sc.frame_start, sc.frame_end = 1, frame - GAP - 1
elif clips:
    act = by_key[(arm.name, clips[0])]
    sc.frame_start, sc.frame_end = int(act.frame_range[0]), int(act.frame_range[1])
    sc.timeline_markers.new(short(clips[0]), frame=sc.frame_start)


def add_extra(path):
    """무기 FBX를 가져와 '무기' 컬렉션에 두고, 동작마다 캐릭터 이름표와 같은 프레임에 놓는다.
    무기 FBX에는 캐릭터와 같은 이름의 팔 뼈 사슬이 같은 동작으로 들어 있어서, 자리만 맞추면 손에 쥔 채로 움직인다."""
    marks = {m.name: m.frame for m in sc.timeline_markers}
    fps, fs, fe = sc.render.fps, sc.frame_start, sc.frame_end
    objs0, acts0 = set(bpy.data.objects), set(bpy.data.actions)
    import_fbx(path)
    sc.render.fps, sc.frame_start, sc.frame_end = fps, fs, fe
    new = [o for o in bpy.data.objects if o not in objs0]
    acts = [x for x in bpy.data.actions if x not in acts0]
    coll = bpy.data.collections.new("무기")
    sc.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
        if o.type == "EMPTY":
            o.empty_display_size = 0.03
    # 가져오기가 붙여 둔 액션 앞부분으로 주인을 찾는다(이름이 겹쳐 .001이 붙은 오브젝트도)
    own = {}
    for o in new:
        ad = o.animation_data
        if ad and ad.action and split(ad.action)[0]:
            own[split(ad.action)[0]] = o
    placed = 0
    for pre, o in own.items():
        ad = o.animation_data
        ad.action = None
        tr = ad.nla_tracks.new()
        tr.name = "동작"
        for act in acts:
            p, clip = split(act)
            if p != pre or short(clip) not in marks:
                continue
            s = tr.strips.new(short(clip), int(marks[short(clip)]), act)
            if hasattr(s, "action_slot") and getattr(act, "slots", None):
                try:
                    s.action_slot = act.slots[0]
                except Exception:
                    pass
            placed += 1
    print(f"EXTRA {path.name}: objects={len(new)} strips={placed}")


if len(clips) > 1:
    for p in extras:
        add_extra(p)
sc.frame_set(sc.frame_start)

# 앞머리 그림자용 보조 메시(<코드>_HairShadow)는 게임에서 얼굴에 그림자를 찍는 데만 쓰고 화면에 보이지 않는다.
# 앞머리와 같은 자리에 겹쳐 있어 그대로 두면 앞머리가 얼룩지거나 구멍 난 것처럼 보이므로, 따로 모아 꺼 둔다.
shadow = [o for o in bpy.data.objects if o.type == "MESH" and o.name.split(".")[0].endswith("_HairShadow")]
if shadow:
    sc_coll = bpy.data.collections.new("보조 메시 (앞머리 그림자)")
    sc.collection.children.link(sc_coll)
    for o in shadow:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        sc_coll.objects.link(o)
    sc_coll.hide_viewport = True
    sc_coll.hide_render = True

# 보기 좋게: 머티리얼 미리보기(텍스처 보임), 뼈대 선택
for scr in bpy.data.screens:
    for area in scr.areas:
        for sp in area.spaces:
            if sp.type == "VIEW_3D":
                sp.shading.type = "MATERIAL"
for o in bpy.data.objects:
    o.select_set(False)
arm.select_set(True)
bpy.context.view_layer.objects.active = arm

note = bpy.data.texts.new("읽어보기")
note.write(
    f"원본: {fbx.name}\n"
    "실제 크기(가져오기 Scale 100), 60 fps로 맞춰 두었습니다.\n"
    + (f"동작 {len(clips)}개를 타임라인에 이어 붙였습니다. 마커 이름이 동작 이름입니다.\n"
       "- 재생: Space / 처음으로: Shift+Left\n"
       "- 동작 하나만 반복해 보려면 타임라인에서 P를 누르고 그 구간을 드래그합니다(미리보기 범위, 풀기는 Alt+P).\n"
       "- 동작 하나를 따로 꺼내려면 Nonlinear Animation 창에서 그 줄을 고르고 Tab으로 편집합니다.\n"
       if clips else "동작이 없는 모델 파일입니다.\n")
    + "공격·회피는 앞으로 나가는 동작이라 캐릭터가 제자리를 벗어납니다.\n"
    + ("앞머리 그림자용 보조 메시(*_HairShadow)는 '보조 메시' 컬렉션에 모아 꺼 두었습니다. FBX에는 그대로 들어 있습니다.\n"
       if shadow else ""))

# 텍스처: 같은 파일을 가리키는 중복 이미지를 하나로 합치고, .blend 옆 파일을 이름으로 가리킨다(폴더째 옮겨도 열림)
first = {}
for img in list(bpy.data.images):
    if img.source != "FILE" or not img.filepath:
        continue
    name = Path(bpy.path.abspath(img.filepath)).name
    if name in first:
        img.user_remap(first[name])
        bpy.data.images.remove(img)
        continue
    first[name] = img
    if (out.parent / name).exists():
        img.filepath = "//" + name
    img.name = name
bpy.ops.wm.save_as_mainfile(filepath=str(out), relative_remap=False)
print(f"BLEND {out} clips={len(clips)} frames={sc.frame_end}")
