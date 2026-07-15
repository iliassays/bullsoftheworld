import type { ReactNode } from "react";
import type { ButtonProps } from "react-aria-components";

import { Button } from "./Button";
import { AppTooltip } from "./Tooltip";

interface IconButtonProps extends Omit<ButtonProps, "children" | "aria-label"> {
  label: string;
  children: ReactNode;
  tone?: "default" | "danger";
}

export function IconButton({
  label,
  children,
  className,
  tone = "default",
  ...props
}: IconButtonProps) {
  return (
    <AppTooltip label={label}>
      <Button
        {...props}
        aria-label={label}
        variant={tone === "danger" ? "danger" : "quiet"}
        className={(renderProps) => {
          const resolved =
            typeof className === "function" ? className(renderProps) : (className ?? "");
          return `ds-icon-button ${resolved}`.trim();
        }}
      >
        {children}
      </Button>
    </AppTooltip>
  );
}
