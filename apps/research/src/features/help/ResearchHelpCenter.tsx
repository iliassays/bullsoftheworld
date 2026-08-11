import {
  ArrowRight,
  BookOpen,
  ChartCandlestick,
  FileSearch,
  FlaskConical,
  History,
  RotateCcw,
  Scale,
  ShieldCheck,
  X,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Dialog, Modal, ModalOverlay, Switch } from "react-aria-components";
import { Link } from "react-router-dom";

import { Button, IconButton, SearchInput, SegmentedControl } from "../../design-system";
import { trackAtlasEvent } from "./analytics";
import {
  GLOSSARY,
  ORIENTATION_STEPS,
  filterGlossary,
  type AnalyticsConsent,
  type AtlasExperienceIdentity,
} from "./model";

type HelpSection = "workflow" | "glossary" | "privacy";

const HELP_SECTIONS = [
  { value: "workflow", label: "Workflow" },
  { value: "glossary", label: "Glossary", count: GLOSSARY.length },
  { value: "privacy", label: "Privacy" },
] as const;

const STEP_ICONS: Record<(typeof ORIENTATION_STEPS)[number]["key"], LucideIcon> = {
  discover: ChartCandlestick,
  investigate: FileSearch,
  validate: FlaskConical,
  allocate: Scale,
  learn: History,
};

interface ResearchHelpCenterProps {
  analyticsConsent: AnalyticsConsent;
  identity: AtlasExperienceIdentity;
  isOpen: boolean;
  onAnalyticsConsentChange(value: Exclude<AnalyticsConsent, null>): void;
  onOpenChange(open: boolean): void;
  onReplayOrientation(): void;
}

