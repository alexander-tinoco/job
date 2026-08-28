/**
 * Drawn, not borrowed from a font. One stroke weight, one grid, currentColor.
 * An emoji standing in for an icon is a costume; these are part of the system.
 */
const base = {
  width: 14,
  height: 14,
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const LocatedIcon = () => (
  <svg {...base}>
    {/* A magnifier over a rule: the instrument finding a line. */}
    <circle cx="6.8" cy="6.8" r="4.1" />
    <path d="M9.9 9.9 13.4 13.4" />
  </svg>
);

export const UnverifiedIcon = () => (
  <svg {...base}>
    <path d="M8 2.4 14 13H2Z" />
    <path d="M8 6.6v3" />
    <path d="M8 11.4h.01" />
  </svg>
);

export const DecidedIcon = () => (
  <svg {...base}>
    <path d="M2.6 8.4 6.2 12 13.4 4.4" />
  </svg>
);

export const PageIcon = () => (
  <svg {...base}>
    <path d="M3.4 1.9h6l3.2 3.2v9H3.4Z" />
    <path d="M9.4 1.9v3.2h3.2" />
  </svg>
);

export const TranscriptIcon = () => (
  <svg {...base}>
    <path d="M2.6 4h10.8M2.6 7.2h10.8M2.6 10.4h7.4M2.6 13.6h5" />
  </svg>
);

export const SignOutIcon = () => (
  <svg {...base}>
    <path d="M6.2 13.6H3.4V2.4h2.8" />
    <path d="M9.8 11 12.8 8 9.8 5" />
    <path d="M12.8 8H6.6" />
  </svg>
);
