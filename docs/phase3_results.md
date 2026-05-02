# Phase 3 결과: 네트워크 프로토콜 분석

> 완료일: 2026-04-19  
> 도구: ilspycmd 역분석 + Python 문자열 복호화  
> 복호화된 문자열 수: 2698개 (XOR key: `byte ^ position ^ 0xAA`)

---

## 1. 네트워크 아키텍처

```
클라이언트 ─── TCP 7942/7945 ───► 서버  (JSON 라인 + 바이너리 게임 프레임)
클라이언트 ─── UDP 7946       ───► 서버  (Opus 음성, 48kHz mono)
```

### TCP 프레임 구조

```
[u32 length LE][payload]           ← 외부 envelope
payload[0] 타입:
  1  → JSON 텍스트 프레임: [u8=1][i16 json_len][UTF-8 JSON \n]
  3  → keepalive (1바이트)
  5  → 바이너리 게임 패킷: [u8=5][payload...]
  6  → 음성 제어: [flag][message]
```

### 바이너리 게임 패킷 헤더 (type=5 페이로드)

```
[u16 seq_num LE]         ← 자동증가 시퀀스
[u8  type_name_len]
[bytes type_name]        ← ASCII 패킷 타입 이름
[... payload ...]
```

### JSON 패킷 구조 (포트 7942/7945)

```json
{ "type": "<packet_type>", "field1": "value1", ... }
```

- 송신: `Dictionary<string, string>` → `JavaScriptEncoder(BasicLatin + HangulSyllables)` → JSON  
- 수신: `StreamReader.ReadLineAsync()` → `JsonDocument.Parse()` → `"type"` 필드로 dispatch

---

## 2. 문자열 복호화

### XOR 알고리즘 (Phase 1과 동일)

```python
blob_decrypted[p] = blob_raw[p] ^ p ^ 0xAA
string = blob_decrypted[offset:offset+length].decode('utf-8')
```

- 블롭 크기: 42,797 bytes (`_4` 배열)
- 캐시 배열: `string[2698]` (`_5`)
- 접근 함수: `_6(idx, offset, len)` = `Encoding.UTF8.GetString(_4, offset, len)` (복호화 후)
- 접근자 메서드: `_XXXX_YYYY()` → `_5[N] ?? _6(N, offset, len)`

---

## 3. 인바운드 패킷 (서버 → 클라이언트): 131개

### 핵심 게임 패킷

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `login` | `_2007` | 로그인 성공 → 게임 화면 표시 (1024×790), `myId` 저장 |
| `loginQueue` | `_2008` | 대기열 위치 (`position`, `retryAfter`) |
| `obj` | `_2025` | 게임 오브젝트 일괄 동기화 (`gameObjects: ConcurrentDict<long,GameObject>`) |
| `objc` | `_202A` | 게임 오브젝트 추가 |
| `remove` | `_2064` | 오브젝트 제거 |
| `move` | `_2062` | 이동 업데이트: `no`(id), `VX`, `VY`, `TX`, `TY` |
| `delta` | `_202B` | 임의 필드 reflection 업데이트 |
| `map` | `_2027` | 방/맵 퇴장 처리 |
| `motion` | `_2003` | 이동 취소/리셋 |
| `motion2` | `_2004` | 위치 업데이트: `ox`, `oy`, `idxs` |
| `state` | `_2005` | 상태 업데이트: `stateIdx`, `stateIdxs` |

### 채팅 패킷

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `chat` | `_00A0` | 채팅: `id`(long), `text` → `gameObject.Chat` |
| `typing` | `_1680` | 타이핑 시작 → `gameObject.TypingText = "..."` |
| `stopTyping` | `_2000` | 타이핑 중지 |
| `streamChat` | `_2001` | 타이핑 중 텍스트 미리보기: `text`, `time` |
| `message` | `_2002` | 시스템 메시지/공지 |
| `alert` | `_2009` | 컬러 채팅: `color`(hex), `text` |
| `newMessage` | `_206B` | 새 DM 알림 |
| `conversationList` | `_206C` | 대화 목록 |
| `messageHistory` | `_206D` | 메시지 내역 |
| `unreadMessages` | `_206E` | 읽지 않은 메시지 수 |

