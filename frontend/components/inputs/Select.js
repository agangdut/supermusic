"use client";
import React from "react";

export default function Select({
  id,
  name,
  label,
  value,
  onChange,
  options = [],
  placeholder = "Select…",
  helperText,
  error,
  required,
  className = "",
  ...props
}) {
  const inputCls =
    "block w-full rounded-lg border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 " +
    (error ? "border-red-400" : "border-gray-300");
  return (
    <label className={`block ${className}`}>
      {label && (
        <span className="mb-1 block text-sm font-medium text-gray-700">
          {label} {required ? <span className="text-red-500">*</span> : null}
        </span>
      )}
      <select
        id={id}
        name={name}
        value={value}
        onChange={onChange}
        required={required}
        className={inputCls}
        {...props}
      >
        <option value="" disabled hidden>
          {placeholder}
        </option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {helperText && !error && <p className="mt-1 text-xs text-gray-500">{helperText}</p>}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </label>
  );
}
