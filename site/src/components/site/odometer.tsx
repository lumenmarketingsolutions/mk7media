"use client";

import { animate, motion, useInView, useMotionValue, useTransform, type MotionValue } from "motion/react";
import { useEffect, useRef } from "react";
import useMeasure from "react-use-measure";

/* Rolling odometer count up (the "slide" effect from the count-up prompt). */
function Digit({ spring, place }: { spring: MotionValue<number>; place: number }) {
  const [ref, { height }] = useMeasure();
  const y = useTransform(spring, (v) => (height ? -((Math.abs(v) / place) % 10) * height : 0));
  return (
    <span className="relative inline-block h-[1em] w-[0.62em] overflow-hidden text-center leading-none tabular-nums">
      <span ref={ref} className="invisible block">0</span>
      <motion.span style={{ y }} className="absolute inset-x-0 top-0 flex flex-col">
        {Array.from({ length: 11 }, (_, i) => (
          <span key={i} className="flex items-center justify-center" style={{ height: height || "1em" }}>
            {i % 10}
          </span>
        ))}
      </motion.span>
    </span>
  );
}

export function Odometer({
  to,
  prefix = "",
  suffix = "",
  className,
  duration = 1.6,
}: {
  to: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  duration?: number;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const spring = useMotionValue(0);
  useEffect(() => {
    if (!inView) return;
    const c = animate(spring, to, { duration, ease: [0.16, 1, 0.3, 1] });
    return () => c.stop();
  }, [inView, spring, to, duration]);

  const str = to.toLocaleString("en-US");
  const digitCount = str.replace(/\D/g, "").length;
  let d = 0;

  return (
    <span ref={ref} className={className}>
      <span className="sr-only">{`${prefix}${str}${suffix}`}</span>
      <span aria-hidden className="inline-flex items-baseline">
        {prefix}
        {str.split("").map((ch, i) => {
          if (!/\d/.test(ch)) return <span key={i}>{ch}</span>;
          const place = Math.pow(10, digitCount - 1 - d++);
          return <Digit key={i} spring={spring} place={place} />;
        })}
        {suffix}
      </span>
    </span>
  );
}
