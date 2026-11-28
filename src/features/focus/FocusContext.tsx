import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState, type ReactNode, type RefObject } from 'react';
import { Link } from 'react-router-dom';
import { classifyLeave, focusReducer, initialFocus, lockNotice, type FocusState, type LockEvent } from './focusMachine';
import { exitFullscreen, fullscreenElement, fullscreenSupported, lockEscapeKey, requestFullscreen, requestWakeLock, SUSPEND_EVENT, unlockEscapeKey } from './fullscreen';

/** 유형 집중 풀이 범위(전체화면 + 잠김 횟수) */
export interface StrictScope {
  /** 범위 식별자(과정:유형). 바뀌면 시작 화면부터 */
  key: string;
  /** 안내 문구용 이름(예: '유형 3', '시험 13번 유형') */
  label: string;
  /** 지금까지 잠긴 횟수(초기화 후 0부터) */
  locks: number;
  limit: number;
  /** 잠김 1회 기록(이 기기에 바로 저장). 몇 번째인지와 초기화했는지를 돌려준다 */
  onLock: () => { count: number; reset: boolean };
}

interface FocusCtx {
  state: FocusState;
  active: boolean;
  manualBreak: () => void;
  resume: () => void;
  strict: StrictScope;
  /** 방금 잠긴 결과(안내 표시용) */
  lastLock: { count: number; reset: boolean } | null;
  /** 이 기기에서 전체화면을 쓸 수 있는지 */
  fullscreenOk: boolean;
}

const Ctx = createContext<FocusCtx | null>(null);
const useFocus = () => useContext(Ctx)!;

const env = () => ({ visible: document.visibilityState === 'visible', hasFocus: document.hasFocus() });

/** 전체화면에 들어가거나 시작한 직후 잠시 생기는 포커스 흔들림은 세지 않고, 끝난 뒤 다시 확인한다 */
const GRACE_MS = 1500;

/**
 * 유형 집중 풀이(선생님 요청 2026-11-28, 배움 숲 단원 집중 학습과 같은 방식·한도만 3번).
 * 이 창의 visibility·focus·전체화면만 쓴다. 다른 프로그램·다른 탭 주소는 알 수 없고 감시·차단하지 않는다.
 */
