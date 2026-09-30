(async()=>{
  const m=document.body.innerText.match(/\b\d{6}\b/);
  if(!m)return;
  const code=m[0], fmt=n=>n==null?'—':Math.round(n).toLocaleString('ko-KR');
  const snapshot=document.querySelector('.sig');
  if(snapshot){
    const tag=snapshot.querySelector('b.up');
    if(tag)tag.textContent='ORIGINAL ANALYSIS SNAPSHOT';
    snapshot.style.opacity='.58';
    snapshot.style.borderColor='#304454';
  }
  try{
    const r=await fetch('https://raw.githubusercontent.com/sasohanbam-wq/Mingo/main/data/live_scores.json?t='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    const s=d.stocks.find(x=>x.code===code);
    if(!s)return;
    const box=document.createElement('section');
    box.style.cssText='padding:18px;border-radius:18px;margin:18px 0;background:#0c1b28;border:2px solid #73b7ff;line-height:1.55';
    const zone=s.buy_zone&&s.buy_zone[0]!=null?fmt(s.buy_zone[0])+'~'+fmt(s.buy_zone[1])+'원':'—';
    box.innerHTML='<div style="font-size:11px;font-weight:900;color:#73b7ff;letter-spacing:.08em">MINGO V2 · LIVE GATE</div>'+
      '<h2 style="margin:7px 0">'+s.label+'</h2>'+
      '<div style="font-size:27px;font-weight:900">'+fmt(s.price)+'원</div>'+
      '<div style="color:#8da4b5;font-size:12px">가격 기준 '+(s.quote_as_of||'—')+' · 기대 완료세션 '+(s.expected_completed_session||'—')+' · '+(s.session||'—')+'</div>'+
      '<p><b>셋업:</b> '+(s.setup_reason||'—')+'</p>'+
      '<p><b>매수구간:</b> '+zone+' · <b>트리거:</b> '+fmt(s.trigger)+'원 · <b>무효화:</b> '+fmt(s.invalidation)+'원</p>'+
      '<p><b>기술/셋업 점수:</b> '+(s.execution_score??'—')+' · <b>Wilder RSI:</b> '+(s.rsi14_wilder??'—')+'</p>'+
      '<p style="color:#ffd166"><b>기업 근거:</b> '+(s.evidence_status||'—')+' · 연구점수 '+(s.research_score??'N/A')+'</p>'+
      '<p><b>새 F/E/V:</b> '+(s.research_F??'N/A')+' / '+(s.research_E??'N/A')+' / '+(s.research_V??'N/A')+
      ' <span style="color:#8da4b5;font-size:11px">('+ (s.research_F_status??'—')+' / '+(s.research_E_status??'—')+' / '+(s.research_V_status??'—') +')</span></p>'+
      '<div style="color:#8da4b5;font-size:11px">기존 F/E/V는 감사용 값. 세 요인이 모두 verified일 때만 연구점수를 생성하며, 연구점수 70 미만은 셋업이 좋아도 확정 🟢가 되지 않는다.</div>';
    const h1=document.querySelector('h1');
    const thesis=h1?.nextElementSibling;
    (thesis||h1)?.insertAdjacentElement('afterend',box);
  }catch(e){
    console.warn('MINGO live gate unavailable',e);
  }
})();