import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { jsonResponse } from "../../test/renderApp";
import { DocumentUpload } from "./DocumentUpload";

function renderUpload(props: Partial<React.ComponentProps<typeof DocumentUpload>> = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DocumentUpload type="government_id" label="Government ID" {...props} />
    </QueryClientProvider>,
  );
}

function file(name: string, type: string, sizeBytes = 100): File {
  return new File([new Uint8Array(sizeBytes)], name, { type });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("DocumentUpload", () => {
  test("rejects a file type that isn't a PDF, JPG or PNG, without calling the API", async () => {
    vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse([]))) as typeof fetch);
    renderUpload();
    const input = (await screen.findByLabelText("Government ID")) as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file("id.txt", "text/plain")] } });
    expect(await screen.findByText("Please choose a PDF, JPG or PNG file.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("upload-url"))).toBe(false);
  });

  test("rejects a file over 5 MB, without calling the API", async () => {
    vi.mocked(fetch).mockImplementation((() => Promise.resolve(jsonResponse([]))) as typeof fetch);
    renderUpload();
    const input = (await screen.findByLabelText("Government ID")) as HTMLInputElement;

    fireEvent.change(input, { target: { files: [file("id.pdf", "application/pdf", 6 * 1024 * 1024)] } });
    expect(await screen.findByText("That file is larger than 5 MB.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls.some(([url]) => String(url).includes("upload-url"))).toBe(false);
  });

  test("a valid file is uploaded and confirmed, and shows as uploaded", async () => {
    // /documents/mine must reflect the document once it exists, including after it's confirmed --
    // DocumentUpload refetches that list to learn the outcome, it doesn't trust the confirm response.
    let document: Record<string, unknown> | null = null;
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      if (path.startsWith("/documents/mine")) return Promise.resolve(jsonResponse(document ? [document] : []));
      if (path === "/documents/upload-url") {
        document = { id: "doc-1", type: "government_id", child_id: null, status: "pending_upload" };
        return Promise.resolve(jsonResponse({ document_id: "doc-1", upload_url: "https://fake.storage/upload/doc-1" }));
      }
      if (url === "https://fake.storage/upload/doc-1" && init?.method === "PUT") {
        return Promise.resolve(new Response(null, { status: 200 }));
      }
      if (path === "/documents/doc-1/confirm") {
        document = { ...document, status: "uploaded" };
        return Promise.resolve(jsonResponse({ status: "uploaded" }));
      }
      return Promise.reject(new Error(`unexpected request: ${path}`));
    }) as typeof fetch);

    renderUpload();
    const input = (await screen.findByLabelText("Government ID")) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file("id.pdf", "application/pdf")] } });

    expect(await screen.findByText("Uploaded")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Replace file/ })).toBeTruthy();
  });

  test("a file the API rejects shows as not usable", async () => {
    vi.mocked(fetch).mockImplementation(((url: string, init?: RequestInit) => {
      const path = url.replace(/^https?:\/\/[^/]+/, "");
      if (path.startsWith("/documents/mine")) return Promise.resolve(jsonResponse([]));
      if (path === "/documents/upload-url") {
        return Promise.resolve(jsonResponse({ document_id: "doc-2", upload_url: "https://fake.storage/upload/doc-2" }));
      }
      if (url === "https://fake.storage/upload/doc-2" && init?.method === "PUT") {
        return Promise.resolve(new Response(null, { status: 200 }));
      }
      if (path === "/documents/doc-2/confirm") return Promise.resolve(jsonResponse({ status: "invalid" }));
      return Promise.reject(new Error(`unexpected request: ${path}`));
    }) as typeof fetch);

    renderUpload();
    const input = (await screen.findByLabelText("Government ID")) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file("id.pdf", "application/pdf")] } });

    expect(await screen.findByText(/isn't a PDF, JPG or PNG, or it's larger than 5 MB/)).toBeTruthy();
  });
});
