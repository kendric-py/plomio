// run challenge script in a vm context whose global is a logging Proxy over jsdom window props
const {JSDOM}=require('jsdom');const fs=require('fs');const vm=require('vm');
const UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'https://www.wildberries.ru/',pretendToBeVisual:true,userAgent:UA});
const w=dom.window;
const base={};
for(const k of Object.getOwnPropertyNames(w)){ if(/^(Object|Array|Function|String|Number|Boolean|Symbol|Math|JSON|Date|RegExp|Error|Promise|Map|Set|WeakMap|WeakSet|Proxy|Reflect|Uint8Array|Uint32Array|Int32Array|Float64Array|ArrayBuffer|DataView|TypeError|globalThis|eval|parseInt|parseFloat|isNaN|undefined|NaN|Infinity)$/.test(k)) continue;
 try{base[k]=typeof w[k]==='function'&&!/^[A-Z]/.test(k)?w[k].bind(w):w[k]}catch(e){} }
const log=new Map();const NODEONLY=new Set(['process','Buffer','require','module','global','setImmediate','clearImmediate','fetch','WebAssembly','navigator','crypto','performance','structuredClone','queueMicrotask']);
const proxy=new Proxy(base,{
 get(t,k){ if(typeof k==='symbol') return t[k]; if(k==='window'||k==='self'||k==='globalThis'||k==='top'||k==='parent'||k==='frames') return proxy; let v=t[k]; if(v===undefined && k in globalThis && !NODEONLY.has(k)) v=globalThis[k]; log.set('get '+k+(v===undefined?' (UNDEF)':''),1); return v},
 has(t,k){ return k in t},
 set(t,k,v){t[k]=v;return true}
});
const ctx=vm.createContext(proxy);
const src=fs.readFileSync(process.argv[2],'utf8');
vm.runInContext(src,ctx);
const sym=Object.getOwnPropertySymbols(base).find(s=>typeof base[s]==='function');
console.log('sym',String(sym));
Promise.resolve(base[sym](fs.readFileSync(process.argv[3],'utf8').trim())).then(r=>console.log('OK',String(r).slice(0,200)),e=>{let c=e;while(c){console.log('ERR',c.message);c=c.cause}}).finally(()=>{console.log([...log.keys()].join('\n'));process.exit(0)});
