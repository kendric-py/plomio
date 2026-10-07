// usage: node solver.js <challenge.html> <challenge_script.js> <user-agent> [page-url]
// Runs the original Ozon challenge script in jsdom, intercepts its POST /abt/result,
// swaps the (non-browser) environment sections of the fingerprint for a real-Chrome capture,
// and prints {url, body} as JSON.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { JSDOM, VirtualConsole } = require('jsdom');
const codec = require('./codec');
const { patchCanvasAndNavigator, patchBrowserApis } = require('./env');

const DATA = path.join(__dirname, '..', 'data');
// Dynamic fields, produced by the VM itself; everything else comes from the real-browser capture.
const KEEP_FROM_VM = ['challenge', 'ts', 'nonce', 'pzs', 'pzc'];
const GLOBALS_SKIP = /^(Object|Array|Function|String|Number|Boolean|Symbol|Math|JSON|Date|RegExp|Error|Promise|Map|Set|WeakMap|WeakSet|Proxy|Reflect|Uint8Array|Uint32Array|Int32Array|Float64Array|ArrayBuffer|DataView|TypeError|globalThis|eval|parseInt|parseFloat|isNaN|undefined|NaN|Infinity)$/;
const NODE_ONLY = new Set(['process', 'Buffer', 'require', 'module', 'global', 'setImmediate', 'clearImmediate', 'fetch', 'WebAssembly', 'navigator', 'crypto', 'performance', 'structuredClone', 'queueMicrotask']);

function captureChallengeRequest(html, scriptSource, ua, pageUrl) {
  const dom = new JSDOM(html, { url: pageUrl, pretendToBeVisual: true, virtualConsole: new VirtualConsole() });
  const w = dom.window;
  const base = {};
  for (const k of Object.getOwnPropertyNames(w)) {
    if (GLOBALS_SKIP.test(k)) continue;
    try {
      base[k] = typeof w[k] === 'function' && !/^[A-Z]/.test(k) ? w[k].bind(w) : w[k];
    } catch (e) { /* getter threw */ }
  }
  patchCanvasAndNavigator(w, ua);
  patchBrowserApis(base);
  base.console = new Proxy({}, { get: () => () => {} });

  return new Promise((resolve, reject) => {
    base.fetch = (url, opts) => { resolve({ url, body: opts && opts.body }); return new Promise(() => {}); };
    const proxy = new Proxy(base, {
      get(t, k) {
        if (typeof k === 'symbol') return t[k];
        if (['window', 'self', 'globalThis', 'top', 'parent', 'frames'].includes(k)) return proxy;
        let v = t[k];
        if (v === undefined && !GLOBALS_SKIP.test(k) && k in w && !NODE_ONLY.has(k)) {
          v = w[k];
          if (typeof v === 'function' && !/^[A-Z]/.test(k)) v = v.bind(w);
          t[k] = v;
        }
        if (v === undefined && k in globalThis && !NODE_ONLY.has(k)) v = globalThis[k];
        return v;
      },
      set(t, k, v) { t[k] = v; return true; },
    });
    try {
      vm.runInContext(scriptSource, vm.createContext(proxy), { timeout: 20000 });
    } catch (e) { reject(e); }
    setTimeout(() => reject(new Error('challenge script made no request in 15s')), 15000);
  });
}

function forge(vmBody) {
  const body = JSON.parse(vmBody);
  const dec = codec.decode(body.fp, body.token);
  const mine = codec.parseTrailing(dec.json);
  const version = (mine.challenge && mine.challenge.version) || '';

  // Prefer a genuine capture of the SAME script build (build constants differ per build).
  let template = JSON.parse(fs.readFileSync(path.join(DATA, 'template_chrome154.json'), 'utf8'));
  const perBuild = path.join(DATA, `real_script_v${version}_0.json`);
  if (fs.existsSync(perBuild)) {
    const cap = JSON.parse(fs.readFileSync(perBuild, 'utf8'));
    template = codec.parseTrailing(codec.decode(cap.fp, cap.token).json);
  }

  const out = {};
  for (const k of Object.keys(template)) {
    out[k] = KEEP_FROM_VM.includes(k) && k in mine ? mine[k] : template[k];
  }

  // Stack traces embed the script URL: put the real one in place of jsdom's `evalmachine`.
  const scriptUrl = `https://st.ozone.ru/s3/abt-challenge/script_v${version}.js`;
  for (const k of Object.keys(out)) {
    const tpl = JSON.stringify(template[k]);
    if (k in mine && tpl.includes('script_v') && !tpl.includes(`script_v${version}.js`)) {
      out[k] = JSON.parse(JSON.stringify(mine[k]).replace(/evalmachine\.<anonymous>/g, scriptUrl));
    }
  }
  const salt = Buffer.from(Buffer.from(codec.splitSeed(body.fp).b64, 'base64').subarray(8, 16));
  const fp = codec.encode(JSON.stringify(out), body.token, dec.seed, salt, dec.chain);
  return JSON.stringify({ ...body, fp });
}

async function main() {
  const [htmlPath, scriptPath, ua, pageUrl = 'https://www.ozon.ru/?__rr=1'] = process.argv.slice(2);
  const req = await captureChallengeRequest(
    fs.readFileSync(htmlPath, 'utf8'), fs.readFileSync(scriptPath, 'utf8'), ua, pageUrl,
  );
  process.stdout.write(JSON.stringify({ url: req.url, body: forge(req.body) }));
  process.exit(0);
}

main().catch((e) => { console.error((e && e.stack) || e); process.exit(1); });
