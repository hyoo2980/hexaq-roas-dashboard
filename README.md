# 헥사큐아쿠아메딘 ROAS 디스코드 봇

메타(Meta) 광고계정 + 카페24 자사몰 + 쿠팡 매출을 합산해 ROAS를 계산하고, 디스코드
웹훅으로 일일 리포트를 보내는 봇입니다. ("알파셀올나잇세이프" 프로젝트의 ROAS 리포트
기능 중 Meta + Cafe24 + 쿠팡 부분을 가져온 축소판입니다.)

## 1. 설치

```
pip install -r requirements.txt
```

## 2. `.env` 채우기

`.env` 파일이 이미 생성되어 있습니다. 아래 값들을 채워주세요.

### 디스코드 웹훅 (`DISCORD_WEBHOOK_URL`)
1. 알림을 받을 디스코드 서버에서 채널 설정 → 연동 → 웹훅 → "새 웹훅" 생성
2. "웹훅 URL 복사" → `.env`의 `DISCORD_WEBHOOK_URL=`에 붙여넣기

### 메타(Meta) 광고 API
1. https://developers.facebook.com 에서 앱 생성 (또는 기존 앱 사용)
2. Marketing API 권한 추가, 광고계정에 접근 가능한 **access token** 발급
   (Graph API Explorer에서 단기 토큰을 받거나, 시스템 사용자로 장기 토큰 발급 권장)
3. `META_ACCESS_TOKEN` 에 토큰 입력
4. 광고관리자(Ads Manager)에서 계정 ID 확인 (`act_숫자` 형식) → `META_AD_ACCOUNT_ID`
   에 입력. 여러 계정이면 `META_EXTRA_AD_ACCOUNT_IDS`에 쉼표로 추가.

### 카페24(Cafe24) API
1. https://developers.cafe24.com 에서 앱 등록 (Mall ID 필요)
2. `CAFE24_CLIENT_ID`, `CAFE24_CLIENT_SECRET`, `CAFE24_MALL_ID`, `CAFE24_REDIRECT_URI` 입력
3. OAuth 인증 플로우(최초 1회, 브라우저에서 권한 동의)로 `refresh_token`을 발급받아
   `CAFE24_REFRESH_TOKEN`에 입력. 이후 토큰은 코드가 자동으로 갱신/저장합니다.
4. 특정 상품만 매출에 포함하고 싶다면 `CAFE24_TARGET_KEYWORD`에 상품명에 포함된
   키워드를 입력 (비워두면 전체 주문을 집계).

### 쿠팡(Coupang) Wing API
1. 쿠팡 Wing(판매자) 계정 → 오픈API 메뉴에서 **Access Key / Secret Key** 발급
2. `COUPANG_ACCESS_KEY`, `COUPANG_SECRET_KEY` 입력
3. 업체코드(Vendor ID, `A00012345` 형식)를 `COUPANG_VENDOR_ID`에 입력
4. 같은 쿠팡 판매자 계정에서 다른 상품도 함께 팔고 있다면 `COUPANG_TARGET_KEYWORD`에
   상품명에 포함된 키워드(예: "헥사큐")를 입력해 헥사큐아쿠아메딘 매출만 집계. 이
   계정에서 헥사큐아쿠아메딘만 판매한다면 비워둬도 됩니다.

### 손익 추정 (선택)
- `BEP_ROAS`에 손익분기 ROAS를 입력하면 리포트에 추정 순이익이 함께 표시됩니다.
  비워두면 순이익 추정 없이 ROAS만 표시됩니다.

## 3. 실행

특정 날짜 하루치 수집 + 리포트 발송:
```
python collect_meta_range.py 2026-06-27 2026-06-27
python collect_cafe24_range.py 2026-06-27 2026-06-27
python collect_coupang_range.py 2026-06-27 2026-06-27
```

전날 데이터 수집 + 디스코드 리포트 발송까지 한 번에:
```
python daily_pipeline.py
```

매일 자동 실행하려면 Windows 작업 스케줄러에 `python daily_pipeline.py`를 등록하세요.

## 구조

```
config.py              환경변수 로드
collectors/meta.py       메타 광고 인사이트 수집
collectors/cafe24.py     카페24 주문/환불 수집
collectors/coupang.py    쿠팡 주문 수집
storage/db.py             SQLite 저장 (data/roas.db)
analysis/roas.py          ROAS 계산
notify/discord.py         디스코드 리포트 포맷 + 발송
collect_meta_range.py     메타 데이터 수집 스크립트
collect_cafe24_range.py   카페24 데이터 수집 스크립트
collect_coupang_range.py  쿠팡 데이터 수집 스크립트
daily_pipeline.py         수집 + 리포트 발송 통합 실행
```