export function FocusProvider({ children, strict }: { children: ReactNode; strict: StrictScope }) {
  const [state, dispatch] = useReducer(focusReducer, initialFocus);
  const [lastLock, setLastLock] = useState<{ count: number; reset: boolean } | null>(null);
  const strictRef = useRef(strict);
  strictRef.current = strict;
  const strictKey = strict.key;
  /** 전체화면에 들어갔는지(나가면 잠김) */
  const fsWanted = useRef(false);
  const graceUntil = useRef(0);
  const graceTimer = useRef<number | null>(null);
  /** 이번 이탈을 이미 셌는지(다시 시작하면 지움) */
  const countedRef = useRef(false);
  const statusRef = useRef(state.status);

  /** 이탈 이벤트. 같은 이탈의 blur·hidden이 연달아 와도 한 번만 센다. 이벤트 처리기 안에서 바로 기록한다(pagehide 뒤에는 화면이 다시 그려지지 않을 수 있음) */
  const leave = useCallback((ev: LockEvent) => {
    const decision = classifyLeave(ev, { status: statusRef.current, fsGrace: performance.now() < graceUntil.current, counted: countedRef.current });
    if (decision === 'defer') {
      if (graceTimer.current === null) {
        graceTimer.current = window.setTimeout(() => {
          graceTimer.current = null;
          const e = env();
          if (statusRef.current !== 'active') return;
          if (!e.visible) leaveRef.current('hidden');
          else if (!e.hasFocus) leaveRef.current('blur');
          else if (fsWanted.current && !fullscreenElement()) leaveRef.current('fullscreen');
        }, Math.max(0, graceUntil.current - performance.now()) + 50);
      }
      return;
    }
    if (decision === 'lock') {
      countedRef.current = true;
      const r = strictRef.current.onLock();
      setLastLock(r);
    }
    dispatch({ type: ev });
  }, []);
  const leaveRef = useRef(leave);
  leaveRef.current = leave;

  useEffect(() => {
    dispatch({ type: 'start', env: env() });
  }, []);

  // 다른 유형으로 넘어감: 전체화면 중이면 그대로 이어 가고, 아니면 시작 화면
  useEffect(() => {
    setLastLock(null);
    if (!(fsWanted.current && fullscreenElement())) dispatch({ type: 'gate' });
  }, [strictKey]);

  // 화면을 떠날 때(메뉴·링크로 나감) 전체화면을 끝낸다(잠김으로 세지 않음)
  useEffect(
    () => () => {
      if (graceTimer.current !== null) window.clearTimeout(graceTimer.current);
      if (fsWanted.current) {
        fsWanted.current = false;
        unlockEscapeKey();
        exitFullscreen();
      }
    },
    [],
  );

  useEffect(() => {
    statusRef.current = state.status;
    if (state.status === 'active') countedRef.current = false;
  }, [state.status]);

  useEffect(() => {
    const onVis = () => (document.visibilityState === 'hidden' ? leave('hidden') : dispatch({ type: 'visible', env: env() }));
    const onBlur = () => leave('blur');
    const onFocus = () => dispatch({ type: 'focus', env: env() });
    const onHide = () => leave('pagehide');
    // 전체화면을 나가면(Esc 등) 잠김. 우리가 끝낸 경우(fsWanted=false)는 세지 않는다
    const onFs = () => {
      if (!fullscreenElement() && fsWanted.current) leave('fullscreen');
    };
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('blur', onBlur);
    window.addEventListener('focus', onFocus);
    window.addEventListener('pagehide', onHide);
    document.addEventListener('fullscreenchange', onFs);
    document.addEventListener('webkitfullscreenchange', onFs);
    return () => {
      document.removeEventListener('visibilitychange', onVis);
      window.removeEventListener('blur', onBlur);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('pagehide', onHide);
      document.removeEventListener('fullscreenchange', onFs);
      document.removeEventListener('webkitfullscreenchange', onFs);
    };
  }, [leave]);

  // 앱 안의 버튼이 페이지를 떠나게 할 때(로그인): 잠김 없이 멈춘다
  useEffect(() => {
    const on = () => {
      countedRef.current = true; // 곧 이어질 hidden·pagehide를 세지 않음
      if (fsWanted.current) {
        fsWanted.current = false;
        unlockEscapeKey();
        exitFullscreen();
      }
      dispatch({ type: 'manualBreak' });
    };
    window.addEventListener(SUSPEND_EVENT, on);
    return () => window.removeEventListener(SUSPEND_EVENT, on);
  }, []);

  // 푸는 동안 화면 꺼짐 방지(휴대폰 자동 잠금이 이탈로 세지지 않게)
  const isActive = state.status === 'active';
  useEffect(() => {
    if (!isActive) return;
    let lock: { release: () => Promise<void> } | null = null;
    let alive = true;
    void requestWakeLock().then((l) => {
      if (alive) lock = l;
      else void l?.release().catch(() => {});
    });
    return () => {
      alive = false;
      void lock?.release().catch(() => {});
    };
  }, [isActive]);

  /** 시작·다시 시작(버튼 클릭 안에서): 전체화면을 요청한다 */
  const resume = () => {
    if (fullscreenSupported()) {
      graceUntil.current = performance.now() + GRACE_MS;
      if (fullscreenElement()) fsWanted.current = true;
      else {
        requestFullscreen().then(
          () => {
            fsWanted.current = true;
            lockEscapeKey();
          },
          () => {
            fsWanted.current = false;
          },
        );
      }
    } else graceUntil.current = performance.now() + 300;
    setLastLock(null);
    dispatch({ type: 'resume', env: env() });
  };
  const manualBreak = () => {
    // 쉬기는 잠김으로 세지 않는다. 전체화면도 함께 끝낸다
    if (fsWanted.current) {
      fsWanted.current = false;
      unlockEscapeKey();
      exitFullscreen();
    }
    dispatch({ type: 'manualBreak' });
  };

  const value: FocusCtx = { state, active: state.status === 'active', manualBreak, resume, strict, lastLock, fullscreenOk: fullscreenSupported() };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** 문제 화면을 가리는 불투명 덮개 + 문제 영역 inert */
export function FocusGate({ children, exit }: { children: ReactNode; exit: { to: string; label: string } }) {
  const f = useFocus();
  const btn = useRef<HTMLButtonElement>(null);
  const paused = !f.active;
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    if (paused) el.setAttribute('inert', '');
    else el.removeAttribute('inert');
  }, [paused]);

  useEffect(() => {
    if (paused) btn.current?.focus();
  }, [paused]);

  // 가림 중에는 단축키도 무효화
  useEffect(() => {
    if (!paused) return;
    const block = (e: KeyboardEvent) => {
      if (e.target instanceof Node && (e.target as HTMLElement).closest?.('.focus-overlay')) return;
      e.preventDefault();
      e.stopPropagation();
    };
    window.addEventListener('keydown', block, true);
    return () => window.removeEventListener('keydown', block, true);
  }, [paused]);

  const sc = f.strict;
  return (
    <>
      <div ref={root} aria-hidden={paused || undefined} data-focus-status={f.state.status}>
        {f.active && (
          <div className="page strict-wrap">
            <div className="strict-bar" role="status">
              <span>
                🔒 집중 풀이 중 · {sc.label} 잠김{' '}
                <b>
                  {Math.min(sc.locks, sc.limit - 1)}/{sc.limit}
                </b>
              </span>
              <button className="btn small ghost" onClick={f.manualBreak}>
                쉬기
              </button>
            </div>
          </div>
        )}
        {children}
      </div>
      {paused && (
        <div className="focus-overlay" role="dialog" aria-modal="true" aria-labelledby="focus-title" aria-describedby="focus-desc" data-testid="focus-overlay">
          <div className="focus-card">
            <StrictCard btn={btn} exit={exit} />
          </div>
        </div>
      )}
    </>
  );
}

