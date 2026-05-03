# Phase 4 보강: Windows 에셋 폴더 매핑 & 파서 검증

> 검증일: 2026-05-03
> 환경: `C:\Users\berrr\AppData\Local\Joytalk\`
> 총 사이즈: Itm 7.9 MB / Res 28 MB / Street 1.5 GB

---

## 1. 파서 동작 결과 (Windows 경로 그대로)

| 파서 | 대상 파일 | 결과 |
|---|---|---|
| `jcr_parser.py` | `Res\jcr\c0001.jcr` | ✅ 6 프레임 (75x93 RGB) — 디코드 성공 |
| `mst_parser.py` | `Res\Lst\item.mst` | ✅ 750 아이템 — 한글명 정상 디코드 |
| `csmi_parser.py` | `Street\M\A\obj.gpd` | ✅ 987 오브젝트 — `CSMI File 2.0` magic 일치 |
| `irs_parser.py` | `Street\A\MGO\MGO00000.irs` | ✅ 10 프레임 (위치 + 픽셀 인덱스) |
| `rmm_parser.py` | `Street\M\Map00001.rmm` | ✅ 11x16 셀, 버전 `자기방` |

**파서 코드 수정 0줄.** 인자로 Windows 경로만 넘기면 그대로 작동. macOS 기본 경로(`/Applications/JoyTalk.app/...`)는 standalone 실행 시에만 쓰이므로 사용 안 하면 무관.

샘플 PPM 출력: `captures/sprites/c0001_frame00..05.ppm`, `MGO00000_frameNN_GRAY.ppm`
(jcr 는 임베디드 팔레트 → 컬러 정상 / irs 는 외부 `.pal` 필요해서 grayscale 디버그)

---

## 2. 에셋 폴더 매핑

### 최상위

```
Itm\          7.9 MB   아이템 / 아바타 스프라이트 (jcr)
Res\           28 MB   리소스 (jcr 캐릭터, mst 아이템 DB, Wav/Bus/Icons)
Street\       1.5 GB   맵 + 거리 자원 (irs/rms/lst/rmm/mp3 등)
```

### `Itm\` — 아이템/아바타 (3-letter code)

| 폴더 | 추정 용도 | 파일 형식 |
|---|---|---|
| `Avt\HLP, UBB, UBG, ULB, ULG, UYB, UYG, VLL, _` | 아바타 (Avatar) — 의상/머리 등 카테고리별 | jcr + ils |
| `BtI\` | 일반 아이템 (Boutique Item?) | jcr + ils |
| `BtI_HC\` | 헤어 컬러 변형 (HC = Hair Color) | jcr + ils |
| `ShI\` | Shop Item | jcr + ils |

확장자 분포: 120 `.jcr` (스프라이트) + 120 `.ils` (스프라이트 리스트). 한 쌍씩 매칭.

### `Res\` — 공용 리소스

| 폴더 | 용도 | 파서 |
|---|---|---|
| `jcr\` | 캐릭터/오브젝트 베이스 스프라이트 (`c0001.jcr`, `h0005.jcr`, `intro.jpg`) | `jcr_parser` |
| `Lst\` | 데이터 테이블 — `item.mst`, `item_hc.mst`, `msg.mst`, `Dialog.mst`, `rcp.mst`, `woa.mst` | `mst_parser` |
| `Bus\` | UI 버스(이동) 아이콘 | (이미지) |
| `Icons\` | UI 아이콘 | (이미지) |
| `Wav\` | 효과음 wav | (PCM) |

### `Street\X\` — 알파벳 인덱스 (DLL 내부 하드코딩 경로 기준)

DLL 내 디코드된 경로 패턴 (`playground/string_blob_windows.dec` 의 offset 약 800–4400):

| 폴더 | 매핑 | 파일 예시 / magic |
|---|---|---|
| `Street\A\MGO\` | A의 게임오브젝트 (Map Game Object?) | `MGO0000N.irs` (Resource File) |
| `Street\A\STR\` | A의 거리 (street) 스프라이트 | `STR0000N.irs` |
| `Street\A\_\` | A의 인덱스 — `mgo.lst`, `str.lst` | (lst) |
| `Street\C\` | **캐릭터 (Character)** — `chr.gpc`, `chr_hc.gpc` (GPC 매직) | `chr.gpc` |
| `Street\E\EOb\` | etc 오브젝트 | `etc.epc` (EPC 매직) |
| `Street\E\MCR\` | mcr (몬스터 / NPC?) | `mcr.cpc` (CPC 매직) |
| `Street\I\<a–z>\` | **아이템 인덱스** — 알파벳별 분리 (a.gpi, b.gpi, … z.gpi) | `Street\I\a\A00000.irs` |
| `Street\IS\<a–z>\` | I 의 secondary (`IS\a.gpi` … `IS\z.gpi`) — 동일 패턴 | irs |
| `Street\J\` | Jym (운동 동작?) — `cjm.gpj` (GPJ 매직) | jcr/irs |
| `Street\M\` | **맵 데이터** — `Map00001.rmm` … (RedMoon Map 1.0) + `Street\M\A\obj.gpd`, `tile.gpd`, `Mapobj.gpd` (CSMI 2.0) | `rmm_parser`, `csmi_parser` |
| `Street\MS\` | Map Secondary — `MS\A\obj.gpd`, `Mapobj.gpd`, `tile.gpd` 같은 구조 | csmi |
| `Street\M\_\O\`, `_\T\` | **맵 공용 인덱스** — `tile.lst`, `obj.lst` | (lst) |
| `Street\P\` | **팔레트** (PaletteHeader v1.00) — `B.pal`, `C.pal`, `G.pal`, `H.pal`, `M.pal`, `M2.pal`, `M3.pal`, `N.pal`, `R.pal`, `S.pal`, `x.pal` | (구조 §3 참조) |
| `Street\S\Cef\` | Cef 사운드 효과 | `cef.spc` (SPC 매직) |
| `Street\S\GEF\` | GEF 사운드 효과 | `gef.spc` |
| `Street\W\Bks\` | **BGM** (Backgrounds) — `b-.mp3` 등 | mp3 |
| `Street\W\Chr\`, `Chr_hc\`, `Eft\`, `Jym\` | W의 캐릭터/효과/체조 — `Eft.lst`, `Jym.lst`, `chr.lst` | irs/lst |
| `Street\X\` | CAD 데이터 — `CAD0000N.irs` (용도 미상) | irs |

### 확장자 빈도 (Street\)

```
2207 irs    Resource File (sprite)
1409 rms    RedMoon Sprite (?)        ← 신규: 파서 없음
 272 lst    list (id → file) index
 213 rmm    RedMoon MapData 1.0       ← rmm_parser
 111 IRS    case-different irs
  72 mp3    BGM
  41 gpi    GPI (item palette index?)
  11 pal    PaletteHeader v1.00
   6 gpd    CSMI File 2.0 / tile data ← csmi_parser
   5 epc, 3 png, 2 spc, 2 gpc, 2 cpc
