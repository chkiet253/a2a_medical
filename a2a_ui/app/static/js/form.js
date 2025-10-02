function renderForm(formData) {
    const chatContainer = document.getElementById("chatContainer");
    const formDiv = document.createElement("div");
    formDiv.className = "message agent";
    formDiv.innerHTML = `<strong>${formData.title}</strong><br>`;
  
    formData.fields.forEach(field => {
      if (field.type === "checkbox") {
        formDiv.innerHTML += `<label><input type="checkbox" id="${field.name}"> ${field.label}</label><br>`;
      } else if (field.type === "select") {
        let opts = field.options.map(o=>`<option>${o}</option>`).join("");
        formDiv.innerHTML += `<label>${field.label}: <select id="${field.name}">${opts}</select></label><br>`;
      }
    });
  
    formDiv.innerHTML += `<button onclick="submitForm('${formData.fields.map(f=>f.name).join(',')}')">${formData.submit_label}</button>`;
    chatContainer.appendChild(formDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
  }
  
  function submitForm(names) {
    const fields = names.split(",");
    let values = {};
    fields.forEach(n => {
      const el = document.getElementById(n);
      values[n] = el.type === "checkbox" ? el.checked : el.value;
    });
    addMessage("user", "Đã điền form: " + JSON.stringify(values));
    addMessage("agent", "💵 Tổng chi phí dự toán: 1,200,000 VNĐ");
  }
  