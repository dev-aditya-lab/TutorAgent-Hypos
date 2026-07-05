"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";

const LINKS = [
  { href: "/roadmap", label: "Roadmap" },
  { href: "/quiz", label: "Daily Quiz" },
  { href: "/interview", label: "Mock Interview" },
  { href: "/progress", label: "Progress" },
];

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    <nav className="mb-6 flex w-full max-w-3xl flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap gap-1.5">
        {LINKS.map((link) => {
          const active = pathname === link.href;
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                active ? "bg-emerald-600 text-white" : "text-emerald-700 hover:bg-emerald-100"
              }`}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => {
          logout();
          router.push("/login");
        }}
        className="rounded-lg border border-emerald-200 bg-white px-3 py-1.5 text-sm font-medium text-emerald-700 transition hover:bg-emerald-50"
      >
        Log out
      </button>
    </nav>
  );
}
