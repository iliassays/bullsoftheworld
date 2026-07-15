import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { ResearchApp } from "./app/ResearchApp";
import { ResearchErrorBoundary } from "./app/ResearchErrorBoundary";
import { AppProviders } from "./app/providers";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <AppProviders>
        <ResearchErrorBoundary>
          <ResearchApp />
        </ResearchErrorBoundary>
      </AppProviders>
    </BrowserRouter>
  </React.StrictMode>,
);
