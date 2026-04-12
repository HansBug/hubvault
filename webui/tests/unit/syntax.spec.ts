import { describe, expect, it } from "vitest";

import { getFileExtension, guessCodeLanguage, highlightCode, resolveCodeLanguage } from "@/utils/syntax";

describe("syntax helpers", function suite() {
  it("maps common repository extensions to Prism languages", function testLanguageGuessing() {
    expect(getFileExtension("docs/readme.md")).toBe("md");
    expect(guessCodeLanguage("src/app.py")).toBe("python");
    expect(guessCodeLanguage("configs/settings.yaml")).toBe("yaml");
    expect(guessCodeLanguage("README.txt")).toBe("text");
    expect(guessCodeLanguage("unknown.custom")).toBe("text");
  });

  it("resolves fence aliases and highlights supported languages", function testHighlighting() {
    expect(resolveCodeLanguage("js")).toBe("javascript");
    expect(resolveCodeLanguage("language-python")).toBe("python");
    expect(resolveCodeLanguage("unknown-language")).toBe("text");
    expect(highlightCode("const value = 1;", "javascript")).toContain("token keyword");
    expect(highlightCode("<tag>", "text")).toContain("&lt;tag&gt;");
  });
});
