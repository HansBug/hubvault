import { describe, expect, it } from "vitest";

import { formatBytes, shortOid } from "@/utils/format";

describe("format helpers", function suite() {
  it("formats bytes across ranges", function testFormatting() {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("shortens oids for compact display", function testShortOid() {
    expect(shortOid("1234567890abcdef")).toBe("1234567890");
    expect(shortOid("short")).toBe("short");
  });
});
