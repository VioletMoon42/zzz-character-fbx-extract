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
    "version": (1, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > ZZZ FBX",
    "description": "zzz-character-fbx-extract 결과를 불러오고, 모드 메시를 게임 뼈대에 붙여 게임 동작으로 시험한다",
    "category": "Animation",
}

TAG = "zzz_fbx_source"          # 불러온 게임 오브젝트 표시 (값 = 원본 .blend 경로)
TEST_COLL = "게임 뼈대 시험"
SCALES = (1.0, 0.01, 100.0, 0.1, 10.0)


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
        pts += [mw @ v.co for v in vs[::step]]
    return pts


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
    """src 점들을 게임 몸에 가장 잘 겹치게 하는 축 바꿈·반전·크기 (원점 기준). (행렬, 중앙 거리 / 키)"""
    sample = src_pts[:: max(1, len(src_pts) // 1500)]
    best = None
    for M in candidate_matrices():
        d = sorted(tree.find(M @ p)[2] for p in sample)
        med = d[len(d) // 2]
        if best is None or med < best[1]:
            best = (M, med)
    return best[0], best[1] / height


def find_palette(src_blend, obj_name):
    """원본 .blend 옆 dump_map\\**\\<부위>_palette_to_bone.json 중 오브젝트 이름이 그 부위 이름으로 시작하는 것"""
    if not src_blend:
        return None
    root = Path(src_blend).parents[1] / "dump_map"
    if not root.exists():
        return None
    base = re.split(r"[-.=]", obj_name)[0].lower()
    best = None
    for f in root.rglob("*_palette_to_bone.json"):
        part = f.name[: -len("_palette_to_bone.json")].lower()
        if base.startswith(part) and (best is None or len(part) > len(best[0])):
            best = (part, f)
    return best[1] if best else None


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
        gp = rest_points(body)
        tree = KDTree(len(gp))
        for i, p in enumerate(gp):
            tree.insert(p, i)
        tree.balance()
        height = max(p.z for p in gp) - min(p.z for p in gp)

        coll = bpy.data.collections.get(TEST_COLL) or bpy.data.collections.new(TEST_COLL)
        if coll.name not in context.scene.collection.children:
            context.scene.collection.children.link(coll)
        src_blend = arm.get(TAG)
        lines = []
        for o in sel:
            c = o.copy()
            c.data = o.data.copy()
            c.name = o.name + "_게임뼈대"
            c.parent = None
            c.matrix_world = o.matrix_world.copy()
            for md in [m for m in c.modifiers if m.type == "ARMATURE"]:
                c.modifiers.remove(md)
            coll.objects.link(c)
            # 1) 위치 맞추기
            M, err = best_fit(rest_points([c]), tree, height)
            c.matrix_world = M @ c.matrix_world
            how = f"위치 오차 {err * 100:.1f}% (키 대비)"
            # 2) 웨이트
            names = [g.name for g in c.vertex_groups]
            numeric = names and all(n.isdigit() for n in names)
            bones = set(arm.data.bones.keys())
            if numeric:
                f = Path(bpy.path.abspath(self.palette)) if self.palette else find_palette(src_blend, o.name)
                if not f or not f.exists():
                    lines.append(f"{o.name}: 번호 그룹인데 palette_to_bone.json을 못 찾음 → 게임 몸에서 웨이트를 옮김")
                    self.transfer(context, c, body)
                    how += ", 웨이트 옮김"
                else:
                    table = json.loads(f.read_text(encoding="utf-8"))
                    miss = 0
                    for g in c.vertex_groups:
                        b = table.get(g.name)
                        if b in bones:
                            g.name = b
                        else:
                            miss += 1
                    how += f", 표 {f.name}" + (f" (표에 없는 그룹 {miss}개)" if miss else "")
            elif not (set(names) & bones):
                self.transfer(context, c, body)
                how += ", 웨이트 옮김"
            # 3) 뼈대에 붙이기
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
            md.vert_mapping = "POLYINTERP_NEAREST"
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
        col = lay.column()
        col.enabled = arm is not None
        col.operator(ZZZFBX_OT_bind.bl_idname, icon="ARMATURE_DATA")
        sc = context.scene
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


CLASSES = (ZZZFBX_OT_load, ZZZFBX_OT_bind, ZZZFBX_OT_jump, ZZZFBX_PT_panel)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
