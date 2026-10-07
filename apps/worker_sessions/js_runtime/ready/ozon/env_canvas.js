// Patches a jsdom window: real 2D canvas via @napi-rs/canvas, navigator overrides.
const {createCanvas}=require('@napi-rs/canvas');
module.exports=function(w,ua,extra={}){
 const back=new WeakMap();
 const proto=w.HTMLCanvasElement.prototype;
 const get=(el)=>{let b=back.get(el);if(!b){b=createCanvas(el.width||300,el.height||150);back.set(el,b)}
  if(b.width!==(el.width||300))b.width=el.width||300; if(b.height!==(el.height||150))b.height=el.height||150; return b};
 const LOG=process.env.CANVAS_LOG;
 proto.getContext=function(type,...rest){ if(LOG)console.error('getContext',type,JSON.stringify(rest)); if(type==='webgl'||type==='experimental-webgl'||type==='webgl2'){ if(!extra.webgl||type==='webgl2') return null; return require('./env_webgl.js')(this,LOG)} if(type!=='2d') return null; const c=get(this).getContext('2d'); if(!c.__patched){for(const m of ['arc','ellipse','isPointInPath','isPointInStroke']){const o=c[m].bind(c);c[m]=(...a)=>{if(m==='arc'&&a.length>5)a[5]=!!a[5];if(m==='ellipse'&&a.length>7)a[7]=!!a[7];return o(...a)}}c.__patched=true}
  if(!LOG) return c;
  return new Proxy(c,{get(t,k){const v=t[k];if(v===undefined)console.error('MISSING ctx.'+String(k));if(typeof v==='function')return (...a)=>{console.error('ctx.'+String(k),JSON.stringify(a).slice(0,150));return v.apply(t,a)};return v},set(t,k,v){console.error('ctx.'+String(k)+'=',String(v).slice(0,80));t[k]=v;return true}})};
 proto.toDataURL=function(...a){return get(this).toDataURL(...a)};
 const nav=w.navigator;
 const def=(k,v)=>Object.defineProperty(nav,k,{get:()=>v,configurable:true});
 def('userAgent',ua);def('appVersion',ua.replace(/^Mozilla\//,''));
 def('platform',extra.platform||'Win32');def('languages',['ru-RU','ru','en-US','en']);def('language','ru-RU');
 def('hardwareConcurrency',8);def('webdriver',false);def('vendor','');def('oscpu','Windows NT 10.0; Win64; x64');
 def('buildID','20181001000000');def('productSub','20100101');
};
