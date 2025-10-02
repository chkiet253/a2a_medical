# a2a_ui/app/host_bridge.py
import os
import json
from typing import Dict, Any, List

MODE = os.getenv("HOST_MODE", "import")  # "import" | "http"

def _to_ui_messages(host_result: Any) -> Dict[str, Any]:
    """
    Quy ước chuyển đổi kết quả từ Host Agent -> JSON cho UI:
    - Text: {"type":"text","content":"..."}
    - Form: {"type":"form","title":"...","fields":[...],"submit_label":"..."}
    - Options: {"type":"options","title":"...","options":[...]}
    - Host steps: {"type":"host","steps":[{"agent":"...","message":"..."}]}
    Bạn sửa phần này theo đúng artifact/trace của Host bạn.
    """
    # Mặc định: nếu host_result là chuỗi
    if isinstance(host_result, str):
        return {"type": "text", "content": host_result}

    # Nếu host_result có trace các agent con
    if isinstance(host_result, dict) and "steps" in host_result:
        return {"type": "host", "steps": host_result["steps"]}

    # Nếu host_result đã là JSON hợp lệ cho UI (form / options / text)
    if isinstance(host_result, dict) and "type" in host_result:
        return host_result

    # Fallback
    return {"type": "text", "content": json.dumps(host_result, ensure_ascii=False)}

# =========================
# MODE A: IMPORT TRỰC TIẾP
# =========================
if MODE == "import":
    # TODO: CHỈNH ĐÚNG ĐƯỜNG DẪN IMPORT TRONG REPO CỦA BẠN
    # Ví dụ nếu bạn có hosts/orchestrator/host_agent_executor.py:
    # from hosts.orchestrator.host_agent_executor import HostAgentExecutor
    try:
        from hosts import orchestrator  # ví dụ "hosts/orchestrator/__init__.py"
        from hosts.orchestrator.host_agent_executor import HostAgentExecutor  # <- sửa theo repo thật
    except Exception as e:
        # Nếu đường import trên không đúng, chỉnh lại theo layout của bạn
        HostAgentExecutor = None
        _import_error = e

    _host = HostAgentExecutor() if HostAgentExecutor else None

    def handle_user_message(text: str) -> Dict[str, Any]:
        if not _host:
            return {"type":"text","content":f"❌ Không import được HostAgentExecutor: {_import_error}"}
        # Giả định host.run(...) trả về text/trace/artifact. Bạn sửa cho khớp hàm thật.
        result = _host.run(text)
        return _to_ui_messages(result)

    def handle_submit(kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submit form/options. Bạn có thể định nghĩa API riêng trong Host:
        ví dụ _host.submit(kind, values) hoặc _host.run(f'__submit__::{kind}::{json}')
        """
        if not _host:
            return {"type":"text","content":f"❌ Không import được HostAgentExecutor: {_import_error}"}
        if hasattr(_host, "submit"):
            result = _host.submit(kind=kind, values=values)
        else:
            # Fallback: gửi lại vào run dưới dạng lệnh
            result = _host.run(f"__submit__::{kind}::{json.dumps(values, ensure_ascii=False)}")
        return _to_ui_messages(result)

# ======================
# MODE B: GỌI HTTP HOST
# ======================
else:
    import httpx
    HOST_URL = os.getenv("HOST_URL", "http://127.0.0.1:8010")  # Sửa theo host thật của bạn
    SEND_PATH = os.getenv("HOST_SEND_PATH", "/api/host/run")   # Sửa path đúng
    SUBMIT_PATH = os.getenv("HOST_SUBMIT_PATH", "/api/host/submit")

    _client = httpx.Client(timeout=60)

    def handle_user_message(text: str) -> Dict[str, Any]:
        """Gọi host HTTP: đổi payload/field theo API của bạn."""
        r = _client.post(HOST_URL + SEND_PATH, json={"text": text})
        r.raise_for_status()
        result = r.json()
        return _to_ui_messages(result)

    def handle_submit(kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
        r = _client.post(HOST_URL + SUBMIT_PATH, json={"kind": kind, "values": values})
        r.raise_for_status()
        result = r.json()
        return _to_ui_messages(result)
