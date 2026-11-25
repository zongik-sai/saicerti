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
    } else if (msg.type === 'initC') {
      const info = await init(msg.base);
      await initC(msg.base, info);
      self.postMessage({ id: msg.id, ok: true });
    }
  } catch (err) {
    self.postMessage({ id: msg.id, ok: false, error: String((err && err.message) || err).slice(0, 600) });
  }
};
