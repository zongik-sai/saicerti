import type { Figure } from '../content/types';

/**
 * 문제 속 그림. 시험지의 이미지를 사진 대신 **데이터로 다시 그린다**(확대해도 선명, 다크 모드·화면 읽기 프로그램 대응).
 * - cells: 1차원 배열(위에 인덱스, 칸 강조·흐리게, 아래 표시, 칸 사이 화살표)
 * - grid: 2차원 배열·격자(행·열 머리, 칸 강조)
 * - table: 머리가 있는 표
 * - svg: 그 밖의 도형(트리·그래프 등). 안전하게 정리한 SVG만 넣는다
 */
export function FigureView({ fig }: { fig: Figure }) {
  return (
    <figure className="fig" role="group" aria-label={fig.alt}>
      {fig.kind === 'cells' && <Cells fig={fig} />}
      {fig.kind === 'grid' && <Grid fig={fig} />}
      {fig.kind === 'table' && <TableFig fig={fig} />}
      {fig.kind === 'svg' && <SvgFig fig={fig} />}
      {fig.caption && <figcaption>{fig.caption}</figcaption>}
    </figure>
  );
}

function Cells({ fig }: { fig: Extract<Figure, { kind: 'cells' }> }) {
  const n = fig.values.length;
  const idx = fig.index === 'auto' || fig.index === undefined ? fig.values.map((_, i) => i) : fig.index === 'auto1' ? fig.values.map((_, i) => i + 1) : fig.index;
  const hi = new Set(fig.highlight ?? []);
  const dim = new Set(fig.dim ?? []);
  const marks = new Map((fig.marks ?? []).map((m) => [m.at, m.label]));
  // 겹치지 않는 묶음·화살표는 같은 줄에(원본 그림처럼 한 줄로), 겹치면 아래 줄로
  const groupRows = packRows(fig.groups ?? []);
  const groupLevels = groupRows.reduce((m, x) => Math.max(m, x.row + 1), 0);
  const arrowRows = packRows(fig.arrows ?? []);
  return (
    <div className="fig-scroll">
      <div className="fig-cells" style={{ gridTemplateColumns: `repeat(${n}, minmax(2.4rem, auto))` }}>
        {idx.map((v, i) => (
          <div key={`i${i}`} className="fig-idx" aria-hidden>
            {v}
          </div>
        ))}
        {fig.values.map((v, i) => (
          <div key={`v${i}`} className={`fig-cell${hi.has(i) ? ' hi' : ''}${dim.has(i) ? ' dim' : ''}`}>
            {v}
          </div>
        ))}
        {marks.size > 0 &&
          fig.values.map((_, i) => (
            <div key={`m${i}`} className="fig-mark">
              {marks.get(i) ?? ''}
            </div>
          ))}
        {groupRows.map(({ g, row }, i) => (
          <div key={`g${i}`} className="fig-group" style={{ gridColumn: `${Math.min(g.from, g.to) + 1} / ${Math.max(g.from, g.to) + 2}`, gridRow: 4 + row }}>
            <span>{g.label}</span>
          </div>
        ))}
        {arrowRows.map(({ g: a, row }, i) => (
          <div key={`a${i}`} className={`fig-arrow ${a.both ? 'both' : a.to >= a.from ? 'right' : 'left'}`} style={{ gridColumn: `${Math.min(a.from, a.to) + 1} / ${Math.max(a.from, a.to) + 2}`, gridRow: 4 + groupLevels + row }}>
            <span>{a.label ?? ''}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function packRows<T extends { from: number; to: number }>(items: T[]): { g: T; row: number }[] {
  const ends: number[] = [];
  return items.map((g) => {
    const lo = Math.min(g.from, g.to);
    const hi = Math.max(g.from, g.to);
    let row = ends.findIndex((e) => e < lo);
    if (row < 0) {
      row = ends.length;
      ends.push(hi);
    } else ends[row] = hi;
    return { g, row };
  });
}

function Grid({ fig }: { fig: Extract<Figure, { kind: 'grid' }> }) {
  const hi = new Set((fig.highlight ?? []).map(([r, c]) => `${r},${c}`));
  const dim = new Set((fig.dim ?? []).map(([r, c]) => `${r},${c}`));
  return (
    <div className="fig-scroll">
      <table className="fig-grid">
        {fig.colLabels && (
          <thead>
            <tr>
              {fig.rowLabels && <th />}
              {fig.colLabels.map((c, i) => (
                <th key={i} scope="col">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {fig.rows.map((row, r) => (
            <tr key={r}>
              {fig.rowLabels && <th scope="row">{fig.rowLabels[r]}</th>}
              {row.map((v, c) => (
                <td key={c} className={`${hi.has(`${r},${c}`) ? 'hi' : ''}${dim.has(`${r},${c}`) ? ' dim' : ''}`}>
                  {v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TableFig({ fig }: { fig: Extract<Figure, { kind: 'table' }> }) {
  const hi = new Set(fig.highlight ?? []);
  return (
    <div className="fig-scroll">
      <table className="fig-grid fig-table">
        <thead>
          <tr>
            {fig.head.map((h, i) => (
              <th key={i} scope="col">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fig.rows.map((row, r) => (
            <tr key={r} className={hi.has(r) ? 'hi' : ''}>
              {row.map((v, c) => (
                <td key={c}>{v}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** SVG 정리: 스크립트·이벤트 속성·외부 링크·foreignObject를 지운다(문제 데이터는 저장소에서 오지만 한 번 더 막는다) */
export function cleanSvg(svg: string): string {
  return svg
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<foreignObject[\s\S]*?<\/foreignObject>/gi, '')
    .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/\s(xlink:)?href\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(/javascript:/gi, '');
}

function SvgFig({ fig }: { fig: Extract<Figure, { kind: 'svg' }> }) {
  return <div className="fig-svg fig-scroll" role="img" aria-label={fig.alt} dangerouslySetInnerHTML={{ __html: cleanSvg(fig.svg) }} />;
}
