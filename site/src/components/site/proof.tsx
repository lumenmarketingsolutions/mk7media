"use client";

import { useInView } from "motion/react";
import { useRef } from "react";
import useMeasure from "react-use-measure";
import { RevealHeading, FadeUp } from "./reveal";
import { Odometer } from "./odometer";

/* NOTE: $2,000,000 / 4.5x / 30M / 30+ are inside the ranges you gave.
   Confirm the exact figures before launch. */

function ViewsCard() {
  const [measure, { width, height }] = useMeasure();
  const view = useRef<HTMLDivElement>(null);
  const inView = useInView(view, { margin: "0px" });
  // the dot travels the inner frame: 10% in from the sides, 12% from top and bottom
  const tw = Math.max(0, width * 0.8 - 6);
  const th = Math.max(0, height * 0.76 - 6);
  return (
    <div
      ref={(n) => {
        measure(n);
        view.current = n;
      }}
      className="relative mx-auto aspect-[4/3] w-full max-w-[420px] overflow-hidden rounded-[10px] border border-white/10 bg-[#0c0c0f]"
      style={{ ["--tw" as string]: `${tw}px`, ["--th" as string]: `${th}px` }}
    >
      {/* light ray */}
      <div
        aria-hidden
        className="absolute -top-1/3 -left-1/4 h-[120%] w-[70%] rotate-[35deg] opacity-60 blur-2xl"
        style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.22), transparent 70%)" }}
      />
      {/* frame lines */}
      <span aria-hidden className="absolute inset-x-0 top-[14%] h-px bg-white/[0.07]" />
      <span aria-hidden className="absolute inset-x-0 bottom-[14%] h-px bg-white/[0.07]" />
      <span aria-hidden className="absolute inset-y-0 left-[10%] w-px bg-white/[0.07]" />
      <span aria-hidden className="absolute inset-y-0 right-[10%] w-px bg-white/[0.07]" />
      {/* travelling dot */}
      <span
        aria-hidden
        className="absolute top-[12%] left-[10%] z-10 size-1.5 rounded-full bg-white will-change-transform"
        style={{
          animation: "orbit-dot 7s linear infinite",
          animationPlayState: inView ? "running" : "paused",
          boxShadow: "0 0 12px 2px rgba(255,255,255,0.6)",
        }}
      />
      <div className="relative flex h-full flex-col items-center justify-center text-center">
        <p
          className="text-[64px] leading-none font-bold tracking-[-0.05em] sm:text-[76px]"
          style={{
            background: "linear-gradient(180deg,#ffffff 20%, rgba(255,255,255,0.35))",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
            color: "transparent",
          }}
        >
          30M+
        </p>
        <p className="mt-3 text-[14px] text-text">views on client reels</p>
      </div>
    </div>
  );
}

export function Proof() {
  return (
    <section className="section" id="results">
      <div className="wrap">
        <p className="eyebrow">Since 2023</p>
        <RevealHeading
          className="h-section mt-4 max-w-[16ch]"
          parts={["We would rather", { t: "show you the numbers.", accent: true }]}
        />

        <div className="mt-16 grid items-center gap-14 border-b border-line pb-16 md:mt-20 md:grid-cols-[1.2fr_1fr] md:gap-16">
          <FadeUp>
            <p className="text-[56px] leading-none font-semibold tracking-[-0.05em] sm:text-[88px]">
              <Odometer to={2000000} prefix="$" suffix="+" />
            </p>
            <p className="mt-5 text-[17px] font-medium tracking-[-0.02em]">In ad spend managed</p>
            <p className="mt-2 max-w-[36ch] text-[15px] leading-relaxed text-muted">
              Across Meta and Google, for brands in nine countries. Every dollar tracked to what it brought back.
            </p>
          </FadeUp>
          <FadeUp delay={0.1}>
            <ViewsCard />
          </FadeUp>
        </div>

        <div className="mt-14 grid grid-cols-3 gap-x-4 text-center md:text-left">
          {[
            { v: "4.5x", l: "Average return on ad spend" },
            { v: "30+", l: "Brands grown" },
            { v: "9", l: "Countries served" },
          ].map((s, i) => (
            <FadeUp key={s.l} delay={i * 0.08}>
              <p className="text-[34px] leading-none font-semibold tracking-[-0.045em] sm:text-[40px] md:text-[48px]">{s.v}</p>
              <p className="mx-auto mt-3 max-w-[14ch] text-[12px] leading-snug text-muted sm:text-[13px] md:mx-0 md:max-w-none">{s.l}</p>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}
