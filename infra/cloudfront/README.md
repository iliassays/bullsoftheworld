# CloudFront bot-routing for SEO

Turns on server-rendered HTML for crawlers and social scrapers. The site is a client-rendered SPA
on S3 (`bullsofdhaka-web`, distribution `EPJ7LAHUJDDMK`); bots/social scrapers don't run JS, so
without this they see one generic page for every stock and every shared link. This routes only
bot/social user-agents to the API's `/seo/*` renderer (real per-page HTML); humans keep getting the
SPA from S3.

Repeat the same origin, behavior, and function association on the Bulls of Wall Street
distribution. Its API origin should be `api.bullsofwallst.com`; the function forwards the viewer
host, so the shared backend resolves the correct tenant without market-specific function code.

**Everything else in the SEO work is already live** (bilingual URLs, per-page meta, sitemap,
robots, GA ticker tracking). This is the one piece that needs a change to the CloudFront
distribution, which is managed by hand — so it's documented here for you to apply (or grant AWS CLI
access and I'll run it). Until it's wired, nothing breaks: the `/seo/*` API endpoint just sits
unused and shared links keep showing the generic card.

## What it does

`bot-router.js` (a CloudFront **Function**, viewer-request — sub-ms, no cold starts) checks the
User-Agent; for known crawlers/scrapers it rewrites `/<path>` → `/seo/<path>`. A cache behavior
sends `/seo/*` to the API origin, which renders the HTML. Not cloaking: `/seo/<path>` serves the
same content a human sees at `<path>`, just without needing JS.

## Steps

**1. Create + publish the function** (safe, isolated — just the function):

```bash
./infra/cloudfront/create-function.sh          # needs aws CLI with CloudFront perms
```

**2. Add the API as a second origin** on distribution `EPJ7LAHUJDDMK` (console: CloudFront →
Distributions → EPJ7LAHUJDDMK → Origins → Create origin):
- Origin domain: `api.bullsofdhaka.com`
- Protocol: HTTPS only
- Origin ID: e.g. `bulls-api`

The viewer-request function copies the public `Host` into `X-Tenant-Host`; keep that header in the
origin request policy. The API intentionally rejects unknown production hosts instead of falling
back to a tenant.

**3. Add a cache behavior** for the renderer (Behaviors → Create behavior):
- Path pattern: `/seo/*`
- Origin: `bulls-api` (from step 2)
- Viewer protocol policy: Redirect HTTP to HTTPS
- Allowed methods: GET, HEAD
- Cache policy: **CachingDisabled** (or a short-TTL policy — the renderer already sends
  `Cache-Control: public, max-age=900`)
- Origin request policy: **AllViewer** (forwards the User-Agent etc.)
- Function associations → Viewer request: **none** here (the function belongs on the DEFAULT
  behavior, step 4 — it must run on the human/S3 path so it can rewrite INTO `/seo/*`).

**4. Attach the function to the DEFAULT behavior** (Behaviors → Default (`*`) → Edit → Function
associations → Viewer request → CloudFront Functions → `bulls-bot-router`). This is what inspects
the UA on every request and rewrites bot requests to `/seo/*` (which then matches the step-3
behavior). Assets, `/seo/*`, `/robots.txt`, `/sitemap.xml`, and any path with a file extension are
skipped inside the function.

**5. Verify** (after the distribution finishes deploying, ~5 min):

```bash
# Bot UA → should return server-rendered HTML with a real per-stock <title>:
curl -s -A "facebookexternalhit/1.1" https://bullsofdhaka.com/en/s/GP | grep -o '<title>[^<]*</title>'
# Human UA → should return the SPA shell (generic index.html title):
curl -s -A "Mozilla/5.0" https://bullsofdhaka.com/en/s/GP | grep -o '<title>[^<]*</title>'
```

Then confirm with Google's Rich Results Test and the Facebook Sharing Debugger against a live
`/en/s/GP` URL, and (once verified) submit `https://bullsofdhaka.com/sitemap.xml` in Google Search
Console.

## Notes
- To update the bot list later: edit `bot-router.js`, re-run `create-function.sh` (it updates +
  republishes), then invalidate `/*` if needed.
- `robots.txt` and `sitemap.xml` are served from S3 (the sitemap is regenerated each
  `deploy-prod.sh` from the live symbol list), so they need no CloudFront behavior.
