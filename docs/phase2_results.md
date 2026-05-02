# Phase 2 결과: 파일 포맷 파서

> 완료일: 2026-04-19  
> 도구: ilspycmd DLL 역분석 + Python 구현 + 실파일 검증

---

## 1. 구현된 파서 목록

| 파일 | 포맷 | 결과 | 검증 |
|------|------|------|------|
| `parsers/rmm_parser.py` | RedMoon MapData 1.0 | ✅ | 65개 맵 파일 |
| `parsers/irs_parser.py` | Resource File (스프라이트) | ✅ | 96개 타일 |
| `parsers/jcr_parser.py` | Joycity RAW (캐릭터) | ✅ | 79개 JCR, PPM 출력 |
| `parsers/mst_parser.py` | JcMsgList Table (텍스트 DB) | ✅ | 750/1019 아이템 |
| `parsers/csmi_parser.py` | CSMI File 2.0 (오브젝트) | ✅ | 1032 오브젝트, 34848 스프라이트 |

---

## 2. 포맷별 상세 구조

### 2.1 RMM (RedMoon Map Data)

```
[u8 len]["RedMoon MapData 1.0"]
[u32 width][u32 height]
[u8 ver_len][bytes version EUC-KR]  ← 건물명/지역명 포함
[u32 skip]
[u32 tile_type_count]
  For each tile_type: [u16 id][u32 a][u32 b][u32 c][u32 d]
Grid[height][width] × 8바이트:
  tileId  = ((b1 & 0x7F) << 4) | ((b0 & 0xF0) >> 4)   // 11비트
  objCode = ((b3 & 0xFF) << 2) | ((b2 & 0xC0) >> 6)   // 10비트
  subType = ((b2 & 0x3F) << 1) | ((b1 & 0x80) >> 7)   // 7비트
  frame   = b6                                           // 8비트
  rotation = b4 / 8                                     // 5비트
```

**맵 통계**: 65개 실내맵 (14×21 ~ 13×19 그리드), 평균 280개 오브젝트/맵  
**버전 필드**: 한국어 건물명 (EUC-KR), 예: "강아지 게임방", "Coffee Shop"

---

### 2.2 IRS (Resource File - 타일 스프라이트)

```
[14바이트 "Resource File\0"]
[u32 skip/version]
[u32 frame_count]
[frame_count × u32 offset_table]

At each offset (0 = empty):
  [u32 data_size]  ← 인코딩된 데이터 크기 (num5 카운터 상한)
  [u32 origin_x]   ← 스프라이트 캔버스 왼쪽 여백
  [u32 origin_y]   ← 스프라이트 캔버스 위쪽 여백
  [u32 sprite_w]   ← 스프라이트 실제 너비
  [u32 sprite_h]   ← 스프라이트 실제 높이
  [u32 × 4 skip]
  
픽셀 스트림 명령:
  0 → 프레임 종료
  1 → [u32 count] [u16 palette_idx × count] → RGBA
  2 → [u32 skip_count] → count/2 픽셀 건너뜀
  3 → 다음 행으로 이동
```

**외부 팔레트 필요**: 픽셀 인덱스만 저장, RGBA는 별도 팔레트 필요  
**통계**: 10프레임/파일, 64×32 픽셀 (애니메이션 타일)

---

### 2.3 JCR (Joycity RAW - 캐릭터 스프라이트)

```
[28바이트 "Joycity #$@(RAW! #!#(!# #!TS"]
[u16 frame_count]
[u16 × frame_count 프레임 데이터 크기]

각 프레임:
  [u16 width][u16 height]
  [u8 palette_type]:
    0  → 그레이스케일 256색 팔레트 (인덱스0 = 마젠타 투명)
    1  → 커스텀 팔레트: [u8 count][RGB × count]
    57 → 특수 (864바이트 건너뜀, 35×35 빈 프레임)
    93 → 특수 (offset 3927로 리셋)
    197 → 종료 센티넬

  RLE 픽셀 데이터:
    RLE 마커: FF FE [u8 idx] [u16 count]  ← 5바이트
    단일 픽셀: [u8 idx]
  출력: width×height×3 바이트 (RGB)
```

