# Phase 1 결과: .NET 디컴파일 분석

> 완료일: 2026-04-19  
> 도구: ilspycmd 10.0.0.8330 + Python 복호화

---

## 1. 디컴파일 환경

| 항목 | 내용 |
|------|------|
| .NET SDK | 10.0.106 (brew install dotnet) |
| ilspycmd | 10.0.0.8330 |
| 대상 | `Joytalk.dll` |
| 출력 | `/Applications/JoyTalk.app/decompiled/` |

---

## 2. 난독화 분석

### 수법
- **클래스/메서드 이름**: 유니코드 특수문자로 치환 (예: `\u00a0`, `\u1680`, `⁈` 등)
- **문자열 암호화**: XOR 암호화 → `_4[i] = _4[i] ^ i ^ 0xAA`
  - 42,797바이트 암호화 문자열 blob (`_4` 배열)
  - 2,698개 문자열 인덱스 테이블 (`_5` 배열)
  - 접근 함수: `_6(index, offset, length)` → UTF-8 디코딩

### 복호화 코드 (Python)
```python
import re

cs_file = "decompiled/.../3CDA3D22-BFAD-4812-B058-4341C38661CE.cs"
with open(cs_file, 'r') as f:
    content = f.read()

data_match = re.search(r'data\(([^\)]+)\)', content)
raw_bytes = bytearray(int(x, 16) for x in data_match.group(1).split())

# XOR 복호화: _4[i] ^= i ^ 0xAA
decrypted = bytearray(b ^ (i & 0xFF) ^ 0xAA for i, b in enumerate(raw_bytes))
```

### 복호화 결과
- **총 2,698개** 문자열 성공적으로 복호화

---

## 3. 서버 인프라 (복호화된 URL)

| 함수 | URL | 용도 |
|------|-----|------|
| `_00A0()` | `https://jc.joy-june.com/joytalk/update/manifest.json` | 업데이트 매니페스트 |
| `_1680()` | `http://jc.joy-june.com/joytalk/server_status.php` | 서버 상태 확인 |
| `_2000()` | `http://jc.joy-june.com/joycityw/joytalk_notice.php` | 공지사항 |
| `_2001()` | `http://jc.joy-june.com/joytalk2.php?version=` | 버전 확인 |
| `_2002()` | `https://jc.joy-june.com/joytalk/map/?Id=` | 맵 데이터 API |
| `_2003()` | `https://jc.joy-june.com` | 베이스 URL |
| `_2005()` | `/park/apartment.php?img=` | 아파트 이미지 |
| `_2006()` | `http://jc.joy-june.com/joytalk/skill/` | 스킬 데이터 |
| `_2007()` | `http://jc.joy-june.com/joytalk/award/` | 어워드 데이터 |
| `_2008()` | `https://jc.joy-june.com/bbs/board.php?bo_table=jc_notice` | 공지 게시판 |
| `_2009()` | `https://jc.joy-june.com/bbs/register.php` | 회원가입 |
| `_200A()` | `https://jc.joy-june.com/` | 홈페이지 |
| `_200A_204E()` | `/bbs/login_check.php?pcode=` | 웹 로그인 |
| `_2036_2057()` | `https://jc.joy-june.com/joytalk/custom_upload.php` | 이미지 업로드 |
| `_2005_202F()` | `https://download.joy-june.com/joytalk/` | 파일 다운로드 |

**게임 서버 도메인**: `jc.joy-june.com`

---

## 4. 네트워크 프로토콜

### TCP 소켓 (게임 메인 프로토콜)
```csharp
// 포트 7945: 메인 게임 서버 (TCP)
TcpClient.ConnectAsync("jc.joy-june.com", 7945)

// 포트 7946: 음성채팅 서버 (UDP)  
UdpClient.Bind(IPEndPoint(IPAddress.Any, 0))
IPEndPoint("jc.joy-june.com", 7946)  // UDP 대상

// 포트 7942: 보조 연결 (TCP, 채팅/API?)
TcpClient.ConnectAsync("jc.joy-june.com", 7942)
```

### 포트 요약
| 포트 | 프로토콜 | 용도 |
|------|---------|------|
| 7942 | TCP | 보조 서버 연결 (채팅/상점 등) |
| 7945 | TCP | 메인 게임 서버 |
| 7946 | UDP | 음성채팅 (VoiceTalk, Opus/Concentus) |
| 80/443 | HTTP/HTTPS | 웹 API (PHP) |

### 패킷 구조
- **메시지 포맷**: JSON 기반 추정 (키 이름들이 camelCase JSON 형태)
- **웹 인증**: `webtoken` + `/bbs/login_check.php?pcode=` 조합
- **Keep-Alive**: `KeepAliveValues` IOControl 사용

