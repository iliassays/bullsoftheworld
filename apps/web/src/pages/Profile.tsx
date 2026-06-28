import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Avatar } from "../components/ui";

// Real, monitored mailbox — also set as Reply-To on transactional email.
const SUPPORT_EMAIL = "hello@bullsofdhaka.com";

function ContactLine() {
  const { t } = useLang();
  return (
    <p className="text-muted text-xs text-center mt-2">
      {t("profile.contact")}{" "}
      <a href={`mailto:${SUPPORT_EMAIL}`} className="text-accent">
        {SUPPORT_EMAIL}
      </a>
    </p>
  );
}

export function Profile() {
  const { user, login, register, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
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
      else await register(name.trim(), idField.trim(), password);
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