### 인증/세션

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `webtoken` | `_1680_2055` | 인증 토큰: `token` → 브라우저로 `/bbs/login_check.php?pcode=TOKEN` 열기 |
| `messagebox` | `_2024` | 로그인 버튼 재활성화 (로그인 실패 응답) |

### 경제/아이템

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `bn` | `_2011` | 코인/재화 업데이트 |
| `hp` | `_2012` | HP 업데이트 |
| `exp` | `_2015` | 경험치 업데이트 |
| `expGain` | `_2022` | 다른 플레이어에게 코인 지급 |
| `refresh` | `_202C` | 아이템 목록 동기화: `items: Dict<int, GameItem>` |
| `saleShow` | `_202D` | 판매 아이템 목록: `Dict<int, GameSaleItem>` |
| `info` | `_2014` | 경품/수상 정보 (AwardData list) |

### UI/윈도우

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `apart` | `_202E` | 아파트/의상 창 표시 |
| `clubMake` | `_202F` | 클럽 창 표시 |
| `magic` | `_2047` | 설정 창 표시 |
| `profile` | `_2048` | 거래/프로필 창: name, description, price, AwardData |
| `avatar` | `_2013` | `_205B` 폼 표시 |
| `skillList` | `_2035` | 위젯+애니메이션 표시 |
| `joymonInfo` | `_2049` | 조이몬 스탯: 14+ 수치 필드 |
| `joymonInventory` | `_204A` | 조이몬 장비 초기화 |
| `joymonShop` | `_204E` | 로딩 오버레이 표시 |
| `music` | `_2010` | 게임 상태/맵 변경 |
| `music_broadcast` | `_200A` | 방 상태 플래그 |
| `flash` | `_200B` | 작업표시줄 창 깜박임 |

### 교류/소셜

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `friends` | `_2032` | 친구 목록: `[{name, online}]` |
| `newFriends` | `_2054` | 친구 요청 |
| `exchange` | `_2053` | 교환 제안 |
| `exchangeClose` | `_2055` | 교환 창 닫기 |
| `exchange2` | `_2056` | 교환 창 열기 |
| `exchangeUp` | `_2057` | 교환 아이템 슬롯 업데이트 |
| `workList` | `_2059` | 직업 목록: `[{workId, exp, expMax, level}]` |
| `familyData` | `_1680_2003` | 가족 데이터 |
| `familyRequest` | `_1680_2004` | 가족 요청 |
| `household` | `_1680_2005` | 가구/세대 정보 |

### 상점 시스템

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `shopClose` | `_1680_2014` | 상점 닫기 |
| `openShopManage` | `_1680_2015` | 상점 관리 창 |
| `myShopInfo` | `_1680_2022` | 내 상점 정보 |
| `shopZoneList` | `_1680_2024` | 상점 구역 목록 |
| `wholesaleItems` | `_1680_2027` | 도매 상품 목록 |
| `shopProfit` | `_1680_2029` | 상점 수익 |
| `shopError` | `_1680_202D` | 상점 오류 |
| `visitShopInfo` | `_1680_202C` | 방문 상점 정보 |
| `shopAdminPanel` | `_1680_204F` | 상점 관리자 패널 |
| `salesHistory` | `_1680_202B` | 판매 내역 |

### 클럽/길드

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `clubManager` | `_1680_2008` | 클럽 관리자 정보 |
| `myClubs` | `_1680_2009` | 내 클럽 목록 |
| `publicClubs` | `_1680_200B` | 공개 클럽 목록 |
| `roomMembers` | `_3000` | 방 멤버 목록 |
| `myRoomList` | `_206F` | 내 방 목록 |
| `groupMessage` | `_1680_00A0` | 그룹 메시지 |

