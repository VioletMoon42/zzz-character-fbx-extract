---
name: zzz-character-fbx-extract
description: 젠레스 존 제로(ZZZ) 캐릭터의 게임 뼈대·모델·몸 동작(공격, 회피, 궁극기, 대기, 걷기 등)을 내 PC에 설치된 게임 파일에서 FBX로 뽑고, ZZ-Model-Importer-Assets 덤프의 뼈 팔레트 번호를 실제 뼈 이름에 연결한다. 의상 이식·웨이트 작업 전에 캐릭터 데이터를 뽑아 둘 때, 근사 뼈대 대신 게임 뼈대로 웨이트를 시험할 때, 실제 게임 동작으로 클리핑을 확인할 때 쓴다. "게임 데이터 뽑아줘", "모션 데이터", "애니메이션 추출", "뼈대 추출", "진짜 뼈대", "실제 모션으로 시험", "AnimeStudio" 같은 말이 나오면 이 스킬을 쓴다.
---

# ZZZ Character FBX Extract (캐릭터 뼈대·모델·동작 → FBX)

내 PC에 설치된 ZZZ 게임 파일에서 캐릭터의 **게임 뼈대 + 모델 + 몸 동작 전체**를 FBX로 뽑는다. 그다음 ZZMI 덤프의 **팔레트 번호 → 실제 뼈 이름** 표를 만든다.

