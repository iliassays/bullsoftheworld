import {
  BookOpenCheck,
  CalendarDays,
  ChartCandlestick,
  ChartNoAxesCombined,
  FileSearch,
  FlaskConical,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  CircleHelp,
  Radar,
  Sun,
  X,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { IconButton, StatusBadge } from "../design-system";
import { useResearchAuth } from "../app/auth";
import { isResearchPreview, researchDeployment } from "../app/deployment";
import { AtlasOnboarding } from "../features/help/AtlasOnboarding";
import { ResearchHelpCenter } from "../features/help/ResearchHelpCenter";
import {
  notifyAtlasConsentChanged,
  trackAtlasEvent,
  useAtlasRouteAnalytics,
} from "../features/help/analytics";
import {
  readAnalyticsConsent,
  shouldShowOrientation,
  writeAnalyticsConsent,
  writeOrientationOutcome,
  type AnalyticsConsent,
  type AtlasExperienceIdentity,
} from "../features/help/model";

type Theme = "light" | "dark";

interface NavItem {
  label: string;
  icon: LucideIcon;
  href?: string;
}

const NAV_GROUPS: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "Investment",
    items: [
      { label: "Command", icon: LayoutDashboard, href: "/today" },
      { label: "Portfolio & risk", icon: ChartNoAxesCombined, href: "/portfolio" },
      { label: "Strategy lab", icon: FlaskConical, href: "/hypotheses" },
      { label: "Research outcomes", icon: History, href: "/memory" },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Research inbox", icon: BookOpenCheck, href: "/queue" },
      { label: "Setup monitor", icon: ChartCandlestick, href: "/setups" },
      { label: "Condition scanner", icon: Radar, href: "/conditions" },
      { label: "Company research", icon: FileSearch, href: "/companies" },
      { label: "Catalysts", icon: CalendarDays, href: "/catalysts" },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Automation & audit", icon: Workflow, href: "/operations" },
    ],
  },
];

