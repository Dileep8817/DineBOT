import { useCallback, useEffect, useRef, useState } from "react";
import { apiUrl } from "./apiConfig";
import "./StaffDashboard.css";

const STAFF_KEY_STORAGE = "dinebot_staff_key";
const BOARD_COLUMNS = [
  { status: "pending", label: "New" },
  { status: "preparing", label: "Preparing" },
  { status: "ready", label: "Ready" },
];
const CLOSED_STATUSES = ["completed", "cancelled"];
const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 15000;

function readRestaurantId() {
  const fromUrl = new URLSearchParams(window.location.search).get("restaurant_id");
  if (fromUrl?.trim()) return fromUrl.trim();
  const fromEnv = process.env.REACT_APP_DEFAULT_RESTAURANT_ID;
  return fromEnv?.trim() || "";
}

/** The staff key is a header, never a query param, so it stays out of URLs and logs. */
function staffFetch(path, key, options = {}) {
  return fetch(apiUrl(path), {
    ...options,
    headers: { ...(options.headers || {}), "X-Staff-Key": key },
  });
}

async function errorMessage(response, fallback) {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message) return detail.message;
  } catch (e) {
    // no JSON body; fall through
  }
  return `${fallback} (${response.status})`;
}

function money(value) {
  return `$${Number(value || 0).toFixed(2)}`;
}

function timeOfDay(value) {
  const date = new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function parseFrame(frame) {
  let event = "message";
  const data = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith(":")) continue; // heartbeat comment
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trim());
  }
  if (!data.length) return null;
  try {
    return { event, payload: JSON.parse(data.join("\n")) };
  } catch (e) {
    return null;
  }
}

function OrderCard({ order, busy, onAdvance, onCancel }) {
  const canCancel = order.status === "pending" || order.status === "preparing";
  return (
    <article className="staff-card">
      <header className="staff-card-head">
        <span className="staff-card-number">{order.order_number}</span>
        <span className="staff-card-time">{timeOfDay(order.created_at)}</span>
      </header>
      <ul className="staff-card-items">
        {order.items?.map((item, i) => (
          <li key={`${item.name}-${i}`}>
            <span className="staff-qty">{item.quantity}×</span> {item.name}
          </li>
        ))}
      </ul>
      <footer className="staff-card-foot">
        <div className="staff-card-meta">
          <span className="staff-total">{money(order.total)}</span>
          <span
            className={`staff-pay staff-pay--${order.payment_status}`}
            title={`Payment: ${order.payment_status}`}
          >
            {order.payment_status}
          </span>
        </div>
        <div className="staff-card-actions">
          {canCancel && (
            <button
              type="button"
              className="staff-btn staff-btn--ghost"
              disabled={busy}
              onClick={() => onCancel(order)}
            >
              Cancel
            </button>
          )}
          {order.next_status && (
            <button
              type="button"
              className="staff-btn"
              disabled={busy}
              onClick={() => onAdvance(order)}
            >
              {order.next_status === "preparing" && "Start preparing"}
              {order.next_status === "ready" && "Mark ready"}
              {order.next_status === "completed" && "Complete"}
            </button>
          )}
        </div>
      </footer>
    </article>
  );
}

