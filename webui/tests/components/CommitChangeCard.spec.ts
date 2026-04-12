import ElementPlus from "element-plus";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/HtmlDiffViewer.vue", function mockHtmlDiffViewer() {
  return {
    default: {
      props: ["diffText"],
      template: "<div data-testid='html-diff-viewer-stub'>{{ diffText }}</div>"
    }
  };
});

vi.mock("@/components/ImageCompareViewer.vue", function mockImageCompareViewer() {
  return {
    default: {
      props: ["oldImageUrl", "newImageUrl"],
      template: "<div data-testid='image-compare-viewer-stub'>{{ oldImageUrl }}|{{ newImageUrl }}</div>"
    }
  };
});

import CommitChangeCard from "@/components/CommitChangeCard.vue";

describe("CommitChangeCard", function suite() {
  it("renders text diffs without binary metadata panels", function testTextChange() {
    const wrapper = mount(CommitChangeCard, {
      props: {
        commitId: "commit-2",
        compareParentCommitId: "commit-1",
        change: {
          path: "docs/guide.md",
          change_type: "modified",
          is_binary: false,
          unified_diff: "diff --git a/docs/guide.md b/docs/guide.md\n",
          old_file: {
            path: "docs/guide.md",
            size: 10,
            oid: "1111111111111111111111111111111111111111",
            blob_id: "blob-old",
            sha256: "old-sha"
          },
          new_file: {
            path: "docs/guide.md",
            size: 12,
            oid: "2222222222222222222222222222222222222222",
            blob_id: "blob-new",
            sha256: "new-sha"
          }
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.text()).toContain("docs/guide.md");
    expect(wrapper.text()).toContain("10 B -> 12 B");
    expect(wrapper.get("[data-testid='html-diff-viewer-stub']").text()).toContain("diff --git");
    expect(wrapper.find("[data-testid='binary-metadata-panel']").exists()).toBe(false);
    expect(wrapper.html()).toContain("/api/v1/content/download/docs/guide.md?revision=commit-2");
  });

  it("delegates image changes to the image comparison viewer without binary metadata", function testImageChange() {
    const wrapper = mount(CommitChangeCard, {
      props: {
        commitId: "commit-2",
        compareParentCommitId: "commit-1",
        change: {
          path: "images/logo.png",
          change_type: "modified",
          is_binary: true,
          unified_diff: null,
          old_file: {
            path: "images/logo.png",
            size: 100,
            oid: "old-oid",
            blob_id: "old-blob",
            sha256: "old-sha"
          },
          new_file: {
            path: "images/logo.png",
            size: 200,
            oid: "new-oid",
            blob_id: "new-blob",
            sha256: "new-sha"
          }
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("[data-testid='image-compare-viewer-stub']").text()).toContain(
      "/api/v1/content/blob/images/logo.png?revision=commit-1"
    );
    expect(wrapper.get("[data-testid='image-compare-viewer-stub']").text()).toContain(
      "/api/v1/content/blob/images/logo.png?revision=commit-2"
    );
    expect(wrapper.find("[data-testid='binary-metadata-panel']").exists()).toBe(false);
  });

  it("shows compact metadata only for opaque binary changes", function testBinaryMetadataChange() {
    const wrapper = mount(CommitChangeCard, {
      props: {
        commitId: "commit-2",
        compareParentCommitId: "commit-1",
        change: {
          path: "artifacts/model.bin",
          change_type: "added",
          is_binary: true,
          unified_diff: null,
          old_file: null,
          new_file: {
            path: "artifacts/model.bin",
            size: 9321,
            oid: "new-oid-1234567890",
            blob_id: "new-blob",
            sha256: "new-sha-1234567890"
          }
        }
      },
      global: {
        plugins: [ElementPlus]
      }
    });

    expect(wrapper.get("[data-testid='binary-metadata-panel']").text()).toContain("Before");
    expect(wrapper.get("[data-testid='binary-metadata-panel']").text()).toContain("Not present");
    expect(wrapper.get("[data-testid='binary-metadata-panel']").text()).toContain("After");
    expect(wrapper.find("[data-testid='html-diff-viewer-stub']").exists()).toBe(false);
    expect(wrapper.find("[data-testid='image-compare-viewer-stub']").exists()).toBe(false);
  });
});
