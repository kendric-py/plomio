// Brute-force the md5-chain length on failed fp captures: node brute_chain.js [file...]
const crypto=require('crypto');const fs=require('fs');
const H=s=>crypto.createHash('md5').update(s).digest('hex');
function kdf(pw,salt){let d=Buffer.alloc(0),p=Buffer.alloc(0);while(d.length<48){p=crypto.createHash('md5').update(Buffer.concat([p,Buffer.from(pw),salt])).digest();d=Buffer.concat([d,p])}return {key:d.subarray(0,32),iv:d.subarray(32,48)}}
const xor=(b,tok)=>{const t=Buffer.from(tok,'latin1');const o=Buffer.alloc(b.length);for(let i=0;i<b.length;i++)o[i]=b[i]^t[i%t.length];return o};
// chain recipe: a1=md5(seed); a2=md5(a1+token); then plain md5 iterations up to `rounds` total
function chainPw(seed,token,rounds){let a=H(seed);if(rounds===1)return a;a=H(a+token);for(let i=2;i<rounds;i++)a=H(a);return a}
const files=process.argv.slice(2).length?process.argv.slice(2):fs.readdirSync('raw').filter(f=>f.startsWith('failed_body_')).map(f=>'raw/'+f);
for(const f of files){
  const b=JSON.parse(fs.readFileSync(f,'utf8'));
  const fp=b.fp;const L=fp.length-4;const m=Math.floor(L/2);
  const seed=fp.slice(m,m+4);const b64=fp.slice(0,m)+fp.slice(m+4);
  const buf=Buffer.from(b64,'base64');const salt=buf.subarray(8,16);const ct=buf.subarray(16);
  let found=null;
  for(let r=1;r<=12;r++){
    try{const {key,iv}=kdf(chainPw(seed,b.token,r),salt);
    const c=crypto.createDecipheriv('aes-256-cbc',key,iv);const out=Buffer.concat([c.update(ct),c.final()]);
    const json=xor(out,b.token).toString('utf8');if(json.startsWith('{"')){found=r;break}}catch(e){}
  }
  console.log(f,'-> rounds:',found,'(token len '+b.token.length+')');
}
