"use client";
import { useEffect, useRef } from "react";

/**
 * Generic slide-over panel with backdrop.
 * Props:
 *  - open: boolean
 *  - onClose: () => void
 *  - title?: string
 *  - side?: "right" | "left" (default "right")
 *  - children: ReactNode
 *  - footer?: ReactNode
 */
export default function SlideOver({
  open,
  onClose,
  title = "",
  side = "right",
  children,
  footer,
}) {
  const closeBtnRef = useRef(null);

  // ESC to close + focus management + body scroll lock
  useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose?.();
    }
    if (open) {
      document.addEventListener("keydown", onKey);
      // focus the close button on open
      setTimeout(() => closeBtnRef.current?.focus(), 0);
      // lock scroll
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.removeEventListener("keydown", onKey);
        document.body.style.overflow = prev;
      };
    }
  }, [open, onClose]);

  const sideClasses =
    side === "left"
      ? "left-0 -translate-x-full data-[open=true]:translate-x-0"
      : "right-0 translate-x-full data-[open=true]:translate-x-0";

  return (
    <div
      aria-hidden={!open}
      className={`fixed inset-0 z-40 ${
        open ? "pointer-events-auto" : "pointer-events-none"
      }`}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        className={`absolute inset-0 bg-black/40 transition-opacity ${
          open ? "opacity-100" : "opacity-0"
        }`}
        aria-hidden="true"
      />
      {/* Panel */}
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title || "Panel"}
        data-open={open ? "true" : "false"}
        className={`absolute top-0 h-full w-full sm:w-[28rem] bg-white shadow-2xl transition-transform duration-300 ease-out ${sideClasses}`}
      >
        <header className="flex items-center justify-between gap-4 px-5 py-4 border-b">
          <h2 className="text-lg font-semibold truncate">{title}</h2>
          <button
            ref={closeBtnRef}
            onClick={onClose}
            className="inline-flex items-center rounded-md border px-3 py-1.5 text-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Close panel"
          >
            ✕
          </button>
        </header>

        <div className="overflow-y-auto h-[calc(100%-4rem-4rem)] px-5 py-4">
          {children}
        </div>

        {footer && (
          <footer className="px-5 py-3 border-t bg-gray-50">{footer}</footer>
        )}
      </section>
    </div>
  );
}
