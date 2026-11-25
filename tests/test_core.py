# 게임 파일 없이 돌아가는 단위 테스트:  python -m unittest discover -s tests
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="zx_test_")
os.environ["ZX_ROOT"] = TMP   # 테스트는 임시 작업 폴더만 쓴다
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import numpy as np  # noqa: E402

import zx_build_map  # noqa: E402
import zx_common  # noqa: E402
import zx_extract  # noqa: E402
import zx_find  # noqa: E402

zx_find.game_version = lambda: "9.9.9"   # 설정 파일 없이 plan을 만들 수 있게

ROWS = [
    ("Avatar_Female_Size02_Pheony_Model", "Animator", "a.blk"),
    ("Avatar_Female_Size02_Pheony_ModelAvatar", "Avatar", "a.blk"),
    ("Avatar_Female_Size02_Pheony_Model", "Animator", "old.blk"),
    ("Avatar_Female_Size02_Pheony_Youth_Model", "Animator", "y.blk"),
    ("Avatar_Female_Size02_Pheony_Weapon_Model", "Animator", "w.blk"),
    ("Pheony_Body", "Mesh", "m1.blk"),
    ("Pheony_Hair_1", "Mesh", "m1.blk"),
    ("Pheony_Body_LOD1", "Mesh", "lod.blk"),
    ("Pheony_Youth_Body", "Mesh", "y.blk"),
    ("Pheony_Weapon_Sword", "Mesh", "w.blk"),
    ("Avatar_Female_Size02_Pheony_Ani_Idle_Loop", "AnimationClip", "c1.blk"),
    ("Avatar_Female_Size02_Pheony_Ani_Attack_Normal_01", "AnimationClip", "c1.blk"),
    ("Avatar_Female_Size02_Pheony_Ani_Facial_Smile", "AnimationClip", "c2.blk"),
    ("Avatar_Female_Size02_Pheony_Youth_Ani_Idle_Loop", "AnimationClip", "y.blk"),
    ("Avatar_Female_Size01_Astra_Chandelier_Model", "Animator", "s.blk"),
]


