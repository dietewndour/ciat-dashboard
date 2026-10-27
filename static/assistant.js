// Interface de l'assistant : envoie la question, affiche une réponse construite par le serveur.
(function () {
  const chat = document.getElementById("chat");
  const form = document.getElementById("ask");
  const input = document.getElementById("q");
  const add = (cls, text) => {
    const d = document.createElement("div");
    d.className = "msg " + cls;
    d.textContent = text; // textContent : pas d'injection HTML
    chat.appendChild(d); chat.scrollTop = chat.scrollHeight;
    return d;
  };
  async function ask(question) {
    add("q", question);
    const wait = add("a", "Calcul en cours...");
    try {
      const r = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": document.getElementById("csrf").value },
        body: JSON.stringify({ question }),
      });
      const data = await r.json();
      wait.textContent = (data.interpretation ? "Interprétation : " + data.interpretation + "\n" : "") + data.text;
      
    } catch (e) {
      wait.textContent = "Erreur de communication avec le serveur.";
    }
  }
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (q) { input.value = ""; ask(q); }
  });
  document.querySelectorAll(".chips button").forEach((b) =>
    b.addEventListener("click", () => ask(b.textContent)));
})();
