import type { ButtonHTMLAttributes, ReactNode } from "react";

// A closed set of button variants so approval, secondary and destructive
// actions are never visually confusable (Stage 10 §9). `primary` is the
// one accent-filled action per view — reserved for approve/execute/save,
// never for reject or cancel. `danger` is reserved for genuinely
// irreversible actions (permanent deletion), never for a normal decision
// like reject or disconnect.
export type ButtonVariant = "primary" | "secondary" | "danger";

const VARIANT_STYLE: Record<ButtonVariant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover disabled:opacity-50",
  secondary:
    "border border-border-strong bg-transparent text-foreground hover:bg-surface-raised disabled:opacity-50",
  danger: "bg-danger-solid text-white hover:bg-danger-solid-hover disabled:opacity-50",
};

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...props
}: {
  variant?: ButtonVariant;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`inline-flex w-fit items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${VARIANT_STYLE[variant]} ${className}`}
    >
      {children}
    </button>
  );
}