### 전투/경쟁

| JSON `"type"` | 핸들러 | 기능 |
|---|---|---|
| `allShopsForAttack` | `_1680_2035` | 공격 가능한 상점 목록 |
| `defenseStatus` | `_1680_2033` | 방어 상태 |
| `attackResult` | `_1680_203E` | 공격 결과 |
| `shieldResult` | `_1680_2047` | 방어막 결과 |
| `shopAttacked` | `_1680_2049` | 상점 공격받음 알림 |

### 무시 패킷 (HashSet, 처리 없음)

```
shopCreateResult      shopCloseResult       shopExtendResult
shopDepositResult     shopWithdrawResult    shopToggleOpenResult
wholesalePurchaseResult  productPriceResult  productSlotResult
productRemoveResult   hireNpcResult         fireNpcResult
setNpcPositionResult  giveNpcSnackResult    giveNpcDrinkResult
sendNpcVacationResult buyFromShopResult     shopQuestCancel
shopQuestGenerate
```

---

## 4. 아웃바운드 패킷 (클라이언트 → 서버): 188개

### 인증

```json
{ "type": "login",      "version": "<ver>", "userid": "<id>", "userpw": "<pw>" }
{ "type": "loginRetry", "version": "<ver>", "userid": "<id>", "userpw": "<pw>", "X": "<x>", "Y": "<y>" }
{ "type": "webtoken" }    // 브라우저 로그인 요청
{ "type": "ping" }        // keepalive (별도 TCP keepalive와 다름)
{ "type": "exit" }        // 연결 종료
```

### 이동/동작

```json
{ "type": "move",     "no": "<id>", "TX": "<tx>", "TY": "<ty>" }
{ "type": "myState",  "LocationX": "<x>", "LocationY": "<y>", "motion": "<idx>" }
{ "type": "myState2" }
{ "type": "motion",   "motion": "<idx>", "sound": "<snd>" }
{ "type": "action",   "no": "<item_no>" }
{ "type": "map",      ... }           // 맵 이동
{ "type": "bus" }                     // 버스 탑승
```

### 채팅/소통

```json
{ "type": "chat",       "text": "<message>" }
{ "type": "typing" }
{ "type": "stopTyping" }
{ "type": "sendMessage",  "to": "<id>", "text": "<msg>" }
{ "type": "sendGroupMessage", "roomId": "<id>", "text": "<msg>" }
{ "type": "memo",        ... }
{ "type": "report",      ... }
```

### 아이템/인벤토리

```json
{ "type": "itemGet",      "no": "<item_no>" }
{ "type": "itemDrop",     "no": "<item_no>" }
{ "type": "itemMove",     "no": "<item_no>", ... }
{ "type": "itemRotation", "no": "<item_no>" }
{ "type": "itemEat",      "no": "<item_no>" }
{ "type": "invenMove",    ... }
{ "type": "buyItem",      ... }
{ "type": "storageGet" / "storagePut" / "storageSwap" / "storageOpen" }
```

### 소셜

```json
{ "type": "friendsAdd" / "friendsDel" / "friendsAgree" / "friendsList" }
{ "type": "profile",    "no": "<id>" }
{ "type": "rightClick", ... }
{ "type": "clickEvent", "click": "<event>", "saleId": "<id>" }
{ "type": "recallFriend", ... }
{ "type": "praise",      ... }
{ "type": "setSpouse" / "removeSpouse" }
{ "type": "addChild" / "removeChild" }
```

### 교환/거래

```json
{ "type": "exchange",       "no": "<id>" }
{ "type": "exchange2" }
{ "type": "exchangeMoney",  "money": "<amount>" }
{ "type": "exchangeUp",     ... }
{ "type": "exchangeFinish" }
{ "type": "resell",         ... }
{ "type": "resellClose" }
{ "type": "resellFinish" }
```

### 상점

