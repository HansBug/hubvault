import { sha256 } from "js-sha256";

export interface BrowserUploadEntry {
  pathInRepo: string;
  file: File;
}

export interface ExactUploadManifestOperation {
  type: "add";
  path_in_repo: string;
  size: number;
  sha256: string;
  chunks: [];
}

export interface ExactUploadManifestResult {
  operations: ExactUploadManifestOperation[];
  uploads: BrowserUploadEntry[];
}

export function basename(path: string): string {
  const parts = String(path || "").split("/");
  return parts[parts.length - 1] || path;
}

export function joinRepoPath(basePath: string, relativePath: string): string {
  const normalizedBase = String(basePath || "").replace(/^\/+|\/+$/g, "");
  const normalizedRelative = String(relativePath || "").replace(/^\/+|\/+$/g, "");
  if (!normalizedBase) {
    return normalizedRelative;
  }
  if (!normalizedRelative) {
    return normalizedBase;
  }
  return normalizedBase + "/" + normalizedRelative;
}

export function readBlobAsArrayBuffer(blob: Blob): Promise<ArrayBuffer> {
  return new Promise(function resolveArrayBuffer(resolve, reject) {
    const reader = new FileReader();
    reader.onload = function handleLoad() {
      if (reader.result instanceof ArrayBuffer) {
        resolve(reader.result);
        return;
      }
      reject(new Error("Unable to read file bytes."));
    };
    reader.onerror = function handleError() {
      reject(reader.error || new Error("Unable to read file bytes."));
    };
    reader.readAsArrayBuffer(blob);
  });
}

export async function buildExactUploadManifest(entries: BrowserUploadEntry[]): Promise<ExactUploadManifestResult> {
  const operations: ExactUploadManifestOperation[] = [];
  for (const entry of entries) {
    const buffer = await readBlobAsArrayBuffer(entry.file);
    operations.push({
      type: "add",
      path_in_repo: entry.pathInRepo,
      size: entry.file.size,
      sha256: sha256(new Uint8Array(buffer)),
      chunks: []
    });
  }
  return {
    operations,
    uploads: entries.slice()
  };
}