/** 시작·잠김·쉬기 화면 */
function StrictCard({ btn, exit }: { btn: RefObject<HTMLButtonElement>; exit: { to: string; label: string } }) {
  const f = useFocus();
  const sc = f.strict;
  const reason = f.state.reason;
  const fsWord = f.fullscreenOk ? '전체화면으로 ' : '';
  const shown = Math.min(sc.locks, sc.limit - 1);
  const locked = f.lastLock ?? (reason === 'hidden' || reason === 'blur' || reason === 'pagehide' || reason === 'fullscreen' ? { count: shown, reset: false } : null);
  const note = locked ? lockNotice(locked.count, sc.limit, locked.reset) : null;
  return (
    <>
      {reason === 'manual' ? (
        <>
          <h2 id="focus-title">쉬는 중이에요</h2>
          <p id="focus-desc">
            쉬는 동안은 잠김으로 세지 않아요. 준비되면 다시 시작하세요. (이 유형 잠김 {shown}/{sc.limit})
          </p>
        </>
      ) : note ? (
        <>
          <h2 id="focus-title" className={note.last || locked?.reset ? 'strict-warn' : undefined}>
            {note.title}
          </h2>
          <p id="focus-desc">{note.body}</p>
        </>
      ) : (
        <>
          <h2 id="focus-title">{sc.label} 집중 풀이</h2>
          <p id="focus-desc">
            문제는 {f.fullscreenOk ? '전체화면으로' : '한 화면에 집중해서'} 풀어요. 지금까지 이 유형 잠김{' '}
            <b>
              {shown}/{sc.limit}
            </b>
          </p>
          <ul className="strict-rules">
            <li>푸는 동안 다른 창·탭·앱으로 가거나{f.fullscreenOk ? ' 전체화면을 나가면(Esc)' : ''} 화면이 잠겨요.</li>
            <li>
              한 유형에서 <b>{sc.limit}번</b> 잠기면 그 유형의 풀이 기록과 코드 초안이 처음으로 돌아가요. 모의고사·다른 유형은 그대로예요.
            </li>
            <li>
              그만할 때는 <b>쉬기</b>를 누르거나 위 메뉴·아래 버튼으로 나가세요. 이때는 세지 않아요.
            </li>
          </ul>
          {!f.fullscreenOk && <p className="faint">이 기기(브라우저)는 웹페이지 전체화면을 지원하지 않아요. 전체화면 없이 진행하지만, 다른 앱으로 가면 똑같이 잠겨요.</p>}
        </>
      )}
      <button ref={btn} className="btn primary" onClick={f.resume}>
        {reason === 'gate' ? `${fsWord}풀이 시작` : `${fsWord}다시 시작`}
      </button>
      {f.state.status !== 'readyToResume' && reason !== 'manual' && (
        <p className="faint" style={{ marginTop: '0.75rem' }}>
          이 창으로 돌아오면 버튼을 눌러 계속할 수 있어요.
        </p>
      )}
      <p style={{ margin: '1rem 0 0' }}>
        <Link className="btn small ghost" to={exit.to}>
          {exit.label}
        </Link>
      </p>
    </>
  );
}
