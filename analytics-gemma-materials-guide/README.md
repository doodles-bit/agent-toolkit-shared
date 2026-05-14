# Gemma 로컬 materials 추출 가이드

작성일: 2026-05-13
대상: 커뮤니티 댓글 요약, 번역, 센티멘트 분석을 수행하는 분석 에이전트

Windows 회사 PC에서 Ollama 설치부터 Gemma 4 옵션 smoke test까지 막힌 지점을 복구해야
한다면 [OLLAMA_GEMMA4_WINDOWS_SETUP.md](./OLLAMA_GEMMA4_WINDOWS_SETUP.md)를 먼저 본다.

## 결론

Gemma는 최종 리포트를 쓰는 편집자보다, 원문에서 분석 재료를 뽑는 materials 추출기로
쓰는 편이 더 안정적이다.

권장 구조:

```text
원문 댓글
-> Gemma 로컬 materials 추출
-> validator로 충돌, 누락, 형식 경고 표시
-> 강한 모델이 최종 요약, 번역 보정, 센티멘트 판단, 리포트 작성
```

Gemma 단독으로 최종 리포트까지 맡기는 구조는 아직 권하지 않는다. 문장 품질, 토픽 선정,
긴 입력 전체 커버리지에서 강한 모델보다 약하다. 대신 번역 초안, 타깃 식별, 핵심 주장,
근거 quote, 불확실성 같은 구조화 재료 추출에는 쓸만하다.

## 검증한 환경

- 로컬 런타임: Ollama
- 주 테스트 모델: `gemma4:e2b`
- 비교 모델: `gemma3:1b`, `qwen3:0.6b`
- 실험 입력: AI briefing 영상 자막 청크
- 기본 청크: 자막 3,000자, overlap 200자
- 기본 컨텍스트: `num_ctx 4096`
- 기본 temperature: `0.2`
- 성능 기준: 집 PC 기준

집 PC 기준 실험에서는 처리 시간이 길고 PC 반응성 저하가 있었다. 회사 PC는 성능이 훨씬
높을 수 있으므로 처리 시간, 동시 처리량, batch 크기는 회사 환경 smoke test로 다시
측정해야 한다. 이 문서의 품질 판단은 처리 속도보다 materials 추출 구조의 적합성에 관한
것이다.

확인한 내용:

- Ollama `create`, `show --system`, `show --parameters`, native chat 호출이 정상 동작했다.
- `gemma4:e2b`는 작은 모델보다 품질이 낫지만 PC 부하가 컸다.
- summary보다 materials 추출 구조가 후속 리포트 작성에 유리했다.
- 커뮤니티 댓글 도메인에서는 별도 샘플 검증이 필요하다.

## 권장 출력 스키마

댓글 분석에서는 summary보다 댓글별 materials 추출을 먼저 한다.

입력 예:

```text
comment_id: c_001
author: user123
language_hint: en
text: The product is much faster now, but the pricing is confusing.
```

출력 예:

```json
{
  "comment_id": "c_001",
  "language": "en",
  "translation_ko": "제품이 이제 훨씬 빨라졌지만 가격 정책은 헷갈린다.",
  "sentiment": "mixed",
  "sentiment_score": 0.1,
  "targets": ["product speed", "pricing"],
  "key_points": [
    "속도 개선에 긍정적이다.",
    "가격 정책은 혼란스럽다고 본다."
  ],
  "evidence": [
    {"target": "product speed", "quote": "much faster now"},
    {"target": "pricing", "quote": "pricing is confusing"}
  ],
  "uncertainty": []
}
```

권장 스키마:

```json
{
  "comment_id": "string",
  "language": "string",
  "translation_ko": "string",
  "sentiment": "positive|neutral|negative|mixed|unclear",
  "sentiment_score": -1.0,
  "targets": ["string"],
  "key_points": ["string"],
  "evidence": [{"target": "string", "quote": "string"}],
  "uncertainty": ["string"]
}
```

주의:

- `sentiment_score`는 정밀한 계량값이 아니라 정렬용 보조값으로 본다.
- sarcasm, 밈, 짧은 감탄 댓글은 `unclear` 또는 낮은 확신으로 처리한다.
- 최종 센티멘트 집계는 강한 모델, validator, 또는 human review가 담당한다.

## 주요 관찰

### summary 경로는 최종 리포트용으로 약하다

3,000자 청크를 200~400자 요약으로 줄이는 데는 성공했다. 다만 넓은 뉴스형 입력에서는
첫 주제만 요약하고 뒤쪽 주제는 빠졌다. 요약은 토큰 절감에는 좋지만, 리포트 작성자는
근거 문장과 숫자 출처를 다시 확인해야 한다.

### materials 경로가 분석 에이전트에 더 맞다

materials 출력은 summary보다 길지만 원문보다 훨씬 짧고, 최종 리포트 작성에 필요한
근거를 보존한다.

1청크 3,000자 기준 관찰:

| 입력 | summary 결과 | materials 결과 |
|---|---:|---:|
| AI 뉴스 청크 | 약 250자 | 약 887~922자 |
| Codex 청크 | 약 353자 | 약 733~867자 |

해석:

- summary: 원문 대비 약 8~12%
- materials: 원문 대비 약 24~31%
- materials는 summary보다 길지만 원문 자막 대비 약 3~4배 작다.

강한 모델에 원문 전체를 넣던 구조라면 materials는 API 비용 절감에 도움이 된다. 이미 짧은
summary만 넣던 구조라면 비용 절감보다 근거 보존과 품질 관리 이득이 더 크다.

