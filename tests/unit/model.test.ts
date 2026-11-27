import { describe, expect, it } from 'vitest';
import { advGate, emptyProb, isAdvId, mergeState, mockGate, sanitize, tally, type CourseState } from '../../src/features/progress/model';

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
    const s = sanitize({ probs: { 'pyb-t01-adv1': { solved: true }, 'pyb-t01-adv6': {}, 'cb-t10-adv5': {} }, advOpen: ['t01', 't01', 't11', 3, 't10'] });
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
