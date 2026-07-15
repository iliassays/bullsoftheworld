import type { ReactElement } from "react";
import {
  OverlayArrow,
  Tooltip,
  TooltipTrigger,
} from "react-aria-components";

export function AppTooltip({ children, label }: { children: ReactElement; label: string }) {
  return (
    <TooltipTrigger delay={450} closeDelay={80}>
      {children}
      <Tooltip className="ds-tooltip" placement="bottom">
        <OverlayArrow className="ds-tooltip__arrow">
          <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
            <path d="M0 0 L4 4 L8 0" />
          </svg>
        </OverlayArrow>
        {label}
      </Tooltip>
    </TooltipTrigger>
  );
}
