// jsdom-backed environment, global = Proxy over jsdom window props (see trace.js findings)
const {JSDOM,VirtualConsole}=require('jsdom');
module.exports=function(UA,url='https://www.wildberries.ru/'){
 const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url,pretendToBeVisual:true,userAgent:UA,virtualConsole:new VirtualConsole()});
 const w=dom.window;const base={};
 const SKIP=/^(Object|Array|Function|String|Number|Boolean|Symbol|Math|JSON|Date|RegExp|Error|Promise|Map|Set|WeakMap|WeakSet|Proxy|Reflect|Uint8Array|Uint32Array|Int32Array|Float64Array|ArrayBuffer|DataView|TypeError|globalThis|eval|parseInt|parseFloat|isNaN|undefined|NaN|Infinity)$/;
 for(const k of Object.getOwnPropertyNames(w)){ if(SKIP.test(k)) continue; try{base[k]=typeof w[k]==='function'&&!/^[A-Z]/.test(k)?w[k].bind(w):w[k]}catch(e){} }
 const NODEONLY=new Set(['process','Buffer','require','module','global','setImmediate','clearImmediate','fetch','WebAssembly','navigator','crypto','performance','structuredClone','queueMicrotask']);
 const proxy=new Proxy(base,{
  get(t,k){ if(typeof k==='symbol') return t[k]; if(['window','self','globalThis','top','parent','frames'].includes(k)) return proxy;
    let v=t[k]; if(v===undefined&&k in globalThis&&!NODEONLY.has(k)) v=globalThis[k]; return v},
  set(t,k,v){t[k]=v;return true}});
 return {global:proxy,dom};
};
