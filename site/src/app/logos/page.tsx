import { Inter_Tight } from "next/font/google";

export const metadata = { title: "Logo directions", robots: { index: false, follow: false } };

const tight = Inter_Tight({ subsets: ["latin"], weight: ["500", "600", "700", "800"] });

const V = "#B9A7FF";
const T = "#F2F2F3";

// Regular heptagon (7 sides, for the 7 in MK7), radius 20 around (24,24)
const HEPT: [number, number][] = Array.from({ length: 7 }, (_, k) => {
  const a = ((-90 + (k * 360) / 7) * Math.PI) / 180;
  return [24 + 20 * Math.cos(a), 24 + 20 * Math.sin(a)];
});
const pts = (arr: [number, number][]) => arr.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
const STAR = [0, 3, 6, 2, 5, 1, 4].map((i) => HEPT[i]);

type Mark = (p: { size: number }) => React.ReactElement;

const marks: { id: string; name: string; idea: string; Mark: Mark; word?: "full" | "short" }[] = [
  {
    id: "1",
    name: "M7 ligature",
    idea: "One continuous line: the M runs straight into a 7. Sharp, simple, works tiny. Modern agency feel.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <path d="M8 37V11l13 15 13-15h7L29 37" stroke={T} strokeWidth="3.6" strokeLinejoin="miter" strokeLinecap="square" />
      </svg>
    ),
  },
  {
    id: "2",
    name: "Heptagon, refined",
    idea: "The current mark grown up. Seven sides for the 7, cleaner lines, violet only on the frame. Keeps brand continuity.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <polygon points={pts(HEPT)} stroke={V} strokeWidth="1.6" />
        <path d="M16 31V18l8 8.5 8-8.5v13" stroke={T} strokeWidth="2.6" strokeLinejoin="miter" strokeLinecap="square" />
      </svg>
    ),
  },
  {
    id: "3",
    name: "Seven point star",
    idea: "A heptagram: a seven point star drawn in one line. Fits the dark universe vibe and quietly says 7.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <polygon points={pts(STAR)} stroke={T} strokeWidth="1.5" strokeLinejoin="miter" />
        <circle cx="24" cy="24" r="2.4" fill={V} />
      </svg>
    ),
  },
  {
    id: "4",
    name: "Ascend",
    idea: "Three rising bars that also read as an M. Growth in one glance. The last bar is the only color.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <rect x="8" y="24" width="8" height="16" fill={T} />
        <rect x="20" y="16" width="8" height="24" fill={T} />
        <rect x="32" y="8" width="8" height="32" fill={V} />
      </svg>
    ),
  },
  {
    id: "5",
    name: "Wordmark only",
    idea: "No symbol, just MK7 in tight bold type with the 7 cut at an angle. Confident, like Linear or Vercel.",
    word: "short",
    Mark: ({ size }) => (
      <svg width={size * 1.9} height={size} viewBox="0 0 92 48" fill="none">
        <text x="0" y="37" fontSize="38" fontWeight="800" letterSpacing="-2.4" fill={T} className={tight.className}>
          MK
        </text>
        <path d="M60 11h24L69 38" stroke={V} strokeWidth="6.2" strokeLinecap="square" strokeLinejoin="miter" />
      </svg>
    ),
  },
  {
    id: "6",
    name: "Orbit",
    idea: "A planet with one moon in orbit. The moon is the client, we keep it moving. Softest and most 'universe'.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <ellipse cx="24" cy="24" rx="19" ry="7.5" stroke="rgba(242,242,243,0.45)" strokeWidth="1.3" transform="rotate(-24 24 24)" />
        <circle cx="24" cy="24" r="8" fill={T} />
        <circle cx="40.2" cy="16.6" r="2.6" fill={V} />
      </svg>
    ),
  },
  {
    id: "7",
    name: "Monogram tile",
    idea: "The M7 ligature inside a sharp edged tile, like an app icon. Strongest as a profile picture and favicon.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <defs>
          <linearGradient id="tile" x1="0" y1="0" x2="48" y2="48">
            <stop stopColor="#2A2440" />
            <stop offset="1" stopColor="#0E0C16" />
          </linearGradient>
        </defs>
        <rect x="2" y="2" width="44" height="44" rx="8" fill="url(#tile)" stroke="rgba(185,167,255,0.35)" />
        <path d="M12 34V14l10 11.5L32 14h5l-9 20" stroke={T} strokeWidth="3" strokeLinejoin="miter" strokeLinecap="square" />
      </svg>
    ),
  },
  {
    id: "8",
    name: "Split M",
    idea: "An M made of two sharp blocks with a gap of light between them. Feels architectural and premium.",
    Mark: ({ size }) => (
      <svg width={size} height={size} viewBox="0 0 48 48" fill="none">
        <path d="M7 40V8l15 17v15H7z" fill={T} />
        <path d="M41 40V8L26 25v15h15z" fill={V} />
      </svg>
    ),
  },
];

function Wordmark({ kind }: { kind?: "full" | "short" }) {
  if (kind === "short") return null;
  return <span className={`${tight.className} text-[22px] font-semibold tracking-[-0.03em] text-[#F2F2F3]`}>MK7 Media</span>;
}

export default function Logos() {
  return (
    <main className={`${tight.className} min-h-screen bg-[#09090B] text-[#F2F2F3]`}>
      <div className="mx-auto max-w-5xl px-5 py-16 sm:px-8 sm:py-24">
        <p className="text-[12px] text-[#8D8D96]">MK7 logo directions · palette B</p>
        <h1 className="mt-3 text-[28px] font-bold tracking-[-0.03em]">Pick a number</h1>
        <p className="mt-2 max-w-[56ch] text-[15px] text-[#8D8D96]">
          Each shows the mark large, with the name, and at favicon size (the tiny one in a browser tab). These are directions:
          once you pick, I refine the winner properly.
        </p>

        <div className="mt-12 grid gap-px bg-[#222228] sm:grid-cols-2">
          {marks.map(({ id, name, idea, Mark, word }) => (
            <section key={id} className="bg-[#09090B] px-6 py-10 sm:px-8">
              <p className="text-[12px] text-[#8D8D96]">
                <span className="text-[#F2F2F3]">{id}</span>
                <span className="mx-2">·</span>
                {name}
              </p>
              <div className="mt-10 flex h-28 items-center">
                <Mark size={96} />
              </div>
              <div className="mt-8 flex items-center gap-3">
                <Mark size={30} />
                <Wordmark kind={word} />
              </div>
              <div className="mt-6 flex items-center gap-4">
                <span className="flex items-center gap-2 rounded-[6px] border border-[#222228] bg-[#111114] px-2.5 py-1.5">
                  <Mark size={16} />
                  <span className="text-[11px] text-[#8D8D96]">mk7media.com</span>
                </span>
                <span className="flex size-10 items-center justify-center rounded-full border border-[#222228] bg-[#111114]">
                  <Mark size={22} />
                </span>
              </div>
              <p className="mt-8 max-w-[44ch] text-[13px] leading-relaxed text-[#8D8D96]">{idea}</p>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
