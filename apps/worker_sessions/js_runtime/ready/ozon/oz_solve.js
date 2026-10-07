// usage: node oz_solve.js <challenge.html> <script.js> [UA] [url]  -> JSON of the first fetch() the challenge makes
const {JSDOM,VirtualConsole}=require('jsdom');const fs=require('fs');const vm=require('vm');
const t0=process.hrtime.bigint();
const UA=process.argv[4]||'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const html=fs.readFileSync(process.argv[2],'utf8');
const dom=new JSDOM(html,{url:process.argv[5]||'https://www.ozon.ru/?__rr=1',pretendToBeVisual:true,virtualConsole:new VirtualConsole()});
const w=dom.window;const base={};
const SKIP=/^(Object|Array|Function|String|Number|Boolean|Symbol|Math|JSON|Date|RegExp|Error|Promise|Map|Set|WeakMap|WeakSet|Proxy|Reflect|Uint8Array|Uint32Array|Int32Array|Float64Array|ArrayBuffer|DataView|TypeError|globalThis|eval|parseInt|parseFloat|isNaN|undefined|NaN|Infinity)$/;
for(const k of Object.getOwnPropertyNames(w)){ if(SKIP.test(k)) continue; try{base[k]=typeof w[k]==='function'&&!/^[A-Z]/.test(k)?w[k].bind(w):w[k]}catch(e){} }
require('./env_canvas.js')(w,UA,{webgl:!process.env.NOWEBGL});require('./env_extra.js')(w,base);
base.console=new Proxy({log:(...a)=>{if(String(a[0]).startsWith('__ENC__')&&process.env.ENCOUT)fs.writeFileSync(process.env.ENCOUT,String(a[0]).slice(7))}},{get:(t,k)=>k in t?t[k]:()=>{}});
let done=false;
base.fetch=(u,o)=>{ if(!done){done=true;console.log(JSON.stringify({url:u,method:o&&o.method,body:o&&o.body,ms:Number(process.hrtime.bigint()-t0)/1e6,rss:process.memoryUsage().rss}));setTimeout(()=>process.exit(0),0)} return new Promise(()=>{}) };
const NODEONLY=new Set(['process','Buffer','require','module','global','setImmediate','clearImmediate','fetch','WebAssembly','navigator','crypto','performance','structuredClone','queueMicrotask']);
const proxy=new Proxy(base,{
 get(t,k){ if(typeof k==='symbol') return t[k]; if(['window','self','globalThis','top','parent','frames'].includes(k)) return proxy;
   let v=t[k]; if(v===undefined&&!SKIP.test(k)&&k in w&&!NODEONLY.has(k)){v=w[k];if(typeof v==='function'&&!/^[A-Z]/.test(k))v=v.bind(w);t[k]=v} if(v===undefined&&k in globalThis&&!NODEONLY.has(k)) v=globalThis[k]; return v},
 set(t,k,v){t[k]=v;return true}});
process.on('unhandledRejection',e=>{console.error('UNHANDLED',e&&e.message);});
const ctx=vm.createContext(proxy);if(process.env.HOOK){vm.runInContext(fs.readFileSync(__dirname+'/../../debug/ozon/hook.js','utf8').replace(/window\./g,'globalThis.'),ctx)}
base.fetch=(u,o)=>{ if(!done){done=true;console.log(JSON.stringify({url:u,method:o&&o.method,body:o&&o.body,js:process.env.HOOK?ctx.__js:undefined,enc:ctx.__enc,blk:ctx.__blk,ms:Number(process.hrtime.bigint()-t0)/1e6,rss:process.memoryUsage().rss}));setTimeout(()=>process.exit(0),0)} return new Promise(()=>{}) };
if(process.env.FIXED_TS){vm.runInContext('Date.now=function(){return '+Number(process.env.FIXED_TS)+'};(function(){var s=12345;Math.random=function(){s=(s*1103515245+12345)%2147483648;return s/2147483648}})()',ctx)}
try{vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),ctx,{timeout:20000})}catch(e){console.error('RUN ERR',e.message);process.exit(1)}
setTimeout(()=>{console.error('TIMEOUT no fetch');process.exit(3)},15000);
