/**
 * 과정 진도 저장소: 이 기기(localStorage) + 서버(Supabase course_progress, 본인 행만 RLS).
 * - 바뀌면 바로 이 기기에 저장하고, 잠시 뒤 서버에 저장(revision 비교 저장: 다른 기기가 먼저 저장했으면 합쳐서 다시 저장).
 * - 학생 코드는 서버로 보내지 않는다(진도·횟수만).
 */
import { useEffect, useState, useSyncExternalStore } from 'react';
import type { CourseId } from '../../content/types';
import { isSupabaseConfigured } from '../../lib/config';
import { learnerPrefix, readJson, removeRaw, UNSYNCED_SUFFIX, writeJson, writeRaw } from '../../lib/storage';
import { supabase } from '../auth/supabase';
import { addLock, emptyProb, emptyState, mergeState, sameState, sanitize, type CourseState, type MockState, type ProbState } from './model';

export type SyncStatus = 'local' | 'loading' | 'saving' | 'saved' | 'offline' | 'not-ready';

interface Entry {
  key: string;
  learnerKey: string;
  course: CourseId;
  remote: boolean;
  state: CourseState;
  revision: number;
  sync: SyncStatus;
  syncError?: string;
  listeners: Set<() => void>;
  timer?: ReturnType<typeof setTimeout>;
  saving?: Promise<void>;
  loaded: boolean;
  snapshot: { state: CourseState; sync: SyncStatus; syncError?: string };
}

const entries = new Map<string, Entry>();

const storeKey = (learnerKey: string, course: CourseId) => `${learnerPrefix(learnerKey)}${course}`;

function emit(e: Entry) {
  e.snapshot = { state: e.state, sync: e.sync, syncError: e.syncError };
  for (const l of e.listeners) l();
}

function persistLocal(e: Entry, unsynced: boolean) {
  writeJson(e.key, { state: e.state, revision: e.revision });
  if (unsynced) writeRaw(e.key + UNSYNCED_SUFFIX, '1');
  else removeRaw(e.key + UNSYNCED_SUFFIX);
}

function entry(learnerKey: string, course: CourseId, remote: boolean): Entry {
  const key = storeKey(learnerKey, course);
  let e = entries.get(key);
  if (!e) {
    const saved = readJson<{ state?: unknown; revision?: number }>(key, {});
    const state = sanitize(saved.state);
    e = {
      key,
      learnerKey,
      course,
      remote: remote && isSupabaseConfigured,
      state,
      revision: typeof saved.revision === 'number' ? saved.revision : 0,
      sync: remote && isSupabaseConfigured ? 'loading' : 'local',
      listeners: new Set(),
      loaded: false,
      snapshot: { state, sync: 'local' },
    };
    e.snapshot = { state: e.state, sync: e.sync };
    entries.set(key, e);
    if (e.remote) void loadRemote(e);
    else e.loaded = true;
  }
  return e;
}

function friendly(msg: string): { status: SyncStatus; text: string } {
  if (/알 수 없는 과목/.test(msg)) return { status: 'not-ready', text: '서버 저장 준비가 아직 안 됐어요(선생님 설정 필요). 기록은 이 기기에 남아 있어요.' };
  if (/JWT|auth|401|403/i.test(msg)) return { status: 'offline', text: '로그인이 만료되어 서버에 저장하지 못했어요. 다시 로그인해 주세요.' };
  return { status: 'offline', text: '서버에 저장하지 못했어요(인터넷 확인). 기록은 이 기기에 남아 있어요.' };
}

/** 서버에 저장할 기록이 있는지(빈 기록으로 행을 만들지 않게) */
const hasAny = (s: CourseState) => Object.keys(s.probs).length > 0 || !!s.mocks || !!s.locks || !!s.resets || !!s.advOpen;

async function loadRemote(e: Entry) {
  const sb = supabase();
  if (!sb) return;
  const { data, error } = await sb.from('course_progress').select('state, revision').eq('course', e.course).maybeSingle();
  e.loaded = true;
  if (error) {
    const f = friendly(error.message);
    e.sync = f.status;
    e.syncError = f.text;
    emit(e);
    return;
  }
  const server = data ? sanitize(data.state) : emptyState();
  e.revision = data ? Number(data.revision) : 0;
  const merged = mergeState(server, e.state);
  e.state = merged;
  const differs = !data || !sameState(merged, server);
  const any = hasAny(merged);
  persistLocal(e, differs && any);
  e.sync = 'saved';
  e.syncError = undefined;
  emit(e);
  if (differs && any) schedule(e, 0);
}

function schedule(e: Entry, ms = 1200) {
  if (!e.remote) return;
  clearTimeout(e.timer);
  e.timer = setTimeout(() => void save(e), ms);
}

async function save(e: Entry, retry = true): Promise<void> {
  const sb = supabase();
  if (!sb || !e.loaded) return;
  if (e.saving) {
    await e.saving;
  }
  const run = (async () => {
    e.sync = 'saving';
    emit(e);
    const sent = e.state;
    const { data, error } = await sb.rpc('save_course_progress', { p_course: e.course, p_state: sent, p_expected_revision: e.revision });
    if (error) {
      const f = friendly(error.message);
      e.sync = f.status;
      e.syncError = f.text;
      emit(e);
      return;
    }
    const r = data as { status: string; revision: number; state?: unknown };
    if (r.status === 'conflict') {
      e.revision = r.revision;
      e.state = mergeState(sanitize(r.state), e.state);
      persistLocal(e, true);
      emit(e);
      if (retry) {
        e.saving = undefined;
        await save(e, false);
      }
      return;
    }
    e.revision = r.revision;
    const clean = sameState(sent, e.state);
    persistLocal(e, !clean);
    e.sync = clean ? 'saved' : 'saving';
    e.syncError = undefined;
    emit(e);
    if (!clean) schedule(e, 300);
  })();
  e.saving = run;
  try {
    await run;
  } finally {
    if (e.saving === run) e.saving = undefined;
  }
}

