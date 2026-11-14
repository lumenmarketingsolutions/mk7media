"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Logo } from "./logo";
import { Cta } from "./cta";
import { NAV, SERVICES, CTA_HREF } from "@/lib/site";

export function Nav() {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
  }, [open]);

  return (
    <header
      className="fixed inset-x-0 top-0 z-50 transition-colors duration-300"
      style={{
        background: scrolled || open ? "rgba(9,9,11,0.78)" : "transparent",
        backdropFilter: scrolled || open ? "blur(16px)" : undefined,
        WebkitBackdropFilter: scrolled || open ? "blur(16px)" : undefined,
        borderBottom: `1px solid ${scrolled ? "var(--line-soft)" : "transparent"}`,
      }}
    >
      <nav className="wrap flex h-16 items-center justify-between">
        <Link href="/" aria-label="MK7 Media home" onClick={() => setOpen(false)}>
          <Logo />
        </Link>

        <div className="hidden items-center gap-9 md:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="text-[14px] text-muted transition-colors hover:text-text">
              {n.label}
            </Link>
          ))}
        </div>

        <div className="hidden md:block">
          <Cta href={CTA_HREF} className="h-10 px-5 text-[14px]">
            Let&apos;s talk
          </Cta>
        </div>

        <button
          type="button"
          aria-label={open ? "Close menu" : "Open menu"}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="relative -mr-2 flex size-10 items-center justify-center md:hidden"
        >
          <span className="relative block h-3 w-5">
            <span
              className="absolute left-0 block h-px w-5 bg-text transition-all duration-300"
              style={{ top: open ? 6 : 0, transform: open ? "rotate(45deg)" : undefined }}
            />
            <span
              className="absolute left-0 block h-px w-5 bg-text transition-all duration-300"
              style={{ top: open ? 6 : 12, transform: open ? "rotate(-45deg)" : undefined }}
            />
          </span>
        </button>
      </nav>

      {/* mobile menu */}
      <div
        className="overflow-y-auto transition-[max-height,opacity] duration-500 md:hidden"
        style={{ maxHeight: open ? "calc(100svh - 64px)" : 0, opacity: open ? 1 : 0 }}
      >
        <div className="wrap pt-6 pb-10">
          <p className="eyebrow">Services</p>
          <ul className="mt-4">
            {SERVICES.map((s) => (
              <li key={s.slug}>
                <Link
                  href={`/services/${s.slug}`}
                  onClick={() => setOpen(false)}
                  className="flex items-center justify-between border-b border-line-soft py-3.5 text-[17px] font-medium tracking-[-0.02em]"
                >
                  {s.name}
                  <span className="text-faint">→</span>
                </Link>
              </li>
            ))}
          </ul>
          <ul className="mt-8 flex items-center gap-8">
            {NAV.filter((n) => n.label !== "Services").map((n) => (
              <li key={n.href}>
                <Link href={n.href} onClick={() => setOpen(false)} className="text-[15px] text-muted">
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-10">
            <Cta href={CTA_HREF} className="w-full">
              Book a free strategy call
            </Cta>
          </div>
        </div>
      </div>
    </header>
  );
}
