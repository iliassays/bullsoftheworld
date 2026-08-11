import { ArrowRight, Radar } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "../../design-system";
import { SqueezeMonitorPanel } from "./SqueezeMonitorPanel";
import { StrategyReadinessPanel } from "./StrategyReadinessPanel";

export function SetupMonitorPage() {
  const navigate = useNavigate();

  return (
    <div className="atlas-page setup-monitor-page">
      <header className="atlas-page-header">
        <div>
          <span className="atlas-page-header__eyebrow">
            Point-in-time discovery research · never an order queue
          </span>
          <h1>Setup monitor</h1>
          <p>
            Follow chart-pattern lifecycles, inspect supporting and counter-evidence, and keep
            rule confirmation separate from strategy eligibility.
          </p>
        </div>
        <span className="atlas-page-header__actions">
          <Button onPress={() => navigate("/conditions")} variant="secondary">
            <Radar aria-hidden="true" size={14} />
            Condition scanner
          </Button>
          <Button onPress={() => navigate("/hypotheses")} variant="quiet">
            Strategy lab
            <ArrowRight aria-hidden="true" size={14} />
          </Button>
        </span>
      </header>

      <SqueezeMonitorPanel />
      <StrategyReadinessPanel />
    </div>
  );
}
