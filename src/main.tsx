import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { logError } from "./lib/logger";
import "./index.css";

// Capture anything that escapes React (event handlers, async callbacks, the
// error boundary's own rethrow) and forward it to the shell log.
window.addEventListener("error", (e) => {
  logError("uncaught error", e.error ?? e.message, {
    source: `${e.filename}:${e.lineno}:${e.colno}`,
  });
});
window.addEventListener("unhandledrejection", (e) => {
  logError("unhandled promise rejection", e.reason);
});

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
