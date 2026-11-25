# C 채점기(cinterp) 명세

saicerti의 C 과정(프로그래밍 C 기본 = COS Pro 2급 C 유형)은 **브라우저 안의 Pyodide에서 도는 C 인터프리터**로 채점한다(학생 코드를 서버로 보내지 않음). 같은 파일을 검수 도구(CPython)에서도 쓰고, 검수 도구는 **gcc로 컴파일한 결과와 대조**해 인터프리터를 검증한다.

## 파일
- `src/grader/cinterp.py` — 인터프리터(순수 Python 3.11+, 의존: pycparser 3.12만. 경로: `src/grader/vendor/pycparser-3.12-py3-none-any.whl`을 sys.path에 넣고 import)
- `src/grader/harness.py`의 `run_cases_c(code, func, cases_json, mode='exact', spec_json='{}')` — `run_cases`와 **같은 JSON 결과 모양**(`compile`, `results[{ok, got, error}]`, `stdout`, `stdoutCut`)을 돌려준다. `same()` 비교 함수를 그대로 쓴다.
- `tools/test_cinterp.py` — 회귀 테스트: C 예제 묶음을 gcc(-O0 -fsanitize=address,undefined)와 인터프리터로 각각 실행해 출력이 같은지 확인. `python3 tools/test_cinterp.py` → 모두 통과해야 함.

## 지원 범위(COS Pro 2급 C 수준, 필요하면 1급 일부)
- 전처리: 주석 제거(문자열 안은 그대로), `#include <stdio.h|stdlib.h|string.h|stdbool.h|math.h|ctype.h|limits.h|stddef.h|stdint.h>` 허용(그 밖은 컴파일 오류), 객체형 `#define NAME 값`. 함수형 매크로는 '지원하지 않음' 오류.
- 미리 정의: `size_t`(unsigned 64비트), `bool`/`true`/`false`, `NULL`, `INT_MAX`/`INT_MIN`/`LLONG_MAX` 등 limits.h 상수.
- 타입: char(부호 있는 8비트), short, int(32비트), long/long long(64비트), unsigned 계열, float/double, bool, 포인터, 배열(다차원), struct(typedef 포함, 중첩, 배열 필드), 함수 포인터(qsort 비교 함수용).
- 정수 의미: C와 같게 — 나눗셈은 0 쪽으로 버림, `%` 부호는 피제수, 오버플로는 비트 수만큼 감아 돌림(wrap), 부호 없는 수 비교·감소(0에서 1 빼면 큰 수), 정수 승격·일반 산술 변환(한쪽이 double이면 double, long long, unsigned …), char 산술, 비트 연산·시프트.
- 실수: printf `%f`·`%.2f`·`%lf`·`%g`, 정수→실수 변환, 실수→정수 캐스트는 버림.
- 문장: 선언(초기화 목록, 중첩 `{}`, 문자열로 char 배열 초기화, 크기 생략 배열), if/else, for/while/do-while, switch/case/default(fall-through), break/continue/return, 삼항, 쉼표, 복합 대입, 전위·후위 ++/--, `&`·`*`, `sizeof`(타입·식), 캐스트, `.`·`->`, 전역 변수(0으로 초기화), static 지역 변수.
- 메모리: 블록(바이트 단위 크기) + 포인터(블록, 바이트 오프셋, 가리키는 타입). sizeof: char 1, short 2, int 4, long/long long/size_t/포인터 8, float 4, double 8, struct는 필드 합(정렬 패딩은 gcc x86-64와 같게 맞추면 더 좋음). malloc/calloc/realloc/free, 문자열 리터럴(읽기 전용), 범위 밖 접근·해제된 블록 접근·NULL 역참조는 **한국어 런타임 오류**로 멈춤(예: "배열(메모리) 범위를 벗어났어요: arr[5] (크기 5)").
- **초기화하지 않은 지역 변수·배열·malloc 영역을 읽으면** 런타임 오류("초기화하지 않은 값을 읽었어요: answer")로 멈춘다(실제 C의 쓰레기값 대신, 디버깅 문제의 '초기화 빠짐' 버그가 드러나도록). 전역·static·calloc·`= {0}`은 0.
- 라이브러리: printf(`%d %i %u %ld %lld %lu %zu %c %s %f %lf %.Nf %e %g %x %X %o %%`, 폭·`-`·`0` 플래그), puts, putchar, sprintf, strlen, strcpy, strncpy, strcat, strncat, strcmp, strncmp, strchr, strrchr, strstr, memset, memcpy, memmove, malloc, calloc, realloc, free, abs, labs, llabs, atoi, atol, qsort(비교 함수 포인터), rand/srand(결정적 LCG), exit, sqrt, pow, fabs, floor, ceil, round, fmin, fmax, log, exp, sin, cos, toupper, tolower, isdigit, isalpha, isalnum, isupper, islower, isspace, ispunct. 그 밖의 함수를 부르면 컴파일 오류 "지원하지 않는 함수: xxx".
- 재귀(깊이 제한 2000, 넘으면 "재귀가 너무 깊어요"), 실행 단계 제한(기본 2,000만 단계 넘으면 "시간 초과: 반복이 끝나지 않아요") — 브라우저는 별도로 워커 시간 제한도 있음.
- 오류 메시지: 컴파일 오류는 pycparser 메시지를 줄 번호와 함께 한국어 안내로(예: "문법 오류(3번째 줄): 세미콜론(;)이나 괄호를 확인해 보세요 — 원문: …"). 선언 안 된 이름 사용, 인자 수 불일치, 타입이 맞지 않는 대입(예: 포인터에 정수) 정도는 컴파일 단계에서 잡는다.

