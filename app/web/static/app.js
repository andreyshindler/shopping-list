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

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("li.item[data-id]").forEach((el) => {
    el.addEventListener("click", () => toggleItem(el));
  });
  initCompleteForm();
});
