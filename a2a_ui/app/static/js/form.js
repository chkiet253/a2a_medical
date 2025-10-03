function renderForm(formData) {
  const chatContainer = document.getElementById("chatContainer");
  const formDiv = document.createElement("div");
  formDiv.className = "message agent";
  const submitLabel = formData.submit_label || "Gửi";
  const kind = formData.kind || "form_submit";

  formDiv.innerHTML = `<strong>${formData.title || "Nhập thông tin"}</strong><br>`;

  formData.fields.forEach(field => {
    const id = field.name;
    if (field.type === "checkbox") {
      formDiv.innerHTML += `<label><input type="checkbox" id="${id}"> ${field.label}</label><br>`;
    } else if (field.type === "select") {
      let opts = (field.options || []).map(o=>`<option>${o}</option>`).join("");
      formDiv.innerHTML += `<label>${field.label}: <select id="${id}">${opts}</select></label><br>`;
    } else {
      // text | number | date ...
      formDiv.innerHTML += `<label>${field.label}: <input id="${id}" type="${field.type || "text"}" placeholder="${field.placeholder || ""}"></label><br>`;
    }
  });

  formDiv.innerHTML += `<button data-kind="${kind}" class="btn-submit-form"> ${submitLabel} </button>`;
  chatContainer.appendChild(formDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;

  const btn = formDiv.querySelector(".btn-submit-form");
  btn.addEventListener("click", async () => {
    const values = {};
    formData.fields.forEach(f => {
      const el = document.getElementById(f.name);
      values[f.name] = el?.type === "checkbox" ? !!el.checked : (el?.value ?? "");
    });

    addMessage("user", "Đã gửi form: " + JSON.stringify(values));

    try {
      const res = await fetch("/api/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, values })
      });
      const data = await res.json();
      renderResponse(data);
    } catch (e) {
      addMessage("agent", "❌ Lỗi gửi form: " + (e?.message || e));
    }
  });
}
