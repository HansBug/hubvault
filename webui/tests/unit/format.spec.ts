import { describe, expect, it } from "vitest";

import { formatBytes, formatDateTime, formatRelativeDate, shortOid } from "@/utils/format";

describe("format helpers", function suite() {
  it("formats bytes across ranges", function testFormatting() {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("shortens oids for compact display", function testShortOid() {
    expect(shortOid("1234567890abcdef")).toBe("1234567890");
    expect(shortOid("short")).toBe("short");
    expect(shortOid(undefined as any)).toBe("");
  });

  it("formats absolute and relative dates with unknown fallbacks", function testDateFormatting() {
    expect(formatDateTime("2026-04-12 00:00:00")).toBe("2026-04-12 00:00:00");
    expect(formatDateTime("")).toBe("Unknown");
    expect(formatRelativeDate("2026-04-12T00:00:00Z")).not.toBe("Unknown");
    expect(formatRelativeDate("")).toBe("Unknown");
  });
});
