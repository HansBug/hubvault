import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const overviewMocks = vi.hoisted(function buildOverviewMocks() {
  return {
    getBlobBytes: vi.fn(),
    getCommits: vi.fn(),
    getRepoFiles: vi.fn(),
    getStorageOverview: vi.fn()
  };
});

const sessionState = reactive({
  refs: null as any,
  repo: null as any,
  service: null as any
});

vi.mock("@/api/client", function mockClientModule() {
  return {
    getBlobBytes: overviewMocks.getBlobBytes,
    getCommits: overviewMocks.getCommits,
    getRepoFiles: overviewMocks.getRepoFiles,
    getStorageOverview: overviewMocks.getStorageOverview
  };
});

vi.mock("@/stores/session", function mockSessionStore() {
  return {
    useSessionStore: function useSessionStore() {
      return {
        state: readonly(sessionState)
      };
    }
  };
});

vi.mock("@/components/ReadmeViewer.vue", function mockReadmeViewer() {
  return {
    default: {
      props: ["path", "content", "loading"],
      template: "<div data-testid=\"readme-viewer\">{{ path }}|{{ loading ? 'loading' : content }}</div>"
    }
  };
});

vi.mock("@/components/RepoSummaryCards.vue", function mockSummaryCards() {
  return {
    default: {
      props: ["filesCount", "commitsCount"],
      template: "<div data-testid=\"repo-summary\">{{ filesCount }}|{{ commitsCount }}</div>"
    }
  };
});

import OverviewView from "@/views/OverviewView.vue";

const overviewStubs = {
  ElAlert: {
    props: ["title"],
    template: "<div class=\"el-alert\">{{ title }}</div>"
  },
  ElCard: {
    template: "<div class=\"el-card\"><slot /></div>"
  },
  ElSkeleton: {
    template: "<div class=\"el-skeleton\"></div>"
  },
  ElEmpty: {
    props: ["description"],
    template: "<div class=\"el-empty\">{{ description }}</div>"
  }
};

describe("OverviewView", function suite() {
  beforeEach(function resetSessionState() {
    vi.clearAllMocks();
    sessionState.refs = {
      branches: [{ name: "release/v1" }],
      tags: [{ name: "v1.0" }]
    };
    sessionState.repo = {
      default_branch: "release/v1",
      head: "1234567890abcdef1234567890abcdef12345678"
    };
    sessionState.service = {
      repo: {
        default_branch: "release/v1",
        path: "/tmp/repo"
      }
    };
  });

  it("loads summary data and README content", async function testOverviewSuccess() {
    overviewMocks.getRepoFiles.mockResolvedValueOnce(["README.md", "docs/guide.md"]);
    overviewMocks.getCommits.mockResolvedValueOnce([
      {
        commit_id: "1234567890abcdef1234567890abcdef12345678",
        title: "first",
        created_at: "2026-04-12T00:00:00Z"
      }
    ]);
    overviewMocks.getStorageOverview.mockResolvedValueOnce({
      total_size: 4096
    });
    overviewMocks.getBlobBytes.mockResolvedValueOnce(new TextEncoder().encode("# README\n").buffer);

    const wrapper = mount(OverviewView, {
      props: {
        revision: "release/v1"
      },
      global: {
        stubs: overviewStubs
      }
    });

    await flushPromises();

    expect(wrapper.get("[data-testid='repo-summary']").text()).toBe("2|1");
    expect(wrapper.get("[data-testid='readme-viewer']").text()).toContain("README.md|# README");
    expect(wrapper.text()).toContain("/tmp/repo");
    expect(wrapper.text()).toContain("first");
  });

  it("shows a route-level error when loading fails", async function testOverviewFailure() {
    overviewMocks.getRepoFiles.mockRejectedValueOnce(new Error("overview failed"));

    const wrapper = mount(OverviewView, {
      props: {
        revision: "release/v1"
      },
      global: {
        stubs: overviewStubs
      }
    });

    await flushPromises();
    await flushPromises();

    expect(wrapper.text()).toContain("overview failed");
  });
});
