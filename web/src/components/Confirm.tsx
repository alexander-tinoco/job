import { useEffect, useRef } from "react";

/**
 * A native <dialog>, so the browser supplies the focus trap, the escape key and
 * the inert background rather than us reimplementing them badly.
 *
 * Used only where an action is hard to take back: signing out loses your place
 * in a long review, and an application cannot be unsent.
 */
export function Confirm({
  open,
  title,
  body,
  confirmLabel,
  destructive,
  busy,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="confirm" onCancel={onCancel} onClose={onCancel}>
      <h2>{title}</h2>
      <p>{body}</p>
      <div className="confirm-actions">
        <button className="control" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <button
          className={destructive ? "control" : "control primary"}
          onClick={onConfirm}
          disabled={busy}
          autoFocus
        >
          {busy ? "Working…" : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