class FindTest(unittest.TestCase):
    def setUp(self):
        self.codes = zx_find.model_codes(ROWS)

    def test_model_codes_include_skins(self):
        self.assertEqual(set(self.codes), {"Pheony", "Pheony_Youth", "Pheony_Weapon", "Astra_Chandelier"})

    def test_own_mesh_excludes_other_models_and_lod(self):
        others = ["Pheony_Youth", "Pheony_Weapon"]
        self.assertTrue(zx_find.is_own_mesh("Pheony_Body", "Pheony", others))
        self.assertFalse(zx_find.is_own_mesh("Pheony_Youth_Body", "Pheony", others))
        self.assertFalse(zx_find.is_own_mesh("Pheony_Weapon_Sword", "Pheony", others))
        self.assertFalse(zx_find.is_own_mesh("Pheony_Body_LOD1", "Pheony", others))
        self.assertFalse(zx_find.is_own_mesh("PheonyX_Body", "Pheony", others))
        # 초기 캐릭터: 몸 메시가 모델 이름으로 시작 (다른 모습 EllenOnCampus는 빼고)
        m = "Avatar_Female_Size02_Ellen_Model"
        self.assertTrue(zx_find.is_own_mesh(f"SeparateMesh_{m}_Ellen_Body_1", "Ellen", [], m))
        self.assertFalse(zx_find.is_own_mesh(f"SeparateMesh_{m}_Ellen_Body_1_LOD1", "Ellen", [], m))
        self.assertFalse(zx_find.is_own_mesh("SeparateMesh_Avatar_Female_Size02_EllenOnCampus_Model_Ellen_Face", "Ellen", [], m))

    def test_meshes_named_from_hierarchy(self):
        # 니콜: 코드명 Nostradamus, 메시는 NuoCha_*. 계층의 뼈 이름(Head, Weapon_01)과 같은 이름의 남의 메시는 빼야 한다
        rows = [("NuoCha_Body_1", "Mesh", "a.blk"), ("NuoCha_Face", "Mesh", "b.blk"), ("NuoCha_Face_LOD1", "Mesh", "c.blk"),
                ("NuoCha_CunningCutie_Body_1", "Mesh", "d.blk"), ("Head", "Mesh", "x.blk"), ("Weapon_01", "Mesh", "y.blk")]
        names = {"NuoCha_Body_1", "NuoCha_Face", "Head", "Weapon_01", "Spine"}
        plan = zx_find.set_meshes({}, zx_find.meshes_named(rows, names))
        self.assertEqual(plan["meshes"], ["NuoCha_Body_1", "NuoCha_Face"])
        self.assertEqual(plan["mesh_blks"], ["a.blk", "b.blk"])

    def test_plan(self):
        plan = zx_find.make_plan(ROWS, self.codes, "Pheony", "Phoenix")
        self.assertEqual(plan["model_blks"], ["a.blk"])           # Avatar가 같이 든 파일만
        self.assertEqual(plan["mesh_blks"], ["m1.blk"])           # 다른 모습·무기·LOD 메시 파일은 빠진다
        self.assertEqual(plan["clip_blks"], ["c1.blk", "c2.blk"])  # Pheony_Youth 동작은 빠진다
        self.assertEqual(plan["body_clip_count"], 2)
        self.assertEqual(plan["facial_clip_count"], 1)
        self.assertEqual(plan["other_models_same_code_prefix"], ["Pheony_Weapon", "Pheony_Youth"])

    def test_resolve(self):
        self.assertEqual(zx_find.resolve("pheony", self.codes), "Pheony")
        self.assertIsNone(zx_find.resolve("Phoenix", self.codes))
        self.assertIn("Pheony", zx_find.candidates("Pheon", self.codes))
        zx_find.ALIASES_FILE.write_text(json.dumps({"Phoenix": "Pheony"}), encoding="utf-8")
        try:
            self.assertEqual(zx_find.resolve("phoenix", self.codes), "Pheony")
        finally:
            zx_find.ALIASES_FILE.unlink()

    def test_clip_regex(self):
        import re
        plan = {"model_animator": "Avatar_Female_Size02_Pheony_Model"}
        rx = re.compile(zx_extract.clip_regex(plan))
        self.assertTrue(rx.search("Avatar_Female_Size02_Pheony_Ani_Idle_Loop"))
        self.assertFalse(rx.search("Avatar_Female_Size02_Pheony_Ani_Facial_Smile"))
        self.assertFalse(rx.search("Avatar_Female_Size02_Pheony_Youth_Ani_Idle_Loop"))
        self.assertTrue(re.search(zx_extract.clip_regex(plan, facial=True), "Avatar_Female_Size02_Pheony_Ani_Facial_Smile"))
        # --clips: 같은 파일에 섞인 다른 모습(Pheony_Illness)의 같은 이름 동작은 잡지 않는다 (훅은 Regex.IsMatch = search)
        some = re.compile(zx_extract.clip_regex(plan, "Idle_Loop|Attack_Normal_01"))
        self.assertTrue(some.search("Avatar_Female_Size02_Pheony_Ani_Attack_Normal_01"))
        self.assertFalse(some.search("Avatar_Female_Size02_Pheony_Illness_Ani_Idle_Loop"))
        self.assertFalse(some.search("Avatar_Female_Size02_Pheony_Ani_Battle_Idle_Loop"))