**팔레트 내장**: JCR은 각 프레임에 팔레트 포함  
**통계**: 3~15프레임/파일, 최대 339×234 픽셀

---

### 2.4 MST (JcMsgList Table - 아이템 텍스트 DB)

```
[u8 15]["JcMsgList Table"]
[u32 count_metadata]
[u32 metadata]
... 헤더 패딩 (offset ~919까지) ...

각 레코드 (바이너리 스캔으로 검색):
  [u8 code_len][ASCII code][0x01][0x80]
  [u32 type_id][u32 item_num][u32 flags][2바이트 class_code]
  [;][EUC-KR name][;][EUC-KR detail][;][EUC-KR 가격식][;][;][;]
```

**인코딩**: EUC-KR (CP949)  
**파싱 방법**: `[code_len][code][0x01][0x80]` 패턴 스캔  
**통계**: item.mst=750개, item_hc.mst=1019개

---

### 2.5 CSMI (CSMI File 2.0 - 오브젝트 배치)

```
[u32 object_count]

각 오브젝트:
  [pascal_str "CSMI File 2.0"]  ← 타입 체크
  [u32 object_id][u32 skip][u32 skip]
  [pascal_str type_code]
  [u32 skip][u32 skip]
  [pascal_str transform]         ← 애니메이션 행렬 (UTF-8)
  [pascal_str name]              ← ASCII
  [u32 layer_count]
  For each layer:
    [u32 sprite_count]
    For each sprite: [u32×6][i32×3][u32][u32][u32×anim_count]
  [u32 collision_layer_count]
  For each: [u32 point_count][u16×point_count]
  [u32 trailing]

※ pascal_str: [u8 len][bytes], len==0xFF → [u16 len][bytes]
```

**통계**: MS/A/obj.gpd = 1032 오브젝트, 34848 스프라이트  
**트랜스폼 형식**: "w h depth rotation_matrices;..." ASCII 텍스트

---

## 3. 발견된 특이사항

### 가변 길이 인코딩
CSMI 포맷의 pascal 문자열은 `0xFF` 바이트가 나오면 다음 2바이트를 u16 길이로 사용:
```python
slen = data[pos]; pos += 1
if slen == 0xFF:
    slen = struct.unpack_from('<H', data, pos)[0]; pos += 2
```

### IRS 외부 팔레트
IRS 타일 스프라이트는 팔레트 인덱스만 저장. 실제 색상은 게임 내 글로벌 팔레트 테이블을 참조. Phase 3 (네트워크 분석) 후 완전한 이미지 추출 가능.

### RMM 버전 필드
맵 파일의 "버전" 필드는 실제로 건물/장소 이름을 EUC-KR로 저장:
```
"강아지 게임방" (dog game room)
"Coffee Shop"
"세탁소" (laundromat)
```

---

## 4. 파일 통계

| 포맷 | 파일 수 | 총 용량 |
|------|---------|---------|
| .rmm (맵) | 65 | ~200KB |
| .irs (타일) | 96 | ~500KB |
| .jcr (캐릭터) | 79 | ~10MB |
| .mst (텍스트) | 6 | ~1MB |
| .gpd (오브젝트) | 2 | ~5MB |

---

## 5. Phase 3 준비

### 네트워크 분석 방법
```bash
# Wireshark 캡처 (게임 실행 중)
sudo tcpdump -i any -w joytalk.pcap host jc.joy-june.com

# 대상 포트
7942/TCP  # 채팅/API
7945/TCP  # 메인 게임
7946/UDP  # 음성채팅
```

### 패킷 포맷 검증 필요 항목
- JSON 패킷 구조 확인 (Phase 1에서 추정)
- 로그인 토큰 흐름 (`webtoken` 패킷)
- 이동 패킷 (`move` 타입) 좌표 체계
- 게임 오브젝트 동기화 (`gameObjects` 타입)
