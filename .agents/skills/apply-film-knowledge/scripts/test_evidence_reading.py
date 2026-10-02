"""Reading, provenance and context regressions using disposable knowledge files."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from knowledge_evidence import load_corpus, make_review, candidates, full_evidence, resolve_link
from read_knowledge_section import read_section, extract_heading


def topic(title, body, kind='主题笔记'):
    return f'---\n类型: {kind}\n分类: 导演与视听语言\n材料类型: 主题沉淀\n---\n# {title}\n\n{body}\n'


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ('vault/.obsidian','vault/library','vault/sources','cache','skills','.codex'):
            (self.root/name).mkdir(parents=True,exist_ok=True)
        self.vault=self.root/'vault'
        self.library=self.vault/'library'
        (self.vault/'box.md').write_text('# box',encoding='utf-8')
        self.config_path=self.root/'.codex/knowledge-tree.json'
        self.config_path.write_text(json.dumps({'version':2,'workspace':'..','vault':'vault','vault_name':'fixture',
             'knowledge_library':'vault/library','source_notes':'vault/sources','raw_cache':'cache',
             'prompt_box':'vault/box.md','obsidian_cli':None,'skills_root':'skills'}),encoding='utf-8')
        self.config={'vault':str(self.vault),'knowledge_library':str(self.library),
                     'source_notes':str(self.vault/'sources'),'raw_cache':str(self.root/'cache')}
        self.path=self.library/'方法.md'

    def tearDown(self):
        self.temp.cleanup()

    def write(self, body):
        self.path.write_text(topic('方法',body),encoding='utf-8')

    def test_large_table_returns_exact_row_and_required_context(self):
        rows=['| 项目 | 适用 | 边界 |','|---|---|---|']
        rows += [f'| 技术{i} | 参数{i} | 不可凭表格保证效果 |' for i in range(20)]
        rows.insert(9,'| 双层透片 | 两个分别清楚的区域 | 中间区域不能保证清楚 |')
        self.write('## 器材比较\n\n只在两主体固定时比较以下候选。\n\n'+'\n'.join(rows)+'\n\n人物移动越过交界时需要重新测试。')
        c=load_corpus(self.config)
        ranked=candidates(c,'双层透片',limit=3)
        row=ranked[0]['block']
        self.assertEqual(row['fragment_kind'],'table_row')
        self.assertNotIn('技术19',row['text'])
        contexts=[full_evidence(c,item)['excerpt'] for item in row['context_ids']]
        self.assertTrue(any('| 项目 |' in value for value in contexts))
        self.assertTrue(any('两主体固定' in value for value in contexts))
        self.assertTrue(any('移动越过交界' in value for value in contexts))
        self.assertIn('技术19',full_evidence(c,row['parent_id'])['excerpt'])
        source=self.path.read_text(encoding='utf-8').splitlines()
        doc=next(iter(c['documents'].values()))
        self.assertEqual(len(doc['blocks']),len({b['id'] for b in doc['blocks']}))
        for b in doc['blocks']:
            self.assertEqual(b['text'],'\n'.join(source[b['line_start']-1:b['line_end']]))
        pack=make_review(c,'选择器材',['双层透片'])
        primary=next(e for e in pack['evidence'] if e['id']==pack['facets'][0]['evidence_ids'][0])
        self.assertTrue(set(primary['context_ids']).issubset(pack['facets'][0]['context_ids']))

    def test_fenced_table_remains_code(self):
        self.write('## 示例\n```text\n| 值 | 条件 |\n|---|---|\n'+'\n'.join('| x | y |' for _ in range(20))+'\n```\n这只是代码示范。')
        c=load_corpus(self.config)
        blocks=next(iter(c['documents'].values()))['blocks']
        self.assertFalse(any(b.get('fragment_kind')=='table_row' for b in blocks))

    def test_multiple_tables_keep_shared_final_condition(self):
        first=['| 装置 | 用途 |','|---|---|']+[f'| 棱镜{i} | 参数{i} |' for i in range(10)]
        second=['| 设置 | 用途 |','|---|---|','| 其他设置 | 对照 |']
        self.write('## 同条件比较\n适用配置如下。\n\n'+'\n'.join(first)+'\n\n第二组设置如下。\n\n'+'\n'.join(second)+'\n\n以上两表只在24fps条件成立；其他时基需要重查。')
        c=load_corpus(self.config)
        ranked=candidates(c,'棱镜 参数',limit=1)
        row=ranked[0]['block']
        self.assertTrue(any('以上两表只在24fps' in full_evidence(c,i)['excerpt'] for i in row['context_ids']))
        r=make_review(c,'选择装置',['棱镜 参数'])
        self.assertTrue(any('以上两表只在24fps' in full_evidence(c,i)['excerpt'] for i in r['facets'][0]['context_ids']))

    def test_nested_existing_file_is_not_read_as_knowledge(self):
        p=self.library/'private/deep/日常记录.md'
        p.parent.mkdir(parents=True)
        p.write_text(topic('日常记录','## 私人正文\n独有字符串M7X秘密材料',kind='个人思考'),encoding='utf-8')
        self.write('## 来源\n[[日常记录]]')
        c=load_corpus(self.config)
        key=p.relative_to(self.vault).as_posix()
        self.assertIn(key,c['file_catalog'])
        self.assertNotIn(key,c['documents'])
        self.assertEqual(resolve_link('日常记录',self.path,c['documents'],self.vault,c['file_catalog'])[1],'exists_outside_index')
        self.assertEqual(resolve_link(key,self.path,c['documents'],self.vault,c['file_catalog'])[1],'exists_outside_index')
        self.assertEqual(candidates(c,'M7X秘密材料'),[])
        self.assertEqual(resolve_link('不存在',self.path,c['documents'],self.vault,c['file_catalog'])[1],'missing')

    def test_catalog_ambiguity_and_outside_path(self):
        self.write('## 方法\n普通内容')
        for folder in ('a','b'):
            p=self.library/folder/'重复.md';p.parent.mkdir();p.write_text('# local',encoding='utf-8')
        c=load_corpus(self.config)
        self.assertEqual(resolve_link('重复',self.path,c['documents'],self.vault,c['file_catalog'])[1],'ambiguous')
        self.assertEqual(resolve_link('C:/elsewhere/重复',self.path,c['documents'],self.vault,c['file_catalog'])[1],'outside')

    def test_identity_and_constraints_do_not_create_or_change_matches(self):
        self.write('## 方法\n服装连续性检查颜色、磨损和变化。')
        c=load_corpus(self.config)
        plain=make_review(c,'检查',['服装连续性'])
        tagged=make_review(c,'检查',['服装连续性'],task_type='字幕',object_name='V99',constraints='天体超算',expected_output='声音')
        self.assertEqual(plain['facets'],tagged['facets'])
        self.assertEqual(tagged['context']['object'],'V99')
        gap=make_review(c,'检查',['星系坐标超算'],constraints='服装连续性',expected_output='服装')
        self.assertEqual(gap['facets'][0]['status'],'gap')

    def test_pagination_preserves_exact_section_and_final_boundary(self):
        body='甲乙丙丁。'*1500+'\n仅在设备模式明确时适用。'
        self.write('## 长方法\n'+body+'\n\n## 其他\n不应混入')
        pieces=[];offset=0;snapshot=None;doc_hash=None
        while True:
            r=read_section(self.config_path,self.path,'长方法',1000,offset,snapshot,doc_hash)
            pieces.append(r['content'])
            self.assertEqual(r['returned_characters'],len(r['content']))
            if not r['truncated']:
                self.assertFalse(r['read_required']);break
            self.assertTrue(r['read_required'])
            continuation=r['continuation']
            offset=continuation['offset'];snapshot=continuation['snapshot'];doc_hash=continuation['document_hash']
        exact=extract_heading(self.path.read_bytes().decode('utf-8'),'长方法')[1]
        self.assertEqual(''.join(pieces),exact)
        self.assertIn('设备模式明确',pieces[-1])

    def test_continuation_refuses_changed_document(self):
        self.write('## 长方法\n'+'甲乙'*3000)
        first=read_section(self.config_path,self.path,'长方法',100)
        self.path.write_text(self.path.read_text(encoding='utf-8')+'\n新条件',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'变化'):
            read_section(self.config_path,self.path,'长方法',100,100,first['snapshot'],first['document_hash'])

    def test_unbound_continuation_is_rejected(self):
        self.write('## 方法\n'+'初始条件。'*100)
        with self.assertRaisesRegex(ValueError,'continuation'):
            read_section(self.config_path,self.path,'方法',100,100)

    def test_h4_and_duplicate_heading_resolution(self):
        self.assertEqual(extract_heading('## A\n#### 深层\n必要条件\n## B\n其他','深层'),(4,'必要条件'))
        with self.assertRaisesRegex(ValueError,'不唯一'):
            extract_heading('## A\n### 方法\n甲\n## B\n### 方法\n乙','方法')

    def test_reading_path_has_no_write_side_effects(self):
        self.write('## 方法\n服装状态对应同一人物。')
        code='''import sys,os\nfrom read_knowledge_section import read_section\ndef audit(event,args):\n if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or (isinstance(args[2],int) and args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))):\n  raise RuntimeError('write blocked')\n if event in ('os.remove','os.rename','os.mkdir','os.rmdir'):\n  raise RuntimeError('mutation blocked')\nsys.addaudithook(audit)\nr=read_section(sys.argv[1],sys.argv[2],'方法')\nassert not r['truncated']\nprint('read-only-ok')\n'''
        p=subprocess.run([sys.executable,'-B','-X','utf8','-c',code,str(self.config_path),str(self.path)],
                         cwd=Path(__file__).parent,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('read-only-ok',p.stdout)


if __name__=='__main__': unittest.main()
