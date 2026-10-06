"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", short: "Dashboard" },
  { href: "/demo", label: "Replay demo", short: "Replay" },
  { href: "/about", label: "Method & evidence", short: "Method" },
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
    <header className="sticky top-0 z-[1100] border-b bg-background/85 backdrop-blur">
      <div className="container flex h-14 items-center gap-2 sm:gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold">
          <img src="/logo.svg" alt="" className="h-7 w-7" />
          <span>NadiNet</span>
          <span className="bn hidden text-sm font-normal text-muted-foreground sm:inline">নদীনেট</span>
        </Link>
        <nav className="ml-auto flex min-w-0 items-center gap-0.5 text-sm sm:gap-1">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "whitespace-nowrap rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:text-foreground sm:px-2.5",
                path?.startsWith(n.href) && "bg-muted text-foreground",
              )}
            >
              <span className="sm:hidden">{n.short}</span>
              <span className="hidden sm:inline">{n.label}</span>
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
