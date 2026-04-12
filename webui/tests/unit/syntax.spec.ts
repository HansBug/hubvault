import { describe, expect, it } from "vitest";

import { getFileExtension, guessCodeLanguage } from "@/utils/syntax";

describe("syntax helpers", function suite() {
  it("maps common repository extensions to Prism languages", function testLanguageGuessing() {
    expect(getFileExtension("docs/readme.md")).toBe("md");
    expect(guessCodeLanguage("src/app.py")).toBe("python");
    expect(guessCodeLanguage("configs/settings.yaml")).toBe("yaml");
    expect(guessCodeLanguage("README.txt")).toBe("text");
    expect(guessCodeLanguage("unknown.custom")).toBe("text");
  });
});
