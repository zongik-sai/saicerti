import type { ReactNode } from 'react';

const KW = new Set(['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'and', 'or', 'break', 'continue', 'pass', 'import', 'from', 'as', 'True', 'False', 'None', 'lambda', 'is', 'global', 'del', 'try', 'except', 'class', 'with', 'yield']);
const BUILTIN = new Set(['len', 'range', 'print', 'max', 'min', 'sum', 'sorted', 'list', 'int', 'str', 'abs', 'enumerate', 'zip', 'map', 'float', 'round', 'set', 'dict', 'tuple', 'append', 'sort', 'join', 'split', 'count', 'index', 'reverse', 'pop', 'insert', 'remove', 'extend', 'keys', 'values', 'items', 'isdigit', 'upper', 'lower', 'strip', 'replace', 'find', 'any', 'all', 'ord', 'chr', 'bool', 'divmod', 'pow']);
const TOKEN = /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/gm;

/** 아주 간단한 파이썬 색칠(한 줄 단위). 실행에는 영향 없음. */
export function highlightLine(line: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  TOKEN.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = TOKEN.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const [t, com, str, num, word] = m;
    const k = `${key}-${n++}`;
    if (com) out.push(<span key={k} className="tok-com">{t}</span>);
    else if (str) out.push(<span key={k} className="tok-str">{t}</span>);
    else if (num) out.push(<span key={k} className="tok-num">{t}</span>);
    else if (word && KW.has(word)) out.push(<span key={k} className="tok-kw">{t}</span>);
    else if (word && BUILTIN.has(word)) out.push(<span key={k} className="tok-fn">{t}</span>);
    else out.push(t);
    last = m.index + t.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

export function CodeView({ code, className = 'sol-code' }: { code: string; className?: string }) {
  return (
    <pre className={className}>
      <code>
        {code.split('\n').map((l, i) => (
          <span key={i} style={{ display: 'block' }}>
            {highlightLine(l, `c${i}`)}
            {l === '' ? ' ' : null}
          </span>
        ))}
      </code>
    </pre>
  );
}
