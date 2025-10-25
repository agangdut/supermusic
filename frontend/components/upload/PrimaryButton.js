"use client";

export default function PrimaryButton({
  children,
  className = "",
  ...props
}) {
  return (
    <button
      {...props}
      className={
        "inline-flex items-center justify-center rounded-md px-3 py-2 text-sm font-medium " +
        "bg-gradient-to-r from-purple-500 to-indigo-500 text-white " +
        "shadow-[0_10px_30px_rgba(168,85,247,0.4)] " +
        "hover:shadow-[0_14px_40px_rgba(168,85,247,0.6)] " +
        "focus:outline-none focus:ring-2 focus:ring-purple-500/40 " +
        "transition-all " +
        className
      }
    >
      {children}
    </button>
  );
}
