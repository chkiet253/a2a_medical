import requests
from config import API_URL

def upload_pdfs_api(files, timeout=60):
    files_payload = [("files", (f.name, f.read(), "application/pdf")) for f in files]
    try:
        return requests.post(f"{API_URL}/upload_pdfs/", files=files_payload, timeout=timeout)
    except requests.RequestException as e:
        class Resp:  # fake minimal Response
            status_code, text = 599, f"Client error: {e}"
            def json(self): return {"error": self.text}
        return Resp()

def ask_question(question, timeout=60, use_json=True):
    try:
        if use_json:
            return requests.post(f"{API_URL}/ask/", json={"question": question}, timeout=timeout)
        else:
            return requests.post(f"{API_URL}/ask/", data={"question": question}, timeout=timeout)
    except requests.RequestException as e:
        class Resp:
            status_code, text = 599, f"Client error: {e}"
            def json(self): return {"error": self.text}
        return Resp()
