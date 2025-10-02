async function sendMessage() {
    const input = document.getElementById("userInput");
    const msg = input.value.trim();
    if (!msg) return;
  
    addMessage("user", msg);
    input.value = "";
  
    const res = await fetch("/api/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: msg })
    });
    const data = await res.json();
    renderResponse(data);
  }
  