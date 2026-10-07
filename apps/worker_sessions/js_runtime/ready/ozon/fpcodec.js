// Ozon antibot fp codec (reverse-engineered, script v47_x):
//   fp = b64("Salted__"+salt+AES256CBC(PKCS7(XOR(utf8(JSON), token)), EvpKDF-md5(pw)))  with 4-hex `seed` inserted at the middle of the b64 string
//   pw = md5-chain of `rounds` steps: a1=md5(seed), a2=md5(a1+token), then plain md5 up to `rounds` total.
// The VM picks `rounds` per challenge (observed in the wild: 2..5, genuine captures and jsdom alike;
// the server accepts any of them). Legacy names: v3=2 rounds, v4=4 rounds, v5=5 rounds.
const crypto=require('crypto');
const H=s=>crypto.createHash('md5').update(s).digest('hex');
const pwFor=(seed,token)=>H(H(H(H(seed)+token)));
const pwFor2=(seed,token)=>{const a0=H(seed),a1=H(a0+token),a2=H(a1);return H(a2)};
function chainPw(seed,token,rounds){let a=H(seed);if(rounds===1)return a;a=H(a+token);for(let i=2;i<rounds;i++)a=H(a);return a}
const CHAINS={};for(let r=1;r<=8;r++)CHAINS['r'+r]=(s,t)=>chainPw(s,t,r);
CHAINS.v3=(s,t)=>chainPw(s,t,2);CHAINS.v4=(s,t)=>chainPw(s,t,4);CHAINS.v5=(s,t)=>chainPw(s,t,5); // legacy aliases
function kdf(pw,salt){let d=Buffer.alloc(0),p=Buffer.alloc(0);while(d.length<48){p=crypto.createHash('md5').update(Buffer.concat([p,Buffer.from(pw),salt])).digest();d=Buffer.concat([d,p])}return {key:d.subarray(0,32),iv:d.subarray(32,48)}}
const xor=(b,tok)=>{const t=Buffer.from(tok,'latin1');const o=Buffer.alloc(b.length);for(let i=0;i<b.length;i++)o[i]=b[i]^t[i%t.length];return o};
function split(fp){const L=fp.length-4;const m=L/2;return {seed:fp.slice(m,m+4),b64:fp.slice(0,m)+fp.slice(m+4)}}
// chain a genuine browser uses per script build — OBSOLETE: captures show every build mixes 2/4/5-round
// chains per challenge, and the server accepts the VM's pick whatever it is. Kept for history.
const GENUINE={'47_4':'v4','47_3':'v5'};
function decode(fp,token,chain){const {seed,b64}=split(fp);const buf=Buffer.from(b64,'base64');
 const salt=buf.subarray(8,16);const ct=buf.subarray(16);let last;
 for(const name of (chain?[chain]:Object.keys(CHAINS))){
  try{const pw=CHAINS[name](seed,token);const {key,iv}=kdf(pw,salt);
   const c=crypto.createDecipheriv('aes-256-cbc',key,iv);const out=Buffer.concat([c.update(ct),c.final()]);
   const json=xor(out,token).toString('utf8');if(!json.startsWith('{"'))throw new Error('not json');
   return {seed,pw,salt,json,chain:name}}catch(e){last=e}}
 throw last}
function encode(json,token,seed,salt,chain){const pw=(CHAINS[chain||'v4'])(seed,token);const {key,iv}=kdf(pw,salt);
 const c=crypto.createCipheriv('aes-256-cbc',key,iv);const ct=Buffer.concat([c.update(xor(Buffer.from(json,'utf8'),token)),c.final()]);
 const b64=Buffer.concat([Buffer.from('Salted__'),salt,ct]).toString('base64');const m=b64.length/2; // original length excl. seed
 return b64.slice(0,m)+seed+b64.slice(m)}
module.exports={decode,encode,pwFor,split,GENUINE,chainPw};
if(require.main===module){const fs=require('fs');const b=JSON.parse(fs.readFileSync(__dirname+'/../../debug/ozon/fixtures/real_body.json','utf8'));
 const d=decode(b.fp,b.token);console.log('seed',d.seed,'chain',d.chain,'pw ok',d.pw===fs.readFileSync(__dirname+'/../../debug/ozon/fixtures/real_pw.txt','utf8'),'json len',d.json.length);
 let j;try{j=JSON.parse(d.json)}catch(e){console.log('json parse fail',e.message)}
 if(j){const re=encode(d.json,b.token,d.seed,d.salt,d.chain);console.log('roundtrip identical:',re===b.fp,re.length,b.fp.length)}}
