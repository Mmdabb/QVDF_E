// Read-only static DOM substitute: executes only the inline dashboard handlers.
// No browser, URL, server, layout engine or network is used.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path');
const supplied=process.argv[2]||'debug/full_experiment/steps/11_episode_time_series';
const directory=supplied.endsWith('.html')?path.dirname(supplied):supplied;
const decode=s=>s.replace(/&quot;/g,'"').replace(/&#x27;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class Element{
 constructor(tag,attrs={}){this.tag=tag;this.attrs=attrs;this.children=[];this.parentElement=null;this.handlers={};this.hidden='hidden'in attrs;this.checked='checked'in attrs;this.dataset={};this.classList={toggle:(c)=>{const set=new Set((this.attrs.class||'').split(/\s+/).filter(Boolean));const added=!set.has(c);if(added)set.add(c);else set.delete(c);this.attrs.class=[...set].join(' ');return added;},contains:(c)=>(this.attrs.class||'').split(/\s+/).includes(c)};for(const[k,v]of Object.entries(attrs))if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,l)=>l.toUpperCase())]=v;}
 appendChild(child){if(child.parentElement){const c=child.parentElement.children,i=c.indexOf(child);if(i>=0)c.splice(i,1);}this.children.push(child);child.parentElement=this;return child;}
 get rows(){return this.children.filter(e=>e.tag==='tr');}get cells(){return this.children.filter(e=>['td','th'].includes(e.tag));}get tBodies(){return this.children.filter(e=>e.tag==='tbody');}
 get value(){if(this._value!==undefined)return this._value;if(this.tag==='select')return this.querySelector('option')?.attrs.value||'';return this.attrs.value||'';}set value(v){this._value=v;}
 get textContent(){return this._text!==undefined?this._text:this.children.map(e=>e.textContent).join('');}set textContent(s){this._text=s;}
 getAttribute(k){return this.attrs[k]??null;}setAttribute(k,v){this.attrs[k]=v;}
 addEventListener(event,cb){(this.handlers[event]??=[]).push(cb);}emit(event){for(const cb of this.handlers[event]||[])cb({target:this});}
 descendants(){return this.children.flatMap(e=>[e,...e.descendants()]);}
 querySelectorAll(selector){const parts=selector.split(/\s+/);return this.descendants().filter(e=>{if(!matches(e,parts.at(-1)))return false;let p=e.parentElement;for(let i=parts.length-2;i>=0;i--){while(p&&!matches(p,parts[i]))p=p.parentElement;if(!p)return false;p=p.parentElement;}return true;});}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
