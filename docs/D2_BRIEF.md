# Data 분석 2급(d2) 문제 제작 안내 (작업자용)

선생님 요청(2026-11-28): YBM **DAT 2급(Python)** 시험지(PPT, 20문항)를 기준으로 Data 2급 과정을 만든다. 다른 과정처럼 유형마다 **[기본] 1~5**(필수, `src/content/d2/tNN.json`)와 **[심화] 1~5**(선택, `src/content/d2/adv/tNN.json`, 점점 어렵게)를 둔다. 학생은 사전 지식이 적은 고등학생이다.

먼저 읽을 것: `docs/CONTENT_SCHEMA.md`의 **중간 점검(steps)** 부분(표·객관식·단답 형식과 규칙 — d2도 똑같이 쓴다), `docs/ADV_BRIEF.md`(심화 난이도 사다리·중간 점검 늘리는 법). 아래 형식이 CONTENT_SCHEMA와 다르면 이 문서를 따른다.

## 시험 구성(원본 요약 — 문장을 베끼지 않는다)

50분, 20문항. 1~12번은 객관식 이론(4지선다), 13~20번은 pandas 코드(CSV 데이터를 읽고 `solution()`이 답을 반환). 코드 문항의 공통 틀:

```python
import pandas as pd

df = pd.read_csv("파일.csv")

def solution():
    answer = …
    print("solution 함수의 반환 값은 " + str(answer) + "입니다.")
    return answer
```
문제 끝에는 `※` 줄로 조건을 적는다(데이터 파일, solution()으로 반환, print로 중간 확인, "정답은 반올림하여 소수점 둘째 자리까지", "정답은 정수로" 등)와 `(정답 예시: 0.12)`.

| 유형 | typeTitle(정확히) | kind | 원본 문항(요약) | 핵심 |
|---|---|---|---|---|
| t01 | 데이터 분석의 이해 | choice | 1 빅데이터 시대의 직접적 이점(전수조사가 쉬워짐), 2 CRISP-DM 단계와 거리가 먼 것(데이터 비식별화), 7 DB에서 데이터를 뽑고 정제할 때 쓰는 것(쿼리) | 빅데이터 특징(3V 등)·이점, 분석 절차 CRISP-DM 6단계(업무 이해→데이터 이해→데이터 준비→모델링→평가→전개)와 단계별 활동, 데이터베이스 용어(테이블·스키마·쿼리·인덱스·SQL), 정형·반정형·비정형, 개인정보 비식별화 |
| t02 | 기초 통계와 분포 | choice | 3 상자그림에 나타나지 않는 통계량(산술평균), 4 오른쪽으로 꼬리가 긴 히스토그램 해석으로 틀린 것, 8 극단치 판별·처리와 거리가 먼 것 | 평균·중앙값·최빈값, 사분위수·IQR, 상자수염그림 구성, 왜도(꼬리 방향과 부호, 평균↔중앙값 위치)·첨도, 극단치(IQR×1.5, 표준점수) |
| t03 | pandas 기본 문법 | choice | 5 concat으로 이어 붙일 때 맞지 않으면 어긋나고 결측이 생기는 것(인덱스), 6 행·열 개수를 주는 속성(.shape), 9 문자열을 날짜로 바꾸는 함수(to_datetime) | DataFrame·Series, shape·size·ndim·columns·dtypes, head·info·describe, loc·iloc, concat·merge(인덱스·키 정렬과 NaN), to_datetime, value_counts, isna·notna, astype |
| t04 | 머신러닝 기초 | choice | 10 의사결정나무에서 모든 데이터가 든 첫 노드(뿌리 노드), 11 머신러닝 갈래가 아닌 것(교차학습), 12 실제값 대비 오차의 비율을 쓰는 지표(MAPE) | 지도·비지도·강화학습, 분류·회귀·군집, 의사결정나무 용어(뿌리·중간·말단 노드, 가지, 깊이, 불순도), 학습·평가 데이터 나누기, 과적합, MAE·MSE·RMSE·MAPE·정확도 |
| t05 | 집계해서 그래프 그리기 | write | 13 발견 연도를 10년 단위로 묶어(`year // 10 * 10`) 개수를 세고 막대그래프 | 파생 열(구간), groupby·value_counts·sum, sort_index, `.plot(kind="bar")`, `plt.show()` |
| t06 | 가장 많은 값 찾기 | blank | 14 가장 많이 발견한 사람(`value_counts().idxmax()`)을 찾고, 그 사람의 행만 골라(`loc`) 마지막 연도(`max`) | value_counts·idxmax·idxmin, 조건 필터 `df.loc[조건, ]`, max·min |
| t07 | 비율·구성비 구하기 | write | 15 개수가 많은 상위 3개 분류의 구성비(`value_counts()[:3].sum() / len(df)`), 18 두 분류에 속한 상품 중 남성 상품의 비율 | value_counts·슬라이싱, 조건 비율, isin, `normalize=True`, round |
| t08 | 파생 변수와 평균 | blank | 17 2차 카테고리가 HATS인 행만 골라, 할인율 = 1 − 할인가/판매가 열을 만들고 평균 | 조건 필터, 열 연산으로 새 열, mean, round |
| t09 | 결측치 다루기 | fix | 19 3차 카테고리가 **결측**인 행을 1차 카테고리별로 세어 가장 많은 개수 — 틀린 코드는 `notna()`(고칠 줄: `isna()`) | isna·notna·sum, 결측 행 고르기, value_counts·max, dropna·fillna |
| t10 | 검정과 군집 분석 | blank | 16 주 서식지가 5개인 행(`dist_5` 결측 아님)에서 2000년 전·후의 연도별 개수를 독립 2표본 t-검정(`scipy.stats.ttest_ind`)해 p-value, 20 할인율로 k-means 군집(군집 3개, seed 123) 후 가장 큰 군집의 크기(함수 작성) | ttest_ind(통계량, p-value), KMeans(n_clusters, random_state, n_init) fit·labels_, value_counts |

