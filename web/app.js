const state={all:[],filtered:[]};
const yen=n=>new Intl.NumberFormat('ja-JP',{notation:'compact',maximumFractionDigits:1}).format(n)+'円';
const esc=s=>String(s??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const ids=['searchInput','revenueFilter','productFilter','industryFilter','prefectureFilter','priorityFilter'];
const $=id=>document.getElementById(id);

async function init(){
  const res=await fetch('./data/contacts.json');
  state.all=await res.json();
  [...new Set(state.all.map(x=>x.industry))].sort().forEach(v=>$('industryFilter').add(new Option(v,v)));
  [...new Set(state.all.map(x=>x.prefecture))].sort().forEach(v=>$('prefectureFilter').add(new Option(v,v)));
  ids.forEach(id=>$(id).addEventListener('input',applyFilters));
  $('resetButton').addEventListener('click',reset);
  $('csvButton').addEventListener('click',downloadCsv);
  $('closeDialog').addEventListener('click',()=>$('detailDialog').close());
  $('detailDialog').addEventListener('click',e=>{if(e.target===$('detailDialog'))$('detailDialog').close()});
  applyFilters();
}

function applyFilters(){
  const q=$('searchInput').value.trim().toLowerCase();
  const min=Number($('revenueFilter').value||0);
  const product=$('productFilter').value;
  const industry=$('industryFilter').value;
  const prefecture=$('prefectureFilter').value;
  const priority=$('priorityFilter').value;
  state.filtered=state.all.filter(x=>{
    const hay=[x.company_name,x.industry,x.prefecture,x.pitch_reason,x.target_department,...x.recommended_products].join(' ').toLowerCase();
    return (!q||hay.includes(q))&&x.revenue_yen>=min&&(!product||x.recommended_products.includes(product))&&(!industry||x.industry===industry)&&(!prefecture||x.prefecture===prefecture)&&(!priority||x.priority===priority);
  });
  render();
}

function render(){
  $('totalCount').textContent=state.all.length;
  $('filteredCount').textContent=state.filtered.length;
  $('highPriority').textContent=state.filtered.filter(x=>x.priority==='A').length;
  $('revenueTotal').textContent=(state.filtered.reduce((s,x)=>s+x.revenue_yen,0)/1e12).toLocaleString('ja-JP',{maximumFractionDigits:1})+'兆円';
  $('verifiedDate').textContent=state.all[0]?.verified_at??'-';
  $('emptyState').hidden=state.filtered.length!==0;
  $('companyRows').innerHTML=state.filtered.map((x,i)=>`<tr>
    <td><span class="priority priority--${esc(x.priority)}">${esc(x.priority)}</span></td>
    <td><span class="company-name">${esc(x.company_name)}</span><span class="company-meta">${esc(x.prefecture)} / ${esc(x.fiscal_year)}</span></td>
    <td>${esc(yen(x.revenue_yen))}</td>
    <td>${esc(x.industry)}</td>
    <td><div class="chips">${x.recommended_products.map(p=>`<span class="chip">${esc(p)}</span>`).join('')}</div></td>
    <td><a class="contact-link" href="${esc(x.contact_value)}" target="_blank" rel="noopener noreferrer">公式窓口 ↗</a></td>
    <td><button class="row-button" data-index="${i}">詳細</button></td>
  </tr>`).join('');
  document.querySelectorAll('.row-button').forEach(b=>b.addEventListener('click',()=>openDetail(state.filtered[Number(b.dataset.index)])));
}

function createDraft(x){
  const product=x.recommended_products[0];
  return `件名：${x.company_name}様の${x.target_department}業務に関するご提案（${product}）\n\n${x.company_name}\nご担当者様\n\n突然のご連絡失礼いたします。\n公開情報を拝見し、${x.pitch_reason}\n\nLayerXの「${product}」では、関連業務の効率化・標準化をご支援しています。現在の運用や課題を短時間お伺いし、適合する場合のみ具体例をご案内できればと考えております。\n\nご関心がございましたら、ご都合のよい方法をご教示ください。\n\n※送信前に、貴社問い合わせ窓口の利用条件に沿った内容か必ず確認します。`;
}

function openDetail(x){
  $('detailCompany').textContent=x.company_name;
  const draft=createDraft(x);
  $('detailContent').innerHTML=`<div class="detail-grid">
    <section class="detail-card"><h3>売上規模</h3><p>${esc(yen(x.revenue_yen))}<br><small>${esc(x.fiscal_year)}・公式資料ベース</small></p></section>
    <section class="detail-card"><h3>優先度 / 適合度</h3><p><span class="priority priority--${esc(x.priority)}">${esc(x.priority)}</span> ${esc(x.fit_score)} / 100</p></section>
    <section class="detail-card detail-card--wide"><h3>推奨プロダクト</h3><div class="chips">${x.recommended_products.map(p=>`<span class="chip">${esc(p)}</span>`).join('')}</div></section>
    <section class="detail-card"><h3>想定担当部門</h3><p>${esc(x.target_department)}</p></section>
    <section class="detail-card"><h3>提案理由</h3><p>${esc(x.pitch_reason)}</p></section>
    <section class="detail-card detail-card--wide"><h3>提案文の下書き</h3><div class="draft" id="draftText">${esc(draft)}</div><button class="button copy-button" id="copyDraft">下書きをコピー</button></section>
    <section class="detail-card detail-card--wide"><h3>公式ソース</h3><div class="source-list">
      <a class="detail-link" href="${esc(x.contact_value)}" target="_blank" rel="noopener noreferrer">公式問い合わせ窓口を開く ↗</a>
      <a class="detail-link" href="${esc(x.revenue_source_url)}" target="_blank" rel="noopener noreferrer">売上高の公式根拠を開く ↗</a>
      <a class="detail-link" href="${esc(x.official_url)}" target="_blank" rel="noopener noreferrer">企業公式サイトを開く ↗</a>
    </div><p class="company-meta">確認日: ${esc(x.verified_at)} / 自動送信不可</p></section>
  </div>`;
  $('copyDraft').addEventListener('click',async()=>{await navigator.clipboard.writeText(draft);$('copyDraft').textContent='コピーしました';});
  $('detailDialog').showModal();
}

function reset(){ids.forEach(id=>$(id).value='');$('revenueFilter').value='0';applyFilters()}
function downloadCsv(){
  const cols=['company_name','revenue_yen','fiscal_year','industry','prefecture','recommended_products','priority','fit_score','target_department','pitch_reason','contact_type','contact_value','official_url','revenue_source_url','verified_at'];
  const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"';
  const lines=[cols.join(','),...state.filtered.map(x=>cols.map(c=>quote(Array.isArray(x[c])?x[c].join(' / '):x[c])).join(','))];
  const blob=new Blob(['\ufeff'+lines.join('\r\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='layerx-sales-targets.csv';a.click();URL.revokeObjectURL(a.href);
}
init().catch(err=>{console.error(err);$('emptyState').hidden=false;$('emptyState').textContent='データを読み込めませんでした。';});
