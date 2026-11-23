import { useEffect, useState, type ReactNode } from 'react';
import { HashRouter, Link, Navigate, NavLink, Route, Routes, useLocation, useParams } from 'react-router-dom';
import { COURSES, courseMeta, findProblem, loadCourse, type CourseMeta } from '../content';
import type { Course } from '../content/types';
import { useAuth } from '../features/auth/AuthContext';
import { isDemoEnabled, isSupabaseConfigured, BASE_URL } from '../lib/config';
import { forgetLearner, useCourseProgress } from '../features/progress/store';
import { CourseHome } from './CourseHome';
import { ProblemPage } from './ProblemPage';
import { TeacherPage } from '../features/teacher/TeacherPage';
import { AdminPage } from '../features/admin/AdminPage';
import { useRoles } from '../features/admin/roles';
import { tally } from '../features/progress/model';

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
  const { identity, signOut, exitDemo } = useAuth();
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

function SignIn({ next }: { next: string }) {
  const { signIn, startDemo, authError, clearError, expired, status } = useAuth();
  if (status === 'loading') return <div className="page" role="status">불러오는 중…</div>;
  return (
    <div className="card" style={{ maxWidth: 520 }}>
      <h2>로그인하고 시작해요</h2>
      <p className="muted">학교 Google 계정으로 로그인하면 푼 문제와 중간 점검 기록이 저장되어 어느 기기에서나 이어서 할 수 있어요.</p>
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
  return (
    <div className="page">
      <section className="hero">
        <h1>자격증 코딩, 손으로 따라가고 코드로 확인해요</h1>
        <p className="muted" style={{ maxWidth: '44rem' }}>
          COS Pro Python 시험 유형마다 비슷한 연습 문제 5개. 먼저 표를 채우며 코드를 손으로 따라가 보고, 그다음 직접 코드를 고치거나 작성해 자동 채점을 받아요. 코드는 내 브라우저 안에서만 실행돼요.
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
            {identity && <CourseBar meta={c} learnerKey={identity.learnerKey} remote={identity.kind === 'user'} />}
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
        <div>프로그래밍 C 기본 (COS Pro 2급 C)</div>
        <div>프로그래밍 C 심화 (COS Pro 1급 C)</div>
        <div>Data 2급 · Data 1급</div>
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
  const solved = tally(prog.state, Object.keys(prog.state.probs)).solved;
  return (
    <div>
      <div className="faint">해결 {solved} / 50</div>
      <div className="bar" aria-hidden>
        <i style={{ width: `${(solved / 50) * 100}%` }} />
      </div>
    </div>
  );
}

function CourseRoute({ meta }: { meta: CourseMeta }) {
  const { identity, status } = useAuth();
  const loc = useLocation();
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
  if (!identity)
    return (
      <div className="page narrow">
        <div className="crumb">
          <Link to="/">홈</Link> › {meta.name}
        </div>
        <h1>{meta.name}</h1>
        <SignIn next={loc.pathname} />
      </div>
    );
  if (err) return <div className="page notice bad">문제를 불러오지 못했어요. 새로고침해 주세요.</div>;
  if (!course || course.id !== meta.id) return <div className="page" role="status">문제 불러오는 중…</div>;
  return (
    <Routes>
      <Route index element={<CourseHome course={course} learnerKey={identity.learnerKey} remote={identity.kind === 'user'} />} />
      <Route path=":pid" element={<ProblemRoute course={course} learnerKey={identity.learnerKey} remote={identity.kind === 'user'} />} />
    </Routes>
  );
}

function ProblemRoute({ course, learnerKey, remote }: { course: Course; learnerKey: string; remote: boolean }) {
  const { pid = '' } = useParams();
  const f = findProblem(course, pid);
  if (!f) return <Navigate to={courseMeta(course.id)!.path} replace />;
  return <ProblemPage course={course} type={f.type} problem={f.problem} index={f.index} learnerKey={learnerKey} remote={remote} />;
}
