/** Build a safe redirect when the first URL segment is not valid for the active tenant. */
export function invalidLocaleRedirectTarget(
  pathname: string,
  search: string,
  firstSegment: string | undefined,
  defaultLocale: string,
  portalLocales: readonly string[],
): string {
  // A known portal locale can be replaced (for example, Dhaka's /bn path on the US tenant).
  // Any other segment is an unprefixed application route and must be preserved: /reset must
  // become /bn/reset, not /bn. This also protects legacy links and browser bookmarks.
  const rest =
    firstSegment && portalLocales.includes(firstSegment)
      ? pathname.replace(/^\/[^/]+(?=\/|$)/, "")
      : pathname === "/"
        ? ""
        : pathname;
  return `/${defaultLocale}${rest}${search}`;
}
