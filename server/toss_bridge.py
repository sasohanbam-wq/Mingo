import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

import httpx
import websockets
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

TOSS_CLIENT_ID = os.environ["TOSS_CLIENT_ID"]
TOSS_CLIENT_SECRET = os.environ["TOSS_CLIENT_SECRET"]
TOSS_TOKEN_URL = "https://openapi.tossinvest.com/oauth2/token"
TOSS_WS_URL = "wss://openapi-ws.tossinvest.com/ws/v1"
TOSS_TRADES_URL = "https://openapi.tossinvest.com/api/v1/trades"
SYMBOLS = [x.strip() for x in os.getenv("MINGO_SYMBOLS","").split(",") if x.strip()]

quotes = {}
status = {"connected": False, "last_error": None, "last_message_at": None}

async def issue_token():
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            TOSS_TOKEN_URL,
            data={
                "grant_type":"client_credentials",
                "client_id":TOSS_CLIENT_ID,
                "client_secret":TOSS_CLIENT_SECRET,
            },
            headers={"Content-Type":"application/x-www-form-urlencoded"},
        )
        r.raise_for_status()
        data = r.json()
        return data["access_token"]

def save_quote(code, data, source):
    """Store only the public market fields the browser needs."""
    try:
        price = float(data["price"])
    except (KeyError, TypeError, ValueError):
        return
    quotes[code] = {
        "code": code,
        "price": price,
        "volume": data.get("volume"),
        "timestamp": data.get("timestamp"),
        "currency": data.get("currency", "KRW"),
        "received_at": int(time.time()),
        "source": source,
    }

async def load_initial_quotes(token):
    """WebSocket sends only the next trade, so seed every symbol via REST."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for code in SYMBOLS:
            try:
                r = await client.get(TOSS_TRADES_URL, params={"symbol": code, "count": 1})
                r.raise_for_status()
                result = r.json().get("result") or []
                if result:
                    save_quote(code, result[0], "tossinvest REST snapshot")
            except Exception as e:
                status["last_error"] = f"initial quote {code}: {type(e).__name__}"
            await asyncio.sleep(0.22)

async def ws_loop():
    while True:
        try:
            token = await issue_token()
            await load_initial_quotes(token)
            headers={"Authorization":f"Bearer {token}"}
            async with websockets.connect(
                TOSS_WS_URL,
                additional_headers=headers,
                ping_interval=None,
                close_timeout=5,
            ) as ws:
                status["connected"]=True
                status["last_error"]=None
                req=[{"id":"mingo-live"}]
                if SYMBOLS:
                    req.append({"type":"trade:kr","codes":SYMBOLS})
                await ws.send(json.dumps(req, ensure_ascii=False))

                async def keepalive():
                    while True:
                        await asyncio.sleep(60)
                        await ws.send("PING")

                ping_task=asyncio.create_task(keepalive())
                try:
                    async for raw in ws:
                        status["last_message_at"]=int(time.time())
                        if raw == "PONG":
                            continue
                        try:
                            msg=json.loads(raw)
                        except Exception:
                            continue
                        if msg.get("type")!="message":
                            continue
                        topic=msg.get("topic","")
                        if not topic.startswith("trade:kr:"):
                            continue
                        code=topic.rsplit(":",1)[-1]
                        data=msg.get("data") or {}
                        save_quote(code, data, "tossinvest trade:kr")
                finally:
                    ping_task.cancel()
        except Exception as e:
            status["connected"]=False
            status["last_error"]=repr(e)
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task=asyncio.create_task(ws_loop())
    yield
    task.cancel()

app=FastAPI(title="MINGO Toss Bridge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://sasohanbam-wq.github.io",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {
        "ok": True,
        "connected": status["connected"],
        "symbols": SYMBOLS,
        "last_error": status["last_error"],
        "last_message_at": status["last_message_at"],
    }

@app.get("/quotes")
def get_quotes():
    return {
        "source":"tossinvest",
        "connected":status["connected"],
        "quotes":quotes,
        "last_message_at":status["last_message_at"],
        "server_time":int(time.time()),
    }

@app.get("/quotes/{code}")
def get_quote(code: str):
    return quotes.get(code, {"code":code,"available":False})
