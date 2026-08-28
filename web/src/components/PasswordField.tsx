import { useState } from "react";
import { EyeIcon, EyeOffIcon } from "./icons";

/**
 * A password field you can read.
 *
 * Hiding what someone types is a defence against a shoulder, not against an
 * attacker, and it causes far more failed sign-ins than it prevents. The toggle
 * stays off by default and never persists.
 */
export function PasswordField({
  value,
  onChange,
  autoComplete = "current-password",
}: {
  value: string;
  onChange: (value: string) => void;
  autoComplete?: string;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <div className="password">
      <input
        className="field"
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        className="peek"
        onClick={() => setVisible((current) => !current)}
        aria-pressed={visible}
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
      >
        {/* Crossed out while the password is hidden; open once it is readable. */}
        {visible ? <EyeIcon /> : <EyeOffIcon />}
      </button>
    </div>
  );
}