### thinking off를 기본값으로 둔다

`thinking on`은 `max_tokens 500`에서 출력 예산을 추론에 써서 요약 본문이 비는 문제가
있었다. `max_tokens 2000`으로 올리면 정상 종료했지만, 품질 이득은 제한적이었다.

2샘플 비교:

| 조건 | 총 처리시간 | 관찰 |
|---|---:|---|
| thinking off, max_tokens 2000 | 약 218초 | 더 빠르고 숫자 보존이 좋음 |
| thinking on, max_tokens 2000 | 약 348초 | 짧은 샘플에서 토픽은 생성했지만 AI 뉴스 품질 개선은 약함 |

운영 기본값은 `thinking: off`가 낫다.

### Ollama wrapper 모델은 운영 관리용이다

`Modelfile`로 system prompt와 파라미터를 고정한 전용 모델을 만들 수 있었다.

예:

```text
ai-briefing-summary-gemma4:thinkoff
ai-briefing-materials-gemma4:thinkoff
```

장점:

- 호출 코드에서 긴 system prompt를 덜 들고 다닌다.
- 모델 태그로 역할을 명확히 고정할 수 있다.
- 실험 조건 관리가 쉬워진다.

한계:

- `prompt_eval_count`는 줄지 않았다. 모델 SYSTEM도 내부 평가에 포함되는 것으로 보인다.
- summary 품질은 inline system prompt보다 좋아지지 않았다.
- materials 품질도 inline과 거의 같았다.

따라서 wrapper는 운영 정리용이지 품질 향상 카드로 보지는 않는다.

### source conflict는 validator warning으로 잡는다

`Codex` 영상에서 제목과 메타데이터는 `Codex`, 자막 원문은 `Cody's`로 되어 있었다. Gemma가
`Cody`를 쓴 것은 환각이 아니라 원문 충실 결과다.

권장 warning 예:

```json
{
  "warning_code": "source_conflict",
  "field": "name",
  "meta_value": "Codex",
  "source_value": "Cody",
  "action": "final_model_should_resolve"
}
```

모델에게 불확실성 판단을 모두 기대하기보다 validator가 명시 warning으로 남기고, 후속
강한 모델이 최종 해석을 맡는 편이 안정적이다.

## 추천 파이프라인

### 1단계: 로컬 전처리

Gemma가 댓글별 materials를 만든다.

목표:

- 번역 초안
- 감정 후보
- 타깃 제품, 기능, 회사
- 핵심 주장
- 근거 quote
- 불확실성

### 2단계: validator

규칙 기반으로 오류 가능성을 표시한다.

체크:

- JSON parse 실패
- 필수 키 누락
- quote가 원문에 없는 경우
- sentiment와 key_points가 충돌하는 경우
- 번역이 비어 있는 경우
- 같은 댓글의 언어 판단이 흔들리는 경우
- 스팸, 광고, 무의미 댓글 후보

### 3단계: 강한 모델 최종 분석

강한 모델은 원문 전체가 아니라 materials와 warnings를 입력으로 받아 최종 리포트를 쓴다.

역할:

- 중복 제거
- 토픽 클러스터링
- 긍정, 부정, 혼합 비율 해석
- 대표 quote 선택
- 번역 품질 보정
- source conflict 또는 low-confidence 항목 교정
- 최종 리포트 작성

## 운영 가이드

기본값:

```text
model: gemma4:e2b
runtime: Ollama
thinking: off
temperature: 0.2
num_ctx: 4096
batch: 작게 시작
output: compact JSON
```

권장하지 않음:

- Gemma에게 최종 보고서까지 맡기기
- 긴 원문 전체를 한 번에 넣기
- `thinking on`을 기본값으로 쓰기
- source conflict 판단을 모델에게만 맡기기

권장:

- 작고 반복 가능한 batch로 shadow run
- JSON schema를 엄격하게 유지
- validator warning을 강한 모델에 함께 전달
- 집 PC에서는 운영 시간 PC 부하 제한
- 회사 PC에서는 별도 smoke test로 가능한 병렬도와 batch 크기 측정
- 긴 입력은 multi-chunk 또는 comment batch로 분리

## 다음 실험

커뮤니티 댓글용으로 바로 검증할 실험:

1. 실제 댓글 50~100개 샘플을 언어별로 섞는다.
2. Gemma materials 추출을 `thinking: off`로 실행한다.
3. 강한 모델에 원문 전체 입력 vs materials 입력을 비교한다.
4. 비교 항목:
   - 최종 요약 품질
   - 번역 오류
   - sentiment 분류 일치율
   - 대표 quote 품질
   - 입력 토큰 절감률
   - 처리 시간과 PC 부하
   - 회사 PC에서 batch 크기별 처리량

추천 판단 기준:

- materials 입력으로 최종 리포트 품질이 유지되고 입력량이 50% 이상 줄면 도입 가치가 있다.
- sentiment가 민감한 의사결정에 쓰이면 Gemma 단독 판정은 금지하고, 강한 모델 또는 human
  review를 둔다.
- 회사 PC에서 댓글 50~100개 batch가 실무 시간 안에 끝나면 로컬 전처리 도입 가능성이
  높다.

## 한 줄 ADR

2026-05-13: 로컬 Gemma는 최종 리포트 작성자가 아니라 comments/transcripts materials
추출기로 사용한다. 근거는 summary 품질 이득보다 names/numbers/key_facts/evidence 보존이
더 안정적이었기 때문이며, 포기한 대안은 Gemma summary를 최종 브리핑 초안으로 직접
사용하는 방식이다.
