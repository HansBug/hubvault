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
  return LANGUAGE_BY_EXTENSION[extension] || "text";
}

export function highlightCodeElement(element: Element | null | undefined) {
  if (!element) {
    return;
  }
  Prism.highlightElement(element as HTMLElement);
}
