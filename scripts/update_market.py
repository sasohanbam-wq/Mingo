import json, math, os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ROOT=os.path.dirname(os.path.dirname(__file__))
CFG=os.path.join(ROOT,"data","stocks.json")
OUT=os.path.join(ROOT,"data","live_scores.json")
KST=ZoneInfo("Asia/Seoul")

def clamp(x,a=0,b=100):
    return max(a,min(b,x))

def rsi14(s):
    d=s.diff()
    up=d.clip(lower=0).rolling(14).mean()
    dn=(-d.clip(upper=0)).rolling(14).mean()
    rs=up/dn.replace(0,float("nan"))
    r=100-(100/(1+rs))
    return float(r.iloc[-1]) if len(r) and pd.notna(r.iloc[-1]) else 50.0

def ret(s,n):
    if len(s)<=n or float(s.iloc[-n-1])==0: return 0.0
    return float(s.iloc[-1]/s.iloc[-n-1]-1)

def load_hist(sym):
    d=yf.Ticker(sym).history(period="1y",interval="1d",auto_adjust=False)
    if d is None or d.empty: raise RuntimeError("empty history")
    d=d.dropna(subset=["Close"])
    if len(d)<60: raise RuntimeError("insufficient history")
    return d

def tech(d, bench):
    c=d["Close"].astype(float)
    v=d["Volume"].astype(float) if "Volume" in d else pd.Series(index=d.index,dtype=float)
    p=float(c.iloc[-1])
    prev=float(c.iloc[-2]) if len(c)>1 else p
    ma20=float(c.rolling(20).mean().iloc[-1])
    ma50=float(c.rolling(50).mean().iloc[-1])
    ma200=float(c.rolling(200).mean().iloc[-1]) if len(c)>=200 else float(c.mean())
    high20=float(c.tail(20).max())
    low20=float(c.tail(20).min())
    rsi=rsi14(c)
    r20=ret(c,20); r60=ret(c,60)
    bc=bench["Close"].astype(float)
    br20=ret(bc,20); br60=ret(bc,60)
    rel20=(r20-br20)*100
    rel60=(r60-br60)*100
    vol20=float(v.tail(20).mean()) if len(v) and v.tail(20).mean()>0 else 0
    vr=float(v.iloc[-1]/vol20) if vol20>0 else 1.0
    trend=0
    trend+=22 if p>ma20 else 4
    trend+=20 if p>ma50 else 4
    trend+=14 if p>ma200 else 2
    trend+=14 if ma20>ma50 else 3
    trend+=10 if ma50>ma200 else 3
    trend+=20 if p>=high20*0.97 else 8 if p>=high20*0.90 else 2
    rel=clamp(50+rel20*2.8+rel60*1.1)
    if 50<=rsi<=68: rsis=92
    elif 45<=rsi<50 or 68<rsi<=73: rsis=75
    elif 40<=rsi<45 or 73<rsi<=78: rsis=58
    elif 35<=rsi<40 or 78<rsi<=82: rsis=40
    else: rsis=25
    vols=clamp(45+(vr-1)*35)
    pr=0.42*trend+0.28*rel+0.20*rsis+0.10*vols
    ext=(p/ma20-1)*100 if ma20 else 0
    if ext>20: pr-=24
    elif ext>14: pr-=14
    elif ext>10: pr-=7
    if rsi>82: pr-=12
    pr=round(clamp(pr),1)
    if p>=ma20 and p<=ma20*1.055 and pr>=60:
        setup="눌림 추세매수"
    elif p>=high20*0.985 and pr>=65:
        setup="돌파 추세추종"
    elif p>ma20:
        setup="추세 보유·돌파 대기"
    elif p>ma50:
        setup="스윙·추세복귀"
    else:
        setup="반등 확인 대기"
    buy_lo=ma20*0.99
    buy_hi=ma20*1.025
    trigger=max(high20*1.003,ma20*1.04)
    stop=min(ma20*0.965,ma50*0.985) if ma50 else ma20*0.965
    return {
        "price":round(p,2),"change_pct":round((p/prev-1)*100,2),
        "ma20":round(ma20,2),"ma50":round(ma50,2),"ma200":round(ma200,2),
        "high20":round(high20,2),"low20":round(low20,2),"rsi14":round(rsi,1),
        "ret20_pct":round(r20*100,1),"ret60_pct":round(r60*100,1),
        "rel20_pct":round(rel20,1),"rel60_pct":round(rel60,1),
        "volume_ratio":round(vr,2),"extension_ma20_pct":round(ext,1),
        "pr_score":pr,"setup":setup,
        "buy_zone":[round(buy_lo,-1),round(buy_hi,-1)],
        "trigger":round(trigger,-1),"stop":round(stop,-1)
    }

