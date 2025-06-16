from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import sqlite3
import random
import json
import os

app = FastAPI()

DB_PATH = "lottery.db"

if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE draws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            winning_numbers TEXT
        );
    """)
    cursor.execute("""
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draw_id INTEGER NOT NULL,
            numbers TEXT NOT NULL,
            FOREIGN KEY(draw_id) REFERENCES draws(id)
        );
    """)
    conn.commit()
    conn.close()


class TicketRequest(BaseModel):
    draw_id: int
    numbers: List[int] = Field(..., min_items=5, max_items=5)


class DrawResult(BaseModel):
    winning_numbers: Optional[List[int]] = None
    tickets: List[dict]


def get_db_connection():
    return sqlite3.connect(DB_PATH)


def serialize_numbers(numbers: List[int]) -> str:
    return json.dumps(sorted(numbers))


def deserialize_numbers(data: str) -> List[int]:
    return json.loads(data)


@app.post("/draws")
def create_draw():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM draws WHERE status = 'active'")
    if cur.fetchone()[0] > 0:
        conn.close()
        raise HTTPException(status_code=400, detail="Active draw already exists")
    cur.execute("INSERT INTO draws (status) VALUES ('active')")
    conn.commit()
    draw_id = cur.lastrowid
    conn.close()
    return {"draw_id": draw_id, "status": "active"}

@app.post("/tickets")
def buy_ticket(req: TicketRequest):
    if len(set(req.numbers)) != 5:
        raise HTTPException(status_code=400, detail="Numbers must be unique")
    if any(n < 1 or n > 36 for n in req.numbers):
        raise HTTPException(status_code=400, detail="Numbers must be in range 1-36")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM draws WHERE id = ?", (req.draw_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Draw not found")
    if row[0] != 'active':
        conn.close()
        raise HTTPException(status_code=400, detail="Draw is not active")
    cur.execute(
        "INSERT INTO tickets (draw_id, numbers) VALUES (?, ?)",
        (req.draw_id, serialize_numbers(req.numbers))
    )
    conn.commit()
    ticket_id = cur.lastrowid
    conn.close()
    return {"ticket_id": ticket_id}

@app.post("/draws/{draw_id}/close")
def close_draw(draw_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status FROM draws WHERE id = ?", (draw_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Draw not found")
    if row[0] != 'active':
        conn.close()
        raise HTTPException(status_code=400, detail="Draw already closed")
    winning = random.sample(range(1, 37), 5)
    cur.execute(
        "UPDATE draws SET status = 'closed', winning_numbers = ? WHERE id = ?",
        (serialize_numbers(winning), draw_id)
    )
    conn.commit()
    conn.close()
    return {"draw_id": draw_id, "winning_numbers": sorted(winning)}

@app.get("/draws/{draw_id}/results", response_model=DrawResult)
def get_results(draw_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT status, winning_numbers FROM draws WHERE id = ?", (draw_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Draw not found")
    status, win_json = row
    winning_numbers = deserialize_numbers(win_json) if win_json else None
    cur.execute("SELECT id, numbers FROM tickets WHERE draw_id = ?", (draw_id,))
    tickets = [
        {"ticket_id": tid, "numbers": deserialize_numbers(nums)}
        for tid, nums in cur.fetchall()
    ]
    conn.close()
    return {"winning_numbers": winning_numbers, "tickets": tickets}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)