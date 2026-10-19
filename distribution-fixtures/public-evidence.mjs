import assert from "node:assert/strict";
import { readFile,writeFile,appendFile,mkdtemp,mkdir } from "node:fs/promises";
import { join,resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";
const env=process.env, automation=resolve("automation");
const {distribute}=await import(pathToFileURL(join(automation,"src/distribution/action.ts")));
const {GhClient}=await import(pathToFileURL(join(automation,"src/distribution/gh.ts")));
const report=JSON.parse(await readFile(env.DISTRIBUTION_REPORT,"utf8"));
const tag=env.FIXTURE_TAG;
const sourceEnv={...env,GITHUB_OUTPUT:"",INPUT_FILES:"bootstrap.sh\ndiagnose.ps1\nbootstrap.mjs",INPUT_TAG:tag,INPUT_TOKEN:env.GH_TOKEN,INPUT_COMMIT:env.GITHUB_SHA};
assert.equal(execFileSync("git",["-C",automation,"rev-parse","HEAD"],{encoding:"utf8"}).trim(),env.AUTOMATION_SHA);
assert.deepEqual(await readFile(join(env.DISTRIBUTION_PATH,"bootstrap.sh")),execFileSync("git",["-C",automation,"show",`${env.AUTOMATION_SHA}:test/distribution-fixtures/authored/bootstrap.sh`]));
const rerun=await distribute(sourceEnv);assert.equal(rerun.digest,report.digest);
const bad=new GhClient(env.GH_TOKEN,join(env.RUNNER_TEMP,"tamper-gh-cache"));const download=bad.download.bind(bad);
bad.download=async(endpoint,path,maximum)=>{await download(endpoint,path,maximum);await appendFile(path,"tampered");};
await assert.rejects(distribute(sourceEnv,bad),/digest/);
await distribute({...sourceEnv,INPUT_TAG:"v1.7.12",INPUT_REPOSITORY:"rhysd/actionlint",INPUT_FILES:"actionlint_1.7.12_checksums.txt",INPUT_COMMIT:""});
const home=await mkdtemp(join(env.RUNNER_TEMP,"distribution-native-")),scriptEnv={...env,FIXTURE_HOME:home};
assert.match(execFileSync("bash",[join(env.DISTRIBUTION_PATH,"bootstrap.sh"),"2.3.4"],{env:scriptEnv,encoding:"utf8"}),/installed:2.3.4/);
assert.equal(execFileSync(process.execPath,[join(env.DISTRIBUTION_PATH,"bootstrap.mjs"),"2.3.4"],{env:scriptEnv,encoding:"utf8"}).trim(),"generated:2.3.4");
if(process.platform==="win32"){
 execFileSync("pwsh",["-NoProfile","-File",join(env.DISTRIBUTION_PATH,"diagnose.ps1"),"-Expected","2.3.4"],{env:scriptEnv});
 execFileSync("pwsh",["-NoProfile","-File",join(env.DISTRIBUTION_PATH,"diagnose.ps1"),"-Uninstall"],{env:scriptEnv});
}
const receipt={schema:1,kind:"core",candidate:env.AUTOMATION_SHA,sourceCommit:env.GITHUB_SHA,runId:env.GITHUB_RUN_ID,attempt:env.GITHUB_RUN_ATTEMPT,platform:env.RUNNER_OS,cases:["public-release","cross-repo-read","negative-tamper","rerun","native-script"],report};
await mkdir("distribution-evidence",{recursive:true});await writeFile("distribution-evidence/receipt.json",JSON.stringify(receipt,null,2));
