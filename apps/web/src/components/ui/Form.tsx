import type { InputHTMLAttributes, ReactNode } from "react";

// One coherent, accessible form system for Settings (Stage 10 §12).
// Deliberately kept to *styled native* controls — `accent-color` recolours
// native checkboxes without losing their native semantics, keyboard
// behaviour or screen-reader announcement, which a custom-built checkbox
// would risk regressing for no real visual gain.

export function Field({
  label,
  helper,
  htmlFor,
  children,
}: {
  label: ReactNode;
  helper?: ReactNode;
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {helper ? <p className="text-sm text-text-secondary">{helper}</p> : null}
      {children}
    </div>
  );
}

const inputStyle =
  "w-full max-w-xs rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-foreground";

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputStyle} ${props.className ?? ""}`} />;
}

export function TimeInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} type="time" className={`${inputStyle} w-36 ${props.className ?? ""}`} />;
}

export function Checkbox({
  label,
  description,
  ...props
}: { label: ReactNode; description?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex items-start gap-2.5 text-sm">
      <input type="checkbox" {...props} className="mt-0.5 size-4 shrink-0 accent-accent" />
      <span className="flex flex-col gap-0.5">
        <span className="font-medium text-foreground">{label}</span>
        {description ? <span className="text-text-secondary">{description}</span> : null}
      </span>
    </label>
  );
}

export function FormSection({
  legend,
  description,
  children,
  testId,
}: {
  legend: string;
  description?: ReactNode;
  children: ReactNode;
  testId?: string;
}) {
  return (
    <fieldset
      data-testid={testId}
      className="flex flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-xs"
    >
      <div className="flex flex-col gap-1">
        <legend className="px-0 text-base font-semibold text-foreground">{legend}</legend>
        {description ? <p className="text-sm text-text-secondary">{description}</p> : null}
      </div>
      {children}
    </fieldset>
  );
}
