import { Link } from 'react-router-dom';
import type { Course } from '../content/types';
import { KIND_LABEL } from '../content/types';
import { allProblems, courseMeta } from '../content';
import { tally } from '../features/progress/model';
import { useCourseProgress } from '../features/progress/store';

export function CourseHome({ course, learnerKey, remote }: { course: Course; learnerKey: string; remote: boolean }) {
  const meta = courseMeta(course.id)!;
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const ids = allProblems(course).map((p) => p.id);
  const t = tally(prog.state, ids);
  return (
    <div className="page narrow">
      <div className="crumb">
        <Link to="/">홈</Link> › {meta.name}
      </div>
      <div className="exam faint" style={{ color: 'var(--accent)', fontWeight: 600 }}>
        {meta.exam}
      </div>
      <h1>{meta.name}</h1>
      <p className="muted">{meta.blurb}</p>
      <div className="card" style={{ marginTop: '0.75rem' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <strong>
            해결 {t.solved} / {ids.length}
          </strong>
          <span className="faint">중간 점검 마침 {t.stepsDone}</span>
        </div>
        <div className="bar" style={{ marginTop: '0.4rem' }} aria-hidden>
          <i style={{ width: `${ids.length ? (t.solved / ids.length) * 100 : 0}%` }} />
        </div>
        <p className="faint" style={{ margin: '0.5rem 0 0' }}>
          유형마다 비슷한 문제 5개. 문제마다 <b>① 중간 점검</b>(표 채우기·객관식)을 푼 뒤 <b>② 코드 풀이</b>로 자동 채점을 받아요.
        </p>
        {prog.syncError && <p className="notice warn" style={{ margin: '0.5rem 0 0' }}>{prog.syncError}</p>}
      </div>
      <h2 style={{ marginTop: '1.4rem' }}>모의고사</h2>
      <p className="faint" style={{ marginTop: 0 }}>
        원본 기출 10문항과 같은 유형·같은 코드(예시만 다름) · 중간 점검 없이 실전처럼 · 결과는 시험을 끝낸 뒤 공개
      </p>
      <div className="mock-cards">
        {course.mocks.map((m) => {
          const st = prog.state.mocks?.[m.key];
          const solvedN = st ? Object.values(st.results).filter((r) => r.solved).length : 0;
          const label = !m.items.length ? '준비 중' : !st ? '시작 전' : st.endedAt ? `해결 ${solvedN}/${m.items.length}` : `진행 중 · 제출 ${Object.keys(st.results).length}/${m.items.length}`;
          return (
            <Link key={m.key} to={`${meta.path}/mock/${m.n}`} className={`card mock-card${st?.endedAt ? ' done' : st ? ' going' : ''}`}>
              <strong>모의고사 {m.n}회</strong>
              <span className="faint">{m.items.length}문항</span>
              <span className="mock-state">{label}</span>
            </Link>
          );
        })}
      </div>
      <h2 style={{ marginTop: '1.4rem' }}>유형별 연습</h2>
      <div className="types" style={{ marginTop: '0.4rem' }}>
        {course.types.map((ty) => (
          <article className="card type-card" key={ty.type}>
            <div className="type-no">{String(ty.type).padStart(2, '0')}</div>
            <div>
              <h2>
                {ty.typeTitle} <span className={`badge ${ty.kind}`}>{KIND_LABEL[ty.kind]}</span>
              </h2>
              <p>{ty.intro}</p>
              <div className="probs">
                {ty.problems.map((p, i) => {
                  const s = prog.state.probs[p.id];
                  const coding = s?.stepsDone || (s?.tries ?? 0) > 0;
                  const cls = s?.solved ? 'solved' : coding ? 'coding' : s ? 'started' : '';
                  const label = s?.solved ? '해결' : coding ? '코드 풀이 중' : s ? '중간 점검 중' : '시작 전';
                  return (
                    <Link key={p.id} to={`${meta.path}/${p.id}`} className={`prob-chip ${cls}`} title={`${p.title} · ${label}`}>
                      <span className="dot" aria-hidden />
                      <span>
                        {i + 1}. {p.title}
                      </span>
                      <span className="sr-only">({label})</span>
                    </Link>
                  );
                })}
              </div>
            </div>
          </article>
        ))}
      </div>
      {course.types.length < 10 && <p className="notice" style={{ marginTop: '1rem' }}>문제를 준비하고 있어요(지금 {course.types.length}개 유형).</p>}
      <div className="legend" aria-hidden>
        <span>
          <span className="prob-chip" style={{ minHeight: 0, padding: '0 0.3rem' }}>
            <span className="dot" />
          </span>
          시작 전
        </span>
        <span>
          <span className="prob-chip started" style={{ minHeight: 0, padding: '0 0.3rem' }}>
            <span className="dot" />
          </span>
          중간 점검 중
        </span>
        <span>
          <span className="prob-chip coding" style={{ minHeight: 0, padding: '0 0.3rem' }}>
            <span className="dot" />
          </span>
          코드 풀이 중
        </span>
        <span>
          <span className="prob-chip solved" style={{ minHeight: 0, padding: '0 0.3rem' }}>
            <span className="dot" />
          </span>
          해결
        </span>
      </div>
    </div>
  );
}
