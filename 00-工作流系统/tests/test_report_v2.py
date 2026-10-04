import sys
from pathlib import Path
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bin"))
import check_job_reports


def fixture(*, v2: bool = True, shareholder_label: str = "直接股东") -> str:
    meta = '<meta name="jobflow-report-version" content="2">' if v2 else ""
    labels = [
        "招聘主体",
        "合同主体",
        shareholder_label,
        "持股比例",
        "控制链",
        "最终母公司",
        "证据断点",
        "硬线状态",
        "证据覆盖率",
        "配置版本",
    ]
    evidence = "".join(f"<p>{label}</p>" for label in labels)
    return f"""<!doctype html><html><head>{meta}<style>:root{{--bg:#111111}}</style></head><body>
<div class="jhead"><div class="tags"><span>未核实</span></div><a class="jdlink" href="https://example.invalid/job/demo">JD</a><p>工作地址：未能核实</p></div>
<h2><span class="num">01</span>业务与产品</h2>
<h2><span class="num">02</span>JD 要点</h2>
<h2><span class="num">03</span>薪资</h2>
<h2><span class="num">04</span>公司背景</h2>
<h2><span class="num">05</span>WLB</h2>
<h2><span class="num">06</span>匹配面</h2>
<h2><span class="num">07</span>投递建议</h2>
<table class="ownership-evidence">{evidence}</table>
</body></html>"""


class V2ReportTests(unittest.TestCase):
    def test_v2_missing_equity_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft-20260922-example.html"
            path.write_text(fixture(shareholder_label="融资方名单"), encoding="utf-8")
            self.assertTrue(any("直接股东" in problem for problem in check_job_reports.problems(path)))

    def test_legacy_report_does_not_claim_v2_completeness(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "draft-20260922-example.html"
            path.write_text(fixture(v2=False, shareholder_label="融资方名单"), encoding="utf-8")
            self.assertFalse(any("v2报告" in problem for problem in check_job_reports.problems(path)))


if __name__ == "__main__":
    unittest.main()
