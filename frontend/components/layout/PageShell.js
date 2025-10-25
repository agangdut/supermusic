"use client";
import React from "react";
import Navbar from "./Navbar";

/**
 * PageShell composes Navbar and your page content.
 *
 * Props:
 *  - children: ReactNode (main content)
 *  - toolbar?: ReactNode (renders under Navbar; toolbar should be sticky itself)
 *  - onOpenLibrary?: () => void
 *  - onOpenNav?: () => void
 */
export default function PageShell({ children }) {
  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: 24 }}>
      <header style={{ marginBottom: 32 }}>
        <h1>SuperMusic</h1>
      </header>
      <main>{children}</main>
    </div>
  );
}
