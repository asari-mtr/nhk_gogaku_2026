// nhk_gogaku_2026 LP - クリップボードコピー
"use strict";

document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".copy-btn");
  if (!btn) return;
  const targetSel = btn.dataset.copy;
  const target = document.querySelector(targetSel);
  if (!target) return;
  const text = target.textContent.trim();
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch {}
    ta.remove();
  }
  const label = btn.querySelector(".copy-label");
  btn.classList.add("copied");
  if (label) {
    const orig = label.textContent;
    label.textContent = "✓ コピー済";
    setTimeout(() => {
      label.textContent = orig;
      btn.classList.remove("copied");
    }, 1800);
  } else {
    setTimeout(() => btn.classList.remove("copied"), 1800);
  }
});
