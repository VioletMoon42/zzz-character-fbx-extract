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

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(fbx), global_scale=100.0)
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
    bpy.ops.import_scene.fbx(filepath=str(path), global_scale=100.0)
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
    + "공격·회피는 앞으로 나가는 동작이라 캐릭터가 제자리를 벗어납니다.\n")

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
