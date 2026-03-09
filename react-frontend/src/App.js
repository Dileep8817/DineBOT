import { useEffect, useState, useRef } from "react";
import axios from "axios";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";
const SESSION_ID = "session_" + Math.random().toString(36).slice(2, 9);

function formatBotResponse(data) {
  if (typeof data === "string") return data;
  if (!data || typeof data !== "object") return String(data);
  if (data.items && Array.isArray(data.items)) {
    if (data.items.length === 0) return "No items found.";
    return data.items
      .map(
        (i) =>
          `• ${i.name} — $${i.price}${i.description ? ": " + i.description : ""}`
      )
      .join("\n");
  }
  if (data.daily_specials || data.ongoing) {
    const parts = [];
    if (data.daily_specials?.length)
      parts.push(
        "Daily specials:\n" +
          data.daily_specials
            .map(
              (s) =>
                `• ${s.title}: ${s.description} (${s.discount || ""})`
            )
            .join("\n")
      );
    if (data.ongoing?.length)
      parts.push(
        "Ongoing:\n" +
          data.ongoing.map((o) => `• ${o.title}: ${o.description}`).join("\n")
      );
    return parts.join("\n\n") || "No specials right now.";
  }
  if (data.monday || data.tuesday) {
    return Object.entries(data)
      .map(([day, hours]) => `${day}: ${hours}`)
      .join("\n");
  }
  return JSON.stringify(data, null, 2);
}

