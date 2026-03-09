import { useEffect, useState, useRef } from "react";
import axios from "axios";
import "./Widget.css";

const DEFAULT_API_BASE = "http://127.0.0.1:8000";
const LOGO_URL = process.env.PUBLIC_URL ? process.env.PUBLIC_URL + "/dinebot-logo.png" : "/dinebot-logo.png";

function getSessionId() {
  let id = sessionStorage.getItem("dinebot_session_id");
  if (!id) {
    id = "session_" + Math.random().toString(36).slice(2, 9);
    sessionStorage.setItem("dinebot_session_id", id);
  }
  return id;
}

function getRestaurantId() {
  const params = new URLSearchParams(window.location.search);
  return params.get("restaurant_id") || "restaurant_1";
}

function getThemeFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const primary = params.get("primary_color") || "#2d7d46";
  const name = params.get("restaurant_name") || "DineBot";
  return { primaryColor: primary, restaurantName: name };
}

const QUICK_PROMPTS = ["What's on the menu?", "Hours?", "Add Margherita Pizza to cart", "View my cart"];

function getApiBase() {
  return process.env.REACT_APP_API_BASE || DEFAULT_API_BASE;
}

function formatBotResponse(data) {
  if (typeof data === "string") return data;
  if (!data || typeof data !== "object") return String(data);
  if (data.items && Array.isArray(data.items)) {
    if (data.items.length === 0) return "No items found.";
    return data.items
      .map((i) => `• ${i.name} — $${i.price}${i.description ? ": " + i.description : ""}`)
      .join("\n");
  }
  if (data.daily_specials || data.ongoing) {
    const parts = [];
    if (data.daily_specials?.length)
      parts.push(
        "Daily specials:\n" +
          data.daily_specials.map((s) => `• ${s.title}: ${s.description} (${s.discount || ""})`).join("\n")
      );
    if (data.ongoing?.length)
      parts.push("Ongoing:\n" + data.ongoing.map((o) => `• ${o.title}: ${o.description}`).join("\n"));
    return parts.join("\n\n") || "No specials right now.";
  }
  if (data.monday || data.tuesday) {
    return Object.entries(data)
      .map(([day, hours]) => `${day}: ${hours}`)
      .join("\n");
  }
  return JSON.stringify(data, null, 2);
}

