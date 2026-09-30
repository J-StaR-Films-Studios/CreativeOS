import assert from "node:assert/strict";
import test from "node:test";
import { findProjectForItem } from "../src/js/projectSelection.js";

const projects = [
  { name: "Same", slug: "Same", path: "C:/Projects/Video/Same" },
  { name: "Same", slug: "Same", path: "C:/Projects/Code/Same" },
];

test("duplicate titles never override the selected filesystem path", () => {
  const selected = { name: "Same", path: "c:\\projects\\code\\Same" };
  assert.equal(findProjectForItem(projects, selected), projects[1]);
  assert.equal(findProjectForItem(projects, selected, true), projects[1]);
  assert.equal(findProjectForItem(projects, { name: "Same", path: "C:/Untracked/Same" }), null);
});

test("selected descendants belong only to their containing project", () => {
  const selected = { name: "Same", path: "C:/Projects/Code/Same/notes.txt" };
  assert.equal(findProjectForItem(projects, selected), null);
  assert.equal(findProjectForItem(projects, selected, true), projects[1]);
  assert.equal(findProjectForItem(projects, { path: "C:/Projects/Code/Same-other/a.txt" }, true), null);
});
