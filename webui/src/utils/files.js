const README_CANDIDATES = ["README.md", "README.markdown", "README.rst", "README.txt"];
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

export function isTextLikePath(path) {
  const text = String(path || "").toLowerCase();
  for (let index = 0; index < TEXT_EXTENSIONS.length; index += 1) {
    if (text.endsWith(TEXT_EXTENSIONS[index])) {
      return true;
    }
  }
  return false;
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
