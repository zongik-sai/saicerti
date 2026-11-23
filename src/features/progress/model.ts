/**
 * 과정 진도 기록(순수 함수, 테스트 대상). 서버 course_progress.state(JSON 문서)와 같은 모양.
 * 학생 코드는 넣지 않는다(코드 초안은 이 기기에만: drafts.ts).
 */
export interface ProbState {
  /** 문제 version(내용이 바뀌면 중간 점검 기록을 다시 시작할지 판단) */
  ver: number;
  /** 맞힌 중간 점검 단계 id */
  steps: string[];
  /** 중간 점검을 모두 마침 → 코드 풀이 열림 */
  stepsDone: boolean;
  /** 숨은 테스트까지 모두 통과 */
  solved: boolean;
  /** 채점(제출) 횟수 */
  tries: number;
  /** 정답을 본 중간 점검 단계 id(세 번 틀린 뒤 '정답 보기') */
  revealed?: string[];
  /** 정답 코드를 본 시각(풀기 전에 봤으면 기록) */
  sawAnswerAt?: string;
  solvedAt?: string;
  lastAt: string;
}

export interface CourseState {
  v: 1;
  probs: Record<string, ProbState>;
}

export const emptyState = (): CourseState => ({ v: 1, probs: {} });

export const emptyProb = (ver: number, now = new Date().toISOString()): ProbState => ({ ver, steps: [], stepsDone: false, solved: false, tries: 0, lastAt: now });

const uniq = (a: string[] = [], b: string[] = []) => [...new Set([...a, ...b])].sort();
const minIso = (a?: string, b?: string) => (!a ? b : !b ? a : a < b ? a : b);
const maxIso = (a?: string, b?: string) => (!a ? b : !b ? a : a > b ? a : b);

function mergeProb(a: ProbState | undefined, b: ProbState | undefined): ProbState {
  if (!a) return b!;
  if (!b) return a;
  // 문제 version이 다르면 새 version 쪽의 중간 점검 기록만 쓴다(풀이 기록은 합친다)
  const ver = Math.max(a.ver || 1, b.ver || 1);
  const sa = (a.ver || 1) === ver ? a : null;
  const sb = (b.ver || 1) === ver ? b : null;
  const out: ProbState = {
    ver,
    steps: uniq(sa?.steps, sb?.steps),
    stepsDone: !!(sa?.stepsDone || sb?.stepsDone),
    solved: a.solved || b.solved,
    tries: Math.max(a.tries || 0, b.tries || 0),
    lastAt: maxIso(a.lastAt, b.lastAt) ?? new Date(0).toISOString(),
  };
  const rv = uniq(sa?.revealed, sb?.revealed);
  if (rv.length) out.revealed = rv;
  const solvedAt = minIso(a.solvedAt, b.solvedAt);
  if (solvedAt) out.solvedAt = solvedAt;
  const saw = minIso(a.sawAnswerAt, b.sawAnswerAt);
  if (saw) out.sawAnswerAt = saw;
  return out;
}

/** 두 기기의 기록 합치기: 무엇도 잃지 않는다(합집합·최댓값). */
export function mergeState(a: CourseState | null | undefined, b: CourseState | null | undefined): CourseState {
  const pa = sanitize(a).probs;
  const pb = sanitize(b).probs;
  const probs: Record<string, ProbState> = {};
  for (const id of new Set([...Object.keys(pa), ...Object.keys(pb)])) probs[id] = mergeProb(pa[id], pb[id]);
  return { v: 1, probs };
}

const PID = /^(pyb|pya)-t\d{2}-[a-e]$/;
const SID = /^s\d{1,2}$/;
const ISO = (v: unknown): string | undefined => (typeof v === 'string' && v.length <= 40 && !Number.isNaN(Date.parse(v)) ? v : undefined);

/** 서버·저장소에서 읽은 값을 믿지 않고 모양을 검사해 정리한다. */
export function sanitize(raw: unknown): CourseState {
  const out = emptyState();
  if (!raw || typeof raw !== 'object') return out;
  const probs = (raw as { probs?: unknown }).probs;
  if (!probs || typeof probs !== 'object') return out;
  for (const [id, v] of Object.entries(probs as Record<string, unknown>)) {
    if (!PID.test(id) || !v || typeof v !== 'object') continue;
    const p = v as Record<string, unknown>;
    const steps = Array.isArray(p.steps) ? p.steps.filter((s): s is string => typeof s === 'string' && SID.test(s)).slice(0, 12) : [];
    const ps: ProbState = {
      ver: typeof p.ver === 'number' && p.ver >= 1 && p.ver < 1000 ? Math.floor(p.ver) : 1,
      steps,
      stepsDone: p.stepsDone === true,
      solved: p.solved === true,
      tries: typeof p.tries === 'number' && p.tries >= 0 ? Math.min(Math.floor(p.tries), 100000) : 0,
      lastAt: ISO(p.lastAt) ?? new Date(0).toISOString(),
    };
    const rv = Array.isArray(p.revealed) ? p.revealed.filter((s): s is string => typeof s === 'string' && SID.test(s)).slice(0, 12) : [];
    if (rv.length) ps.revealed = rv;
    const sa = ISO(p.solvedAt);
    if (sa) ps.solvedAt = sa;
    const saw = ISO(p.sawAnswerAt);
    if (saw) ps.sawAnswerAt = saw;
    out.probs[id] = ps;
  }
  return out;
}

export const sameState = (a: CourseState, b: CourseState) => JSON.stringify(sanitize(a)) === JSON.stringify(sanitize(b));

export interface Tally {
  solved: number;
  stepsDone: number;
  started: number;
}
export function tally(state: CourseState, ids: string[]): Tally {
  let solved = 0;
  let stepsDone = 0;
  let started = 0;
  for (const id of ids) {
    const p = state.probs[id];
    if (!p) continue;
    started++;
    if (p.stepsDone) stepsDone++;
    if (p.solved) solved++;
  }
  return { solved, stepsDone, started };
}
