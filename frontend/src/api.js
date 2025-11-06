const API_BASE = import.meta.env.VITE_API_URL;



export async function searchQuery(query) {
  console.log("Searching:", query);
  try {
    const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
    console.log("Backend response status:", res.status);
    if (!res.ok) throw new Error("Search failed");
    const data = await res.json();
    console.log("Backend data:", data);
    return data.results || [];
  } catch (err) {
    console.error("Search error:", err);
    return [];
  }
}
