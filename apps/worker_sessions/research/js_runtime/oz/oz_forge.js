// node oz_forge.js <vm_body.json> <template.json>  -> forged body JSON on stdout
// Decrypts the fp the VM produced in our fake env, keeps its dynamic fields, swaps the environment sections for a real-browser template.
const fs=require('fs');const codec=require('./fpcodec.js');
const body=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const tpl=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const d=codec.decode(body.fp,body.token);
let mine;{let t=d.json,i=t.length;while((i=t.lastIndexOf('}',i))>0){try{mine=JSON.parse(t.slice(0,i+1));break}catch(e){i--}}}
// Dynamic per-challenge fields, always taken from our VM run.
const KEEP=(process.env.KEEP||'challenge,ts,nonce,pzs,pzc').split(',');
// Build constants baked into the script bytecode itself (decoy browser id, function-source checks):
// stable across genuine captures of one build but differ between builds, so the template (another
// build) would send the wrong value. Our VM ran the CURRENT script, so its values are the right ones.
const VM_DERIVED=(process.env.VM_DERIVED||'browser_2,fn_1,fn_2,fn_3').split(',');
// per-build template: a genuine Chromium capture of the SAME script version (build constants such as browser_2 differ per build)
let base=tpl;
{const v=(mine.challenge&&mine.challenge.version)||'';const gf='raw/real_script_v'+v+'_0.json';
 if(fs.existsSync(gf)){const gb=JSON.parse(fs.readFileSync(gf,'utf8'));const gd=codec.decode(gb.fp,gb.token);let t=gd.json,i=t.length;while((i=t.lastIndexOf('}',i))>0){try{base=JSON.parse(t.slice(0,i+1));break}catch(e){i--}}}}
// The key set (schema) comes from OUR VM run — it always matches the build the server just served
// (builds add/drop sections: v47_4 had battery/storage/hev/media_devices, v47_2 dropped them).
// Values come from the genuine template where the key exists there; otherwise keep our VM's own.
const out={};for(const k of Object.keys(mine))out[k]=(KEEP.includes(k)||VM_DERIVED.includes(k)||!(k in base))?mine[k]:base[k];
// stack traces embed the script URL + build-specific offsets: take our VM's own and put the real URL in place of `evalmachine`
const ver=(mine.challenge&&mine.challenge.version)||'';
const url='https://st.ozone.ru/s3/abt-challenge/script_v'+ver+'.js';
for(const k of Object.keys(out)){ if(k in base&&JSON.stringify(base[k]).includes('script_v')&&!JSON.stringify(base[k]).includes('script_v'+ver+'.js')) out[k]=JSON.parse(JSON.stringify(mine[k]).replace(/evalmachine\.<anonymous>/g,url)); }
// the template's performance.timing holds absolute timestamps of the genuine capture day — rebase
// them onto this run (navigationStart ~1.2s before fp assembly, internal deltas preserved, zeros stay zero)
if(out.performance&&base.performance&&mine.ts){
  try{
    const p=JSON.parse(JSON.stringify(base.performance));
    const nav0=p['@proto:Performance']['@get:timing']['@proto:PerformanceTiming']['@get:navigationStart'];
    const shift=Math.round(mine.ts-1200-nav0);
    for(const tim of Object.values(p['@proto:Performance'])){ if(tim&&tim['@proto:PerformanceTiming'])for(const k of Object.keys(tim)){const v=tim[k];if(typeof v==='number'&&v>1e12)tim[k]=v+shift} }
    p['@proto:Performance']['@get:timeOrigin']+=shift;
    out.performance=p;
  }catch(e){console.error('perf rebase failed:',e.message)}
}
const json=JSON.stringify(out);
const salt=Buffer.from(Buffer.from(codec.split(body.fp).b64,'base64').subarray(8,16));
const chain=process.env.FORCE_CHAIN||d.chain; // md5-chain length depends on the challenge (genuine captures: 2/4/5 rounds), the VM derives it from the challenge
const fp=codec.encode(json,body.token,d.seed,salt,chain);
const nb=Object.assign({},body,{fp});if(process.env.TIMINGS_FROM_TPL)nb.timings=tpl.timings;
console.error('forge: version=%s chain=%s seed=%s keys=%d',ver,chain,d.seed,Object.keys(out).length);
process.stdout.write(JSON.stringify(nb));
