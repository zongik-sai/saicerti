import { Link } from 'react-router-dom';
import type { Course, Problem, TypeFile } from '../content/types';
import { KIND_LABEL } from '../content/types';
import { allAdvProblems, allProblems, courseMeta, typeKey } from '../content';
import { advGate, mockGate, solvedCount, tally, type CourseState } from '../features/progress/model';
import { useCourseProgress } from '../features/progress/store';
import { ExamCourseHome } from './ExamCourseHome';

interface Props {
  course: Course;
  learnerKey: string;
  remote: boolean;
  /** 선생님 미리 보기: 잠금 없이 모두 열림 */
  preview?: boolean;
}

export function CourseHome(props: Props) {
  if (courseMeta(props.course.id)?.style === 'exam') return <ExamCourseHome {...props} />;
  return <TypeCourseHome {...props} />;
}

function TypeCourseHome({ course, learnerKey, remote, preview = false }: Props) {
  const meta = courseMeta(course.id)!;
  const prog = useCourseProgress(learnerKey, course.id, remote);
  const ids = allProblems(course).map((p) => p.id);
  const advIds = allAdvProblems(course).map((p) => p.id);
  const t = tally(prog.state, ids);
  const advSolved = solvedCount(prog.state, advIds);
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
            기본 해결 {t.solved} / {ids.length}
          </strong>
          {advIds.length > 0 && <span className="adv-count">심화 해결 {advSolved} / {advIds.length}</span>}
        </div>
        <div className="bar" style={{ marginTop: '0.4rem' }} aria-hidden>
          <i style={{ width: `${ids.length ? (t.solved / ids.length) * 100 : 0}%` }} />
        </div>
        <p className="faint" style={{ margin: '0.5rem 0 0' }}>
          유형마다 <b>[기본] 5문제</b>는 꼭 풀고, <b className="adv-ink">[심화] 5문제</b>는 원하면 도전해요(그 유형의 기본 5문제를 모두 풀면 열 수 있어요). 문제마다 <b>① 중간 점검</b>(표 채우기·객관식)을 푼 뒤 <b>② {course.id === 'd2' ? '답 고르기(이론)·코드 풀이(데이터)' : '코드 풀이'}</b>로 자동 채점을 받아요. 기본 {ids.length}문제를 모두 풀면 맨 아래 <b>모의고사</b>가 열려요.
        </p>
        <p className="faint" style={{ margin: '0.4rem 0 0' }}>
          문제는 <b>전체화면 집중 풀이</b>로 풀어요. 푸는 중에 다른 창으로 가거나 전체화면을 나가면 잠기고, 한 유형에서 <b>3번</b> 잠기면 그 유형의 기록(기본·심화)이 처음으로 돌아가요.
        </p>
        {preview && (
          <p className="notice" style={{ margin: '0.5rem 0 0' }}>
            선생님 계정이라 심화·모의고사가 잠금 없이 열려 있어요. 학생에게는 조건을 채워야 열려요.
          </p>
        )}
        {prog.syncError && <p className="notice warn" style={{ margin: '0.5rem 0 0' }}>{prog.syncError}</p>}
      </div>

      <h2 style={{ marginTop: '1.4rem' }}>유형별 연습</h2>
      <div className="types" style={{ marginTop: '0.4rem' }}>
        {course.types.map((ty) => (
          <TypeCard key={ty.type} ty={ty} path={meta.path} state={prog.state} preview={preview} onOpen={() => prog.openAdv(typeKey(ty))} />
        ))}
      </div>
      {course.types.length < 10 && <p className="notice" style={{ marginTop: '1rem' }}>문제를 준비하고 있어요(지금 {course.types.length}개 유형).</p>}
      <Legend />

      <MockSection course={course} state={prog.state} ids={ids} preview={preview} />
    </div>
  );
}

