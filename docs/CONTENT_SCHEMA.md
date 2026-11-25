# saicerti 문제 데이터 형식 (v1)

과정 ID: `pyb` = 프로그래밍 Python 기본(COS Pro 2급 Python 유형), `pya` = 프로그래밍 Python 심화(COS Pro 1급 Python 유형).
유형(원본 문제 번호) 1~10마다 파일 하나: `src/content/<과정>/tNN.json` (예: `src/content/pyb/t01.json`). 파일마다 유사 문제 **정확히 5개**(a~e).

모의고사: `src/content/<과정>/mock/tNN.json`에 문제 3개(id `<과정>-m1-tNN`~`-m3-tNN`, 1·2·3회), `steps`는 `[]`(중간 점검 없음). 만드는 법은 `docs/MOCK_BRIEF.md`.

검수: `python3 tools/validate.py src/content/pyb/t01.json` → `✓ … 검수 통과`가 나와야 한다. 브라우저 채점과 검수 도구는 같은 `src/grader/harness.py`를 쓴다.

## 파일

```jsonc
{
  "course": "pyb",                  // 경로와 같아야 함
  "type": 1,                        // 유형 번호(원본 문제 번호)
  "typeTitle": "2차원 리스트 행 처리",  // 2~24자, 유형 목록에 보이는 이름
  "kind": "blank",                  // blank(빈칸 채우기) | fix(한 줄 수정) | write(함수 작성) — 원본과 같은 형식
  "skills": ["2차원 리스트", "max·min", "홀짝 판별"],
  "intro": "유형 소개 2~3문장(무엇을 연습하는지)",
  "problems": [ 문제 5개 ]
}
```

## 문제

| 필드 | 설명 |
|---|---|
| `id` | `<과정>-tNN-<a~e>` (예: `pyb-t01-a`). 진도 ID라 한 번 정하면 바꾸지 않는다 |
| `version` | 1부터. 내용을 고치면 올린다 |
| `title` | 2~30자 |
| `statement` | 문제 설명. 문단은 `\n\n`, 줄바꿈 `\n`, `- `로 시작하는 줄은 글머리표, `` `코드` ``는 코드 글꼴. 마지막 문단에 할 일(예: "빈칸을 채워 전체 코드를 완성해 주세요." / "코드에서 한 줄만 변경해서 프로그램이 올바르게 동작하도록 해 주세요." / "solution 함수를 완성해 주세요.") |
| `params` | 매개변수 설명 글머리표 목록(문자열 배열, 값의 범위·조건 포함) |
| `returns` | return 값 설명 목록 |
| `funcName` | 채점이 부르는 함수 이름(보통 `solution`) |
| `argNames` | 매개변수 이름 배열(순서대로) |
| `examples` | 2~3개. `{ "args": [인자1, 인자2…], "expected": 값, "explain": "예시 설명(선택)" }` |
| `code` | 학생이 처음 보는 코드. blank: 빈칸 자리를 `⟦1⟧`, `⟦2⟧`…로 표시(순서대로). fix: 틀린 한 줄이 들어 있는 전체 코드. write: 함수 머리와 `answer = …`, `return answer` 정도의 틀 |
| `blanks` | blank만. 빈칸마다 `{ "answer": "정답 코드 조각", "alts": ["다른 정답(선택)"] }` — 채점은 테스트 실행으로 하므로 참고용(정답 보기) |
| `bugLine` | fix만. 틀린 줄 번호(1부터) |
| `solution` | 정답 전체 코드. blank면 `⟦n⟧`을 `blanks[n-1].answer`로 바꾼 코드와 **줄마다 똑같아야** 한다. fix면 `code`와 **정확히 한 줄만** 달라야 한다 |
| `tests` | 숨은 테스트 10개 이상 `{ "args": [...], "expected": 값 }`. 경계값(최솟값·최댓값·같은 값·빈 경우가 허용되면 빈 경우)을 꼭 넣는다. 예시와 같은 입력은 넣지 않는다 |
| `compare` | `exact`(기본: 정수는 정수로 비교, 3.0≠3) 또는 `float`(오차 허용) |
| `inputCheck` | `def valid(인자들): return bool` — 매개변수 설명의 조건을 그대로 코드로. 모든 예시·테스트에서 참이어야 한다 |
| `steps` | 중간 점검 3~6단계(아래). 표(table)와 객관식(mcq)이 각각 1개 이상 |
| `explain` | 해설 2~4문장(핵심 아이디어, 흔한 실수) |

값은 JSON으로 쓸 수 있는 것만: 정수, 실수, 문자열, 참/거짓, 리스트(중첩 가능). 튜플·딕셔너리 반환은 쓰지 않는다(리스트로).

## 중간 점검 단계(steps)

코드를 풀기 전에 차례로 푸는 것을 권한다. 한 문제 안에서는 단계와 코드 풀이를 자유롭게 오갈 수 있다(선생님 요청 2026-11-26, 맞힌 단계에만 ✓). 틀리면 다시, 세 번 틀리면 정답 보기. **질문·보기·해설에 코드 풀이의 빈칸 번호(⟦1⟧ 등)를 쓰지 않는다** — 학생이 코드를 보지 않고 질문만 읽어도 풀 수 있게, 필요한 코드 조각을 질문에 직접 적는다(단위 테스트가 막음). 목표: 문제 이해 → 손으로 따라가기(표) → 코드의 핵심 결정 순서로 스스로 답에 다가가게 한다. 코드 정답을 통째로 알려 주지 않는다.

