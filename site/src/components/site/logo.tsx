/* Logo #5 (chosen): "MK" in Inter Tight extra bold + an angled violet 7. */
export function Logo({ size = 25 }: { size?: number }) {
  return (
    <span
      className="inline-flex items-baseline font-extrabold leading-none tracking-[-0.065em] text-text"
      style={{ fontSize: size }}
      aria-label="MK7 Media"
    >
      <span aria-hidden>MK</span>
      <svg
        aria-hidden
        viewBox="0 0 26 29"
        style={{ width: "0.66em", height: "0.73em", marginLeft: "0.04em", overflow: "visible" }}
        fill="none"
      >
        <path d="M1.5 3.1h22L9.6 28" stroke="#B9A7FF" strokeWidth="6.2" strokeLinecap="square" strokeLinejoin="miter" />
      </svg>
    </span>
  );
}

export const LogoMark = Logo;
