import { forwardRef } from "react";
import {
  Link as RRLink,
  NavLink as RRNavLink,
  useLocation,
  useNavigate as useRRNavigate,
  type LinkProps,
  type NavLinkProps,
  type NavigateFunction,
  type NavigateOptions,
  type To,
} from "react-router-dom";
import { type Lang, SUPPORTED, useLang } from "./i18n";

// Locale-aware routing. Canonical URLs carry a language segment (/bn/…, /en/…) for SEO/hreflang,
// but pages still link with plain app paths ("/s/GP", "/markets"). These wrappers prepend the
// active language so every internal navigation stays inside the current locale — swap the import
// source from "react-router-dom" to "../lib/nav" and existing `to=` props keep working unchanged.
// `useParams`/`useSearchParams`/`Outlet` etc. are unaffected and still come from react-router-dom.

export function withLocale(to: To, lang: Lang): To {
  if (typeof to !== "string") return to; // object form — none in this codebase; leave untouched
  if (!to.startsWith("/")) return to; // relative, hash, mailto, or external — leave untouched
  const first = to.split("/")[1] ?? "";
  if (SUPPORTED.includes(first as Lang)) return to; // already prefixed
  return to === "/" ? `/${lang}` : `/${lang}${to}`;
}

export const Link = forwardRef<HTMLAnchorElement, LinkProps>(function Link({ to, ...rest }, ref) {
  const { lang } = useLang();
  return <RRLink ref={ref} to={withLocale(to, lang)} {...rest} />;
});

export const NavLink = forwardRef<HTMLAnchorElement, NavLinkProps>(
  function NavLink({ to, ...rest }, ref) {
    const { lang } = useLang();
    return <RRNavLink ref={ref} to={withLocale(to, lang)} {...rest} />;
  },
);

export function useNavigate(): NavigateFunction {
  const navigate = useRRNavigate();
  const { lang } = useLang();
  return ((to: To | number, options?: NavigateOptions) =>
    typeof to === "number"
      ? navigate(to)
      : navigate(withLocale(to, lang), options)) as NavigateFunction;
}

// Switch language in place: swap the leading /bn or /en segment of the current path, preserving
// the rest of the route + query. Drives the header toggle (the URL is now the source of truth).
export function useSwitchLang(): (l: Lang) => void {
  const navigate = useRRNavigate();
  const loc = useLocation();
  return (l: Lang) => {
    const rest = loc.pathname.replace(/^\/(bn|en)(?=\/|$)/, "");
    navigate(`/${l}${rest}${loc.search}`);
  };
}
