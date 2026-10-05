"""Target evidence must not be replaced by a questioned reference domain."""
from pathlib import Path
import tempfile
import unittest

from knowledge_evidence import candidates, load_corpus, make_review
from retrieve_knowledge import object_foci, query_roles, retrieve_scoped


class QueryRoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / 'vault'
        self.library = self.vault / 'library'
        self.creation = self.library / 'creation/岗位共用'
        self.learning = self.library / 'learning'
        self.cache = self.root / 'cache'
        for folder in (self.creation, self.learning, self.cache):
            folder.mkdir(parents=True)
        self.config = {'vault': str(self.vault), 'knowledge_library': str(self.library),
                       'creation_root': str(self.library / 'creation'), 'learning_root': str(self.learning),
                       'source_notes': str(self.learning), 'raw_cache': str(self.cache)}

    def write(self, title, body, *, source=False, problem=''):
        path = self.creation / (title + ('-来源' if source else '') + '.md')
        path.write_text(f'---\n类型: {"来源笔记" if source else "主题笔记"}\n分类: 声音与后期\n'
                        f'解决问题: {problem}\n---\n# {title}\n{body}\n', encoding='utf-8')
        return path

    def quick(self, question):
        return retrieve_scoped(self.config, question, role='E', no_cache=True)

    def write_color(self, *, source=False):
        return self.write('曝光与肤色调色', '## 知识单元\n### 曝光匹配方法\n'
                          '先核对曝光和白平衡，再比较肤色与调色管线，保留混合光意图。',
                          source=source, problem='曝光与肤色调色怎样判断')

    def test_borrowed_reference_is_not_primary_target_evidence(self):
        self.write_color()
        self.write_color(source=True)
        self.write('现场声音', '## 知识单元\n### 声音记录方法\n'
                   '先比较声音曝光记录，再核对底噪与空间。')
        question = '平台曝光少，是否能按调色曝光做传播原因依据？'
        result = self.quick(question)
        self.assertEqual(result['query'], question)
        self.assertEqual(result['query_roles']['mode'], 'borrowed_reference')
        self.assertEqual(result['query_roles']['target_foci'], ['release'])
        self.assertIn('color', result['query_roles']['comparison_foci'])
        self.assertTrue(result['gap'])
        self.assertTrue(result['method_gap'])
        self.assertEqual(result['source_candidates'], [])
        review = make_review(load_corpus(self.config, scope=result['scope']), question, [])
        self.assertEqual(review['facets'][0]['status'], 'gap')
        self.assertEqual(review['facets'][0]['evidence_ids'], [])

    def test_reference_only_subquestion_keeps_original_target(self):
        self.write_color()
        self.write('后期受控变更传播', '## 锁画后修改必须显式传播\n'
                   '记录调色变化及调色依据，修改需要传播到后期分支，重新核对素材。', source=True)
        query = '平台曝光少，是否能按调色曝光做传播原因依据？'
        review = make_review(load_corpus(self.config), query, ['调色曝光能否作为判断依据？'])
        facet = review['facets'][0]
        self.assertEqual(facet['query_roles']['mode'], 'reference_within_target_task')
        self.assertEqual(facet['query_roles']['target_foci'], ['release'])
        self.assertEqual(facet['status'], 'gap')
        self.assertEqual(facet['question'], '调色曝光能否作为判断依据？')
        self.assertIn('平台曝光', facet['query_roles']['target_text'])

    def test_labeled_reference_prefix_does_not_become_a_target(self):
        self.write_color()
        plain = '播放量降低，能用调色匹配来解释平台曝光量吗？'
        prefixed = '参考知识：调色匹配。实际问题：' + plain
        for question in (plain, prefixed):
            with self.subTest(question=question):
                result = self.quick(question)
                self.assertEqual(result['query'], question)
                self.assertEqual(result['query_roles']['mode'], 'borrowed_reference')
                self.assertEqual(result['query_roles']['target_foci'], ['release'])
                self.assertTrue(result['gap'])
                self.assertTrue(result['method_gap'])
                self.assertEqual(result['source_candidates'], [])

    def test_labeled_target_can_still_request_a_real_two_domain_comparison(self):
        question = '参考方法：调色曝光。当前问题：比较平台曝光和镜头曝光各自的含义。'
        roles = query_roles(question)
        self.assertEqual(roles['mode'], 'multiple_targets')
        self.assertEqual(set(roles['target_foci']), {'release', 'color'})
        self.assertEqual(roles['target_text'], '比较平台曝光和镜头曝光各自的含义。')

    def test_subject_first_capability_is_reference_not_target(self):
        self.write_color()
        for question in ('调色曝光方法能否解释平台曝光少？', '混音方法是否代表服装连续性？',
                         '配乐方法能不能解决字幕错字？'):
            with self.subTest(question=question):
                roles = query_roles(question)
                self.assertEqual(roles['mode'], 'borrowed_reference')
                self.assertTrue(roles['explicit_target'])
                self.assertFalse(set(roles['comparison_foci']) & set(roles['target_foci']))
        result = self.quick('调色曝光方法能否解释平台曝光少？')
        self.assertTrue(result['gap'])
        self.assertTrue(result['method_gap'])

    def test_explicit_unclassified_target_never_inherits_reference_domain(self):
        self.write_color()
        self.write('行动失败与策略', '## 知识单元\n### 行动检查方法\n'
                   '先对照行动与失败结果，再检查下一次策略是否改变。', problem='行动失败怎样改变策略')
        for anchor in ('我实际要检查', '我只想检查', '需要检查'):
            question = '借调色曝光打个比方：' + anchor + '行动、失败和策略之间的变化。'
            with self.subTest(anchor=anchor):
                result = self.quick(question)
                self.assertEqual(result['query_roles']['mode'], 'borrowed_reference')
                self.assertTrue(result['query_roles']['explicit_target'])
                self.assertEqual(result['query_roles']['target_foci'], [])
                self.assertNotIn('调色', result['query_roles']['target_text'])
                self.assertFalse(result['gap'])
                self.assertEqual(result['candidates'][0]['title'], '行动失败与策略')
                review = make_review(load_corpus(self.config, scope=result['scope']), question,
                                     ['行动失败以后怎样改变策略？'])
                by_id = {item['id']: item for item in review['evidence']}
                self.assertEqual({by_id[key]['heading'] for key in review['facets'][0]['evidence_ids']}, {'行动检查方法'})

    def test_borrowed_syntax_is_general_across_professional_objects(self):
        examples = [
            ('服装状态反复变化，能否用混音方法来判断服装连续性？', 'assets', 'sound'),
            ('肤色偏绿，是否可以按平台曝光量来判断白平衡？', 'color', 'release'),
            ('字幕错字很多，能否借用配乐方法作为字幕检查依据？', 'text', 'music'),
            ('平台曝光量低，能不能拿相机曝光量来推断传播原因？', 'release', 'color'),
        ]
        for question, target, reference in examples:
            with self.subTest(question=question):
                roles = query_roles(question)
                self.assertEqual(roles['mode'], 'borrowed_reference')
                self.assertIn(target, roles['target_foci'])
                self.assertNotIn(reference, roles['target_foci'])
                self.assertIn(reference, roles['comparison_foci'])

    def test_explicit_two_domain_comparison_stays_readable(self):
        self.write('平台曝光含义', '## 知识单元\n### 概念\n平台曝光表示传播触达次数，不能代替播放量或受众反馈。')
        self.write('镜头曝光含义', '## 知识单元\n### 概念\n镜头曝光涉及光线与调色记录，不能代替肤色或白平衡判断。')
        question = '比较平台曝光和镜头曝光各自的含义与适用条件。'
        roles = query_roles(question)
        self.assertEqual(roles['mode'], 'multiple_targets')
        self.assertEqual(set(roles['target_foci']), {'release', 'color'})
        rows = candidates(load_corpus(self.config), question)
        titles = {load_corpus(self.config)['documents'][row['key']]['title'] for row in rows}
        self.assertEqual(titles, {'平台曝光含义', '镜头曝光含义'})

    def test_explicit_neutral_decision_review_is_not_lost(self):
        self.write_color()
        self.write('创作决策复盘', '## 知识单元\n### 事实与解释方法\n'
                   '先列事实和真实结果，再区分解释假设与反证；一次结果不能证明整套方法有效。',
                   problem='怎样区分事实、解释假设与反证')
        question = '一次短片播放量低，怎样区分作品、包装与发布条件的影响，避免凭一次结果改整套方法？'
        result = self.quick(question)
        self.assertFalse(result['gap'])
        self.assertFalse(result['method_gap'])
        self.assertEqual(result['candidates'][0]['title'], '创作决策复盘')
        review = make_review(load_corpus(self.config, scope=result['scope']), question,
                             ['创作决策怎样根据事前依据、真实结果与反证复盘？'])
        by_id = {item['id']: item for item in review['evidence']}
        self.assertTrue(review['facets'][0]['evidence_ids'])
        self.assertEqual({by_id[key]['heading'] for key in review['facets'][0]['evidence_ids']}, {'事实与解释方法'})

    def test_color_target_still_gets_color_method_when_release_is_reference(self):
        self.write_color()
        question = '同一场戏肤色偏绿，是否可以按平台曝光量来判断白平衡？'
        result = self.quick(question)
        self.assertFalse(result['gap'])
        self.assertEqual(result['query_roles']['target_foci'], ['color'])
        self.assertEqual(result['candidates'][0]['method_chunks'][0]['heading'], '曝光匹配方法')

    def test_metric_exposure_without_borrowed_method_is_not_color(self):
        self.assertEqual(object_foci('平台曝光少，怎样判断传播原因？'), ('release',))
        self.assertIn('color', object_foci('肤色曝光和白平衡怎样匹配？'))
        self.assertEqual(object_foci('镜头曝光量怎样判断？'), ('color',))
        self.assertNotIn('release', object_foci('锁画变更怎样向调色分支传播？'))

    def test_plain_trailing_request_keeps_the_concrete_problem(self):
        self.write('折返方向连续性', '## 知识单元\n### 折返检查方法\n'
                   '对照折返前后的画面方向、动作接口和轴线，再比较具体线索。',
                   problem='折返后画面方向怎样检查')
        question = '角色折返后画面方向变了，需要比较哪些具体线索？'
        roles = query_roles(question)
        self.assertEqual(roles['target_text'], question)
        self.assertIn('camera_space', roles['target_foci'])
        self.assertEqual(roles['comparison_foci'], [])
        result = self.quick(question)
        self.assertFalse(result['gap'])
        self.assertEqual(result['candidates'][0]['method_chunks'][0]['heading'], '折返检查方法')


if __name__ == '__main__':
    unittest.main()
