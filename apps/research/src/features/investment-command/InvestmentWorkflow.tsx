import {
  ArrowRight,
  ChartCandlestick,
  ChevronDown,
  FileSearch,
  FlaskConical,
  History,
  Scale,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { Link } from "react-router-dom";

interface InvestmentWorkflowProps {
  bookCount: number;
  catalystCount: number;
  researchAttention: number;
  reviewCount: number;
  targetCount: number;
}

interface WorkflowStage {
  detail: string;
  href: string;
  icon: LucideIcon;
  label: string;
}

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

export function InvestmentWorkflow({
  bookCount,
  catalystCount,
  researchAttention,
  reviewCount,
  targetCount,
}: InvestmentWorkflowProps) {
  const stages: WorkflowStage[] = [
    {
      detail: `${countLabel(catalystCount, "dated catalyst")} plus point-in-time setup scans`,
      href: "/setups",
      icon: ChartCandlestick,
      label: "Discover",
    },
    {
      detail: researchAttention
        ? `${countLabel(researchAttention, "evidence brief")} require attention`
        : "No fresh evidence brief requires attention",
      href: "/queue",
      icon: FileSearch,
      label: "Investigate",
    },
    {
      detail: "Registered tests, costs, and promotion gates",
      href: "/hypotheses",
      icon: FlaskConical,
      label: "Validate",
    },
    {
      detail: `${countLabel(targetCount, "target change")} · ${countLabel(reviewCount, "risk review")}`,
      href: "/portfolio",
      icon: Scale,
      label: "Allocate",
    },
    {
      detail: `${countLabel(bookCount, "paper book")} · immutable forward outcomes`,
      href: "/memory",
      icon: History,
      label: "Learn",
    },
  ];

  return (
    <details className="investment-workflow">
      <summary>
        <Workflow aria-hidden="true" size={17} />
        <span>
          <strong>How Atlas reaches a paper decision</strong>
          <small>Discover → Investigate → Validate → Allocate → Learn</small>
        </span>
        <ChevronDown aria-hidden="true" className="investment-workflow__chevron" size={16} />
      </summary>
      <div className="investment-workflow__body">
        <p>
          A scanner observation cannot become a paper target until a registered strategy passes
          its evidence and risk gates.
        </p>
        <ol>
          {stages.map((stage, index) => {
            const Icon = stage.icon;
            return (
              <li key={stage.label}>
                <Link
                  aria-label={`Open ${stage.label}: ${stage.detail}`}
                  to={stage.href}
                >
                  <span className="investment-workflow__icon">
                    <Icon aria-hidden="true" size={16} />
                  </span>
                  <span>
                    <small>{String(index + 1).padStart(2, "0")}</small>
                    <strong>{stage.label}</strong>
                    <em>{stage.detail}</em>
                  </span>
                  <ArrowRight aria-hidden="true" size={14} />
                </Link>
              </li>
            );
          })}
        </ol>
      </div>
    </details>
  );
}
