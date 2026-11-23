import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, test } from "vitest";

// The web app's security headers (public/_headers, served by Cloudflare Pages; CLAUDE.md 9 "Security
// testing"). The policy names the one inline script, index.html's theme script, by its hash: change the
// script and this fails until the hash in _headers is updated too.

const root = resolve(__dirname, "..");
// Line endings as git stores them (LF), which is what Cloudflare builds from, whatever this checkout uses.
const lf = (text: string) => text.replace(/\r\n/g, "\n");
const headers = lf(readFileSync(resolve(root, "public/_headers"), "utf-8"));
const page = lf(readFileSync(resolve(root, "index.html"), "utf-8"));

function header(name: string): string {
  const line = headers.split("\n").find((item) => item.trim().toLowerCase().startsWith(`${name.toLowerCase()}:`));
  return line ? line.slice(line.indexOf(":") + 1).trim() : "";
}

describe("Security headers", () => {
  test("every page gets them", () => {
    expect(headers).toMatch(/^\/\*$/m);
    expect(header("X-Content-Type-Options")).toBe("nosniff");
    expect(header("X-Frame-Options")).toBe("DENY");
    expect(header("Referrer-Policy")).toBe("strict-origin-when-cross-origin");
    expect(header("Strict-Transport-Security")).toMatch(/max-age=\d{8,}/);
    // Check-in records the sitter's location (CLAUDE.md 6.7): allowed for the app itself, nothing else.
    expect(header("Permissions-Policy")).toContain("geolocation=(self)");
    expect(header("Permissions-Policy")).toContain("camera=()");
  });

  test("the content policy allows only our own scripts and the theme script", () => {
    const policy = header("Content-Security-Policy-Report-Only") || header("Content-Security-Policy");
    expect(policy).toContain("default-src 'self'");
    expect(policy).toContain("frame-ancestors 'none'");
    expect(policy).toContain("object-src 'none'");
    const scripts = /script-src ([^;]+)/.exec(policy)?.[1] ?? "";
    expect(scripts).not.toContain("unsafe-inline");
    expect(scripts).not.toContain("unsafe-eval");

    const inline = [...page.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
    expect(inline).toHaveLength(1);
    const hash = `'sha256-${createHash("sha256").update(inline[0], "utf8").digest("base64")}'`;
    expect(scripts).toContain(hash);
  });
});
