// Offline only (no network): node oz_repeat.js <challenge.html> <script.js> [N=10]
// Runs the challenge VM N times on a saved challenge and checks whether oz_forge.js can decode + re-encode each body.
const cp=require('child_process'),fs=require('fs'),path=require('path');
const [html,script,n]=[process.argv[2],process.argv[3],+process.argv[4]||10];
const UA=process.env.UA||'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36';
const codec=require('../../ready/ozon/fpcodec.js');
let ok=0;
for(let i=0;i<n;i++){
  const r=cp.spawnSync('node',[path.join(__dirname,'../../ready/ozon/oz_solve.js'),html,script,UA],{encoding:'utf8',env:{...process.env,NOWEBGL:'1'},maxBuffer:1<<26});
  if(r.status){console.log(i,'VM FAIL',(r.stderr||'').slice(-120));continue}
  const body=JSON.parse(JSON.parse(r.stdout).body);
  const L=body.fp.length;
  try{const d=codec.decode(body.fp,body.token);const fpj=JSON.parse(d.json.slice(0,d.json.lastIndexOf('}')+1));ok++;console.log(i,'ok','fp len',L,'seed',d.seed,'checkStr',fpj.challenge.checkStr,'nonce',fpj.nonce,'ts',fpj.ts)}
  catch(e){
    const {seed}=codec.split(body.fp);
    console.log(i,'FAIL',e.message.slice(0,60),'fp len',L,'(len-4)%2',(L-4)%2,'seed?',JSON.stringify(seed),'tok len',body.token.length,'ends',body.fp.slice(-4),'has fp',!!body.fp)}
}
console.log('ok',ok,'of',n);
