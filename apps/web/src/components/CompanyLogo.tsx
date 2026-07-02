import { useState } from "react";
import { logoUrl } from "../lib/api";

// Ticker-initials fallback when we have no logo. Brand-tinted, carries no up/down meaning.
function Monogram({ code, size }: { code: string; size: number }) {
  return (
    <span
      className="flex-none rounded-full bg-accent/10 text-accent grid place-items-center font-bold"
      style={{ width: size, height: size, fontSize: Math.round(size * 0.34) }}
    >
      {code.slice(0, 2)}
    </span>
  );
}

// Company logo fetched at onboarding from the company's own website. Rendered on a white chip so
// dark/transparent marks stay visible on the dark theme; falls back to a monogram on 404/error.
export function CompanyLogo({ code, size = 32 }: { code: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <Monogram code={code} size={size} />;
  return (
    <img
      src={logoUrl(code)}
      alt={`${code} logo`}
      loading="lazy"
      onError={() => setFailed(true)}
      className="flex-none rounded-full bg-white object-contain p-0.5 border border-border"
      style={{ width: size, height: size }}
    />
  );
}
