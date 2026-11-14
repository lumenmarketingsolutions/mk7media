"use client";

import { liquidMetalFragmentShader, ShaderMount } from "@paper-design/shaders";
import { useEffect, useRef, useState } from "react";

/* Liquid metal ring button, adapted from the 21st.dev prompt.
   A WebGL shader paints a moving chrome ring; the face sits on top. */
export function LiquidMetalButton({
  label = "Book a strategy call",
  radius = 999,
  height = 48,
  href,
}: {
  label?: string;
  radius?: number;
  height?: number;
  href?: string;
}) {
  const shaderRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mount = useRef<any>(null);
  const [pressed, setPressed] = useState(false);

  useEffect(() => {
    if (!shaderRef.current) return;
    mount.current = new ShaderMount(
      shaderRef.current,
      liquidMetalFragmentShader,
      {
        u_colorBack: [0, 0, 0, 0],
        u_colorTint: [1, 1, 1, 1],
        u_repetition: 4,
        u_softness: 0.5,
        u_shiftRed: 0.3,
        u_shiftBlue: 0.3,
        u_distortion: 0,
        u_contour: 0,
        u_angle: 45,
        u_shape: 0,
        u_isImage: false,
        u_imageAspectRatio: 1,
        u_fit: 0,
        u_scale: 1,
        u_rotation: 0,
        u_offsetX: 0,
        u_offsetY: 0,
        u_originX: 0.5,
        u_originY: 0.5,
        u_worldWidth: 0,
        u_worldHeight: 0,
      },
      undefined,
      0.6,
    );
    return () => mount.current?.dispose?.();
  }, []);

  const Tag = href ? "a" : "button";
  return (
    <Tag
      href={href}
      onMouseEnter={() => mount.current?.setSpeed?.(1)}
      onMouseLeave={() => {
        mount.current?.setSpeed?.(0.6);
        setPressed(false);
      }}
      onMouseDown={() => setPressed(true)}
      onMouseUp={() => setPressed(false)}
      className="group relative inline-flex cursor-pointer items-center justify-center overflow-hidden px-7 text-[14px] font-medium tracking-[-0.01em] text-[#E9E9EC] transition-transform duration-200"
      style={{
        height,
        borderRadius: radius,
        transform: pressed ? "translateY(1px) scale(0.985)" : undefined,
        boxShadow: "0 1px 0 rgba(255,255,255,0.06), 0 12px 28px -12px rgba(0,0,0,0.8)",
      }}
    >
      <div ref={shaderRef} aria-hidden className="absolute inset-0 [&>canvas]:!h-full [&>canvas]:!w-full" />
      <span
        aria-hidden
        className="absolute inset-[2px]"
        style={{
          borderRadius: Math.max(0, radius - 2),
          background: "linear-gradient(180deg, #1d1d21 0%, #050506 100%)",
          boxShadow: pressed ? "inset 0 2px 4px rgba(0,0,0,0.5)" : "inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
      />
      <span className="relative z-10">{label}</span>
    </Tag>
  );
}
