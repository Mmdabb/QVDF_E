// Read-only static DOM substitute: executes only the inline dashboard handlers.
// No browser, URL, server, layout engine or network is used.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const filename=process.argv[2]||'debug/full_experiment/steps/11_episode_time_series/traffic_parameters.html';
const html=fs.readFileSync(filename,'utf8');
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const decode=s=>s.replace(/&quot;/g,'"').replace(/&#x27;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class Element{
 constructor(tag,attrs={}){this.tag=tag;this.attrs=attrs;this.children=[];this.parentElement=null;this.handlers={};this.hidden='hidden'in attrs;this.checked='checked'in attrs;this.dataset={};for(const[k,v]of Object.entries(attrs))if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,l)=>l.toUpperCase())]=v;}
 appendChild(child){if(child.parentElement){const c=child.parentElement.children,i=c.indexOf(child);if(i>=0)c.splice(i,1);}this.children.push(child);child.parentElement=this;return child;}
 get rows(){return this.children.filter(e=>e.tag==='tr');}get tBodies(){return this.children.filter(e=>e.tag==='tbody');}
 get value(){if(this._value!==undefined)return this._value;if(this.tag==='select')return this.querySelector('option')?.attrs.value||'';return this.attrs.value||'';}set value(v){this._value=v;}
 get textContent(){return this._text!==undefined?this._text:this.children.map(e=>e.textContent).join('');}set textContent(s){this._text=s;}
 getAttribute(k){return this.attrs[k]??null;}setAttribute(k,v){this.attrs[k]=v;}
 addEventListener(event,cb){(this.handlers[event]??=[]).push(cb);}emit(event){for(const cb of this.handlers[event]||[])cb({target:this});}
 descendants(){return this.children.flatMap(e=>[e,...e.descendants()]);}
 querySelectorAll(selector){const parts=selector.split(/\s+/);return this.descendants().filter(e=>{if(!matches(e,parts.at(-1)))return false;let p=e.parentElement;for(let i=parts.length-2;i>=0;i--){while(p&&!matches(p,parts[i]))p=p.parentElement;if(!p)return false;p=p.parentElement;}return true;});}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function matches(e,s){const attr=s.match(/^\[([^=]+)="([^"]*)"\]$/);if(attr)return e.attrs[attr[1]]===attr[2];const m=s.match(/^([\w-]+)?(?:\.([\w-]+))?$/);if(!m)throw Error('Unsupported selector '+s);return (!m[1]||e.tag===m[1])&&(!m[2]||(e.attrs.class||'').split(/\s+/).includes(m[2]));}
const document=new Element('document'),stack=[document],voids=new Set(['meta','input','br','img','link','hr']);
for(const token of html.replace(/<script>[\s\S]*?<\/script>/g,'').replace(/<style>[\s\S]*?<\/style>/g,'').match(/<[^>]*>|[^<]+/g)||[]){
 if(token.startsWith('<!'))continue;
 if(token.startsWith('</')){const tag=token.slice(2,-1).trim();while(stack.length>1){const current=stack.pop();if(current.tag===tag)break;}continue;}
 if(token.startsWith('<')){const tag=token.match(/^<([\w-]+)/)[1],attrs={};const rest=token.slice(tag.length+1,-1);for(const m of rest.matchAll(/([\w-]+)(?:="([^"]*)")?/g))attrs[m[1]]=decode(m[2]??'');const e=new Element(tag,attrs);stack.at(-1).appendChild(e);if(!voids.has(tag))stack.push(e);}
 else{const e=new Element('#text');e.textContent=decode(token);stack.at(-1).appendChild(e);}
}
document.getElementById=id=>document.descendants().find(e=>e.attrs.id===id)||null;
const context=vm.createContext({document,console});for(const s of scripts)vm.runInContext(s,context);
let checks=0;function ok(value,label){checks++;assert(value,label);}
const traffic=document.getElementById('traffic-parameter-table'),inv=document.getElementById('inverse-emission-table'),fd=document.getElementById('inverse-fd-table'),bounded=document.getElementById('bounded-fd-table');
const visible=t=>t.tBodies[0].rows.filter(r=>!r.hidden);
ok(visible(traffic).length===137,'137 traffic rows');ok(visible(inv).length===274,'274 inverse rows initially');ok(visible(fd).length===274,'274 backward FD rows initially');ok(visible(bounded).length===274,'274 primary bounded rows initially');
ok(visible(bounded).every(r=>r.dataset.bounds==='primary'),'initial primary bounds filter');
let sortTests=0;
for(const table of [traffic,inv,fd,bounded]){
 const cls=table===traffic?'button.sort':'.inverse-sort';
 for(const button of table.querySelectorAll(cls))for(const direction of [1,-1]){
  button.emit('click');const key=button.dataset.key,numeric=button.dataset.numeric==='true';
  const values=table.tBodies[0].rows.map(r=>r.querySelector('[data-key="'+key+'"]').dataset.value);
  const valid=numeric?values.filter(v=>v!==''&&Number.isFinite(Number(v))).map(Number):values.filter(v=>v!=='');
  ok(valid.every((v,i)=>!i||(numeric?direction*(v-valid[i-1])>=-1e-12:direction*valid[i-1].localeCompare(v,undefined,{numeric:true})<=0)),'sort '+table.attrs.id+' '+key+' '+direction);
  if(numeric){const firstMissing=values.findIndex(v=>v===''||!Number.isFinite(Number(v)));ok(firstMissing<0||values.slice(firstMissing).every(v=>v===''||!Number.isFinite(Number(v))),'numeric missing values last');}
  sortTests++;
 }
}
const boundSelect=document.getElementById('inverse-bounds'),strategy=document.getElementById('inverse-strategy'),search=document.getElementById('inverse-search'),topSearch=document.getElementById('search');
for(const bound of ['primary','expanded_lower_wave'])for(const strat of ['','co2_target','balanced_four_pollutants']){
 boundSelect.value=bound;boundSelect.emit('change');strategy.value=strat;strategy.emit('change');
 ok(visible(inv).length===(strat?137:274),'inverse strategy filter '+strat);
 ok(visible(bounded).length===(strat?137:274),'bounded strategy count '+strat);
 ok(visible(bounded).every(r=>r.dataset.bounds===bound&&(!strat||r.dataset.strategy===strat)),'bound/strategy conjunction');
}
strategy.value='';strategy.emit('change');search.value='ep014';search.emit('input');ok(visible(inv).length===2&&visible(fd).length===2&&visible(bounded).length===2,'inverse case filter');
topSearch.value='ep020';topSearch.emit('input');ok(visible(traffic).length===1,'top traffic filter');ok(visible(inv).length===2&&visible(bounded).length===2,'top search synchronizes inverse');
topSearch.value='no-such-case';topSearch.emit('input');ok([traffic,inv,fd,bounded].every(t=>visible(t).length===0),'empty results');
topSearch.value='';topSearch.emit('input');ok(visible(traffic).length===137&&visible(inv).length===274&&visible(bounded).length===274,'clear filter restores rows');
document.getElementById('all-view').emit('click');ok(traffic.querySelectorAll('[data-group="inputs"]').every(e=>!e.hidden),'show all inputs');ok(traffic.querySelectorAll('[data-group="coefficients"]').every(e=>!e.hidden),'show all coefficients');
document.getElementById('summary-view').emit('click');for(const g of ['inputs','delay','coefficients','fd_support'])ok(traffic.querySelectorAll('[data-group="'+g+'"]').every(e=>e.hidden),'hide detail group '+g);for(const g of ['id','qvdf','fd'])ok(traffic.querySelectorAll('[data-group="'+g+'"]').every(e=>!e.hidden),'show summary group '+g);
ok(visible(inv).length===274&&visible(bounded).length===274,'traffic group toggle does not hide inverse rows');
console.log(JSON.stringify({checks,sort_direction_checks:sortTests,scripts_executed:scripts.length,all_passed:true},null,2));