/** 과정 화면 맨 아래 모의고사(기본 문제를 모두 풀면 열림) */
export function MockSection({ course, state, ids, preview }: { course: Course; state: CourseState; ids: string[]; preview: boolean }) {
  const meta = courseMeta(course.id)!;
  const solved = solvedCount(state, ids);
  const basicLeft = ids.length - solved;
  const t = { solved };
  const prog = { state };
  const word = meta.style === 'exam' ? '연습' : '기본';
  return (
    <>
      <h2 style={{ marginTop: '1.6rem' }}>모의고사</h2>
      <p className="faint" style={{ marginTop: 0 }}>
        {course.id === 'd2'
          ? `원본 기출 ${course.mocks[0]?.items.length ?? 20}문항과 같은 구성(객관식 이론 + pandas 코드) · 데이터는 같은 열 구조로 새로 만든 연습용 · 중간 점검 없이 실전처럼 · 결과는 시험을 끝낸 뒤 공개`
          : '원본 기출 10문항과 같은 유형·같은 코드(예시만 다름) · 중간 점검 없이 실전처럼 · 결과는 시험을 끝낸 뒤 공개'}
      </p>
      {basicLeft > 0 && !preview && (
        <p className="notice lock-note">
          🔒 {word} {ids.length}문제를 모두 풀면 모의고사가 열려요. 지금 {t.solved}/{ids.length} — {basicLeft}문제 남았어요.
        </p>
      )}
      <div className="mock-cards">
        {course.mocks.map((m) => {
          const st = prog.state.mocks?.[m.key];
          const open = mockGate(prog.state, ids, m.key, preview);
          if (!open)
            return (
              <div key={m.key} className="card mock-card locked" aria-disabled="true">
                <strong>🔒 모의고사 {m.n}회</strong>
                <span className="faint">{m.items.length}문항</span>
                <span className="mock-state">{word} 문제를 모두 풀면 열려요</span>
              </div>
            );
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
    </>
  );
}

export function chipState(state: CourseState, p: Problem) {
  const s = state.probs[p.id];
  const coding = s?.stepsDone || (s?.tries ?? 0) > 0;
  const cls = s?.solved ? 'solved' : coding ? 'coding' : s ? 'started' : '';
  const label = s?.solved ? '해결' : coding ? '코드 풀이 중' : s ? '중간 점검 중' : '시작 전';
  return { cls, label };
}

function TypeCard({ ty, path, state, preview, onOpen }: { ty: TypeFile; path: string; state: CourseState; preview: boolean; onOpen: () => void }) {
  const basicIds = ty.problems.map((p) => p.id);
  const basicSolved = solvedCount(state, basicIds);
  const adv = ty.adv?.problems ?? [];
  const gate = advGate(state, typeKey(ty), basicIds, preview);
  const advSolved = solvedCount(
    state,
    adv.map((p) => p.id),
  );
  return (
    <article className="card type-card">
      <div className="type-no">{String(ty.type).padStart(2, '0')}</div>
      <div>
        <h2>
          {ty.typeTitle} <span className={`badge ${ty.kind}`}>{KIND_LABEL[ty.kind]}</span>
        </h2>
        <p>{ty.intro}</p>
        <div className="tiers">
          <section className="tier basic" aria-label={`유형 ${ty.type} 기본 문제`}>
            <div className="tier-head">
              <span className="tier-name">[기본] 1~5</span>
              <span className="faint">
                {basicSolved}/{ty.problems.length}
              </span>
            </div>
            <div className="tier-list">
              {ty.problems.map((p, i) => {
                const { cls, label } = chipState(state, p);
                return (
                  <Link key={p.id} to={`${path}/${p.id}`} className={`prob-chip ${cls}`} title={`${p.title} · ${label}`}>
                    <span className="dot" aria-hidden />
                    <span>
                      {i + 1}. {p.title}
                    </span>
                    <span className="sr-only">({label})</span>
                  </Link>
                );
              })}
            </div>
          </section>
          {adv.length > 0 && (
            <section className={`tier adv ${gate}`} aria-label={`유형 ${ty.type} 심화 문제(선택)`}>
              <div className="tier-head">
                <span className="tier-name">[심화] 1~5</span>
                <span className="tier-opt">선택</span>
                <span className="faint" style={{ marginLeft: 'auto' }}>
                  {gate === 'open' ? `${advSolved}/${adv.length}` : '🔒'}
                </span>
              </div>
              {gate === 'locked' && <p className="tier-note">기본 5문제를 모두 풀면 열 수 있어요(지금 {basicSolved}/5).</p>}
              {gate === 'ready' && (
                <div className="tier-unlock">
                  <p className="tier-note">기본 5문제를 모두 풀었어요! 눌러서 심화 문제를 여세요.</p>
                  <button className="btn small adv-btn" onClick={onOpen}>
                    🔓 심화 열기
                  </button>
                </div>
              )}
              <div className="tier-list">
                {adv.map((p, i) => {
                  if (gate !== 'open')
                    return (
                      <span key={p.id} className="prob-chip adv locked" aria-disabled="true" title="아직 잠겨 있어요">
                        <span aria-hidden>🔒</span>
                        <span>
                          {i + 1}. {p.title}
                        </span>
                      </span>
                    );
                  const { cls, label } = chipState(state, p);
                  return (
                    <Link key={p.id} to={`${path}/${p.id}`} className={`prob-chip adv ${cls}`} title={`심화 ${i + 1} · ${p.title} · ${label}`}>
                      <span className="dot" aria-hidden />
                      <span>
                        {i + 1}. {p.title}
                      </span>
                      <span className="sr-only">(심화, {label})</span>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}
        </div>
      </div>
    </article>
  );
}

export function Legend({ adv = true }: { adv?: boolean }) {
  const chip = (cls: string) => (
    <span className={`prob-chip ${cls}`} style={{ minHeight: 0, padding: '0 0.3rem' }}>
      <span className="dot" />
    </span>
  );
  return (
    <div className="legend" aria-hidden>
      <span>{chip('')}시작 전</span>
      <span>{chip('started')}중간 점검 중</span>
      <span>{chip('coding')}코드 풀이 중</span>
      <span>{chip('solved')}해결</span>
      {adv && <span>{chip('adv')}심화(선택)</span>}
    </div>
  );
}
