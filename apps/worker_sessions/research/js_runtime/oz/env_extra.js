// Fills gaps jsdom doesn't implement that the Ozon challenge touches.
module.exports=function(w,base){
 const now=Date.now(), nav=now-1200, origin=performance.timeOrigin;
 const timing={navigationStart:nav,unloadEventStart:0,unloadEventEnd:0,redirectStart:0,redirectEnd:0,fetchStart:nav+5,domainLookupStart:nav+5,domainLookupEnd:nav+5,connectStart:nav+5,connectEnd:nav+30,secureConnectionStart:nav+10,requestStart:nav+31,responseStart:nav+90,responseEnd:nav+95,domLoading:nav+100,domInteractive:nav+300,domContentLoadedEventStart:nav+300,domContentLoadedEventEnd:nav+302,domComplete:nav+500,loadEventStart:nav+500,loadEventEnd:nav+505};
 timing.toJSON=function(){const o={};for(const k in this)if(k!=='toJSON')o[k]=this[k];return o};
 const entries=[];
 const mk=(type,name,startTime,duration=0,detail=null)=>({name,entryType:type,startTime,duration,detail,toJSON(){return {name,entryType:type,startTime,duration}}});
 const perf={timeOrigin:origin,timing,now:()=>performance.now(),
  mark(name,o){const e=mk('mark',name,o&&o.startTime!==undefined?o.startTime:performance.now());entries.push(e);return e},
  measure(name,a,b){const e=mk('measure',name,0,performance.now());entries.push(e);return e},
  getEntries:()=>entries.slice(),getEntriesByName:n=>entries.filter(e=>e.name===n),getEntriesByType:t=>entries.filter(e=>e.entryType===t),
  clearMarks(){},clearMeasures(){},toJSON(){return {timeOrigin:origin,timing:timing.toJSON()}}};
 base.performance=perf;
 perf.mark('jobStart',{startTime:Date.now()});
 base.visualViewport={width:1920,height:937,scale:1};
 base.isSecureContext=true;
 base.matchMedia=(q)=>({media:q,matches:/prefers-color-scheme:\s*light|prefers-reduced-motion:\s*no-preference|hover:\s*hover|pointer:\s*fine|any-hover:\s*hover|any-pointer:\s*fine/.test(q),onchange:null,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},dispatchEvent(){return false}});
};
