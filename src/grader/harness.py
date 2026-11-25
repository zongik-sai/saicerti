# saicerti 채점 하네스 (브라우저 Pyodide와 검수 도구 tools/validate.py가 같은 파일을 쓴다)
# - 학생 코드를 새 이름공간에서 실행하고, 테스트마다 인자를 깊은 복사해 함수를 부른 뒤 반환값을 비교한다.
# - 코드를 서버로 보내지 않는다(브라우저 안에서만 실행).
import builtins
import copy
import io
import json
import math
import os
import sys
import traceback

_ERR_KO = {
    'SyntaxError': '문법 오류: 괄호·콜론(:)·따옴표가 맞는지 확인해 보세요.',
    'IndentationError': '들여쓰기 오류: 같은 블록의 줄은 같은 칸만큼 들여 써야 해요.',
    'TabError': '들여쓰기 오류: 탭과 공백을 섞어 쓰지 마세요.',
    'NameError': '이름 오류: 만들지 않은 변수나 함수 이름을 썼어요(철자 확인).',
    'TypeError': '자료형 오류: 맞지 않는 자료형끼리 계산했거나 인자 수가 달라요.',
    'IndexError': '인덱스 오류: 리스트·문자열 범위를 벗어난 위치를 읽었어요.',
    'KeyError': '키 오류: 딕셔너리에 없는 키를 읽었어요.',
    'ValueError': '값 오류: 함수에 알맞지 않은 값을 넣었어요(예: int("a")).',
    'ZeroDivisionError': '0으로 나누기 오류: 나누는 수가 0이 되었어요.',
    'AttributeError': '속성 오류: 그 자료형에 없는 메서드를 불렀어요.',
    'RecursionError': '재귀 오류: 함수가 자기 자신을 너무 많이 불렀어요.',
    'UnboundLocalError': '지역 변수 오류: 값을 넣기 전에 변수를 읽었어요.',
}


def _no_input(*_a, **_k):
    raise RuntimeError('이 문제에서는 input()을 쓰지 않아요. 매개변수로 받은 값을 쓰세요.')


def norm(v):
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    if isinstance(v, dict):
        return {str(k): norm(x) for k, x in v.items()}
    return v


