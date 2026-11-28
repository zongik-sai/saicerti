import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { TypeFile } from '../../src/content/types';
import { cellOk, cRepr, normCell, pyRepr } from '../../src/lib/pyrepr';
import { cleanSvg } from '../../src/components/Figure';
import { countBlanks, fillBlanks } from '../../src/components/BlankCode';
import { STORAGE_PREFIX } from '../../src/lib/storage';
import { AUTH_STORAGE_KEY } from '../../src/features/auth/supabase';

const root = join(__dirname, '../../src/content');
const COURSES = ['pyb', 'pya', 'cb'];
const files: TypeFile[] = [];
for (const c of COURSES) for (const f of readdirSync(join(root, c)).filter((x) => x.endsWith('.json')).sort()) files.push(JSON.parse(readFileSync(join(root, c, f), 'utf8')));
/** [심화] 1~5(src/content/<과정>/adv/tNN.json) */
const advFiles: TypeFile[] = [];
for (const c of COURSES) {
  const d = join(root, c, 'adv');
  if (existsSync(d)) for (const f of readdirSync(d).filter((x) => x.endsWith('.json')).sort()) advFiles.push(JSON.parse(readFileSync(join(d, f), 'utf8')));
}
const every = [...files, ...advFiles];

describe('문제 데이터(자세한 검수는 tools/validate.py)', () => {
  it('과정마다 10유형 × 5문제, id는 고유', () => {
    for (const c of COURSES) {
      const fs = files.filter((f) => f.course === c);
      expect(fs.map((f) => f.type)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      for (const f of fs) expect(f.problems).toHaveLength(5);
    }
    const ids = files.flatMap((f) => f.problems.map((p) => p.id));
    expect(new Set(ids).size).toBe(50 * COURSES.length);
  });

  it('[심화] 과정마다 10유형 × 5문제(adv1~adv5), 기본과 같은 형식·이름, 중간 점검 6~9단계', () => {
    for (const c of COURSES) {
      const fs = advFiles.filter((f) => f.course === c);
      expect(fs.map((f) => f.type), c).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      for (const f of fs) {
        const base = files.find((b) => b.course === c && b.type === f.type)!;
        expect(f.kind, `${c} t${f.type}`).toBe(base.kind);
        expect(f.typeTitle, `${c} t${f.type}`).toBe(base.typeTitle);
        expect(f.problems.map((p) => p.id)).toEqual([1, 2, 3, 4, 5].map((n) => `${c}-t${String(f.type).padStart(2, '0')}-adv${n}`));
        for (const p of f.problems) {
          expect(p.steps.length, p.id).toBeGreaterThanOrEqual(6);
          expect(p.steps.length, p.id).toBeLessThanOrEqual(9);
        }
      }
    }
    const ids = every.flatMap((f) => f.problems.map((p) => p.id));
    expect(new Set(ids).size).toBe(100 * COURSES.length);
  });

  it('표·단답 정답은 화면 채점 규칙(cellOk)으로 자기 자신과 맞는다', () => {
    for (const f of every)
      for (const p of f.problems)
        for (const s of p.steps) {
          if (s.kind === 'table') for (const c of s.rows.flat()) if (typeof c === 'object') expect(cellOk(c.a, c.a, c.alts), `${p.id} ${s.id}`).toBe(true);
          if (s.kind === 'short') expect(cellOk(s.a, s.a, s.alts)).toBe(true);
          if (s.kind === 'mcq') expect(s.answer).toBeLessThan(s.options.length);
        }
  });

  it('빈칸 정답을 넣으면 정답 코드가 된다(화면 조립 함수)', () => {
    for (const f of every.filter((x) => x.kind === 'blank'))
      for (const p of f.problems) {
        expect(countBlanks(p.code)).toBe(p.blanks!.length);
        const filled = fillBlanks(p.code, p.blanks!.map((b) => b.answer));
        const norm = (s: string) => s.replace(/\s+$/, '').split('\n').map((l) => l.replace(/\s+$/, '')).join('\n');
        expect(norm(filled), p.id).toBe(norm(p.solution));
      }
  });

  it('중간 점검 질문·보기·해설에 코드 빈칸 번호(⟦n⟧)가 없다(질문만 읽고 풀 수 있게)', () => {
    for (const f of every)
      for (const p of f.problems)
        for (const st of p.steps) {
          const shown = JSON.stringify(st, (k, v: unknown) => (k === 'check' ? undefined : v));
          expect(shown, `${p.id} ${st.id}`).not.toMatch(/⟦\d+⟧/);
        }
  });

  it('C 과정 파일은 lang "c", 정답 코드에 main이 없다(채점기가 함수를 직접 부름)', () => {
    for (const f of every.filter((x) => x.course === 'cb')) {
      expect(f.lang, `${f.course} t${f.type}`).toBe('c');
      for (const p of f.problems) {
        expect(p.solution, p.id).not.toMatch(/\bmain\s*\(/);
      }
    }
  });
});

describe('그림(figures)', () => {
  const texts = (p: TypeFile['problems'][number]) => [p.statement, p.explain ?? '', ...p.steps.flatMap((s) => [s.kind === 'table' ? s.prompt : s.q, s.explain])].join('\n');
  it('글 속 {{fig:ID}}는 그 문제의 그림을 가리키고, 그림은 모두 쓰이며 alt가 있다', () => {
    for (const f of every)
      for (const p of f.problems) {
        const used = [...texts(p).matchAll(/\{\{fig:([\w-]+)\}\}/g)].map((m) => m[1]);
        const ids = (p.figures ?? []).map((x) => x.id);
        for (const u of used) expect(ids, `${p.id} ${u}`).toContain(u);
        for (const id of ids) expect(used, `${p.id} ${id}`).toContain(id);
        for (const fig of p.figures ?? []) expect(fig.alt.length, `${p.id} ${fig.id}`).toBeGreaterThan(10);
      }
  });
  it('SVG 정리: 스크립트·이벤트·링크를 지운다', () => {
    const dirty = `<svg><script>alert(1)</script><a href="javascript:x"><text onclick="x()">t</text></a></svg>`;
    const clean = cleanSvg(dirty);
    expect(clean).not.toMatch(/script|onclick|href|javascript/i);
    expect(clean).toContain('<text>t</text>');
  });
});

describe('표시·채점 도우미', () => {
  it('파이썬 표기', () => {
    expect(pyRepr([1, 'a', true, null, [2.5]])).toBe("[1, 'a', True, None, [2.5]]");
    expect(pyRepr("it's")).toBe('"it\'s"');
  });
  it('C 표기', () => {
    expect(cRepr([1, 2, 3])).toBe('{1, 2, 3}');
    expect(cRepr('abc')).toBe('"abc"');
    expect(cRepr(true)).toBe('true');
  });
  it('표 칸 비교: 공백 무시, 따옴표 같게', () => {
    expect(normCell(' [ "a" , 1 ] ')).toBe("['a',1]");
    expect(cellOk('True', 'True')).toBe(true);
    expect(cellOk('', 'True')).toBe(false);
    expect(cellOk('27', '0', ['27'])).toBe(true);
  });
  it('배움 숲(saiedu)과 같은 사이트에서 저장 키가 겹치지 않는다', () => {
    expect(STORAGE_PREFIX).toBe('saicerti:v1:');
    expect(STORAGE_PREFIX.startsWith('sqlforest')).toBe(false);
    expect(AUTH_STORAGE_KEY).toBe('saicerti-auth');
  });
});

describe('객관식 보기 섞기', () => {
  it('정답이 한 자리(①)에 몰리지 않는다', async () => {
    const { optionOrder, refersToPosition } = await import('../../src/components/Steps');
    const pos: number[] = [0, 0, 0, 0, 0];
    for (const f of every)
      for (const p of f.problems)
        for (const s of p.steps)
          if (s.kind === 'mcq') {
            const order = optionOrder(s.options, `${p.id}:${s.id}`, refersToPosition(s.q + s.explain));
            expect([...order].sort()).toEqual(s.options.map((_, i) => i));
            pos[order.indexOf(s.answer)]++;
          }
    const total = pos.reduce((a, b) => a + b, 0);
    expect(pos[0] / total).toBeLessThan(0.45);
  });
});

describe('모의고사 데이터', () => {
  const mocks: TypeFile[] = [];
  for (const c of COURSES) for (const f of readdirSync(join(root, c, 'mock')).filter((x) => x.endsWith('.json')).sort()) mocks.push(JSON.parse(readFileSync(join(root, c, 'mock', f), 'utf8')));
  it('과정마다 10유형 × 3회, 연습 문제와 같은 형식(kind)', () => {
    for (const c of COURSES) {
      const ms = mocks.filter((m) => m.course === c);
      expect(ms.map((m) => m.type)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      for (const m of ms) {
        expect(m.problems.map((p) => p.id)).toEqual([1, 2, 3].map((n) => `${c}-m${n}-t${String(m.type).padStart(2, '0')}`));
        expect(m.kind).toBe(files.find((f) => f.course === c && f.type === m.type)!.kind);
      }
    }
  });
  it('같은 유형의 1·2·3회는 코드·정답이 같고 예시는 서로 다르다', () => {
    for (const m of mocks) {
      const [a, b, c] = m.problems;
      expect(b.code, a.id).toBe(a.code);
      expect(c.code, a.id).toBe(a.code);
      expect(b.solution, a.id).toBe(a.solution);
      expect(c.solution, a.id).toBe(a.solution);
      const ex = m.problems.map((p) => JSON.stringify(p.examples.map((e) => e.args)));
      expect(new Set(ex).size, a.id).toBe(3);
    }
  });
});

describe('Data 분석 2급(d2)', () => {
  const dir = join(root, 'd2');
  const has = existsSync(dir);
  const load = (d: string) => (existsSync(d) ? readdirSync(d).filter((x) => /^t\d\d\.json$/.test(x)).sort().map((f) => JSON.parse(readFileSync(join(d, f), 'utf8')) as TypeFile) : []);
  const base = has ? load(dir) : [];
  const adv = has ? load(join(dir, 'adv')) : [];
  const catalog = JSON.parse(readFileSync(join(__dirname, '../../src/datasets/d2.json'), 'utf8')) as Record<string, { rows: number[] }>;
  const all = [...base, ...adv];
  const kindOf = (f: TypeFile, p: TypeFile['problems'][number]) => p.kind ?? f.kind;

  it('10유형 × [기본] 5 + [심화] 5, 심화는 기본과 같은 형식·이름', () => {
    expect(base.map((f) => f.type)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(adv.map((f) => f.type)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    for (const f of base) expect(f.problems.map((p) => p.id)).toEqual('abcde'.split('').map((l) => `d2-t${String(f.type).padStart(2, '0')}-${l}`));
    for (const f of adv) {
      const b = base.find((x) => x.type === f.type)!;
      expect(f.kind).toBe(b.kind);
      expect(f.typeTitle).toBe(b.typeTitle);
      expect(f.problems.map((p) => p.id)).toEqual([1, 2, 3, 4, 5].map((n) => `d2-t${String(f.type).padStart(2, '0')}-adv${n}`));
      for (const p of f.problems) expect(p.steps.length, p.id).toBeGreaterThanOrEqual(6);
    }
    expect(new Set(all.flatMap((f) => f.problems.map((p) => p.id))).size).toBe(100);
  });

  it('객관식은 보기 4개·정답·보기별 풀이, 코드 문제는 데이터 파일·예시(변형 0)·숨은 데이터(변형 1·2)', () => {
    for (const f of all)
      for (const p of f.problems) {
        const k = kindOf(f, p);
        if (k === 'choice') {
          expect(p.choice!.options, p.id).toHaveLength(4);
          expect(p.choice!.why, p.id).toHaveLength(4);
          expect(p.choice!.answer).toBeGreaterThanOrEqual(0);
          expect(p.choice!.answer).toBeLessThan(4);
        } else {
          for (const file of p.data!.files) expect(catalog[file], `${p.id} ${file}`).toBeDefined();
          expect(p.examples.map((e) => e.data), p.id).toEqual([0]);
          expect(p.tests.map((e) => e.data), p.id).toEqual(p.tests.map((_, i) => i + 1));
          for (const c of [...p.examples, ...p.tests]) expect(c.expected, p.id).toBeDefined();
          if (k === 'blank') {
            const filled = fillBlanks(p.code, p.blanks!.map((b) => b.answer));
            const norm = (s: string) => s.replace(/\s+$/, '').split('\n').map((l) => l.replace(/\s+$/, '')).join('\n');
            expect(norm(filled), p.id).toBe(norm(p.solution));
          }
        }
        for (const s of p.steps) {
          expect(JSON.stringify(s, (key, v: unknown) => (key === 'check' ? undefined : v)), `${p.id} ${s.id}`).not.toMatch(/⟦\d+⟧/);
          if (s.kind === 'table') for (const c of s.rows.flat()) if (typeof c === 'object') expect(cellOk(c.a, c.a, c.alts), `${p.id} ${s.id}`).toBe(true);
        }
      }
  });

  it('글 속 {{fig:ID}}는 그 문제의 그림을 가리키고, 그림은 모두 쓰이며 alt가 있다', () => {
    for (const f of all)
      for (const p of f.problems) {
        const text = [p.statement, p.explain, ...(p.choice?.options ?? []), ...p.steps.flatMap((s) => [s.kind === 'table' ? s.prompt : s.q, s.explain])].join('\n');
        const used = [...text.matchAll(/\{\{fig:([\w-]+)\}\}/g)].map((x) => x[1]);
        const ids = (p.figures ?? []).map((x) => x.id);
        for (const u of used) expect(ids, `${p.id} ${u}`).toContain(u);
        for (const id of ids) expect(used, `${p.id} ${id}`).toContain(id);
        for (const fig of p.figures ?? []) expect(fig.alt.length, `${p.id} ${fig.id}`).toBeGreaterThan(10);
      }
  });

  it('객관식 정답이 한 자리에 몰리지 않는다', () => {
    const pos = [0, 0, 0, 0];
    for (const f of all) for (const p of f.problems) if (p.choice) pos[p.choice.answer]++;
    const total = pos.reduce((a, b) => a + b, 0);
    for (const n of pos) expect(n / total).toBeLessThan(0.45);
  });

  it('모의고사 1회: 시험지처럼 20문항(객관식 이론 + 코드), 중간 점검 없음, 유형이 있음', () => {
    const m = JSON.parse(readFileSync(join(dir, 'mock', 'm1.json'), 'utf8')) as { course: string; mock: number; items: { type: number; kind: string; problem: TypeFile['problems'][number] }[] };
    expect(m.course).toBe('d2');
    expect(m.items).toHaveLength(20);
    m.items.forEach((it, i) => {
      expect(it.problem.id).toBe(`d2-m1-q${String(i + 1).padStart(2, '0')}`);
      expect(it.problem.steps).toEqual([]);
      expect(base.map((f) => f.type)).toContain(it.type);
    });
    expect(m.items.filter((it) => it.kind === 'choice').length).toBe(12);
  });
});