---

## 5. 전체 패킷 타입 목록 (복호화 확인됨)

### 인증/연결
```
login, loginQueue, loginRetry, webtoken
ping, viewerHeartbeat
```

### 캐릭터/이동
```
move, avatar, avatarMake, profile
clickEvent, exchange, exchange2
```

### 채팅/메시지
```
chat, streamChat, typing, stopTyping
sendMessage, getMessages, messageHistory
sendGroupMessage, getGroupMessages, groupMessage
conversationList, conversations, deleteConversation, deleteMessage
```

### 방/채팅방
```
createRoom, deleteRoom, joinRoom, leaveRoom
getRoomMembers, getMyRooms, inviteToRoom
roomInvite, roomDeleted, kickedFromRoom
```

### 아이템/인벤토리
```
itemGet, itemDrop, itemEat, itemMove, itemRotation
invenMove, invSlot
storageGet, storagePut, storageSwap, storageOpen, storageShow, storageUpdate
```

### 상점 시스템 (매우 상세)
```
createShop, closeShop, openShopManage, toggleShopOpen
getMyShop, visitShop, visitShopInfo, getAllShopsForAttack
buyFromShop, depositToShop, withdrawFromShop
setProductPrice, setProductSlot, removeProduct
purchaseWholesale, getWholesaleItems, getWholesaleCategories
expandStorage, expandDisplay, expandNpcSlot, upgradeShopGrade
shopQuestList, shopQuestComplete, shopQuestCancel, shopQuestGenerate
shopAttacked, attackShop, activateShield, activateReflection, activateReinforcedShield
repairDamage, disposeExpired, startPromotion, cancelPromotion
hireNpc, fireNpc, setNpcPosition, sendNpcVacation, trainNpc, giveNpcSnack, giveNpcDrink
```

### 가족/결혼 시스템
```
marriage, divorce, setSpouse, removeSpouse
addChild, removeChild, approveMarriage, approveDivorce, approveAddChild
leaveFamily, buyFamilyRoom, familyRoomMap
moveOriginalFamilyRoom, moveCurrentFamilyRoom
```

### 직업/스킬
```
getWork, workInit, workStart, workOk, workClose, workUp
skill, useSkill, skillList, skillId
changeWork
```

### 동아리/클럽
```
clubs, myClubs, publicClubs
clubSelect, clubMake, clubMove, clubEnterByName
clubManager, clubManagerAdd, clubManagerRemove, clubManagerResign
clubOrderSaved, clubClosureScheduled, clubClosureCancelled
requestClubClosure, cancelClubClosure, setClubPublic, setClubOrder
kickMember
```

### 조이몬 (펫) 시스템
```
joymon, joymonBuy, joymonInfo, joymonEat, joymonEquip, joymonUnequip
joymonUpdate, joymonError, joymonOutdoor, joymonShop
joymonInventory, joymonInventoryGet, joymonInventoryPut, joymonInventorySwap
```

### 친구/소셜
```
friendsList, friendsAdd, friendsAgree, friendsDel, newFriends
praise, report, block
recallFriend
```

### 아파트/주거
```
apart, apartmentBuy, apartmentMove, apartmentBell, apartmentBellAgree, apartmentUpgrade
home, outskirtsList, visitOutskirts
villaBuy, villaBuyAgree, richvilleTrade, richvilleTradeAccept, richvilleTradeDecline
```

### 기타
```
weather, staminaUpdate, userExpLevel
exchange, exchangeMoney, exchangeFinish, exchangeClose, exchangeUp
refine, refinementStart, refinementFinish, refinementWork, refinementCancel
award, setAwardOrder
memo, memoList, memoResponse, memos
```

---

## 6. 게임 콘텐츠 파악

### 맵/도시 이름 (복호화 확인)
- 루팡시티, 삐에로시티, 쇼팽시티, 앨리스시티
- 로미오시티, 줄리엣시티, 새내기시티
- 연인의섬, 모래속의사막, 나무속의숲, 가을신촌
- 해피새내기

### 직업 시스템 (3차 직업 트리)
- **1차**: 주스리(채집/노란꽃), 자브리(요정/파란꽃), 캐리(광부/빨간꽃)
- **2차**: 식장이(요리사), 의장이(재봉사), 주장이(대장장이)
- **3차**: 거래사(상인, 100만삥 필요)

### 시민 등급 (10단계)
불량시민 → 새내기시민 → 일반시민 → 열정시민 → 모범시민 → 우수시민 → 으뜸시민 → 운사선인 → 우사선인 → 풍백선인

