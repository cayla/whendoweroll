tailwind.config = {
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: 'var(--color-canvas)',
        surface: 'var(--color-surface)',
        elevated: 'var(--color-elevated)',
        line: 'var(--color-line)',
        ink: 'var(--color-ink)',
        muted: 'var(--color-muted)',
        subtle: 'var(--color-subtle)',
        brand: 'var(--color-brand)',
        'brand-hover': 'var(--color-brand-hover)',
        'brand-fg': 'var(--color-brand-fg)',
        'brand-fg-hover': 'var(--color-brand-fg-hover)',
        'btn-primary': 'var(--color-btn-primary)',
        'btn-primary-hover': 'var(--color-btn-primary-hover)',
        'on-btn': 'var(--color-on-btn-primary)',
      },
      accentColor: {
        brand: 'var(--color-brand)',
      },
      ringOffsetColor: {
        canvas: 'var(--color-canvas)',
      },
      ringColor: {
        brand: 'var(--color-ring)',
      },
    },
  },
};
