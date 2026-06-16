const tg = window.Telegram?.WebApp;
let dashboardUrl = "/";

if (tg) {
  tg.ready();
  tg.expand();
  tg.setHeaderColor("#0c1117");
  tg.setBackgroundColor("#0c1117");
}

function uid() {
  return tg?.initDataUnsafe?.user?.id || new URLSearchParams(location.search).get("uid");
}

function fmt(n) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n || 0);
}

async function api(path) {
  const id = uid();
  const sep = path.includes("?") ? "&" : "?";
  const url = id ? `${path}${sep}user_id=${id}` : path;
  const r = await fetch(url);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function haptic() {
  try { tg?.HapticFeedback?.impactOccurred("light"); } catch (_) {}
}

function send(action, extra = {}) {
  haptic();
  const payload = JSON.stringify({ action, ...extra });
  if (tg?.sendData) {
    tg.sendData(payload);
    setTimeout(() => tg.close?.(), 200);
    return;
  }
  alert("Открой из Telegram-бота Money Hub");
}

async function load() {
  try {
    const data = await api("/api/mini/home");
    const m = data.metrics || {};
    document.getElementById("target").textContent = fmt(m.target_today) + " ₽";
    document.getElementById("actual").textContent = fmt(m.actual_today) + " ₽";
    document.getElementById("gap").textContent = fmt(m.gap) + " ₽";
    dashboardUrl = data.dashboard_url || dashboardUrl;

    const list = document.getElementById("planList");
    const plan = data.plan || [];
    if (!plan.length) {
      list.innerHTML = "<li>План пуст — добавь в боте /money plan slug</li>";
    } else {
      list.innerHTML = plan
        .map((p) => `<li>${p.title || p.slug} — ${fmt(p.expected_rub)} ₽</li>`)
        .join("");
    }

    const sel = document.getElementById("ideaSlug");
    const ideas = data.ideas || [];
    sel.innerHTML = ideas.length
      ? ideas.map((i) => `<option value="${i.slug}">${i.title}</option>`).join("")
      : '<option value="oracle-platform">oracle-platform</option>';
  } catch (e) {
    console.warn(e);
    document.getElementById("subtitle").textContent = "Нет доступа или офлайн";
  }
}

document.querySelectorAll(".amounts button").forEach((btn) => {
  btn.addEventListener("click", () => {
    const slug = document.getElementById("ideaSlug")?.value;
    send("revenue", { slug, amount: Number(btn.dataset.amt) });
  });
});

document.getElementById("btnReport")?.addEventListener("click", () => send("report"));
document.getElementById("btnSummary")?.addEventListener("click", () => send("summary"));
document.getElementById("btnDashboard")?.addEventListener("click", () => {
  haptic();
  if (dashboardUrl.startsWith("http")) {
    tg?.openLink?.(dashboardUrl) || window.open(dashboardUrl, "_blank");
  }
});

load();
