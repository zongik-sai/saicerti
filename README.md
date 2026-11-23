# saicerti · 자격증 코딩 연습

COS Pro Python 시험 유형을 **중간 점검(표 채우기·객관식) → 코드 풀이(자동 채점)** 순서로 연습하는 사이트.

- 주소: https://zongik-sai.github.io/saicerti/
- 과정: 프로그래밍 Python 기본(2급 유형 10개 × 5문제), 프로그래밍 Python 심화(1급 유형 10개 × 5문제)
- 모의고사: 과정마다 1~3회(원본 기출 10문항과 같은 유형·코드, 예시·숨은 테스트만 다름), 중간 점검 없이 풀고 시험을 끝내면 결과·해설 공개 — `src/content/<과정>/mock/tNN.json`(안내: `docs/MOCK_BRIEF.md`)
- 채점: 브라우저 안의 파이썬(Pyodide 0.29.5, 사이트에 직접 올림). 예시 + 숨은 테스트(문제마다 10개 이상). 코드는 서버로 가지 않음
- 기록: Google 로그인 후 Supabase `course_progress`(pyb·pya)에 문제별 진도만 저장. 코드 초안은 그 기기에만
- 선생님 메뉴(선생님 계정에만 보임): `#/teacher` 반 현황(과정별 진도), `#/admin` 교사 관리(계정 목록, 관리자만 교사·관리자 지정·해제 — 배움 숲과 같은 권한 목록이라 두 사이트에 함께 적용)

## 개발

```bash
npm ci
npm run dev            # http://localhost:5174 (개발용 데모 버튼 있음)
npm test               # 단위 테스트
python3 tools/validate.py   # 문제 100개 검수
npm run build          # public/pyodide/ 복사 후 빌드
BASE_PATH=/saicerti/ node scripts/verify-dist.mjs dist
```

문제 형식: `docs/CONTENT_SCHEMA.md` · 문제 만들기 안내: `docs/AGENT_BRIEF.md`

## 배포 (GitHub Pages)

1. 저장소 Settings → Pages → Source: **GitHub Actions**
2. Settings → Secrets and variables → Actions → **Variables**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` (배움 숲과 같은 공개 값. service_role/secret 키는 넣지 않음)
3. Supabase → Authentication → URL Configuration → Redirect URLs에 `https://zongik-sai.github.io/saicerti/` 추가
4. Supabase SQL Editor에서 saiedu 저장소의 `supabase/migrations/20261026000000_courses.sql` 실행(과목 목록에 pyb·pya 추가, 여러 번 실행해도 안전)
5. main에 push하면 자동 배포(타입·린트·단위 테스트·문제 검수·빌드 검증 통과 시)
