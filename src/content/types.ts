/** 문제 데이터 형식(docs/CONTENT_SCHEMA.md). 검수: python3 tools/validate.py */
export type CourseId = 'pyb' | 'pya';
export type ProblemKind = 'blank' | 'fix' | 'write';
export type CompareMode = 'exact' | 'float';
export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

export interface Case {
  args: Json[];
  expected: Json;
}
export interface Example extends Case {
  explain?: string;
}

export interface InputCell {
  a: string;
  alts?: string[];
}
export type TableCell = string | InputCell;

export type Step =
  | { id: string; kind: 'mcq'; q: string; options: string[]; answer: number; explain: string }
  | { id: string; kind: 'table'; title?: string; prompt: string; columns: string[]; rows: TableCell[][]; check?: string; explain: string }
  | { id: string; kind: 'short'; q: string; a: string; alts?: string[]; check?: string; explain: string };

export interface Problem {
  id: string;
  version: number;
  title: string;
  statement: string;
  params: string[];
  returns: string[];
  funcName: string;
  argNames: string[];
  examples: Example[];
  code: string;
  blanks?: { answer: string; alts?: string[] }[];
  bugLine?: number;
  solution: string;
  tests: Case[];
  compare?: CompareMode;
  inputCheck?: string;
  steps: Step[];
  explain: string;
}

export interface TypeFile {
  course: CourseId;
  type: number;
  typeTitle: string;
  kind: ProblemKind;
  skills: string[];
  intro: string;
  problems: Problem[];
}

/** 모의고사 한 회: 원본 유형 1~10이 한 문제씩(같은 유형의 1·2·3회는 예시·테스트만 다름) */
export interface MockItem {
  type: TypeFile;
  problem: Problem;
}
export interface MockSet {
  n: number;
  key: string;
  items: MockItem[];
}

export interface Course {
  id: CourseId;
  name: string;
  exam: string;
  blurb: string;
  types: TypeFile[];
  mocks: MockSet[];
}

export const KIND_LABEL: Record<ProblemKind, string> = {
  blank: '빈칸 채우기',
  fix: '한 줄 수정',
  write: '함수 작성',
};

export const KIND_TASK: Record<ProblemKind, string> = {
  blank: '빈칸을 채워 코드를 완성해요.',
  fix: '틀린 한 줄만 고쳐요(두 줄 이상 바꾸면 채점하지 않아요).',
  write: 'solution 함수를 직접 작성해요.',
};
