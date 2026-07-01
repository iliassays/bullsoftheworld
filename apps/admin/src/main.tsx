import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import { App } from "./App";

// The cockpit is a single-page ops console — no router, no i18n, no consumer chrome.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
