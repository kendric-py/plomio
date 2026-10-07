// Warm solver: JSON lines on stdin {id,script,payload,ua} -> JSON lines on stdout {id,solution,ms}
const fs=require('fs'),vm=require('vm'),readline=require('readline');
const mk=require('./env_min.js');
const cache=new Map();
const rl=readline.createInterface({input:process.stdin});
rl.on('line',async line=>{
 const q=JSON.parse(line);const t0=process.hrtime.bigint();
 try{
  let src=cache.get(q.script); if(!src){src=fs.readFileSync(q.script,'utf8');cache.set(q.script,new vm.Script(src))}
  const sc=cache.get(q.script)||src;
  const env=mk(q.ua);const ctx=vm.createContext(env.global);
  (sc instanceof vm.Script?sc:new vm.Script(sc)).runInContext(ctx);
  const sym=Object.getOwnPropertySymbols(env.global).find(s=>typeof env.global[s]==='function');
  const sol=await env.global[sym](q.payload);
  env.dom.window.close();
  console.log(JSON.stringify({id:q.id,solution:sol,ms:Number(process.hrtime.bigint()-t0)/1e6,rss:process.memoryUsage().rss}));
 }catch(e){let c=e,m=[];while(c){m.push(c.message);c=c.cause}console.log(JSON.stringify({id:q.id,error:m.join(' <- ')}))}
});
