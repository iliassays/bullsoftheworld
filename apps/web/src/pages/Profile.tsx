import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";
import { Avatar } from "../components/ui";

export function Profile() {
  const { user, login, register, logout } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [handle, setHandle] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
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
      </div>
    );

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      if (mode === "login") await login(handle, password);
      else await register(handle, name, email, password);
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
      <input
        className={field}
        placeholder={t("profile.handle")}
        value={handle}
        onChange={(e) => setHandle(e.target.value)}
      />
      {mode === "register" && (
        <p className="text-[11px] text-muted -mt-1 px-1">{t("profile.handleHint")}</p>
      )}
      {mode === "register" && (
        <>
          <input
            className={field}
            placeholder={t("profile.name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className={field}
            type="email"
            placeholder={t("profile.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </>
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
        {busy ? "…" : mode === "login" ? t("common.login") : t("profile.createAccount")}
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
    </div>
  );
}
