import { useEffect, useState, type ReactNode } from 'react';
import { HashRouter, Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom';
import { allProblems, COURSES, courseMeta, findProblem, loadCourse, typeKey, type CourseMeta } from '../content';
import type { Course } from '../content/types';
import { useAuth } from '../features/auth/AuthContext';
import { isDemoEnabled, isSupabaseConfigured, BASE_URL } from '../lib/config';
import { forgetLearner, useCourseProgress } from '../features/progress/store';
import { CourseHome } from './CourseHome';
import { ProblemPage } from './ProblemPage';
import { MockPage } from './MockPage';
import { TeacherPage } from '../features/teacher/TeacherPage';
import { AdminPage } from '../features/admin/AdminPage';
import { useRoles } from '../features/admin/roles';
import { advGate, isAdvId, LOCK_LIMIT, lockCount, mockGate, tally } from '../features/progress/model';
import { FocusGate, FocusProvider, type StrictScope } from '../features/focus/FocusContext';
import { suspendLearning } from '../features/focus/fullscreen';

/** 로그인하지 않은 사람도 문제를 풀 수 있다(선생님 요청 2026-11-27). 기록은 이 브라우저에만(접두사 saicerti:v1:guest:), 서버·선생님 화면에는 가지 않는다 */
const GUEST_KEY = 'guest';
function useLearner(): { learnerKey: string; remote: boolean; guest: boolean } {
  const { identity } = useAuth();
  if (!identity) return { learnerKey: GUEST_KEY, remote: false, guest: true };
  return { learnerKey: identity.learnerKey, remote: identity.kind === 'user', guest: false };
}

export function App() {
  return (
    <HashRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Home />} />
          {COURSES.map((c) => (
            <Route key={c.id} path={`${c.path}/*`} element={<CourseRoute key={c.id} meta={c} />} />
          ))}
          <Route path="/teacher" element={<TeacherPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </HashRouter>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const { identity, signOut, exitDemo, signIn, status } = useAuth();
  const loc = useLocation();
  const roles = useRoles();
  const [warn, setWarn] = useState(false);
  const out = async (force = false) => {
    if (identity?.kind === 'demo') {
      exitDemo();
      return;
    }
    const key = identity?.learnerKey;
    const ok = await signOut(force);
    if (!ok) {
      setWarn(true);
      return;
    }
    setWarn(false);
    if (key) forgetLearner(key);
  };
  return (
    <>
      <header className="top">
        <div className="top-in">
          <Link to="/" className="brand" aria-label="saicerti 홈">
            <span>
              <span className="brand-mark">sai</span>certi
            </span>
            <small>자격증 코딩 연습</small>
          </Link>
          <nav className="top-nav" aria-label="과정">
            {COURSES.map((c) => (
              <NavLink key={c.id} to={c.path}>
                {c.name.replace('프로그래밍 ', '')}
              </NavLink>
            ))}
            {roles?.teacher && <NavLink to="/teacher">반 현황</NavLink>}
            {roles?.teacher && <NavLink to="/admin">교사 관리</NavLink>}
          </nav>
          <div className="top-right">
            {identity?.kind === 'demo' && <span className="dev-flag">개발용 데모</span>}
            {identity?.kind === 'user' && <span className="who">{identity.name || identity.email}</span>}
            {identity && (
              <button className="btn small ghost" onClick={() => void out()}>
                {identity.kind === 'demo' ? '데모 끝내기' : '로그아웃'}
              </button>
            )}
            {!identity && status !== 'loading' && isSupabaseConfigured && (
              <button className="btn small" onClick={() => {
                suspendLearning();
                void signIn(loc.pathname);
              }}>
                로그인
              </button>
            )}
          </div>
        </div>
      </header>
      {warn && (
        <div className="page narrow" style={{ paddingBottom: 0 }}>
          <p className="notice warn" role="alert">
            아직 서버에 저장되지 않은 기록이 있어요. 인터넷 연결을 확인하고 잠시 뒤 다시 로그아웃해 주세요.{' '}
            <button className="btn small" onClick={() => void out(true)}>
              그래도 로그아웃(이 기기 기록 삭제)
            </button>
          </p>
        </div>
      )}
      <main>{children}</main>
      <footer className="footer">
        <span>saicerti · 서울인공지능고 수업용 연습 사이트</span>
        <a href={`${BASE_URL}privacy.html`}>개인정보처리방침</a>
        <a href="https://zongik-sai.github.io/saiedu/">배움 숲(saiedu)</a>
        <Link to="/teacher">선생님 화면</Link>
      </footer>
    </>
  );
}

function SignIn({ next, title = '로그인하면 기록이 남아요' }: { next: string; title?: string }) {
  const { signIn, startDemo, authError, clearError, expired, status } = useAuth();
  if (status === 'loading') return <div className="page" role="status">불러오는 중…</div>;
  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h2>{title}</h2>
      <p className="muted">로그인하지 않아도 문제를 풀 수 있어요(기록은 이 브라우저에만 남아요). 학교 Google 계정으로 로그인하면 푼 문제와 중간 점검 기록이 계정에 저장되어 어느 기기에서나 이어서 할 수 있고, 선생님 화면에도 보여요.</p>
      {expired && <p className="notice warn">로그인이 만료되었어요. 다시 로그인해 주세요.</p>}
      {authError && (
        <p className="notice bad" role="alert">
          로그인 오류: {authError}{' '}
          <button className="btn small ghost" onClick={clearError}>
            닫기
          </button>
        </p>
      )}
      {isSupabaseConfigured ? (
        <button className="btn primary" onClick={() => void signIn(next)}>
          Google 계정으로 로그인
        </button>
      ) : (
        <p className="notice warn">로그인 설정(VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY)이 아직 없어요. 사이트 관리자가 저장소 설정에 공개 값을 넣으면 로그인할 수 있어요.</p>
      )}
      {isDemoEnabled && (
        <div style={{ marginTop: '0.75rem' }}>
          <button className="btn" onClick={startDemo}>
            개발용 데모로 둘러보기
          </button>
          <p className="faint">개발 서버 전용 · 기록은 이 브라우저에만 저장되고 운영 데이터와 섞이지 않아요.</p>
        </div>
      )}
    </div>
  );
}

function Home() {
  const { identity } = useAuth();
  const learner = useLearner();
  return (
    <div className="page">
      <section className="hero">
        <h1>자격증 코딩, 손으로 따라가고 코드로 확인해요</h1>
        <p className="muted" style={{ maxWidth: '44rem' }}>
          COS Pro Python·C는 시험 유형마다 기본 연습 문제 5개와 도전용 심화 문제 5개, YBM DAT(Data 분석) 2급은 시험 20문항 유형마다 연습 5문제, 그리고 모의고사. 표를 채우며 코드를 손으로 따라가 보고, 직접 코드를 고치거나 작성해 자동 채점을 받아요. 코드는 내 브라우저 안에서만 실행돼요.
        </p>
      </section>
      <div className="courses">
        {COURSES.map((c) => (
          <Link key={c.id} to={c.path} className="card course-card">
            <span className="exam">{c.exam}</span>
            <h2>{c.name}</h2>
            <p className="muted" style={{ margin: 0 }}>
              {c.blurb}
            </p>
            <CourseBar meta={c} learnerKey={learner.learnerKey} remote={learner.remote} />
            <span className="btn primary" style={{ alignSelf: 'flex-start', marginTop: '0.3rem' }}>
              시작하기 →
            </span>
          </Link>
        ))}
      </div>
      <h2 style={{ marginTop: '1.6rem' }}>이렇게 공부해요</h2>
      <div className="how">
        <div className="card">
          <div className="n">01</div>
          <strong>문제 읽기</strong>
          <p className="faint" style={{ margin: 0 }}>시험지와 같은 형식: 문제 설명, 매개변수, return 값, 예시.</p>
        </div>
        <div className="card">
          <div className="n">02</div>
          <strong>중간 점검</strong>
          <p className="faint" style={{ margin: 0 }}>표에 값을 채우며 코드를 한 줄씩 따라가고, 핵심을 객관식으로 확인해요.</p>
        </div>
        <div className="card">
          <div className="n">03</div>
          <strong>코드 풀이 · 자동 채점</strong>
          <p className="faint" style={{ margin: 0 }}>빈칸 채우기 · 한 줄 수정 · 함수 작성. 예시로 실행해 보고, 숨은 테스트까지 채점해요.</p>
        </div>
      </div>
      <h2 style={{ marginTop: '1.6rem' }}>준비 중인 과정</h2>
      <div className="soon">
        <div>프로그래밍 C 심화 (COS Pro 1급 C)</div>
        <div>Data 1급</div>
      </div>
      {!identity && (
        <div style={{ marginTop: '1.6rem' }}>
          <SignIn next="/" />
        </div>
      )}
    </div>
  );
}

function CourseBar({ meta, learnerKey, remote }: { meta: CourseMeta; learnerKey: string; remote: boolean }) {
  const prog = useCourseProgress(learnerKey, meta.id, remote);
  const keys = Object.keys(prog.state.probs);
  const solved = tally(
    prog.state,
    keys.filter((k) => !isAdvId(k)),
  ).solved;
  const adv = tally(prog.state, keys.filter(isAdvId)).solved;
  return (
    <div>
      <div className="faint">
        {meta.style === 'exam' ? '' : '기본 '}해결 {Math.min(solved, meta.total)} / {meta.total}
        {adv > 0 && <span className="adv-count"> · 심화 {adv}</span>}
      </div>
      <div className="bar" aria-hidden>
        <i style={{ width: `${(Math.min(solved, meta.total) / meta.total) * 100}%` }} />
      </div>
    </div>
  );
}

function CourseRoute({ meta }: { meta: CourseMeta }) {
  const { status } = useAuth();
  const learner = useLearner();
  // 선생님은 잠금 없이 미리 볼 수 있다(심화·모의고사). 학생에게는 조건을 채워야 열림
  const preview = useRoles()?.teacher === true;
  const [course, setCourse] = useState<Course | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadCourse(meta.id).then(
      (c) => alive && setCourse(c),
      (e: unknown) => alive && setErr(String(e)),
    );
    return () => {
      alive = false;
    };
  }, [meta.id]);
  if (status === 'loading') return <div className="page" role="status">불러오는 중…</div>;
  if (err) return <div className="page notice bad">문제를 불러오지 못했어요. 새로고침해 주세요.</div>;
  if (!course || course.id !== meta.id) return <div className="page" role="status">문제 불러오는 중…</div>;
  const { learnerKey, remote } = learner;
  return (
    <>
      {learner.guest && <GuestBar />}
      <Routes>
        <Route index element={<CourseHome course={course} learnerKey={learnerKey} remote={remote} preview={preview} />} />
        <Route path="mock/:n" element={<MockRoute course={course} learnerKey={learnerKey} remote={remote} preview={preview} />} />
        <Route path=":pid" element={<ProblemRoute course={course} learnerKey={learnerKey} remote={remote} preview={preview} />} />
      </Routes>
    </>
  );
}

