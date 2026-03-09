import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import Widget from "./Widget";
import reportWebVitals from "./reportWebVitals";

function Root() {
  const isWidget =
    window.location.pathname === "/widget" ||
    new URLSearchParams(window.location.search).get("embed") === "1";
  return <React.StrictMode>{isWidget ? <Widget /> : <App />}</React.StrictMode>;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<Root />);

reportWebVitals();
