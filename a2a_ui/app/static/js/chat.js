const { fetchJSON, addMsg, patientPayload } = window.__utils;

async function sendChat(text) {
  addMsg(text, "user");
  try {
    const payload = { message: text, patient: patientPayload(), mode: "orchestrate" };
    const data = await fetchJSON("/api/chat", { method: "POST", body: JSON.stringify(payload) });
    const reply = data.reply || JSON.stringify(data);
    addMsg(reply, "bot");
  } catch (e) {
    addMsg("Lỗi gửi tin: " + e.message, "bot");
  }
}

function initChat() {
  const form = document.getElementById("chat-form");
  const inp = document.getElementById("chat-text");
  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = inp.value.trim(); if (!text) return;
    inp.value = "";
    sendChat(text);
  });
}

window.__chat = { initChat };