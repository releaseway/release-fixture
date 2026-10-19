import copy
import hashlib
import json
from pathlib import Path
import runpy
import unittest

ROOT=Path(__file__).resolve().parents[1]
api=runpy.run_path(str(ROOT/'scripts/verify-distribution-candidate.py'))
CANDIDATE='a'*40
SOURCE='b'*40
RUN='20'
ATTEMPT='1'
def report(kind='github-release', artifact=False):
    names=['.nojekyll','.well-known/fixture.json'] if artifact else ['bootstrap.sh','diagnose.ps1','bootstrap.mjs']
    files=[dict(path=n,size=2,sha256=hashlib.sha256(b'ok').hexdigest(),origin='selected',**({'from':n} if not artifact else {})) for n in names]
    entries=sorted([[f['path'],f['size'],f['sha256']]for f in files],key=lambda e:e[0].encode())
    digest='sha256:'+hashlib.sha256(json.dumps(entries,separators=(',',':')).encode()).hexdigest()
    src=dict(kind='github-release',repository='releaseway/release-fixture',commit=SOURCE,releaseId=4,tag='distribution-20-1',assets=[dict(id=i+1,name=f['path'],size=2,digest='sha256:'+f['sha256'])for i,f in enumerate(files)])
    if kind=='workflow-artifact':src=dict(kind=kind,artifactId='9',runId=RUN,callerSha=SOURCE,artifactDigest='sha256:'+'c'*64)
    return dict(schema=1,files=files,digest=digest,source=src,latestId='4')
def receipts():
    result=[dict(schema=1,kind='core',candidate=CANDIDATE,sourceCommit=SOURCE,runId=RUN,attempt=ATTEMPT,platform=p,cases=['public-release','cross-repo-read','negative-tamper','rerun','native-script'],report=report())for p in ['Linux','macOS','Windows']]
    for i,mode in enumerate(['latest','release','artifact']):
        r=report('workflow-artifact' if mode=='artifact' else 'github-release',artifact=True)
        result.append(dict(schema=1,kind='pages',mode=mode,candidate=CANDIDATE,sourceCommit=SOURCE,runId=RUN,attempt=ATTEMPT,report=r,served=True,deploymentId=str(100+i),reportArtifactId=str(200+i),pageUrl='https://releaseway.github.io/release-fixture/',deliveryDigest=r['digest'],sourceArtifactId='9'if mode=='artifact' else '',negative404=(mode=='artifact'),negativeDigest=(mode=='artifact')))
    return result
class DistributionTests(unittest.TestCase):
    def verify(self,items,**kw):return api['verify_receipts'](CANDIDATE,SOURCE,RUN,ATTEMPT,items,**kw)
    def test_exact_workflow_pins(self):
        text=(ROOT/'.github/workflows/distribution-acceptance.yml').read_text();candidate=text.split('AUTOMATION_SHA: ')[1].splitlines()[0]
        api['verify_pin'](candidate,text)
        for bad in ['main','d'*40]:
            with self.assertRaises(ValueError):api['verify_pin'](bad,text)
        with self.assertRaises(ValueError):api['verify_pin'](candidate,text.replace('@'+candidate,'@'+'f'*40,1))
    def test_complete_current_receipts_only(self):
        self.verify(receipts())
        for key,value in [('candidate','d'*40),('sourceCommit','d'*40),('runId','19'),('attempt','2')]:
            bad=receipts();bad[0][key]=value
            with self.assertRaises(ValueError):self.verify(bad)
        with self.assertRaises(ValueError):self.verify(receipts()[:-1])
        self.verify(receipts()[:3],require_pages=False)
        with self.assertRaises(ValueError):self.verify(receipts()[:3])
    def test_missing_cases_damaged_digest_or_artifact_identity(self):
        for mutate in [lambda r:r[0]['cases'].pop(),lambda r:r[0]['report'].__setitem__('digest','sha256:'+'0'*64),lambda r:r[-1]['report']['source'].__setitem__('artifactId','8'),lambda r:r[-1].__setitem__('served',False),lambda r:r[0]['report']['source'].__setitem__('tag','distribution-19-1'),lambda r:r[0]['report']['source']['assets'][0].__setitem__('digest','sha256:'+'0'*64)]:
            bad=receipts();mutate(bad)
            with self.assertRaises(ValueError):self.verify(bad)
    def test_no_pages_default_and_isolated_target_preflight(self):
        text=(ROOT/'.github/workflows/distribution-acceptance.yml').read_text()
        self.assertIn('default: false',text)
        self.assertIn('test "$GITHUB_REPOSITORY" = releaseway/release-fixture',text)
        self.assertIn('--prerelease --latest=false',text)
        self.assertIn('distribution-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT',text)
        self.assertNotIn('gh api --method POST',text)
if __name__=='__main__':unittest.main()
