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
function renderResponse(data) {
if (data.type === "text") {
    addMessage("agent", data.content);
} 
else if (data.type === "form") {
    renderForm(data);
} 
else if (data.type === "options") {
    renderOptions(data);
}
else if (data.type === "host") {
    renderHostSteps(data.steps);
}
}

function renderHostSteps(steps) {
steps.forEach(step => {
    addMessage("agent", `<strong>${step.agent}:</strong> ${step.message}`);
});
}
  