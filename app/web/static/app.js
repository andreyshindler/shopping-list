// Toggle an item bought/unbought and refresh totals without a full reload.
async function toggleItem(el) {
  const id = el.dataset.id;
  const token = el.dataset.token;
  el.style.pointerEvents = "none";
  try {
    const res = await fetch(`/api/lists/${token}/items/${id}/toggle`, { method: "POST" });
    if (!res.ok) throw new Error("toggle failed");
    const data = await res.json();
    // If this tap just completed the whole list, remember it so the page can celebrate
    // after the reload (the flag is consumed once, on the next load).
    if (data.all_bought && data.totals && data.totals.total_count > 0) {
      sessionStorage.setItem("celebrate:" + location.pathname, "1");
    }
    // Easiest correct UI: reload so items re-group into the right section.
    window.location.reload();
  } catch (e) {
    el.style.pointerEvents = "";
    alert("Could not update item. Please try again.");
  }
}

// Keep "Total paid" in sync with the per-item prices the user enters,
// falling back to the predicted total. Manual edits to the field win.
function initCompleteForm() {
  const form = document.querySelector(".complete-card form");
  if (!form) return;
  const total = form.querySelector('input[name="real_total"]');
  const prices = [...form.querySelectorAll('input[name^="price_"]')];
  if (!total || prices.length === 0) return;

  let manual = false;
  total.addEventListener("input", () => {
    manual = true;
  });

  const sync = () => {
    if (manual) return;
    // For each item use the entered price, or fall back to its predicted price
    // (shown as the placeholder), so items left blank still count toward the total.
    let sum = 0;
    for (const p of prices) {
      const entered = parseFloat(p.value);
      sum += !isNaN(entered) ? entered : parseFloat(p.placeholder) || 0;
    }
    total.value = sum.toFixed(2);
  };

  prices.forEach((p) => p.addEventListener("input", sync));
  sync();
}

async function deleteItem(li) {
  try {
    const res = await fetch(`/api/lists/${li.dataset.token}/items/${li.dataset.id}/delete`, { method: "POST" });
    if (!res.ok) throw new Error("delete failed");
    window.location.reload();
  } catch {
    li.style.transform = "";
    li.style.background = "";
    li.style.pointerEvents = "";
  }
}

function initSwipeDelete() {
  document.querySelectorAll("li.item[data-id]:not(.bought)").forEach((li) => {
    let startX = 0, startY = 0, dx = 0, dragging = false;
    const THRESHOLD = 80;

    li.addEventListener("touchstart", (e) => {
      startX = e.touches[0].clientX;
      startY = e.touches[0].clientY;
      dx = 0;
      dragging = false;
      li.style.transition = "none";
    }, { passive: true });

    li.addEventListener("touchmove", (e) => {
      const newDx = e.touches[0].clientX - startX;
      const dy = e.touches[0].clientY - startY;
      if (!dragging && Math.abs(dy) > Math.abs(newDx)) return; // vertical scroll wins
      if (newDx > 0) return; // ignore right swipe
      dragging = true;
      dx = newDx;
      e.preventDefault();
      li.style.transform = `translateX(${Math.max(dx, -li.offsetWidth)}px)`;
      li.style.background = `rgba(231,76,60,${Math.min(1, Math.abs(dx) / THRESHOLD) * 0.2})`;
    }, { passive: false });

    li.addEventListener("touchend", () => {
      li.style.transition = "";
      li._swiped = dragging;
      if (dragging && dx < -THRESHOLD) {
        li.style.pointerEvents = "none";
        deleteItem(li);
      } else {
        li.style.transform = "";
        li.style.background = "";
      }
      dragging = false;
    });
  });
}

// A short, self-contained fireworks burst to celebrate a fully checked-off list.
// No libraries: a transient full-screen canvas of gravity-driven particles.
function launchFireworks() {
  // Respect users who ask for less motion — do nothing (the flag is already cleared).
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const colors = ["#2f80ed", "#27ae60", "#f2c94c", "#eb5757", "#9b51e0", "#ffffff"];
  const dpr = window.devicePixelRatio || 1;
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:9999";
  document.body.appendChild(canvas);
  const ctx = canvas.getContext("2d");

  const resize = () => {
    canvas.width = window.innerWidth * dpr;
    canvas.height = window.innerHeight * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  resize();
  window.addEventListener("resize", resize);

  const W = () => window.innerWidth;
  const H = () => window.innerHeight;
  const particles = [];

  function burst(x, y) {
    const color = colors[Math.floor(Math.random() * colors.length)];
    const count = 28 + Math.floor(Math.random() * 12);
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + Math.random() * 0.3;
      const speed = 2 + Math.random() * 3.5;
      particles.push({
        x, y,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        life: 1,
        color,
        size: 2 + Math.random() * 2,
      });
    }
  }

  // Stagger a few bursts across the upper half of the screen.
  const bursts = 5;
  for (let b = 0; b < bursts; b++) {
    setTimeout(() => burst(W() * (0.2 + Math.random() * 0.6), H() * (0.2 + Math.random() * 0.35)), b * 160);
  }

  const start = performance.now();
  let raf;
  function frame(now) {
    ctx.clearRect(0, 0, W(), H());
    for (const p of particles) {
      p.vy += 0.06;        // gravity
      p.vx *= 0.99;        // drag
      p.x += p.vx;
      p.y += p.vy;
      p.life -= 0.012;
      if (p.life <= 0) continue;
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    // Keep going until the last burst has faded (bursts finish at ~640ms + fade).
    if (now - start < 2200) {
      raf = requestAnimationFrame(frame);
    } else {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      canvas.remove();
    }
  }
  raf = requestAnimationFrame(frame);
}

// Note: after picking a variant the server redirects to "#item-<id>", so the browser
// lands on the resolved item natively. No scroll handling is needed here.
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("li.item[data-id]").forEach((el) => {
    el.addEventListener("click", () => {
      if (el._swiped) { el._swiped = false; return; }
      toggleItem(el);
    });
  });
  initCompleteForm();
  initSwipeDelete();

  // Celebrate once if the last item was just checked off (flag set before the reload).
  const celebrateKey = "celebrate:" + location.pathname;
  if (sessionStorage.getItem(celebrateKey)) {
    sessionStorage.removeItem(celebrateKey);
    launchFireworks();
  }
});
