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

export function Markdown({ body }: { body: string }) {
  return (
    <>
      {toBlocks(body).map((block, index) => {
        switch (block.kind) {
          case "heading":
            if (block.level === 1) return <h1 key={index}>{inline(block.text)}</h1>;
            return block.level === 2 ? (
              <h2 key={index} className="mt-7 text-h3">
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