t10 안에서는 문제마다 `"kind": "write"`를 적어 함수 작성 문제를 섞어도 된다(기본 5문제 중 1~2개 정도). 다른 유형은 유형의 kind만 쓴다.

## 공통 규칙

- **원본과 똑같으면 안 된다**: 원본 문장·보기를 베끼지 않는다. 연습 문제는 상황·데이터·수치·보기를 새로 만든다(유형의 핵심 개념·기술은 같게). 5문제끼리, 기본과 심화끼리도 상황·질문이 겹치지 않게. 제목도 서로 다르게(2~30자).
- 문제 문장은 시험지 말투(합니다체), 중간 점검·해설은 해요체. 처음 나오는 용어(예: 사분위수, 결측치, p-value, 군집)는 중간 점검 질문·해설에서 쉬운 말로 풀어 준다.
- 사실이 정확해야 한다(통계·머신러닝 정의, pandas 2.x 동작). 애매한 보기(정답이 둘일 수 있는 보기)를 만들지 않는다.
- 난이도: [기본] a는 원본보다 살짝 쉽게, b~d 원본 수준, e 원본 수준 또는 살짝 어렵게. [심화] 1→5 점점 어렵게(ADV_BRIEF의 사다리), 중간 점검 6~9단계로 앞에서부터 디딤돌.

## 객관식 문제(choice) 형식

