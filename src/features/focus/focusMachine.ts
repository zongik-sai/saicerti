/**
 * 유형 집중 풀이 상태기계(배움 숲 docs/09_FOCUS_MODE.md의 '단원 집중 학습'을 따름, 선생님 요청 2026-11-28).
 * 유형의 문제 화면은 시작 화면(gate)에서 클릭으로 전체화면에 들어간다. 푸는 중(active) 포커스를 잃거나
 * 전체화면을 나가면 잠김 1회로 세고(같은 이탈의 연속 이벤트는 한 번만), 한 유형에서 3번 잠기면
 * 그 유형의 기록을 초기화한다(호출하는 쪽이 처리). '쉬기'와 메뉴로 나가는 것은 세지 않는다. 자동 제출은 하지 않는다.
 *
 * 이 창의 포커스·표시 상태만 안다. 다른 프로그램 실행 여부, 다른 탭 주소, 분할 화면, 두 번째 모니터는 알 수 없다.
 */

export type FocusStatus = 'active' | 'paused' | 'readyToResume';
export type PauseReason = 'hidden' | 'blur' | 'pagehide' | 'fullscreen' | 'manual' | 'gate';

export interface FocusState {
  status: FocusStatus;
  reason: PauseReason | null;
}

export interface Env {
  visible: boolean;
  hasFocus: boolean;
}

export type FocusEvent =
  | { type: 'start'; env: Env }
  | { type: 'hidden' }
  | { type: 'blur' }
  | { type: 'pagehide' }
  | { type: 'fullscreen' }
  /** 다른 유형에 들어옴: 클릭으로 시작할 때까지 가린다(잠김으로 세지 않음) */
  | { type: 'gate' }
  | { type: 'visible'; env: Env }
  | { type: 'focus'; env: Env }
  | { type: 'resume'; env: Env }
  | { type: 'manualBreak' };

export const initialFocus: FocusState = { status: 'paused', reason: 'gate' };

const canRun = (e: Env) => e.visible && e.hasFocus;

export function focusReducer(s: FocusState, ev: FocusEvent): FocusState {
  switch (ev.type) {
    case 'start':
      return { status: canRun(ev.env) ? 'readyToResume' : 'paused', reason: 'gate' };
    case 'hidden':
    case 'blur':
    case 'pagehide':
    case 'fullscreen':
      // 이미 잠긴 이탈이면 그대로(첫 이유를 남긴다). 시작 화면·쉬는 중에 떠나면 이유는 두고 '돌아오면 버튼' 상태로
      if (s.status === 'paused' && s.reason !== 'manual' && s.reason !== 'gate') return s;
      if (s.status !== 'active') return { ...s, status: 'paused' };
      return { status: 'paused', reason: ev.type };
    case 'gate':
      return { ...s, status: s.status === 'active' ? 'paused' : s.status, reason: 'gate' };
    case 'manualBreak':
      if (s.status !== 'active') return s;
      return { status: 'paused', reason: 'manual' };
    case 'visible':
    case 'focus':
      // 돌아와도 자동으로 다시 시작하지 않는다(버튼을 눌러야 함)
      if (s.status === 'paused' && canRun(ev.env)) return { ...s, status: 'readyToResume' };
      return s;
    case 'resume':
      if (s.status !== 'active' && canRun(ev.env)) return { status: 'active', reason: null };
      return s;
  }
}

/** 푸는 중(active)에 이 이벤트가 오면 잠김 1회로 센다 */
export const LOCK_EVENTS = ['hidden', 'blur', 'pagehide', 'fullscreen'] as const;
export type LockEvent = (typeof LOCK_EVENTS)[number];

/**
 * 이탈 이벤트를 어떻게 처리할지(순수 함수, 테스트 대상).
 * - defer: 시작 직후(전체화면 전환 흔들림)의 blur·전체화면 나감은 세지도 멈추지도 않고, 유예가 끝난 뒤 다시 확인한다
 * - lock: 푸는 중 이번 이탈의 첫 이벤트 → 잠김 1회(창 닫기·새로고침 pagehide는 유예 없이 바로)
 * - pause: 세지 않고 상태기계에만 전달(이미 멈춤·같은 이탈의 연속 이벤트)
 */
export type LeaveDecision = 'defer' | 'lock' | 'pause';
export function classifyLeave(ev: LockEvent, o: { status: FocusStatus; fsGrace: boolean; counted: boolean }): LeaveDecision {
  if (o.status !== 'active') return 'pause';
  if (o.fsGrace && (ev === 'blur' || ev === 'fullscreen')) return 'defer';
  if (!o.counted) return 'lock';
  return 'pause';
}

/** 잠김 안내 문구(남은 횟수·마지막 경고·초기화) */
export function lockNotice(count: number, limit: number, reset: boolean): { title: string; body: string; last: boolean } {
  if (reset) return { title: '이 유형 기록이 처음으로 돌아갔어요', body: `${limit}번 잠겨서 이 유형의 풀이 기록과 코드 초안을 지웠어요. 모의고사·다른 유형 기록은 그대로예요. 첫 문제부터 다시 풀어요.`, last: false };
  const left = Math.max(1, limit - count);
  if (left === 1) return { title: `화면이 잠겼어요 (${Math.min(count, limit - 1)}/${limit})`, body: '마지막 경고예요! 한 번 더 잠기면 이 유형의 풀이 기록이 처음으로 돌아가요.', last: true };
  return { title: `화면이 잠겼어요 (${count}/${limit})`, body: `푸는 중에 다른 창·탭·앱으로 가거나 전체화면을 나가면 잠겨요. 이 유형에서 ${limit}번 잠기면 풀이 기록이 처음으로 돌아가요(${left}번 남음).`, last: false };
}
