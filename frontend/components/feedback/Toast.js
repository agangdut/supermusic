// frontend/components/feedback/Toast.js
"use client";
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

/**
 * Usage:
 * ------
 * // app root (e.g., pages/_app.js or layout component)
 * import ToastProvider from "@/components/feedback/Toast";
 * export default function App({ Component, pageProps }) {
 *   return <ToastProvider><Component {...pageProps} /></ToastProvider>;
 * }
 *
 * // anywhere in app:
 * import { useToast } from "@/components/feedback/Toast";
 * const { toast } = useToast();
 * toast.success("Done!", "MIDI conversion complete");
 * toast.error("Failed", "Please try again");
 */

const ToastCtx = createContext(null);

const VARIANTS = {
  info:    { ring: "ring-blue-200",  bg: "bg-white",  dot: "text-blue-600",  title: "text-gray-900", desc: "text-gray-600" },
  success: { ring: "ring-green-200", bg: "bg-white",  dot: "text-green-600", title: "text-gray-900", desc: "text-gray-600" },
  warning: { ring: "ring-amber-200", bg: "bg-white",  dot: "text-amber-600", title: "text-gray-900", desc: "text-gray-700" },
  error:   { ring: "ring-red-200",   bg: "bg-white",  dot: "text-red-600",   title: "text-gray-900", desc: "text-gray-700" },
};

function genId() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export default function ToastProvider({ children, position = "top-right", max = 5 }) {
  const [toasts, setToasts] = useState([]);

  const remove = useCallback((id) => {
    setToasts((t) => t.filter((x) => x.id !== id));
  }, []);

  const clear = useCallback(() => setToasts([]), []);

  const push = useCallback(
    (t) => {
      const id = t.id ?? genId();
      const next = { id, title: "", description: "", variant: "info", duration: 4000, ...t };
      setToasts((prev) => {
        const arr = [...prev, next];
        if (arr.length > max) arr.splice(0, arr.length - max);
        return arr;
      });
      return id;
    },
    [max]
  );

  const api = useMemo(() => {
    const base = (variant) => (title, description = "", opts = {}) =>
      push({ title, description, variant, ...opts });
    return {
      toast: {
        show: (opts) => push(opts),
        success: base("success"),
        info: base("info"),
        warning: base("warning"),
        error: base("error"),
        dismiss: remove,
        clear,
      },
    };
  }, [push, remove, clear]);

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <ToastViewport
        toasts={toasts}
        onDismiss={remove}
        position={position}
      />
    </ToastCtx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

function ToastViewport({ toasts, onDismiss, position }) {
  const posClass = {
    "top-right": "top-16 right-4 items-end",
    "top-left": "top-16 left-4 items-start",
    "bottom-right": "bottom-4 right-4 items-end",
    "bottom-left": "bottom-4 left-4 items-start",
  }[position] || "top-16 right-4 items-end";

  return (
    <div
      className={`pointer-events-none fixed z-[100] flex flex-col gap-2 ${posClass}`}
      aria-live="polite"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }) {
  const { id, title, description, variant = "info", duration = 4000 } = toast;
  const styles = VARIANTS[variant] || VARIANTS.info;

  // enter animation
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // auto-dismiss with pause-on-hover
  const timer = useRef(null);
  const startTime = useRef(Date.now());
  const remaining = useRef(duration);

  const startTimer = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(onDismiss, Math.max(0, remaining.current));
    startTime.current = Date.now();
  }, [onDismiss]);

  useEffect(() => {
    if (duration > 0) startTimer();
    return () => clearTimeout(timer.current);
  }, [duration, startTimer]);

  const onMouseEnter = () => {
    if (duration <= 0) return;
    clearTimeout(timer.current);
    remaining.current = Math.max(0, remaining.current - (Date.now() - startTime.current));
  };

  const onMouseLeave = () => {
    if (duration <= 0) return;
    startTimer();
  };

  return (
    <div
      role={variant === "error" ? "alert" : "status"}
      className={[
        "pointer-events-auto w-80 sm:w-96 rounded-xl border ring-1 shadow-lg",
        styles.bg,
        styles.ring,
        "transition-all duration-200",
        mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2",
      ].join(" ")}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="p-3">
        <div className="flex items-start gap-3">
          <span className={`mt-1 text-lg ${styles.dot}`}>
            {variant === "success" ? "✔️" : variant === "error" ? "⛔" : variant === "warning" ? "⚠️" : "ℹ️"}
          </span>
          <div className="min-w-0 flex-1">
            {title ? <div className={`font-medium ${styles.title} truncate`}>{title}</div> : null}
            {description ? (
              <div className={`mt-0.5 text-sm ${styles.desc}`}>{description}</div>
            ) : null}
          </div>
          <button
            onClick={onDismiss}
            className="ml-1 rounded-md px-2 py-1 text-sm text-gray-500 hover:bg-gray-50 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            aria-label="Dismiss notification"
          >
            ✕
          </button>
        </div>

        {duration > 0 && (
          <Progress duration={duration} start={startTime} remainingRef={remaining} />
        )}
      </div>
    </div>
  );
}

function Progress({ duration, start, remainingRef }) {
  const [pct, setPct] = useState(100);

  useEffect(() => {
    let raf;
    const tick = () => {
      const elapsed = Date.now() - start.current;
      const remaining = Math.max(0, remainingRef.current - elapsed);
      const nextPct = Math.max(0, Math.min(100, (remaining / duration) * 100));
      setPct(nextPct);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [duration, start, remainingRef]);

  return (
    <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-gray-100">
      <div
        className="h-full bg-gray-300 transition-[width] duration-100"
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      />
    </div>
  );
}
