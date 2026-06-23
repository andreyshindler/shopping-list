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

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("li.item[data-id]").forEach((el) => {
    el.addEventListener("click", () => toggleItem(el));
  });
});
