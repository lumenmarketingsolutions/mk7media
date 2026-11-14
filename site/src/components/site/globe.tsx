"use client";

import createGlobe from "cobe";
import { useEffect, useRef } from "react";

const BEIRUT: [number, number] = [33.89, 35.5];
const PLACES: { name: string; loc: [number, number] }[] = [
  { name: "New York", loc: [40.71, -74.0] },
  { name: "Los Angeles", loc: [34.05, -118.24] },
  { name: "Toronto", loc: [43.65, -79.38] },
  { name: "London", loc: [51.5, -0.12] },
  { name: "Paris", loc: [48.86, 2.35] },
  { name: "Yerevan", loc: [40.18, 44.51] },
  { name: "Dubai", loc: [25.2, 55.27] },
  { name: "Doha", loc: [25.29, 51.53] },
  { name: "Riyadh", loc: [24.71, 46.68] },
  { name: "Sydney", loc: [-33.87, 151.21] },
];

export function Globe({ className = "" }: { className?: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const drag = useRef<number | null>(null);
  const offset = useRef(0);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    let phi = 3.6; // starts just west of Beirut and rotates it into view
    let globe: ReturnType<typeof createGlobe> | null = null;
    let raf = 0;
    let visible = true;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    const start = () => {
      const w = el.offsetWidth;
      if (!w || globe) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      globe = createGlobe(el, {
        devicePixelRatio: dpr,
        width: w * dpr,
        height: w * dpr,
        phi,
        theta: 0.28,
        dark: 1,
        diffuse: 1.4,
        mapSamples: 16000,
        mapBrightness: 5,
        mapBaseBrightness: 0.02,
        baseColor: [0.16, 0.16, 0.19],
        markerColor: [0.73, 0.65, 1],
        glowColor: [0.09, 0.09, 0.12],
        markers: [{ location: BEIRUT, size: 0.08 }, ...PLACES.map((p) => ({ location: p.loc, size: 0.035 }))],
        arcs: PLACES.map((p) => ({ from: BEIRUT, to: p.loc })),
        arcColor: [0.73, 0.65, 1],
        arcWidth: 0.6,
        arcHeight: 0.3,
        markerElevation: 0.01,
        opacity: 0.9,
      });
      requestAnimationFrame(() => (el.style.opacity = "1"));
    };

    const tick = () => {
      if (drag.current === null && !reduce) phi += 0.0025;
      globe?.update({ phi: phi + offset.current });
      raf = visible ? requestAnimationFrame(tick) : 0;
    };

    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible) {
        start();
        if (!raf) tick();
      }
    });
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
      globe?.destroy();
    };
  }, []);

  return (
    <div className={`relative aspect-square w-full ${className}`}>
      <canvas
        ref={canvas}
        className="size-full cursor-grab opacity-0 transition-opacity duration-1000"
        style={{ touchAction: "pan-y" }}
        onPointerDown={(e) => (drag.current = e.clientX - offset.current * 200)}
        onPointerUp={() => (drag.current = null)}
        onPointerOut={() => (drag.current = null)}
        onPointerMove={(e) => {
          if (drag.current !== null) offset.current = (e.clientX - drag.current) / 200;
        }}
      />
    </div>
  );
}

export const GLOBE_PLACES = PLACES.map((p) => p.name);
