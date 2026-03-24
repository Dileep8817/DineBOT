// Vanilla HTML demo — set API_KEY to match server .env API_KEY (same-origin proxy not used here).

const API_BASE = "http://127.0.0.1:8000";
const API_KEY = ""; // paste for local testing only; prefer React dev proxy

const apiHeaders = () =>
  API_KEY ? { "X-API-Key": API_KEY } : {};

let sessionId = "session_demo_1";

async function loadMenu() {
  const res = await fetch(`${API_BASE}/menu?restaurant_id=restaurant_1`, {
    headers: apiHeaders(),
  });
  const menu = await res.json();

  const menuDiv = document.getElementById("menu");
  menuDiv.innerHTML = "";

  menu.items.forEach((item) => {
    const itemDiv = document.createElement("div");
    itemDiv.innerHTML = `
            <strong>${item.name}</strong> - $${item.price} <br>
            ${item.description} <br>
            <button onclick="addToCart('${item.name.replace(/'/g, "\\'")}')">Add to Cart</button>
            <hr>
        `;
    menuDiv.appendChild(itemDiv);
  });
}

async function addToCart(itemName) {
  await fetch(
    `${API_BASE}/cart/add?session_id=${sessionId}&name=${encodeURIComponent(itemName)}`,
    { method: "POST", headers: apiHeaders() }
  );
  loadCart();
}

async function loadCart() {
  const res = await fetch(`${API_BASE}/cart?session_id=${sessionId}`, {
    headers: apiHeaders(),
  });
  const cart = await res.json();

  const cartDiv = document.getElementById("cart");
  cartDiv.innerHTML = "";

  let total = 0;
  cart.forEach((item) => {
    const itemDiv = document.createElement("div");
    itemDiv.innerHTML = `
            ${item.name} - $${item.price} x ${item.quantity}
            <button onclick="updateItem('${item.name.replace(/'/g, "\\'")}', ${item.quantity + 1})">+</button>
            <button onclick="updateItem('${item.name.replace(/'/g, "\\'")}', ${item.quantity - 1})">-</button>
            <button onclick="removeItem('${item.name.replace(/'/g, "\\'")}')">Remove</button>
        `;
    cartDiv.appendChild(itemDiv);
    total += item.price * item.quantity;
  });

  document.getElementById("total").innerText = total;
}

async function updateItem(name, quantity) {
  if (quantity <= 0) {
    removeItem(name);
    return;
  }

  await fetch(
    `${API_BASE}/cart/update?session_id=${sessionId}&name=${encodeURIComponent(name)}&quantity=${quantity}`,
    { method: "POST", headers: apiHeaders() }
  );
  loadCart();
}

async function removeItem(name) {
  await fetch(
    `${API_BASE}/cart/remove?session_id=${sessionId}&name=${encodeURIComponent(name)}`,
    { method: "POST", headers: apiHeaders() }
  );
  loadCart();
}

loadMenu();
loadCart();