```jsonc
{
  "id": "d2-t02-a", "version": 1, "title": "상자그림에 없는 값",
  "statement": "한 반 학생 20명의 수학 점수를 상자수염그림으로 나타냈습니다. 상자수염그림만 보고 **알 수 없는** 값은 무엇입니까?",
  "choice": {
    "options": ["중앙값", "제1사분위수", "산술평균", "제3사분위수"],
    "answer": 2,
    "why": ["상자 안의 굵은 선이 중앙값이에요.", "상자의 아래쪽 끝이 제1사분위수(Q1)예요.", "평균은 상자그림에 그려지지 않아요(정답).", "상자의 위쪽 끝이 제3사분위수(Q3)예요."]
  },
  "steps": [ … 중간 점검(기본 3~6단계: 표 1개·객관식 1개 이상 / 심화 6~9단계: 표 2개·객관식 2개 이상) … ],
  "explain": "해설 2~4문장"
}
```
- 보기는 정확히 4개, `answer`는 0~3, `why`는 보기마다 왜 맞고 틀린지 한 문장(8자 이상). 정답 위치를 문제마다 고르게 섞는다.
- 그림이 필요하면(히스토그램·상자그림 등) `figures`에 `svg`(또는 `table`)로 그리고 설명 글에 한 줄 `{{fig:ID}}`(CONTENT_SCHEMA·`src/components/Figure.tsx` 참고). SVG는 `viewBox`를 쓰고 색은 `currentColor`·회색 계열로(밝은/어두운 화면 모두 보이게), 글자는 영어·숫자만.
- 중간 점검으로 개념을 쌓는다: 용어 뜻(mcq), 작은 수 목록으로 중앙값·사분위수·IQR·평균 계산(table·short), 작은 표(DataFrame)로 shape·loc 결과 예측(table), 작은 실제값·예측값 표로 MAE·MAPE 계산(table) 등. `check`의 `answers()`로 정답을 계산(파이썬 표준 라이브러리, pandas 사용 가능 — 브라우저와 같은 Pyodide의 pandas 2.3에서 실행됨).
- [심화] 객관식은 개념 두세 개를 묶거나(“옳은 것을 모두 고른 것: ㄱ·ㄴ·ㄷ”), 작은 계산(IQR 울타리, MAPE), 코드 결과 읽기(`df.shape`, `concat` 결과의 NaN 개수) 같은 한 단계 깊은 문제.

## 데이터 코드 문제(blank·fix·write) 형식

