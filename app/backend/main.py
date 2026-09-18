from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import psycopg2
from psycopg2.extras import RealDictCursor

app = FastAPI(title="TechMart Backend API")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "techmart")
DB_USER = os.getenv("DB_USER", "techmart")
DB_PASS = os.getenv("DB_PASS", "changeme")


def get_conn():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        cursor_factory=RealDictCursor,
    )


class Order(BaseModel):
    customer_name: str
    item: str
    quantity: int


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    try:
        conn = get_conn()
        conn.close()
        return {"status": "ready"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/orders")
def list_orders():
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT id, customer_name, item, quantity FROM orders ORDER BY id DESC LIMIT 50;")
        rows = cur.fetchall()
    conn.close()
    return rows


@app.post("/orders")
def create_order(order: Order):
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO orders (customer_name, item, quantity) VALUES (%s, %s, %s) RETURNING id;",
            (order.customer_name, order.item, order.quantity),
        )
        new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, **order.dict()}
