import natsort from "natsort";

const README_CANDIDATES = ["README.md", "README.markdown", "README.rst", "README.txt"];
const IMAGE_EXTENSIONS = [".avif", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"];
const AUDIO_EXTENSIONS = [".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"];
const VIDEO_EXTENSIONS = [".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ogv", ".webm"];
const FONT_EXTENSIONS = [".eot", ".otf", ".ttf", ".woff", ".woff2"];
const MULTIPART_EXTENSIONS = [".tar.bz2", ".tar.gz", ".tar.xz", ".tar.zst"];
const ARCHIVE_EXTENSIONS = [".7z", ".bz2", ".gz", ".rar", ".tar", ".tar.bz2", ".tar.gz", ".tar.xz", ".tgz", ".xz", ".zip"];
const TABLE_EXTENSIONS = [".arrow", ".avro", ".csv", ".feather", ".jsonl", ".ndjson", ".ods", ".orc", ".parquet", ".psv", ".tsv", ".xls", ".xlsx"];
const DATABASE_EXTENSIONS = [".db", ".duckdb", ".ldb", ".mdb", ".sqlite", ".sqlite3"];
const MODEL_EXTENSIONS = [
  ".ckpt",
  ".ggml",
  ".gguf",
  ".h5",
  ".hdf5",
  ".joblib",
  ".keras",
  ".pb",
  ".pkl",
  ".pickle",
  ".pt",
  ".pth",
  ".safetensors",
  ".tflite"
];
const CODE_EXTENSIONS = [
  ".astro",
  ".c",
  ".cc",
  ".clj",
  ".cljc",
  ".cljs",
  ".cpp",
  ".cs",
  ".cuh",
  ".cu",
  ".cxx",
  ".dart",
  ".erl",
  ".ex",
  ".exs",
  ".f",
  ".f90",
  ".f95",
  ".fish",
  ".go",
  ".gql",
  ".graphql",
  ".gradle",
  ".groovy",
  ".h",
  ".hh",
  ".hpp",
  ".hrl",
  ".hs",
  ".html",
  ".htm",
  ".java",
  ".jl",
  ".js",
  ".json",
  ".jsx",
  ".kt",
  ".kts",
  ".less",
  ".lua",
  ".m",
  ".md",
  ".mdx",
  ".mts",
  ".nim",
  ".php",
  ".pl",
  ".pm",
  ".proto",
  ".ps1",
  ".psd1",
  ".psm1",
  ".py",
  ".pyi",
  ".r",
  ".rb",
  ".rkt",
  ".rs",
  ".sass",
  ".scala",
  ".scss",
  ".sh",
  ".sol",
  ".sql",
  ".svelte",
  ".swift",
  ".tf",
  ".tfvars",
  ".toml",
  ".ts",
  ".tsx",
  ".vue",
  ".wasm",
  ".xml",
  ".yaml",
  ".yml",
  ".zig",
  ".zsh"
];
const TEXT_EXTENSIONS = CODE_EXTENSIONS.concat([
  ".adoc",
  ".asciidoc",
  ".bash",
  ".cfg",
  ".conf",
  ".env",
  ".hcl",
  ".ini",
  ".ipynb",
  ".json5",
  ".jsonc",
  ".markdown",
  ".rst",
  ".txt"
]).concat(TABLE_EXTENSIONS.filter(function pickTextTableExtension(extension) {
  return extension === ".csv" || extension === ".jsonl" || extension === ".ndjson" || extension === ".psv" || extension === ".tsv";
}));

const EXACT_NAME_VISUALS: Record<string, string> = {
  ".editorconfig": "config",
  ".env": "config",
  ".gitattributes": "git",
  ".gitignore": "git",
  ".gitmodules": "git",
  ".npmrc": "npm",
  ".yarnrc": "yarn",
  ".yarnrc.yml": "yarn",
  "build.gradle": "gradle",
  "build.gradle.kts": "gradle",
  "cargo.lock": "lock",
  "cargo.toml": "rust",
  "chart.yaml": "helm",
  "cmakelists.txt": "cmake",
  "compose.yaml": "docker",
  "compose.yml": "docker",
  "composer.json": "php",
  "composer.lock": "lock",
  "dockerfile": "docker",
  "gemfile": "ruby",
  "gemfile.lock": "lock",
  "go.mod": "go",
  "go.sum": "go",
  "gnumakefile": "makefile",
  "kustomization.yaml": "kubernetes",
  "kustomization.yml": "kubernetes",
  "makefile": "makefile",
  "npm-shrinkwrap.json": "npm",
  "package-lock.json": "npm",
  "package.json": "npm",
  "pnpm-lock.yaml": "pnpm",
  "pnpm-workspace.yaml": "pnpm",
  "pom.xml": "maven",
  "pyproject.toml": "python",
  "requirements-dev.txt": "python",
  "requirements-test.txt": "python",
  "requirements.txt": "python",
  "settings.gradle": "gradle",
  "settings.gradle.kts": "gradle",
  "setup.py": "python",
  "terraform.lock.hcl": "lock",
  "tox.ini": "python",
  "yarn.lock": "yarn"
};

const EXTENSION_VISUALS: Record<string, string> = {
  ".7z": "zip",
  ".adoc": "document",
  ".arrow": "table",
  ".asciidoc": "document",
  ".astro": "astro",
  ".avro": "table",
  ".bash": "console",
  ".bat": "console",
  ".c": "c",
  ".cc": "cpp",
  ".cfg": "config",
  ".ckpt": "pytorch",
  ".clj": "clojure",
  ".cljc": "clojure",
  ".cljs": "clojure",
  ".conf": "config",
  ".cpp": "cpp",
  ".cs": "csharp",
  ".css": "css",
  ".csv": "table",
  ".cu": "cuda",
  ".cuh": "cuda",
  ".cxx": "cpp",
  ".dart": "dart",
  ".db": "database",
  ".duckdb": "database",
  ".env": "config",
  ".erl": "erlang",
  ".ex": "elixir",
  ".exs": "elixir",
  ".f": "fortran",
  ".f90": "fortran",
  ".f95": "fortran",
  ".feather": "table",
  ".fish": "console",
  ".ggml": "pytorch",
  ".gguf": "pytorch",
  ".go": "go",
  ".gql": "graphql",
  ".graphql": "graphql",
  ".gradle": "gradle",
  ".groovy": "groovy",
  ".h": "c",
  ".h5": "pytorch",
  ".hcl": "terraform",
  ".hdf5": "pytorch",
  ".hh": "cpp",
  ".hpp": "cpp",
  ".hrl": "erlang",
  ".hs": "haskell",
  ".htm": "html",
  ".html": "html",
  ".ini": "config",
  ".ipynb": "jupyter",
  ".java": "java",
  ".jl": "julia",
  ".joblib": "pytorch",
  ".json": "json",
  ".json5": "json",
  ".jsonc": "json",
  ".jsonl": "table",
  ".js": "javascript",
  ".jsx": "react",
  ".keras": "pytorch",
  ".kt": "kotlin",
  ".kts": "kotlin",
  ".ldb": "database",
  ".less": "less",
  ".lua": "lua",
  ".m": "c",
  ".markdown": "markdown",
  ".mat": "matlab",
  ".mdb": "database",
  ".md": "markdown",
  ".mdx": "markdown",
  ".mts": "typescript",
  ".ndjson": "table",
  ".nim": "nim",
  ".ods": "table",
  ".onnx": "onnx",
  ".orc": "table",
  ".parquet": "table",
  ".pb": "pytorch",
  ".pdf": "pdf",
  ".php": "php",
  ".pickle": "pytorch",
  ".pkl": "pytorch",
  ".pl": "perl",
  ".pm": "perl",
  ".prisma": "prisma",
  ".proto": "proto",
  ".ps1": "powershell",
  ".psd1": "powershell",
  ".psm1": "powershell",
  ".psv": "table",
  ".pt": "pytorch",
  ".pth": "pytorch",
  ".py": "python",
  ".pyi": "python",
  ".r": "r",
  ".rar": "zip",
  ".rb": "ruby",
  ".rkt": "racket",
  ".rst": "document",
  ".rs": "rust",
  ".sass": "sass",
  ".scala": "scala",
  ".scss": "sass",
  ".safetensors": "pytorch",
  ".sh": "console",
  ".sol": "solidity",
  ".sqlite": "database",
  ".sqlite3": "database",
  ".sql": "database",
  ".svg": "svg",
  ".svelte": "svelte",
  ".swift": "swift",
  ".tar": "zip",
  ".tf": "terraform",
  ".tflite": "pytorch",
  ".tfvars": "terraform",
  ".tgz": "zip",
  ".toml": "toml",
  ".ts": "typescript",
  ".tsv": "table",
  ".tsx": "react",
  ".txt": "document",
  ".vue": "vue",
  ".wasm": "webassembly",
  ".xls": "table",
  ".xlsx": "table",
  ".xml": "xml",
  ".yaml": "yaml",
  ".yml": "yaml",
  ".zip": "zip",
  ".zig": "zig",
  ".zsh": "console"
};

const TEXTUAL_NAME_KINDS = [
  "cmake",
  "config",
  "docker",
  "git",
  "go",
  "gradle",
  "helm",
  "kubernetes",
  "makefile",
  "maven",
  "npm",
  "pnpm",
  "python",
  "ruby",
  "rust",
  "yarn"
];
const MODEL_NAME_PATTERN = /(adapter|checkpoint|consolidated|diffusion|embedding|ggml|gguf|lora|model|pytorch|tensor|tokenizer|unet|vae|weights?)/;
const TENSORBOARD_NAME_PATTERN = /(events\.out\.tfevents|tensorboard|tblog)/;
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

function baseName(path) {
  const text = String(path || "");
  const parts = text.split("/");
  return (parts[parts.length - 1] || text).toLowerCase();
}

function pathExtension(path) {
  const name = baseName(path);
  for (let index = 0; index < MULTIPART_EXTENSIONS.length; index += 1) {
    if (name.endsWith(MULTIPART_EXTENSIONS[index])) {
      return MULTIPART_EXTENSIONS[index];
    }
  }
  const marker = name.lastIndexOf(".");
  if (marker < 0) {
    return "";
  }
  return name.slice(marker);
}

function matchesReadmeName(name) {
  return /^readme([._-]|$)/.test(name);
}

function matchesLicenseName(name) {
  return /^(license|licence|copying|notice|authors)([._-]|$)/.test(name);
}

function matchesDocsName(name) {
  return /^(changelog|changes|contributing|code_of_conduct|security|roadmap|release_notes)([._-]|$)/.test(name);
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
  const name = baseName(path);
  if (matchesReadmeName(name) || matchesLicenseName(name) || matchesDocsName(name)) {
    return true;
  }
  if (TENSORBOARD_NAME_PATTERN.test(name)) {
    return false;
  }
  if (name.indexOf(".safetensors") >= 0 || name.indexOf(".ckpt") >= 0) {
    return false;
  }

  const knownNameKind = EXACT_NAME_VISUALS[name];
  if (knownNameKind && TEXTUAL_NAME_KINDS.indexOf(knownNameKind) >= 0) {
    return true;
  }
  if (/^dockerfile([._-]|$)/.test(name) || /^docker-compose([._-].*)?\.(yaml|yml)$/.test(name) || /^compose([._-].*)?\.(yaml|yml)$/.test(name)) {
    return true;
  }
  if (/^requirements([._-].*)?\.txt$/.test(name) || /^tailwind\.config\./.test(name)) {
    return true;
  }

  return hasKnownExtension(path, TEXT_EXTENSIONS);
}

export function isCodeLikePath(path) {
  return hasKnownExtension(path, CODE_EXTENSIONS);
}

export function getFileVisualKind(path, entryType) {
  if (entryType === "folder") {
    return "folder";
  }

  const name = baseName(path);
  if (!name) {
    return "document";
  }
  if (matchesReadmeName(name)) {
    return "readme";
  }
  if (matchesLicenseName(name)) {
    return "license";
  }
  if (matchesDocsName(name)) {
    return "document";
  }
  if (TENSORBOARD_NAME_PATTERN.test(name)) {
    return "log";
  }
  if (name.indexOf(".safetensors") >= 0 || name.indexOf(".ckpt") >= 0) {
    return "pytorch";
  }
  if (EXACT_NAME_VISUALS[name]) {
    return EXACT_NAME_VISUALS[name];
  }
  if (/^dockerfile([._-]|$)/.test(name) || /^docker-compose([._-].*)?\.(yaml|yml)$/.test(name) || /^compose([._-].*)?\.(yaml|yml)$/.test(name)) {
    return "docker";
  }
  if (/^requirements([._-].*)?\.txt$/.test(name)) {
    return "python";
  }
  if (/^tailwind\.config\./.test(name)) {
    return "tailwindcss";
  }
  if (/^schema\.(graphql|gql)$/.test(name)) {
    return "graphql";
  }
  if (/^docker-compose([._-].*)?\.(yaml|yml)$/.test(name) || /^compose([._-].*)?\.(yaml|yml)$/.test(name)) {
    return "docker";
  }

  const extension = pathExtension(path);
  if (extension === ".bin" && MODEL_NAME_PATTERN.test(name)) {
    return "pytorch";
  }
  if (MODEL_EXTENSIONS.indexOf(extension) >= 0) {
    return "pytorch";
  }
  if (TABLE_EXTENSIONS.indexOf(extension) >= 0) {
    return "table";
  }
  if (DATABASE_EXTENSIONS.indexOf(extension) >= 0) {
    return "database";
  }
  if (ARCHIVE_EXTENSIONS.indexOf(extension) >= 0) {
    return "zip";
  }
  if (FONT_EXTENSIONS.indexOf(extension) >= 0) {
    return "font";
  }
  if (EXTENSION_VISUALS[extension]) {
    return EXTENSION_VISUALS[extension];
  }
  if (isImagePath(path)) {
    return extension === ".svg" ? "svg" : "image";
  }
  if (isAudioPath(path)) {
    return "audio";
  }
  if (isVideoPath(path)) {
    return "video";
  }
  if (isTextLikePath(path)) {
    return "document";
  }
  return "binary";
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
