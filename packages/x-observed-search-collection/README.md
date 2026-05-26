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

## 준비물

- Python 3.11+ 권장.
- Chrome 또는 Chromium.
- Playwright.
- 수집 전용 X 계정. 브라우저 프로필에 로그인 세션을 저장해 두는 방식 권장.
- 로컬 저장 폴더. 예: `reports/operations/x_topic_collect_<date>/`.

민감정보는 repo에 커밋하지 않는다. API 키, X 계정 정보, DB 토큰은 `.env` 또는 OS 환경변수로만 둔다.

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

### 1. scrape-only로 raw 먼저 만들기

분석이나 DB 업로드를 붙이기 전에 raw CSV만 만든다.

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-01 `
  --end-date 2026-01-31 `
  --window-days 1 `
  --max-tweets-per-query-window 100 `
  --max-no-new 10 `
  --queries "#Topic,Topic Name,TopicName" `
  --scrape-only
```

실제 스크립트 이름은 프로젝트마다 달라도 된다. 다만 옵션 의미는 위 형태로 맞추면 다른 프로젝트에서도 재사용하기 쉽다.

### 2. raw union 만들기

여러 pass를 실행한 뒤 모든 `raw_observed_posts.csv`를 `tweet_url` 기준으로 합친다.

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
  --max-tweets-per-query-window 1000 `
  --max-no-new 50 `
  --queries "#Topic,Topic Name,TopicName,topic name,TOPIC NAME" `
  --scrape-only
```

재검색해도 0건이면 `현재 검색 surface 기준 0건`이라고 기록한다. `실제 0건`이라고 쓰지 않는다.

### 4. AI 분석은 별도 단계로 실행

raw 수집이 끝난 뒤 필요한 경우에만 분석한다.

```powershell
python scripts\x_observed_search_collect.py `
  --start-date 2026-01-01 `
  --end-date 2026-01-31 `
  --from-raw-csv reports\operations\x_topic_union\raw_observed_posts_union.csv `
  --max-new-to-analyze 200
```

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
      raw_observed_posts.csv
      window_log.csv
      new_rows_to_analyze.csv
      analyzed_observed_posts.csv
      manifest.json
    x_topic_union_YYYYMMDD/
      raw_observed_posts_union.csv
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
  "raw_observed_rows": 1234,
  "distinct_urls": 1200,
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
- [ ] 1일 window scrape-only 실행.
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
