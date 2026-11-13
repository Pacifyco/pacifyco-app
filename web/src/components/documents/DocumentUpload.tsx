import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, FileCheck2, Upload } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { ApiError, apiFetch } from "../../lib/api";
import { Button } from "../ui";

// Mirrors api/app/models/documents.py. CLAUDE.md section 7: PDF, JPG or PNG only, at most 5 MB.
export type DocumentType =
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
// Parents see sitters' photos in the browser, so a photo must be an image (the API checks too).
const PHOTO_TYPES = ["image/jpeg", "image/png"];

export function clientCheck(file: File, type: DocumentType): string | undefined {
  if (type === "photo" && !PHOTO_TYPES.includes(file.type)) return "Please choose a JPG or PNG photo.";
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

export async function uploadOne(
  type: DocumentType,
  childId: string | undefined,
  file: File,
): Promise<DocumentStatus> {
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
  // The file just sent, shown by name (and as a thumbnail if it's a picture) so people can see what
  // they uploaded (UX review 2026-11-13). Only in this browser: stored files are for Pacifyco's eyes.
  const [sent, setSent] = useState<{ name: string; preview?: string }>();
  useEffect(() => () => {
    if (sent?.preview) URL.revokeObjectURL(sent.preview);
  }, [sent]);

  const upload = useMutation({
    mutationFn: (file: File) => uploadOne(type, childId, file),
    onSuccess: (status, file) => {
      onUploaded();
      setError(status === "invalid" ? "That file isn't a PDF, JPG or PNG, or it's larger than 5 MB." : undefined);
      if (status !== "invalid") {
        const preview =
          file.type.startsWith("image/") && typeof URL.createObjectURL === "function"
            ? URL.createObjectURL(file)
            : undefined;
        setSent({ name: file.name, preview });
      }
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again."),
  });

  function pick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // so picking the same file again still fires onChange
    if (!file) return;
    const problem = clientCheck(file, type);
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
        {sent?.preview && !upload.isPending && (
          <img
            src={sent.preview}
            alt=""
            className={type === "photo" ? "size-[64px] rounded-pill object-cover" : "size-[48px] rounded-sm object-cover"}
          />
        )}
        {current && !upload.isPending && <StatusPill status={current.status} />}
        {sent && !upload.isPending && <span className="min-w-0 break-all text-small text-muted">{sent.name}</span>}
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={
            type === "photo"
              ? ".jpg,.jpeg,.png,image/jpeg,image/png"
              : ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
          }
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
