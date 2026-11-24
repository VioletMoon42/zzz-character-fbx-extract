# 동작 FBX가 실제로 움직이는지 확인한다: 동작(Action)마다 길이와, 몇 프레임에서 뼈가 rest 대비 얼마나 움직이는지 (FBX는 읽기만)
# blender -b --factory-startup --python zx_check_anim_blender.py -- <fbx> <출력 json>
import bpy, sys, json
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
fbx, out = argv[0], argv[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=fbx, automatic_bone_orientation=False, ignore_leaf_bones=False)
arm = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
if arm is None:
    print("ERROR: FBX에 뼈대(Armature)가 없습니다:", fbx)
    sys.exit(1)
sc = bpy.context.scene
rest = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
key = [n for n in ("Bip001 Pelvis", "Bip001 L Hand", "Bip001 R Hand", "Bip001 L Foot", "Bip001 Head") if n in rest]
h = max(v[2] for v in rest.values()) - min(v[2] for v in rest.values())
rep = {"armature": arm.name, "bones": len(rest), "rest_height_world": float(h), "note": "max_move_rel = 이동 거리 / rest 키(머리 본 높이 차)", "actions": []}
if arm.animation_data is None:
    arm.animation_data_create()
for act in [a for a in bpy.data.actions if a.name.startswith(arm.name + "|")]:   # 뼈대 자신의 동작만 (Root|, Key|, FX_Root|는 다른 오브젝트 몫)
    arm.animation_data.action = act
    # Blender 4.4+ 슬롯 액션
    if hasattr(arm.animation_data, "action_slot") and getattr(act, "slots", None):
        try:
            arm.animation_data.action_slot = act.slots[0]
        except Exception:
            pass
    f0, f1 = act.frame_range
    moves = {}
    for f in np.linspace(f0, f1, 5):
        sc.frame_set(int(round(f)))
        for n in key:
            pb = arm.pose.bones[n]
            p = np.array(arm.matrix_world @ pb.head)
            moves.setdefault(n, []).append(float(np.linalg.norm(p - rest[n])))
    rep["actions"].append({"name": act.name, "frames": [float(f0), float(f1)], "fcurves": len(act.fcurves) if hasattr(act, "fcurves") else None,
                           "max_move_rel": {n: round(float(max(v) / h), 3) for n, v in moves.items()}})
json.dump(rep, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ACTIONS", len(rep["actions"]))
for a in rep["actions"]:
    print(a["name"].split("|")[1], a["frames"], a["max_move_rel"])