function App() {
  const [menu, setMenu] = useState([]);
  const [menuLoading, setMenuLoading] = useState(true);
  const [menuError, setMenuError] = useState(false);
  const [cart, setCart] = useState([]);
  const [total, setTotal] = useState(0);
  const [messages, setMessages] = useState([
    {
      role: "bot",
      text: "Hi! I can help you with our menu, hours, address, specials, dietary options, or take your order. Just ask!",
      key: "welcome",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeSection, setActiveSection] = useState("chat");
  const messagesEndRef = useRef(null);
  const chatContainerRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    loadMenu();
    loadCart();
  }, []);

  const loadMenu = async () => {
    setMenuLoading(true);
    setMenuError(false);
    try {
      const res = await axios.get(`${API_BASE}/menu`);
      setMenu(res.data.items || []);
    } catch (e) {
      console.error(e);
      setMenuError(true);
      setMenu([]);
    } finally {
      setMenuLoading(false);
    }
  };

  const loadCart = async () => {
    try {
      const res = await axios.get(`${API_BASE}/cart`, {
        params: { session_id: SESSION_ID },
      });
      const data = res.data || [];
      setCart(Array.isArray(data) ? data : []);
      const list = Array.isArray(data) ? data : [];
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
      const res = await axios.post(`${API_BASE}/chat`, {
        session_id: SESSION_ID,
        message: text,
      });
      const data = res.data;
      let botText = data.response;
      if (typeof botText === "object") {
        botText = formatBotResponse(botText);
      } else {
        botText = String(botText);
      }
      setMessages((m) => [
        ...m,
        { role: "bot", text: botText, key: Date.now() + "b" },
      ]);
      if (data.cart) {
        setCart(Array.isArray(data.cart) ? data.cart : []);
        setTotal(
          (Array.isArray(data.cart) ? data.cart : []).reduce(
            (sum, item) => sum + item.price * item.quantity,
            0
          )
        );
      }
    } catch (e) {
      const hint = e.response
        ? ` (${e.response.status})`
        : ". Is the backend running? Start it with: uvicorn main:app --reload";
      setMessages((m) => [
        ...m,
        {
          role: "bot",
          text: `Something went wrong${hint}. Make sure the API is running at ${API_BASE}.`,
          key: Date.now() + "err",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const addToCart = async (name) => {
    try {
      await axios.post(`${API_BASE}/cart/add`, null, {
        params: { session_id: SESSION_ID, name },
      });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  const updateItem = async (name, quantity) => {
    if (quantity <= 0) {
      removeItem(name);
      return;
    }
    try {
      await axios.post(`${API_BASE}/cart/update`, null, {
        params: { session_id: SESSION_ID, name, quantity },
      });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  const removeItem = async (name) => {
    try {
      await axios.post(`${API_BASE}/cart/remove`, null, {
        params: { session_id: SESSION_ID, name },
      });
      loadCart();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1 className="brand">Dileep's Pizzeria</h1>
        <p className="tagline">Chat, browse, and order — all in one place</p>
        <nav className="nav">
          <button
            className={activeSection === "chat" ? "active" : ""}
            onClick={() => setActiveSection("chat")}
          >
            Chat
          </button>
          <button
            className={activeSection === "menu" ? "active" : ""}
            onClick={() => setActiveSection("menu")}
          >
            Menu
          </button>
          <button
            className={activeSection === "cart" ? "active" : ""}
            onClick={() => setActiveSection("cart")}
          >
            Cart {cart.length > 0 && `(${cart.length})`}
          </button>
        </nav>
      </header>

      <main className="main">
        <section
          className={`panel chat-panel ${activeSection === "chat" ? "active" : ""}`}
          ref={chatContainerRef}
        >
          <div className="messages">
            {messages.map((msg) => (
              <div
                key={msg.key}
                className={`message message--${msg.role} animate-message`}
              >
                <div className="message-bubble">
                  {msg.text.split("\n").map((line, i) => (
                    <p key={i}>{line || "\u00A0"}</p>
                  ))}
                </div>
              </div>
            ))}
            {loading && (
              <div className="message message--bot animate-message">
                <div className="message-bubble typing">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="chat-input-wrap">
            <input
              type="text"
              className="chat-input"
              placeholder="Ask about menu, hours, specials, or add items to cart..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
            />
            <button
              type="button"
              className="chat-send"
              onClick={sendMessage}
              disabled={loading}
              aria-label="Send"
            >
              Send
            </button>
          </div>
        </section>

        <section
          className={`panel menu-panel ${activeSection === "menu" ? "active" : ""}`}
        >
          <h2 className="panel-title">Menu</h2>
          {menuLoading && (
            <p className="panel-message">Loading menu…</p>
          )}
          {!menuLoading && menuError && (
            <p className="panel-message panel-error">
              Couldn’t load menu. Is the backend running? Try: <code>uvicorn main:app --reload</code> in the project folder.
            </p>
          )}
          {!menuLoading && !menuError && menu.length === 0 && (
            <p className="panel-message">No menu items.</p>
          )}
          <div className="menu-grid">
            {menu.map((item, i) => (
              <article
                key={item.name}
                className="menu-card animate-card"
                style={{ animationDelay: `${i * 0.06}s` }}
              >
                <div className="menu-card-inner">
                  <h3 className="menu-card-name">{item.name}</h3>
                  <p className="menu-card-desc">{item.description}</p>
                  {item.dietary?.length > 0 && (
                    <div className="menu-card-tags">
                      {item.dietary.map((d) => (
                        <span key={d} className="tag">{d}</span>
                      ))}
                    </div>
                  )}
                  <div className="menu-card-footer">
                    <span className="menu-card-price">${item.price}</span>
                    <button
                      type="button"
                      className="btn btn-add"
                      onClick={() => addToCart(item.name)}
                    >
                      Add to cart
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section
          className={`panel cart-panel ${activeSection === "cart" ? "active" : ""}`}
        >
          <h2 className="panel-title">Your order</h2>
          {cart.length === 0 ? (
            <p className="cart-empty">
              Your cart is empty. Ask in chat (e.g. “add margherita pizza to cart”) or add something from the Menu tab!
            </p>
          ) : (
            <div className="cart-list">
              {cart.map((item) => (
                <div key={item.name} className="cart-item animate-cart-item">
                  <div className="cart-item-info">
                    <strong>{item.name}</strong>
                    <span>${item.price} × {item.quantity}</span>
                  </div>
                  <div className="cart-item-actions">
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => updateItem(item.name, item.quantity - 1)}
                      aria-label="Decrease"
                    >
                      −
                    </button>
                    <span className="cart-qty">{item.quantity}</span>
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => updateItem(item.name, item.quantity + 1)}
                      aria-label="Increase"
                    >
                      +
                    </button>
                    <button
                      type="button"
                      className="btn-icon btn-remove"
                      onClick={() => removeItem(item.name)}
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {cart.length > 0 && (
            <div className="cart-footer">
              <p className="cart-total">Total: ${total.toFixed(2)}</p>
              <a
                href="https://fake-payment-link.com"
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-checkout"
              >
                Checkout
              </a>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

export default App;
