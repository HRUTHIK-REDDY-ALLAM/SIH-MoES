"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Risk map" },
  { href: "/farmer", label: "Farmer view" },
  { href: "/officer", label: "Officer console" },
  { href: "/replay", label: "2023 replay" },
  { href: "/skill", label: "Skill" },
];

export default function Header({ right = null }) {
  const path = usePathname();
  return (
    <header className="app-header">
      <Link href="/" className="brand" style={{ textDecoration: "none" }}>
        <span style={{ fontSize: "1.4rem" }} aria-hidden>
          🌧️
        </span>
        <div>
          <h1 className="brand-title">Varsha</h1>
          <p className="brand-sub">Monsoon onset &amp; break outlook</p>
        </div>
      </Link>
      <nav className="nav" aria-label="Main">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
            {l.label}
          </Link>
        ))}
      </nav>
      <div className="header-right">{right}</div>
    </header>
  );
}