```jsonc
{
  "id": "d2-t08-a", "version": 1, "title": "회원 주문의 평균 금액",
  "statement": "카페 주문 데이터에서 회원(member가 Y)의 주문만 골라 주문 금액(가격 × 수량)의 평균을 구하려고 합니다.\n\n※ 데이터는 \"cafe_orders.csv\"를 사용하시오.\n※ 주문 금액은 \"amount\" 변수로 만드시오.\n※ 정답은 사용자 정의 함수 solution()을 통하여 반환되도록 하시오.\n※ 중간 결과물 출력은 solution() 함수 내 print() 함수를 활용하여 확인하시오.\n※ 정답은 반올림하여 소수점 둘째 자리까지 반환하도록 하시오.",
  "answerFormat": "0.12",
  "data": { "files": ["cafe_orders.csv"] },
  "code": "import pandas as pd\n\ndf = pd.read_csv(\"cafe_orders.csv\")\n\ndf_sub = df.loc[df[\"member\"] == ⟦1⟧, ].copy()\ndf_sub[\"amount\"] = df_sub[\"price\"] ⟦2⟧ df_sub[\"qty\"]\n\ndef solution():\n    answer = round(df_sub[\"amount\"].⟦3⟧(), 2)\n    print(\"solution 함수의 반환 값은 \" + str(answer) + \"입니다.\")\n    return answer",
  "blanks": [{ "answer": "\"Y\"" }, { "answer": "*" }, { "answer": "mean" }],
  "solution": "… ⟦n⟧을 정답으로 바꾼 전체 코드(줄마다 같게) …",
  "examples": [{ "data": 0 }],
  "tests": [{ "data": 1 }, { "data": 2 }],
  "steps": [ … ],
  "explain": "해설 2~4문장"
}
```
- `data.files`: 읽는 CSV(아래 목록). 처음 코드의 `read_csv` 줄에 그 이름이 그대로 있어야 한다.
- 채점: 예시 데이터(변형 0)와 같은 열·같은 규칙에 값만 다른 숨은 데이터(변형 1·2)에서 각각 코드를 새로 실행해 `solution()`의 반환값을 정답 코드의 값과 비교한다(정수 기댓값은 12.0도 맞게 봄, 실수는 아주 작은 오차만 허용 → 반올림 자리를 문제에 꼭 적는다). **examples·tests의 expected는 손으로 쓰지 말고 `--fill`로 채운다**.
- 정답은 정수·실수·문자열 하나. 데이터마다 정답이 달라지는 질문으로(세 변형의 정답이 모두 같으면 검수에서 막힘 — 값을 외워도 통과하니까). 동점(가장 많은 것이 둘)이나 반올림 경계(…5)에 걸리지 않는지 세 변형 모두 확인한다.
- blank: 빈칸 2~5개(심화 3~8개)를 조건 값·함수 이름·연산자·인덱싱 같은 핵심 자리에. fix: 정확히 한 줄만 틀리게(예: notna↔isna, `<`↔`<=`, mean↔sum, 잘못된 열 이름 말고 **논리 버그**), 틀린 코드는 예시 데이터에서 틀린 값을 내야 함(오류로 멈추는 버그 금지), `bugLine`(1부터). write: `def solution():` 안에 `answer = 1`·print·return 정도의 틀만(원본처럼 import와 read_csv는 위에 둔다).
- 쓸 수 있는 모듈: pandas, numpy, matplotlib, scipy, sklearn, math.
- 그래프 문제(t05): `"data": {"files": [...], "plot": true}`, `answerFormat` 없음. `solution()`이 막대(또는 선) 그래프를 그리고 `plt.show()`. 채점은 그래프의 막대 이름표(x)와 높이(y)를 정답 그래프와 비교한다(그리는 방법이 달라도 모양이 같으면 정답). 문제에 무엇을 세고/더하는지, x축 순서(예: 오름차순)를 분명히 적는다. 이름표·제목에 한글을 쓰지 않는다(그림 글꼴에 한글 없음). 정답 그래프 그림을 시험지처럼 보여 주고 싶으면 `figures`에 `table`로 x·y 값을 적는다(정확한 값 대신 모양만 알려도 됨).
- t-검정: `from scipy.stats import ttest_ind`, `stat, p = ttest_ind(a, b)`(기본 등분산 가정). 문제에 두 집단을 무엇으로 나누는지, 무엇을 비교하는지, p-value 반올림 자리(보통 넷째 자리)를 적는다.
- 군집: `from sklearn.cluster import KMeans`, `KMeans(n_clusters=3, random_state=123, n_init=10)` — 문제에 군집 수·seed(random_state)·`n_init=10`·쓰는 열을 모두 적는다. 답은 가장 큰(작은) 군집의 크기, 특정 행이 속한 군집의 크기처럼 라벨 번호에 따라 달라지지 않는 값으로.

### 연습용 데이터(모두 지어낸 데이터, `public/data/d2/`, 개요: `src/datasets/d2.json`)

