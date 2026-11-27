// 화면 전체 점검: 모든 문제를 실제 화면에서 중간 점검(정답 입력) → 코드(정답) → 채점까지 진행해 '모든 테스트 통과'를 확인한다.
// 사용: npm run dev (다른 창) → node scripts/check-all-ui.cjs <스크린샷 폴더> <pyb|pya|cb> [adv] [문제 id...]
//   adv: [심화] 문제(adv/tNN.json)를 점검한다. 이때 기본 문제를 모두 푼 것으로·심화를 모두 연 것으로 데모 기록을 미리 넣는다.
// Playwright 브라우저가 설치된 환경에서 실행한다.
const { chromium } = require('playwright');
const fs = require('fs');
// src/components/Steps.tsx optionOrder와 같아야 한다(보기 섞기)
function optionOrder(options, seed, fixed = false) {
  const idx = options.map((_, i) => i);
  if (fixed) return idx;
  if (options.every((o) => /^-?\d+(\.\d+)?$/.test(o.trim()))) return idx.sort((a, b) => Number(options[a]) - Number(options[b]));
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) h = Math.imul(h ^ seed.charCodeAt(i), 16777619) >>> 0;
  for (let i = idx.length - 1; i > 0; i--) {
    h = Math.imul(h ^ (h >>> 15), 2246822507) >>> 0;
    const j = h % (i + 1);
    [idx[i], idx[j]] = [idx[j], idx[i]];
  }
  return idx;
}
(async () => {
  const [S, course, ...rest] = process.argv.slice(2);
  const adv = rest[0] === 'adv';
  const pids = adv ? rest.slice(1) : rest;
  const root = require('path').join(__dirname, '..', 'src', 'content', course, adv ? 'adv' : '');
  const files = fs.readdirSync(root).filter((f) => f.endsWith('.json')).sort();
  const probs = [];
  for (const f of files) { const d = JSON.parse(fs.readFileSync(root + '/' + f, 'utf8')); for (const p of d.problems) probs.push({ ...p, kind: d.kind }); }
  const target = pids.length ? probs.filter((p) => pids.includes(p.id)) : probs;
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1360, height: 900 } });
  const errs = [];
  page.on('pageerror', (e) => errs.push('pageerror ' + e.message));
  await page.goto('http://localhost:5174/');
  await page.getByRole('button', { name: '개발용 데모로 둘러보기' }).click();
  if (adv) {
    const now = new Date().toISOString();
    const probs = {};
    for (let t = 1; t <= 10; t++) for (const l of 'abcde') probs[`${course}-t${String(t).padStart(2, '0')}-${l}`] = { ver: 99, steps: [], stepsDone: true, solved: true, tries: 1, lastAt: now };
    const advOpen = Array.from({ length: 10 }, (_, i) => `t${String(i + 1).padStart(2, '0')}`);
    await page.evaluate(([k, v]) => localStorage.setItem(k, v), [`saicerti:v1:demo:${course}`, JSON.stringify({ state: { v: 1, probs, advOpen }, revision: 0 })]);
    await page.reload();
  }
  const path = { pyb: 'basic', pya: 'advanced', cb: 'c-basic' }[course];
  const results = [];
  for (const p of target) {
    const t0 = Date.now();
    try {
      await page.goto(`http://localhost:5174/#/${path}/${p.id}`);
      await page.waitForSelector('.statement');
      for (let i = 0; i < p.steps.length; i++) {
        const s = p.steps[i];
        if (s.kind === 'mcq') {
          await page.locator('.opt').nth(optionOrder(s.options, `${p.id}:${s.id}`, /[①②③④⑤]|번째 보기|마지막 보기|첫 보기/.test(s.q + s.explain)).indexOf(s.answer)).click();
        } else if (s.kind === 'table') {
          const cells = s.rows.flat().filter((c) => typeof c === 'object');
          const inputs = page.locator('.trace input');
          for (let k = 0; k < cells.length; k++) await inputs.nth(k).fill(cells[k].a);
        } else {
          await page.locator('.short-input').fill(s.a);
        }
        await page.getByRole('button', { name: '확인', exact: true }).click();
        await page.locator('.explain').waitFor({ timeout: 3000 });
        await page.getByRole('button', { name: i === p.steps.length - 1 ? '코드 풀러 가기 →' : '다음 단계 →' }).click();
      }
      if (p.kind === 'blank') {
        const inputs = page.locator('.blank-code input');
        for (let k = 0; k < p.blanks.length; k++) await inputs.nth(k).fill(p.blanks[k].answer);
      } else {
        await page.locator('.cm-content').click();
        await page.keyboard.press('Control+A');
        await page.keyboard.press('Delete');
        await page.keyboard.insertText(p.solution);
      }
      await page.getByRole('button', { name: '채점하기' }).click();
      await page.locator('.res-head strong').waitFor({ timeout: 60000 });
      const head = await page.locator('.res-head strong').innerText();
      const ok = head.includes('모든 테스트 통과');
      if (!ok || pids.length) await page.screenshot({ path: `${S}/${p.id}.png`, fullPage: true });
      results.push(`${ok ? '✓' : '✗'} ${p.id} ${head} (${Date.now() - t0}ms)`);
    } catch (e) {
      await page.screenshot({ path: `${S}/${p.id}-err.png`, fullPage: true }).catch(() => {});
      results.push(`✗ ${p.id} ERROR ${String(e.message).split('\n')[0]}`);
    }
  }
  console.log(results.join('\n'));
  console.log('ERRS', errs.slice(0, 5));
  await b.close();
})();
