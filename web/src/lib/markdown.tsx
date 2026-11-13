import type { ReactNode } from "react";

// A small renderer for our own legal and consent texts in /src/content: front matter, "#" to "###"
// headings, paragraphs, "- " lists, tables, **bold**, *italic* and backslash escapes (\[ \] \.).
// Text is rendered as React text, never as HTML.

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

function unescape(text: string): string {
  return text.replace(/\\([\\[\]().*_#|>+-])/g, "$1");
}

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{unescape(part.slice(2, -2))}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={index}>{unescape(part.slice(1, -1))}</em>;
    }
    return unescape(part);
  });
}

/** Plain text of a heading, without ** or escapes. */
function plainText(text: string): string {
  return unescape(text.replace(/\*\*/g, "").replace(/(^|\s)\*(\S)/g, "$1$2").replace(/(\S)\*(\s|$)/g, "$1$2"));
}

/** An anchor for a section heading: "3. Bookings and payments" → "3-bookings-and-payments". */
export function headingId(text: string): string {
  return plainText(text)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** The "##" sections of a document, for a contents list (UX review 2026-11-13). */
export function sections(body: string): { id: string; text: string }[] {
  return toBlocks(body)
    .filter((block): block is Extract<Block, { kind: "heading" }> => block.kind === "heading" && block.level === 2)
    .map((block) => ({ id: headingId(block.text), text: plainText(block.text) }));
}

function cells(row: string): string[] {
  return row
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

type Block =
  | { kind: "heading"; level: 1 | 2 | 3; text: string }
  | { kind: "list"; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "paragraph"; text: string };

function toBlocks(body: string): Block[] {
  const blocks: Block[] = [];
  for (const chunk of body.trim().split(/\n\s*\n/)) {
    const lines = chunk.split("\n").map((line) => line.trimEnd());
    const heading = /^(#{1,3}) (.*)$/.exec(chunk);
    const previous = blocks.at(-1);
    if (heading && lines.length === 1) {
      blocks.push({ kind: "heading", level: heading[1].length as 1 | 2 | 3, text: heading[2] });
    } else if (lines.every((line) => /^\s*- /.test(line))) {
      const items = lines.map((line) => line.replace(/^\s*- /, ""));
      // Items separated by blank lines still form one list.
      if (previous?.kind === "list") previous.items.push(...items);
      else blocks.push({ kind: "list", items });
    } else if (lines.every((line) => line.trimStart().startsWith("|"))) {
      const rows = lines.filter((line) => !/^\s*\|?\s*:?-{3,}/.test(line)).map(cells);
      blocks.push({ kind: "table", header: rows[0] ?? [], rows: rows.slice(1) });
    } else {
      blocks.push({ kind: "paragraph", text: lines.join(" ") });
    }
  }
  return blocks;
}

/** `boldTitle`: a first line that's all bold ("**Pacifyco Family Terms of Use**") is the page's title,
so it's shown as the H1 without changing the document's wording (UX review 2026-11-13). */
export function Markdown({ body, boldTitle = false }: { body: string; boldTitle?: boolean }) {
  return (
    <>
      {toBlocks(body).map((block, index) => {
        if (boldTitle && index === 0 && block.kind === "paragraph" && /^\*\*[^*]+\*\*$/.test(block.text)) {
          return <h1 key={index}>{inline(block.text.slice(2, -2))}</h1>;
        }
        switch (block.kind) {
          case "heading":
            if (block.level === 1) return <h1 key={index}>{inline(block.text)}</h1>;
            return block.level === 2 ? (
              <h2 key={index} id={headingId(block.text)} className="mt-7 scroll-mt-5 text-h3">
                {inline(block.text)}
              </h2>
            ) : (
              <h3 key={index} className="mt-5 text-ui">
                {inline(block.text)}
              </h3>
            );
          case "list":
            return (
              <ul key={index} className="mt-3 list-disc space-y-2 pl-6">
                {block.items.map((item, i) => (
                  <li key={i}>{inline(item)}</li>
                ))}
              </ul>
            );
          case "table":
            return (
              <div key={index} className="mt-4 overflow-x-auto">
                <table className="w-full border-collapse text-left text-small">
                  <thead>
                    <tr>
                      {block.header.map((cell, i) => (
                        <th key={i} scope="col" className="border-b border-strong px-3 py-2 align-top">
                          {inline(cell)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, i) => (
                          <td key={i} className="border-b border-line px-3 py-2 align-top">
                            {inline(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return (
              <p key={index} className="mt-3">
                {inline(block.text)}
              </p>
            );
        }
      })}
    </>
  );
}
