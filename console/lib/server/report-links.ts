/** Resolve report-local links through the existing allowlisted document proxy. */
export function reportLinks(html: string, sourcePath: string): string {
  return html.replace(/<a\b[^>]*>/gi, (tag) => {
    const match = tag.match(/\bhref\s*=\s*(["'])(.*?)\1/i);
    if (!match) return tag;
    const href = match[2]!.replace(/&amp;/g, "&");
    if (href.startsWith("#")) return tag;
    let output = href;
    try {
      const base = "https://jobflow.invalid/";
      const url = new URL(href, base + sourcePath);
      if (!["http:", "https:"].includes(url.protocol)) return tag.replace(match[0], 'href="#"');
      if (url.origin === "https://jobflow.invalid") {
        const relative = url.pathname === "/document" ? url.searchParams.get("f") : url.pathname === "/api/document" ? url.searchParams.get("path") : decodeURIComponent(url.pathname.slice(1));
        if (relative) output = `/api/document?path=${encodeURIComponent(relative)}${url.hash}`;
      }
    } catch { return tag; }
    return tag.replace(match[0], `href="${output.replace(/&/g, "&amp;").replace(/"/g, "&quot;")}"`)
      .replace(/\s(?:target|rel)\s*=\s*(["']).*?\1/gi, "")
      .replace(/>$/, ' target="_blank" rel="noopener noreferrer">');
  });
}
