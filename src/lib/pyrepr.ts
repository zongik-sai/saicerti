import type { Json } from '../content/types';

/** JSON 값을 파이썬 표기로(예시 표·결과 표시용): None/True/False, 문자열은 작은따옴표. */
export function pyRepr(v: Json): string {
  if (v === null) return 'None';
  if (v === true) return 'True';
  if (v === false) return 'False';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : String(v);
  if (typeof v === 'string') {
    const q = v.includes("'") && !v.includes('"') ? '"' : "'";
    const body = v.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/\t/g, '\\t');
    return q + (q === "'" ? body.replace(/'/g, "\\'") : body) + q;
  }
  if (Array.isArray(v)) return '[' + v.map(pyRepr).join(', ') + ']';
  return '{' + Object.entries(v).map(([k, x]) => `${pyRepr(k)}: ${pyRepr(x)}`).join(', ') + '}';
}

/** JSON 값을 C 표기로(C 문제 예시 표): 배열 {1, 2}, 문자열 "abc", true/false, NULL */
export function cRepr(v: Json): string {
  if (v === null) return 'NULL';
  if (v === true) return 'true';
  if (v === false) return 'false';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string') return '"' + v.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n') + '"';
  if (Array.isArray(v)) return '{' + v.map(cRepr).join(', ') + '}';
  return '{' + Object.values(v).map(cRepr).join(', ') + '}';
}

export function reprFor(lang: 'python' | 'c', v: Json): string {
  return lang === 'c' ? cRepr(v) : pyRepr(v);
}

export function reprPretty(lang: 'python' | 'c', v: Json): string {
  const flat = reprFor(lang, v);
  if (flat.length <= 60 || !Array.isArray(v) || !v.every((x) => Array.isArray(x))) return flat;
  const [o, c] = lang === 'c' ? ['{', '}'] : ['[', ']'];
  return o + v.map((row) => reprFor(lang, row)).join(',\n ') + c;
}

/** 2차원 리스트처럼 긴 값은 행마다 줄바꿈 */
export function pyReprPretty(v: Json): string {
  const flat = pyRepr(v);
  if (flat.length <= 60 || !Array.isArray(v) || !v.every((x) => Array.isArray(x))) return flat;
  return '[' + v.map((row) => pyRepr(row)).join(',\n ') + ']';
}

/** 표 칸 정답 비교: 공백 무시, 큰따옴표=작은따옴표(검수 도구 norm_cell과 같은 규칙) */
export const normCell = (s: string) => s.replace(/\s+/g, '').replace(/"/g, "'");

export function cellOk(input: string, a: string, alts: string[] = []): boolean {
  const n = normCell(input);
  if (!n) return false;
  return [a, ...alts].some((x) => normCell(x) === n);
}
