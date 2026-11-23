import type { Course, CourseId, MockSet, Problem, TypeFile } from './types';

export interface CourseMeta {
  id: CourseId;
  name: string;
  exam: string;
  blurb: string;
  path: string;
}

/** 과정 목록. ID(pyb·pya)는 진도 저장 키라 바꾸지 않는다. */
export const COURSES: CourseMeta[] = [
  {
    id: 'pyb',
    name: '프로그래밍 Python 기본',
    exam: 'COS Pro 2급 Python 대비',
    blurb: '반복문·조건문·리스트로 푸는 10가지 시험 유형. 빈칸 채우기, 한 줄 수정, 함수 작성을 단계별로 연습해요.',
    path: '/basic',
  },
  {
    id: 'pya',
    name: '프로그래밍 Python 심화',
    exam: 'COS Pro 1급 Python 대비',
    blurb: '정렬 기준, 슬라이싱, 함수 나누기, 시뮬레이션처럼 한 단계 깊은 10가지 시험 유형을 연습해요.',
    path: '/advanced',
  },
];

export const courseMeta = (id: string): CourseMeta | undefined => COURSES.find((c) => c.id === id);
export const courseByPath = (path: string): CourseMeta | undefined => COURSES.find((c) => c.path === path);

const loaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/t*.json', { import: 'default' }),
};

const mockLoaders: Record<CourseId, Record<string, () => Promise<TypeFile>>> = {
  pyb: import.meta.glob<TypeFile>('./pyb/mock/t*.json', { import: 'default' }),
  pya: import.meta.glob<TypeFile>('./pya/mock/t*.json', { import: 'default' }),
};

export const MOCK_SETS = 3;

/** 유형별 모의고사 파일(문제 3개: 1·2·3회) → 회별 묶음 */
export function buildMocks(files: TypeFile[]): MockSet[] {
  const sorted = files.filter((t) => t && Array.isArray(t.problems)).sort((a, b) => a.type - b.type);
  return Array.from({ length: MOCK_SETS }, (_, i) => ({
    n: i + 1,
    key: `m${i + 1}`,
    items: sorted.filter((t) => t.problems[i]).map((t) => ({ type: t, problem: t.problems[i] })),
  }));
}

const cache = new Map<CourseId, Promise<Course>>();

/** 과정의 문제를 불러온다(과정마다 한 번, 필요할 때). */
export function loadCourse(id: CourseId): Promise<Course> {
  let p = cache.get(id);
  if (!p) {
    const meta = courseMeta(id)!;
    p = Promise.all([Promise.all(Object.values(loaders[id]).map((l) => l())), Promise.all(Object.values(mockLoaders[id]).map((l) => l()))]).then(([types, mocks]) => ({
      id,
      name: meta.name,
      exam: meta.exam,
      blurb: meta.blurb,
      types: types.filter((t) => t && Array.isArray(t.problems)).sort((a, b) => a.type - b.type),
      mocks: buildMocks(mocks),
    }));
    cache.set(id, p);
    p.catch(() => cache.delete(id));
  }
  return p;
}

export function findProblem(course: Course, pid: string): { type: TypeFile; problem: Problem; index: number } | null {
  for (const t of course.types) {
    const i = t.problems.findIndex((p) => p.id === pid);
    if (i >= 0) return { type: t, problem: t.problems[i], index: i };
  }
  return null;
}

export const allProblems = (course: Course): Problem[] => course.types.flatMap((t) => t.problems);
