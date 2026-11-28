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

/** 모의고사 한 문제의 결과(마지막 제출 기준). 학생 코드는 넣지 않는다 */
export interface MockResult {
  /** 마지막 제출의 테스트 통과율(0~100) */
  score: number;
  solved: boolean;
  tries: number;
  at: string;
}

/** 모의고사 한 회(m1~m3)의 응시 기록. round: '다시 풀기'마다 1씩 늘어남(높은 round가 이긴다) */
export interface MockState {
  round: number;
  startedAt: string;
  endedAt?: string;
  /** 키: 유형 t01~t10(Data 과정은 문항 q01~q20) */
  results: Record<string, MockResult>;
}

export interface CourseState {
  v: 1;
  probs: Record<string, ProbState>;
  mocks?: Record<string, MockState>;
  /** [심화]를 연 유형(t01~t10). 그 유형의 기본 5문제를 모두 푼 뒤 학생이 직접 연다 */
  advOpen?: string[];
  /** 유형 집중 풀이에서 잠긴 시각(마지막 초기화 이후). 키: 유형 t01~t20 */
  locks?: Record<string, string[]>;
  /** 유형 초기화 표시(한 유형에서 LOCK_LIMIT번 잠겨 그 유형 기록을 지운 시각·누적 횟수). 다른 기기의 예전 기록이 되살아나지 않게 */
  resets?: Record<string, { at: string; n: number }>;
}

/** 한 유형에서 이만큼 잠기면 그 유형의 풀이 기록을 초기화한다(선생님 요청 2026-11-28) */
export const LOCK_LIMIT = 3;

export const emptyState = (): CourseState => ({ v: 1, probs: {} });

export const emptyProb = (ver: number, now = new Date().toISOString()): ProbState => ({ ver, steps: [], stepsDone: false, solved: false, tries: 0, lastAt: now });

const uniq = (a: string[] = [], b: string[] = []) => [...new Set([...a, ...b])].sort();
/** 같은 시각이 겹치지 않게(앞 기록보다 1ms 뒤) */
const after = (now: string, prev?: string) => (prev && prev >= now ? new Date(Date.parse(prev) + 1).toISOString() : now);
/** 문제 id의 유형 키('pyb-t03-a' → 't03') */
export const typeOfId = (id: string) => id.split('-')[1] ?? '';
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

function mergeMock(a: MockState | undefined, b: MockState | undefined): MockState {
  if (!a) return b!;
  if (!b) return a;
  if (a.round !== b.round) return a.round > b.round ? a : b;
  const results: Record<string, MockResult> = {};
  for (const k of new Set([...Object.keys(a.results), ...Object.keys(b.results)])) {
    const x = a.results[k];
    const y = b.results[k];
    if (!x || !y) {
      results[k] = (x ?? y)!;
      continue;
    }
    const later = x.at >= y.at ? x : y;
    results[k] = { score: later.score, solved: x.solved || y.solved, tries: Math.max(x.tries, y.tries), at: later.at };
  }
  const out: MockState = { round: a.round, startedAt: minIso(a.startedAt, b.startedAt)!, results };
  const ended = minIso(a.endedAt, b.endedAt);
  if (ended) out.endedAt = ended;
  return out;
}

