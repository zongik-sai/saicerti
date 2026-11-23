import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { TypeFile } from '../../src/content/types';
import { cellOk, normCell, pyRepr } from '../../src/lib/pyrepr';
import { countBlanks, fillBlanks } from '../../src/components/BlankCode';
import { STORAGE_PREFIX } from '../../src/lib/storage';
import { AUTH_STORAGE_KEY } from '../../src/features/auth/supabase';

const root = join(__dirname, '../../src/content');
const files: TypeFile[] = [];
for (const c of ['pyb', 'pya']) for (const f of readdirSync(join(root, c)).filter((x) => x.endsWith('.json')).sort()) files.push(JSON.parse(readFileSync(join(root, c, f), 'utf8')));

describe('문제 데이터(자세한 검수는 tools/validate.py)', () => {
  it('과정마다 10유형 × 5문제, id는 고유', () => {
    for (const c of ['pyb', 'pya']) {
      const fs = files.filter((f) => f.course === c);
      expect(fs.map((f) => f.type)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
      for (const f of fs) expect(f.problems).toHaveLength(5);
    }
    const ids = files.flatMap((f) => f.problems.map((p) => p.id));
    expect(new Set(ids).size).toBe(100);
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
});

describe('표시·채점 도우미', () => {
  it('파이썬 표기', () => {
    expect(pyRepr([1, 'a', true, null, [2.5]])).toBe("[1, 'a', True, None, [2.5]]");
    expect(pyRepr("it's")).toBe('"it\'s"');
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
