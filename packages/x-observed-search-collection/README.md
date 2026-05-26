# X.com Observed Search Collection Manual

이 문서는 집이나 개인 환경에서 X.com 공개 검색 화면에 노출되는 포스트를 다른 주제로 수집할 때 쓰는 운영 매뉴얼이다.

중요한 전제: 이 방식은 X API full archive 수집이 아니다. 브라우저로 X.com 검색 결과에 실제 노출된 공개 포스트를 작은 날짜 구간으로 저장하는 방식이다. 따라서 보고서에서는 항상 `Observed X.com public searchable posts`, `관측된 X.com 공개 검색 결과`처럼 표현하고, `전체 트윗`, `전체 언급량`, `complete archive`라고 쓰지 않는다.

## 언제 쓰는가

- 공식 X full archive API를 쓸 수 없지만 특정 주제의 공개 반응 흐름을 관측하고 싶을 때.
- 일별 추이, 키워드별 관측량, 대표 포스트, 감성/유형 분류 후보를 만들고 싶을 때.
- 과거 구간을 완전 복원하는 목적이 아니라, 현재 검색 화면에서 다시 노출되는 공개 포스트를 최대한 체계적으로 모으고 싶을 때.

쓰면 안 되는 경우:

- 법무/정산/계약처럼 전체 모집단이 필요한 분석.
- 비공개 계정, 로그인 뒤 개인화 영역, 개인 식별정보를 대량 저장하는 작업.
- X의 이용약관이나 대상 사이트의 접근 제한을 우회해야 하는 작업.

## 핵심 원칙

1. 날짜 구간은 작게 자른다. 백필은 기본 1일 window를 권장한다.
2. 검색어는 여러 변형을 쓴다. 해시태그, 띄어쓰기, 대소문자, 공식명/약칭을 분리한다.
3. 결과는 `tweet_url` 기준으로 dedupe한다.
4. 0건 또는 비정상적으로 적은 날짜는 재검색한다.
5. raw 수집과 AI 분석/업로드를 분리한다.
6. 모든 산출물은 manifest와 함께 남긴다.
7. 보고서에는 항상 관측 한계를 명시한다.

## 시작 전 결정할 것

아무것도 없는 상태라면 먼저 아래 네 가지를 정한다.

| item | decision |
|---|---|
| 수집 주제 | 게임명, 브랜드명, 이벤트명, 인물명 등 |
| 수집 기간 | `YYYY-MM-DD` 기준 시작일/종료일 |
| 검색어 세트 | core query와 expanded query를 분리 |
| 저장 위치 | 개인 PC의 로컬 프로젝트 폴더 |

예:

```text
topic: Example Game
period: 2026-01-01 ~ 2026-01-31
core queries: "#ExampleGame", "Example Game", "ExampleGame"
expanded queries: "example game", "EXAMPLE GAME", "Studio ExampleGame"
output root: C:\Users\<you>\project_repo\x_observed_example_game
```

## 준비물

- Python 3.11+ 권장.
- Chrome 또는 Chromium.
- Playwright.
- 수집 전용 X 계정. 브라우저 프로필에 로그인 세션을 저장해 두는 방식 권장.
- 로컬 저장 폴더. 예: `reports/operations/x_topic_collect_<date>/`.

민감정보는 repo에 커밋하지 않는다. API 키, X 계정 정보, DB 토큰은 `.env` 또는 OS 환경변수로만 둔다.

## 포함된 최소 CLI

이 패키지는 운영 매뉴얼과 함께 POC용 최소 수집 CLI를 포함한다.

| path | role |
|---|---|
| `scripts/x_observed_search_collect.py` | X.com 공개 검색 화면 관측 수집 및 fixture/dry-run 산출물 생성 |
| `queries/japan-tourism-ja.txt` | 일본어 한국 관광 POC query seed |
| `tests/fixtures/japan_tourism_observed_fixture.csv` | dedupe/manifest/gap check 검증용 공개 fixture |
| `tests/test_x_observed_search_collect.py` | fixture mode smoke test |

CLI 산출물은 실행별 output directory 아래에 아래 이름으로 고정 생성된다.

