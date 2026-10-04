// Dodavanje nove stavke u formu narudžbine
function addItem() {
  const tpl = document.getElementById('item-template');
  if (!tpl) return;
  const clone = tpl.content.cloneNode(true);
  document.getElementById('items').appendChild(clone);
}

// Osvježavanje low-stock alarma svakih 60s (bez reload-a stranice)
setInterval(async () => {
  try {
    const r = await fetch('/api/low-stock');
    const data = await r.json();
    if (data.length > 0) {
      document.title = `⚠️ (${data.length}) MicroStock`;
    }
  } catch (e) {}
}, 60000);