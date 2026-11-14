import { siMeta, siShopify, siWhatsapp, siClaude, siInstagram, siYoutube, siTiktok } from "simple-icons";

/* iOS style app tiles. Rounded squircle, brand color face, soft top light. */
function Tile({ bg, children, label }: { bg: string; children: React.ReactNode; label: string }) {
  return (
    <span
      role="img"
      aria-label={label}
      className="relative flex size-full items-center justify-center overflow-hidden"
      style={{
        borderRadius: "23%",
        background: bg,
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.25), inset 0 -1px 0 rgba(0,0,0,0.2), 0 6px 14px -6px rgba(0,0,0,0.7)",
      }}
    >
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-1/2"
        style={{ background: "linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0))" }}
      />
      {children}
    </span>
  );
}

function Glyph({ path, color = "#fff", size = "58%" }: { path: string; color?: string; size?: string }) {
  return (
    <svg viewBox="0 0 24 24" style={{ width: size, height: size }} fill={color} aria-hidden className="relative">
      <path d={path} />
    </svg>
  );
}

export const AppIcon = {
  meta: () => (
    <Tile label="Meta ads" bg="linear-gradient(180deg,#1877F2 0%,#0057D9 100%)">
      <Glyph path={siMeta.path} size="62%" />
    </Tile>
  ),
  google: () => (
    <Tile label="Google ads" bg="linear-gradient(180deg,#FFFFFF 0%,#EDEEF2 100%)">
      <svg viewBox="0 0 48 48" className="relative" style={{ width: "56%", height: "56%" }} aria-hidden>
        <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
        <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
        <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
        <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
      </svg>
    </Tile>
  ),
  shopify: () => (
    <Tile label="Shopify stores" bg="linear-gradient(180deg,#A4CF5A 0%,#7AAB31 100%)">
      <Glyph path={siShopify.path} size="56%" />
    </Tile>
  ),
  whatsapp: () => (
    <Tile label="WhatsApp automation" bg="linear-gradient(180deg,#5EF07F 0%,#1DB954 100%)">
      <Glyph path={siWhatsapp.path} size="58%" />
    </Tile>
  ),
  highlevel: () => (
    <Tile label="HighLevel CRM" bg="linear-gradient(180deg,#1E2230 0%,#0E1018 100%)">
      <svg viewBox="0 0 24 24" className="relative" style={{ width: "58%", height: "58%" }} aria-hidden>
        <path d="M4 20V11H1.8L6 6l4.2 5H8v9z" fill="#F5B82E" />
        <path d="M10 20V8H7.8L12 3l4.2 5H14v12z" fill="#3B82F6" />
        <path d="M16 20v-6h-2.2L18 9l4.2 5H20v6z" fill="#37CA6E" />
      </svg>
    </Tile>
  ),
  claude: () => (
    <Tile label="AI automation" bg="linear-gradient(180deg,#E08A68 0%,#C96442 100%)">
      <Glyph path={siClaude.path} size="58%" />
    </Tile>
  ),
  seo: () => (
    <Tile label="SEO" bg="linear-gradient(180deg,#2A2A33 0%,#141419 100%)">
      <svg viewBox="0 0 24 24" className="relative" style={{ width: "54%", height: "54%" }} fill="none" aria-hidden>
        <circle cx="10.5" cy="10.5" r="6.5" stroke="#F2F2F3" strokeWidth="2.2" />
        <path d="M15.5 15.5L21 21" stroke="#F2F2F3" strokeWidth="2.4" strokeLinecap="round" />
        <path d="M7.5 12.5l2-2.2 1.6 1.4 2.4-3" stroke="#6EE7A8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Tile>
  ),
  instagram: () => (
    <Tile label="Content and social" bg="radial-gradient(circle at 30% 107%, #fdf497 0%, #fd5949 45%, #d6249f 60%, #285AEB 90%)">
      <Glyph path={siInstagram.path} size="56%" />
    </Tile>
  ),
  web: () => (
    <Tile label="Websites" bg="linear-gradient(180deg,#2A2A33 0%,#141419 100%)">
      <svg viewBox="0 0 24 24" className="relative" style={{ width: "56%", height: "56%" }} fill="none" aria-hidden>
        <rect x="3" y="4.5" width="18" height="15" rx="2.2" stroke="#F2F2F3" strokeWidth="1.9" />
        <path d="M3 9h18" stroke="#F2F2F3" strokeWidth="1.9" />
        <circle cx="6" cy="6.8" r="0.9" fill="#B9A7FF" />
        <path d="M7 13h6M7 16h4" stroke="#6EE7A8" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </Tile>
  ),
  youtube: () => (
    <Tile label="YouTube ads" bg="linear-gradient(180deg,#FF3B3B 0%,#D90000 100%)">
      <Glyph path={siYoutube.path} size="60%" />
    </Tile>
  ),
  tiktok: () => (
    <Tile label="TikTok ads" bg="linear-gradient(180deg,#1A1A1F 0%,#050506 100%)">
      <Glyph path={siTiktok.path} size="52%" />
    </Tile>
  ),
};
