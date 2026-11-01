import type { ReactNode } from "react";

// A tiny renderer for our own legal and consent texts in /src/content: front matter, "#" and "##"
// headings, paragraphs, "- " lists and **bold**. Text is rendered as React text, never as HTML.

export type Document = { meta: Record<string, string>; body: string };

export function parseDocument(source: string): Document {
  const text = source.replace(/\r\n/g, "\n");
  const match = /^---\n([\s\S]*?)\n---\n/.exec(text);
  if (!match) return { meta: {}, body: text };
  const meta: Record<string, string> = {};
  for (const line of match[1].split("\n")) {
    const [key, ...rest] = line.split(":");
    if (key.trim() && rest.length) meta[key.trim()] = rest.join(":").trim();
  }
  return { meta, body: text.slice(match[0].length) };
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : part,
  );
}

export function Markdown({ body }: { body: string }) {
  const blocks = body.trim().split(/\n\s*\n/);
  return (
    <>
      {blocks.map((block, index) => {
        const lines = block.split("\n");
        if (block.startsWith("# ")) return <h1 key={index}>{inline(block.slice(2))}</h1>;
        if (block.startsWith("## ")) {
          return (
            <h2 key={index} className="mt-6 text-h3">
              {inline(block.slice(3))}
            </h2>
          );
        }
        if (lines.every((line) => line.startsWith("- "))) {
          return (
            <ul key={index} className="mt-3 list-disc space-y-2 pl-6">
              {lines.map((line, item) => (
                <li key={item}>{inline(line.slice(2))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className="mt-3">
            {inline(lines.join(" "))}
          </p>
        );
      })}
    </>
  );
}
