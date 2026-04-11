import { describe, expect, it } from "vitest";

import { basename, buildExactUploadManifest, joinRepoPath } from "@/utils/uploads";

describe("upload helpers", function suite() {
  it("joins repo paths without duplicate separators", function testJoinRepoPath() {
    expect(joinRepoPath("", "demo.txt")).toBe("demo.txt");
    expect(joinRepoPath("nested", "demo.txt")).toBe("nested/demo.txt");
    expect(joinRepoPath("/nested/", "/deep/demo.txt")).toBe("nested/deep/demo.txt");
    expect(basename("nested/deep/demo.txt")).toBe("demo.txt");
  });

  it("builds exact upload manifests from browser files", async function testBuildExactUploadManifest() {
    const file = new File(["hello world"], "demo.txt", {
      type: "text/plain"
    });

    const result = await buildExactUploadManifest([
      {
        pathInRepo: "docs/demo.txt",
        file: file
      }
    ]);

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
  });
});
