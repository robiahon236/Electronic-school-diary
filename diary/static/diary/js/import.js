function getCookie(name) {
  const row = document.cookie.split('; ').find(r => r.startsWith(name + '='));
  return row ? decodeURIComponent(row.slice(name.length + 1)) : null;
}

document.getElementById('importBtn')?.addEventListener('click', async () => {
  const btn = document.getElementById('importBtn');
  const box = document.getElementById('importStatus');
  btn.disabled = true;
  box.textContent = 'Импорт...';
  box.className = 'ms-2 text-muted';
  try {
    const res = await fetch(btn.dataset.url, {
      method: 'POST',
      headers: {'X-CSRFToken': getCookie('csrftoken')},
    });
    const data = await res.json();
    if (data.status === 'ok') {
      let msg = `Загружено записей: ${data.count}`;
      if (data.source === 'fallback') msg += ' (резервный файл)';
      box.textContent = msg;
      box.className = 'ms-2 text-success';
    } else {
      box.textContent = data.message || 'Ошибка импорта';
      box.className = 'ms-2 text-danger';
    }
  } catch (e) {
    box.textContent = 'Сетевая ошибка';
    box.className = 'ms-2 text-danger';
  } finally {
    btn.disabled = false;
  }
});
