"use client";
import React, { forwardRef } from "react";

const VARIANTS = {
  primary: "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300",
  secondary: "bg-white text-gray-900 border hover:bg-gray-50 disabled:bg-gray-100",
  ghost: "bg-transparent text-gray-700 hover:bg-gray-100",
};
const SIZES = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-11 px-5 text-base",
};

const Spinner = () => (
  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
  </svg>
);

const Button = forwardRef(function Button(
  { as: Comp = "button", variant = "primary", size = "md", loading = false, className = "", children, ...props },
  ref
) {
  const base =
    "inline-flex items-center justify-center rounded-lg border transition focus:outline-none focus:ring-2 focus:ring-blue-500 gap-2";
  return (
    <Comp
      ref={ref}
      className={`${base} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      aria-busy={loading || undefined}
      disabled={props.disabled || loading}
      {...props}
    >
      {loading && <Spinner />}
      <span>{children}</span>
    </Comp>
  );
});

export default Button;
