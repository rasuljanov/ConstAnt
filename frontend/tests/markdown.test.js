import assert from "node:assert/strict";
import { test } from "node:test";
import { renderMarkdown } from "../src/markdown.js";

test("legacy collection labels are omitted while record references remain", () => {
  const html = renderMarkdown("Measured peak [file-123] at 11:19.\n\n[Selected tables]");
  assert.doesNotMatch(html, /selected tables/i);
  assert.match(html, /\[file-123\]/);
});

test("chat renders emphasis, lists, and tables", () => {
  const output = renderMarkdown(
    "**27 sensor CSV files**\n\n- PM2.5 and PM10\n- Weather readings\n\n| Field | Unit |\n|---|---|\n| PM2.5 | μg/m³ |",
  );
  assert.match(output, /<strong>27 sensor CSV files<\/strong>/);
  assert.match(output, /<ul>/);
  assert.match(output, /<li>PM2.5 and PM10<\/li>/);
  assert.match(output, /<table>/);
  assert.match(output, /<td>μg\/m³<\/td>/);
});

test("model text cannot execute HTML, javascript links, or remote images", () => {
  const output = renderMarkdown(
    "<script>alert(1)</script>\n<img src=x onerror=alert(1)>\n\n[bad](javascript:alert(1))\n\n![tracking](https://example.com/pixel.png)\n\n[reference](https://example.com)",
  );
  assert.doesNotMatch(output, /<script|<img|href="javascript:/);
  assert.match(output, /&lt;script&gt;/);
  assert.match(output, /rel="noopener noreferrer"/);
  assert.match(output, /tracking/);
});