## 지켜야 할 것
- **게임 폴더는 읽기만 한다.** 필요한 `.blk`는 `characters\<코드명>\input\`에 사본으로 복사해서 쓴다.
- **개인 작업용으로만 쓴다.** 뽑은 모델·동작은 배포하지 않는다. 게임 약관상 위험(모드 작업과 비슷)은 사용자에게 처음 한 번만 짧게 말한다.
- **다른 사이트의 막힌 파일을 우회해 받지 않는다.** 항상 사용자 자신의 게임 파일에서 뽑는다.
- **출력 폴더가 이미 있으면 덮어쓰지 않는다.** 스크립트가 알아서 멈춘다. 다시 뽑으려면 사용자 승인을 받고 폴더 이름을 바꾸거나 새 폴더를 쓴다.

## 준비 (처음 한 번)
`zx.py setup`이 게임·도구·Blender를 찾아 설정을 만들고 훅을 빌드한다. 수동으로 하면 다음과 같다.
- 작업 폴더(`ZX_ROOT`, 기본값 `%USERPROFILE%\ZZZ_CharacterFBX`)에 AnimeStudioUltimate 1.8.1과 휴대용 .NET 10 런타임을 둔다.
- `scripts\ExtractHook.cs`를 빌드해 `ExtractHook.dll`을 만든다.
- 아무 스크립트나 한 번 돌리면 `config.json` 틀이 생긴다. `<...>` 부분을 채운다.

사람이 직접 쓸 때는 `zzz-character-fbx-extract.bat`(메뉴) 또는 `scripts\zx.py setup|extract|check|dump|list|map`을 쓴다. 아래 단계는 그 안에서 부르는 개별 스크립트다.

스크립트는 모두 `python -X utf8 <스크립트>`로 돌린다(`-X utf8`이 없으면 한글이 깨진다). 각 스크립트는 `--help`로 인자를 보여 준다. 필요한 패키지: numpy, scipy(덤프 대조, `requirements.txt`).
게임 없이 도는 단위 테스트: `python -m unittest discover -s tests`. 스크립트를 고친 뒤에는 이것부터 돌린다.

## 작업 폴더 구성 (`ZX_ROOT`)
- `config.json`: 게임 Blocks 경로, Blender, 덤프 루트, 도구 경로.
- `map\zzz_map_compact.tsv`: 간추린 검색 지도(이름·종류·.blk, 약 17 MB). `map_info.json`에 만든 날짜와 게임 버전이 있다.
- `aliases.json`: 표시 이름 → 게임 코드명 (예: Phoenix → Pheony).
- `characters\<코드명>\`: 캐릭터별 결과.

## 순서
1. **지도 확인**: `map\map_info.json`이 없거나, 그 `game_version`이 게임 `config.ini`의 `game_version`과 다르면 `zx_build_map.py`를 돌린다.
   - 약 7분 걸리니 사용자에게 먼저 알린다.
   - 전체 지도(약 3.5 GB JSON)를 만들어 간추린 뒤, 큰 임시 파일은 스스로 지운다.
2. **찾기**: `zx_find.py <이름>`
   - 코드명, 모델 Animator(`Avatar_*_<코드명>_Model`), 모델·메시·동작이 든 `.blk` 목록, 몸 동작 수를 찾아 `characters\<코드명>\plan.json`에 쓴다.
   - 표시 이름과 코드명이 다를 수 있다(Phoenix → Pheony). 못 찾으면 후보 목록이 나오니, 사용자와 확인한 뒤 `--code <코드명>`으로 다시 돌린다. 확정되면 `aliases.json`에 쌓인다.
   - 스킨·의상은 `Astra_Chandelier`처럼 밑줄이 들어간 코드명이다.
3. **뽑기**: `zx_extract.py <코드명>` (몸 동작 100여 개면 5~10분)
   - `model\`: 모델만 든 FBX(가볍다, 수 MB).
   - `anim\`: 모델 + 몸 동작 전체 FBX(수백 MB)와 `.animator.json`(게임 속 동작 연결·타이밍).
   - 선택 옵션
     - `--clips <정규식>`: 동작 일부만. `_Ani_` 다음 동작 이름의 **앞부분**에 맞춘다(예: `Idle_Loop|Attack_Normal_01`, 정확히 하나만이면 끝에 `$`). 같은 게임 파일에 다른 모습(`Pheony_Illness` 등)의 같은 이름 동작이 섞여 있어서, 스크립트가 앞부분을 이 모델로 고정한다.
     - `--with-facial`: 얼굴 동작 포함
     - `--model-only`: 모델만
4. **덤프와 대조** (ZZMI 덤프를 쓸 때만): `zx_map_dump.py <코드명> [덤프 폴더 이름]`
   - 덤프 폴더 이름은 ZZ-Model-Importer-Assets 이름이다. 코드명과 다를 수 있다(예: Pheonix, Astra).
   - 모델 FBX를 Blender로 읽어 `fbx_data\`를 만든다(`zx_read_fbx_blender.py`, 처음 한 번만).
   - 덤프 부위마다 FBX 메시를 찾고, `dump_map\<부위>_palette_to_bone.json`과 `dump_map_report.json`을 만든다.
   - **확인할 값**: `check_weight_L1`의 median·max가 0 근처여야 표가 맞다. 0이 아니면 그대로 쓰지 말고 원인부터 본다.
   - 좌표 관계도 보고서에 남긴다. 지금까지는 덤프 → FBX가 x 반전 × 0.01이었다.
   - 무기처럼 모델 FBX에 없는 부위는 "맞는 메시 없음"으로 건너뛴다. 무기는 별도 모델(`*_Weapon_Model` 등)이다.
5. **동작 확인**: 큰 FBX를 열지 말고, 대표 동작 2~3개만 따로 뽑아 실제로 움직이는지 본다.
   - `zx.py check <코드명>`: Idle_Loop, Attack_Normal_01, Evade_Front_01(있는 것만)을 `anim_check\`에 따로 뽑고 `zx_check_anim_blender.py`로 잰다.
   - `max_move_rel`(이동 거리 ÷ 키)이 대기는 0.1 안팎으로 작고, 공격·회피는 앞으로 나가는 만큼 커지면(피닉스 공격 4.3) 정상이다. 모두 0이면 동작이 뼈대에 안 붙은 것이다.
6. **보고**: 코드명, 뼈 수, 몸 동작 수와 대표 동작 이름, 부위별 대조 결과, 동작 확인 결과, 결과 폴더를 보고한다. 큰 FBX를 Blender로 열어 봤는지는 따로 밝힌다.

## 결과를 쓰는 법 (웨이트 작업)
- 다른 캐릭터에서 옮겨 온 웨이트를 **팔레트 번호**로 만들었으면 `palette_to_bone.json`으로 이름을 붙여 게임 뼈대에 그대로 얹을 수 있다.
- **크기 주의**: Blender로 가져오면 캐릭터가 1/100 크기다(덤프 좌표 → FBX = x 반전 × 0.01). 덤프 좌표로 작업한 장면에 얹을 때는 이 관계를 쓴다.
- Blender에서 동작 하나를 가져오면 `<뼈대 이름>|<동작>|Base Layer` 외에 `Root|`, `Key|`(셰이프 키), `FX_Root|` 액션도 생긴다. 뼈대에는 뼈대 이름으로 시작하는 액션만 쓴다.
- 동작 FBX에는 게임 rest 자세와 보조 본(Skn_*, 치마·머리 본 등)이 있다. 근사 뼈대로 하던 자세 시험을 실제 동작으로 대신할 수 있다.
- 동작은 60 fps다. 연속 동작(콤보)은 `.animator.json`의 타이밍을 쓴다. AnimeStudioUltimate 문서 `docs/zzz-animator-controllers.md`에 설명이 있다.
- 동작이 많이 든 FBX는 Blender로 열 때 오래 걸린다. 시험에는 `--clips`로 대표 동작 몇 개만 따로 뽑는 편이 빠르다.
- **바로 쓰는 .blend**: Blender가 설정돼 있으면 `zx_extract.py`가 FBX마다 옆에 `.blend`를 만든다(`zx_make_blend_blender.py`, 끄려면 `--no-blend`). 예전 결과는 `zx.py blend <코드명>`.
  - FBX를 Scale 100으로 가져와 실제 크기(키 1.5~1.7 m), 60 fps, 머티리얼 미리보기.
  - 동작은 NLA로 타임라인 하나에 이어 붙이고(대기 동작 먼저, 사이 10프레임) 동작마다 마커를 단다. 뼈대·셰이프 키(`Key|`)·`Root|`·`FX_Root|`의 같은 동작을 같은 자리에 놓는다.
  - 텍스처는 `//파일이름`으로 가리키고 같은 파일 중복 이미지는 하나로 합친다.
  - 확인한 값: 피닉스 2동작(키 1.538 m, 마커 2), 아스트라 134동작(마커 133, 1.70 m, 2분 남짓, .blend 714 MB).