### 상점 공격 종류
- 방화 (100,000BN) - 상품 30% 손실
- 수해 (80,000BN) - 상품 20% 손실  
- 강도 (150,000BN) - 상품 10% + 현금 20%
- 정전 (50,000BN) - 효율만 감소
- 진상고객 (70,000BN) - 상품 15% + 현금 5%

### 화폐
- `BN` (삥): 주 화폐
- `포인트`: 보조 화폐

### 조이몬 종족
- 키유 (B-612 행성), 피유 (견우성), 치유 (말머리 성운)

### 매크로 감지 시스템
```
감지 대상: TeamViewer, AnyDesk, RustDesk, NomMachine, LogMeIn, Parsec
         TigerVNC, TurboVNC, x11vnc, WinVNC, UltraVNC
         Wacom, Huion, XP-Pen, Pentablet
감지 방식: INJECTED 플래그, 마우스 이동 패턴, 클릭 자동화
```

---

## 7. 파일 경로 (복호화 확인)

```
Res\Lst\item.mst          → 아이템 텍스트 DB
Res\Lst\item_hc.mst       → HC 아이템 텍스트 DB
Street\C\chr.gpc          → 캐릭터 스프라이트 정의
Street\C\chr_hc.gpc       → HC 캐릭터 스프라이트
Street\J\cjm.gpj          → 조인트/파티클
Street\I\a.gpi ~ z.gpi    → 인벤토리 아이템 정의
Street\M\_\O\             → 맵 오브젝트
Street\M\_\T\             → 맵 타일
Street\M\_\tile.lst       → 타일 목록
Street\M\_\obj.lst        → 오브젝트 목록
Street\M\A\obj.gpd        → 맵 오브젝트 배치
Street\M\A\tile.gpd       → 맵 타일 배치
etc\grade{N}.png          → 등급 이미지
chr\chr{0:D5}             → 캐릭터 파일 (5자리 번호)
eft\eft{0:D5}             → 이펙트 파일
{경로}\{카테고리}\{코드}{번호:D5}.irs  → IRS 포맷
```

---

## 8. Phase 2를 위한 핵심 발견

### IRS 파서 구현 힌트
```
헤더 매직: "Resource File\0" (확인됨)
포맷 상수: _2049() = 'Resource File\x00'
```

### JCR 파서 구현 힌트
```
헤더 매직: "Joycity #$@(RAW! #!#(!# #!TS" (확인됨)
포맷 상수: _204A() = 'Joycity #$@(RAW! #!#(!# #!TS'
```

### RMM 파서 구현 힌트
```
헤더: "RedMoon MapData 1.0" (확인됨)
타일 파일: tile.gpd, tile.lst
오브젝트 파일: obj.gpd, obj.lst
맵 경로: Street\M\{MapId}\
```

### MST 파서 (이미 Python 구현 완료)
```
헤더: "JcMsgList Table"
구분자: ';' (이름, 설명 등 분리)
인코딩: UTF-8 (구버전은 EUC-KR)
```

---

## 9. 서버 에뮬레이터 구현 가이드

### 필요한 서버 컴포넌트
1. **TCP 서버 포트 7945**: 메인 게임 (이동, 아이템, 상점 등)
2. **TCP 서버 포트 7942**: 채팅/API
3. **UDP 서버 포트 7946**: 음성채팅 (Opus 릴레이)
4. **HTTP 서버**: PHP API 에뮬레이션

### 패킷 포맷 추정 (Wireshark 검증 필요)
```json
// 추정 클라이언트→서버 패킷
{
  "type": "move",
  "posX": 100,
  "posY": 200,
  "mapId": "A",
  "userNo": 12345
}

// 추정 서버→클라이언트 패킷
{
  "type": "gameObjects",
  "data": [...]
}
```

### 웹 로그인 흐름
1. 클라이언트 → `GET /bbs/login_check.php?pcode={userid}&pw={userpw}`
2. 서버 → JSON 응답 (token 포함)
3. 클라이언트 → TCP:7945 에 token 전송
4. 서버 → 게임 세션 시작

---

## 10. 다음 단계

### Phase 2 (파일 포맷 파서) 우선순위
1. `mst_parser.py` - 구조 100% 파악, 즉시 구현 가능
2. `irs_parser.py` - 헤더 구조 파악, 내부 압축 추가 분석 필요
3. `rmm_parser.py` - tile.gpd, obj.gpd 파싱 코드 DLL에서 추출 가능
4. `jcr_parser.py` - 압축 알고리즘은 DLL의 실제 로더 코드 분석 필요

### Phase 3 (네트워크) 준비
- **서버 주소**: `jc.joy-june.com` 포트 7942, 7945, 7946
- **Wireshark 필터**: `host jc.joy-june.com`
- **패킷 형식**: JSON (추정, Wireshark로 확인)