/** 두 기기의 기록 합치기: 무엇도 잃지 않는다(합집합·최댓값). 모의고사는 높은 round(다시 풀기)가 이긴다. */
export function mergeState(a: CourseState | null | undefined, b: CourseState | null | undefined): CourseState {
  const a0 = sanitize(a);
  const b0 = sanitize(b);
  // 유형 초기화: 더 최근 초기화를 모르는 쪽의 그 유형 기록은 버린다(초기화가 되살아나지 않게)
  const resets: NonNullable<CourseState['resets']> = {};
  for (const t of new Set([...Object.keys(a0.resets ?? {}), ...Object.keys(b0.resets ?? {})])) {
    const ra = a0.resets?.[t];
    const rb = b0.resets?.[t];
    resets[t] = { at: maxIso(ra?.at, rb?.at)!, n: Math.max(ra?.n ?? 0, rb?.n ?? 0) };
  }
  const sa = dropStaleTypes(a0, resets);
  const sb = dropStaleTypes(b0, resets);
  const probs: Record<string, ProbState> = {};
  for (const id of new Set([...Object.keys(sa.probs), ...Object.keys(sb.probs)])) probs[id] = mergeProb(sa.probs[id], sb.probs[id]);
  const out: CourseState = { v: 1, probs };
  const open = uniq(sa.advOpen, sb.advOpen);
  if (open.length) out.advOpen = open;
  const locks: Record<string, string[]> = {};
  for (const t of new Set([...Object.keys(sa.locks ?? {}), ...Object.keys(sb.locks ?? {})])) {
    const l = uniq(sa.locks?.[t], sb.locks?.[t]).filter((x) => !resets[t] || x > resets[t].at);
    if (l.length) locks[t] = l.slice(-50);
  }
  if (Object.keys(locks).length) out.locks = locks;
  if (Object.keys(resets).length) out.resets = resets;
  const ma = sa.mocks ?? {};
  const mb = sb.mocks ?? {};
  const keys = new Set([...Object.keys(ma), ...Object.keys(mb)]);
  if (keys.size) {
    out.mocks = {};
    for (const k of [...keys].sort()) out.mocks[k] = mergeMock(ma[k], mb[k]);
  }
  return out;
}

const PID = /^(pyb|pya|cb|ca|d2)-t\d{2}-([a-e]|adv[1-5])$/;
/** 모의고사 기록 키: 유형 t01~t10, Data 과정은 문항 q01~q30 */
const MKEY = /^(t(0[1-9]|10)|q(0[1-9]|[12]\d|30))$/;
const TKEY = /^t(0[1-9]|1\d|20)$/;
/**
 * 과정별로 이보다 낮은 문제 version 기록은 버린다. Data 2급은 시험 20문항 유형으로 다시 만들면서(2026-11-28)
 * 같은 id가 다른 문제를 가리키게 되어, 예전 판(version 1) 기록이 새 문제에 붙지 않게 한다.
 */
