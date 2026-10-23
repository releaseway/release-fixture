import assert from "node:assert/strict";
import { appendFile,readFile,writeFile,mkdir } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve,join } from "node:path";
import { pathToFileURL } from "node:url";
import { build,supersedingInventory } from "./release-set-fixtures.mjs";

const env=process.env,automation=resolve("automation");
const {distribute}=await import(pathToFileURL(join(automation,"src/distribution/action.ts")));
const {GhClient}=await import(pathToFileURL(join(automation,"src/distribution/gh.ts")));
assert.equal(execFileSync("git",["-C",automation,"rev-parse","HEAD"],{encoding:"utf8"}).trim(),env.AUTOMATION_SHA);
assert.equal(process.platform,{Linux:"linux",macOS:"darwin",Windows:"win32"}[env.RUNNER_OS]);
const policy=await build("initial"),prefix=policy.releases["tag-prefix"];
const sourceEnv={...env,GITHUB_OUTPUT:"",INPUT_TOKEN:env.GH_TOKEN,INPUT_CONFIG:".github/distribution/release-set-initial.json",INPUT_SITE:"release-set-site-initial",INPUT_FILES:"",INPUT_TAG:"",INPUT_COMMIT:""};
const first=await distribute(sourceEnv),report=JSON.parse(await readFile(first.report,"utf8"));
const rerun=await distribute(sourceEnv);assert.equal(rerun.digest,first.digest);
const partial=".release-set-partial.json";
await writeFile(partial,JSON.stringify({...policy,releases:{tags:[prefix+"partial-v1.0.0"]},aliases:undefined}));
await assert.rejects(distribute({...sourceEnv,INPUT_CONFIG:partial}),/required|missing/i);
const tamper=new GhClient(env.GH_TOKEN,join(env.RUNNER_TEMP,"set-tamper")),download=tamper.download.bind(tamper);
tamper.download=async(...args)=>{await download(...args);await appendFile(args[1],"tampered");};
await assert.rejects(distribute(sourceEnv,tamper),/digest|size/i);
const changed=new GhClient(env.GH_TOKEN,join(env.RUNNER_TEMP,"set-change")),json=changed.json.bind(changed),get=changed.download.bind(changed);let downloaded=false;
changed.download=async(...args)=>{await get(...args);downloaded=true;};
changed.json=async(endpoint,projection)=>{
  const result=await json(endpoint,projection);
  if(downloaded&&endpoint.includes("/releases?")&&endpoint.endsWith("&page=1"))return supersedingInventory(result,prefix);
  return result;
};
await assert.rejects(distribute(sourceEnv,changed),/changed|superseded/i);
const marker="release-set:1.1.0";
const observed=execFileSync(process.platform==="win32"?"pwsh":"bash",process.platform==="win32"?["-NoProfile","-File",join(first.path,"install.ps1")]:[join(first.path,"install.sh")],{encoding:"utf8"}).trim();assert.equal(observed,marker);
const legacy=JSON.parse(await readFile(env.DISTRIBUTION_REPORT,"utf8"));assert.equal(legacy.schema,1);
const receipt={schema:1,kind:"release-set-core",candidate:env.AUTOMATION_SHA,sourceCommit:env.GITHUB_SHA,runId:env.GITHUB_RUN_ID,attempt:env.GITHUB_RUN_ATTEMPT,platform:env.RUNNER_OS,report,rerunDigest:rerun.digest,nativeMarker:observed,cases:["partial-rejected","digest-tamper-rejected","rerun-same-digest","schema1-regression","source-change-rejected"]};
await mkdir("release-set-evidence",{recursive:true});await writeFile("release-set-evidence/receipt.json",JSON.stringify(receipt,null,2)+"\n");

// Supplement the historical receipt without adding new mandatory cases to it.
// Exercise the committed bundle, not only the source imports used above.
await mkdir("release-set-contract",{recursive:true});
const exactFiles=[{from:"bootstrap.sh",to:"bootstrap.sh",required:true},
  {from:"diagnose.ps1",to:"diagnose.ps1",required:true},
  {from:"metadata.json",to:"metadata.json",required:false}];
const legacyPolicy={schema:2,releases:policy.releases,files:exactFiles,
  aliases:{tag:policy.aliases.tag,files:[{from:"bootstrap.sh",to:"bootstrap.sh"},{from:"diagnose.ps1",to:"diagnose.ps1"}]}};
const shorthandPolicy={releases:policy.releases,files:["bootstrap.sh",{from:"diagnose.ps1",to:"diagnose.ps1"},exactFiles[2]],
  aliases:{tag:policy.aliases.tag,files:["bootstrap.sh","diagnose.ps1"]}};
async function bundled(value,name) {
  const config=join("release-set-contract",name+".json"),output=resolve("release-set-contract",name+".outputs");
  await writeFile(config,JSON.stringify(value));await writeFile(output,"");
  execFileSync(process.execPath,[join(automation,"dist/distribute.cjs")],{env:{...sourceEnv,INPUT_CONFIG:config,GITHUB_OUTPUT:output},encoding:"utf8"});
  const outputs=Object.fromEntries((await readFile(output,"utf8")).trim().split(/\r?\n/).map(line=>{
    const equal=line.indexOf("=");return [line.slice(0,equal),line.slice(equal+1)];
  }));
  return JSON.parse(await readFile(outputs.report,"utf8"));
}
const legacyReport=await bundled(legacyPolicy,"legacy"),shorthandReport=await bundled(shorthandPolicy,"shorthand");
assert.deepEqual(shorthandReport,legacyReport);
const invalidConfig=join("release-set-contract","invalid.json"),invalidOutput=resolve("release-set-contract","invalid.outputs");
await writeFile(invalidConfig,JSON.stringify({...shorthandPolicy,files:["bootstrap.sh",{from:"diagnose.ps1",to:"diagnose.ps1",requried:true}]}));
await writeFile(invalidOutput,"");
assert.throws(()=>execFileSync(process.execPath,[join(automation,"dist/distribute.cjs")],{env:{...sourceEnv,INPUT_CONFIG:invalidConfig,GITHUB_OUTPUT:invalidOutput},encoding:"utf8"}),error=>{
  assert.equal(error.status,1);assert.match(error.stdout,/invalid\.json":1:\d+: Unknown key "requried"/);
  assert.match(error.stdout,/files\[1\]\.requried/);return true;
});
assert.equal(await readFile(invalidOutput,"utf8"),"");
await writeFile("release-set-contract/result.json",JSON.stringify({schema:1,kind:"distribution-contract",candidate:env.AUTOMATION_SHA,
  sourceCommit:env.GITHUB_SHA,runId:env.GITHUB_RUN_ID,attempt:env.GITHUB_RUN_ATTEMPT,platform:env.RUNNER_OS,
  shorthandEqual:true,invalidKeyRejected:true,legacyReport,shorthandReport},null,2)+"\n");
console.log("public bundle: unversioned mixed files/aliases equal legacy policy and bytes; invalid key location verified");
