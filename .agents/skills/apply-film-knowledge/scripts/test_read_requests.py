"""End-to-end reading locators retain the text's final conditions and original scope."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from retrieve_knowledge import load_config, retrieve_scoped
from knowledge_review import read_request, review_scoped
from knowledge_evidence import full_evidence
from read_knowledge_section import extract_heading


class ReadRequestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('vault/.obsidian', 'vault/library/creation/C-导演与视觉', 'vault/library/learning', 'cache', 'skills', '.codex'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root/'vault/box.md').write_text('# box', encoding='utf-8')
        self.cp = self.root/'.codex/knowledge-tree.json'
        self.cp.write_text(json.dumps({'version': 2, 'workspace': '..', 'vault': 'vault', 'vault_name': 'fixture',
            'knowledge_library': 'vault/library', 'creation_root': 'vault/library/creation',
            'learning_root': 'vault/library/learning', 'source_notes': 'vault/library/learning',
            'raw_cache': 'cache', 'prompt_box': 'vault/box.md', 'skills_root': 'skills', 'obsidian_cli': None}), encoding='utf-8')
        self.config = load_config(self.cp)
        self.path = self.root/'vault/library/creation/C-导演与视觉/方法.md'
        self.path.write_text('---\n类型: 主题笔记\n分类: 导演与视听语言\n---\n# 服装状态\n'
            '## 方法与案例\n### 服装状态链\n' + '服装状态链需要比较同一人物。'*420 +
            '\n```text\n## 不是真标题\n```\n仅限同一角色同一时段；不应用于平行世界。\n'
            '## 适用边界\n先确认角色身份。\n', encoding='utf-8')

    def quick(self):
        return retrieve_scoped(self.config, '服装状态链', role='C', no_cache=True)

    def test_quick_to_paged_section_keeps_final_boundary_and_fence(self):
        result = self.quick()
        chunk = result['candidates'][0]['method_chunks'][0]
        self.assertEqual(chunk['heading'], '服装状态链')
        self.assertTrue(chunk['truncated'])
        request = chunk['continuation']
        self.assertEqual(request['offset'], 0)  # Do not append a normalized preview to exact text.
        parts = []
        while request:
            out = read_request(self.config, request, self.cp)
            self.assertEqual(out['kind'], 'topic')
            parts.append(out['content'])
            request = out['continuation']
        expected = extract_heading(self.path.read_bytes().decode('utf-8'), '服装状态链')[1]
        self.assertEqual(''.join(parts), expected)
        self.assertIn('不应用于平行世界', parts[-1])
        self.assertIn('## 不是真标题', ''.join(parts))

    def test_source_evidence_continuation_keeps_kind_and_full_text(self):
        source = self.path.with_name('来源.md')
        source.write_text('---\n类型: 来源笔记\n材料类型: 专业资料\n---\n# 频闪时基\n## 频闪时基\n'+
            '频闪时基需要核对快门与设备。'*500+'\n只在明确设备模式后适用。', encoding='utf-8')
        pack, corpus = review_scoped(self.config, '频闪时基', ['频闪时基'], role='C', no_cache=True)
        item = next(e for e in pack['evidence'] if e['read_required'] and e['id'] in pack['facets'][0]['evidence_ids'])
        request, pieces = item['continuation'], []
        while request:
            out = read_request(self.config, request, self.cp)['evidence']
            self.assertEqual(out['kind'], 'source')
            pieces.append(out['excerpt']); request = out['continuation']
        self.assertEqual(''.join(pieces), full_evidence(corpus, item['id'])['excerpt'])
        self.assertIn('明确设备模式', pieces[-1])

    def test_changed_text_rejects_original_request(self):
        request = self.quick()['candidates'][0]['method_chunks'][0]['continuation']
        self.path.write_text(self.path.read_text(encoding='utf-8')+'\n变更', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '变化'):
            read_request(self.config, request, self.cp)

    def test_section_source_identity(self):
        self.path.write_text(self.path.read_text(encoding='utf-8').replace('主题笔记', '来源笔记'), encoding='utf-8')
        pack, corpus = review_scoped(self.config, '服装状态链', ['服装状态链'], role='C', no_cache=True)
        out = read_request(self.config, {'mode': 'section', 'path': str(self.path), 'heading': '服装状态链',
            'scope': pack['scope'], 'snapshot': pack['snapshot'],
            'document_hash': hashlib.sha256(self.path.read_bytes()).hexdigest()}, self.cp)
        self.assertEqual(out['kind'], 'source')

    def test_scope_unknown_fields_offsets_and_config_are_not_silently_accepted(self):
        request = self.quick()['candidates'][0]['method_chunks'][0]['continuation']
        changes = [{'scope': None}, {'include_path': 'vault/library/learning'}, {'offset': True},
                   {'offset': -1}, {'max_chars': 0}, {'config': str(self.root/'other.json')}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                read_request(self.config, {**request, **change}, self.cp)

    def test_cli_read_request_rejects_even_empty_extra_query(self):
        request = self.quick()['candidates'][0]['method_chunks'][0]['continuation']
        proc = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(Path(__file__).with_name('knowledge_review.py')),
            '--config', str(self.cp), '--read-request', json.dumps(request, ensure_ascii=False), '--query', ''],
            text=True, capture_output=True, encoding='utf-8')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('不可同时', proc.stdout)

    def test_short_sections_need_no_extra_read(self):
        self.path.write_text('---\n类型: 主题笔记\n---\n# 服装状态链\n## 方法与案例\n服装状态链只核对同一角色。', encoding='utf-8')
        card = self.quick()['candidates'][0]
        self.assertFalse(card['read_required'])
        self.assertFalse(card['truncated'])


if __name__ == '__main__':
    unittest.main()
