"""Data 2급(d2) 문제 검수 — tools/validate.py가 src/content/d2/ 파일을 이 모듈로 넘긴다(형식: docs/D2_BRIEF.md).

- 객관식(choice): 보기 4개·정답 번호·보기별 풀이(why)·중간 점검
- 데이터 코드 문제(blank·fix·write): 정답 코드를 브라우저와 같은 Pyodide(tools/pyodide_runner.mjs)로
  예시 데이터(변형 0)와 숨은 데이터(변형 1·2)에서 실행해 기댓값과 같은지, 처음 코드는 틀리는지 확인
- 중간 점검 check도 같은 Pyodide에서 예시 데이터 폴더를 기준으로 실행(pandas 사용 가능)
- --fill: 정답 코드를 실행해 examples·tests의 expected를 채워 파일에 다시 쓴다(그 뒤 검수)
"""
import atexit
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, 'src', 'datasets', 'd2.json')
KINDS = ('choice', 'blank', 'fix', 'write')
CODE_KINDS = ('blank', 'fix', 'write')
ALLOWED_IMPORTS = {'pandas', 'numpy', 'matplotlib', 'scipy', 'sklearn', 'math'}


class Runner:
    proc = None

    @classmethod
    def get(cls):
        if cls.proc is None:
            cls.proc = subprocess.Popen(['node', os.path.join(ROOT, 'tools', 'pyodide_runner.mjs')], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            first = cls.proc.stdout.readline()
            if '"ready"' not in first:
                raise RuntimeError('Pyodide 실행기를 띄우지 못함(npm run runtime으로 패키지를 먼저 받을 것): ' + first[:300])
            atexit.register(cls.close)
        return cls

    @classmethod
    def ask(cls, req):
        cls.get()
        cls.proc.stdin.write(json.dumps(req, ensure_ascii=False) + '\n')
        cls.proc.stdin.flush()
        line = cls.proc.stdout.readline()
        if not line:
            raise RuntimeError('Pyodide 실행기가 멈춤')
        return json.loads(line)

    @classmethod
    def close(cls):
        if cls.proc:
            try:
                cls.proc.stdin.close()
                cls.proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                cls.proc.kill()
            cls.proc = None


def pyo_run_py(src, timeout=20):
    """validate.run_py 대신: Pyodide에서 예시 데이터 폴더를 기준으로 실행하고 RESULT를 돌려준다."""
    r = Runner.ask({'op': 'exec', 'code': src, 'data': 0})
    if 'error' in r:
        return None, r['error'][-800:]
    return r['result'], None


AREAS = ('A1', 'A2', 'A3', 'A4', 'A5')


def catalog():
    try:
        return json.load(open(CATALOG, encoding='utf-8'))
    except Exception:  # noqa: BLE001
        return {}


def run_cases(code, cases, plot, mode='float'):
    req = {'op': 'data', 'code': code, 'cases': [{'data': c['data'], **({'expected': c['expected']} if 'expected' in c else {}), **({'plot': True} if plot else {})} for c in cases], 'mode': mode}
    return Runner.ask(req)


def check_problem(V, where, p, kind, expected_id, seen, adv=False, mock=False, fill=False):
    err = V.err
    req = ['id', 'version', 'title', 'statement', 'steps', 'explain']
    for k in req:
        if k not in p:
            err(where, f'{k} 없음')
    if any(k not in p for k in req):
        return False
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
    for k in ('statement', 'explain'):
        if not isinstance(p[k], str) or not p[k].strip():
            err(where, f'{k}는 비어 있지 않은 문자열')
    if V.MARK.search(p['statement']) and kind != 'blank':
        err(where, '문제 설명에 빈칸 표시가 있음')
    changed = False
    if kind == 'choice':
        for k in ('code', 'solution', 'data', 'tests', 'examples'):
            if k in p:
                err(where, f'객관식 문제에는 {k}를 쓰지 않음')
        c = p.get('choice')
        if not isinstance(c, dict):
            err(where, 'choice {options, answer, why} 필요')
        else:
            o = c.get('options')
            if not isinstance(o, list) or len(o) != 4 or not all(isinstance(x, str) and x.strip() for x in o):
                err(where, 'choice.options는 문자열 4개(시험처럼 4지선다)')
            elif len(set(o)) != 4:
                err(where, 'choice.options 중복')
            a = c.get('answer')
            if not isinstance(a, int) or not (0 <= a < 4):
                err(where, 'choice.answer는 0~3')
            w = c.get('why')
            if not isinstance(w, list) or len(w) != 4 or not all(isinstance(x, str) and len(x) >= 8 for x in w):
                err(where, 'choice.why는 보기마다 왜 맞고 틀린지 한 문장씩(4개, 8자 이상)')
    else:
        data = p.get('data')
        cat = catalog()
        if not isinstance(data, dict) or not isinstance(data.get('files'), list) or not data['files']:
            err(where, 'data.files(읽는 데이터 파일 목록) 필요')
            return False
        for f in data['files']:
            if f not in cat:
                err(where, f'없는 데이터 파일 {f!r}(목록: {", ".join(cat)})')
        plot = bool(data.get('plot'))
        for k in ('code', 'solution'):
            if not isinstance(p.get(k), str) or not p[k].strip():
                err(where, f'{k}는 비어 있지 않은 문자열')
                return False
        for f in data['files']:
            if f not in p['code']:
                err(where, f'처음 코드가 {f}를 읽어야 함(read_csv)')
        if 'def solution(' not in p['solution']:
            err(where, '정답 코드에 def solution(): 필요')
        for mod in re.findall(r'^\s*(?:from|import)\s+([A-Za-z_]\w*)', p['solution'] + '\n' + p['code'], re.M):
            if mod not in ALLOWED_IMPORTS:
                err(where, f'쓸 수 없는 모듈 {mod}(pandas·numpy·matplotlib·scipy·sklearn·math만)')
        if not plot:
            af = p.get('answerFormat')
            if not isinstance(af, str) or not af.strip():
                err(where, 'answerFormat(정답 예시, 예: "0.12" 또는 "123") 필요')
        mode = p.get('compare', 'float')
        if mode not in ('exact', 'float'):
            err(where, 'compare는 exact|float')
        ex, tests = p.get('examples'), p.get('tests')
        if not isinstance(ex, list) or len(ex) != 1 or not isinstance(ex[0], dict) or ex[0].get('data') != 0:
            err(where, 'examples는 [{"data": 0, "expected": …}] 하나(예시 데이터)')
            return False
        if not isinstance(tests, list) or len(tests) < 2 or sorted(t.get('data') for t in tests if isinstance(t, dict)) != list(range(1, len(tests) + 1)):
            err(where, 'tests는 [{"data": 1, …}, {"data": 2, …}] (숨은 데이터 변형마다 하나)')
            return False
        allc = ex + tests
        if fill:
            r = run_cases(p['solution'], [{'data': c['data']} for c in allc], plot, mode)
            if r.get('compile') or 'error' in r or any('error' in x for x in r.get('results', [])):
                err(where, f'채우기 실패(정답 코드 오류): {r.get("compile") or r.get("error") or [x.get("error") for x in r.get("results", [])]}')
                return False
            for c, x in zip(allc, r['results']):
                if c.get('expected') != x['value']:
                    c['expected'] = x['value']
                    changed = True
        if any('expected' not in c for c in allc):
            err(where, 'expected 없음(--fill로 채울 것)')
            return changed
        r = run_cases(p['solution'], allc, plot, mode)
        if 'error' in r:
            err(where, f'정답 실행 실패: {r["error"]}')
            return changed
        if r['compile']:
            err(where, f'정답 코드 오류: {r["compile"]}')
            return changed
        bad = [i for i, x in enumerate(r['results']) if not x['ok']]
        if bad:
            err(where, f'정답이 틀린 데이터 변형 {bad} — {[r["results"][i].get("got") or r["results"][i].get("error") for i in bad][:2]}')
        vals = [json.dumps(c['expected'], sort_keys=True) for c in allc]
        if not plot and len(set(vals)) == 1 and not p.get('sameAnswerOk'):
            err(where, f'예시·숨은 데이터의 정답이 모두 같음({vals[0]}) — 값만 외워도 통과하니 데이터에 따라 달라지는 질문으로(정말 괜찮으면 "sameAnswerOk": true)')
        if not plot:
            for c in allc:
                e = c['expected']
                if not isinstance(e, (int, float, str, bool)) or isinstance(e, bool):
                    err(where, f'정답은 정수·실수·문자열 하나로(지금 {e!r})')
                    break
        code = p['code']
        if kind == 'blank':
            ms = [int(m) for m in V.MARK.findall(code)]
            if not ms or ms != list(range(1, len(ms) + 1)):
                err(where, f'빈칸 표시 ⟦1⟧⟦2⟧…가 순서대로여야 함(지금 {ms})')
                return changed
            lo, hi = (2, 8) if not mock else (1, 8)
            if not (lo <= len(ms) <= hi):
                err(where, f'빈칸 {lo}~{hi}개')
            bl = p.get('blanks')
            if not isinstance(bl, list) or len(bl) != len(ms) or not all(isinstance(b, dict) and isinstance(b.get('answer'), str) and b['answer'].strip() for b in bl):
                err(where, 'blanks는 빈칸 수만큼 {answer} 목록')
                return changed
            filled = V.MARK.sub(lambda m: bl[int(m.group(1)) - 1]['answer'], code)
            if V.lines(filled) != V.lines(p['solution']):
                err(where, '빈칸에 정답을 넣은 코드가 정답 코드와 다름')
        elif kind == 'fix':
            a, b = V.lines(code), V.lines(p['solution'])
            if len(a) != len(b):
                err(where, '한 줄 수정: 처음 코드와 정답 코드의 줄 수가 같아야 함')
            else:
                diff = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
                if len(diff) != 1:
                    err(where, f'한 줄 수정: 다른 줄이 정확히 1개여야 함(지금 {diff})')
                elif p.get('bugLine') != diff[0]:
                    err(where, f'bugLine은 {diff[0]}')
            r2 = run_cases(code, ex, plot, mode)
            if 'error' not in r2 and not r2['compile'] and all(x['ok'] for x in r2['results']):
                err(where, '처음(틀린) 코드가 예시 데이터에서 맞음 — 틀리게 할 것')
        elif kind == 'write':
            if V.MARK.search(code):
                err(where, '함수 작성 코드에 빈칸 표시가 있음')
            if 'def solution(' not in code:
                err(where, '처음 코드에 def solution(): 필요')
            r2 = run_cases(code, allc, plot, mode)
            if 'error' not in r2 and not r2['compile'] and all(x['ok'] for x in r2['results']):
                err(where, '처음 코드가 이미 정답')
    if mock and p.get('steps') == []:
        return changed
    # Data 2급(시험형): 중간 점검은 '풀이 도움'(선택, 0~9단계)
    V.check_steps(where, p, adv, kind if kind in CODE_KINDS else None, help_only=True)
    return changed


def check_file(V, path, seen, fill=False):
    where = os.path.relpath(path, ROOT)
    err = V.err
    try:
        d = json.load(open(path, encoding='utf-8'))
    except Exception as e:  # noqa: BLE001
        err(where, f'JSON 오류: {e}')
        return 0
    old_run_py = V.run_py
    V.run_py = pyo_run_py
    try:
        n, changed = _check_file(V, path, where, d, seen, fill)
    finally:
        V.run_py = old_run_py
    if fill and changed:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
            f.write('\n')
        print(f'  ↺ expected 채움: {where}')
    return n


def _check_file(V, path, where, d, seen, fill):
    err = V.err
    changed = False
    mm = re.search(r'd2[/\\]mock[/\\]m(\d)\.json$', path)
    if mm:
        n = int(mm.group(1))
        if d.get('course') != 'd2' or d.get('mock') != n:
            err(where, f'course "d2", mock {n} 이어야 함')
        items = d.get('items')
        if not isinstance(items, list) or not (10 <= len(items) <= 30):
            err(where, 'items 10~30개')
            return 0, False
        for i, it in enumerate(items):
            w = f'{where} #{i + 1}'
            if not isinstance(it, dict) or not isinstance(it.get('type'), int) or it.get('kind') not in KINDS or not isinstance(it.get('problem'), dict):
                err(w, '{type: 유형 번호, kind, problem} 필요')
                continue
            if it['type'] != i + 1:
                err(w, f'유형 번호는 시험 문항 번호와 같아야 함({i + 1}, 지금 {it["type"]})')
            if not os.path.exists(os.path.join(ROOT, 'src', 'content', 'd2', f't{it["type"]:02d}.json')):
                err(w, f'유형 {it["type"]}의 기본 문제 파일이 없음')
            changed |= check_problem(V, w, it['problem'], it['kind'], f'd2-m{n}-q{i + 1:02d}', seen, mock=True, fill=fill)
        return len(items), changed
    m = re.search(r'd2[/\\]t(\d{2})\.json$', path)
    if not m:
        err(where, '파일 경로는 src/content/d2/tNN.json(NN = 시험 문항 번호 01~20), .../mock/mN.json. Data 2급에는 [심화](adv)가 없음')
        return 0, False
    adv, tnum = False, int(m.group(1))
    if not 1 <= tnum <= 20:
        err(where, '유형 번호는 시험 문항 번호 1~20')
    if d.get('area') not in AREAS:
        err(where, f'area는 {", ".join(AREAS)} 중 하나(src/content/index.ts D2_AREAS)')
    c = d.get('concept')
    if not isinstance(c, dict) or not isinstance(c.get('text'), str) or not (60 <= len(c['text']) <= 320):
        err(where, 'concept.text(핵심 개념 2~4문장, 60~320자) 필요')
    elif 'table' in c:
        tb = c['table']
        if not isinstance(tb, dict) or not isinstance(tb.get('head'), list) or not isinstance(tb.get('rows'), list) or any(len(r) != len(tb['head']) for r in tb['rows']):
            err(where, 'concept.table은 {head, rows}이고 행마다 칸 수가 head와 같아야 함')
    if isinstance(c, dict) and 'saiedu' in c:
        z = c['saiedu']
        if not isinstance(z, dict) or not isinstance(z.get('unit'), int) or not 1 <= z['unit'] <= 11 or not isinstance(z.get('title'), str):
            err(where, 'concept.saiedu는 {unit: 배움 숲 Data 단원 1~11, title}')
    if d.get('course') != 'd2' or d.get('type') != tnum:
        err(where, f'course/type이 경로와 다름({d.get("course")}, {d.get("type")})')
    kind = d.get('kind')
    if kind not in KINDS:
        err(where, 'kind는 choice|blank|fix|write')
        return 0, False
    if (kind == 'choice') != (tnum <= 12):
        err(where, '시험 1~12번은 객관식(choice), 13~20번은 작업형(코드) 유형')
    if not isinstance(d.get('typeTitle'), str) or not (2 <= len(d['typeTitle']) <= 24):
        err(where, 'typeTitle 2~24자')
    if not isinstance(d.get('skills'), list) or not d['skills']:
        err(where, 'skills 목록 필요')
    if not isinstance(d.get('intro'), str) or len(d['intro']) < 20:
        err(where, 'intro(유형 소개 2~3문장) 필요')
    probs = d.get('problems')
    if not isinstance(probs, list) or len(probs) != 5:
        err(where, 'problems는 5개')
        return 0, False
    if adv:
        base = os.path.join(os.path.dirname(os.path.dirname(path)), f't{tnum:02d}.json')
        try:
            bd = json.load(open(base, encoding='utf-8'))
            if bd.get('kind') != kind:
                err(where, f'심화 문제 kind는 기본 유형과 같아야 함({bd.get("kind")})')
            if bd.get('typeTitle') != d.get('typeTitle'):
                err(where, f'심화 문제 typeTitle은 기본 유형과 같아야 함({bd.get("typeTitle")!r})')
        except Exception as e:  # noqa: BLE001
            err(where, f'같은 유형의 기본 문제 파일을 읽지 못함: {e}')
    for i, p in enumerate(probs):
        pk = p.get('kind', kind) if isinstance(p, dict) else kind
        if kind == 'choice' and pk != 'choice' or kind != 'choice' and pk not in CODE_KINDS:
            err(f'{where} #{i + 1}', '객관식 유형에는 객관식만, 코드 유형에는 코드 문제만')
            continue
        eid = f'd2-t{tnum:02d}-{"abcde"[i]}'
        # 예전 판(10유형, version 1) 기록이 새 문제에 붙지 않게 version은 2 이상(src/features/progress/model.ts MIN_VER)
        if isinstance(p.get('version'), int) and p['version'] < 2:
            err(f'{where} #{i + 1}', 'Data 2급 문제 version은 2 이상')
        changed |= check_problem(V, f'{where} #{i + 1}', p, pk, eid, seen, adv=adv, fill=fill)
    return len(probs), changed
