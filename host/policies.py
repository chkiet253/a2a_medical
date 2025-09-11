from fastapi import HTTPException

BLOCKLIST = {"tự sát", "suicide", "ransomware", "đặt bom", "bomb", "hack", "delete ehr"}

def safety_check(text: str):
    low = text.lower()
    if any(b in low for b in BLOCKLIST):
        raise HTTPException(status_code=400, detail="Blocked by safety policy.")
