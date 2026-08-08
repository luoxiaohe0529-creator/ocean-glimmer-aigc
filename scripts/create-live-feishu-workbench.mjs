import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const cli = process.env.LARK_CLI || "lark-cli";
const schemaPath = process.env.FEISHU_SCHEMA || "";
const baseHost = process.env.FEISHU_BASE_HOST || "pcn7bpsihajy.feishu.cn";
const sourceBaseToken = process.env.SOURCE_FEISHU_BASE_TOKEN || "";
const sourceTableId = process.env.SOURCE_FEISHU_TABLE_ID || "";
const args = new Set(process.argv.slice(2));
const contentTypeArg = process.argv.find((value) => value.startsWith("--content-type="));
const contentType = contentTypeArg ? contentTypeArg.slice("--content-type=".length) : "";

if (process.env.CREATE_FEISHU_WORKBENCH !== "YES") {
  console.error("This creates a new Feishu Base and does not change the old Bases.");
  console.error("Run again with: CREATE_FEISHU_WORKBENCH=YES node scripts/create-live-feishu-workbench.mjs");
  process.exit(2);
}

if (!schemaPath) {
  console.error("请设置 FEISHU_SCHEMA，指向飞书多维表格 schema JSON 文件。");
  process.exit(2);
}

const schema = JSON.parse(readFileSync(schemaPath, "utf8"));

function parseJsonOutput(stdout) {
  const trimmed = stdout.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    const start = trimmed.indexOf("{");
    const end = trimmed.lastIndexOf("}");
    if (start >= 0 && end > start) return JSON.parse(trimmed.slice(start, end + 1));
    throw new Error("CLI did not return JSON:\n" + trimmed);
  }
}

function runCli(cliArgs) {
  const result = spawnSync(cli, [
    ...cliArgs,
    "--as", "user",
    "--format", "json"
  ], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024
  });

  if (result.error) throw result.error;
  if (result.status !== 0) {
    throw new Error("lark-cli failed (" + result.status + "):\n" + (result.stderr || result.stdout));
  }

  const response = parseJsonOutput(result.stdout);
  if (response.ok === false) {
    throw new Error("lark-cli returned an error:\n" + JSON.stringify(response.error || response));
  }
  return response;
}

function collectObjects(value, predicate, output = []) {
  if (!value || typeof value !== "object") return output;
  if (Array.isArray(value)) {
    for (const item of value) collectObjects(item, predicate, output);
    return output;
  }
  if (predicate(value)) output.push(value);
  for (const child of Object.values(value)) collectObjects(child, predicate, output);
  return output;
}

function isTableId(value) {
  return typeof value === "string" && value.startsWith("tbl");
}

function tableIdFromObject(value) {
  for (const key of ["table_id", "tableId", "table_token", "tableToken", "id"]) {
    if (isTableId(value[key])) return value[key];
  }
  return undefined;
}

function findId(response, key) {
  const objects = collectObjects(response, (value) => typeof value[key] === "string");
  return objects.map((value) => value[key]).find((value) => value.length > 0);
}

function findTableIdByName(response, tableName) {
  const objects = collectObjects(response, (value) => {
    return tableIdFromObject(value) &&
      ["name", "table_name", "tableName", "title"].some((key) => value[key] === tableName);
  });
  return objects.map(tableIdFromObject).find(Boolean);
}

function toCliField(field) {
  if (field.type === "url") {
    return { name: field.name, type: "text", style: { type: "url" } };
  }
  if (field.type === "single_select") {
    return {
      name: field.name,
      type: "select",
      multiple: false,
      options: (field.options || []).map((name) => ({ name }))
    };
  }
  if (field.type === "number") {
    return { name: field.name, type: "number" };
  }
  if (field.type === "attachment") {
    return { name: field.name, type: "attachment" };
  }
  if (field.type === "text") {
    return { name: field.name, type: "text" };
  }
  return null;
}

function normalFields(table, primaryName) {
  const fields = table.fields
    .filter((field) => !field.system && !["link", "formula", "created_time"].includes(field.type))
    .map(toCliField)
    .filter(Boolean);
  const primary = fields.find((field) => field.name === primaryName) || fields[0];
  return [primary, ...fields.filter((field) => field.name !== primary.name)];
}

function getTableId(baseToken, tableName, response) {
  return findTableIdByName(response, tableName) ||
    findTableIdByName(runCli(["base", "+table-list", "--base-token", baseToken]), tableName);
}