/** 로그인하지 않고 푸는 중이라는 안내(로그인 만료면 더 눈에 띄게) */
function GuestBar() {
  const { signIn, expired, authError, clearError } = useAuth();
  const loc = useLocation();
  return (
    <div className="page guest-wrap">
      <div className={`notice guest-bar${expired ? ' warn' : ''}`} role="status">
        <span>
          {expired ? '로그인이 만료되었어요. 지금부터의 기록은 이 브라우저에만 남아요. 다시 로그인해 주세요.' : '로그인하지 않고 푸는 중이에요. 기록은 이 브라우저에만 남고 선생님 화면에는 보이지 않아요.'}
        </span>
        {isSupabaseConfigured && (
          <button className="btn small primary" onClick={() => {
                suspendLearning();
                void signIn(loc.pathname);
              }}>
            Google 계정으로 로그인
          </button>
        )}
      </div>
      {authError && (
        <p className="notice bad" role="alert" style={{ marginTop: '0.5rem' }}>
          로그인 오류: {authError}{' '}
          <button className="btn small ghost" onClick={clearError}>
            닫기
          </button>
        </p>
      )}
    </div>
  );
}

interface RouteProps {
  course: Course;
  learnerKey: string;
  remote: boolean;
  preview: boolean;
}

function MockRoute({ course, learnerKey, remote, preview }: RouteProps) {
  const { n = '' } = useParams();
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const set = course.mocks.find((m) => String(m.n) === n);
  if (!set) return <Navigate to={courseMeta(course.id)!.path} replace />;
  const ids = allProblems(course).map((p) => p.id);
  if (!mockGate(prog.state, ids, set.key, preview)) {
    if (prog.sync === 'loading') return <div className="page" role="status">기록 불러오는 중…</div>;
    const solved = ids.filter((id) => prog.state.probs[id]?.solved).length;
    return <Locked course={course} title={`모의고사 ${set.n}회`} text={`모의고사는 기본 문제 ${ids.length}개를 모두 푼 뒤에 열려요. 지금 ${solved}/${ids.length}개 풀었어요.`} />;
  }
  return <MockPage key={set.key} course={course} set={set} learnerKey={learnerKey} remote={remote} />;
}

