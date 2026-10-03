import { useEffect, useState } from "react";

const LINKS = [
  { href: "#loop", label: "The Loop" },
  { href: "#strategies", label: "Strategies" },
  { href: "#live", label: "Live Console" },
  { href: "#trace", label: "Agent Trace" },
  { href: "#scale", label: "Scale" },
] as const;

export function SiteNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const go = (href: string) => {
    setOpen(false);
    const el = document.querySelector(href);
    el?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <>
      <header className={`site-nav ${scrolled ? "scrolled" : ""}`}>
        <a
          className="nav-brand"
          href="#top"
          onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        >
          Revive<span>/agent</span>
        </a>
        <nav className="nav-links" aria-label="Primary">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              onClick={(e) => {
                e.preventDefault();
                go(l.href);
              }}
            >
              {l.label}
            </a>
          ))}
        </nav>
        <div className="nav-actions">
          <a className="btn-primary" href="#live" onClick={(e) => { e.preventDefault(); go("#live"); }}>
            See live
          </a>
          <button
            type="button"
            className="nav-burger"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </header>

      {open ? (
        <div className="nav-overlay open" role="dialog" aria-modal="true">
          <button type="button" className="nav-overlay-close" aria-label="Close menu" onClick={() => setOpen(false)}>
            ×
          </button>
          <nav>
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={(e) => {
                  e.preventDefault();
                  go(l.href);
                }}
              >
                {l.label}
              </a>
            ))}
            <a
              className="btn-primary"
              href="#live"
              onClick={(e) => {
                e.preventDefault();
                go("#live");
              }}
            >
              Open live console
            </a>
          </nav>
        </div>
      ) : null}
    </>
  );
}
