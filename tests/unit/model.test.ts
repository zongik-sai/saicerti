import { describe, expect, it } from 'vitest';
import { emptyProb, mergeState, sanitize, tally, type CourseState } from '../../src/features/progress/model';

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
