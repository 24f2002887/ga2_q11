import time
import uuid
import base64
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"]
)

TOTAL_ORDERS = 55
RATE_LIMIT = 16
WINDOW_SECONDS = 10

idempotency_cache = {}
rate_limit_buckets = {}

def encode_cursor(order_id):
    return base64.urlsafe_b64encode(str(order_id).encode()).decode()

def decode_cursor(cursor_str):
    try:
        return int(base64.urlsafe_b64decode(cursor_str.encode()).decode())
    except Exception:
        return 1

@app.post("/orders")
async def create_order(
    request: Request,
    idempotency_key: Optional[str] = Header(None),
    x_client_id: Optional[str] = Header(None)
):
    client_id = x_client_id or "default_client"
    now = time.time()
    
    if client_id not in rate_limit_buckets:
        rate_limit_buckets[client_id] = []
        
    rate_limit_buckets[client_id] = [ts for ts in rate_limit_buckets[client_id] if now - ts < WINDOW_SECONDS]
    
    # 1. Rate Limit Check
    if len(rate_limit_buckets[client_id]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(WINDOW_SECONDS)}
        )
        
    rate_limit_buckets[client_id].append(now)

    # 2. Idempotency Check
    if idempotency_key and idempotency_key in idempotency_cache:
        return JSONResponse(
            status_code=200,
            content=idempotency_cache[idempotency_key]
        )

    # 3. Create Order
    body = {}
    try:
        body = await request.json()
    except:
        pass

    new_order = {
        "id": str(uuid.uuid4()),
        "status": "created",
        "amount": body.get("amount", 100.0)
    }
    
    if idempotency_key:
        idempotency_cache[idempotency_key] = new_order

    return JSONResponse(
        status_code=201,
        content=new_order
    )

@app.get("/orders")
async def get_orders(
    limit: int = Query(10, ge=1, le=TOTAL_ORDERS),
    cursor: Optional[str] = Query(None),
    x_client_id: Optional[str] = Header(None)
):
    client_id = x_client_id or "default_client"
    now = time.time()
    
    if client_id not in rate_limit_buckets:
        rate_limit_buckets[client_id] = []
        
    rate_limit_buckets[client_id] = [ts for ts in rate_limit_buckets[client_id] if now - ts < WINDOW_SECONDS]
    
    # Rate Limit Check
    if len(rate_limit_buckets[client_id]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(WINDOW_SECONDS)}
        )
    rate_limit_buckets[client_id].append(now)

    start_id = decode_cursor(cursor) if cursor else 1
    
    items = []
    current_id = start_id
    
    while len(items) < limit and current_id <= TOTAL_ORDERS:
        items.append({
            "id": current_id,
            "status": "completed",
            "amount": current_id * 10.0
        })
        current_id += 1
        
    next_cursor = None
    if current_id <= TOTAL_ORDERS:
        next_cursor = encode_cursor(current_id)

    return JSONResponse(
        status_code=200,
        content={
            "items": items,
            "next_cursor": next_cursor
        }
    )
