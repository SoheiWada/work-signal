import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class PagesRecoveryTests(unittest.TestCase):
    def test_recovery_matrix(self):
        workflow = (ROOT / '.github/workflows/pages-recovery.yml').read_text()
        script = '\n'.join(line[10:] for line in workflow.split('        run: |\n', 1)[1].splitlines())
        for current, latest, state, jobs, expected in [
            ('abc','1','completed:failure:1','timed_out\\nskipped',True),
            ('abc','1','completed:timed_out:1','success\\ntimed_out',True),
            ('abc','1','completed:failure:1','failure\\nskipped',False),
            ('abc','1','completed:failure:1','timed_out\\nfailure',False),
            ('abc','1','completed:timed_out:2','timed_out',False),
            ('new','1','completed:timed_out:1','timed_out',False),
            ('abc','2','completed:timed_out:1','timed_out',False),
        ]:
            with self.subTest(current=current,latest=latest,state=state,jobs=jobs), tempfile.TemporaryDirectory() as tmp:
                p=pathlib.Path(tmp)
                gh=p/'gh'
                gh.write_text("""#!/bin/bash
case "$*" in
  *git/ref/heads/main*) echo "$MOCK_CURRENT";;
  *workflows/pages.yml/runs*) echo "$MOCK_LATEST";;
  *attempts/1/jobs*) printf '%b\\n' "$MOCK_JOBS";;
  *--method*POST*) touch "$MOCK_POST";;
  *actions/runs/1*) echo "$MOCK_STATE";;
  *) exit 99;;
esac
""")
                gh.chmod(0o755)
                env=dict(os.environ,PATH=tmp+':'+os.environ['PATH'],REPO='test/repo',RUN_ID='1',HEAD_SHA='abc',GITHUB_STEP_SUMMARY=str(p/'summary'),MOCK_CURRENT=current,MOCK_LATEST=latest,MOCK_STATE=state,MOCK_JOBS=jobs,MOCK_POST=str(p/'post'))
                subprocess.run(['bash','-c',script],env=env,check=True)
                self.assertEqual((p/'post').exists(),expected)