function initialTheme(): Theme {
  const stored = window.localStorage.getItem("bulls-research-theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function ResearchShell() {
  const auth = useResearchAuth();
  const identity = useMemo<AtlasExperienceIdentity>(
    () => ({ tenant: researchDeployment.tenant, userId: auth.user?.id ?? 0 }),
    [auth.user?.id],
  );
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [navOpen, setNavOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [replayOrientation, setReplayOrientation] = useState(false);
  const [orientationRequired, setOrientationRequired] = useState(() =>
    shouldShowOrientation(identity),
  );
  const [analyticsConsent, setAnalyticsConsent] = useState<AnalyticsConsent>(() =>
    readAnalyticsConsent(identity),
  );

  useAtlasRouteAnalytics(identity);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("bulls-research-theme", theme);
  }, [theme]);

  const changeAnalyticsConsent = (value: Exclude<AnalyticsConsent, null>) => {
    writeAnalyticsConsent(identity, value);
    setAnalyticsConsent(value);
    notifyAtlasConsentChanged();
  };

  const openHelp = () => {
    setHelpOpen(true);
    void trackAtlasEvent(identity, "atlas_help_opened", window.location.pathname, {
      source: "topbar",
    });
  };

  const finishOrientation = (consent: Exclude<AnalyticsConsent, null>) => {
    changeAnalyticsConsent(consent);
    writeOrientationOutcome(identity, "completed");
    setOrientationRequired(false);
    setReplayOrientation(false);
  };

  const skipOrientation = () => {
    writeOrientationOutcome(identity, "skipped");
    setOrientationRequired(false);
    setReplayOrientation(false);
  };

  return (
    <div className="research-app-shell">
      <aside className={`research-sidebar ${navOpen ? "research-sidebar--open" : ""}`}>
        <div className="research-sidebar__brand">
          <img src="/logo-mark-v2.png" alt="" className="research-sidebar__logo" />
          <div>
            <strong>Bulls Atlas</strong>
            <span>Evidence before conviction</span>
          </div>
          <IconButton label="Close navigation" className="research-sidebar__close" onPress={() => setNavOpen(false)}>
            <X aria-hidden="true" size={18} />
          </IconButton>
        </div>

        <div aria-label="Current research workspace" className="workspace-switcher">
          <span className="workspace-switcher__mark">{researchDeployment.market}</span>
          <span className="workspace-switcher__text">
            <strong>{researchDeployment.brandName}</strong>
            <small>{researchDeployment.exchangeName} only</small>
          </span>
        </div>

        <nav aria-label="Research workspace" className="research-nav">
          {NAV_GROUPS.map((group) => (
            <div className="research-nav__group" key={group.label}>
              <span className="research-nav__label">{group.label}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                if (item.href) {
                  return (
                    <NavLink
                      className={({ isActive }) =>
                        `research-nav__item ${isActive ? "research-nav__item--active" : ""}`
                      }
                      key={item.label}
                      onClick={() => setNavOpen(false)}
                      to={item.href}
                    >
                      <Icon aria-hidden="true" size={17} strokeWidth={1.8} />
                      <span>{item.label}</span>
                    </NavLink>
                  );
                }
                return null;
              })}
            </div>
          ))}
        </nav>

        <div className="research-sidebar__footer">
          <div className="research-profile">
            <span className="research-profile__avatar">
              {(auth.user?.name || "User")
                .split(/\s+/)
                .map((part) => part[0])
                .join("")
                .slice(0, 2)
                .toUpperCase()}
            </span>
            <span className="research-profile__identity">
              <strong>{auth.user?.name}</strong>
              <small>@{auth.user?.handle}</small>
            </span>
            <IconButton label="Sign out" onPress={() => void auth.logout()}>
              <LogOut aria-hidden="true" size={15} />
            </IconButton>
          </div>
        </div>
      </aside>

      {navOpen && (
        <button
          aria-label="Close navigation"
          className="research-nav-scrim"
          onClick={() => setNavOpen(false)}
          type="button"
        />
      )}

      <div className="research-workspace">
        <header className="research-topbar">
          <div className="research-topbar__left">
            <IconButton label="Open navigation" className="research-topbar__menu" onPress={() => setNavOpen(true)}>
              <Menu aria-hidden="true" size={18} />
            </IconButton>
            <div className="research-breadcrumb">
              <span>{researchDeployment.brandName}</span>
              <strong>Private research</strong>
            </div>
          </div>
          <div className="research-topbar__right">
            <div className="data-cutoff" title="This application is hard-bound to one market tenant">
              <span className="data-cutoff__pulse" aria-hidden="true" />
              <span>
                <strong>{researchDeployment.market} boundary</strong>
                <small>{researchDeployment.exchangeName}</small>
              </span>
            </div>
            {isResearchPreview && <StatusBadge tone="warning">Preview dataset</StatusBadge>}
            <IconButton label="Open Atlas help" onPress={openHelp}>
              <CircleHelp aria-hidden="true" size={17} />
            </IconButton>
            <IconButton label={`Use ${theme === "light" ? "dark" : "light"} theme`} onPress={() => setTheme(theme === "light" ? "dark" : "light")}>
              {theme === "light" ? <Moon aria-hidden="true" size={17} /> : <Sun aria-hidden="true" size={17} />}
            </IconButton>
          </div>
        </header>

        <main className="research-main">
          <Outlet />
        </main>
      </div>

      <AtlasOnboarding
        analyticsConsent={analyticsConsent}
        identity={identity}
        isFirstSession={orientationRequired}
        isOpen={orientationRequired || replayOrientation}
        onComplete={finishOrientation}
        onDismiss={() => setReplayOrientation(false)}
        onSkip={skipOrientation}
      />
      <ResearchHelpCenter
        analyticsConsent={analyticsConsent}
        identity={identity}
        isOpen={helpOpen}
        onAnalyticsConsentChange={changeAnalyticsConsent}
        onOpenChange={setHelpOpen}
        onReplayOrientation={() => {
          setHelpOpen(false);
          setReplayOrientation(true);
        }}
      />
    </div>
  );
}
