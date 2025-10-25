"use client";
import React from "react";

export default function TextField({
  id,
  name,
  type = "text",
  label,
  value,
  onChange,
  placeholder,
  helperText,
  error,
  required,
  leftSlot,
  rightSlot,
  className = "",
  ...props
}) {
  const base =
    "block w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 " +
    (error ? "border-red-400" : "border-gray-300");
  return (
    <label className={`block ${className}`}>
      {label && (
        <span className="mb-1 block text-sm font-medium text-gray-700">
          {label} {required ? <span className="text-red-500">*</span> : null}
        </span>
      )}
      <div className="relative">
        {leftSlot && <div className="absolute inset-y-0 left-2 flex items-center">{leftSlot}</div>}
        <input
          id={id}
          name={name}
          type={type}
          value={value}
          onChange={onChange}
          required={required}
          placeholder={placeholder}
          className={`${base} ${leftSlot ? "pl-8" : ""} ${rightSlot ? "pr-8" : ""}`}
          {...props}
        />
        {rightSlot && <div className="absolute inset-y-0 right-2 flex items-center">{rightSlot}</div>}
      </div>
      {helperText && !error && <p className="mt-1 text-xs text-gray-500">{helperText}</p>}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </label>
  );
}
