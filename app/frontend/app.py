import os
import requests
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="TechMart Frontend")

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    try:
        orders = requests.get(f"{BACKEND_URL}/orders", timeout=3).json()
    except Exception:
        orders = []
    rows = "".join(
        f"<tr><td>{o['id']}</td><td>{o['customer_name']}</td><td>{o['item']}</td><td>{o['quantity']}</td></tr>"
        for o in orders
    )
    return f"""
    <html><head><title>TechMart</title></head>
    <body style="font-family: sans-serif; max-width: 600px; margin: 40px auto;">
      <h1>TechMart orders</h1>
      <form method="post" action="/orders">
        <input name="customer_name" placeholder="Customer name" required>
        <input name="item" placeholder="Item" required>
        <input name="quantity" type="number" placeholder="Qty" required>
        <button type="submit">Place order</button>
      </form>
      <table border="1" cellpadding="6" style="margin-top:20px; width:100%;">
        <tr><th>ID</th><th>Customer</th><th>Item</th><th>Qty</th></tr>
        {rows}
      </table>
    </body></html>
    """


@app.post("/orders", response_class=HTMLResponse)
def place_order(customer_name: str = Form(...), item: str = Form(...), quantity: int = Form(...)):
    requests.post(
        f"{BACKEND_URL}/orders",
        json={"customer_name": customer_name, "item": item, "quantity": quantity},
        timeout=3,
    )
    return index()
