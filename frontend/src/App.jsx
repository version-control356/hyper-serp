import { useEffect, useMemo, useRef, useState } from "react";
import { searchQuery } from "./api";

export default function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    const clear = (e) => e.key === "Escape" && setQuery("");
    window.addEventListener("keydown", clear);
    return () => window.removeEventListener("keydown", clear);
  }, []);

  const handleSearch = async (e) => {
    e?.preventDefault?.();
    if (!query.trim()) return;
    setLoading(true);
    setHasSearched(true);
    const data = await searchQuery(query);
    setResults(Array.isArray(data) ? data : []);
    setLoading(false);
  };

  const skeletonRows = useMemo(() => new Array(6).fill(null), []);

  return (
    <div className="min-h-screen text-gray-100 bg-[#0b0f1a] transition">
      <header
        className={`sticky top-0 z-10 transition-all duration-300 ${
          hasSearched
            ? "backdrop-blur-md bg-[#0b0f1acc] border-b border-white/5"
            : "bg-transparent"
        }`}
      >
        <div className="mx-auto w-full max-w-3xl px-4">
          <form
            onSubmit={handleSearch}
            className={`${
              hasSearched
                ? "py-4"
                : "min-h-[60vh] flex items-center justify-center"
            }`}
          >
            <div className="w-full">
              {!hasSearched && (
                <h1 className="text-6xl font-extrabold text-center mb-8 bg-clip-text text-transparent bg-gradient-to-r from-blue-500 to-purple-500">
                  HyperSerp
                </h1>
              )}

              <div
                className="flex items-center gap-2 rounded-2xl border border-white/10 bg-[#0f172a]/80
                px-5 py-3 shadow-[0_10px_30px_rgba(0,0,0,0.35)]
                focus-within:ring-2 focus-within:ring-blue-500/40 transition"
              >
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Search the web..."
                  className="w-full bg-transparent text-gray-100 placeholder-gray-400 text-lg outline-none"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  type="submit"
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-purple-600 px-5 py-2 text-white font-medium hover:from-blue-500 hover:to-purple-500 active:scale-[0.97] transition"
                >
                  Search
                </button>
              </div>

              {!hasSearched && (
                <p className="text-center text-sm text-gray-400 mt-3">
                  Press <b>Enter</b> to search • Press <b>Esc</b> to clear
                </p>
              )}
            </div>
          </form>
        </div>
      </header>

      <main className="mx-auto w-full max-w-3xl px-4">
        {hasSearched && <div className="h-4" />}

        {loading && (
          <ul className="divide-y divide-white/5 mt-6">
            {skeletonRows.map((_, i) => (
              <li key={i} className="py-5">
                <div className="h-5 w-3/4 rounded-md bg-[#141b2c] animate-pulse mb-2" />
                <div className="h-4 w-full rounded-md bg-[#141b2c] animate-pulse mb-1" />
                <div className="h-4 w-11/12 rounded-md bg-[#141b2c] animate-pulse" />
              </li>
            ))}
          </ul>
        )}

        {!loading && hasSearched && results.length === 0 && (
          <div className="text-center text-gray-400 py-16">
            No results yet. Try a different search.
          </div>
        )}

        {!loading && results.length > 0 && (
          <ul className="divide-y divide-white/5 mt-6">
            {results.map((r, i) => (
              <li key={i} className="py-5 group">
                <a
                  href={r.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block"
                >
                  <h3 className="text-xl font-semibold text-blue-400 group-hover:underline">
                    {r.title || "Untitled"}
                  </h3>

                  {r.url && (
                    <p className="text-xs text-gray-500 mt-1 truncate">
                      {r.url}
                    </p>
                  )}

                  {r.snippet && (
                    <p className="text-gray-300 mt-2 text-sm leading-relaxed">
                      {r.snippet}
                    </p>
                  )}

                  {r.summary && (
                    <p className="mt-2 text-sm text-purple-200 bg-purple-950/30 border border-purple-700/20 rounded-lg p-3">
                      🧠 {r.summary}
                    </p>
                  )}
                </a>
              </li>
            ))}
          </ul>
        )}
      </main>

      <footer className="text-center text-xs text-gray-500 py-10">
        HyperSerp • Dark mode • No external APIs
      </footer>
    </div>
  );
}
