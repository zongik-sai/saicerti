# C 과정 문제 제작 안내 (작업자용) — 프로그래밍 C 기본(cb, COS Pro 2급 C)

파이썬 과정과 같은 사이트·같은 데이터 형식이다. 먼저 `docs/CONTENT_SCHEMA.md`, 연습 문제면 `docs/AGENT_BRIEF.md`, 모의고사면 `docs/MOCK_BRIEF.md`를 읽고, **아래 C 차이점**을 지킨다. 참고로 파이썬 2급 연습 파일 `src/content/pyb/tNN.json`의 구성·중간 점검 흐름을 본보기로 삼아도 된다.

## 원본
COS Pro 2급 C 시험 화면 받아쓰기: `/tmp/claude-0/-home-claude/f9ff8c2b-5b59-50ab-b880-76e35968603d/scratchpad/cpages/transcript.md` (문제 01~10, 사진 p00~p25.jpg가 같은 폴더에 있으니 헷갈리면 사진을 직접 본다). 원문은 내부 참고용이며 그대로 옮겨 공개하지 않는다.

## 파일
- 연습: `src/content/cb/tNN.json` (문제 5개 a~e, id `cb-tNN-a`) / 모의고사: `src/content/cb/mock/tNN.json` (문제 3개, id `cb-m1-tNN`~`cb-m3-tNN`, steps `[]`)
- 파일 머리에 `"course": "cb"`, **`"lang": "c"`** 를 꼭 넣는다.

## C 코드 규칙
- `code`·`solution`은 C 소스: 필요한 `#include <stdio.h>`·`<stdlib.h>`·`<string.h>`·`<stdbool.h>`·`<math.h>`·`<ctype.h>`를 맨 위에, 그다음 보조 함수와 `solution`. **main 함수는 넣지 않는다**(채점기가 solution을 직접 부름. 시험 화면의 테스트 출력용 main은 빼도 된다).
- COS Pro C 관례대로 배열은 `int arr[], int arr_len`(또는 `size_t arr_len`), 2차원은 `int arr[][5]`, 문자열은 `char* s`, 문자열 배열은 `char* words[], int words_len`, 배열을 돌려줄 때는 `int*` + `malloc`.
- 값은 ASCII만(한글 문자열 금지: C의 char 단위 처리와 맞지 않음). 정수는 int 범위(±2,147,483,647) 안, 실수 반환은 `"compare": "float"`.
- 들여쓰기는 공백 4칸, 중괄호 스타일은 원본처럼.

## 채점 정보 `cspec`
- `argNames`와 각 테스트의 `args`에는 **시험지 예시 표에 보이는 매개변수만** 순서대로 넣는다. 길이 매개변수(예: `arr_len`)는 숨기고 `cspec.derived`로 채운다:
  `"cspec": {"derived": {"arr_len": "len(arr)"}}` (허용: `len(이름)`, `len(이름[0])`, 정수)
- 배열(포인터)을 return 하면 길이를 적는다: `"cspec": {"ret": {"len": "2"}}` 또는 `{"len": "arr_len"}`. `char*`(문자열) return은 길이 필요 없음. `bool` return은 기댓값을 true/false로.
- 예시 표는 C 표기로 보인다: 배열 `{1, 2, 3}`, 문자열 `"abc"`, 참/거짓 `true/false`.

