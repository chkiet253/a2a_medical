function renderOptions(optData) {
    const chatContainer = document.getElementById("chatContainer");
    const div = document.createElement("div");
    div.className = "message agent";
    div.innerHTML = `<strong>${optData.title}</strong><br>`;
    optData.options.forEach(opt => {
      div.innerHTML += `<button onclick="selectOption('${opt}')">${opt}</button><br>`;
    });
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
  
  function selectOption(val) {
    addMessage("user", val);
    addMessage("agent", "✅ Đặt lịch thành công với: " + val);
  }
  