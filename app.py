import json
import os
import random
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


DATA_FILE = "case_simulator_data.json"


@dataclass
class Rarity:
    id: str
    name: str
    min_roll: float
    max_roll: float
    color: str = "#888888"


@dataclass
class Item:
    id: str
    name: str
    rarity_id: str
    weight: float
    image_path: str = ""
    description: str = ""


class DataStore:
    def __init__(self, path: str = DATA_FILE):
        self.path = path
        self.data = {
            "rarities": [],
            "items": [],
            "inventory": {},
            "history": [],
            "stats": {
                "total_opened": 0,
                "total_spent": 0,
                "by_rarity": {},
                "by_item": {},
            },
            "settings": {
                "roll_min": 0,
                "roll_max": 100,
                "open_price": 1,
            },
        }
        self._load_or_create_defaults()

    def _load_or_create_defaults(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass
        if not self.data["rarities"]:
            self.data["rarities"] = [
                asdict(Rarity(str(uuid.uuid4()), "Обычная", 0, 60, "#b0b0b0")),
                asdict(Rarity(str(uuid.uuid4()), "Редкая", 60, 85, "#4f8cff")),
                asdict(Rarity(str(uuid.uuid4()), "Эпическая", 85, 97, "#bb6eff")),
                asdict(Rarity(str(uuid.uuid4()), "Легендарная", 97, 100, "#ff9f1a")),
            ]
        if not self.data["items"]:
            r = self.data["rarities"]
            self.data["items"] = [
                asdict(Item(str(uuid.uuid4()), "Старый нож", r[0]["id"], 10, "", "Простой предмет")),
                asdict(Item(str(uuid.uuid4()), "Сияющий пистолет", r[1]["id"], 6, "", "Редкая находка")),
                asdict(Item(str(uuid.uuid4()), "Кристальный меч", r[2]["id"], 3, "", "Очень ценный")),
                asdict(Item(str(uuid.uuid4()), "Драконья корона", r[3]["id"], 1, "", "Почти не выпадает")),
            ]
        self.save()

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def _rarity_map(self) -> Dict[str, dict]:
        return {r["id"]: r for r in self.data["rarities"]}

    def _item_map(self) -> Dict[str, dict]:
        return {i["id"]: i for i in self.data["items"]}

    def _append_history(self, action: str, payload: dict):
        self.data["history"].insert(0, {
            "id": str(uuid.uuid4()),
            "timestamp": int(time.time()),
            "action": action,
            "payload": payload,
        })
        self.data["history"] = self.data["history"][:500]

    def _roll_rarity(self, roll: float) -> Optional[dict]:
        for r in self.data["rarities"]:
            if r["min_roll"] <= roll <= r["max_roll"]:
                return r
        return None

    def _pick_item_by_rarity(self, rarity_id: str) -> Optional[dict]:
        candidates = [i for i in self.data["items"] if i["rarity_id"] == rarity_id and i["weight"] > 0]
        if not candidates:
            return None
        total_weight = sum(i["weight"] for i in candidates)
        point = random.uniform(0, total_weight)
        current = 0
        for item in candidates:
            current += item["weight"]
            if point <= current:
                return item
        return candidates[-1]

    def _validate_rarity_ranges(self) -> Tuple[bool, str]:
        roll_min = self.data["settings"]["roll_min"]
        roll_max = self.data["settings"]["roll_max"]
        if roll_min >= roll_max:
            return False, "roll_min должен быть меньше roll_max"
        for r in self.data["rarities"]:
            if r["min_roll"] > r["max_roll"]:
                return False, f"У редкости {r['name']} min_roll > max_roll"
        ranges = sorted((r["min_roll"], r["max_roll"], r["name"]) for r in self.data["rarities"])
        for i in range(1, len(ranges)):
            if ranges[i][0] < ranges[i - 1][1]:
                return False, f"Диапазоны {ranges[i - 1][2]} и {ranges[i][2]} пересекаются"
        return True, "ok"

    def open_case(self, times: int = 1) -> dict:
        times = max(1, min(100, int(times)))
        valid, msg = self._validate_rarity_ranges()
        if not valid:
            return {"ok": False, "message": msg}

        result = []
        settings = self.data["settings"]
        for _ in range(times):
            roll = random.uniform(settings["roll_min"], settings["roll_max"])
            rarity = self._roll_rarity(roll)
            if rarity is None:
                continue
            item = self._pick_item_by_rarity(rarity["id"])
            if item is None:
                continue

            inv = self.data["inventory"]
            inv[item["id"]] = inv.get(item["id"], 0) + 1
            self.data["stats"]["total_opened"] += 1
            self.data["stats"]["total_spent"] += settings["open_price"]
            self.data["stats"]["by_rarity"][rarity["id"]] = self.data["stats"]["by_rarity"].get(rarity["id"], 0) + 1
            self.data["stats"]["by_item"][item["id"]] = self.data["stats"]["by_item"].get(item["id"], 0) + 1
            result.append({
                "roll": round(roll, 3),
                "rarity": rarity,
                "item": item,
            })

        self._append_history("open_case", {"times": times, "results": result[:10], "count_results": len(result)})
        self.save()
        return {"ok": True, "results": result, "state": self.state()}

    def add_rarity(self, rarity: dict) -> dict:
        entry = asdict(Rarity(
            id=str(uuid.uuid4()),
            name=rarity["name"],
            min_roll=float(rarity["min_roll"]),
            max_roll=float(rarity["max_roll"]),
            color=rarity.get("color", "#888888"),
        ))
        self.data["rarities"].append(entry)
        valid, msg = self._validate_rarity_ranges()
        if not valid:
            self.data["rarities"].pop()
            return {"ok": False, "message": msg}
        self._append_history("add_rarity", entry)
        self.save()
        return {"ok": True, "state": self.state()}

    def update_rarity(self, rarity_id: str, payload: dict) -> dict:
        for rarity in self.data["rarities"]:
            if rarity["id"] == rarity_id:
                rarity["name"] = payload.get("name", rarity["name"])
                rarity["min_roll"] = float(payload.get("min_roll", rarity["min_roll"]))
                rarity["max_roll"] = float(payload.get("max_roll", rarity["max_roll"]))
                rarity["color"] = payload.get("color", rarity["color"])
                valid, msg = self._validate_rarity_ranges()
                if not valid:
                    return {"ok": False, "message": msg}
                self._append_history("update_rarity", rarity)
                self.save()
                return {"ok": True, "state": self.state()}
        return {"ok": False, "message": "Редкость не найдена"}

    def delete_rarity(self, rarity_id: str) -> dict:
        if any(i["rarity_id"] == rarity_id for i in self.data["items"]):
            return {"ok": False, "message": "Нельзя удалить редкость, пока есть связанные предметы"}
        before = len(self.data["rarities"])
        self.data["rarities"] = [r for r in self.data["rarities"] if r["id"] != rarity_id]
        if len(self.data["rarities"]) == before:
            return {"ok": False, "message": "Редкость не найдена"}
        self._append_history("delete_rarity", {"rarity_id": rarity_id})
        self.save()
        return {"ok": True, "state": self.state()}

    def add_item(self, payload: dict) -> dict:
        rarity_map = self._rarity_map()
        if payload["rarity_id"] not in rarity_map:
            return {"ok": False, "message": "Указанная редкость не существует"}
        item = asdict(Item(
            id=str(uuid.uuid4()),
            name=payload["name"],
            rarity_id=payload["rarity_id"],
            weight=float(payload.get("weight", 1)),
            image_path=payload.get("image_path", ""),
            description=payload.get("description", ""),
        ))
        self.data["items"].append(item)
        self._append_history("add_item", item)
        self.save()
        return {"ok": True, "state": self.state()}

    def update_item(self, item_id: str, payload: dict) -> dict:
        rarity_map = self._rarity_map()
        for item in self.data["items"]:
            if item["id"] == item_id:
                if "rarity_id" in payload and payload["rarity_id"] not in rarity_map:
                    return {"ok": False, "message": "Указанная редкость не существует"}
                item["name"] = payload.get("name", item["name"])
                item["rarity_id"] = payload.get("rarity_id", item["rarity_id"])
                item["weight"] = float(payload.get("weight", item["weight"]))
                item["image_path"] = payload.get("image_path", item["image_path"])
                item["description"] = payload.get("description", item["description"])
                self._append_history("update_item", item)
                self.save()
                return {"ok": True, "state": self.state()}
        return {"ok": False, "message": "Предмет не найден"}

    def delete_item(self, item_id: str) -> dict:
        before = len(self.data["items"])
        self.data["items"] = [i for i in self.data["items"] if i["id"] != item_id]
        if len(self.data["items"]) == before:
            return {"ok": False, "message": "Предмет не найден"}
        self.data["inventory"].pop(item_id, None)
        self._append_history("delete_item", {"item_id": item_id})
        self.save()
        return {"ok": True, "state": self.state()}

    def adjust_inventory(self, item_id: str, delta: int) -> dict:
        items = self._item_map()
        if item_id not in items:
            return {"ok": False, "message": "Предмет не найден"}
        cur = self.data["inventory"].get(item_id, 0)
        new_val = cur + delta
        if new_val < 0:
            return {"ok": False, "message": "Недостаточно предметов в инвентаре"}
        if new_val == 0:
            self.data["inventory"].pop(item_id, None)
        else:
            self.data["inventory"][item_id] = new_val
        action = "consume_item" if delta < 0 else "add_inventory"
        self._append_history(action, {"item_id": item_id, "delta": delta})
        self.save()
        return {"ok": True, "state": self.state()}

    def update_settings(self, payload: dict) -> dict:
        s = self.data["settings"]
        for key in ("roll_min", "roll_max", "open_price"):
            if key in payload:
                s[key] = float(payload[key])
        valid, msg = self._validate_rarity_ranges()
        if not valid:
            return {"ok": False, "message": msg}
        self._append_history("update_settings", s)
        self.save()
        return {"ok": True, "state": self.state()}

    def clear_history(self):
        self.data["history"] = []
        self.save()
        return {"ok": True, "state": self.state()}

    def reset_stats(self):
        self.data["stats"] = {
            "total_opened": 0,
            "total_spent": 0,
            "by_rarity": {},
            "by_item": {},
        }
        self._append_history("reset_stats", {})
        self.save()
        return {"ok": True, "state": self.state()}

    def state(self):
        return self.data


class API:
    def __init__(self):
        self.store = DataStore()

    def get_state(self):
        return {"ok": True, "state": self.store.state()}

    def open_case(self, times=1):
        return self.store.open_case(times)

    def add_rarity(self, rarity):
        return self.store.add_rarity(rarity)

    def update_rarity(self, rarity_id, payload):
        return self.store.update_rarity(rarity_id, payload)

    def delete_rarity(self, rarity_id):
        return self.store.delete_rarity(rarity_id)

    def add_item(self, payload):
        return self.store.add_item(payload)

    def update_item(self, item_id, payload):
        return self.store.update_item(item_id, payload)

    def delete_item(self, item_id):
        return self.store.delete_item(item_id)

    def adjust_inventory(self, item_id, delta):
        return self.store.adjust_inventory(item_id, int(delta))

    def update_settings(self, payload):
        return self.store.update_settings(payload)

    def clear_history(self):
        return self.store.clear_history()

    def reset_stats(self):
        return self.store.reset_stats()


HTML = r"""
<!doctype html>
<html lang="ru">
<head>
<meta charset="UTF-8" />
<title>Симулятор кейсов</title>
<style>
  body { font-family: Inter, Arial, sans-serif; margin: 0; background: #111827; color: #f9fafb; }
  header { padding: 16px 22px; border-bottom: 1px solid #374151; display:flex; justify-content:space-between; align-items:center; }
  .container { padding: 18px 22px; }
  .row { display:flex; gap:14px; flex-wrap:wrap; }
  .card { background: #1f2937; border:1px solid #374151; border-radius:10px; padding:14px; margin-bottom:14px; }
  .card h3 { margin-top:0; }
  input, select, button, textarea { background:#111827; color:#f9fafb; border:1px solid #4b5563; border-radius:8px; padding:8px; }
  button { cursor:pointer; }
  button.primary { background:#2563eb; border-color:#2563eb; }
  table { width:100%; border-collapse: collapse; }
  th,td { border-bottom:1px solid #374151; padding:6px; text-align:left; font-size: 13px; }
  .tabs button { margin-right: 8px; }
  .hidden { display:none; }
  .badge { padding:2px 8px; border-radius:999px; font-size:12px; }
  .mini { font-size:12px; color:#cbd5e1; }
  .img-thumb { width:38px; height:38px; object-fit:cover; border-radius:8px; border:1px solid #4b5563; }
</style>
</head>
<body>
<header>
  <strong>🎁 Полноценный симулятор кейсов</strong>
  <span id="status" class="mini"></span>
</header>
<div class="container">
  <div class="tabs card">
    <button onclick="showTab('open')">Открытие</button>
    <button onclick="showTab('items')">Предметы</button>
    <button onclick="showTab('rarities')">Редкости</button>
    <button onclick="showTab('inventory')">Инвентарь</button>
    <button onclick="showTab('history')">История</button>
    <button onclick="showTab('stats')">Статистика</button>
    <button onclick="showTab('settings')">Настройки</button>
  </div>

  <section id="tab-open" class="card">
    <h3>Открытие кейсов</h3>
    <div class="row">
      <input id="open-times" type="number" min="1" max="100" value="1" />
      <button class="primary" onclick="openCases()">Открыть</button>
    </div>
    <div id="open-results" style="margin-top:10px"></div>
  </section>

  <section id="tab-items" class="card hidden">
    <h3>Управление предметами</h3>
    <div class="row">
      <input id="item-name" placeholder="Название" />
      <select id="item-rarity"></select>
      <input id="item-weight" type="number" step="0.1" value="1" placeholder="Вес" />
      <input id="item-image" placeholder="Путь/URL изображения" />
      <input id="item-description" placeholder="Описание" />
      <button onclick="addItem()">Добавить</button>
    </div>
    <table id="items-table"></table>
  </section>

  <section id="tab-rarities" class="card hidden">
    <h3>Категории редкости и диапазоны</h3>
    <div class="row">
      <input id="rarity-name" placeholder="Название" />
      <input id="rarity-min" type="number" step="0.1" placeholder="min" />
      <input id="rarity-max" type="number" step="0.1" placeholder="max" />
      <input id="rarity-color" type="color" value="#888888" />
      <button onclick="addRarity()">Добавить</button>
    </div>
    <table id="rarities-table"></table>
  </section>

  <section id="tab-inventory" class="card hidden">
    <h3>Инвентарь и расход предметов</h3>
    <table id="inventory-table"></table>
  </section>

  <section id="tab-history" class="card hidden">
    <h3>История действий</h3>
    <button onclick="clearHistory()">Очистить историю</button>
    <table id="history-table"></table>
  </section>

  <section id="tab-stats" class="card hidden">
    <h3>Статистика</h3>
    <button onclick="resetStats()">Сброс статистики</button>
    <div id="stats-box"></div>
  </section>

  <section id="tab-settings" class="card hidden">
    <h3>Настройки симулятора</h3>
    <div class="row">
      <label>roll_min <input id="set-roll-min" type="number" step="0.1"></label>
      <label>roll_max <input id="set-roll-max" type="number" step="0.1"></label>
      <label>Цена открытия <input id="set-open-price" type="number" step="0.1"></label>
      <button onclick="saveSettings()">Сохранить</button>
    </div>
  </section>
</div>

<script>
let state = null;

function setStatus(text, err=false) {
  const el = document.getElementById('status');
  el.textContent = text;
  el.style.color = err ? '#fca5a5' : '#93c5fd';
}

function showTab(name) {
  for (const sec of document.querySelectorAll('section[id^="tab-"]')) sec.classList.add('hidden');
  document.getElementById('tab-' + name).classList.remove('hidden');
}

function rarityById(id) { return state.rarities.find(r => r.id === id); }
function itemById(id) { return state.items.find(i => i.id === id); }

async function apiCall(name, ...args) {
  const res = await window.pywebview.api[name](...args);
  if (!res.ok) { setStatus(res.message || 'Ошибка', true); throw new Error(res.message || 'Ошибка'); }
  if (res.state) state = res.state;
  setStatus('Готово');
  renderAll();
  return res;
}

function rarityBadge(r) {
  return `<span class="badge" style="background:${r.color}22;border:1px solid ${r.color};color:${r.color}">${r.name}</span>`;
}

function renderItems() {
  const sel = document.getElementById('item-rarity');
  sel.innerHTML = state.rarities.map(r => `<option value="${r.id}">${r.name}</option>`).join('');

  const tbl = document.getElementById('items-table');
  const head = `<tr><th>Изобр.</th><th>Название</th><th>Редкость</th><th>Вес</th><th>Описание</th><th></th></tr>`;
  const rows = state.items.map(i => {
    const r = rarityById(i.rarity_id);
    const img = i.image_path ? `<img class="img-thumb" src="${i.image_path}"/>` : '-';
    return `<tr>
      <td>${img}</td>
      <td>${i.name}</td>
      <td>${r ? rarityBadge(r) : '-'}</td>
      <td>${i.weight}</td>
      <td>${i.description || ''}</td>
      <td>
        <button onclick="editItem('${i.id}')">Ред.</button>
        <button onclick="deleteItem('${i.id}')">Удалить</button>
      </td>
    </tr>`;
  }).join('');
  tbl.innerHTML = head + rows;
}

function renderRarities() {
  const tbl = document.getElementById('rarities-table');
  const head = `<tr><th>Название</th><th>Диапазон</th><th>Цвет</th><th></th></tr>`;
  const rows = state.rarities.map(r => `<tr>
    <td>${r.name}</td>
    <td>${r.min_roll} - ${r.max_roll}</td>
    <td>${rarityBadge(r)}</td>
    <td>
      <button onclick="editRarity('${r.id}')">Ред.</button>
      <button onclick="deleteRarity('${r.id}')">Удалить</button>
    </td>
  </tr>`).join('');
  tbl.innerHTML = head + rows;
}

function renderInventory() {
  const tbl = document.getElementById('inventory-table');
  const head = `<tr><th>Предмет</th><th>Редкость</th><th>Количество</th><th></th></tr>`;
  const rows = Object.entries(state.inventory).map(([itemId, qty]) => {
    const i = itemById(itemId);
    if (!i) return '';
    const r = rarityById(i.rarity_id);
    return `<tr>
      <td>${i.name}</td>
      <td>${r ? rarityBadge(r) : '-'}</td>
      <td>${qty}</td>
      <td>
        <button onclick="adjustInv('${i.id}',1)">+1</button>
        <button onclick="adjustInv('${i.id}',-1)">Потратить 1</button>
      </td>
    </tr>`;
  }).join('');
  tbl.innerHTML = head + rows;
}

function renderHistory() {
  const tbl = document.getElementById('history-table');
  const head = `<tr><th>Время</th><th>Действие</th><th>Данные</th></tr>`;
  const rows = state.history.slice(0, 100).map(h => `<tr>
    <td>${new Date(h.timestamp * 1000).toLocaleString()}</td>
    <td>${h.action}</td>
    <td><code>${JSON.stringify(h.payload)}</code></td>
  </tr>`).join('');
  tbl.innerHTML = head + rows;
}

function renderStats() {
  const box = document.getElementById('stats-box');
  const s = state.stats;
  const rarityStats = Object.entries(s.by_rarity).map(([rid, cnt]) => {
    const r = rarityById(rid);
    return `<li>${r ? r.name : rid}: ${cnt}</li>`;
  }).join('');
  const itemStats = Object.entries(s.by_item).map(([iid, cnt]) => {
    const i = itemById(iid);
    return `<li>${i ? i.name : iid}: ${cnt}</li>`;
  }).join('');

  box.innerHTML = `
    <p>Всего открытий: <strong>${s.total_opened}</strong></p>
    <p>Потрачено валюты: <strong>${s.total_spent}</strong></p>
    <h4>По редкостям</h4><ul>${rarityStats}</ul>
    <h4>По предметам</h4><ul>${itemStats}</ul>
  `;
}

function renderSettings() {
  document.getElementById('set-roll-min').value = state.settings.roll_min;
  document.getElementById('set-roll-max').value = state.settings.roll_max;
  document.getElementById('set-open-price').value = state.settings.open_price;
}

function renderAll() {
  if (!state) return;
  renderItems();
  renderRarities();
  renderInventory();
  renderHistory();
  renderStats();
  renderSettings();
}

async function openCases() {
  const times = parseInt(document.getElementById('open-times').value || '1', 10);
  const res = await apiCall('open_case', times);
  const html = res.results.map(row => `${rarityBadge(row.rarity)} ${row.item.name} (roll ${row.roll})`).join('<br>');
  document.getElementById('open-results').innerHTML = html || '<i>Нет выпавших предметов</i>';
}

async function addItem() {
  await apiCall('add_item', {
    name: document.getElementById('item-name').value,
    rarity_id: document.getElementById('item-rarity').value,
    weight: parseFloat(document.getElementById('item-weight').value || '1'),
    image_path: document.getElementById('item-image').value,
    description: document.getElementById('item-description').value,
  });
}

async function editItem(id) {
  const i = itemById(id);
  const name = prompt('Название', i.name); if (name === null) return;
  const weight = prompt('Вес', i.weight); if (weight === null) return;
  const image_path = prompt('Изображение', i.image_path || '') ?? '';
  const description = prompt('Описание', i.description || '') ?? '';
  const rarity_id = prompt('ID редкости', i.rarity_id); if (rarity_id === null) return;
  await apiCall('update_item', id, {name, weight: parseFloat(weight), image_path, description, rarity_id});
}

async function deleteItem(id) { if (confirm('Удалить предмет?')) await apiCall('delete_item', id); }

async function addRarity() {
  await apiCall('add_rarity', {
    name: document.getElementById('rarity-name').value,
    min_roll: parseFloat(document.getElementById('rarity-min').value),
    max_roll: parseFloat(document.getElementById('rarity-max').value),
    color: document.getElementById('rarity-color').value,
  });
}

async function editRarity(id) {
  const r = rarityById(id);
  const name = prompt('Название', r.name); if (name === null) return;
  const min_roll = prompt('Минимум', r.min_roll); if (min_roll === null) return;
  const max_roll = prompt('Максимум', r.max_roll); if (max_roll === null) return;
  const color = prompt('Цвет', r.color); if (color === null) return;
  await apiCall('update_rarity', id, {name, min_roll: parseFloat(min_roll), max_roll: parseFloat(max_roll), color});
}

async function deleteRarity(id) { if (confirm('Удалить редкость?')) await apiCall('delete_rarity', id); }
async function adjustInv(id, delta) { await apiCall('adjust_inventory', id, delta); }
async function clearHistory() { if (confirm('Очистить историю?')) await apiCall('clear_history'); }
async function resetStats() { if (confirm('Сбросить статистику?')) await apiCall('reset_stats'); }
async function saveSettings() {
  await apiCall('update_settings', {
    roll_min: parseFloat(document.getElementById('set-roll-min').value),
    roll_max: parseFloat(document.getElementById('set-roll-max').value),
    open_price: parseFloat(document.getElementById('set-open-price').value),
  });
}

window.addEventListener('pywebviewready', async () => {
  const res = await window.pywebview.api.get_state();
  state = res.state;
  renderAll();
});
</script>
</body>
</html>
"""


def main():
    import webview

    api = API()
    window = webview.create_window(
        "Симулятор кейсов",
        html=HTML,
        js_api=api,
        width=1400,
        height=900,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
