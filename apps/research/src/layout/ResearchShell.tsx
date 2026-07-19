import {
  BookOpenCheck,
  CalendarDays,
  ChartNoAxesCombined,
  FileSearch,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Settings,
  Sun,
  X,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { AppTooltip, IconButton, StatusBadge } from "../design-system";
import { useResearchAuth } from "../app/auth";
import { isResearchPreview, researchDeployment } from "../app/deployment";
import { ManagerGuide } from "./ManagerGuide";
import { managerGuideForPath } from "./manager-guides";

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
      { label: "Today", icon: LayoutDashboard, href: "/today" },
      { label: "Portfolio & risk", icon: ChartNoAxesCombined, href: "/portfolio" },
      { label: "Strategy lab", icon: FlaskConical, href: "/hypotheses" },
    ],
  },
  {
    label: "Research",
    items: [
      { label: "Research inbox", icon: BookOpenCheck, href: "/queue" },
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
  const location = useLocation();
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("bulls-research-theme", theme);
  }, [theme]);

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
          <AppTooltip label="Not enabled in this foundation build">
            <span
              aria-disabled="true"
              className="research-nav__item research-nav__item--disabled"
              role="button"
              tabIndex={0}
            >
              <Settings aria-hidden="true" size={17} strokeWidth={1.8} />
              <span>Workspace settings</span>
            </span>
          </AppTooltip>
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
            <IconButton label={`Use ${theme === "light" ? "dark" : "light"} theme`} onPress={() => setTheme(theme === "light" ? "dark" : "light")}>
              {theme === "light" ? <Moon aria-hidden="true" size={17} /> : <Sun aria-hidden="true" size={17} />}
            </IconButton>
          </div>
        </header>

        <main className="research-main">
          <ManagerGuide guide={managerGuideForPath(location.pathname)} />
          <Outlet />
        </main>
      </div>
    </div>
  );
}
