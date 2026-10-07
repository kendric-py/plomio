// Light runtime: run WB challenge script in a bare node:vm context (no jsdom) with a minimal browser env.
// usage: node solve_vm.js <script.js> <payload.txt> [UA]  -> JSON {solution, ms}
const fs=require('fs'),vm=require('vm');
const t0=process.hrtime.bigint();
const UA=process.argv[4]||'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const env=require('./env_min.js')(UA);
const ctx=vm.createContext(env.global);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
const sym=Object.getOwnPropertySymbols(env.global).find(s=>typeof env.global[s]==='function');
const t1=process.hrtime.bigint();
Promise.resolve(env.global[sym](fs.readFileSync(process.argv[3],'utf8').trim())).then(r=>{
 console.log(JSON.stringify({solution:r,ms:Number(process.hrtime.bigint()-t1)/1e6,load_ms:Number(t1-t0)/1e6,rss:process.memoryUsage().rss}));process.exit(0)},
 e=>{let c=e,m=[];while(c){m.push(c.message);c=c.cause}console.error('ERR',m.join(' <- '));process.exit(1)});
