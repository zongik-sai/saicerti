import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { COURSES, loadCourse } from '../../content';
import type { Course, CourseId } from '../../content/types';
import { sanitize, type CourseState } from '../progress/model';
import { supabase } from '../auth/supabase';
import { useRoles } from '../admin/roles';

interface Row {
  user_id: string;
  name: string | null;
  email: string | null;
  state: CourseState;
  updated_at: string;
}

/** 선생님 화면: 과정별 반 학습 현황(읽기만). 선생님 계정(am_i_teacher)만 자료를 읽는다. */
export function TeacherPage() {
  const roles = useRoles();
  const isTeacher = roles === null ? null : roles.teacher;
  const [cid, setCid] = useState<CourseId>('pyb');
  const [course, setCourse] = useState<Course | null>(null);
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isTeacher) return;
    let alive = true;
    setRows(null);
    setError(null);
    void loadCourse(cid).then((c) => alive && setCourse(c));
    const sb = supabase()!;
    void Promise.resolve(sb.rpc('course_class_overview', { p_course: cid })).then(({ data, error: e }) => {
      if (!alive) return;
      if (e) {
        setError(/알 수 없는 과목/.test(e.message) ? '서버에 이 과정이 아직 등록되지 않았어요(설정 SQL 실행 필요).' : `불러오지 못했어요: ${e.message}`);
        return;
      }
      setRows(((data as Row[]) ?? []).map((r) => ({ ...r, state: sanitize(r.state) })));
    });
    return () => {
      alive = false;
    };
  }, [isTeacher, cid]);

  if (isTeacher === null) return <div className="page" role="status">확인 중…</div>;
  if (!isTeacher)
    return (
      <div className="page narrow">
        <h1>선생님 화면</h1>
        <p className="muted">지정된 선생님 계정으로 로그인하면 반 학생들의 과정별 진도를 볼 수 있어요.</p>
        <Link className="btn" to="/">
          홈으로
        </Link>
      </div>
    );

  return (
    <div className="page">
      <h1>반 학습 현황</h1>
      <div className="row" role="tablist" style={{ margin: '0.6rem 0 1rem' }}>
        {COURSES.map((c) => (
          <button key={c.id} role="tab" aria-selected={cid === c.id} className={`btn small${cid === c.id ? ' primary' : ''}`} onClick={() => setCid(c.id)}>
            {c.name}
          </button>
        ))}
      </div>
      {error && <p className="notice bad">{error}</p>}
      {!error && (!rows || !course) && <p role="status">불러오는 중…</p>}
      {rows && course && rows.length === 0 && <p className="muted">아직 이 과정 기록이 없어요.</p>}
      {rows && course && rows.length > 0 && (
        <div className="scroll-x card" style={{ padding: 0 }}>
          <table className="t-table">
            <thead>
              <tr>
                <th>학생</th>
                <th>해결</th>
                {course.types.map((t) => (
                  <th key={t.type} title={t.typeTitle}>
                    유형 {t.type}
                  </th>
                ))}
                {course.mocks.map((m) => (
                  <th key={m.key} title={`모의고사 ${m.n}회: 해결 문항 수(끝낸 경우)`}>
                    모의 {m.n}
                  </th>
                ))}
                <th>채점 횟수</th>
                <th>답 확인</th>
                <th>마지막 기록</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const probs = r.state.probs;
                const total = course.types.reduce((n, t) => n + t.problems.filter((p) => probs[p.id]?.solved).length, 0);
                const tries = Object.values(probs).reduce((n, p) => n + p.tries, 0);
                const saw = Object.values(probs).filter((p) => p.sawAnswerAt).length;
                return (
                  <tr key={r.user_id}>
                    <td className="name">
                      {r.name || '(이름 없음)'}
                      <div className="faint">{r.email}</div>
                    </td>
                    <td>
                      <strong>{total}</strong>/{course.types.length * 5}
                    </td>
                    {course.types.map((t) => {
                      const s = t.problems.filter((p) => probs[p.id]?.solved).length;
                      const st = t.problems.filter((p) => probs[p.id]?.stepsDone).length;
                      return (
                        <td key={t.type} className={s === t.problems.length ? 'full' : s > 0 || st > 0 ? 'part' : ''} title={`해결 ${s}, 중간 점검 마침 ${st}`}>
                          {s}/{t.problems.length}
                        </td>
                      );
                    })}
                    {course.mocks.map((m) => {
                      const ms = r.state.mocks?.[m.key];
                      const sol = ms ? Object.values(ms.results).filter((x) => x.solved).length : 0;
                      return (
                        <td key={m.key} className={ms?.endedAt ? (sol === m.items.length ? 'full' : 'part') : ''} title={ms ? `${ms.round}번째 응시${ms.endedAt ? '' : ' · 진행 중'}` : '응시 전'}>
                          {!ms ? '-' : ms.endedAt ? `${sol}/${m.items.length}` : '진행 중'}
                        </td>
                      );
                    })}
                    <td>{tries}</td>
                    <td>{saw}</td>
                    <td>{new Date(r.updated_at).toLocaleString('ko-KR', { dateStyle: 'short', timeStyle: 'short' })}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="faint" style={{ marginTop: '0.75rem' }}>
        유형 칸 = 유형별 해결 문제 수(5문제 중), 모의 칸 = 모의고사 해결 문항 수(시험을 끝낸 경우). 점수는 학생 브라우저가 기록한 자기 학습 기록이며 평가 근거가 아니에요. 학생 코드는 서버에 저장하지 않아요.
      </p>
    </div>
  );
}