function ProblemRoute({ course, learnerKey, remote, preview }: RouteProps) {
  const { pid = '' } = useParams();
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const navigate = useNavigate();
  const f = findProblem(course, pid);
  if (!f) return <Navigate to={courseMeta(course.id)!.path} replace />;
  const meta = courseMeta(course.id)!;
  const tkey = typeKey(f.type);
  if (f.adv) {
    const basicIds = f.type.problems.map((p) => p.id);
    const gate = advGate(prog.state, typeKey(f.type), basicIds, preview);
    if (gate !== 'open') {
      if (prog.sync === 'loading') return <div className="page" role="status">기록 불러오는 중…</div>;
      const solved = basicIds.filter((id) => prog.state.probs[id]?.solved).length;
      return (
        <Locked
          course={course}
          title={`유형 ${f.type.type} [심화] ${f.index + 1}`}
          text={gate === 'ready' ? '기본 5문제를 모두 풀었어요. 과정 화면에서 [심화 열기]를 누르면 들어갈 수 있어요.' : `[심화]는 유형 ${f.type.type}의 기본 5문제를 모두 푼 뒤 열 수 있어요. 지금 ${solved}/5개 풀었어요.`}
        />
      );
    }
  }
  // 유형 집중 풀이(선생님 요청 2026-11-28): 전체화면으로 풀고, 다른 창으로 가거나 전체화면을 나가면 잠긴다. 한 유형에서 3번 잠기면 그 유형 기록을 처음으로
  const typePids = [...f.type.problems, ...(f.type.adv?.problems ?? [])].map((p) => p.id);
  const strict: StrictScope = {
    key: `${course.id}:${tkey}`,
    label: course.id === 'd2' ? `시험 ${f.type.type}번 유형` : `유형 ${f.type.type}`,
    locks: lockCount(prog.state, tkey),
    limit: LOCK_LIMIT,
    onLock: () => {
      const r = prog.addLock(tkey, typePids);
      if (r.reset) navigate(`${meta.path}/${f.type.problems[0].id}`, { replace: true });
      return r;
    },
  };
  const resetN = prog.state.resets?.[tkey]?.n ?? 0;
  // 문제마다 새로 그린다(앞 문제의 단계 위치·탭이 남지 않게). 초기화되면 풀던 화면도 새로
  return (
    <FocusProvider strict={strict}>
      <FocusGate exit={{ to: meta.path, label: '과정 화면으로 나가기' }}>
        <ProblemPage key={`${f.problem.id}:${resetN}`} course={course} type={f.type} problem={f.problem} index={f.index} adv={f.adv} learnerKey={learnerKey} remote={remote} />
      </FocusGate>
    </FocusProvider>
  );
}

/** 아직 잠긴 곳(심화·모의고사)에 주소로 바로 들어왔을 때 */
function Locked({ course, title, text }: { course: Course; title: string; text: string }) {
  const meta = courseMeta(course.id)!;
  return (
    <div className="page narrow">
      <div className="crumb">
        <Link to="/">홈</Link> › <Link to={meta.path}>{meta.name}</Link>
      </div>
      <div className="card" style={{ marginTop: '0.75rem' }}>
        <h1 style={{ marginTop: 0 }}>🔒 {title}</h1>
        <p>{text}</p>
        <Link to={meta.path} className="btn primary">
          과정 화면으로
        </Link>
      </div>
    </div>
  );
}
