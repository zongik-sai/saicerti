# saicerti · 자격증 코딩 연습

COS Pro Python·C 시험 유형을 **중간 점검(표 채우기·객관식) → 코드 풀이(자동 채점)** 순서로 연습하는 사이트.

- 주소: https://zongik-sai.github.io/saicerti/
- 과정: 프로그래밍 Python 기본(2급 유형 10개 × 5문제), 프로그래밍 Python 심화(1급 유형 10개 × 5문제), 프로그래밍 C 기본(COS Pro 2급 C 유형 10개 × 5문제)
- 유형마다 [기본] 1~5(필수)와 [심화] 1~5(선택, 주황색): 심화는 1→5로 점점 어렵고 중간 점검 6~9단계, 그 유형의 기본 5문제를 모두 푼 뒤 '심화 열기'로 들어감 — `src/content/<과정>/adv/tNN.json`(안내: `docs/ADV_BRIEF.md`)
- 모의고사: 기본 50문제를 모두 풀면 열림(과정 화면 맨 아래), 과정마다 1~3회(원본 기출 10문항과 같은 유형·코드, 예시·숨은 테스트만 다름), 중간 점검 없이 풀고 시험을 끝내면 결과·해설 공개 — `src/content/<과정>/mock/tNN.json`(안내: `docs/MOCK_BRIEF.md`)
- 채점: 브라우저 안의 파이썬(Pyodide 0.29.5, 사이트에 직접 올림). 예시 + 숨은 테스트(문제마다 10개 이상). 코드는 서버로 가지 않음
- C 채점: 같은 워커에서 C 인터프리터(`src/grader/cinterp.py`, pycparser 3.12)로 실행 — 범위 밖 접근·초기화 안 한 값·무한 반복을 한국어로 알려 줌. 검수 도구가 gcc(-fsanitize)와 결과를 대조
- 그림: 시험지의 이미지(배열 칸·격자·표·도형)는 사진 대신 `figures` 데이터로 다시 그림(확대·다크 모드·화면 읽기 대응) — `src/components/Figure.tsx`
- 기록: Google 로그인 후 Supabase `course_progress`(pyb·pya·cb)에 문제별 진도만 저장. 코드 초안은 그 기기에만
- 로그인 없이도 문제·모의고사를 풀 수 있음: 기록·초안은 그 브라우저에만(`saicerti:v1:guest:`), 서버·선생님 화면에는 가지 않고 로그인해도 계정 기록과 합치지 않음
- 선생님 메뉴(선생님 계정에만 보임): `#/teacher` 반 현황(과정별 진도), `#/admin` 교사 관리(계정 목록, 관리자만 교사·관리자 지정·해제 — 배움 숲과 같은 권한 목록이라 두 사이트에 함께 적용)

## 개발

```bash
npm ci
npm run dev            # http://localhost:5174 (개발용 데모 버튼 있음)
npm test               # 단위 테스트
python3 tools/validate.py   # 문제 240개 검수(C는 gcc 대조)
python3 tools/test_cinterp.py  # C 인터프리터 회귀 테스트(gcc 필요)
npm run build          # public/pyodide/ 복사 후 빌드
BASE_PATH=/saicerti/ node scripts/verify-dist.mjs dist
```

문제 형식: `docs/CONTENT_SCHEMA.md` · 문제 만들기 안내: `docs/AGENT_BRIEF.md`(C: `docs/AGENT_BRIEF_C.md`) · C 인터프리터 명세: `docs/CINTERP_SPEC.md`

## 배포 (GitHub Pages)

1. 저장소 Settings → Pages → Source: **GitHub Actions**
2. Settings → Secrets and variables → Actions → **Variables**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` (배움 숲과 같은 공개 값. service_role/secret 키는 넣지 않음)
3. Supabase → Authentication → URL Configuration → Redirect URLs에 `https://zongik-sai.github.io/saicerti/` 추가
4. Supabase SQL Editor에서 saiedu 저장소의 `supabase/migrations/20261026000000_courses.sql` 실행(과목 목록에 pyb·pya·cb·ca 추가, 여러 번 실행해도 안전)
5. main에 push하면 자동 배포(타입·린트·단위 테스트·문제 검수·빌드 검증 통과 시)