```

신규 발견 포맷 (파서 미구현):
- `*.rms` — 1,409개. 가장 많음. `Street\W.rms` 같은 거리 단위 스프라이트 묶음? 매직 확인 필요.
- `*.gpi` / `*.gpc` / `*.gpj` / `*.gpd` — 모두 첫 4글자가 `magic`-처럼 보이는 변형. CSMI/Resource 의 친척일 가능성.
- `*.epc` / `*.cpc` / `*.spc` — 카테고리별 컬렉션 헤더.

---

## 3. `.pal` 파일 포맷 (Street\P\)

11개 파일, 대부분 1814 bytes (몇 개 662 bytes).

```
[1]    u8     0x0d ('\r')
[13]   bytes  "PaletteHeader"
[1]    u8     0x03
[3]    bytes  "100"          ← 버전
[18]   bytes  헤더 padding (마지막 4바이트가 색 개수 추정)
... 이후 색 데이터 ...
```

색 데이터 정확한 인코딩 (RGBA / RGB / 다른 형식)은 `irs_parser` 의 palette index 와 매칭해보면서 확정 필요. 현재는 grayscale debug 만 제공.

→ **TODO:** `parsers/pal_parser.py` 신규 + `irs_parser` 의 color 출력 결합. Step 6 후속 과제로.

---

## 4. CSMI File 2.0 — `obj.gpd` / `tile.gpd` 검증

`Street\M\A\obj.gpd` 에 987 오브젝트 파싱 성공. 단, 현재 csmi_parser 가 `type=''`, `name=''` 으로 비어 나옴 — type/name 필드가 옵셔널이거나 별도 인코딩일 수 있음. 추가 분석 필요하지만 Step 4 (에뮬레이터) 진행에는 무관.

---

## 5. 파서 standalone 기본 경로 갱신 여부

기존 `parsers/*.py` 의 `if __name__ == "__main__"` 블록은 macOS 경로 `/Applications/JoyTalk.app/...` 를 default 로 사용. **수정 안 함** — 인자 없이 실행하는 케이스는 거의 없고, 인자 넘기면 Windows 경로 그대로 작동.

만약 Windows 환경 default 가 필요해지면 `os.name == 'nt'` 분기 추가하는 식으로 한 줄로 끝날 일.

---

## 6. 산출물

```
captures/sprites/c0001_frame00..05.ppm           jcr 6 프레임 (75x93, RGB)
captures/sprites/MGO00000_frame01..09_GRAY.ppm   irs 9 프레임 (grayscale debug)

tools/render_sprite.py    파서 결과를 PPM 으로 떨어뜨리는 헬퍼
docs/windows_assets.md    이 문서
```
