import { describe, expect, it } from "vitest";

import { basename, buildExactUploadManifest, joinRepoPath } from "@/utils/uploads";

describe("upload helpers", function suite() {
  it("joins repo paths without duplicate separators", function testJoinRepoPath() {
    expect(joinRepoPath("", "demo.txt")).toBe("demo.txt");
    expect(joinRepoPath("nested", "demo.txt")).toBe("nested/demo.txt");
    expect(joinRepoPath("/nested/", "/deep/demo.txt")).toBe("nested/deep/demo.txt");
    expect(basename("nested/deep/demo.txt")).toBe("demo.txt");
  });

  it("builds exact upload manifests from browser files and reports progress", async function testBuildExactUploadManifest() {
    const file = new File(["hello world"], "demo.txt", {
      type: "text/plain"
    });
    const events: any[] = [];

    const result = await buildExactUploadManifest(
      [
        {
          pathInRepo: "docs/demo.txt",
          file: file
        }
      ],
      function handleProgress(payload) {
        events.push({
          phase: payload.phase,
          currentPathInRepo: payload.currentPathInRepo,
          completedEntries: payload.completedEntries,
          totalEntries: payload.totalEntries,
          processedBytes: payload.processedBytes,
          totalBytes: payload.totalBytes
        });
      }
    );

    expect(result.operations).toEqual([
      {
        type: "add",
        path_in_repo: "docs/demo.txt",
        size: 11,
        sha256: "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9",
        chunks: []
      }
    ]);
    expect(result.uploads[0].file).toBe(file);
    expect(events.map(function collectPhase(item) {
      return item.phase;
    })).toEqual(expect.arrayContaining(["reading", "hashing", "completed"]));
    expect(events[events.length - 1]).toMatchObject({
      phase: "completed",
      currentPathInRepo: "docs/demo.txt",
      completedEntries: 1,
      totalEntries: 1,
      processedBytes: 11,
      totalBytes: 11
    });
  });
});
