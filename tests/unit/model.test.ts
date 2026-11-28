import { describe, expect, it } from 'vitest';
import { addLock, advGate, emptyProb, isAdvId, LOCK_LIMIT, lockCount, mergeState, mockGate, resetType, sanitize, tally, type CourseState, type ProbState } from '../../src/features/progress/model';
import { classifyLeave, focusReducer, initialFocus, lockNotice } from '../../src/features/focus/focusMachine';

const t = (s: string) => `2026-11-23T0${s}:00:00.000Z`;

describe('진도 합치기', () => {
  it('두 기기 기록을 잃지 않고 합친다', () => {
    const a: CourseState = { v: 1, probs: { 'pyb-t01-a': { ...emptyProb(1, t('1')), steps: ['s1'], tries: 2 } } };
    const b: CourseState = {
      v: 1,
      probs: {
        'pyb-t01-a': { ...emptyProb(1, t('2')), steps: ['s2'], stepsDone: true, solved: true, tries: 1, solvedAt: t('2') },
        'pya-t10-e': { ...emptyProb(1, t('3')) },
      },
    };
    const m = mergeState(a, b);
    expect(m.probs['pyb-t01-a']).toMatchObject({ steps: ['s1', 's2'], stepsDone: true, solved: true, tries: 2, solvedAt: t('2'), lastAt: t('2') });
    expect(Object.keys(m.probs)).toHaveLength(2);
    expect(mergeState(b, a)).toEqual(m);
  });

  it('문제 version이 바뀌면 옛 중간 점검 기록은 버리고 해결 기록은 남긴다', () => {
    const old: CourseState = { v: 1, probs: { 'pyb-t02-b': { ...emptyProb(1, t('1')), steps: ['s1', 's2'], stepsDone: true, solved: true } } };
    const neu: CourseState = { v: 1, probs: { 'pyb-t02-b': { ...emptyProb(2, t('2')), steps: ['s1'] } } };
    const m = mergeState(old, neu).probs['pyb-t02-b'];
    expect(m.ver).toBe(2);
    expect(m.steps).toEqual(['s1']);
    expect(m.stepsDone).toBe(false);
    expect(m.solved).toBe(true);
  });

  it('믿을 수 없는 값은 정리한다', () => {
    const s = sanitize({ probs: { 'pyb-t01-a': { steps: ['s1', 'x', 3], solved: 'yes', tries: -1, ver: 'a' }, '../evil': {}, 'pyb-t99-z': {} } });
    expect(Object.keys(s.probs)).toEqual(['pyb-t01-a']);
    expect(s.probs['pyb-t01-a']).toMatchObject({ steps: ['s1'], solved: false, tries: 0, ver: 1 });
    expect(sanitize(null)).toEqual({ v: 1, probs: {} });
  });

  it('해결·중간 점검 수를 센다', () => {
    const s: CourseState = { v: 1, probs: { 'pyb-t01-a': { ...emptyProb(1), stepsDone: true, solved: true }, 'pyb-t01-b': { ...emptyProb(1), stepsDone: true } } };
    expect(tally(s, ['pyb-t01-a', 'pyb-t01-b', 'pyb-t01-c'])).toEqual({ solved: 1, stepsDone: 2, started: 2 });
  });
});

describe('모의고사 기록 합치기', () => {
  const r = (score: number, solved: boolean, tries: number, at: string) => ({ score, solved, tries, at });
  it('같은 회차(round)는 문항별로 합치고, 마지막 제출 점수를 쓴다', () => {
    const a: CourseState = { v: 1, probs: {}, mocks: { m1: { round: 1, startedAt: t('1'), results: { t01: r(50, false, 1, t('2')) } } } };
    const b: CourseState = { v: 1, probs: {}, mocks: { m1: { round: 1, startedAt: t('2'), endedAt: t('5'), results: { t01: r(100, true, 2, t('3')), t02: r(0, false, 1, t('4')) } } } };
    const m = mergeState(a, b).mocks!.m1;
    expect(m.startedAt).toBe(t('1'));
    expect(m.endedAt).toBe(t('5'));
    expect(m.results.t01).toEqual(r(100, true, 2, t('3')));
    expect(Object.keys(m.results)).toEqual(['t01', 't02']);
  });
  it('다시 풀기(round가 큰 쪽)가 이긴다', () => {
    const old: CourseState = { v: 1, probs: {}, mocks: { m2: { round: 1, startedAt: t('1'), endedAt: t('2'), results: { t01: r(100, true, 1, t('2')) } } } };
    const neu: CourseState = { v: 1, probs: {}, mocks: { m2: { round: 2, startedAt: t('3'), results: {} } } };
    expect(mergeState(old, neu).mocks!.m2).toEqual({ round: 2, startedAt: t('3'), results: {} });
    expect(mergeState(neu, old).mocks!.m2.round).toBe(2);
  });
  it('모의고사 기록 모양 검사', () => {
    const s = sanitize({ probs: {}, mocks: { m1: { round: 1, startedAt: t('1'), results: { t01: { score: 250, solved: 'y', tries: 3, at: t('2') }, t11: {} } }, m9: {}, m2: { results: {} } } });
    expect(Object.keys(s.mocks!)).toEqual(['m1']);
    expect(s.mocks!.m1.results).toEqual({ t01: { score: 0, solved: false, tries: 3, at: t('2') } });
  });
});

