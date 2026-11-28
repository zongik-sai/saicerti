/* saicerti 파이썬 채점 워커(classic worker).
 * - 같은 사이트에 직접 올린 Pyodide(pyodide/)를 불러 학생 코드를 이 브라우저 안에서만 실행한다(서버로 보내지 않음).
 * - 무한 반복 등으로 멈추면 메인 화면이 이 워커를 끝내고(terminate) 새로 만든다.
 */
/* global importScripts, loadPyodide */
let py = null;
let runCases = null;
let runCasesC = null;
let initPromise = null;
let cPromise = null;
let ns = null;
let runDataFn = null;
const loadedPkgs = new Set();
const writtenFiles = new Set();

function init(base) {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const info = await (await fetch(base + 'pyodide/runtime.json', { cache: 'no-cache' })).json();
    importScripts(base + 'pyodide/pyodide.js');
    py = await loadPyodide({ indexURL: base + 'pyodide/', stdout: () => {}, stderr: () => {} });
    const src = await (await fetch(base + 'pyodide/harness.py?v=' + encodeURIComponent(info.harness))).text();
    ns = py.toPy({ __name__: 'saicerti_harness' });
    py.runPython(src, { globals: ns });
    runCases = ns.get('run_cases');
    return info;
  })();
  initPromise.catch(() => {
    initPromise = null;
  });
  return initPromise;
}

/** C 채점 준비: pycparser(wheel=zip)를 sys.path에, cinterp.py를 모듈 cinterp로 등록 */
function initC(base, info) {
  if (cPromise) return cPromise;
  cPromise = (async () => {
    const v = encodeURIComponent(info.cinterp || info.harness);
    const whl = new Uint8Array(await (await fetch(base + 'pyodide/' + info.pycparser)).arrayBuffer());
    py.FS.mkdirTree('/saicerti');
    py.FS.writeFile('/saicerti/pycparser.whl', whl);
    const src = await (await fetch(base + 'pyodide/cinterp.py?v=' + v)).text();
    py.FS.writeFile('/saicerti/cinterp.py', src);
    py.runPython("import sys\nfor p in ('/saicerti/pycparser.whl', '/saicerti'):\n    p in sys.path or sys.path.insert(0, p)\nimport cinterp");
    runCasesC = ns.get('run_cases_c');
  })();
  cPromise.catch(() => {
    cPromise = null;
  });
  return cPromise;
}

/** Data 과정: 필요한 패키지(pandas 등)를 같은 사이트의 pyodide/에서 불러오고, CSV(예시·숨은 데이터)를 /d2data/v<k>/에 써 둔다 */
async function initData(base, info, pkgs, files) {
  const need = (pkgs || []).filter((p) => !loadedPkgs.has(p));
  if (need.length) {
    await py.loadPackage(need, { messageCallback: () => {} });
    need.forEach((p) => loadedPkgs.add(p));
  }
  for (const f of files || []) {
    const key = f.name + '@' + f.v;
    if (writtenFiles.has(key)) continue;
    const stem = f.name.replace(/\.csv$/, '');
    const url = base + 'data/d2/' + stem + (f.v ? '.v' + f.v : '') + '.csv?v=' + encodeURIComponent(info.data || info.harness);
    const res = await fetch(url);
    if (!res.ok) throw new Error('데이터 파일을 불러오지 못했어요: ' + f.name);
    const buf = new Uint8Array(await res.arrayBuffer());
    py.FS.mkdirTree('/d2data/v' + f.v);
    py.FS.writeFile('/d2data/v' + f.v + '/' + f.name, buf);
    writtenFiles.add(key);
  }
  runDataFn = runDataFn || ns.get('run_data');
}

self.onmessage = async (e) => {
  const msg = e.data || {};
  try {
    if (msg.type === 'init') {
      const info = await init(msg.base);
      self.postMessage({ id: msg.id, ok: true, info });
    } else if (msg.type === 'run') {
      const info = await init(msg.base);
      let out;
      if (msg.lang === 'c') {
        await initC(msg.base, info);
        out = runCasesC(String(msg.code), String(msg.func), msg.cases, msg.mode || 'exact', msg.spec || '{}');
      } else {
        out = runCases(String(msg.code), String(msg.func), msg.cases, msg.mode || 'exact');
      }
      self.postMessage({ id: msg.id, ok: true, result: JSON.parse(out) });
    } else if (msg.type === 'initData') {
      const info = await init(msg.base);
      await initData(msg.base, info, msg.pkgs, msg.files);
      self.postMessage({ id: msg.id, ok: true });
    } else if (msg.type === 'runData') {
      await init(msg.base);
      const out = runDataFn(String(msg.code), msg.cases, msg.mode || 'float', 6000, true);
      self.postMessage({ id: msg.id, ok: true, result: JSON.parse(out) });
    } else if (msg.type === 'initC') {
      const info = await init(msg.base);
      await initC(msg.base, info);
      self.postMessage({ id: msg.id, ok: true });
    }
  } catch (err) {
    self.postMessage({ id: msg.id, ok: false, error: String((err && err.message) || err).slice(0, 600) });
  }
};
