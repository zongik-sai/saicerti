# saicerti C 인터프리터(cinterp) — 명세: docs/CINTERP_SPEC.md
# - COS Pro 2급 C 수준의 코드를 pycparser(3.12)로 파싱하고, 한 번 Python 클로저로 컴파일해 실행한다.
# - 브라우저(Pyodide)와 검수 도구(CPython)가 같은 파일을 쓴다. 순수 Python, 표준 라이브러리 + pycparser만 쓴다.
# - 학생 코드를 서버로 보내지 않는다(이 파일 안에서만 실행).
# - 메모리: 블록(bytearray + 초기화 표시) + 포인터(정수 주소 = 블록번호 << 32 + 2^31 + 오프셋).
#   범위 밖·해제된 메모리·NULL·초기화하지 않은 값 읽기는 한국어 런타임 오류로 멈춘다.
import functools
import math
import os
import re
import struct
import sys
import time


def _load_pycparser():
    """같은 폴더 vendor/의 pycparser 3.12 wheel을 먼저 쓴다(브라우저에서는 워커가 미리 넣어 둔 pycparser)."""
    here = ''
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        pass
    whl = os.path.join(here, 'vendor', 'pycparser-3.12-py3-none-any.whl') if here else ''
    if whl and os.path.exists(whl):
        mod = sys.modules.get('pycparser')
        if mod is not None and getattr(mod, '__version__', '') != '3.12':
            for k in [k for k in sys.modules if k == 'pycparser' or k.startswith('pycparser.')]:
                del sys.modules[k]
        if whl not in sys.path:
            sys.path.insert(0, whl)
    try:
        import pycparser  # noqa: F401
    except ImportError as e:
        if 'subprocess' in str(e):  # 일부 환경(브라우저)에서 subprocess를 못 불러오면 빈 모듈로 대신한다
            import types
            sys.modules['subprocess'] = types.ModuleType('subprocess')
            sys.modules['subprocess'].check_output = None
            import pycparser  # noqa: F401
        else:
            raise
    from pycparser import c_ast as _ast, c_parser as _parser
    return _ast, _parser


c_ast, c_parser = _load_pycparser()

MAX_DEPTH = 2000          # 재귀 깊이 제한
MAX_STEPS = 20_000_000    # 실행 단계(반복 1회·함수 호출 1회) 제한
OUT_CAP = 1 << 16         # 출력 모으는 최대 바이트
HEAP_CAP = 64 << 20       # malloc 총량
STACK_CAP = 8 << 20       # 지역 배열 하나의 최대 크기
SH = 32
BIAS = 1 << 31
MASK = (1 << 32) - 1
PY_RECURSION = 60000

# ---------------------------------------------------------------- 오류
H_OOB = '인덱스는 0부터 (크기-1)까지예요. 반복 조건(<, <=)이나 인덱스 계산을 확인해 보세요.'
H_UNINIT = "값을 넣기 전에 읽었어요. 변수를 만들 때 처음 값(예: int answer = 0;)을 넣었는지, 배열 칸에 값을 넣은 뒤 읽는지 확인해 보세요."
H_UNINIT_STR = "문자열을 읽다가 값을 넣지 않은 칸을 만났어요. 문자열 끝에 '\\0'을 넣었는지 확인해 보세요."
H_NUL = "문자열은 끝에 '\\0'이 있어야 해요. 배열 크기를 (글자 수 + 1)로 만들었는지, 끝에 '\\0'을 넣었는지 확인해 보세요."
H_NULL = '포인터에 malloc 결과나 변수의 주소를 넣었는지, NULL인지 먼저 확인했는지 살펴보세요.'
H_FREED = 'free 한 메모리를 다시 쓰거나, 함수 안 지역 배열의 주소를 return 하지 않았는지 확인해 보세요. (지역 배열은 함수가 끝나면 사라져요. 돌려줄 배열은 malloc으로 만드세요.)'
H_BADPTR = '포인터에 올바른 주소가 들어 있는지 확인해 보세요.'
H_RO = 'char *s = "..." 는 바꿀 수 없는 문자열 상수를 가리켜요. 바꾸려면 char s[] = "..." 처럼 배열로 만드세요.'
H_DIV0 = '나누는 수가 0이 되지 않는지 확인해 보세요.'
H_TIME = '반복 조건이 언젠가 거짓이 되는지, 반복할 때마다 변수가 바뀌는지 확인해 보세요.'
H_REC = '재귀를 멈추는 조건(기저 사례)이 있는지, 부를 때마다 문제가 작아지는지 확인해 보세요.'
H_SYNTAX = '세미콜론(;)·괄호·중괄호 짝이 맞는지, 바로 앞 줄 끝을 확인해 보세요.'
H_TYPE = '변수와 값의 타입(int, 포인터, 배열 등)이 맞는지 확인해 보세요.'
H_FMT = 'printf 서식과 값의 타입이 맞아야 해요: 정수 %d, 실수 %f, 문자 %c, 문자열 %s.'


class CError(Exception):
    kind = 'RuntimeError'

    def __init__(self, msg, line=None, hint='', kind=None):
        super().__init__(msg)
        self.msg = msg
        self.line = line
        self.hint = hint
        if kind:
            self.kind = kind

    def as_dict(self):
        return {'type': self.kind, 'message': self.msg[:600], 'line': self.line, 'hint': self.hint}


class CCompileError(CError):
    kind = 'CompileError'


class CRuntimeError(CError):
    kind = 'RuntimeError'


