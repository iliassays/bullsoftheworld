import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import { App } from "./App";
import { SeoProvider } from "./components/Seo";
import { AuthProvider } from "./lib/auth";
import { LanguageProvider } from "./lib/i18n";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <LanguageProvider>
        <SeoProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </SeoProvider>
      </LanguageProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