```text
raw.csv
observed_posts.csv
manifest.json
gap_check.md
window_log.csv
```

`observed_posts.csv`는 `tweet_url` 기준 dedupe 결과다. `raw.csv`와 `window_log.csv`는 관측 경로와 gap 확인을 위한 자료이며, 실제 X.com 수집 결과물은 개인 raw 데이터로 취급한다.

### Fixture smoke

실제 X.com 접근 없이 산출물 생성과 dedupe를 검증한다.

```powershell
python scripts\x_observed_search_collect.py `
  --query-file queries\japan-tourism-ja.txt `
  --start-date 2026-05-24 `
  --end-date 2026-05-26 `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\fixture-smoke `
  --fixture-csv tests\fixtures\japan_tourism_observed_fixture.csv
```

또는 unittest:

```powershell
python -m unittest tests.test_x_observed_search_collect
```

### Dry run

쿼리/date window/manifest/gap file만 확인할 때 쓴다. X.com 접속이나 Playwright import가 없다.

```powershell
python scripts\x_observed_search_collect.py `
  --query-file queries\japan-tourism-ja.txt `
  --recent-days 3 `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\dry-run `
  --dry-run
```

### Live X.com observed-search smoke

아래는 로그인 세션이 준비된 개인 환경에서만 소규모로 실행한다. 계정 ID/PW, cookie, `.state/x_chrome_profile`은 repo에 커밋하지 않는다.

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium

python scripts\x_observed_search_collect.py `
  --query-file queries\japan-tourism-ja.txt `
  --start-date 2026-05-25 `
  --end-date 2026-05-25 `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\jp-tourism-smoke `
  --profile-dir .state\x_chrome_profile `
  --max-posts-per-query-window 5 `
  --max-no-new 3 `
  --page-delay 3
```

처음 실행은 `--headless`를 쓰지 않는다. 브라우저가 열리면 사용자가 직접 로그인하고, 같은 profile dir을 이후에도 계속 쓴다. X 접근 제한이나 약관 우회는 하지 않는다.

## 0부터 설치하기

아래는 Windows PowerShell 기준이다. macOS/Linux는 path와 venv activate 명령만 바꾸면 된다.

### 1. 로컬 프로젝트 폴더 만들기

```powershell
mkdir C:\Users\<you>\project_repo\x_observed_topic
cd C:\Users\<you>\project_repo\x_observed_topic

mkdir scripts
mkdir reports
mkdir reports\operations
mkdir data
mkdir data\raw
mkdir data\processed
mkdir .state
```

권장 구조:

```text
x_observed_topic/
  .env
  .gitignore
  scripts/
    x_observed_search_collect.py
  reports/
    operations/
  data/
    raw/
    processed/
  .state/
    x_chrome_profile/
```

`.state/x_chrome_profile/`은 X 로그인 세션이 들어가는 로컬 브라우저 프로필이다. 절대 공유 repo에 올리지 않는다.

