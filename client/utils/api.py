import requests
API_URL = "http://127.0.0.1:8000"

def ask_question(query: str, timeout=60):
    try:
        return requests.post(f"{API_URL}/ask", data={"query": query}, timeout=timeout)
    except requests.RequestException as e:
        class Resp:
            status_code, text = 599, f"Client error: {e}"
            def json(self): return {"error": self.text}
        return Resp()