def same(got, exp, mode='exact'):
    """반환값 비교. exact: 정수는 정수로(3.0은 3과 다름), float 기댓값은 오차 허용. float 모드: 정수 기댓값도 오차 허용."""
    if isinstance(exp, bool) or isinstance(got, bool):
        return isinstance(exp, bool) and isinstance(got, bool) and exp == got
    if isinstance(exp, float):
        return isinstance(got, (int, float)) and math.isclose(got, exp, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(exp, int):
        if mode == 'float' and isinstance(got, float):
            return math.isclose(got, exp, rel_tol=1e-9, abs_tol=1e-9)
        return isinstance(got, int) and got == exp
    if isinstance(exp, list):
        return isinstance(got, (list, tuple)) and len(got) == len(exp) and all(same(g, e, mode) for g, e in zip(got, exp))
    if isinstance(exp, dict):
        return isinstance(got, dict) and set(map(str, got.keys())) == set(exp.keys()) and all(same(got[k] if k in got else got.get(_maybe_int(k)), exp[k], mode) for k in exp)
    if exp is None:
        return got is None
    return type(got) is type(exp) and got == exp


def _maybe_int(k):
    try:
        return int(k)
    except Exception:
        return k


def short_repr(v, limit=300):
    try:
        s = repr(v)
    except Exception:
        s = '<표시할 수 없는 값>'
    return s if len(s) <= limit else s[:limit] + ' …'


def _err(e, code_name='<학생 코드>'):
    name = type(e).__name__
    tb = traceback.extract_tb(e.__traceback__)
    line = None
    for fr in tb:
        if fr.filename == code_name:
            line = fr.lineno
    if isinstance(e, SyntaxError) and e.filename == code_name:
        line = e.lineno
    msg = f'{name}: {e}'
    return {'type': name, 'message': msg[:400], 'line': line, 'hint': _ERR_KO.get(name, '')}


class _Cap(io.StringIO):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit
        self.size = 0

    def write(self, s):
        if self.size < self.limit:
            super().write(s[: self.limit - self.size])
        self.size += len(s)
        return len(s)


def run_cases(code, func, cases_json, mode='exact', stdout_limit=6000):
    """code를 실행하고 cases(JSON 문자열 [{args, expected}])마다 func(*args)를 비교한다. JSON 문자열을 돌려준다."""
    cases = json.loads(cases_json)
    cap = _Cap(stdout_limit)
    old_out, old_err, old_input = sys.stdout, sys.stderr, builtins.input
    sys.stdout = cap
    sys.stderr = cap
    builtins.input = _no_input
    out = {'compile': None, 'results': []}
    try:
        ns = {'__name__': '__main__', '__builtins__': builtins}
        try:
            exec(compile(code, '<학생 코드>', 'exec'), ns)
        except KeyboardInterrupt:
            raise
        except BaseException as e:  # noqa: BLE001 학생 코드의 어떤 오류(exit() 포함)도 잡는다
            out['compile'] = _err(e)
            return json.dumps(out | {'stdout': cap.getvalue(), 'stdoutCut': cap.size > stdout_limit}, ensure_ascii=False)
        f = ns.get(func)
        if not callable(f):
            out['compile'] = {'type': 'NameError', 'message': f'{func} 함수가 없어요.', 'line': None, 'hint': f'def {func}(...): 로 시작하는 함수 이름을 바꾸지 마세요.'}
            return json.dumps(out | {'stdout': cap.getvalue(), 'stdoutCut': cap.size > stdout_limit}, ensure_ascii=False)
        for c in cases:
            args = copy.deepcopy(c['args'])
            try:
                got = f(*args)
                out['results'].append({'ok': same(got, c['expected'], mode), 'got': short_repr(norm(got) if isinstance(got, tuple) else got)})
            except KeyboardInterrupt:
                raise
            except BaseException as e:  # noqa: BLE001
                out['results'].append({'ok': False, 'error': _err(e)})
    finally:
        sys.stdout, sys.stderr, builtins.input = old_out, old_err, old_input
    out['stdout'] = cap.getvalue()
    out['stdoutCut'] = cap.size > stdout_limit
    return json.dumps(out, ensure_ascii=False)


def _load_cinterp():
    """C 인터프리터 모듈. 브라우저에서는 워커가 cinterp.py를 모듈 'cinterp'로 미리 등록해 둔다.
    검수 도구(CPython)에서는 이 파일과 같은 폴더(src/grader)에서 불러온다."""
    try:
        import cinterp
    except ImportError:
        here = globals().get('__file__')
        if not here:
            raise
        d = os.path.dirname(os.path.abspath(here))
        if d not in sys.path:
            sys.path.insert(0, d)
        import cinterp
    return cinterp


def run_cases_c(code, func, cases_json, mode='exact', spec_json='{}', stdout_limit=6000):
    """C 코드를 브라우저 안 C 인터프리터(cinterp)로 실행하고 cases마다 func(args…)의 반환값을 비교한다.
    run_cases와 같은 모양의 JSON 문자열을 돌려준다. spec: {derived: {매개변수: 'len(arr)'…}, ret: {len: …}}"""
    ci = _load_cinterp()
    cases = json.loads(cases_json)
    spec = json.loads(spec_json or '{}') or {}
    cap = _Cap(stdout_limit)
    out = {'compile': None, 'results': []}
    prog = None
    try:
        prog = ci.compile_c(code)
        if not prog.has(func):
            out['compile'] = {'type': 'NameError', 'message': f'{func} 함수가 없어요.', 'line': None, 'hint': f'{func} 함수의 이름과 모양(반환 타입 {func}(매개변수…) {{ … }})을 바꾸지 마세요.'}
    except ci.CError as e:
        out['compile'] = e.as_dict()
    except Exception as e:  # noqa: BLE001 채점기 내부 오류도 결과로 돌려준다
        out['compile'] = _err(e)
        out['compile']['hint'] = '채점기 내부 오류예요. 선생님께 알려 주세요.'
    if out['compile'] is None:
        for c in cases:
            try:
                got = prog.call(func, c['args'], spec)
                out['results'].append({'ok': same(got, c['expected'], mode), 'got': short_repr(got)})
            except ci.CError as e:
                out['results'].append({'ok': False, 'error': e.as_dict()})
            except KeyboardInterrupt:
                raise
            except Exception as e:  # noqa: BLE001
                d = _err(e)
                d['hint'] = '채점기 내부 오류예요. 선생님께 알려 주세요.'
                out['results'].append({'ok': False, 'error': d})
    cut = False
    if prog is not None:
        cap.write(prog.stdout_text())
        cut = prog.rt.out_total > len(prog.rt.out)
    out['stdout'] = cap.getvalue()
    out['stdoutCut'] = cap.size > stdout_limit or cut
    return json.dumps(out, ensure_ascii=False)


if __name__ == '__main__':
    # 검수 도구용: stdin으로 {code, func, cases, mode, lang, spec}를 받아 결과 JSON을 출력(lang이 'c'면 C 인터프리터)
    req = json.loads(sys.stdin.read())
    if req.get('lang') == 'c':
        res = run_cases_c(req['code'], req['func'], json.dumps(req['cases']), req.get('mode', 'exact'), json.dumps(req.get('spec') or {}))
    else:
        res = run_cases(req['code'], req['func'], json.dumps(req['cases']), req.get('mode', 'exact'))
    sys.__stdout__.write(res)
