import { useEffect, useMemo, useState } from "react";
import { CATEGORIES, TOOLS, type Category } from "./tools";

function useQueryState() {
  const [params, setParams] = useState(() => new URLSearchParams(window.location.search));
  useEffect(() => {
    const onPop = () => setParams(new URLSearchParams(window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const update = (next: Record<string, string>) => {
    const p = new URLSearchParams(window.location.search);
    for (const [k, v] of Object.entries(next)) p.set(k, v);
    const url = `${window.location.pathname}?${p.toString()}`;
    window.history.pushState({}, "", url);
    setParams(new URLSearchParams(p.toString()));
  };
  return { params, update };
}

export default function App() {
  const { params, update } = useQueryState();
  const cat = (params.get("cat") as Category | null) ?? "launch";
  const tab = params.get("tab") ?? TOOLS.find((t) => t.cat === cat)?.tab ?? "launcher";
  const tools = useMemo(() => TOOLS.filter((t) => t.cat === cat), [cat]);
  const current = tools.find((t) => t.tab === tab) ?? tools[0];

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-900 bg-gray-950/80 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <img src="/icon.svg" alt="" className="h-8 w-8" />
            <div>
              <div className="font-semibold tracking-tight">SAI Agency</div>
              <div className="text-xs text-gray-400">Launch · Acquire · Own</div>
            </div>
          </div>
          <a
            href="https://desiredsolutions.me"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-gray-400 hover:text-gray-200"
          >
            by Desired Solutions ↗
          </a>
        </div>
        <nav className="max-w-6xl mx-auto px-5 pb-3 flex gap-2 overflow-x-auto">
          {CATEGORIES.map((c) => {
            const active = c.key === cat;
            const firstTab = TOOLS.find((t) => t.cat === c.key)?.tab;
            return (
              <button
                key={c.key}
                onClick={() => firstTab && update({ cat: c.key, tab: firstTab })}
                className={
                  "px-3 py-1.5 rounded-full text-sm whitespace-nowrap border transition " +
                  (active
                    ? "bg-brand-600 border-brand-500 text-white"
                    : "bg-gray-900 border-gray-800 text-gray-300 hover:border-gray-700")
                }
              >
                {c.label}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="max-w-6xl mx-auto px-5 py-8">
        <section className="mb-6">
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
            {CATEGORIES.find((c) => c.key === cat)?.label}
          </h1>
          <p className="text-gray-400 mt-1">
            {CATEGORIES.find((c) => c.key === cat)?.blurb}
          </p>
        </section>

        <div className="flex gap-2 flex-wrap mb-6">
          {tools.map((t) => {
            const active = t.tab === current?.tab;
            return (
              <button
                key={t.key}
                onClick={() => update({ cat, tab: t.tab })}
                className={
                  "px-3 py-1.5 rounded-lg text-sm border transition " +
                  (active
                    ? "bg-gray-800 border-brand-600 text-white"
                    : "bg-gray-900 border-gray-800 text-gray-300 hover:border-gray-700")
                }
              >
                {t.name}
              </button>
            );
          })}
        </div>

        {current && (
          <article className="rounded-2xl border border-gray-800 bg-gradient-to-b from-gray-900 to-gray-950 p-6 md:p-8">
            <h2 className="text-xl font-semibold">{current.name}</h2>
            <p className="text-gray-400 mt-1">{current.tagline}</p>
            <div className="mt-6 rounded-lg border border-dashed border-gray-800 p-6 text-sm text-gray-400">
              <p className="mb-2 font-medium text-gray-200">
                This tool is being migrated from the built bundle.
              </p>
              <p>
                The production implementation lives in <code className="text-brand-500">/dist</code> and
                is the version Netlify currently serves. The source for this
                scaffold will replace it, one tool at a time, in future PRs.
              </p>
            </div>
          </article>
        )}

        <footer className="mt-12 text-xs text-gray-500">
          <p>
            Privacy-first. Everything runs on your device. Nothing is sent
            anywhere. No emails. No cookies. One click wipes it all.
          </p>
        </footer>
      </main>
    </div>
  );
}
