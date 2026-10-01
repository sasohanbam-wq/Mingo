(function () {
  const configured = window.MINGO_LIVE_API || new URLSearchParams(location.search).get('live_api');
  const api = configured ? configured.replace(/\/$/, '') : '';
  const MAX_AGE_SECONDS = 90;

  function number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function evaluate(base, quote) {
    const price = number(quote && quote.price);
    if (price == null) return base;
    const low = number(base.buy_zone && base.buy_zone[0]);
    const high = number(base.buy_zone && base.buy_zone[1]);
    const stop = number(base.stop);
    const trigger = number(base.trigger);
    const ma20 = number(base.ma20);
    const inZone = low != null && high != null && price >= low && price <= high;
    const invalidated = stop != null && price <= stop;
    const triggered = trigger != null && price >= trigger;
    const aboveMa20 = ma20 == null || price >= ma20;
    let delta = 0;
    if (inZone) delta += 8;
    if (triggered) delta += 5;
    if (!aboveMa20) delta -= 10;
    if (invalidated) delta -= 25;
    const execution = Math.max(0, Math.min(100, Math.round(number(base.execution_score) + delta)));
    let state = base.state;
    let label = base.label;
    let reason = '실시간 현재가 반영 · 일봉 지표는 최근 완료세션 기준';
    if (invalidated) {
      state = 'red'; label = '🔴 실시간 손절선 이탈'; reason = '실시간 현재가가 손절선 이하';
    } else if (!aboveMa20) {
      state = 'yellow'; label = '🟡 실시간 MA20 하회'; reason = '실시간 현재가가 완료세션 MA20 아래';
    } else if (inZone || triggered) {
      state = base.evidence_status === 'verified' && number(base.research_score) >= 70 ? 'green' : 'blue';
      label = state === 'green' ? '🟢 실시간 조건 충족' : '🔵 실시간 가격조건 충족';
      reason = inZone ? '실시간 현재가가 매수구간 안' : '실시간 현재가가 트리거 이상';
    }
    return Object.assign({}, base, {
      price, state, label, execution_score: execution, setup_reason: reason,
      live: true, live_timestamp: quote.timestamp, live_source: quote.source,
      live_in_buy_zone: inZone, live_triggered: triggered, live_invalidated: invalidated
    });
  }

  async function fetchQuotes() {
    if (!api) return { enabled: false, reason: '실시간 서버 주소 미설정' };
    const response = await fetch(api + '/quotes?t=' + Date.now(), { cache: 'no-store' });
    if (!response.ok) throw new Error('실시간 서버 HTTP ' + response.status);
    const data = await response.json();
    return { enabled: true, data };
  }

  window.MingoLive = { api, maxAgeSeconds: MAX_AGE_SECONDS, evaluate, fetchQuotes };
})();