class CExit(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


_CUT = (CError, CExit)


def _ln(n):
    c = getattr(n, 'coord', None)
    return c.line if c is not None else None


# ---------------------------------------------------------------- 타입
class CType:
    __slots__ = ()

    def __repr__(self):
        return tname(self)


class Prim(CType):
    __slots__ = ('name', 'size', 'align', 'signed', 'flt', 'rank', 'lo', 'hi', 'pk', 'up')

    def __init__(self, name, size, signed, rank, fmt, flt=False):
        self.name = name
        self.size = size
        self.align = size
        self.signed = signed
        self.flt = flt
        self.rank = rank
        if flt:
            self.lo = -math.inf
            self.hi = math.inf
        elif name == '_Bool':
            self.lo, self.hi = 0, 1
        elif signed:
            self.lo, self.hi = -(1 << (size * 8 - 1)), (1 << (size * 8 - 1)) - 1
        else:
            self.lo, self.hi = 0, (1 << (size * 8)) - 1
        st = struct.Struct('<' + fmt)
        self.pk = st.pack_into
        self.up = st.unpack_from


BOOL = Prim('_Bool', 1, False, 0, 'B')
CHAR = Prim('char', 1, True, 1, 'b')
SCHAR = Prim('signed char', 1, True, 1, 'b')
UCHAR = Prim('unsigned char', 1, False, 1, 'B')
SHORT = Prim('short', 2, True, 2, 'h')
USHORT = Prim('unsigned short', 2, False, 2, 'H')
INT = Prim('int', 4, True, 3, 'i')
UINT = Prim('unsigned int', 4, False, 3, 'I')
LONG = Prim('long', 8, True, 4, 'q')
ULONG = Prim('unsigned long', 8, False, 4, 'Q')
LLONG = Prim('long long', 8, True, 5, 'q')
ULLONG = Prim('unsigned long long', 8, False, 5, 'Q')
FLOAT = Prim('float', 4, True, 10, 'f', flt=True)
DOUBLE = Prim('double', 8, True, 11, 'd', flt=True)
LDOUBLE = Prim('long double', 16, True, 12, 'd', flt=True)  # 값은 double로 다룬다(크기만 16)
_UNSIGNED_OF = {INT: UINT, LONG: ULONG, LLONG: ULLONG, UINT: UINT, ULONG: ULONG, ULLONG: ULLONG}


class VoidT(CType):
    __slots__ = ()
    size = 1
    align = 1


VOID = VoidT()
_PST = struct.Struct('<q')


class Ptr(CType):
    __slots__ = ('to', 'cto')
    size = 8
    align = 8
    pk = _PST.pack_into
    up = _PST.unpack_from

    def __init__(self, to, cto=False):
        self.to = to
        self.cto = cto


class Arr(CType):
    __slots__ = ('of', 'n', 'vla')

    def __init__(self, of, n, vla=None):
        self.of = of
        self.n = n
        self.vla = vla  # 가변 길이 배열이면 크기를 담는 프레임 칸 번호

    @property
    def size(self):
        return self.of.size * (self.n or 0)

    @property
    def align(self):
        return self.of.align


class Field:
    __slots__ = ('name', 't', 'off', 'ro')

    def __init__(self, name, t, off, ro):
        self.name = name
        self.t = t
        self.off = off
        self.ro = ro


class StructT(CType):
    __slots__ = ('tag', 'fields', 'fmap', 'size', 'align', 'complete', 'union', 'tdname')

    def __init__(self, tag, union=False):
        self.tag = tag
        self.union = union
        self.fields = []
        self.fmap = {}
        self.size = 0
        self.align = 1
        self.complete = False
        self.tdname = None


class FuncT(CType):
    __slots__ = ('ret', 'params', 'variadic')
    size = 1
    align = 1

    def __init__(self, ret, params, variadic=False):
        self.ret = ret
        self.params = params
        self.variadic = variadic


def tname(t):
    c = t.__class__
    if c is Prim:
        return 'bool' if t is BOOL else t.name
    if c is VoidT:
        return 'void'
    if c is Ptr:
        to = t.to
        if to.__class__ is Arr:
            return f'{tname(to.of)} (*)[{to.n if to.n is not None else ""}]'
        if to.__class__ is FuncT:
            return f'{tname(to.ret)} (*)({", ".join(tname(p) for p in to.params)})'
        return ('const ' if t.cto else '') + tname(to) + '*'
    if c is Arr:
        dims = ''
        while t.__class__ is Arr:
            dims += f'[{t.n if t.n is not None else ""}]'
            t = t.of
        return tname(t) + dims
    if c is StructT:
        return t.tdname or (('union ' if t.union else 'struct ') + (t.tag or '(이름 없음)'))
    if c is FuncT:
        return f'{tname(t.ret)} ({", ".join(tname(p) for p in t.params)})'
    return '?'


def is_int(t):
    return t.__class__ is Prim and not t.flt


def is_flt(t):
    return t.__class__ is Prim and t.flt


def is_arith(t):
    return t.__class__ is Prim


def is_ptr(t):
    return t.__class__ is Ptr


def is_scalar(t):
    return t.__class__ is Prim or t.__class__ is Ptr


def is_charish(t):
    return t.__class__ is Prim and t.size == 1 and not t.flt and t is not BOOL


def is_vla(t):
    while t.__class__ is Arr:
        if t.vla is not None:
            return True
        t = t.of
    return False


def promote(t):
    if t.__class__ is Prim and not t.flt and t.rank < 3:
        return INT
    return t


def usual_arith(a, b):
    if a.flt or b.flt:
        if not a.flt:
            return b
        if not b.flt:
            return a
        return a if a.rank >= b.rank else b
    a = promote(a)
    b = promote(b)
    if a is b:
        return a
    if a.signed == b.signed:
        return a if a.rank >= b.rank else b
    u, s = (b, a) if a.signed else (a, b)
    if u.rank >= s.rank:
        return u
    if s.size > u.size:
        return s
    return _UNSIGNED_OF[s]


def same_type(a, b):
    if a is b:
        return True
    ca = a.__class__
    if ca is not b.__class__:
        return False
    if ca is Ptr:
        return same_type(a.to, b.to)
    if ca is Arr:
        return (a.n is None or b.n is None or a.n == b.n) and same_type(a.of, b.of)
    if ca is FuncT:
        return True
    if ca is Prim:
        return a.size == b.size and a.flt == b.flt and a.signed == b.signed and (a.rank == b.rank or a.size == 8)
    return False


def ptr_compat(d, s):
    a, b = d.to, s.to
    if a is VOID or b is VOID:
        return True
    if a.__class__ is Prim and b.__class__ is Prim:
        if a is b:
            return True
        return not a.flt and not b.flt and a.size == b.size  # 부호만 다른 정수 포인터(gcc 경고)
    if a.__class__ is FuncT and b.__class__ is FuncT:
        return True
    return same_type(a, b)


def arr_dims(t):
    """배열 타입의 (차원 목록, 맨 안쪽 원소 타입)."""
    dims = []
    while t.__class__ is Arr:
        dims.append(t.n or 0)
        t = t.of
    return tuple(dims), t


_F32 = struct.Struct('<f')


def f32(x):
    try:
        return _F32.unpack(_F32.pack(x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def _tobool(v):
    return 1 if v else 0


_WRAP = {}


def wrapf(t):
    w = _WRAP.get(t)
    if w is not None:
        return w
    if t is BOOL:
        w = _tobool
    elif t.__class__ is Prim and t.flt:
        w = f32 if t is FLOAT else float
    else:
        bits = t.size * 8
        m = (1 << bits) - 1
        if t.signed:
            half = 1 << (bits - 1)

            def w(v, half=half, m=m):
                return ((v + half) & m) - half
        else:
            def w(v, m=m):
                return v & m
    _WRAP[t] = w
    return w


def _f2i(dst):
    w = wrapf(dst)
    if dst.signed and dst.size == 8:
        def f(v):
            if v != v or v >= 9.223372036854776e18 or v < -9.223372036854776e18:
                return -(1 << 63)
            return int(v)
    elif dst.size < 4 or (dst.size == 4 and dst.signed):
        def f(v):
            if v != v or not (-2147483649.0 < v < 2147483648.0):
                return w(-2147483648)
            return w(int(v))
    elif dst.size == 4:  # unsigned int: 64비트로 바꾼 뒤 아래 32비트(gcc x86-64와 같음)
        def f(v):
            if v != v or not (-9.223372036854776e18 <= v < 9.223372036854776e18):
                return 0
            return w(int(v))
    else:  # unsigned long: 2^63 이상이면 2^63을 빼고 바꾼 뒤 최상위 비트를 뒤집는다(gcc x86-64와 같음)
        def c64(x):
            if x != x or x >= 9.223372036854776e18 or x < -9.223372036854776e18:
                return -(1 << 63)
            return int(x)

        def f(v):
            if v < 9.223372036854776e18 or v != v:
                return w(c64(v))
            return w(c64(v - 9.223372036854776e18) ^ (1 << 63))
    return f


def _i2f32(v):
    return f32(float(v))


def conv_fn(src, dst):
    """src 타입 값을 dst 타입으로 바꾸는 함수(바꿀 필요 없으면 None)."""
    if dst is src:
        return None
    dc = dst.__class__
    sc = src.__class__
    if dc is Prim:
        if dst is BOOL:
            return None if src is BOOL else _tobool
        if not dst.flt:
            if sc is Prim:
                if src.flt:
                    return _f2i(dst)
                if dst.lo <= src.lo and src.hi <= dst.hi:
                    return None
                return wrapf(dst)
            if sc is Ptr:
                return None if (dst.size == 8 and dst.signed) else wrapf(dst)
            return None
        if sc is Prim:
            if src.flt:
                return f32 if (dst is FLOAT and src is not FLOAT) else None
            return _i2f32 if dst is FLOAT else float
        return None
    return None


# ---------------------------------------------------------------- 메모리 · 실행 상태
class Block:
    __slots__ = ('data', 'init', 'size', 'name', 'kind', 'ro', 'dims', 'esz', 'func', 'st')


_ONES = {n: b'\x01' * n for n in range(0, 33)}


def _ones(n):
    o = _ONES.get(n)
    return o if o is not None else b'\x01' * n


def _fpath(st, off):
    for F in st.fields:
        if F.off <= off < F.off + F.t.size:
            r = off - F.off
            s = '.' + F.name
            t = F.t
            while t.__class__ is Arr:
                es = t.of.size or 1
                s += '[%d]' % (r // es)
                r %= es
                t = t.of
            if t.__class__ is StructT:
                s += _fpath(t, r)
            return s
    return ''


class Runtime:
    def __init__(self):
        self.B = {}
        self.next = 1
        self.dyn0 = 1
        self.out = bytearray()
        self.out_total = 0
        self.max_steps = MAX_STEPS
        self.left = MAX_STEPS
        self.depth = 0
        self.deadline = None
        self.heap = 0
        self.srand(1)

    # ---- 블록
    def new_block(self, size, name, kind, init=False, dims=None, esz=0, ro=False, data=None, st=None):
        bid = self.next
        self.next = bid + 1
        b = Block()
        b.data = bytearray(size) if data is None else bytearray(data)
        b.init = (bytearray(b'\x01') * size) if init else bytearray(size)
        b.size = size
        b.name = name
        b.kind = kind
        b.ro = ro
        b.dims = dims
        b.esz = esz
        b.func = None
        b.st = st
        self.B[bid] = b
        return (bid << SH) + BIAS

    # ---- 오류
    def bad(self, a, line, write=False):
        bid = a >> SH
        if bid == 0:
            raise CRuntimeError('NULL 포인터를 사용했어요: 가리키는 메모리가 없는 포인터로 값을 ' + ('바꾸려고' if write else '읽으려고') + ' 했어요.', line, H_NULL)
        if self.dyn0 <= bid < self.next:
            raise CRuntimeError('이미 해제(free)했거나 함수가 끝나 사라진 메모리를 사용했어요.', line, H_FREED)
        raise CRuntimeError('잘못된 주소(포인터)를 사용했어요.', line, H_BADPTR)

    def where(self, b, o, n, size=False):
        esz = b.esz or n or 1
        dims = b.dims
        if not dims and b.kind in ('heap', 'arg') and b.size % esz == 0:
            dims = (b.size // esz,)
        if dims:
            flat, rem = divmod(o, esz)
            idx = []
            for d in reversed(dims[1:]):
                flat, r = divmod(flat, d or 1)
                idx.append(r)
            idx.append(flat)
            s = b.name + ''.join('[%d]' % i for i in reversed(idx))
            if b.st is not None and 0 <= o < b.size:
                s += _fpath(b.st, rem)
            if size:
                s += ' (크기 %s)' % '×'.join(map(str, dims))
            return s
        if b.st is not None and 0 <= o < b.size:
            return b.name + _fpath(b.st, o)
        s = '%s의 %d번째 바이트' % (b.name, o)
        if size:
            s += ' (크기 %d바이트)' % b.size
        return s

    def oob(self, b, o, n, line, write=False):
        if write and b.ro and 0 <= o and o + n <= b.size:
            raise CRuntimeError('문자열 상수는 바꿀 수 없어요: ' + b.name, line, H_RO)
        if b.kind == 'func':
            raise CRuntimeError('함수 주소를 배열(데이터)처럼 읽거나 썼어요.', line, H_BADPTR)
        bad = o if (o < 0 or o >= b.size) else b.size
        raise CRuntimeError('배열(메모리) 범위를 벗어났어요: ' + self.where(b, bad, n, True), line, H_OOB)

    def uninit(self, b, o, n, line, hint=H_UNINIT):
        raise CRuntimeError('초기화하지 않은 값을 읽었어요: ' + self.where(b, o, n), line, hint)

    def chk(self, a, n, line, write=False):
        try:
            b = self.B[a >> SH]
        except KeyError:
            self.bad(a, line, write)
        o = (a & MASK) - BIAS
        if o < 0 or o + n > b.size or (write and b.ro):
            self.oob(b, o, n, line, write)
        return b, o

    def rd(self, a, t, line):
        b, o = self.chk(a, t.size, line)
        if not b.init[o]:
            self.uninit(b, o, t.size, line)
        return t.up(b.data, o)[0]

    def wr(self, a, t, v, line):
        b, o = self.chk(a, t.size, line, True)
        t.pk(b.data, o, v)
        b.init[o:o + t.size] = _ones(t.size)

    def cstr(self, a, line, limit=None):
        """널 문자까지(또는 limit 바이트까지) 읽은 bytes."""
        try:
            b = self.B[a >> SH]
        except KeyError:
            self.bad(a, line)
        o = (a & MASK) - BIAS
        size = b.size
        if limit == 0 and 0 <= o <= size:
            return b''
        if o < 0 or o >= size:
            self.oob(b, o, 1, line)
        data = b.data
        stop = size if limit is None else min(size, o + limit)
        end = data.find(0, o, stop)
        if end < 0:
            z = b.init.find(0, o, stop)
            if z >= 0:
                self.uninit(b, z, 1, line, H_UNINIT_STR)
            if limit is not None and o + limit <= size:
                return bytes(data[o:o + limit])
            raise CRuntimeError("문자열 끝('\\0')을 찾지 못하고 배열(메모리) 범위를 벗어났어요: " + self.where(b, size, 1, True), line, H_NUL)
        z = b.init.find(0, o, end + 1)
        if z >= 0:
            self.uninit(b, z, 1, line, H_UNINIT_STR)
        return bytes(data[o:end])

    def wbytes(self, a, bs, line):
        n = len(bs)
        b, o = self.chk(a, n, line, True)
        b.data[o:o + n] = bs
        b.init[o:o + n] = _ones(n)

    def func_at(self, a, line):
        b = self.B.get(a >> SH)
        if b is None or b.func is None or (a & MASK) != BIAS:
            if a == 0:
                raise CRuntimeError('NULL 함수 포인터를 호출했어요.', line, H_NULL)
            raise CRuntimeError('함수가 아닌 주소를 함수처럼 호출했어요.', line, H_BADPTR)
        return b.func

    # ---- 단계 제한
    def spend(self, c):
        left = self.left - c
        self.left = left
        if left < 0:
            raise CRuntimeError('시간 초과: 반복이 끝나지 않아요(실행 단계가 너무 많아요).', None, H_TIME, 'TimeoutError')
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise CRuntimeError('시간 초과: 실행 시간이 너무 길어요.', None, H_TIME, 'TimeoutError')

    def tick(self):
        self.spend(0)

    # ---- 출력
    def emit(self, bs):
        self.out_total += len(bs)
        room = OUT_CAP - len(self.out)
        if room > 0:
            self.out += bs[:room]

    # ---- rand (glibc random_r TYPE_3와 같은 수열)
    def srand(self, seed, line=None):
        seed &= 0xFFFFFFFF
        if seed == 0:
            seed = 1
        st = [0] * 31
        st[0] = seed
        word = seed
        for i in range(1, 31):
            hi, lo = divmod(word, 127773) if word >= 0 else (-((-word) // 127773), -((-word) % 127773))
            word = 16807 * lo - 2836 * hi
            if word < 0:
                word += 2147483647
            st[i] = word & 0xFFFFFFFF
        self.rst = st
        self.rf = 3
        self.rr = 0
        for _ in range(310):
            self.rand()

    def rand(self, line=None):
        st = self.rst
        f = self.rf
        r = self.rr
        v = (st[f] + st[r]) & 0xFFFFFFFF
        st[f] = v
        f += 1
        if f >= 31:
            f = 0
            r += 1
        else:
            r += 1
            if r >= 31:
                r = 0
        self.rf = f
        self.rr = r
        return v >> 1

    # ---- 동적 메모리
    def malloc(self, n, line, zero=False, name='malloc 메모리'):
        if n > HEAP_CAP or self.heap + n > HEAP_CAP:
            raise CRuntimeError(f'메모리를 너무 많이 요청했어요({n}바이트). 크기 계산(예: n * sizeof(int))을 확인해 보세요.', line)
        self.heap += n
        return self.new_block(n, name, 'heap', init=zero)

    def free(self, a, line):
        if a == 0:
            return
        bid = a >> SH
        b = self.B.get(bid)
        if b is None:
            if self.dyn0 <= bid < self.next:
                raise CRuntimeError('이미 해제(free)한 메모리를 또 free 했어요(또는 사라진 지역 변수의 주소예요).', line, H_FREED)
            raise CRuntimeError('free에는 malloc·calloc·realloc으로 받은 주소만 넣을 수 있어요.', line, H_BADPTR)
        if b.kind != 'heap':
            raise CRuntimeError('free에는 malloc·calloc·realloc으로 받은 주소만 넣을 수 있어요. (배열이나 지역 변수의 주소는 free 하지 않아요)', line, H_BADPTR)
        if (a & MASK) != BIAS:
            raise CRuntimeError('free에는 malloc이 돌려준 주소(첫 칸)를 그대로 넣어야 해요.', line, H_BADPTR)
        del self.B[bid]
        self.heap -= b.size


# ---------------------------------------------------------------- printf 서식
_FMT_RE = re.compile(rb'%([-+ #0]*)(\*|\d+)?(?:\.(\*|\d*))?(hh|h|ll|l|L|q|j|z|Z|t)?(.)', re.S)
_LBITS = {None: 32, b'hh': 8, b'h': 16, b'l': 64, b'll': 64, b'L': 64, b'q': 64, b'j': 64, b'z': 64, b'Z': 64, b't': 64}
_FMT_CACHE = {}


def _parse_fmt(fmt, line):
    p = _FMT_CACHE.get(fmt)
    if p is not None:
        return p
    out = []
    i = 0
    n = len(fmt)
    while i < n:
        j = fmt.find(b'%', i)
        if j < 0:
            out.append(fmt[i:])
            break
        if j > i:
            out.append(fmt[i:j])
        m = _FMT_RE.match(fmt, j)
        if not m:
            raise CRuntimeError("printf 서식 끝에 '%'만 있어요. '%'를 출력하려면 %%를 쓰세요.", line, H_FMT)
        flags, width, prec, length, conv = m.groups()
        conv = conv.decode('latin-1')
        if conv not in 'diouxXeEfFgGcsp%n':
            if not conv.isprintable() or conv == ' ':
                raise CRuntimeError("printf 서식의 '%' 다음 글자가 잘못됐어요. '%'를 그대로 출력하려면 %%를 쓰세요.", line, H_FMT)
            raise CRuntimeError(f'printf 서식 %{conv}는 지원하지 않아요.', line, H_FMT)
        out.append((flags, width, prec, length, conv))
        i = m.end()
    if len(_FMT_CACHE) < 2000:
        _FMT_CACHE[fmt] = out
    return out


def _sx(v, bits):
    m = (1 << bits) - 1
    v &= m
    return v - (1 << bits) if v >> (bits - 1) else v


def _ferr(conv, cls, line):
    what = {'f': '실수(double)', 'p': '포인터(주소)', 'i': '정수', 'u': '정수'}[cls]
    need = {'d': '정수', 'i': '정수', 'u': '정수', 'o': '정수', 'x': '정수', 'X': '정수', 'c': '문자(정수)', 's': '문자열(char*)', 'p': '포인터'}.get(conv, '실수(double)')
    tip = ''
    if conv in 'diuoxX' and cls == 'f':
        tip = ' %f를 쓰거나 (int)로 바꾸세요.'
    elif conv in 'fFeEgG' and cls in 'iu':
        tip = ' %d를 쓰거나 (double)로 바꾸세요.'
    raise CRuntimeError(f'printf의 %{conv}에는 {need}를 넣어야 하는데 {what} 값을 넣었어요.{tip}', line, H_FMT)


def _fmt1(rt, flags, width, prec, length, conv, cls, v, line):
    w = width or b''
    if conv in 'di':
        if cls not in 'iu':
            _ferr(conv, cls, line)
        v = _sx(v, _LBITS.get(length, 32))
        fl = flags
        if prec is not None:
            fl = fl.replace(b'0', b'')
            if v == 0 and prec in (b'', b'0'):
                return (b'%' + fl.replace(b'+', b'').replace(b' ', b'') + w + b's') % ((b'+' if b'+' in flags else (b' ' if b' ' in flags else b'')),)
            return (b'%' + fl + w + b'.' + prec + b'd') % v
        return (b'%' + fl + w + b'd') % v
    if conv in 'uoxX':
        if cls not in 'iu':
            _ferr(conv, cls, line)
        v &= (1 << _LBITS.get(length, 32)) - 1
        fl = flags.replace(b'+', b'').replace(b' ', b'')
        ps = b''
        if prec is not None:
            fl = fl.replace(b'0', b'')
            if v == 0 and prec in (b'', b'0'):
                return (b'%' + fl.replace(b'#', b'') + w + b's') % ((b'0' if (conv == 'o' and b'#' in flags) else b''),)
            ps = b'.' + prec
        if conv == 'o' and b'#' in fl:
            digits = (b'%' + ps + b'o') % v
            if not digits.startswith(b'0'):
                digits = b'0' + digits
            fl2 = fl.replace(b'#', b'')
            if b'-' in fl2:
                return (b'%-' + w + b's') % digits
            if b'0' in fl2 and w:
                return digits.rjust(int(w), b'0')
            return (b'%' + w + b's') % digits
        if conv in 'xX' and v == 0:
            fl = fl.replace(b'#', b'')
        return (b'%' + fl + w + ps + (b'd' if conv == 'u' else conv.encode())) % v
    if conv == 'c':
        if cls not in 'iu':
            _ferr(conv, cls, line)
        return (b'%' + flags.replace(b'0', b'').replace(b'#', b'') + w + b'c') % (v & 0xFF)
    if conv == 's':
        if cls != 'p':
            _ferr(conv, cls, line)
        if v == 0:
            s = b'(null)' if (prec is None or int(prec or b'0') >= 6) else b''
        else:
            s = rt.cstr(v, line, None if prec is None else int(prec or b'0'))
        return (b'%' + flags.replace(b'0', b'').replace(b'#', b'') + w + b's') % s
    if conv in 'fFeEgG':
        if cls != 'f':
            _ferr(conv, cls, line)
        if v != v or v == math.inf or v == -math.inf:
            s = b'nan' if v != v else b'inf'
            if conv in 'FEG':
                s = s.upper()
            if math.copysign(1.0, v) < 0:
                s = b'-' + s
            elif b'+' in flags:
                s = b'+' + s
            elif b' ' in flags:
                s = b' ' + s
            return (b'%' + (b'-' if b'-' in flags else b'') + w + b's') % s
        return (b'%' + flags + w + (b'' if prec is None else b'.' + prec) + conv.encode()) % v
    if conv == 'p':
        s = b'(nil)' if v == 0 else b'0x%x' % (v & 0xFFFFFFFFFFFFFFFF)
        return (b'%' + (b'-' if b'-' in flags else b'') + w + b's') % s
    raise CRuntimeError('printf의 %n은 지원하지 않아요.', line, H_FMT)


def cfmt(rt, parsed, vals, line):
    out = []
    n = len(vals)
    ai = 0
    for it in parsed:
        if it.__class__ is bytes:
            out.append(it)
            continue
        flags, width, prec, length, conv = it
        if conv == '%':
            out.append(b'%')
            continue
        if width == b'*':
            if ai >= n or vals[ai][0] not in 'iu':
                raise CRuntimeError('printf 서식의 * 자리에 넣을 정수가 없어요.', line, H_FMT)
            wv = _sx(vals[ai][1], 32)
            ai += 1
            if wv < 0:
                flags += b'-'
                wv = -wv
            width = str(wv).encode()
        if prec == b'*':
            if ai >= n or vals[ai][0] not in 'iu':
                raise CRuntimeError('printf 서식의 .* 자리에 넣을 정수가 없어요.', line, H_FMT)
            pv = _sx(vals[ai][1], 32)
            ai += 1
            prec = None if pv < 0 else str(pv).encode()
        if ai >= n:
            raise CRuntimeError(f'printf 서식 %{conv}에 넣을 값이 없어요(값의 개수가 서식보다 적어요).', line, H_FMT)
        cls, v = vals[ai]
        ai += 1
        out.append(_fmt1(rt, flags, width, prec, length, conv, cls, v, line))
    return b''.join(out)


# ---------------------------------------------------------------- 전처리
ALLOWED_HEADERS = ('stdio.h', 'stdlib.h', 'string.h', 'stdbool.h', 'math.h', 'ctype.h', 'limits.h', 'stddef.h', 'stdint.h')
_PRELUDE = ('typedef unsigned long size_t; typedef long ssize_t; typedef long ptrdiff_t; typedef _Bool bool; '
            'typedef signed char int8_t; typedef short int16_t; typedef int int32_t; typedef long int64_t; '
            'typedef unsigned char uint8_t; typedef unsigned short uint16_t; typedef unsigned int uint32_t; '
            'typedef unsigned long uint64_t; typedef long intptr_t; typedef unsigned long uintptr_t; '
            'typedef long intmax_t; typedef unsigned long uintmax_t;\n#line 1\n')
PREDEF = {
    'NULL': '((void*)0)', 'true': '1', 'false': '0', '__bool_true_false_are_defined': '1',
    'INT_MAX': '2147483647', 'INT_MIN': '(-2147483647-1)', 'UINT_MAX': '4294967295U',
    'LONG_MAX': '9223372036854775807L', 'LONG_MIN': '(-9223372036854775807L-1)', 'ULONG_MAX': '18446744073709551615UL',
    'LLONG_MAX': '9223372036854775807LL', 'LLONG_MIN': '(-9223372036854775807LL-1)', 'ULLONG_MAX': '18446744073709551615ULL',
    'SHRT_MAX': '32767', 'SHRT_MIN': '(-32768)', 'USHRT_MAX': '65535',
    'CHAR_MAX': '127', 'CHAR_MIN': '(-128)', 'SCHAR_MAX': '127', 'SCHAR_MIN': '(-128)', 'UCHAR_MAX': '255', 'CHAR_BIT': '8',
    'INT8_MAX': '127', 'INT8_MIN': '(-128)', 'UINT8_MAX': '255', 'INT16_MAX': '32767', 'INT16_MIN': '(-32768)', 'UINT16_MAX': '65535',
    'INT32_MAX': '2147483647', 'INT32_MIN': '(-2147483647-1)', 'UINT32_MAX': '4294967295U',
    'INT64_MAX': '9223372036854775807L', 'INT64_MIN': '(-9223372036854775807L-1)', 'UINT64_MAX': '18446744073709551615UL',
    'SIZE_MAX': '18446744073709551615UL', 'RAND_MAX': '2147483647', 'EXIT_SUCCESS': '0', 'EXIT_FAILURE': '1', 'EOF': '(-1)',
    'M_PI': '3.14159265358979323846', 'M_E': '2.7182818284590452354', 'M_SQRT2': '1.41421356237309504880',
    'INFINITY': '(1e999f)', 'HUGE_VAL': '(1e999)',
}
_PP_TOK = re.compile(r'"(?:\\.|[^"\\\n])*"?|\'(?:\\.|[^\'\\\n])*\'?|\.?\d(?:[eEpP][+-]|[\w.])*|[A-Za-z_]\w*|\s+|.', re.S)


def _strip_comments(src):
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == '/' and i + 1 < n:
            d = src[i + 1]
            if d == '/':
                j = src.find('\n', i)
                if j < 0:
                    break
                i = j
                continue
            if d == '*':
                j = src.find('*/', i + 2)
                if j < 0:
                    raise CCompileError('주석(/* … */)이 닫히지 않았어요.', src.count('\n', 0, i) + 1, H_SYNTAX, 'SyntaxError')
                out.append(' ' + '\n' * src.count('\n', i, j))
                i = j + 2
                continue
        if c == '"' or c == "'":
            j = i + 1
            while j < n and src[j] != c and src[j] != '\n':
                if src[j] == '\\':
                    j += 1
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def _expand(line, macros, active=()):
    out = []
    for m in _PP_TOK.finditer(line):
        tok = m.group(0)
        body = macros.get(tok)
        if body is not None and tok not in active:
            out.append(' ' + _expand(body, macros, active + (tok,)) + ' ')
        else:
            out.append(tok)
    return ''.join(out)


def preprocess(code):
    """주석 제거, #include 확인, 객체형 #define 펼치기. 줄 번호는 그대로 둔다."""
    code = code.replace('\r\n', '\n').replace('\r', '\n')
    if '\\\n' in code:
        lines = code.split('\n')
        out = []
        i = 0
        while i < len(lines):
            cur = lines[i]
            extra = 0
            while cur.endswith('\\') and i + 1 < len(lines):
                i += 1
                extra += 1
                cur = cur[:-1] + lines[i]
            out.append(cur)
            out.extend([''] * extra)
            i += 1
        code = '\n'.join(out)
    text = _strip_comments(code)
    macros = dict(PREDEF)
    lines = text.split('\n')
    res = []
    stack = []  # (부모 활성, 이 단계에서 이미 참이었던 갈래가 있는지, 지금 활성)
    active = True
    for no, line in enumerate(lines, 1):
        s = line.lstrip()
        if s.startswith('#'):
            m = re.match(r'#\s*([A-Za-z_]*)(.*)$', s)
            d = m.group(1)
            rest = m.group(2).strip()
            res.append('')
            if d in ('ifdef', 'ifndef', 'if'):
                if d == 'if':
                    cond = _pp_if(rest, macros, no)
                else:
                    cond = (rest.split()[0] in macros) if rest.split() else False
                    if d == 'ifndef':
                        cond = not cond
                stack.append((active, cond, active and cond))
                active = active and cond
                continue
            if d in ('elif', 'else'):
                if not stack:
                    raise CCompileError(f'#{d} 앞에 #if가 없어요.', no, '', 'SyntaxError')
                par, taken, _ = stack[-1]
                cond = (not taken) and (True if d == 'else' else _pp_if(rest, macros, no))
                stack[-1] = (par, taken or cond, par and cond)
                active = par and cond
                continue
            if d == 'endif':
                if not stack:
                    raise CCompileError('#endif 앞에 #if가 없어요.', no, '', 'SyntaxError')
                active = stack.pop()[0]
                continue
            if not active:
                continue
            if d == 'include':
                mm = re.match(r'[<"]\s*([^>"]+?)\s*[>"]', rest)
                if not mm:
                    raise CCompileError('#include 다음에는 <헤더이름.h>를 써요.', no, '', 'SyntaxError')
                h = mm.group(1)
                if h not in ALLOWED_HEADERS:
                    raise CCompileError(f'지원하지 않는 헤더예요: <{h}> (쓸 수 있는 헤더: ' + ', '.join(ALLOWED_HEADERS) + ')', no, '', 'CompileError')
                continue
            if d == 'define':
                mm = re.match(r'([A-Za-z_]\w*)(\()?(.*)$', rest)
                if not mm:
                    raise CCompileError('#define 다음에 이름이 필요해요.', no, '', 'SyntaxError')
                if mm.group(2):
                    raise CCompileError(f'함수형 매크로(#define {mm.group(1)}(…))는 지원하지 않아요. 함수를 만들어 쓰세요.', no, '', 'CompileError')
                macros[mm.group(1)] = mm.group(3).strip()
                continue
            if d == 'undef':
                if rest.split():
                    macros.pop(rest.split()[0], None)
                continue
            if d in ('pragma', ''):
                continue
            raise CCompileError(f'지원하지 않는 전처리 지시문이에요: #{d}', no, '', 'CompileError')
        if not active:
            res.append('')
            continue
        res.append(_expand(line, macros) if line.strip() else line)
    if stack:
        raise CCompileError('#if/#ifdef를 #endif로 닫지 않았어요.', len(lines), '', 'SyntaxError')
    return '\n'.join(res)


def _pp_if(rest, macros, no):
    s = re.sub(r'defined\s*\(\s*([A-Za-z_]\w*)\s*\)|defined\s+([A-Za-z_]\w*)',
               lambda m: '1' if (m.group(1) or m.group(2)) in macros else '0', rest)
    s = _expand(s, macros).strip()
    s = re.sub(r'\b([0-9]+)[uUlL]*\b', r'\1', s)
    if re.fullmatch(r'[0-9\s()!+\-*/%<>=&|]*', s) and s:
        try:
            return bool(eval(s.replace('&&', ' and ').replace('||', ' or ').replace('!', ' not ').replace(' not =', '!='), {'__builtins__': {}}, {}))
        except Exception:  # noqa: BLE001
            pass
    raise CCompileError(f'#if 조건을 이해하지 못했어요: {rest}', no, '', 'CompileError')


def _syntax_error(msg, text):
    m = re.match(r'<c>:(\d+)(?::\d+)?:\s*(.*)$', msg, re.S)
    line = None
    body = msg
    if m:
        line = int(m.group(1))
        body = m.group(2)
    elif msg.startswith('<c>:'):
        body = msg[4:].strip()
    if 'At end of input' in body:
        nlines = text.count('\n')
        return CCompileError('문법 오류: 코드가 중간에 끝났어요. 닫는 중괄호 }나 세미콜론(;)이 빠졌는지 확인해 보세요 — 원문: ' + body, max(1, nlines - 1), H_SYNTAX, 'SyntaxError')
    if body.startswith('Illegal character'):
        return CCompileError(f'문법 오류({line}번째 줄): C 코드에 쓸 수 없는 문자가 있어요 — 원문: {body}', line, '전각 문자(；, （ 등)나 특수 기호가 섞이지 않았는지 확인해 보세요.', 'SyntaxError')
    where = f'({line}번째 줄)' if line else ''
    return CCompileError(f'문법 오류{where}: 세미콜론(;)이나 괄호를 확인해 보세요 — 원문: {body}', line, H_SYNTAX, 'SyntaxError')


def parse(code):
    text = preprocess(code)
    full = _PRELUDE + text
    try:
        return c_parser.CParser().parse(full, '<c>')
    except c_parser.ParseError as e:
        raise _syntax_error(str(e), text) from None
    except RecursionError:
        raise CCompileError('코드가 너무 깊게 중첩되어 있어요.', None, '', 'SyntaxError') from None
    except CError:
        raise
    except Exception as e:  # noqa: BLE001
        raise CCompileError(f'문법 오류: {e}', None, H_SYNTAX, 'SyntaxError') from None


# ---------------------------------------------------------------- 상수
_INT_RE = re.compile(r'(0[xX][0-9a-fA-F]+|0[bB][01]+|0[0-7]*|[1-9][0-9]*)([uUlL]*)$')


def parse_int(s, line):
    s = s.replace("'", '')
    m = _INT_RE.match(s)
    if not m:
        raise CCompileError(f'숫자 형식이 잘못됐어요: {s}', line)
    d, suf = m.groups()
    if d[:2] in ('0x', '0X'):
        v, dec = int(d[2:], 16), False
    elif d[:2] in ('0b', '0B'):
        v, dec = int(d[2:], 2), False
    elif len(d) > 1 and d[0] == '0':
        v, dec = int(d, 8), False
    else:
        v, dec = int(d), True
    sl = suf.lower()
    u = 'u' in sl
    nl = sl.count('l')
    if nl == 0:
        cands = [UINT, ULONG] if u else ([INT, LONG] if dec else [INT, UINT, LONG, ULONG])
    elif nl == 1:
        cands = [ULONG] if u else ([LONG] if dec else [LONG, ULONG])
    else:
        cands = [ULLONG] if u else ([LLONG] if dec else [LLONG, ULLONG])
    for t in cands:
        if v <= t.hi:
            return t, v
    if v <= ULLONG.hi:
        return ULLONG, v
    raise CCompileError(f'정수 상수가 너무 커요: {s}', line)


_ESC = {'n': 10, 't': 9, 'r': 13, '\\': 92, "'": 39, '"': 34, '?': 63, 'a': 7, 'b': 8, 'f': 12, 'v': 11, 'e': 27}
_HEX = set('0123456789abcdefABCDEF')


def unescape(s, line):
    if '\\' not in s:
        return s.encode('utf-8')
    out = bytearray()
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c != '\\':
            out += c.encode('utf-8')
            i += 1
            continue
        i += 1
        if i >= n:
            break
        c = s[i]
        if c in _ESC:
            out.append(_ESC[c])
            i += 1
        elif c == 'x':
            j = i + 1
            while j < n and s[j] in _HEX:
                j += 1
            if j == i + 1:
                raise CCompileError('\\x 다음에는 16진수 숫자가 와야 해요.', line)
            out.append(int(s[i + 1:j], 16) & 0xFF)
            i = j
        elif '0' <= c <= '7':
            j = i
            while j < n and j < i + 3 and '0' <= s[j] <= '7':
                j += 1
            out.append(int(s[i:j], 8) & 0xFF)
            i = j
        else:
            out += c.encode('utf-8')
            i += 1
    return bytes(out)


def parse_char(s, line):
    if s[0] != "'":
        raise CCompileError(f'넓은 문자 상수({s[:2]}…)는 지원하지 않아요.', line)
    bs = unescape(s[1:-1], line)
    if not bs:
        raise CCompileError("빈 문자 상수 ''는 쓸 수 없어요.", line)
    if len(bs) == 1:
        v = bs[0]
        return INT, (v - 256 if v >= 128 else v)
    v = 0
    for x in bs:
        v = ((v << 8) | x) & 0xFFFFFFFF
    return INT, _sx(v, 32)


def parse_float(s):
    t = DOUBLE
    if s[-1] in 'fF':
        t, s = FLOAT, s[:-1]
    elif s[-1] in 'lL':
        t, s = LDOUBLE, s[:-1]
    s = s.replace("'", '')
    v = float.fromhex(s) if s[:2] in ('0x', '0X') else float(s)
    if t is FLOAT:
        v = f32(v)
    return t, v


# ---------------------------------------------------------------- 클로저 틀(한 번 컴파일해 재사용)
_TPL = {}


def _tpl(key, src):
    f = _TPL.get(key)
    if f is None:
        ns = {'F32': f32}
        exec(compile(src, '<cinterp>', 'exec'), ns)
        f = _TPL[key] = ns['mk']
    return f


def _oc(k, n):
    if k == 'c':
        return n
    if k == 'r':
        return 'fr[' + n + ']'
    return n + '(fr)'


def _acode(kb, ki, one):
    a = _oc(kb, 'A')
    if ki is None:
        return a
    i = _oc(ki, 'I')
    return f'{a} + {i}' if one else f'{a} + {i} * ESZ'


def tpl_bin(op, ka, kb, mode):
    a, b = _oc(ka, 'A'), _oc(kb, 'B')
    if mode == 'w':
        body = f'        r = {a} {op} {b}\n        if r > HI or r < LO:\n            r = W(r)\n        return r\n'
    elif mode == 'f32':
        body = f'        return F32({a} {op} {b})\n'
    elif mode == 'shl':
        body = f'        r = {a} << ({b} & M)\n        if r > HI or r < LO:\n            r = W(r)\n        return r\n'
    elif mode == 'shr':
        body = f'        return {a} >> ({b} & M)\n'
    else:
        body = f'        return {a} {op} {b}\n'
    return _tpl(('bin', op, ka, kb, mode), 'def mk(A, B, LO, HI, W, M):\n    def f(fr):\n' + body + '    return f\n')


def tpl_cmp(op, ka, kb, cond):
    a, b = _oc(ka, 'A'), _oc(kb, 'B')
    body = f'        return {a} {op} {b}\n' if cond else f'        return 1 if {a} {op} {b} else 0\n'
    return _tpl(('cmp', op, ka, kb, cond), 'def mk(A, B):\n    def f(fr):\n' + body + '    return f\n')


def tpl_asg(kv, want):
    v = _oc(kv, 'V')
    body = f'        v = {v}\n        fr[D] = v\n        return v\n' if want else f'        fr[D] = {v}\n'
    return _tpl(('asg', kv, want), 'def mk(D, V):\n    def f(fr):\n' + body + '    return f\n')


def tpl_casg(op, kb, mode, want):
    b = _oc(kb, 'B')
    if mode == 'w':
        body = f'        r = fr[D] {op} {b}\n        if r > HI or r < LO:\n            r = W(r)\n        fr[D] = r\n'
    elif mode == 'f32':
        body = f'        r = F32(fr[D] {op} {b})\n        fr[D] = r\n'
    else:
        body = f'        r = fr[D] {op} {b}\n        fr[D] = r\n'
    if want:
        body += '        return r\n'
    return _tpl(('casg', op, kb, mode, want), 'def mk(D, B, LO, HI, W):\n    def f(fr):\n' + body + '    return f\n')


def tpl_inc(sign, mode, post, want):
    if mode == 'w':
        chk = '        if v > HI:\n            v = W(v)\n' if sign == '+' else '        if v < LO:\n            v = W(v)\n'
        body = f'        o = fr[D]\n        v = o {sign} 1\n' + chk + '        fr[D] = v\n'
    elif mode == 'p':
        body = f'        o = fr[D]\n        v = o {sign} DL\n        fr[D] = v\n'
    else:
        body = f'        o = fr[D]\n        v = W(o {sign} DL)\n        fr[D] = v\n'
    if want:
        body += '        return o\n' if post else '        return v\n'
    return _tpl(('inc', sign, mode, post, want), 'def mk(D, DL, LO, HI, W):\n    def f(fr):\n' + body + '    return f\n')


def tpl_addr(kb, ki, one):
    return _tpl(('addr', kb, ki, one), f'def mk(A, I, ESZ):\n    def f(fr):\n        return {_acode(kb, ki, one)}\n    return f\n')


def tpl_load(kb, ki, one):
    src = f'''def mk(A, I, ESZ, N, UP, BT, RT, LINE):
    def f(fr):
        a = {_acode(kb, ki, one)}
        try:
            b = BT[a >> 32]
        except KeyError:
            RT.bad(a, LINE)
        o = (a & 4294967295) - 2147483648
        if o < 0 or o + N > b.size:
            RT.oob(b, o, N, LINE)
        if not b.init[o]:
            RT.uninit(b, o, N, LINE)
        return UP(b.data, o)[0]
    return f
'''
    return _tpl(('load', kb, ki, one), src)


def tpl_store(kb, ki, one, kv, want, n1):
    initl = '        b.init[o] = 1\n' if n1 else '        b.init[o:o + N] = ONES\n'
    src = f'''def mk(A, I, ESZ, V, N, PK, BT, RT, LINE, ONES):
    def f(fr):
        a = {_acode(kb, ki, one)}
        v = {_oc(kv, 'V')}
        try:
            b = BT[a >> 32]
        except KeyError:
            RT.bad(a, LINE, True)
        o = (a & 4294967295) - 2147483648
        if o < 0 or o + N > b.size or b.ro:
            RT.oob(b, o, N, LINE, True)
        PK(b.data, o, v)
{initl}{'        return v' if want else ''}
    return f
'''
    return _tpl(('store', kb, ki, one, kv, want, n1), src)


def _st(f, want):
    """want=False로 만든 틀 클로저는 None을 돌려주므로 문장으로 바로 쓸 수 있다고 표시한다."""
    if not want:
        f._stmt = True
    return f


def _const_fn(v):
    return lambda fr: v


def _slot_fn(k):
    return lambda fr: fr[k]


class _Sig:
    __slots__ = ('name',)

    def __init__(self, n):
        self.name = n


BRK = _Sig('break')
CONT = _Sig('continue')
RET = _Sig('return')


def mk_block(items):
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    fs = tuple(items)

    def blk(fr):
        try:
            for s in fs:
                r = s(fr)
                if r is not None:
                    return r
        except CError as e:
            if e.line is None:
                e.line = getattr(s, 'ln', None)
            raise
    return blk


# ---------------------------------------------------------------- 컴파일러 자료
class E:
    """컴파일된 식. k: 'v' 값, 'r' 레지스터 지역 변수(프레임 칸), 'm' 메모리(f가 주소), 'b' 라이브러리 함수 이름."""
    __slots__ = ('t', 'k', 'f', 'slot', 'init', 'cv', 'ro', 'name', 'ca', 'fn', 'parts', 'line', 'mslot', 'lit')

    def __init__(self, t, k, f=None, line=None):
        self.t = t
        self.k = k
        self.f = f
        self.line = line
        self.slot = None
        self.init = True
        self.cv = None
        self.ro = False
        self.name = None
        self.ca = None
        self.fn = None
        self.parts = None
        self.mslot = None
        self.lit = None


class Sym:
    __slots__ = ('kind', 't', 'slot', 'init', 'name', 'ro', 'ca', 'fn', 'val', 'has_init')

    def __init__(self, kind, t=None, slot=None, init=True, name=None, ro=False, ca=None, fn=None, val=None):
        self.kind = kind
        self.t = t
        self.slot = slot
        self.init = init
        self.name = name
        self.ro = ro
        self.ca = ca
        self.fn = fn
        self.val = val
        self.has_init = False


class Func:
    __slots__ = ('name', 't', 'pnames', 'body', 'nslots', 'mslots', 'mparams', 'defined', 'invoke', 'addr', 'line', 'used')

    def __init__(self, name, t, line):
        self.name = name
        self.t = t
        self.pnames = []
        self.body = None
        self.nslots = 0
        self.mslots = []
        self.mparams = []
        self.defined = False
        self.invoke = None
        self.addr = 0
        self.line = line
        self.used = None


class FnCtx:
    __slots__ = ('func', 'n', 'mslots', 'loops', 'switches', 'addr_taken', 'rv')

    def __init__(self, func):
        self.func = func
        self.n = 0
        self.mslots = []
        self.loops = 0
        self.switches = 0
        self.addr_taken = set()
        self.rv = 0

    def new_slot(self):
        k = self.n
        self.n += 1
        return k


CMP_OPS = ('<', '>', '<=', '>=', '==', '!=')

_CC = Ptr(CHAR, True)
_CP = Ptr(CHAR)
_VP = Ptr(VOID)
_CVP = Ptr(VOID, True)
_CMPF = Ptr(FuncT(INT, [_CVP, _CVP]))
_D1 = (DOUBLE, [DOUBLE], False)
_D2 = (DOUBLE, [DOUBLE, DOUBLE], False)
_I1 = (INT, [INT], False)
BUILTINS = {
    'printf': (INT, [_CC], True), 'sprintf': (INT, [_CP, _CC], True),
    'puts': (INT, [_CC], False), 'putchar': (INT, [INT], False),
    'strlen': (ULONG, [_CC], False), 'strcpy': (_CP, [_CP, _CC], False), 'strncpy': (_CP, [_CP, _CC, ULONG], False),
    'strcat': (_CP, [_CP, _CC], False), 'strncat': (_CP, [_CP, _CC, ULONG], False),
    'strcmp': (INT, [_CC, _CC], False), 'strncmp': (INT, [_CC, _CC, ULONG], False),
    'strchr': (_CP, [_CC, INT], False), 'strrchr': (_CP, [_CC, INT], False), 'strstr': (_CP, [_CC, _CC], False),
    'memset': (_VP, [_VP, INT, ULONG], False), 'memcpy': (_VP, [_VP, _CVP, ULONG], False), 'memmove': (_VP, [_VP, _CVP, ULONG], False),
    'malloc': (_VP, [ULONG], False), 'calloc': (_VP, [ULONG, ULONG], False), 'realloc': (_VP, [_VP, ULONG], False), 'free': (VOID, [_VP], False),
    'abs': _I1, 'labs': (LONG, [LONG], False), 'llabs': (LLONG, [LLONG], False),
    'atoi': (INT, [_CC], False), 'atol': (LONG, [_CC], False), 'atoll': (LLONG, [_CC], False),
    'qsort': (VOID, [_VP, ULONG, ULONG, _CMPF], False),
    'rand': (INT, [], False), 'srand': (VOID, [UINT], False), 'exit': (VOID, [INT], False),
    'sqrt': _D1, 'fabs': _D1, 'floor': _D1, 'ceil': _D1, 'round': _D1, 'trunc': _D1, 'log': _D1, 'log10': _D1, 'log2': _D1,
    'exp': _D1, 'sin': _D1, 'cos': _D1, 'tan': _D1, 'atan': _D1,
    'pow': _D2, 'fmin': _D2, 'fmax': _D2, 'fmod': _D2, 'atan2': _D2, 'hypot': _D2,
    'toupper': _I1, 'tolower': _I1, 'isdigit': _I1, 'isalpha': _I1, 'isalnum': _I1, 'isupper': _I1, 'islower': _I1,
    'isspace': _I1, 'ispunct': _I1, 'isxdigit': _I1, 'isprint': _I1,
}
_NO_INPUT = ('scanf', 'gets', 'fgets', 'getchar', 'getc', 'fgetc', 'scanf_s', 'fscanf', 'sscanf')

# glibc ctype 표의 비트 값(gcc에서 isdigit('5') == 2048 등)
_CT_UPPER, _CT_LOWER, _CT_ALPHA, _CT_DIGIT, _CT_XDIGIT, _CT_SPACE, _CT_PRINT, _CT_GRAPH = 256, 512, 1024, 2048, 4096, 8192, 16384, 32768
_CT_BLANK, _CT_CNTRL, _CT_PUNCT, _CT_ALNUM = 1, 2, 4, 8


def _ctmask(c):
    if not (0 <= c < 128):
        return 0
    ch = chr(c)
    m = 0
    if 'A' <= ch <= 'Z':
        m |= _CT_UPPER | _CT_ALPHA | _CT_ALNUM
    if 'a' <= ch <= 'z':
        m |= _CT_LOWER | _CT_ALPHA | _CT_ALNUM
    if '0' <= ch <= '9':
        m |= _CT_DIGIT | _CT_ALNUM
    if ch in '0123456789abcdefABCDEF':
        m |= _CT_XDIGIT
    if ch in ' \t\n\v\f\r':
        m |= _CT_SPACE
    if 0x20 <= c <= 0x7e:
        m |= _CT_PRINT
    if 0x21 <= c <= 0x7e:
        m |= _CT_GRAPH
        if not ('A' <= ch <= 'Z' or 'a' <= ch <= 'z' or '0' <= ch <= '9'):
            m |= _CT_PUNCT
    if ch in ' \t':
        m |= _CT_BLANK
    if c < 0x20 or c == 0x7f:
        m |= _CT_CNTRL
    return m


_CTAB = [_ctmask(c) for c in range(128)]


def _ctype_fn(bit):
    tab = _CTAB

    def f(c, line):
        return tab[c] & bit if 0 <= c < 128 else 0
    return f


_NNAN = -math.nan if math.copysign(1.0, -math.nan) < 0 else math.copysign(math.nan, -1.0)


def _m1(fn):
    def f(x, line):
        try:
            return fn(x)
        except OverflowError:
            return math.inf
        except ValueError:
            return _NNAN
    return f


def _m_sqrt(x, line):
    if x < 0:
        return _NNAN
    return math.sqrt(x)


def _m_log(fn):
    def f(x, line):
        if x != x:
            return x
        if x == 0:
            return -math.inf
        if x < 0:
            return _NNAN
        return fn(x)
    return f


def _m_round(x, line):
    if x != x or x in (math.inf, -math.inf):
        return x
    a = abs(x)
    fl = math.floor(a)
    r = fl + 1 if a - fl >= 0.5 else fl
    return math.copysign(float(r), x)


def _m_floor(fn):
    def f(x, line):
        if x != x or x in (math.inf, -math.inf):
            return x
        return math.copysign(float(fn(x)), x) if fn(x) == 0 else float(fn(x))
    return f


def _m_pow(x, y, line):
    try:
        return math.pow(x, y)
    except OverflowError:
        if x < 0 and y == int(y) and int(y) % 2 == 1:
            return -math.inf
        return math.inf
    except ValueError:
        if x == 0:
            if y == int(y) and int(y) % 2 == 1:
                return math.copysign(math.inf, x)
            return math.inf
        return _NNAN


def _m_fmin(x, y, line):
    if x != x:
        return y
    if y != y:
        return x
    return x if x < y or (x == y and math.copysign(1, x) < 0) else y


def _m_fmax(x, y, line):
    if x != x:
        return y
    if y != y:
        return x
    return x if x > y or (x == y and math.copysign(1, x) > 0) else y


def _m_fmod(x, y, line):
    try:
        return math.fmod(x, y)
    except ValueError:
        return _NNAN


def _fdiv0(a, b):
    if a != a or a == 0:
        return _NNAN
    return math.copysign(math.inf, math.copysign(1.0, a) * math.copysign(1.0, b))


def _fdiv(a, b):
    if b == 0:
        return _fdiv0(a, b)
    return a / b


def _strtol(bs):
    i = 0
    n = len(bs)
    while i < n and bs[i] in b' \t\n\v\f\r':
        i += 1
    neg = False
    if i < n and bs[i] in b'+-':
        neg = bs[i] == 45
        i += 1
    j = i
    while j < n and 48 <= bs[j] <= 57:
        j += 1
    v = int(bs[i:j]) if j > i else 0
    if neg:
        v = -v
    return max(-(1 << 63), min((1 << 63) - 1, v))


# ---------------------------------------------------------------- 컴파일러
def _addr_taken(node):
    names = set()
    stack = [node]
    while stack:
        n = stack.pop()
        if n is None:
            continue
        if n.__class__ is c_ast.UnaryOp and n.op == '&' and n.expr.__class__ is c_ast.ID:
            names.add(n.expr.name)
        for _, ch in n.children():
            stack.append(ch)
    return names


def dtype(e):
    t = e.t
    c = t.__class__
    if c is Arr:
        return Ptr(t.of, e.ro)
    if c is FuncT:
        return Ptr(t)
    return t


class Compiler:
    def __init__(self, rt):
        self.rt = rt
        self.scopes = [{}]
        self.funcs = {}
        self.gblocks = []
        self.ginit = []
        self.lits = {}
        self.fn = None
        self.vla_pending = None
        self.in_param = False

    # ---- 이름표
    def push(self):
        self.scopes.append({})

    def pop(self):
        self.scopes.pop()

    def lookup(self, name):
        for s in reversed(self.scopes):
            v = s.get(name)
            if v is not None:
                return v
        return None

    def lookup_tag(self, key):
        for s in reversed(self.scopes):
            v = s.get(key)
            if v is not None:
                return v
        return None

    # ---- 타입 풀기
    def ty(self, node, line=None):
        """선언자 노드 → (타입, 이 객체가 const인지)."""
        c = node.__class__
        if c is c_ast.TypeDecl:
            return self.base(node.type, _ln(node) or line), ('const' in (node.quals or []))
        if c is c_ast.Typename:
            return self.ty(node.type, line)
        if c is c_ast.PtrDecl:
            inner, ic = self.ty(node.type, line)
            return Ptr(inner, ic), ('const' in (node.quals or []))
        if c is c_ast.ArrayDecl:
            inner, ic = self.ty(node.type, line)
            ln = _ln(node) or line
            if inner is VOID or inner.__class__ is FuncT:
                raise CCompileError('void나 함수의 배열은 만들 수 없어요.', ln)
            if inner.__class__ is StructT and not inner.complete:
                raise CCompileError(f'정의하지 않은 구조체의 배열이에요: {tname(inner)}', ln)
            if inner.__class__ is Arr and inner.n is None and inner.vla is None:
                raise CCompileError('2차원 배열의 두 번째 크기는 생략할 수 없어요(예: int a[][4]).', ln)
            if node.dim is None:
                return Arr(inner, None), ic
            de = self.ex(node.dim)
            if not is_int(dtype(de)):
                raise CCompileError('배열 크기는 정수여야 해요.', ln)
            if de.cv is not None:
                if de.cv < 0:
                    raise CCompileError('배열 크기는 0보다 커야 해요.', ln)
                return Arr(inner, de.cv), ic
            if self.fn is None or self.vla_pending is None:
                if self.in_param:
                    raise CCompileError('매개변수 배열의 두 번째 크기는 상수여야 해요(예: int a[][4]).', ln)
                raise CCompileError('배열 크기는 상수여야 해요(함수 밖·구조체 안에서는 변수를 크기로 쓸 수 없어요).', ln)
            slot = self.fn.new_slot()
            self.vla_pending.append((slot, self.val(de), ln))
            return Arr(inner, None, slot), ic
        if c is c_ast.FuncDecl:
            ft, _ = self.functype(node)
            return ft, False
        if c in (c_ast.Struct, c_ast.Union, c_ast.Enum, c_ast.IdentifierType):
            return self.base(node, _ln(node) or line), False
        raise CCompileError(f'지원하지 않는 선언이에요: {c.__name__}', line)

    def base(self, node, line):
        c = node.__class__
        if c is c_ast.IdentifierType:
            return self.ident_type(node.names, line)
        if c is c_ast.Struct:
            return self.struct_type(node, False)
        if c is c_ast.Union:
            return self.struct_type(node, True)
        if c is c_ast.Enum:
            return self.enum_type(node)
        raise CCompileError(f'지원하지 않는 타입이에요: {c.__name__}', line)

    _KW = {'void', 'char', 'short', 'int', 'long', 'float', 'double', 'signed', 'unsigned', '_Bool', '__int128', '_Complex'}

    def ident_type(self, names, line):
        if len(names) == 1 and names[0] not in self._KW:
            s = self.lookup(names[0])
            if s is None or s.kind != 'typedef':
                raise CCompileError(f'알 수 없는 타입 이름이에요: {names[0]}', line)
            return s.t
        u = 'unsigned' in names
        sg = 'signed' in names
        nl = names.count('long')
        if '__int128' in names or '_Complex' in names:
            raise CCompileError('지원하지 않는 타입이에요: ' + ' '.join(names), line)
        if 'void' in names:
            return VOID
        if '_Bool' in names:
            return BOOL
        if 'char' in names:
            return UCHAR if u else (SCHAR if sg else CHAR)
        if 'short' in names:
            return USHORT if u else SHORT
        if 'double' in names:
            return LDOUBLE if nl else DOUBLE
        if 'float' in names:
            return FLOAT
        if nl >= 2:
            return ULLONG if u else LLONG
        if nl == 1:
            return ULONG if u else LONG
        if 'int' in names or u or sg:
            return UINT if u else INT
        raise CCompileError('알 수 없는 타입이에요: ' + ' '.join(names), line)

    def struct_type(self, node, union):
        tag = node.name
        key = ('union ' if union else 'struct ') + (tag or '')
        line = _ln(node)
        if node.decls is None:
            st = self.lookup_tag(key) if tag else None
            if st is None:
                st = StructT(tag, union)
                if tag:
                    self.scopes[-1][key] = st
            return st
        st = self.scopes[-1].get(key) if tag else None
        if st is not None and st.complete:
            raise CCompileError(f'같은 구조체를 두 번 정의했어요: {key}', line)
        if st is None:
            st = StructT(tag, union)
            if tag:
                self.scopes[-1][key] = st
        fields = []
        seen = set()
        saved, self.vla_pending = self.vla_pending, None
        try:
            for fd in node.decls:
                fl = _ln(fd) or line
                if getattr(fd, 'bitsize', None) is not None:
                    raise CCompileError('비트 필드는 지원하지 않아요.', fl)
                if fd.name is None:
                    raise CCompileError('이름 없는 구조체 멤버는 지원하지 않아요.', fl)
                ft, fc = self.ty(fd.type, fl)
                if ft is VOID or ft.__class__ is FuncT:
                    raise CCompileError(f'구조체 멤버 타입이 잘못됐어요: {fd.name}', fl)
                if ft.__class__ is StructT and not ft.complete:
                    raise CCompileError(f'정의하지 않은 구조체를 멤버로 쓸 수 없어요: {tname(ft)} (포인터는 괜찮아요)', fl)
                if ft.__class__ is Arr and ft.n is None:
                    raise CCompileError(f'구조체 멤버 배열에는 크기가 필요해요: {fd.name}', fl)
                if fd.name in seen:
                    raise CCompileError(f'구조체 멤버 이름이 겹쳐요: {fd.name}', fl)
                seen.add(fd.name)
                fields.append((fd.name, ft, fc))
        finally:
            self.vla_pending = saved
        off = 0
        align = 1
        size = 0
        for name, ft, fc in fields:
            a = ft.align
            align = max(align, a)
            if union:
                F = Field(name, ft, 0, fc)
                size = max(size, ft.size)
            else:
                off = (off + a - 1) // a * a
                F = Field(name, ft, off, fc)
                off += ft.size
                size = off
            st.fields.append(F)
            st.fmap[name] = F
        st.align = align
        st.size = (size + align - 1) // align * align
        st.complete = True
        return st

    def enum_type(self, node):
        if node.values is not None:
            v = 0
            for en in node.values.enumerators:
                if en.value is not None:
                    e = self.ex(en.value)
                    if e.cv is None or not is_int(e.t):
                        raise CCompileError(f'enum 값은 정수 상수여야 해요: {en.name}', _ln(en))
                    v = e.cv
                if en.name in self.scopes[-1]:
                    raise CCompileError(f'같은 이름이 이미 있어요: {en.name}', _ln(en))
                self.scopes[-1][en.name] = Sym('const', INT, val=_sx(v, 32), name=en.name)
                v += 1
        return INT

    def functype(self, fd):
        ret, _ = self.ty(fd.type)
        line = _ln(fd)
        if ret.__class__ is Arr:
            raise CCompileError('C 함수는 배열을 return 할 수 없어요(포인터로 돌려주세요).', line)
        if ret.__class__ is FuncT:
            raise CCompileError('함수를 return 하는 함수는 만들 수 없어요.', line)
        params, names = [], []
        variadic = False
        if fd.args is not None:
            ps = fd.args.params
            for p in ps:
                if p.__class__ is c_ast.EllipsisParam:
                    variadic = True
                    continue
                if p.__class__ is c_ast.ID:
                    raise CCompileError('매개변수 앞에 타입(int 등)이 빠졌어요(옛날 방식 함수 선언은 지원하지 않아요).', line)
                pt = self.param_type(p.type, _ln(p) or line)
                if pt is VOID and getattr(p, 'name', None) is None and len(ps) == 1:
                    break
                if pt is VOID:
                    raise CCompileError('매개변수 타입으로 void를 쓸 수 없어요.', _ln(p) or line)
                params.append(pt)
                names.append(getattr(p, 'name', None))
        return FuncT(ret, params, variadic), names

    def param_type(self, tnode, line):
        saved = self.vla_pending, self.in_param
        self.vla_pending, self.in_param = None, True
        try:
            if tnode.__class__ is c_ast.ArrayDecl:
                inner, ic = self.ty(tnode.type, line)
                if inner.__class__ is Arr and inner.n is None:
                    raise CCompileError('2차원 배열 매개변수의 두 번째 크기는 생략할 수 없어요(예: int a[][4]).', line)
                return Ptr(inner, ic)
            t, _ = self.ty(tnode, line)
            if t.__class__ is FuncT:
                return Ptr(t)
            return t
        finally:
            self.vla_pending, self.in_param = saved

    # ---- 전체
    def unit(self, ast):
        bodies = []
        for ext in ast.ext:
            c = ext.__class__
            if c is c_ast.FuncDef:
                f = self.declare_func(ext.decl, True)
                bodies.append((f, ext))
            elif c is c_ast.Decl:
                self.global_decl(ext)
            elif c is c_ast.Typedef:
                self.typedef(ext)
            elif c is c_ast.Pragma:
                pass
            elif c is c_ast.StaticAssert:
                raise CCompileError('_Static_assert는 지원하지 않아요.', _ln(ext))
            else:
                raise CCompileError(f'지원하지 않는 문법이에요: {c.__name__}', _ln(ext))
        for f, ext in bodies:
            self.compile_func(f, ext)
        for f in self.funcs.values():
            if f.used is not None and not f.defined and f.name not in BUILTINS:
                raise CCompileError(f'함수를 선언만 하고 본문을 만들지 않았어요: {f.name}', f.used)

    def typedef(self, n):
        t, _ = self.ty(n.type, _ln(n))
        if t.__class__ is StructT and t.tdname is None:
            t.tdname = n.name
        old = self.scopes[-1].get(n.name)
        if old is not None and old.kind != 'typedef':
            raise CCompileError(f'같은 이름이 이미 있어요: {n.name}', _ln(n))
        self.scopes[-1][n.name] = Sym('typedef', t, name=n.name)

    def declare_func(self, d, defining=False):
        line = _ln(d)
        t, names = self.functype(d.type)
        name = d.name
        f = self.funcs.get(name)
        if f is None:
            old = self.scopes[0].get(name)
            if old is not None:
                raise CCompileError(f'같은 이름이 이미 있어요: {name}', line)
            f = Func(name, t, line)
            f.pnames = names
            self.funcs[name] = f
            f.addr = self.rt.new_block(0, name, 'func', True)
            self.rt.B[f.addr >> SH].func = f
            self.scopes[0][name] = Sym('func', t, fn=f, name=name)
        else:
            if not same_type(f.t.ret, t.ret) or len(f.t.params) != len(t.params):
                raise CCompileError(f'함수 {name}의 선언과 정의가 서로 달라요(반환 타입이나 매개변수 수).', line)
        if self.fn is not None and name not in self.scopes[-1]:
            self.scopes[-1][name] = self.scopes[0][name]
        if defining:
            if f.defined:
                raise CCompileError(f'같은 함수를 두 번 정의했어요: {name}', line)
            f.defined = True
            f.t = t
            f.pnames = names
            f.line = line
            for i, pn in enumerate(names):
                if pn is None:
                    raise CCompileError(f'{name} 함수의 {i + 1}번째 매개변수에 이름이 없어요.', line)
        return f

    def global_decl(self, d):
        line = _ln(d)
        if d.name is None:
            self.ty(d.type, line)
            return
        t, c = self.ty(d.type, line)
        if t.__class__ is FuncT:
            self.declare_func(d)
            return
        st = d.storage or []
        old = self.scopes[0].get(d.name)
        if old is not None:
            if old.kind != 'gmem' or not same_type(old.t, t):
                raise CCompileError(f'같은 이름이 이미 있어요: {d.name}', line)
            if d.init is not None:
                if old.has_init:
                    raise CCompileError(f'전역 변수를 두 번 초기화했어요: {d.name}', line)
                self.ginit.append((old.ca, old.t, self.init_writes(old.t, d.init, line), line))
                old.has_init = True
            return
        if t is VOID:
            raise CCompileError('void 타입 변수는 만들 수 없어요.', line)
        if t.__class__ is StructT and not t.complete:
            raise CCompileError(f'정의하지 않은 구조체 타입이에요: {tname(t)}', line)
        if t.__class__ is Arr and t.n is None:
            if d.init is None:
                if 'extern' in st:
                    raise CCompileError('크기를 모르는 extern 배열은 지원하지 않아요.', line)
                raise CCompileError('배열 크기를 정하지 않았어요.', line)
            t = Arr(t.of, self.init_count(t, d.init, line))
        a = self.alloc_static(t, d.name)
        sym = Sym('gmem', t, ca=a, name=d.name, ro=c)
        self.scopes[0][d.name] = sym
        if d.init is not None:
            self.ginit.append((a, t, self.init_writes(t, d.init, line), line))
            sym.has_init = True

    def alloc_static(self, t, name):
        if t.size > STACK_CAP * 4:
            raise CCompileError(f'전역 배열이 너무 커요: {name}', None)
        dims, leaf = arr_dims(t)
        st = leaf if leaf.__class__ is StructT else None
        a = self.rt.new_block(t.size, name, 'global', True, dims or None, leaf.size if dims else 0, st=st)
        self.gblocks.append(a)
        return a

    # ---- 초기화 목록
    def init_count(self, t, init, line):
        if init.__class__ is c_ast.InitList:
            out = []
            return self.fill_braced(t, init.exprs, 0, out, line)
        if self.is_strlit(init) and is_charish(t.of):
            return len(self.lit_bytes(init.value, line)) + 1
        raise CCompileError('크기를 생략한 배열은 { } 나 문자열로 초기화해야 해요.', line)

    @staticmethod
    def is_strlit(n):
        return n.__class__ is c_ast.Constant and n.type == 'string'

    def init_writes(self, t, init, line):
        out = []
        if t.__class__ in (Arr, StructT):
            if init.__class__ is c_ast.InitList:
                self.fill_braced(t, init.exprs, 0, out, line)
            elif t.__class__ is Arr and self.is_strlit(init) and is_charish(t.of):
                self.str_init(t, init, 0, out, line)
            elif t.__class__ is StructT:
                e = self.ex(init)
                if e.t is not t:
                    raise CCompileError(f'구조체 초기값의 타입이 맞지 않아요: {tname(t)}', line, H_TYPE)
                out.append(('s', 0, t.size, self.val_any(e)))
            else:
                raise CCompileError('배열은 { } 로 초기화해요(예: int a[3] = {1, 2, 3};).', line)
            return out
        if init.__class__ is c_ast.InitList:
            if len(init.exprs) != 1:
                raise CCompileError('변수 하나에는 값 하나만 넣을 수 있어요.', line)
            init = init.exprs[0]
        e = self.ex(init)
        self.check_assign(t, e, line, '초기화')
        out.append(self.scalar_write(0, t, e))
        return out

    def scalar_write(self, off, t, e):
        k, p = self.opnd(e, t)
        if k == 'c':
            return ('v', off, t, _const_fn(p), p)
        return ('v', off, t, _slot_fn(p) if k == 'r' else p, None)

    def str_init(self, t, it, off, out, line):
        bs = self.lit_bytes(it.value, line) + b'\0'
        n = t.n
        if n is not None and len(bs) > n:
            bs = bs[:n]
        out.append(('b', off, bs))

    def fill_braced(self, t, items, off, out, line):
        i, cnt = self.fill_elems(t, items, 0, off, out, line, True)
        if i < len(items):
            raise CCompileError('초기화 값이 너무 많아요.', _ln(items[i]) or line)
        return cnt

    def fill_elems(self, t, items, i, off, out, line, braced):
        n_items = len(items)
        if t.__class__ is Arr:
            et = t.of
            esz = et.size
            n = t.n
            k = 0
            mx = 0
            while i < n_items and (n is None or k < n or (braced and items[i].__class__ is c_ast.NamedInitializer)):
                it = items[i]
                if it.__class__ is c_ast.NamedInitializer:
                    if not braced:
                        break
                    if len(it.name) != 1 or it.name[0].__class__ is not c_ast.ArrayDesignator and it.name[0].__class__ is c_ast.ID:
                        raise CCompileError('배열에는 [번호] = 값 형태로만 지정할 수 있어요.', _ln(it) or line)
                    dn = it.name[0]
                    de = self.ex(dn.expr if dn.__class__ is c_ast.ArrayDesignator else dn)
                    if de.cv is None:
                        raise CCompileError('[번호]는 정수 상수여야 해요.', _ln(it) or line)
                    k = de.cv
                    if k < 0 or (n is not None and k >= n):
                        raise CCompileError('[번호]가 배열 범위를 벗어났어요.', _ln(it) or line)
                    self.fill_one(et, [it.expr], 0, off + k * esz, out, line)
                    i += 1
                else:
                    i = self.fill_one(et, items, i, off + k * esz, out, line)
                k += 1
                mx = max(mx, k)
            return i, mx
        fields = t.fields[:1] if t.union else t.fields
        fi = 0
        while i < n_items and (fi < len(fields) or (braced and items[i].__class__ is c_ast.NamedInitializer)):
            it = items[i]
            if it.__class__ is c_ast.NamedInitializer:
                if not braced:
                    break
                if len(it.name) != 1 or it.name[0].__class__ is not c_ast.ID:
                    raise CCompileError('구조체에는 .멤버 = 값 형태로만 지정할 수 있어요.', _ln(it) or line)
                nm = it.name[0].name
                F = t.fmap.get(nm)
                if F is None:
                    raise CCompileError(f'{tname(t)}에 없는 멤버예요: {nm}', _ln(it) or line)
                fi = t.fields.index(F)
                self.fill_one(F.t, [it.expr], 0, off + F.off, out, line)
                i += 1
            else:
                F = fields[fi]
                i = self.fill_one(F.t, items, i, off + F.off, out, line)
            fi += 1
        return i, fi

    def fill_one(self, t, items, i, off, out, line):
        it = items[i]
        il = _ln(it) or line
        if t.__class__ in (Arr, StructT):
            if it.__class__ is c_ast.InitList:
                self.fill_braced(t, it.exprs, off, out, il)
                return i + 1
            if t.__class__ is Arr and is_charish(t.of) and self.is_strlit(it):
                self.str_init(t, it, off, out, il)
                return i + 1
            if t.__class__ is StructT and it.__class__ is not c_ast.NamedInitializer:
                e = self.ex(it)
                if e.t is t:
                    out.append(('s', off, t.size, self.val_any(e)))
                    return i + 1
            i2, _ = self.fill_elems(t, items, i, off, out, il, False)
            if i2 == i:
                raise CCompileError('초기화 값의 모양이 타입과 맞지 않아요.', il)
            return i2
        if it.__class__ is c_ast.InitList:
            if len(it.exprs) == 0:
                return i + 1
            if len(it.exprs) > 1:
                raise CCompileError('값 하나를 넣을 자리에 여러 값을 넣었어요.', il)
            it = it.exprs[0]
        if it.__class__ is c_ast.NamedInitializer:
            raise CCompileError('지정 초기화(.x = / [i] =)의 위치가 잘못됐어요.', il)
        e = self.ex(it)
        self.check_assign(t, e, il, '초기화')
        out.append(self.scalar_write(off, t, e))
        return i + 1

    # ---- 함수 본문
    def compile_func(self, f, fd):
        ctx = FnCtx(f)
        self.fn = ctx
        ctx.addr_taken = _addr_taken(fd.body)
        self.push()
        np_ = len(f.t.params)
        ctx.n = np_ + 1
        ctx.rv = np_
        for i, (pn, pt) in enumerate(zip(f.pnames, f.t.params)):
            if pn in self.scopes[-1]:
                raise CCompileError(f'매개변수 이름이 겹쳐요: {pn}', f.line)
            if pt.__class__ is StructT or pn in ctx.addr_taken:
                if pt.__class__ is StructT and not pt.complete:
                    raise CCompileError(f'정의하지 않은 구조체 타입이에요: {tname(pt)}', f.line)
                self.scopes[-1][pn] = Sym('mem', pt, slot=i, name=pn)
                f.mparams.append((i, pt, pn))
                ctx.mslots.append(i)
            else:
                self.scopes[-1][pn] = Sym('reg', pt, slot=i, init=True, name=pn)
        items = []
        for it in fd.body.block_items or []:
            s = self.stmt(it)
            if s is not None:
                s.ln = _ln(it)
                items.append(s)
        self.pop()
        body = mk_block(items)
        self.fn = None
        f.body = body
        f.nslots = ctx.n
        f.mslots = ctx.mslots
        f.invoke = self.make_invoke(f, ctx.rv, _ln(fd.body))

    def make_invoke(self, f, rv, endline):
        rt = self.rt
        B = rt.B
        body = f.body or (lambda fr: None)
        np_ = len(f.t.params)
        pad = [None] * (f.nslots - np_)
        mparams = tuple((i, t, n, t.size, dims_leaf(t)) for i, t, n in f.mparams)
        mslots = tuple(f.mslots)
        nonvoid = f.t.ret is not VOID
        is_main = f.name == 'main'
        name = f.name
        nb = rt.new_block

        def finish(fr):
            if mslots:
                for k in mslots:
                    a = fr[k]
                    if a is not None:
                        B.pop(a >> SH, None)
            v = fr[rv]
            if v is None and nonvoid:
                if is_main:
                    return 0
                raise CRuntimeError(f'{name} 함수가 값을 return 하지 않고 끝났어요.', endline, '함수가 끝나기 전에 모든 경우에 return 문이 있는지 확인해 보세요.')
            return v

        if not mparams and not mslots and nonvoid:
            def invoke(args):
                d = rt.depth + 1
                if d > MAX_DEPTH:
                    raise CRuntimeError(f'재귀가 너무 깊어요({MAX_DEPTH}단계를 넘었어요): {name}', None, H_REC, 'RecursionError')
                rt.depth = d
                left = rt.left - 1
                rt.left = left
                if left & 4095 == 0 or left < 0:
                    rt.tick()
                fr = args + pad
                try:
                    body(fr)
                except _CUT as e:
                    # 깊은 재귀에서 오류가 위로 올라갈 때 traceback이 길게 쌓이면 브라우저(WASM)
                    # 스택이 넘치므로 함수 단계마다 끊는다
                    raise e.with_traceback(None)
                rt.depth = d - 1
                v = fr[rv]
                if v is None:
                    if is_main:
                        return 0
                    raise CRuntimeError(f'{name} 함수가 값을 return 하지 않고 끝났어요.', endline, '함수가 끝나기 전에 모든 경우에 return 문이 있는지 확인해 보세요.')
                return v
            return invoke

        def invoke(args):
            d = rt.depth + 1
            if d > MAX_DEPTH:
                raise CRuntimeError(f'재귀가 너무 깊어요({MAX_DEPTH}단계를 넘었어요): {name}', None, H_REC, 'RecursionError')
            rt.depth = d
            left = rt.left - 1
            rt.left = left
            if left & 4095 == 0 or left < 0:
                rt.tick()
            fr = args + pad
            for i, t, pn, size, (dims, leaf) in mparams:
                v = fr[i]
                a = nb(size, pn, 'stack', True, dims or None, leaf.size if dims else 0, st=leaf if leaf.__class__ is StructT else None)
                b = B[a >> SH]
                if t.__class__ is StructT:
                    b.data[:] = v[0]
                    b.init[:] = v[1]
                else:
                    t.pk(b.data, 0, v)
                fr[i] = a
            try:
                body(fr)
            except _CUT as e:
                raise e.with_traceback(None)
            rt.depth = d - 1
            return finish(fr)
        return invoke

    # ---- 식: 도우미
    def rv(self, e):
        k = e.k
        t = e.t
        if k == 'v':
            if t.__class__ is FuncT:
                return Ptr(t), e.f
            return t, e.f
        if k == 'r':
            s = e.slot
            if e.init:
                return t, _slot_fn(s)
            name = e.name
            line = e.line

            def rd(fr):
                v = fr[s]
                if v is None:
                    raise CRuntimeError(f'초기화하지 않은 값을 읽었어요: {name}', line, H_UNINIT)
                return v
            return t, rd
        if k == 'm':
            c = t.__class__
            if c is Arr:
                return Ptr(t.of, e.ro), e.f
            if c is FuncT:
                return Ptr(t), e.f
            if c is StructT:
                return t, self.mk_snap(e)
            return t, self.mk_load(e)
        raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {e.name}', e.line)

    def opnd(self, e, to=None):
        t, f = self.rv(e)
        cf = conv_fn(t, to) if (to is not None and to is not t) else None
        if e.cv is not None and e.k == 'v':
            v = e.cv
            return 'c', (cf(v) if cf is not None else v)
        if cf is None:
            if e.k == 'r' and e.init:
                return 'r', e.slot
            return 'f', f
        g = f
        return 'f', (lambda fr: cf(g(fr)))

    def val(self, e, to=None):
        k, p = self.opnd(e, to)
        if k == 'c':
            return _const_fn(p)
        if k == 'r':
            return _slot_fn(p)
        return p

    def val_any(self, e):
        if e.t is VOID:
            return e.f
        return self.rv(e)[1]

    def parts_of(self, e):
        if e.parts is not None:
            return e.parts
        return ('f', e.f, None, None, 1)

    def mk_load(self, e):
        t = e.t
        line = e.line
        if e.ca is not None:
            b = self.rt.B.get(e.ca >> SH)
            o = (e.ca & MASK) - BIAS
            if b is not None and b.kind in ('global', 'literal') and 0 <= o and o + t.size <= b.size:
                data = b.data
                up = t.up
                return lambda fr: up(data, o)[0]
        kb, pb, ki, pi, esz = self.parts_of(e)
        one = esz == 1
        return tpl_load(kb, ki, one)(pb, pi, esz, t.size, t.up, self.rt.B, self.rt, line)

    def mk_store(self, e, kv, pv, want):
        t = e.t
        line = e.line
        if e.ca is not None and not e.ro:
            b = self.rt.B.get(e.ca >> SH)
            o = (e.ca & MASK) - BIAS
            if b is not None and b.kind == 'global' and 0 <= o and o + t.size <= b.size:
                data = b.data
                pk = t.pk
                vf = pv if kv == 'f' else (_const_fn(pv) if kv == 'c' else _slot_fn(pv))
                if want:
                    def st(fr):
                        v = vf(fr)
                        pk(data, o, v)
                        return v
                else:
                    def st(fr):
                        pk(data, o, vf(fr))
                return st
        kb, pb, ki, pi, esz = self.parts_of(e)
        n = t.size
        return tpl_store(kb, ki, esz == 1, kv, want, n == 1)(pb, pi, esz, pv, n, t.pk, self.rt.B, self.rt, line, _ones(n))

    def mk_reader(self, t, line):
        RT = self.rt

        def rd(a):
            return RT.rd(a, t, line)
        return rd

    def mk_writer(self, t, line):
        RT = self.rt

        def wr(a, v):
            RT.wr(a, t, v, line)
        return wr

    def mk_snap(self, e):
        n = e.t.size
        af = e.f
        RT = self.rt
        line = e.line

        def snap(fr):
            b, o = RT.chk(af(fr), n, line)
            return (bytes(b.data[o:o + n]), bytes(b.init[o:o + n]))
        return snap

    def dsize(self, t):
        """타입 크기(가변 길이 배열이면 프레임에서 계산하는 함수)."""
        if t.__class__ is Arr and is_vla(t):
            inner = self.dsize(t.of)
            if t.vla is not None:
                s = t.vla
                if callable(inner):
                    return lambda fr: fr[s] * inner(fr)
                return lambda fr: fr[s] * inner
            n = t.n or 0
            return lambda fr: n * inner(fr)
        return t.size

    def elem_size(self, pt, line):
        to = pt.to
        if to is VOID:
            return 1
        if to.__class__ is FuncT:
            raise CCompileError('함수 포인터에는 + - 계산을 할 수 없어요.', line)
        if to.__class__ is StructT and not to.complete:
            raise CCompileError(f'정의하지 않은 구조체 포인터는 계산할 수 없어요: {tname(to)}', line)
        s = self.dsize(to)
        if s == 0 and not callable(s) and to.__class__ is Arr:
            raise CCompileError('크기를 모르는 배열이에요.', line)
        return s

    def check_assign(self, dt, R, line, what='대입'):
        if R.k == 'b':
            raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {R.name}', line)
        st = dtype(R)
        if st is VOID:
            raise CCompileError('값이 없는(void) 결과는 쓸 수 없어요.', line, H_TYPE)
        dc = dt.__class__
        if dc is Prim:
            if st.__class__ is Prim:
                return
            if st.__class__ is Ptr and dt is BOOL:
                return
            raise CCompileError(f'{what} 타입이 맞지 않아요: {tname(dt)}에 {tname(st)} 값을 넣을 수 없어요.', line, H_TYPE)
        if dc is Ptr:
            if st.__class__ is Ptr:
                if ptr_compat(dt, st):
                    return
                raise CCompileError(f'{what} 타입이 맞지 않아요: {tname(dt)}에 {tname(st)} 값을 넣을 수 없어요.', line, H_TYPE)
            if is_int(st) and R.cv == 0 and R.k == 'v':
                return
            raise CCompileError(f'{what} 타입이 맞지 않아요: 포인터({tname(dt)})에 {tname(st)} 값을 넣을 수 없어요.', line, H_TYPE)
        if dc is StructT:
            if st is dt:
                return
            raise CCompileError(f'{what} 타입이 맞지 않아요: {tname(dt)}에 {tname(st)} 값을 넣을 수 없어요.', line, H_TYPE)
        if dc is Arr:
            raise CCompileError('배열 전체에는 = 로 값을 넣을 수 없어요. 한 칸씩 넣거나 strcpy·memcpy를 쓰세요.', line, H_TYPE)
        raise CCompileError(f'{what} 타입이 맞지 않아요: {tname(dt)}', line, H_TYPE)

    def need_lvalue(self, L, line):
        if L.k not in ('r', 'm'):
            raise CCompileError('값을 넣을 수 없는 곳에 대입했어요(= 왼쪽에는 변수나 배열 칸이 와야 해요).', line)
        if L.t.__class__ is Arr:
            raise CCompileError('배열 전체에는 = 로 값을 넣을 수 없어요. 한 칸씩 넣거나 strcpy·memcpy를 쓰세요.', line, H_TYPE)
        if L.t.__class__ is FuncT:
            raise CCompileError('함수에는 값을 넣을 수 없어요.', line)
        if L.ro:
            raise CCompileError('const로 정한 값은 바꿀 수 없어요' + (f': {L.name}' if L.name else '.'), line)

    # ---- 식
    def ex(self, n):
        m = getattr(self, 'x_' + n.__class__.__name__, None)
        if m is None:
            raise CCompileError(f'지원하지 않는 문법이에요: {n.__class__.__name__}', _ln(n))
        return m(n)

    def lit_bytes(self, v, line):
        if v.startswith('u8"'):
            v = v[2:]
        if not v.startswith('"'):
            raise CCompileError('넓은 문자열(L"…")은 지원하지 않아요.', line)
        return unescape(v[1:-1], line)

    def x_Constant(self, n):
        line = _ln(n)
        ty = n.type
        v = n.value
        if ty == 'string':
            bs = self.lit_bytes(v, line) + b'\0'
            a = self.lits.get(bs)
            if a is None:
                shown = bs[:-1].decode('utf-8', 'replace')
                shown = '"' + (shown if len(shown) <= 20 else shown[:20] + '…') + '"'
                a = self.rt.new_block(len(bs), '문자열 상수 ' + shown, 'literal', True, (len(bs),), 1, ro=True, data=bs)
                self.lits[bs] = a
            e = E(Arr(CHAR, len(bs)), 'm', _const_fn(a), line)
            e.ca = a
            e.lit = bs
            return e
        if ty == 'char':
            t, val = parse_char(v, line)
        elif 'float' in ty or 'double' in ty:
            t, val = parse_float(v)
        elif ty == 'bool':
            t, val = INT, (1 if v == 'true' else 0)
        else:
            t, val = parse_int(v, line)
        e = E(t, 'v', _const_fn(val), line)
        e.cv = val
        return e

    def x_ID(self, n):
        line = _ln(n)
        s = self.lookup(n.name)
        if s is None:
            if n.name in BUILTINS:
                e = E(VOID, 'b', None, line)
                e.name = n.name
                return e
            raise CCompileError(f'선언하지 않은 이름이에요: {n.name}', line, '변수·함수 이름의 철자와, 쓰기 전에 선언했는지 확인해 보세요.')
        k = s.kind
        if k == 'reg':
            e = E(s.t, 'r', None, line)
            e.slot = s.slot
            e.init = s.init
        elif k == 'mem':
            e = E(s.t, 'm', _slot_fn(s.slot), line)
            e.mslot = s.slot
            e.parts = ('r', s.slot, None, None, 1)
        elif k == 'gmem':
            e = E(s.t, 'm', _const_fn(s.ca), line)
            e.ca = s.ca
            e.parts = ('c', s.ca, None, None, 1)
        elif k == 'func':
            if s.fn.used is None:
                s.fn.used = line
            e = E(s.fn.t, 'v', _const_fn(s.fn.addr), line)
            e.fn = s.fn
        elif k == 'const':
            e = E(INT, 'v', _const_fn(s.val), line)
            e.cv = s.val
        else:
            raise CCompileError(f'타입 이름을 값처럼 썼어요: {n.name}', line)
        e.name = n.name
        e.ro = s.ro
        return e

    def x_ArrayRef(self, n):
        line = _ln(n)
        be = self.ex(n.name)
        ie = self.ex(n.subscript)
        bt, it = dtype(be), dtype(ie)
        if is_int(bt) and is_ptr(it):
            be, ie, bt, it = ie, be, it, bt
        if not is_ptr(bt):
            raise CCompileError('배열이나 포인터가 아닌 값에 [ ]를 썼어요' + (f': {be.name}' if be.name else '.'), line)
        if not is_int(it):
            raise CCompileError('배열의 인덱스(번호)는 정수여야 해요.', line)
        et = bt.to
        if et is VOID:
            raise CCompileError('void* 포인터에는 [ ]를 바로 쓸 수 없어요. (int*)처럼 타입을 바꾼 뒤 쓰세요.', line)
        esz = self.elem_size(bt, line)
        if be.k == 'm' and be.t.__class__ is Arr:
            if be.mslot is not None:
                kb, pb = 'r', be.mslot
            elif be.ca is not None:
                kb, pb = 'c', be.ca
            else:
                kb, pb = 'f', be.f
        else:
            kb, pb = self.opnd(be)
        ki, pi = self.opnd(ie)
        if callable(esz):
            bf = _const_fn(pb) if kb == 'c' else (_slot_fn(pb) if kb == 'r' else pb)
            xf = _const_fn(pi) if ki == 'c' else (_slot_fn(pi) if ki == 'r' else pi)
            ef = esz

            def af(fr):
                return bf(fr) + xf(fr) * ef(fr)
            e = E(et, 'm', af, line)
            e.parts = ('f', af, None, None, 1)
        else:
            if ki == 'c':
                pi = pi * esz
                one = True
            else:
                one = esz == 1
            e = E(et, 'm', tpl_addr(kb, ki, one)(pb, pi, esz), line)
            e.parts = (kb, pb, ki, pi, 1 if one else esz)
            if kb == 'c' and ki == 'c':
                e.ca = pb + pi
        e.ro = bt.cto
        e.name = be.name
        return e

    def x_StructRef(self, n):
        line = _ln(n)
        fld = n.field.name
        if n.type == '->':
            pe = self.ex(n.name)
            pt = dtype(pe)
            if pt.__class__ is StructT:
                raise CCompileError('구조체 변수에는 -> 대신 . 을 써요.', line)
            if not (is_ptr(pt) and pt.to.__class__ is StructT):
                raise CCompileError('구조체 포인터가 아닌 값에 ->를 썼어요.', line)
            st = pt.to
            if not st.complete:
                raise CCompileError(f'정의하지 않은 구조체예요: {tname(st)}', line)
            F = st.fmap.get(fld)
            if F is None:
                raise CCompileError(f'{tname(st)}에 없는 멤버예요: {fld}', line)
            kb, pb = self.opnd(pe)
            off = F.off
            e = E(F.t, 'm', tpl_addr(kb, 'c', True)(pb, off, 1), line)
            e.parts = (kb, pb, 'c', off, 1)
            e.ro = pt.cto or F.ro
            e.name = fld
            return e
        se = self.ex(n.name)
        st = se.t
        if is_ptr(dtype(se)) and dtype(se).to.__class__ is StructT:
            raise CCompileError('구조체 포인터에는 . 대신 -> 를 써요.', line)
        if st.__class__ is not StructT:
            raise CCompileError('구조체가 아닌 값에 . 을 썼어요.', line)
        if not st.complete:
            raise CCompileError(f'정의하지 않은 구조체예요: {tname(st)}', line)
        F = st.fmap.get(fld)
        if F is None:
            raise CCompileError(f'{tname(st)}에 없는 멤버예요: {fld}', line)
        off = F.off
        if se.k == 'm':
            kb, pb, ki, pi, esz = self.parts_of(se)
            if ki is None:
                e = E(F.t, 'm', tpl_addr(kb, 'c', True)(pb, off, 1), line)
                e.parts = (kb, pb, 'c', off, 1)
            elif ki == 'c' and esz == 1:
                e = E(F.t, 'm', tpl_addr(kb, 'c', True)(pb, pi + off, 1), line)
                e.parts = (kb, pb, 'c', pi + off, 1)
            else:
                sf = se.f
                af = (lambda fr: sf(fr) + off)
                e = E(F.t, 'm', af, line)
            if se.ca is not None:
                e.ca = se.ca + off
            e.ro = se.ro or F.ro
            e.name = fld
            return e
        snapf = self.val_any(se)
        ft = F.t
        sz = ft.size
        if ft.__class__ is StructT:
            def f(fr):
                d, i = snapf(fr)
                return (d[off:off + sz], i[off:off + sz])
        elif is_scalar(ft):
            up = ft.up

            def f(fr):
                d, i = snapf(fr)
                if not i[off]:
                    raise CRuntimeError(f'초기화하지 않은 값을 읽었어요: .{fld}', line, H_UNINIT)
                return up(d, off)[0]
        else:
            raise CCompileError('함수가 돌려준 구조체의 배열 멤버는 바로 쓸 수 없어요. 변수에 담은 뒤 쓰세요.', line)
        return E(ft, 'v', f, line)

    def x_UnaryOp(self, n):
        op = n.op
        line = _ln(n)
        if op in ('++', '--', 'p++', 'p--'):
            f, t = self.incdec(n, True)
            return E(t, 'v', f, line)
        if op == '!':
            f, cv = self.cond(n.expr)
            if cv is not None:
                r = E(INT, 'v', _const_fn(0 if cv else 1), line)
                r.cv = 0 if cv else 1
                return r
            return E(INT, 'v', lambda fr: 0 if f(fr) else 1, line)
        if op == 'sizeof':
            return self.sizeof(n.expr, line)
        if op == '&':
            e = self.ex(n.expr)
            if e.k == 'm':
                if e.t.__class__ is Arr and e.t.n is None and e.t.vla is None:
                    raise CCompileError('크기를 모르는 배열의 주소예요.', line)
                r = E(Ptr(e.t, e.ro), 'v', e.f, line)
                return r
            if e.k == 'v' and e.t.__class__ is FuncT:
                return E(Ptr(e.t), 'v', e.f, line)
            raise CCompileError('주소(&)를 구할 수 없는 값이에요.', line)
        if op == '*':
            e = self.ex(n.expr)
            t = dtype(e)
            if not is_ptr(t):
                raise CCompileError('포인터가 아닌 값에 *를 썼어요' + (f': {e.name}' if e.name else '.'), line)
            to = t.to
            if to.__class__ is FuncT:
                r = E(to, 'v', self.val(e), line)
                return r
            if to is VOID:
                raise CCompileError('void* 포인터는 바로 *로 읽을 수 없어요. (int*)처럼 타입을 바꾼 뒤 쓰세요.', line)
            if to.__class__ is StructT and not to.complete:
                raise CCompileError(f'정의하지 않은 구조체예요: {tname(to)}', line)
            kb, pb = self.opnd(e)
            r = E(to, 'm', self.val(e), line)
            r.parts = (kb, pb, None, None, 1)
            r.ro = t.cto
            r.name = e.name
            return r
        e = self.ex(n.expr)
        t = dtype(e)
        if op in ('-', '+'):
            if not is_arith(t):
                raise CCompileError(f'숫자가 아닌 값에 {op}를 붙였어요.', line)
        elif op == '~':
            if not is_int(t):
                raise CCompileError('~ 연산은 정수에만 쓸 수 있어요.', line)
        else:
            raise CCompileError(f'지원하지 않는 연산이에요: {op}', line)
        pt = promote(t)
        k, p = self.opnd(e, pt)
        g = p if k == 'f' else (_const_fn(p) if k == 'c' else _slot_fn(p))
        if op == '+':
            f = g
        elif op == '-':
            if pt.flt:
                def f(fr):
                    return -g(fr)
            else:
                lo, hi, w = pt.lo, pt.hi, wrapf(pt)

                def f(fr):
                    v = -g(fr)
                    if v > hi or v < lo:
                        v = w(v)
                    return v
        else:
            w = wrapf(pt)

            def f(fr):
                return w(~g(fr))
        r = E(pt, 'v', f, line)
        if k == 'c':
            r.cv = f(None)
            r.f = _const_fn(r.cv)
        return r

    def sizeof(self, x, line):
        if x.__class__ is c_ast.Typename:
            saved = self.vla_pending
            self.vla_pending = None
            try:
                t, _ = self.ty(x.type, line)
            finally:
                self.vla_pending = saved
        else:
            e = self.ex(x)  # 식은 계산하지 않고 타입만 본다
            if e.k == 'b':
                raise CCompileError('라이브러리 함수에는 sizeof를 쓸 수 없어요.', line)
            t = e.t
        if t.__class__ is FuncT:
            raise CCompileError('함수에는 sizeof를 쓸 수 없어요.', line)
        if t.__class__ is StructT and not t.complete:
            raise CCompileError(f'정의하지 않은 구조체에는 sizeof를 쓸 수 없어요: {tname(t)}', line)
        if t.__class__ is Arr and is_vla(t):
            s = self.dsize(t)
            return E(ULONG, 'v', s, line)
        if t.__class__ is Arr and t.n is None:
            raise CCompileError('크기를 모르는 배열에는 sizeof를 쓸 수 없어요.', line)
        r = E(ULONG, 'v', _const_fn(t.size), line)
        r.cv = t.size
        return r

    def x_Cast(self, n):
        line = _ln(n)
        saved = self.vla_pending
        self.vla_pending = None
        try:
            t, _ = self.ty(n.to_type, line)
        finally:
            self.vla_pending = saved
        e = self.ex(n.expr)
        if t is VOID:
            g = self.val_any(e)

            def f(fr):
                g(fr)
            return E(VOID, 'v', f, line)
        if e.k == 'b':
            raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {e.name}', line)
        st = dtype(e)
        if t.__class__ in (StructT, Arr, FuncT):
            raise CCompileError('구조체·배열·함수 타입으로는 형 변환(캐스트)할 수 없어요.', line)
        if st.__class__ is StructT or st is VOID:
            raise CCompileError('이 값은 형 변환(캐스트)할 수 없어요.', line)
        if (is_ptr(t) and is_flt(st)) or (is_flt(t) and is_ptr(st)):
            raise CCompileError('포인터와 실수 사이는 형 변환할 수 없어요.', line)
        cf = conv_fn(st, t)
        if e.cv is not None and e.k == 'v':
            v = cf(e.cv) if cf is not None else e.cv
            r = E(t, 'v', _const_fn(v), line)
            r.cv = v
            return r
        g = self.val(e)
        if cf is None:
            r = E(t, 'v', g, line)
        else:
            r = E(t, 'v', lambda fr: cf(g(fr)), line)
        return r

    def binop_fn(self, op, ct, line):
        if ct.flt:
            if op == '/':
                return (lambda a, b: f32(_fdiv(a, b))) if ct is FLOAT else _fdiv
            base = {'+': lambda a, b: a + b, '-': lambda a, b: a - b, '*': lambda a, b: a * b}.get(op)
            if base is None:
                raise CCompileError(f'실수에는 {op} 연산을 쓸 수 없어요.', line)
            if ct is FLOAT:
                return lambda a, b: f32(base(a, b))
            return base
        w = wrapf(ct)
        lo, hi = ct.lo, ct.hi
        m = ct.size * 8 - 1
        if op == '+':
            return lambda a, b: w(a + b)
        if op == '-':
            return lambda a, b: w(a - b)
        if op == '*':
            return lambda a, b: w(a * b)
        if op == '&':
            return lambda a, b: a & b
        if op == '|':
            return lambda a, b: a | b
        if op == '^':
            return lambda a, b: a ^ b
        if op == '<<':
            return lambda a, b: w(a << (b & m))
        if op == '>>':
            return lambda a, b: a >> (b & m)
        if op == '/':
            def dv(a, b):
                if b == 0:
                    raise CRuntimeError('0으로 나눴어요.', line, H_DIV0)
                q = a // b
                if q < 0 and q * b != a:
                    q += 1
                if q > hi or q < lo:
                    raise CRuntimeError('정수 나눗셈 결과가 표현할 수 있는 범위를 넘었어요.', line)
                return q
            return dv
        if op == '%':
            def md(a, b):
                if b == 0:
                    raise CRuntimeError('0으로 나눈 나머지(%)를 구했어요.', line, H_DIV0)
                r = a % b
                if r and (r < 0) != (a < 0):
                    r -= b
                return r
            return md
        raise CCompileError(f'지원하지 않는 연산이에요: {op}', line)

    def x_BinaryOp(self, n):
        op = n.op
        line = _ln(n)
        if op in ('&&', '||'):
            a, ca = self.cond(n.left)
            b, cb = self.cond(n.right)
            if ca is not None and cb is not None:
                v = 1 if ((ca and cb) if op == '&&' else (ca or cb)) else 0
                r = E(INT, 'v', _const_fn(v), line)
                r.cv = v
                return r
            if op == '&&':
                return E(INT, 'v', lambda fr: 1 if (a(fr) and b(fr)) else 0, line)
            return E(INT, 'v', lambda fr: 1 if (a(fr) or b(fr)) else 0, line)
        L = self.ex(n.left)
        R = self.ex(n.right)
        for x in (L, R):
            if x.k == 'b':
                raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {x.name}', line)
        lt, rt_ = dtype(L), dtype(R)
        if op in CMP_OPS:
            f, cv = self.cmp(op, L, R, line, False)
            r = E(INT, 'v', f, line)
            r.cv = cv
            return r
        if op in ('+', '-') and (is_ptr(lt) or is_ptr(rt_)):
            return self.ptr_arith(op, L, R, lt, rt_, line)
        if not (is_arith(lt) and is_arith(rt_)):
            raise CCompileError(f'숫자가 아닌 값으로 {op} 계산을 할 수 없어요: {tname(lt)} {op} {tname(rt_)}', line, H_TYPE)
        if op in ('%', '<<', '>>', '&', '|', '^') and not (is_int(lt) and is_int(rt_)):
            raise CCompileError(f'실수에는 {op} 연산을 쓸 수 없어요(정수에만 쓸 수 있어요).', line, H_TYPE)
        if op in ('<<', '>>'):
            ct = promote(lt)
            rct = promote(rt_)
        else:
            ct = rct = usual_arith(lt, rt_)
        ka, pa = self.opnd(L, ct)
        kb, pb = self.opnd(R, rct)
        w = wrapf(ct)
        m = ct.size * 8 - 1
        if op in ('+', '-', '*', '&', '|', '^'):
            if ct.flt:
                mode = 'f32' if ct is FLOAT else 'n'
            else:
                mode = 'w' if op in ('+', '-', '*') else 'n'
            f = tpl_bin(op, ka, kb, mode)(pa, pb, ct.lo, ct.hi, w, m)
        elif op == '<<':
            if kb == 'c':
                f = tpl_bin('<<', ka, 'c', 'w')(pa, pb & m, ct.lo, ct.hi, w, m)
            else:
                f = tpl_bin('<<', ka, kb, 'shl')(pa, pb, ct.lo, ct.hi, w, m)
        elif op == '>>':
            if kb == 'c':
                f = tpl_bin('>>', ka, 'c', 'n')(pa, pb & m, ct.lo, ct.hi, w, m)
            else:
                f = tpl_bin('>>', ka, kb, 'shr')(pa, pb, ct.lo, ct.hi, w, m)
        else:
            fn = self.binop_fn(op, ct, line)
            af = pa if ka == 'f' else (_const_fn(pa) if ka == 'c' else _slot_fn(pa))
            bf = pb if kb == 'f' else (_const_fn(pb) if kb == 'c' else _slot_fn(pb))
            if kb == 'c' and not ct.flt and pb != 0 and pb != -1:
                if op == '/':
                    if pb > 0:
                        def f(fr):
                            a = af(fr)
                            return a // pb if a >= 0 else -((-a) // pb)
                    else:
                        def f(fr):
                            return fn(af(fr), pb)
                else:
                    if pb > 0:
                        def f(fr):
                            a = af(fr)
                            return a % pb if a >= 0 else -((-a) % pb)
                    else:
                        def f(fr):
                            return fn(af(fr), pb)
            else:
                def f(fr):
                    return fn(af(fr), bf(fr))
        r = E(ct, 'v', f, line)
        if ka == 'c' and kb == 'c':
            try:
                v = f(None)
            except CError:
                v = None
            if v is not None:
                r.cv = v
                r.f = _const_fn(v)
        return r

    def ptr_arith(self, op, L, R, lt, rt_, line):
        if is_ptr(lt) and is_ptr(rt_):
            if op != '-':
                raise CCompileError('포인터끼리는 더할 수 없어요.', line)
            if not (same_type(lt.to, rt_.to) or lt.to is VOID or rt_.to is VOID):
                raise CCompileError(f'타입이 다른 포인터끼리는 뺄 수 없어요: {tname(lt)} - {tname(rt_)}', line, H_TYPE)
            esz = self.elem_size(lt, line)
            if callable(esz):
                raise CCompileError('가변 길이 배열 포인터끼리의 뺄셈은 지원하지 않아요.', line)
            af, bf = self.val(L), self.val(R)

            def f(fr):
                d = af(fr) - bf(fr)
                return d // esz if d >= 0 else -((-d) // esz)
            return E(LONG, 'v', f, line)
        if is_ptr(lt):
            P, I, pt = L, R, lt
        else:
            if op == '-':
                raise CCompileError('정수에서 포인터를 뺄 수 없어요.', line)
            P, I, pt = R, L, rt_
        if not is_int(dtype(I)):
            raise CCompileError('포인터에는 정수만 더하거나 뺄 수 있어요.', line, H_TYPE)
        esz = self.elem_size(pt, line)
        kp, pp = self.opnd(P)
        ki, pi = self.opnd(I)
        if callable(esz):
            pf = self.val(P)
            xf = self.val(I)
            sgn = -1 if op == '-' else 1

            def f(fr):
                return pf(fr) + sgn * xf(fr) * esz(fr)
            return E(pt, 'v', f, line)
        if op == '-':
            if ki == 'c':
                pi = -pi
            else:
                g = pi if ki == 'f' else _slot_fn(pi)
                ki, pi = 'f', (lambda fr: -g(fr))
        if ki == 'c':
            f = tpl_addr(kp, 'c', True)(pp, pi * esz, 1)
        else:
            f = tpl_addr(kp, ki, esz == 1)(pp, pi, esz)
        return E(pt, 'v', f, line)

    def cmp(self, op, L, R, line, cond):
        lt, rt_ = dtype(L), dtype(R)
        if is_arith(lt) and is_arith(rt_):
            ct = usual_arith(lt, rt_)
            ka, pa = self.opnd(L, ct)
            kb, pb = self.opnd(R, ct)
        elif (is_ptr(lt) or is_int(lt)) and (is_ptr(rt_) or is_int(rt_)):
            ka, pa = self.opnd(L)
            kb, pb = self.opnd(R)
        else:
            raise CCompileError(f'비교할 수 없는 값이에요: {tname(lt)} {op} {tname(rt_)}', line, H_TYPE)
        f = tpl_cmp(op, ka, kb, cond)(pa, pb)
        cv = None
        if ka == 'c' and kb == 'c':
            cv = f(None)
            cv = (1 if cv else 0) if not cond else bool(cv)
        return f, cv

    def cond(self, n):
        """조건식 → (참/거짓을 내는 함수, 상수면 그 값)."""
        c = n.__class__
        line = _ln(n)
        if c is c_ast.BinaryOp:
            if n.op in CMP_OPS:
                L = self.ex(n.left)
                R = self.ex(n.right)
                for x in (L, R):
                    if x.k == 'b':
                        raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {x.name}', line)
                return self.cmp(n.op, L, R, line, True)
            if n.op == '&&':
                a, ca = self.cond(n.left)
                b, cb = self.cond(n.right)
                if ca is not None and cb is not None:
                    v = bool(ca and cb)
                    return (lambda fr: v), v
                return (lambda fr: a(fr) and b(fr)), None
            if n.op == '||':
                a, ca = self.cond(n.left)
                b, cb = self.cond(n.right)
                if ca is not None and cb is not None:
                    v = bool(ca or cb)
                    return (lambda fr: v), v
                return (lambda fr: a(fr) or b(fr)), None
        if c is c_ast.UnaryOp and n.op == '!':
            a, ca = self.cond(n.expr)
            if ca is not None:
                v = not ca
                return (lambda fr: v), v
            return (lambda fr: not a(fr)), None
        e = self.ex(n)
        if e.k == 'b':
            raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {e.name}', line)
        t = dtype(e)
        if not is_scalar(t):
            raise CCompileError('조건에는 숫자나 포인터 값이 와야 해요.', line, H_TYPE)
        if e.cv is not None and e.k == 'v':
            v = bool(e.cv)
            return (lambda fr: v), v
        k, p = self.opnd(e)
        if k == 'r':
            return _slot_fn(p), None
        return p, None

    def x_TernaryOp(self, n):
        line = _ln(n)
        c, cv = self.cond(n.cond)
        A = self.ex(n.iftrue)
        B = self.ex(n.iffalse)
        at, bt = dtype(A), dtype(B)
        if is_arith(at) and is_arith(bt):
            t = usual_arith(at, bt)
        elif is_ptr(at) and is_ptr(bt):
            t = Ptr(VOID) if (at.to is VOID or bt.to is VOID) else at
        elif is_ptr(at) and is_int(bt) and B.cv == 0:
            t = at
        elif is_ptr(bt) and is_int(at) and A.cv == 0:
            t = bt
        elif at is bt and at.__class__ is StructT:
            t = at
        elif at is VOID and bt is VOID:
            t = VOID
        else:
            raise CCompileError('삼항 연산자(? :)의 두 값의 타입이 맞지 않아요.', line, H_TYPE)
        if is_scalar(t):
            af, bf = self.val(A, t), self.val(B, t)
        else:
            af, bf = self.val_any(A), self.val_any(B)
        r = E(t, 'v', lambda fr: af(fr) if c(fr) else bf(fr), line)
        if cv is not None and A.cv is not None and B.cv is not None and is_scalar(t):
            r.cv = af(None) if cv else bf(None)
            r.f = _const_fn(r.cv)
        return r

    def x_ExprList(self, n):
        line = _ln(n)
        es = [self.ex(x) for x in n.exprs]
        for x in es:
            if x.k == 'b':
                raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {x.name}', line)
        fs = [self.val_any(e) for e in es]
        last = es[-1]
        t = dtype(last)
        init = tuple(fs[:-1])
        lf = fs[-1]

        def f(fr):
            for g in init:
                g(fr)
            return lf(fr)
        return E(t, 'v', f, line)

    def x_Assignment(self, n):
        f, t = self.assign(n, True)
        return E(t, 'v', f, _ln(n))

    def assign(self, n, want):
        f, t = self._assign(n, want)
        if not want and not getattr(f, '_stmt', False):
            g = f

            def f(fr):
                g(fr)
        return f, t

    def _assign(self, n, want):
        line = _ln(n)
        L = self.ex(n.lvalue)
        self.need_lvalue(L, line)
        R = self.ex(n.rvalue)
        lt = L.t
        if n.op == '=':
            if lt.__class__ is StructT:
                self.check_assign(lt, R, line)
                sz = lt.size
                af = L.f
                sf = self.val_any(R)
                RT = self.rt

                def f(fr):
                    a = af(fr)
                    s = sf(fr)
                    b, o = RT.chk(a, sz, line, True)
                    b.data[o:o + sz] = s[0]
                    b.init[o:o + sz] = s[1]
                    return s
                return f, lt
            self.check_assign(lt, R, line)
            kv, pv = self.opnd(R, lt)
            if L.k == 'r':
                return _st(tpl_asg(kv, want)(L.slot, pv), want), lt
            return _st(self.mk_store(L, kv, pv, want), want), lt
        op = n.op[:-1]
        rt_ = dtype(R)
        if is_ptr(lt):
            if op not in ('+', '-') or not is_int(rt_):
                raise CCompileError(f'포인터에는 {n.op} 를 쓸 수 없어요(정수만 더하거나 뺄 수 있어요).', line, H_TYPE)
            esz = self.elem_size(lt, line)
            if callable(esz):
                raise CCompileError('가변 길이 배열 포인터의 += 는 지원하지 않아요.', line)
            bf = self.val(R)
            sg = -esz if op == '-' else esz
            if L.k == 'r':
                s = L.slot
                rd = self.rv(L)[1]

                def f(fr):
                    v = rd(fr) + bf(fr) * sg
                    fr[s] = v
                    return v
                return f, lt
            af = L.f
            rd = self.mk_reader(lt, line)
            wr = self.mk_writer(lt, line)

            def f(fr):
                a = af(fr)
                v = rd(a) + bf(fr) * sg
                wr(a, v)
                return v
            return f, lt
        if not (is_arith(lt) and is_arith(rt_)):
            raise CCompileError(f'숫자가 아닌 값으로 {n.op} 계산을 할 수 없어요: {tname(lt)} {n.op} {tname(rt_)}', line, H_TYPE)
        if op in ('%', '<<', '>>', '&', '|', '^') and not (is_int(lt) and is_int(rt_)):
            raise CCompileError(f'실수에는 {op} 연산을 쓸 수 없어요(정수에만 쓸 수 있어요).', line, H_TYPE)
        if op in ('<<', '>>'):
            ct, rct = promote(lt), promote(rt_)
        else:
            ct = rct = usual_arith(lt, rt_)
        if L.k == 'r' and L.init and ct is lt and op in ('+', '-', '*', '&', '|', '^'):
            kb, pb = self.opnd(R, ct)
            if ct.flt:
                mode = 'f32' if ct is FLOAT else 'n'
            else:
                mode = 'w' if op in ('+', '-', '*') else 'n'
            return _st(tpl_casg(op, kb, mode, want)(L.slot, pb, ct.lo, ct.hi, wrapf(ct)), want), lt
        opf = self.binop_fn(op, ct, line)
        to_ct = conv_fn(lt, ct) or (lambda v: v)
        to_lt = conv_fn(ct, lt) or (lambda v: v)
        bf = self.val(R, rct)
        if L.k == 'r':
            s = L.slot
            rd = self.rv(L)[1]

            def f(fr):
                v = to_lt(opf(to_ct(rd(fr)), bf(fr)))
                fr[s] = v
                return v
            return f, lt
        af = L.f
        rd = self.mk_reader(lt, line)
        wr = self.mk_writer(lt, line)

        def f(fr):
            a = af(fr)
            v = to_lt(opf(to_ct(rd(a)), bf(fr)))
            wr(a, v)
            return v
        return f, lt

    def incdec(self, n, want):
        f, t = self._incdec(n, want)
        if not want and not getattr(f, '_stmt', False):
            g = f

            def f(fr):
                g(fr)
        return f, t

    def _incdec(self, n, want):
        line = _ln(n)
        op = n.op
        post = op[0] == 'p'
        sign = '+' if '++' in op else '-'
        e = self.ex(n.expr)
        self.need_lvalue(e, line)
        t = e.t
        if is_ptr(t):
            dl = self.elem_size(t, line)
            if callable(dl):
                raise CCompileError('가변 길이 배열 포인터의 ++ 는 지원하지 않아요.', line)
            mode, W = 'p', None
        elif is_arith(t):
            if t is DOUBLE or t is LDOUBLE:
                mode, W, dl = 'p', None, 1.0
            elif t is FLOAT:
                mode, W, dl = 'g', f32, 1.0
            elif t is BOOL:
                mode, W, dl = 'g', _tobool, 1
            else:
                mode, W, dl = 'w', wrapf(t), 1
        else:
            raise CCompileError('++/--는 숫자나 포인터 변수에만 쓸 수 있어요.', line)
        lo = getattr(t, 'lo', 0)
        hi = getattr(t, 'hi', 0)
        if e.k == 'r' and e.init:
            return _st(tpl_inc(sign, mode, post, want)(e.slot, dl, lo, hi, W), want), t
        d = dl if sign == '+' else -dl
        conv = W if W is not None else (lambda v: v)
        if mode == 'w':
            def nv(o):
                v = o + d
                return v if lo <= v <= hi else W(v)
        else:
            def nv(o):
                return conv(o + d)
        if e.k == 'r':
            s = e.slot
            rd = self.rv(e)[1]

            def f(fr):
                o = rd(fr)
                v = nv(o)
                fr[s] = v
                return o if post else v
            return f, t
        af = e.f
        rd = self.mk_reader(t, line)
        wr = self.mk_writer(t, line)

        def f(fr):
            a = af(fr)
            o = rd(a)
            v = nv(o)
            wr(a, v)
            return o if post else v
        return f, t

    # ---- 함수 호출
    def x_FuncCall(self, n):
        line = _ln(n)
        callee = n.name
        argn = n.args.exprs if n.args is not None else []
        if callee.__class__ is c_ast.ID:
            s = self.lookup(callee.name)
            nm = callee.name
            if s is None or (s.kind == 'func' and not s.fn.defined and nm in BUILTINS):
                if nm in BUILTINS:
                    return self.call_builtin(nm, argn, line)
                if nm in _NO_INPUT:
                    raise CCompileError(f'입력 함수({nm})는 쓰지 않아요. 매개변수로 받은 값을 쓰세요.', line)
                raise CCompileError(f'지원하지 않는 함수: {nm}', line, '직접 만든 함수라면 이름의 철자를 확인해 보세요. 쓸 수 있는 라이브러리 함수는 정해져 있어요.')
            if s.kind == 'func':
                f = s.fn
                if f.used is None:
                    f.used = line
                return self.call_user(f.t, argn, line, f, None, nm)
        ce = self.ex(callee)
        if ce.k == 'v' and ce.fn is not None:
            return self.call_user(ce.fn.t, argn, line, ce.fn, None, ce.fn.name)
        ct = dtype(ce)
        if not (is_ptr(ct) and ct.to.__class__ is FuncT):
            raise CCompileError('함수가 아닌 것을 호출했어요' + (f': {ce.name}' if ce.name else '.'), line)
        return self.call_user(ct.to, argn, line, None, self.val(ce), ce.name or '함수 포인터')

    def call_user(self, ft, argn, line, fn, ptrf, name):
        if len(argn) != len(ft.params) and not (ft.variadic and len(argn) >= len(ft.params)):
            raise CCompileError(f'인자 수가 맞지 않아요: {name} 함수는 인자 {len(ft.params)}개가 필요한데 {len(argn)}개를 넣었어요.', line)
        if ft.variadic:
            raise CCompileError('가변 인자(...) 함수는 지원하지 않아요.', line)
        fs = []
        for i, (pt, a) in enumerate(zip(ft.params, argn)):
            e = self.ex(a)
            self.check_assign(pt, e, line, f'{name}의 {i + 1}번째 인자')
            fs.append(self.val_any(e) if pt.__class__ is StructT else self.val(e, pt))
        RT = self.rt
        k = len(fs)
        if fn is not None:
            F = fn
            if k == 0:
                def f(fr):
                    return F.invoke([])
            elif k == 1:
                a0 = fs[0]

                def f(fr):
                    return F.invoke([a0(fr)])
            elif k == 2:
                a0, a1 = fs

                def f(fr):
                    return F.invoke([a0(fr), a1(fr)])
            elif k == 3:
                a0, a1, a2 = fs

                def f(fr):
                    return F.invoke([a0(fr), a1(fr), a2(fr)])
            else:
                fl = tuple(fs)

                def f(fr):
                    return F.invoke([g(fr) for g in fl])
        else:
            fl = tuple(fs)
            pf = ptrf

            def f(fr):
                F = RT.func_at(pf(fr), line)
                if len(F.t.params) != len(fl):
                    raise CRuntimeError('함수 포인터가 가리키는 함수의 매개변수 수가 달라요.', line)
                return F.invoke([g(fr) for g in fl])
        return E(ft.ret, 'v', f, line)

    def call_builtin(self, name, argn, line):
        ret, ptypes, variadic = BUILTINS[name]
        if len(argn) < len(ptypes) or (not variadic and len(argn) > len(ptypes)):
            raise CCompileError(f'인자 수가 맞지 않아요: {name} 함수는 인자 {len(ptypes)}개가 필요한데 {len(argn)}개를 넣었어요.', line)
        args = [self.ex(a) for a in argn]
        if name in ('printf', 'sprintf'):
            return self.call_printf(name, args, line)
        fs = []
        for i, (pt, a) in enumerate(zip(ptypes, args)):
            self.check_assign(pt, a, line, f'{name}의 {i + 1}번째 인자')
            fs.append(self.val(a, pt))
        m = self.builtin_impl(name, line)
        k = len(fs)
        if k == 0:
            def f(fr):
                return m(line)
        elif k == 1:
            a0 = fs[0]

            def f(fr):
                return m(a0(fr), line)
        elif k == 2:
            a0, a1 = fs

            def f(fr):
                return m(a0(fr), a1(fr), line)
        elif k == 3:
            a0, a1, a2 = fs

            def f(fr):
                return m(a0(fr), a1(fr), a2(fr), line)
        else:
            fl = tuple(fs)

            def f(fr):
                return m(*[g(fr) for g in fl], line)
        return E(ret, 'v', f, line)

    def builtin_impl(self, name, line):
        rt = self.rt
        L = Lib(rt)
        g = getattr(L, 'b_' + name, None)
        if g is not None:
            return g
        ct = {'isdigit': _CT_DIGIT, 'isalpha': _CT_ALPHA, 'isalnum': _CT_ALNUM, 'isupper': _CT_UPPER, 'islower': _CT_LOWER,
              'isspace': _CT_SPACE, 'ispunct': _CT_PUNCT, 'isxdigit': _CT_XDIGIT, 'isprint': _CT_PRINT}
        if name in ct:
            return _ctype_fn(ct[name])
        mf = {'sqrt': _m_sqrt, 'fabs': lambda x, line: abs(x), 'floor': _m_floor(math.floor), 'ceil': _m_floor(math.ceil),
              'trunc': _m_floor(math.trunc), 'round': _m_round, 'log': _m_log(math.log), 'log10': _m_log(math.log10),
              'log2': _m_log(math.log2), 'exp': _m1(math.exp), 'sin': _m1(math.sin), 'cos': _m1(math.cos), 'tan': _m1(math.tan),
              'atan': _m1(math.atan), 'pow': _m_pow, 'fmin': _m_fmin, 'fmax': _m_fmax, 'fmod': _m_fmod,
              'atan2': lambda y, x, line: math.atan2(y, x), 'hypot': lambda x, y, line: math.hypot(x, y)}
        if name in mf:
            return mf[name]
        raise CCompileError(f'지원하지 않는 함수: {name}', line)

    def call_printf(self, name, args, line):
        if name == 'printf':
            fe, rest, be = args[0], args[1:], None
        else:
            be, fe, rest = args[0], args[1], args[2:]
            self.check_assign(_CP, be, line, 'sprintf의 1번째 인자')
        self.check_assign(_CC, fe, line, f'{name}의 서식')
        specs = []
        for a in rest:
            if a.k == 'b':
                raise CCompileError(f'라이브러리 함수 이름을 값처럼 쓸 수는 없어요: {a.name}', line)
            t = dtype(a)
            if t.__class__ is Prim:
                if t.flt:
                    specs.append(('f', self.val(a, DOUBLE)))
                else:
                    pt = promote(t)
                    specs.append(('i' if pt.signed else 'u', self.val(a, pt)))
            elif t.__class__ is Ptr:
                specs.append(('p', self.val(a)))
            else:
                raise CCompileError(f'{name}로 {tname(t)} 값을 바로 출력할 수 없어요.', line)
        specs = tuple(specs)
        RT = self.rt
        parsed = None
        if fe.k == 'm' and fe.lit is not None:
            parsed = _parse_fmt(fe.lit[:-1], line)
        ff = self.val(fe)
        if name == 'printf':
            if parsed is not None:
                def f(fr):
                    bs = cfmt(RT, parsed, [(c, g(fr)) for c, g in specs], line)
                    RT.emit(bs)
                    return len(bs)
            else:
                def f(fr):
                    p = _parse_fmt(RT.cstr(ff(fr), line), line)
                    bs = cfmt(RT, p, [(c, g(fr)) for c, g in specs], line)
                    RT.emit(bs)
                    return len(bs)
            return E(INT, 'v', f, line)
        bf = self.val(be)

        def f(fr):
            dst = bf(fr)
            p = parsed if parsed is not None else _parse_fmt(RT.cstr(ff(fr), line), line)
            bs = cfmt(RT, p, [(c, g(fr)) for c, g in specs], line)
            RT.wbytes(dst, bs + b'\0', line)
            return len(bs)
        return E(INT, 'v', f, line)

    # ---- 문장
    def stmt(self, n):
        m = getattr(self, 's_' + n.__class__.__name__, None)
        if m is not None:
            return m(n)
        return self.s_expr(n)

    def sub(self, n):
        if n is None:
            return None
        self.push()
        try:
            s = self.stmt(n)
        finally:
            self.pop()
        if s is not None:
            s.ln = _ln(n)
        return s

    def s_expr(self, n):
        c = n.__class__
        line = _ln(n)
        if c is c_ast.Assignment:
            return self.assign(n, False)[0]
        if c is c_ast.UnaryOp and n.op in ('++', '--', 'p++', 'p--'):
            return self.incdec(n, False)[0]
        if c is c_ast.ExprList:
            fs = tuple(self.s_expr(x) for x in n.exprs)

            def s(fr):
                for g in fs:
                    g(fr)
            return s
        if c not in (c_ast.FuncCall, c_ast.UnaryOp, c_ast.BinaryOp, c_ast.TernaryOp, c_ast.Cast, c_ast.ID, c_ast.Constant,
                     c_ast.ArrayRef, c_ast.StructRef):
            raise CCompileError(f'지원하지 않는 문장이에요: {c.__name__}', line)
        e = self.ex(n)
        if e.k == 'b':
            raise CCompileError(f'함수 이름 뒤에 ( )가 없어요: {e.name}', line)
        g = self.val_any(e)
        if c is c_ast.FuncCall and e.t is VOID:
            def s(fr):
                g(fr)
            return s

        def s(fr):
            g(fr)
        return s

    def s_Compound(self, n):
        self.push()
        items = []
        try:
            for it in n.block_items or []:
                s = self.stmt(it)
                if s is not None:
                    s.ln = _ln(it)
                    items.append(s)
        finally:
            self.pop()
        return mk_block(items)

    def s_EmptyStatement(self, n):
        return None

    def s_Pragma(self, n):
        return None

    def s_Typedef(self, n):
        self.typedef(n)
        return None

    def s_DeclList(self, n):
        fs = [f for f in (self.local_decl(d) for d in n.decls) if f is not None]
        if not fs:
            return None
        if len(fs) == 1:
            return fs[0]
        fs = tuple(fs)

        def s(fr):
            for g in fs:
                g(fr)
        return s

    def s_Decl(self, n):
        return self.local_decl(n)

    def s_If(self, n):
        c, cv = self.cond(n.cond)
        t = self.sub(n.iftrue)
        e = self.sub(n.iffalse)
        if t is None and e is None:
            def s(fr):
                c(fr)
        elif e is None:
            def s(fr):
                if c(fr):
                    return t(fr)
        elif t is None:
            def s(fr):
                if not c(fr):
                    return e(fr)
        else:
            def s(fr):
                if c(fr):
                    return t(fr)
                return e(fr)
        return s

    def loop_body(self, n):
        self.fn.loops += 1
        try:
            return self.sub(n)
        finally:
            self.fn.loops -= 1

    def s_While(self, n):
        c, cv = self.cond(n.cond)
        body = self.loop_body(n.stmt)
        return _mk_loop(None, None if cv is True else c, cv, None, body, self.rt, False)

    def s_DoWhile(self, n):
        body = self.loop_body(n.stmt)
        c, cv = self.cond(n.cond)
        return _mk_loop(None, None if cv is True else c, cv, None, body, self.rt, True)

    def s_For(self, n):
        self.push()
        try:
            init = None
            if n.init is not None:
                if n.init.__class__ is c_ast.DeclList:
                    init = self.s_DeclList(n.init)
                elif n.init.__class__ is c_ast.Decl:
                    init = self.local_decl(n.init)
                else:
                    init = self.s_expr(n.init)
            if n.cond is not None:
                c, cv = self.cond(n.cond)
            else:
                c, cv = None, True
            nxt = self.s_expr(n.next) if n.next is not None else None
            body = self.loop_body(n.stmt)
        finally:
            self.pop()
        return _mk_loop(init, None if cv is True else c, cv, nxt, body, self.rt, False)

    def s_Break(self, n):
        if self.fn.loops == 0 and self.fn.switches == 0:
            raise CCompileError('반복문이나 switch 밖에서 break를 썼어요.', _ln(n))

        def s(fr):
            return BRK
        return s

    def s_Continue(self, n):
        if self.fn.loops == 0:
            raise CCompileError('반복문 밖에서 continue를 썼어요.', _ln(n))

        def s(fr):
            return CONT
        return s

    def s_Return(self, n):
        line = _ln(n)
        ctx = self.fn
        ret = ctx.func.t.ret
        rv = ctx.rv
        if n.expr is None:
            if ret is not VOID and ctx.func.name != 'main':
                raise CCompileError(f'이 함수({ctx.func.name})는 {tname(ret)} 값을 return 해야 해요.', line)
            if ret is not VOID:
                def s(fr):
                    fr[rv] = 0
                    return RET
                return s

            def s(fr):
                return RET
            return s
        e = self.ex(n.expr)
        if ret is VOID:
            if e.t is VOID:
                g = e.f

                def s(fr):
                    g(fr)
                    return RET
                return s
            raise CCompileError('void 함수에서는 값을 return 할 수 없어요.', line)
        self.check_assign(ret, e, line, 'return 값')
        if ret.__class__ is StructT:
            g = self.val_any(e)
        else:
            k, p = self.opnd(e, ret)
            if k == 'c':
                def s(fr):
                    fr[rv] = p
                    return RET
                return s
            if k == 'r':
                def s(fr):
                    fr[rv] = fr[p]
                    return RET
                return s
            g = p

        def s(fr):
            fr[rv] = g(fr)
            return RET
        return s

    def s_Switch(self, n):
        line = _ln(n)
        e = self.ex(n.cond)
        t = dtype(e)
        if not is_int(t):
            raise CCompileError('switch에는 정수(또는 문자) 값이 와야 해요.', line, H_TYPE)
        pt = promote(t)
        cf = self.val(e, pt)
        flat = []
        table = {}
        dflt = [None]
        self.push()
        self.fn.switches += 1
        try:
            body = n.stmt
            items = body.block_items if body.__class__ is c_ast.Compound else [body]

            def add(it):
                ic = it.__class__
                if ic is c_ast.Case:
                    ce = self.ex(it.expr)
                    if ce.cv is None or not is_int(ce.t):
                        raise CCompileError('case 값은 정수 상수여야 해요(변수는 쓸 수 없어요).', _ln(it))
                    cvf = conv_fn(ce.t, pt)
                    v = cvf(ce.cv) if cvf else ce.cv
                    if v in table:
                        raise CCompileError(f'같은 case 값이 두 번 나왔어요: {v}', _ln(it))
                    table[v] = len(flat)
                    for s2 in it.stmts or []:
                        add(s2)
                elif ic is c_ast.Default:
                    if dflt[0] is not None:
                        raise CCompileError('default가 두 번 나왔어요.', _ln(it))
                    dflt[0] = len(flat)
                    for s2 in it.stmts or []:
                        add(s2)
                else:
                    s = self.stmt(it)
                    if s is not None:
                        s.ln = _ln(it)
                        flat.append(s)
            for it in items or []:
                add(it)
        finally:
            self.fn.switches -= 1
            self.pop()
        flat = tuple(flat)
        nf = len(flat)
        dv = dflt[0]

        def sw(fr):
            i = table.get(cf(fr), dv)
            if i is None:
                return None
            try:
                while i < nf:
                    r = flat[i](fr)
                    if r is not None:
                        return None if r is BRK else r
                    i += 1
            except CError as ex:
                if ex.line is None and i < nf:
                    ex.line = getattr(flat[i], 'ln', None)
                raise
            return None
        return sw

    def s_Case(self, n):
        raise CCompileError('case는 switch 바로 안에서만 쓸 수 있어요.', _ln(n))

    def s_Default(self, n):
        raise CCompileError('default는 switch 바로 안에서만 쓸 수 있어요.', _ln(n))

    def s_Goto(self, n):
        raise CCompileError('goto는 지원하지 않아요. 반복문과 break를 쓰세요.', _ln(n))

    def s_Label(self, n):
        raise CCompileError('레이블(이름:)과 goto는 지원하지 않아요.', _ln(n))

    def s_FuncDef(self, n):
        raise CCompileError('함수 안에서 함수를 만들 수 없어요(중괄호 짝을 확인해 보세요).', _ln(n))

    def local_decl(self, d):
        line = _ln(d)
        if d.__class__ is c_ast.Typedef:
            self.typedef(d)
            return None
        if d.name is None:
            self.ty(d.type, line)
            return None
        st = d.storage or []
        pend = []
        saved = self.vla_pending
        self.vla_pending = pend
        try:
            t, c = self.ty(d.type, line)
        finally:
            self.vla_pending = saved
        if t.__class__ is FuncT:
            self.declare_func(d)
            return None
        scope = self.scopes[-1]
        if 'extern' in st:
            g = self.scopes[0].get(d.name)
            if g is None or g.kind != 'gmem':
                raise CCompileError(f'extern으로 가리킨 전역 변수가 없어요: {d.name}', line)
            scope[d.name] = g
            return None
        old = scope.get(d.name)
        if old is not None and old.kind != 'func':
            raise CCompileError(f'같은 이름을 이 블록에서 또 선언했어요: {d.name}', line)
        if t is VOID:
            raise CCompileError('void 타입 변수는 만들 수 없어요.', line)
        if t.__class__ is StructT and not t.complete:
            raise CCompileError(f'정의하지 않은 구조체 타입이에요: {tname(t)}', line)
        if pend:
            if d.init is not None:
                raise CCompileError('크기가 변수인 배열(가변 길이 배열)은 선언할 때 초기화할 수 없어요.', line)
            if 'static' in st:
                raise CCompileError('static 배열의 크기는 상수여야 해요.', line)
        if t.__class__ is Arr and t.n is None and t.vla is None:
            if d.init is None:
                raise CCompileError('배열 크기를 정하지 않았어요. int arr[5]; 처럼 크기를 쓰거나 초기값을 주세요.', line)
            t = Arr(t.of, self.init_count(t, d.init, line))
        if 'static' in st:
            a = self.alloc_static(t, d.name)
            if d.init is not None:
                self.ginit.append((a, t, self.init_writes(t, d.init, line), line))
            scope[d.name] = Sym('gmem', t, ca=a, name=d.name, ro=c)
            return None
        fn = self.fn
        memory = t.__class__ in (Arr, StructT) or d.name in fn.addr_taken
        if not memory:
            slot = fn.new_slot()
            # C에서는 변수의 이름이 자기 초기값 식 안에서도 보인다(예: int *p = malloc(sizeof *p);)
            sym = Sym('reg', t, slot=slot, init=False, name=d.name, ro=c)
            scope[d.name] = sym
            if d.init is not None:
                init = d.init
                if init.__class__ is c_ast.InitList:
                    if len(init.exprs) != 1:
                        raise CCompileError('변수 하나에는 값 하나만 넣을 수 있어요.', line)
                    init = init.exprs[0]
                e = self.ex(init)
                self.check_assign(t, e, line, '초기화')
                kv, pv = self.opnd(e, t)
                f = tpl_asg(kv, False)(slot, pv)
                sym.init = True
                return f

            def f(fr):
                fr[slot] = None
            return f
        slot = fn.new_slot()
        fn.mslots.append(slot)
        scope[d.name] = Sym('mem', t, slot=slot, name=d.name, ro=c)
        writes = self.init_writes(t, d.init, line) if d.init is not None else None
        return self.mk_local(slot, t, d.name, writes, pend, line)

    def mk_local(self, slot, t, name, writes, pend, line):
        rt = self.rt
        B = rt.B
        nb = rt.new_block
        dims, leaf = arr_dims(t)
        st = leaf if leaf.__class__ is StructT else None
        esz = leaf.size if dims else 0
        if pend:
            pend = tuple(pend)
            sizef = self.dsize(t)
            vdims = []
            tt = t
            while tt.__class__ is Arr:
                vdims.append(tt.vla if tt.vla is not None else -1 - (tt.n or 0))
                tt = tt.of
            vdims = tuple(vdims)

            def f(fr):
                for s, g, ln in pend:
                    v = g(fr)
                    if v < 0:
                        raise CRuntimeError(f'배열 크기가 음수예요: {v}', ln)
                    fr[s] = v
                size = sizef(fr) if callable(sizef) else sizef
                if size > STACK_CAP:
                    raise CRuntimeError(f'지역 배열이 너무 커요({size}바이트): {name}', line, '큰 배열은 malloc으로 만드세요.')
                old = fr[slot]
                if old is not None:
                    B.pop(old >> SH, None)
                ds = tuple(fr[x] if x >= 0 else -1 - x for x in vdims)
                fr[slot] = nb(size, name, 'stack', False, ds, esz, st=st)
            return f
        size = t.size
        if size > STACK_CAP:
            raise CCompileError(f'지역 배열이 너무 커요({size}바이트): {name}', line, '큰 배열은 malloc이나 전역 변수로 만드세요.')
        dimsv = dims or None
        if writes is None:
            def f(fr):
                old = fr[slot]
                if old is not None:
                    B.pop(old >> SH, None)
                fr[slot] = nb(size, name, 'stack', False, dimsv, esz, st=st)
            return f
        tmpl = bytearray(size)
        dyn = []
        for w in writes:
            k = w[0]
            if k == 'v':
                _, off, wt, vf, cv = w
                if cv is not None:
                    wt.pk(tmpl, off, cv)
                else:
                    dyn.append(_mk_write(w))
            elif k == 'b':
                _, off, bs = w
                tmpl[off:off + len(bs)] = bs
            else:
                dyn.append(_mk_write(w))
        tmpl = bytes(tmpl)
        dyn = tuple(dyn)
        if not dyn:
            def f(fr):
                old = fr[slot]
                if old is not None:
                    B.pop(old >> SH, None)
                fr[slot] = nb(size, name, 'stack', True, dimsv, esz, data=tmpl, st=st)
            return f

        def f(fr):
            old = fr[slot]
            if old is not None:
                B.pop(old >> SH, None)
            a = nb(size, name, 'stack', True, dimsv, esz, data=tmpl, st=st)
            b = B[a >> SH]
            for w in dyn:
                w(fr, b)
            fr[slot] = a
        return f

    # ---- 마무리
    def finish(self):
        rt = self.rt
        rt.dyn0 = rt.next
        for a, t, writes, line in self.ginit:
            b = rt.B[a >> SH]
            for w in writes:
                try:
                    _mk_write(w)(None, b)
                except CError as e:
                    if e.line is None:
                        e.line = line
                    raise
                except (TypeError, IndexError):
                    raise CCompileError('전역·static 변수의 초깃값은 상수여야 해요.', line) from None
        snaps = []
        for a in self.gblocks:
            b = rt.B[a >> SH]
            snaps.append((b, bytes(b.data), bytes(b.init)))
        return snaps


def dims_leaf(t):
    return arr_dims(t)


def _mk_write(w):
    k = w[0]
    if k == 'v':
        _, off, t, vf, _cv = w
        pk = t.pk

        def wr(fr, b):
            pk(b.data, off, vf(fr))
        return wr
    if k == 'b':
        _, off, bs = w
        n = len(bs)

        def wr(fr, b):
            b.data[off:off + n] = bs
        return wr
    _, off, n, sf = w

    def wr(fr, b):
        d, i = sf(fr)
        b.data[off:off + n] = d
        b.init[off:off + n] = i
    return wr


def _mk_loop(init, cond, cv, nxt, body, rt, do):
    spend = rt.spend
    if cv is False and not do:
        if init is None:
            return None

        def lp0(fr):
            init(fr)
        return lp0
    if cond is None and not do:
        # 무한 반복(while(1) / for(;;)): break나 return으로만 끝난다
        def lp(fr):
            if init is not None:
                init(fr)
            c = 0
            while True:
                c += 1
                if c > 4095:
                    spend(c)
                    c = 0
                if body is not None:
                    r = body(fr)
                    if r is not None:
                        if r is BRK:
                            break
                        if r is not CONT:
                            spend(c)
                            return r
                if nxt is not None:
                    nxt(fr)
            spend(c)
        return lp
    if do:
        cnd = cond if cond is not None else (lambda fr: True)

        def lp(fr):
            c = 0
            while True:
                c += 1
                if c > 4095:
                    spend(c)
                    c = 0
                if body is not None:
                    r = body(fr)
                    if r is not None:
                        if r is BRK:
                            break
                        if r is not CONT:
                            spend(c)
                            return r
                if not cnd(fr):
                    break
            spend(c)
        return lp
    if body is not None and nxt is not None:
        def lp(fr):
            if init is not None:
                init(fr)
            c = 0
            while cond(fr):
                c += 1
                if c > 4095:
                    spend(c)
                    c = 0
                r = body(fr)
                if r is not None:
                    if r is BRK:
                        break
                    if r is not CONT:
                        spend(c)
                        return r
                nxt(fr)
            if c:
                spend(c)
        return lp
    if body is not None:
        def lp(fr):
            if init is not None:
                init(fr)
            c = 0
            while cond(fr):
                c += 1
                if c > 4095:
                    spend(c)
                    c = 0
                r = body(fr)
                if r is not None:
                    if r is BRK:
                        break
                    if r is not CONT:
                        spend(c)
                        return r
            if c:
                spend(c)
        return lp

    def lp(fr):
        if init is not None:
            init(fr)
        c = 0
        while cond(fr):
            c += 1
            if c > 4095:
                spend(c)
                c = 0
            if nxt is not None:
                nxt(fr)
        if c:
            spend(c)
    return lp


# ---------------------------------------------------------------- 라이브러리 함수
class Lib:
    def __init__(self, rt):
        self.rt = rt

    def b_puts(self, s, line):
        bs = self.rt.cstr(s, line) + b'\n'
        self.rt.emit(bs)
        return len(bs)

    def b_putchar(self, c, line):
        self.rt.emit(bytes((c & 0xFF,)))
        return c & 0xFF

    def b_strlen(self, s, line):
        return len(self.rt.cstr(s, line))

    def _overlap(self, d, s, n, what, line):
        if d >> SH == s >> SH and n > 0:
            if d < s + n and s < d + n:
                raise CRuntimeError(f'{what}의 두 메모리 영역이 겹쳐요. 겹칠 때는 memmove를 쓰세요.', line)

    def b_strcpy(self, d, s, line):
        bs = self.rt.cstr(s, line) + b'\0'
        self._overlap(d, s, len(bs), 'strcpy', line)
        self.rt.wbytes(d, bs, line)
        return d

    def b_strncpy(self, d, s, n, line):
        bs = self.rt.cstr(s, line, n)
        bs = bs + b'\0' * (n - len(bs))
        self.rt.wbytes(d, bs, line)
        return d

    def b_strcat(self, d, s, line):
        dl = len(self.rt.cstr(d, line))
        bs = self.rt.cstr(s, line) + b'\0'
        self._overlap(d + dl, s, len(bs), 'strcat', line)
        self.rt.wbytes(d + dl, bs, line)
        return d

    def b_strncat(self, d, s, n, line):
        dl = len(self.rt.cstr(d, line))
        bs = self.rt.cstr(s, line, n) + b'\0'
        self.rt.wbytes(d + dl, bs, line)
        return d

    def _scmp(self, a, c, line, limit):
        rt = self.rt
        try:
            b1 = rt.B[a >> SH]
        except KeyError:
            rt.bad(a, line)
        try:
            b2 = rt.B[c >> SH]
        except KeyError:
            rt.bad(c, line)
        o1 = (a & MASK) - BIAS
        o2 = (c & MASK) - BIAS
        if limit == 0:
            return 0
        e1 = b1.data.find(0, o1) if 0 <= o1 < b1.size else -1
        e2 = b2.data.find(0, o2) if 0 <= o2 < b2.size else -1
        if e1 >= 0 and e2 >= 0 and b1.init.find(0, o1, e1 + 1) < 0 and b2.init.find(0, o2, e2 + 1) < 0:
            s1 = bytes(b1.data[o1:e1])
            s2 = bytes(b2.data[o2:e2])
            if limit is not None:
                s1, s2 = s1[:limit], s2[:limit]
            return 0 if s1 == s2 else (-1 if s1 < s2 else 1)
        i = 0
        while limit is None or i < limit:
            p1, p2 = o1 + i, o2 + i
            if not (0 <= p1 < b1.size):
                rt.oob(b1, p1, 1, line)
            if not b1.init[p1]:
                rt.uninit(b1, p1, 1, line, H_UNINIT_STR)
            if not (0 <= p2 < b2.size):
                rt.oob(b2, p2, 1, line)
            if not b2.init[p2]:
                rt.uninit(b2, p2, 1, line, H_UNINIT_STR)
            x, y = b1.data[p1], b2.data[p2]
            if x != y:
                return -1 if x < y else 1
            if x == 0:
                return 0
            i += 1
        return 0

    def b_strcmp(self, a, b, line):
        return self._scmp(a, b, line, None)

    def b_strncmp(self, a, b, n, line):
        return self._scmp(a, b, line, n)

    def b_strchr(self, s, c, line):
        bs = self.rt.cstr(s, line)
        c &= 0xFF
        if c == 0:
            return s + len(bs)
        i = bs.find(c)
        return 0 if i < 0 else s + i

    def b_strrchr(self, s, c, line):
        bs = self.rt.cstr(s, line)
        c &= 0xFF
        if c == 0:
            return s + len(bs)
        i = bs.rfind(c)
        return 0 if i < 0 else s + i

    def b_strstr(self, h, nd, line):
        hb = self.rt.cstr(h, line)
        nb_ = self.rt.cstr(nd, line)
        i = hb.find(nb_)
        return 0 if i < 0 else h + i

    def b_memset(self, p, c, n, line):
        if n == 0:
            return p
        b, o = self.rt.chk(p, n, line, True)
        b.data[o:o + n] = bytes((c & 0xFF,)) * n
        b.init[o:o + n] = _ones(n)
        return p

    def b_memcpy(self, d, s, n, line):
        if n == 0:
            return d
        self._overlap(d, s, n, 'memcpy', line)
        return self.b_memmove(d, s, n, line)

    def b_memmove(self, d, s, n, line):
        if n == 0:
            return d
        bs, os_ = self.rt.chk(s, n, line)
        data = bytes(bs.data[os_:os_ + n])
        ini = bytes(bs.init[os_:os_ + n])
        bd, od = self.rt.chk(d, n, line, True)
        bd.data[od:od + n] = data
        bd.init[od:od + n] = ini
        return d

    def b_malloc(self, n, line):
        return self.rt.malloc(n, line)

    def b_calloc(self, n, s, line):
        return self.rt.malloc(n * s, line, True, 'calloc 메모리')

    def b_realloc(self, p, n, line):
        rt = self.rt
        if p == 0:
            return rt.malloc(n, line, False, 'realloc 메모리')
        b = rt.B.get(p >> SH)
        if b is None or b.kind != 'heap' or (p & MASK) != BIAS:
            rt.free(p, line)
        new = rt.malloc(n, line, False, 'realloc 메모리')
        nb_ = rt.B[new >> SH]
        k = min(n, b.size)
        nb_.data[:k] = b.data[:k]
        nb_.init[:k] = b.init[:k]
        rt.free(p, line)
        return new

    def b_free(self, p, line):
        self.rt.free(p, line)

    def b_abs(self, v, line):
        return v if v >= 0 else (-v if v != -2147483648 else v)

    def b_labs(self, v, line):
        return v if v >= 0 else (-v if v != -(1 << 63) else v)

    b_llabs = b_labs

    def b_atoi(self, s, line):
        return _sx(_strtol(self.rt.cstr(s, line)), 32)

    def b_atol(self, s, line):
        return _strtol(self.rt.cstr(s, line))

    b_atoll = b_atol

    def b_rand(self, line):
        return self.rt.rand()

    def b_srand(self, s, line):
        self.rt.srand(s)

    def b_exit(self, c, line):
        raise CExit(c)

    def b_toupper(self, c, line):
        return c - 32 if 97 <= c <= 122 else c

    def b_tolower(self, c, line):
        return c + 32 if 65 <= c <= 90 else c

    def b_qsort(self, base, n, size, cmp, line):
        rt = self.rt
        if n == 0 or size == 0:
            return None
        total = n * size
        b, o = rt.chk(base, total, line, True)
        fn = rt.func_at(cmp, line)
        data = bytes(b.data[o:o + total])
        ini = bytes(b.init[o:o + total])
        tmp = rt.new_block(total, 'qsort 임시 메모리', 'heap', False, None, size, data=data)
        rt.B[tmp >> SH].init[:] = ini
        inv = fn.invoke

        def c(i, j):
            r = inv([tmp + i * size, tmp + j * size])
            return r
        order = sorted(range(n), key=functools.cmp_to_key(c))
        nd = bytearray()
        ni = bytearray()
        for i in order:
            nd += data[i * size:(i + 1) * size]
            ni += ini[i * size:(i + 1) * size]
        b.data[o:o + total] = nd
        b.init[o:o + total] = ni
        rt.B.pop(tmp >> SH, None)
        return None


# ---------------------------------------------------------------- 실행 단위
class Program:
    def __init__(self, comp):
        self.rt = comp.rt
        self.funcs = comp.funcs
        self.snaps = comp.finish()
        self.max_steps = MAX_STEPS
        self.time_limit = None

    def has(self, name):
        f = self.funcs.get(name)
        return f is not None and f.defined

    def reset(self):
        rt = self.rt
        B = rt.B
        d0 = rt.dyn0
        for k in [k for k in B if k >= d0]:
            del B[k]
        for b, data, ini in self.snaps:
            b.data[:] = data
            b.init[:] = ini
        rt.next = d0
        rt.depth = 0
        rt.left = self.max_steps
        rt.heap = 0
        rt.srand(1)
        rt.deadline = (time.monotonic() + self.time_limit) if self.time_limit else None

    def stdout_text(self):
        return self.rt.out.decode('utf-8', 'replace')

    def _run(self, f, args):
        old = sys.getrecursionlimit()
        if old < PY_RECURSION:
            sys.setrecursionlimit(PY_RECURSION)
        try:
            return f.invoke(args)
        except RecursionError:
            raise CRuntimeError('재귀가 너무 깊어요.', None, H_REC, 'RecursionError') from None
        finally:
            sys.setrecursionlimit(old)

    def run_main(self):
        """main을 실행한다. {'stdout', 'exit', 'error'}"""
        f = self.funcs.get('main')
        if f is None or not f.defined:
            return {'stdout': '', 'exit': None, 'error': CCompileError('main 함수가 없어요.').as_dict()}
        self.reset()
        rt = self.rt
        args = []
        np_ = len(f.t.params)
        if np_ >= 1:
            args.append(1)
        if np_ >= 2:
            s = rt.new_block(5, 'argv[0]', 'arg', True, (5,), 1, data=b'prog\0')
            av = rt.new_block(16, 'argv', 'arg', True, (2,), 8)
            Ptr.pk(rt.B[av >> SH].data, 0, s)
            args.append(av)
        try:
            r = self._run(f, args)
            code = (r or 0) & 0xFF
        except CExit as e:
            code = e.code & 0xFF
        except CError as e:
            return {'stdout': self.stdout_text(), 'exit': None, 'error': e.as_dict()}
        return {'stdout': self.stdout_text(), 'exit': code, 'error': None}

    def call(self, name, jargs, spec=None):
        """name(jargs…)를 부르고 반환값을 JSON 값으로 돌려준다(spec: derived·ret)."""
        spec = spec or {}
        f = self.funcs.get(name)
        if f is None or not f.defined:
            raise CCompileError(f'{name} 함수가 없어요.')
        try:
            full = expand_args(f.pnames, jargs, spec)
        except ValueError as e:
            raise CError(str(e), None, '테스트 인자와 cspec(derived)을 확인해 주세요.', 'ArgError') from None
        self.reset()
        vals = [self.arg_in(t, v, pn) for t, v, pn in zip(f.t.params, full, f.pnames)]
        try:
            r = self._run(f, vals)
        except CExit as e:
            raise CRuntimeError(f'exit({e.code})가 호출되어 프로그램이 끝났어요.', None, f'{name} 함수 안에서는 exit 대신 return을 쓰세요.') from None
        env = dict(zip(f.pnames, full))
        return self.ret_out(f.t.ret, r, env, spec.get('ret') or {})

    # ---- JSON → C
    def arg_in(self, t, jv, name):
        c = t.__class__
        if c is Prim:
            if t.flt:
                if isinstance(jv, bool) or not isinstance(jv, (int, float)):
                    raise _argerr(name, t, jv)
                v = float(jv)
                return f32(v) if t is FLOAT else v
            if t is BOOL:
                if isinstance(jv, bool):
                    return 1 if jv else 0
                if isinstance(jv, int) and jv in (0, 1):
                    return jv
                raise _argerr(name, t, jv)
            if isinstance(jv, str) and t.size == 1:
                bs = jv.encode('utf-8')
                if len(bs) != 1:
                    raise CError(f'char 매개변수 {name}에는 한 글자(영문·숫자·기호)를 넣어야 해요: {jv!r}', None, '', 'ArgError')
                v = bs[0]
                return v - 256 if (t.signed and v >= 128) else v
            if isinstance(jv, int) and not isinstance(jv, bool):
                if not (t.lo <= jv <= t.hi):
                    raise CError(f'인자 {name}의 값 {jv}이(가) {tname(t)} 범위를 벗어났어요.', None, '', 'ArgError')
                return jv
            raise _argerr(name, t, jv)
        if c is Ptr:
            if jv is None:
                return 0
            return self.make_block(t.to, jv, name)
        if c is StructT:
            if not isinstance(jv, dict):
                raise _argerr(name, t, jv)
            a = self.make_block(t, jv, name)
            b = self.rt.B[a >> SH]
            return (bytes(b.data), bytes(b.init))
        raise CError(f'매개변수 {name}의 타입({tname(t)})은 테스트 값으로 넣을 수 없어요.', None, '', 'ArgError')

    def make_block(self, et, jv, name):
        rt = self.rt
        if isinstance(jv, str):
            if not is_charish(et):
                raise _argerr(name, Ptr(et), jv)
            bs = jv.encode('utf-8') + b'\0'
            return rt.new_block(len(bs), name, 'arg', True, (len(bs),), 1, data=bs)
        if isinstance(jv, dict) and et.__class__ is StructT:
            items, single = [jv], True
        elif isinstance(jv, list):
            items, single = jv, False
        else:
            raise _argerr(name, Ptr(et), jv)
        if et is VOID or et.__class__ is FuncT or (et.__class__ is StructT and not et.complete):
            raise CError(f'매개변수 {name}({tname(Ptr(et))})에는 테스트 값을 넣을 수 없어요.', None, '', 'ArgError')
        esz = et.size
        dims, leaf = arr_dims(et)
        st = leaf if leaf.__class__ is StructT else None
        bd = None if single else (len(items),) + dims
        a = rt.new_block(len(items) * esz, name, 'arg', True, bd, leaf.size, st=st)
        for i, item in enumerate(items):
            self.store_json(et, a + i * esz, item, name if single else f'{name}[{i}]')
        return a

    def store_json(self, t, a, jv, name):
        rt = self.rt
        c = t.__class__
        if c is Prim or c is Ptr:
            v = self.arg_in(t, jv, name)
            b, o = rt.chk(a, t.size, None)
            t.pk(b.data, o, v)
            return
        if c is Arr:
            if isinstance(jv, str) and is_charish(t.of):
                bs = jv.encode('utf-8')
                if len(bs) > t.n:
                    raise CError(f'{name}에 넣을 문자열이 너무 길어요(최대 {t.n}바이트).', None, '', 'ArgError')
                rt.wbytes(a, bs + b'\0' * (t.n - len(bs)), None)
                return
            if not isinstance(jv, list) or len(jv) != t.n:
                raise CError(f'{name}은(는) 길이 {t.n}인 리스트여야 해요: {jv!r}'[:300], None, '', 'ArgError')
            for j, x in enumerate(jv):
                self.store_json(t.of, a + j * t.of.size, x, f'{name}[{j}]')
            return
        if c is StructT:
            if not isinstance(jv, dict):
                raise _argerr(name, t, jv)
            extra = set(jv) - set(t.fmap)
            if extra:
                raise CError(f'{name}에 없는 멤버 값이 있어요: {sorted(extra)}', None, '', 'ArgError')
            for F in t.fields:
                if F.name not in jv:
                    raise CError(f'{name}에 {F.name} 값이 없어요.', None, '', 'ArgError')
                self.store_json(F.t, a + F.off, jv[F.name], f'{name}.{F.name}')
            return
        raise CError(f'{name}의 타입({tname(t)})은 테스트 값으로 넣을 수 없어요.', None, '', 'ArgError')

    # ---- C → JSON
    def prim_out(self, t, v):
        if t is BOOL:
            return bool(v)
        if t.flt:
            return float(v)
        if t.size == 1:
            return chr(v & 0xFF)
        return v

    def ret_out(self, t, v, env, rs):
        c = t.__class__
        if t is VOID:
            return None
        if c is Prim:
            return self.prim_out(t, v)
        if c is StructT:
            return self.struct_out(t, v[0], v[1])
        if c is Ptr:
            return self.ptr_out(t, v, env, rs, 'len')
        raise CError(f'반환 타입 {tname(t)}은 채점할 수 없어요.', None, '', 'SpecError')

    def ptr_out(self, t, v, env, rs, key):
        if v == 0:
            return None
        et = t.to
        if is_charish(et):
            return self.rt.cstr(v, None).decode('utf-8', 'replace')
        if key not in rs:
            raise CError(f'반환 타입이 {tname(t)}이면 spec.ret.{key}(돌려줄 원소 수)가 필요해요.', None, '', 'SpecError')
        try:
            n = eval_len(rs[key], env)
        except ValueError as e:
            raise CError(str(e), None, '', 'SpecError') from None
        if et is VOID or et.__class__ is FuncT:
            raise CError(f'반환 타입 {tname(t)}은 채점할 수 없어요.', None, '', 'SpecError')
        return [self.read_out(et, v + i * et.size, env, rs) for i in range(n)]

    def read_out(self, t, a, env, rs):
        rt = self.rt
        c = t.__class__
        if c is Prim:
            return self.prim_out(t, rt.rd(a, t, None))
        if c is Ptr:
            p = rt.rd(a, t, None)
            return self.ptr_out(t, p, env, rs, 'len2')
        if c is Arr:
            if is_charish(t.of):
                b, o = rt.chk(a, t.n, None)
                raw = bytes(b.data[o:o + t.n])
                k = raw.find(0)
                return (raw if k < 0 else raw[:k]).decode('utf-8', 'replace')
            return [self.read_out(t.of, a + i * t.of.size, env, rs) for i in range(t.n)]
        if c is StructT:
            b, o = rt.chk(a, t.size, None)
            return self.struct_out(t, bytes(b.data[o:o + t.size]), bytes(b.init[o:o + t.size]))
        raise CError(f'{tname(t)} 값은 채점할 수 없어요.', None, '', 'SpecError')

    def struct_out(self, t, data, ini):
        tmp = self.rt.new_block(len(data), '반환 구조체', 'arg', False, None, 0, data=data, st=t)
        self.rt.B[tmp >> SH].init[:] = ini
        out = {}
        for F in t.fields:
            out[F.name] = self.read_out(F.t, tmp + F.off, {}, {})
        return out


def _argerr(name, t, jv):
    return CError(f'테스트 인자 {name}의 값이 매개변수 타입({tname(t)})과 맞지 않아요: {jv!r}'[:300], None, '테스트 args의 순서·모양을 확인해 주세요.', 'ArgError')


# ---------------------------------------------------------------- 공개 함수
def compile_c(code):
    """C 코드 → Program. 문법·타입 오류는 CCompileError."""
    old = sys.getrecursionlimit()
    if old < 20000:
        sys.setrecursionlimit(20000)
    try:
        ast = parse(code)
        comp = Compiler(Runtime())
        comp.unit(ast)
        return Program(comp)
    except RecursionError:
        raise CCompileError('코드가 너무 깊게 중첩되어 있어요.', None) from None
    finally:
        sys.setrecursionlimit(old)


def run_program(code, max_steps=MAX_STEPS, time_limit=None):
    """main이 있는 프로그램을 실행한다(회귀 테스트용). {'stdout', 'exit', 'error'}"""
    try:
        p = compile_c(code)
    except CError as e:
        return {'stdout': '', 'exit': None, 'error': e.as_dict()}
    p.max_steps = max_steps
    p.time_limit = time_limit
    return p.run_main()


def signature(code, func):
    """func의 (매개변수 이름 목록, 매개변수 타입 목록, 반환 타입). 본문은 컴파일하지 않는다(gcc 대조 도구용)."""
    ast = parse(code)
    comp = Compiler(Runtime())
    for ext in ast.ext:
        c = ext.__class__
        if c is c_ast.FuncDef:
            if ext.decl.name == func:
                ft, names = comp.functype(ext.decl.type)
                return names, ft.params, ft.ret
        elif c is c_ast.Typedef:
            comp.typedef(ext)
        elif c is c_ast.Decl:
            if ext.name is None:
                comp.ty(ext.type, _ln(ext))
            elif ext.type.__class__ is not c_ast.FuncDecl and ext.type.__class__ is c_ast.TypeDecl and ext.type.type.__class__ in (c_ast.Struct, c_ast.Union, c_ast.Enum):
                comp.ty(ext.type, _ln(ext))
    raise CCompileError(f'{func} 함수가 없어요.')


_LEN_RE = re.compile(r'\s*len\(\s*([A-Za-z_]\w*)\s*(\[\s*0\s*\])?\s*\)\s*$')


def _jlen(v):
    if isinstance(v, str):
        return len(v.encode('utf-8'))
    return len(v)


def expand_args(params, args, spec):
    """spec.derived에 있는 매개변수(테스트 args에 없음)를 채워 선언 순서대로 모든 인자를 돌려준다.
    derived 식: len(이름), len(이름[0]), 정수 상수."""
    derived = (spec or {}).get('derived') or {}
    for k in derived:
        if k not in params:
            raise ValueError(f'spec.derived의 {k}는 매개변수가 아니에요(매개변수: {", ".join(map(str, params))}).')
    given = [p for p in params if p not in derived]
    if not isinstance(args, list) or len(args) != len(given):
        n = len(args) if isinstance(args, list) else '?'
        raise ValueError(f'테스트 인자 수가 맞지 않아요: {len(given)}개({", ".join(given)})가 필요한데 {n}개를 받았어요.')
    env = dict(zip(given, args))
    for p in params:
        if p in derived:
            env[p] = _derive(derived[p], env, p)
    return [env[p] for p in params]


def _derive(expr, env, pname):
    if isinstance(expr, int) and not isinstance(expr, bool):
        return expr
    s = str(expr).strip()
    if re.fullmatch(r'-?\d+', s):
        return int(s)
    m = _LEN_RE.match(s)
    if not m:
        raise ValueError(f"spec.derived['{pname}']에는 len(이름), len(이름[0]), 정수만 쓸 수 있어요: {expr!r}")
    name, sub = m.groups()
    if name not in env:
        raise ValueError(f"spec.derived['{pname}']: {name}은(는) 테스트 인자에 없어요.")
    v = env[name]
    if sub:
        if not isinstance(v, list) or not v:
            raise ValueError(f"spec.derived['{pname}']: len({name}[0])을 구할 수 없어요({name}이 비어 있거나 리스트가 아니에요).")
        v = v[0]
    if not isinstance(v, (list, str)):
        raise ValueError(f"spec.derived['{pname}']: {name}은(는) 리스트나 문자열이 아니에요.")
    return _jlen(v)


_LTOK = re.compile(r'\s*(?:(\d+)|([A-Za-z_]\w*)|(//|[-+*/%()\[\]]))')


def eval_len(expr, env):
    """spec.ret.len 같은 간단한 식(정수, 매개변수 이름, len(이름), len(이름[0]), + - * / % 괄호)을 계산한다."""
    if isinstance(expr, bool):
        raise ValueError(f'길이 식이 잘못됐어요: {expr!r}')
    if isinstance(expr, int):
        return expr
    s = str(expr)
    toks = []
    pos = 0
    while pos < len(s):
        m = _LTOK.match(s, pos)
        if not m or m.end() == pos:
            if s[pos:].strip() == '':
                break
            raise ValueError(f'길이 식을 이해하지 못했어요: {expr!r}')
        pos = m.end()
        if m.group(1):
            toks.append(('n', int(m.group(1))))
        elif m.group(2):
            toks.append(('id', m.group(2)))
        else:
            toks.append(('op', m.group(3)))
    i = [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else (None, None)

    def take(kind=None, val=None):
        t = peek()
        if t[0] is None or (kind and t[0] != kind) or (val is not None and t[1] != val):
            raise ValueError(f'길이 식을 이해하지 못했어요: {expr!r}')
        i[0] += 1
        return t

    def atom():
        k, v = peek()
        if k == 'n':
            take()
            return v
        if k == 'op' and v == '(':
            take()
            r = add()
            take('op', ')')
            return r
        if k == 'op' and v == '-':
            take()
            return -atom()
        if k == 'id':
            take()
            if v == 'len' and peek() == ('op', '('):
                take()
                nm = take('id')[1]
                sub = False
                if peek() == ('op', '['):
                    take()
                    take('n', 0)
                    take('op', ']')
                    sub = True
                take('op', ')')
                if nm not in env:
                    raise ValueError(f'길이 식의 {nm}은(는) 매개변수가 아니에요.')
                x = env[nm]
                if sub:
                    if not isinstance(x, list) or not x:
                        raise ValueError(f'len({nm}[0])을 구할 수 없어요.')
                    x = x[0]
                if not isinstance(x, (list, str)):
                    raise ValueError(f'len({nm}): 리스트나 문자열이 아니에요.')
                return _jlen(x)
            if v not in env:
                raise ValueError(f'길이 식의 {v}은(는) 매개변수가 아니에요.')
            x = env[v]
            if isinstance(x, bool) or not isinstance(x, int):
                raise ValueError(f'길이 식의 {v} 값이 정수가 아니에요.')
            return x
        raise ValueError(f'길이 식을 이해하지 못했어요: {expr!r}')

    def mul():
        r = atom()
        while peek()[0] == 'op' and peek()[1] in ('*', '/', '//', '%'):
            op = take()[1]
            b = atom()
            if op == '*':
                r *= b
            elif b == 0:
                raise ValueError('길이 식에서 0으로 나눴어요.')
            elif op == '%':
                r %= b
            else:
                r //= b
        return r

    def add():
        r = mul()
        while peek()[0] == 'op' and peek()[1] in ('+', '-'):
            op = take()[1]
            b = mul()
            r = r + b if op == '+' else r - b
        return r
    r = add()
    if i[0] != len(toks):
        raise ValueError(f'길이 식을 이해하지 못했어요: {expr!r}')
    if r < 0:
        raise ValueError(f'길이 식의 값이 음수예요: {expr!r} = {r}')
    return r