function findBaseToken(response, baseName) {
  const objects = collectObjects(response, (value) => {
    const token = ["base_token", "baseToken", "app_token", "appToken", "token"]
      .map((key) => value[key])
      .find((candidate) => typeof candidate === "string" && !isTableId(candidate));
    const url = ["url", "base_url", "baseUrl", "link"]
      .map((key) => value[key])
      .find((candidate) => typeof candidate === "string" && candidate.includes("/base/"));
    if (!token && !url) return false;
    if (!baseName) return true;
    return ["name", "base_name", "baseName", "title"].some((key) => value[key] === baseName);
  });
  return objects.map((value) => {
    for (const key of ["base_token", "baseToken", "app_token", "appToken", "token"]) {
      if (typeof value[key] === "string" && !isTableId(value[key])) return value[key];
    }
    for (const key of ["url", "base_url", "baseUrl", "link"]) {
      const match = typeof value[key] === "string" && value[key].match(/\/base\/([^/?]+)/);
      if (match) return match[1];
    }
    return undefined;
  }).find(Boolean);
}

function safeRunCli(cliArgs) {
  try {
    return runCli(cliArgs);
  } catch {
    return null;
  }
}

function resolveExistingBase(baseName) {
  const response = safeRunCli(["base", "+title-resolve", "--title", baseName]);
  if (!response) return undefined;
  return findBaseToken(response, baseName) || findBaseToken(response);
}

function tableList(baseToken) {
  return runCli(["base", "+table-list", "--base-token", baseToken]);
}

function existingFieldNames(baseToken, tableId) {
  const response = safeRunCli([
    "base", "+field-list",
    "--base-token", baseToken,
    "--table-id", tableId
  ]);
  if (!response) return new Set();
  const fields = collectObjects(response, (value) => {
    return typeof value.name === "string" &&
      (typeof value.id === "string" || typeof value.field_id === "string" || typeof value.fieldId === "string");
  });
  return new Set(fields.map((field) => field.name));
}

function existingProductNames(baseToken, tableId) {
  const response = safeRunCli([
    "base", "+record-list",
    "--base-token", baseToken,
    "--table-id", tableId,
    "--limit", "200"
  ]);
  if (!response) return new Set();
  return new Set(sourceRecords(response)
    .map((record) => sourceField(record, "项目名称"))
    .filter(Boolean));
}

function cellText(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) return value.map(cellText).filter(Boolean).join("、");
  if (typeof value === "object") {
    for (const key of ["text", "value", "name", "url"]) {
      if (value[key] !== undefined) return cellText(value[key]);
    }
    return JSON.stringify(value);
  }
  return "";
}

function sourceRecords(response) {
  return collectObjects(response, (value) => {
    const ids = [
      value.record_id,
      value._record_id,
      value.recordId,
      value.id,
      value.record?.record_id,
      value.record?.recordId,
      value.record?.id
    ];
    const fields = value.fields || value.properties || value.record?.fields || value.record?.properties;
    return ids.some((id) => typeof id === "string" && (id.startsWith("rec") || id.length > 8)) && Boolean(fields);
  });
}

function sourceField(record, name) {
  const fields = record.fields || record.properties || record.record?.fields || record.record?.properties || {};
  if (Array.isArray(fields)) {
    const match = fields.find((field) => field.name === name || field.field_name === name || field.fieldName === name);
    return cellText(match?.value ?? match?.text ?? match?.cell_value);
  }
  if (fields[name] !== undefined) return cellText(fields[name]);
  return cellText(fields[name.trim()]);
}