export default function StaffDashboard() {
  const [restaurantId, setRestaurantId] = useState(readRestaurantId);
  const [staffKey, setStaffKey] = useState(
    () => sessionStorage.getItem(STAFF_KEY_STORAGE) || ""
  );
  const [authorized, setAuthorized] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [restaurantInput, setRestaurantInput] = useState(readRestaurantId);
  const [signInError, setSignInError] = useState("");
  const [orders, setOrders] = useState({});
  const [closed, setClosed] = useState([]);
  const [connection, setConnection] = useState("connecting");
  const [error, setError] = useState("");
  const [busyOrder, setBusyOrder] = useState(null);
  const abortRef = useRef(null);

  const signOut = useCallback(() => {
    sessionStorage.removeItem(STAFF_KEY_STORAGE);
    abortRef.current?.abort();
    setStaffKey("");
    setAuthorized(false);
    setOrders({});
    setClosed([]);
    setConnection("connecting");
  }, []);

  const mergeOrder = useCallback((order) => {
    if (CLOSED_STATUSES.includes(order.status)) {
      setOrders((prev) => {
        const next = { ...prev };
        delete next[order.order_number];
        return next;
      });
      setClosed((prev) => [
        order,
        ...prev.filter((o) => o.order_number !== order.order_number),
      ].slice(0, 8));
      return;
    }
    setClosed((prev) => prev.filter((o) => o.order_number !== order.order_number));
    setOrders((prev) => ({ ...prev, [order.order_number]: order }));
  }, []);

  // Verify the key before showing the board, so a wrong key reports itself
  // instead of looking like an empty restaurant.
  const signIn = async (event) => {
    event.preventDefault();
    const key = keyInput.trim();
    const rid = restaurantInput.trim();
    if (!key || !rid) {
      setSignInError("Staff key and restaurant id are both required.");
      return;
    }
    setSignInError("");
    try {
      const res = await staffFetch("/staff/session", key);
      if (!res.ok) {
        setSignInError(await errorMessage(res, "Could not sign in"));
        return;
      }
      sessionStorage.setItem(STAFF_KEY_STORAGE, key);
      setStaffKey(key);
      setRestaurantId(rid);
      setKeyInput("");
      setAuthorized(true);
    } catch (e) {
      setSignInError("Could not reach the API. Is the backend running?");
    }
  };

  useEffect(() => {
    if (!staffKey || authorized) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await staffFetch("/staff/session", staffKey);
        if (cancelled) return;
        if (res.ok) setAuthorized(true);
        else signOut();
      } catch (e) {
        if (!cancelled) setConnection("offline");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [staffKey, authorized, signOut]);

  useEffect(() => {
    if (!authorized || !staffKey || !restaurantId) return undefined;

    let stopped = false;
    let retryDelay = RECONNECT_MIN_MS;
    let retryTimer = null;

    const connect = async () => {
      const controller = new AbortController();
      abortRef.current = controller;
      setConnection("connecting");
      try {
        const res = await staffFetch(
          `/staff/stream?restaurant_id=${encodeURIComponent(restaurantId)}`,
          staffKey,
          { signal: controller.signal, headers: { Accept: "text/event-stream" } }
        );
        if (!res.ok || !res.body) {
          setError(await errorMessage(res, "Live updates unavailable"));
          throw new Error("stream rejected");
        }
        setConnection("live");
        setError("");
        retryDelay = RECONNECT_MIN_MS;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!stopped) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let split;
          while ((split = buffer.indexOf("\n\n")) >= 0) {
            const parsed = parseFrame(buffer.slice(0, split));
            buffer = buffer.slice(split + 2);
            if (!parsed) continue;
            if (parsed.event === "snapshot") {
              const next = {};
              for (const order of parsed.payload.orders || []) {
                next[order.order_number] = order;
              }
              setOrders(next);
            } else if (parsed.event === "order") {
              mergeOrder(parsed.payload);
            } else if (parsed.event === "error") {
              setError(parsed.payload.detail || "Live updates interrupted");
            }
          }
        }
      } catch (e) {
        if (controller.signal.aborted || stopped) return;
      }
      if (stopped) return;
      // The stream ends when the server restarts or a proxy times out; retry with
      // backoff rather than leaving a silently stale board on the wall.
      setConnection("reconnecting");
      retryTimer = setTimeout(connect, retryDelay);
      retryDelay = Math.min(retryDelay * 2, RECONNECT_MAX_MS);
    };

    connect();
    return () => {
      stopped = true;
      if (retryTimer) clearTimeout(retryTimer);
      abortRef.current?.abort();
    };
  }, [authorized, staffKey, restaurantId, mergeOrder]);

  const changeStatus = async (order, status) => {
    setBusyOrder(order.order_number);
    setError("");
    try {
      const res = await staffFetch(
        `/staff/orders/${encodeURIComponent(order.order_number)}/status` +
          `?restaurant_id=${encodeURIComponent(restaurantId)}&status=${status}`,
        staffKey,
        { method: "PATCH" }
      );
      if (!res.ok) {
        setError(await errorMessage(res, "Could not update the order"));
        return;
      }
      mergeOrder(await res.json());
    } catch (e) {
      setError("Could not reach the API.");
    } finally {
      setBusyOrder(null);
    }
  };

  if (!authorized) {
    return (
      <div className="staff staff--signin">
        <form className="staff-signin-card" onSubmit={signIn}>
          <h1>Kitchen dashboard</h1>
          <p className="staff-signin-lead">
            Staff access uses its own key, separate from the ordering app's API key.
          </p>
          <label htmlFor="staff-restaurant">Restaurant id</label>
          <input
            id="staff-restaurant"
            value={restaurantInput}
            onChange={(e) => setRestaurantInput(e.target.value)}
            placeholder="restaurant_1"
            autoComplete="off"
          />
          <label htmlFor="staff-key">Staff key</label>
          <input
            id="staff-key"
            type="password"
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            placeholder="STAFF_API_KEY"
            autoComplete="current-password"
          />
          {signInError && <p className="staff-signin-error">{signInError}</p>}
          <button type="submit" className="staff-btn staff-btn--wide">
            Open the board
          </button>
        </form>
      </div>
    );
  }

  const byStatus = (status) =>
    Object.values(orders)
      .filter((o) => o.status === status)
      .sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));

  return (
    <div className="staff">
      <header className="staff-header">
        <div>
          <h1>Kitchen dashboard</h1>
          <p className="staff-sub">{restaurantId}</p>
        </div>
        <div className="staff-header-right">
          <span className={`staff-status staff-status--${connection}`}>
            {connection === "live" ? "Live" : connection}
          </span>
          <button type="button" className="staff-btn staff-btn--ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>

      {error && <p className="staff-error">{error}</p>}

      <div className="staff-board">
        {BOARD_COLUMNS.map((column) => {
          const columnOrders = byStatus(column.status);
          return (
            <section key={column.status} className="staff-column">
              <h2>
                {column.label}
                <span className="staff-count">{columnOrders.length}</span>
              </h2>
              {columnOrders.length === 0 && (
                <p className="staff-empty">Nothing here.</p>
              )}
              {columnOrders.map((order) => (
                <OrderCard
                  key={order.order_number}
                  order={order}
                  busy={busyOrder === order.order_number}
                  onAdvance={(o) => changeStatus(o, o.next_status)}
                  onCancel={(o) => changeStatus(o, "cancelled")}
                />
              ))}
            </section>
          );
        })}
      </div>

      {closed.length > 0 && (
        <section className="staff-closed">
          <h2>Just closed</h2>
          <ul>
            {closed.map((order) => (
              <li key={order.order_number}>
                <strong>{order.order_number}</strong> {order.status} ·{" "}
                {money(order.total)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
