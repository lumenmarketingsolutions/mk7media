"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRef, useState } from "react";
import { SITE } from "@/lib/site";

const NEEDS = ["Paid ads", "Ecommerce", "Website", "WhatsApp", "CRM", "Automation", "Content", "SEO", "Not sure yet"];
const STEPS = ["Your details", "What you need", "Your goal"];

declare global {
  interface Window {
    fbq?: (...a: unknown[]) => void;
  }
}

function cookie(name: string) {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find((c) => c.startsWith(name + "="))?.split("=")[1] ?? "";
}

/* Three steps. Step 1 already sends the lead (email alert + Meta Lead, deduped with the pixel),
   so people who stop early are still captured. Steps 2 and 3 enrich the same lead. */
export function ContactForm() {
  const [step, setStep] = useState(0);
  const [data, setData] = useState({ name: "", whatsapp: "", email: "", business: "", goals: "" });
  const [needs, setNeeds] = useState<string[]>([]);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const eventId = useRef<string>("");

  const set = (k: keyof typeof data) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setData((d) => ({ ...d, [k]: e.target.value }));

  async function post(extra: Record<string, unknown>) {
    const r = await fetch("/api/inquiry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: data.name.trim(),
        whatsapp: data.whatsapp.trim(),
        email: data.email.trim(),
        business: data.business.trim(),
        website: data.business.trim(),
        fbp: cookie("_fbp"),
        fbc: cookie("_fbc"),
        ...extra,
      }),
    });
    if (!r.ok) throw new Error(String(r.status));
  }

  async function next(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    if (step === 0) {
      if (!data.name.trim()) return setErr("Add your name so we know who we're talking to.");
      if (data.whatsapp.replace(/\D/g, "").length < 10)
        return setErr("Add your full WhatsApp number with the country code, like +961 70 123 456.");
      setSending(true);
      try {
        eventId.current = crypto.randomUUID();
        await post({ event_id: eventId.current, source: "website_contact" });
        window.fbq?.("track", "Lead", {}, { eventID: eventId.current });
      } catch {
        setSending(false);
        return setErr("send");
      }
      setSending(false);
      setStep(1);
      return;
    }
    if (step === 1) {
      setStep(2);
      return;
    }
    setSending(true);
    try {
      await post({ is_enrichment: true, service_type: needs.join(", "), goals: data.goals.trim() });
    } catch {
      /* the lead is already in from step 1, so we still show success */
    }
    setSending(false);
    setDone(true);
  }

  const field =
    "mt-2 block h-[52px] w-full rounded-[8px] border border-white/[0.12] bg-[#16161b] px-4 text-[16px] text-text placeholder:text-[#6d6d78] outline-none transition-[border-color,box-shadow] focus:border-brand/70 focus:shadow-[0_0_0_3px_rgba(185,167,255,0.15)]";
  const label = "block text-[14px] text-text";

  return (
    <div
      className="relative overflow-hidden rounded-[12px] border border-white/10 p-6 sm:p-9"
      style={{ background: "linear-gradient(180deg,#121217 0%,#0c0c0f 100%)", boxShadow: "0 40px 80px -40px rgba(0,0,0,0.9)" }}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute -top-24 left-1/2 h-48 w-[80%] -translate-x-1/2 rounded-[50%] opacity-60 blur-3xl"
        style={{ background: "radial-gradient(closest-side, rgba(185,167,255,0.18), transparent)" }}
      />

      {done ? (
        <div className="relative py-12 text-center">
          <p className="text-[28px] font-bold tracking-[-0.035em]">
            You're in. <span className="text-brand">Talk soon.</span>
          </p>
          <p className="mx-auto mt-4 max-w-[36ch] text-[15px] leading-relaxed text-muted">
            We'll reach out on WhatsApp shortly to set a time for your strategy call.
          </p>
        </div>
      ) : (
        <form onSubmit={next} className="relative">
          {/* progress */}
          <div className="flex items-center justify-between">
            <p className="text-[13px] text-muted">
              Step {step + 1} of 3 <span className="mx-1.5 text-faint">·</span> <span className="text-text">{STEPS[step]}</span>
            </p>
            {step > 0 && (
              <button type="button" onClick={() => setStep((s) => s - 1)} className="cursor-pointer text-[13px] text-muted hover:text-text">
                ← Back
              </button>
            )}
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2">
            {STEPS.map((_, i) => (
              <span key={i} className="h-[3px] rounded-full transition-colors duration-500" style={{ background: i <= step ? "#B9A7FF" : "rgba(255,255,255,0.08)" }} />
            ))}
          </div>

          <div className="mt-8 min-h-[300px]">
            <AnimatePresence mode="wait">
              <motion.div
                key={step}
                initial={{ opacity: 0, x: 16 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -16 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              >
                {step === 0 && (
                  <div className="space-y-5">
                    <label className={label}>
                      Your name
                      <input value={data.name} onChange={set("name")} autoComplete="name" className={field} placeholder="Full name" autoFocus />
                    </label>
                    <label className={label}>
                      WhatsApp number
                      <input value={data.whatsapp} onChange={set("whatsapp")} inputMode="tel" autoComplete="tel" className={field} placeholder="+961 70 123 456" />
                    </label>
                    <div className="grid gap-5 sm:grid-cols-2">
                      <label className={label}>
                        Email <span className="text-faint">(optional)</span>
                        <input value={data.email} onChange={set("email")} type="email" autoComplete="email" className={field} placeholder="you@company.com" />
                      </label>
                      <label className={label}>
                        Business or website
                        <input value={data.business} onChange={set("business")} className={field} placeholder="Name or link" />
                      </label>
                    </div>
                  </div>
                )}

                {step === 1 && (
                  <fieldset>
                    <legend className="text-[20px] font-semibold tracking-[-0.025em]">What do you need help with?</legend>
                    <p className="mt-1.5 text-[14px] text-muted">Pick as many as you like.</p>
                    <div className="mt-6 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
                      {NEEDS.map((n) => {
                        const on = needs.includes(n);
                        return (
                          <button
                            type="button"
                            key={n}
                            onClick={() => setNeeds((x) => (on ? x.filter((y) => y !== n) : [...x, n]))}
                            className={`flex h-12 cursor-pointer items-center justify-between rounded-[8px] border px-4 text-[15px] transition-colors ${
                              on ? "border-brand/70 bg-brand/[0.1] text-text" : "border-white/[0.12] bg-[#16161b] text-muted hover:text-text"
                            }`}
                          >
                            {n}
                            <span className={`text-[12px] ${on ? "text-brand" : "text-transparent"}`}>✓</span>
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>
                )}

                {step === 2 && (
                  <label className="block">
                    <span className="block text-[20px] font-semibold tracking-[-0.025em]">Where do you want to be in six months?</span>
                    <span className="mt-1.5 block text-[14px] text-muted">Optional. A sentence or two is plenty.</span>
                    <textarea
                      value={data.goals}
                      onChange={set("goals")}
                      rows={5}
                      className={`${field} mt-6 h-auto py-3.5 leading-relaxed`}
                      placeholder="Double our orders, launch in the Gulf, stop losing leads..."
                    />
                  </label>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          {err && (
            <p className="mb-5 text-[14px] text-[#f0a3a3]">
              {err === "send" ? (
                <>
                  Something went wrong sending that. Message us on{" "}
                  <a className="underline" href={`https://wa.me/${SITE.whatsapp}`}>
                    WhatsApp
                  </a>{" "}
                  instead.
                </>
              ) : (
                err
              )}
            </p>
          )}

          <div className="flex flex-col items-stretch gap-4 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="submit"
              disabled={sending}
              className="relative isolate inline-flex h-[54px] cursor-pointer items-center justify-center rounded-full px-9 text-[15px] font-medium text-text transition-transform duration-300 hover:scale-[1.02] disabled:opacity-60"
              style={{
                background: "linear-gradient(180deg, rgba(255,255,255,0.14), rgba(255,255,255,0.05))",
                boxShadow:
                  "inset -3px -3px 0.5px -3.5px rgba(255,255,255,0.85), inset 1px 1px 1px -0.5px rgba(255,255,255,0.6), inset -1px -1px 1px -0.5px rgba(255,255,255,0.6), inset 0 0 6px 6px rgba(255,255,255,0.06), 0 10px 30px -12px rgba(0,0,0,0.9)",
              }}
            >
              {sending ? "One moment..." : step < 2 ? "Continue" : "Book my free strategy call"}
            </button>
            <p className="text-center text-[13px] text-faint sm:text-right">No pressure, no obligation.</p>
          </div>
        </form>
      )}
    </div>
  );
}