```json
{ "type": "createShop" / "closeShop" / "toggleShopOpen" }
{ "type": "depositToShop" / "withdrawFromShop" }
{ "type": "visitShop",      ... }
{ "type": "buyFromShop",    ... }
{ "type": "shopUpdatePrice" / "shopUpdateStock" }
{ "type": "getMyShop" / "getShopZones" }
{ "type": "getWholesaleItems", ... }
{ "type": "purchaseWholesale", ... }
{ "type": "saleUp" / "saleState" }
{ "type": "userSaleUp",    ... }
{ "type": "setProductPrice" / "setProductSlot" }
```

### 전투

```json
{ "type": "attackShop",     ... }
{ "type": "getAllShopsForAttack" }
{ "type": "getDefenseStatus" }
{ "type": "activateShield" / "activateReflection" / "activateReinforcedShield" }
{ "type": "repairDamage",   ... }
{ "type": "getCompetitionInfo" }
```

### 클럽/방

```json
{ "type": "clubMake",         "title": "<name>" }
{ "type": "clubSelect",       "title": "<name>" }
{ "type": "clubEnterByName",  "name": "<name>" }
{ "type": "clubMove",         "no": "<room>" }
{ "type": "createRoom",       ... }
{ "type": "joinRoom" / "leaveRoom" / "inviteToRoom" / "deleteRoom" }
{ "type": "getRoomMembers",   ... }
{ "type": "getMyRooms" }
```

### 아바타/조이몬

```json
{ "type": "avatarMake",         "no": "<id>" }
{ "type": "joymonBuy" / "joymonEat" / "joymonEquip" / "joymonUnequip" }
{ "type": "joymonInfo" / "joymonInventory" / "joymonInventoryGet" }
{ "type": "joymonInventoryPut" / "joymonInventorySwap" / "joymonOutdoor" }
{ "type": "reColor",            ... }
```

### 부동산/아파트

```json
{ "type": "apartmentBuy",      "no": "<id>" }
{ "type": "apartmentUpgrade",  "no": "<id>" }
{ "type": "apartmentMove" }
{ "type": "apartmentBell",     "no": "<id>" }
{ "type": "apartmentBellAgree", ... }
{ "type": "villaBuyAgree",     ... }
```

### 직업/작업

```json
{ "type": "getWork",          "num": "<n>" }
{ "type": "workList" / "workStart" / "workClose" / "workOk" / "workUp" }
{ "type": "changeWork",       ... }
{ "type": "refinementStart" / "refinementUp" / "refinementWork" / "refinementCancel" / "refinementClose" }
```

### 기타

```json
{ "type": "skillList" }
{ "type": "useSkill",    ... }
{ "type": "useEnergyDrink" }
{ "type": "viewerHeartbeat" }
{ "type": "getOptions" / "setOption",  ... }
{ "type": "getMemo" / "memoResponse" }
{ "type": "getMessages" / "deleteMessage" / "deleteConversation" }
{ "type": "forceGenerateQuest" / "completeQuest" / "cancelQuest" }
{ "type": "startPromotion" / "cancelPromotion" }
{ "type": "upgradeShopGrade" }
{ "type": "shopAdminRequest" }
{ "type": "disposeExpired" }
{ "type": "manualRestock" }
{ "type": "leaveFamily" / "buyFamilyRoom" }
{ "type": "richvilleTradeAccept" / "richvilleTradeDecline" / "richvilleTradeInput" }
{ "type": "visitOutskirts",  ... }
{ "type": "rideResponse" / "tentResponse" }
{ "type": "hireNpc" / "fireNpc" / "trainNpc" / "setNpcPosition" }
{ "type": "giveNpcSnack" / "giveNpcDrink" / "sendNpcVacation" }
```

---

## 5. 인증 플로우

