async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function el(tag, cls) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function addMsg(text, who = "bot") {
  const log = document.getElementById("chat-log");
  const m = el("div", `msg ${who}`);
  m.textContent = text;
  log.appendChild(m);
  log.scrollTop = log.scrollHeight;
}

function patientPayload() {
  return {
    name: document.getElementById("pt-name").value || undefined,
    age: Number(document.getElementById("pt-age").value) || undefined,
    gender: document.getElementById("pt-gender").value || undefined,
    history: document.getElementById("pt-history").value || undefined,
  };
}

window.__utils = { fetchJSON, el, addMsg, patientPayload };