```jsonc
// 객관식
{ "id": "s1", "kind": "mcq", "q": "질문", "options": ["보기1", "보기2", "보기3", "보기4"], "answer": 0, "explain": "해설" }
// 표 채우기: 문자열 칸은 그대로 보이고, {"a": "정답"} 칸은 입력 칸
{ "id": "s2", "kind": "table", "title": "예시 1 따라가기", "prompt": "반복할 때마다 값을 채워 보세요.",
  "columns": ["s", "s >= 10", "total", "count"],
  "rows": [["5", {"a": "False", "alts": ["false"]}, {"a": "0"}, {"a": "1"}]],
  "check": "def answers():\n    ...\n    return [False, 0, 1]",
  "explain": "해설" }
// 단답
{ "id": "s3", "kind": "short", "q": "질문", "a": "정답", "alts": [], "check": "def answers():\n    return [정답]", "explain": "해설" }
```

- `id`는 `s1`, `s2`… 
- table: 열 2~7개, 행 1~12개, 입력 칸 2~16개. 입력 칸 정답은 40자 이하의 짧은 값(숫자, `True`, 짧은 리스트 등). 비교할 때 공백을 무시하고 `"`와 `'`를 같게 본다.
- `check`(table·short 필수): `def answers():`가 **입력 칸 정답을 행 순서(왼쪽→오른쪽, 위→아래)대로** 계산해 돌려준다. 검수 도구가 `str(값)`을 `a`(또는 `alts`)와 비교한다 → 손으로 셈한 값이 틀리면 검수에서 걸린다. 가능하면 문제의 정답 함수 일부를 그대로 실행해 계산한다.
- mcq: 보기 3~5개(중복 없음), `answer`는 0부터. 그럴듯한 오답(흔한 실수)을 보기로 넣는다.

## 예시(형식 참고용 — 실제 유형과 관계없음)

```json
{
  "id": "pyb-t01-a", "version": 1, "title": "목표 달성한 날",
  "statement": "한 가게의 하루 판매량을 날짜 순서대로 담은 리스트 `sales`와 목표량 `target`이 주어집니다. 판매량이 목표량 이상인 날은 **달성**, 아니면 **미달**입니다.\n\n달성한 날의 판매량 합계와 미달인 날의 수를 `[합계, 날 수]` 형태로 return 하려 합니다. 빈칸을 채워 전체 코드를 완성해 주세요.",
  "params": ["sales의 길이는 1 이상 30 이하입니다.", "sales의 원소와 target은 0 이상 100 이하인 정수입니다."],
  "returns": ["[달성한 날의 판매량 합계, 미달인 날의 수]를 return 합니다."],
  "funcName": "solution", "argNames": ["sales", "target"],
  "examples": [
    { "args": [[5, 12, 8, 15, 10, 3, 20], 10], "expected": [57, 3], "explain": "12, 15, 10, 20이 달성(합 57)이고 5, 8, 3이 미달(3일)입니다." },
    { "args": [[1, 2, 3], 5], "expected": [0, 3] }
  ],
  "code": "def solution(sales, target):\n    total = 0\n    count = 0\n    for s in sales:\n        if ⟦1⟧:\n            total += ⟦2⟧\n        else:\n            count += 1\n    return ⟦3⟧",
  "blanks": [{ "answer": "s >= target", "alts": ["target <= s"] }, { "answer": "s" }, { "answer": "[total, count]" }],
  "solution": "def solution(sales, target):\n    total = 0\n    count = 0\n    for s in sales:\n        if s >= target:\n            total += s\n        else:\n            count += 1\n    return [total, count]",
  "tests": [ { "args": [[10], 10], "expected": [10, 0] }, "… 10개 이상" ],
  "inputCheck": "def valid(sales, target):\n    return 1 <= len(sales) <= 30 and all(isinstance(x, int) and 0 <= x <= 100 for x in sales) and 0 <= target <= 100",
  "steps": [
    { "id": "s1", "kind": "mcq", "q": "판매량이 목표량과 똑같은 날은 어떻게 볼까요?", "options": ["달성", "미달", "세지 않는다"], "answer": 0, "explain": "'목표량 이상'은 같은 경우를 포함해요. 그래서 >= 를 써요." },
    { "id": "s2", "kind": "table", "title": "예시 1 따라가기", "prompt": "앞의 4일만 따라가며, 그날을 처리한 뒤의 total과 count를 채워 보세요(target = 10).",
      "columns": ["s", "s >= target", "total", "count"],
      "rows": [["5", {"a": "False"}, {"a": "0"}, {"a": "1"}], ["12", {"a": "True"}, {"a": "12"}, {"a": "1"}], ["8", {"a": "False"}, {"a": "12"}, {"a": "2"}], ["15", {"a": "True"}, {"a": "27"}, {"a": "2"}]],
      "check": "def answers():\n    out = []\n    total = count = 0\n    for s in [5, 12, 8, 15]:\n        ok = s >= 10\n        if ok:\n            total += s\n        else:\n            count += 1\n        out += [ok, total, count]\n    return out",
      "explain": "달성한 날에만 total이 늘고, 미달인 날에만 count가 1씩 늘어요." },
    { "id": "s3", "kind": "mcq", "q": "마지막 return에 알맞은 것은?", "options": ["[total, count]", "[count, total]", "total + count", "total"], "answer": 0, "explain": "문제에서 [합계, 날 수] 순서로 돌려 달라고 했어요." }
  ],
  "explain": "조건(목표량 이상)에 맞는 날과 아닌 날을 if/else로 나누어 각각 누적합니다. '이상'은 >=, '초과'는 > 라는 점을 헷갈리지 않아야 해요."
}
```
