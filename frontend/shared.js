export const state = {locale:localStorage.getItem('khattama-locale')||'kk',page:'meetings',meeting:null,draft:null,tab:'summary',dirty:false,timer:null};
export const t=(kk,ru)=>state.locale==='kk'?kk:ru;
export const esc=(s)=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const $=(s)=>document.querySelector(s);
export const $$=(s)=>[...document.querySelectorAll(s)];
export const time=(n)=>`${String(Math.floor(n/60)).padStart(2,'0')}:${String(Math.floor(n%60)).padStart(2,'0')}`;
export function notify(message,error=false){$('#message').textContent=message;$('#message').className=error?'error':'';}
export async function api(url,options={}){const r=await fetch(url,options);if(!r.ok){let j;try{j=await r.json()}catch{j={detail:r.statusText}}throw Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail));}return r.json();}
export const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const field=(label,control)=>`<label class="field">${esc(label)}${control}</label>`;
export const input=(value,attrs='')=>`<input value="${esc(value)}" ${attrs}>`;
export const textarea=(value,attrs='')=>`<textarea ${attrs}>${esc(value)}</textarea>`;
export const options=(values,selected)=>values.map(([v,label])=>`<option value="${esc(v)}" ${selected===v?'selected':''}>${esc(label)}</option>`).join('');
export function dirty(){state.dirty=true;const x=$('#unsaved');if(x)x.textContent=t('Сақталмаған өзгерістер','Несохранённые изменения');}
