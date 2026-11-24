# ZZZ Character FBX Extract

젠레스 존 제로(ZZZ) 캐릭터의 **게임 뼈대 + 모델 + 몸 동작 전체**를 내 PC에 설치된 게임 파일에서 FBX 하나로 뽑는 도구입니다. ZZMI(ZZ-Model-Importer) 덤프의 **뼈 팔레트 번호 → 실제 뼈 이름** 표도 만들어 줍니다.

더블클릭해서 메뉴로 쓸 수 있고, AI 없이도 됩니다. [Claude Code](https://claude.com/claude-code)가 있다면 스킬로 넣어 말로 시킬 수도 있습니다.

[English README](README.en.md)

## 왜 만들었나
의상 이식·웨이트 작업을 하다 보면 이런 것들이 필요합니다.
- 근사 뼈대가 아닌 **진짜 게임 뼈대**로 웨이트 시험하기
- 공격·회피·궁극기 같은 **실제 게임 동작**으로 옷이 뚫리는지(클리핑) 확인하기

AnimeStudio CLI는 게임 파일(.blk)을 **하나씩 따로** 읽습니다. 그런데 ZZZ는 몸 메시와 동작이 모델과 다른 파일에 들어 있습니다. 그래서 CLI만 쓰면 뼈대와 머리카락만 나오고 몸과 동작이 빠집니다.

이 도구는 작은 시작 훅으로 CLI가 필요한 파일을 **한꺼번에** 읽게 합니다. 그 덕분에 모델과 동작이 한 FBX로 나옵니다. AnimeStudio 코드 자체는 고치지 않습니다.

## 결과 예시
- **피닉스(Pheony):** 뼈 314개, 몸 동작 123개. ZZMI 덤프와 정점 순서가 같았고, 부위마다 웨이트 차이는 0이었습니다.
- **아스트라:** 대기·공격·회피 동작이 Blender에서 실제로 움직이는 것까지 확인했습니다.

## 주의
- **내 게임 파일에서 개인 작업용으로만 쓰세요.** 뽑은 모델·동작을 배포하지 마세요. 게임 파일 추출은 모드 작업처럼 게임 약관에 걸릴 수 있습니다. 쓰는 책임은 각자에게 있습니다.
- 게임 폴더는 읽기만 합니다. 필요한 파일은 작업 폴더로 복사해서 씁니다.
- 이미 뽑은 결과 폴더는 덮어쓰지 않습니다.
- 이 저장소에는 게임 데이터, 뽑은 결과물, 도구 실행 파일이 들어 있지 않습니다.

## 준비물
| 필요한 것 | 어디서 | 메모 |
|---|---|---|
| 젠레스 존 제로 | Steam 또는 HoYoPlay | 설치 폴더를 자동으로 찾습니다 |
| Python 3.10 이상 | [python.org](https://www.python.org/downloads/) | 설치할 때 **"Add python.exe to PATH"**에 체크 |
| AnimeStudioUltimate 1.8.1 | [GitHub 릴리스](https://github.com/LegionInstaller/AnimeStudioUltimate/releases) | 실제로 파일을 읽고 FBX를 만드는 도구 (MIT) |
| .NET 10 런타임 | [Microsoft](https://dotnet.microsoft.com/download/dotnet/10.0) | **Windows x64 zip**을 받으면 설치 없이 압축만 풀면 됩니다 |
| Blender (권장) | [blender.org](https://www.blender.org/download/) | 바로 여는 `.blend` 만들기, 애드온, 동작 확인, 덤프 대조 (5.2에서 확인) |
| ZZ-Model-Importer-Assets (선택) | [ZZ-Model-Importer](https://github.com/leotorrez/ZZ-Model-Importer) 관련 프로젝트 | 팔레트 → 뼈 이름 대조에만 필요 |

## 쓰는 법
### 1. 받기
[최신 릴리스](https://github.com/VioletMoon42/zzz-character-fbx-extract/releases/latest)에서 **Source code (zip)**을 받아 아무 곳에 풉니다. 실행 파일은 들어 있지 않습니다.

### 2. 처음 설정 (한 번만)
1. `zzz-character-fbx-extract.bat`을 더블클릭하고 메뉴에서 **1. 처음 설정**을 고릅니다.
2. 작업 폴더(`%USERPROFILE%\ZZZ_CharacterFBX`)가 생기고, 그 안의 `tools` 폴더에 무엇을 풀어야 하는지 알려 줍니다.
3. AnimeStudioUltimate zip과 .NET 10 런타임 zip을 `tools` 안에 풉니다. 폴더 이름은 자유입니다.
4. 다시 **1. 처음 설정**을 고릅니다. 게임 폴더, 도구, Blender를 찾아 설정을 저장하고, 훅도 알아서 빌드합니다. 윈도우에 기본으로 들어 있는 컴파일러를 쓰므로 따로 설치할 것은 없습니다.

### 3. 캐릭터 뽑기
1. **2. 캐릭터 뽑기**를 고르고 영어 이름을 넣습니다. 예: `Astra`, `Phoenix`.
2. 처음이거나 게임이 업데이트됐으면 검색 지도부터 만듭니다(약 7분, 임시 공간 약 4 GB).
3. 이름이 게임 속 이름과 다르면 후보가 나옵니다. 번호로 고르면 됩니다. 예를 들어 Phoenix의 게임 속 이름은 Pheony입니다. 한 번 고르면 기억합니다.
4. 몸 동작이 100개쯤이면 5~10분 걸립니다.

결과는 `%USERPROFILE%\ZZZ_CharacterFBX\characters\<게임 속 이름>\`에 생깁니다.
- `model\`: 모델만 든 FBX (수 MB)
- `anim\`: 모델 + 몸 동작 전체 FBX (수백 MB)와 `.animator.json` (동작 연결·타이밍)
- 각 폴더의 `.blend`: Blender가 있으면 같이 만듭니다. 바로 열어 쓰는 파일입니다(아래 "뽑은 결과 쓰는 법").

### 4. 확인 (선택)
- **3. 뽑은 동작 확인**: 대표 동작 2~3개만 따로 뽑아 Blender에서 실제로 움직이는지 숫자로 보여 줍니다.
- **4. ZZMI 덤프와 뼈 이름 대조**: 부위마다 `palette_to_bone.json`을 만들고 ✓/✗로 결과를 보여 줍니다. 애드온이 모드 메시를 붙일 때 이 표를 씁니다.
- **7. 이미 뽑은 결과로 Blender 파일 만들기**: `.blend`가 없는 결과에 만들어 줍니다.

## 명령으로 쓰기
메뉴 대신 명령으로도 됩니다(PowerShell, 압축 푼 폴더에서).
```powershell
.\zzz-character-fbx-extract.bat extract Astra
.\zzz-character-fbx-extract.bat extract Astra --clips "Idle_Loop|Attack_Normal_01"
.\zzz-character-fbx-extract.bat check Astra
.\zzz-character-fbx-extract.bat dump Pheony Pheonix
.\zzz-character-fbx-extract.bat list
.\zzz-character-fbx-extract.bat blend Astra
```
- `--clips <정규식>`: 동작 일부만. 동작 이름(`..._Ani_` 다음)의 앞부분에 맞춥니다. 정확히 그 동작 하나만이면 끝에 `$`를 붙입니다.
- `--with-facial`: 얼굴 동작도
- `--model-only`: 모델만
- `--code <게임 속 이름>`: 후보 고르기를 건너뛰고 바로
- `--no-blend`: `.blend`를 만들지 않음

작업 폴더를 바꾸려면 환경 변수 `ZX_ROOT`를 정합니다.

## 뽑은 결과 쓰는 법 (Blender)
### 바로 열기
Blender가 설정돼 있으면 뽑을 때 FBX 옆에 **`.blend`**도 만들어 둡니다. 더블클릭해서 열면 됩니다.
- 실제 크기(키 약 1.5~1.7 m), 60 fps, 텍스처가 보이는 화면으로 맞춰 두었습니다.
- 동작 전체가 타임라인 하나에 이어 붙어 있고, 동작마다 이름표(마커)가 있습니다. **Space**로 재생합니다.
- 공격·회피는 앞으로 나가는 동작이라 캐릭터가 제자리를 벗어납니다. 정상입니다.
- 예전에 뽑은 결과는 메뉴 **7번**으로 `.blend`를 만들 수 있습니다.
- 몸 텍스처는 빠질 수 있습니다(AnimeStudio가 읽은 파일에 들어 있던 텍스처만 나옵니다). 모양과 동작을 보는 데는 지장이 없습니다.

### 애드온: 동작 고르기, 내 모드 메시 붙이기
설치: Blender → **Edit → Preferences → Add-ons** → 오른쪽 위 ▼ → **Install from Disk…** → 이 폴더의 `blender_addon\zzz_character_fbx_tools.py`. 3D 화면에서 **N**을 누르면 오른쪽에 **ZZZ FBX** 탭이 생깁니다.

- **동작 고르기**: 탭에 나온 동작 이름을 누르면 그 동작으로 가서 그 구간만 반복 재생합니다.
- **내 모드 메시로 클리핑 미리 보기**
  1. 내 모드 작업 파일(XXMI Tools로 가져온 메시가 있는 .blend)을 엽니다.
  2. **게임 캐릭터 불러오기** → 뽑은 결과의 `anim\….blend`를 고릅니다. 뼈대, 메시, 동작, 이름표가 들어옵니다.
  3. 내 메시를 선택하고 **선택한 메시를 게임 뼈대에**를 누릅니다.
  4. `게임 뼈대 시험` 컬렉션에 사본이 생기고 게임 동작대로 움직입니다. **원본 메시는 그대로**입니다.
  - 위치·크기·좌우 반전은 게임 몸에 가장 잘 겹치는 쪽으로 자동으로 맞춥니다.
  - 버텍스 그룹이 번호(`0`, `1`, `2`…)면 메뉴 4번이 만든 `palette_to_bone.json`으로 뼈 이름을 붙여 **모드 웨이트를 그대로** 씁니다. 표는 같은 캐릭터 폴더에서 메시 이름으로 찾습니다.
  - 표가 없으면 게임 메시에서 가장 가까운 웨이트를 옮겨 옵니다.

### FBX를 직접 쓸 때
- Blender에서 FBX를 직접 가져올 때는 Scale을 **100**으로 하세요. 그대로면 키가 1.5 cm입니다.
- 뼈대 이름으로 시작하는 액션만 그 뼈대의 동작입니다. `Root|`, `Key|`, `FX_Root|`로 시작하는 액션은 다른 오브젝트용입니다.
- ZZMI 덤프 좌표 → FBX는 x 반전 × 0.01입니다.

## 다른 게임
젠레스 존 제로 전용입니다. 원신(7.0)으로 시험해 보니 AnimeStudio가 파일은 읽지만, 몸 메시가 `Body`·`Face` 같은 공통 이름으로 다른 파일에 흩어져 있어 이 도구의 찾기 방식으로는 뼈대만 나왔습니다. 붕괴: 스타레일은 시험하지 못했습니다.

## 문제가 생기면
- **"먼저 setup을 실행해 주세요"**: 메뉴 1번을 실행합니다.
- **후보가 하나도 안 나옴**: 영어 이름(인게임 영어판 이름)으로 다시 해 보세요.
- **뽑기 실패**: `characters\<이름>\log_*.txt`를 보세요. 게임 업데이트 직후라면 메뉴 6번으로 지도를 다시 만듭니다.
- **`.blend`가 안 생김**: 메뉴 1번에서 Blender를 찾았는지 봅니다. 실패했다면 `characters\<이름>\log_*_blend.txt`를 보세요.
- **AnimeStudio를 새 버전으로 바꾼 뒤 안 됨**: 훅이 1.8.1의 내부 이름에 맞춰져 있습니다. 1.8.1을 쓰세요.

## 고치거나 기여할 때
- 게임 없이 도는 단위 테스트: `python -m unittest discover -s tests`
- 각 스크립트는 `--help`로 인자를 보여 줍니다. 구조와 함정은 [SKILL.md](SKILL.md)의 "원리와 함정"에 있습니다.

## Claude Code 스킬로 쓰기
이 폴더를 `%USERPROFILE%\.claude\skills\zzz-character-fbx-extract\`에 두면 "아스트라 게임 동작 뽑아줘"처럼 말로 시킬 수 있습니다. 순서와 확인할 값은 [SKILL.md](SKILL.md)에 있습니다.

## 감사
- [AnimeStudioUltimate](https://github.com/LegionInstaller/AnimeStudioUltimate): 실제 읽기와 FBX 내보내기는 이 도구가 합니다. 훅은 그 CLI 코드를 그대로 불러 쓸 뿐입니다.
- [ZZ-Model-Importer (ZZMI)](https://github.com/leotorrez/ZZ-Model-Importer)와 ZZ-Model-Importer-Assets

## 라이선스
MIT. [LICENSE](LICENSE)를 보세요. 이 저장소의 스크립트에만 적용되며, 게임 데이터와 거기서 뽑은 결과물에는 적용되지 않습니다.
