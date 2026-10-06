"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/demo", label: "Replay demo" },
  { href: "/about", label: "Method & evidence" },
];

export function SiteHeader() {
  const path = usePathname();
  const [dark, setDark] = useState(false);
  useEffect(() => setDark(document.documentElement.classList.contains("dark")), []);
  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("nadinet.theme", next ? "dark" : "light");
    } catch {
      /* theme just won't persist */
    }
  };
  return (
    <header className="sticky top-0 z-[1000] border-b bg-background/85 backdrop-blur">
      <div className="container flex h-14 items-center gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <img src="/logo.svg" alt="" className="h-7 w-7" />
          <span>NadiNet</span>
          <span className="bn hidden text-sm font-normal text-muted-foreground sm:inline">নদীনেট</span>
        </Link>
        <nav className="ml-auto flex items-center gap-1 overflow-x-auto text-sm">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "rounded-md px-2.5 py-1.5 text-muted-foreground transition-colors hover:text-foreground",
                path?.startsWith(n.href) && "bg-muted text-foreground",
              )}
            >
              {n.label}
            </Link>
          ))}
          <button
            onClick={toggle}
            aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
            className="ml-1 rounded-md p-2 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </nav>
      </div>
    </header>
  );
}
