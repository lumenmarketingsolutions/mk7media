import Link from "next/link";
import { cn } from "@/lib/utils";

/* The one button component for the whole site. Change the look here and it changes everywhere.
   "glass" = rounded liquid glass (Kendall's pick). A faint frosted base keeps it visible on flat black. */
export function Cta({
  href,
  children,
  variant = "glass",
  className,
  size = "md",
}: {
  href: string;
  children: React.ReactNode;
  variant?: "glass" | "link";
  className?: string;
  size?: "md" | "lg";
}) {
  if (variant === "link") {
    return (
      <Link
        href={href}
        className={cn("group inline-flex items-center gap-2 text-[15px] text-text transition-colors hover:text-brand", className)}
      >
        {children}
        <span aria-hidden className="transition-transform duration-300 group-hover:translate-x-0.5">→</span>
      </Link>
    );
  }
  return (
    <Link
      href={href}
      className={cn(
        "relative isolate inline-flex shrink-0 items-center justify-center rounded-full font-medium tracking-[-0.01em] text-text transition-transform duration-300 hover:scale-[1.03] active:scale-[0.98]",
        size === "lg" ? "h-[52px] px-8 text-[15px]" : "h-12 px-7 text-[15px]",
        className,
      )}
    >
      {/* frosted base: always visible */}
      <span
        aria-hidden
        className="absolute inset-0 -z-10 rounded-full"
        style={{
          background: "linear-gradient(180deg, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0.04) 100%)",
          backdropFilter: "blur(14px) saturate(150%)",
          WebkitBackdropFilter: "blur(14px) saturate(150%)",
        }}
      />
      {/* glass edge and inner light */}
      <span
        aria-hidden
        className="absolute inset-0 rounded-full"
        style={{
          boxShadow:
            "inset 3px 3px 0.5px -3.5px rgba(255,255,255,0.09), inset -3px -3px 0.5px -3.5px rgba(255,255,255,0.85), inset 1px 1px 1px -0.5px rgba(255,255,255,0.6), inset -1px -1px 1px -0.5px rgba(255,255,255,0.6), inset 0 0 6px 6px rgba(255,255,255,0.06), inset 0 0 2px 2px rgba(255,255,255,0.05), 0 10px 30px -12px rgba(0,0,0,0.9)",
        }}
      />
      <span className="relative">{children}</span>
    </Link>
  );
}