| 파일 | 내용(행 수) | 주요 열 |
|---|---|---|
| cafe_orders.csv | 카페 주문(2,500) | date, hour, store(4), menu(13), category(coffee·tea·dessert·juice), price, qty, member(Y·N), rating(1~5, 결측 약 30%) |
| bike_rentals.csv | 공공 자전거 대여(3,000) | date, hour, station(12), district(4), user_type(member·guest), age_group(결측 있음), minutes, distance_km |
| student_scores.csv | 학생 성적(900) | grade, class, gender, club(결측 = 동아리 없음), math, korean, english, science(결측 = 결시), study_hours, absences |
| movies.csv | 영화(1,500) | title, genre(8), country(6), release_year, running_time, audience, rating(결측 있음), director |
| weather_daily.csv | 5개 도시 하루 날씨(1,830) | date(YYYY-MM-DD, 변형마다 연도가 다름), city, temp_max, temp_min, rain_mm(결측 있음), humidity, wind_speed(결측 있음) |
| customers.csv | 쇼핑몰 고객(1,200) | age, gender, region, membership(basic·silver·gold), annual_spend(만 원), visits_per_month, app_user — 구매 금액·방문 횟수에 뚜렷한 세 무리(군집 문제에 알맞음) |
| used_cars.csv | 중고차 매물(1,600) | brand(8), model, year, mileage_km, fuel(결측 있음), transmission, price(만 원), accident(Y·N) |
| spyder.csv · shop_products.csv | **모의고사 전용**(원본 상황) | 연습 문제에는 쓰지 않는다 |

열 이름·값은 `python3 -c "import pandas as pd; d=pd.read_csv('public/data/d2/cafe_orders.csv'); print(d.head()); print(d.describe(include='all'))"`처럼 직접 확인한다(로컬 pandas는 3.x라 출력 모양이 조금 다를 수 있다 — 정답 계산은 늘 검수 도구가 Pyodide의 pandas 2.3으로 한다).

## 중간 점검(코드 문제)

흐름 예: ① 문제 이해(mcq: 무엇을 고르고 무엇을 세는지) → ② 작은 표로 따라가기(table: 질문에 5~8행짜리 작은 표를 직접 적고, 필터·새 열·집계 결과를 채우게) → ③ 필요한 pandas 기능 고르기(mcq: `value_counts()` vs `count()`, `isna()` vs `notna()`) → ④ 핵심 코드 결정(short/mcq: 조건식·함수 이름, 코드 조각을 질문에 직접 적는다) → (심화) 예시 데이터의 중간 값 예측(short: 예시 데이터에서 조건에 맞는 행 수 — `check`가 `pd.read_csv("cafe_orders.csv")`로 계산). 코드를 봐야 풀리는 단계에는 `"code": "start"`. 빈칸 번호(⟦1⟧)는 중간 점검에 쓰지 않는다. 한 줄 수정에서 고친 코드는 '어떻게 고칠까요?' 단계보다 먼저 알려 주지 않는다.

## 작업 방법

1. 스크래치 폴더 `/tmp/claude-0/-home-claude/f9ff8c2b-5b59-50ab-b880-76e35968603d/scratchpad/gen/d2-tNN/`에 **파이썬 생성 스크립트**를 만들어 JSON을 쓴다(`ensure_ascii=False, indent=1`). 코드 문자열의 따옴표·줄바꿈 실수를 막는다.
2. 데이터 문제는 `python3 tools/validate.py --fill src/content/d2/tNN.json`(정답 코드로 expected를 채운 뒤 검수) → 이후 수정마다 `python3 tools/validate.py src/content/d2/tNN.json`이 `✓ 문제 5개 검수 통과`가 될 때까지 고친다(처음 실행은 Pyodide를 띄우느라 10초쯤 걸린다). 생성 스크립트를 다시 돌리면 expected가 지워지니 다시 `--fill`.
3. [기본] 파일을 먼저 끝내고, 같은 kind·typeTitle로 [심화] `src/content/d2/adv/tNN.json`(id `d2-tNN-adv1`~`adv5`)을 만든다.
4. 스스로 점검: 설명만 읽고 답(코드)을 낼 수 있는가? 객관식 정답이 하나뿐이고 사실이 정확한가? 1→5로 정말 어려워지는가? 중간 점검을 차례로 풀면 답을 낼 수 있겠는가?
5. 다른 파일은 건드리지 않는다. git 명령은 하지 않는다.

## 보고(마지막 메시지, 한국어, 8줄 이내)
- 파일 경로와 검수 결과 한 줄
- [기본]·[심화] 제목을 한 줄로
- 걱정되는 점(있으면)
