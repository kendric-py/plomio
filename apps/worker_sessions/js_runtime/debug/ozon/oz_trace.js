const {JSDOM,VirtualConsole,CookieJar}=require('jsdom');const fs=require('fs');const vm=require('vm');
const UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const html=fs.readFileSync(process.argv[2]||'raw/challenge.html','utf8');
const dom=new JSDOM(html,{url:'https://www.ozon.ru/?__rr=1',pretendToBeVisual:true,userAgent:UA,virtualConsole:new VirtualConsole()});
const w=dom.window;const base={};
const SKIP=/^(Object|Array|Function|String|Number|Boolean|Symbol|Math|JSON|Date|RegExp|Error|Promise|Map|Set|WeakMap|WeakSet|Proxy|Reflect|Uint8Array|Uint32Array|Int32Array|Float64Array|ArrayBuffer|DataView|TypeError|globalThis|eval|parseInt|parseFloat|isNaN|undefined|NaN|Infinity)$/;
for(const k of Object.getOwnPropertyNames(w)){ if(SKIP.test(k)) continue; try{base[k]=typeof w[k]==='function'&&!/^[A-Z]/.test(k)?w[k].bind(w):w[k]}catch(e){} }
require('../../ready/ozon/env_canvas.js')(w,UA);require('../../ready/ozon/env_extra.js')(w,base);const log=[];const seen=new Set();
base.fetch=async(u,o)=>{log.push(['FETCH',u,o&&o.method,String(o&&o.body).slice(0,3000),JSON.stringify(o&&o.headers)]);try{const j=JSON.parse(o.body);if(j.error)console.log('ERRFIELD',j.error);console.log('FETCH',u,o.method,Object.entries(j).map(([k,v])=>k+'='+(typeof v==='string'?v.length+'ch:'+v.slice(0,40):JSON.stringify(v).slice(0,300))).join(' | '),'hdr',JSON.stringify(o.headers))}catch(e){console.log('FETCH',u)}
  return {ok:false,status:500,headers:{get:()=>null},json:async()=>({}),text:async()=>''}};
const NODEONLY=new Set(['process','Buffer','require','module','global','setImmediate','clearImmediate','fetch','WebAssembly','navigator','crypto','performance','structuredClone','queueMicrotask']);
const proxy=new Proxy(base,{
 get(t,k){ if(typeof k==='symbol') return t[k]; if(['window','self','globalThis','top','parent','frames'].includes(k)) return proxy;
   let v=t[k]; if(v===undefined&&!SKIP.test(k)&&k in w&&!NODEONLY.has(k)){v=w[k];if(typeof v==='function'&&!/^[A-Z]/.test(k)&&!SKIP.test(k))v=v.bind(w);t[k]=v} if(v===undefined&&k in globalThis&&!NODEONLY.has(k)) v=globalThis[k]; if(!seen.has(k)){seen.add(k);if(v===undefined)console.log('UNDEF global',k)} return v},
 set(t,k,v){t[k]=v;return true}});
const ctx=vm.createContext(proxy);
const t0=Date.now();
process.on('unhandledRejection',e=>console.log('UNHANDLED',e&&e.message));
try{vm.runInContext(fs.readFileSync(process.argv[3]||'raw/script_v47_4.js','utf8'),ctx,{timeout:20000})}catch(e){console.log('RUN ERR',e.message)}
setTimeout(()=>{console.log('cookie:',w.document.cookie,'elapsed',Date.now()-t0);process.exit(0)},8000);
