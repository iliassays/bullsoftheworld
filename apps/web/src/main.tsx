import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import { App } from "./App";
import { EuConsentGate } from "./components/EuConsentGate";
import { SeoProvider } from "./components/Seo";
import { AuthProvider } from "./lib/auth";
import { LanguageProvider } from "./lib/i18n";
import { TenantConfigProvider } from "./lib/tenant";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <LanguageProvider>
        <TenantConfigProvider>
          <SeoProvider>
            <AuthProvider>
              <App />
              <EuConsentGate />
            </AuthProvider>
          </SeoProvider>
        </TenantConfigProvider>
      </LanguageProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
