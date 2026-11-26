import assert from "node:assert/strict";
import { test } from "node:test";
import { LANGUAGES, responseDuration, messageTime, translate } from "../src/locale.js";

test("supported languages translate UI labels and preserve unknown source text", () => {
  assert.deepEqual(LANGUAGES.map((l) => l.code), ["en", "uz", "ko"]);
  assert.equal(translate("uz", "Thinking…"), "O‘ylanmoqda…");
  assert.equal(translate("ko", "Thinking…"), "생각 중…");
  assert.equal(translate("en", "Thinking…"), "Thinking…");
  assert.equal(translate("ko", "Actual_filename.csv"), "Actual_filename.csv");
});

test("message dates omit the year and retain each message's actual time", () => {
  const sent = new Date(2026, 10, 18, 17, 40).toISOString();
  const finished = new Date(2026, 10, 18, 17, 44).toISOString();
  for (const language of ["en", "uz", "ko"]) {
    assert.doesNotMatch(messageTime(finished, language), /2026/);
    assert.match(messageTime(finished, language), /18/);
    assert.match(messageTime(finished, language), /17:44/);
    assert.match(messageTime(sent, language), /17:40/);
  }
  assert.match(messageTime(finished, "en"), /18 Nov/);
  assert.equal(messageTime("invalid", "en"), "");
  assert.equal(messageTime(null, "en"), "");
  assert.equal(messageTime(undefined, "en"), "");
});

test("response duration uses real recorded values, with no invented zero", () => {
  const run = { wall_seconds: 12.345 };
  assert.equal(responseDuration(run, "en"), "12.3 s");
  assert.equal(responseDuration({ metrics: { inference_seconds: 0 } }, "en"), "0 s");
  assert.equal(responseDuration({}, "en"), "");
});
