(async()=>{
  const m=document.body.innerText.match(/\b\d{6}\b/);
  if(!m)return;
  const code=m[0];
  const fmt=n=>n==null?'—':Math.round(n).toLocaleString('ko-KR');
  const fp=v=>v==null?'—':(v>0?'+':'')+Number(v).toFixed(1)+'%';
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const rel=(price,level)=>price==null||level==null||!level?null:(price/level-1)*100;

  // ---------- global page polish (applies to the static parts too) ----------
  if(!document.getElementById('mxg-style')){
    const g=document.createElement('style');
    g.id='mxg-style';
    g.textContent=
    'body{background:radial-gradient(1100px 520px at 88% -90px,rgba(115,183,255,.14),rgba(115,183,255,0) 60%),radial-gradient(900px 500px at -12% 260px,rgba(99,230,190,.09),rgba(99,230,190,0) 55%),#08111f!important}'
    +'h1{letter-spacing:-.02em;font-variant-numeric:tabular-nums}'
    +'h2{border-bottom:1px solid rgba(120,160,220,.16);padding-bottom:8px;letter-spacing:-.01em}'
    +'.card,.box,.sig{box-shadow:0 12px 30px rgba(0,0,0,.32);background-image:linear-gradient(160deg,rgba(255,255,255,.05),rgba(255,255,255,0) 55%)}'
    +'.eyebrow{display:inline-block;padding:5px 12px;border:1px solid rgba(99,230,190,.4);border-radius:99px;background:rgba(99,230,190,.08);font-size:11px}'
    +'.node{box-shadow:0 8px 20px rgba(0,0,0,.28)}'
    +'.score{font-variant-numeric:tabular-nums}'
    +'.tag{border-radius:99px}';
    document.head.appendChild(g);
  }

  // ---------- panel design system ----------
  if(!document.getElementById('mx-style')){
    const st=document.createElement('style');
    st.id='mx-style';
    st.textContent=
    '.mx-sec{background:linear-gradient(165deg,#0d1c2e,#0a1626 62%);border:1px solid #22344e;border-radius:20px;padding:20px;margin:14px 0;line-height:1.65;color:#edf4ff;box-shadow:0 16px 42px rgba(0,0,0,.4);animation:mxUp .5s ease both;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans KR",sans-serif}'
    +'@keyframes mxUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}'
    +'.mx-h{font-size:12.5px;font-weight:900;letter-spacing:.1em;color:#9fd0ff;margin:20px 0 10px;display:flex;align-items:center;gap:8px}'
    +'.mx-h::before{content:"";width:4px;height:14px;border-radius:2px;background:linear-gradient(180deg,#73b7ff,#63e6be);flex:none}'
    +'.mx-h:first-child{margin-top:0}'
    +'.mx-top{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}'
    +'.mx-state{font-size:23px;font-weight:900;display:flex;align-items:center;gap:9px;margin-top:2px}'
    +'.mx-dot{width:12px;height:12px;border-radius:50%;display:inline-block;flex:none;animation:mxPulse 1.9s ease-out infinite}'
    +'@keyframes mxPulse{0%{box-shadow:0 0 0 0 rgba(255,255,255,.35)}70%{box-shadow:0 0 0 9px rgba(255,255,255,0)}100%{box-shadow:0 0 0 0 rgba(255,255,255,0)}}'
    +'.mx-live{font-size:10px;font-weight:900;color:#ff8f8f;letter-spacing:.14em;margin-left:6px}'
    +'.mx-price{font-size:34px;font-weight:900;letter-spacing:-.01em;font-variant-numeric:tabular-nums;line-height:1.25}'
    +'.mx-chg{font-size:13.5px;font-weight:800;padding:3px 10px;border-radius:99px;vertical-align:middle}'
    +'.mx-chg.up{background:rgba(99,230,190,.13);color:#63e6be}.mx-chg.dn{background:rgba(255,123,123,.13);color:#ff7b7b}'
    +'.mx-sub{color:#91a4bf;font-size:12px;line-height:1.6}'
    +'.mx-tr{display:flex;gap:16px;align-items:flex-start}'
    +'.mx-donut{width:92px;text-align:center;flex:none}'
    +'.mx-dl{text-align:center;font-size:11.5px;color:#91a4bf;margin-top:1px}'
    +'.mx-pos{background:linear-gradient(90deg,rgba(115,183,255,.09),rgba(115,183,255,.02));border:1px solid #22344e;border-left:4px solid #73b7ff;border-radius:12px;padding:11px 14px;font-size:13.5px;margin:12px 0}'
    +'.mx-pos.warn{border-left-color:#ff7b7b;background:linear-gradient(90deg,rgba(255,123,123,.1),rgba(255,123,123,.02))}'
    +'.mx-map{margin:6px 0 2px}'
    +'.mx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:8px 0}'
    +'.mx-kv{background:#0e1a2c;border:1px solid #22344e;border-radius:14px;padding:11px 13px}'
    +'.mx-k{font-size:11px;color:#91a4bf;margin-bottom:2px}'
    +'.mx-v{font-size:17px;font-weight:800;font-variant-numeric:tabular-nums}'
    +'.mx-minibar{height:6px;background:#16263e;border-radius:99px;margin-top:8px;overflow:hidden}'
    +'.mx-minibar div{height:100%;border-radius:99px}'
    +'.mx-gtrack{position:relative;height:10px;border-radius:99px;background:linear-gradient(90deg,#5b8def,#63e6be 32%,#ffd166 68%,#ff7b7b);margin-top:9px}'
    +'.mx-gtrack.flat{background:linear-gradient(90deg,#27435f,#3f6ea6)}'
    +'.mx-gmark{position:absolute;top:-3px;width:4px;height:16px;border-radius:2px;background:#fff;box-shadow:0 0 0 2px rgba(0,0,0,.4);transform:translateX(-2px)}'
    +'.mx-glab{display:flex;justify-content:space-between;font-size:10.5px;color:#5f748c;margin-top:4px}'
    +'.mx-tbl{width:100%;border-collapse:collapse;font-size:13px}'
    +'.mx-tbl td{padding:7px 8px;border-bottom:1px solid rgba(120,160,220,.12);vertical-align:top}'
    +'.mx-tbl td:first-child{color:#91a4bf;width:32%;white-space:nowrap;font-size:12.5px}'
    +'.mx-sbar{display:grid;grid-template-columns:64px 1fr 40px;gap:10px;align-items:center;margin:5px 0;font-size:12.5px}'
    +'.mx-sbt{height:9px;background:#101d30;border-radius:99px;overflow:hidden}'
    +'.mx-sbf{height:100%;border-radius:99px}'
    +'.mx-sbv{text-align:right;font-weight:800;font-variant-numeric:tabular-nums}'
    +'.mx-dbar{display:grid;grid-template-columns:92px 1fr 128px;gap:10px;align-items:center;margin:6px 0;font-size:12.5px}'
    +'.mx-dbt{position:relative;height:10px;background:#101d30;border-radius:99px}'
    +'.mx-dbc{position:absolute;left:50%;top:-2px;bottom:-2px;width:1px;background:#3a506e}'
    +'.mx-dbf{position:absolute;top:0;height:10px;border-radius:99px}'
    +'.mx-dbv{text-align:right;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}'
    +'.mx-prog{height:9px;background:#101d30;border-radius:99px;overflow:hidden;margin:4px 0 11px}'
    +'.mx-progf{height:100%;border-radius:99px;background:linear-gradient(90deg,#73b7ff,#63e6be)}'
    +'.mx-chk{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:6px}'
    +'.mx-chip{border:1px solid #22344e;border-radius:10px;padding:7px 10px;font-size:12.5px;background:#0e1a2c;color:#5f748c}'
    +'.mx-chip.on{border-color:rgba(99,230,190,.45);background:rgba(99,230,190,.07);color:#a7f3d0}'
    +'.mx-fev{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:10px}'
    +'.mx-fcard{background:#0e1a2c;border:1px solid #22344e;border-radius:16px;padding:15px;text-align:center}'
    +'.mx-fcard .mx-donut{margin:2px auto}'
    +'.mx-fname{font-size:13px;font-weight:800;text-align:left}'
    +'.mx-pill{display:inline-block;font-size:11px;font-weight:800;border-radius:99px;padding:3px 9px}'
    +'.mx-pill.v{background:rgba(99,230,190,.14);color:#63e6be}.mx-pill.p{background:rgba(255,209,102,.14);color:#ffd166}.mx-pill.n{background:rgba(145,164,191,.14);color:#91a4bf}'
    +'.mx-basis{font-size:12.5px;color:#aebdd2;line-height:1.65;margin-top:9px;text-align:left}'
    +'.mx-note{font-size:12px;color:#91a4bf;line-height:1.7}'
    +'.mx-sec ul{margin:6px 0;padding-left:18px;line-height:1.75;font-size:13px}'
    +'.mx-sec a{color:#73b7ff}'
    +'.mx-src{display:inline-block;border:1px solid #2b4a6e;background:#0e1a2c;border-radius:99px;padding:4px 11px;font-size:11.5px;margin:2px 3px 2px 0;text-decoration:none}'
    +'.mx-nc{display:flex;flex-wrap:wrap;gap:6px}'
    +'.mx-nc span{border:1px solid #22344e;background:#101d30;border-radius:99px;padding:6px 12px;font-size:12.5px}'
    +'.mx-reg{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:10px}'
    +'.mx-rcard{background:#0e1a2c;border:1px solid #22344e;border-radius:16px;padding:14px}'
    +'.mx-dots{font-size:15px;letter-spacing:3px;color:#63e6be}'
    +'.mx-dots i{color:#2c4258;font-style:normal}'
    +'@media(max-width:640px){.mx-price{font-size:29px}.mx-dbar{grid-template-columns:74px 1fr 104px}.mx-tr{gap:10px}}';
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
  const setupNames={trend:'추세추종',pullback:'눌림',breakout:'돌파',recovery:'회복 확인형',value_swing:'가치 스윙'};
  const scoreColor=v=>v==null?'#5f748c':v>=70?'#63e6be':v>=50?'#ffd166':'#ff9d7b';

  function donut(score,label){
    if(score==null){
      return '<div class="mx-donut"><svg viewBox="0 0 92 92" width="92" height="92"><circle cx="46" cy="46" r="41.5" fill="none" stroke="#1c2c44" stroke-width="9"/><text x="46" y="53" text-anchor="middle" font-size="22" font-weight="900" fill="#5f748c">—</text></svg><div class="mx-dl">'+label+'</div></div>';
    }
    const c=2*Math.PI*41.5, arc=Math.max(0,Math.min(100,score))/100*c;
    return '<div class="mx-donut"><svg viewBox="0 0 92 92" width="92" height="92">'
      +'<circle cx="46" cy="46" r="41.5" fill="none" stroke="#1c2c44" stroke-width="9"/>'
      +'<circle cx="46" cy="46" r="41.5" fill="none" stroke="'+scoreColor(score)+'" stroke-width="9" stroke-linecap="round" stroke-dasharray="'+arc.toFixed(1)+' '+c.toFixed(1)+'" transform="rotate(-90 46 46)"/>'
      +'<text x="46" y="53" text-anchor="middle" font-size="24" font-weight="900" fill="#edf4ff">'+score+'</text></svg>'
      +'<div class="mx-dl">'+label+'</div></div>';
  }

  function priceMap(s){
    if(s.price==null)return '';
    const vals=[s.price,s.trigger,s.invalidation,s.ma20,s.high20_actual,s.low20_actual].concat(s.buy_zone||[]).filter(v=>v!=null);
    if(vals.length<2)return '';
    let lo=Math.min.apply(null,vals), hi=Math.max.apply(null,vals);
    const pad=(hi-lo)*0.06||hi*0.02||1; lo-=pad; hi+=pad;
    const W=720,X0=14,X1=W-14;
    const X=v=>X0+(v-lo)/(hi-lo)*(X1-X0);
    const cl=x=>Math.max(46,Math.min(W-46,x));
    let g='';
    g+='<defs><linearGradient id="mxgrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#27435f"/><stop offset=".55" stop-color="#3f6ea6"/><stop offset="1" stop-color="#2f7d68"/></linearGradient></defs>';
    g+='<rect x="'+X0+'" y="34" width="'+(X1-X0)+'" height="16" rx="8" fill="url(#mxgrad)" opacity=".55"/>';
    if(s.buy_zone&&s.buy_zone[0]!=null&&s.buy_zone[1]!=null){
      const zx=X(s.buy_zone[0]),zw=Math.max(3,X(s.buy_zone[1])-zx);
      g+='<rect x="'+zx.toFixed(1)+'" y="32" width="'+zw.toFixed(1)+'" height="20" rx="9" fill="rgba(99,230,190,.22)" stroke="rgba(99,230,190,.65)" stroke-width="1.2"/>';
      g+='<text x="'+cl(zx+zw/2)+'" y="27" text-anchor="middle" font-size="11" font-weight="700" fill="#63e6be">매수구간 '+fmt(s.buy_zone[0])+'~'+fmt(s.buy_zone[1])+'</text>';
    }
    const tickB=(v,color,label)=>{
      if(v==null)return '';
      const x=X(v);
      return '<line x1="'+x.toFixed(1)+'" y1="28" x2="'+x.toFixed(1)+'" y2="56" stroke="'+color+'" stroke-width="2"/>'
        +'<text x="'+cl(x)+'" y="74" text-anchor="middle" font-size="11.5" font-weight="700" fill="'+color+'">'+label+'</text>';
    };
    g+=tickB(s.invalidation,'#ff7b7b','무효화 '+fmt(s.invalidation));
    g+=tickB(s.trigger,'#73b7ff','트리거 '+fmt(s.trigger));
    if(s.ma20!=null){
      const x=X(s.ma20);
      g+='<line x1="'+x.toFixed(1)+'" y1="30" x2="'+x.toFixed(1)+'" y2="54" stroke="#8fa5c0" stroke-width="1.4" stroke-dasharray="3 3"/>'
        +'<text x="'+cl(x)+'" y="92" text-anchor="middle" font-size="11" fill="#8fa5c0">MA20 '+fmt(s.ma20)+'</text>';
    }
    if(s.low20_actual!=null)g+='<text x="'+X0+'" y="92" font-size="11" fill="#5f748c">20일 저가 '+fmt(s.low20_actual)+'</text>';
    if(s.high20_actual!=null)g+='<text x="'+X1+'" y="92" text-anchor="end" font-size="11" fill="#5f748c">20일 고가 '+fmt(s.high20_actual)+'</text>';
    const px=X(s.price);
    g+='<circle cx="'+px.toFixed(1)+'" cy="42" r="11" fill="'+stateColor+'" opacity=".25"/>'
      +'<line x1="'+px.toFixed(1)+'" y1="24" x2="'+px.toFixed(1)+'" y2="60" stroke="'+stateColor+'" stroke-width="2.4"/>'
      +'<circle cx="'+px.toFixed(1)+'" cy="42" r="5.5" fill="'+stateColor+'" stroke="#0a1626" stroke-width="2"/>'
      +'<text x="'+cl(px)+'" y="15" text-anchor="middle" font-size="14.5" font-weight="900" fill="#ffffff">현재가 '+fmt(s.price)+'원</text>';
    return '<div class="mx-map"><svg viewBox="0 0 720 100" style="width:100%;height:auto;display:block" role="img" aria-label="가격 위치 맵">'+g+'</svg></div>';
  }

  function devBar(label,pct,valText,cap){
    if(pct==null)return '<div class="mx-dbar"><div>'+label+'</div><div class="mx-dbt"><div class="mx-dbc"></div></div><div class="mx-dbv">—</div></div>';
    const w=Math.min(Math.abs(pct)/cap*50,50);
    const col=pct>=0?'#63e6be':'#ff7b7b';
    const bar=pct>=0
      ?'<div class="mx-dbf" style="left:50%;width:'+w.toFixed(1)+'%;background:'+col+'"></div>'
      :'<div class="mx-dbf" style="left:'+(50-w).toFixed(1)+'%;width:'+w.toFixed(1)+'%;background:'+col+'"></div>';
    return '<div class="mx-dbar"><div>'+label+'</div><div class="mx-dbt"><div class="mx-dbc"></div>'+bar+'</div><div class="mx-dbv" style="color:'+col+'">'+valText+'</div></div>';
  }

  function scoreBar(label,v){
    if(v==null)return '';
    return '<div class="mx-sbar"><div>'+label+'</div><div class="mx-sbt"><div class="mx-sbf" style="width:'+Math.max(0,Math.min(100,v))+'%;background:'+scoreColor(v)+'"></div></div><div class="mx-sbv">'+v+'</div></div>';
  }

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
  const dTrig=rel(s.trigger,s.price);
  const dInv=rel(s.price,s.invalidation);
  const snapNote=s.price_mode==='manual_snapshot'
    ? '수동 조회 현재가 '+(s.price_timestamp?esc(String(s.price_timestamp).slice(11,16)):'')+' 반영 · 일봉 지표는 완료세션 기준'
    : '완료세션 종가 기준';

  let html='';

  // ---------- 1) LIVE GATE header ----------
  html+='<div class="mx-top"><div>'
    +'<div class="mx-h" style="margin:0">MINGO V2 · LIVE GATE<span class="mx-live">● LIVE</span></div>'
    +'<div class="mx-state" style="color:'+stateColor+'"><span class="mx-dot" style="background:'+stateColor+'"></span>'+esc(s.label||'')+'</div>'
    +'<div class="mx-price">'+fmt(s.price)+'원 <span class="mx-chg '+(s.change_pct>=0?'up':'dn')+'">'+fp(s.change_pct)+'</span></div>'
    +'<div class="mx-sub">가격 기준 '+(s.quote_as_of||'—')+' · 기대 완료세션 '+(s.expected_completed_session||'—')+' · 세션 '+(s.session||'—')+'<br>'+snapNote+'</div>'
    +'</div><div class="mx-tr">'
    +donut(s.execution_score,'실행점수')
    +donut(s.research_score,'연구점수'+(s.research_score==null?' (미생성)':''))
    +'</div></div>'
    +'<div class="mx-pos'+(s.invalidated?' warn':'')+'"><b>현재 위치:</b> '+esc(positionText(s))+'<br><b>판정 이유:</b> '+esc(s.setup_reason||'—')+'</div>';

  // ---------- 2) PRICE MAP + setup ----------
  html+='<div class="mx-h">🗺️ 가격 맵 — 구간 · 트리거 · 무효화</div>'
    +priceMap(s)
    +'<table class="mx-tbl">'
    +'<tr><td>셋업 유형</td><td>'+esc(setupNames[s.setup_type]||s.setup_type||'—')+'</td></tr>'
    +'<tr><td>매수구간</td><td>'+zone+'</td></tr>'
    +'<tr><td>돌파 트리거</td><td>'+fmt(s.trigger)+'원'+(dTrig!=null?' <span class="mx-sub">(현재가에서 '+fp(dTrig)+')</span>':'')+'</td></tr>'
    +'<tr><td>무효화</td><td>'+fmt(s.invalidation)+'원'+(dInv!=null?' <span class="mx-sub">(여유 '+fp(dInv)+')</span>':'')+'</td></tr>'
    +'</table>'
    +'<div class="mx-h">실행점수 구성</div>'
    +scoreBar('기술',s.technical_score)
    +scoreBar('추세',s.trend_score)
    +scoreBar('상대수익',s.relative_return_score)
    +'<div class="mx-note">레짐 보정 '+(s.regime_adjustment>=0?'+':'')+(s.regime_adjustment??'—')+' ('+esc(s.regime_label||'')+') 포함 → 실행점수 <b style="color:#edf4ff">'+(s.execution_score??'—')+'</b></div>';

  // ---------- 3) GATE checklist ----------
  const checks=[
    [!!s.in_buy_zone,'매수구간 진입'],
    [!!s.support_or_reversal_confirmed,'지지/반전 확인'],
    [!!s.breakout_confirmed,'돌파 확인'+(s.breakout_cross_date?' ('+esc(s.breakout_cross_date)+')':'')],
    [!!s.trend_valid,'추세 유효 (MA20 위)'],
    [!s.overheated,'과열 아님'],
    [!s.invalidated,'무효화 이탈 아님'],
    [!s.regime_blocked,'레짐 차단 없음'],
    [s.evidence_status==='verified','기업근거 verified'],
    [!!s.setup_pass,'셋업 통과']
  ];
  const met=checks.filter(c=>c[0]).length;
  html+='<div class="mx-h">게이트 조건표 <span style="margin-left:auto;letter-spacing:0" class="mx-pill '+(met===checks.length?'v':'p')+'">'+met+' / '+checks.length+' 충족</span></div>'
    +'<div class="mx-prog"><div class="mx-progf" style="width:'+(met/checks.length*100).toFixed(0)+'%"></div></div>'
    +'<div class="mx-chk">'+checks.map(c=>'<div class="mx-chip'+(c[0]?' on':'')+'">'+(c[0]?'✅':'⬜')+' '+c[1]+'</div>').join('')+'</div>'
    +(s.regime_blocked?'<div class="mx-pos warn"><b>레짐 차단:</b> '+esc(s.regime_blocked)+'</div>':'')
    +(s.live_triggered?'<div class="mx-pos">📌 장중 트리거 터치 기록 있음 (종가 확정 전 승격 아님)</div>':'')
    +(s.live_in_buy_zone&&!s.in_buy_zone?'<div class="mx-pos">📌 장중 매수구간 진입 기록 있음 (완료세션 기준 판정과 별개)</div>':'');

  // ---------- 4) PRICE / TECHNICALS ----------
  const rsi=s.rsi14_wilder;
  const volW=s.volume_ratio==null?0:Math.min(s.volume_ratio/2*100,100);
  const rangePos=(s.price!=null&&s.high20_actual!=null&&s.low20_actual!=null&&s.high20_actual>s.low20_actual)
    ?Math.max(0,Math.min(100,(s.price-s.low20_actual)/(s.high20_actual-s.low20_actual)*100)):null;
  html+='<div class="mx-h">📊 가격 · 기술 상세 (완료세션 일봉 기준)</div>'
    +'<div class="mx-grid">'
    +'<div class="mx-kv"><div class="mx-k">Wilder RSI(14)</div><div class="mx-v">'+(rsi??'—')+'</div>'
    +(rsi!=null?'<div class="mx-gtrack"><div class="mx-gmark" style="left:'+Math.max(0,Math.min(100,rsi))+'%"></div></div><div class="mx-glab"><span>0 · 과매도 30</span><span>과열 70 · 100</span></div>':'')
    +'</div>'
    +'<div class="mx-kv"><div class="mx-k">거래량 비율 (20일 평균 대비)</div><div class="mx-v">'+(s.volume_ratio==null?'—':Number(s.volume_ratio).toFixed(2)+'배')+'</div>'
    +(s.volume_ratio!=null?'<div class="mx-minibar"><div style="width:'+volW.toFixed(0)+'%;background:#73b7ff"></div></div><div class="mx-glab"><span>0</span><span>2.0배 = 풀바</span></div>':'')
    +'</div>'
    +'<div class="mx-kv"><div class="mx-k">20일 구간 내 위치</div><div class="mx-v">'+(rangePos==null?'—':rangePos.toFixed(0)+'%')+'</div>'
    +(rangePos!=null?'<div class="mx-gtrack flat"><div class="mx-gmark" style="left:'+rangePos.toFixed(1)+'%"></div></div><div class="mx-glab"><span>저가 '+fmt(s.low20_actual)+'</span><span>고가 '+fmt(s.high20_actual)+'</span></div>':'')
    +'</div>'
    +'<div class="mx-kv"><div class="mx-k">MA20 이격</div><div class="mx-v">'+fp(s.extension_ma20_pct)+'</div><div class="mx-note">지수 대비 상대 이격 '+fp(s.excess_extension_ma20_pct)+'</div></div>'
    +'</div>'
    +'<div class="mx-h">이동평균 대비 위치</div>'
    +devBar('MA20',rel(s.price,s.ma20),fmt(s.ma20)+'원 · '+fp(rel(s.price,s.ma20)),30)
    +devBar('MA50',rel(s.price,s.ma50),fmt(s.ma50)+'원 · '+fp(rel(s.price,s.ma50)),30)
    +devBar('MA200',rel(s.price,s.ma200),fmt(s.ma200)+'원 · '+fp(rel(s.price,s.ma200)),30)
    +'<div class="mx-h">지수 대비 초과수익</div>'
    +devBar('20일',s.excess_return_20d_pct,fp(s.excess_return_20d_pct),40)
    +devBar('60일',s.excess_return_60d_pct,fp(s.excess_return_60d_pct),40)
    +'<div class="mx-note">데이터 상태: '+esc(s.data_status||'—')+' · 벤치마크 '+esc(s.benchmark_status||'—')+' ('+(s.benchmark_as_of||'—')+')</div>';

  // ---------- 5) EVIDENCE F/E/V ----------
  const fName={F:'Fundamental · 실적/재무',E:'Estimate · 추정치/컨센서스',V:'Valuation · 밸류에이션'};
  const fScore={F:s.research_F,E:s.research_E,V:s.research_V};
  const fStatus={F:s.research_F_status,E:s.research_E_status,V:s.research_V_status};
  const pillCls=st=>st==='verified'?'v':(st==='partial'||st==='partially_verified')?'p':'n';
  let fevCards='';
  ['F','E','V'].forEach(k=>{
    const e=ev?ev[k]:null;
    fevCards+='<div class="mx-fcard"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span class="mx-fname">'+fName[k]+'</span><span class="mx-pill '+pillCls(fStatus[k])+'">'+esc(fStatus[k]||'미확인')+'</span></div>'
      +donut(fScore[k],'')
      +'<div class="mx-note">'+(e&&e.grade?'등급 '+esc(e.grade):'')+(e&&e.as_of?' · 기준 '+esc(e.as_of):'')+'</div>'
      +'<div class="mx-basis">'+esc(e&&e.basis?e.basis:'근거 상세가 아직 등록되지 않았습니다.')+'</div></div>';
  });
  html+='<div class="mx-h">🧾 기업 근거 F/E/V</div>'
    +'<div class="mx-pos">근거 상태 <b>'+esc(s.evidence_status||'—')+'</b> · 연구점수 <b>'+(s.research_score??'미생성')+'</b> <span class="mx-sub">'+esc(s.research_score_status||'')+'</span><br><span class="mx-sub">세 요인이 모두 verified일 때만 연구점수를 생성하고, 연구점수 70 미만은 셋업이 좋아도 확정 🟢가 되지 않습니다.</span></div>'
    +'<div class="mx-fev">'+fevCards+'</div>'
    +((s.evidence_notes&&s.evidence_notes.length)
      ?'<div class="mx-h">검증 노트</div><ul>'+s.evidence_notes.map(n=>'<li>'+esc(n)+'</li>').join('')+'</ul>'
      :'')
    +((s.evidence_sources&&s.evidence_sources.length)
      ?'<div style="margin-top:8px">'+s.evidence_sources.map((u,i)=>'<a class="mx-src" href="'+esc(u)+'" target="_blank" rel="noopener">📎 근거 문서 '+(i+1)+'</a>').join('')+'</div>'
      :'')
    +'<div class="mx-note" style="margin-top:8px">기존 F/E/V(F '+(s.legacy_F??'—')+' · E '+(s.legacy_E??'—')+' · V '+(s.legacy_V??'—')+' · PR '+(s.legacy_PR??'—')+')는 감사용 구값입니다.</div>';

  // ---------- 6) NEXT CHECKS ----------
  html+='<div class="mx-h">🔭 다음에 확인할 것</div>'
    +((s.research_next_check&&s.research_next_check.length)
      ?'<div class="mx-nc">'+s.research_next_check.map(n=>'<span>▸ '+esc(n)+'</span>').join('')+'</div>'
      :'<div class="mx-note">등록된 후속 확인 사항이 없습니다.</div>');

  // ---------- 7) REGIME ----------
  if(regime){
    const idx=regime.indices||{};
    const cards=Object.keys(idx).map(k=>{
      const i=idx[k];
      const dots='●'.repeat(Math.max(0,Math.min(3,i.points)))+'<i>'+'●'.repeat(Math.max(0,3-Math.min(3,i.points)))+'</i>';
      return '<div class="mx-rcard"><div style="display:flex;justify-content:space-between;align-items:center"><b>'+esc(k)+'</b><span class="mx-dots">'+dots+'</span></div>'
        +'<table class="mx-tbl" style="margin-top:6px">'
        +'<tr><td>종가</td><td>'+fmt(i.close)+'</td></tr>'
        +'<tr><td>MA20 / MA60</td><td>'+fmt(i.ma20)+' / '+fmt(i.ma60)+'</td></tr>'
        +'<tr><td>20일 수익률</td><td style="color:'+(i.return_20d_pct>=0?'#63e6be':'#ff7b7b')+'">'+fp(i.return_20d_pct)+'</td></tr>'
        +'</table></div>';
    }).join('');
    html+='<div class="mx-h">🌡️ 시장 레짐 ('+(regime.as_of||'—')+' 기준)</div>'
      +'<div class="mx-pos">레짐 <b>'+esc(regime.label||'')+'</b> · 평균 '+regime.points_avg+'점 · 실행점수 보정 <b>'+(regime.execution_adjustment>=0?'+':'')+regime.execution_adjustment+'</b></div>'
      +'<div class="mx-reg">'+cards+'</div>';
  }

  html+='<div class="mx-note" style="margin-top:16px">이 패널은 data/live_scores.json 기준으로 자동 생성됩니다 (계산: '+esc(calcLabel||'—')+'). 고정 텍스트가 아니며, 데이터 출처: '+esc(s.source||'—')+'</div>';

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