### 2. Python 가상환경 만들기

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install playwright python-dotenv pandas
python -m playwright install chromium
```

Chrome channel을 직접 쓰는 스크립트라면 `python -m playwright install chromium`이 없어도 될 수 있다. 처음 구성에서는 설치해 두는 편이 단순하다.

### 3. `.gitignore` 만들기

```text
.venv/
.env
.state/
reports/operations/
data/raw/
data/processed/
*.log
```

raw 데이터와 로그인 세션, API 키는 기본적으로 커밋하지 않는다. 공유해야 할 것은 요약 문서, schema, 재현 가능한 query/manifest이다.

본 패키지의 `.gitignore`도 `.state/`, `.env*`, `reports/operations/`, `data/raw/`, `data/processed/`, 브라우저 profile/cookie/session 파일, run output 기본 파일을 제외한다.

### 4. `.env` 만들기

처음에는 X API token이 필요 없다. 이 방식은 X API가 아니라 브라우저 로그인 세션을 사용한다.

```text
X_PROFILE_DIR=.state/x_chrome_profile
OUTPUT_ROOT=reports/operations
SEARCH_QUERIES=#Topic,Topic Name,TopicName
SCROLL_DELAY=2
```

AI 분석이나 DB 업로드까지 붙일 때만 아래처럼 별도 값을 추가한다.

```text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
DATABASE_URL=
```

빈 값이든 실제 값이든 `.env`는 커밋하지 않는다.

### 5. 수집 스크립트 옵션 확인

이 패키지의 현재 CLI는 아래 옵션을 사용한다. 다른 프로젝트에 이 스크립트를 옮길 때도 이 이름을 기준으로 맞춘다.

| option | required | meaning |
|---|---:|---|
| `--queries` 또는 `--query-file` | yes | comma-separated query list 또는 UTF-8 query file |
| `--start-date` 또는 `--recent-days` | yes | inclusive start date 또는 최근 N일 |
| `--end-date` | `--start-date` 사용 시 yes | inclusive end date |
| `--timezone` | no | default `Asia/Tokyo` |
| `--output-dir` | yes | 실행 산출물 폴더. `--prepare-login`에서는 불필요 |
| `--window-days` | no | default `1` |
| `--max-posts-per-query-window` | no | default `100` |
| `--max-no-new` | no | default `10` |
| `--scroll-delay` | no | default `2` seconds |
| `--page-delay` | no | default `2` seconds |
| `--profile-dir` | no | default `.state/x_chrome_profile` |
| `--headless` | no | login 완료 후에만 사용 |
| `--dry-run` | no | X.com 접속 없이 빈 산출물과 manifest 생성 |
| `--fixture-csv` | no | fixture CSV에서 산출물 생성 |
| `--prepare-login` | no | X.com home을 non-headless persistent profile로 열고 수집 없이 종료 |
| `--login-wait-seconds` | no | `--prepare-login`에서 로그인 상태를 기다리는 시간, default `180` |

가장 중요한 구현 요구사항:

- Playwright persistent browser profile을 사용한다.
- 첫 인증 준비는 `--prepare-login`으로 headless가 아닌 브라우저 창에서 수행한다.
- `https://x.com/home`에 접근해 로그인 여부를 확인한다.
- 검색 URL은 `https://x.com/search?q=<query since:YYYY-MM-DD until:YYYY-MM-DD>&src=typed_query&f=live` 형태를 사용한다.
- `tweet_url`을 반드시 저장한다.
- 같은 run 안에서는 `tweet_url` 기준 중복을 제거한다.
- `raw.csv`, `observed_posts.csv`, `window_log.csv`, `manifest.json`, `gap_check.md`를 저장한다.

### 6. X.com 로그인 세션 만들기

첫 실행은 인증 준비 단계다. 이 단계에서는 수집을 시작하지 않고, `.state/x_chrome_profile`에 사용자가 직접 로그인한 브라우저 세션을 남기는 것이 목적이다.

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\x_observed_search_collect.py `
  --profile-dir .state\x_chrome_profile `
  --prepare-login `
  --login-wait-seconds 300
```

브라우저가 열리면 X.com에 직접 로그인한다. 2FA가 있으면 직접 처리한다. 스크립트는 계정/비밀번호를 받지 않고, cookie를 export하지 않으며, 검색 수집도 시작하지 않는다. 종료 JSON의 `login_state`가 `logged-in`이면 같은 `--profile-dir`로 첫 smoke run을 실행한다. `login-required` 또는 `unknown`이면 브라우저에서 로그인 상태를 확인하고 같은 명령을 다시 실행한다.

주의:

- X 계정 ID/PW를 스크립트에 넣지 않는다.
- cookie를 export해서 repo에 넣지 않는다.
- `.state/x_chrome_profile` 폴더는 개인 PC에만 둔다.
- 로그인 세션이 만료되면 같은 `--prepare-login` 방식으로 다시 headless 없이 실행해 재로그인한다.

### 7. 첫 smoke run

로그인 세션이 저장되었는지 확인하기 위해 아주 작은 범위를 돌린다.

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-01 `
  --end-date 2026-01-01 `
  --queries "#Topic,Topic Name" `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\topic-smoke-2026-01-01 `
  --window-days 1 `
  --max-posts-per-query-window 10 `
  --max-no-new 5 `
  --profile-dir .state\x_chrome_profile
```

