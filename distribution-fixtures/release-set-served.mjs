import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";
const {verifyServed}=await import(pathToFileURL(resolve("automation/src/distribution/verify-served.ts")));
const report=JSON.parse(await readFile(process.argv[2],"utf8"));
await verifyServed(process.env.PAGE_URL,report.files);
