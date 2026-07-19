import { BookOpenCheck, CheckCircle2, CircleAlert, Scale } from "lucide-react";
import { useState } from "react";

import type { ManagerGuide as ManagerGuideContent } from "./manager-guides";

export function ManagerGuide({ guide }: { guide: ManagerGuideContent }) {
  const [open, setOpen] = useState(() => !window.matchMedia("(max-width: 620px)").matches);

  return (
    <details
      className="manager-guide"
      onToggle={(event) => setOpen(event.currentTarget.open)}
      open={open}
    >
      <summary>
        <span className="manager-guide__icon"><BookOpenCheck aria-hidden="true" size={16} /></span>
        <span>
          <small>New manager guide · {guide.section}</small>
          <strong>{guide.question}</strong>
        </span>
        <span className="manager-guide__toggle">How research works</span>
      </summary>
      <div className="manager-guide__body">
        <article>
          <span className="manager-guide__label"><CheckCircle2 aria-hidden="true" size={13} /> Process</span>
          <ol>{guide.workflow.map((step) => <li key={step}>{step}</li>)}</ol>
        </article>
        <article>
          <span className="manager-guide__label"><Scale aria-hidden="true" size={13} /> Manager decision</span>
          <p>{guide.managerDecision}</p>
          {guide.fieldNote && <p className="manager-guide__note">Field note: {guide.fieldNote}</p>}
        </article>
        <article>
          <span className="manager-guide__label"><CircleAlert aria-hidden="true" size={13} /> Do not infer</span>
          <p>{guide.boundary}</p>
          <p className="manager-guide__clock"><strong>Clock discipline:</strong> a session is one completed DSE trading day. The 15-session user onboarding, 5-session feed check, 60-session strategy evidence gate, and 63-session Quality Reversal maximum hold are separate clocks.</p>
        </article>
      </div>
      <footer><strong>First rule:</strong> an idea is not a position. Before capital, require a knowledge cutoff, thesis, counter-evidence, size, executable entry, and exit rule.</footer>
    </details>
  );
}
