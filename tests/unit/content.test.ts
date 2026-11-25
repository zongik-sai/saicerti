import { readdirSync, readFileSync } from 'node:fs';
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

  it('표·단답 정답은 화면 채점 규칙(cellOk)으로 자기 자신과 맞는다', () => {
    for (const f of files)
      for (const p of f.problems)
        for (const s of p.steps) {
          if (s.kind === 'table') for (const c of s.rows.flat()) if (typeof c === 'object') expect(cellOk(c.a, c.a, c.alts), `${p.id} ${s.id}`).toBe(true);
          if (s.kind === 'short') expect(cellOk(s.a, s.a, s.alts)).toBe(true);
          if (s.kind === 'mcq') expect(s.answer).toBeLessThan(s.options.length);
        }
  });

  it('빈칸 정답을 넣으면 정답 코드가 된다(화면 조립 함수)', () => {
    for (const f of files.filter((x) => x.kind === 'blank'))
      for (const p of f.problems) {
        expect(countBlanks(p.code)).toBe(p.blanks!.length);
        const filled = fillBlanks(p.code, p.blanks!.map((b) => b.answer));
        const norm = (s: string) => s.replace(/\s+$/, '').split('\n').map((l) => l.replace(/\s+$/, '')).join('\n');
        expect(norm(filled), p.id).toBe(norm(p.solution));
      }
  });

  it('C 과정 파일은 lang "c", 정답 코드에 main이 없다(채점기가 함수를 직접 부름)', () => {
    for (const f of files.filter((x) => x.course === 'cb')) {
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
    for (const f of files)
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
    for (const f of files)
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
