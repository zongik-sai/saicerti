import { Fragment } from 'react';
import { highlightLine } from './pyHighlight';

const MARK = /⟦(\d+)⟧/g;

export const countBlanks = (code: string) => [...code.matchAll(MARK)].length;

/** 빈칸 자리에 학생 답을 넣은 코드 */
export function fillBlanks(code: string, values: string[]): string {
  return code.replace(MARK, (_, n: string) => values[Number(n) - 1] ?? '');
}

interface Props {
  code: string;
  values: string[];
  onChange: (i: number, v: string) => void;
  disabled?: boolean;
  lang?: 'python' | 'c';
}

/** 빈칸 채우기 코드: 코드는 읽기 전용, 빈칸마다 입력 칸(입력 길이에 따라 넓어짐). */
export function BlankCode({ code, values, onChange, disabled, lang = 'python' }: Props) {
  const lines = code.split('\n');
  return (
    <div className="code-box">
      <pre className="blank-code" aria-label="빈칸 채우기 코드">
        {lines.map((line, li) => {
          const parts: React.ReactNode[] = [];
          let last = 0;
          for (const m of line.matchAll(MARK)) {
            const idx = m.index ?? 0;
            if (idx > last) parts.push(<Fragment key={`t${idx}`}>{highlightLine(line.slice(last, idx), `h${li}-${idx}`, lang)}</Fragment>);
            const n = Number(m[1]);
            const v = values[n - 1] ?? '';
            parts.push(
              <span key={`b${n}`}>
                <span className="bn" aria-hidden>
                  {n}
                </span>
                <input
                  aria-label={`빈칸 ${n}`}
                  value={v}
                  disabled={disabled}
                  spellCheck={false}
                  autoCapitalize="off"
                  autoCorrect="off"
                  autoComplete="off"
                  style={{ width: `${Math.max(6, v.length + 2)}ch` }}
                  onChange={(e) => onChange(n - 1, e.target.value.replace(/[\r\n]/g, ''))}
                />
              </span>,
            );
            last = idx + m[0].length;
          }
          if (last < line.length) parts.push(<Fragment key="end">{highlightLine(line.slice(last), `e${li}`, lang)}</Fragment>);
          return (
            <span className="ln" key={li}>
              {parts.length ? parts : ' '}
            </span>
          );
        })}
      </pre>
    </div>
  );
}