pass 기준:

- 지정한 `--output-dir` 아래 `manifest.json` 생성.
- `raw.csv`, `observed_posts.csv`, `window_log.csv`, `gap_check.md` 생성.
- X login 페이지로 되돌아가지 않음.
- 0건이어도 `window_log.csv`에 검색 window와 query가 기록됨.

0건은 실패가 아닐 수 있다. 하지만 검색 화면에서 수동으로 결과가 보이는데 raw가 0이면 selector, scroll, query encoding, 로그인 상태를 확인한다.

### 8. 실제 수집으로 넘어가기

smoke run이 통과한 뒤에만 실제 기간을 수집한다.

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-01 `
  --end-date 2026-01-31 `
  --queries "#Topic,Topic Name,TopicName" `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\topic-observed-2026-01 `
  --window-days 1 `
  --max-posts-per-query-window 100 `
  --max-no-new 10 `
  --profile-dir .state\x_chrome_profile
```

처음부터 `--headless`를 쓰지 않는다. 며칠 운용해서 로그인 세션이 안정적인 것을 확인한 뒤에만 headless를 켠다.

## 권장 데이터 스키마

raw CSV는 최소 아래 컬럼을 가진다.

| column | required | note |
|---|---:|---|
| `collect_date` | yes | 수집 실행일 |
| `tweet_date` | yes | 포스트 작성일, `YYYY-MM-DD` |
| `author_handle` | yes | 작성자 handle |
| `author_name` | no | 표시명 |
| `content` | yes | 포스트 본문 |
| `tweet_url` | yes | dedupe key |
| `view_count` | no | 검색 화면에서 보이면 저장 |
| `like_count` | no | 검색 화면에서 보이면 저장 |
| `hashtags` | no | 쉼표 또는 JSON array |
| `language` | no | 추정 언어 |
| `image_urls` | no | 여러 개면 `\|` 구분 |
| `media_type` | yes | `text`, `image`, `video` 중 하나 권장 |

AI 분석 CSV를 만들면 아래 컬럼을 추가한다.

| column | required | note |
|---|---:|---|
| `translation_kr` | yes | 한국어 번역 또는 원문 유지 |
| `summary_kr` | yes | 짧은 요약 |
| `sentiment` | yes | 프로젝트별 허용 label만 사용 |
| `post_type` 또는 `tweet_type` | yes | 프로젝트별 허용 type만 사용 |
| `image_description` | media row only | 이미지/비디오가 있으면 비어 있으면 안 됨 |
| `analyzed_at` | yes | 분석 시각 |

## 검색어 설계

처음부터 넓은 검색어 하나로 끝내지 않는다. 아래 네 묶음을 만든다.

| group | example |
|---|---|
| 공식명 | `"Hi-Fi Rush"` |
| 띄어쓰기/철자 변형 | `"HiFi Rush"`, `"Hi Fi Rush"`, `"hifi rush"` |
| 해시태그 | `#HiFiRush`, `#HifiRush` |
| 관련 고유명사 | 퍼블리셔명, 스튜디오명, 이벤트명, 제품명 |

검색어가 너무 넓으면 unrelated row가 늘어난다. 반대로 너무 좁으면 gap이 생긴다. 운영 기준은 `핵심 검색어 세트`와 `보강 검색어 세트`를 분리하는 것이다.

예:

```text
core: "#HiFiRush", "Hi-Fi Rush", "HiFi Rush"
expanded: "Hi Fi Rush", "hifi rush", "Tango Hi-Fi Rush", "KRAFTON Hi-Fi Rush"
```

## 날짜 window 기준

| 목적 | window | cap | note |
|---|---:|---:|---|
| 최근 일일 수집 | 1일 | query당 100 | 매일 같은 시각 실행 |
| 과거 백필 1차 | 1일 | query당 100 | 기본값 |
| 저볼륨 주제 빠른 확인 | 3~7일 | query당 100 | gap 검증 필수 |
| 0건/누락 의심 재시도 | 1일 | query당 500~1000 | `max_no_new` 상향 |

