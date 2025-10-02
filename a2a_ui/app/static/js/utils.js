function addMessage(role, content) {
    const chatContainer = document.getElementById("chatContainer");
    const msg = document.createElement("div");
    msg.className = "message " + role;
    msg.innerHTML = content;
    chatContainer.appendChild(msg);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
  
  function handleKeyPress(event) {
    if (event.key === "Enter") sendMessage();
  }
  