## 그림(원본의 이미지)
사진 대신 **데이터로 다시 그린다**: 문제(또는 중간 점검)에 `figures` 배열을 두고, 설명 글에서 그 자리에 **한 줄짜리** `{{fig:f1}}`을 쓴다.
- 1차원 배열·수열·칸: `{"id": "f1", "kind": "cells", "alt": "그림 설명(화면 읽기용, 그림의 모든 정보를 문장으로)", "caption": "선택", "index": "auto"(0부터)|"auto1"(1부터)|[직접], "values": [0, 1, 1, 2], "highlight": [0, 1], "dim": [], "marks": [{"at": 3, "label": "i"}], "groups": [{"from": 0, "to": 2, "label": "3"}](칸 아래 중괄호 묶음+글자, 구간 길이 표시 등), "arrows": [{"from": 0, "to": 2, "label": "+1"}](칸 아래 화살표+글자, 영향·이동 표시)}`
- 2차원 배열·격자·보드: `{"id": "f2", "kind": "grid", "alt": "…", "rows": [[1, 2], [3, 4]], "rowLabels": ["0행", "1행"], "colLabels": ["0열", "1열"], "highlight": [[0, 1]], "dim": [[1, 0]]}`
- 표(머리 있음): `{"id": "f3", "kind": "table", "alt": "…", "head": ["이름", "점수"], "rows": [["A", 90]], "highlight": [0]}`
- 위로 안 되는 도형(트리·그래프·좌표·화살표 흐름 등)만 `{"id": "f4", "kind": "svg", "alt": "…", "svg": "<svg viewBox='0 0 300 120' xmlns='http://www.w3.org/2000/svg'>…</svg>"}` — 색은 `currentColor`와 `fill='none'`·`stroke='currentColor'`만, 강조는 `stroke-width`·점선·굵게로(다크 모드에서도 보이게). 글자는 `<text>`(fill 지정 없이). 스크립트·링크·이미지 금지. 폭 600 이하.
- `alt`는 그림을 못 보는 학생도 문제를 풀 수 있을 만큼 구체적으로. 그림에 강조(색칠)가 의미를 가지면 `highlight`로 옮기고 설명 글에도 말로 적는다.
- 원본에 그림이 있으면 모의고사는 같은 그림 구조에 회차 수치만 바꾸고, 연습 문제는 새 상황에 맞는 그림을 만든다(그림이 이해에 도움이 되면 원본에 없어도 넣어도 됨).

## 중간 점검(연습 문제만)
- 파이썬 과정과 같은 흐름(문제 이해 mcq → 표로 따라가기 → 핵심 결정 → 경계). 표 칸 정답은 C 표기: 문자 `'a'`, 문자열 `"ab"`, 참/거짓은 `1`/`0`(alts에 `true`/`false`도), 배열은 `{1, 2}`(alts에 `[1, 2]`도).
- `check`의 `answers()`는 **Python**으로 계산한다(C 코드를 Python으로 옮겨 계산). C의 정수 나눗셈(0 쪽 버림)·나머지 부호·char 산술에 주의.
- C를 처음 배우는 학생: 포인터·malloc·`\0`(널 문자)·`size_t` 같은 말은 처음 나올 때 해설에 짧게 풀어 준다.

## 검수
- 기댓값은 생성 스크립트에서 **gcc로 컴파일한 정답 코드**로 만든다(작은 main을 생성해 테스트 입력을 넣고 결과를 출력 → 읽기). gcc는 `gcc -O0 -fsanitize=address,undefined -w`로, 생성 파일은 스크래치 폴더에.
- 자체 점검도 gcc로: blank는 빈칸 정답을 넣은 코드가 정답 코드와 같고 통과, fix는 처음 코드가 예시에서 틀리고(무한 반복·충돌 없이) 정답 코드와 정확히 한 줄만 다름, write는 처음 틀이 컴파일되고 테스트에서 틀림.
- 마지막에 `python3 tools/validate.py src/content/cb/tNN.json src/content/cb/mock/tNN.json`을 돌린다. 브라우저용 C 인터프리터(`src/grader/cinterp.py`)와 gcc 대조기(`tools/cref.py`)는 다른 작업자가 만드는 중이라, 아직 없으면 관련 오류("정답 실행 실패", "gcc 대조 실행 실패")만 남을 수 있다 — 그 밖의 오류는 모두 고친다. 남은 오류는 보고에 그대로 적는다.