with open(CFG,encoding="utf-8") as f:
    cfg=json.load(f)

old={}
if os.path.exists(OUT):
    try:
        with open(OUT,encoding="utf-8") as f:
            oldj=json.load(f)
            old={x["code"]:x for x in oldj.get("stocks",[])}
    except Exception:
        old={}

bench={}
for ex,sym in [("KS","^KS11"),("KQ","^KQ11")]:
    try: bench[ex]=load_hist(sym)
    except Exception: bench[ex]=None

rows=[]
errors=[]
for s in cfg["stocks"]:
    sym=s["code"]+(".KS" if s["exchange"]=="KS" else ".KQ")
    try:
        d=load_hist(sym)
        b=bench.get(s["exchange"])
        if b is None: raise RuntimeError("benchmark unavailable")
        t=tech(d,b)
        ratio=t["price"]/s["ref"] if s["ref"] else 1
        dynV=round(clamp(s["V"]-70*math.log(max(ratio,0.25))),1)
        buy=round(0.18*s["F"]+0.17*s["E"]+0.25*dynV+0.40*t["pr_score"],1)
        if t["pr_score"]<35 or (t["rsi14"]>82 and t["extension_ma20_pct"]>16):
            state="red"; label="🔴 보류"
        elif buy>=70 and t["pr_score"]>=60 and t["extension_ma20_pct"]<15 and t["rsi14"]<79:
            state="green"; label="🟢 지금 가능"
        else:
            state="yellow"; label="🟡 조건부"
        row={**s,**t,"dynamic_V":dynV,"company_score":round((s["F"]+s["E"])/2,1),
             "buy_score":buy,"state":state,"label":label,"data_status":"live"}
    except Exception as e:
        errors.append(f'{s["code"]}:{e}')
        prev=old.get(s["code"])
        if prev:
            row={**prev,"data_status":"stale"}
        else:
            buy=round(0.18*s["F"]+0.17*s["E"]+0.25*s["V"]+0.40*s["PR"],1)
            state="green" if buy>=72 and s["PR"]>=60 else "yellow"
            row={**s,"price":s["ref"],"change_pct":0,"dynamic_V":s["V"],"pr_score":s["PR"],
                 "company_score":round((s["F"]+s["E"])/2,1),"buy_score":buy,
                 "state":state,"label":"🟢 지금 가능" if state=="green" else "🟡 조건부",
                 "setup":"마지막 분석 기준","buy_zone":[None,None],"trigger":None,"stop":None,
                 "rsi14":None,"ma20":None,"ma50":None,"ma200":None,"rel20_pct":None,
                 "data_status":"fallback"}
        row["error"]=str(e)
    rows.append(row)

rows.sort(key=lambda x:x.get("buy_score",0),reverse=True)
now=datetime.now(KST)
out={
    "version":1,
    "model":"MINGO dynamic v1",
    "updated_at":now.isoformat(timespec="seconds"),
    "updated_at_label":now.strftime("%Y-%m-%d %H:%M KST"),
    "refresh_policy":"KST weekdays 09:07-15:37 every 30m + 16:10 close",
    "source":"Yahoo Finance via yfinance; quotes may be delayed",
    "errors":errors,
    "stocks":rows
}
with open(OUT,"w",encoding="utf-8") as f:
    json.dump(out,f,ensure_ascii=False,indent=2)
print(f"updated {len(rows)} stocks; errors={len(errors)}")
