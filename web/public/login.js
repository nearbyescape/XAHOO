(async () => {
  const $ = s => document.querySelector(s);
  try { const i = await (await fetch("/api/login/info")).json(); $("#codewrap").hidden = !i.totp; } catch (e) { /* offline */ }
  $("#lf").addEventListener("submit", async ev => {
    ev.preventDefault();
    $("#err").textContent = "";
    const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: $("#pw").value, code: $("#code").value }) });
    if (r.ok) { location.replace("/"); return; }
    let msg = "Login failed";
    try { msg = (await r.json()).detail || msg; } catch (e) { /* ignore */ }
    $("#err").textContent = msg;
    $("#pw").select();
  });
})();