function matches(e,s){const attr=s.match(/^\[([^=]+)="([^"]*)"\]$/);if(attr)return e.attrs[attr[1]]===attr[2];const m=s.match(/^([\w-]+)?(?:\.([\w-]+))?$/);if(!m)throw Error('Unsupported selector '+s);return (!m[1]||e.tag===m[1])&&(!m[2]||(e.attrs.class||'').split(/\s+/).includes(m[2]));}
function loadPage(filename){
const html=fs.readFileSync(filename,'utf8');
const scripts=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
const document=new Element('document'),stack=[document],voids=new Set(['meta','input','br','img','link','hr']);
for(const token of html.replace(/<script>[\s\S]*?<\/script>/g,'').replace(/<style>[\s\S]*?<\/style>/g,'').match(/<[^>]*>|[^<]+/g)||[]){
 if(token.startsWith('<!'))continue;
 if(token.startsWith('</')){const tag=token.slice(2,-1).trim();while(stack.length>1){const current=stack.pop();if(current.tag===tag)break;}continue;}
 if(token.startsWith('<')){const tag=token.match(/^<([\w-]+)/)[1],attrs={};const rest=token.slice(tag.length+1,-1);for(const m of rest.matchAll(/([\w-]+)(?:="([^"]*)")?/g))attrs[m[1]]=decode(m[2]??'');const e=new Element(tag,attrs);stack.at(-1).appendChild(e);if(!voids.has(tag))stack.push(e);}
 else{const e=new Element('#text');e.textContent=decode(token);stack.at(-1).appendChild(e);}
}
document.getElementById=id=>document.descendants().find(e=>e.attrs.id===id)||null;
document.body=document.querySelector('body');
const context=vm.createContext({document,console});for(const s of scripts)vm.runInContext(s,context);
return {document,html,scripts};
}
let checks=0;function ok(value,label){checks++;assert(value,label);}

let sortTests=0,pages=0;
const configs=[
 ['index.html',137],['traffic_parameters.html',137],['inverse_emissions.html',274],
 ['inverse_fd.html',274],['fd_sensitivity.html',274],['fd_summary.html',4],
 ['fd_capacity_comparison.html',274]
];
for(const [filename,expectedRows] of configs){
 const {document,html,scripts}=loadPage(path.join(directory,filename));pages++;
 const tables=document.querySelectorAll('table');ok(tables.length===1,filename+': exactly one data table');
 const table=tables[0],visible=()=>table.tBodies[0].rows.filter(r=>!r.hidden);
 ok(visible().length===expectedRows,filename+': initial visible rows');
 ok(document.querySelectorAll('math').length>0,filename+': native typeset math');
 ok(document.querySelectorAll('details').length>0,filename+': collapsible navigation');
 ok(document.querySelectorAll('[aria-current="page"]').length===1,filename+': active page indicator');
 const menu=document.getElementById('dashboard-menu-toggle');menu.emit('click');ok(document.body.classList.contains('dashboard-nav-hidden')&&menu.getAttribute('aria-expanded')==='false',filename+': hide navigation');menu.emit('click');ok(!document.body.classList.contains('dashboard-nav-hidden')&&menu.getAttribute('aria-expanded')==='true',filename+': show navigation');
 const ids=document.descendants().filter(e=>e.attrs.id).map(e=>e.attrs.id);ok(new Set(ids).size===ids.length,filename+': unique IDs');
 const buttons=table.querySelectorAll('button').filter(b=>b.dataset.key!==undefined||b.dataset.index!==undefined);
 for(const button of buttons)for(const direction of [1,-1]){
  button.emit('click');const key=button.dataset.key,numeric=button.dataset.numeric==='true';
  const values=table.tBodies[0].rows.map(r=>(key!==undefined?r.querySelector('[data-key="'+key+'"]'):r.cells[Number(button.dataset.index)]).dataset.value);
  const valid=numeric?values.filter(v=>v!==''&&Number.isFinite(Number(v))).map(Number):values.filter(v=>v!=='');
  ok(valid.every((v,i)=>!i||(numeric?direction*(v-valid[i-1])>=-1e-12:direction*valid[i-1].localeCompare(v,undefined,{numeric:true})<=0)),filename+': sort '+(key||button.dataset.index)+' '+direction);
  if(numeric){const firstMissing=values.findIndex(v=>v===''||!Number.isFinite(Number(v)));ok(firstMissing<0||values.slice(firstMissing).every(v=>v===''||!Number.isFinite(Number(v))),filename+': numeric missing values last');}
  sortTests++;
 }
 const strategy=document.getElementById('inverse-strategy'),bounds=document.getElementById('inverse-bounds');
 if(strategy){for(const value of ['co2_target','balanced_four_pollutants','']){strategy.value=value;strategy.emit('change');ok(visible().length===(value?137:274),filename+': strategy row count');ok(visible().every(r=>!value||r.dataset.strategy===value),filename+': strategy membership');}}
 if(bounds){for(const value of ['expanded_lower_wave','primary']){bounds.value=value;bounds.emit('change');ok(visible().length===274,filename+': bound row count');ok(visible().every(r=>r.dataset.bounds===value),filename+': bound membership');}}
 const search=document.getElementById('inverse-search')||document.getElementById('search');
 if(search){for(const [term,n]of [['ep014',strategy?2:1],['no-such-case',0],['',expectedRows]]){search.value=term;search.emit('input');ok(visible().length===n,filename+': search '+term);}}
 const all=document.getElementById('all-view'),summary=document.getElementById('summary-view');
 if(all){all.emit('click');ok(table.querySelectorAll('[data-group="inputs"]').every(e=>!e.hidden),'show all inputs');ok(table.querySelectorAll('[data-group="coefficients"]').every(e=>!e.hidden),'show all coefficients');summary.emit('click');for(const g of ['inputs','delay','coefficients','fd_support'])ok(table.querySelectorAll('[data-group="'+g+'"]').every(e=>e.hidden),'hide detail '+g);}
}
// All five views per episode contain one table and link through nested navigation.
const episodeRoot=path.join(directory,'episodes');let episodePages=0;
for(const folder of fs.readdirSync(episodeRoot))for(const filename of ['index.html','emissions_CO2.html','emissions_NOx.html','emissions_CO.html','emissions_HC.html']){
 const {document}=loadPage(path.join(episodeRoot,folder,filename));episodePages++;
 ok(document.querySelectorAll('table').length===1,folder+'/'+filename+': one table');
 ok(document.querySelectorAll('math').length>0,folder+'/'+filename+': math');
 ok(document.querySelectorAll('[aria-current="page"]').length===1,folder+'/'+filename+': active page');
}
ok(episodePages===685,'five views for all 137 episodes');
console.log(JSON.stringify({checks,pages,episode_pages:episodePages,sort_direction_checks:sortTests,all_passed:true},null,2));
