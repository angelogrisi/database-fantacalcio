let DB={players:[],summary:{}};
const $=s=>document.querySelector(s); const val=v=>v??'—';
const num=v=>v==null?'—':Number(v).toFixed(Number(v)%1?2:0);
async function load(){
 try{const r=await fetch('data/database.json',{cache:'no-store'}); if(!r.ok)throw Error(); DB=await r.json(); init();}
 catch(e){$('#status').textContent='Archivio non ancora pubblicato. Esegui il workflow “Publish Fantacalcio web app”.';}
}
function init(){
 const seasons=[...new Set(DB.players.map(x=>x.season).filter(Boolean))].sort().reverse();
 const clubs=[...new Set(DB.players.map(x=>x.club).filter(Boolean))].sort();
 seasons.forEach(x=>$('#season').add(new Option(x,x))); clubs.forEach(x=>$('#club').add(new Option(x,x)));
 $('#summary').innerHTML=`<span class="chip">${DB.summary.players||0} giocatori</span><span class="chip">${DB.summary.clubs||0} club</span><span class="chip">${DB.summary.matches||0} partite</span>`;
 ['search','season','club','role','sort'].forEach(id=>$('#'+id).addEventListener('input',render));
 $('#close').onclick=()=>$('#detail').close(); render();
}
function roleOf(p){const r=(p.fantasy_role||p.position||'').toUpperCase(); if(r.startsWith('G')||r==='P')return'P';if(r.startsWith('D'))return'D';if(r.startsWith('M')||r.startsWith('C'))return'C';if(r.startsWith('A')||r.startsWith('F'))return'A';return r||'—'}
function render(){
 const q=$('#search').value.trim().toLowerCase(),s=$('#season').value,c=$('#club').value,r=$('#role').value;
 let rows=DB.players.filter(p=>(!q||(p.name||'').toLowerCase().includes(q))&&(!s||p.season===s)&&(!c||p.club===c)&&(!r||roleOf(p)===r));
 const sort=$('#sort').value; rows.sort((a,b)=>sort==='name'?(a.name||'').localeCompare(b.name||''):sort==='goals_desc'?(b.goals||0)-(a.goals||0):sort==='assists_desc'?(b.assists||0)-(a.assists||0):sort==='auction_desc'?(b.auction_value||0)-(a.auction_value||0):(b.fantasy_average||0)-(a.fantasy_average||0));
 $('#status').textContent=`${rows.length} risultati`;
 $('#players').innerHTML=rows.slice(0,500).map((p,i)=>`<article class="card" data-i="${DB.players.indexOf(p)}"><div class="topline"><span class="role">${roleOf(p)}</span><span class="club">${val(p.club)}</span></div><h2>${val(p.name)}</h2><div class="season">${val(p.season)}</div><div class="metrics"><div class="metric"><strong>${num(p.appearances)}</strong><small>Pres.</small></div><div class="metric"><strong>${num(p.goals)}</strong><small>Gol</small></div><div class="metric"><strong>${num(p.fantasy_average)}</strong><small>F.Media</small></div></div></article>`).join('');
 document.querySelectorAll('.card').forEach(el=>el.onclick=()=>show(DB.players[+el.dataset.i]));
}
function show(p){
 const history=DB.players.filter(x=>x.player_id===p.player_id).sort((a,b)=>(b.season||'').localeCompare(a.season||''));
 $('#detailContent').innerHTML=`<p class="eyebrow">${roleOf(p)} · ${val(p.club)}</p><h1>${val(p.name)}</h1><p>${val(p.nationality)} · ${val(p.position)}</p><div class="detail-grid"><div class="metric"><strong>${num(p.fantasy_average)}</strong><small>Fantamedia</small></div><div class="metric"><strong>${num(p.goals)}</strong><small>Gol</small></div><div class="metric"><strong>${num(p.assists)}</strong><small>Assist</small></div><div class="metric"><strong>${num(p.xg)}</strong><small>xG</small></div><div class="metric"><strong>${num(p.xa)}</strong><small>xA</small></div><div class="metric"><strong>${num(p.auction_value)}</strong><small>Valore asta</small></div></div><table class="history"><thead><tr><th>Stagione</th><th>Club</th><th>Pres.</th><th>Gol</th><th>Assist</th><th>F.Media</th></tr></thead><tbody>${history.map(x=>`<tr><td>${val(x.season)}</td><td>${val(x.club)}</td><td>${num(x.appearances)}</td><td>${num(x.goals)}</td><td>${num(x.assists)}</td><td>${num(x.fantasy_average)}</td></tr>`).join('')}</tbody></table>`;
 $('#detail').showModal();
}
load();