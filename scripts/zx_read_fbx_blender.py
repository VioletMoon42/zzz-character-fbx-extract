# 게임에서 뽑은 캐릭터 모델 FBX를 읽어 메시(정점·UV·웨이트)·뼈대 정보를 npz/json으로 저장한다 (zzz-game-extract, FBX는 읽기만)
# blender -b --factory-startup --python zx_read_fbx_blender.py -- <fbx> <출력 폴더>
import bpy, sys, json
import numpy as np
from pathlib import Path

argv = sys.argv[sys.argv.index("--") + 1:]
fbx, out = Path(argv[0]), Path(argv[1])
out.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=str(fbx), automatic_bone_orientation=False, ignore_leaf_bones=False)

rep = {"objects": []}
arm = None
for ob in bpy.data.objects:
    rep["objects"].append({"name": ob.name, "type": ob.type, "parent": ob.parent.name if ob.parent else None,
                           "verts": len(ob.data.vertices) if ob.type == "MESH" else None})
    if ob.type == "ARMATURE":
        arm = ob

bpy.context.view_layer.update()
for ob in bpy.data.objects:
    if ob.type != "MESH":
        continue
    me = ob.data
    mw = np.array(ob.matrix_world)
    co = np.array([v.co for v in me.vertices])
    co = co @ mw[:3, :3].T + mw[:3, 3]
    uv = np.zeros((len(me.vertices), 2))
    if me.uv_layers:
        lu = me.uv_layers[0].data
        for lp in me.loops:
            uv[lp.vertex_index] = lu[lp.index].uv
    gnames = [g.name for g in ob.vertex_groups]
    wi = np.full((len(me.vertices), 8), -1, np.int32); ww = np.zeros((len(me.vertices), 8))
    for v in me.vertices:
        gs = sorted(((g.weight, g.group) for g in v.groups), reverse=True)[:8]
        for k, (w, g) in enumerate(gs):
            wi[v.index, k] = g; ww[v.index, k] = w
    tri = np.array([p.vertices[:] for p in me.polygons if len(p.vertices) == 3], np.int32)
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in ob.name)
    np.savez_compressed(out / f"mesh_{safe}.npz", co=co, uv=uv, wi=wi, ww=ww, tri=tri,
                        gnames=np.array(gnames), mw=mw)

if arm:
    bones = []
    for b in arm.data.bones:
        bones.append({"name": b.name, "parent": b.parent.name if b.parent else None,
                      "head": list(arm.matrix_world @ b.head_local), "tail": list(arm.matrix_world @ b.tail_local),
                      "matrix_local": [list(r) for r in (arm.matrix_world @ b.matrix_local)]})
    rep["armature"] = arm.name
    rep["bones"] = bones
    rep["actions"] = [a.name for a in bpy.data.actions]
(out / "game_fbx_info.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
print("OBJ", [(o["name"], o["type"], o["verts"]) for o in rep["objects"] if o["type"] != "EMPTY"][:40])
print("BONES", len(rep.get("bones", [])), "ACTIONS", len(rep.get("actions", [])))
