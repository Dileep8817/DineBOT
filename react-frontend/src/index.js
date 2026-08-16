import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import App from "./App";
import Widget from "./Widget";
import StaffDashboard from "./StaffDashboard";
import reportWebVitals from "./reportWebVitals";

/**
 * Three views, chosen from the path (no router dependency):
 *   /staff            kitchen dashboard (staff key)
 *   /widget, ?embed=1 embeddable customer widget
 *   everything else   customer ordering app
 */
function Root() {
  const path = window.location.pathname;
  const params = new URLSearchParams(window.location.search);

  let view = <App />;
  if (path === "/staff" || path === "/staff/") {
    view = <StaffDashboard />;
  } else if (path === "/widget" || params.get("embed") === "1") {
    view = <Widget />;
  }

  return <React.StrictMode>{view}</React.StrictMode>;
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<Root />);

reportWebVitals();
