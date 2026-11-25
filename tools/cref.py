#!/usr/bin/env python3
"""gcc 대조 실행기(검수 도구용). 명세: docs/CINTERP_SPEC.md

run_gcc(code, func, cases, spec) -> [{ok, value | error, stdout}]
- 매개변수 선언을 pycparser(src/grader/cinterp.py와 같은 해석)로 읽고, 테스트 args를 C 리터럴로 바꾼 시험용 main을
  따로 만든 C 파일(드라이버)에 생성한다. 학생 코드는 따로 컴파일하고(main이 있으면 이름을 바꿈) 함께 링크한다.
- gcc -O0 -fsanitize=address,undefined -fno-sanitize-recover=undefined -w 로 컴파일하고, 테스트마다 따로 실행한다(시간 제한 10초).
  범위 밖 접근·정의되지 않은 동작은 오류(ok: false)로 돌려준다.
- 반환값은 run_cases_c와 같은 규칙으로 JSON 값이 된다(char* → 문자열, int* → spec.ret.len개 리스트, bool → true/false, char → 한 글자).
- 생성 코드·실행 파일은 임시 폴더에 만들고 지운다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_G = os.path.join(ROOT, 'src', 'grader')
if _G not in sys.path:
    sys.path.insert(0, _G)
import cinterp as ci  # noqa: E402

MARK = '@@SAICERTI-RESULT@@'
GCC = os.environ.get('CREF_GCC', 'gcc')
CFLAGS = ['-O0', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined', '-w']
ENV = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:symbolize=0:abort_on_error=0', UBSAN_OPTIONS='print_stacktrace=0')

_HELPERS = r'''
static void sc_jstr(const char *s) {
    putchar('"');
    for (const unsigned char *p = (const unsigned char *)s; *p; p++) {
        unsigned c = *p;
        if (c == '"' || c == '\\') printf("\\%c", (int)c);
        else if (c < 0x20 || c == 0x7f) printf("\\u%04x", c);
        else putchar((int)c);
    }
    putchar('"');
}
static void sc_jchr(char ch) {
    unsigned c = (unsigned char)ch;
    if (c == '"' || c == '\\') printf("\"\\%c\"", (int)c);
    else if (c < 0x20 || c >= 0x7f) printf("\"\\u%04x\"", c);
    else printf("\"%c\"", (int)c);
}
static void sc_jdbl(double d) {
    if (d != d) printf("NaN");
    else if (d > 1.7976931348623157e308) printf("Infinity");
    else if (d < -1.7976931348623157e308) printf("-Infinity");
    else printf("%.17g", d);
}
'''


class _Gen:
    def __init__(self):
        self.snames = {}
        self.sorder = []
        self.n = 0

    def tmp(self):
        self.n += 1
        return f'sc_v{self.n}'

    # ---- 타입 → C 선언
    def sname(self, st):
        if st not in self.snames:
            self.snames[st] = f'sc_s{len(self.snames)}'
            for F in st.fields:
                self.collect(F.t)
            self.sorder.append(st)
        return self.snames[st]

    def collect(self, t):
        c = t.__class__
        if c is ci.StructT:
            self.sname(t)
        elif c is ci.Ptr:
            to = t.to
            if to.__class__ is ci.StructT:
                if to not in self.snames:
                    self.snames[to] = f'sc_s{len(self.snames)}'
                    for F in to.fields:
                        self.collect(F.t)
                    self.sorder.append(to)
            else:
                self.collect(to)
        elif c is ci.Arr:
            self.collect(t.of)
        elif c is ci.FuncT:
            self.collect(t.ret)
            for p in t.params:
                self.collect(p)

    def cdecl(self, t, inner=''):
        c = t.__class__
        if c is ci.Prim:
            return f'{t.name} {inner}'.strip()
        if c is ci.VoidT:
            return f'void {inner}'.strip()
        if c is ci.StructT:
            return f'{"union" if t.union else "struct"} {self.snames[t]} {inner}'.strip()
        if c is ci.Ptr:
            if t.to.__class__ in (ci.Arr, ci.FuncT):
                return self.cdecl(t.to, f'(*{inner})')
            return self.cdecl(t.to, f'*{inner}')
        if c is ci.Arr:
            return self.cdecl(t.of, f'{inner}[{t.n or 0}]')
        if c is ci.FuncT:
            ps = ', '.join(self.cdecl(p) for p in t.params) or 'void'
            return self.cdecl(t.ret, f'{inner}({ps})')
        raise ValueError(f'C 선언으로 바꿀 수 없는 타입: {ci.tname(t)}')

    def struct_defs(self):
        out = [f'{"union" if st.union else "struct"} {self.snames[st]};' for st in self.sorder]
        done = set()

        def emit(st):
            if st in done:
                return
            done.add(st)
            for F in st.fields:
                b = F.t
                while b.__class__ is ci.Arr:
                    b = b.of
                if b.__class__ is ci.StructT:
                    emit(b)
            body = ' '.join(self.cdecl(F.t, F.name) + ';' for F in st.fields)
            out.append(f'{"union" if st.union else "struct"} {self.snames[st]} {{ {body} }};')
        for st in self.sorder:
            emit(st)
        return '\n'.join(out)

    # ---- JSON 값 → C
    @staticmethod
    def int_lit(t, v):
        if t.signed:
            if v == -(1 << 63):
                return f'(({t.name})(-9223372036854775807LL-1))'
            return f'(({t.name})({v}LL))'
        return f'(({t.name})({v}ULL))'

    @staticmethod
    def dbl_lit(v):
        if v != v:
            return '(0.0/0.0)'
        if v in (float('inf'), float('-inf')):
            return '(1.0/0.0)' if v > 0 else '(-1.0/0.0)'
        s = repr(float(v))
        return f'({s})'

    @staticmethod
    def c_str(bs):
        out = []
        for b in bs:
            ch = chr(b)
            if 0x20 <= b < 0x7f and ch not in '"\\?':
                out.append(ch)
            else:
                out.append('\\%03o' % b)
        return '"' + ''.join(out) + '"'

    def scalar(self, t, jv, name, prog):
        v = prog.arg_in(t, jv, name)  # 인터프리터와 같은 규칙으로 검사·변환
        if t.flt:
            lit = self.dbl_lit(v)
            return f'((float){lit})' if t is ci.FLOAT else lit
        if t is ci.BOOL:
            return '((_Bool)1)' if v else '((_Bool)0)'
        return self.int_lit(t, v)

    def value(self, t, jv, name, lines, prog):
        """t 타입 값의 C 식(필요한 준비 문장은 lines에)."""
        c = t.__class__
        if c is ci.Prim:
            return self.scalar(t, jv, name, prog)
        if c is ci.Ptr:
            if jv is None:
                return '0'
            et = t.to
            v = self.tmp()
            if isinstance(jv, str):
                if not ci.is_charish(et):
                    raise ci._argerr(name, t, jv)
                bs = jv.encode('utf-8') + b'\0'
                lines.append(f'char *{v} = (char *)malloc({len(bs)}); memcpy({v}, {self.c_str(bs)}, {len(bs)});')
                return f'(({self.cdecl(t)}){v})'
            if isinstance(jv, dict) and et.__class__ is ci.StructT:
                items = [jv]
            elif isinstance(jv, list):
                items = jv
            else:
                raise ci._argerr(name, t, jv)
            lines.append(f'{self.cdecl(ci.Ptr(et), v)} = malloc({len(items)} * sizeof *{v});')
            if et.__class__ is ci.Prim and items:
                lits = ', '.join(self.scalar(et, x, f'{name}[{i}]', prog) for i, x in enumerate(items))
                lines.append(f'{{ static const {self.cdecl(et, "sd[]")} = {{ {lits} }}; memcpy({v}, sd, sizeof sd); }}')
            else:
                for i, x in enumerate(items):
                    self.store(et, f'{v}[{i}]', x, f'{name}[{i}]', lines, prog)
            return v
        if c is ci.StructT:
            v = self.tmp()
            lines.append(f'{self.cdecl(t, v)}; memset(&{v}, 0, sizeof {v});')
            self.store(t, v, jv, name, lines, prog)
            return v
        raise ValueError(f'매개변수 {name}의 타입({ci.tname(t)})은 테스트 값으로 넣을 수 없어요.')

    def store(self, t, lv, jv, name, lines, prog):
        c = t.__class__
        if c is ci.Prim or c is ci.Ptr:
            lines.append(f'{lv} = {self.value(t, jv, name, lines, prog)};')
            return
        if c is ci.Arr:
            if isinstance(jv, str) and ci.is_charish(t.of):
                bs = jv.encode('utf-8')
                if len(bs) > t.n:
                    raise ValueError(f'{name}에 넣을 문자열이 너무 길어요.')
                bs = bs + b'\0' * (t.n - len(bs))
                lines.append(f'memcpy({lv}, {self.c_str(bs)}, {t.n});')
                return
            if not isinstance(jv, list) or len(jv) != t.n:
                raise ValueError(f'{name}은(는) 길이 {t.n}인 리스트여야 해요: {jv!r}'[:200])
            for j, x in enumerate(jv):
                self.store(t.of, f'{lv}[{j}]', x, f'{name}[{j}]', lines, prog)
            return
        if c is ci.StructT:
            if not isinstance(jv, dict) or set(jv) != set(t.fmap):
                raise ValueError(f'{name}의 멤버가 구조체와 맞지 않아요: {jv!r}'[:200])
            for F in t.fields:
                self.store(F.t, f'{lv}.{F.name}', jv[F.name], f'{name}.{F.name}', lines, prog)
            return
        raise ValueError(f'{name}의 타입({ci.tname(t)})은 테스트 값으로 넣을 수 없어요.')

    # ---- 반환값 출력
    def emit_out(self, t, ex, env, rs, key, lines, depth=0):
        c = t.__class__
        if c is ci.Prim:
            if t is ci.BOOL:
                lines.append(f'printf("%s", ({ex}) ? "true" : "false");')
            elif t.flt:
                lines.append(f'sc_jdbl((double)({ex}));')
            elif t.size == 1:
                lines.append(f'sc_jchr((char)({ex}));')
            elif t.signed:
                lines.append(f'printf("%lld", (long long)({ex}));')
            else:
                lines.append(f'printf("%llu", (unsigned long long)({ex}));')
            return
        if c is ci.Ptr:
            et = t.to
            if ci.is_charish(et):
                lines.append(f'if ({ex}) sc_jstr((const char *)({ex})); else printf("null");')
                return
            if key not in rs:
                raise ValueError(f'반환 타입이 {ci.tname(t)}이면 spec.ret.{key}(돌려줄 원소 수)가 필요해요.')
            n = ci.eval_len(rs[key], env)
            i = f'sc_i{depth}'
            lines.append(f'if (!({ex})) printf("null"); else {{ printf("["); for (long {i} = 0; {i} < {n}; {i}++) {{ if ({i}) printf(",");')
            self.emit_out(et, f'({ex})[{i}]', env, rs, 'len2', lines, depth + 1)
            lines.append('} printf("]"); }')
            return
        if c is ci.Arr:
            if ci.is_charish(t.of):
                lines.append(f'{{ char sc_b[{t.n + 1}]; memcpy(sc_b, {ex}, {t.n}); sc_b[{t.n}] = 0; sc_jstr(sc_b); }}')
                return
            i = f'sc_i{depth}'
            lines.append(f'printf("["); for (long {i} = 0; {i} < {t.n}; {i}++) {{ if ({i}) printf(",");')
            self.emit_out(t.of, f'({ex})[{i}]', env, rs, key, lines, depth + 1)
            lines.append('} printf("]");')
            return
        if c is ci.StructT:
            lines.append('printf("{");')
            for k, F in enumerate(t.fields):
                lines.append(f'printf("%s\\"{F.name}\\":", "{"," if k else ""}");')
                self.emit_out(F.t, f'({ex}).{F.name}', {}, {}, 'len', lines, depth + 1)
            lines.append('printf("}");')
            return
        raise ValueError(f'반환 타입 {ci.tname(t)}은 채점할 수 없어요.')


def _fix(t, v):
    """gcc 출력 JSON 값을 인터프리터와 같은 파이썬 타입으로 맞춘다."""
    c = t.__class__
    if v is None:
        return None
    if c is ci.Prim:
        if t is ci.BOOL:
            return bool(v)
        if t.flt:
            return float(v)
        return v
    if c is ci.Ptr:
        if ci.is_charish(t.to):
            return v
        return [_fix(t.to, x) for x in v]
    if c is ci.Arr:
        if ci.is_charish(t.of):
            return v
        return [_fix(t.of, x) for x in v]
    if c is ci.StructT:
        return {F.name: _fix(F.t, v[F.name]) for F in t.fields}
    return v


def _san_msg(err):
    lines = [x for x in err.splitlines() if x.strip()]
    for x in lines:
        if 'runtime error:' in x or 'ERROR: AddressSanitizer' in x or 'ERROR: LeakSanitizer' in x:
            s = x.strip()
            i = s.find('runtime error:')
            return s[i:] if i >= 0 else s[s.find('ERROR:'):]
    for x in lines:
        if 'SUMMARY:' in x:
            return x.strip()
    return (lines[-1] if lines else '').strip()[:300]


def run_gcc(code, func, cases, spec=None, timeout=10):
    """gcc로 code의 func를 cases마다 실행한다. [{ok: bool, value | error, stdout}]"""
    spec = spec or {}
    rs = spec.get('ret') or {}
    names, ptypes, ret = ci.signature(code, func)
    if any(n is None for n in names):
        raise ValueError(f'{func}의 매개변수에 이름이 없어요.')
    g = _Gen()
    for t in list(ptypes) + [ret]:
        g.collect(t)
    shim = ci.Program.__new__(ci.Program)  # JSON 인자 검사(arg_in)만 쓰는 빈 실행 단위
    shim.rt = ci.Runtime()
    results = [None] * len(cases)
    bodies = []
    for k, c in enumerate(cases):
        try:
            full = ci.expand_args(names, c['args'], spec)
            env = dict(zip(names, full))
            pre = []
            argx = [g.value(t, jv, nm, pre, shim) for t, jv, nm in zip(ptypes, full, names)]
            post = []
            call = f'{func}({", ".join(argx)})'
            if ret is ci.VOID:
                pre.append(f'{call};')
                post.append('printf("null");')
            else:
                pre.append(f'{g.cdecl(ret, "sc_r")} = {call};')
                g.emit_out(ret, 'sc_r', env, rs, 'len', post)
            bodies.append((k, pre, post))
        except (ValueError, ci.CError) as e:
            results[k] = {'ok': False, 'error': f'인자 변환 실패: {getattr(e, "msg", None) or e}'}
    proto = f'{g.cdecl(ci.FuncT(ret, list(ptypes)), func)};'
    drv = ['#include <stdio.h>', '#include <stdlib.h>', '#include <string.h>', g.struct_defs(), proto, _HELPERS]
    for k, pre, post in bodies:
        drv.append(f'static void sc_case{k}(void) {{')
        drv.extend('    ' + x for x in pre)
        drv.append(f'    printf("\\n{MARK}");')
        drv.extend('    ' + x for x in post)
        drv.append('    printf("\\n"); fflush(stdout);')
        drv.append('}')
    drv.append('int main(int argc, char **argv) {')
    drv.append('    int k = argc > 1 ? atoi(argv[1]) : -1;')
    drv.append('    switch (k) {')
    for k, _, _ in bodies:
        drv.append(f'    case {k}: sc_case{k}(); break;')
    drv.append('    default: return 3;')
    drv.append('    }')
    drv.append('    return 0;')
    drv.append('}')
    d = tempfile.mkdtemp(prefix='saicerti-cref-')
    try:
        with open(os.path.join(d, 'user.c'), 'w', encoding='utf-8') as f:
            f.write(code)
        with open(os.path.join(d, 'driver.c'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(drv) + '\n')
        steps = [
            [GCC, *CFLAGS, '-Dmain=saicerti_user_main_', '-c', 'user.c', '-o', 'user.o'],
            [GCC, *CFLAGS, '-c', 'driver.c', '-o', 'driver.o'],
            [GCC, *CFLAGS, 'user.o', 'driver.o', '-o', 'prog', '-lm'],
        ]
        for cmd in steps:
            p = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                msg = 'gcc 컴파일 오류: ' + (p.stderr.strip()[-800:] or p.stdout.strip()[-800:])
                return [r or {'ok': False, 'error': msg} for r in results]
        for k, _, _ in bodies:
            try:
                p = subprocess.run([os.path.join(d, 'prog'), str(k)], cwd=d, capture_output=True, timeout=timeout, env=ENV)
            except subprocess.TimeoutExpired:
                results[k] = {'ok': False, 'error': f'시간 초과({timeout}초)'}
                continue
            out = p.stdout.decode('utf-8', 'replace')
            err = p.stderr.decode('utf-8', 'replace')
            if MARK not in out:
                why = _san_msg(err) if err.strip() else f'종료 코드 {p.returncode}'
                results[k] = {'ok': False, 'error': f'gcc 실행 오류: {why}', 'stdout': out}
                continue
            before, after = out.rsplit('\n' + MARK, 1)
            line = after.split('\n', 1)[0]
            if p.returncode != 0 or 'runtime error:' in err or 'ERROR: AddressSanitizer' in err:
                results[k] = {'ok': False, 'error': f'gcc 실행 오류: {_san_msg(err) or "종료 코드 " + str(p.returncode)}', 'stdout': before}
                continue
            try:
                v = json.loads(line)
            except ValueError:
                results[k] = {'ok': False, 'error': f'결과를 읽지 못했어요: {line[:200]!r}', 'stdout': before}
                continue
            results[k] = {'ok': True, 'value': _fix(ret, v), 'stdout': before}
    finally:
        shutil.rmtree(d, ignore_errors=True)
    return results


if __name__ == '__main__':
    # 사용: python3 tools/cref.py < {"code", "func", "cases", "spec"} JSON
    req = json.loads(sys.stdin.read())
    print(json.dumps(run_gcc(req['code'], req['func'], req['cases'], req.get('spec') or {}), ensure_ascii=False))
