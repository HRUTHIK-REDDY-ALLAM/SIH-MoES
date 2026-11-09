"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Risk map" },
  { href: "/farmer", label: "Farmer view" },
  { href: "/officer", label: "Officer console" },
  { href: "/replay", label: "2023 replay" },
  { href: "/skill", label: "Skill" },
];

const FONT_SIZES = [
  ["sm", "A-", "14px", "Decrease text size"],
  ["md", "A", "15px", "Normal text size"],
  ["lg", "A+", "17px", "Increase text size"],
];

function TextSize() {
  const [size, setSize] = useState("md");
  useEffect(() => {
    let s = "md";
    try { s = localStorage.getItem("varsha.fs") || "md"; } catch { /* storage unavailable */ }
    apply(s);
  }, []);
  function apply(k) {
    const px = FONT_SIZES.find((f) => f[0] === k)?.[2] || "15px";
    document.documentElement.style.setProperty("--base-fs", px);
    setSize(k);
    try { localStorage.setItem("varsha.fs", k); } catch { /* storage unavailable */ }
  }
  return (
    <span className="fs" role="group" aria-label="Text size">
      {FONT_SIZES.map(([k, l, , title]) => (
        <button key={k} type="button" title={title} aria-pressed={size === k} className={size === k ? "active" : ""} onClick={() => apply(k)}>{l}</button>
      ))}
    </span>
  );
}

function RainMark() {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path d="M9.5 19.5a5.5 5.5 0 0 1-.6-10.97A7.5 7.5 0 0 1 23.3 9.6 5 5 0 0 1 23 19.5H9.5Z" fill="#fff" />
      <path d="M11 22.5l-1.2 3M16 22.5l-1.2 3M21 22.5l-1.2 3" stroke="#ff9933" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export default function Header({ right = null }) {
  const path = usePathname();
  return (
    <>
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <div className="tricolor" aria-hidden="true" />
      <div className="gov-strip">
        <div className="gov-strip-inner">
          <div className="goi">
            <span lang="hi">भारत सरकार</span><span className="sep">|</span><span>Government of India</span>
            <span className="sep hide-xs">|</span><span className="hide-xs">Ministry of Earth Sciences</span>
          </div>
          <div className="tools">
            <a href="#main-content" className="hide-xs">Skip to main content</a>
            <TextSize />
          </div>
        </div>
      </div>
      <header className="app-header">
        <div className="masthead-inner">
          <Link href="/" className="brand">
            <span className="brand-mark"><RainMark /></span>
            <div className="brand-text">
              <p className="brand-kicker">Ministry of Earth Sciences · Government of India</p>
              <h1 className="brand-title">Varsha<span className="hi" lang="hi">वर्षा</span></h1>
              <p className="brand-sub">Monsoon Onset &amp; Break Outlook — block &amp; panchayat level agro-advisories</p>
            </div>
          </Link>
          <div className="header-right">{right}</div>
        </div>
        <nav className="gov-nav" aria-label="Main">
          <div className="gov-nav-inner">
            <div className="nav">
              {LINKS.map((l) => (
                <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""} aria-current={path === l.href ? "page" : undefined}>
                  {l.label}
                </Link>
              ))}
            </div>
            <span className="nav-meta">Kharif season · Telangana pilot</span>
          </div>
        </nav>
      </header>
      <div id="main-content" tabIndex={-1} />
    </>
  );
}
