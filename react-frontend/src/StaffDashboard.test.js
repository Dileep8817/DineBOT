import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import StaffDashboard from "./StaffDashboard";

// jsdom provides neither, and the stream reader needs both.
global.TextDecoder = TextDecoder;
global.TextEncoder = TextEncoder;

const ORDER = {
  order_id: 1,
  order_number: "RESTAURANT_1-0001",
  status: "pending",
  payment_status: "unpaid",
  total: 32.5,
  created_at: "2026-08-15 17:00:00-07:00",
  updated_at: "2026-08-15 17:00:00-07:00",
  items: [{ name: "Cheese Pizza", price: 13.0, quantity: 2 }],
  next_status: "preparing",
};

/** A response body that yields SSE frames, the way /staff/stream does. */
function streamOf(frames) {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    getReader: () => ({
      read: () =>
        i < frames.length
          ? Promise.resolve({ value: encoder.encode(frames[i++]), done: false })
          : new Promise(() => {}), // stay open instead of triggering a reconnect
    }),
  };
}

function mockApi({ frames = [], onPatch } = {}) {
  return jest.fn((url, options = {}) => {
    const path = String(url);
    if (path.includes("/staff/session")) {
      const key = options.headers?.["X-Staff-Key"];
      return Promise.resolve(
        key === "good-key"
          ? { ok: true, json: async () => ({ restaurant_scope: "any" }) }
          : { ok: false, status: 401, json: async () => ({ detail: "Invalid or missing staff key" }) }
      );
    }
    if (path.includes("/staff/stream")) {
      return Promise.resolve({ ok: true, body: streamOf(frames) });
    }
    if (options.method === "PATCH") {
      return Promise.resolve({ ok: true, json: async () => onPatch(path) });
    }
    throw new Error(`unexpected request: ${path}`);
  });
}

function signIn(key = "good-key") {
  fireEvent.change(screen.getByLabelText(/restaurant id/i), {
    target: { value: "restaurant_1" },
  });
  fireEvent.change(screen.getByLabelText(/staff key/i), { target: { value: key } });
  fireEvent.click(screen.getByRole("button", { name: /open the board/i }));
}

beforeEach(() => {
  sessionStorage.clear();
  window.history.pushState({}, "", "/staff");
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("asks for a staff key before showing any orders", () => {
  global.fetch = mockApi();
  render(<StaffDashboard />);

  expect(screen.getByLabelText(/staff key/i)).toBeInTheDocument();
  expect(screen.queryByText(/RESTAURANT_1/)).not.toBeInTheDocument();
});

test("reports a rejected key instead of an empty board", async () => {
  global.fetch = mockApi();
  render(<StaffDashboard />);

  signIn("wrong-key");

  expect(await screen.findByText(/invalid or missing staff key/i)).toBeInTheDocument();
});

test("renders the snapshot and then a streamed status change", async () => {
  global.fetch = mockApi({
    frames: [
      `event: snapshot\ndata: ${JSON.stringify({
        restaurant_id: "restaurant_1",
        orders: [ORDER],
      })}\n\n`,
      ": heartbeat\n\n",
      `event: order\ndata: ${JSON.stringify({
        ...ORDER,
        status: "ready",
        next_status: "completed",
      })}\n\n`,
    ],
  });
  render(<StaffDashboard />);
  signIn();

  expect(await screen.findByText("RESTAURANT_1-0001")).toBeInTheDocument();
  expect(screen.getByText(/Cheese Pizza/)).toBeInTheDocument();
  expect(screen.getByText("$32.50")).toBeInTheDocument();
  expect(await screen.findByText("Live")).toBeInTheDocument();

  // The streamed update moves the card to Ready, so its action becomes Complete.
  expect(await screen.findByRole("button", { name: /complete/i })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /start preparing/i })).not.toBeInTheDocument();
});

test("advancing an order PATCHes the staff route and re-renders it", async () => {
  const patched = [];
  global.fetch = mockApi({
    frames: [
      `event: snapshot\ndata: ${JSON.stringify({
        restaurant_id: "restaurant_1",
        orders: [ORDER],
      })}\n\n`,
    ],
    onPatch: (path) => {
      patched.push(path);
      return { ...ORDER, status: "preparing", next_status: "ready" };
    },
  });
  render(<StaffDashboard />);
  signIn();

  fireEvent.click(await screen.findByRole("button", { name: /start preparing/i }));

  await waitFor(() => expect(patched).toHaveLength(1));
  expect(patched[0]).toContain("/staff/orders/RESTAURANT_1-0001/status");
  expect(patched[0]).toContain("status=preparing");
  expect(await screen.findByRole("button", { name: /mark ready/i })).toBeInTheDocument();
});

test("a completed order leaves the board", async () => {
  global.fetch = mockApi({
    frames: [
      `event: snapshot\ndata: ${JSON.stringify({
        restaurant_id: "restaurant_1",
        orders: [ORDER],
      })}\n\n`,
      `event: order\ndata: ${JSON.stringify({
        ...ORDER,
        status: "completed",
        next_status: null,
      })}\n\n`,
    ],
  });
  render(<StaffDashboard />);
  signIn();

  expect(await screen.findByText(/just closed/i)).toBeInTheDocument();
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: /start preparing/i })).not.toBeInTheDocument()
  );
});

test("sends the staff key as a header, never in the URL", async () => {
  const fetchMock = mockApi({ frames: [] });
  global.fetch = fetchMock;
  render(<StaffDashboard />);
  signIn();

  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  for (const [url, options] of fetchMock.mock.calls) {
    expect(String(url)).not.toContain("good-key");
    expect(options.headers["X-Staff-Key"]).toBe("good-key");
  }
});
