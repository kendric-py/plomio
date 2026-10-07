// Fills what jsdom lacks and the challenge touches: real 2D canvas (@napi-rs/canvas),
// navigator overrides, performance timeline, visualViewport, matchMedia.
const { createCanvas } = require('@napi-rs/canvas');

function patchCanvasAndNavigator(w, ua) {
  const backing = new WeakMap();
  const proto = w.HTMLCanvasElement.prototype;
  const canvasOf = (el) => {
    let b = backing.get(el);
    if (!b) { b = createCanvas(el.width || 300, el.height || 150); backing.set(el, b); }
    if (b.width !== (el.width || 300)) b.width = el.width || 300;
    if (b.height !== (el.height || 150)) b.height = el.height || 150;
    return b;
  };
  proto.getContext = function (type) {
    if (type !== '2d') return null; // no WebGL: a stub breaks fp computation
    const ctx = canvasOf(this).getContext('2d');
    if (!ctx.__patched) {
      // napi-canvas wants a boolean where browsers accept 0/1
      for (const [m, idx] of [['arc', 5], ['ellipse', 7]]) {
        const orig = ctx[m].bind(ctx);
        ctx[m] = (...a) => { if (a.length > idx) a[idx] = !!a[idx]; return orig(...a); };
      }
      ctx.__patched = true;
    }
    return ctx;
  };
  proto.toDataURL = function (...a) { return canvasOf(this).toDataURL(...a); };

  const nav = w.navigator;
  const def = (k, v) => Object.defineProperty(nav, k, { get: () => v, configurable: true });
  def('userAgent', ua);
  def('appVersion', ua.replace(/^Mozilla\//, ''));
  def('platform', 'Win32');
  def('languages', ['ru-RU', 'ru', 'en-US', 'en']);
  def('language', 'ru-RU');
  def('hardwareConcurrency', 8);
  def('webdriver', false);
  def('vendor', '');
}

function patchBrowserApis(base) {
  const nav = Date.now() - 1200;
  const timing = {
    navigationStart: nav, unloadEventStart: 0, unloadEventEnd: 0, redirectStart: 0, redirectEnd: 0,
    fetchStart: nav + 5, domainLookupStart: nav + 5, domainLookupEnd: nav + 5, connectStart: nav + 5,
    connectEnd: nav + 30, secureConnectionStart: nav + 10, requestStart: nav + 31, responseStart: nav + 90,
    responseEnd: nav + 95, domLoading: nav + 100, domInteractive: nav + 300,
    domContentLoadedEventStart: nav + 300, domContentLoadedEventEnd: nav + 302, domComplete: nav + 500,
    loadEventStart: nav + 500, loadEventEnd: nav + 505,
  };
  const timingJson = () => ({ ...timing });
  timing.toJSON = timingJson;
  const entries = [];
  const entry = (type, name, startTime, duration = 0) => ({
    name, entryType: type, startTime, duration, detail: null,
    toJSON() { return { name, entryType: type, startTime, duration }; },
  });
  base.performance = {
    timeOrigin: performance.timeOrigin,
    timing,
    now: () => performance.now(),
    mark(name, o) {
      const e = entry('mark', name, o && o.startTime !== undefined ? o.startTime : performance.now());
      entries.push(e);
      return e;
    },
    measure(name) { const e = entry('measure', name, 0, performance.now()); entries.push(e); return e; },
    getEntries: () => entries.slice(),
    getEntriesByName: (n) => entries.filter((e) => e.name === n),
    getEntriesByType: (t) => entries.filter((e) => e.entryType === t),
    clearMarks() {},
    clearMeasures() {},
    toJSON() { return { timeOrigin: performance.timeOrigin, timing: timingJson() }; },
  };
  base.performance.mark('jobStart', { startTime: Date.now() });
  base.visualViewport = { width: 1920, height: 937, scale: 1 };
  base.isSecureContext = true;
  const MEDIA = /prefers-color-scheme:\s*light|prefers-reduced-motion:\s*no-preference|hover:\s*hover|pointer:\s*fine/;
  base.matchMedia = (q) => ({
    media: q, matches: MEDIA.test(q), onchange: null,
    addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent: () => false,
  });
}

module.exports = { patchCanvasAndNavigator, patchBrowserApis };
