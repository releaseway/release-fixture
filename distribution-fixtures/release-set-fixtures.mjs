import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir,readFile,writeFile } from "node:fs/promises";
import { resolve,join } from "node:path";
import { pathToFileURL } from "node:url";

export const versions=["0.9.0","1.0.0","1.1.0","1.3.0-beta.1","2.0.0","partial-v1.0.0"];
export function payload(version) {
  if(version==="0.9.0")return {};
  const files={"bootstrap.sh":`#!/bin/sh\nprintf '%s\\n' 'release-set:${version}'\n`};
  if(version!=="partial-v1.0.0")Object.assign(files,{
    "diagnose.ps1":`Write-Output 'release-set:${version}'\n`,
    "metadata.json":JSON.stringify({version})+"\n",
  });
  return files;
}
export function docs(phase) {
  return {"index.html":`<!doctype html><title>Release set ${phase}</title>\n`,
    ".well-known/release-set.json":JSON.stringify({phase})+"\n"};
}
export async function build(phase) {
  assert.ok(["initial","final"].includes(phase));
  const policy=JSON.parse(await readFile(`.github/distribution/release-set-${phase}.json`,"utf8"));
  const selected=phase==="initial"?versions:["1.2.0"];
  for(const version of selected){
    const dir=join("release-set-payload",version);await mkdir(dir,{recursive:true});
    for(const [name,bytes]of Object.entries(payload(version)))await writeFile(join(dir,name),bytes);
  }
  for(const [name,bytes]of Object.entries(docs(phase))){
    const target=join(`release-set-site-${phase}`,name);await mkdir(resolve(target,".."),{recursive:true});await writeFile(target,bytes);
  }
  return policy;
}
function gh(args,optional=false){
  try{return execFileSync("gh",args,{encoding:"utf8",stdio:["ignore","pipe","pipe"]});}
  catch(e){if(optional&&String(e.stderr).includes("HTTP 404"))return null;throw e;}
}
function api(endpoint,optional=false){const out=gh(["api","--hostname","github.com",endpoint],optional);return out===null?null:JSON.parse(out);}
export async function publish(phase) {
  const env=process.env,repo=env.GITHUB_REPOSITORY;
  assert.equal(repo,"releaseway/release-fixture");assert.match(env.GITHUB_SHA,/^[a-f0-9]{40}$/);
  const policy=await build(phase),prefix=policy.releases["tag-prefix"];
  const latest=api(`repos/${repo}/releases/latest`),stable={id:latest.id,tag:latest.tag_name};
  for(const version of phase==="initial"?versions:["1.2.0"]){
    const tag=prefix+version,endpoint=`repos/${repo}/releases/tags/${encodeURIComponent(tag)}`;
    let release=api(endpoint,true);
    if(!release){
      gh(["release","create",tag,...Object.keys(payload(version)).map(n=>join("release-set-payload",version,n)),"--repo",repo,"--target",env.GITHUB_SHA,"--prerelease","--latest=false","--title",tag,"--notes","Isolated release-set acceptance fixtures."]);
      release=api(endpoint);
    }
    const ref=api(`repos/${repo}/git/ref/tags/${encodeURIComponent(tag)}`);
    assert.deepEqual(ref.object,{...ref.object,type:"commit",sha:env.GITHUB_SHA},"campaign prefix already belongs to another source commit; commit a fresh prefix");
    assert.equal(release.prerelease,true);assert.equal(release.draft,false);
    const assets=api(`repos/${repo}/releases/${release.id}/assets?per_page=100`),expected=payload(version);
    assert.equal(assets.length,Object.keys(expected).length);
    for(const a of assets){const bytes=expected[a.name];assert.equal(typeof bytes,"string");assert.equal(a.size,Buffer.byteLength(bytes));assert.equal(a.state,"uploaded");assert.equal(a.digest,"sha256:"+createHash("sha256").update(bytes).digest("hex"));}
  }
  const after=api(`repos/${repo}/releases/latest`);assert.deepEqual({id:after.id,tag:after.tag_name},stable,"fixture publishing changed latest stable");
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  const [operation,phase]=process.argv.slice(2);assert.ok(["build","publish"].includes(operation));
  await (operation==="build"?build(phase):publish(phase));
}