과거 백필에서 4일 또는 7일 window만 쓰면 검색 결과가 날짜 안쪽 일부로 쏠릴 수 있다. 장기간 공백이 보이면 실제 무활동으로 단정하지 말고 1일 window로 재검색한다.

## 권장 실행 절차

아래 절차는 위의 `0부터 설치하기`와 첫 smoke run이 끝난 뒤의 운영 단계다.
아직 X 로그인 세션이 없으면 이 단계로 바로 넘어가지 말고 먼저 `.state/x_chrome_profile`에 로그인 세션을 만든다.

### 1. raw 먼저 만들기

분석이나 DB 업로드를 붙이기 전에 raw CSV만 만든다.

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-01 `
  --end-date 2026-01-31 `
  --window-days 1 `
  --max-posts-per-query-window 100 `
  --max-no-new 10 `
  --queries "#Topic,Topic Name,TopicName" `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\x-topic-raw-2026-01 `
  --profile-dir .state\x_chrome_profile
```

실제 스크립트 이름은 프로젝트마다 달라도 된다. 다만 옵션 의미는 위 형태로 맞추면 다른 프로젝트에서도 재사용하기 쉽다. 새 환경에서는 처음 며칠 동안 `--headless`를 쓰지 않고 로그인 유지 상태를 확인한다.

### 2. raw union 만들기

여러 pass를 실행한 뒤 모든 `raw.csv`를 `tweet_url` 기준으로 합친다.

필수 검증:

- 전체 raw row 수.
- distinct `tweet_url` 수.
- 날짜별 distinct URL 수.
- 같은 URL이 서로 다른 `tweet_date`로 들어온 date conflict 수.
- 기존 union 또는 DB와 overlap 수.

### 3. gap 확인

날짜별 count를 보고 아래 케이스는 재검색한다.

- 0건 날짜.
- 앞뒤 날짜 대비 갑자기 낮은 날짜.
- 이벤트 기간인데 관측량이 끊긴 날짜.
- X 검색 화면에서 수동으로는 보이는데 raw에 없는 날짜.

재검색 예:

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-08 `
  --end-date 2026-01-08 `
  --window-days 1 `
  --max-posts-per-query-window 1000 `
  --max-no-new 50 `
  --queries "#Topic,Topic Name,TopicName,topic name,TOPIC NAME" `
  --timezone Asia/Tokyo `
  --output-dir reports\operations\x-topic-retry-2026-01-08 `
  --profile-dir .state\x_chrome_profile
```

재검색해도 0건이면 `현재 검색 surface 기준 0건`이라고 기록한다. `실제 0건`이라고 쓰지 않는다.

### 4. AI 분석은 별도 단계로 실행

raw 수집이 끝난 뒤 필요한 경우에만 별도 분석 도구나 notebook에서 분석한다. 이 POC CLI는 X.com observed-search raw 수집과 fixture/dry-run 검증만 담당하며, AI 분석 옵션은 제공하지 않는다.

권장 운영:

- 200건 단위 chunk.
- 실패하면 chunk 전체를 버리지 말고 실패 URL만 분리.
- 정상 분석 row만 업로드 또는 다음 단계로 이동.
- 실패 URL은 manifest에 남기고 재시도 후보로 둔다.

### 5. AI guard 기준

분석 결과는 아래 조건에서 실패로 처리한다.

- `summary_kr`가 비어 있음.
- `summary_kr`가 `분석 실패`로 시작.
- `translation_kr`가 비어 있음.
- `sentiment`가 허용 label 밖.
- `tweet_type` 또는 `post_type`이 허용 type 밖.
- `media_type != text`이고 `image_urls`가 있는데 `image_description`이 비어 있음.

가드 실패는 원문이 나쁘다는 뜻이 아니다. 모델 응답이 스키마를 만족하지 못해 DB나 최종 산출물을 오염시킬 수 있다는 뜻이다.

### 6. 업로드 전 최종 검증

DB에 올리거나 분석용 parquet/csv로 확정하기 전 아래를 확인한다.

| check | pass condition |
|---|---|
| `tweet_url` duplicate | 0 |
| date conflict URL | 0 또는 수동 판정 기록 |
| raw target URL missing after upload | 0 |
| invalid AI analysis | 0 |
| 날짜별 source vs target count mismatch | 0 |
| manifest 존재 | yes |

## 산출물 구조

권장 폴더 구조:

```text
reports/
  operations/
    x_topic_observed_YYYYMMDD_HHMMSS/
      raw.csv
      observed_posts.csv
      window_log.csv
      manifest.json
      gap_check.md
    x_topic_union_YYYYMMDD/
      raw_union.csv
      observed_posts_union.csv
      union_manifest.json
      gap_check.md
