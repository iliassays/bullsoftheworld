import { useState } from "react";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Avatar } from "../components/ui";

export function Profile() {
  const { user, login, register, logout } = useAuth();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [handle, setHandle] = useState("");
  const [name, setName] = useState("");
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
          Log out
        </button>
      </div>
    );

  const submit = async () => {
    setBusy(true);
    setErr("");
    try {
      if (mode === "login") await login(handle, password);
      else await register(handle, name, password);
    } catch (e) {
      setErr(e instanceof ApiError ? e.detail : "Something went wrong");
    } finally {
      setBusy(false);
    }
  };

  const field = "bg-surface border border-border rounded-xl px-3 py-2.5 text-sm outline-none focus:border-accent";

  return (
    <div className="flex flex-col gap-3 max-w-sm mx-auto pt-6">
      <h1 className="text-xl font-bold">
        {mode === "login" ? "Welcome back" : "Join Bulls of Dhaka"} 🐂
      </h1>
      <input className={field} placeholder="handle" value={handle} onChange={(e) => setHandle(e.target.value)} />
      {mode === "register" && (
        <input className={field} placeholder="full name" value={name} onChange={(e) => setName(e.target.value)} />
      )}
      <input
        className={field}
        type="password"
        placeholder="password (min 8 chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      {err && <p className="text-down text-xs">{err}</p>}
      <button
        disabled={busy}
        onClick={submit}
        className="bg-accent text-bg font-bold rounded-xl py-2.5 text-sm disabled:opacity-40"
      >
        {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
      </button>
      <button
        onClick={() => {
          setMode(mode === "login" ? "register" : "login");
          setErr("");
        }}
        className="text-muted text-sm"
      >
        {mode === "login" ? "New here? Create an account" : "Already have an account? Log in"}
      </button>
    </div>
  );
}
