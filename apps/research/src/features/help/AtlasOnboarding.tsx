import {
  ArrowLeft,
  ArrowRight,
  ChartCandlestick,
  FileSearch,
  FlaskConical,
  History,
  Scale,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useState } from "react";
import { Dialog, Modal, ModalOverlay, Switch } from "react-aria-components";

import { Button } from "../../design-system";
import { trackAtlasEvent } from "./analytics";
import {
  ATLAS_EXPERIENCE_VERSION,
  ORIENTATION_STEPS,
  type AnalyticsConsent,
  type AtlasExperienceIdentity,
} from "./model";

const STEP_ICONS: Record<(typeof ORIENTATION_STEPS)[number]["key"], LucideIcon> = {
  discover: ChartCandlestick,
  investigate: FileSearch,
  validate: FlaskConical,
  allocate: Scale,
  learn: History,
};

interface AtlasOnboardingProps {
  analyticsConsent: AnalyticsConsent;
  identity: AtlasExperienceIdentity;
  isFirstSession: boolean;
  isOpen: boolean;
  onComplete(consent: Exclude<AnalyticsConsent, null>): void;
  onDismiss(): void;
  onSkip(): void;
}

export function AtlasOnboarding({
  analyticsConsent,
  identity,
  isFirstSession,
  isOpen,
  onComplete,
  onDismiss,
  onSkip,
}: AtlasOnboardingProps) {
  const [stepIndex, setStepIndex] = useState(0);
  const [shareUsage, setShareUsage] = useState(analyticsConsent === "granted");
  const step = ORIENTATION_STEPS[stepIndex] ?? ORIENTATION_STEPS[0]!;
  const StepIcon = STEP_ICONS[step.key];
  const isLast = stepIndex === ORIENTATION_STEPS.length - 1;

  useEffect(() => {
    if (!isOpen) return;
    setStepIndex(0);
    setShareUsage(analyticsConsent === "granted");
    void trackAtlasEvent(identity, "atlas_onboarding_started", "/today", {
      atlas_version: ATLAS_EXPERIENCE_VERSION,
      source: isFirstSession ? "first_session" : "help_center",
    });
  }, [analyticsConsent, identity, isFirstSession, isOpen]);

  const complete = () => {
    const consent = shareUsage ? "granted" : "denied";
    onComplete(consent);
    void trackAtlasEvent(identity, "atlas_onboarding_completed", step.route, {
      atlas_stage: step.key,
      atlas_version: ATLAS_EXPERIENCE_VERSION,
      evaluation: "completed",
    });
  };

  const skip = () => {
    onSkip();
    void trackAtlasEvent(identity, "atlas_onboarding_skipped", step.route, {
      atlas_stage: step.key,
      atlas_version: ATLAS_EXPERIENCE_VERSION,
      evaluation: "skipped",
    });
  };

  return (
    <ModalOverlay
      className="ds-modal-overlay atlas-orientation-overlay"
      isDismissable={!isFirstSession}
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open && !isFirstSession) onDismiss();
      }}
    >
      <Modal className="ds-modal atlas-orientation-modal">
        <Dialog aria-labelledby="atlas-orientation-title" className="atlas-orientation">
          <header className="atlas-orientation__header">
            <div>
              <span>Atlas orientation</span>
              <strong>
                {stepIndex + 1} of {ORIENTATION_STEPS.length}
              </strong>
            </div>
            <div
              aria-label={`Orientation progress: ${stepIndex + 1} of ${ORIENTATION_STEPS.length}`}
              className="atlas-orientation__progress"
              role="progressbar"
              aria-valuemax={ORIENTATION_STEPS.length}
              aria-valuemin={1}
              aria-valuenow={stepIndex + 1}
            >
              {ORIENTATION_STEPS.map((item, index) => (
                <span
                  className={index <= stepIndex ? "atlas-orientation__progress-step--active" : ""}
                  key={item.key}
                />
              ))}
            </div>
          </header>

          <div className="atlas-orientation__content">
            <span className="atlas-orientation__icon">
              <StepIcon aria-hidden="true" size={24} strokeWidth={1.7} />
            </span>
            <p className="atlas-orientation__stage">{step.label}</p>
            <h2 id="atlas-orientation-title">{step.title}</h2>
            <p className="atlas-orientation__body">{step.body}</p>
            <div className="atlas-orientation__guardrail">
              <ShieldCheck aria-hidden="true" size={17} />
              <span>{step.guardrail}</span>
            </div>

            {isLast && (
              <div className="atlas-orientation__consent">
                <div>
                  <strong>Help improve the research workflow</strong>
                  <p>
                    Share pseudonymous route and workflow-stage usage. No ticker, research text,
                    portfolio value, or order data is collected. Raw events expire after 180 days.
                  </p>
                </div>
                <Switch
                  aria-label="Share pseudonymous Atlas usage analytics"
                  className="atlas-switch"
                  isSelected={shareUsage}
                  onChange={setShareUsage}
                >
                  <span aria-hidden="true" className="atlas-switch__track">
                    <span className="atlas-switch__thumb" />
                  </span>
                </Switch>
              </div>
            )}
          </div>

          <footer className="atlas-orientation__footer">
            <Button onPress={isFirstSession ? skip : onDismiss} variant="quiet">
              {isFirstSession ? "Skip orientation" : "Close"}
            </Button>
            <div>
              {stepIndex > 0 && (
                <Button onPress={() => setStepIndex((value) => value - 1)} variant="secondary">
                  <ArrowLeft aria-hidden="true" size={15} />
                  Back
                </Button>
              )}
              {isLast ? (
                <Button onPress={complete} variant="primary">
                  Finish
                  <ShieldCheck aria-hidden="true" size={15} />
                </Button>
              ) : (
                <Button onPress={() => setStepIndex((value) => value + 1)} variant="primary">
                  Next
                  <ArrowRight aria-hidden="true" size={15} />
                </Button>
              )}
            </div>
          </footer>
        </Dialog>
      </Modal>
    </ModalOverlay>
  );
}
