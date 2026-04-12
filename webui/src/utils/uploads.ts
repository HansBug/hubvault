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

export interface ManifestBuildProgress {
  phase: "reading" | "hashing" | "completed";
  currentPathInRepo: string;
  completedEntries: number;
  totalEntries: number;
  processedBytes: number;
  totalBytes: number;
}

export type ManifestBuildProgressCallback = (payload: ManifestBuildProgress) => void;

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

export function readBlobAsArrayBuffer(blob: Blob, onProgress?: (loaded: number, total: number) => void): Promise<ArrayBuffer> {
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
    reader.onprogress = function handleProgress(event) {
      if (typeof onProgress === "function" && event.lengthComputable) {
        onProgress(Number(event.loaded || 0), Number(event.total || 0));
      }
    };
    reader.readAsArrayBuffer(blob);
  });
}

export async function buildExactUploadManifest(
  entries: BrowserUploadEntry[],
  onProgress?: ManifestBuildProgressCallback
): Promise<ExactUploadManifestResult> {
  const operations: ExactUploadManifestOperation[] = [];
  const totalEntries = Array.isArray(entries) ? entries.length : 0;
  const totalBytes = entries.reduce(function accumulate(total, entry) {
    return total + Number(entry.file.size || 0);
  }, 0);
  let processedBytes = 0;

  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const currentPath = String(entry.pathInRepo || "");
    const currentSize = Number(entry.file.size || 0);
    if (typeof onProgress === "function") {
      onProgress({
        phase: "reading",
        currentPathInRepo: currentPath,
        completedEntries: index,
        totalEntries,
        processedBytes,
        totalBytes
      });
    }
    const buffer = await readBlobAsArrayBuffer(entry.file, function forwardReadProgress(loaded) {
      if (typeof onProgress === "function") {
        onProgress({
          phase: "reading",
          currentPathInRepo: currentPath,
          completedEntries: index,
          totalEntries,
          processedBytes: processedBytes + Number(loaded || 0),
          totalBytes
        });
      }
    });
    if (typeof onProgress === "function") {
      onProgress({
        phase: "hashing",
        currentPathInRepo: currentPath,
        completedEntries: index,
        totalEntries,
        processedBytes: processedBytes + currentSize,
        totalBytes
      });
    }
    operations.push({
      type: "add",
      path_in_repo: currentPath,
      size: currentSize,
      sha256: sha256(new Uint8Array(buffer)),
      chunks: []
    });
    processedBytes += currentSize;
    if (typeof onProgress === "function") {
      onProgress({
        phase: "completed",
        currentPathInRepo: currentPath,
        completedEntries: index + 1,
        totalEntries,
        processedBytes,
        totalBytes
      });
    }
  }
  return {
    operations,
    uploads: entries.slice()
  };
}
