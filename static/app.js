'use strict';
const $ = (s) => document.querySelector(s);
const state = {me:null, users:[], docs:[], csrf:'', current:null, filter:'all', timer:null, saving:false, dirty:false, blocked:false};
function esc(s){return String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function initials(name){return name.split(' ').map(x=>x[0]).slice(0,2).join('').toUpperCase();}
function timeLabel(iso){let d=new Date(iso); return Number.isNaN(+d)?'Recently edited':`Edited ${new Intl.DateTimeFormat('en-US',{month:'short',day:'numeric'}).format(d)}`;}
function toast(message, error=false){let el=$('#toast');el.textContent=message;el.className='toast'+(error?' error':'');el.hidden=false;clearTimeout(el._timer);el._timer=setTimeout(()=>el.hidden=true,4000);}
async function api(path, options={}){
  const r=await fetch(path,{...options,headers:{...(options.body instanceof FormData?{}:{'Content-Type':'application/json'}), 'X-CSRF-Token':state.csrf,...options.headers}});
  let data;try{data=await r.json();}catch{throw new Error('Server returned an unexpected response');}
  if(!r.ok)throw new Error(data.error||`Request failed (${r.status})`);
  return data;
}
async function bootstrap(){
  let data=await api('/api/bootstrap');Object.assign(state,{me:data.me, users:data.users, docs:data.documents, csrf:data.csrf});
  $('#top-user').textContent=state.me.name.split(' ')[0];$('#user-avatar').textContent=initials(state.me.name);
  $('#account').innerHTML=state.users.map(u=>`<option value="${u.id}" ${u.id===state.me.id?'selected':''}>${esc(u.name)}</option>`).join('');
  renderDocs();
}
async function refreshDocs(){let d=await api('/api/documents');state.docs=d.documents;renderDocs();}
function renderDocs(){
  let mine=state.docs.filter(d=>d.permission==='owner'), shared=state.docs.filter(d=>d.permission!=='owner');
  $('#count-all').textContent=state.docs.length;$('#count-mine').textContent=mine.length;$('#count-shared').textContent=shared.length;
  let shown=state.filter==='mine'?mine:state.filter==='shared'?shared:state.docs;
  const labels={all:['All documents',"Everything you're working on, in one place."],mine:['Owned by me','Documents you created and control.'],shared:['Shared with me','Collaborative work from your teammates.']};
  $('#list-title').textContent=labels[state.filter][0];$('#location').textContent=labels[state.filter][0];$('#list-subtitle').textContent=labels[state.filter][1];
  $('#doc-grid').innerHTML=shown.map((d,i)=>`<button class="doc-card" data-id="${d.id}" aria-label="Open ${esc(d.title)}">
    <span class="doc-card-icon">▤</span><span class="doc-card-tag ${d.permission==='owner'?'tag-own':'tag-share'}">${d.permission==='owner'?'Owned':d.permission==='edit'?'Can edit':'View only'}</span>
    <span class="doc-card-title">${esc(d.title)}</span><span class="doc-card-description">${d.permission==='owner'?'Your document':`Shared by ${esc(d.owner_name)}`}</span>
    <span class="doc-card-footer"><span>${timeLabel(d.updated_at)}</span><span class="card-arrow">↗</span></span></button>`).join('');
  $('#empty-state').hidden=shown.length!==0;
  document.querySelectorAll('.doc-card').forEach(el=>el.addEventListener('click',()=>openDoc(+el.dataset.id)));
}
function setFilter(filter){state.filter=filter;document.querySelectorAll('[data-filter]').forEach(x=>x.classList.toggle('active',x.dataset.filter===filter));renderDocs();showDashboard();}
function showDashboard(){clearTimeout(state.timer);$('#dashboard').hidden=false;$('#editor-screen').hidden=true;state.current=null;state.dirty=false;state.blocked=false;renderDocs();}
async function createDoc(){try{await saveNow();const d=await api('/api/documents',{method:'POST',body:JSON.stringify({title:'Untitled document'})});await refreshDocs();await openDoc(d.document.id);$('#doc-title').focus();$('#doc-title').select();}catch(e){toast(e.message,true);}}
async function openDoc(id){
  if(state.current&&state.current.id!==id)await saveNow();
  try{let d=await api('/api/documents/'+id);state.current=d.document;state.blocked=false;state.dirty=false;
    $('#dashboard').hidden=true;$('#editor-screen').hidden=false;
    $('#doc-title').value=state.current.title;$('#editor').innerHTML=state.current.content||'<p><br></p>';
    const readonly=state.current.permission==='view';$('#editor').contentEditable=String(!readonly);$('#doc-title').readOnly=readonly;
    document.querySelectorAll('#toolbar button, #toolbar select').forEach(el=>el.disabled=readonly);
    $('#doc-access').textContent=state.current.permission==='owner'?'Owner':readonly?'View only':'Can edit';
    $('#share-btn').textContent=readonly?'♧ People':'♧ Share';
    $('#save-indicator').textContent=readonly?'Read-only':'All changes saved';
    $('#location').textContent=state.current.title;drawAvatars();
  }catch(e){toast(e.message,true);}
}
function drawAvatars(){let d=state.current;if(!d)return;
  let people=[state.users.find(u=>u.id===d.owner_id),...d.collaborators].filter(Boolean);
  $('#avatar-stack').innerHTML=people.slice(0,3).map((u,i)=>`<div class="mini-avatar av${i}" title="${esc(u.name)}">${initials(u.name)}</div>`).join('');
}
function changed(){if(!state.current||state.current.permission==='view'||state.blocked)return;state.dirty=true;$('#save-indicator').textContent='Unsaved changes';clearTimeout(state.timer);state.timer=setTimeout(saveNow,700);}
async function saveNow(){
  clearTimeout(state.timer);
  if(!state.current||!state.dirty||state.saving||state.blocked)return;
  state.saving=true;const thisId=state.current.id; const docTitle=$('#doc-title').value.trim()||'Untitled document';const docHtml=$('#editor').innerHTML;const rev=state.current.revision;
  state.dirty=false;$('#save-indicator').textContent='Saving…';
  try{
    const data=await api(`/api/documents/${thisId}`,{method:'PATCH',body:JSON.stringify({title:docTitle,content:docHtml,revision:rev})});
    if(state.current&&state.current.id===thisId){state.current.revision=data.document.revision;state.current.title=data.document.title;state.current.updated_at=data.document.updated_at;$('#save-indicator').textContent=state.dirty?'Unsaved changes':'All changes saved';$('#location').textContent=data.document.title;}
    await refreshDocs();
  }catch(e){state.dirty=true;state.blocked=true;$('#save-indicator').textContent='Save failed';toast(e.message+' Your changes remain visible; copy them before reloading.',true);}
  finally{state.saving=false;if(state.dirty&&!state.blocked&&state.current&&state.current.id===thisId){state.timer=setTimeout(saveNow,300);}}
}
async function importFile(file){
  if(!file)return;if(!file.name.toLowerCase().endsWith('.txt')){toast('Only .txt files are supported',true);return;}
  if(file.size>1000000){toast('The file must be under 1 MB',true);return;}
  let fd=new FormData();fd.append('file',file);
  try{let d=await api('/api/import',{method:'POST',body:fd});await refreshDocs();await openDoc(d.document.id);toast('File imported as an editable document');}catch(e){toast(e.message,true);}
}
function drawShare(){
  let d=state.current;if(!d)return;
  let owner=d.permission==='owner';$('#share-controls').hidden=!owner;
  const eligible=state.users.filter(u=>u.id!==d.owner_id && !d.collaborators.some(c=>c.id===u.id));
  $('#share-email').innerHTML=eligible.length?eligible.map(u=>`<option value="${esc(u.email)}">${esc(u.name)} (${esc(u.email)})</option>`).join(''):'<option value="">Everyone already has access</option>';
  $('#grant-share').disabled=!eligible.length;
  let all=[{...state.users.find(u=>u.id===d.owner_id),role:'Owner'},...d.collaborators];
  $('#shared-people').innerHTML=all.map((p,i)=>`<div class="person"><div class="person-avatar av${i%3}">${initials(p.name)}</div><div class="person-text"><strong>${esc(p.name)}</strong><span>${esc(p.email)}</span></div><span class="person-role">${p.role==='Owner'?'Owner':p.role==='edit'?'Can edit':'Can view'}</span>${owner&&p.role!=='Owner'?`<button class="remove-share" title="Remove access" data-id="${p.id}">×</button>`:''}</div>`).join('');
  document.querySelectorAll('.remove-share').forEach(btn=>btn.addEventListener('click',()=>removeShare(+btn.dataset.id)));
}
function openShare(){drawShare();$('#share-modal').hidden=false;}
function closeShare(){$('#share-modal').hidden=true;}
async function grantShare(){let email=$('#share-email').value; if(!email)return;try{await saveNow();let d=await api(`/api/documents/${state.current.id}/share`,{method:'POST',body:JSON.stringify({email,role:$('#share-role').value})});state.current=d.document;drawShare();drawAvatars();toast('Access granted to '+email);}catch(e){toast(e.message,true);}}
async function removeShare(id){try{let d=await api(`/api/documents/${state.current.id}/share/${id}`,{method:'DELETE'});state.current=d.document;drawShare();drawAvatars();toast('Access removed');}catch(e){toast(e.message,true);}}
function format(command,value){if(state.current?.permission==='view')return;$('#editor').focus();document.execCommand(command,false,value||null);changed();}
function bind(){
  ['#new-doc','#create-btn','#empty-create'].forEach(s=>$(s).addEventListener('click',createDoc));
  document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>setFilter(b.dataset.filter)));
  $('#import-btn').addEventListener('click',()=>$('#file-input').click());$('#file-input').addEventListener('change',e=>{importFile(e.target.files[0]);e.target.value='';});
  $('#account').addEventListener('change',async e=>{try{await saveNow();await api('/api/switch',{method:'POST',body:JSON.stringify({user_id:+e.target.value})});location.reload();}catch(err){toast(err.message,true);}});
  $('#back-btn').addEventListener('click',async()=>{await saveNow();if(!state.blocked)showDashboard();});
  $('#editor').addEventListener('input',changed);$('#doc-title').addEventListener('input',changed);
  document.querySelectorAll('#toolbar button[data-cmd]').forEach(b=>{b.addEventListener('mousedown',e=>e.preventDefault());b.addEventListener('click',()=>format(b.dataset.cmd));});
  $('#block-style').addEventListener('change',e=>{format('formatBlock',e.target.value);});
  $('#clear-format').addEventListener('mousedown',e=>e.preventDefault());$('#clear-format').addEventListener('click',()=>format('removeFormat'));
  $('#share-btn').addEventListener('click',openShare);$('#close-share').addEventListener('click',closeShare);$('#share-modal').addEventListener('click',e=>{if(e.target.id==='share-modal')closeShare();});$('#grant-share').addEventListener('click',grantShare);
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveNow();}if(e.key==='Escape')closeShare();});
  window.addEventListener('beforeunload',e=>{if(state.dirty||state.saving){e.preventDefault();e.returnValue='';}});
}
window.addEventListener('DOMContentLoaded',async()=>{bind();try{await bootstrap();}catch(e){toast('Unable to load workspace: '+e.message,true);}});
