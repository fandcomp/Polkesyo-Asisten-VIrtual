import type { ButtonHTMLAttributes, ReactNode } from "react"

type ButtonVariant = "primary" | "secondary" | "danger" | "approve"

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  children: ReactNode
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-r from-primary to-accent text-white border border-gold/60 shadow-premium hover:brightness-105 active:brightness-95",
  secondary:
    "bg-transparent text-primary border border-primary/40 hover:bg-surface-elevated",
  danger:
    "bg-danger-bg text-danger border border-danger-border hover:brightness-95",
  approve:
    "bg-surface-elevated text-primary border border-primary/50 hover:border-primary",
}

export function Button({ variant = "primary", className = "", children, ...props }: ButtonProps) {
  return (
    <button
      className={`rounded-2xl px-5 py-2.5 text-sm font-semibold transition-all duration-300 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