export function ResearchHelpCenter({
  analyticsConsent,
  identity,
  isOpen,
  onAnalyticsConsentChange,
  onOpenChange,
  onReplayOrientation,
}: ResearchHelpCenterProps) {
  const [section, setSection] = useState<HelpSection>("workflow");
  const [query, setQuery] = useState("");
  const glossary = useMemo(() => filterGlossary(query), [query]);

  const changeSection = (next: HelpSection) => {
    setSection(next);
    if (next === "glossary") {
      void trackAtlasEvent(identity, "atlas_glossary_opened", "/today", {
        result_count: glossary.length,
        source: "help_center",
      });
    }
  };

  return (
    <ModalOverlay
      className="ds-modal-overlay atlas-help-overlay"
      isDismissable
      isOpen={isOpen}
      onOpenChange={onOpenChange}
    >
      <Modal className="ds-modal atlas-help-modal">
        <Dialog aria-labelledby="atlas-help-title" className="atlas-help">
          {({ close }) => (
            <>
              <header className="atlas-help__header">
                <div>
                  <span className="atlas-help__eyebrow">Reference</span>
                  <h2 id="atlas-help-title">Atlas help center</h2>
                  <p>Workflow definitions and privacy controls for this research workspace.</p>
                </div>
                <IconButton label="Close help center" onPress={close}>
                  <X aria-hidden="true" size={18} />
                </IconButton>
              </header>

              <div className="atlas-help__tabs">
                <SegmentedControl
                  label="Help center section"
                  onChange={changeSection}
                  options={HELP_SECTIONS}
                  value={section}
                />
              </div>

              <div className="atlas-help__body">
                {section === "workflow" && (
                  <section aria-labelledby="atlas-help-workflow-title">
                    <div className="atlas-help__section-heading">
                      <div>
                        <span>Decision path</span>
                        <h3 id="atlas-help-workflow-title">Evidence before allocation</h3>
                      </div>
                      <Button onPress={onReplayOrientation} variant="secondary">
                        <RotateCcw aria-hidden="true" size={14} />
                        Replay orientation
                      </Button>
                    </div>
                    <p className="atlas-help__intro">
                      Atlas separates observations, investigation, strategy validation, risk, and
                      outcomes. No research scanner creates an order directly.
                    </p>
                    <ol className="atlas-help__workflow">
                      {ORIENTATION_STEPS.map((step, index) => {
                        const Icon = STEP_ICONS[step.key];
                        return (
                          <li key={step.key}>
                            <Link onClick={() => onOpenChange(false)} to={step.route}>
                              <span className="atlas-help__workflow-index">
                                {String(index + 1).padStart(2, "0")}
                              </span>
                              <span className="atlas-help__workflow-icon">
                                <Icon aria-hidden="true" size={17} />
                              </span>
                              <span>
                                <strong>{step.label}</strong>
                                <small>{step.title}</small>
                              </span>
                              <ArrowRight aria-hidden="true" size={15} />
                            </Link>
                          </li>
                        );
                      })}
                    </ol>
                  </section>
                )}

                {section === "glossary" && (
                  <section aria-labelledby="atlas-help-glossary-title">
                    <div className="atlas-help__section-heading">
                      <div>
                        <span>Terminology</span>
                        <h3 id="atlas-help-glossary-title">What Atlas means</h3>
                      </div>
                    </div>
                    <SearchInput
                      aria-label="Search Atlas glossary"
                      onChange={setQuery}
                      placeholder="Search setup, MFE, target..."
                      value={query}
                    />
                    <div aria-live="polite" className="atlas-help__result-count">
                      {glossary.length} {glossary.length === 1 ? "definition" : "definitions"}
                    </div>
                    <dl className="atlas-help__glossary">
                      {glossary.map((entry) => (
                        <div key={entry.term}>
                          <dt>
                            <span>{entry.term}</span>
                            <small>{entry.category}</small>
                          </dt>
                          <dd>
                            <p>{entry.meaning}</p>
                            <p>
                              <strong>Not:</strong> {entry.not}
                            </p>
                            {entry.route && (
                              <Link onClick={() => onOpenChange(false)} to={entry.route}>
                                Open relevant workspace
                                <ArrowRight aria-hidden="true" size={13} />
                              </Link>
                            )}
                          </dd>
                        </div>
                      ))}
                    </dl>
                    {!glossary.length && (
                      <div className="atlas-help__empty">
                        <BookOpen aria-hidden="true" size={20} />
                        <strong>No matching term</strong>
                        <span>Try a shorter market or workflow phrase.</span>
                      </div>
                    )}
                  </section>
                )}

                {section === "privacy" && (
                  <section aria-labelledby="atlas-help-privacy-title">
                    <div className="atlas-help__section-heading">
                      <div>
                        <span>Usage analytics</span>
                        <h3 id="atlas-help-privacy-title">Your choice</h3>
                      </div>
                    </div>
                    <div className="atlas-help__privacy-control">
                      <div>
                        <strong>Share pseudonymous Atlas usage</strong>
                        <p>
                          Helps measure whether analysts reach useful workflow stages and where they
                          leave. This setting is separate for each market account.
                        </p>
                      </div>
                      <Switch
                        aria-label="Share pseudonymous Atlas usage analytics"
                        className="atlas-switch"
                        isSelected={analyticsConsent === "granted"}
                        onChange={(selected) =>
                          onAnalyticsConsentChange(selected ? "granted" : "denied")
                        }
                      >
                        <span aria-hidden="true" className="atlas-switch__track">
                          <span className="atlas-switch__thumb" />
                        </span>
                      </Switch>
                    </div>
                    <div className="atlas-help__privacy-facts">
                      <div>
                        <ShieldCheck aria-hidden="true" size={17} />
                        <span>
                          <strong>Collected</strong>
                          Tenant, market, normalized route, workflow stage, and a pseudonymous
                          session identifier.
                        </span>
                      </div>
                      <div>
                        <ShieldCheck aria-hidden="true" size={17} />
                        <span>
                          <strong>Never collected here</strong>
                          Ticker symbols, research questions, portfolio values, order details, or
                          free-form text.
                        </span>
                      </div>
                      <div>
                        <ShieldCheck aria-hidden="true" size={17} />
                        <span>
                          <strong>Retention</strong>
                          Raw product events expire after 180 days. Turning this off stops new
                          events immediately.
                        </span>
                      </div>
                    </div>
                  </section>
                )}
              </div>
            </>
          )}
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
