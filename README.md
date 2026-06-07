# 이실장 원룸 매물 광고 등록 봇

`mamuls.csv`의 각 행을 읽어 이실장(AIPartner) 원룸 광고 등록 폼을
Playwright로 입력하는 Python 3.11+ CLI 프로그램입니다. 내부 API를 직접
호출하지 않고 브라우저의 DOM selector, text, role, label만 사용합니다.

기본 실행 모드는 **dry-run**입니다. 모든 값을 입력하고 최종 `광고하기`
버튼이 활성화된 것을 확인한 뒤 스크린샷을 남기며, 버튼은 누르지 않습니다.
`--submit`을 명시한 경우에만 실제 등록을 시도합니다.

## 구조

```text
realestate_bot/
  main.py
  requirements.txt
  README.md
  .env.example
  config.json
  mamuls.example.csv
  src/
    __init__.py
    browser.py
    login.py
    popup.py
    aipartner_oneroom.py
    csv_loader.py
    logger.py
    selectors.py
  logs/
    .gitkeep
  screenshots/
    .gitkeep
```

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## 로그인 설정

```bash
cp .env.example .env
```

`.env`에 실제 계정을 입력합니다.

```dotenv
AIPARTNER_ID=아이디
AIPARTNER_PW=비밀번호
```

`.env`는 저장소에 커밋하지 마세요. `config.json`의
`browser.user_data_dir`에 로그인 세션이 저장됩니다.

## CSV

```text
platform,property_type,deal_type,sido,sigungu,eupmyeon_dong,ri,jibun,building_dong,detail_addr,deposit,monthly_rent,maintenance_fee,exclusive_area_m2,supply_area_m2,floor,total_floor,room_count,bath_count,direction,direction_basis,parking,move_in_date,title,memo,option_aircon,option_life,option_security,option_etc,photo_folder
```

- `platform`: `aipartner`
- `property_type`: `oneroom` 또는 `원룸`
- `deal_type`: `monthly`, `월세`, `jeonse`, `전세`, `sale`, `매매`,
  `short`, `단기임대`
- 가격 단위는 만원입니다.
- `maintenance_fee`도 기본적으로 만원 단위이며, `config.json`의
  `maintenance_fee_multiplier`로 변경할 수 있습니다.
- `move_in_date`: `즉시입주` 또는 `YYYY-MM-DD`
- `building_dong`: 집합건물의 동 정보입니다. 예: `101동`. 일반 건물은
  빈 값으로 둡니다.
- `direction`: `동향`, `서향`, `남향`, `북향`, `남동향` 등
- `direction_basis`: `거실` 또는 `안방`
- `parking`: `Y/N`, `TRUE/FALSE`, `가능/불가능`
- 동 주소는 `eupmyeon_dong=무거동`, `ri`는 빈 값으로 둡니다.
  예: `울산,남구,무거동,,345`. 이 경우 리 선택을 건너뛰고 `345`를
  본번에 입력합니다.
- 리 주소는 `eupmyeon_dong=온산읍`, `ri=덕신리`처럼 둘 다 입력합니다.
- 옵션은 사이트 표시명 그대로 `|`로 구분합니다.
- `option_etc`: `엘리베이터|화재경보기|테라스|베란다|마당|무인택배함`
- `option_aircon=TRUE`이면 `config.json`의 `default_aircon`을 선택합니다.
- `photo_folder`는 CSV 기준이 아니라 실행 디렉터리 기준 상대경로 또는
  절대경로입니다. jpg, jpeg, png, gif를 이름순으로 최대 20장 올립니다.
- 사진 폴더가 없거나 비어 있으면 기본적으로 경고 후 계속합니다.
  이를 실패로 처리하려면 `config.json`의 `fail_on_missing_folder` 또는
  `fail_on_empty_folder`를 `true`로 설정합니다.

기존 CSV처럼 맨 앞에 빈 인덱스 컬럼이 있어도 무시합니다.
`exclusive_area_m2`가 없으면 호환을 위해 `supply_area_m2` 값을 사용하고
실행 시 경고합니다.

