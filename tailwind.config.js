/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--color-canvas)",
        surface: "var(--color-surface)",
        elevated: "var(--color-elevated)",
        line: "var(--color-line)",
        ink: "var(--color-ink)",
        muted: "var(--color-muted)",
        subtle: "var(--color-subtle)",
        brand: "var(--color-brand)",
        "brand-hover": "var(--color-brand-hover)",
        "brand-fg": "var(--color-brand-fg)",
        "brand-fg-hover": "var(--color-brand-fg-hover)",
        "btn-primary": "var(--color-btn-primary)",
        "btn-primary-hover": "var(--color-btn-primary-hover)",
        "on-btn": "var(--color-on-btn-primary)",
      },
      accentColor: {
        brand: "var(--color-brand)",
      },
      ringOffsetColor: {
        canvas: "var(--color-canvas)",
      },
      ringColor: {
        brand: "var(--color-ring)",
      },
    },
  },
  safelist: [
    // avail_row.html — conditional Yes/No button states
    "bg-[var(--color-btn-primary)]",
    "text-[var(--color-on-btn-primary)]",
    "hover:bg-emerald-50",
    "text-emerald-800",
    "dark:hover:bg-emerald-950/40",
    "dark:text-emerald-300",
    "bg-neutral-600",
    "text-white",
    "dark:bg-neutral-700",
    "hover:bg-elevated",
    // public.html — consensus card variants
    "border-emerald-500",
    "dark:border-emerald-400",
    "border-amber-500",
    "border-dashed",
    "dark:border-amber-400",
    "text-emerald-800",
    "dark:text-emerald-300",
    "text-amber-800",
    "dark:text-amber-200",
    "text-emerald-900",
    "dark:text-emerald-300/90",
    "text-amber-900",
    "dark:text-amber-200/90",
  ],
};
