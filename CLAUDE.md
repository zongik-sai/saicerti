# saicerti 프로젝트 규칙

- 자격증 코딩 연습 사이트. 지금 과정: 프로그래밍 Python 기본(pyb, COS Pro 2급 Python 유형), 프로그래밍 Python 심화(pya, COS Pro 1급 Python 유형). C언어·Data 과정은 나중에.
- 문제는 원본 기출과 형식·난이도가 비슷하지만 똑같지 않게 만든다(문장·상황·수치를 새로). 원본 문제·구름(goorm) 콘텐츠를 그대로 옮기지 않는다.
- 문제 데이터는 `src/content/<과정>/tNN.json`(형식: docs/CONTENT_SCHEMA.md). 문제 id(`pyb-t01-a`)는 진도 키라 바꾸지 않는다. 내용을 고치면 version을 올린다.
- 문제를 바꾸면 반드시 `python3 tools/validate.py`(정답·테스트·빈칸·한 줄 수정·중간 점검 정답 검수)와 `npm test`를 통과시킨다.
- 채점은 브라우저 안의 Pyodide(`public/pyworker.js` + `src/grader/harness.py`)로만 한다. 학생 코드를 서버로 보내거나 저장하지 않는다. 검수 도구와 브라우저는 같은 harness.py를 쓴다.
- 문제마다 흐름: 문제 읽기 → 중간 점검(표 채우기·객관식·단답, 다 맞혀야 다음) → 코드 풀이(빈칸 채우기 / 한 줄 수정(정확히 한 줄만 바뀌어야 채점) / 함수 작성) → 예시 실행·전체 채점.
- 배움 숲(saiedu)과 같은 사이트(zongik-sai.github.io)·같은 Supabase 프로젝트를 쓴다: localStorage 접두사 `saicerti:v1:`, 로그인 저장 키 `saicerti-auth`를 바꾸지 않는다(서로의 기록·로그인을 건드리지 않게).
- 서버 표는 saiedu의 `course_progress`(과목 pyb·pya)와 `save_course_progress`·`course_class_overview`·`am_i_teacher`를 쓴다. 과목 목록 SQL은 saiedu 저장소 `supabase/migrations/20261026000000_courses.sql`이 기준이다.
- 클라이언트에 service_role/secret 키를 넣지 않는다. Google 로그인은 진짜 OAuth(루트 callback + HashRouter).
- 개발용 데모는 `npm run dev`에서만, 화면에 '개발용 데모'로 표시한다. 운영 빌드는 데모를 거부한다.
- 집중 모드(전체화면 잠금)는 이 사이트에 두지 않는다.
- 학생은 사전 지식이 적다: 처음 나오는 용어는 중간 점검 질문·해설에서 짧게 풀어 준다. 문제 문장은 시험지 말투(합니다체), 중간 점검은 해요체.
- 구현/실행/검증한 것과 미검증인 것을 구별해 보고한다. 사용자에게는 한국어로만 말한다.