```

manifest에는 최소 아래를 남긴다.

```json
{
  "source": "X.com web search observed public searchable posts",
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "window_days": 1,
  "queries": ["#Topic", "Topic Name", "TopicName"],
  "raw_rows": 1234,
  "distinct_urls": 1200,
  "duplicate_url_rows": 34,
  "date_conflict_url_count": 0,
  "upload_requested": false
}
```

## 보고서 문구

좋은 표현:

- `X.com 공개 검색 화면에서 관측된 포스트`
- `Observed X.com public searchable posts`
- `현재 수집 방식 기준 관측 하한`
- `검색 surface의 비결정성 때문에 full archive로 해석하면 안 됨`

피해야 할 표현:

- `전체 트윗`
- `전체 X 언급량`
- `해당 기간 트윗이 하나도 없음`
- `full archive`
- `complete coverage`

예시 주석:

```text
본 수치는 X.com web search에서 관측된 공개 검색 결과 기준이다.
X full archive API 기반 전체 언급량이 아니므로, 날짜별 비교는 검색 노출 surface의 변동 가능성을 포함한다.
```

## 운영 체크리스트

- [ ] 검색어 core/expanded 세트 정의.
- [ ] 날짜 범위와 timezone 기준 명시.
- [ ] `--prepare-login`으로 local profile 로그인 상태 확인.
- [ ] 1일 window raw 수집 실행.
- [ ] raw union 및 `tweet_url` dedupe.
- [ ] 날짜별 0건/저건수 재검색.
- [ ] manifest와 gap check 문서 작성.
- [ ] 필요 시 AI 분석을 chunk 단위로 실행.
- [ ] AI guard 실패 URL 분리.
- [ ] 최종 target과 업로드/분석 테이블 URL count 대조.
- [ ] 보고서에 observed-search 한계 문구 삽입.

## 자주 생기는 문제

### 같은 날짜를 다시 돌렸는데 결과가 다름

정상적으로 발생할 수 있다. X.com 검색 화면은 비결정적이고, 스크롤 깊이/쿼리/시간/로그인 상태에 따라 노출 결과가 달라질 수 있다. 단일 run을 정답으로 두지 말고 여러 pass union을 쓴다.

### 긴 구간이 비어 있음

실제 무활동으로 단정하지 않는다. 1일 window, expanded query, 높은 `max_no_new`로 재검색한다.

### query당 100개 제한 때문에 누락이 생김

수집 스크립트 cap이 100이면 high-volume 날짜에서 잘릴 수 있다. 날짜를 1일 이하로 줄이고, 재검색 시 cap을 500~1000으로 높인다.

### 이미지/비디오 포스트 분석이 실패함

이미지 다운로드 실패, 모델 응답 JSON 파싱 실패, token limit, safety refusal 등이 원인일 수 있다. 해당 URL만 별도 재분석하고, 실패가 반복되면 raw는 유지하되 분석 row는 제외한다.

### 집 환경에서 로그인 창이 뜸

처음 1회는 headless를 끄고 브라우저에서 로그인한다. 이후 같은 persistent Chrome profile을 쓰면 세션이 유지된다. 계정/2FA 정보는 repo에 저장하지 않는다.

## 최소 원칙

이 방식의 목적은 `전체를 다 긁었다`고 주장하는 것이 아니라, 제한된 검색 surface에서 재현 가능한 절차로 관측치를 넓히고 한계를 명시하는 것이다. 수집보다 중요한 것은 dedupe, gap 재검색, 검증, 그리고 보고서 표현의 정확성이다.