describe('[심화]·모의고사 잠금(선생님 요청 2026-11-27)', () => {
  const basic = ['a', 'b', 'c', 'd', 'e'].map((x) => `pyb-t01-${x}`);
  const solved = (ids: string[]): CourseState => ({ v: 1, probs: Object.fromEntries(ids.map((id) => [id, { ...emptyProb(1), solved: true }])) });
  it('심화 id를 알아보고, 기록 정리에서 남긴다', () => {
    expect(isAdvId('pyb-t01-adv3')).toBe(true);
    expect(isAdvId('pyb-t01-a')).toBe(false);
    const s = sanitize({ probs: { 'pyb-t01-adv1': { solved: true }, 'pyb-t01-adv6': {}, 'cb-t10-adv5': {} }, advOpen: ['t01', 't01', 't21', 3, 't10'] });
    expect(Object.keys(s.probs).sort()).toEqual(['cb-t10-adv5', 'pyb-t01-adv1']);
    expect(s.advOpen).toEqual(['t01', 't10']);
  });
  it('연 유형(advOpen)은 두 기기 기록을 합친다', () => {
    const m = mergeState({ v: 1, probs: {}, advOpen: ['t02'] }, { v: 1, probs: {}, advOpen: ['t01'] });
    expect(m.advOpen).toEqual(['t01', 't02']);
    expect(mergeState({ v: 1, probs: {} }, { v: 1, probs: {} }).advOpen).toBeUndefined();
  });
  it('기본 5문제를 다 풀어야 열 수 있고(ready), 연 뒤에 들어간다(open). 선생님 미리 보기는 늘 open', () => {
    expect(advGate(solved(basic.slice(0, 4)), 't01', basic)).toBe('locked');
    expect(advGate(solved(basic), 't01', basic)).toBe('ready');
    expect(advGate({ ...solved(basic), advOpen: ['t01'] }, 't01', basic)).toBe('open');
    expect(advGate({ ...solved(basic.slice(0, 4)), advOpen: ['t01'] }, 't01', basic)).toBe('locked');
    expect(advGate({ v: 1, probs: {} }, 't01', basic, true)).toBe('open');
  });
  it('모의고사는 기본 문제를 모두 풀어야 열리고, 이미 시작한 회차 기록은 볼 수 있다', () => {
    expect(mockGate(solved(basic.slice(1)), basic, 'm1')).toBe(false);
    expect(mockGate(solved(basic), basic, 'm1')).toBe(true);
    expect(mockGate({ v: 1, probs: {}, mocks: { m2: { round: 1, startedAt: t('1'), results: {} } } }, basic, 'm2')).toBe(true);
    expect(mockGate({ v: 1, probs: {} }, basic, 'm1', true)).toBe(true);
  });
});

