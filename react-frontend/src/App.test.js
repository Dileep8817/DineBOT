import { render, screen, waitFor } from "@testing-library/react";
import axios from "axios";
import App from "./App";

jest.mock("axios");

beforeEach(() => {
  jest.clearAllMocks();
  axios.get.mockResolvedValue({ data: { items: [] } });
});

test("says no restaurant is selected instead of calling the API without one", async () => {
  window.history.pushState({}, "", "/");

  render(<App />);

  expect(screen.getByText(/no restaurant selected/i)).toBeInTheDocument();
  expect(screen.getByText(/\?restaurant_id=restaurant_1/)).toBeInTheDocument();
  await waitFor(() => expect(axios.get).not.toHaveBeenCalled());
});

test("loads the menu for the restaurant in the URL", async () => {
  window.history.pushState({}, "", "/?restaurant_id=restaurant_1");
  axios.get.mockImplementation((url) =>
    url.includes("/menu")
      ? Promise.resolve({
          data: { items: [{ name: "Cheese Pizza", price: 13, category: "Mains" }] },
        })
      : Promise.resolve({ data: [] })
  );

  render(<App />);

  expect(await screen.findByText("Cheese Pizza")).toBeInTheDocument();
  const menuCall = axios.get.mock.calls.find(([url]) => url.includes("/menu"));
  expect(menuCall[1].params.restaurant_id).toBe("restaurant_1");
});