## 성능
- AST를 **한 번 Python 클로저로 컴파일**한 뒤 실행(노드마다 isinstance 분기하는 느린 방문자 대신). 목표: CPython에서 단순 for 루프 100만 번 ≤ 2초.

## 채점 연결(run_cases_c)
- `func`(보통 `solution`)의 매개변수 선언에서 타입을 읽어, 테스트의 `args`(JSON)를 C 값으로 바꿔 넣는다. **C 문제의 args는 C 함수의 매개변수를 순서대로 모두** 담는다(배열 길이 매개변수도 따로 값으로).
  - 정수·실수·char(길이 1 문자열 또는 정수) → 스칼라
  - `int arr[]` / `int* arr` / `double*` … ← JSON 리스트 → 새 블록
  - `int arr[][N]` ← 리스트의 리스트(행 길이 N) → 평평한 블록 / `int** arr` ← 리스트의 리스트 → 행 포인터 배열
  - `char* s` / `char s[]` / `const char*` ← 문자열 → 널 종료 char 블록(쓰기 가능 복사본)
  - `char* words[]` / `char** words` ← 문자열 리스트
  - `bool` ← true/false
- 반환값: 정수 → int, 실수 → float, bool → JSON true/false, `char*` → 널 종료까지 읽은 문자열, `int*`·`double*` → `spec.ret.len`(정수 또는 매개변수 이름 또는 `"매개변수이름*2"` 같은 간단 식) 개수만큼 읽은 리스트, `char**` → 같은 방식으로 문자열 리스트.
- 테스트마다 전역 상태를 처음으로 되돌린다(전역 변수 재초기화). printf 출력은 stdout으로 모은다(최대 6000자).
- `main` 함수가 있어도 채점에서는 부르지 않는다.

## 검수 도구 연동(tools/validate.py에서 사용)
- `tools/cref.py`(gcc 대조): 같은 `args`·반환 규칙으로 C 테스트 main을 **생성**해 학생 코드(정답 코드)와 함께 gcc로 컴파일·실행하고 결과(JSON 한 줄씩)를 돌려준다. `-fsanitize=address,undefined`로 범위 밖 접근 등을 잡는다. 생성 main은 `printf`로 결과를 JSON 모양으로 출력.
- validate.py는 C 문제(`lang: "c"`)에서 정답 코드를 **인터프리터와 gcc 둘 다**로 돌려 기댓값과 같은지 확인한다.
