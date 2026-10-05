"""Directory routing checks only; no answer-quality evaluation or live Vault writes."""
from __future__ import annotations
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from knowledge_scope import make_scope, restore_scope, scope_roots, ROLE_DIRS
from knowledge_evidence import load_corpus, full_evidence
from knowledge_followup import followup, snapshot_state
from knowledge_review import review_scoped, main as review_main
from retrieve_knowledge import retrieve_scoped
from read_knowledge_section import read_section
from record_application import build_plan


def note(title, body, kind="材料总览", extra=""):
    return f"---\n类型: {kind}\n分类: 摄影美术与现场制作\n材料类型: 专业补充\n{extra}\n---\n# {title}\n\n## 方法与案例\n{body}\n"


class ZoneScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.library = self.vault / "知识库"
        self.creation = self.library / "创作区"
        self.learning = self.library / "学习区"
        self.cache = self.root / "cache"
        for p in [self.creation, self.learning, self.cache, self.vault/".obsidian"]:
            p.mkdir(parents=True, exist_ok=True)
        self.roles = {k: self.creation / v for k,v in ROLE_DIRS.items()}
        for p in [*self.roles.values(), self.creation/"岗位共用"]:
            p.mkdir()
        self.config = dict(vault=str(self.vault), knowledge_library=str(self.library), source_notes=str(self.learning),
                           raw_cache=str(self.cache), creation_root=str(self.creation), learning_root=str(self.learning))
        self.config_path = self.root / "config.json"
        self.config_path.write_text("{}", encoding="utf-8")
        self.c = self.write(self.roles["C"]/"服装资料.md", "服装状态链", "服装状态链通过同一服装的污损变化记录剧情时间。")
        self.d = self.write(self.roles["D"]/"声音资料.md", "Orbitalboundary", "Orbitalboundary is the unique test locator.")
        self.l = self.write(self.learning/"综合整理"/"服装主题.md", "服装状态链", "服装状态链是学习主题的详细说明。", "主题笔记")
        self.personal = self.write(self.learning/"个人.md", "个人想法", "私人想法不构成来源。", "个人思考")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, title, body, kind="材料总览", extra=""):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(note(title, body, kind, extra), encoding="utf-8")
        return path

    def assert_not_read(self, forbidden, run):
        original_bytes, original_text = Path.read_bytes, Path.read_text
        seen=[]
        def read_bytes(path, *a, **kw):
            if path.is_relative_to(self.vault): seen.append(path)
            if any(path == p or p.is_dir() and path.is_relative_to(p) for p in forbidden):
                raise AssertionError("unexpected body read: " + str(path))
            return original_bytes(path, *a, **kw)
        def read_text(path, *a, **kw):
            if path.is_relative_to(self.vault): seen.append(path)
            if any(path == p or p.is_dir() and path.is_relative_to(p) for p in forbidden):
                raise AssertionError("unexpected text read: " + str(path))
            return original_text(path, *a, **kw)
        with patch.object(Path, "read_bytes", read_bytes), patch.object(Path, "read_text", read_text):
            result=run()
        return result,seen

    def test_primary_role_and_shared_read_before_other_roles_or_learning(self):
        shared=self.write(self.creation/"岗位共用"/"共用.md", "服装状态链记录", "服装状态链记录说明。")
        out,seen=self.assert_not_read([self.learning,self.roles["D"]],
            lambda:retrieve_scoped(self.config,"服装状态链",role="C1",no_cache=True))
        self.assertFalse(out["scope"]["expanded"])
        self.assertEqual(out["scope"]["role"],"C")
        self.assertIn(shared,seen)
        self.assertEqual(out["source_candidates"][0]["kind"],"source")
        self.assertEqual(out["candidates"],[])
        self.assertFalse(out["gap"])

    def test_e_without_directory_uses_shared_before_creation_fallback(self):
        self.roles["E"].rmdir()  # Disposable empty fixture; no E folder is created in the actual candidate.
        shared=self.write(self.creation/"岗位共用"/"共用.md","SharedReleaseEvidence","SharedReleaseEvidence test source.")
        out,_=self.assert_not_read([self.learning,*self.roles.values()],lambda:retrieve_scoped(
            self.config,"SharedReleaseEvidence",role="E",no_cache=True))
        self.assertFalse(out["scope"]["expanded"])
        self.assertEqual(out["scope"]["paths"],[(self.creation/"岗位共用").relative_to(self.vault).as_posix()])
        out,_=self.assert_not_read([self.learning],lambda:retrieve_scoped(
            self.config,"Orbitalboundary",role="E",no_cache=True))
        self.assertTrue(out["scope"]["expanded"])
        self.assertEqual(out["source_candidates"][0]["path"],str(self.d))

    def test_fallback_expands_creation_only_after_primary_gap(self):
        out,_=self.assert_not_read([self.learning],lambda:retrieve_scoped(self.config,"Orbitalboundary",role="C2",no_cache=True))
        self.assertTrue(out["scope"]["expanded"])
        self.assertEqual(out["source_candidates"][0]["path"],str(self.d))

    def test_no_match_never_loads_learning(self):
        out,_=self.assert_not_read([self.learning],lambda:retrieve_scoped(self.config,"UnmatchableXYZ",role="B",no_cache=True))
        self.assertTrue(out["gap"])

    def test_explicit_file_include_reads_no_neighbor_or_other_learning(self):
        selected=self.write(self.learning/"课程"/"目标.md","PhotonRefraction","PhotonRefraction test source.")
        neighbor=self.write(selected.parent/"邻居.md","private","Do not read.")
        out,_=self.assert_not_read([neighbor,self.l,self.personal],lambda:retrieve_scoped(
            self.config,"PhotonRefraction",role="C",include_paths=[str(selected)],no_cache=True))
        self.assertEqual(out["source_candidates"][0]["path"],str(selected))
        again,_=self.assert_not_read([self.learning],lambda:retrieve_scoped(self.config,"PhotonRefraction",role="C",no_cache=True))
        self.assertTrue(again["gap"])

    def test_explicit_directory_and_corpus_type_filter(self):
        scope=make_scope(self.config,"C",[str(self.learning)])
        corpus=load_corpus(self.config,scope=scope)
        self.assertEqual(corpus["documents"][self.l.relative_to(self.vault).as_posix()]["kind"],"topic")
        self.assertNotIn(self.personal.relative_to(self.vault).as_posix(),corpus["documents"])

    def test_nested_paths_read_note_bytes_once(self):
        calls=[]; original=Path.read_bytes
        def read(path):
            if path==self.l:calls.append(path)
            return original(path)
        with patch.object(Path,"read_bytes",read):
            load_corpus(self.config,scope=make_scope(self.config,"C",[str(self.learning),str(self.l)]))
        self.assertEqual(calls,[self.l])

    def test_include_path_outside_zones_rejected(self):
        outside=self.write(self.vault/"outside.md","other","Other")
        for value in [outside,self.library,self.vault,self.root/"missing.md"]:
            with self.assertRaises((ValueError,OSError)):
                make_scope(self.config,"C",[str(value)])

    def test_scope_tampering_and_alias_restore(self):
        scope=make_scope(self.config,"C2")
        self.assertEqual(restore_scope(self.config,json.dumps(scope)),scope)
        tampered={**scope,"paths":[self.learning.relative_to(self.vault).as_posix()]}
        with self.assertRaises(ValueError):restore_scope(self.config,tampered)

    def test_out_of_scope_source_link_is_not_broken(self):
        target=self.l.relative_to(self.vault).with_suffix("").as_posix()
        self.c.write_text(note("服装状态链","服装状态链正文。","主题笔记",f'来源材料: ["[[{target}]]"]'),encoding="utf-8")
        corpus,_=self.assert_not_read([self.learning],lambda:load_corpus(self.config,scope=make_scope(self.config,"C")))
        d=corpus["documents"][self.c.relative_to(self.vault).as_posix()]
        self.assertEqual(d["broken_links"],[])
        self.assertEqual(d["scope_links"][0]["reason"],"outside_requested_scope")

    def test_review_primary_and_continuation_use_same_scope(self):
        review,corpus=self.assert_not_read([self.learning,self.roles["D"]],lambda:review_scoped(
            self.config,"服装状态链",role="C",no_cache=True))[0]
        self.assertFalse(review["scope"]["expanded"])
        eid=review["facets"][0]["evidence_ids"][0]
        buf=io.StringIO()
        args=["knowledge_review.py","--read-id",eid,"--snapshot",corpus["snapshot"],"--scope",json.dumps(review["scope"]),"--no-cache"]
        with patch("knowledge_review.load_config",return_value=self.config),patch("knowledge_review.resolve_config",return_value=self.config_path),patch("sys.argv",args),redirect_stdout(buf):
            self.assertEqual(review_main(),0)
        self.assertIn("服装状态链",json.loads(buf.getvalue())["evidence"]["excerpt"])
        bad=make_scope(self.config,"C",[str(self.l)])
        args[args.index("--scope")+1]=json.dumps(bad)
        with patch("knowledge_review.load_config",return_value=self.config),patch("knowledge_review.resolve_config",return_value=self.config_path),patch("sys.argv",args),redirect_stdout(io.StringIO()):
            self.assertEqual(review_main(),2)

    def test_topic_continuation_requires_scope_and_never_reads_unselected_learning(self):
        self.c.write_text(note("服装状态链","服装状态链。"*60,"主题笔记"),encoding="utf-8")
        with patch("read_knowledge_section.load_config",return_value=self.config),patch("read_knowledge_section.resolve_config",return_value=self.config_path):
            first,_=self.assert_not_read([self.learning],lambda:read_section(self.config_path,self.c,"方法与案例",20,role="C"))
            self.assertTrue(first["truncated"])
            cont=first["continuation"]
            more=read_section(cont["config"],cont["path"],cont["heading"],cont["max_chars"],cont["offset"],cont["snapshot"],cont["document_hash"],scope=cont["scope"])
            self.assertEqual(more["scope"],first["scope"])
            with self.assertRaises(ValueError):
                read_section(self.config_path,self.c,"方法与案例",20,20,first["snapshot"],first["document_hash"])

    def test_global_followup_still_inventories_both_zones(self):
        corpus=load_corpus(self.config)
        self.assertIn(self.l.relative_to(self.vault).as_posix(),corpus["documents"])
        followup(corpus)
        scoped=load_corpus(self.config,scope=make_scope(self.config,"C"))
        for func in [followup,snapshot_state]:
            with self.assertRaises(ValueError):func(scoped)

    def test_new_application_location_and_vault_relative_links(self):
        from test_record_application import topic_text
        self.c.write_text(topic_text("创作主题"),encoding="utf-8")
        kwargs=dict(config_path=self.config_path,project="测试",problem="连续性",stage="拍摄",topic_names=["创作主题"],method="核对",action="检查",result="",conditions="",status="待验证",observable=False,record_date="2026-09-22",record_key="")
        with patch("record_application.load_config",return_value=self.config):plan=build_plan(**kwargs)
        self.assertEqual(plan.application_path.parent,self.creation/"岗位共用"/"项目经验"/"项目应用")
        self.assertFalse(plan.application_path.exists())
        self.assertIn("[[知识库/创作区/C-导演与视觉/服装资料",plan.changes[plan.application_path])
        self.assertIn("[[知识库/创作区/岗位共用/项目经验/项目应用",plan.changes[self.c])

    def test_legacy_quick_keeps_topic_only_behavior(self):
        legacy={k:v for k,v in self.config.items() if k not in {"creation_root","learning_root"}}
        out=retrieve_scoped(legacy,"服装状态链",role="C",no_cache=True)
        self.assertNotIn("source_candidates",out)
        self.assertNotIn("scope",out)


if __name__ == "__main__":
    unittest.main()