describe('유형 집중 풀이: 잠김·초기화(선생님 요청 2026-11-28)', () => {
  const solved = (ver = 1): ProbState => ({ ...emptyProb(ver, '2026-11-28T00:00:00.000Z'), solved: true, stepsDone: true, steps: ['s1'] });
  const base = (): CourseState => ({
    v: 1,
    probs: { 'pyb-t01-a': solved(), 'pyb-t01-adv1': solved(), 'pyb-t02-a': solved() },
    advOpen: ['t01', 't02'],
    mocks: { m1: { round: 1, startedAt: '2026-11-28T00:00:00.000Z', results: { t01: { score: 100, solved: true, tries: 1, at: '2026-11-28T00:00:00.000Z' } } } },
  });

  it('세 번째 잠김에서 그 유형(기본·심화·심화 열림)만 지우고 모의고사·다른 유형은 남긴다', () => {
    expect(LOCK_LIMIT).toBe(3);
    let s = base();
    const r1 = addLock(s, 't01', '2026-11-28T01:00:00.000Z');
    expect(r1).toMatchObject({ count: 1, reset: false });
    const r2 = addLock(r1.state, 't01', '2026-11-28T01:00:00.000Z');
    expect(r2.count).toBe(2);
    expect(r2.state.locks!.t01![1] > r2.state.locks!.t01![0]).toBe(true);
    expect(lockCount(r2.state, 't01')).toBe(2);
    const r3 = addLock(r2.state, 't01', '2026-11-28T02:00:00.000Z');
    expect(r3).toMatchObject({ count: 3, reset: true });
    s = r3.state;
    expect(Object.keys(s.probs)).toEqual(['pyb-t02-a']);
    expect(s.advOpen).toEqual(['t02']);
    expect(s.mocks?.m1.results.t01.solved).toBe(true);
    expect(lockCount(s, 't01')).toBe(0);
    expect(s.resets?.t01).toEqual({ at: '2026-11-28T02:00:00.000Z', n: 1 });
  });

  it('다른 기기의 예전 기록이 초기화를 되살리지 않는다(초기화 뒤에 푼 것은 남는다)', () => {
    const old = base();
    const reset = resetType(base(), 't01', '2026-11-28T02:00:00.000Z');
    const after = { ...reset, probs: { ...reset.probs, 'pyb-t01-b': solved() } };
    for (const m of [mergeState(old, after), mergeState(after, old)]) {
      expect(Object.keys(m.probs).sort()).toEqual(['pyb-t01-b', 'pyb-t02-a']);
      expect(m.resets?.t01.n).toBe(1);
      expect(m.advOpen).toEqual(['t02']);
    }
    // 잠김 횟수: 초기화 전 시각은 버리고, 초기화 뒤 시각은 합친다
    const a = { ...old, locks: { t01: ['2026-11-28T01:00:00.000Z', '2026-11-28T01:30:00.000Z'] } };
    const b = { ...reset, locks: { t01: ['2026-11-28T03:00:00.000Z'] } };
    expect(mergeState(a, b).locks).toEqual({ t01: ['2026-11-28T03:00:00.000Z'] });
  });

  it('저장된 잠김·초기화 값을 믿지 않고 정리한다', () => {
    const s = sanitize({ v: 1, probs: {}, locks: { t01: ['x', '2026-11-28T01:00:00.000Z'], t99: ['2026-11-28T01:00:00.000Z'], t20: [] }, resets: { t13: { at: '2026-11-28T01:00:00.000Z', n: -3 }, t02: { at: 'nope' } } });
    expect(s.locks).toEqual({ t01: ['2026-11-28T01:00:00.000Z'] });
    expect(s.resets).toEqual({ t13: { at: '2026-11-28T01:00:00.000Z', n: 1 } });
  });

  it('Data 2급 예전 판(version 1) 기록은 버린다(같은 id가 다른 문제를 가리키게 됨)', () => {
    const s = sanitize({ v: 1, probs: { 'd2-t05-a': solved(1), 'd2-t13-a': solved(2), 'pyb-t01-a': solved(1) } });
    expect(Object.keys(s.probs).sort()).toEqual(['d2-t13-a', 'pyb-t01-a']);
  });
});

describe('유형 집중 풀이 상태기계', () => {
  const on = { visible: true, hasFocus: true };
  it('시작 화면 → 풀이 시작 → 이탈은 잠김 1회, 연속 이벤트는 세지 않음, 자동 재개 없음', () => {
    let s = focusReducer(initialFocus, { type: 'start', env: on });
    expect(s).toEqual({ status: 'readyToResume', reason: 'gate' });
    expect(classifyLeave('blur', { status: s.status, fsGrace: false, counted: false })).toBe('pause');
    s = focusReducer(s, { type: 'resume', env: on });
    expect(s.status).toBe('active');
    expect(classifyLeave('blur', { status: 'active', fsGrace: true, counted: false })).toBe('defer');
    expect(classifyLeave('pagehide', { status: 'active', fsGrace: true, counted: false })).toBe('lock');
    expect(classifyLeave('hidden', { status: 'active', fsGrace: false, counted: false })).toBe('lock');
    expect(classifyLeave('hidden', { status: 'active', fsGrace: false, counted: true })).toBe('pause');
    s = focusReducer(s, { type: 'blur' });
    expect(s).toEqual({ status: 'paused', reason: 'blur' });
    s = focusReducer(s, { type: 'hidden' });
    expect(s.reason).toBe('blur');
    s = focusReducer(s, { type: 'focus', env: on });
    expect(s.status).toBe('readyToResume');
    s = focusReducer(s, { type: 'manualBreak' });
    expect(s.status).toBe('readyToResume');
  });
  it('쉬기는 세지 않는 멈춤이고, 안내 문구는 마지막 경고·초기화를 알린다', () => {
    const s = focusReducer({ status: 'active', reason: null }, { type: 'manualBreak' });
    expect(s).toEqual({ status: 'paused', reason: 'manual' });
    expect(lockNotice(1, 3, false).last).toBe(false);
    expect(lockNotice(2, 3, false).last).toBe(true);
    expect(lockNotice(3, 3, true).title).toContain('처음으로');
  });
});
