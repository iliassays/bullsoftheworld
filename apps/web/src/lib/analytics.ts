import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

// GA4 SPA tracking. gtag.js + its config live in index.html (their sha256 is pinned in the CSP, so
// they must not be edited here). GA4's auto page_view only fires on the initial hard load; this
// hook fires page_view on every subsequent client route change, and a `view_stock` event on stock
// pages so "most-viewed tickers" is a clean report in Analytics.
//
// Because URLs are now language-prefixed (/bn/s/GP), page_path already carries language + ticker,
// so the Pages report shows per-ticker counts directly; `view_stock` + the `stock_code` custom
// dimension (register it in the GA4 UI) gives the same, aggregated cleanly across bn/en.

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
  }
}

function ga(...args: unknown[]) {
  // gtag is defined synchronously inline (queues into dataLayer) even before gtag.js finishes.
  if (typeof window !== "undefined" && typeof window.gtag === "function") window.gtag(...args);
}

// /{bn|en}/s/{CODE} → CODE (uppercased); null for any other route.
function stockCodeFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/(?:bn|en)\/s\/([^/]+)/);
  return m ? decodeURIComponent(m[1]).toUpperCase() : null;
}

export function usePageViewTracking() {
  const loc = useLocation();
  const first = useRef(true);
  useEffect(() => {
    const path = loc.pathname + loc.search;
    const skipPageView = first.current; // GA4 config already auto-sent the first page_view
    first.current = false;
    const code = stockCodeFromPath(loc.pathname);
    // Defer a tick: the <Seo> head effect runs AFTER this one (it's higher in the tree, so its
    // passive effect fires later), so document.title is stale until the next task. Sending on a
    // 0ms timeout lets the title settle before it's read.
    const id = window.setTimeout(() => {
      if (!skipPageView) {
        ga("event", "page_view", {
          page_path: path,
          page_location: window.location.href,
          page_title: document.title,
        });
      }
      // A dedicated stock-view event fires on EVERY stock page (incl. the first), so the
      // most-viewed-tickers report is complete regardless of the page_view skip above.
      if (code) ga("event", "view_stock", { stock_code: code });
    }, 0);
    return () => window.clearTimeout(id);
  }, [loc.pathname, loc.search]);
}
