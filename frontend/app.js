// This file fetches from FastAPI and updates the page

const API_BASE = "http://127.0.0.1:8000"; // your FastAPI backend

let sessionId = "restaurant_1"; // just for testing

// Fetch menu from backend
async function loadMenu() {
    const res = await fetch(`${API_BASE}/menu?restaurant_id=restaurant_1`);
    const menu = await res.json();

    const menuDiv = document.getElementById("menu");
    menuDiv.innerHTML = "";

    menu.items.forEach(item => {
        const itemDiv = document.createElement("div");
        itemDiv.innerHTML = `
            <strong>${item.name}</strong> - $${item.price} <br>
            ${item.description} <br>
            <button onclick="addToCart('${item.name}')">Add to Cart</button>
            <hr>
        `;
        menuDiv.appendChild(itemDiv);
    });
}

// Add item to cart
async function addToCart(itemName) {
    const res = await fetch(`${API_BASE}/cart/add?session_id=${sessionId}&name=${encodeURIComponent(itemName)}`, {
        method: "POST"
    });

    const cart = await res.json();
    loadCart();
}

// Load cart from backend
async function loadCart() {
    const res = await fetch(`${API_BASE}/cart?session_id=${sessionId}`);
    const cart = await res.json();

    const cartDiv = document.getElementById("cart");
    cartDiv.innerHTML = "";

    let total = 0;
    cart.forEach(item => {
        const itemDiv = document.createElement("div");
        itemDiv.innerHTML = `
            ${item.name} - $${item.price} x ${item.quantity}
            <button onclick="updateItem('${item.name}', ${item.quantity + 1})">+</button>
            <button onclick="updateItem('${item.name}', ${item.quantity - 1})">-</button>
            <button onclick="removeItem('${item.name}')">Remove</button>
        `;
        cartDiv.appendChild(itemDiv);
        total += item.price * item.quantity;
    });

    document.getElementById("total").innerText = total;
}

// Update item quantity
async function updateItem(name, quantity) {
    if (quantity <= 0) {
        removeItem(name);
        return;
    }

    await fetch(`${API_BASE}/cart/update?session_id=${sessionId}&name=${encodeURIComponent(name)}&quantity=${quantity}`, {
        method: "POST"
    });
    loadCart();
}

// Remove item
async function removeItem(name) {
    await fetch(`${API_BASE}/cart/remove?session_id=${sessionId}&name=${encodeURIComponent(name)}`, {
        method: "POST"
    });
    loadCart();
}

// Initialize
loadMenu();
loadCart();