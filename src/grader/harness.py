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


# ── Data 과정(d2): CSV 데이터를 읽는 코드를 실행하고 solution()의 반환값·그래프를 비교한다 ──────────
# 브라우저 워커가 데이터 변형마다 /d2data/v<k>/ 폴더에 CSV를 써 두고, 케이스마다 그 폴더에서 학생 코드를 새로 실행한다.
# 검수 도구(tools/pyodide_runner.mjs)도 같은 Pyodide·같은 패키지·같은 함수로 실행한다.

_ERR_KO_DATA = {
    'KeyError': '키 오류: 데이터프레임에 없는 열 이름(또는 인덱스)을 썼어요. 열 이름의 철자·대소문자를 확인해 보세요.',
    'FileNotFoundError': '파일 오류: 데이터 파일 이름을 확인해 보세요(처음 코드의 read_csv 줄을 바꾸지 마세요).',
    'ModuleNotFoundError': '모듈 오류: 이 사이트에서는 pandas·numpy·matplotlib·scipy·sklearn만 쓸 수 있어요.',
    'ImportError': '가져오기 오류: 함수·모듈 이름을 확인해 보세요.',
}


def _plain(v):
    """numpy·pandas 값을 파이썬 기본 값으로(비교·표시용)"""
    try:
        import numpy as _np
    except ImportError:
        _np = None
    if _np is not None:
        if isinstance(v, _np.generic):
            return v.item()
        if isinstance(v, _np.ndarray):
            return [_plain(x) for x in v.tolist()]
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def _num_label(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if math.isfinite(f) and abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f'{f:.6g}'


def _label(s):
    s = str(s).strip()
    try:
        return _num_label(float(s.replace('−', '-')))
    except ValueError:
        return s


def plot_data(fig):
    """그래프의 첫 번째 축에서 막대(높이)·선(점) 데이터를 읽는다. 학생이 어떤 방법(pandas plot, plt.bar 등)으로 그려도 같은 모양이면 같은 결과."""
    if fig is None or not fig.axes:
        return None
    ax = fig.axes[0]
    from matplotlib.patches import Rectangle
    bars = [p for p in ax.patches if isinstance(p, Rectangle) and p.get_visible()]
    if bars:
        horiz = len({round(p.get_height(), 9) for p in bars}) == 1 and len({round(p.get_width(), 9) for p in bars}) > 1 and len({round(p.get_x(), 9) for p in bars}) == 1
        if horiz:
            bars.sort(key=lambda p: p.get_y())
            ticks, labels = list(ax.get_yticks()), [t.get_text() for t in ax.get_yticklabels()]
            centers = [p.get_y() + p.get_height() / 2 for p in bars]
            values = [p.get_width() for p in bars]
            width = [p.get_height() for p in bars]
            kind = 'barh'
        else:
            bars.sort(key=lambda p: p.get_x())
            ticks, labels = list(ax.get_xticks()), [t.get_text() for t in ax.get_xticklabels()]
            centers = [p.get_x() + p.get_width() / 2 for p in bars]
            values = [p.get_height() for p in bars]
            width = [p.get_width() for p in bars]
            kind = 'bar'
        xs = []
        for c, w in zip(centers, width):
            lab = None
            if labels and len(labels) == len(ticks):
                j = min(range(len(ticks)), key=lambda i: abs(ticks[i] - c))
                if abs(ticks[j] - c) <= w / 2 + 1e-9 and labels[j].strip():
                    lab = _label(labels[j])
            xs.append(lab if lab is not None else _num_label(c))
        return {'kind': kind, 'x': xs, 'y': [round(float(v), 9) for v in values]}
    lines = [ln for ln in ax.get_lines() if ln.get_visible() and len(ln.get_xdata()) > 0]
    if lines:
        ln = lines[0]
        xd = [str(x)[:10] if hasattr(x, 'isoformat') or type(x).__name__ == 'datetime64' else x for x in ln.get_xdata()]
        return {'kind': 'line', 'x': [_label(x) for x in xd], 'y': [round(float(v), 9) for v in ln.get_ydata()]}
    return None


def same_plot(got, exp):
    if not isinstance(got, dict) or not isinstance(exp, dict):
        return False
    if got.get('kind') != exp.get('kind') or len(got.get('x', [])) != len(exp.get('x', [])) or len(got.get('y', [])) != len(exp.get('y', [])):
        return False
    if [_label(x) for x in got['x']] != [_label(x) for x in exp['x']]:
        return False
    return all(math.isclose(g, e, rel_tol=1e-6, abs_tol=1e-6) for g, e in zip(got['y'], exp['y']))


def _plot_hint(got, exp):
    if not got:
        return '그래프를 찾지 못했어요. 막대(또는 선) 그래프를 그린 뒤 plt.show()를 불렀는지 확인해 보세요.'
    if got.get('kind') != exp.get('kind'):
        k = {'bar': '세로 막대', 'barh': '가로 막대', 'line': '선'}
        return f'그래프 종류가 달라요: {k.get(exp.get("kind"), exp.get("kind"))} 그래프를 그려야 해요.'
    if len(got.get('x', [])) != len(exp.get('x', [])):
        return f'막대(점) 개수가 달라요: 정답은 {len(exp["x"])}개, 내 그래프는 {len(got["x"])}개예요.'
    if [_label(x) for x in got['x']] != [_label(x) for x in exp['x']]:
        return 'x축 값(이름표)의 값이나 순서가 달라요.'
    return '막대(점)의 높이가 달라요. 집계 방법(합계·개수·평균)을 확인해 보세요.'


def _num_hint(got, exp):
    if isinstance(exp, float) and isinstance(got, (int, float)) and not isinstance(got, bool):
        if math.isclose(round(got, 2), exp, abs_tol=1e-9) or math.isclose(round(got, 4), exp, abs_tol=1e-9) or abs(got - exp) < 0.005:
            return '값이 거의 같아요. 문제에서 말한 자리에서 반올림(round)했는지 확인해 보세요.'
    return ''


def run_data(code, cases_json, mode='float', stdout_limit=6000, want_png=True):
    """Data 문제 채점. cases: [{dir, expected, plot?}] — 케이스마다 dir 폴더(데이터 변형)에서 code를 새로 실행하고
    solution()의 반환값(plot이면 그래프)을 비교한다. 첫 케이스의 그래프는 PNG(base64)로 돌려준다."""
    import base64
    cases = json.loads(cases_json)
    cap = _Cap(stdout_limit)
    old_out, old_err, old_input, old_cwd = sys.stdout, sys.stderr, builtins.input, os.getcwd()
    out = {'compile': None, 'results': [], 'images': []}
    plt = None
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt  # noqa: F811
    except ImportError:
        plt = None
    shown = []
    if plt is not None:
        old_show = plt.show

        def _show(*_a, **_k):
            fig = plt.gcf()
            if fig.axes:
                shown.append(fig)
                plt.figure()
        plt.show = _show
    sys.stdout = cap
    sys.stderr = cap
    builtins.input = _no_input
    import warnings
    wctx = warnings.catch_warnings()
    wctx.__enter__()
    warnings.simplefilter('ignore')  # 라이브러리 경고(버전 안내 등)는 학생에게 보이지 않게
    try:
        for ci, c in enumerate(cases):
            if c.get('stdout') is False:
                sys.stdout = sys.stderr = io.StringIO()
            else:
                sys.stdout = sys.stderr = cap
            shown.clear()
            if plt is not None:
                plt.close('all')
            os.chdir(c['dir'])
            ns = {'__name__': '__main__', '__builtins__': builtins}
            try:
                exec(compile(code, '<학생 코드>', 'exec'), ns)
            except KeyboardInterrupt:
                raise
            except BaseException as e:  # noqa: BLE001
                d = _err(e)
                d['hint'] = _ERR_KO_DATA.get(d['type'], d['hint'])
                if ci == 0:
                    out['compile'] = d
                    break
                out['results'].append({'ok': False, 'error': d})
                continue
            f = ns.get('solution')
            if not callable(f):
                out['compile'] = {'type': 'NameError', 'message': 'solution 함수가 없어요.', 'line': None, 'hint': 'def solution(): 로 시작하는 함수 이름을 바꾸지 마세요.'}
                break
            try:
                got = _plain(f())
            except KeyboardInterrupt:
                raise
            except BaseException as e:  # noqa: BLE001
                d = _err(e)
                d['hint'] = _ERR_KO_DATA.get(d['type'], d['hint'])
                out['results'].append({'ok': False, 'error': d})
                continue
            if c.get('plot'):
                fig = shown[0] if shown else (plt.gcf() if plt is not None and plt.gcf().axes else None)
                if fig is not None and want_png and ci == 0:
                    try:
                        buf = io.BytesIO()
                        fig.savefig(buf, format='png', dpi=72, bbox_inches='tight')
                        out['images'].append(base64.b64encode(buf.getvalue()).decode('ascii'))
                    except Exception:  # noqa: BLE001
                        pass
                elif fig is not None:
                    fig.canvas.draw()
                pd_ = plot_data(fig) if fig is not None else None
                exp = c.get('expected')
                ok = same_plot(pd_, exp) if exp is not None else True
                r = {'ok': ok, 'got': short_repr(pd_), 'value': pd_}
                if not ok and exp is not None:
                    r['hint'] = _plot_hint(pd_, exp)
            else:
                exp = c.get('expected')
                ok = same(got, exp, mode) if 'expected' in c else True
                r = {'ok': ok, 'got': short_repr(got), 'value': got if isinstance(got, (int, float, str, bool, type(None))) else short_repr(got)}
                if not ok:
                    h = _num_hint(got, exp)
                    if h:
                        r['hint'] = h
            out['results'].append(r)
    finally:
        sys.stdout, sys.stderr, builtins.input = old_out, old_err, old_input
        wctx.__exit__(None, None, None)
        os.chdir(old_cwd)
        if plt is not None:
            plt.show = old_show
            plt.close('all')
    out['stdout'] = cap.getvalue()
    out['stdoutCut'] = cap.size > stdout_limit
    return json.dumps(out, ensure_ascii=False, default=str)


def run_check(code, cwd):
    """중간 점검의 check(def answers())를 데이터 폴더에서 실행해 [str(값)…]을 돌려준다(검수 도구용)."""
    old = os.getcwd()
    try:
        os.chdir(cwd)
        ns = {'__name__': '__main__', '__builtins__': builtins}
        exec(compile(code, '<check>', 'exec'), ns)
        return json.dumps([str(_plain(x)) for x in ns['answers']()], ensure_ascii=False)
    finally:
        os.chdir(old)


if __name__ == '__main__':
    # 검수 도구용: stdin으로 {code, func, cases, mode, lang, spec}를 받아 결과 JSON을 출력(lang이 'c'면 C 인터프리터)
    req = json.loads(sys.stdin.read())
    if req.get('lang') == 'c':
        res = run_cases_c(req['code'], req['func'], json.dumps(req['cases']), req.get('mode', 'exact'), json.dumps(req.get('spec') or {}))
    else:
        res = run_cases(req['code'], req['func'], json.dumps(req['cases']), req.get('mode', 'exact'))
    sys.__stdout__.write(res)
