// 화면 전체 점검: 모든 문제를 실제 화면에서 중간 점검(정답 입력) → 코드(정답) → 채점까지 진행해 '모든 테스트 통과'를 확인한다.
// 사용: npm run dev (다른 창) → node scripts/check-all-ui.cjs <스크린샷 폴더> <pyb|pya> [문제 id...]
// Playwright 브라우저가 설치된 환경에서 실행한다.
const { chromium } = require('playwright');
const fs = require('fs');
// 사용: node flow.cjs <shots dir> <course> <pid...>  (pid 생략 시 전체)
(async () => {
  const [S, course, ...pids] = process.argv.slice(2);
  const root = require('path').join(__dirname, '..', 'src', 'content', course);
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
  const path = course === 'pyb' ? 'basic' : 'advanced';
  const results = [];
  for (const p of target) {
    const t0 = Date.now();
    try {
      await page.goto(`http://localhost:5174/#/${path}/${p.id}`);
      await page.waitForSelector('.statement');
      for (let i = 0; i < p.steps.length; i++) {
        const s = p.steps[i];
        if (s.kind === 'mcq') {
          await page.locator('.opt').nth(s.answer).click();
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
