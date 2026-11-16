'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number.isFinite(Number(n)) && n !== null ? Number(n).toLocaleString('zh-CN') : '未确认';
const pct = n => (Number(n) * 100).toFixed(3) + '%';
const SOURCE = 'https://github.com/zzbyzt/SMSever/blob/master/CellMem/';
const palette = ['#4d9180','#94bcb1','#66869b','#b29b79','#89a7bc','#b4b48b','#b894a8','#739c9b','#adbdcf','#d0bdab','#a1b3a0','#9695b7'];
const state = {engine:null,token:null,files:{reference:null,bulk:null},demo:false,job:null,poll:null,clock:null,activeJobId:null,pollGeneration:0,dataset:null,lane:'person',filter:'all',page:'workbench'};
const audit = window.CELLMEM_AUDIT || {scope:{},summary:{},studies:[],checks:[],limitations:['本轮核验记录尚未加载。']};
const statusNames = {PASS:'核验通过',FAIL:'不通过',PARTIAL:'部分核验',NOT_VERIFIED:'未核验',NOT_APPLICABLE:'不适用',RUNNING:'核验中'};
const statusClasses = {PASS:'pass',FAIL:'fail',PARTIAL:'partial',NOT_VERIFIED:'unknown',NOT_APPLICABLE:'neutral',RUNNING:'warn'};
function badge(status){return `<span class="tag ${statusClasses[status]||'neutral'}">${esc(statusNames[status]||status||'未核验')}</span>`;}
function toast(text){$('toast').textContent=text;$('toast').classList.remove('hidden');setTimeout(()=>$('toast').classList.add('hidden'),3500);}
function showPage(page){state.page=page;document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id==='page-'+page));document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.page===page));if(page==='history')loadHistory();location.hash=page;}
document.querySelectorAll('.nav-item').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.page)));
window.addEventListener('hashchange',()=>{const p=location.hash.slice(1);if(['workbench','datasets','method','history'].includes(p)&&p!==state.page)showPage(p);});

