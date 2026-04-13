import { flushPromises, mount } from "@vue/test-utils";
import { reactive, readonly } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const overviewMocks = vi.hoisted(function buildOverviewMocks() {
  return {
    getBlobBytes: vi.fn(),
    getCommits: vi.fn(),
    getRepoFiles: vi.fn(),
    getStorageOverview: vi.fn(),
    push: vi.fn()
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

vi.mock("vue-router", function mockVueRouter() {
  return {
    useRouter: function useRouter() {
      return {
        push: overviewMocks.push
      };
    }
  };
});

vi.mock("@/components/ReadmeViewer.vue", function mockReadmeViewer() {
  return {
    default: {
      props: ["path", "content", "loading"],
      template: `<div data-testid="readme-viewer">{{ path }}|{{ loading ? 'loading' : content }}</div>`
    }
  };
});

vi.mock("@/components/RepoSummaryCards.vue", function mockSummaryCards() {
  return {
    default: {
      props: ["filesCount", "commitsCount"],
      template: `<div data-testid="repo-summary">{{ filesCount }}|{{ commitsCount }}</div>`
    }
  };
});

import OverviewView from "@/views/OverviewView.vue";

const overviewStubs = {
  ElAlert: {
    props: ["title"],
    template: `<div class="el-alert">{{ title }}</div>`
  },
  ElButton: {
    emits: ["click"],
    template: `<button @click="$emit('click')"><slot /></button>`
  },
  ElCard: {
    template: `<div class="el-card"><slot /></div>`
  },
  ElSkeleton: {
    template: `<div class="el-skeleton"></div>`
  },
  ElEmpty: {
    props: ["description"],
    template: `<div class="el-empty">{{ description }}</div>`
  }
};

function findButtonByText(wrapper, value: string) {
  const button = wrapper.findAll("button").find(function findMatch(item) {
    return item.text().indexOf(value) >= 0;
  });
  expect(button).toBeTruthy();
  return button!;
}

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

  it("loads summary data, keeps overview side cards isolated, and opens commit detail from recent commits", async function testOverviewSuccess() {
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
    expect(wrapper.get("[data-testid='overview-snapshot-card']").text()).toContain("/tmp/repo");
    expect(wrapper.get("[data-testid='overview-commits-card']").text()).toContain("first");
    expect(wrapper.get(".overview-content-grid").classes()).toContain("overview-content-grid");
    expect(wrapper.get(".overview-sidebar").classes()).toContain("overview-sidebar");

    await findButtonByText(wrapper, "first").trigger("click");

    expect(overviewMocks.push).toHaveBeenCalledWith({
      name: "commit-detail",
      params: {
        commitId: "1234567890abcdef1234567890abcdef12345678"
      },
      query: {
        revision: "release/v1"
      }
    });
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

  it("keeps readme content empty when no root readme exists and falls back snapshot metadata to the service defaults", async function testOverviewFallbackBranches() {
    sessionState.repo = {
      default_branch: "",
      head: ""
    };
    sessionState.service = {
      repo: {
        default_branch: "main",
        path: "/tmp/service-only"
      }
    };
    overviewMocks.getRepoFiles.mockResolvedValueOnce(["docs/guide.md"]);
    overviewMocks.getCommits.mockResolvedValueOnce([]);
    overviewMocks.getStorageOverview.mockResolvedValueOnce({
      total_size: 0
    });

    const wrapper = mount(OverviewView, {
      props: {
        revision: "main"
      },
      global: {
        stubs: overviewStubs
      }
    });

    await flushPromises();

    expect(overviewMocks.getBlobBytes).not.toHaveBeenCalled();
    expect(wrapper.get("[data-testid='readme-viewer']").text()).toBe("|");
    expect(wrapper.get("[data-testid='overview-snapshot-card']").text()).toContain("main");
    expect(wrapper.get("[data-testid='overview-commits-card']").text()).toContain("No commits available.");

    overviewMocks.getRepoFiles.mockRejectedValueOnce({});

    const errorWrapper = mount(OverviewView, {
      props: {
        revision: "main"
      },
      global: {
        stubs: overviewStubs
      }
    });

    await flushPromises();
    await flushPromises();

    expect(errorWrapper.text()).toContain("Unable to load overview data.");
  });
});
