// usage: node solve.js <scriptfile> <payloadfile>  -> prints JSON {solution, ms}
const {JSDOM}=require('jsdom');const fs=require('fs');
const UA=process.env.UA||'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0';
const dom=new JSDOM('<!doctype html><html><head></head><body></body></html>',{url:'https://www.wildberries.ru/',runScripts:'outside-only',pretendToBeVisual:true,userAgent:UA});
const w=dom.window;
if(fs.existsSync(__dirname+'/env.js')) require('./env.js')(w);
const t0=Date.now();
w.eval(fs.readFileSync(process.argv[2],'utf8'));
const payload=fs.readFileSync(process.argv[3],'utf8').trim();
const sym=Object.getOwnPropertySymbols(w).find(s=>typeof w[s]==='function'&&!String(s).includes('webidl2js'));
if(!sym){console.error('no solver fn');process.exit(2)}
const t1=Date.now();
Promise.resolve(w[sym](payload)).then(r=>{console.log(JSON.stringify({solution:r,ms:Date.now()-t1,load_ms:t1-t0,rss:process.memoryUsage().rss}));process.exit(0)},e=>{
  let c=e;while(c){console.error('ERR:',c.message);console.error(String(c.stack).split('\n').slice(0,5).join('\n'));c=c.cause}
  process.exit(1)});