## 실행

기본 dry-run:

```bash
python main.py --csv mamuls.csv --dry-run
```

`--dry-run`을 생략해도 같은 안전 모드입니다.

```bash
python main.py --csv mamuls.csv
```

실제 등록:

```bash
python main.py --csv mamuls.csv --submit
```

첫 데이터 행만 시험:

```bash
python main.py --csv mamuls.csv --row 1 --dry-run
```

dry-run 완료 후 브라우저는 자동으로 닫히지 않습니다. 화면에서 사진을
추가하거나 값을 수정하고, 검토가 끝나면 브라우저 창을 직접 닫으세요.
자동 테스트처럼 즉시 종료해야 할 때만 다음 옵션을 사용합니다.

```bash
python main.py --csv mamuls.csv --row 1 --dry-run --close-on-finish
```

## 처리 방식

1. 등록 페이지 접속 및 로그인
   - 첫 창에서 로그인한 세션을 모든 행별 창이 공유합니다.
   - 새 창에서 세션이 만료되어 로그인 화면이 보이면 자동으로 다시
     로그인합니다.
2. `오늘 하루 보지 않기` 또는 닫기 팝업 처리
3. `다른 매물 등록`과 원룸 유형 선택
4. 주소 입력 후 `주소확인(필수)` 실행
5. `건축물대장 불러오기`에서 건물 유형을 확인해 상세항목을 적용
   - 집합건물: CSV `building_dong`과 일치하는 동을 선택하고
     `detail_addr`와 일치하는 호실 적용
   - 일반 건물: CSV `floor`와 일치하는 층 적용
   - 사이트 유형 정보가 없으면 `building_dong`이 있으면 집합건물,
     비어 있으면 일반 건물로 판단
6. 건축물대장 반영 후 상세주소와 가격, 면적, 층, 방향 등 CSV 값을
   다시 입력하여 CSV 값을 최종값으로 사용
7. 옵션 선택과 사진 업로드
8. `offeringsGbn=OR`, 거래 유형 hidden value 등 내부 값 검증
9. dry-run이면 저장 직전 스크린샷 후 다음 행으로 이동
10. `--submit`이면 `광고하기` 클릭

건축물대장에 CSV 동·호실 또는 층수와 일치하는 항목이 없으면 다른
항목을 임의로 선택하지 않고 해당 행을 실패로 기록합니다.

행 하나가 실패해도 다음 행을 계속 처리합니다.

`--row`를 지정하지 않으면 CSV의 데이터 행마다 독립된 Chromium 창을
하나씩 엽니다. 각 창은 해당 행의 저장 직전 상태를 유지하므로 서로 다른
매물을 동시에 검토하거나 사진을 추가할 수 있습니다. 모든 창을 직접
닫으면 프로그램이 종료됩니다. 로그인 쿠키는 `browser.user_data_dir`의
영구 프로필과 그 안의 `storage_state.json`에 저장되므로 다음 실행에서도
재사용됩니다. 사이트가 서버에서 세션을 만료시킨 경우에만 `.env`
계정으로 다시 로그인합니다.

## 결과 로그

`logs/result.csv`에 다음 값이 누적됩니다.

```text
processed_at,source_row,status,mode,title,address,current_url,error_message,screenshot_path
```

- dry-run 준비 완료: `dry_run_ready`
- 실제 등록 완료: `success`
- 실패: `failed`

실패 시 현재 URL, 예외 메시지, 전체 페이지 스크린샷 경로를 기록합니다.

## 주의

- 사이트 UI나 필수 입력 정책이 바뀌면 `src/selectors.py`와
  `src/aipartner_oneroom.py`의 selector를 조정해야 할 수 있습니다.
- 관리비는 2023년 이후 세부 입력이 필수입니다. 현재 기본값은
  `기타부과`, `직전월 관리비`, `정액관리비가 10만원 미만인 경우`입니다.
- 실제 등록 전에는 반드시 한 행을 `--dry-run --row 1`로 검토하세요.
- CAPTCHA나 추가 본인인증이 표시되면 자동 우회하지 않습니다.
