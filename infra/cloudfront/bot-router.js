// CloudFront Function (viewer-request) — bot/social-scraper routing for SEO.
import cf from "cloudfront";
//
// The site is a client-rendered SPA on S3; search engines (unreliably) and social scrapers
// (never) run JS, so they'd see one generic HTML shell for every route. This function detects
// crawler/social user-agents, rewrites "/<path>" to "/seo/<path>", and selects the tenant API
// origin already configured in each distribution. Humans fall through untouched to the S3 SPA.
//
// CloudFront Functions (not Lambda@Edge): sub-ms, no cold starts, runs on viewer-request. This is
// pure JS (ECMAScript 5.1-ish runtime) — no async, no fetch, keep it tiny.
//
// NOT cloaking: /seo/<path> renders the same content a human sees on <path>, just without needing
// JS. Only the delivery differs, not the substance.

var BOT_RE =
  /googlebot|bingbot|slurp|duckduckbot|baiduspider|yandex|sogou|exabot|facebot|facebookexternalhit|twitterbot|linkedinbot|slackbot|slack-imgproxy|whatsapp|telegrambot|discordbot|pinterest|redditbot|applebot|petalbot|ia_archiver|embedly|quora link preview|bitlybot|skypeuripreview|nuzzel|vkshare|w3c_validator|google-inspectiontool/i;

function handler(event) {
  var request = event.request;
  // Preserve the viewer domain for a shared API origin. The API fails closed on unknown hosts.
  if (request.headers.host) {
    request.headers["x-tenant-host"] = { value: request.headers.host.value };
  }
  var ua = "";
  if (request.headers["user-agent"]) ua = request.headers["user-agent"].value;

  // Static assets + already-SEO paths + files with an extension (robots.txt, sitemap.xml,
  // /assets/*, images) must never be rewritten — bots fetch those directly from S3/behaviors.
  var uri = request.uri;
  var isAsset =
    uri.indexOf("/seo/") === 0 ||
    uri.indexOf("/assets/") === 0 ||
    uri === "/robots.txt" ||
    uri === "/sitemap.xml" ||
    uri.lastIndexOf(".") > uri.lastIndexOf("/"); // has a file extension in the last segment

  if (!isAsset && BOT_RE.test(ua)) {
    request.uri = "/seo" + uri;
    // URI rewrites do not reselect a cache behavior. Select the standardized per-distribution API
    // origin directly; the same function remains tenant-agnostic across every branded domain.
    cf.selectRequestOriginById("tenant-api-seo");
  }
  return request;
}
