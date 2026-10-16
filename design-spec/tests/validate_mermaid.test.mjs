// Tests for skill/tools/validate_mermaid.mjs. Run from the repository root:
//   node --test --experimental-test-coverage --test-coverage-include="design-spec/skill/tools/*.mjs" \
//     --test-coverage-lines=100 --test-coverage-branches=100 "design-spec/tests/*.test.mjs"
// The parser tests use the real pinned packages from the shared cache, installing them on first run.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";
import { after, before, describe, test } from "node:test";
import { fileURLToPath } from "node:url";

import { PINS, cacheDir, checkFile, ensureDeps, extractDiagrams, loadParser, main, npmInstall } from "../skill/tools/validate_mermaid.mjs";

const SCRIPT = fileURLToPath(new URL("../skill/tools/validate_mermaid.mjs", import.meta.url));
const GOOD = "flowchart LR\n    A --> B\n";
const BAD = "flowchart LR\n    A --> (\n";
const work = mkdtempSync(join(tmpdir(), "validate-mermaid-"));
after(() => rmSync(work, { recursive: true, force: true }));

function file(name, text) {
    const path = join(work, name);
    writeFileSync(path, text);
    return path;
}

function fakePackages(dir, versions, withLoader) {
    for (const [name, version] of Object.entries(versions)) {
        mkdirSync(join(dir, "node_modules", name), { recursive: true });
        writeFileSync(join(dir, "node_modules", name, "package.json"), JSON.stringify({ version }));
    }
    if (withLoader) {
        writeFileSync(join(dir, "loader.mjs"), "");
    }
}

function capture() {
    const io = { outText: "", errText: "" };
    io.out = (text) => { io.outText += text; };
    io.err = (text) => { io.errText += text; };
    return io;
}

describe("extractDiagrams", () => {
    test("returns each mermaid block in Markdown with the line its fence opens on", () => {
        const text = "# Title\n\n```mermaid\nflowchart LR\n  A --> B\n```\n\ntext\n```mermaid\r\nstateDiagram-v2\n  [*] --> A\n```\n";
        assert.deepEqual(extractDiagrams("design.md", text), [
            { line: 3, source: "flowchart LR\n  A --> B\n" },
            { line: 9, source: "stateDiagram-v2\n  [*] --> A\n" },
        ]);
    });

    test("ignores non-mermaid fences in Markdown", () => {
        assert.deepEqual(extractDiagrams("README.MD", "```python\nx = 1\n```\n"), []);
    });

    test("treats a whole .mmd or .mermaid file as one diagram", () => {
        assert.deepEqual(extractDiagrams("a.mmd", GOOD), [{ line: 1, source: GOOD }]);
        assert.deepEqual(extractDiagrams("a.mermaid", GOOD), [{ line: 1, source: GOOD }]);
    });

    test("returns nothing for other file types", () => {
        assert.deepEqual(extractDiagrams("main.py", "```mermaid\nflowchart LR\n```\n"), []);
    });
});

describe("cacheDir", () => {
    test("uses DESIGN_SPEC_MERMAID_CACHE when set", () => {
        assert.equal(cacheDir({ DESIGN_SPEC_MERMAID_CACHE: "/x/cache" }, "/home/u"), "/x/cache");
    });

    test("defaults to ~/.cache/design-spec-mermaid", () => {
        assert.equal(cacheDir({}, "/home/u"), join("/home/u", ".cache", "design-spec-mermaid"));
    });
});

describe("ensureDeps", () => {
    test("does nothing when the pinned versions and the loader are present", () => {
        const dir = mkdtempSync(join(work, "deps-"));
        fakePackages(dir, PINS, true);
        const calls = [];
        assert.equal(ensureDeps(dir, (...args) => { calls.push(args); return { status: 0 }; }), dir);
        assert.deepEqual(calls, []);
    });

    test("installs the exact pins and writes the loader when the cache is empty", () => {
        const dir = join(work, "fresh", "cache");
        const calls = [];
        ensureDeps(dir, (...args) => { calls.push(args); return { status: 0 }; });
        assert.deepEqual(calls, [[dir, [`mermaid@${PINS.mermaid}`, `jsdom@${PINS.jsdom}`]]]);
        assert.match(readFileSync(join(dir, "loader.mjs"), "utf8"), /import\("mermaid"\)/);
    });

    test("reinstalls when an installed version differs from its pin", () => {
        const dir = mkdtempSync(join(work, "deps-"));
        fakePackages(dir, { ...PINS, mermaid: "0.0.1" }, true);
        const calls = [];
        ensureDeps(dir, (...args) => { calls.push(args); return { status: 0 }; });
        assert.equal(calls.length, 1);
    });

    test("reinstalls when the loader is missing", () => {
        const dir = mkdtempSync(join(work, "deps-"));
        fakePackages(dir, PINS, false);
        const calls = [];
        ensureDeps(dir, (...args) => { calls.push(args); return { status: 0 }; });
        assert.equal(calls.length, 1);
    });

    test("throws with npm's error output when the install fails", () => {
        const dir = mkdtempSync(join(work, "deps-"));
        assert.throws(() => ensureDeps(dir, () => ({ status: 1, stderr: "ENOTFOUND registry" })), /npm install failed .*ENOTFOUND registry/);
        assert.equal(existsSync(join(dir, "loader.mjs")), false);
    });
});

