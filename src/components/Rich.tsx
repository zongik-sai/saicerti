import { Fragment, type ReactNode } from 'react';
import type { Figure } from '../content/types';
import { FigureView } from './Figure';

const FIG = /^\s*\{\{fig:([\w-]+)\}\}\s*$/;

/** 인라인: `코드`, **굵게** */
export function inline(text: string, keyBase = 'i'): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let n = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const t = m[0];
    if (t.startsWith('`')) out.push(<code key={`${keyBase}${n++}`}>{t.slice(1, -1)}</code>);
    else out.push(<strong key={`${keyBase}${n++}`}>{t.slice(2, -2)}</strong>);
    last = m.index + t.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** 문제 설명: 문단(빈 줄), 줄바꿈, '- ' 글머리표, 한 줄짜리 {{fig:ID}} = 그림 */
export function Rich({ text, className = 'rich', figures }: { text: string; className?: string; figures?: Figure[] }) {
  const blocks = text.replace(/\r/g, '').split(/\n{2,}/);
  return (
    <div className={className}>
      {blocks.map((b, i) => {
        const lines = b.split('\n');
        const items: ReactNode[] = [];
        let list: string[] = [];
        const flush = (k: string) => {
          if (list.length) {
            items.push(
              <ul key={k}>
                {list.map((l, j) => (
                  <li key={j}>{inline(l.replace(/^\s*[-•]\s+/, ''), `l${j}-`)}</li>
                ))}
              </ul>,
            );
            list = [];
          }
        };
        let para: string[] = [];
        const flushPara = (k: string) => {
          if (para.length) {
            items.push(
              <p key={k}>
                {para.map((l, j) => (
                  <Fragment key={j}>
                    {j > 0 && <br />}
                    {inline(l, `p${j}-`)}
                  </Fragment>
                ))}
              </p>,
            );
            para = [];
          }
        };
        lines.forEach((l, j) => {
          const fm = FIG.exec(l);
          if (fm) {
            flushPara(`p${j}`);
            flush(`u${j}`);
            const fig = figures?.find((f) => f.id === fm[1]);
            items.push(fig ? <FigureView key={`f${j}`} fig={fig} /> : <p key={`f${j}`} className="faint">[그림 {fm[1]}]</p>);
          } else if (/^\s*[-•]\s+/.test(l)) {
            flushPara(`p${j}`);
            list.push(l);
          } else {
            flush(`u${j}`);
            para.push(l);
          }
        });
        flushPara('pe');
        flush('ue');
        return <Fragment key={i}>{items}</Fragment>;
      })}
    </div>
  );
}

/** 글머리표 목록(매개변수 설명 등) */
export function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="rich" style={{ margin: 0, paddingLeft: '1.2rem' }}>
      {items.map((t, i) => (
        <li key={i}>{inline(t.replace(/^\s*[-•]\s+/, ''), `b${i}-`)}</li>
      ))}
    </ul>
  );
}
