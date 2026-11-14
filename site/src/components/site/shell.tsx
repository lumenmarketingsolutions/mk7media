import { Nav } from "./nav";
import { Footer } from "./footer";

export function Shell({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Nav />
      <main className="relative z-10 bg-bg shadow-[0_40px_60px_-20px_rgba(0,0,0,0.9)]">{children}</main>
      <Footer />
    </>
  );
}
