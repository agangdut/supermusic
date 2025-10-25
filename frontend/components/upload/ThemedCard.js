"use client";

export default function ThemedCard({
  title,
  desc,
  rightSlot,
  footer,
  children,
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-[#0f172a] p-4 flex flex-col gap-4 w-full">
      <header className="flex items-start justify-between">
        <div>
          <h2 className="text-white font-semibold text-base leading-tight">
            {title}
          </h2>
          {desc && (
            <p className="text-gray-400 text-sm mt-1 leading-snug">
              {desc}
            </p>
          )}
        </div>

        {rightSlot ?? null}
      </header>

      <div className="flex flex-col gap-3">{children}</div>

      {footer && (
        <footer className="pt-2 border-t border-white/5 text-xs text-gray-500 flex items-center justify-between flex-wrap gap-2">
          {footer}
        </footer>
      )}
    </section>
  );
}

