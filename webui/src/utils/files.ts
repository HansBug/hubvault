import natsort from "natsort";

const README_CANDIDATES = ["README.md", "README.markdown", "README.rst", "README.txt"];
const IMAGE_EXTENSIONS = [".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"];
const AUDIO_EXTENSIONS = [".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"];
const VIDEO_EXTENSIONS = [".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ogv", ".webm"];
const TEXT_EXTENSIONS = [
  ".cfg",
  ".css",
  ".csv",
  ".html",
  ".ini",
  ".js",
  ".json",
  ".md",
  ".py",
  ".rst",
  ".sh",
  ".toml",
  ".ts",
  ".txt",
  ".xml",
  ".yaml",
  ".yml"
];

const NATURAL_SORTER = natsort();

function hasKnownExtension(path, extensions) {
  const text = String(path || "").toLowerCase();
  for (let index = 0; index < extensions.length; index += 1) {
    if (text.endsWith(extensions[index])) {
      return true;
    }
  }
  return false;
}

function entryName(entry) {
  const path = String((entry && entry.path) || "");
  const parts = path.split("/");
  return parts[parts.length - 1] || path;
}

export function findReadmePath(files) {
  const values = Array.isArray(files) ? files : [];
  for (let index = 0; index < README_CANDIDATES.length; index += 1) {
    if (values.indexOf(README_CANDIDATES[index]) >= 0) {
      return README_CANDIDATES[index];
    }
  }
  return "";
}

export function isMarkdownPath(path) {
  return /\.(md|markdown)$/i.test(String(path || ""));
}

export function isJsonPath(path) {
  return /\.json$/i.test(String(path || ""));
}

export function isImagePath(path) {
  return hasKnownExtension(path, IMAGE_EXTENSIONS);
}

export function isAudioPath(path) {
  return hasKnownExtension(path, AUDIO_EXTENSIONS);
}

export function isVideoPath(path) {
  return hasKnownExtension(path, VIDEO_EXTENSIONS);
}

export function isTextLikePath(path) {
  const text = String(path || "").toLowerCase();
  for (let index = 0; index < TEXT_EXTENSIONS.length; index += 1) {
    if (text.endsWith(TEXT_EXTENSIONS[index])) {
      return true;
    }
  }
  return false;
}

export function isCodeLikePath(path) {
  return isTextLikePath(path) && !isMarkdownPath(path);
}

export function naturalCompare(left, right) {
  const leftText = String(left || "");
  const rightText = String(right || "");
  return NATURAL_SORTER(leftText, rightText);
}

export function sortRepoEntries(entries) {
  const values = Array.isArray(entries) ? entries.slice() : [];
  return values.sort(function sortEntries(left, right) {
    const leftIsFolder = left && left.entry_type === "folder";
    const rightIsFolder = right && right.entry_type === "folder";
    if (leftIsFolder !== rightIsFolder) {
      return leftIsFolder ? -1 : 1;
    }

    const byName = naturalCompare(entryName(left), entryName(right));
    if (byName !== 0) {
      return byName;
    }

    return naturalCompare(String((left && left.path) || ""), String((right && right.path) || ""));
  });
}

export function decodeUtf8Bytes(bytes) {
  if (typeof TextDecoder !== "undefined") {
    return new TextDecoder("utf-8").decode(bytes);
  }
  let result = "";
  for (let index = 0; index < bytes.length; index += 1) {
    result += String.fromCharCode(bytes[index]);
  }
  return decodeURIComponent(escape(result));
}

export function buildBreadcrumbs(path) {
  const text = String(path || "").trim();
  if (!text) {
    return [];
  }
  const parts = text.split("/");
  const breadcrumbs = [];
  for (let index = 0; index < parts.length; index += 1) {
    breadcrumbs.push({
      label: parts[index],
      path: parts.slice(0, index + 1).join("/")
    });
  }
  return breadcrumbs;
}
