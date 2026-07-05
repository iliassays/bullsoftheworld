import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, type User } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Avatar } from "../components/ui";

// Real, monitored mailbox — also set as Reply-To on transactional email.
const SUPPORT_EMAIL = "hello@bullsofdhaka.com";

const PHONE_RE = /^\+?\d{7,15}$/; // lenient: BD (01…) or international (+cc…); server normalizes

// One contact row (email or phone): shows value + verified state, lets the user add/change it.
function ContactRow({
  kind,
  user,
}: {
  kind: "email" | "phone";
  user: User;
}) {
  const { t } = useLang();
  const { refresh } = useAuth();
  const value = kind === "email" ? user.email : user.phone;
  const verified = kind === "email" ? user.email_verified : user.phone_verified;
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(value ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const save = async () => {
    const v = val.trim();
    if (kind === "phone" && !PHONE_RE.test(v.replace(/[\s-]/g, ""))) {
      setMsg(t("profile.badPhone"));
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      await api.updateContact({ [kind]: v });
      await refresh();
      setEditing(false);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.detail : t("profile.error"));
    } finally {
      setBusy(false);
    }
  };

  const verifyEmail = async () => {
    setBusy(true);
    setMsg("");
    try {
      await api.resendVerify();
      setMsg(t("profile.verifySent"));
    } catch {
      setMsg(t("profile.error"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-1 py-2 border-b border-border last:border-0">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted w-14 shrink-0">
          {t(kind === "email" ? "profile.emailLabel" : "profile.phoneLabel")}
        </span>
        <span className="text-sm flex-1 truncate">
          {value || <span className="text-muted">{t("profile.notAdded")}</span>}
        </span>
        {value &&
          (verified ? (
            <span className="text-[11px] text-up font-semibold">{t("profile.verified")}</span>
          ) : (
            <span className="text-[11px] text-muted">{t("profile.unverified")}</span>
          ))}
        {value && !verified && kind === "email" && (
          <button onClick={verifyEmail} disabled={busy} className="text-[11px] text-accent font-semibold">
            {t("profile.verifyBtn")}
          </button>
        )}
        <button onClick={() => setEditing((e) => !e)} className="text-[11px] text-accent">
          {value ? t("profile.change") : t("profile.add")}
        </button>
      </div>
      {value && !verified && kind === "phone" && (
        <span className="text-[10px] text-muted pl-16">{t("profile.phoneVerifySoon")}</span>
      )}
      {editing && (
        <div className="flex gap-2 pl-16 mt-1">
          <input
            value={val}
            onChange={(e) => setVal(e.target.value)}
            placeholder={t(kind === "email" ? "profile.emailLabel" : "profile.phoneLabel")}
            className="flex-1 bg-surface border border-border rounded-lg px-2 py-1.5 text-sm outline-none focus:border-accent"
          />
          <button
            onClick={save}
            disabled={busy || !val.trim()}
            className="bg-accent text-bg font-bold text-xs px-3 rounded-lg disabled:opacity-40"
          >
            {busy ? "…" : t("profile.save")}
          </button>
        </div>
      )}
      {msg && <span className="text-[11px] text-muted pl-16">{msg}</span>}
    </div>
  );
}

function AccountSection({ user }: { user: User }) {
  const { t } = useLang();
  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="text-xs uppercase tracking-wide text-muted mb-1">
        {t("profile.account")}
      </div>
      <ContactRow kind="email" user={user} />
      <ContactRow kind="phone" user={user} />
    </div>
  );
}

// Off by default — a real holdings list is sensitive. Only the account owner can turn this on
// for themselves (PATCH /portfolio/visibility), and turning it off re-locks /u/{handle}
// immediately since the backend re-checks the flag on every request, not just at toggle time.
function PortfolioPrivacySection({ user }: { user: User }) {
  const { t } = useLang();
  const { refresh } = useAuth();
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    setBusy(true);
    try {
      await api.portfolioSetVisibility(!user.portfolio_public);
      await refresh();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bg-surface border border-border rounded-2xl p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold">{t("profile.publicPortfolio")}</div>
          <p className="text-xs text-muted mt-0.5 leading-relaxed">
            {t("profile.publicPortfolioHint")}
          </p>
        </div>
        <button
          onClick={toggle}
          disabled={busy}
          aria-pressed={user.portfolio_public}
          className={`shrink-0 w-12 h-7 rounded-full relative transition-colors disabled:opacity-50 ${
            user.portfolio_public ? "bg-accent" : "bg-card border border-border"
          }`}
        >
          <span
            className={`absolute top-0.5 w-6 h-6 rounded-full bg-bg transition-transform ${
              user.portfolio_public ? "translate-x-[22px]" : "translate-x-0.5"
            }`}
          />
        </button>
      </div>
      {user.portfolio_public && (
        <Link to={`/u/${user.handle}`} className="inline-block mt-3 text-xs text-accent">
          {t("profile.viewPublicProfile")} →
        </Link>
      )}
    </div>
  );
}

// Bulls of Dhaka's Facebook page (numeric id works even without a vanity URL).
const FB_URL = "https://www.facebook.com/1214682241723822";

function ContactLine() {
  const { t } = useLang();
  return (
    <div className="mt-2 flex flex-col gap-1.5 text-center">
      <p className="text-muted text-xs">
        {t("profile.contact")}{" "}
        <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent">
          {SUPPORT_EMAIL}
        </a>
      </p>
      {/* Relocated from the header (2026-07 noise cut) — reachable, not omnipresent. */}
      <p className="text-muted text-xs">
        <Link to="/about" className="text-accent">
          ⓘ {t("nav.about")}
        </Link>
        {" · "}
        <a href={FB_URL} target="_blank" rel="noopener noreferrer" className="text-accent">
          Facebook ↗
        </a>
      </p>
    </div>
  );
}

export function Profile() {
  const { user, login, register, logout, refresh } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");

  // Re-fetch on mount + when the tab regains focus, so a verification done elsewhere
  // (e.g. clicking the email link in another tab) reflects here without a manual reload.
  useEffect(() => {
    if (!user) return;
    refresh();
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const [name, setName] = useState("");
  const [idField, setIdField] = useState(""); // email/phone (register) or email/phone/username (login)
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  if (user)
    return (
      <div className="flex flex-col gap-4">
        <div className="bg-surface border border-border rounded-2xl p-4 flex items-center gap-3">
          <Avatar name={user.name} />
          <div>
            <div className="font-bold">{user.name}</div>
            <div className="text-sm text-muted">@{user.handle}</div>
          </div>
        </div>
        <AccountSection user={user} />
        <PortfolioPrivacySection user={user} />
        <Link
          to="/watchlist"
          className="bg-surface border border-border rounded-2xl py-3 text-center text-sm font-semibold hover:border-accent hover:text-accent"
        >
          {t("profile.watchlist")}
        </Link>
        <button
          onClick={logout}
          className="text-down border border-border rounded-xl py-2.5 text-sm font-semibold"
        >
          {t("profile.logout")}
        </button>
        <ContactLine />
      </div>
    );

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      if (mode === "login") await login(idField.trim(), password);
      else {
        await register(name.trim(), idField.trim(), password);
        navigate("/welcome", { replace: true }); // seed sectors → stocks → desks
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : t("profile.error"));
    } finally {
      setBusy(false);
    }
  };

  const field =
    "bg-surface border border-border rounded-xl px-3 py-2.5 text-sm outline-none focus:border-accent";

  return (
    <div className="flex flex-col gap-3 max-w-sm mx-auto pt-6">
      <h1 className="text-xl font-bold">
        {mode === "login" ? t("profile.welcomeBack") : t("profile.join")} 🐂
      </h1>
      {mode === "register" && (
        <input
          className={field}
          placeholder={t("profile.name")}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      )}
      <input
        className={field}
        placeholder={mode === "register" ? t("profile.emailOrPhone") : t("profile.loginId")}
        value={idField}
        onChange={(e) => setIdField(e.target.value)}
      />
      {mode === "register" && (
        <p className="text-[11px] text-muted -mt-1 px-1">{t("profile.autoHandleHint")}</p>
      )}
      <input
        className={field}
        type="password"
        placeholder={t("profile.password")}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {err && <p className="text-down text-xs">{err}</p>}
      <button
        disabled={busy}
        onClick={submit}
        className="bg-accent text-bg font-bold rounded-xl py-2.5 text-sm disabled:opacity-40"
      >
        {busy
          ? "…"
          : mode === "login"
            ? t("common.login")
            : t("profile.createAccount")}
      </button>
      <button
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setErr("");
        }}
        className="text-muted text-sm"
      >
        {mode === "login" ? t("profile.toRegister") : t("profile.toLogin")}
      </button>
      {mode === "login" && (
        <Link to="/forgot" className="text-muted text-xs text-center">
          {t("profile.forgot")}
        </Link>
      )}
      <button
        onClick={() => navigate(-1)}
        className="text-muted text-sm border border-border rounded-xl py-2.5"
      >
        {t("common.cancel")}
      </button>
      <ContactLine />
    </div>
  );
}
