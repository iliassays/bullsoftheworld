import { LockKeyhole } from "lucide-react";
import { useState } from "react";

import { researchDeployment } from "../../app/deployment";
import { useResearchAuth } from "../../app/auth";
import { Button } from "../../design-system";

export function LoginPage() {
  const auth = useResearchAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  return (
    <main className="research-login">
      <section className="research-login__panel" aria-labelledby="research-login-title">
        <header className="research-login__brand">
          <img src="/logo-mark-v2.png" alt="" />
          <span>
            <strong>Bulls Atlas</strong>
            <small>{researchDeployment.brandName} · Private research</small>
          </span>
        </header>
        <div className="research-login__heading">
          <span><LockKeyhole aria-hidden="true" size={18} /></span>
          <div>
            <h1 id="research-login-title">Research workspace</h1>
            <p>Sign in with your {researchDeployment.brandName} account.</p>
          </div>
        </div>
        <form
          onSubmit={async (event) => {
            event.preventDefault();
            setSubmitting(true);
            try {
              await auth.login(identifier.trim(), password);
            } catch {
              // The provider exposes the normalized error below.
            } finally {
              setSubmitting(false);
            }
          }}
        >
          <label htmlFor="research-login-identifier">Email, phone, or handle</label>
          <input
            autoComplete="username"
            id="research-login-identifier"
            onChange={(event) => setIdentifier(event.currentTarget.value)}
            required
            value={identifier}
          />
          <label htmlFor="research-login-password">Password</label>
          <input
            autoComplete="current-password"
            id="research-login-password"
            onChange={(event) => setPassword(event.currentTarget.value)}
            required
            type="password"
            value={password}
          />
          <a className="research-login__recovery" href={researchDeployment.accountRecoveryUrl}>
            Forgot password? Reset it on {researchDeployment.brandName}
          </a>
          {auth.error && <p className="research-login__error" role="alert">{auth.error}</p>}
          <Button isDisabled={submitting || !identifier.trim() || !password} type="submit" variant="primary">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <footer>
          Access is isolated to {researchDeployment.exchangeName}. Accounts and workspaces do not cross markets.
        </footer>
      </section>
    </main>
  );
}
