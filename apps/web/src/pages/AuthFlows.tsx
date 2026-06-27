import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";

const field =
  "w-full bg-surface border border-border rounded-xl px-3 py-2.5 text-sm outline-none focus:border-accent";
const btn = "bg-accent text-bg font-bold rounded-xl py-2.5 text-sm disabled:opacity-40";

export function ForgotPassword() {
  const { t } = useLang();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await api.forgotPassword(email.trim());
    } catch {
      /* ignore — never reveal whether the email exists */
    } finally {
      setBusy(false);
      setSent(true);
    }
  };

  return (
    <div className="flex flex-col gap-3 max-w-sm mx-auto pt-6">
      <h1 className="text-xl font-bold">{t("forgot.title")} 🐂</h1>
      {sent ? (
        <p className="text-sm text-muted leading-relaxed">{t("forgot.sent")}</p>
      ) : (
        <>
          <p className="text-sm text-muted">{t("forgot.intro")}</p>
          <input
            className={field}
            type="email"
            placeholder={t("profile.email")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button disabled={busy || !email.trim()} onClick={submit} className={btn}>
            {busy ? "…" : t("forgot.send")}
          </button>
        </>
      )}
      <Link to="/me" className="text-muted text-sm text-center">
        {t("common.login")}
      </Link>
    </div>
  );
}

export function ResetPassword() {
  const { t } = useLang();
  const { applyToken } = useAuth();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      const { access_token } = await api.resetPassword(token, password);
      await applyToken(access_token);
      navigate("/");
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : t("reset.invalid"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 max-w-sm mx-auto pt-6">
      <h1 className="text-xl font-bold">{t("reset.title")} 🐂</h1>
      <input
        className={field}
        type="password"
        placeholder={t("reset.newPassword")}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {err && <p className="text-down text-xs">{err}</p>}
      <button disabled={busy || password.length < 8} onClick={submit} className={btn}>
        {busy ? "…" : t("reset.submit")}
      </button>
    </div>
  );
}

export function VerifyEmail() {
  const { t } = useLang();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"loading" | "ok" | "fail">("loading");

  useEffect(() => {
    if (!token) {
      setState("fail");
      return;
    }
    api
      .verifyEmail(token)
      .then(() => setState("ok"))
      .catch(() => setState("fail"));
  }, [token]);

  const msg =
    state === "loading" ? t("verify.verifying") : state === "ok" ? t("verify.ok") : t("verify.fail");
  return (
    <div className="flex flex-col gap-3 max-w-sm mx-auto pt-10 text-center">
      <div className="text-3xl">{state === "ok" ? "✅" : state === "fail" ? "⚠️" : "⏳"}</div>
      <p className="text-sm">{msg}</p>
      <Link to="/" className="text-accent text-sm">
        {t("common.backHome")}
      </Link>
    </div>
  );
}
