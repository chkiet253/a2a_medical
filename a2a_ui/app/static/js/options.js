function renderOptions(optData) {
  const chatContainer = document.getElementById("chatContainer");
  const div = document.createElement("div");
  div.className = "message agent";
  const kind = optData.kind || "option_select";
  div.innerHTML = `<strong>${optData.title || "Chọn một tùy chọn"}</strong><br>`;

  (optData.options || []).forEach(opt => {
    const btn = document.createElement("button");
    btn.textContent = typeof opt === "string" ? opt : (opt.label || JSON.stringify(opt));
    btn.addEventListener("click", async () => {
      const value = typeof opt === "string" ? opt : (opt.value ?? opt);
      addMessage("user", btn.textContent);
      try {
        const res = await fetch("/api/submit", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ kind, values: { selection: value } })
        });
        const data = await res.json();
        renderResponse(data);
      } catch (e) {
        addMessage("agent", "❌ Lỗi submit lựa chọn: " + (e?.message || e));
      }
    });
    div.appendChild(btn);
    div.appendChild(document.createElement("br"));
  });

  chatContainer.appendChild(div);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}
