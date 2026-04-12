import Prism from "prismjs";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-css";
import "prismjs/components/prism-diff";
import "prismjs/components/prism-ini";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-json";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-markup";
import "prismjs/components/prism-python";
import "prismjs/components/prism-toml";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-yaml";
import "prismjs/plugins/line-numbers/prism-line-numbers";

const LANGUAGE_BY_EXTENSION: Record<string, string> = {
  bash: "bash",
  cfg: "ini",
  css: "css",
  csv: "text",
  diff: "diff",
  htm: "markup",
  html: "markup",
  ini: "ini",
  js: "javascript",
  json: "json",
  md: "markdown",
  markdown: "markdown",
  py: "python",
  rst: "text",
  sh: "bash",
  toml: "toml",
  ts: "typescript",
  txt: "text",
  vue: "markup",
  xml: "markup",
  yaml: "yaml",
  yml: "yaml"
};

const LANGUAGE_ALIASES: Record<string, string> = {
  bash: "bash",
  css: "css",
  diff: "diff",
  html: "markup",
  ini: "ini",
  javascript: "javascript",
  js: "javascript",
  json: "json",
  markdown: "markdown",
  md: "markdown",
  markup: "markup",
  plaintext: "text",
  py: "python",
  python: "python",
  rst: "text",
  sh: "bash",
  shell: "bash",
  svg: "markup",
  text: "text",
  toml: "toml",
  ts: "typescript",
  typescript: "typescript",
  txt: "text",
  vue: "markup",
  xml: "markup",
  yaml: "yaml",
  yml: "yaml"
};

function normalizeLanguageName(language: string): string {
  return String(language || "")
    .trim()
    .toLowerCase()
    .replace(/^language-/, "");
}

function escapeHtml(value: string): string {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function resolveCodeLanguage(languageHint: string): string {
  const normalized = normalizeLanguageName(languageHint);
  const resolved = LANGUAGE_ALIASES[normalized] || normalized;
  if (resolved && Prism.languages[resolved]) {
    return resolved;
  }
  return "text";
}

export function getFileExtension(path: string): string {
  const text = String(path || "");
  const parts = text.split(".");
  if (parts.length < 2) {
    return "";
  }
  return parts[parts.length - 1].toLowerCase();
}

export function guessCodeLanguage(path: string): string {
  const extension = getFileExtension(path);
  return resolveCodeLanguage(LANGUAGE_BY_EXTENSION[extension] || "text");
}

export function highlightCode(content: string, languageHint: string): string {
  const resolvedLanguage = resolveCodeLanguage(languageHint);
  const grammar = Prism.languages[resolvedLanguage];
  if (!grammar || resolvedLanguage === "text") {
    return escapeHtml(content);
  }
  return Prism.highlight(String(content || ""), grammar, resolvedLanguage);
}

export function highlightCodeElement(element: Element | null | undefined) {
  if (!element) {
    return;
  }
  Prism.highlightElement(element as HTMLElement);
}
