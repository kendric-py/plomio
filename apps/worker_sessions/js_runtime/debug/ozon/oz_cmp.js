// Offline only: node oz_cmp.js -- compare genuine v47_3 fp captures (Chromium) with the v47_4 template
const fs=require('fs');const codec=require('../../ready/ozon/fpcodec.js');
function load(f){const b=JSON.parse(fs.readFileSync(f,'utf8'));const d=codec.decode(b.fp,b.token);let t=d.json,i=t.length,fp;while((i=t.lastIndexOf('}',i))>0){try{fp=JSON.parse(t.slice(0,i+1));break}catch(e){i--}}return {b,fp,d}}
const files=fs.readdirSync('raw').filter(f=>/^real_script_v47_3_\d\.json$/.test(f));
const G=[];for(const f of files){try{G.push(load('raw/'+f))}catch(e){console.log('decode fail',f,e.message.slice(0,50))}}
console.log('decoded',G.length,'of',files.length,'chains',G.map(g=>g.d.chain).join(','));
const T=JSON.parse(fs.readFileSync('template_chrome154.json','utf8'));
const g0=G[0].fp;
console.log('keys genuine v3 :',Object.keys(g0).join(','));
console.log('keys template v4:',Object.keys(T).join(','));
console.log('only genuine:',Object.keys(g0).filter(k=>!(k in T)),'only template:',Object.keys(T).filter(k=>!(k in g0)));
for(const k of Object.keys(g0)){const s=G.map(g=>JSON.stringify(g.fp[k]));const same=s.every(x=>x===s[0]);const ts=JSON.stringify(T[k]);
 console.log(k.padEnd(14),'len',String(s[0].length).padStart(6),'stable:',same?'Y':'n','eq template:',ts===s[0]?'Y':'n','tpl len',ts===undefined?'-':ts.length)}