function Widget() {
  const [open, setOpen] = useState(false);
  const [justOpened, setJustOpened] = useState(false);
  const [activeTab, setActiveTab] = useState("chat");
  const [menu, setMenu] = useState([]);
  const [menuLoading, setMenuLoading] = useState(true);
  const [menuError, setMenuError] = useState(false);
  const [cart, setCart] = useState([]);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState([
    { role: "bot", text: "Hi! I'm DineBot. Ask about our menu, hours, or add items to your order.", key: "welcome" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastOrderNumber, setLastOrderNumber] = useState(null);
  const messagesEndRef = useRef(null);

  const apiBase = getApiBase();
  const sessionId = getSessionId();
  const restaurantId = getRestaurantId();
  const theme = getThemeFromUrl();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    loadMenu();
    loadCart();
  }, [restaurantId]);

  const loadMenu = async () => {
    setMenuLoading(true);
    setMenuError(false);
    try {
      const res = await axios.get(`${apiBase}/menu`, { params: { restaurant_id: restaurantId } });
      setMenu(res.data.items || []);
    } catch (e) {
      setMenuError(true);
      setMenu([]);
    } finally {
      setMenuLoading(false);
    }
  };

  const loadCart = async () => {
    try {
      const res = await axios.get(`${apiBase}/cart`, { params: { session_id: sessionId } });
      const data = res.data || [];
      const list = Array.isArray(data) ? data : [];
      setCart(list);
      setTotal(list.reduce((sum, item) => sum + item.price * item.quantity, 0));
    } catch (e) {
      setCart([]);
      setTotal(0);
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text, key: Date.now() + "u" }]);
    setLoading(true);
    try {
      const res = await axios.post(`${apiBase}/chat`, {
        session_id: sessionId,
        message: text,
        restaurant_id: restaurantId,
      });
      const data = res.data;
      let botText = data.response;
      if (typeof botText === "object") botText = formatBotResponse(botText);
      else botText = String(botText);
      setMessages((m) => [...m, { role: "bot", text: botText, key: Date.now() + "b" }]);
      if (data.cart) {
        const list = Array.isArray(data.cart) ? data.cart : [];
        setCart(list);
        setTotal(list.reduce((s, i) => s + i.price * i.quantity, 0));
      }
      const orderMatch = typeof botText === "string" && botText.match(/Order\s+([A-Z0-9_-]+)\s+placed/i);
      if (orderMatch) setLastOrderNumber(orderMatch[1]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "bot", text: "Something went wrong. Please try again.", key: Date.now() + "err" },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const addToCart = async (name) => {
    try {
      await axios.post(`${apiBase}/cart/add`, null, { params: { session_id: sessionId, name } });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  const updateItem = async (name, quantity) => {
    if (quantity <= 0) {
      try {
        await axios.post(`${apiBase}/cart/remove`, null, { params: { session_id: sessionId, name } });
      } catch (_) {}
      loadCart();
      return;
    }
    try {
      await axios.post(`${apiBase}/cart/update`, null, { params: { session_id: sessionId, name, quantity } });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  const removeItem = async (name) => {
    try {
      await axios.post(`${apiBase}/cart/remove`, null, { params: { session_id: sessionId, name } });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="dinebot-widget" style={{ "--dinebot-primary": theme.primaryColor }}>
      <button
        type="button"
        className={`dinebot-trigger ${justOpened ? "jiggle" : ""}`}
        onClick={() => {
          const next = !open;
          setOpen(next);
          if (next) {
            setJustOpened(true);
            setTimeout(() => setJustOpened(false), 500);
          }
        }}
        aria-label={open ? "Close chat" : "Open DineBot chat"}
      >
        <img
          src={LOGO_URL}
          alt="DineBot"
          className="dinebot-trigger-logo"
          onError={(e) => {
            e.target.style.display = "none";
            const fallback = e.target.nextElementSibling;
            if (fallback) fallback.classList.add("show");
          }}
        />
        <span className="dinebot-trigger-fallback">DineBot</span>
      </button>

      {open && (
        <div className="dinebot-panel">
          <div className="dinebot-panel-header">
            <img src={LOGO_URL} alt="" className="dinebot-panel-logo" />
            <span className="dinebot-panel-title">{theme.restaurantName}</span>
            <button type="button" className="dinebot-panel-close" onClick={() => setOpen(false)} aria-label="Close">
              ×
            </button>
          </div>

          <div className="dinebot-tabs">
            <button type="button" className={activeTab === "chat" ? "active" : ""} onClick={() => setActiveTab("chat")}>
              Chat
            </button>
            <button type="button" className={activeTab === "menu" ? "active" : ""} onClick={() => setActiveTab("menu")}>
              Menu
            </button>
            <button type="button" className={activeTab === "cart" ? "active" : ""} onClick={() => setActiveTab("cart")}>
              Cart {cart.length > 0 ? `(${cart.length})` : ""}
            </button>
          </div>

          <div className="dinebot-panel-body">
            {activeTab === "chat" && (
              <>
                {lastOrderNumber && (
                  <div className="dinebot-order-confirmed">
                    Order {lastOrderNumber} confirmed! Track with &quot;order status {lastOrderNumber}&quot;
                  </div>
                )}
                <div className="dinebot-messages">
                  {messages.map((msg) => (
                    <div key={msg.key} className={`dinebot-msg dinebot-msg--${msg.role}`}>
                      <div className="dinebot-msg-bubble">
                        {msg.text.split("\n").map((line, i) => (
                          <p key={i}>{line || "\u00A0"}</p>
                        ))}
                      </div>
                    </div>
                  ))}
                  {loading && (
                    <div className="dinebot-msg dinebot-msg--bot">
                      <div className="dinebot-msg-bubble typing">
                        <span></span><span></span><span></span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
                <div className="dinebot-quick-prompts">
                  {QUICK_PROMPTS.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      className="dinebot-quick-chip"
                      onClick={() => setInput(prompt)}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
                <div className="dinebot-input-wrap">
                  <input
                    type="text"
                    className="dinebot-input"
                    placeholder="Ask or add items..."
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                  />
                  <button type="button" className="dinebot-send" onClick={sendMessage} disabled={loading}>
                    Send
                  </button>
                </div>
              </>
            )}

            {activeTab === "menu" && (
              <div className="dinebot-menu-list">
                {menuLoading && <p className="dinebot-loading">Loading menu…</p>}
                {menuError && <p className="dinebot-error">Couldn't load menu.</p>}
                {!menuLoading && !menuError && menu.map((item) => (
                  <div key={item.name} className="dinebot-menu-item">
                    <div>
                      <strong>{item.name}</strong> — ${item.price}
                      {item.description && <p className="dinebot-menu-desc">{item.description}</p>}
                    </div>
                    <button type="button" className="dinebot-btn-add" onClick={() => addToCart(item.name)}>
                      Add
                    </button>
                  </div>
                ))}
              </div>
            )}

            {activeTab === "cart" && (
              <div className="dinebot-cart">
                {cart.length === 0 ? (
                  <p className="dinebot-empty">Your cart is empty. Use Chat or Menu to add items.</p>
                ) : (
                  <>
                    <ul className="dinebot-cart-list">
                      {cart.map((item) => (
                        <li key={item.name} className="dinebot-cart-item">
                          <span>{item.name} × {item.quantity}</span>
                          <div>
                            <button type="button" className="dinebot-btn-icon" onClick={() => updateItem(item.name, item.quantity - 1)}>−</button>
                            <span className="dinebot-qty">{item.quantity}</span>
                            <button type="button" className="dinebot-btn-icon" onClick={() => updateItem(item.name, item.quantity + 1)}>+</button>
                            <button type="button" className="dinebot-btn-icon remove" onClick={() => removeItem(item.name)}>×</button>
                          </div>
                        </li>
                      ))}
                    </ul>
                    <p className="dinebot-total">Total: ${total.toFixed(2)}</p>
                    <a href="https://fake-payment-link.com" target="_blank" rel="noopener noreferrer" className="dinebot-checkout">
                      Checkout
                    </a>
                  </>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default Widget;
