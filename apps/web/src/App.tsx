import { useEffect, type ReactNode } from "react";
import { Navigate, Outlet, Route, Routes, useLocation, useParams } from "react-router-dom";
import { About } from "./pages/About";
import { Beta } from "./pages/Beta";
import { Shell } from "./components/Shell";
import { Alerts } from "./pages/Alerts";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/AuthFlows";
import { Cockpit } from "./pages/Cockpit";
import { DeskProfile } from "./pages/DeskProfile";
import { Feed } from "./pages/Feed";
import { Markets } from "./pages/Markets";
import { Institutions } from "./pages/Institutions";
import { Privacy, Terms } from "./pages/Policies";
import { PatternDetail } from "./pages/PatternDetail";
import { PatternLibrary } from "./pages/PatternLibrary";
import { Portfolio } from "./pages/Portfolio";
import { Scanner } from "./pages/Scanner";
import { Profile } from "./pages/Profile";
import { ScreenExplore } from "./pages/ScreenExplore";
import { SymbolPage } from "./pages/Symbol";
import { UserProfile } from "./pages/UserProfile";
import { Watchlist } from "./pages/Watchlist";
import { Trust } from "./pages/Trust";
import { Welcome } from "./pages/Welcome";
import { type Lang, SUPPORTED, currentLang, useLang } from "./lib/i18n";
import { invalidLocaleRedirectTarget } from "./lib/locale-route";
import { useTenantConfig } from "./lib/tenant";

// Language layout: every canonical URL is prefixed with /bn or /en (for SEO + hreflang). This
// validates the segment, drives the i18n state from the URL, and bounces any unprefixed/legacy
// path to the language-prefixed equivalent. `currentLang()` reads the path directly, so API
// requests already carry the right locale regardless of when this effect runs.
function LangLayout() {
  const { lang } = useParams();
  const { setLang } = useLang();
  const { config } = useTenantConfig();
  const loc = useLocation();
  const valid =
    !!lang &&
    SUPPORTED.includes(lang as Lang) &&
    config.supported_locales.includes(lang);
  useEffect(() => {
    if (valid) setLang(lang as Lang);
  }, [valid, lang, setLang]);
  if (!valid) {
    return (
      <Navigate
        to={invalidLocaleRedirectTarget(
          loc.pathname,
          loc.search,
          lang,
          config.default_locale,
          SUPPORTED,
        )}
        replace
      />
    );
  }
  return <Outlet />;
}

// Locale-preserving redirect for the legacy in-app aliases (kept from the 2026-07 nav redesign).
function LocaleRedirect({ to }: { to: string }) {
  const { lang } = useParams();
  const pref = SUPPORTED.includes(lang as Lang) ? (lang as Lang) : currentLang();
  return <Navigate to={`/${pref}${to}`} replace />;
}

// Bare root and any other unprefixed path → prefixed equivalent (default/stored/URL language).
function RootRedirect() {
  const loc = useLocation();
  const { config } = useTenantConfig();
  const rest = loc.pathname === "/" ? "" : loc.pathname;
  const stored = currentLang();
  const lang = config.supported_locales.includes(stored) ? stored : config.default_locale;
  return <Navigate to={`/${lang}${rest}${loc.search}`} replace />;
}

function CapabilityRoute({ feature, children }: { feature: string; children: ReactNode }) {
  const { config } = useTenantConfig();
  const { lang } = useParams();
  return config.features[feature] ? <>{children}</> : <Navigate to={`/${lang ?? currentLang()}`} replace />;
}

function ResearchBetaRoute({ children }: { children: ReactNode }) {
  const { config } = useTenantConfig();
  const { lang } = useParams();
  return config.research_beta ? <>{children}</> : <Navigate to={`/${lang ?? currentLang()}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path=":lang" element={<LangLayout />}>
        <Route element={<Shell />}>
          <Route index element={<Feed />} />
          <Route path="markets" element={<CapabilityRoute feature="curated_screens"><Markets /></CapabilityRoute>} />
          <Route path="markets/:key" element={<CapabilityRoute feature="curated_screens"><ScreenExplore /></CapabilityRoute>} />
          <Route path="learn/patterns" element={<CapabilityRoute feature="curated_screens"><PatternLibrary /></CapabilityRoute>} />
          <Route path="learn/patterns/:type" element={<CapabilityRoute feature="curated_screens"><PatternDetail /></CapabilityRoute>} />
          <Route path="ideas" element={<CapabilityRoute feature="strategy_scanner"><Scanner /></CapabilityRoute>} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="alerts" element={<Alerts />} />
          {/* Redesign 2026-07: Bulls tab merged into Home (desks filter chip); Scanner renamed Ideas. */}
          <Route path="bulls" element={<CapabilityRoute feature="automated_desks"><LocaleRedirect to="/?feed=desks" /></CapabilityRoute>} />
          <Route path="scanner" element={<LocaleRedirect to="/ideas" />} />
          <Route path="desk/:handle" element={<CapabilityRoute feature="automated_desks"><DeskProfile /></CapabilityRoute>} />
          <Route path="u/:handle" element={<UserProfile />} />
          <Route path="watchlist" element={<Watchlist />} />
          <Route path="s/:code" element={<SymbolPage />} />
          {/* Admin-only (token-gated in the page itself); deliberately not linked from any nav. */}
          <Route path="cockpit" element={<CapabilityRoute feature="automated_desks"><Cockpit /></CapabilityRoute>} />
          <Route path="me" element={<Profile />} />
          <Route path="welcome" element={<CapabilityRoute feature="curated_screens"><Welcome /></CapabilityRoute>} />
          <Route path="about" element={<About />} />
          <Route path="beta" element={<ResearchBetaRoute><Beta /></ResearchBetaRoute>} />
          <Route path="institutions" element={<Institutions />} />
          <Route path="trust" element={<Trust />} />
          <Route path="privacy" element={<Privacy />} />
          <Route path="terms" element={<Terms />} />
          <Route path="forgot" element={<ForgotPassword />} />
          <Route path="reset" element={<ResetPassword />} />
          <Route path="verify" element={<VerifyEmail />} />
        </Route>
      </Route>
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
