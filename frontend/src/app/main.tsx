import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App.tsx";
// Order matters: each layer may override the previous one (ADR-0005). The import
// lives in ONE file so the order is a list a reader can check, not a property of
// whichever component happened to be imported first.
import "./styles/index.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root element not found");
}

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);