/** 보이지 않게 될 때(탭 닫기 등) 저장 대기 중인 것을 바로 보낸다. */
if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'hidden') return;
    for (const e of entries.values()) {
      if (e.timer) {
        clearTimeout(e.timer);
        e.timer = undefined;
        void save(e);
      }
    }
  });
}

/** 로그아웃 때 메모리의 기록을 비운다(다음 사용자에게 보이지 않게). */
export function forgetLearner(learnerKey: string) {
  for (const [k, e] of entries) {
    if (e.learnerKey === learnerKey) {
      clearTimeout(e.timer);
      entries.delete(k);
    }
  }
}

export interface CourseProgress {
  state: CourseState;
  sync: SyncStatus;
  syncError?: string;
  update: (pid: string, ver: number, fn: (p: ProbState) => ProbState) => void;
  /** 모의고사 한 회(m1~m3) 기록 바꾸기 */
  updateMock: (key: string, fn: (m: MockState | undefined) => MockState) => void;
  /** [심화] 열기(유형 t01~t10) */
  openAdv: (tkey: string) => void;
  /**
   * 유형 집중 풀이 잠김 1회(이 기기에 바로 저장: 창을 닫는 중일 수도 있으므로). 세 번째면 그 유형 기록을 지우고
   * 그 유형 문제(pids)의 코드 초안도 지운다. 몇 번째인지와 초기화했는지를 돌려준다
   */
  addLock: (tkey: string, pids: string[]) => { count: number; reset: boolean };
  retry: () => void;
}

export function useCourseProgress(learnerKey: string, course: CourseId, remote: boolean): CourseProgress {
  const e = entry(learnerKey, course, remote);
  const snap = useSyncExternalStore(
    (cb) => {
      e.listeners.add(cb);
      return () => e.listeners.delete(cb);
    },
    () => e.snapshot,
  );
  return {
    state: snap.state,
    sync: snap.sync,
    syncError: snap.syncError,
    update: (pid, ver, fn) => {
      const now = new Date().toISOString();
      const cur = e.state.probs[pid];
      const base = cur && cur.ver === ver ? cur : { ...emptyProb(ver, now), solved: cur?.solved ?? false, tries: cur?.tries ?? 0, solvedAt: cur?.solvedAt };
      const next = { ...fn(base), lastAt: now };
      e.state = { ...e.state, probs: { ...e.state.probs, [pid]: next } };
      persistLocal(e, e.remote);
      emit(e);
      schedule(e);
    },
    updateMock: (key, fn) => {
      const next = fn(e.state.mocks?.[key]);
      e.state = { ...e.state, mocks: { ...(e.state.mocks ?? {}), [key]: next } };
      persistLocal(e, e.remote);
      emit(e);
      schedule(e);
    },
    openAdv: (tkey) => {
      if (e.state.advOpen?.includes(tkey)) return;
      e.state = { ...e.state, advOpen: [...new Set([...(e.state.advOpen ?? []), tkey])].sort() };
      persistLocal(e, e.remote);
      emit(e);
      schedule(e);
    },
    addLock: (tkey, pids) => {
      const r = addLock(e.state, tkey);
      e.state = r.state;
      persistLocal(e, e.remote);
      if (r.reset) for (const pid of pids) clearDraft(learnerKey, pid);
      emit(e);
      // 잠김은 곧 창을 닫는 중(pagehide)일 수도 있어 서버에도 바로 보낸다
      if (e.remote) {
        clearTimeout(e.timer);
        e.timer = undefined;
        void save(e);
      }
      return { count: r.count, reset: r.reset };
    },
    retry: () => {
      if (!e.loaded) void loadRemote(e);
      else void save(e);
    },
  };
}

/** 코드 초안(이 기기에만). 문제 version이 바뀌면 버린다. */
export interface Draft {
  ver: number;
  code?: string;
  blanks?: string[];
}
const draftKey = (learnerKey: string, pid: string) => `${learnerPrefix(learnerKey)}code:${pid}`;
export function readDraft(learnerKey: string, pid: string, ver: number): Draft | null {
  const d = readJson<Draft | null>(draftKey(learnerKey, pid), null);
  if (!d || d.ver !== ver) return null;
  if (d.code !== undefined && (typeof d.code !== 'string' || d.code.length > 20000)) return null;
  if (d.blanks !== undefined && !(Array.isArray(d.blanks) && d.blanks.every((x) => typeof x === 'string'))) return null;
  return d;
}
export function writeDraft(learnerKey: string, pid: string, d: Draft) {
  writeJson(draftKey(learnerKey, pid), d);
}
export function clearDraft(learnerKey: string, pid: string) {
  removeRaw(draftKey(learnerKey, pid));
}

/** 값이 잠시 멈췄을 때만 저장(입력마다 저장하지 않게) */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