async function main() {
  const product = schema.tables.product;
  const hook = schema.tables.hook;
  const script = schema.tables.script;
  const video = schema.tables.video;

  const baseName = "AI视频工厂工作台";
  let baseToken = process.env.FEISHU_BASE_TOKEN || resolveExistingBase(baseName);
  let created = null;

  if (baseToken) {
    console.log("Reusing existing Feishu Base: " + baseToken);
  } else {
    console.log("Creating a new Feishu Base...");
    created = runCli([
      "base", "+base-create",
      "--name", baseName,
      "--time-zone", "Asia/Shanghai",
      "--table-name", product.name,
      "--fields", JSON.stringify(normalFields(product, "项目名称"))
    ]);
    baseToken = findId(created, "base_token") || findBaseToken(created);
  }
  if (!baseToken) throw new Error("Cannot find base_token in create response:\n" + JSON.stringify(created));

  const tableIds = {};
  tableIds.product = getTableId(baseToken, product.name, created || tableList(baseToken));
  if (!tableIds.product) {
    throw new Error("Cannot find the first table ID. Set FEISHU_BASE_TOKEN to the Base token and rerun.");
  }

  for (const [key, table] of [["hook", hook], ["script", script], ["video", video]]) {
    const existing = findTableIdByName(tableList(baseToken), table.name);
    if (existing) {
      console.log("Reusing table: " + table.name);
      tableIds[key] = existing;
      continue;
    }
    console.log("Creating table: " + table.name);
    const response = runCli([
      "base", "+table-create",
      "--base-token", baseToken,
      "--name", table.name,
      "--fields", JSON.stringify(normalFields(table, {
        hook: "Hook概念",
        script: "脚本标题",
        video: "视频标题"
      }[key]))
    ]);
    tableIds[key] = getTableId(baseToken, table.name, response);
    if (!tableIds[key]) throw new Error("Cannot find table ID for " + table.name + ".");
  }

  for (const [key, table] of Object.entries(schema.tables)) {
    const fieldNames = existingFieldNames(baseToken, tableIds[key]);
    for (const field of table.fields.filter((item) => item.type === "link")) {
      if (fieldNames.has(field.name)) {
        console.log("Reusing link: " + table.name + "." + field.name);
        continue;
      }
      console.log("Creating link: " + table.name + "." + field.name);
      runCli([
        "base", "+field-create",
        "--base-token", baseToken,
        "--table-id", tableIds[key],
        "--json", JSON.stringify({
          name: field.name,
          type: "link",
          link_table: tableIds[field.linkedTable]
        })
      ]);
    }
  }

  if (!args.has("--no-migrate")) {
    if (!sourceBaseToken || !sourceTableId) {
      throw new Error("迁移旧数据前请设置 SOURCE_FEISHU_BASE_TOKEN 和 SOURCE_FEISHU_TABLE_ID；不迁移请使用 --no-migrate。");
    }
    console.log("Migrating populated strategy cases...");
    const sourceResponse = runCli([
      "base", "+record-list",
      "--base-token", sourceBaseToken,
      "--table-id", sourceTableId,
      "--limit", "200"
    ]);
    const records = sourceRecords(sourceResponse);
    const migratedNames = existingProductNames(baseToken, tableIds.product);
    let migrated = 0;
    for (const record of records) {
      const projectName = sourceField(record, "项目名称");
      const productInfo = sourceField(record, "产品信息");
      if (!projectName && !productInfo) continue;
      if (projectName && migratedNames.has(projectName)) {
        console.log("Skipping existing case: " + projectName);
        continue;
      }

      const fields = {
        "项目名称": projectName,
        "产品名称": productInfo,
        "产品信息": productInfo,
        "核心卖点": sourceField(record, "核心卖点"),
        "目标人群": sourceField(record, "目标用户"),
        "用户手动备注": sourceField(record, "项目目标"),
        "卖点转译规则": sourceField(record, "卖点转译规则"),
        "场景/地标资源": sourceField(record, "场景/地标资源"),
        "核心视觉资产": sourceField(record, "核心视觉资产"),
        "Campaign主题与口播": sourceField(record, "Campaign主题与口播"),
        "甲方限制": sourceField(record, "甲方限制"),
        "状态": "待生成",
        "提取状态": "已提取",
        "确认状态": "待确认"
      };
      if (contentType) fields["内容类型"] = contentType;
      for (const [key, value] of Object.entries(fields)) {
        if (!value) delete fields[key];
      }
      runCli([
        "base", "+record-upsert",
        "--base-token", baseToken,
        "--table-id", tableIds.product,
        "--json", JSON.stringify(fields)
      ]);
      if (projectName) migratedNames.add(projectName);
      migrated += 1;
    }
    console.log("Migrated " + migrated + " populated case records.");
  }

  console.log("");
  console.log("BASE_TOKEN=" + baseToken);
  console.log("PRODUCT_TABLE_ID=" + tableIds.product);
  console.log("HOOK_TABLE_ID=" + tableIds.hook);
  console.log("SCRIPT_TABLE_ID=" + tableIds.script);
  console.log("VIDEO_TABLE_ID=" + tableIds.video);
  console.log("BASE_URL=https://" + baseHost + "/base/" + baseToken);
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exit(1);
});