describe("npmInstall", () => {
    test("runs npm install in the given folder", () => {
        const dir = mkdtempSync(join(work, "npm-"));
        writeFileSync(join(dir, "package.json"), '{ "private": true }\n');
        assert.equal(npmInstall(dir, []).status, 0);
    });
});

describe("with the real parser", () => {
    let parse;
    before(async () => {
        parse = await loadParser(ensureDeps(cacheDir(process.env, homedir())));
    });

    test("accepts flowchart, state, and C4 diagrams and names their type", async () => {
        assert.deepEqual(await parse(GOOD), { ok: true, detail: "flowchart-v2" });
        assert.deepEqual(await parse("stateDiagram-v2\n    [*] --> Landed\n"), { ok: true, detail: "stateDiagram" });
        assert.equal((await parse('C4Context\n    System(s, "Pipeline")\n')).ok, true);
    });

    test("rejects a broken diagram with the parser's message", async () => {
        const result = await parse(BAD);
        assert.equal(result.ok, false);
        assert.match(result.detail, /Parse error/);
    });

    test("checkFile reports each block of a Markdown file", async () => {
        const path = file("mixed.md", "```mermaid\n" + GOOD + "```\n\n```mermaid\n" + BAD + "```\n");
        const results = await checkFile(path, async () => parse);
        assert.deepEqual(results.map((r) => [r.block, r.line, r.ok]), [[1, 1, true], [2, 6, false]]);
    });

    test("checkFile does not load the parser for a file without diagrams", async () => {
        const path = file("plain.md", "# No diagrams\n");
        assert.deepEqual(await checkFile(path, async () => assert.fail("parser loaded")), []);
    });

    describe("main as a CLI", () => {
        test("prints usage and exits 2 without arguments", async () => {
            const io = capture();
            assert.equal(await main([], io), 2);
            assert.match(io.errText, /usage/);
        });

        test("reports OK for every block, notes files without diagrams, and loads the parser once", async () => {
            const io = capture();
            let loads = 0;
            io.getParse = async () => { loads += 1; return parse; };
            const code = await main([file("good.md", "```mermaid\n" + GOOD + "```\n"), file("good.mmd", GOOD), file("none.md", "text\n")], io);
            assert.equal(code, 0);
            assert.equal(loads, 1);
            assert.match(io.outText, /good\.md: block 1 \(line 1\): OK flowchart-v2/);
            assert.match(io.outText, /good\.mmd: block 1 \(line 1\): OK/);
            assert.match(io.outText, /none\.md: no Mermaid diagrams/);
        });

        test("exits 1 when any block fails", async () => {
            const io = capture();
            io.getParse = async () => parse;
            assert.equal(await main([file("bad.mermaid", BAD)], io), 1);
            assert.match(io.outText, /bad\.mermaid: block 1 \(line 1\): FAIL .*Parse error/);
        });
    });

    describe("main as a hook", () => {
        const hookInput = (path) => () => JSON.stringify({ tool_name: "Write", tool_input: { file_path: path } });

        test("exits 0 silently for a file type it does not check", async () => {
            const io = capture();
            io.stdin = hookInput(file("x.py", "print(1)\n"));
            io.getParse = async () => assert.fail("parser loaded");
            assert.equal(await main(["--hook"], io), 0);
            assert.equal(io.errText, "");
        });

        test("exits 0 silently when every diagram parses", async () => {
            const io = capture();
            io.stdin = hookInput(file("ok.md", "```mermaid\n" + GOOD + "```\n"));
            io.getParse = async () => parse;
            assert.equal(await main(["--hook"], io), 0);
            assert.equal(io.errText, "");
        });

        test("exits 2 and lists each failing block on stderr", async () => {
            const io = capture();
            const path = file("broken.md", "intro\n\n```mermaid\n" + BAD + "```\n");
            io.stdin = hookInput(path);
            io.getParse = async () => parse;
            assert.equal(await main(["--hook"], io), 2);
            assert.match(io.errText, /broken\.md: block 1 \(line 3\): FAIL .*Parse error/);
            assert.match(io.errText, /Fix the failing Mermaid diagram/);
        });

        test("exits 2 with the reason when the checker cannot run", async () => {
            const io = capture();
            io.stdin = hookInput(file("needs.md", "```mermaid\n" + GOOD + "```\n"));
            io.getParse = async () => { throw new Error("npm install failed: offline"); };
            assert.equal(await main(["--hook"], io), 2);
            assert.match(io.errText, /Mermaid check could not run: npm install failed: offline/);
        });
    });
});

describe("the script", () => {
    test("runs as a CLI and sets its exit code", () => {
        const result = spawnSync(process.execPath, [SCRIPT, file("cli.mmd", BAD)], { encoding: "utf8" });
        assert.equal(result.status, 1, result.stderr);
        assert.match(result.stdout, /cli\.mmd: block 1 \(line 1\): FAIL/);
    });

    test("runs as a hook reading JSON on stdin", () => {
        const input = JSON.stringify({ tool_input: { file_path: file("hook.md", "```mermaid\n" + BAD + "```\n") } });
        const result = spawnSync(process.execPath, [SCRIPT, "--hook"], { input, encoding: "utf8" });
        assert.equal(result.status, 2);
        assert.match(result.stderr, /hook\.md: block 1 \(line 1\): FAIL/);
    });
});
