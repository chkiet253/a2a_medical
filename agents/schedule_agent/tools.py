from langchain.tools import Tool
import sqlite3
from datetime import datetime, timedelta
import json
import random

DB_PATH = r"D:/projects/intern/a2a_medical/agents/schedule_agent/schedule.db"  # Đổi thành path khác

def find_today(_input: str):
    """Return today's date in 'YYYY-MM-DD' (system local time)."""
    return datetime.now().date().isoformat()

find_today_tool = Tool(
    name="find_today_tool",
    func=find_today,
    description=(
        "Find today's date in 'YYYY-MM-DD' format. "
        "Input a string (can be empty). "
        "Returns a string representing today's date"
    ),
)

def time_to_seconds(t):
    try:
        parts = [int(x) for x in t.split(":")]
        while len(parts) < 3:
            parts.append(0)
        return parts[0]*3600 + parts[1]*60 + parts[2]
    except Exception:
        return None

def overlaps(s1,e1,s2,e2):
    if s1 is None or e1 is None or s2 is None or e2 is None:
        return True
    return not (e1 <= s2 or e2 <= s1)

def find_available_shift(range_date: str):
    """
    Find the earliest available shift between start_date and end_date inclusive.
    Returns dict:
      { "date": "YYYY-MM-DD", "shift": "<shift_id>", "shift_start": "HH:MM:SS",
        "shift_end": "HH:MM:SS", "doctor_id": "<id>", "doctor_name": "...", "room": "..." }
    Or returns {"message": "no doctors available"} if none found.
    """
    json_input = json.loads(range_date)
    start_date = json_input.get("start_date")
    end_date = json_input.get("end_date")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # parse dates
    try:
        d0 = datetime.fromisoformat(start_date).date()
    except Exception:
        d0 = datetime.strptime(start_date, "%Y-%m-%d").date()
    try:
        d1 = datetime.fromisoformat(end_date).date()
    except Exception:
        d1 = datetime.strptime(end_date, "%Y-%m-%d").date()
    if d1 < d0:
        conn.close()
        raise ValueError("end_date must be >= start_date")

    # shifts list & ordering
    shifts = [r[0] for r in cur.execute("SELECT DISTINCT id FROM work_shifts").fetchall()]
    common_order = {"early":0,"morning":1,"noon":2,"afternoon":3,"evening":4,"night":5,"late":6}
    shifts_sorted = sorted(shifts, key=lambda s: common_order.get(s.lower(), 1000))

    current = d0
    while current <= d1:
        dow = str(current.weekday())  # stored as '0'..'6' in DB
        date_str = current.isoformat()
        for shift in shifts_sorted:
            # find shift time (prefer entry for this weekday)
            row = cur.execute(
                "SELECT start_time, end_time FROM work_shifts WHERE id = ? AND day_of_week = ? LIMIT 1",
                (shift, dow)
            ).fetchone()
            if row is None:
                row = cur.execute("SELECT start_time, end_time FROM work_shifts WHERE id = ? LIMIT 1", (shift,)).fetchone()
            if row is None:
                continue
            shift_start, shift_end = row["start_time"], row["end_time"]
            s_sec = time_to_seconds(shift_start)
            e_sec = time_to_seconds(shift_end)

            # doctors scheduled for this weekday+shift
            scheduled_rows = cur.execute(
                "SELECT doctor_id FROM work_shifts WHERE id = ? AND day_of_week = ?",
                (shift, dow)
            ).fetchall()
            scheduled = {r["doctor_id"] for r in scheduled_rows}

            # apply exceptions for this date
            exc_rows = cur.execute("SELECT * FROM shift_exceptions WHERE date = ?", (date_str,)).fetchall()
            for ex in exc_rows:
                doc = ex["doctor_id"]
                is_avail = ex["is_available"]
                ex_s_sec = time_to_seconds(ex["start_time"])
                ex_e_sec = time_to_seconds(ex["end_time"])
                if not overlaps(s_sec, e_sec, ex_s_sec, ex_e_sec):
                    continue
                if is_avail in (0, "0", 0.0):
                    scheduled.discard(doc)
                else:
                    scheduled.add(doc)

            if not scheduled:
                continue

            # remove doctors with booked appointments that overlap shift
            available = set(scheduled)
            ap_rows = cur.execute("SELECT doctor_id, start_time, end_time, status FROM appointments WHERE date = ?", (date_str,)).fetchall()
            for ap in ap_rows:
                if ap["status"] and ap["status"].lower() == "canceled":
                    continue
                ap_doc = ap["doctor_id"]
                ap_s_sec = time_to_seconds(ap["start_time"])
                ap_e_sec = time_to_seconds(ap["end_time"])
                if overlaps(s_sec, e_sec, ap_s_sec, ap_e_sec):
                    available.discard(ap_doc)

            if available:
                chosen = random.choice(list(available))
                doc_row = cur.execute("SELECT * FROM doctors WHERE id = ?", (chosen,)).fetchone()
                res = {
                    "date": date_str,
                    "shift": shift,
                    "shift_start": shift_start,
                    "shift_end": shift_end,
                    "doctor_id": chosen,
                    "doctor_name": doc_row["name"] if doc_row else None,
                    "room": doc_row["room"] if doc_row else None
                }
                conn.close()
                return res
        current += timedelta(days=1)

    conn.close()
    return {"message": "no doctors available"}

find_available_shift_tool = Tool(
    name="find_available_shift",
    func=find_available_shift,
    description=(
        "Find the earliest available shift between start_date and end_date inclusive. "
        "Input should be a JSON string with 'start_date' and 'end_date' in 'YYYY-MM-DD' format. "
        "Returns a dict with details of the available shift, or a message if none found."
    )
)

def save_to_txt(data: str, filename: str = "booking_output.txt"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_text = f"--- Booking Output ---\nTimestamp: {timestamp}\n\n{data}\n\n"

    with open(filename, "a", encoding="utf-8") as f:
        f.write(formatted_text)
    
    return f"Data successfully saved to {filename}"

save_tool = Tool(
    name="save_tool",
    func=save_to_txt,
    description="Saves structured data to a text file.",
)