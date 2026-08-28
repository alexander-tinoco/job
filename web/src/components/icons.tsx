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

export const EyeIcon = () => (
  <svg {...base}>
    <path d="M1.6 8S3.9 3.6 8 3.6 14.4 8 14.4 8 12.1 12.4 8 12.4 1.6 8 1.6 8Z" />
    <circle cx="8" cy="8" r="2.1" />
  </svg>
);

export const EyeOffIcon = () => (
  <svg {...base}>
    <path d="M6.3 4A6.7 6.7 0 0 1 8 3.8c4.1 0 6.4 4.2 6.4 4.2a12 12 0 0 1-2 2.6" />
    <path d="M3.9 4.9A12 12 0 0 0 1.6 8s2.3 4.2 6.4 4.2c1 0 1.9-.2 2.7-.6" />
    <path d="M6.7 6.7a1.9 1.9 0 0 0 2.7 2.7" />
    <path d="M2 2l12 12" />
  </svg>
);

export const CollapseIcon = () => (
  <svg {...base}>
    <path d="M2.4 2.8v10.4" />
    <path d="M13.6 8H6.2" />
    <path d="M8.9 5.3 6.2 8l2.7 2.7" />
  </svg>
);

export const ExpandIcon = () => (
  <svg {...base}>
    <path d="M2.4 2.8v10.4" />
    <path d="M6.2 8h7.4" />
    <path d="M10.9 5.3 13.6 8l-2.7 2.7" />
  </svg>
);


export const ShareIcon = () => (
  <svg {...base}>
    <path d="M11 5.2 8 2.2 5 5.2" />
    <path d="M8 2.2v8.4" />
    <path d="M3.4 9.2v3.2a1.4 1.4 0 0 0 1.4 1.4h6.4a1.4 1.4 0 0 0 1.4-1.4V9.2" />
  </svg>
);

/** Two plates on a balance: the comparison, not a verdict. */
export const CompareIcon = () => (
  <svg {...base}>
    <path d="M8 2.4v11.2" />
    <path d="M2.6 5.4h10.8" />
    <path d="M2.2 10.2 4.6 5.4 7 10.2" />
    <path d="M9 10.2l2.4-4.8 2.4 4.8" />
  </svg>
);