class MapTest(unittest.TestCase):
    def test_compact(self):
        src = Path(TMP) / "full.json"
        src.write_text('''[
  {
    "Name": "Avatar_Female_Size02_Pheony_Model",
    "Container": "",
    "Source": "C:\\\\Game\\\\Blocks\\\\a.blk",
    "PathID": 1,
    "Type": "Animator"
  },
  {
    "Name": "Some\\ttexture",
    "Source": "C:\\\\Game\\\\Blocks\\\\t.blk",
    "Type": "Texture2D"
  },
  {
    "Name": "Pheony_Body",
    "Source": "C:/Game/Blocks/m1.blk",
    "Type": "Mesh"
  }
]
''', encoding="utf-8")
        dst = Path(TMP) / "compact.tsv"
        self.assertEqual(zx_build_map.compact(src, dst), 2)
        self.assertEqual(dst.read_text(encoding="utf-8").splitlines(),
                         ["Avatar_Female_Size02_Pheony_Model\tAnimator\ta.blk", "Pheony_Body\tMesh\tm1.blk"])


class CommonTest(unittest.TestCase):
    def test_copy_if_changed(self):
        d = Path(tempfile.mkdtemp(dir=TMP))
        src, dst = d / "a.blk", d / "b.blk"
        src.write_bytes(b"one")
        self.assertTrue(zx_common.copy_if_changed(src, dst))
        self.assertFalse(zx_common.copy_if_changed(src, dst))   # 같으면 다시 복사하지 않는다
        src.write_bytes(b"two!")                                  # 게임 업데이트로 바뀜
        os.utime(src, (time.time() + 10, time.time() + 10))
        self.assertTrue(zx_common.copy_if_changed(src, dst))
        self.assertEqual(dst.read_bytes(), b"two!")

    def test_decode_console(self):
        self.assertEqual(zx_common.decode_console("[훅] 동작 3개".encode("utf-8")), "[훅] 동작 3개")
        if os.name == "nt":
            import ctypes
            cp = f"cp{ctypes.windll.kernel32.GetOEMCP()}"
            try:
                raw = "[훅] 동작".encode(cp)
            except UnicodeEncodeError:
                self.skipTest(f"OEM 코드 페이지 {cp}에 한글이 없음")
            self.assertEqual(zx_common.decode_console(raw), "[훅] 동작")


class DumpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import zx_map_dump
        except ImportError as e:   # scipy가 없으면 건너뛴다
            raise unittest.SkipTest(f"zx_map_dump를 못 불러옴: {e}")
        cls.m = zx_map_dump

    def test_parse_vb(self):
        f = Path(TMP) / "x-vb0=abc.txt"
        f.write_text("stride: 40\nvertex count: 2\n"
                     "vb0[0]+000 POSITION: 1, 2, 3\nvb0[0]+012 BLENDINDICES: 0, 1, 0, 0\n"
                     "vb0[1]+000 POSITION: 4, 5, 6\nvb0[1]+012 BLENDINDICES: 2, 0, 0, 0\n", encoding="utf-8")
        vb = self.m.parse_vb(f)
        np.testing.assert_array_equal(vb["POSITION"], [[1, 2, 3], [4, 5, 6]])
        np.testing.assert_array_equal(vb["BLENDINDICES"][:, 0], [0, 2])

    def test_best_axis_finds_xflip_scale(self):
        rng = np.random.default_rng(0)
        dump = rng.normal(size=(500, 3)) * 50
        fbx = dump * np.array([-1, 1, 1]) * 0.01              # 지금까지 본 관계: x 반전 × 0.01
        d, p, sg, s, gi = self.m.best_axis(dump, [np.zeros((3, 3)), fbx])
        self.assertEqual((tuple(p), tuple(sg), s, gi), ((0, 1, 2), (-1, 1, 1), 0.01, 1))
        self.assertLess(d, 1e-9)

    def test_best_axis_nearest_ignores_order(self):
        from scipy.spatial import cKDTree
        rng = np.random.default_rng(1)
        dump = rng.normal(size=(2000, 3)) * 50
        fbx = (dump * np.array([-1, 1, 1]) * 0.01)[rng.permutation(2000)]
        m, p, sg, s = self.m.best_axis_nearest(dump, cKDTree(fbx))
        self.assertEqual((tuple(p), tuple(sg), s), ((0, 1, 2), (-1, 1, 1), 0.01))


if __name__ == "__main__":
    unittest.main()
