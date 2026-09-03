#!/usr/bin/env python3
"""META-023/024: pack-view layered prose + overlay-apply."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent


def _repo_root() -> Path:
    from ndf_paths import detect_repo_root

    return detect_repo_root(TOOLS)


ROOT = _repo_root()
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "pack-view-consumer"
CONSUMER_ROOT = FIXTURE_ROOT if FIXTURE_ROOT.is_dir() else ROOT


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ctx = _load("ndf_context")


def _main_before_appendix(md: str) -> str:
    idx = md.find("## 附录")
    return md if idx < 0 else md[:idx]


class Meta024PackViewTests(unittest.TestCase):
    def test_apply_overlay_to_seeds(self):
        seeds = ctx.apply_overlay_to_seeds(
            ["META-012", "META-011", "BEH-025"],
            {
                "remove_seeds": ["BEH-025"],
                "add_seeds": ["META-023"],
                "temp_depends_on": {"META-023": ["META-001"]},
                "exclude_nodes": ["META-011"],
            },
        )
        self.assertIn("META-012", seeds)
        self.assertIn("META-023", seeds)
        self.assertIn("META-001", seeds)
        self.assertNotIn("BEH-025", seeds)
        self.assertNotIn("META-011", seeds)

    def test_process_pack_view_is_layered_prose(self):
        plan, md = ctx.build_pack_view(
            root=CONSUMER_ROOT,
            topic=None,
            role="project-control",
            task="process_land",
            track="process",
            seed_ids=["META-024"],
            hop="process_land",
        )
        self.assertEqual(plan["schema"], "ndf-context-plan/v1")
        self.assertIn("ndf-pack-view/v2", md)
        self.assertIn("## 前言", md)
        main = _main_before_appendix(md)
        self.assertIn("META-024", main)
        self.assertIn("分层", main)
        self.assertNotIn("## Graph closure", main)
        self.assertIn("### Graph closure", md)
        # Product clause bodies must not enter process main text.
        self.assertNotIn("{#ARCH-FFT-008}", main)
        self.assertNotIn("{#CHR-FFT-001}", main)
        self.assertIn("> 源：", main)
        self.assertIn("spec/meta/process.md", main)

    def test_product_topic_has_architecture_and_binder(self):
        _, md = ctx.build_pack_view(
            root=CONSUMER_ROOT,
            topic="jit-n1024-xbyak",
            role="claude-code",
            task="implement",
            track="promote",
            seed_ids=["ARCH-FFT-008", "ARCH-FFT-009"],
            hop="promote_land",
            depth=2,
            overlay={
                "promote": {
                    "draft_to_stable": ["ARCH-FFT-008", "ARCH-FFT-009"],
                    "trunk_write_roots": ["src/", "include/", "tests/"],
                    "promotes": "jit-n1024-xbyak",
                }
            },
        )
        main = _main_before_appendix(md)
        self.assertIn("## Architecture", main)
        self.assertIn("{#ARCH-FFT-008}", main)
        self.assertIn("本主题装订", main)
        self.assertIn("### TOPIC", main)
        self.assertNotIn("## Graph closure", main)
        self.assertIn("### Graph closure", md)
        self.assertIn("Promotes：`jit-n1024-xbyak`", main)
        # Process META bodies should not flood product main.
        self.assertNotIn("{#META-012}", main)
        self.assertIn("> 源：", main)
        self.assertIn("spec/10-architecture/architecture.md", main)
        self.assertIn("种子", main)
        self.assertIn("poc/jit-n1024-xbyak/ndf/TOPIC.md", main)
        self.assertIn("切片 `topic_contract`", main)

    def test_overlay_exclude_changes_prose(self):
        _, base = ctx.build_pack_view(
            root=CONSUMER_ROOT,
            topic=None,
            role="project-control",
            task="process_land",
            track="process",
            seed_ids=["META-024", "META-012"],
        )
        _, md = ctx.build_pack_view(
            root=CONSUMER_ROOT,
            topic=None,
            role="project-control",
            task="process_land",
            track="process",
            seed_ids=["META-024", "META-012"],
            overlay={"exclude_nodes": ["META-012"]},
        )
        main = _main_before_appendix(md)
        self.assertIn("{#META-024}", main)
        self.assertNotIn("{#META-012}", main)
        self.assertIn("### Overlay (not SoT)", md)
        self.assertIn("{#META-012}", _main_before_appendix(base))

    def test_cli_pack_view_writes_tmp(self):
        report = ROOT / "tmp" / "ndf-pack-view-meta024-test.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        if report.is_file():
            report.unlink()
        rc = ctx.main(
            [
                "--root",
                str(ROOT),
                "pack-view",
                "--role",
                "project-control",
                "--task",
                "process_land",
                "--track",
                "process",
                "--seed-ids",
                "META-024",
                "--hop",
                "process_land",
                "--report",
                "tmp/ndf-pack-view-meta024-test.md",
            ]
        )
        self.assertEqual(rc, 0)
        text = report.read_text(encoding="utf-8")
        self.assertIn("ndf-pack-view/v2", text)
        self.assertIn("## 前言", text)

    def test_cli_overlay_apply(self):
        overlay_path = ROOT / "tmp" / "ndf-overlay-meta024-test.json"
        overlay_path.parent.mkdir(parents=True, exist_ok=True)
        overlay_path.write_text(
            json.dumps(
                {
                    "add_seeds": ["META-001"],
                    "exclude_nodes": ["META-008"],
                    "temp_depends_on": {"META-024": ["META-012"]},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        report = ROOT / "tmp" / "ndf-pack-view-overlay-meta024-test.md"
        rc = ctx.main(
            [
                "--root",
                str(ROOT),
                "overlay-apply",
                "--overlay",
                "tmp/ndf-overlay-meta024-test.json",
                "--role",
                "project-control",
                "--task",
                "process_land",
                "--track",
                "process",
                "--seed-ids",
                "META-024",
                "--report",
                "tmp/ndf-pack-view-overlay-meta024-test.md",
            ]
        )
        self.assertEqual(rc, 0)
        text = report.read_text(encoding="utf-8")
        self.assertIn("Temporary depends-on", text)
        self.assertIn("ndf-pack-view/v2", text)

    def test_why_in_pack_seed_and_edge(self):
        seeds = ["ARCH-FFT-008"]
        sources = {"explicit": ["ARCH-FFT-008"]}
        nodes = [
            {
                "id": "ARCH-FFT-008",
                "edges": {"depends-on": ["ARCH-FFT-007"]},
            },
            {"id": "ARCH-FFT-007", "edges": {}},
        ]
        self.assertEqual(
            ctx.why_in_pack(
                "ARCH-FFT-008",
                seeds=seeds,
                seed_sources=ctx.invert_seed_sources(sources),
                nodes=nodes,
            ),
            "种子（点名）",
        )
        self.assertEqual(
            ctx.why_in_pack(
                "ARCH-FFT-007",
                seeds=seeds,
                seed_sources=ctx.invert_seed_sources(sources),
                nodes=nodes,
            ),
            "因 `ARCH-FFT-008` 的 depends-on",
        )

    def test_strip_ndf_comments(self):
        raw = "## Title {#X-1}\n<!-- ndf: kind=req -->\n\nBody MUST work.\n"
        out = ctx.strip_ndf_html_comments(raw)
        self.assertNotIn("<!-- ndf:", out)
        self.assertIn("Body MUST work.", out)
        self.assertIn("{#X-1}", out)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
