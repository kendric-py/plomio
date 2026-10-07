const {JSDOM}=require('jsdom');const fs=require('fs');
const UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'https://www.wildberries.ru/',runScripts:'outside-only',pretendToBeVisual:true,userAgent:UA});
const w=dom.window;
const before=new Set(Object.getOwnPropertyNames(w));
const src=fs.readFileSync(process.argv[2]||'../../ready/wb/cache_438ddd46c1de1715.js','utf8');
const t0=Date.now();
try{w.eval(src);}catch(e){console.log('EVAL ERR',e&&e.stack||e)}
setTimeout(()=>{
 const added=Object.getOwnPropertyNames(w).filter(k=>!before.has(k));
 console.log('syms',Object.getOwnPropertySymbols(w).map(String));console.log('added',added.map(k=>k+':'+typeof w[k]),Date.now()-t0);
 process.exit(0)},1500);