async function initEngine(){
  try{
    const r=await fetch('/api/health',{signal:AbortSignal.timeout(4000)});if(!r.ok)throw new Error();const h=await r.json();if(h.app!=='cellmem-ui')throw new Error();
    state.engine=h;state.token=h.token;$('connection').innerHTML='<i></i>本地引擎已连接';
    if(!h.environment.ready){$('mode-banner').textContent='当前运行环境或冻结核心校验不通过。请恢复 Python 3.11、NumPy 1.26.2 和 SciPy 1.11.4 后运行。';$('mode-banner').classList.remove('hidden');$('connection').classList.add('offline');}
  }catch{
    $('connection').innerHTML='<i></i>界面浏览模式';$('connection').classList.add('offline');
    $('mode-banner').innerHTML='运行计算需要本机 Python 引擎。请启动下载包中的 <b>启动 CellMem</b> 快捷方式或 <code>local/Start-CellMem.ps1</code>。当前页面可浏览方法和数据核验，不会模拟运行结果。';$('mode-banner').classList.remove('hidden');
  }
  updateRunButton();
}
function updateRunButton(){const active=state.job&&['queued','running'].includes(state.job.status);$('run-button').disabled=!!active||!state.engine?.environment.ready||!(state.demo||(state.files.reference&&state.files.bulk));$('run-button').innerHTML=active?'计算中，请稍候…':'运行冻结算法 <span>→</span>';}
function setFile(key,file){if(file&&!file.name.toLowerCase().endsWith('.npz')){toast('请选择 NPZ 文件。');return;}state.files[key]=file;state.demo=false;$('demo-notice').classList.add('hidden');$(key+'-name').textContent=file?`${file.name} · ${(file.size/1024/1024).toFixed(2)} MB`:`点击选择或拖入 ${key}.npz`;$(key+'-zone').classList.toggle('chosen',!!file);updateRunButton();}
for(const key of ['reference','bulk']){
 $(key+'-file').addEventListener('change',e=>setFile(key,e.target.files[0]));const zone=$(key+'-zone');
 zone.addEventListener('dragover',e=>{e.preventDefault();zone.classList.add('drag');});zone.addEventListener('dragleave',()=>zone.classList.remove('drag'));
 zone.addEventListener('drop',e=>{e.preventDefault();zone.classList.remove('drag');setFile(key,e.dataTransfer.files[0]);});
}
$('load-demo').addEventListener('click',()=>{state.demo=true;state.files={reference:null,bulk:null};for(const key of ['reference','bulk']){$(key+'-file').value='';$(key+'-name').textContent='使用内置合成示例';$(key+'-zone').classList.add('chosen');}$('demo-notice').classList.remove('hidden');updateRunButton();if(!state.engine)toast('合成示例也需要本地引擎；请先启动桌面工具。');});
$('run-button').addEventListener('click',async()=>{
 clearInterval(state.poll);clearInterval(state.clock);state.pollGeneration++;state.activeJobId=null;state.job=null;$('run-state').textContent='提交输入';$('run-state').className='tag neutral';$('input-summary').innerHTML='';$('phase-label').textContent='提交并校验输入';
 $('run-error').classList.add('hidden');$('results').classList.add('hidden');const fd=new FormData();if(state.demo)fd.append('demo','true');else{fd.append('reference',state.files.reference);fd.append('bulk',state.files.bulk);}
 $('run-button').disabled=true;$('run-button').textContent='正在提交输入…';
 try{const r=await fetch('/api/jobs',{method:'POST',headers:{'X-CellMem-Token':state.token},body:fd});const j=await r.json();if(!r.ok)throw new Error(j.error||'提交失败');state.job=j;renderJob(j);startPolling(j.id);}
 catch(e){$('run-error').textContent=e.message;$('run-error').classList.remove('hidden');updateRunButton();}
});
function startPolling(id){clearInterval(state.poll);clearInterval(state.clock);state.activeJobId=id;const generation=++state.pollGeneration;$('results').classList.add('hidden');$('run-error').classList.add('hidden');$('download-all').removeAttribute('href');pollJob(id,generation);state.poll=setInterval(()=>pollJob(id,generation),1500);state.clock=setInterval(()=>{if(state.job){const sec=Math.max(0,Math.floor((Date.now()/1000)-(state.job.started||state.job.created)));$('elapsed').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');}},1000);}
async function pollJob(id,generation=state.pollGeneration){try{const r=await fetch('/api/jobs/'+id);if(!r.ok)throw new Error('无法读取运行状态');const j=await r.json();if(generation!==state.pollGeneration||id!==state.activeJobId)return;state.job=j;renderJob(j);if(!['queued','running'].includes(j.status)){clearInterval(state.poll);clearInterval(state.clock);if(j.result)renderResults(j);updateRunButton();}}catch(e){if(generation!==state.pollGeneration||id!==state.activeJobId)return;clearInterval(state.poll);clearInterval(state.clock);$('phase-label').textContent='连接中断，请到运行记录查看';toast(e.message);}}
function renderJob(j){
 if(!['complete','uncertified'].includes(j.status))$('results').classList.add('hidden');
 if(!j.error)$('run-error').classList.add('hidden');
 const names={queued:'等待执行',running:'运行中',complete:'认证完成',uncertified:'存在未认证解',failed:'运行失败',interrupted:'任务中断'};
 const stage={validating:'检查字段、标签与基因轴',fitting:'初始计数求解 → 精度加权求解',complete:'预测与运行锁已保存',uncertified:'保留未认证结果，请查看诊断',failed:'输入或运行检查未通过'};
 $('run-state').textContent=names[j.status]||j.status;$('run-state').className='tag '+({complete:'green',failed:'fail',uncertified:'warn',running:'green',interrupted:'warn'}[j.status]||'neutral');
 $('progress-empty').classList.add('hidden');$('progress-active').classList.remove('hidden');$('phase-label').textContent=stage[j.phase?.stage]||names[j.status];$('job-id').textContent='RUN / '+j.id.slice(0,12);
 $('step-run').classList.add('current');$('step-result').classList.toggle('current',['complete','uncertified'].includes(j.status));document.querySelector('.progress-track').classList.toggle('done',!['running','queued'].includes(j.status));
 const p=j.input_preview;$('input-summary').innerHTML=p?`<span><b>${fmt(p.genes)}</b>基因</span><span><b>${fmt(p.samples)}</b>样本</span><span><b>${fmt(p.types.length)}</b>类型</span><span><b>${fmt(p.reference_profiles)}</b>参考列</span>`:'';
 if(j.error){$('run-error').textContent=j.error;$('run-error').classList.remove('hidden');}
 if(j.finished){const sec=Math.round(j.finished-(j.started||j.created));$('elapsed').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');}
 updateRunButton();
}
function renderResults(j){
 $('results').classList.remove('hidden');$('sample-select').innerHTML=j.result.ids.map((id,i)=>`<option value="${i}">${esc(id)}</option>`).join('');
 const uns=j.numerics.reference_background.variance_unsupported_types||[];
 const prefix=j.demo?'合成示例结果，用于验证工具流程。':'这是当前输入的 RNA 份额预测，未读取目标真值或计算准确率。';
 $('result-notice').textContent=prefix+(uns.length?` ${uns.length}个类型只有不足2个参考供体列，方差不受支持：${uns.map(k=>j.result.types[k]).join('、')}。本版不借方差。`:' 所有类型至少有2个参考供体列。');$('result-notice').classList.toggle('warn',uns.length>0||j.status==='uncertified');
 $('download-all').href=`/api/jobs/${j.id}/download/results.zip`;
 $('download-links').innerHTML=['predictions.tsv','predictions.npz','RUN_LOCK.json','PREDICTION_LOCK.json','NUMERICS.json'].map(n=>`<a href="/api/jobs/${j.id}/download/${n}">${n} ↓</a>`).join('');
 renderSample(0);
}
$('sample-select').addEventListener('change',e=>renderSample(Number(e.target.value)));
function renderSample(index){
 const j=state.job,r=j.result,d=j.numerics.final[index],values=r.prediction[index];
 $('certificate').className='tag '+(d.numeric_certified?'green':'warn');$('certificate').textContent=d.numeric_certified?'数值认证通过':'未获数值认证';
 $('composition-bar').innerHTML=values.map((v,k)=>`<div style="width:${Math.max(0,v*100)}%;background:${palette[k%palette.length]}" title="${esc(r.types[k])}: ${pct(v)}"></div>`).join('');
 const sorted=values.map((v,k)=>({v,k})).sort((a,b)=>b.v-a.v);
 $('composition-legend').innerHTML=sorted.slice(0,12).map(({v,k})=>`<span><i style="background:${palette[k%palette.length]}"></i>${esc(r.types[k])}<b>${pct(v)}</b></span>`).join('');
 $('result-rows').innerHTML=sorted.map(({v,k})=>`<tr><td>${esc(r.types[k])}</td><td class="mono">${pct(v)}</td><td>${r.reference_support[k]}${r.reference_support[k]<2?' · 方差不支持':''}</td></tr>`).join('');
 $('numeric-detail').innerHTML=[['单纯形一阶间隙',Number(d.global_simplex_gap).toExponential(3)],['可行性误差',Number(d.feasibility).toExponential(3)],['初始解认证',d.initial_certified?'通过':'未通过'],['最小基因精度',Number(d.precision_min).toPrecision(4)],['中位基因精度',Number(d.precision_median).toPrecision(4)],['目标函数',Number(d.objective).toPrecision(6)]].map(([a,b])=>`<span>${esc(a)}<b>${esc(b)}</b></span>`).join('');
}
async function loadHistory(){
 if(!state.engine){$('history-empty').textContent='运行记录存储在本机。请启动本地引擎后查看。';return;}
 try{const r=await fetch('/api/jobs');const x=await r.json();$('history-empty').classList.toggle('hidden',x.jobs.length>0);if(!x.jobs.length)$('history-empty').textContent='尚无运行记录。可以先运行一个合成示例。';
 $('history-rows').innerHTML=x.jobs.map(j=>`<tr><td class="mono">${j.id.slice(0,12)}</td><td>${j.demo?'合成示例':'用户输入'}</td><td>${new Date(j.created*1000).toLocaleString('zh-CN',{hour12:false})}</td><td>${esc({complete:'认证完成',uncertified:'未完全认证',failed:'失败',queued:'等待',running:'运行中',interrupted:'已中断'}[j.status]||j.status)}</td><td><button class="button secondary view-run" data-id="${j.id}">查看</button></td></tr>`).join('');
 document.querySelectorAll('.view-run').forEach(b=>b.addEventListener('click',async()=>{showPage('workbench');startPolling(b.dataset.id);$('progress-active').scrollIntoView({behavior:'smooth',block:'center'});}));
 }catch{$('history-empty').textContent='读取失败，请确认本地服务仍在运行。';}
}
$('refresh-history').addEventListener('click',loadHistory);

function valueSummary(value){if(value==null)return '';if(typeof value==='string')return value;if(Array.isArray(value))return value.map(valueSummary).join('；');if(typeof value==='number')return fmt(value);return Object.entries(value).filter(([k])=>!['asset_ids','evidence','paths'].includes(k)).slice(0,8).map(([k,v])=>`${k}: ${typeof v==='object'?JSON.stringify(v):v}`).join('；');}
function renderAudit(){
 const s=audit.summary||{},scope=audit.scope||{};
 $('audit-metrics').innerHTML=[['研究来源',scope.researchStudies||audit.studies.length,'项','核心研究；组织分块不重复计数'],['本轮分卷 SHA256',`${s.shaPassed??0}/${s.archiveCount??78}`,'','与冻结归档校验值比较'],['本轮 ZIP CRC',`${s.crcPassed??0}/${s.archiveCount??78}`,'','实际解压读取并检查成员'],['历史资源',scope.historicalResourceGroups??20,'组','登记资源 ≠ 独立完成的评测']].map(([a,b,u,c])=>`<div class="metric"><div class="eyebrow">${esc(a)}</div><div class="number">${esc(b)}<span class="unit">${esc(u)}</span></div><p>${esc(c)}</p></div>`).join('');
 $('audit-scope').textContent=`核验时间：${audit.generatedAt?new Date(audit.generatedAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false}):'未记录'}。${audit.status==='RUNNING'?'本轮核验仍在进行，待核验项不会标为通过。':'文件完整性与科学设置的适用性分层报告。'} 未重跑模型、未改变划分、未读取封存测试真值数值。`;
 state.dataset=state.dataset||audit.studies[0]?.id;renderDatasetList();renderDataset();renderChecks();
 $('audit-limitations').innerHTML=(audit.limitations||[]).map(t=>`<li>${esc(valueSummary(t))}</li>`).join('');
}
function renderDatasetList(){const query=$('dataset-search').value.toLowerCase();$('dataset-list').innerHTML=(audit.studies||[]).filter(s=>(s.name+' '+s.id).toLowerCase().includes(query)).map(s=>`<button class="dataset-option ${s.id===state.dataset?'active':''}" data-id="${esc(s.id)}"><span><strong>${esc(s.name||s.id)}</strong><small>${s.sourceBlocks?.length||1} 个来源分块</small></span><span>›</span></button>`).join('');document.querySelectorAll('.dataset-option').forEach(b=>b.addEventListener('click',()=>{state.dataset=b.dataset.id;state.lane=state.dataset==='GSE161918'?'independent':'person';renderDatasetList();renderDataset();}));}
$('dataset-search').addEventListener('input',renderDatasetList);
function range(r){return Array.isArray(r)?(r[0]===r[1]?fmt(r[0]):`${fmt(r[0])}–${fmt(r[1])}`):'未记录';}
function renderDataset(){
 const d=(audit.studies||[]).find(s=>s.id===state.dataset);if(!d){$('dataset-detail').textContent='没有可显示的研究记录。';return;}const c=d.recordedCounts||{};
 const split=d.splits?.[state.lane]||{status:'NOT_VERIFIED'};
 const statuses=[d.matrices?.status,d.labels?.status,...Object.values(d.splits||{}).map(x=>x.status)];
 const overall=d.status||(statuses.includes('FAIL')?'FAIL':statuses.some(x=>['PARTIAL','NOT_VERIFIED'].includes(x))?'PARTIAL':'PASS');
 const moduleCards=[['矩阵',d.matrices],['标签',d.labels],['划分',split]].map(([name,item])=>`<div class="module-box"><h3>${name}</h3>${badge(item?.status)}<p>${esc(item?.summary||item?.evidenceLevel||'核验范围待确认')}</p></div>`).join('');
 $('dataset-detail').innerHTML=`<div class="dataset-head"><div><div class="eyebrow">STUDY / ${esc(d.id)}</div><h2>${esc(d.name||d.id)}</h2><p>${esc((d.sourceBlocks||[]).map(x=>x.source||x.name||x.id).join(' · '))}</p></div>${badge(overall)}</div><div class="dataset-facts"><span><b>${fmt(c.rawCells)}</b>目录登记细胞</span><span><b>${c.people!=null?fmt(c.people):fmt(c.batches)}</b>${c.people!=null?'来源内供体':'批次（不等于供体）'}</span><span><b>${range(c.geneRange)}</b>登记基因范围</span><span><b>${range(c.candidateTypeRange)}</b>历史候选类型范围</span></div><p class="muted">这些规模来自归档登记，当前读取验证的范围见下方证据；不可简单跨版本累加。</p><div class="module-row">${moduleCards}</div><div class="split-tabs"><button data-lane="person" class="${state.lane==='person'?'active':''}">人员划分</button><button data-lane="cell" class="${state.lane==='cell'?'active':''}">细胞划分</button><button data-lane="independent" class="${state.lane==='independent'?'active':''}">独立来源</button></div><div class="split-detail">${badge(split.status)}<p>${esc(split.summary||split.generalization||split.reason||valueSummary(split.details)||'此项尚无可展示的当前核验结论。')}</p><p>${esc(split.evidenceLevel||'')}</p><div id="split-quantities"></div></div><ul class="issue-list">${(d.issues||[]).map(x=>`<li>${esc(valueSummary(x))}</li>`).join('')}</ul><details class="contract"><summary>查看当前研究的核验明细 <span>＋</span></summary><div><pre style="white-space:pre-wrap;font-size:10px;max-height:320px;overflow:auto">${esc(JSON.stringify({matrices:d.matrices,labels:d.labels,splits:d.splits,evidence:d.evidence},null,2))}</pre></div></details>`;
 document.querySelectorAll('.split-tabs button').forEach(b=>b.addEventListener('click',()=>{state.lane=b.dataset.lane;renderDataset();}));
 const counts=split.roleCounts||split.counts||split.counts_author||null;
 if(counts&&['train','validation','test'].every(k=>Number.isFinite(counts[k]))){const total=counts.train+counts.validation+counts.test;$('split-quantities').innerHTML=`<div class="split-bar">${['train','validation','test'].map(k=>`<i style="width:${counts[k]/total*100}%"></i>`).join('')}</div><div class="split-legend"><span>参考 ${fmt(counts.train)}</span><span>开发 ${fmt(counts.validation)}</span><span>测试 ${fmt(counts.test)}</span></div><p class="muted">角色表的细胞数；不等同于独立供体数。</p>`;}
}
function renderChecks(){const checks=(audit.checks||[]).filter(c=>state.filter==='all'||!['PASS','NOT_APPLICABLE'].includes(c.status));$('audit-checks').innerHTML=checks.map(c=>`<tr><td><strong>${esc(c.name||c.id)}</strong><br><span class="muted">${esc(c.summary||'')}</span></td><td>${esc(valueSummary(c.scope)||'全归档')}<br><span class="muted">${esc(c.evidenceLevel||'')}</span></td><td>${badge(c.status)}</td></tr>`).join('')||'<tr><td colspan="3">此筛选下暂无核验项。</td></tr>';}
document.querySelectorAll('.status-filter button').forEach(b=>b.addEventListener('click',()=>{state.filter=b.dataset.filter;document.querySelectorAll('.status-filter button').forEach(x=>x.classList.toggle('selected',x===b));renderChecks();}));
$('download-audit').addEventListener('click',()=>{const a=document.createElement('a');a.href='audit-detail.json';a.download='CellMem_dataset_audit_detail_20261117.json';a.click();});

const steps=[
 {name:'输入与基因轴',formula:'F, reference_count_sums, Y, column_type\n相同且同序的完整基因轴',text:'输入从已构建的供体×类型参考开始。F每列和为1，Y保留未变换计数；核对基因唯一、顺序、样本编号和供体×类型重复。',boundary:'界面不自动注释细胞、不把未测基因补零，也不把目标真值交给预测器。',file:'src/cellmem_full_axis/api.py#L20'},
 {name:'参考微量平滑',formula:'ε = 1 / (median(reference depth) + 1)\nP = (1 − ε) F + ε / G',text:'由参考原始计数深度确定均匀平滑质量，使参考概率严格为正，保留每个供体×类型列。',boundary:'这是参考概率模型的平滑，不是原始测量补齐，也不是UNKNOWN成分。',file:'src/cellmem_full_axis/_frozen_core.py#L10'},
 {name:'全轴初始解',formula:'q = Y / N\nx⁽⁰⁾ = argmin Σg [(Px)g − qg log(Px)g]\nx ≥ 0, Σj xj = 1',text:'以相同单纯形约束求参考列系数，按类型聚合为初始组成π⁽⁰⁾。每次求解从均匀系数开始。',boundary:'使用完整输入轴；固定828身份面板不是这个默认路径的参数。',file:'src/cellmem_full_axis/api.py#L77'},
 {name:'参考均值与方差',formula:'Cgk = mean_d Pgkd\nVgk = sample_variance_d(Pgkd) / Dk',text:'至少两个参考供体时计算参考均值的方差。支持不足的类型明确标记为unsupported。',boundary:'V不是新供体的预测方差。单供体类型数值V=0，本版不执行VarPool借方差。',file:'src/cellmem_full_axis/api.py#L68'},
 {name:'样本条件精度',formula:'μ = C π⁽⁰⁾\nv = V (π⁽⁰⁾ ⊙ π⁽⁰⁾)\nw = μ / (μ + N v)',text:'把参考均值方差、初始组成和当前bulk深度结合为每个基因的固定精度权重。',boundary:'μ一般不等于初始拟合的P x⁽⁰⁾。该公式没有估计类型间协方差或初始组成的不确定性。',file:'src/cellmem_full_axis/api.py#L79'},
 {name:'固定精度再求解',formula:'x⁽¹⁾ = argmin Σg wg [(Px)g − qg log(Px)g]\nx ≥ 0, Σj xj = 1',text:'固定w并保留原参考矩阵P，再拟合一次。SLSQP后进行Newton和坐标精修，并记录一阶间隙与可行性。',boundary:'线性项必须保留，Y=0的基因仍约束拟合质量。外层权重不循环训练。',file:'src/cellmem_full_axis/api.py#L83'},
 {name:'RNA 份额与诊断',formula:'RNA_fraction_k = Σ(j: type(j)=k) x⁽¹⁾j\ngap ≤ 10⁻⁸; feasibility ≤ 10⁻¹⁰',text:'聚合到已知细胞类型；同时保存初始和最终参考列系数、精度向量、供体支持及运行锁。',boundary:'数值认证适用于两个固定子问题，不证明联合全局最优，也不证明细胞真实存在。',file:'src/cellmem_full_axis/api.py#L84'}
];
function renderMethod(index=0){$('method-steps').innerHTML=steps.map((s,i)=>`<button class="method-step ${i===index?'active':''}" data-step="${i}"><b>${String(i+1).padStart(2,'0')}</b>${s.name}</button>`).join('');const s=steps[index];$('method-detail').innerHTML=`<div class="eyebrow">ATOMIC OPERATION / ${String(index+1).padStart(2,'0')}</div><h2>${s.name}</h2><p>${s.text}</p><div class="formula">${esc(s.formula)}</div><p><strong>解释边界</strong><br>${s.boundary}</p><a class="button secondary" href="${SOURCE+s.file}" target="_blank" rel="noreferrer">查看对应源码 ↗</a>`;document.querySelectorAll('.method-step').forEach(b=>b.addEventListener('click',()=>renderMethod(Number(b.dataset.step))));}
renderAudit();renderMethod();initEngine();const page=location.hash.slice(1);if(['workbench','datasets','method','history'].includes(page))showPage(page);
