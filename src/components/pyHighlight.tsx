import type { ReactNode } from 'react';

const KW = new Set(['def', 'return', 'if', 'elif', 'else', 'for', 'while', 'in', 'not', 'and', 'or', 'break', 'continue', 'pass', 'import', 'from', 'as', 'True', 'False', 'None', 'lambda', 'is', 'global', 'del', 'try', 'except', 'class', 'with', 'yield']);
const BUILTIN = new Set(['len', 'range', 'print', 'max', 'min', 'sum', 'sorted', 'list', 'int', 'str', 'abs', 'enumerate', 'zip', 'map', 'float', 'round', 'set', 'dict', 'tuple', 'append', 'sort', 'join', 'split', 'count', 'index', 'reverse', 'pop', 'insert', 'remove', 'extend', 'keys', 'values', 'items', 'isdigit', 'upper', 'lower', 'strip', 'replace', 'find', 'any', 'all', 'ord', 'chr', 'bool', 'divmod', 'pow']);
const C_KW = new Set(['int', 'char', 'double', 'float', 'long', 'short', 'unsigned', 'signed', 'void', 'bool', 'size_t', 'const', 'static', 'struct', 'typedef', 'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default', 'break', 'continue', 'sizeof', 'true', 'false', 'NULL', 'enum', 'union', 'goto']);
const C_FN = new Set(['printf', 'scanf', 'malloc', 'calloc', 'realloc', 'free', 'strlen', 'strcpy', 'strncpy', 'strcat', 'strcmp', 'strncmp', 'strchr', 'strstr', 'memset', 'memcpy', 'abs', 'atoi', 'qsort', 'sqrt', 'pow', 'toupper', 'tolower', 'isdigit', 'isalpha', 'isupper', 'islower', 'isspace', 'puts', 'putchar', 'sprintf']);
const TOKEN_C = /(\/\/.*$|#\s*\w+.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/gm;
const TOKEN = /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/gm;

/** 아주 간단한 파이썬 색칠(한 줄 단위). 실행에는 영향 없음. */
export function highlightLine(line: string, key: string, lang: 'python' | 'c' = 'python'): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  const re = lang === 'c' ? TOKEN_C : TOKEN;
  const kw = lang === 'c' ? C_KW : KW;
  const fn = lang === 'c' ? C_FN : BUILTIN;
  re.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m.index > last) out.push(line.slice(last, m.index));
    const [t, com, str, num, word] = m;
    const k = `${key}-${n++}`;
    if (com) out.push(<span key={k} className="tok-com">{t}</span>);
    else if (str) out.push(<span key={k} className="tok-str">{t}</span>);
    else if (num) out.push(<span key={k} className="tok-num">{t}</span>);
    else if (word && kw.has(word)) out.push(<span key={k} className="tok-kw">{t}</span>);
    else if (word && fn.has(word)) out.push(<span key={k} className="tok-fn">{t}</span>);
    else out.push(t);
    last = m.index + t.length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

export function CodeView({ code, className = 'sol-code', lang = 'python' }: { code: string; className?: string; lang?: 'python' | 'c' }) {
  return (
    <pre className={className}>
      <code>
        {code.split('\n').map((l, i) => (
          <span key={i} style={{ display: 'block' }}>
            {highlightLine(l, `c${i}`, lang)}
            {l === '' ? ' ' : null}
          </span>
        ))}
      </code>
    </pre>
  );
}
