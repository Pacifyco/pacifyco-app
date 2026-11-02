import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, FileCheck2, Upload } from "lucide-react";
import { useId, useRef, useState } from "react";
import { ApiError, apiFetch } from "../../lib/api";
import { Button } from "../ui";

// Mirrors api/app/models/documents.py. CLAUDE.md section 7: PDF, JPG or PNG only, at most 5 MB.
export type DocumentType =
  | "aadhaar_masked"
  | "birth_certificate"
  | "government_id"
  | "college_or_work_id"
  | "police_certificate"
  | "first_aid_certificate"
  | "doctor_note"
  | "photo";

export type DocumentStatus = "pending_upload" | "uploaded" | "invalid";

export type DocumentOut = {
  id: string;
  type: DocumentType;
  child_id: string | null;
  status: DocumentStatus;
};

const MAX_FILE_BYTES = 5 * 1024 * 1024;
const ALLOWED_TYPES = ["application/pdf", "image/jpeg", "image/png"];

function clientCheck(file: File): string | undefined {
  if (!ALLOWED_TYPES.includes(file.type)) return "Please choose a PDF, JPG or PNG file.";
  if (file.size > MAX_FILE_BYTES) return "That file is larger than 5 MB.";
  return undefined;
}

export function documentsKey(type: DocumentType, childId?: string) {
  return ["documents", type, childId ?? null] as const;
}

export function useMyDocuments(type: DocumentType, childId?: string) {
  return useQuery({
    queryKey: documentsKey(type, childId),
    queryFn: () => apiFetch<DocumentOut[]>(`/documents/mine?type=${type}${childId ? `&child_id=${childId}` : ""}`),
  });
}

async function uploadOne(type: DocumentType, childId: string | undefined, file: File): Promise<DocumentStatus> {
  const ticket = await apiFetch<{ document_id: string; upload_url: string }>("/documents/upload-url", {
    method: "POST",
    body: JSON.stringify({ type, child_id: childId ?? null }),
  });
  const put = await fetch(ticket.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
  if (!put.ok) throw new ApiError(put.status, "upload_failed", "That upload didn't go through. Please try again.");
  const confirmed = await apiFetch<{ status: DocumentStatus }>(`/documents/${ticket.document_id}/confirm`, {
    method: "POST",
  });
  return confirmed.status;
}

function StatusPill({ status }: { status: DocumentStatus }) {
  if (status === "uploaded") {
    return (
      <span className="inline-flex items-center gap-1 text-small text-trust">
        <FileCheck2 aria-hidden="true" size={18} strokeWidth={1.75} />
        Uploaded
      </span>
    );
  }
  if (status === "invalid") {
    return (
      <span className="inline-flex items-center gap-1 text-small text-danger">
        <CircleAlert aria-hidden="true" size={18} strokeWidth={1.75} />
        Couldn't be used
      </span>
    );
  }
  return <span className="text-small text-muted">Being checked…</span>;
}

/** One upload slot: a label, the current file's status (if any), and a picker to add or replace it.
Purely presentational about *which* document it shows -- the caller says so via `current` and is told
when a new one lands via `onUploaded`, so a list of several slots of the same type never collide. */
function UploadSlot({
  type,
  childId,
  label,
  hint,
  current,
  onUploaded,
}: {
  type: DocumentType;
  childId?: string;
  label: string;
  hint?: string;
  current?: DocumentOut;
  onUploaded: () => void;
}) {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();

  const upload = useMutation({
    mutationFn: (file: File) => uploadOne(type, childId, file),
    onSuccess: (status) => {
      onUploaded();
      setError(status === "invalid" ? "That file isn't a PDF, JPG or PNG, or it's larger than 5 MB." : undefined);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so picking the same file again still fires onChange
    if (!file) return;
    const problem = clientCheck(file);
    if (problem) return setError(problem);
    setError(undefined);
    upload.mutate(file);
  }

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-ui text-ink">
        {label}
      </label>
      {hint && <p className="-mt-1 text-small text-muted">{hint}</p>}
      <div className="flex flex-wrap items-center gap-3">
        {current && !upload.isPending && <StatusPill status={current.status} />}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          className="hidden"
          onChange={pick}
        />
        <Button
          type="button"
          variant="secondary"
          fullWidthOnPhone={false}
          loading={upload.isPending}
          onClick={() => inputRef.current?.click()}
        >
          <Upload aria-hidden="true" size={18} strokeWidth={1.75} />
          {current ? "Replace file" : "Choose file"}
        </Button>
      </div>
      {error && (
        <p role="alert" className="flex items-start gap-2 text-small text-danger">
          <CircleAlert aria-hidden="true" size={20} strokeWidth={1.75} className="mt-px shrink-0" />
          <span>{error}</span>
        </p>
      )}
    </div>
  );
}

/** A single upload slot for one document type (and child, if it's child-linked): fetches whether
one already exists and shows its status, or an empty picker. */
export function DocumentUpload({
  type,
  childId,
  label,
  hint,
}: {
  type: DocumentType;
  childId?: string;
  label: string;
  hint?: string;
}) {
  const queryClient = useQueryClient();
  const documents = useMyDocuments(type, childId);
  return (
    <UploadSlot
      type={type}
      childId={childId}
      label={label}
      hint={hint}
      current={documents.data?.[0]}
      onUploaded={() => queryClient.invalidateQueries({ queryKey: documentsKey(type, childId) })}
    />
  );
}

/** Up to `max` upload slots of the same type (e.g. two masked Aadhaars). Fetches the list once and
hands each slot its own document (if any), so slots never show each other's status. */
export function DocumentUploadList({ type, label, max }: { type: DocumentType; label: string; max: number }) {
  const queryClient = useQueryClient();
  const documents = useMyDocuments(type);
  const existing = documents.data ?? [];
  const [extraSlots, setExtraSlots] = useState(0);
  const baseline = existing.length > 0 ? existing.length : 1; // always at least one slot to start
  const shown = Math.min(max, baseline + extraSlots);

  return (
    <div className="flex flex-col gap-4">
      {Array.from({ length: shown }, (_, index) => (
        <UploadSlot
          key={existing[index]?.id ?? `empty-${index}`}
          type={type}
          label={shown > 1 ? `${label} ${index + 1}` : label}
          current={existing[index]}
          onUploaded={() => queryClient.invalidateQueries({ queryKey: documentsKey(type) })}
        />
      ))}
      {shown < max && (
        <Button type="button" variant="tertiary" onClick={() => setExtraSlots((count) => count + 1)}>
          Add another
        </Button>
      )}
    </div>
  );
}
