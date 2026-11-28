#!/usr/bin/env python3
"""saicerti 문제 검수 도구.

사용: python3 tools/validate.py [--fill] [파일 또는 폴더 ...]   (기본: src/content)
- Data 2급(src/content/d2/)은 tools/validate_d2.py가 검수한다(--fill: 데이터 문제의 expected를 정답 코드로 채움)
- 형식(스키마) 검사
- 정답 코드가 예시·숨은 테스트를 모두 통과하는지(브라우저와 같은 src/grader/harness.py로 실행)
- 빈칸: 정답을 넣은 코드 == 정답 코드, 그리고 통과
- 한 줄 수정: 처음 코드와 정답 코드가 정확히 한 줄만 다르고, 처음 코드는 예시에서 틀림
- 함수 작성: 처음(빈) 코드는 테스트에서 틀림
- 입력 조건(inputCheck)이 모든 예시·테스트에서 참
- 중간 점검 표·단답의 정답이 check 코드의 계산과 같음
- 심화 문제(src/content/<과정>/adv/tNN.json, id <과정>-tNN-adv1~adv5): 기본 유형과 같은 형식(kind),
  중간 점검 6~9단계(표 2개·객관식 2개 이상), 숨은 테스트 12개 이상
실패가 하나라도 있으면 종료 코드 1.
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, 'src', 'grader', 'harness.py')
MARK = re.compile(r'⟦(\d+)⟧')
IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
ERRORS = []


def err(where, msg):
    ERRORS.append(f'{where}: {msg}')


CTX = {'lang': 'python'}
# 함수 정의 찾기: 파이썬 def f( / C 반환형 f(
FUNC_DEF = {'python': r'def\s+{f}\s*\(', 'c': r'[\w\*]\s+\**{f}\s*\('}


def run_harness(code, func, cases, mode, spec=None):
    # C 문제(lang=c)는 같은 harness의 run_cases_c(브라우저와 같은 인터프리터)로 실행
    req = json.dumps({'code': code, 'func': func, 'cases': cases, 'mode': mode, 'lang': CTX['lang'], 'spec': spec or {}})
    try:
        p = subprocess.run([sys.executable, '-I', HARNESS], input=req, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return None, '시간 초과(20초)'
    if p.returncode != 0:
        return None, p.stderr[-800:]
    try:
        return json.loads(p.stdout), None
    except Exception:
        return None, 'harness 출력 해석 실패: ' + p.stdout[-300:]


def run_py(src, timeout=20):
    """src를 실행하고 마지막에 RESULT 변수를 JSON으로 출력."""
    prog = src + '\nimport json as _j, sys as _s\n_s.stdout.write("\\n@@RESULT@@" + _j.dumps(RESULT, ensure_ascii=False, default=str))\n'
    try:
        p = subprocess.run([sys.executable, '-I', '-c', prog], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, '시간 초과'
    if p.returncode != 0:
        return None, p.stderr[-800:]
    if '@@RESULT@@' not in p.stdout:
        return None, '결과 없음'
    return json.loads(p.stdout.rsplit('@@RESULT@@', 1)[1]), None


def norm_cell(s):
    return re.sub(r'\s+', '', str(s)).replace('"', "'")


def lines(code):
    return [l.rstrip() for l in code.rstrip('\n').split('\n')]


# 코드를 보고 푸는 단계: 질문 위에 처음 코드가 보이도록 "code": "start"가 있어야 한다(선생님 요청 2026-11-27)
NEEDS_CODE = {
    'fix': re.compile(r'틀린 코드|처음 코드|지금 코드|\d+\s*번(째)?\s*줄|어느 줄|어떤 줄|틀린 줄|틀린 return|틀린 func|틀린 함수'),
    'blank': re.compile(r'빈칸\s*\d|처음 코드'),
    'write': re.compile(r'처음 코드'),
}


def check_steps(where, p, adv=False, kind=None):
    steps = p.get('steps')
    lo, hi = (6, 9) if adv else (3, 6)
    if not isinstance(steps, list) or not (lo <= len(steps) <= hi):
        err(where, f'steps는 {lo}~{hi}개' + ('(심화 문제)' if adv else ''))
        return
    ids = set()
    kinds = []
    for i, s in enumerate(steps):
        w = f'{where} step{i + 1}'
        if not isinstance(s, dict):
            err(w, '객체가 아님')
            continue
        if MARK.search(json.dumps({k_: v_ for k_, v_ in s.items() if k_ != 'check'}, ensure_ascii=False)):
            err(w, '중간 점검에 빈칸 번호(⟦1⟧ 등)를 쓰지 말 것 — 질문만 읽고 풀리게 코드 조각을 직접 적는다')
        if 'code' in s and s['code'] != 'start':
            err(w, 'code는 "start"만 쓸 수 있음(질문 위에 처음 코드를 보여 줌)')
        shown_text = ' '.join(str(s.get(k_, '')) for k_ in ('title', 'q', 'prompt')) + ' ' + ' '.join(map(str, s.get('options', [])))
        if kind in NEEDS_CODE and NEEDS_CODE[kind].search(shown_text) and s.get('code') != 'start':
            err(w, f'코드를 보고 푸는 단계("{NEEDS_CODE[kind].search(shown_text).group(0)}")에는 "code": "start"를 넣어 질문 위에 처음 코드를 보여 줄 것')
        sid = s.get('id')
        if not isinstance(sid, str) or not re.match(r'^s\d+$', sid) or sid in ids:
            err(w, f'id 오류 {sid!r}')
        ids.add(sid)
        k = s.get('kind')
        kinds.append(k)
        if not isinstance(s.get('explain'), str) or len(s['explain']) < 10:
            err(w, 'explain(해설) 필요(10자 이상)')
        if k == 'mcq':
            if not isinstance(s.get('q'), str) or not s['q'].strip():
                err(w, 'q 필요')
            o = s.get('options')
            if not isinstance(o, list) or not (3 <= len(o) <= 5) or not all(isinstance(x, str) and x.strip() for x in o):
                err(w, 'options 3~5개 문자열')
            elif len(set(o)) != len(o):
                err(w, 'options 중복')
            a = s.get('answer')
            if not isinstance(a, int) or not isinstance(o, list) or not (0 <= a < len(o)):
                err(w, 'answer는 options 인덱스(0부터)')
        elif k == 'table':
            cols = s.get('columns')
            rows = s.get('rows')
            if not isinstance(s.get('prompt'), str) or not s['prompt'].strip():
                err(w, 'prompt 필요')
            if not isinstance(cols, list) or not (2 <= len(cols) <= 7):
                err(w, 'columns 2~7개')
                continue
            if not isinstance(rows, list) or not (1 <= len(rows) <= 12):
                err(w, 'rows 1~12개')
                continue
            inputs = []
            for r in rows:
                if not isinstance(r, list) or len(r) != len(cols):
                    err(w, '행의 칸 수가 columns와 다름')
                    continue
                for c in r:
                    if isinstance(c, dict):
                        if not isinstance(c.get('a'), str) or not c['a'].strip():
                            err(w, '입력 칸 a(정답 문자열) 필요')
                        elif len(c['a']) > 40:
                            err(w, f'입력 칸 정답이 너무 김: {c["a"]!r}')
                        if 'alts' in c and not (isinstance(c['alts'], list) and all(isinstance(x, str) for x in c['alts'])):
                            err(w, 'alts는 문자열 목록')
                        inputs.append(c)
                    elif not isinstance(c, str):
                        err(w, '칸은 문자열 또는 {a}')
            if not (2 <= len(inputs) <= 16):
                err(w, f'입력 칸 2~16개(지금 {len(inputs)})')
            chk = s.get('check')
            if not isinstance(chk, str) or 'def answers' not in chk:
                err(w, 'check(def answers(): 입력 칸 정답 목록을 행 순서대로 돌려줌) 필요')
            else:
                res, e = run_py(chk + '\nRESULT = [str(x) for x in answers()]')
                if e:
                    err(w, f'check 실행 실패: {e}')
                elif len(res) != len(inputs):
                    err(w, f'check 결과 {len(res)}개 ≠ 입력 칸 {len(inputs)}개')
                else:
                    for j, (got, c) in enumerate(zip(res, inputs)):
                        accepted = [c.get('a', '')] + c.get('alts', [])
                        if norm_cell(got) not in [norm_cell(x) for x in accepted]:
                            err(w, f'입력 칸 {j + 1}: 정답 {c.get("a")!r} ≠ 계산 {got!r}')
        elif k == 'short':
            if not isinstance(s.get('q'), str) or not s['q'].strip():
                err(w, 'q 필요')
            if not isinstance(s.get('a'), str) or not s['a'].strip():
                err(w, 'a 필요')
            chk = s.get('check')
            if not isinstance(chk, str) or 'def answers' not in chk:
                err(w, 'check 필요')
            else:
                res, e = run_py(chk + '\nRESULT = [str(x) for x in answers()]')
                if e:
                    err(w, f'check 실행 실패: {e}')
                elif len(res) != 1 or norm_cell(res[0]) not in [norm_cell(x) for x in [s.get('a', '')] + s.get('alts', [])]:
                    err(w, f'정답 {s.get("a")!r} ≠ 계산 {res}')
        else:
            err(w, f'kind 오류 {k!r}(mcq|table|short)')
    need = 2 if adv else 1
    if kinds.count('table') < need:
        err(where, f'표 채우기(table) 단계가 {need}개 이상 필요')
    if kinds.count('mcq') < need:
        err(where, f'객관식(mcq) 단계가 {need}개 이상 필요')


def check_problem(where, p, course, tnum, kind, expected_id, seen, mock=False, adv=False):
    req = ['id', 'version', 'title', 'statement', 'params', 'returns', 'funcName', 'argNames', 'examples', 'code', 'solution', 'tests', 'inputCheck', 'steps', 'explain']
    for k in req:
        if k not in p:
            err(where, f'{k} 없음')
    if any(k not in p for k in req):
        return
    pid = p['id']
    if pid != expected_id:
        err(where, f'id는 {expected_id} 이어야 함(지금 {pid})')
    if pid in seen:
        err(where, f'id 중복 {pid}')
    seen.add(pid)
    if not isinstance(p['version'], int) or p['version'] < 1:
        err(where, 'version은 1 이상 정수')
    if not isinstance(p['title'], str) or not (2 <= len(p['title']) <= 30):
        err(where, 'title 2~30자')
    for k in ('statement', 'explain', 'code', 'solution', 'inputCheck'):
        if not isinstance(p[k], str) or not p[k].strip():
            err(where, f'{k}는 비어 있지 않은 문자열')
            return
    for k in ('params', 'returns'):
        if not isinstance(p[k], list) or not p[k] or not all(isinstance(x, str) for x in p[k]):
            err(where, f'{k}는 문자열 목록(1개 이상)')
    if not IDENT.match(str(p['funcName'])):
        err(where, 'funcName 오류')
    an = p['argNames']
    if not isinstance(an, list) or not an or not all(isinstance(x, str) and IDENT.match(x) for x in an):
        err(where, 'argNames 오류')
        return
    if not re.search(FUNC_DEF[CTX['lang']].format(f=re.escape(p['funcName'])), p['solution']):
        err(where, '정답 코드에 funcName 함수 정의 없음')
    mode = p.get('compare', 'exact')
    if mode not in ('exact', 'float'):
        err(where, 'compare는 exact|float')
    ex = p['examples']
    if not isinstance(ex, list) or not (2 <= len(ex) <= 3):
        err(where, 'examples 2~3개')
        return
    tests = p['tests']
    min_tests = 12 if adv else 10
    if not isinstance(tests, list) or len(tests) < min_tests:
        err(where, f'tests {min_tests}개 이상(지금 {len(tests) if isinstance(tests, list) else "?"})')
        return
    allc = []
    for j, c in enumerate(ex + tests):
        if not isinstance(c, dict) or not isinstance(c.get('args'), list) or len(c['args']) != len(an) or 'expected' not in c:
            err(where, f'케이스 {j + 1}: args(argNames 수만큼)·expected 필요')
            return
        allc.append({'args': c['args'], 'expected': c['expected']})
    # 브라우저(JavaScript)는 3.0과 3을 구분하지 못한다: 인자에 정수값 실수 금지, 실수 반환이 있으면 compare=float
    def floats(v):
        if isinstance(v, float):
            yield v
        elif isinstance(v, list):
            for x in v:
                yield from floats(x)
    if any(f.is_integer() for c in allc for f in floats(c['args'])):
        err(where, '인자에 정수값 실수(예: 3.0)를 쓰지 말 것(브라우저에서 정수 3으로 바뀜)')
    def ints(v):
        if isinstance(v, bool):
            return
        if isinstance(v, int):
            yield v
        elif isinstance(v, list):
            for x in v:
                yield from ints(x)
    if any(abs(n) > 2 ** 53 for c in allc for part in (c['args'], c['expected']) for n in ints(part)):
        err(where, '2^53보다 큰 정수는 브라우저에서 정확하지 않으니 쓰지 말 것')
    if mode != 'float' and any(True for c in allc for _ in floats(c['expected'])):
        err(where, '기댓값에 실수가 있으면 "compare": "float"로 둘 것')
    keys = [json.dumps(c['args'], sort_keys=True) for c in allc]
    if len(set(keys)) != len(keys):
        err(where, '예시·테스트 입력 중복')
    for j, c in enumerate(ex):
        if 'explain' in c and not isinstance(c['explain'], str):
            err(where, f'예시 {j + 1} explain은 문자열')
    # 입력 조건
    res, e = run_py(p['inputCheck'] + '\nimport json as _jj\nRESULT = [bool(valid(*a)) for a in _jj.loads(' + repr(json.dumps([c['args'] for c in allc])) + ')]')
    if e:
        err(where, f'inputCheck 실행 실패: {e}')
    elif not all(res):
        bad = [i + 1 for i, v in enumerate(res) if not v]
        err(where, f'inputCheck 거짓인 케이스(예시 먼저 번호): {bad}')
    # 정답 코드
    if CTX['lang'] == 'c':
        spec = p.get('cspec') or {}
        if not isinstance(spec, dict):
            err(where, 'cspec는 객체')
            spec = {}
        if not re.search(r'#include', p['solution']) and re.search(r'\b(printf|malloc|strlen|strcpy|strcmp|sqrt|abs)\s*\(', p['solution']):
            err(where, 'C 코드에서 라이브러리 함수를 쓰면 #include를 넣을 것')
        if re.search(r'\bint\s+main\s*\(', p['solution']):
            err(where, 'C 코드에 main 함수를 넣지 말 것(채점은 solution을 직접 부름)')
        # gcc로 같은 테스트를 돌려 기댓값이 실제 C와 같은지 대조
        try:
            for d_ in (os.path.join(ROOT, 'tools'), os.path.join(ROOT, 'src', 'grader')):
                d_ in sys.path or sys.path.insert(0, d_)
            import cref  # noqa: E402
            from harness import same as _same  # noqa: E402
            g = cref.run_gcc(p['solution'], p['funcName'], allc, spec)
            badg = [i + 1 for i, (x, c) in enumerate(zip(g, allc)) if not x.get('ok') or not _same(x.get('value'), c['expected'], mode)]
            if badg:
                i = badg[0] - 1
                err(where, f'gcc 대조 실패(예시 먼저 번호) {badg[:6]} — #{badg[0]}: {g[i].get("error") or g[i].get("value")!r} ≠ {allc[i]["expected"]!r}')
        except Exception as gexc:  # noqa: BLE001
            err(where, f'gcc 대조 실행 실패: {gexc}')
    else:
        spec = None
    r, e = run_harness(p['solution'], p['funcName'], allc, mode, spec)
    if e or r is None:
        err(where, f'정답 실행 실패: {e}')
    elif r['compile']:
        err(where, f'정답 코드 오류: {r["compile"]}')
    else:
        bad = [i + 1 for i, x in enumerate(r['results']) if not x['ok']]
        if bad:
            detail = '; '.join(f'#{i}: got {r["results"][i - 1].get("got") or r["results"][i - 1].get("error")}' for i in bad[:3])
            err(where, f'정답이 틀린 케이스(예시 먼저 번호) {bad} — {detail}')
    code = p['code']
    if kind == 'blank':
        ms = [int(m) for m in MARK.findall(code)]
        if not ms or ms != list(range(1, len(ms) + 1)):
            err(where, f'빈칸 표시 ⟦1⟧⟦2⟧…가 순서대로여야 함(지금 {ms})')
            return
        if not (2 <= len(ms) <= 8):
            err(where, '빈칸 2~8개')
        bl = p.get('blanks')
        if not isinstance(bl, list) or len(bl) != len(ms) or not all(isinstance(b, dict) and isinstance(b.get('answer'), str) and b['answer'].strip() for b in bl):
            err(where, 'blanks는 빈칸 수만큼 {answer} 목록')
            return
        filled = MARK.sub(lambda m: bl[int(m.group(1)) - 1]['answer'], code)
        if lines(filled) != lines(p['solution']):
            err(where, '빈칸에 정답을 넣은 코드가 정답 코드와 다름')
        for b in bl:
            for alt in b.get('alts', []):
                if not isinstance(alt, str):
                    err(where, 'alts는 문자열 목록')
    elif kind == 'fix':
        a, b = lines(code), lines(p['solution'])
        if len(a) != len(b):
            err(where, '한 줄 수정: 처음 코드와 정답 코드의 줄 수가 같아야 함')
        else:
            diff = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
            if len(diff) != 1:
                err(where, f'한 줄 수정: 다른 줄이 정확히 1개여야 함(지금 {diff})')
            elif p.get('bugLine') != diff[0]:
                err(where, f'bugLine은 {diff[0]}')
        r2, e = run_harness(code, p['funcName'], [{'args': c['args'], 'expected': c['expected']} for c in ex], mode, spec)
        if e or r2 is None:
            err(where, f'처음 코드 실행 실패(시간 초과면 무한 반복 버그는 피할 것): {e}')
        elif not r2['compile'] and all(x['ok'] for x in r2['results']):
            err(where, '처음(틀린) 코드가 예시를 모두 통과함 — 예시에서 틀려야 함')
        if MARK.search(code):
            err(where, '한 줄 수정 코드에 빈칸 표시가 있음')
    elif kind == 'write':
        r2, e = run_harness(code, p['funcName'], allc, mode, spec)
        if r2 and not r2['compile'] and all(x['ok'] for x in r2['results']):
            err(where, '처음 코드가 이미 모든 테스트를 통과함')
        if MARK.search(code):
            err(where, '함수 작성 코드에 빈칸 표시가 있음')
        if not re.search(FUNC_DEF[CTX['lang']].format(f=re.escape(p['funcName'])), code):
            err(where, '처음 코드에 funcName 함수 정의 없음')
    if mock and p.get('steps') == []:
        return  # 모의고사: 중간 점검 없이 실전처럼
    check_steps(where, p, adv, kind)


def check_file(path, seen):
    where = os.path.relpath(path, ROOT)
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:
        err(where, f'JSON 오류: {e}')
        return 0
    mock = bool(re.search(r'[/\\]mock[/\\]t\d{2}\.json$', path))
    adv = bool(re.search(r'[/\\]adv[/\\]t\d{2}\.json$', path))
    m = re.search(r'(pyb|pya|cb|ca)[/\\](?:(?:mock|adv)[/\\])?t(\d{2})\.json$', path)
    if not m:
        err(where, '파일 경로는 src/content/<과정>/tNN.json, .../mock/tNN.json, .../adv/tNN.json')
        return 0
    course, tnum = m.group(1), int(m.group(2))
    if d.get('course') != course or d.get('type') != tnum:
        err(where, f'course/type이 경로와 다름({d.get("course")}, {d.get("type")})')
    CTX['lang'] = d.get('lang', 'python')
    if CTX['lang'] not in ('python', 'c'):
        err(where, 'lang은 python|c')
        return 0
    if (course in ('cb', 'ca')) != (CTX['lang'] == 'c'):
        err(where, 'C 과정(cb·ca) 파일은 "lang": "c", 파이썬 과정은 lang 생략')
    kind = d.get('kind')
    if kind not in ('blank', 'fix', 'write'):
        err(where, 'kind는 blank|fix|write')
        return 0
    if not isinstance(d.get('typeTitle'), str) or not (2 <= len(d['typeTitle']) <= 24):
        err(where, 'typeTitle 2~24자')
    if not isinstance(d.get('skills'), list) or not d['skills']:
        err(where, 'skills 목록 필요')
    if not isinstance(d.get('intro'), str) or len(d['intro']) < 20:
        err(where, 'intro(유형 소개 2~3문장) 필요')
    probs = d.get('problems')
    if adv:
        # 심화 문제: 같은 유형의 기본 문제 파일과 형식·이름이 같아야 한다
        base = os.path.join(os.path.dirname(os.path.dirname(path)), f't{tnum:02d}.json')
        try:
            bd = json.load(open(base, encoding='utf-8'))
            if bd.get('kind') != kind:
                err(where, f'심화 문제 kind는 기본 유형과 같아야 함({bd.get("kind")})')
            if bd.get('typeTitle') != d.get('typeTitle'):
                err(where, f'심화 문제 typeTitle은 기본 유형과 같아야 함({bd.get("typeTitle")!r})')
        except Exception as e:  # noqa: BLE001
            err(where, f'같은 유형의 기본 문제 파일을 읽지 못함: {e}')
        if not isinstance(probs, list) or len(probs) != 5:
            err(where, '심화 problems는 5개(adv1~adv5)')
            return 0
        for i, p in enumerate(probs):
            check_problem(f'{where} #{i + 1}', p, course, tnum, kind, f'{course}-t{tnum:02d}-adv{i + 1}', seen, adv=True)
        return len(probs)
    if mock:
        # 모의고사: 원본 유형마다 3세트(m1~m3)
        if not isinstance(probs, list) or len(probs) != 3:
            err(where, '모의고사 problems는 3개(1~3회)')
            return 0
        for i, p in enumerate(probs):
            check_problem(f'{where} #{i + 1}', p, course, tnum, kind, f'{course}-m{i + 1}-t{tnum:02d}', seen, mock=True)
        return len(probs)
    if not isinstance(probs, list) or len(probs) != 5:
        err(where, 'problems는 5개')
        return 0
    for i, p in enumerate(probs):
        check_problem(f'{where} #{i + 1}', p, course, tnum, kind, f'{course}-t{tnum:02d}-{"abcde"[i]}', seen)
    return len(probs)


def main():
    args = sys.argv[1:]
    fill = '--fill' in args
    args = [a for a in args if a != '--fill']
    targets = args or [os.path.join(ROOT, 'src', 'content')]
    files = []
    for t in targets:
        if os.path.isdir(t):
            for dp, _, fs in os.walk(t):
                files += [os.path.join(dp, f) for f in fs if f.endswith('.json')]
        else:
            files.append(t)
    seen = set()
    n = 0
    for f in sorted(files):
        f = os.path.abspath(f)
        if re.search(r'[/\\]content[/\\]d2[/\\]', f):
            # Data 2급: 객관식·데이터(CSV) 문제 — 브라우저와 같은 Pyodide로 검수(tools/validate_d2.py)
            sys.path.insert(0, os.path.join(ROOT, 'tools'))
            import validate_d2  # noqa: E402
            n += validate_d2.check_file(sys.modules[__name__], f, seen, fill)
        else:
            n += check_file(f, seen)
    if ERRORS:
        print(f'✗ 오류 {len(ERRORS)}개 (문제 {n}개 검사)')
        for e in ERRORS:
            print(' - ' + e)
        sys.exit(1)
    print(f'✓ 문제 {n}개 검수 통과 ({len(files)}개 파일)')


if __name__ == '__main__':
    main()
