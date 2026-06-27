// Toggle an item bought/unbought and refresh totals without a full reload.
async function toggleItem(el) {
  const id = el.dataset.id;
  el.style.pointerEvents = "none";
  try {
    const res = await fetch(`/api/items/${id}/toggle`, { method: "POST" });
    if (!res.ok) throw new Error("toggle failed");
    const data = await res.json();
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
    const res = await fetch(`/api/items/${li.dataset.id}/delete`, { method: "POST" });
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

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("li.item[data-id]").forEach((el) => {
    el.addEventListener("click", () => {
      if (el._swiped) { el._swiped = false; return; }
      toggleItem(el);
    });
  });
  initCompleteForm();
  initSwipeDelete();
});