const MIN_VER: Record<string, number> = { d2: 2 };
/** [심화] 문제 id(…-adv1~adv5) */
export const isAdvId = (id: string) => /-adv[1-5]$/.test(id);
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
    if ((typeof p.ver === 'number' ? p.ver : 1) < (MIN_VER[id.split('-')[0]] ?? 1)) continue;
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
  const advOpen = (raw as { advOpen?: unknown }).advOpen;
  if (Array.isArray(advOpen)) {
    const open = [...new Set(advOpen.filter((t): t is string => typeof t === 'string' && TKEY.test(t)))].sort();
    if (open.length) out.advOpen = open;
  }
  const locks = (raw as { locks?: unknown }).locks;
  if (locks && typeof locks === 'object') {
    for (const [t, l] of Object.entries(locks as Record<string, unknown>)) {
      if (!TKEY.test(t) || !Array.isArray(l)) continue;
      const ok = [...new Set(l.filter((x): x is string => ISO(x) !== undefined))].sort().slice(-50);
      if (ok.length) (out.locks ??= {})[t] = ok;
    }
  }
  const resets = (raw as { resets?: unknown }).resets;
  if (resets && typeof resets === 'object') {
    for (const [t, z] of Object.entries(resets as Record<string, unknown>)) {
      if (!TKEY.test(t) || !z || typeof z !== 'object') continue;
      const at = ISO((z as { at?: unknown }).at);
      const n = (z as { n?: unknown }).n;
      if (at) (out.resets ??= {})[t] = { at, n: typeof n === 'number' && n >= 1 && n < 100000 ? Math.floor(n) : 1 };
    }
  }
  const mocks = (raw as { mocks?: unknown }).mocks;
  if (mocks && typeof mocks === 'object') {
    for (const [k, v] of Object.entries(mocks as Record<string, unknown>)) {
      if (!/^m[1-3]$/.test(k) || !v || typeof v !== 'object') continue;
      const m = v as Record<string, unknown>;
      const startedAt = ISO(m.startedAt);
      if (!startedAt) continue;
      const ms: MockState = { round: typeof m.round === 'number' && m.round >= 1 && m.round < 10000 ? Math.floor(m.round) : 1, startedAt, results: {} };
      const endedAt = ISO(m.endedAt);
      if (endedAt) ms.endedAt = endedAt;
      const res = m.results && typeof m.results === 'object' ? (m.results as Record<string, unknown>) : {};
      for (const [t, r] of Object.entries(res)) {
        if (!MKEY.test(t) || !r || typeof r !== 'object') continue;
        const x = r as Record<string, unknown>;
        ms.results[t] = {
          score: typeof x.score === 'number' && x.score >= 0 && x.score <= 100 ? Math.round(x.score) : 0,
          solved: x.solved === true,
          tries: typeof x.tries === 'number' && x.tries >= 0 ? Math.min(Math.floor(x.tries), 100000) : 0,
          at: ISO(x.at) ?? new Date(0).toISOString(),
        };
      }
      (out.mocks ??= {})[k] = ms;
    }
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

/** 문제 묶음 중 해결한 수 */
export const solvedCount = (state: CourseState, ids: string[]) => ids.filter((id) => state.probs[id]?.solved).length;

/**
 * [심화] 잠금 상태: locked(기본 5문제를 아직 다 못 풂) → ready(다 풀었고, 누르면 열림) → open(연 뒤).
 * bypass(선생님 미리 보기)면 언제나 open.
 */
export type AdvGate = 'locked' | 'ready' | 'open';
export function advGate(state: CourseState, tkey: string, basicIds: string[], bypass = false): AdvGate {
  if (bypass) return 'open';
  const done = basicIds.length > 0 && solvedCount(state, basicIds) === basicIds.length;
  if (!done) return 'locked';
  return state.advOpen?.includes(tkey) ? 'open' : 'ready';
}

/** 모의고사는 [기본] 문제를 모두 푼 뒤에 연다. 이미 시작한 회차의 기록은 계속 볼 수 있다. bypass(선생님 미리 보기)면 열림 */
export function mockGate(state: CourseState, basicIds: string[], mockKey: string, bypass = false): boolean {
  if (bypass || state.mocks?.[mockKey]) return true;
  return basicIds.length > 0 && solvedCount(state, basicIds) === basicIds.length;
}

/** 유형 잠김 횟수(마지막 초기화 이후) */
export const lockCount = (state: CourseState, tkey: string) => state.locks?.[tkey]?.length ?? 0;

/** 그 유형의 풀이 기록(기본·심화 문제, 심화 열림)과 잠김 횟수를 지우고 초기화 표시를 남긴다. 모의고사·다른 유형은 그대로 */
export function resetType(state: CourseState, tkey: string, now = new Date().toISOString()): CourseState {
  const probs = Object.fromEntries(Object.entries(state.probs).filter(([id]) => typeOfId(id) !== tkey));
  const out: CourseState = { ...state, probs };
  const open = (state.advOpen ?? []).filter((t) => t !== tkey);
  if (open.length) out.advOpen = open;
  else delete out.advOpen;
  const locks = { ...(state.locks ?? {}) };
  delete locks[tkey];
  if (Object.keys(locks).length) out.locks = locks;
  else delete out.locks;
  const prev = state.resets?.[tkey];
  out.resets = { ...(state.resets ?? {}), [tkey]: { at: after(now, prev?.at), n: (prev?.n ?? 0) + 1 } };
  return out;
}

/** 잠김 1회 기록. LOCK_LIMIT번째면 그 유형을 초기화한다 */
export function addLock(state: CourseState, tkey: string, now = new Date().toISOString()): { state: CourseState; count: number; reset: boolean } {
  const cur = state.locks?.[tkey] ?? [];
  const list = [...cur, after(now, cur.at(-1))];
  if (list.length >= LOCK_LIMIT) return { state: resetType(state, tkey, now), count: list.length, reset: true };
  return { state: { ...state, locks: { ...(state.locks ?? {}), [tkey]: list } }, count: list.length, reset: false };
}

/** 병합 전: 상대가 아는 더 최근 초기화를 모르는 쪽이면 그 유형 기록을 버린다 */
function dropStaleTypes(x: CourseState, latest: NonNullable<CourseState['resets']>): CourseState {
  let out = x;
  for (const [t, r] of Object.entries(latest)) {
    if ((x.resets?.[t]?.at ?? '') < r.at) {
      const keepResets = out.resets;
      out = resetType(out, t, r.at);
      // 표시는 병합에서 정한다(여기서 횟수를 올리지 않음)
      if (keepResets) out.resets = keepResets;
      else delete out.resets;
    }
  }
  return out;
}
