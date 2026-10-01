(async()=>{
  const m=document.body.innerText.match(/\b\d{6}\b/);
  if(!m)return;
  const code=m[0];
  const fmt=n=>n==null?'—':Math.round(n).toLocaleString('ko-KR');
  const fp=v=>v==null?'—':(v>0?'+':'')+Number(v).toFixed(1)+'%';
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const rel=(price,level)=>price==null||level==null||!level?null:(price/level-1)*100;

  // --- style (injected once) ---
  if(!document.getElementById('mx-style')){
    const st=document.createElement('style');
    st.id='mx-style';
    st.textContent=
    '.mx-sec{background:#0c1b28;border:1px solid #22344e;border-radius:16px;padding:16px 18px;margin:14px 0;line-height:1.65;color:#edf4ff}'+
    '.mx-h{font-size:12px;font-weight:900;letter-spacing:.08em;color:#73b7ff;margin:0 0 10px}'+
    '.mx-price{font-size:28px;font-weight:900}'+
    '.mx-sub{color:#91a4bf;font-size:12px;line-height:1.6}'+
    '.mx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin:8px 0}'+
    '.mx-kv{background:#101d30;border:1px solid #22344e;border-radius:12px;padding:9px 12px}'+
    '.mx-k{font-size:11px;color:#91a4bf}'+
    '.mx-v{font-size:16px;font-weight:800}'+
    '.mx-tbl{width:100%;border-collapse:collapse;font-size:13px}'+
    '.mx-tbl td{padding:6px 6px;border-bottom:1px solid #1b2c44;vertical-align:top}'+
    '.mx-tbl td:first-child{color:#91a4bf;width:34%;white-space:nowrap}'+
    '.mx-chk{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:4px 14px;font-size:13px}'+
    '.mx-ok{color:#63e6be}.mx-no{color:#5f748c}'+
    '.mx-note{font-size:12px;color:#91a4bf;line-height:1.7}'+
    '.mx-sec ul{margin:6px 0;padding-left:18px;line-height:1.75;font-size:13px}'+
    '.mx-sec a{color:#73b7ff}'+
    '.mx-pos{background:#101d30;border:1px solid #22344e;border-radius:12px;padding:10px 12px;font-size:13px;margin:8px 0}';
    document.head.appendChild(st);
  }

  // --- locate stale static signal sections: keep the first as anchor, drop duplicates ---
  const stale=[...document.querySelectorAll('section')].filter(el=>/CURRENT BUY SIGNAL/.test(el.textContent||''));
  let anchor=stale[0]||null;
  stale.slice(1).forEach(el=>el.remove());
  // legacy .sig blocks that are not the anchor get dimmed (original snapshot)
  const snapshot=document.querySelector('.sig');
  if(snapshot&&snapshot!==anchor){
    const tag=snapshot.querySelector('b.up');
    if(tag)tag.textContent='ORIGINAL ANALYSIS SNAPSHOT';
    snapshot.style.opacity='.58';
    snapshot.style.borderColor='#304454';
  }

  const RAW='https://raw.githubusercontent.com/sasohanbam-wq/Mingo/main/';
  let s=null, regime=null, calcLabel=null, ev=null;
  try{
    const r=await fetch(RAW+'data/live_scores.json?t='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    s=(d.stocks||[]).find(x=>x.code===code);
    regime=d.market_regime||null;
    calcLabel=d.calculated_at_label||d.calculated_at||null;
    if(!s)return;
  }catch(e){
    console.warn('MINGO live data unavailable',e);
    return;
  }
  try{
    const r2=await fetch(RAW+'data/research_evidence.json?t='+Date.now(),{cache:'no-store'});
    if(r2.ok){ const ed=await r2.json(); ev=(ed.stocks||{})[code]||null; }
  }catch(e){ /* evidence detail optional */ }

  const stateColor=s.state==='green'?'#63e6be':s.state==='blue'?'#73b7ff':s.state==='red'?'#ff7b7b':'#ffd166';
  const setupNames={trend:'추세추종',pullback:'눌림',breakout:'돌파',recovery:'회복 확인형'};
  const chk=(ok,label)=>'<div class="'+(ok?'mx-ok':'mx-no')+'">'+(ok?'✅':'⬜')+' '+esc(label)+'</div>';

  function positionText(s){
    const p=s.price,z=s.buy_zone,t=s.trigger;
    if(s.invalidated)return '무효화 가격을 이탈했습니다. 이 셋업은 종료 상태입니다.';
    if(s.in_buy_zone)return '현재가가 매수구간 안에 있습니다. 지지/반전 확인이 승격의 마지막 관문입니다.';
    if(p!=null&&z&&z[1]!=null&&p>z[1]&&t!=null&&p<t)return '현재가는 매수구간 위, 돌파 트리거 아래에 있습니다. 눌림을 기다리거나 종가 돌파 확인이 필요합니다.';
    if(p!=null&&t!=null&&p>=t)return '현재가가 트리거 위에 있습니다. 종가 안착과 거래량 확인이 남았습니다.';
    if(p!=null&&z&&z[0]!=null&&p<z[0])return '현재가가 매수구간 아래에 있습니다. 구간 회복이나 지지 형성을 먼저 확인해야 합니다.';
    return '셋업 조건을 확인 중입니다.';
  }

  const zone=s.buy_zone&&s.buy_zone[0]!=null?fmt(s.buy_zone[0])+'~'+fmt(s.buy_zone[1])+'원':'—';
  const dTrig=rel(s.trigger,s.price);      // 트리거까지 남은 거리
  const dInv=rel(s.price,s.invalidation);  // 무효화까지 여유
  const snapNote=s.price_mode==='manual_snapshot'
    ? '수동 조회 현재가 '+(s.price_timestamp?esc(String(s.price_timestamp).slice(11,16)):'')+' 반영 · 일봉 지표는 완료세션 기준'
    : '완료세션 종가 기준';

  let html='';

  // ---------- 1) LIVE GATE ----------
  html+='<div class="mx-h">MINGO V2 · LIVE GATE</div>'
    +'<div style="font-size:22px;font-weight:900;color:'+stateColor+'">'+esc(s.label||'')+'</div>'
    +'<div class="mx-price">'+fmt(s.price)+'원 <span style="font-size:14px;color:'+(s.change_pct>=0?'#63e6be':'#ff7b7b')+'">'+fp(s.change_pct)+'</span></div>'
    +'<div class="mx-sub">가격 기준 '+(s.quote_as_of||'—')+' · 기대 완료세션 '+(s.expected_completed_session||'—')+' · 세션 '+(s.session||'—')+'<br>'+snapNote+'</div>'
    +'<div class="mx-pos"><b>현재 위치:</b> '+esc(positionText(s))+'<br><b>판정 이유:</b> '+esc(s.setup_reason||'—')+'</div>'
    +'<table class="mx-tbl">'
    +'<tr><td>셋업 유형</td><td>'+esc(setupNames[s.setup_type]||s.setup_type||'—')+'</td></tr>'
    +'<tr><td>매수구간</td><td>'+zone+'</td></tr>'
    +'<tr><td>돌파 트리거</td><td>'+fmt(s.trigger)+'원'+(dTrig!=null?' <span class="mx-sub">(현재가에서 '+fp(dTrig)+')</span>':'')+'</td></tr>'
    +'<tr><td>무효화</td><td>'+fmt(s.invalidation)+'원'+(dInv!=null?' <span class="mx-sub">(여유 '+fp(dInv)+')</span>':'')+'</td></tr>'
    +'<tr><td>실행점수</td><td>'+(s.execution_score??'—')+' <span class="mx-sub">(기술 '+(s.technical_score??'—')+' · 추세 '+(s.trend_score??'—')+' · 상대수익 '+(s.relative_return_score??'—')+' · 레짐 보정 '+(s.regime_adjustment>=0?'+':'')+(s.regime_adjustment??'—')+')</span></td></tr>'
    +'</table>'
    +'<div class="mx-h" style="margin-top:12px">게이트 조건표</div>'
    +'<div class="mx-chk">'
    +chk(!!s.in_buy_zone,'매수구간 진입')
    +chk(!!s.support_or_reversal_confirmed,'지지/반전 확인')
    +chk(!!s.breakout_confirmed,'돌파 확인'+(s.breakout_cross_date?' ('+esc(s.breakout_cross_date)+')':''))
    +chk(!!s.trend_valid,'추세 유효 (MA20 위)')
    +chk(!s.overheated,'과열 아님')
    +chk(!s.invalidated,'무효화 이탈 아님')
    +chk(!s.regime_blocked,'레짐 차단 없음')
    +chk(s.evidence_status==='verified','기업근거 verified')
    +chk(!!s.setup_pass,'셋업 통과')
    +'</div>'
    +(s.regime_blocked?'<div class="mx-pos" style="color:#ff7b7b"><b>레짐 차단:</b> '+esc(s.regime_blocked)+'</div>':'')
    +(s.live_triggered?'<div class="mx-pos">📌 장중 트리거 터치 기록 있음 (종가 확정 전 승격 아님)</div>':'')
    +(s.live_in_buy_zone&&!s.in_buy_zone?'<div class="mx-pos">📌 장중 매수구간 진입 기록 있음 (완료세션 기준 판정과 별개)</div>':'');

  // ---------- 2) PRICE / TECHNICALS ----------
  const maRow=(name,v)=>'<tr><td>'+name+'</td><td>'+fmt(v)+'원 <span class="mx-sub">(현재가 '+fp(rel(s.price,v))+')</span></td></tr>';
  html+='<div class="mx-h" style="margin-top:16px">📊 가격 · 기술 상세 (완료세션 일봉 기준)</div>'
    +'<div class="mx-grid">'
    +'<div class="mx-kv"><div class="mx-k">Wilder RSI(14)</div><div class="mx-v">'+(s.rsi14_wilder??'—')+'</div></div>'
    +'<div class="mx-kv"><div class="mx-k">거래량 비율 (20일 평균 대비)</div><div class="mx-v">'+(s.volume_ratio==null?'—':Number(s.volume_ratio).toFixed(2)+'배')+'</div></div>'
    +'<div class="mx-kv"><div class="mx-k">20일 고가 / 저가</div><div class="mx-v" style="font-size:14px">'+fmt(s.high20_actual)+' / '+fmt(s.low20_actual)+'</div></div>'
    +'<div class="mx-kv"><div class="mx-k">MA20 이격</div><div class="mx-v">'+fp(s.extension_ma20_pct)+'</div></div>'
    +'</div>'
    +'<table class="mx-tbl">'
    +maRow('MA20',s.ma20)+maRow('MA50',s.ma50)+maRow('MA200',s.ma200)
    +'<tr><td>지수 대비 초과수익 20일</td><td>'+fp(s.excess_return_20d_pct)+'</td></tr>'
    +'<tr><td>지수 대비 초과수익 60일</td><td>'+fp(s.excess_return_60d_pct)+'</td></tr>'
    +'<tr><td>상대 이격 (종목−지수)</td><td>'+fp(s.excess_extension_ma20_pct)+'</td></tr>'
    +'<tr><td>데이터 상태</td><td>'+esc(s.data_status||'—')+' · 벤치마크 '+(s.benchmark_status||'—')+' ('+(s.benchmark_as_of||'—')+')</td></tr>'
    +'</table>';

  // ---------- 3) EVIDENCE F/E/V ----------
  const fName={F:'Fundamental (실적·재무)',E:'Estimate (추정치·컨센서스)',V:'Valuation (밸류에이션)'};
  const fScore={F:s.research_F,E:s.research_E,V:s.research_V};
  const fStatus={F:s.research_F_status,E:s.research_E_status,V:s.research_V_status};
  let evRows='';
  ['F','E','V'].forEach(k=>{
    const e=ev?ev[k]:null;
    evRows+='<tr><td>'+fName[k]+'</td><td><b>'+(fScore[k]??'—')+'</b> · '+esc(fStatus[k]||'—')
      +(e&&e.grade?' · 등급 '+esc(e.grade):'')
      +(e&&e.as_of?' · 기준 '+esc(e.as_of):'')
      +'<br><span class="mx-sub">'+esc(e&&e.basis?e.basis:'근거 상세 없음 — research_evidence.json에 아직 등록되지 않았습니다.')+'</span></td></tr>';
  });
  html+='<div class="mx-h" style="margin-top:16px">🧾 기업 근거 F/E/V</div>'
    +'<table class="mx-tbl">'
    +'<tr><td>근거 상태</td><td>'+esc(s.evidence_status||'—')+'</td></tr>'
    +'<tr><td>연구점수</td><td>'+(s.research_score??'미생성')+' <span class="mx-sub">'+esc(s.research_score_status||'')+'</span></td></tr>'
    +evRows
    +'</table>'
    +((s.evidence_notes&&s.evidence_notes.length)
      ?'<div class="mx-h" style="margin-top:10px">검증 노트</div><ul>'+s.evidence_notes.map(n=>'<li>'+esc(n)+'</li>').join('')+'</ul>'
      :'')
    +((s.evidence_sources&&s.evidence_sources.length)
      ?'<div class="mx-note">출처: '+s.evidence_sources.map(u=>'<a href="'+esc(u)+'" target="_blank" rel="noopener">근거 문서</a>').join(' · ')+'</div>'
      :'')
    +'<div class="mx-note">기존 F/E/V(F '+(s.legacy_F??'—')+' · E '+(s.legacy_E??'—')+' · V '+(s.legacy_V??'—')+' · PR '+(s.legacy_PR??'—')+')는 감사용 구값입니다. 세 요인이 모두 verified일 때만 연구점수를 생성하고, 연구점수 70 미만은 셋업이 좋아도 확정 🟢가 되지 않습니다.</div>';

  // ---------- 4) NEXT CHECKS ----------
  html+='<div class="mx-h" style="margin-top:16px">🔭 다음에 확인할 것</div>'
    +((s.research_next_check&&s.research_next_check.length)
      ?'<ul>'+s.research_next_check.map(n=>'<li>'+esc(n)+'</li>').join('')+'</ul>'
      :'<div class="mx-note">등록된 후속 확인 사항이 없습니다.</div>');

  // ---------- 5) REGIME ----------
  if(regime){
    const idx=regime.indices||{};
    const idxLine=Object.keys(idx).map(k=>{
      const i=idx[k];
      return esc(k)+' '+i.points+'점 (종가 '+fmt(i.close)+' · MA20 '+fmt(i.ma20)+' · MA60 '+fmt(i.ma60)+' · 20일 '+fp(i.return_20d_pct)+')';
    }).join('<br>');
    html+='<div class="mx-h" style="margin-top:16px">🌡️ 시장 레짐 ('+(regime.as_of||'—')+' 기준)</div>'
      +'<div style="font-size:15px"><b>'+esc(regime.label||'')+'</b> · 평균 '+regime.points_avg+'점 · 실행점수 보정 '+(regime.execution_adjustment>=0?'+':'')+regime.execution_adjustment+'</div>'
      +'<div class="mx-note">'+idxLine+'</div>';
  }

  html+='<div class="mx-note" style="margin-top:14px">이 패널은 data/live_scores.json 기준으로 자동 생성됩니다 (계산: '+esc(calcLabel||'—')+'). 고정 텍스트가 아니며, 데이터 출처: '+esc(s.source||'—')+'</div>';

  // ---------- mount ----------
  let box;
  if(anchor){
    box=anchor;
    box.removeAttribute('style');
    box.className='mx-sec';
    box.style.border='2px solid '+stateColor;
  }else{
    box=document.createElement('section');
    box.className='mx-sec';
    box.style.border='2px solid '+stateColor;
    const h1=document.querySelector('h1');
    const thesis=h1?h1.nextElementSibling:null;
    (thesis||h1||document.body).insertAdjacentElement('afterend',box);
  }
  box.innerHTML=html;
})();