```
1. Client → Server (TCP):
   {"type":"login","version":"2.X.X","userid":"아이디","userpw":"비번"}

2. Server → Client (조건):
   {"type":"loginQueue","position":3,"retryAfter":5000}   ← 대기열
   OR
   {"type":"webtoken","token":"XXXX"}                      ← 브라우저 인증 필요

3. webtoken 수신 시:
   Client opens: https://jc.joy-june.com/bbs/login_check.php?pcode=XXXX

4. Server → Client (로그인 성공):
   {"type":"login","myId":12345678,"isAdmin":"0"}
   → 게임 화면 표시 (1024×790)

5. 이후:
   {"type":"obj","gameObjects":{...}}    ← 초기 오브젝트 동기화
   {"type":"refresh","items":{...}}      ← 인벤토리 동기화
```

---

## 6. move 패킷 필드 맵 (GameObject ↔ JSON)

```
GameObject 필드  | JSON 키  | 방향       | 의미
─────────────────┼──────────┼────────────┼──────────────────
OX, OY           | ox, oy   | S←C / S→C  | 현재 위치 (origin)
TX, TY           | TX, TY   | S←C        | 목표 위치 (target)
VX, VY           | VX, VY   | S→C        | 검증된 위치
SX, SY           | -        | 내부 전용   | 이동 속도
PX, PY           | -        | 내부 전용   | 진행 오프셋
no / id          | no       | 양방향     | 오브젝트 ID (long)
stateIdx         | stateIdx | S→C        | 상태 인덱스
type             | type     | S→C        | 오브젝트 타입
name             | name     | S→C        | 이름 (string)
Chat             | text     | S→C        | 채팅 텍스트
chatColor        | color    | S→C        | 채팅 색상 (#RRGGBB)
```

---

## 7. 서버 URL 목록 (복호화됨)

```
https://jc.joy-june.com/joytalk/update/manifest.json    ← 자동 업데이트
http://jc.joy-june.com/joytalk/server_status.php         ← 서버 상태 체크
http://jc.joy-june.com/joycityw/joytalk_notice.php       ← 공지사항
http://jc.joy-june.com/joytalk2.php?version=             ← 버전 체크
https://jc.joy-june.com/joytalk/map/?Id=                 ← 맵 URL
https://jc.joy-june.com/bbs/board.php?bo_table=jc_notice ← 공지 게시판
https://jc.joy-june.com/bbs/register.php                 ← 회원가입
https://jc.joy-june.com/bbs/login_check.php?pcode=       ← 웹토큰 인증
http://jc.joy-june.com/joytalk/skill/                    ← 스킬 리소스
http://jc.joy-june.com/joytalk/award/                    ← 경품 리소스
```

---

## 8. Phase 4 준비

### 즉시 가능한 작업

| 작업 | 방법 |
|------|------|
| 실시간 패킷 캡처 | Wireshark + `host jc.joy-june.com and tcp port 7945` |
| JSON 패킷 인터셉트 | `mitmproxy` → TCP 7942 프록시 |
| 패킷 재생 도구 | Python `socket` + JSON 직렬화 |
| 패킷 필드 상세 문서화 | `wireshark_capture.py` 작성 |

### 에뮬레이터 구현 순서

1. **TCP 서버 (`asyncio`)**: 포트 7942/7945 리슨
2. **로그인 핸들러**: `login` 패킷 수신 → `webtoken` + `login` 응답
3. **맵 동기화**: `obj` + `refresh` 전송
4. **move 핸들러**: `move` 수신 → 브로드캐스트
5. **채팅 핸들러**: `chat` 수신 → 브로드캐스트
6. **바이너리 프로토콜**: type=5 패킷 파싱

### 패킷 캡처 명령

```bash
# Wireshark
sudo tcpdump -i any -w joytalk.pcap host jc.joy-june.com

# 포트별
sudo tcpdump -i any -w chat.pcap   host jc.joy-june.com and tcp port 7942
sudo tcpdump -i any -w game.pcap   host jc.joy-june.com and tcp port 7945
sudo tcpdump -i any -w voice.pcap  host jc.joy-june.com and udp port 7946
```