- **애드온** `blender_addon\zzz_character_fbx_tools.py` (사이드바 "ZZZ FBX")
  - 게임 캐릭터 불러오기: 결과 .blend의 장면을 붙여 넣고 마커·프레임 범위·fps를 가져온다. 불러온 오브젝트에는 `zzz_fbx_source` 속성(원본 .blend 경로)을 단다.
  - 선택한 메시를 게임 뼈대에: 사본을 `게임 뼈대 시험` 컬렉션에 만들고, 축 바꿈·반전 48가지 × 크기 5가지 중 게임 메시(rest)와 중앙 거리가 가장 작은 변환을 고른다. 번호 그룹은 `<결과>\..\dump_map\**\<부위>_palette_to_bone.json`(메시 이름이 부위 이름으로 시작)으로 이름을 바꾸고, 없으면 게임 메시 전체를 잠깐 합친 것에서 Data Transfer(Generate Data Layers 포함)로 옮긴다.
  - Data Transfer는 Generate Data Layers를 하지 않으면 그룹이 하나도 안 옮겨진다(0개 → 172개로 확인).
  - 확인한 값: XXMI Tools "Import XXMI dump folder"(ZZZ 프리셋)와 "Frame Analysis" 가져오기 모두, 피닉스 몸·머리카락이 공격 동작 내내 게임 메시와 0.0 mm로 겹쳤다. 원본 메시의 그룹 이름은 그대로였다.

## 원리와 함정 (고칠 때 참고)
- **실행 방법**: CLI는 `app\AnimeStudio.CLI.exe`를 `DOTNET_ROOT=휴대용 .NET 10`으로 직접 실행해야 한다.
  - `dotnet exec AnimeStudio.CLI.dll`로 돌리면 FBX 네이티브 DLL을 `dotnet.exe` 옆에서 찾다가 "The type initializer for 'AnimeStudio.Fbx' threw an exception"이 난다.
- **훅이 필요한 이유**: CLI는 입력 폴더의 파일을 **하나씩 따로** 읽고 내보낸다. ZZZ는 몸 메시(SeparateMesh)와 동작이 모델과 다른 `.blk`에 있어서, CLI만으로는 뼈대·머리카락만 나온다.
  - CAB 지도로 의존성을 풀어도 SeparateMesh는 따라오지 않았다.
- **훅이 하는 일**: `ExtractHook.dll`(DOTNET_STARTUP_HOOKS)은 CLI 프로세스 안에서 CLI 자체 코드를 그대로 부른다(Studio.assetsManager.LoadFiles(전체 파일) → Studio.BuildAssetData → Exporter.ExportAnimator(모델, 출력, 동작 목록)). CLI 코드는 고치지 않는다.
  - 환경 변수: `ZX_LIST`, `ZX_OUT`, `ZX_MODEL`, `ZX_CLIPS`, `ZX_DRY=1`(확인만).
  - 빌드는 윈도우 내장 csc(.NET Framework) 하나로 끝난다.
  - 도구 버전을 바꾸면 훅이 쓰는 내부 이름(Studio, Exporter, AssetItem)이 그대로인지 먼저 확인한다.
- **로그**: CLI 콘솔 출력은 윈도우 OEM 코드 페이지(한국어 윈도우는 cp949)다. 스크립트가 알아서 변환해 `characters\<코드명>\log_*.txt`에 쓴다.
- **지도 크기**: 전체 지도는 약 930만 항목, 3.5 GB JSON이다. 모델·뼈대·메시·동작만 남긴 간추린 지도는 30만 항목이다.
