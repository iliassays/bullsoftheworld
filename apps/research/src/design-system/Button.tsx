import {
  Button as AriaButton,
  type ButtonProps as AriaButtonProps,
} from "react-aria-components";

type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";

interface ButtonProps extends AriaButtonProps {
  variant?: ButtonVariant;
}

export function Button({ variant = "secondary", className, ...props }: ButtonProps) {
  return (
    <AriaButton
      {...props}
      className={(renderProps) => {
        const resolved =
          typeof className === "function" ? className(renderProps) : (className ?? "");
        return `ds-button ds-button--${variant} ${resolved}`.trim();
      }}
    />
  );
}
