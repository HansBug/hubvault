import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import FileTable from '@/components/FileTable.vue';

const ElTableStub = {
  props: ['data'],
  provide() {
    return {
      tableRows: this.data
    };
  },
  template: `<div class='el-table-stub'><slot /></div>`
};

const ElTableColumnStub = {
  inject: ['tableRows'],
  template: [
    `<div class='el-table-column-stub'>`,
    `  <div v-for='row in tableRows' :key='row.path'>`,
    `    <slot :row='row' />`,
    `  </div>`,
    `</div>`
  ].join('')
};

function findButtonByLabelOrText(wrapper, value: string) {
  const button = wrapper.findAll('button').find(function findMatch(item) {
    return item.text().trim() === value || item.attributes('aria-label') === value;
  });
  expect(button).toBeTruthy();
  return button!;
}

describe('FileTable', function suite() {
  it('renders per-file-kind icons, commit links, and action buttons', async function testFileTable() {
    const wrapper = mount(FileTable, {
      props: {
        revision: 'release/v1',
        canWrite: true,
        entries: [
          {
            path: 'docs',
            entry_type: 'folder',
            size: 0,
            last_commit: {
              oid: 'commit-docs',
              title: 'update docs',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: '.gitattributes',
            entry_type: 'file',
            size: 128,
            last_commit: {
              oid: 'commit-meta',
              title: 'track large artifacts',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'Dockerfile',
            entry_type: 'file',
            size: 256,
            last_commit: {
              oid: 'commit-docker',
              title: 'refresh container flow',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'LICENSE',
            entry_type: 'file',
            size: 96,
            last_commit: {
              oid: 'commit-license',
              title: 'add license',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'README.md',
            entry_type: 'file',
            size: 144,
            last_commit: {
              oid: 'commit-root-readme',
              title: 'add root readme',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'models/model.safetensors',
            entry_type: 'file',
            size: 2048,
            last_commit: {
              oid: 'commit-model',
              title: 'update weights',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'data/train.parquet',
            entry_type: 'file',
            size: 4096,
            last_commit: {
              oid: 'commit-data',
              title: 'refresh data',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'runs/events.out.tfevents.1710000.fixture',
            entry_type: 'file',
            size: 1024,
            last_commit: {
              oid: 'commit-runs',
              title: 'record metrics',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'docs/readme.md',
            entry_type: 'file',
            size: 1024,
            last_commit: {
              oid: 'commit-readme',
              title: 'add readme',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'media/clip.wav',
            entry_type: 'file',
            size: 512,
            last_commit: {
              oid: 'commit-audio',
              title: 'add clip',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'media/demo.mp4',
            entry_type: 'file',
            size: 2048,
            last_commit: {
              oid: 'commit-video',
              title: 'add demo',
              date: '2026-04-12T00:00:00Z'
            }
          },
          {
            path: 'src/app.py',
            entry_type: 'file',
            size: 256,
            last_commit: {
              oid: 'commit-python',
              title: 'add python entry',
              date: '2026-04-12T00:00:00Z'
            }
          }
        ]
      },
      global: {
        stubs: {
          ElIcon: {
            template: `<span class='el-icon'><slot /></span>`
          },
          ElTooltip: {
            template: `<span class='el-tooltip-stub'><slot /></span>`
          },
          ElTable: ElTableStub,
          ElTableColumn: ElTableColumnStub,
          Icon: {
            props: ['icon'],
            template: `<span class='iconify-stub'></span>`
          },
          ElButton: {
            props: ['href', 'ariaLabel', 'tag'],
            emits: ['click'],
            template: `<button :aria-label='ariaLabel' :data-href='href' @click="$emit('click')"><slot /></button>`
          }
        }
      }
    });

    expect(findButtonByLabelOrText(wrapper, 'docs').attributes('data-file-kind')).toBe('folder');
    expect(findButtonByLabelOrText(wrapper, '.gitattributes').attributes('data-file-kind')).toBe('git');
    expect(findButtonByLabelOrText(wrapper, 'Dockerfile').attributes('data-file-kind')).toBe('docker');
    expect(findButtonByLabelOrText(wrapper, 'LICENSE').attributes('data-file-kind')).toBe('license');
    expect(findButtonByLabelOrText(wrapper, 'README.md').attributes('data-file-kind')).toBe('readme');
    expect(findButtonByLabelOrText(wrapper, 'model.safetensors').attributes('data-file-kind')).toBe('safetensors');
    expect(findButtonByLabelOrText(wrapper, 'train.parquet').attributes('data-file-kind')).toBe('table');
    expect(findButtonByLabelOrText(wrapper, 'events.out.tfevents.1710000.fixture').attributes('data-file-kind')).toBe('log');
    expect(findButtonByLabelOrText(wrapper, 'readme.md').attributes('data-file-kind')).toBe('readme');
    expect(findButtonByLabelOrText(wrapper, 'clip.wav').attributes('data-file-kind')).toBe('audio');
    expect(findButtonByLabelOrText(wrapper, 'demo.mp4').attributes('data-file-kind')).toBe('video');
    expect(findButtonByLabelOrText(wrapper, 'app.py').attributes('data-file-kind')).toBe('python');

    await findButtonByLabelOrText(wrapper, 'docs').trigger('click');
    await findButtonByLabelOrText(wrapper, 'readme.md').trigger('click');
    await findButtonByLabelOrText(wrapper, 'update docs').trigger('click');
    await findButtonByLabelOrText(wrapper, 'Open folder docs').trigger('click');
    await findButtonByLabelOrText(wrapper, 'Delete docs/readme.md').trigger('click');

    expect(wrapper.emitted('open-folder')).toContainEqual(['docs']);
    expect(wrapper.emitted('open-file')).toContainEqual(['docs/readme.md']);
    expect(wrapper.emitted('open-commit')).toContainEqual(['commit-docs']);
    expect(wrapper.emitted('delete-entry')).toHaveLength(1);
    expect(wrapper.html()).toContain('Download docs/readme.md');
    expect(wrapper.html()).toContain('/api/v1/content/download/docs/readme.md?revision=release%2Fv1');
  });

  it('shows stable fallbacks for unknown commit metadata and hides write-only actions', async function testFileTableFallbacks() {
    const wrapper = mount(FileTable, {
      props: {
        revision: 'release/v1',
        canWrite: false,
        entries: [
          {
            path: 'artifacts',
            entry_type: 'folder',
            size: 0
          },
          {
            path: 'opaque/payload.bin',
            entry_type: 'file',
            size: 8192,
            last_commit: {
              oid: 'commit-unknown',
              title: '',
              date: '2026-04-12T00:00:00Z'
            }
          }
        ]
      },
      global: {
        stubs: {
          ElIcon: {
            template: `<span class='el-icon'><slot /></span>`
          },
          ElTooltip: {
            template: `<span class='el-tooltip-stub'><slot /></span>`
          },
          ElTable: ElTableStub,
          ElTableColumn: ElTableColumnStub,
          Icon: {
            props: ['icon'],
            template: `<span class='iconify-stub'></span>`
          },
          ElButton: {
            props: ['href', 'ariaLabel', 'tag'],
            emits: ['click'],
            template: `<button :aria-label='ariaLabel' :data-href='href' @click="$emit('click')"><slot /></button>`
          }
        }
      }
    });

    expect(findButtonByLabelOrText(wrapper, 'payload.bin').attributes('data-file-kind')).toBe('binary');
    expect(wrapper.text()).toContain('Unknown');
    await findButtonByLabelOrText(wrapper, 'Unknown').trigger('click');
    expect(wrapper.emitted('open-commit')).toContainEqual(['commit-unknown']);
    expect(wrapper.html()).toContain('Download opaque/payload.bin');
    expect(wrapper.html()).not.toContain('Delete opaque/payload.bin');
    expect(wrapper.html()).not.toContain('Download artifacts');
    expect(wrapper.findAll('button').some(function hasUnknownCommitButton(item) {
      return item.text().trim() === 'Unknown';
    })).toBe(true);
  });
});
