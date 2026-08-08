import { readdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const directory = resolve('n8n-workflows/public');
const files = (await readdir(directory)).filter((file) => file.endsWith('.json')).sort();

if (files.length !== 3) {
  throw new Error(`Expected 3 public workflow files, found ${files.length}`);
}

for (const file of files) {
  const workflow = JSON.parse(await readFile(resolve(directory, file), 'utf8'));
  if (!workflow.name || !Array.isArray(workflow.nodes) || workflow.nodes.length === 0) {
    throw new Error(`${file} is not a valid n8n workflow export`);
  }
  if (workflow.active !== false) {
    throw new Error(`${file} must be inactive in the public template`);
  }
  if (workflow.id || workflow.versionId || workflow.activeVersionId || workflow.shared) {
    throw new Error(`${file} contains private n8n instance metadata`);
  }
  if (workflow.nodes.some((node) => !node.id || !node.name || !node.type || !Array.isArray(node.position))) {
    throw new Error(`${file} contains an incomplete node definition`);
  }
  for (const node of workflow.nodes) {
    const jsCode = node.parameters?.jsCode;
    if (typeof jsCode === 'string' && /\b(True|False|None)\b/.test(jsCode)) {
      throw new Error(`${file} contains Python-style literals in JavaScript node: ${node.name}`);
    }
  }
  const nodeNames = new Set(workflow.nodes.map((node) => node.name));
  if (file === '04-video-generation.json') {
    const prep = workflow.nodes.find((node) => /^整理.*参数/.test(node.name));
    const statusQuery = workflow.nodes.find((node) => node.name === 'Seedance 2.0｜查询生成状态');
    const prepCode = prep?.parameters?.jsCode || '';
    if (!prep || !prepCode.includes('selectedMoodBoard') || !prepCode.includes('成片禁止任何字幕') || prepCode.includes('"字幕："+(shot.subtitle')) {
      throw new Error(`${file} must pass the full Mood Board to Stage 4 and strip subtitles before video generation`);
    }
    if (!statusQuery || statusQuery.retryOnFail !== true || statusQuery.maxTries !== 4 || statusQuery.waitBetweenTries !== 10000) {
      throw new Error(`${file} must retry Seedance status queries after transient network failures`);
    }
  }
  for (const [sourceName, outputs] of Object.entries(workflow.connections || {})) {
    if (!nodeNames.has(sourceName)) throw new Error(`${file} has an unknown connection source: ${sourceName}`);
    for (const branches of Object.values(outputs || {})) {
      for (const branch of branches || []) {
        for (const connection of branch || []) {
          if (!nodeNames.has(connection.node)) {
            throw new Error(`${file} connects to an unknown node: ${connection.node}`);
          }
        }
      }
    }
  }
}

console.log(`Validated ${files.length} public n8n workflow templates.`);
